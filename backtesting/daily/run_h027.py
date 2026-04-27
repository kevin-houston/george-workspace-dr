"""
H027 — Yield-Curve-Conditioned Bond Signal

Variants:
  H027a (base):
    - Long TLT when 10Y–2Y spread < 0 (inverted curve)
    - Cash (SHY or 0%) when spread >= 0

  H027b (extended):
    - Long TLT when spread < 0
    - Long SPY when spread >= 0.5%  (steep curve = growth)
    - Cash when spread in [0, 0.5%)

Hypothesis: inverted yield curve signals recession risk → bonds (TLT)
outperform as rates eventually fall. Steep curve = growth regime → equities.

Data:
  - 10Y–2Y spread: FRED T10Y2Y (direct CSV, no key required)
  - TLT, SPY, SHY: yfinance
  - Period: 2003-01-01 to 2026-04-25
  - Rebalance: monthly (first trading day of each month)

Correlation:
  - Monthly returns compared against H020 monthly rebalancer returns
    (loaded from h020_aftertax_results.json equity curve if available)
"""

import json
import sys
import hashlib
import io
from pathlib import Path
from math import sqrt, log

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

START = "2003-01-01"
END   = "2026-04-25"

STEEP_THRESHOLD = 0.005   # 0.5% = 50 bps for H027b SPY regime

CACHE_DIR   = Path(__file__).parent.parent / "cache"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

FRED_T10Y2Y_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y2Y"


# ─────────────────────────────────────────────
# Data fetching
# ─────────────────────────────────────────────

def fetch_fred_spread() -> pd.Series:
    """Fetch 10Y-2Y Treasury spread from FRED (daily, no API key needed)."""
    cache = CACHE_DIR / "fred_t10y2y.parquet"
    if cache.exists():
        print("  Loading T10Y2Y spread from cache …")
        return pd.read_parquet(cache)["spread"]

    print("  Downloading T10Y2Y spread from FRED …")
    resp = requests.get(FRED_T10Y2Y_URL, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text), parse_dates=["observation_date"])
    df = df.rename(columns={"observation_date": "date", "T10Y2Y": "spread"})
    df = df.set_index("date").sort_index()
    # Replace "." (missing) with NaN, cast to float
    df["spread"] = pd.to_numeric(df["spread"], errors="coerce")
    df = df.dropna()

    # Cache as parquet (date index becomes column name)
    df.to_parquet(cache)
    print(f"  Cached {len(df)} days of T10Y2Y data.")
    return df["spread"]


def fetch_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    """Download adjusted close prices for a list of tickers."""
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    cache = CACHE_DIR / f"h027_prices_{h}.parquet"

    if cache.exists():
        return pd.read_parquet(cache)

    print(f"  Downloading {tickers} from {start} to {end} …")
    raw = yf.download(tickers, start=start, end=end,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]]
        closes.columns = tickers

    closes = closes.dropna(how="all")
    closes.to_parquet(cache)
    return closes


# ─────────────────────────────────────────────
# Monthly regime assignment
# ─────────────────────────────────────────────

def build_monthly_regimes(spread_daily: pd.Series,
                          prices: pd.DataFrame,
                          steep_threshold: float = 0.005) -> pd.DataFrame:
    """
    For each month-start trading day, assign a regime based on the
    most recent available spread (last day of prior month or nearest prior value).

    Returns a DataFrame indexed by month-start date with columns:
      spread, regime_a (H027a), regime_b (H027b)
    """
    # Get all trading days from price data
    trading_days = prices.index

    # First trading day of each month
    td_series = pd.Series(trading_days, index=trading_days)
    month_starts = td_series.groupby(td_series.index.to_period("M")).first()

    rows = []
    for period, entry_date in month_starts.items():
        # Use spread value as of prior trading day (no look-ahead)
        prior_days = spread_daily.index[spread_daily.index < entry_date]
        if len(prior_days) == 0:
            continue
        spread_val = float(spread_daily.loc[prior_days[-1]])

        # H027a regime
        if spread_val < 0:
            regime_a = "TLT"
        else:
            regime_a = "CASH"

        # H027b regime
        if spread_val < 0:
            regime_b = "TLT"
        elif spread_val >= steep_threshold:
            regime_b = "SPY"
        else:
            regime_b = "CASH"

        rows.append({
            "entry_date": entry_date,
            "spread": round(spread_val, 4),
            "regime_a": regime_a,
            "regime_b": regime_b,
        })

    df = pd.DataFrame(rows).set_index("entry_date")
    return df


