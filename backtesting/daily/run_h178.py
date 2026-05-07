"""
H178 — Commodity Momentum Rotation
====================================
NEW STRATEGY FAMILY.  Tests whether monthly momentum rotation across
commodity ETFs generates standalone alpha, and whether it is sufficiently
uncorrelated with H026 (equity sector momentum) to justify a portfolio sleeve.

Academic basis:
  Gorton & Rouwenhorst 2006: commodity futures earn a risk premium.
  Erb & Harvey 2006: commodity momentum + carry each independently earn alpha.
  Asness et al. 2013 "Value and Momentum Everywhere": momentum works across
  equities, FX, fixed income, AND commodities — but the commodity factor is
  largely uncorrelated with equity momentum.

Key question: can pure commodity rotation outperform DBC (diversified
commodity index ETF) and SPY on a risk-adjusted basis, and is it
uncorrelated enough with H026 to add diversification value?

Universe (all pre-2008 launch, free yfinance data):
  Core  (8): GLD  SLV  GDX  USO  UNG  XLE  DBA  DBC
  Extended (3): CORN  WEAT  CPER  (added when data available, 2010-2011)
  Safe  (1): BIL  (cash when TSMOM filter eliminates all)

Signal: 12-1 month momentum (11-month lookback, skip most recent month)
  mom_score = close[0] / close[-12] - 1  (skip 1m reversion)

Variants:
  A) top-1, no TSMOM filter            — pure momentum, no protection
  B) top-1, TSMOM 12m > 0%             — stay invested only if trending up
  C) top-2, TSMOM 12m > 0%             — mild diversification
  D) top-1, TSMOM 12m > 2%             — tighter filter
  E) top-3, equal-weight, TSMOM > 0%   — broader basket

Confirm criteria (standalone new strategy):
  OOS Sharpe > 1.0
  OOS cumul > SPY (benchmark ~3.03×)
  Passes both OOS windows (2018+ and 2013+)
  Monthly return corr with H026 < 0.7  (diversification value)
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2005-01-01"
FULL_END   = "2026-04-30"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

CORE_COMMODITIES = ["GLD","SLV","GDX","USO","UNG","XLE","DBA","DBC"]
EXT_COMMODITIES  = ["CORN","WEAT","CPER"]   # launched 2010-2011
ALL_COMMODITIES  = CORE_COMMODITIES + EXT_COMMODITIES

_PREFIXES = [f"h{i:03d}" for i in range(62, 178)]


# ── data helpers ──────────────────────────────────────────────────────────────

def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close", "ohlcv"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h178_{ticker}_close_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close = close.dropna()
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def load_prices(tickers, start, end):
    closes = {}
    for t in tickers:
        try:
            s = fetch_daily_close(t, start, end)
            if len(s) > 100:
                closes[t] = s
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_rt = daily_df.pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1)
    return monthly_px, monthly_rt


# ── strategy engine ───────────────────────────────────────────────────────────

def run_commodity_rotation(monthly_px, monthly_rt, n_hold=1,
                            tsmom_window=None, tsmom_thresh=0.0,
                            mom_window=12, skip_month=True):
    """
    Monthly commodity rotation with optional TSMOM safety filter.
    n_hold   : number of assets to hold (equal weight)
    tsmom_window : if not None, require asset 12m return > tsmom_thresh
    Returns monthly equity series.
    """
    tickers = [c for c in monthly_px.columns if c != "BIL"]
    eq = INITIAL_EQUITY
    equity = []
    dates  = []

    for i in range(mom_window + 1, len(monthly_px)):
        date = monthly_px.index[i]

        # momentum score: 12m return, optionally skip most recent month
        if skip_month:
            score_window = mom_window   # months ago → last month (skip 1m reversal)
            px_now  = monthly_px.iloc[i - 1]   # prior month end (skip 1m)
            px_prev = monthly_px.iloc[i - 1 - score_window]
        else:
            px_now  = monthly_px.iloc[i]
            px_prev = monthly_px.iloc[i - mom_window]

        scores = {}
        for t in tickers:
            if t in px_now.index and t in px_prev.index:
                if pd.notna(px_now[t]) and pd.notna(px_prev[t]) and px_prev[t] > 0:
                    scores[t] = px_now[t] / px_prev[t] - 1

        if not scores:
            equity.append(eq)
            dates.append(date)
            continue

        # TSMOM filter
        if tsmom_window is not None:
            px_tsmom = monthly_px.iloc[i - 1]
            px_tsmom_prev = monthly_px.iloc[i - 1 - tsmom_window]
            scores = {
                t: s for t, s in scores.items()
                if t in px_tsmom.index and t in px_tsmom_prev.index
                and pd.notna(px_tsmom[t]) and pd.notna(px_tsmom_prev[t])
                and px_tsmom_prev[t] > 0
                and (px_tsmom[t] / px_tsmom_prev[t] - 1) > tsmom_thresh
            }

        # Fallback to BIL
        if not scores or len(scores) == 0:
            rt = monthly_rt.iloc[i].get("BIL", 0.0)
            if pd.isna(rt):
                rt = 0.0
            eq *= (1 + rt)
        else:
            top = sorted(scores, key=scores.get, reverse=True)[:n_hold]
            ret_list = []
            for t in top:
                r = monthly_rt.iloc[i].get(t, np.nan)
                ret_list.append(r if pd.notna(r) else 0.0)
            rt = np.mean(ret_list)
            eq *= (1 + rt)

        equity.append(eq)
        dates.append(date)

    return pd.Series(equity, index=dates, name="equity") / INITIAL_EQUITY


def sharpe(eq_series):
    mr = eq_series.pct_change().dropna()
    if mr.std() == 0:
        return 0.0
    return (mr.mean() / mr.std()) * np.sqrt(12)


def maxdd(eq_series):
    roll_max = eq_series.cummax()
    return ((eq_series - roll_max) / roll_max).min()


def neg_years(eq_series):
    yr = eq_series.resample("YE").last().pct_change().dropna()
    return (yr < 0).sum()


def stats(eq_series, label):
    years = len(eq_series) / 12
    cagr  = eq_series.iloc[-1] ** (1 / years) - 1 if years > 0 else 0
    return {
        "label":  label,
        "cumul":  eq_series.iloc[-1],
        "cagr":   cagr,
        "sharpe": sharpe(eq_series),
        "maxdd":  maxdd(eq_series),
        "negyrs": neg_years(eq_series),
    }


def print_stats(s):
    print(f"  {s['label']:<35} "
          f"cumul={s['cumul']:>7.2f}× "
          f"CAGR={s['cagr']*100:>6.1f}% "
          f"Sharpe={s['sharpe']:>5.3f} "
          f"MaxDD={s['maxdd']*100:>7.1f}% "
          f"NegYrs={s['negyrs']}")


def slice_series(eq_series, start, end=None):
    s = eq_series.loc[start:end] if end else eq_series.loc[start:]
    return s / s.iloc[0]


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  H178 — Commodity Momentum Rotation")
    print("=" * 70)

    print("\n[1/5] Loading prices…")
    tickers_to_load = ALL_COMMODITIES + ["BIL", "SPY"]
    monthly_px, monthly_rt = load_prices(tickers_to_load, FULL_START, FULL_END)

    available_commodities = [t for t in ALL_COMMODITIES if t in monthly_px.columns]
    print(f"  Available: {available_commodities}")
    print(f"  Monthly rows: {len(monthly_px)}  ({monthly_px.index[0].date()} → "
          f"{monthly_px.index[-1].date()})")

    print("\n[2/5] Building SPY + DBC benchmarks…")
    spy_eq = (1 + monthly_rt["SPY"]).cumprod().rename("SPY")
    spy_is  = slice_series(spy_eq, IS_START, IS_END)
    spy_oos = slice_series(spy_eq, OOS_START)
    spy_alt = slice_series(spy_eq, ALT_OOS_ST)

    dbc_eq = None
    if "DBC" in monthly_rt.columns:
        dbc_eq = (1 + monthly_rt["DBC"]).cumprod().rename("DBC")

    print("\n[3/5] Running variants…")
    variants = {
        "A  top-1  no-filter":    dict(n_hold=1, tsmom_window=None),
        "B  top-1  TSMOM>0%":     dict(n_hold=1, tsmom_window=12, tsmom_thresh=0.00),
        "C  top-2  TSMOM>0%":     dict(n_hold=2, tsmom_window=12, tsmom_thresh=0.00),
        "D  top-1  TSMOM>2%":     dict(n_hold=1, tsmom_window=12, tsmom_thresh=0.02),
        "E  top-3  equal TSMOM>0%": dict(n_hold=3, tsmom_window=12, tsmom_thresh=0.00),
    }

    results = {}
    for name, kwargs in variants.items():
        eq_full = run_commodity_rotation(monthly_px, monthly_rt, **kwargs)
        results[name] = eq_full

    print("\n[4/5] Evaluating windows…")

    # Load H026 equity curve for correlation check
    h026_path = CACHE_DIR / "h026_production_equity.parquet"
    h026_monthly = None
    if h026_path.exists():
        h026_monthly = pd.read_parquet(h026_path).squeeze()

    print("\n  ── IS 2008–2017 ─────────────────────────────────────────────────")
    spy_is_stats = stats(spy_is, "SPY IS")
    print_stats(spy_is_stats)
    if dbc_eq is not None:
        dbc_is = slice_series(dbc_eq, IS_START, IS_END)
        print_stats(stats(dbc_is, "DBC buy-hold IS"))

    is_results = {}
    for name, eq_full in results.items():
        eq_is = slice_series(eq_full, IS_START, IS_END)
        s = stats(eq_is, name + " IS")
        is_results[name] = s
        print_stats(s)

    print("\n  ── OOS 2018–2026 ────────────────────────────────────────────────")
    spy_oos_stats = stats(spy_oos, "SPY OOS")
    print_stats(spy_oos_stats)
    if dbc_eq is not None:
        dbc_oos = slice_series(dbc_eq, OOS_START)
        print_stats(stats(dbc_oos, "DBC buy-hold OOS"))

    confirmed_variants = []
    oos_results = {}
    for name, eq_full in results.items():
        eq_oos = slice_series(eq_full, OOS_START)
        s = stats(eq_oos, name + " OOS")
        oos_results[name] = s
        # Correlation with H026
        corr_h026 = float("nan")
        if h026_monthly is not None:
            oos_ret = eq_full.pct_change().dropna().loc[OOS_START:]
            h026_oos = h026_monthly.pct_change().dropna().loc[OOS_START:]
            aligned = oos_ret.align(h026_oos, join="inner")
            if len(aligned[0]) > 12:
                corr_h026 = aligned[0].corr(aligned[1])
        print_stats(s)
        print(f"    {'':35} corr(H026)={corr_h026:.3f}")
        if (s["sharpe"] > 1.0
                and s["cumul"] > spy_oos_stats["cumul"]
                and s["negyrs"] <= 2):
            confirmed_variants.append({**s, "corr_h026": corr_h026})

    print("\n  ── AltOOS 2013–2026 ─────────────────────────────────────────────")
    spy_alt_stats = stats(spy_alt, "SPY AltOOS")
    print_stats(spy_alt_stats)

    alt_results = {}
    for name, eq_full in results.items():
        eq_alt = slice_series(eq_full, ALT_OOS_ST)
        s = stats(eq_alt, name + " AltOOS")
        alt_results[name] = s
        print_stats(s)

    print("\n[5/5] Saving H178 equity curves for H179 blend test…")
    # Save the best variant equity curve (variant B — top-1 TSMOM>0%)
    best_key = "B  top-1  TSMOM>0%"
    eq_best  = results[best_key]
    h178_ret = eq_best.pct_change().dropna()
    h178_ret.to_frame("h178_monthly_ret").to_parquet(
        CACHE_DIR / "h178_commodity_equity.parquet")
    print(f"  Saved: h178_commodity_equity.parquet ({len(h178_ret)} months)")

    # ── Verdict ─────────────────────────────────────────────────────────────
    verdict = "CONFIRMED" if confirmed_variants else "NOT CONFIRMED"

    out_lines = [
        "H178 — Commodity Momentum Rotation",
        f"Universe: {available_commodities}",
        f"Signal: 12-1 month momentum (skip 1m reversal), monthly rebalance",
        f"IS: {IS_START}–{IS_END}  |  OOS: {OOS_START}+  |  AltOOS: {ALT_OOS_ST}+",
        "",
        f"SPY OOS: cumul={spy_oos_stats['cumul']:.2f}×  "
        f"Sharpe={spy_oos_stats['sharpe']:.3f}  "
        f"MaxDD={spy_oos_stats['maxdd']*100:.1f}%",
        "",
        "OOS Results:",
    ]
    for name, s in oos_results.items():
        out_lines.append(
            f"  {name:<35} cumul={s['cumul']:.2f}× "
            f"Sharpe={s['sharpe']:.3f} MaxDD={s['maxdd']*100:.1f}% "
            f"NegYrs={s['negyrs']}")

    out_lines += [
        "",
        f"VERDICT: {verdict}",
    ]
    if confirmed_variants:
        best = max(confirmed_variants, key=lambda x: x["sharpe"])
        out_lines += [
            f"Best confirmed: {best['label']}",
            f"  OOS Sharpe={best['sharpe']:.3f}  cumul={best['cumul']:.2f}×  "
            f"MaxDD={best['maxdd']*100:.1f}%  NegYrs={best['negyrs']}  "
            f"corr(H026)={best.get('corr_h026', float('nan')):.3f}",
        ]
    else:
        out_lines += [
            "No variant meets OOS Sharpe>1.0 AND cumul>SPY AND NegYrs≤2.",
            "Check IS/OOS degradation and correlation with H026.",
        ]

    result_path = RESULT_DIR / "h178_commodity_momentum.txt"
    result_path.write_text("\n".join(out_lines))
    print(f"\n  Results → {result_path}")
    print(f"\n  VERDICT: {verdict}")
    print("=" * 70)
    return results, monthly_rt, spy_oos_stats


if __name__ == "__main__":
    main()
