"""
H193 — H192-D (Sector-Neutral BAB) + H181 (Industry Reversal) Blend
=====================================================================
Tests whether blending H192-D (sector-neutral Betting Against Beta,
OOS Sharpe=1.367) with H181 (industry-adjusted reversal, OOS Sharpe=1.138)
improves risk-adjusted returns on the same 30-stock universe.

Background from H192:
  H192-D ranks stocks by rolling 1yr OLS beta vs SPY WITHIN their GICS sector.
  Long bottom-6 (lowest sector-relative beta). OOS Sharpe=1.367, MaxDD=-17.1%.
  Corr(H192-D, H191-A) OOS=0.723 — too correlated with low-vol to add as 2nd satellite.

Background from H181:
  H181 ranks stocks by (last-month return - sector mean return).
  Long bottom-6 (most negative industry-adjusted return). OOS Sharpe=1.138, MaxDD=-18.4%.
  Corr(H181, H026) OOS=0.293 — low; deployed as primary satellite in paper trading.

KEY QUESTION for H193:
  H192-D selects STRUCTURALLY low-beta stocks within each sector (persistent).
  H181 selects TEMPORARILY beaten-down stocks within each sector (mean-reverting).
  These are orthogonal dimensions of the same sector-neutralized signal space.
  Hypothesis: the two signals select DIFFERENT stocks each month → genuine diversification.

If Corr(H192-D, H181) < 0.5 AND blend achieves OOS Sharpe > 1.367 (beats H192-D alone),
then H193 becomes a better satellite recommendation than H181 alone.

Blend weights tested: H192-D / H181 = 100/0, 80/20, 60/40, 50/50, 40/60, 20/80, 0/100
"""

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

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
UNIVERSE = list(UNIVERSE_SECTORS.keys())
SPY = "SPY"

DATA_START = "2012-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
QUINTILE_N = 6

BLEND_WEIGHTS = [
    (1.00, 0.00, "H192-D pure"),
    (0.80, 0.20, "80/20 (BAB/REV)"),
    (0.60, 0.40, "60/40 (BAB/REV)"),
    (0.50, 0.50, "50/50 (BAB/REV)"),
    (0.40, 0.60, "40/60 (BAB/REV)"),
    (0.20, 0.80, "20/80 (BAB/REV)"),
    (0.00, 1.00, "H181 pure"),
]