# ─────────────────────────────────────────────
# Backtest engine
# ─────────────────────────────────────────────

def run_backtest(regimes: pd.DataFrame,
                 prices: pd.DataFrame,
                 regime_col: str,
                 label: str) -> dict:
    """
    Monthly rebalancing backtest.
    On each month-start, invest 100% in the specified asset or hold cash.
    Returns are computed as the price change from this month-start to the next.
    Cash returns = SHY monthly return (if available), else 0%.

    Returns dict with equity_curve (pd.Series) and trades (list).
    """
    equity = 100.0   # normalized to 100
    equity_pts = [(regimes.index[0], equity)]
    trades = []

    dates = list(regimes.index)

    for i, entry_date in enumerate(dates):
        # Find exit: next month-start, or last available date
        if i + 1 < len(dates):
            exit_date = dates[i + 1]
        else:
            # Last month: carry to end of data
            future = prices.index[prices.index > entry_date]
            if len(future) == 0:
                break
            exit_date = future[-1]

        asset = regimes.loc[entry_date, regime_col]
        spread_val = float(regimes.loc[entry_date, "spread"])

        if asset == "CASH":
            # Use SHY if available, else 0
            if "SHY" in prices.columns:
                shy_start = prices["SHY"].asof(entry_date)
                shy_end   = prices["SHY"].asof(exit_date)
                if shy_start > 0 and pd.notna(shy_start) and pd.notna(shy_end):
                    ret = (shy_end / shy_start) - 1.0
                else:
                    ret = 0.0
            else:
                ret = 0.0
        else:
            p_start = prices[asset].asof(entry_date)
            p_end   = prices[asset].asof(exit_date)
            if p_start > 0 and pd.notna(p_start) and pd.notna(p_end):
                ret = (p_end / p_start) - 1.0
            else:
                ret = 0.0

        equity_new = equity * (1 + ret)

        trades.append({
            "entry_date": str(entry_date.date()),
            "exit_date":  str(exit_date.date()),
            "spread":     spread_val,
            "regime":     asset,
            "monthly_return": round(float(ret), 6),
            "equity_before":  round(float(equity), 4),
            "equity_after":   round(float(equity_new), 4),
        })

        equity = equity_new
        equity_pts.append((exit_date, equity))

    eq = pd.Series(
        [v for _, v in equity_pts],
        index=pd.DatetimeIndex([d for d, _ in equity_pts])
    ).sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]

    return {"equity_curve": eq, "trades": trades, "label": label}


# ─────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series, label: str = "") -> dict:
    eq = eq.dropna().sort_index()
    if len(eq) < 4:
        return {"error": "insufficient data"}

    rets = eq.pct_change().dropna()
    n_months = len(rets)
    years    = n_months / 12.0

    total_return = (eq.iloc[-1] / eq.iloc[0]) - 1
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    monthly_mean = rets.mean()
    monthly_std  = rets.std()
    sharpe = (monthly_mean / monthly_std * sqrt(12)) if monthly_std > 0 else 0.0

    # Max drawdown
    running_max = eq.cummax()
    dd = (eq - running_max) / running_max
    max_dd = float(dd.min())

    return {
        "label":        label,
        "n_months":     int(n_months),
        "total_return": round(float(total_return), 4),
        "cagr":         round(float(cagr), 4),
        "sharpe":       round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4),
        "monthly_mean": round(float(monthly_mean), 6),
        "monthly_std":  round(float(monthly_std), 6),
    }


def regime_breakdown(trades: list, regime_col_key: str = "regime") -> dict:
    """Count months per regime and compute avg return per regime."""
    from collections import defaultdict
    counts = defaultdict(int)
    ret_sum = defaultdict(float)

    for t in trades:
        r = t[regime_col_key]
        counts[r] += 1
        ret_sum[r] += t["monthly_return"]

    total = sum(counts.values())
    result = {}
    for r in sorted(counts):
        n = counts[r]
        result[r] = {
            "months": n,
            "pct_time": round(n / total, 4) if total > 0 else 0,
            "avg_monthly_return": round(ret_sum[r] / n, 6) if n > 0 else 0,
        }
    return result


