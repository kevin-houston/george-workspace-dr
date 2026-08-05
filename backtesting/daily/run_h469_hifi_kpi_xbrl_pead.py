#!/usr/bin/env python3
"""
H469 — HiFi-KPI Structured iXBRL KPI Extraction as H174 Signal Layer

Source: arXiv:2502.15411 (Feb 2026) "HiFi-KPI: A Dataset for Hierarchical
        KPI Extraction from Earnings Filings"

Hypothesis: H174 uses raw EPS surprise as a binary gate (>= 0.02). The
HiFi-KPI paper shows KPIs are structured and linkable to iXBRL taxonomies —
implying machine-readable EPS/revenue figures are already available without
LLM extraction. H469 upgrades H174's binary EPS gate to a continuous
magnitude multiplier: bigger EPS beat relative to consensus -> larger
expected PEAD drift -> scale position by min(2.0, max(0.5, 1.0 + beat_pct)).

Data note: EDGAR XBRL companyfacts lacks consensus estimates. Consensus +
actual EPS/revenue instead sourced from FMP `/stable/earnings` (confirmed
working endpoint; the older `/api/v3/earnings-surprises` is deprecated).
Each H174-qualifying event's FMP report date is matched within +/-5 days.

Variants (applied on top of the H174 dual filter: score>=0.18, surprise>=0.02):
  A: EPS magnitude scaling  — size = clip(1.0 + eps_beat_pct, 0.5, 2.0)
  B: Binary EPS gate        — require eps_beat_pct > 5%
  C: Revenue beat gate      — require rev_beat_pct > 0%
  D: Composite magnitude    — size = clip(1.0 + avg(eps_beat, rev_beat), 0.5, 2.0)
  E: H174 baseline (unchanged, no KPI layer) — sanity check, should reproduce H174

IS: 2020-2023 / OOS: 2024-2026 (inherits run_h174.py's own split)
Gate: OOS WR >= 0.818 AND OOS MeanRet >= 6.89% at n >= 15 (H174 baseline)
"""

import warnings
warnings.filterwarnings("ignore")

import os
import json
import time
import importlib.util
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

os.environ["NO_PROXY"] = os.environ.get("NO_PROXY", "") + ",financialmodelingprep.com"
os.environ["no_proxy"] = os.environ.get("no_proxy", "") + ",financialmodelingprep.com"

FMP_BASE = "https://financialmodelingprep.com/stable/earnings"
GATE_WR, GATE_MR, GATE_N = 0.818, 0.0689, 15

_spec = importlib.util.spec_from_file_location(
    "h174mod", Path(__file__).parent / "run_h174.py")
h174mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h174mod)


def fetch_fmp_earnings(ticker):
    cp = CACHE_DIR / f"h469_{ticker}_fmp_earnings.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return pd.DataFrame()
    try:
        r = requests.get(FMP_BASE, params={"symbol": ticker, "apikey": key}, timeout=30)
        if r.status_code != 200:
            print(f"    FMP {ticker}: HTTP {r.status_code}")
            return pd.DataFrame()
        df = pd.DataFrame(r.json())
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        df.to_parquet(cp)
        time.sleep(0.25)
        return df
    except Exception as e:
        print(f"    FMP {ticker}: error {e}")
        return pd.DataFrame()


def nearest_earnings_row(fmp_df, event_date, window_days=5):
    if fmp_df is None or fmp_df.empty:
        return None
    cand = fmp_df[(fmp_df["date"] - event_date).abs() <= pd.Timedelta(days=window_days)]
    if cand.empty:
        return None
    cand = cand.copy()
    cand["dist"] = (cand["date"] - event_date).abs()
    return cand.sort_values("dist").iloc[0]


def eps_beat_pct(row):
    if row is None:
        return float("nan")
    eps_a, eps_e = row.get("epsActual"), row.get("epsEstimated")
    if pd.isna(eps_a) or pd.isna(eps_e) or abs(eps_e) < 1e-6:
        return float("nan")
    return (eps_a - eps_e) / abs(eps_e)


