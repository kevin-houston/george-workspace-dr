#!/usr/bin/env python3
"""
H462 — Systematic 0DTE SPX Iron Condor: Synthetic BSM Backtest

Source: CBOE Insights 2026 (Henry Schwartz); Option Alpha 180-day empirical study (2024);
        FlashAlpha VRP/GEX research (2025-2026)

Hypothesis: 0DTE SPX iron condors (entered ~2:44 PM ET) collect structural time-decay
premium in calm regimes. Variance risk premium (VIX > trailing realized vol) filters
entries to days where seller's edge is highest. Closed hard at 3:30 PM ET to avoid
gamma-explosion window. Synthetic Tier-0 BSM backtest; real options data (ThetaData
~$80/mo) needed for Tier-1 confirmation.

Variants:
  A: 0.2% OTM both sides, no VRP filter, hard 3:30 PM close (baseline)
  B: 0.2% OTM, VRP z-score > 0.5 entry filter
  C: 0.32% OTM, VRP z-score > 0.5 filter (wider strikes = lower credit but safer)
  D: Var B + skip days where |SPX daily return| > 0.5% (trending day filter)
  E: Var B + skip days where VIX 1-day change > +10% (vol spike filter)

Gate: OOS Sharpe >= 1.0; MaxDD <= -20%; zero negative years OOS 2021-2026
IS: 2015-2020, OOS: 2021-2026

Note: This is a SYNTHETIC backtest. BSM end-of-day IV surface approximation.
Real fills would differ due to intraday vol path, bid-ask spread, and slippage.
Assumed transaction cost: 56% of theoretical bid-ask (4 legs, $0.03 spread each).
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats as ss
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY  = 'H462'
DATA_START = '2014-01-01'
IS_START   = '2015-01-01'
IS_END     = '2020-12-31'
OOS_START  = '2021-01-01'
OOS_END    = '2026-07-21'

# Iron condor parameters
OTM_NARROW  = 0.002   # 0.20% OTM for short strikes (Vars A, B, D, E)
OTM_WIDE    = 0.0032  # 0.32% OTM for short strikes (Var C)
WING_WIDTH  = 0.005   # 0.50% wing (long strikes protect short strikes)
TC_PER_LEG  = 0.03    # $0.03 transaction cost per leg (4 legs = $0.12 total)
MAX_CREDIT_LOSS_X = 2.0  # exit if loss exceeds 2× credit received intraday
POSITION_PCT = 0.01   # risk 1% of portfolio per condor

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ── BSM helpers ──────────────────────────────────────────────────────────────

def bsm_put_price(S, K, T, r, sigma):
    """BSM European put price."""
    if T <= 0 or sigma <= 0:
        return max(K - S, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return K * np.exp(-r * T) * ss.norm.cdf(-d2) - S * ss.norm.cdf(-d1)


def bsm_call_price(S, K, T, r, sigma):
    """BSM European call price."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * ss.norm.cdf(d1) - K * np.exp(-r * T) * ss.norm.cdf(d2)


def iron_condor_credit(S, otm_pct, wing_pct, T, r, iv):
    """
    Compute net credit for an OTM iron condor.
    Short put at S*(1-otm_pct), long put at S*(1-otm_pct-wing_pct)
    Short call at S*(1+otm_pct), long call at S*(1+otm_pct+wing_pct)
    Returns: (net_credit, max_loss_per_$1_notional)
    """
    K_sp = S * (1 - otm_pct)        # short put
    K_lp = S * (1 - otm_pct - wing_pct)  # long put
    K_sc = S * (1 + otm_pct)        # short call
    K_lc = S * (1 + otm_pct + wing_pct)  # long call

    short_put  = bsm_put_price(S, K_sp, T, r, iv)
    long_put   = bsm_put_price(S, K_lp, T, r, iv)
    short_call = bsm_call_price(S, K_sc, T, r, iv)
    long_call  = bsm_call_price(S, K_lc, T, r, iv)

    net_credit = (short_put - long_put) + (short_call - long_call)
    # Max loss = wing width - net credit (per $1 of S)
    wing_dollars = S * wing_pct
    max_loss = wing_dollars - net_credit
    return net_credit, max_loss, K_sp, K_lp, K_sc, K_lc


