"""
H308 — Drift-Regime Gated Value+Reversal
=========================================

Hypothesis:
  arXiv:2511.12490 (Nov 2025) documents OOS Sharpe > 13 (L/S, daily rebalance)
  from combining value + short-term reversal signals ONLY during stock-specific
  'drift regimes'. A drift regime is when a stock has >60% positive-close days
  in a trailing 63-calendar-day (~45 trading-day) window.

  This test: long-only adaptation on S&P 500 proxy universe.
    - Drift regime filter activates the scoring for each stock individually
    - Value signal: trailing FCF/P (quarterly, FMP API, forward-filled)
    - Reversal signal: trailing 5-day return (buy negative = mean-reversion)
    - Portfolio: top 20 drift-active stocks by combined score, equal-weight
    - Monthly rebalance

  Variants:
    A: Drift gate + value (FCF/P) + reversal (5-day)
    B: Drift gate + reversal only (no value signal)
    C: Drift gate + industry-adjusted reversal (H181 approach, no FCF/P)

  Prior art:
    H181 (industry-adjusted reversal) — CONFIRMED OOS Sharpe
    H228 (alpha101+H181 blend) — CONFIRMED OOS 1.572
    H284 (FCF/P screener) — CONFIRMED weak
    arXiv:2511.12490 — 13-Sharpe L/S daily; expected ~0.9-1.5 for long-only monthly

  IS:  2010-01-01 to 2019-12-31
  OOS: 2020-01-01 to 2026-06-13
  Gate: OOS Sharpe > 1.3

  NOTE: This is a scaffold. Full implementation requires:
  1. S&P 500 constituent history (to avoid survivorship bias)
  2. FMP quarterly FCF/P data for full universe (API calls limited)
  3. Industry classification for Variant C
"""

import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

RESULT_DIR = Path("/workspace/agent/backtesting/results")
RESULT_DIR.mkdir(exist_ok=True)

# S&P 500 proxy universe — 100 stocks across sectors
# NOTE: survivorship bias caveat — these are current constituents
# For production, use historical constituent data (e.g., Sharadar, Compustat)
SP500_PROXY = [
    # Technology
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "QCOM", "TXN", "AMAT",
    "LRCX", "ADI", "KLAC", "INTC", "MU", "NOW", "ADBE", "SNOW", "PANW", "CDNS",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "BLK", "CB", "PGR", "MET", "AXP",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR", "AMGN", "ISRG",
    # Consumer Discretionary
    "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TJX", "LOW", "BKNG", "MAR",
    # Communication Services
    "META", "GOOGL", "NFLX", "DIS", "CMCSA", "VZ", "T", "EA", "TTWO", "OMC",
    # Industrials
    "CAT", "RTX", "HON", "GE", "LMT", "UPS", "DE", "BA", "MMM", "EMR",
    # Consumer Staples
    "PG", "KO", "PEP", "WMT", "COST", "PM", "MO", "CL", "KHC", "GIS",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "PXD", "VLO", "MPC", "PSX", "HAL",
    # Materials / REITs / Utilities
    "LIN", "APD", "ECL", "DD", "AMT", "PLD", "SPG", "NEE", "DUK", "SO",
]

# GICS sector mapping for Variant C (industry-adjusted reversal)
SECTOR_MAP = {
    "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "AVGO": "Tech", "ORCL": "Tech",
    "CRM": "Tech", "AMD": "Tech", "QCOM": "Tech", "TXN": "Tech", "AMAT": "Tech",
    "LRCX": "Tech", "ADI": "Tech", "KLAC": "Tech", "INTC": "Tech", "MU": "Tech",
    "NOW": "Tech", "ADBE": "Tech", "SNOW": "Tech", "PANW": "Tech", "CDNS": "Tech",
    "JPM": "Fin", "BAC": "Fin", "WFC": "Fin", "GS": "Fin", "MS": "Fin",
    "BLK": "Fin", "CB": "Fin", "PGR": "Fin", "MET": "Fin", "AXP": "Fin",
    "UNH": "HC", "JNJ": "HC", "LLY": "HC", "ABBV": "HC", "MRK": "HC",
    "TMO": "HC", "ABT": "HC", "DHR": "HC", "AMGN": "HC", "ISRG": "HC",
    "AMZN": "CD", "TSLA": "CD", "HD": "CD", "MCD": "CD", "NKE": "CD",
    "SBUX": "CD", "TJX": "CD", "LOW": "CD", "BKNG": "CD", "MAR": "CD",
    "META": "Comm", "GOOGL": "Comm", "NFLX": "Comm", "DIS": "Comm", "CMCSA": "Comm",
    "VZ": "Comm", "T": "Comm", "EA": "Comm", "TTWO": "Comm", "OMC": "Comm",
    "CAT": "Ind", "RTX": "Ind", "HON": "Ind", "GE": "Ind", "LMT": "Ind",
    "UPS": "Ind", "DE": "Ind", "BA": "Ind", "MMM": "Ind", "EMR": "Ind",
    "PG": "CS", "KO": "CS", "PEP": "CS", "WMT": "CS", "COST": "CS",
    "PM": "CS", "MO": "CS", "CL": "CS", "KHC": "CS", "GIS": "CS",
    "XOM": "Egy", "CVX": "Egy", "COP": "Egy", "SLB": "Egy", "EOG": "Egy",
    "PXD": "Egy", "VLO": "Egy", "MPC": "Egy", "PSX": "Egy", "HAL": "Egy",
    "LIN": "Mat", "APD": "Mat", "ECL": "Mat", "DD": "Mat", "AMT": "REIT",
    "PLD": "REIT", "SPG": "REIT", "NEE": "Util", "DUK": "Util", "SO": "Util",
}