def rev_beat_pct(row):
    if row is None:
        return float("nan")
    rev_a, rev_e = row.get("revenueActual"), row.get("revenueEstimated")
    if pd.isna(rev_a) or pd.isna(rev_e) or abs(rev_e) < 1e-6:
        return float("nan")
    return (rev_a - rev_e) / abs(rev_e)


def build_dual_filter_events():
    ohlcv = h174mod.load_ohlcv()
    all_events = h174mod.find_gap_events(ohlcv)
    earnings_by_ticker = {t: h174mod.get_earnings_dates(t) for t in h174mod.UNIVERSE}

    def is_earnings_gap(ticker, gap_date, window=3):
        return any(abs((gap_date - ed).days) <= window
                   for ed in earnings_by_ticker.get(ticker, []))

    conf_events = all_events[
        all_events.apply(lambda r: is_earnings_gap(r["ticker"], r["date"]), axis=1)
    ].copy()

    is_ev  = conf_events[conf_events["date"] <= h174mod.IS_END]
    oos_ev = conf_events[conf_events["date"] >= h174mod.OOS_START]

    score_df = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
    score_df["date"] = pd.to_datetime(score_df["date"])

    def enrich(events):
        rows = []
        for _, ev in events.iterrows():
            ret = h174mod.compute_return(ev["ticker"], ev["date"], ohlcv, hold=20)
            if ret is None:
                continue
            score_row = score_df[(score_df["ticker"] == ev["ticker"]) &
                                  (score_df["date"] == ev["date"])]
            score = score_row.iloc[0]["finbert_score"] if not score_row.empty else float("nan")
            surprise = h174mod.compute_surprise(ev["ticker"], ev["date"], score_df)
            rows.append({"ticker": ev["ticker"], "date": ev["date"],
                         "ret": ret, "score": score, "surprise": surprise})
        return pd.DataFrame(rows)

    is_df, oos_df = enrich(is_ev), enrich(oos_ev)
    is_dual = is_df[(is_df["score"] >= 0.18) & (is_df["surprise"] >= 0.02)] \
        .dropna(subset=["score", "surprise"]).copy()
    oos_dual = oos_df[(oos_df["score"] >= 0.18) & (oos_df["surprise"] >= 0.02)] \
        .dropna(subset=["score", "surprise"]).copy()
    return is_dual, oos_dual


def add_kpi(df, fmp_cache):
    eps_list, rev_list = [], []
    for _, r in df.iterrows():
        row = nearest_earnings_row(fmp_cache.get(r["ticker"]), r["date"])
        eps_list.append(eps_beat_pct(row))
        rev_list.append(rev_beat_pct(row))
    df = df.copy()
    df["eps_beat"], df["rev_beat"] = eps_list, rev_list
    return df


def eval_variant(df, label, weight_fn=None, filter_fn=None):
    d = df.copy()
    if filter_fn is not None:
        d = d[d.apply(filter_fn, axis=1)]
    if len(d) == 0:
        return {"label": label, "n": 0, "wr": float("nan"), "mr": float("nan")}
    wr = (d["ret"] > 0).mean()
    if weight_fn is not None:
        d["w"] = d.apply(weight_fn, axis=1)
        mr = (d["ret"] * d["w"]).sum() / d["w"].sum()
    else:
        mr = d["ret"].mean()
    return {"label": label, "n": len(d), "wr": wr, "mr": mr}


def clip_size(x, lo=0.5, hi=2.0):
    return min(hi, max(lo, x))


def var_a_weight(r):
    return 1.0 if pd.isna(r["eps_beat"]) else clip_size(1.0 + r["eps_beat"])


def var_d_weight(r):
    vals = [v for v in [r["eps_beat"], r["rev_beat"]] if not pd.isna(v)]
    return 1.0 if not vals else clip_size(1.0 + sum(vals) / len(vals))


def var_b_filter(r):
    return (not pd.isna(r["eps_beat"])) and r["eps_beat"] > 0.05


def var_c_filter(r):
    return (not pd.isna(r["rev_beat"])) and r["rev_beat"] > 0.0