def compute_correlation(eq_h027: pd.Series, h020_monthly: pd.Series) -> float:
    """Compute Pearson correlation of monthly returns between H027 and H020."""
    rets_h027 = eq_h027.pct_change().dropna()
    # Resample H020 to monthly if needed
    rets_h020 = h020_monthly.dropna()

    # Align on common months (period-based)
    rets_h027.index = rets_h027.index.to_period("M")
    rets_h020.index = rets_h020.index.to_period("M")

    # Deduplicate: keep last value per period (handles partial last month)
    rets_h027 = rets_h027[~rets_h027.index.duplicated(keep="last")]
    rets_h020 = rets_h020[~rets_h020.index.duplicated(keep="last")]

    common = rets_h027.index.intersection(rets_h020.index)
    if len(common) < 6:
        return float("nan")

    a = rets_h027.loc[common].values.astype(float)
    b = rets_h020.loc[common].values.astype(float)
    corr = float(np.corrcoef(a, b)[0, 1])
    return round(corr, 4)


# ─────────────────────────────────────────────
# Load H020 monthly returns for correlation
# ─────────────────────────────────────────────

def load_h020_returns() -> pd.Series:
    """
    Load H020 monthly returns from the h020_aftertax_results.json or
    h018_h020_results.json. Returns a pd.Series of monthly returns.
    """
    # Try to find equity curve data in h018_h020 results
    p1 = RESULTS_DIR.parent / "daily" / "h018_h020_results.json"
    p2 = RESULTS_DIR / "h020_aftertax_results.json"

    for p in [p1, p2]:
        if p.exists():
            with open(p) as f:
                data = json.load(f)
            # Look for monthly return data stored as a list/series
            if "monthly_returns" in data:
                mr = data["monthly_returns"]
                if isinstance(mr, dict):
                    s = pd.Series(mr)
                    s.index = pd.DatetimeIndex(s.index)
                    return s
            # Look inside nested keys
            for key in ["h020", "pretax", "aftertax"]:
                if key in data and isinstance(data[key], dict):
                    if "monthly_returns" in data[key]:
                        mr = data[key]["monthly_returns"]
                        if isinstance(mr, dict):
                            s = pd.Series(mr)
                            s.index = pd.DatetimeIndex(s.index)
                            return s

    # If no stored monthly returns found, fetch SPY+TLT+GLD+IEF+QQQ
    # and reconstruct H020 (equal-weight monthly rebalance) from scratch
    print("  H020 monthly returns not cached; reconstructing from prices …")
    h020_tickers = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
    prices = fetch_prices(h020_tickers, "2008-01-01", END)

    # Equal-weight monthly rebalance: compute avg of monthly returns
    monthly_closes = prices.resample("ME").last()
    monthly_rets = monthly_closes.pct_change().dropna()
    portfolio_ret = monthly_rets.mean(axis=1)   # equal-weight avg
    return portfolio_ret


# ─────────────────────────────────────────────
# Benchmarks
# ─────────────────────────────────────────────

def tlt_bh_stats(prices: pd.DataFrame) -> dict:
    """Buy-and-hold TLT stats over full period."""
    if "TLT" not in prices.columns:
        return {}
    tlt = prices["TLT"].dropna()
    monthly = tlt.resample("ME").last()
    return calc_stats(monthly / monthly.iloc[0] * 100, label="TLT Buy-Hold")


