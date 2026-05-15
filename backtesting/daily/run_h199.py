"""
H199 — Sector-Neutral Cross-Sectional Momentum
================================================
H198 showed 6-1m momentum has OOS Sharpe 1.174 but Corr-SPY=0.717.
High market correlation limits diversification value.

Sector-neutral adjustment (same structure as H181 for reversal):
  MOM^SN_i = R_i(t-7,t-1) - R̄_sector(t-7,t-1)
where R̄_sector = equal-weight avg 6-1m return of same-GICS-sector stocks

Hypothesis: removing sector-level drift reduces market beta and SPY
correlation while preserving idiosyncratic momentum signal.

Universe / IS / OOS: identical to H198 / H181.
Confirm: OOS Sharpe > 0.5, Cumul > 1.3×, lower Corr-SPY than H198.
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

UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD":  "Information Technology",
    "V":    "Financials",             "MA":   "Financials",
    "BAC":  "Financials",             "WFC":  "Financials", "JPM": "Financials",
    "UNH":  "Health Care",            "LLY":  "Health Care",
    "PFE":  "Health Care",            "JNJ":  "Health Care", "ABBV": "Health Care",
    "WMT":  "Consumer Staples",       "HD":   "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW":  "Consumer Discretionary",
    "COST": "Consumer Staples",       "CVX":  "Energy",     "XOM":  "Energy",
    "BA":   "Industrials",            "CAT":  "Industrials","IBM":  "Information Technology",
}
UNIVERSE = list(UNIVERSE_SECTORS.keys())

SECTOR_MAP = {}
for ticker, sector in UNIVERSE_SECTORS.items():
    SECTOR_MAP.setdefault(sector, []).append(ticker)

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
TOP_N      = 6
LOOKBACK   = 6   # best from H198


def load_prices() -> pd.DataFrame:
    frames = []
    for t in UNIVERSE:
        for prefix in [f"h{i:03d}" for i in range(181, 199)]:
            cp = CACHE_DIR / f"{prefix}_{t}_monthly_{DATA_START}_{DATA_END}.parquet"
            if cp.exists():
                frames.append(pd.read_parquet(cp).squeeze().rename(t))
                break
        else:
            cp = CACHE_DIR / f"h198_{t}_monthly_{DATA_START}_{DATA_END}.parquet"
            if cp.exists():
                frames.append(pd.read_parquet(cp).squeeze().rename(t))
            else:
                print(f"  Downloading {t}…")
                raw = yf.download(t, start=DATA_START, end=DATA_END,
                                  auto_adjust=True, progress=False)
                if isinstance(raw.columns, pd.MultiIndex):
                    raw = raw.xs(t, axis=1, level=1)
                s = raw["Close"].resample("ME").last()
                s.name = t
                pd.DataFrame(s).to_parquet(cp)
                frames.append(s)
    return pd.DataFrame(frames).T.sort_index()


def sharpe(r): return float(r.mean()/r.std()*np.sqrt(12)) if r.std()>0 else 0.0
def cumul(r):  return float((1+r).prod())
def maxdd(r):
    eq = (1+r).cumprod()
    return float((eq/eq.cummax()-1).min())


def backtest_raw(prices, lookback=6, top_n=6) -> pd.Series:
    """Standard cross-sectional momentum (H198 method, 6-1m)."""
    monthly_ret = prices.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < lookback + 1:
            continue
        sig = prices.iloc[loc-1] / prices.iloc[loc-lookback-1] - 1
        sig = sig.dropna()
        if len(sig) < top_n:
            continue
        selected = sig.nlargest(top_n).index.tolist()
        port_rets.append((month_end, monthly_ret.iloc[loc][selected].mean()))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def backtest_sector_neutral(prices, lookback=6, top_n=6) -> pd.Series:
    """Sector-neutral momentum: signal = stock 6-1m return - sector avg 6-1m return."""
    monthly_ret = prices.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < lookback + 1:
            continue
        # Raw 6-1m return for each stock
        raw_sig = prices.iloc[loc-1] / prices.iloc[loc-lookback-1] - 1
        # Sector average
        sector_avg = {}
        for sector, members in SECTOR_MAP.items():
            valid = [m for m in members if m in raw_sig.index and not np.isnan(raw_sig[m])]
            if valid:
                sector_avg[sector] = raw_sig[valid].mean()
        # Adjusted signal
        adj_sig = {}
        for t in raw_sig.index:
            if not np.isnan(raw_sig[t]):
                sector = UNIVERSE_SECTORS.get(t, "")
                adj_sig[t] = raw_sig[t] - sector_avg.get(sector, 0)
        adj_sig = pd.Series(adj_sig).dropna()
        if len(adj_sig) < top_n:
            continue
        selected = adj_sig.nlargest(top_n).index.tolist()
        port_rets.append((month_end, monthly_ret.iloc[loc][selected].mean()))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {}
    return {
        "n":      len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean()*12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def main():
    print("H199 — Sector-Neutral Cross-Sectional Momentum")
    print("Loading prices (cached from H198)…")
    prices = load_prices()
    prices = prices.loc[DATA_START:]
    print(f"  {len(prices.columns)} tickers, {len(prices)} months")

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    spy_px = pd.read_parquet(spy_cp).squeeze() if spy_cp.exists() else \
        yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)["Close"].resample("ME").last()
    spy_ret = spy_px.pct_change().dropna()

    print("\nRunning backtests…")
    rets_raw = backtest_raw(prices)
    rets_sn  = backtest_sector_neutral(prices)

    print("\n=== Results: Raw Momentum (H198 best: 6-1m) vs Sector-Neutral ===")
    print(f"{'Strategy':<22} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7} {'Corr-SPY':>9}")
    print("-" * 90)

    for label, rets in [("Raw 6-1m (H198)", rets_raw), ("Sector-neutral 6-1m", rets_sn)]:
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        full = rets[(rets.index >= IS_START) & (rets.index <= OOS_END)]
        corr = full.corr(spy_ret.reindex(full.index))
        print(f"{label:<22} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d} {corr:>9.3f}")

    spy_is  = eval_period(spy_ret, IS_START, IS_END)
    spy_oos = eval_period(spy_ret, OOS_START, OOS_END)
    print(f"{'SPY BH':<22} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d} {'1.000':>9}")

    # Blend test: H199 sector-neutral + H192-D proxy via H181
    # Cross-correlation between SN momentum and H181 reversal (if H181 results exist)
    h181_path = RESULT_DIR / "h181_results.json"
    print("\n=== H181 (reversal) correlation to sector-neutral momentum ===")
    # Re-run H181-style reversal quickly for correlation
    monthly_ret = prices.pct_change()
    rev_rets = []
    rev_months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in rev_months:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < 2:
            continue
        raw_sig = monthly_ret.iloc[loc-1]
        sector_avg = {}
        for sector, members in SECTOR_MAP.items():
            valid = [m for m in members if m in raw_sig.index and not np.isnan(raw_sig[m])]
            if valid:
                sector_avg[sector] = raw_sig[valid].mean()
        adj_sig = {}
        for t in raw_sig.index:
            if not np.isnan(raw_sig[t]):
                sector = UNIVERSE_SECTORS.get(t, "")
                adj_sig[t] = raw_sig[t] - sector_avg.get(sector, 0)
        adj_sig = pd.Series(adj_sig).dropna()
        if len(adj_sig) < 6:
            continue
        # Reversal: LONG bottom-6 (most negative adj return)
        selected = adj_sig.nsmallest(6).index.tolist()
        rev_rets.append((month_end, monthly_ret.iloc[loc][selected].mean()))
    rev_series = pd.Series({d: r for d, r in rev_rets})
    rev_series.index = pd.DatetimeIndex(rev_series.index)

    # Correlation
    common = rets_sn.index.intersection(rev_series.index)
    corr_rev = rets_sn.reindex(common).corr(rev_series.reindex(common))
    print(f"  Sector-neutral MOM vs H181 reversal: Corr = {corr_rev:.3f}")
    print(f"  (H181 OOS Sharpe 1.138 for reference)")

    # Verdict
    sn_is  = eval_period(rets_sn, IS_START, IS_END)
    sn_oos = eval_period(rets_sn, OOS_START, OOS_END)
    full_sn = rets_sn[(rets_sn.index >= IS_START) & (rets_sn.index <= OOS_END)]
    corr_spy_sn = full_sn.corr(spy_ret.reindex(full_sn.index))
    corr_spy_raw = rets_raw[(rets_raw.index >= IS_START) & (rets_raw.index <= OOS_END)].corr(spy_ret.reindex(full_sn.index))

    confirmed = sn_oos.get("sharpe", 0) > 0.5 and sn_oos.get("cumul", 0) > 1.3 and corr_spy_sn < corr_spy_raw

    print(f"\n=== Verdict ===")
    print(f"Sector-neutral MOM: OOS Sharpe {sn_oos['sharpe']:.3f}, Cumul {sn_oos['cumul']:.4f}")
    print(f"Corr-SPY improvement: {corr_spy_raw:.3f} → {corr_spy_sn:.3f} ({'improved' if corr_spy_sn < corr_spy_raw else 'worsened'})")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H199",
        "raw_is": eval_period(rets_raw, IS_START, IS_END),
        "raw_oos": eval_period(rets_raw, OOS_START, OOS_END),
        "sn_is": sn_is,
        "sn_oos": sn_oos,
        "spy_is": spy_is,
        "spy_oos": spy_oos,
        "corr_spy_raw": round(float(corr_spy_raw), 3),
        "corr_spy_sn":  round(float(corr_spy_sn), 3),
        "corr_reversal": round(float(corr_rev), 3),
        "confirmed": confirmed,
    }
    outpath = RESULT_DIR / "h199_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