def main():
    print("=" * 70)
    print("  H469 — HiFi-KPI: EPS/Revenue Magnitude Layer on H174 Event Set")
    print("=" * 70)

    print("\n[1/4] Reconstructing H174 dual-filter event set (score>=0.18, surprise>=0.02)...")
    is_dual, oos_dual = build_dual_filter_events()
    print(f"  IS n={len(is_dual)}   OOS n={len(oos_dual)}")
    print(f"  OOS baseline: WR={(oos_dual['ret']>0).mean()*100:.1f}%  "
          f"MeanRet={oos_dual['ret'].mean()*100:.2f}%")

    print("\n[2/4] Fetching FMP EPS/revenue actual vs. estimate per ticker...")
    tickers = sorted(set(is_dual["ticker"]).union(oos_dual["ticker"]))
    fmp_cache = {t: fetch_fmp_earnings(t) for t in tickers}
    ok = sum(1 for t in tickers if not fmp_cache[t].empty)
    print(f"  FMP data retrieved for {ok}/{len(tickers)} tickers")

    is_dual = add_kpi(is_dual, fmp_cache)
    oos_dual = add_kpi(oos_dual, fmp_cache)
    eps_cov = oos_dual["eps_beat"].notna().mean() if len(oos_dual) else 0.0
    print(f"  OOS EPS-beat match coverage: {eps_cov*100:.1f}% "
          f"({oos_dual['eps_beat'].notna().sum()}/{len(oos_dual)})")

    print("\n[3/4] Backtesting Variants A-E...")
    results = {}
    for period, df in [("IS", is_dual), ("OOS", oos_dual)]:
        results[f"{period}_A"] = eval_variant(df, "A: EPS magnitude size", weight_fn=var_a_weight)
        results[f"{period}_B"] = eval_variant(df, "B: EPS beat>5% gate", filter_fn=var_b_filter)
        results[f"{period}_C"] = eval_variant(df, "C: Rev beat>0% gate", filter_fn=var_c_filter)
        results[f"{period}_D"] = eval_variant(df, "D: composite EPS+rev size", weight_fn=var_d_weight)
        results[f"{period}_E"] = eval_variant(df, "E: H174 baseline")

    print(f"\n  {'Variant':<28} {'Per':<4} {'n':>4} {'WR%':>7} {'MeanRet%':>10} {'Gate':>6}")
    print("  " + "-" * 65)
    for period in ["IS", "OOS"]:
        for v in ["A", "B", "C", "D", "E"]:
            r = results[f"{period}_{v}"]
            wr = r["wr"] if not pd.isna(r["wr"]) else float("nan")
            mr = r["mr"] if not pd.isna(r["mr"]) else float("nan")
            gate = ""
            if period == "OOS" and r["n"] >= GATE_N and not pd.isna(wr):
                gate = "PASS" if (wr >= GATE_WR and mr >= GATE_MR) else "fail"
            print(f"  {r['label']:<28} {period:<4} {r['n']:>4} "
                  f"{wr*100:>7.1f} {mr*100:>10.2f} {gate:>6}")

    print("\n[4/4] Verdict...")
    oos_pass = [v for v in ["A", "B", "C", "D"]
                if results[f"OOS_{v}"]["n"] >= GATE_N
                and not pd.isna(results[f"OOS_{v}"]["wr"])
                and results[f"OOS_{v}"]["wr"] >= GATE_WR
                and results[f"OOS_{v}"]["mr"] >= GATE_MR]
    verdict = "CONFIRMED" if oos_pass else "NOT CONFIRMED"
    print(f"  VERDICT: {verdict}  (passing variants: {oos_pass})")

    def clean(v):
        return None if isinstance(v, float) and pd.isna(v) else v

    out = {
        "hypothesis": "H469",
        "run_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "eps_coverage_oos": eps_cov,
        "results": {k: {kk: clean(vv) for kk, vv in v.items()} for k, v in results.items()},
        "verdict": verdict,
        "passing_variants": oos_pass,
    }
    (RESULT_DIR / "h469_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Results saved to h469_results.json")


if __name__ == "__main__":
    main()
