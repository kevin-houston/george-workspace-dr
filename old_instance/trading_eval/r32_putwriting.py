"""
R32: Systematic SPX Put-Writing with VIX-Kelly Hybrid Sizing
=============================================================
Evaluates monthly OTM put-writing on SPY (SPX-equivalent) using three variants:
  1. Full Kelly            – fixed half-Kelly (0.5) constant fraction, no VIX filter
  2. VIX-Kelly Hybrid      – rolling Kelly fraction scaled down as VIX rises
  3. VIX-Kelly + SMA Filter– only sell puts when SPY > 200d SMA (bear-market filter)

Portfolio model:
  - $1,000,000 starting equity
  - Each trade sizes contracts based on: kelly_fraction * portfolio_equity / (100 * K)
  - Monthly returns expressed as % of total portfolio equity
  - Cash collateral = 100 * K * n_contracts (cash-secured puts)

Kelly sizing computed from rolling returns-on-capital (ret_pct basis) so that
avg_win and avg_loss are dimensionally consistent. Prior: win_rate=0.80,
avg_win=1.2%, avg_loss=3.5% (empirical put-writing baseline).

VIX scaling (VIX-Kelly variant):
  VIX < 20  -> 100% of Kelly
  VIX 20-30 -> 50% of Kelly
  VIX > 30  -> 25% of Kelly

Put specs:
  Strike  = 0.95 * S  (5% OTM)
  Expiry  = ~30 days  (~21 trading days)
  IV proxy= realized_vol_20d * 1.03 (standard VRP premium)

Author: Ernesto (NanoClaw R32)
Date: 2026-04-11
"""

import sys
import subprocess


def ensure_deps():
    pkgs = ['yfinance', 'scipy', 'numpy', 'pandas']
    for pkg in pkgs:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', pkg,
                '--break-system-packages', '--quiet'
            ])


ensure_deps()

import json
import os
import warnings
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime
import time

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

START_DATE       = '2020-01-01'
END_DATE         = '2025-12-31'
RISK_FREE        = 0.045
IV_PREMIUM       = 0.03       # realized_vol * 1.03 -> IV proxy
STRIKE_OTM       = 0.95       # 5% OTM
STARTING_EQUITY  = 1_000_000  # $1M portfolio
TRADE_DAYS       = 21         # ~1 month to expiry

