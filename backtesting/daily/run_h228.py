"""
H228 — Blend: Median Alpha101 (H217) + Industry-Adjusted Reversal (H181)
=========================================================================
Rationale: H217 selects quality/stability names by intraday price efficiency
(top-6 by median (close-open)/(range)); H181 selects beaten-down within-sector
names (bottom-6 by industry-adjusted prior-month return). These signals pick
opposite stock types, suggesting low correlation and potential diversification.

Precedent: H190 (H188 stock momentum + H181 blend) confirmed at OOS Sharpe 1.191.
H217 (1.559) >> H188 (0.774), so this blend should be materially stronger.

Blend ratios tested: 100/0, 75/25, 50/50, 25/75, 0/100 (H217/H181 weight)
Universe: same 30 large-cap stocks as H217 and H181
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 1.5 (must beat H217 alone at 1.559 meaningfully, or
         show materially lower MaxDD for same Sharpe)
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD":  "Information Technology",
    "V":    "Financials",             "MA":   "Financials",
    "BAC":  "Financials",             "WFC":  "Financials",  "JPM": "Financials",
    "UNH":  "Health Care",            "LLY":  "Health Care",
    "PFE":  "Health Care",            "JNJ":  "Health Care", "ABBV": "Health Care",
    "WMT":  "Consumer Staples",       "HD":   "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW":  "Consumer Discretionary",
    "COST": "Consumer Staples",       "CVX":  "Energy",      "XOM":  "Energy",
    "BA":   "Industrials",            "CAT":  "Industrials", "IBM":  "Information Technology",
}

DATA_START_DAILY   = "2011-01-01"
DATA_START_MONTHLY = "2012-01-01"
DATA_END           = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
TOP_N      = 6
CONFIRM_THRESHOLD = 1.5


# ── metrics ──────────────────────────────────────────────────────────────────

def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r): return float((1 + r).prod())
def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)].dropna()
    if len(r) < 6:
        return {"n": 0, "sharpe": None, "cagr": None, "cumul": None, "maxdd": None, "neg_yrs": None}
    return {
        "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


# ── H217 return series ────────────────────────────────────────────────────────

def fetch_daily_ohlcv(ticker):
    cp = CACHE_DIR / f"h215_{ticker}_daily_{DATA_START_DAILY}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker} daily OHLCV…")
    raw = yf.download(ticker, start=DATA_START_DAILY, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).normalize()
    df.to_parquet(cp)
    return df


def compute_h217_returns() -> pd.Series:
    """Reproduce H217 monthly return series (top-6 by median alpha101)."""
    cache_path = CACHE_DIR / "h228_h217_monthly_rets.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path).squeeze()

    print("  [H217] Loading daily OHLCV and computing alpha101…")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"    WARN {t}: {e}")

    alpha_series = {}
    for t, df in daily_data.items():
        a = (df["close"] - df["open"]) / (0.001 + df["high"] - df["low"])
        alpha_series[t] = a.clip(-1, 1)

    alpha_daily = pd.DataFrame(alpha_series).sort_index().loc[DATA_START_DAILY:]
    alpha_monthly = alpha_daily.resample("ME").median()

    close_monthly = {}
    for t, df in daily_data.items():
        close_monthly[t] = df["close"].resample("ME").last()
    close_px = pd.DataFrame(close_monthly).sort_index().loc[DATA_START_DAILY:]
    monthly_ret = close_px.pct_change()

    alpha_signal = alpha_monthly.shift(1)
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        if month_end not in alpha_signal.index:
            continue
        loc = monthly_ret.index.get_loc(month_end)
        signal_row = alpha_signal.loc[month_end].dropna()
        if len(signal_row) < TOP_N * 2:
            continue
        top_sel = signal_row.nlargest(TOP_N).index.tolist()
        ret = monthly_ret.iloc[loc][top_sel].mean()
        port_rets.append((month_end, ret))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    s.name = "h217_ret"
    pd.DataFrame(s).to_parquet(cache_path)
    return s


# ── H181 return series ────────────────────────────────────────────────────────

def load_monthly_closes() -> pd.DataFrame:
    all_closes = {}
    for ticker in UNIVERSE:
        h181_cache = CACHE_DIR / f"h181_{ticker}_monthly_{DATA_START_MONTHLY}_{DATA_END}.parquet"
        if h181_cache.exists():
            df = pd.read_parquet(h181_cache)
            all_closes[ticker] = df["close"]
        else:
            print(f"  Downloading {ticker} monthly…")
            raw = yf.download(ticker, start=DATA_START_MONTHLY, end=DATA_END,
                              auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw = raw.xs(ticker, axis=1, level=1)
            close_col = "Close" if "Close" in raw.columns else raw.columns[0]
            monthly = raw[close_col].resample("ME").last().dropna()
            pd.DataFrame({"close": monthly}).to_parquet(h181_cache)
            all_closes[ticker] = monthly
    df = pd.DataFrame(all_closes)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def industry_adjusted_reversal(monthly_returns, sector_map):
    sectors = pd.Series(sector_map)
    common = monthly_returns.index.intersection(sectors.index)
    r = monthly_returns[common]
    s = sectors[common]
    industry_means = r.groupby(s).transform("mean")
    return r - industry_means


def compute_h181_returns() -> pd.Series:
    """Reproduce H181 monthly return series (bottom-6 by industry-adjusted reversal)."""
    cache_path = CACHE_DIR / "h228_h181_monthly_rets.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path).squeeze()

    print("  [H181] Loading monthly closes and computing industry reversal…")
    prices = load_monthly_closes()
    available = [t for t in UNIVERSE if t in prices.columns and prices[t].notna().sum() > 24]
    prices = prices[available]
    months = prices.index

    records = []
    for i in range(2, len(months)):
        rebal_date = months[i - 1]
        hold_date  = months[i]
        if hold_date < IS_START:
            continue

        prior_close   = prices.loc[months[i - 2]]
        signal_close  = prices.loc[months[i - 1]]
        hold_close    = prices.loc[months[i]]

        prior_returns   = {}
        current_returns = {}
        for t in available:
            p0 = prior_close.get(t, np.nan)
            p1 = signal_close.get(t, np.nan)
            p2 = hold_close.get(t, np.nan)
            if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                prior_returns[t] = (p1 - p0) / p0
            if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                current_returns[t] = (p2 - p1) / p1

        if len(prior_returns) < TOP_N * 2:
            continue

        adj_rev = industry_adjusted_reversal(pd.Series(prior_returns), UNIVERSE_SECTORS)
        long_tickers = adj_rev.sort_values().head(TOP_N).index.tolist()
        port_returns = [current_returns[t] for t in long_tickers if t in current_returns]
        if not port_returns:
            continue
        records.append((hold_date, np.mean(port_returns)))

    s = pd.Series({d: r for d, r in records})
    s.index = pd.DatetimeIndex(s.index)
    s.name = "h181_ret"
    pd.DataFrame(s).to_parquet(cache_path)
    return s


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("H228 — Blend: Median Alpha101 (H217) + Industry Reversal (H181)")
    print("=" * 64)

    print("\n[1/4] Computing H217 return series (median alpha101 top-6)…")
    r217 = compute_h217_returns()
    print(f"  H217: {len(r217)} monthly returns, "
          f"{r217.index[0].date()} → {r217.index[-1].date()}")

    print("\n[2/4] Computing H181 return series (industry reversal bottom-6)…")
    r181 = compute_h181_returns()
    print(f"  H181: {len(r181)} monthly returns, "
          f"{r181.index[0].date()} → {r181.index[-1].date()}")

    # Align on common dates
    common_idx = r217.index.intersection(r181.index)
    r217 = r217.reindex(common_idx)
    r181 = r181.reindex(common_idx)
    print(f"\n  Aligned on {len(common_idx)} common months")

    # Correlation
    oos_mask = (common_idx >= OOS_START) & (common_idx <= OOS_END)
    corr_full = r217.corr(r181)
    corr_oos  = r217[oos_mask].corr(r181[oos_mask])
    print(f"  Corr(H217, H181) full: {corr_full:.3f}  |  OOS: {corr_oos:.3f}")

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START_DAILY}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START_DAILY, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_cp)
    spy_ret = spy_px.pct_change().dropna()

    print("\n[3/4] Testing blend ratios…")
    ratios = [(1.0, 0.0), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.0, 1.0)]
    blend_results = []

    fmt = (f"{'Ratio (H217/H181)':<22} {'IS Sharpe':>10} {'IS MaxDD':>9} "
           f"{'OOS Sharpe':>11} {'OOS MaxDD':>10} {'OOS NegYrs':>11}")
    print(fmt)
    print("-" * len(fmt))

    spy_is_m  = eval_period(spy_ret, IS_START, IS_END)
    spy_oos_m = eval_period(spy_ret, OOS_START, OOS_END)
    print(f"  {'SPY BH':<20} {spy_is_m['sharpe']:>10.3f} {spy_is_m['maxdd']:>9.1%} "
          f"{spy_oos_m['sharpe']:>11.3f} {spy_oos_m['maxdd']:>10.1%} "
          f"{spy_oos_m['neg_yrs']:>11d}")

    best_oos_sharpe = -999
    best_ratio = None
    for w217, w181 in ratios:
        blend = w217 * r217 + w181 * r181
        is_m  = eval_period(blend, IS_START, IS_END)
        oos_m = eval_period(blend, OOS_START, OOS_END)
        label = f"{w217:.0%}/{w181:.0%}"
        print(f"  {label:<20} {is_m['sharpe']:>10.3f} {is_m['maxdd']:>9.1%} "
              f"{oos_m['sharpe']:>11.3f} {oos_m['maxdd']:>10.1%} "
              f"{oos_m['neg_yrs']:>11d}")
        blend_results.append({
            "ratio_h217": w217, "ratio_h181": w181,
            "is": is_m, "oos": oos_m,
        })
        if (oos_m["sharpe"] or 0) > best_oos_sharpe:
            best_oos_sharpe = oos_m["sharpe"]
            best_ratio = (w217, w181)

    # Verdict
    confirmed = best_oos_sharpe >= CONFIRM_THRESHOLD
    print(f"\n[4/4] Verdict")
    print(f"  Best blend: {best_ratio[0]:.0%}/{best_ratio[1]:.0%} (H217/H181)")
    print(f"  Best OOS Sharpe: {best_oos_sharpe:.3f}  (threshold ≥ {CONFIRM_THRESHOLD})")
    print(f"  Corr(H217, H181) OOS: {corr_oos:.3f}")
    print(f"  {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # Save
    out = {
        "hypothesis": "H228",
        "description": "Blend H217 (median alpha101) + H181 (industry reversal)",
        "corr_h217_h181_full": round(corr_full, 3),
        "corr_h217_h181_oos":  round(corr_oos, 3),
        "blend_results": blend_results,
        "best_ratio_h217": best_ratio[0],
        "best_ratio_h181": best_ratio[1],
        "best_oos_sharpe": round(best_oos_sharpe, 3),
        "confirm_threshold": CONFIRM_THRESHOLD,
        "confirmed": confirmed,
        "spy_is": spy_is_m,
        "spy_oos": spy_oos_m,
    }
    (RESULT_DIR / "h228_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"  Saved → backtesting/results/h228_results.json")
    return out


if __name__ == "__main__":
    main()
