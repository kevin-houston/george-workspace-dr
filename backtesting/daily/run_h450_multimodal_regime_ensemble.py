#!/usr/bin/env python3
"""
H450 — Recency-Weighted Multi-Specialist Regime Ensemble for H026 ETF Rotation
Source: arXiv:2604.17327 (Signal or Noise? Multi-Agent LLM Stock Recommendations)
        arXiv:2605.19337 (Agentic Trading Survey — specialist rotation finding)

Hypothesis: A deterministic recency-weighted meta-ensemble of three price-based
specialists (Macro / Momentum / Volatility) dynamically allocates voting weight
to the most recently predictive specialist, improving on the static H026 ETF
rotation by adapting to regime shifts without LLM calls.

Variants:
  A — equal-weight ensemble of three specialists
  B — recency-weighted ensemble (90-day rolling Sharpe weight)
  C — Var B + VIX<20 / SPY>200MA safety overlay
  D — Var B with top-2 picks instead of top-1

Baseline: H026 canonical OOS Sharpe ~0.785
Gate:     OOS Sharpe >= 0.8
IS:  2004-01-01 to 2017-12-31
OOS: 2018-01-01 to 2026-06-30
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ── Parameters ────────────────────────────────────────────────────────────────
IS_START  = '2004-01-01'
IS_END    = '2017-12-31'
OOS_START = '2018-01-01'
OOS_END   = '2026-06-30'

META_WINDOW = 90   # days for recency-weighted Sharpe computation
MOM_WINDOW  = 252  # 12m momentum lookback
MOM_SKIP    = 21   # 1m skip for momentum (H026 canonical)

# H026 canonical universe (25 assets)
H026_UNIVERSE = [
    'SPY', 'QQQ', 'IWM', 'MDY',           # US equity
    'EFA', 'EEM', 'VGK', 'EWJ',           # International
    'TLT', 'IEF', 'SHY', 'LQD', 'HYG',   # Fixed income
    'GLD', 'SLV', 'DBC', 'USO',           # Commodities
    'VNQ', 'REM',                          # Real estate
    'XLK', 'XLV', 'XLE', 'XLF',          # Sectors
    'XLU', 'XLP',                          # Defensive sectors
]

SAFE_HAVEN = 'SHY'  # cash proxy when regime gate triggers

# ── Data loading ──────────────────────────────────────────────────────────────
def load_etf_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    raw = yf.download(tickers, start=start, end=end, progress=False, auto_adjust=True)['Close']
    if isinstance(raw, pd.Series):
        raw = raw.to_frame()
    raw.index = pd.to_datetime(raw.index)
    return raw


def load_macro_data(start: str, end: str) -> pd.DataFrame:
    """Load VIX and SPY for regime signals."""
    vix = yf.download('^VIX', start=start, end=end, progress=False, auto_adjust=True)['Close']
    spy = yf.download('SPY', start=start, end=end, progress=False, auto_adjust=True)['Close']
    vix.index = pd.to_datetime(vix.index)
    spy.index = pd.to_datetime(spy.index)
    df = pd.DataFrame({'vix': vix.squeeze(), 'spy': spy.squeeze()})
    return df.ffill()


def load_treasury_yields(start: str, end: str) -> pd.DataFrame:
    """
    Yield curve slope proxy: 10Y - 2Y via Treasury ETF duration spread.
    IEF (7-10Y) relative to SHY (1-3Y) as spread approximation.
    """
    ief = yf.download('IEF', start=start, end=end, progress=False, auto_adjust=True)['Close']
    shy = yf.download('SHY', start=start, end=end, progress=False, auto_adjust=True)['Close']
    ief.index = pd.to_datetime(ief.index)
    shy.index = pd.to_datetime(shy.index)
    # Yield curve proxy: 12m return differential (IEF vs SHY)
    # Positive = longer bonds winning = rates falling = bullish macro
    spread = ief.squeeze().pct_change(252) - shy.squeeze().pct_change(252)
    return spread.to_frame('yc_slope').ffill()


# ── Specialist signal functions ────────────────────────────────────────────────
def specialist_macro(prices: pd.DataFrame,
                     macro: pd.DataFrame,
                     yc: pd.DataFrame,
                     date: pd.Timestamp) -> str:
    """
    Macro specialist: selects ETF based on yield curve + VIX regime.
    Bull macro (YC positive + VIX<20): favor SPY/QQQ.
    Bear macro (YC negative or VIX>30): favor TLT/GLD.
    Neutral: standard 12m momentum rank.
    """
    # Get regime state
    vix_val = macro.loc[:date, 'vix'].iloc[-1] if date in macro.index else 25.0
    yc_val  = yc.loc[:date, 'yc_slope'].iloc[-1] if date in yc.index else 0.0

    if vix_val < 20 and yc_val > 0:
        # Bull macro: equity bias
        candidates = ['SPY', 'QQQ', 'IWM', 'EFA']
    elif vix_val > 30 or yc_val < -0.05:
        # Bear macro: defensive
        candidates = ['TLT', 'GLD', 'SHY', 'LQD']
    else:
        # Neutral: standard momentum
        candidates = H026_UNIVERSE

    # Rank by 12m-1m momentum within candidate set
    available = [c for c in candidates if c in prices.columns]
    subset    = prices[available].loc[:date]
    if len(subset) < MOM_WINDOW:
        return SHY

    mom = subset.iloc[-MOM_SKIP] / subset.iloc[-MOM_WINDOW] - 1
    best = mom.idxmax()
    return best if isinstance(best, str) else SHY


def specialist_momentum(prices: pd.DataFrame, date: pd.Timestamp) -> str:
    """
    Momentum specialist: pure 12-1m cross-sectional momentum.
    Direct implementation of H026 canonical signal.
    """
    subset = prices.loc[:date]
    if len(subset) < MOM_WINDOW:
        return SHY

    mom = subset.iloc[-MOM_SKIP] / subset.iloc[-MOM_WINDOW] - 1
    # Only consider ETFs with positive momentum
    pos_mom = mom[mom > 0]
    if pos_mom.empty:
        return SHY
    return pos_mom.idxmax()


def specialist_volatility(prices: pd.DataFrame,
                           macro: pd.DataFrame,
                           date: pd.Timestamp) -> str:
    """
    Volatility specialist: selects asset class based on vol regime.
    Low vol regime (5d RV < 63d RV): risk-on → momentum winner.
    High vol regime (5d RV > 1.5x 63d RV): risk-off → TLT/GLD/SHY.
    """
    spy_prices = macro.loc[:date, 'spy'] if 'spy' in macro.columns else None
    if spy_prices is None or len(spy_prices) < 63:
        return specialist_momentum(prices, date)

    log_ret = np.log(spy_prices / spy_prices.shift(1)).dropna()
    rv5  = log_ret.iloc[-5:].std()  * np.sqrt(252)
    rv63 = log_ret.iloc[-63:].std() * np.sqrt(252)

    if rv63 == 0:
        return SHY

    vol_ratio = rv5 / rv63
    if vol_ratio > 1.5:
        # High vol spike: rotate defensive
        subset = prices[['TLT', 'GLD', 'SHY']].loc[:date]
        if len(subset) < MOM_WINDOW:
            return SHY
        mom = subset.iloc[-MOM_SKIP] / subset.iloc[-MOM_WINDOW] - 1
        return mom.idxmax()
    elif vol_ratio < 0.7:
        # Low vol: momentum winner from full universe
        return specialist_momentum(prices, date)
    else:
        # Neutral: use full universe momentum
        return specialist_momentum(prices, date)


# ── Meta-ensemble ─────────────────────────────────────────────────────────────
def compute_recency_weights(specialist_rets: dict,
                             window: int = 90) -> dict:
    """
    Compute rolling Sharpe-based weights for each specialist over trailing window.
    Higher recent Sharpe → more weight in the meta-ensemble.
    """
    weights = {}
    sharpes = {}
    for name, rets in specialist_rets.items():
        if len(rets) < window:
            sharpes[name] = 0.5  # neutral prior
        else:
            r = pd.Series(rets[-window:])
            s = r.mean() / (r.std() + 1e-6) * np.sqrt(252)
            sharpes[name] = max(s, 0.0)  # floor at 0

    total = sum(sharpes.values())
    if total == 0:
        n = len(sharpes)
        weights = {k: 1.0/n for k in sharpes}
    else:
        weights = {k: v / total for k, v in sharpes.items()}
    return weights


def ensemble_vote(specialist_picks: dict, weights: dict) -> str:
    """
    Weighted vote: aggregate specialist picks by weight.
    The ETF with the highest total weight-votes wins.
    """
    vote_totals = {}
    for spec_name, pick in specialist_picks.items():
        w = weights.get(spec_name, 1.0/3)
        vote_totals[pick] = vote_totals.get(pick, 0.0) + w
    return max(vote_totals, key=vote_totals.get)


def top2_vote(specialist_picks: dict, weights: dict,
              prices: pd.DataFrame, date: pd.Timestamp) -> list:
    """
    Return top-2 ETFs by weighted vote score for Var D.
    """
    vote_totals = {}
    for spec_name, pick in specialist_picks.items():
        w = weights.get(spec_name, 1.0/3)
        vote_totals[pick] = vote_totals.get(pick, 0.0) + w
    sorted_votes = sorted(vote_totals.items(), key=lambda x: x[1], reverse=True)
    return [v[0] for v in sorted_votes[:2]]


# ── Backtest engine ────────────────────────────────────────────────────────────
def run_backtest(prices: pd.DataFrame,
                  macro: pd.DataFrame,
                  yc: pd.DataFrame,
                  variant: str = 'A') -> pd.Series:
    """
    Monthly rebalancing backtest across full date range.
    Returns daily strategy returns.
    """
    # Get month-end rebalance dates
    monthly_dates = prices.resample('ME').last().index
    daily_returns = prices.pct_change()

    holdings = [SHY]
    last_rebal = None
    specialist_rets = {'macro': [], 'momentum': [], 'volatility': []}
    port_returns = []

    for i in range(1, len(monthly_dates)):
        rebal_date = monthly_dates[i - 1]
        next_date  = monthly_dates[i]

        if rebal_date not in prices.index:
            rebal_date = prices.index[prices.index.searchsorted(rebal_date) - 1]

        # Compute specialist picks at rebal date
        pick_macro = specialist_macro(prices, macro, yc, rebal_date)
        pick_mom   = specialist_momentum(prices, rebal_date)
        pick_vol   = specialist_volatility(prices, macro, rebal_date)

        specialist_picks = {
            'macro':      pick_macro,
            'momentum':   pick_mom,
            'volatility': pick_vol,
        }

        if variant == 'A':
            # Equal-weight vote
            weights = {'macro': 1/3, 'momentum': 1/3, 'volatility': 1/3}
        elif variant in ('B', 'C', 'D'):
            # Recency-weighted
            weights = compute_recency_weights(specialist_rets, window=META_WINDOW)

        if variant in ('A', 'B', 'C'):
            picked = ensemble_vote(specialist_picks, weights)
            # Var C: safety overlay
            if variant == 'C':
                vix_val = macro.loc[:rebal_date, 'vix'].iloc[-1] if 'vix' in macro.columns else 25.0
                spy_px  = macro.loc[:rebal_date, 'spy']
                spy_ma200 = spy_px.iloc[-200:].mean() if len(spy_px) >= 200 else spy_px.mean()
                spy_last  = spy_px.iloc[-1]
                if vix_val >= 20 and spy_last < spy_ma200:
                    picked = SHY
            holdings_this = [picked]
        elif variant == 'D':
            holdings_this = top2_vote(specialist_picks, weights, prices, rebal_date)

        # Compute returns for the month
        mask = (daily_returns.index > rebal_date) & (daily_returns.index <= next_date)
        period = daily_returns.loc[mask]

        for dt, row in period.iterrows():
            valid_holds = [h for h in holdings_this if h in row.index and not np.isnan(row[h])]
            if valid_holds:
                port_ret = np.mean([row[h] for h in valid_holds])
            else:
                port_ret = row.get(SHY, 0.0)
            port_returns.append({'date': dt, 'ret': port_ret})

        # Update specialist trailing returns for recency weighting
        for spec_name, spec_pick in specialist_picks.items():
            if spec_pick in period.columns:
                spec_m_ret = (1 + period[spec_pick]).prod() - 1
                specialist_rets[spec_name].append(spec_m_ret)

    if not port_returns:
        return pd.Series(dtype=float)

    port_df = pd.DataFrame(port_returns).set_index('date')
    return port_df['ret']


# ── Performance metrics ────────────────────────────────────────────────────────
def performance_metrics(returns: pd.Series, label: str) -> dict:
    daily = returns.dropna()
    if len(daily) == 0:
        return {}

    ann_ret = daily.mean() * 252
    ann_vol = daily.std()  * np.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0

    cum     = (1 + daily).cumprod()
    roll_max = cum.cummax()
    drawdown = (cum - roll_max) / roll_max
    max_dd  = drawdown.min()
    cagr    = cum.iloc[-1] ** (252 / len(daily)) - 1

    annual    = daily.groupby(daily.index.year).apply(lambda x: (1+x).prod() - 1)
    neg_years = (annual < 0).sum()

    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")
    print(f"  Sharpe:      {sharpe:.3f}")
    print(f"  CAGR:        {cagr*100:.1f}%")
    print(f"  MaxDD:       {max_dd*100:.1f}%")
    print(f"  Neg Years:   {neg_years}")
    for yr, r in annual.items():
        print(f"    {yr}: {r*100:+.1f}%")

    return {'sharpe': sharpe, 'cagr': cagr, 'max_dd': max_dd, 'neg_years': int(neg_years)}


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("H450 — Recency-Weighted Multi-Specialist Regime Ensemble")
    print(f"IS:  {IS_START} to {IS_END}")
    print(f"OOS: {OOS_START} to {OOS_END}")
    print(f"Universe: H026 ({len(H026_UNIVERSE)} ETFs)")

    full_start = '2003-01-01'
    print("\nLoading ETF prices...")
    prices = load_etf_prices(H026_UNIVERSE, full_start, OOS_END)
    macro  = load_macro_data(full_start, OOS_END)
    yc     = load_treasury_yields(full_start, OOS_END)

    results = {}

    for var in ['A', 'B', 'C', 'D']:
        print(f"\nRunning Variant {var}...")
        all_returns = run_backtest(prices, macro, yc, variant=var)
        is_ret  = all_returns.loc[IS_START:IS_END]
        oos_ret = all_returns.loc[OOS_START:OOS_END]

        results[f'Var{var}_IS']  = performance_metrics(is_ret,  f"Var {var} [IS]")
        results[f'Var{var}_OOS'] = performance_metrics(oos_ret, f"Var {var} [OOS]")

    print("\n" + "="*55)
    print("  GATE CHECK (OOS Sharpe >= 0.8 vs H026 baseline ~0.785)")
    print("="*55)
    for k, v in results.items():
        if 'OOS' in k and v:
            passed = v.get('sharpe', 0) >= 0.8
            print(f"  {k}: Sharpe={v.get('sharpe',0):.3f}, MaxDD={v.get('max_dd',0)*100:.1f}% → {'PASS' if passed else 'FAIL'}")


if __name__ == '__main__':
    main()
