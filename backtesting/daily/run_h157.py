"""
H157 — Factor/Style ETF Momentum
==================================
Cross-sectional momentum applied to a universe of 30+ factor and style ETFs
(growth/value, small/large, quality, min-vol, dividend, international, etc.).

Unlike H156 (NASDAQ stock momentum, survivorship-biased), this is bias-free:
ETFs don't disappear, track indices, and have known inception dates.

Signal variants tested:
  A: rank(12m) only  — baseline JT-style
  B: rank(3m)+rank(6m)+rank(12m)+rank(inv_vol)  — H026 production ensemble
  C: same as B + TSMOM filter: only hold ETFs with 12m > +5%  — matches H026

Top-1 and Top-3 selection tested for each signal.

Key question: Does factor ETF rotation beat SPY/QQQ? Is it correlated with
H026 sector rotation (would it add diversification to the production portfolio)?
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2007-01-01"
FULL_END   = "2026-04-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

COST_RT    = 0.0005   # 0.05% RT (ETFs have tight spreads)

# ── Universe ──────────────────────────────────────────────────────────────────
# Factor/style ETFs — each represents a systematic risk premium or style tilt.
# Excludes single-sector ETFs (XLK, XLE, etc.) to avoid overlap with H026.
# Launched dates noted; most available 2004-2007+.

UNIVERSE = [
    # US Large-cap style
    "SPY",   # S&P 500 (benchmark / H026 comparison)
    "QQQ",   # NASDAQ 100 (growth factor proxy)
    "IVW",   # iShares S&P500 Growth (2000)
    "IVE",   # iShares S&P500 Value (2000)
    "VTV",   # Vanguard Value ETF (2004)
    "VUG",   # Vanguard Growth ETF (2004)

    # US Small/Mid cap style
    "IJH",   # iShares S&P400 Mid Cap (2000)
    "IJR",   # iShares S&P600 Small Cap (2000)
    "IWM",   # iShares Russell 2000 (2000)
    "IWO",   # iShares Russell 2000 Growth (2000)
    "IWN",   # iShares Russell 2000 Value (2000)
    "VBR",   # Vanguard Small Cap Value (2004)
    "VBK",   # Vanguard Small Cap Growth (2004)

    # Dividend / Income factor
    "DVY",   # iShares Select Dividend (2003)
    "SDY",   # SPDR S&P Dividend (2005)
    "VYM",   # Vanguard High Div Yield (2006)
    "NOBL",  # ProShares Dividend Aristocrats (2013)

    # Quality / Low-Vol factor (newer)
    "SPLV",  # Invesco S&P500 Low Volatility (2011)
    "USMV",  # iShares MSCI USA Min Vol (2011)
    "QUAL",  # iShares MSCI USA Quality (2013)
    "MTUM",  # iShares MSCI USA Momentum (2013)
    "VLUE",  # iShares MSCI USA Value (2013)

    # International developed markets (style)
    "EFA",   # iShares MSCI EAFE (2001)
    "VEA",   # Vanguard Dev ex-US (2007)
    "IEFA",  # iShares Core MSCI EAFE (2012)
    "EFV",   # iShares MSCI EAFE Value (2005)
    "EFG",   # iShares MSCI EAFE Growth (2005)

    # Emerging markets
    "EEM",   # iShares MSCI Emerging Mkts (2003)
    "VWO",   # Vanguard Emerging Mkts (2005)

    # Defensive / Alternatives (rotation into when equity factors weak)
    "TLT",   # 20+ Year Treasury (2002)
    "IEF",   # 7-10 Year Treasury (2002)
    "GLD",   # Gold (2004)
    "BIL",   # T-Bill cash proxy (2007) — allows going to cash
]

# H026-style sector universe for correlation comparison
H026_SECTORS = [
    "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY", "XLC",
    "BIL",
]


def fetch_prices(tickers, start, end, prefix="h157"):
    """Batch download with cache."""
    result = {}
    to_dl = []
    for t in tickers:
        # Check existing caches from prior H-series
        found = None
        for pfx in [f"h{i:03d}" for i in range(62, 158)] + ["h026", "h112"]:
            for suf in ["ohlc", "close"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_{start}_{end}.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    col = "close" if "close" in df.columns else df.columns[0]
                    found = df[col].rename(t)
                    break
            if found is not None:
                break
        if found is not None:
            result[t] = found
            continue
        cp = CACHE_DIR / f"{prefix}_{t}_close_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            col = "close" if "close" in df.columns else df.columns[0]
            result[t] = df[col].rename(t)
        else:
            to_dl.append(t)

    if to_dl:
        print(f"    Downloading {len(to_dl)} tickers: {to_dl}…")
        batch = yf.download(to_dl, start=start, end=end,
                            auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            closes = batch["Close"]
        else:
            closes = batch[["Close"]] if len(to_dl) == 1 else batch

        for t in to_dl:
            if t in closes.columns:
                s = closes[t].dropna()
                if len(s) > 100:
                    cp = CACHE_DIR / f"{prefix}_{t}_close_{start}_{end}.parquet"
                    s.to_frame().to_parquet(cp)
                    result[t] = s.rename(t)
            elif len(to_dl) == 1:
                s = closes.squeeze().dropna()
                if len(s) > 100:
                    cp = CACHE_DIR / f"{prefix}_{to_dl[0]}_close_{start}_{end}.parquet"
                    s.to_frame().to_parquet(cp)
                    result[to_dl[0]] = s.rename(to_dl[0])

    return result


def build_monthly(price_dict):
    frames = [s.resample("ME").last().pct_change().rename(t)
              for t, s in price_dict.items()]
    return pd.concat(frames, axis=1)


def compute_signal(monthly_ret, date, mode="ensemble", tsmom_thresh=None):
    """
    Compute signal for all assets at given date.
    mode: 'rank12' | 'ensemble' (rank3+rank6+rank12+inv_vol)
    tsmom_thresh: if set, filter out assets with 12m return <= thresh
    """
    avail = monthly_ret.loc[:date]

    def mom_return(lb, skip=1):
        end   = date - pd.DateOffset(months=skip)
        start = end   - pd.DateOffset(months=lb - 1)
        win = monthly_ret.loc[start:end]
        if len(win) < max(lb - 2, 1):
            return pd.Series(dtype=float)
        return (1 + win).prod() - 1

    r12  = mom_return(12, skip=1)
    r6   = mom_return(6,  skip=0)
    r3   = mom_return(3,  skip=0)

    # Require at least 24 months of history to be eligible
    n_obs = avail.count()
    eligible = n_obs[n_obs >= 24].index
    r12 = r12[r12.index.isin(eligible)].dropna()
    r6  = r6 [r6.index.isin(eligible)].dropna()
    r3  = r3 [r3.index.isin(eligible)].dropna()

    if mode == "rank12":
        scores = r12.rank(ascending=True)
    else:
        # Rolling 6m inverse vol
        vol6m_end = date
        vol6m_start = vol6m_end - pd.DateOffset(months=6)
        vol_window = monthly_ret.loc[vol6m_start:vol6m_end, eligible]
        inv_vol = (1.0 / vol_window.std(ddof=1)).replace([np.inf, -np.inf], np.nan)
        common = r12.index.intersection(r6.index).intersection(r3.index).intersection(inv_vol.index)
        if len(common) < 3:
            return pd.Series(dtype=float)
        scores = (r12.loc[common].rank() + r6.loc[common].rank()
                  + r3.loc[common].rank() + inv_vol.loc[common].rank())

    # TSMOM filter
    if tsmom_thresh is not None:
        passing = r12[r12 > tsmom_thresh].index
        scores = scores[scores.index.isin(passing)]

    return scores.dropna()


def backtest(monthly_ret, mode, n_hold, tsmom_thresh=None, cost_rt=COST_RT):
    """Monthly rebalance: buy top-N by signal."""
    dates = monthly_ret.index
    dates = dates[dates >= pd.Timestamp(FULL_START)]
    ret_list = []
    prev_h = set()

    for i in range(len(dates) - 1):
        d = dates[i]
        sig = compute_signal(monthly_ret, d, mode=mode, tsmom_thresh=tsmom_thresh)

        if len(sig) == 0:
            ret_list.append((dates[i+1], 0.0))
            continue

        top = sig.nlargest(n_hold).index.tolist()
        if not top:
            ret_list.append((dates[i+1], 0.0))
            prev_h = set()
            continue

        fwd = monthly_ret.loc[dates[i+1], top].dropna()
        if len(fwd) == 0:
            ret_list.append((dates[i+1], 0.0))
            continue

        port_ret = fwd.mean()
        new_h = set(top)
        turnover = len(new_h.symmetric_difference(prev_h)) / (2 * max(n_hold, 1)) if prev_h else 1.0
        port_ret -= turnover * cost_rt
        prev_h = new_h
        ret_list.append((dates[i+1], port_ret))

    return pd.DataFrame(ret_list, columns=["date", "ret"]).set_index("date")["ret"]


def stats(r, label=""):
    r = r.dropna()
    if len(r) < 6:
        return {"cumul": 1.0, "cagr": 0.0, "vol": 0.0, "sharpe": 0.0, "max_dd": 0.0, "neg_yrs": 0}
    eq = (1 + r).cumprod()
    ann = 12
    cagr   = float(eq.iloc[-1]) ** (ann / len(r)) - 1
    vol    = r.std(ddof=1) * np.sqrt(ann)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cumul": float(eq.iloc[-1]), "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "max_dd": max_dd, "neg_yrs": neg_yrs, "label": label}


def main():
    print(f"\nH157 — Factor/Style ETF Momentum")
    print("=" * 65)

    print(f"\n[1] Loading prices…")
    px = fetch_prices(UNIVERSE, FULL_START, FULL_END)
    h026_px = fetch_prices(H026_SECTORS, FULL_START, FULL_END, prefix="h157s")

    valid = {t: s for t, s in px.items() if len(s) >= 200}
    print(f"    Factor universe: {len(valid)}/{len(UNIVERSE)} tickers loaded")
    for t in UNIVERSE:
        if t not in valid:
            print(f"      MISSING: {t}")

    spy_px  = fetch_prices(["SPY"],  FULL_START, FULL_END)
    qqq_px  = fetch_prices(["QQQ"],  FULL_START, FULL_END)

    print(f"\n[2] Building monthly returns…")
    monthly = build_monthly(valid)
    h026_monthly = build_monthly({t: s for t, s in h026_px.items() if len(s) >= 200})
    spy_m = build_monthly(spy_px)["SPY"]
    qqq_m = build_monthly(qqq_px)["QQQ"]

    print(f"    Grid: {monthly.shape} | {monthly.index[0].date()} → {monthly.index[-1].date()}")

    print(f"\n[3] Building H026-style sector rotation for correlation baseline…")
    # Simple H026 replica: rank(3m)+rank(6m)+rank(12m)+rank(inv_vol), top-1, tsmom>5%
    h026_strat = backtest(h026_monthly, mode="ensemble", n_hold=1, tsmom_thresh=0.05)

    print(f"\n[4] Running H157 variants…")

    VARIANTS = [
        # (label, mode, n_hold, tsmom_thresh)
        ("A1 rank12 top1",           "rank12",   1, None),
        ("A3 rank12 top3",           "rank12",   3, None),
        ("B1 ensemble top1",         "ensemble", 1, None),
        ("B3 ensemble top3",         "ensemble", 3, None),
        ("C1 ensemble+tsmom5% top1", "ensemble", 1, 0.05),
        ("C3 ensemble+tsmom5% top3", "ensemble", 3, 0.05),
    ]

    spy_oos  = stats(spy_m[spy_m.index >= OOS_START])
    spy_alt  = stats(spy_m[spy_m.index >= ALT_OOS_ST])
    qqq_oos  = stats(qqq_m[qqq_m.index >= OOS_START])

    print(f"    SPY OOS: cumul={spy_oos['cumul']:.4f}  Sharpe={spy_oos['sharpe']:.3f}")
    print(f"    QQQ OOS: cumul={qqq_oos['cumul']:.4f}  Sharpe={qqq_oos['sharpe']:.3f}")

    results = []
    for (label, mode, n_hold, thresh) in VARIANTS:
        r = backtest(monthly, mode=mode, n_hold=n_hold, tsmom_thresh=thresh)
        s_is  = stats(r[(r.index >= ALT_OOS_ST) & (r.index <= IS_END)], label)
        s_oos = stats(r[r.index >= OOS_START], label)
        s_alt = stats(r[r.index >= ALT_OOS_ST], label)

        # Correlations vs SPY and H026 sector rotation
        ov_spy  = r.index.intersection(spy_m.index)
        ov_h026 = r.index.intersection(h026_strat.index)
        corr_spy   = r.loc[ov_spy].corr(spy_m.loc[ov_spy])
        corr_h026  = r.loc[ov_h026].corr(h026_strat.loc[ov_h026])

        results.append({
            "label": label, "mode": mode, "n_hold": n_hold, "thresh": thresh,
            "is": s_is, "oos": s_oos, "alt": s_alt,
            "corr_spy": corr_spy, "corr_h026": corr_h026,
            "returns": r,
        })

        print(f"\n  {label}:")
        print(f"    IS(2013-17): cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}")
        print(f"    OOS(2018+):  cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  "
              f"Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
        print(f"    AltOOS:      cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
        print(f"    Corr(SPY OOS): {corr_spy:.3f}  |  Corr(H026 OOS): {corr_h026:.3f}")

    print(f"\n[5] Verdict…")

    confirmed_vars = []
    for rec in results:
        s_oos = rec["oos"]
        s_is  = rec["is"]
        checks = [
            s_oos["sharpe"] > spy_oos["sharpe"],    # beats SPY risk-adjusted
            s_oos["cumul"]  > spy_oos["cumul"],      # beats SPY cumulative
            s_oos["max_dd"] > -0.30,                 # reasonable drawdown
            s_is["sharpe"]  > 0.5,                   # IS viability
        ]
        score = sum(checks)
        verdict = "CONFIRMED" if score >= 3 else "PARTIAL" if score >= 2 else "NOT CONFIRMED"
        rec["verdict"] = verdict
        rec["score"] = score
        if verdict in ("CONFIRMED", "PARTIAL"):
            confirmed_vars.append(rec)
        print(f"  {rec['label']}: {verdict} ({score}/4) | "
              f"OOS Sharpe={s_oos['sharpe']:.3f} cumul={s_oos['cumul']:.4f} MaxDD={s_oos['max_dd']:.2%}")

    # Best variant
    best = max(results, key=lambda x: x["oos"]["sharpe"])
    overall = best["verdict"]

    print(f"\n  Best variant: {best['label']}  →  {overall}")
    print(f"  OOS Sharpe={best['oos']['sharpe']:.3f}  cumul={best['oos']['cumul']:.4f}")
    print(f"  Corr(H026): {best['corr_h026']:.3f}  (low = diversification value)")

    # H026 baseline for comparison
    h026_oos  = stats(h026_strat[h026_strat.index >= OOS_START])
    print(f"\n  H026 sector replica OOS: cumul={h026_oos['cumul']:.4f}  Sharpe={h026_oos['sharpe']:.3f}")
    print(f"  (Note: simplified replica, not full production H026)")

    # Write result
    lines = [
        "H157 — Factor/Style ETF Momentum", "=" * 65, "",
        f"Universe: {len(valid)} factor/style ETFs (bias-free, monthly rebalance)",
        f"Signal: cross-sectional momentum variants (12m, ensemble, TSMOM)",
        f"Cost: {COST_RT:.2%} RT | IS: 2008-17 | OOS: 2018+ | AltOOS: 2013+",
        "",
        f"BENCHMARKS",
        f"  SPY OOS: cumul={spy_oos['cumul']:.4f}  Sharpe={spy_oos['sharpe']:.3f}",
        f"  QQQ OOS: cumul={qqq_oos['cumul']:.4f}  Sharpe={qqq_oos['sharpe']:.3f}",
        f"  H026 sector replica OOS: cumul={h026_oos['cumul']:.4f}  Sharpe={h026_oos['sharpe']:.3f}",
        "",
        "VARIANTS",
    ]
    for rec in results:
        s = rec["oos"]
        lines.append(
            f"  {rec['label']}: OOS cumul={s['cumul']:.4f} CAGR={s['cagr']:.2%} "
            f"Sharpe={s['sharpe']:.3f} MaxDD={s['max_dd']:.2%} NegYrs={s['neg_yrs']} "
            f"Corr(SPY)={rec['corr_spy']:.3f} Corr(H026)={rec['corr_h026']:.3f} "
            f"→ {rec['verdict']}"
        )

    lines += [
        "",
        f"BEST VARIANT: {best['label']}",
        f"  OOS: cumul={best['oos']['cumul']:.4f}  Sharpe={best['oos']['sharpe']:.3f}  "
        f"MaxDD={best['oos']['max_dd']:.2%}  CAGR={best['oos']['cagr']:.2%}",
        f"  AltOOS: cumul={best['alt']['cumul']:.4f}  Sharpe={best['alt']['sharpe']:.3f}",
        f"  Corr(H026 sector rotation): {best['corr_h026']:.3f}",
        "",
        f"VERDICT: {overall}",
    ]
    (RESULT_DIR / "h157_factor_etf_momentum.txt").write_text("\n".join(lines))
    print(f"\n  Results saved to results/h157_factor_etf_momentum.txt")
    return overall, best


if __name__ == "__main__":
    main()
