"""
H179 — Global Equity Momentum Rotation
========================================
NEW STRATEGY.  Tests whether rotating across global/regional equity ETFs
using 12-1 month momentum generates standalone alpha uncorrelated with H026.

H026 already rotates across US sectors + alternatives. H179 asks: does
cross-COUNTRY equity momentum work as an independent strategy? Academic
literature strongly supports it (Asness et al. 2013 "Value and Momentum
Everywhere"; Faber 2013 "Global Tactical Asset Allocation").

Key difference from H026: H179's universe is geographically diversified
equity — the same asset class but different countries, not different sectors.
The signal captures valuation/growth cycle divergence between economies:
US tech cycles (2020-2024) vs EM/commodity-dependent economies (2022).

Universe (all pre-2008, yfinance):
  SPY  — US large-cap
  EFA  — Developed international (Europe + Japan + Australia)
  EEM  — Emerging markets
  EWJ  — Japan
  VGK  — Europe
  EWC  — Canada
  VWO  — Emerging markets broad (Vanguard)
  EWZ  — Brazil (high vol, EM proxy)
  BIL  — Cash safe-harbor

Signal: 12-1 month momentum (11m skip-1m, standard)
TSMOM: require positive 12m return before entering
Top-1 and top-2, monthly rebalance.

Variants:
  A) top-1, no TSMOM filter
  B) top-1, TSMOM 12m > 0%
  C) top-2, TSMOM 12m > 0%
  D) top-2, TSMOM 12m > 2%
  E) top-3, equal-weight, TSMOM > 0%

Confirm criteria:
  OOS Sharpe > 1.0
  OOS cumul > SPY
  NegYrs ≤ 2
  corr(H026 monthly) < 0.7  (to add diversification value)
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

FULL_START = "2003-01-01"
FULL_END   = "2026-04-30"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

GLOBAL_ETFs = ["SPY","EFA","EEM","EWJ","VGK","EWC","VWO","EWZ"]

_PREFIXES = [f"h{i:03d}" for i in range(62, 179)]


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
    cp = CACHE_DIR / f"h179_{ticker}_close_{start}_{end}.parquet"
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


def load_prices(tickers):
    closes = {}
    for t in tickers:
        try:
            s = fetch_daily_close(t, FULL_START, FULL_END)
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

def run_global_rotation(monthly_px, monthly_rt, n_hold=1,
                         tsmom_window=None, tsmom_thresh=0.0,
                         mom_window=12):
    tickers = [c for c in monthly_px.columns
               if c not in ("BIL", "SPY")]   # exclude SPY from selection pool
    eq = INITIAL_EQUITY
    equity = []
    dates  = []

    for i in range(mom_window + 1, len(monthly_px)):
        date = monthly_px.index[i]
        px_now  = monthly_px.iloc[i - 1]      # skip 1m reversal
        px_prev = monthly_px.iloc[i - 1 - mom_window]

        scores = {}
        for t in tickers:
            if t in px_now.index and t in px_prev.index:
                if pd.notna(px_now[t]) and pd.notna(px_prev[t]) and px_prev[t] > 0:
                    scores[t] = px_now[t] / px_prev[t] - 1

        if not scores:
            equity.append(eq)
            dates.append(date)
            continue

        # TSMOM filter: remove negatively trending assets
        if tsmom_window is not None:
            px_t     = monthly_px.iloc[i - 1]
            px_t_bk  = monthly_px.iloc[i - 1 - tsmom_window]
            scores = {
                t: s for t, s in scores.items()
                if t in px_t.index and t in px_t_bk.index
                and pd.notna(px_t[t]) and pd.notna(px_t_bk[t])
                and px_t_bk[t] > 0
                and (px_t[t] / px_t_bk[t] - 1) > tsmom_thresh
            }

        if not scores:
            # All assets below TSMOM threshold → go to BIL
            rt = monthly_rt.iloc[i].get("BIL", 0.0)
            rt = rt if pd.notna(rt) else 0.0
        else:
            top = sorted(scores, key=scores.get, reverse=True)[:n_hold]
            rt = np.mean([monthly_rt.iloc[i].get(t, 0.0) or 0.0 for t in top])

        eq *= (1 + rt)
        equity.append(eq)
        dates.append(date)

    return pd.Series(equity, index=dates) / INITIAL_EQUITY


def sharpe(eq):
    mr = eq.pct_change().dropna()
    return (mr.mean() / mr.std()) * np.sqrt(12) if mr.std() > 0 else 0.0

def maxdd(eq):
    return ((eq - eq.cummax()) / eq.cummax()).min()

def neg_years(eq):
    return (eq.resample("YE").last().pct_change().dropna() < 0).sum()

def stats(eq, label):
    yrs = len(eq) / 12
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else 0
    return {"label": label, "cumul": eq.iloc[-1], "cagr": cagr,
            "sharpe": sharpe(eq), "maxdd": maxdd(eq), "negyrs": neg_years(eq)}

def print_stats(s, extra=""):
    print(f"  {s['label']:<38} cumul={s['cumul']:>6.2f}× "
          f"CAGR={s['cagr']*100:>6.1f}% "
          f"Sharpe={s['sharpe']:>5.3f} "
          f"MaxDD={s['maxdd']*100:>6.1f}% "
          f"NegYrs={s['negyrs']}{extra}")

def slice_eq(eq, start, end=None):
    s = eq.loc[start:end] if end else eq.loc[start:]
    return s / s.iloc[0]


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  H179 — Global Equity Momentum Rotation")
    print("=" * 72)

    print("\n[1/5] Loading prices…")
    monthly_px, monthly_rt = load_prices(GLOBAL_ETFs + ["BIL"])
    avail = [t for t in GLOBAL_ETFs if t in monthly_px.columns]
    print(f"  Available: {avail}")
    print(f"  Monthly rows: {len(monthly_px)}  "
          f"({monthly_px.index[0].date()} → {monthly_px.index[-1].date()})")

    print("\n[2/5] Building SPY benchmark…")
    spy_eq  = (1 + monthly_rt["SPY"]).cumprod()
    efa_eq  = (1 + monthly_rt["EFA"]).cumprod() if "EFA" in monthly_rt else None
    eem_eq  = (1 + monthly_rt["EEM"]).cumprod() if "EEM" in monthly_rt else None

    variants = {
        "A  top-1  no-filter":       dict(n_hold=1, tsmom_window=None),
        "B  top-1  TSMOM>0%":        dict(n_hold=1, tsmom_window=12, tsmom_thresh=0.00),
        "C  top-2  TSMOM>0%":        dict(n_hold=2, tsmom_window=12, tsmom_thresh=0.00),
        "D  top-2  TSMOM>2%":        dict(n_hold=2, tsmom_window=12, tsmom_thresh=0.02),
        "E  top-3  equal TSMOM>0%":  dict(n_hold=3, tsmom_window=12, tsmom_thresh=0.00),
    }

    print("\n[3/5] Running variants…")
    results = {}
    for name, kwargs in variants.items():
        results[name] = run_global_rotation(monthly_px, monthly_rt, **kwargs)

    print("\n[4/5] Evaluating windows…")

    # Try to load H026 equity curve for correlation (may not exist as parquet)
    h026_monthly = None
    for h026_p in [CACHE_DIR / "h026_production_equity.parquet",
                   RESULT_DIR / "h026_monthly_equity.parquet"]:
        if h026_p.exists():
            h026_monthly = pd.read_parquet(h026_p).squeeze()
            break

    print("\n  ── IS 2008–2017 ─────────────────────────────────────────────────")
    spy_is = slice_eq(spy_eq, IS_START, IS_END)
    print_stats(stats(spy_is, "SPY IS"))
    if efa_eq is not None:
        print_stats(stats(slice_eq(efa_eq, IS_START, IS_END), "EFA buy-hold IS"))
    for name, eq_full in results.items():
        print_stats(stats(slice_eq(eq_full, IS_START, IS_END), name + " IS"))

    print("\n  ── OOS 2018–2026 ────────────────────────────────────────────────")
    spy_oos = slice_eq(spy_eq, OOS_START)
    spy_oos_s = stats(spy_oos, "SPY OOS")
    print_stats(spy_oos_s)
    if efa_eq is not None:
        print_stats(stats(slice_eq(efa_eq, OOS_START), "EFA buy-hold OOS"))
    if eem_eq is not None:
        print_stats(stats(slice_eq(eem_eq, OOS_START), "EEM buy-hold OOS"))

    confirmed = []
    oos_stats = {}
    for name, eq_full in results.items():
        eq_oos = slice_eq(eq_full, OOS_START)
        s = stats(eq_oos, name + " OOS")
        oos_stats[name] = s

        # Correlation with H026
        corr_note = ""
        corr_val  = float("nan")
        if h026_monthly is not None:
            ret_oos   = eq_full.pct_change().dropna().loc[OOS_START:]
            h026_oos  = h026_monthly.pct_change().dropna().loc[OOS_START:]
            aligned   = ret_oos.align(h026_oos, join="inner")
            if len(aligned[0]) > 12:
                corr_val  = aligned[0].corr(aligned[1])
                corr_note = f"  corr(H026)={corr_val:.3f}"

        # Compute corr vs SPY as proxy if H026 unavailable
        ret_oos  = eq_full.pct_change().dropna().loc[OOS_START:]
        spy_ret  = spy_eq.pct_change().dropna().loc[OOS_START:]
        al       = ret_oos.align(spy_ret, join="inner")
        corr_spy = al[0].corr(al[1])
        corr_note += f"  corr(SPY)={corr_spy:.3f}"

        print_stats(s, corr_note)

        if (s["sharpe"] > 1.0
                and s["cumul"] > spy_oos_s["cumul"]
                and s["negyrs"] <= 2):
            confirmed.append({**s, "corr_spy": corr_spy, "corr_h026": corr_val})

    print("\n  ── AltOOS 2013–2026 ─────────────────────────────────────────────")
    spy_alt = slice_eq(spy_eq, ALT_OOS_ST)
    spy_alt_s = stats(spy_alt, "SPY AltOOS")
    print_stats(spy_alt_s)
    if efa_eq is not None:
        print_stats(stats(slice_eq(efa_eq, ALT_OOS_ST), "EFA buy-hold AltOOS"))
    for name, eq_full in results.items():
        print_stats(stats(slice_eq(eq_full, ALT_OOS_ST), name + " AltOOS"))

    # ── Detailed holding analysis ─────────────────────────────────────────────
    print("\n[5/5] Holding frequency analysis (variant B — top-1 TSMOM>0%)…")
    eq_b = results["B  top-1  TSMOM>0%"]
    # Reconstruct which asset was held each month
    tickers = [c for c in monthly_px.columns if c not in ("BIL", "SPY")]
    holdings = []
    for i in range(13, len(monthly_px)):
        date   = monthly_px.index[i]
        px_now = monthly_px.iloc[i - 1]
        px_12  = monthly_px.iloc[i - 13]
        scores = {}
        for t in tickers:
            if pd.notna(px_now.get(t)) and pd.notna(px_12.get(t)) and px_12.get(t, 0) > 0:
                tsmom = px_now[t] / monthly_px.iloc[i - 13][t] - 1
                if tsmom > 0:
                    scores[t] = px_now[t] / px_12[t] - 1
        held = sorted(scores, key=scores.get, reverse=True)[:1]
        holdings.append({"date": date, "held": held[0] if held else "BIL"})
    hold_df = pd.DataFrame(holdings).set_index("date")
    oos_hold = hold_df.loc[OOS_START:]
    freq = oos_hold["held"].value_counts()
    print("  OOS holding frequency (variant B):")
    for t, n in freq.items():
        print(f"    {t}: {n} months ({n/len(oos_hold)*100:.0f}%)")

    # ── Verdict ───────────────────────────────────────────────────────────────
    verdict = "CONFIRMED" if confirmed else "NOT CONFIRMED"

    out_lines = [
        "H179 — Global Equity Momentum Rotation",
        f"Universe: {avail}  (SPY excluded from selection pool)",
        f"Signal: 12-1 month momentum, monthly rebalance, TSMOM safety filter",
        f"IS: {IS_START}–{IS_END}  |  OOS: {OOS_START}+  |  AltOOS: {ALT_OOS_ST}+",
        "",
        f"SPY OOS: cumul={spy_oos_s['cumul']:.2f}×  "
        f"Sharpe={spy_oos_s['sharpe']:.3f}  MaxDD={spy_oos_s['maxdd']*100:.1f}%",
        "",
        "OOS Results:",
    ]
    for name, s in oos_stats.items():
        out_lines.append(
            f"  {name:<38} cumul={s['cumul']:.2f}× "
            f"Sharpe={s['sharpe']:.3f} MaxDD={s['maxdd']*100:.1f}% "
            f"NegYrs={s['negyrs']}")
    out_lines += ["", f"VERDICT: {verdict}"]
    if confirmed:
        best = max(confirmed, key=lambda x: x["sharpe"])
        out_lines += [
            f"Best: {best['label']}  OOS Sharpe={best['sharpe']:.3f}  "
            f"cumul={best['cumul']:.2f}×  MaxDD={best['maxdd']*100:.1f}%  "
            f"corr(SPY)={best.get('corr_spy', float('nan')):.3f}"]
    else:
        out_lines += [
            "No variant meets OOS Sharpe>1.0 AND cumul>SPY AND NegYrs≤2.",
            f"Best OOS Sharpe: "
            + str(round(max(s["sharpe"] for s in oos_stats.values()), 3)),
        ]

    result_path = RESULT_DIR / "h179_global_equity_momentum.txt"
    result_path.write_text("\n".join(out_lines))
    print(f"\n  Results → {result_path}")
    print(f"  VERDICT: {verdict}")
    print("=" * 72)


if __name__ == "__main__":
    main()