def load_prices() -> tuple[pd.DataFrame, pd.Series]:
    cache = CACHE_DIR / f"h188_daily_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        print("  Loading daily prices from H188/H192 cache…")
        df = pd.read_parquet(cache)
    else:
        print(f"  Downloading {len(UNIVERSE) + 1} tickers from yfinance…")
        raw = yf.download(UNIVERSE + [SPY], start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        df = df.dropna(how="all", axis=0)
        df.to_parquet(cache)

    if SPY not in df.columns:
        spy_raw = yf.download(SPY, start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
        spy_px = spy_raw["Close"].squeeze() if "Close" in spy_raw.columns else spy_raw.squeeze()
        df[SPY] = spy_px.reindex(df.index, method="ffill")

    return df[UNIVERSE].copy(), df[SPY].copy()


def rolling_beta(stock_rets: pd.Series, spy_rets: pd.Series, window: int = 252) -> float:
    x = spy_rets.tail(window).values
    y = stock_rets.tail(window).values
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < window // 3:
        return np.nan
    xm, ym = x[mask].mean(), y[mask].mean()
    cov = np.mean((x[mask] - xm) * (y[mask] - ym))
    var = np.mean((x[mask] - xm) ** 2)
    return cov / var if var > 1e-10 else np.nan


def compute_monthly_signals(
    daily_prices: pd.DataFrame, spy_prices: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns two DataFrames, each indexed by month-end date, columns = UNIVERSE tickers.
    - bab_signals: sector-neutral beta rank (H192-D signal; lower = more eligible)
    - rev_signals: industry-adjusted reversal (H181 signal; lower = more eligible)
    """
    monthly_px   = daily_prices.resample("ME").last()
    month_ends   = monthly_px.index
    daily_rets   = daily_prices.pct_change()
    spy_daily    = spy_prices.pct_change()

    sectors = pd.Series(UNIVERSE_SECTORS)

    bab_rows, rev_rows, dates = [], [], []

    for i, hold_date in enumerate(month_ends[1:], 1):
        rebal_date = month_ends[i - 1]

        hist_rets = daily_rets[daily_rets.index <= rebal_date]
        if len(hist_rets) < 130:
            continue

        # ── H192-D: sector-neutral beta rank ─────────────────────────────
        spy_ser = spy_daily[spy_daily.index <= rebal_date]
        betas = {}
        for t in UNIVERSE:
            if t in hist_rets.columns:
                b = rolling_beta(hist_rets[t], spy_ser, window=252)
                if pd.notna(b):
                    betas[t] = b

        beta_s = pd.Series(betas)
        common_b = beta_s.index.intersection(sectors.index)
        if len(common_b) < QUINTILE_N * 2:
            continue
        df_b = pd.DataFrame({"beta": beta_s[common_b], "sector": sectors[common_b]})
        df_b["rank"] = df_b.groupby("sector")["beta"].rank(ascending=True)
        bab_signal = df_b["rank"]  # lower rank = lower beta within sector = more eligible

        # ── H181: industry-adjusted reversal ─────────────────────────────
        p0 = monthly_px.iloc[i - 2] if i >= 2 else None
        p1 = monthly_px.iloc[i - 1]
        if p0 is None:
            continue

        rev_rets = {}
        for t in UNIVERSE:
            if t in p0.index and t in p1.index:
                pp0, pp1 = p0[t], p1[t]
                if pd.notna(pp0) and pd.notna(pp1) and pp0 > 0:
                    rev_rets[t] = (pp1 - pp0) / pp0

        rev_s = pd.Series(rev_rets)
        common_r = rev_s.index.intersection(sectors.index)
        if len(common_r) < QUINTILE_N * 2:
            continue
        r = rev_s[common_r]
        s = sectors[common_r]
        industry_means = r.groupby(s).transform("mean")
        rev_signal = r - industry_means  # lower = best reversal candidate

        # Normalize both signals to ranks so they're on the same scale for blending
        common = bab_signal.index.intersection(rev_signal.index)
        if len(common) < QUINTILE_N:
            continue

        bab_rows.append(bab_signal[common].rank(ascending=True))
        rev_rows.append(rev_signal[common].rank(ascending=True))
        dates.append(hold_date)

    bab_df = pd.DataFrame(bab_rows, index=dates)
    rev_df = pd.DataFrame(rev_rows, index=dates)
    return bab_df, rev_df


def run_blend_backtest(
    bab_signals: pd.DataFrame,
    rev_signals: pd.DataFrame,
    daily_prices: pd.DataFrame,
    w_bab: float,
    w_rev: float,
    label: str,
) -> tuple[pd.Series, list[float]]:
    """
    At each month-end rebalance date: blend signal = w_bab * bab_rank + w_rev * rev_rank.
    Long bottom-QUINTILE_N stocks by blended rank (lower = more eligible for both).
    Returns (monthly_returns_series, list_of_monthly_overlaps_with_pure_h181).
    """
    monthly_px = daily_prices.resample("ME").last()
    rets, overlaps = [], []

    for date, row_bab in bab_signals.iterrows():
        if date not in rev_signals.index:
            continue
        row_rev = rev_signals.loc[date]

        common = row_bab.index.intersection(row_rev.index).intersection(
            pd.Index([t for t in UNIVERSE if t in monthly_px.columns])
        )
        if len(common) < QUINTILE_N:
            continue

        blended = w_bab * row_bab[common] + w_rev * row_rev[common]
        long_tickers = blended.nsmallest(QUINTILE_N).index.tolist()

        # For overlap tracking: compare with pure H181 picks
        h181_picks = set(row_rev[common].nsmallest(QUINTILE_N).index.tolist())
        overlaps.append(len(set(long_tickers) & h181_picks) / QUINTILE_N)

        # Monthly return
        hold_idx  = monthly_px.index.get_loc(date)
        rebal_idx = hold_idx - 1
        if rebal_idx < 0:
            continue

        port_rets = []
        for t in long_tickers:
            if t in monthly_px.columns:
                p1 = monthly_px.iloc[rebal_idx][t]
                p2 = monthly_px.iloc[hold_idx][t]
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    port_rets.append((p2 - p1) / p1)
        if port_rets:
            rets.append(np.mean(port_rets))

    idx_dates = []
    for date in bab_signals.index:
        if date not in rev_signals.index:
            continue
        common = bab_signals.loc[date].index.intersection(rev_signals.loc[date].index)
        if len(common) >= QUINTILE_N:
            idx_dates.append(date)

    n = min(len(rets), len(idx_dates))
    return pd.Series(rets[:n], index=idx_dates[:n], name=label), overlaps


def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    if len(returns) == 0:
        return {"label": label, "cumul": 0, "sharpe": 0, "max_dd_pct": 0, "neg_years": 0}
    cum   = (1 + returns).cumprod()
    n_yrs = len(returns) / 12.0
    cagr  = cum.iloc[-1] ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = returns.mean() / returns.std() * np.sqrt(12) if returns.std() > 0 else 0.0
    dd     = (cum / cum.cummax()) - 1
    annual = returns.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {
        "label":    label,
        "n_months": len(returns),
        "cumul":    round(float(cum.iloc[-1]), 4),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe":   round(sharpe, 3),
        "max_dd_pct": round(float(dd.min()) * 100, 2),
        "neg_years":  int(annual.lt(0).sum()),
    }


def print_metrics(m: dict, window: str = "") -> None:
    tag = f"[{window}]" if window else ""
    print(f"    {tag} {m['label']:<38}  Sharpe={m['sharpe']:.3f}  "
          f"Cumul={m['cumul']:.3f}×  CAGR={m['cagr_pct']:.1f}%  "
          f"MaxDD={m['max_dd_pct']:.1f}%  NegYrs={m['neg_years']}")


def main():
    print("=" * 76)
    print("  H193 — H192-D (Sector-Neutral BAB) + H181 (Industry Reversal) Blend")
    print("=" * 76)

    print("\n[1] Loading prices…")
    prices, spy_px = load_prices()
    print(f"    {prices.shape[1]} tickers, {len(prices)} trading days")

    print("\n[2] Computing monthly signals (H192-D beta ranks + H181 reversal ranks)…")
    bab_signals, rev_signals = compute_monthly_signals(prices, spy_px)
    print(f"    {len(bab_signals)} monthly rebalance dates computed")

    spy_monthly = spy_px.resample("ME").last().pct_change().dropna()
    spy_oos = spy_monthly[(spy_monthly.index >= OOS_START) & (spy_monthly.index <= OOS_END)]
    spy_alt = spy_monthly[spy_monthly.index >= IS_START]
    m_spy_oos = calc_metrics(spy_oos, "SPY OOS 2021–2026")
    m_spy_alt = calc_metrics(spy_alt, "SPY ALT 2013–2026")

    print(f"\n[3] Baseline benchmarks:")
    print_metrics(m_spy_oos, "OOS")
    print_metrics(m_spy_alt, "ALT")

    print("\n[4] Running blend variants…")
    all_full_rets = {}

    for w_bab, w_rev, lbl in BLEND_WEIGHTS:
        full_rets, overlaps = run_blend_backtest(
            bab_signals, rev_signals, prices, w_bab, w_rev, lbl
        )
        if full_rets.empty:
            print(f"  {lbl}: no results")
            continue

        is_rets  = full_rets[(full_rets.index >= IS_START)  & (full_rets.index <= IS_END)]
        oos_rets = full_rets[(full_rets.index >= OOS_START) & (full_rets.index <= OOS_END)]
        alt_rets = full_rets[full_rets.index >= IS_START]

        m_is  = calc_metrics(is_rets,  f"{lbl} IS")
        m_oos = calc_metrics(oos_rets, f"{lbl} OOS")
        m_alt = calc_metrics(alt_rets, f"{lbl} ALT")

        avg_overlap = np.mean(overlaps) if overlaps else float("nan")
        print(f"\n  [{lbl}]  avg_overlap_with_H181={avg_overlap:.2f}")
        print_metrics(m_is,  "IS ")
        print_metrics(m_oos, "OOS")
        print_metrics(m_alt, "ALT")

        all_full_rets[lbl] = oos_rets

    # ── Correlation matrix (OOS) ─────────────────────────────────────────────
    if len(all_full_rets) >= 2:
        print("\n[5] OOS correlation matrix (H193 variants):")
        oos_df = pd.DataFrame(all_full_rets)
        oos_df = oos_df.dropna(how="all")
        corr = oos_df.corr()
        labels = list(corr.columns)
        print("    " + "  ".join(f"{l[:12]:>12}" for l in labels))
        for row_lbl in labels:
            row = corr.loc[row_lbl]
            print("    " + f"{row_lbl[:12]:>12}" + "  "
                  + "  ".join(f"{row[c]:>12.3f}" for c in labels))

        # Correlation with SPY
        print("\n    Corr vs SPY OOS:")
        for lbl, ser in all_full_rets.items():
            common_idx = ser.index.intersection(spy_oos.index)
            if len(common_idx) > 5:
                c = ser[common_idx].corr(spy_oos[common_idx])
                print(f"      {lbl:<38} Corr(SPY)={c:.3f}")

    print("\n[6] Summary — confirm criteria: OOS Sharpe > 1.367 (beats H192-D pure)")
    print("    Bonus: MaxDD < -17.1% improvement over H192-D")
    print()
    for lbl, oos_ser in all_full_rets.items():
        m = calc_metrics(oos_ser, lbl)
        flag = "★ BEATS H192-D" if m["sharpe"] > 1.367 else (
               "✓ BEATS H181"   if m["sharpe"] > 1.138 else "  ")
        print(f"    {flag} {lbl:<38}  OOS Sharpe={m['sharpe']:.3f}  MaxDD={m['max_dd_pct']:.1f}%")

    # ── Save results ─────────────────────────────────────────────────────────
    out = RESULT_DIR / "h193_bab_reversal_blend.txt"
    lines = ["H193 — H192-D Sector-Neutral BAB + H181 Industry Reversal Blend\n"]
    for lbl, oos_ser in all_full_rets.items():
        m = calc_metrics(oos_ser, lbl)
        lines.append(
            f"{lbl}: OOS Sharpe={m['sharpe']:.3f} Cumul={m['cumul']:.3f}× "
            f"CAGR={m['cagr_pct']:.1f}% MaxDD={m['max_dd_pct']:.1f}% NegYrs={m['neg_years']}\n"
        )
    out.write_text("".join(lines))
    print(f"\n✓ Results saved to {out}")


if __name__ == "__main__":
    main()
