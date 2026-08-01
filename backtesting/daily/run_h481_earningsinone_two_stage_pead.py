#!/usr/bin/env python3
"""
H481 — Two-Stage PEAD: Numeric Surprise at Open + Qualitative ECT Next Morning
=================================================================================
Source: arXiv:2606.29734 (Ding Yu et al., Jun 2026) — "Fast Numbers, Slow Language:
Bridging Quantitative and Qualitative Earnings Signals"

DATA SUBSTITUTION NOTE: The paper's own "EARNINGSINONE" corpus
(cited as github.com/dingyuqing05/earningsinone) does NOT exist as a public
repository — verified 2026-07-31 (GitHub returns 404 for the repo while the
user account itself exists, and web search finds only the arXiv abstract,
no dataset release). The corpus was meant to supply precise ECT (earnings
call transcript) timestamps for the "next morning" qualitative layer.

Substitute data sources used instead (all already confirmed working):
  - Layer 1 (numeric): FMP `/stable/earnings` endpoint — epsActual/epsEstimated
    per announcement date, available back to 1985 for large-caps. Surprise =
    (epsActual - epsEstimated) / abs(epsEstimated).
  - Layer 2 (qualitative): existing H163/H174 FinBERT 8-K sentiment score cache
    (backtesting/cache/h163_finbert_scores.parquet) + the H174 dual-filter
    pipeline (score >= 0.18, hold 20d from the earnings gap event).

This reproduces the paper's core testable claim (numeric signal is fast/decays
by next open, qualitative signal persists) using data that is actually
accessible, rather than blocking on the missing corpus.

Universe: same 30-stock set as H174/H163.
IS/OOS: IS 2022-2023 / OOS 2024-2026 (per hypothesis spec).
Gate: OOS WR > 81.8% (H174 baseline) AND MeanRet > 6.89% — must beat BOTH.

Variants:
  A: L1 only  — numeric EPS surprise >= 0.02, OPG entry at announcement, hold 1d
  B: L2 only  — FinBERT score >= 0.18, next-morning entry, hold 20d (= H174)
  C: L1+L2 sequential — enter at open on L1 (1d), extend to 20d if L2 confirms next morning
  D: L1 AND L2 gate — only take the 20d position if BOTH L1 >= 0.02 AND L2 >= 0.18
"""

import warnings
warnings.filterwarnings("ignore")

import os
import json
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","GOOGL","META","AMZN","NVDA","TSLA",
    "JPM","BAC","WFC",
    "JNJ","PFE","MRK",
    "XOM","CVX",
    "WMT","COST","HD","LOW",
    "SBUX","V","MA",
    "UNH","ABBV","LLY",
    "AVGO","AMD","QCOM","INTC","IBM",
]

IS_START  = pd.Timestamp("2022-01-01")
IS_END    = pd.Timestamp("2023-12-31")
OOS_START = pd.Timestamp("2024-01-01")
OOS_END   = pd.Timestamp("2026-06-30")

GATE_WR = 0.818       # H174 baseline win rate
GATE_MR = 0.0689      # H174 baseline mean return
GATE_N  = 15

L1_SURPRISE_THRESH = 0.02
L2_SCORE_THRESH    = 0.18

FMP_BASE = "https://financialmodelingprep.com/stable/earnings"
PROXY_ENV = {"NO_PROXY": "financialmodelingprep.com", "no_proxy": "financialmodelingprep.com"}


def fetch_fmp_earnings(ticker: str) -> pd.DataFrame:
    """Fetch EPS actual/estimated history from FMP, cached locally."""
    cp = CACHE_DIR / f"h481_{ticker}_fmp_earnings.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    key = os.environ.get("FMP_API_KEY")
    if not key:
        return pd.DataFrame()
    # ensure NO_PROXY bypass takes effect even if caller didn't set shell env
    os.environ["NO_PROXY"] = os.environ.get("NO_PROXY", "") + ",financialmodelingprep.com"
    os.environ["no_proxy"] = os.environ.get("no_proxy", "") + ",financialmodelingprep.com"
    try:
        r = requests.get(FMP_BASE, params={"symbol": ticker, "apikey": key}, timeout=30)
        if r.status_code != 200:
            print(f"    FMP {ticker}: HTTP {r.status_code} — {r.text[:120]}")
            return pd.DataFrame()
        data = r.json()
        df = pd.DataFrame(data)
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["epsActual", "epsEstimated"])
        df = df[df["epsEstimated"].abs() > 1e-6]
        df["surprise"] = (df["epsActual"] - df["epsEstimated"]) / df["epsEstimated"].abs()
        df = df.sort_values("date").reset_index(drop=True)
        df.to_parquet(cp)
        time.sleep(0.3)
        return df
    except Exception as e:
        print(f"    FMP {ticker}: error {e}")
        return pd.DataFrame()