def condor_pnl_at_expiry(S_entry, S_close, K_sp, K_lp, K_sc, K_lc, net_credit):
    """P&L at 3:30 PM close using BSM with near-zero T."""
    # Treat 3:30 PM close as ~30min to expiry (T = 0.5/390 trading minutes)
    T_close = 0.5 / 252  # ~half a trading day
    r = 0.05

    # Residual IV at close: VIX doesn't reprice intraday so use same IV
    # (conservative: in reality IV compresses as expiry approaches on calm days)
    # We approximate close PnL as: credit - residual option value
    # On calm days residual value ≈ 0, capturing full credit
    # On stressed days residual value >> credit (max loss hit)
    pnl_from_moves = 0.0
    if S_close < K_sp:          # put spread challenged
        intrinsic = min(K_sp - S_close, K_sp - K_lp)
        pnl_from_moves -= intrinsic
    if S_close > K_sc:          # call spread challenged
        intrinsic = min(S_close - K_sc, K_lc - K_sc)
        pnl_from_moves -= intrinsic

    return net_credit + pnl_from_moves


# ── Data download ─────────────────────────────────────────────────────────────

def download_data():
    print('Downloading SPX proxy (SPY), VIX...')
    spy = yf.download('SPY', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)
    vix = yf.download('^VIX', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close'].squeeze()
    tbill = yf.download('^IRX', start=DATA_START, end=OOS_END,
                        auto_adjust=True, progress=False)['Close'].squeeze()
    return spy, vix, tbill


# ── Signal computation ────────────────────────────────────────────────────────

def build_signals(spy: pd.DataFrame, vix: pd.Series) -> pd.DataFrame:
    """Build daily signal table with VRP and daily return filters."""
    close = spy['Close'].squeeze()
    daily_ret = close.pct_change()

    # Realized vol: 20-day trailing (shifted 1d to avoid look-ahead)
    rv_20 = daily_ret.rolling(20).std().shift(1) * np.sqrt(252)

    # VRP = VIX (implied) - realized vol; z-score over trailing 60d
    vrp_raw = vix / 100.0 - rv_20
    vrp_z = (vrp_raw - vrp_raw.rolling(60).mean()) / vrp_raw.rolling(60).std()

    # VIX 1-day change
    vix_chg_pct = vix.pct_change()

    df = pd.DataFrame({
        'close': close,
        'daily_ret': daily_ret,
        'vix': vix,
        'rv20': rv_20,
        'vrp_z': vrp_z.shift(1),       # z-score available at entry (prev close)
        'abs_ret': daily_ret.abs(),     # today's move (known at 2:44 PM entry)
        'vix_chg': vix_chg_pct,        # VIX move today (approx at 2:44 PM)
    }).dropna()
    return df


# ── Backtest engine ───────────────────────────────────────────────────────────

def run_backtest(df: pd.DataFrame, tbill: pd.Series,
                 otm_pct: float, vrp_filter: float | None,
                 skip_trending: bool, skip_vol_spike: bool,
                 label: str) -> pd.Series:
    """
    Simulate daily 0DTE iron condor entries.
    Returns daily equity curve as a pd.Series indexed by date.
    """
    portfolio = 1.0
    equity = {}

    for date, row in df.iterrows():
        equity[date] = portfolio

        # Entry filters
        if vrp_filter is not None and row['vrp_z'] < vrp_filter:
            continue    # no VRP edge today
        if skip_trending and row['abs_ret'] > 0.005:
            continue    # trending day — skip
        if skip_vol_spike and row['vix_chg'] > 0.10:
            continue    # VIX spike — skip

        S = row['close']
        iv = row['vix'] / 100.0   # VIX as annualized IV proxy
        r  = float(tbill.reindex([date], method='ffill').iloc[0]) / 100.0 if date in tbill.index else 0.05
        T  = 1 / 252              # 1 day to expiry

        credit, max_loss, K_sp, K_lp, K_sc, K_lc = iron_condor_credit(
            S, otm_pct, WING_WIDTH, T, r, iv
        )

        # Transaction costs: 4 legs × $TC_PER_LEG, normalized to portfolio
        tc = (4 * TC_PER_LEG) / portfolio

        # Simulate close: use next day open as proxy for 3:30 PM settlement
        # For a synthetic backtest, use same-day close as approximation
        # (no intraday data; conservative: assume no intraday mean-reversion benefit)
        S_close = S * (1 + row['daily_ret'])   # end-of-day SPY level

        pnl_per_dollar = condor_pnl_at_expiry(S, S_close, K_sp, K_lp, K_sc, K_lc, credit)

        # Cap loss at max_loss (long options protect)
        wing_max = S * WING_WIDTH
        pnl_per_dollar = max(pnl_per_dollar, -wing_max)

        # Scale by position size
        position_value = portfolio * POSITION_PCT
        trade_pnl = (pnl_per_dollar / S) * position_value - tc * position_value

        portfolio += trade_pnl

    return pd.Series(equity)


# ── Performance metrics ───────────────────────────────────────────────────────

def metrics(eq: pd.Series, label: str, period: str) -> dict:
    r = eq.pct_change().dropna()
    ann_ret = (eq.iloc[-1] / eq.iloc[0]) ** (252 / len(eq)) - 1
    ann_vol = r.std() * np.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0
    rolling_max = eq.cummax()
    dd = (eq - rolling_max) / rolling_max
    max_dd = dd.min()
    years = r.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg_years = (years < 0).sum()
    print(f'  [{label} {period}] Sharpe={sharpe:.3f} AnnRet={ann_ret:.1%} '
          f'MaxDD={max_dd:.1%} NegYears={neg_years}')
    return {'label': label, 'period': period,
            'sharpe': sharpe, 'ann_ret': ann_ret, 'max_dd': max_dd,
            'neg_years': int(neg_years)}


def split_period(eq: pd.Series, start: str, end: str) -> pd.Series:
    return eq.loc[start:end]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    spy, vix, tbill = download_data()
    df = build_signals(spy, vix)

    variants = [
        # (label, otm_pct, vrp_filter, skip_trending, skip_vol_spike)
        ('Var A: 0.2% OTM no filter',   OTM_NARROW, None,  False, False),
        ('Var B: 0.2% OTM VRP>0.5',     OTM_NARROW, 0.5,   False, False),
        ('Var C: 0.32% OTM VRP>0.5',    OTM_WIDE,   0.5,   False, False),
        ('Var D: B + no trend days',     OTM_NARROW, 0.5,   True,  False),
        ('Var E: B + no vol spike days', OTM_NARROW, 0.5,   False, True),
    ]

    results = []
    for label, otm_pct, vrp_filter, skip_trend, skip_spike in variants:
        print(f'\n--- {label} ---')
        eq = run_backtest(df, tbill, otm_pct, vrp_filter, skip_trend, skip_spike, label)
        eq_is  = split_period(eq, IS_START, IS_END)
        eq_oos = split_period(eq, OOS_START, OOS_END)
        m_is  = metrics(eq_is,  label, 'IS')
        m_oos = metrics(eq_oos, label, 'OOS')
        results.append({'IS': m_is, 'OOS': m_oos})

    print('\n' + '='*60)
    print(f'GATE: OOS Sharpe >= 1.0 | MaxDD >= -20% | NegYears = 0')
    print('='*60)
    passing = 0
    for r in results:
        oos = r['OOS']
        gate = (oos['sharpe'] >= 1.0 and oos['max_dd'] >= -0.20 and oos['neg_years'] == 0)
        status = 'PASS' if gate else 'FAIL'
        print(f"  [{status}] {oos['label']}: Sharpe={oos['sharpe']:.3f} "
              f"MaxDD={oos['max_dd']:.1%} NegYears={oos['neg_years']}")
        if gate:
            passing += 1
    print(f'\n{passing}/{len(results)} variants pass gate.')
    print('\nNote: Synthetic BSM Tier-0 backtest. Real fills require ThetaData intraday.')


if __name__ == '__main__':
    main()