CACHE_DIR  = '/workspace/group/trading_eval/cache'
ROUNDS_DIR = '/workspace/group/trading_eval/rounds'
os.makedirs(CACHE_DIR,  exist_ok=True)
os.makedirs(ROUNDS_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# BLACK-SCHOLES
# ─────────────────────────────────────────────

def bs_put(S, K, T, sigma, r=RISK_FREE):
    """Black-Scholes European put price."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))

# ─────────────────────────────────────────────
# DATA FETCHING & CACHING
# ─────────────────────────────────────────────

def fetch_ticker(ticker, start, end, retries=3):
    import yfinance as yf
    cache_file = os.path.join(CACHE_DIR, f"{ticker}_{start}_{end}.pkl")
    if os.path.exists(cache_file):
        try:
            df = pd.read_pickle(cache_file)
            if len(df) > 100:
                return df
        except Exception:
            pass
    for attempt in range(retries):
        try:
            df = yf.download(ticker, start=start, end=end,
                             progress=False, auto_adjust=True)
            if df is not None and len(df) > 100:
                df.to_pickle(cache_file)
                return df
        except Exception as e:
            if attempt == retries - 1:
                print(f"  Failed {ticker}: {e}")
            time.sleep(1 + attempt)
    return None


def get_close(df):
    """Extract clean Close series."""
    c = df['Close']
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    return c.squeeze().dropna()

# ─────────────────────────────────────────────
# VOLATILITY HELPERS
# ─────────────────────────────────────────────

def realized_vol_20d(close):
    """Annualized 20-day realized volatility."""
    log_ret = np.log(close / close.shift(1)).dropna()
    return log_ret.rolling(20).std() * np.sqrt(252)


def iv_proxy(close):
    """IV proxy = realized_vol_20d * (1 + IV_PREMIUM)."""
    return realized_vol_20d(close) * (1 + IV_PREMIUM)


def sma200(close):
    """200-day simple moving average."""
    return close.rolling(200).mean()

# ─────────────────────────────────────────────
# KELLY SIZING
# ─────────────────────────────────────────────

def compute_kelly(win_rate, avg_win_pct, avg_loss_pct):
    """
    Kelly fraction: f* = (p*b - q) / b
    where b = avg_win_pct / avg_loss_pct (payoff ratio, same units).
    Clamped to [0.05, 0.50] for safety (never exceed half-Kelly).
    """
    if avg_loss_pct <= 0 or avg_win_pct <= 0:
        return 0.25
    b = avg_win_pct / avg_loss_pct
    q = 1 - win_rate
    f = (win_rate * b - q) / b
    return float(np.clip(f, 0.05, 0.50))


def vix_scale(vix_level):
    """Scale Kelly fraction by VIX regime (bet less when vol is elevated)."""
    if vix_level > 30:
        return 0.25
    elif vix_level >= 20:
        return 0.50
    else:
        return 1.00

# ─────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────

def calc_sharpe(monthly_returns):
    r = np.array(monthly_returns, dtype=float)
    if len(r) < 5 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(12))


def calc_cagr(equity_curve, periods_per_year=12):
    eq = np.array(equity_curve, dtype=float)
    if len(eq) < 2 or eq[0] <= 0 or eq[-1] <= 0:
        return 0.0
    n_years = (len(eq) - 1) / periods_per_year
    return float((eq[-1] / eq[0]) ** (1 / n_years) - 1)


def calc_max_dd(equity_curve):
    eq = np.array(equity_curve, dtype=float)
    if len(eq) < 2:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(dd.min())

# ─────────────────────────────────────────────
# CORE BACKTEST ENGINE
# ─────────────────────────────────────────────

def run_putwriting(spy_close, vix_close, variant='full_kelly',
                   use_sma_filter=False):
    """
    Run monthly put-writing strategy on SPY with portfolio equity sizing.

    variant:
      'full_kelly' -> fixed half-Kelly (0.5) fraction of portfolio, no VIX scaling
      'vix_kelly'  -> rolling Kelly fraction (ret_pct basis) scaled by VIX

    use_sma_filter: skip trade if SPY < 200d SMA

    Position sizing: contracts = floor(kelly_f * portfolio_equity / (100 * K))
    Returns expressed as % of portfolio equity each month.
    """
    # Align SPY and VIX on common dates
    combined = pd.DataFrame({'spy': spy_close, 'vix': vix_close}).dropna()
    spy = combined['spy']
    vix = combined['vix']

    iv  = iv_proxy(spy)
    sma = sma200(spy)

    # Monthly entry dates: first trading day of each month
    monthly_groups = spy.groupby([spy.index.year, spy.index.month])
    entry_dates = pd.DatetimeIndex([grp.index[0] for _, grp in monthly_groups])
    entry_dates = entry_dates[:-1]   # drop last month (need exit ~21 days later)

    # Empirical put-writing priors (returns on capital at risk)
    PRIOR_WIN_RATE = 0.80
    PRIOR_AVG_WIN  = 0.012   # 1.2% of capital at risk (typical premium collected)
    PRIOR_AVG_LOSS = 0.035   # 3.5% of capital at risk (typical assignment loss)
    FIXED_KELLY    = 0.50    # full_kelly variant: fixed half-Kelly fraction

    trades         = []
    monthly_pnl    = []    # returns as % of portfolio equity
    portfolio_eq   = STARTING_EQUITY

    for entry_date in entry_dates:
        loc      = spy.index.get_loc(entry_date)
        exit_loc = min(loc + TRADE_DAYS, len(spy) - 1)
        exit_date = spy.index[exit_loc]

        S_entry  = float(spy.iloc[loc])
        S_exit   = float(spy.iloc[exit_loc])
        vix_now  = float(vix.iloc[loc]) if not np.isnan(vix.iloc[loc]) else 20.0
        iv_now   = float(iv.iloc[loc])  if not np.isnan(iv.iloc[loc])  else 0.20
        if iv_now <= 0:
            iv_now = 0.20
        sma_now  = float(sma.iloc[loc]) if not np.isnan(sma.iloc[loc]) else 0.0

        # SMA filter: skip if SPY < 200d SMA
        if use_sma_filter and sma_now > 0 and S_entry < sma_now:
            monthly_pnl.append(0.0)
            portfolio_eq = portfolio_eq * (1 + RISK_FREE / 12)  # earn risk-free on cash
            continue

        # Option parameters
        K = STRIKE_OTM * S_entry         # 5% OTM strike
        T = TRADE_DAYS / 365.0           # time to expiry in years

        # Premium received via Black-Scholes
        premium = bs_put(S_entry, K, T, iv_now)

        # ─── Adaptive Kelly (rolling, returns-on-capital) ───
        if len(trades) >= 10:
            past   = [t for t in trades[-min(60, len(trades)):] if t['capital_ret'] != 0]
            if past:
                wins   = [t['capital_ret'] for t in past if t['capital_ret'] > 0]
                losses = [-t['capital_ret'] for t in past if t['capital_ret'] <= 0]
                wr     = len(wins) / len(past)
                aw     = np.mean(wins)   if wins   else PRIOR_AVG_WIN
                al     = np.mean(losses) if losses else PRIOR_AVG_LOSS
                kelly_f = compute_kelly(wr, aw, al)
            else:
                kelly_f = compute_kelly(PRIOR_WIN_RATE, PRIOR_AVG_WIN, PRIOR_AVG_LOSS)
        else:
            kelly_f = compute_kelly(PRIOR_WIN_RATE, PRIOR_AVG_WIN, PRIOR_AVG_LOSS)

        # Apply variant-specific effective fraction
        if variant == 'full_kelly':
            effective_kelly = FIXED_KELLY
        else:
            effective_kelly = kelly_f * vix_scale(vix_now)

        # Contracts based on portfolio equity, not fixed notional
        # collateral = 100 * K per contract (cash-secured put)
        n_contracts = max(int(effective_kelly * portfolio_eq / (100 * K)), 1)
        # Safety cap: collateral cannot exceed 95% of portfolio
        max_contracts = max(int(0.95 * portfolio_eq / (100 * K)), 1)
        n_contracts = min(n_contracts, max_contracts)

        # P&L at expiry
        intrinsic_at_expiry = max(0.0, K - S_exit)
        pnl_per_share = premium - intrinsic_at_expiry
        pnl_total     = pnl_per_share * 100 * n_contracts

        # Return on capital at risk (for Kelly calibration)
        capital_at_risk = 100 * K * n_contracts
        capital_ret = pnl_total / capital_at_risk if capital_at_risk > 0 else 0.0

        # Portfolio return: P&L relative to total portfolio equity
        portfolio_ret = pnl_total / portfolio_eq if portfolio_eq > 0 else 0.0

        # Update portfolio equity
        portfolio_eq = max(portfolio_eq + pnl_total, 1_000)  # floor at $1k to avoid blowup

        won = pnl_per_share > 0

        trades.append({
            'entry_date':    str(entry_date.date()),
            'exit_date':     str(exit_date.date()),
            'S_entry':       round(S_entry, 2),
            'K':             round(K, 2),
            'premium':       round(premium, 4),
            'iv_now':        round(iv_now, 4),
            'vix_now':       round(vix_now, 2),
            'kelly_f_raw':   round(kelly_f, 4),
            'kelly_f_used':  round(effective_kelly, 4),
            'n_contracts':   n_contracts,
            'pnl_per_share': round(pnl_per_share, 4),
            'pnl_total':     round(pnl_total, 2),
            'capital_ret':   round(capital_ret, 6),
            'portfolio_ret': round(portfolio_ret, 6),
            'portfolio_eq':  round(portfolio_eq, 2),
            'won':           won,
        })
        monthly_pnl.append(portfolio_ret)

    if not monthly_pnl or all(r == 0 for r in monthly_pnl):
        return None

    # Equity curve from portfolio returns (including idle months)
    equity = [1.0]
    for r in monthly_pnl:
        equity.append(equity[-1] * (1 + r))

    active_trades   = [t for t in trades if t['capital_ret'] != 0]
    active_returns  = [r for r in monthly_pnl if r != 0]
    win_rate_actual = (sum(1 for t in active_trades if t['won']) / len(active_trades)
                       if active_trades else 0.0)

    return {
        'sharpe':          round(calc_sharpe(active_returns), 4),
        'cagr':            round(calc_cagr(equity), 4),
        'max_drawdown':    round(calc_max_dd(equity), 4),
        'win_rate':        round(win_rate_actual, 4),
        'total_trades':    len(active_trades),
        'total_months':    len(monthly_pnl),
        'avg_monthly_ret': round(np.mean(active_returns), 6) if active_returns else 0.0,
        'final_equity':    round(portfolio_eq, 2),
        'equity_curve':    [round(e, 6) for e in equity],
        'trades':          trades,
    }

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("R32: SPX Put-Writing with VIX-Kelly Hybrid Sizing")
    print("=" * 60)
    print()

    # Fetch data
    print("Fetching SPY and VIX data...")
    spy_df = fetch_ticker('SPY',  START_DATE, END_DATE)
    vix_df = fetch_ticker('^VIX', START_DATE, END_DATE)

    if spy_df is None or vix_df is None:
        print("ERROR: Could not fetch required data.")
        sys.exit(1)

    spy_close = get_close(spy_df)
    vix_close = get_close(vix_df)

    print(f"  SPY: {len(spy_close)} days  "
          f"({spy_close.index[0].date()} - {spy_close.index[-1].date()})")
    print(f"  VIX: {len(vix_close)} days  "
          f"({vix_close.index[0].date()} - {vix_close.index[-1].date()})")
    print()

    # Strategy variants
    configs = [
        ('Full Kelly (no VIX filter)',      'full_kelly', False),
        ('VIX-Kelly Hybrid',                'vix_kelly',  False),
        ('VIX-Kelly + SPY SMA-200 Filter',  'vix_kelly',  True),
    ]

    variant_keys = {
        'Full Kelly (no VIX filter)':     'full_kelly_no_filter',
        'VIX-Kelly Hybrid':               'vix_kelly_hybrid',
        'VIX-Kelly + SPY SMA-200 Filter': 'vix_kelly_sma_filter',
    }

    results = {}

    for name, variant, sma_filter in configs:
        print(f"Running: {name} ...")
        res = run_putwriting(spy_close, vix_close,
                             variant=variant, use_sma_filter=sma_filter)
        if res is None:
            print(f"  No results for {name}")
            continue
        key = variant_keys[name]
        results[key] = res
        results[key]['name']       = name
        results[key]['variant']    = variant
        results[key]['sma_filter'] = sma_filter
        print(f"  Sharpe: {res['sharpe']:.4f}  |  CAGR: {res['cagr']*100:.2f}%  "
              f"|  MaxDD: {res['max_drawdown']*100:.2f}%  "
              f"|  WinRate: {res['win_rate']*100:.1f}%  "
              f"|  Trades: {res['total_trades']}  "
              f"|  Final equity: ${res['final_equity']:,.0f}")

    # Summary table
    print()
    print("=" * 90)
    print(f"{'Strategy':<40} {'Sharpe':>7} {'CAGR%':>7} {'MaxDD%':>8} "
          f"{'WinRate%':>9} {'Trades':>7} {'FinalEq':>12}")
    print("-" * 90)
    for key, res in results.items():
        print(f"{res['name']:<40} {res['sharpe']:>7.4f} {res['cagr']*100:>7.2f} "
              f"{res['max_drawdown']*100:>8.2f} {res['win_rate']*100:>9.1f} "
              f"{res['total_trades']:>7} ${res['final_equity']:>11,.0f}")
    print("=" * 90)

    # Best variant
    best_key = max(results, key=lambda k: results[k]['sharpe'])
    best = results[best_key]
    print(f"\nBest variant: {best['name']}")
    print(f"  Sharpe: {best['sharpe']:.4f}  |  CAGR: {best['cagr']*100:.2f}%  "
          f"|  MaxDD: {best['max_drawdown']*100:.2f}%")
    print(f"  Leaderboard reference: Bull Put Spread XOM = Sharpe 2.5837")

    # VIX regime breakdown for each variant
    print("\nVIX Regime Trade Distribution:")
    for key, res in results.items():
        ts = res['trades']
        low  = [t for t in ts if t['vix_now'] < 20 and t['capital_ret'] != 0]
        mid  = [t for t in ts if 20 <= t['vix_now'] <= 30 and t['capital_ret'] != 0]
        high = [t for t in ts if t['vix_now'] > 30 and t['capital_ret'] != 0]

        def wr(lst):
            return (f"{sum(1 for t in lst if t['won'])/len(lst)*100:.0f}%"
                    if lst else "N/A")

        def avg_ret(lst, field='portfolio_ret'):
            return (f"{np.mean([t[field] for t in lst])*100:.3f}%"
                    if lst else "N/A")

        def avg_contracts(lst):
            return f"{np.mean([t['n_contracts'] for t in lst]):.1f}" if lst else "N/A"

        print(f"  {res['name']}")
        print(f"    VIX<20:    n={len(low):2d}  win={wr(low):4s}  "
              f"avg_contracts={avg_contracts(low)}  avg_port_ret={avg_ret(low)}")
        print(f"    VIX 20-30: n={len(mid):2d}  win={wr(mid):4s}  "
              f"avg_contracts={avg_contracts(mid)}  avg_port_ret={avg_ret(mid)}")
        print(f"    VIX>30:    n={len(high):2d}  win={wr(high):4s}  "
              f"avg_contracts={avg_contracts(high)}  avg_port_ret={avg_ret(high)}")

    # Save JSON results
    output = {
        'round':    'R32',
        'category': 'SPX Put-Writing / VIX-Kelly',
        'run_date': datetime.now().isoformat(),
        'config': {
            'start_date':      START_DATE,
            'end_date':        END_DATE,
            'ticker':          'SPY',
            'strike_otm':      STRIKE_OTM,
            'iv_premium':      IV_PREMIUM,
            'starting_equity': STARTING_EQUITY,
            'trade_days':      TRADE_DAYS,
            'risk_free':       RISK_FREE,
        },
        'strategies': results,
        'leaderboard_reference': {
            'r28_bull_put_spread_xom_sharpe': 2.5837,
        },
    }

    out_path = os.path.join(ROUNDS_DIR, 'r32_putwriting_results.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {out_path}")

    return results


if __name__ == '__main__':
    main()
