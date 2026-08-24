"""
H532 — Relative-Volume Confirmation Tiebreaker on H026 Sector Rotation
========================================================================
H530 (CONFIRMED, robust) found that on the H241 200-stock universe, filtering
momentum winners to the HIGHEST relative-volume names ("glamour"/heavily-
traded, the opposite of Lee & Swaminathan's 2000 prediction) improved OOS
Sharpe from 1.061 to 1.373 — but OOS correlation with plain momentum was
0.91, too high to justify as a standalone strategy. H530's own recommended
follow-up: "Test Variant B's relative-volume tilt as a tiebreaker layered
directly onto the production H041a or H026 selection logic (analogous to
how H361's OB filter was layered onto H354)."

H041a's 7-asset multi-asset-class universe (SPY/QQQ/TLT/GLD/IEF/EFA/EEM) is
not a meaningful venue for a volume-confirmation tiebreaker — the assets are
different asset classes with structurally different volume profiles, not
comparable cross-sectional "momentum winners" the way same-sector-class
stocks are. H026's 11 same-asset-class (all US sector ETF) universe is the
correct venue: sector ETFs are comparable enough that "is this month's top
pick also the most heavily-traded" is a meaningful confirmation question,
mirroring H530's actual mechanism.

Universe: H026_SECTORS (11 GICS sector ETFs), same list as run_h249.py's
  production-consistent H026 sub-strategy definition.
Signal: base = rank(12m momentum) + rank(inverse 6m vol) composite (H026's
  own scoring, unchanged). Relative volume = trailing 3m avg dollar volume /
  trailing 12m avg dollar volume, computed at the same signal date (month
  t-1 close) as the momentum/vol composite — no additional lag risk.
Variants:
  A — baseline: pure top-1 composite momentum, no volume filter (H026's
      unmodified production logic).
  B — dual-rank composite: 0.5*rank(mom+invvol composite) + 0.5*rank(relvol),
      pick top-1 (H530 Var C style — blend, not hard filter).
  C — confirmation filter, fallback to 2nd choice: pick top-1 by momentum
      composite; if its relative volume is below the cross-sectional
      median that month, fall back to the composite's 2nd-ranked asset.
  D — confirmation filter, fallback to cash: same as C, but fall back to
      BIL instead of the 2nd choice (mirrors H361's OB-filter mechanism
      exactly — unconfirmed momentum picks park in cash).
  E — pure relative-volume tilt, no momentum: top-1 by relative volume
      alone (sanity-check control, expected to be weak).

IS: 2008-01-01 to 2017-12-31  OOS: 2018-01-01 to present (H026 canonical
  split, matching H345/H346/H510-H514).
Gate: OOS Sharpe > 1.300 (H026 canonical family gate, per H511-H514) AND
  must beat Variant A's own freshly-computed baseline (apples-to-apples,
  same code/data/costs).
"""

import warnings; warnings.filterwarnings("ignore")
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

FULL_START = "2005-01-01"
FULL_END   = "2026-05-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

H026_SECTORS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLY","XLP","XLC","XLRE"]
BIL          = "BIL"
GATE         = 1.300