def load_ohlcv():
    result = {}
    start, end = "2019-01-01", "2026-06-30"
    to_dl = []
    for t in UNIVERSE:
        for pfx in [f"h{i:03d}" for i in range(155, 175)]:
            for suf in ["ohlcv", "ohlc"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_2019-01-01_2026-04-30.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "open" in df.columns and "close" in df.columns:
                        result[t] = df[["open", "close"]]
                        break
            if t in result:
                break
        if t not in result:
            to_dl.append(t)
    if to_dl:
        print(f"  Downloading {len(to_dl)} tickers fresh (through {end})…")
        batch = yf.download(to_dl, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    df = df.dropna()
                    if len(df) > 100:
                        df.to_parquet(CACHE_DIR / f"h481_{t}_ohlcv_{start}_{end}.parquet")
                        result[t] = df
                except Exception:
                    pass
    # also pick up any h481-cached extension
    for t in UNIVERSE:
        if t not in result:
            p = CACHE_DIR / f"h481_{t}_ohlcv_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                result[t] = df
    return result


def compute_return(ticker, entry_date, ohlcv, hold=20, entry_field="open", use_next_day=False):
    if ticker not in ohlcv:
        return None
    df = ohlcv[ticker].sort_index()
    future = df[df.index >= entry_date]
    if use_next_day:
        future = future.iloc[1:] if len(future) > 1 else future.iloc[0:0]
    if len(future) < hold:
        return None
    entry = future.iloc[0][entry_field]
    exit_ = future.iloc[hold - 1]["close"]
    return (exit_ - entry) / entry if entry > 0 else None


def build_l1_events(fmp_data, ohlcv):
    """Layer 1: numeric EPS surprise events, 1-day hold from announcement open."""
    rows = []
    for t, df in fmp_data.items():
        if df.empty:
            continue
        for _, ev in df.iterrows():
            surprise = ev["surprise"]
            ret = compute_return(t, ev["date"], ohlcv, hold=1, entry_field="open")
            if ret is None:
                continue
            rows.append({"ticker": t, "date": ev["date"], "surprise": surprise, "ret_l1": ret})
    return pd.DataFrame(rows)


def build_l2_events(score_df, ohlcv):
    """Layer 2: FinBERT qualitative score, next-morning entry, 20d hold (= H174 mechanics)."""
    rows = []
    for t in UNIVERSE:
        sub = score_df[score_df["ticker"] == t].sort_values("date")
        for _, ev in sub.iterrows():
            if pd.isna(ev["finbert_score"]):
                continue
            ret = compute_return(t, ev["date"], ohlcv, hold=20, entry_field="open", use_next_day=True)
            if ret is None:
                continue
            rows.append({"ticker": t, "date": ev["date"], "score": ev["finbert_score"], "ret_l2": ret})
    return pd.DataFrame(rows)


def eval_bucket(df, ret_col, label):
    if len(df) == 0:
        return {"n": 0, "wr": 0.0, "mr": 0.0}
    wr = float((df[ret_col] > 0).mean())
    mr = float(df[ret_col].mean())
    n = len(df)
    print(f"    {label}: n={n}  WR={wr*100:.1f}%  MeanRet={mr*100:.2f}%")
    return {"n": n, "wr": wr, "mr": mr}


def main():
    print("=" * 70)
    print("  H481 — Two-Stage PEAD: Numeric Surprise + Qualitative ECT")
    print("  (adapted: FMP EPS surprise substitutes for missing EarningsInOne corpus)")
    print("=" * 70)

    print("\n[1/5] Loading OHLCV…")
    ohlcv = load_ohlcv()
    print(f"  Loaded {len(ohlcv)} / {len(UNIVERSE)} tickers")

    print("\n[2/5] Fetching FMP EPS surprise history (Layer 1)…")
    fmp_data = {}
    for t in UNIVERSE:
        df = fetch_fmp_earnings(t)
        fmp_data[t] = df
        print(f"    {t}: {len(df)} earnings events" if not df.empty else f"    {t}: NO DATA")

    total_l1_events = sum(len(df) for df in fmp_data.values())
    if total_l1_events == 0:
        print("\nNOT RUNNABLE — FMP earnings endpoint returned no usable data for any ticker.")
        out = {"hypothesis": "H481", "status": "NOT RUNNABLE",
               "reason": "FMP /stable/earnings returned no data; EarningsInOne corpus also unavailable (404)."}
        (RESULT_DIR / "h481_results.json").write_text(json.dumps(out, indent=2))
        return

    print(f"  Total raw L1 (EPS) events across universe: {total_l1_events}")

    print("\n[3/5] Loading FinBERT scores (Layer 2, from H163/H174 cache)…")
    score_path = CACHE_DIR / "h163_finbert_scores.parquet"
    if not score_path.exists():
        print("NOT RUNNABLE — H163 FinBERT score cache missing.")
        return
    score_df = pd.read_parquet(score_path)
    score_df["date"] = pd.to_datetime(score_df["date"])
    print(f"  {len(score_df)} FinBERT-scored events loaded")

    print("\n[4/5] Building L1 and L2 event tables…")
    l1_df = build_l1_events(fmp_data, ohlcv)
    l2_df = build_l2_events(score_df, ohlcv)
    print(f"  L1 events with computable 1d return: {len(l1_df)}")
    print(f"  L2 events with computable 20d return: {len(l2_df)}")

    # merge L1 and L2 on ticker + date (allow +/- 1 day tolerance for announcement vs 8-K date)
    l1_df = l1_df.sort_values("date")
    l2_df = l2_df.sort_values("date")
    merged_rows = []
    for _, l2ev in l2_df.iterrows():
        window = l1_df[
            (l1_df["ticker"] == l2ev["ticker"]) &
            (l1_df["date"] >= l2ev["date"] - pd.Timedelta(days=2)) &
            (l1_df["date"] <= l2ev["date"] + pd.Timedelta(days=2))
        ]
        row = {"ticker": l2ev["ticker"], "date": l2ev["date"], "score": l2ev["score"], "ret_l2": l2ev["ret_l2"]}
        if not window.empty:
            row["surprise"] = window.iloc[0]["surprise"]
            row["ret_l1"] = window.iloc[0]["ret_l1"]
        else:
            row["surprise"] = float("nan")
            row["ret_l1"] = float("nan")
        merged_rows.append(row)
    merged = pd.DataFrame(merged_rows)

    def split(df, col="date"):
        is_ = df[(df[col] >= IS_START) & (df[col] <= IS_END)]
        oos_ = df[(df[col] >= OOS_START) & (df[col] <= OOS_END)]
        return is_, oos_

    print("\n[5/5] Evaluating variants A-D…")
    results = {}

    print("\n  Variant A: L1 only (numeric surprise >= 0.02, 1d hold)")
    l1_is, l1_oos = split(l1_df)
    l1_is_f = l1_is[l1_is["surprise"] >= L1_SURPRISE_THRESH]
    l1_oos_f = l1_oos[l1_oos["surprise"] >= L1_SURPRISE_THRESH]
    results["A"] = {
        "is": eval_bucket(l1_is_f, "ret_l1", "IS"),
        "oos": eval_bucket(l1_oos_f, "ret_l1", "OOS"),
        "desc": "L1 numeric surprise >= 0.02, 1d hold from announcement open",
    }

    print("\n  Variant B: L2 only (FinBERT score >= 0.18, 20d hold) [= H174]")
    l2_is, l2_oos = split(l2_df)
    l2_is_f = l2_is[l2_is["score"] >= L2_SCORE_THRESH]
    l2_oos_f = l2_oos[l2_oos["score"] >= L2_SCORE_THRESH]
    results["B"] = {
        "is": eval_bucket(l2_is_f, "ret_l2", "IS"),
        "oos": eval_bucket(l2_oos_f, "ret_l2", "OOS"),
        "desc": "L2 FinBERT score >= 0.18, 20d hold (H174-equivalent)",
    }

    print("\n  Variant C: L1+L2 sequential (blended return: 1d L1 leg + 20d L2 leg if confirmed)")
    m_is, m_oos = split(merged)
    def seq_ret(df):
        # simple sequential model: take L1 1d return if surprise event fired, then add L2 20d
        # return if the qualitative filter also confirms next morning; else just L1 leg.
        rets = []
        for _, r in df.iterrows():
            has_l1 = not pd.isna(r["surprise"]) and r["surprise"] >= L1_SURPRISE_THRESH
            has_l2 = r["score"] >= L2_SCORE_THRESH
            if has_l1 and has_l2:
                rets.append(r["ret_l1"] + r["ret_l2"])
            elif has_l1:
                rets.append(r["ret_l1"])
            elif has_l2:
                rets.append(r["ret_l2"])
            else:
                continue
        return pd.Series(rets, name="ret_c")
    c_is_ret = seq_ret(m_is)
    c_oos_ret = seq_ret(m_oos)
    results["C"] = {
        "is": eval_bucket(pd.DataFrame({"ret_c": c_is_ret}), "ret_c", "IS"),
        "oos": eval_bucket(pd.DataFrame({"ret_c": c_oos_ret}), "ret_c", "OOS"),
        "desc": "L1+L2 sequential: 1d L1 leg, +20d L2 leg if L2 also confirms",
    }

    print("\n  Variant D: L1 AND L2 gate (both surprise>=0.02 AND score>=0.18, 20d hold)")
    m_is_f = m_is[(m_is["surprise"] >= L1_SURPRISE_THRESH) & (m_is["score"] >= L2_SCORE_THRESH)]
    m_oos_f = m_oos[(m_oos["surprise"] >= L1_SURPRISE_THRESH) & (m_oos["score"] >= L2_SCORE_THRESH)]
    results["D"] = {
        "is": eval_bucket(m_is_f, "ret_l2", "IS"),
        "oos": eval_bucket(m_oos_f, "ret_l2", "OOS"),
        "desc": "L1 AND L2 dual gate, 20d hold on L2 leg",
    }

    print(f"\n{'Var':<4} {'IS n':>5} {'IS WR%':>7} {'IS MR%':>7}   {'OOS n':>6} {'OOS WR%':>8} {'OOS MR%':>8}  Gate")
    print("-" * 80)
    confirmed = []
    for v, res in results.items():
        oos = res["oos"]
        beat = oos["n"] >= GATE_N and oos["wr"] > GATE_WR and oos["mr"] > GATE_MR
        flag = "PASS" if beat else "fail"
        print(f"{v:<4} {res['is']['n']:>5} {res['is']['wr']*100:>7.1f} {res['is']['mr']*100:>7.2f}   "
              f"{oos['n']:>6} {oos['wr']*100:>8.1f} {oos['mr']*100:>8.2f}  {flag}")
        if beat:
            confirmed.append(v)

    print(f"\nGate: OOS WR > {GATE_WR*100:.1f}% AND MeanRet > {GATE_MR*100:.2f}% AND n >= {GATE_N}")
    if confirmed:
        verdict = "CONFIRMED"
        print(f"VERDICT: CONFIRMED — variant(s) {', '.join(confirmed)} beat both metrics")
    else:
        verdict = "NOT CONFIRMED"
        print("VERDICT: NOT CONFIRMED — no variant beat both metrics vs H174 baseline")

    out = {
        "hypothesis": "H481",
        "note": "Adapted: EarningsInOne corpus unavailable (404); FMP EPS surprise substitutes for Layer-1 numeric signal.",
        "gate_wr": GATE_WR, "gate_mr": GATE_MR, "gate_n": GATE_N,
        "results": results,
        "confirmed_variants": confirmed,
        "verdict": verdict,
    }
    outpath = RESULT_DIR / "h481_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")


if __name__ == "__main__":
    main()