FULL_START = "2008-01-01"
IS_START   = "2010-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"
OOS_END    = "2026-06-13"
COST_BPS   = 10     # one-way
DRIFT_WINDOW = 45   # trading days
DRIFT_THRESH = 0.60 # fraction of positive days
REVERSAL_DAYS = 5   # trailing days for reversal signal
TOP_N        = 20   # stocks in portfolio
FMP_KEY = os.environ.get("FMP_API_KEY", "")


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_prices(tickers):
    print(f"  Fetching OHLCV for {len(tickers)} tickers…")
    raw = yf.download(tickers, start=FULL_START, end=OOS_END,
                      auto_adjust=True, progress=False)["Close"]
    return raw.ffill()


def fetch_fcf_per_share_fmp(ticker: str) -> pd.Series:
    """Fetch quarterly FCF per share from FMP; return date-indexed Series."""
    if not FMP_KEY:
        return pd.Series(dtype=float)
    url = f"https://financialmodelingprep.com/api/v3/cash-flow-statement/{ticker}"
    try:
        r = requests.get(url, params={"period": "quarter", "apikey": FMP_KEY, "limit": 60},
                         timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return pd.Series(dtype=float)
        rows = []
        for item in data:
            date_str = item.get("date", "")
            fcf = item.get("freeCashFlow")
            shares = item.get("weightedAverageShsOut")
            if date_str and fcf is not None and shares and shares > 0:
                rows.append((pd.Timestamp(date_str), fcf / shares))
        if not rows:
            return pd.Series(dtype=float)
        s = pd.Series(dict(rows)).sort_index()
        return s
    except Exception:
        return pd.Series(dtype=float)


def build_fcf_price_ratio(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Build quarterly FCF/P matrix (using FMP for FCF, price from yfinance).
    Forward-fill quarterly FCF/P to daily frequency.
    Returns daily DataFrame with same columns as prices.
    """
    print("  Building FCF/P signals (FMP quarterly)…")
    fcf_daily = {}
    for ticker in prices.columns:
        fcf_ps = fetch_fcf_per_share_fmp(ticker)
        if fcf_ps.empty:
            fcf_daily[ticker] = pd.Series(0.0, index=prices.index)
            continue
        # Reindex to daily, forward-fill; then compute FCF/P
        fcf_reindexed = fcf_ps.reindex(prices.index, method="ffill")
        price = prices[ticker]
        ratio = fcf_reindexed / price.where(price > 0)
        fcf_daily[ticker] = ratio.fillna(0.0)
    return pd.DataFrame(fcf_daily)


# ── Signal construction ───────────────────────────────────────────────────────

def compute_drift_regime(prices: pd.DataFrame, window: int = DRIFT_WINDOW,
                          thresh: float = DRIFT_THRESH) -> pd.DataFrame:
    """
    Per stock: fraction of positive-close days in trailing `window` trading days.
    Returns boolean DataFrame (True = stock in drift regime).
    """
    daily_ret = prices.pct_change()
    pos_frac = (daily_ret > 0).rolling(window, min_periods=window // 2).mean()
    return pos_frac >= thresh


def compute_reversal_signal(prices: pd.DataFrame, days: int = REVERSAL_DAYS) -> pd.DataFrame:
    """Trailing `days`-day return, negated (buy low performers)."""
    return -prices.pct_change(days)


def compute_industry_adj_reversal(prices: pd.DataFrame) -> pd.DataFrame:
    """H181-style: reversal minus industry median reversal (signed same direction)."""
    raw = compute_reversal_signal(prices)
    sector_medians = {}
    for sector in set(SECTOR_MAP.values()):
        cols = [t for t in prices.columns if SECTOR_MAP.get(t) == sector and t in raw.columns]
        if cols:
            sector_medians[sector] = raw[cols].median(axis=1)
    adj = raw.copy()
    for ticker in adj.columns:
        sector = SECTOR_MAP.get(ticker)
        if sector and sector in sector_medians:
            adj[ticker] = raw[ticker] - sector_medians[sector]
    return adj


# ── Backtest ──────────────────────────────────────────────────────────────────

def backtest_variant(prices: pd.DataFrame, scores: pd.DataFrame,
                      drift: pd.DataFrame, label: str) -> tuple:
    """
    Monthly rebalance: top TOP_N stocks with drift=True and highest score.
    Equity curve using next-month actual returns.
    """
    monthly_dates = pd.date_range(IS_START, OOS_END, freq="ME")
    equity = 1.0
    equity_curve = {}
    prev_holding = {}

    monthly_px = prices.resample("ME").last()

    for i, dt in enumerate(monthly_dates):
        if dt not in prices.index and dt not in monthly_px.index:
            equity_curve[dt] = equity
            continue

        # Use last available price date at or before month-end
        avail = prices.index[prices.index <= dt]
        if len(avail) == 0:
            equity_curve[dt] = equity
            continue
        snap_date = avail[-1]

        # Score and drift on this date
        if snap_date not in scores.index or snap_date not in drift.index:
            equity_curve[dt] = equity
            continue

        score_row = scores.loc[snap_date].dropna()
        drift_row = drift.loc[snap_date]

        # Filter to drift-active stocks
        active = drift_row[drift_row].index.tolist()
        active = [t for t in active if t in score_row.index]
        if len(active) == 0:
            # No drift-active stocks: hold equal weight of top-scoring regardless
            active = score_row.nlargest(TOP_N).index.tolist()

        score_active = score_row[active]
        picks = score_active.nlargest(min(TOP_N, len(score_active))).index.tolist()
        weights = {p: 1.0 / len(picks) for p in picks}

        # Turnover cost
        all_tickers = set(list(weights.keys()) + list(prev_holding.keys()))
        turnover = sum(abs(weights.get(t, 0) - prev_holding.get(t, 0)) for t in all_tickers)
        cost = turnover * COST_BPS / 10000

        # Next month return
        if i + 1 < len(monthly_dates):
            next_dt = monthly_dates[i + 1]
            avail_next = prices.index[prices.index <= next_dt]
            if len(avail_next) == 0:
                equity_curve[dt] = equity
                continue
            next_snap = avail_next[-1]
            port_ret = 0.0
            for t, w in weights.items():
                if t in prices.columns:
                    p0 = prices.loc[snap_date, t]
                    p1 = prices.loc[next_snap, t] if next_snap in prices.index else p0
                    if p0 > 0:
                        port_ret += w * (p1 / p0 - 1)
            equity *= (1 + port_ret - cost)

        equity_curve[dt] = equity
        prev_holding = weights

    ec = pd.Series(equity_curve)
    return ec


def period_stats(ec: pd.Series, start: str, end: str) -> dict:
    ec_p = ec[(ec.index >= start) & (ec.index <= end)].dropna()
    if len(ec_p) < 6:
        return {"sharpe": float("nan"), "cagr": float("nan"), "maxdd": float("nan")}
    rets = ec_p.pct_change().dropna()
    ann_ret = (ec_p.iloc[-1] / ec_p.iloc[0]) ** (12 / len(ec_p)) - 1
    ann_vol = rets.std() * np.sqrt(12)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    roll_max = ec_p.cummax()
    maxdd = ((ec_p - roll_max) / roll_max).min()
    return {
        "sharpe": round(float(sharpe), 3),
        "cagr": round(float(ann_ret), 4),
        "maxdd": round(float(maxdd), 4),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 60)
print("H308 — Drift-Regime Gated Value+Reversal")
print("=" * 60)
print(f"\nUniverse: {len(SP500_PROXY)} stocks (S&P 500 proxy, survivorship caveat)")
print(f"IS: {IS_START} → {IS_END} | OOS: {OOS_START} → {OOS_END}")
print(f"Drift window: {DRIFT_WINDOW}d, threshold: {DRIFT_THRESH:.0%}")
print(f"Reversal window: {REVERSAL_DAYS}d | Top-N: {TOP_N} | TC: {COST_BPS}bps\n")

print("[1] Fetching prices…")
prices = fetch_prices(SP500_PROXY)
# Drop tickers with insufficient history
prices = prices.dropna(thresh=int(len(prices) * 0.7), axis=1)
print(f"  {len(prices.columns)} tickers with sufficient history")

print("\n[2] Computing signals…")
drift = compute_drift_regime(prices)
reversal = compute_reversal_signal(prices)
reversal_ia = compute_industry_adj_reversal(prices)

if FMP_KEY:
    fcf_ratio = build_fcf_price_ratio(prices)
    # Rank FCF/P cross-sectionally (higher = better value)
    fcf_rank = fcf_ratio.rank(axis=1, pct=True)
else:
    print("  WARNING: FMP_API_KEY not set — skipping FCF/P; Variant A → reversal only")
    fcf_rank = pd.DataFrame(0.5, index=prices.index, columns=prices.columns)

# Reversal rank (higher score = bigger underperformer = better buy)
rev_rank = reversal.rank(axis=1, pct=True)
rev_ia_rank = reversal_ia.rank(axis=1, pct=True)

# Combined scores
score_A = (fcf_rank + rev_rank) / 2   # value + reversal
score_B = rev_rank                      # reversal only
score_C = rev_ia_rank                   # industry-adjusted reversal

print("\n[3] Running variants…")
variants = [
    ("A: drift+value+reversal", score_A),
    ("B: drift+reversal only",  score_B),
    ("C: drift+IA-reversal",    score_C),
]

results = {}
print(f"\n{'Variant':<28} {'IS Sharpe':>10} {'OOS Sharpe':>11} {'OOS CAGR':>10} {'OOS MaxDD':>10}")
print("-" * 74)

for label, score in variants:
    ec = backtest_variant(prices, score, drift, label)
    is_s  = period_stats(ec, IS_START, IS_END)
    oos_s = period_stats(ec, OOS_START, OOS_END)
    gate_str = "PASS" if oos_s["sharpe"] >= 1.3 else "fail"
    print(f"  {label:<26} {is_s['sharpe']:>10.3f} {oos_s['sharpe']:>11.3f} "
          f"{oos_s['cagr']:>9.1%} {oos_s['maxdd']:>9.1%}  {gate_str}")
    results[label] = {"is": is_s, "oos": oos_s}

# SPY baseline
spy = yf.download("SPY", start=IS_START, end=OOS_END, auto_adjust=True,
                   progress=False)["Close"].resample("ME").last()
spy_ec = spy / spy.iloc[0]
spy_oos = period_stats(spy_ec, OOS_START, OOS_END)
print(f"  {'SPY buy-hold':<26} {'—':>10} {spy_oos['sharpe']:>11.3f} "
      f"{spy_oos['cagr']:>9.1%} {spy_oos['maxdd']:>9.1%}")

best_oos = max(
    (results[k]["oos"]["sharpe"] for k in results
     if not np.isnan(results[k]["oos"]["sharpe"])),
    default=0.0,
)
confirmed = best_oos >= 1.3

print("\n" + "=" * 60)
print(f"H308 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
print(f"  Best OOS Sharpe: {best_oos:.3f}  (gate: 1.3)")
print(f"  SPY OOS Sharpe:  {spy_oos['sharpe']:.3f}")
print("=" * 60)

if not confirmed:
    print("""
NOTE: If OOS Sharpe is near 1.0-1.3, consider:
  1. Tightening drift threshold (0.65 vs 0.60)
  2. Shorter reversal window (3-day vs 5-day)
  3. Using historical constituent data to eliminate survivorship bias
  4. Daily rebalance (as in original paper) — much higher Sharpe but impractical TC
""")

out = {
    "hypothesis": "H308",
    "title": "Drift-Regime Gated Value+Reversal",
    "source": "arXiv:2511.12490",
    "universe_size": len(prices.columns),
    "survivorship_caveat": True,
    "is_period": f"{IS_START} to {IS_END}",
    "oos_period": f"{OOS_START} to {OOS_END}",
    "gate": "OOS Sharpe > 1.3",
    "confirmed": bool(confirmed),
    "best_oos_sharpe": float(best_oos),
    "spy_oos_sharpe": float(spy_oos["sharpe"]),
    "variants": {k: {"is": v["is"], "oos": v["oos"]} for k, v in results.items()},
}
path = RESULT_DIR / "h308_results.json"
path.write_text(json.dumps(out, indent=2))
print(f"\nResults → {path}")