def spy_bh_stats(prices: pd.DataFrame) -> dict:
    if "SPY" not in prices.columns:
        return {}
    spy = prices["SPY"].dropna()
    monthly = spy.resample("ME").last()
    return calc_stats(monthly / monthly.iloc[0] * 100, label="SPY Buy-Hold")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("H027 — Yield-Curve-Conditioned Bond Signal")
    print("=" * 55)

    # ── Fetch data ──────────────────────────────────────
    print("Fetching T10Y2Y spread from FRED …")
    spread_daily = fetch_fred_spread()
    spread_daily = spread_daily.loc[START:END]

    print("Fetching TLT, SPY, SHY prices …")
    prices = fetch_prices(["TLT", "SPY", "SHY"], START, END)

    # ── Build monthly regime table ───────────────────────
    print("Building monthly regime table …")
    regimes = build_monthly_regimes(spread_daily, prices,
                                    steep_threshold=STEEP_THRESHOLD)

    print(f"  Regime table: {len(regimes)} months from "
          f"{regimes.index[0].date()} to {regimes.index[-1].date()}")

    # ── Run H027a ────────────────────────────────────────
    print("\nRunning H027a (TLT | Cash) …")
    res_a = run_backtest(regimes, prices, "regime_a", "H027a")

    # ── Run H027b ────────────────────────────────────────
    print("Running H027b (TLT | SPY | Cash) …")
    res_b = run_backtest(regimes, prices, "regime_b", "H027b")

    # ── Statistics ───────────────────────────────────────
    stats_a = calc_stats(res_a["equity_curve"], "H027a")
    stats_b = calc_stats(res_b["equity_curve"], "H027b")

    # Benchmarks (same period)
    bm_tlt = tlt_bh_stats(prices)
    bm_spy = spy_bh_stats(prices)

    # Regime breakdowns
    breakdown_a = regime_breakdown(res_a["trades"])
    breakdown_b = regime_breakdown(res_b["trades"])

    # ── Correlation to H020 ───────────────────────────────
    print("Loading H020 returns for correlation …")
    h020_returns = load_h020_returns()

    corr_a = compute_correlation(res_a["equity_curve"], h020_returns)
    corr_b = compute_correlation(res_b["equity_curve"], h020_returns)
    print(f"  Correlation H027a vs H020: {corr_a:.4f}")
    print(f"  Correlation H027b vs H020: {corr_b:.4f}")

    # ── Print summary ─────────────────────────────────────
    print()
    print("─" * 55)
    print(f"{'Metric':<22} {'H027a':>10} {'H027b':>10} {'TLT B&H':>10} {'SPY B&H':>10}")
    print("─" * 55)
    for key, label in [("cagr", "CAGR"),
                        ("sharpe", "Sharpe"),
                        ("max_drawdown", "Max DD"),
                        ("total_return", "Total Return")]:
        a = stats_a.get(key, 0)
        b = stats_b.get(key, 0)
        t = bm_tlt.get(key, 0)
        s = bm_spy.get(key, 0)
        print(f"  {label:<20} {a:>10.4f} {b:>10.4f} {t:>10.4f} {s:>10.4f}")
    print("─" * 55)

    print()
    print("H027a Regime Breakdown:")
    for regime, info in breakdown_a.items():
        print(f"  {regime:6s}: {info['months']:3d} months ({info['pct_time']:.1%}) "
              f"avg monthly ret = {info['avg_monthly_return']:.3%}")

    print()
    print("H027b Regime Breakdown:")
    for regime, info in breakdown_b.items():
        print(f"  {regime:6s}: {info['months']:3d} months ({info['pct_time']:.1%}) "
              f"avg monthly ret = {info['avg_monthly_return']:.3%}")

    print()
    print(f"Correlation vs H020:  H027a = {corr_a:.4f}  |  H027b = {corr_b:.4f}")

    # ── Build results dict ────────────────────────────────
    results = {
        "strategy": "H027",
        "description": "Yield-Curve-Conditioned Bond Signal",
        "hypothesis": (
            "Inverted yield curve (10Y < 2Y) signals recession risk → TLT outperforms. "
            "Steep curve (spread >= 50bps) signals growth regime → SPY outperforms."
        ),
        "period": {"start": START, "end": END},
        "parameters": {
            "spread_series": "FRED T10Y2Y (10Y minus 2Y Treasury yield)",
            "inversion_threshold": 0.0,
            "steep_threshold_h027b": STEEP_THRESHOLD,
            "rebalance": "monthly, first trading day",
            "cash_instrument": "SHY",
        },
        "h027a": {
            "description": "Long TLT when inverted, else Cash (SHY)",
            "stats": stats_a,
            "regime_breakdown": breakdown_a,
            "correlation_to_h020": corr_a,
        },
        "h027b": {
            "description": "Long TLT when inverted, SPY when steep (>=50bps), else Cash",
            "stats": stats_b,
            "regime_breakdown": breakdown_b,
            "correlation_to_h020": corr_b,
        },
        "benchmarks": {
            "tlt_buy_hold": bm_tlt,
            "spy_buy_hold": bm_spy,
        },
        "spread_stats": {
            "mean_spread":      round(float(spread_daily.loc[START:END].mean()), 4),
            "pct_inverted":     round(float((spread_daily.loc[START:END] < 0).mean()), 4),
            "pct_steep_50bps":  round(float((spread_daily.loc[START:END] >= STEEP_THRESHOLD).mean()), 4),
            "pct_neutral":      round(float(
                ((spread_daily.loc[START:END] >= 0) &
                 (spread_daily.loc[START:END] < STEEP_THRESHOLD)).mean()
            ), 4),
        },
        "trades_h027a": res_a["trades"],
        "trades_h027b": res_b["trades"],
    }

    out_path = RESULTS_DIR / "h027_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved → {out_path}")

    return results


if __name__ == "__main__":
    main()