def fetch_close_volume(tickers, tag=""):
    all_tickers = sorted(set(tickers))
    cache_path = CACHE_DIR / f"h532_{tag}_{FULL_START}_{FULL_END}.parquet"
    vcache_path = CACHE_DIR / f"h532_{tag}_vol_{FULL_START}_{FULL_END}.parquet"
    if cache_path.exists() and vcache_path.exists():
        closes = pd.read_parquet(cache_path)
        vols   = pd.read_parquet(vcache_path)
        if not any(t not in closes.columns for t in all_tickers):
            return closes, vols
    print(f"  Downloading {len(all_tickers)} tickers [{tag}]...")
    raw = yf.download(all_tickers, start=FULL_START, end=FULL_END,
                       auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    volume = raw["Volume"] if isinstance(raw.columns, pd.MultiIndex) else None
    closes = closes.dropna(how="all")
    closes.to_parquet(cache_path)
    if volume is not None:
        volume = volume.dropna(how="all")
        volume.to_parquet(vcache_path)
    return closes, volume


def calc_stats(returns_series, label=""):
    r = returns_series.dropna()
    if len(r) < 12:
        return {}
    eq = (1 + r).cumprod()
    n_years = len(r) / 12
    cagr    = eq.iloc[-1] ** (1/n_years) - 1
    vol     = r.std() * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    max_dd   = (eq / roll_max - 1).min()
    neg_yrs = (r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum()
    return {
        "label": label, "n_months": len(r),
        "cagr": round(float(cagr), 4), "sharpe": round(float(sharpe), 4),
        "max_dd": round(float(max_dd), 4), "ann_vol": round(float(vol), 4),
        "neg_yrs": int(neg_yrs),
    }


def worst_kfold_sharpe(returns_series, k=3):
    r = returns_series.dropna()
    if len(r) < k * 6:
        return None
    chunks = np.array_split(r, k)
    sharpes = []
    for c in chunks:
        if len(c) < 3:
            continue
        s = calc_stats(c)
        if s:
            sharpes.append(s["sharpe"])
    return round(min(sharpes), 4) if sharpes else None


def main():
    print("=" * 60)
    print("H532 — Relative-Volume Confirmation Tiebreaker on H026")
    print("=" * 60)

    tickers = H026_SECTORS + [BIL]
    closes, volume = fetch_close_volume(tickers, tag="h026")
    closes_m = closes.resample("ME").last()
    ret_m    = closes_m.pct_change()

    dollar_vol = (closes * volume).reindex(closes.index)
    dv_3m  = dollar_vol.rolling(63).mean()
    dv_12m = dollar_vol.rolling(252).mean()
    relvol_daily = dv_3m / dv_12m
    relvol_m = relvol_daily.resample("ME").last()

    mom12 = closes_m.pct_change(12)
    vol6  = ret_m.rolling(6).std()

    dates = closes_m.index
    variants = {v: [] for v in "ABCDE"}

    for i in range(13, len(dates)):
        sig_date, hold_date = dates[i-1], dates[i]

        cols = [c for c in H026_SECTORS if c in closes_m.columns]
        m12 = mom12.loc[sig_date, cols]
        v6  = vol6.loc[sig_date, cols]
        rv  = relvol_m.loc[sig_date, cols] if sig_date in relvol_m.index else pd.Series(np.nan, index=cols)

        valid = m12.notna() & v6.notna() & (v6 > 0)
        if valid.sum() < 3:
            for v in "ABCDE":
                variants[v].append((hold_date, 0.0))
            continue

        cols_v = [c for c in cols if valid[c]]
        # rank(ascending=False): best value (highest mom, highest 1/vol) gets rank 1.
        # Lowest rank-sum = best composite asset.
        rank_mom = m12[cols_v].rank(ascending=False)
        rank_vol = (1.0 / v6[cols_v]).rank(ascending=False)
        composite = rank_mom + rank_vol

        rv_valid = rv[cols_v].notna()
        rank_relvol = rv[cols_v][rv_valid].rank(ascending=False) if rv_valid.sum() >= 3 else None

        ranked = composite.sort_values(ascending=True)
        top1_asset = ranked.index[0]
        top2_asset = ranked.index[1] if len(ranked) > 1 else top1_asset
        median_relvol = rv[cols_v].median() if rv_valid.sum() >= 3 else np.nan

        def hold_ret(asset):
            r = ret_m.loc[hold_date, asset] if asset in ret_m.columns else 0.0
            return r if not np.isnan(r) else 0.0

        # A: baseline top-1 composite momentum
        variants["A"].append((hold_date, hold_ret(top1_asset)))

        # B: dual-rank composite (0.5 mom+invvol composite rank + 0.5 relvol rank)
        if rank_relvol is not None:
            # composite is a rank-sum where LOWER = better; re-rank ascending so rank 1 = best.
            norm_composite = composite[cols_v].rank(ascending=True)
            dual = 0.5 * norm_composite.reindex(rank_relvol.index) + \
                   0.5 * rank_relvol
            # lower combined rank = better; pick min
            b_asset = dual.idxmin()
            variants["B"].append((hold_date, hold_ret(b_asset)))
        else:
            variants["B"].append((hold_date, hold_ret(top1_asset)))

        # C: confirmation filter, fallback to 2nd choice
        top1_rv = rv.get(top1_asset, np.nan)
        if not np.isnan(median_relvol) and not np.isnan(top1_rv) and top1_rv < median_relvol:
            variants["C"].append((hold_date, hold_ret(top2_asset)))
        else:
            variants["C"].append((hold_date, hold_ret(top1_asset)))

        # D: confirmation filter, fallback to cash (BIL)
        if not np.isnan(median_relvol) and not np.isnan(top1_rv) and top1_rv < median_relvol:
            variants["D"].append((hold_date, hold_ret(BIL)))
        else:
            variants["D"].append((hold_date, hold_ret(top1_asset)))

        # E: pure relative-volume tilt, no momentum
        if rv_valid.sum() >= 3:
            e_asset = rv[cols_v][rv_valid].idxmax()
            variants["E"].append((hold_date, hold_ret(e_asset)))
        else:
            variants["E"].append((hold_date, hold_ret(top1_asset)))

    series = {}
    for v, recs in variants.items():
        d, r = zip(*recs)
        series[v] = pd.Series(r, index=pd.DatetimeIndex(d))

    is_mask  = series["A"].index <= pd.Timestamp(IS_END)
    oos_mask = series["A"].index >= pd.Timestamp(OOS_START)

    results = {}
    print(f"\n{'Variant':<10}{'IS Sharpe':>12}{'OOS Sharpe':>12}{'OOS CAGR':>12}{'OOS MaxDD':>12}{'NegYrs':>8}{'Worst3Fold':>12}")
    labels = {
        "A": "baseline top-1 composite (no filter)",
        "B": "dual-rank composite (mom+invvol, relvol)",
        "C": "confirm filter, fallback to 2nd choice",
        "D": "confirm filter, fallback to cash",
        "E": "pure relative-volume, no momentum",
    }
    for v in "ABCDE":
        s = series[v]
        is_s  = calc_stats(s[is_mask])
        oos_s = calc_stats(s[oos_mask])
        wf    = worst_kfold_sharpe(s[oos_mask])
        results[v] = {"label": labels[v], "is": is_s, "oos": oos_s, "worst_3fold_oos_sharpe": wf}
        print(f"{v:<10}{is_s.get('sharpe','N/A'):>12}{oos_s.get('sharpe','N/A'):>12}"
              f"{oos_s.get('cagr','N/A'):>12}{oos_s.get('max_dd','N/A'):>12}"
              f"{oos_s.get('neg_yrs','N/A'):>8}{str(wf):>12}")

    baseline_oos_sharpe = results["A"]["oos"]["sharpe"]
    print(f"\nBaseline (A) OOS Sharpe: {baseline_oos_sharpe}")
    print(f"Gate: OOS Sharpe > {GATE} AND beats Variant A baseline")

    confirmed_variants = []
    for v in "BCDE":
        oos_sh = results[v]["oos"]["sharpe"]
        if oos_sh > GATE and oos_sh > baseline_oos_sharpe:
            confirmed_variants.append(v)
    print(f"Confirmed variants (clear gate AND beat baseline A): {confirmed_variants}")

    # Correlation of each variant vs baseline A (production overlap estimate)
    corrs = {v: round(float(series[v][oos_mask].corr(series["A"][oos_mask])), 4) for v in "BCDE"}
    print(f"OOS correlation vs baseline A: {corrs}")

    out = {
        "hypothesis": "H532",
        "description": "Relative-volume confirmation tiebreaker layered on H026 sector rotation (H530 follow-up)",
        "gate": f"OOS Sharpe > {GATE} AND beats Variant A baseline",
        "confirmed_variants": confirmed_variants,
        "results": results,
        "corr_vs_baseline_oos": corrs,
    }
    out_path = RESULT_DIR / "h532_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved -> {out_path}")
    return out


if __name__ == "__main__":
    main()
