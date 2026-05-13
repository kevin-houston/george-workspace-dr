"""
H192 — Betting Against Beta (BAB): 30-Stock Large-Cap Universe
===============================================================
Tests the BAB factor (Frazzini & Pedersen 2014 "Betting Against Beta",
Journal of Financial Economics 111:1, pp 1–45) on the same 30-stock
large-cap S&P 500 universe used by H181/H188/H190/H191.

Background: CAPM predicts high-beta stocks earn higher returns. Empirically,
low-beta stocks deliver higher risk-adjusted returns than high-beta stocks —
the 'low-beta anomaly'. Mechanism: leverage-constrained investors overpay for
high-beta to achieve levered market exposure, depressing their future returns.

Related confirmed hypotheses on this universe:
  H181  (CONFIRMED): Industry-adjusted reversal. OOS Sharpe=1.138
  H188  (CONFIRMED): 52-wk high proximity momentum. OOS Sharpe=0.774
  H191  (CONFIRMED): Low-vol anomaly. Best variant (C): OOS Sharpe=1.110
  H190  (CONFIRMED): H188+H181 blend. OOS Sharpe=1.191

KEY QUESTION: Does beta-based ranking add anything beyond volatility ranking?
Theory says yes: vol and beta differ because vol includes idiosyncratic risk
while beta measures only systematic risk. Stocks can have low vol + high beta
or high vol + low beta. In practice on large-cap stocks the signals overlap
substantially (~0.7 correlation) so we need to test empirically.

Signal variants:
  A: Raw 1yr daily beta (252d rolling OLS vs SPY)
  B: Vasicek-shrunk beta: 0.6 * raw_beta + 0.4 * 1.0 (shrink toward market)
  C: Low-beta + low-vol hybrid 50/50 (replicate H191-C but with beta instead of vol)
  D: Sector-neutral beta (rank within GICS sector)

Universe: 30 large-cap S&P 500 stocks, same as H181/H188/H191
IS: 2013–2020, OOS: 2021–2026
Confirm: OOS Sharpe > 0.5, OOS cumul > 1.3×
Cross-check: Corr with H181, H191-A OOS — assess diversification value
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
SPY      = "SPY"

DATA_START = "2012-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
QUINTILE_N = 6   # long bottom-6 (lowest beta stocks)


def load_prices() -> tuple[pd.DataFrame, pd.Series]:
    """Returns (stock_prices_df, spy_prices_series)."""
    cache = CACHE_DIR / f"h188_daily_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        print("  Loading daily prices from H188 cache…")
        df = pd.read_parquet(cache)
    else:
        print(f"  Downloading {len(UNIVERSE)} tickers from yfinance…")
        raw = yf.download(UNIVERSE + [SPY], start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        df.dropna(how="all", axis=0).to_parquet(cache)
        df = pd.read_parquet(cache)

    # Fetch SPY separately if not cached with universe
    if SPY not in df.columns:
        spy_raw = yf.download(SPY, start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
        spy_px = spy_raw["Close"] if "Close" in spy_raw.columns else spy_raw.squeeze()
        spy_px = spy_px.reindex(df.index, method="ffill")
        df[SPY] = spy_px

    spy_px = df[SPY].copy()
    stock_px = df[UNIVERSE].copy()
    return stock_px, spy_px


def rolling_beta(stock_rets: pd.Series, spy_rets: pd.Series, window: int = 252) -> float:
    """Rolling OLS beta of stock vs SPY over last `window` daily returns."""
    if len(stock_rets) < window // 2:
        return np.nan
    x = spy_rets.tail(window).values
    y = stock_rets.tail(window).values
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < window // 3:
        return np.nan
    xm, ym = x[mask].mean(), y[mask].mean()
    cov = np.mean((x[mask] - xm) * (y[mask] - ym))
    var = np.mean((x[mask] - xm) ** 2)
    return cov / var if var > 1e-10 else np.nan


def run_bab_strategy(
    daily_prices: pd.DataFrame,
    spy_prices: pd.Series,
    variant: str = "A",
    label: str = "",
    n_long: int = QUINTILE_N,
) -> pd.Series:
    """
    Run monthly BAB (low-beta) strategy. Returns monthly return series.

    A: Raw 1yr daily beta — long bottom-6
    B: Vasicek-shrunk beta (0.6*raw + 0.4*1.0)
    C: Hybrid 50/50 low-beta + low-vol
    D: Sector-neutral 1yr beta (rank within GICS sector)
    """
    monthly_px = daily_prices.resample("ME").last()
    spy_monthly = spy_prices.resample("ME").last()
    month_ends  = monthly_px.index

    # Pre-compute daily returns
    daily_rets     = daily_prices.pct_change()
    spy_daily_rets = spy_prices.pct_change()

    # For variant C we also need vol
    if variant == "C":
        vol_daily_rets = daily_prices.pct_change()

    rets, dates = [], []

    for i, hold_date in enumerate(month_ends[1:], 1):
        rebal_date = month_ends[i - 1]

        hist_rets     = daily_rets[daily_rets.index <= rebal_date]
        spy_hist_rets = spy_daily_rets[spy_daily_rets.index <= rebal_date]

        if len(hist_rets) < 130:
            continue

        # ── Beta computation ─────────────────────────────────────────────
        spy_ser = spy_hist_rets.tail(252)

        betas = {}
        for t in UNIVERSE:
            if t not in hist_rets.columns:
                continue
            b = rolling_beta(hist_rets[t], spy_ser, window=252)
            if pd.notna(b):
                betas[t] = b

        if len(betas) < n_long * 2:
            continue

        beta_series = pd.Series(betas)

        # ── Variant-specific signal ──────────────────────────────────────
        if variant == "A":
            signal = beta_series  # sort ascending → bottom = lowest beta

        elif variant == "B":
            # Vasicek shrinkage toward 1.0
            shrunk = 0.6 * beta_series + 0.4 * 1.0
            signal = shrunk

        elif variant == "C":
            # 50/50 low-beta + low-vol hybrid
            if len(hist_rets) < 253:
                continue
            vol_hist = vol_daily_rets[vol_daily_rets.index <= rebal_date]
            vol_1yr = vol_hist.tail(253).std() * np.sqrt(252)
            vol_1yr = vol_1yr.dropna()
            common = beta_series.index.intersection(vol_1yr.index)
            if len(common) < n_long * 2:
                continue
            beta_s = beta_series[common]
            vol_s  = vol_1yr[common]
            beta_rank = beta_s.rank()   # low beta → low rank (want low)
            vol_rank  = vol_s.rank()    # low vol  → low rank (want low)
            # Combined score: average of the two ranks
            signal = (beta_rank + vol_rank) / 2.0

        elif variant == "D":
            # Sector-neutral: rank beta within GICS sector
            sectors = pd.Series(UNIVERSE_SECTORS)
            common = beta_series.index.intersection(sectors.index)
            df_tmp = pd.DataFrame({
                "beta": beta_series[common],
                "sector": sectors[common],
            })
            df_tmp["rank_in_sector"] = df_tmp.groupby("sector")["beta"].rank(ascending=True)
            signal = df_tmp["rank_in_sector"]

        if len(signal) < n_long:
            continue

        # Long bottom-N (lowest signal value)
        long_tickers = signal.nsmallest(n_long).index.tolist()

        # Compute this month's return (rebal_date → hold_date)
        port_rets = []
        for t in long_tickers:
            if t in monthly_px.columns:
                p1 = monthly_px.iloc[i - 1].get(t, np.nan)
                p2 = monthly_px.iloc[i].get(t, np.nan)
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    port_rets.append((p2 - p1) / p1)
        if port_rets:
            rets.append(np.mean(port_rets))
            dates.append(hold_date)

    return pd.Series(rets, index=dates, name=label)


def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    if len(returns) == 0:
        return {"label": label, "cumul": 0, "sharpe": 0, "max_dd_pct": 0, "neg_years": 0}
    cum    = (1 + returns).cumprod()
    n_yrs  = len(returns) / 12.0
    cagr   = cum.iloc[-1] ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = returns.mean() / returns.std() * np.sqrt(12) if returns.std() > 0 else 0.0
    dd     = (cum / cum.cummax()) - 1
    annual = returns.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {
        "label":      label,
        "n_months":   len(returns),
        "cumul":      round(float(cum.iloc[-1]), 4),
        "cagr_pct":   round(cagr * 100, 2),
        "sharpe":     round(sharpe, 3),
        "max_dd_pct": round(float(dd.min()) * 100, 2),
        "neg_years":  int(annual.lt(0).sum()),
    }


def print_metrics(m: dict, window: str = "") -> None:
    tag = f"[{window}]" if window else ""
    print(f"    {tag} {m['label']:<35}  Sharpe={m['sharpe']:.3f}  "
          f"Cumul={m['cumul']:.3f}×  CAGR={m['cagr_pct']:.1f}%  "
          f"MaxDD={m['max_dd_pct']:.1f}%  NegYrs={m['neg_years']}")


def main():
    print("=" * 72)
    print("  H192 — Betting Against Beta (BAB): 30-Stock Large-Cap Universe")
    print("=" * 72)

    print("\n[1] Loading prices…")
    prices, spy_px = load_prices()
    print(f"    {prices.shape[1]} tickers, {len(prices)} trading days")

    # SPY benchmark monthly
    spy_monthly = spy_px.resample("ME").last().pct_change().dropna()

    variants = [
        ("A", "Raw 1yr beta"),
        ("B", "Vasicek-shrunk beta (0.6/0.4)"),
        ("C", "Low-beta + Low-vol 50/50 hybrid"),
        ("D", "Sector-neutral 1yr beta"),
    ]

    print("\n[2] Running 4 BAB variants…")

    all_results = {}
    for code, desc in variants:
        print(f"\n  Variant {code}: {desc}")
        full_rets = run_bab_strategy(prices, spy_px, variant=code, label=f"H192-{code}: {desc}")
        if full_rets.empty:
            print("    No results — skipping.")
            continue

        is_rets   = full_rets[(full_rets.index >= IS_START)  & (full_rets.index <= IS_END)]
        oos_rets  = full_rets[(full_rets.index >= OOS_START) & (full_rets.index <= OOS_END)]
        alt_rets  = full_rets[full_rets.index >= IS_START]

        m_is  = calc_metrics(is_rets,  label=f"H192-{code} IS  2013–2020")
        m_oos = calc_metrics(oos_rets, label=f"H192-{code} OOS 2021–2026")
        m_alt = calc_metrics(alt_rets, label=f"H192-{code} ALT 2013–2026")

        print_metrics(m_is,  "IS ")
        print_metrics(m_oos, "OOS")
        print_metrics(m_alt, "ALT")

        all_results[code] = {
            "full": full_rets,
            "is": is_rets,
            "oos": oos_rets,
            "alt": alt_rets,
            "m_is": m_is,
            "m_oos": m_oos,
            "m_alt": m_alt,
        }

    if not all_results:
        print("ERROR: No variants produced results.")
        return

    # ── SPY benchmark ────────────────────────────────────────────────────
    spy_oos = spy_monthly[(spy_monthly.index >= OOS_START) & (spy_monthly.index <= OOS_END)]
    spy_alt = spy_monthly[spy_monthly.index >= IS_START]
    m_spy_oos = calc_metrics(spy_oos, label="SPY benchmark OOS 2021–2026")
    m_spy_alt = calc_metrics(spy_alt, label="SPY benchmark ALT 2013–2026")
    print(f"\n  SPY benchmark:")
    print_metrics(m_spy_oos, "OOS")
    print_metrics(m_spy_alt, "ALT")

    # ── Correlation analysis ─────────────────────────────────────────────
    print("\n[3] Correlation analysis (OOS 2021–2026)…")

    # Load H181 OOS returns for cross-correlation
    try:
        h181_cache = CACHE_DIR / "h181_oos_returns.parquet"
        if h181_cache.exists():
            h181_oos = pd.read_parquet(h181_cache).squeeze()
        else:
            # Reconstruct from H181 run — use H181 script's load function
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "run_h181", WORKSPACE / "backtesting/daily/run_h181.py")
            h181_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(h181_mod)
            h181_full = h181_mod.run_reversal_strategy(prices)
            h181_oos  = h181_full[(h181_full.index >= OOS_START) & (h181_full.index <= OOS_END)]
        print(f"    H181 OOS loaded: {len(h181_oos)} months")
    except Exception as e:
        print(f"    H181 OOS not available ({e}) — skipping H181 cross-corr")
        h181_oos = None

    # Load H191-A OOS returns
    try:
        h191_cache = CACHE_DIR / "h191_oos_returns.parquet"
        if h191_cache.exists():
            h191a_oos = pd.read_parquet(h191_cache).squeeze()
        else:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "run_h191", WORKSPACE / "backtesting/daily/run_h191.py")
            h191_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(h191_mod)
            h191_full = h191_mod.run_vol_strategy(prices, variant="A")
            h191a_oos = h191_full[(h191_full.index >= OOS_START) & (h191_full.index <= OOS_END)]
        print(f"    H191-A OOS loaded: {len(h191a_oos)} months")
    except Exception as e:
        print(f"    H191-A OOS not available ({e}) — skipping H191 cross-corr")
        h191a_oos = None

    for code, data in all_results.items():
        oos_s = data["oos"]
        corr_spy  = oos_s.corr(spy_oos.reindex(oos_s.index))
        line = f"    H192-{code}: Corr(SPY)={corr_spy:.3f}"
        if h181_oos is not None:
            c181 = oos_s.corr(h181_oos.reindex(oos_s.index))
            line += f"  Corr(H181)={c181:.3f}"
        if h191a_oos is not None:
            c191 = oos_s.corr(h191a_oos.reindex(oos_s.index))
            line += f"  Corr(H191-A)={c191:.3f}"
        print(line)

    # ── Verdict ──────────────────────────────────────────────────────────
    print("\n[4] Verdict…")
    confirmed = []
    for code, data in all_results.items():
        m = data["m_oos"]
        ok = m["sharpe"] > 0.5 and m["cumul"] > 1.3
        status = "CONFIRMED ✓" if ok else "NOT CONFIRMED ✗"
        print(f"    H192-{code}: OOS Sharpe={m['sharpe']:.3f} Cumul={m['cumul']:.3f}×  → {status}")
        if ok:
            confirmed.append(code)

    if confirmed:
        best = max(confirmed, key=lambda c: all_results[c]["m_oos"]["sharpe"])
        print(f"\n  Best variant: H192-{best} ({variants[ord(best)-65][1]})")
        print(f"    OOS Sharpe={all_results[best]['m_oos']['sharpe']:.3f}  "
              f"MaxDD={all_results[best]['m_oos']['max_dd_pct']:.1f}%")
    else:
        best = None

    # ── Save results ─────────────────────────────────────────────────────
    outfile = RESULT_DIR / "h192_bab_30stock.txt"
    lines = [
        "H192 — Betting Against Beta: 30-Stock Large-Cap Universe",
        "=" * 60,
        "",
    ]
    for code, data in all_results.items():
        for window, key in [("IS 2013-2020", "m_is"), ("OOS 2021-2026", "m_oos"), ("ALT 2013-2026", "m_alt")]:
            m = data[key]
            lines.append(
                f"H192-{code} [{window}]: Sharpe={m['sharpe']:.3f}  "
                f"Cumul={m['cumul']:.3f}×  CAGR={m['cagr_pct']:.1f}%  "
                f"MaxDD={m['max_dd_pct']:.1f}%  NegYrs={m['neg_years']}"
            )
        lines.append("")
    lines.append(f"SPY OOS 2021-2026: Sharpe={m_spy_oos['sharpe']:.3f}  Cumul={m_spy_oos['cumul']:.3f}×")
    lines.append(f"Confirmed variants: {confirmed}")
    outfile.write_text("\n".join(lines))
    print(f"\n  Results saved → {outfile}")

    print("\n" + "=" * 72)
    print("  H192 COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
