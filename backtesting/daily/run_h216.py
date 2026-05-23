"""
H216 — Volume-Price Divergence (alpha002 + alpha013 Composite)
================================================================
Kakushadze (2015) "101 Formulaic Alphas":

    alpha002 = -rank(delta(log(volume), 2)) * rank((close - open) / open)
    alpha013 = -rank(cov(rank(close), rank(volume), 5))

Hypothesis: stocks where volume surges but price doesn't follow (or vice versa)
are due for reversal. The composite alpha002+013 captures volume-price
decoupling — a different dimension from pure price momentum.

Expected to be negatively correlated with momentum (H198/H212) in crash periods:
when markets crash, price drops but volume surges → alpha002/013 signal long
on the same stocks that momentum signals short → diversification benefit.

Implementation:
- Compute daily alpha002 and alpha013 in cross-sectional rank space
- Average the two signals; resample to monthly mean
- Long top-6 (highest composite = strongest volume-price divergence), monthly rebalance
- OHLCV-only: no VWAP required

IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 0.6 (these are weaker signals; expect to add value in blend)

Note on cross-sectional ranks: applied within the 30-stock universe daily,
so rank(x) = percentile rank of x among the 30 stocks on that date.
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from scipy.stats import rankdata

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

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
TOP_N      = 6


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    # Re-use H215 cache if available
    for prefix in ["h215", "h216"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).normalize()
    cp_out = CACHE_DIR / f"h216_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    df.to_parquet(cp_out)
    return df


def cross_rank(series: pd.Series) -> pd.Series:
    """Percentile rank [0, 1] within the series (handles NaN)."""
    valid = series.dropna()
    if len(valid) == 0:
        return series * np.nan
    ranks = rankdata(valid, method="average") / len(valid)
    result = series.copy() * np.nan
    result.loc[valid.index] = ranks
    return result


def compute_alpha002(close: pd.DataFrame, open_: pd.DataFrame,
                     volume: pd.DataFrame) -> pd.DataFrame:
    """
    alpha002 = -rank(delta(log(volume), 2)) * rank((close - open) / open)
    Cross-sectional rank applied daily across the 30-stock universe.
    delta(x, d) = x - x.shift(d)
    """
    log_vol_delta = np.log(volume + 1).diff(2)   # delta over 2 days
    price_chg     = (close - open_) / (open_.replace(0, np.nan))

    # Daily cross-sectional ranks
    rank_vol  = log_vol_delta.rank(axis=1, pct=True)
    rank_pchg = price_chg.rank(axis=1, pct=True)

    alpha = -rank_vol * rank_pchg
    return alpha


def compute_alpha013(close: pd.DataFrame, volume: pd.DataFrame,
                     window: int = 5) -> pd.DataFrame:
    """
    alpha013 = -rank(cov(rank(close), rank(volume), 5))
    Rolling 5-day covariance of cross-sectional close rank vs volume rank.
    Then cross-sectionally rank the covariances.
    """
    rank_close  = close.rank(axis=1, pct=True)
    rank_volume = volume.rank(axis=1, pct=True)

    # Rolling covariance per ticker — more efficient row-by-row approach
    cov_df = pd.DataFrame(index=close.index, columns=close.columns, dtype=float)
    for col in close.columns:
        rc = rank_close[col]
        rv = rank_volume[col]
        # Rolling sample covariance
        cov_col = rc.rolling(window).cov(rv)
        cov_df[col] = cov_col

    # Cross-sectional rank of covariance, then negate
    ranked_cov = cov_df.rank(axis=1, pct=True)
    alpha = -ranked_cov
    return alpha


def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r): return float((1 + r).prod())
def maxdd(r): eq = (1 + r).cumprod(); return float((eq / eq.cummax() - 1).min())


def eval_period(rets, label, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"label": label, "n": 0}
    return {
        "label": label, "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def main():
    print("H216 — Volume-Price Divergence (alpha002 + alpha013 composite)")

    print("Loading daily OHLCV data…")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN: {t} — {e}")
    print(f"  Loaded {len(daily_data)} tickers")

    # Assemble panel DataFrames
    close  = pd.DataFrame({t: daily_data[t]["close"]  for t in daily_data}).sort_index()
    open_  = pd.DataFrame({t: daily_data[t]["open"]   for t in daily_data}).sort_index()
    volume = pd.DataFrame({t: daily_data[t]["volume"] for t in daily_data}).sort_index()
    close  = close.loc[DATA_START:]
    open_  = open_.loc[DATA_START:]
    volume = volume.loc[DATA_START:]
    print(f"  Panel: {close.shape[0]} days × {close.shape[1]} stocks")

    # Compute alpha signals
    print("Computing alpha002 (volume-surge vs price-change)…")
    a002 = compute_alpha002(close, open_, volume)
    print("Computing alpha013 (cov(rank_close, rank_vol), 5d)…")
    a013 = compute_alpha013(close, volume, window=5)

    # Composite: equal blend of both signals (both already in [-1, 1] cross-sectional rank space)
    composite = (a002 + a013) / 2.0

    # Monthly mean signal — shift 1 month so signal known at end of M is applied to M+1 returns
    composite_monthly = composite.resample("ME").mean().shift(1)
    print(f"  Monthly composite signal (1-month lag): {composite_monthly.shape}")

    # Monthly returns
    close_monthly = close.resample("ME").last()
    monthly_ret = close_monthly.pct_change()

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_cp)
    spy_ret = spy_px.pct_change().dropna()

    print("\n=== Exp A: Long top-6 composite alpha002+013 ===")
    port_rets_top = []
    port_rets_bot = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        if month_end not in composite_monthly.index:
            continue
        loc = monthly_ret.index.get_loc(month_end)
        row = composite_monthly.loc[month_end].dropna()
        if len(row) < TOP_N * 2:
            continue
        top_sel = row.nlargest(TOP_N).index.tolist()
        bot_sel = row.nsmallest(TOP_N).index.tolist()
        port_rets_top.append((month_end, monthly_ret.iloc[loc][top_sel].mean()))
        port_rets_bot.append((month_end, monthly_ret.iloc[loc][bot_sel].mean()))

    rets_top = pd.Series({d: r for d, r in port_rets_top})
    rets_top.index = pd.DatetimeIndex(rets_top.index)
    rets_bot = pd.Series({d: r for d, r in port_rets_bot})
    rets_bot.index = pd.DatetimeIndex(rets_bot.index)

    fmt = f"{'Strategy':<30} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(fmt)
    print("-" * len(fmt))
    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    for label, rets in [("Top-6 composite (H216)", rets_top), ("Bottom-6 composite", rets_bot)]:
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        print(f"{label:<30} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")
    print(f"{'SPY BH':<30} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")

    # Correlation with H198/H212 (momentum) — key diagnostic
    print("\n=== Exp B: Individual alpha002 vs alpha013 ===")
    for a_label, a_signal in [("alpha002", a002), ("alpha013", a013)]:
        sig_m = a_signal.resample("ME").mean().shift(1)
        pr = []
        for month_end in months:
            if month_end not in sig_m.index:
                continue
            loc = monthly_ret.index.get_loc(month_end)
            row = sig_m.loc[month_end].dropna()
            if len(row) < TOP_N * 2:
                continue
            sel = row.nlargest(TOP_N).index.tolist()
            pr.append((month_end, monthly_ret.iloc[loc][sel].mean()))
        rs = pd.Series({d: r for d, r in pr})
        rs.index = pd.DatetimeIndex(rs.index)
        is_r  = eval_period(rs, a_label, IS_START, IS_END)
        oos_r = eval_period(rs, a_label, OOS_START, OOS_END)
        print(f"  {a_label:<10} IS Sharpe {is_r['sharpe']:.3f} | OOS Sharpe {oos_r['sharpe']:.3f}")

    print("\n=== Correlation with SPY ===")
    all_top = rets_top.reindex(spy_ret.index).dropna()
    spy_aligned = spy_ret.reindex(all_top.index).dropna()
    corr_spy = all_top.corr(spy_aligned)
    print(f"  Top-6 composite vs SPY: {corr_spy:.3f}")

    top_is  = eval_period(rets_top, "composite", IS_START, IS_END)
    top_oos = eval_period(rets_top, "composite", OOS_START, OOS_END)
    confirmed = top_oos.get("sharpe", 0) >= 0.6

    print(f"\n=== Verdict ===")
    print(f"Top-6 composite OOS Sharpe: {top_oos['sharpe']:.3f} (threshold ≥ 0.6)")
    print(f"Top-6 composite OOS MaxDD:  {top_oos['maxdd']:.1%}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H216",
        "top6_is":    top_is,
        "top6_oos":   top_oos,
        "bot6_is":    eval_period(rets_bot, "bot-6", IS_START, IS_END),
        "bot6_oos":   eval_period(rets_bot, "bot-6", OOS_START, OOS_END),
        "spy_is":     spy_is,
        "spy_oos":    spy_oos,
        "corr_spy":   round(corr_spy, 3),
        "confirmed":  confirmed,
    }
    (RESULT_DIR / "h216_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {RESULT_DIR}/h216_results.json")
    return out


if __name__ == "__main__":
    main()
