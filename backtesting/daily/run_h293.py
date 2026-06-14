"""
H293 — Press Release Structure Signal for PEAD
===============================================

Hypothesis:
  Wu, Akin, Martineau, Grégoire & Veneris (2025) "Extracting the Structure of Press
  Releases for Predicting Earnings Announcement Returns." ACM ICAIF 2025.
  arXiv:2509.24254

  Key finding: structural decomposition of earnings press releases (scoring HIGHLIGHTS,
  RESULTS, and GUIDANCE sections separately) is AS informative as EPS surprise for
  predicting announcement-day returns. FinBERT is the highest-performing model.

  Upgrade over H174 (OOS WR=81.8%, n=22): instead of a single FinBERT score on the
  full 8-K document, compute a section-weighted composite:
    composite = 0.3 * score_highlights + 0.2 * score_results + 0.5 * score_guidance

  The guidance/outlook section gets double weight because it reflects management's
  forward expectations — the most predictive component for PEAD.

  Gate improvement: OOS WR > 81.8%, n >= 15
  Dual filter: composite_score >= 0.18 AND EPS_surprise >= 0.02 (same as H174)

  IS:  2018-2022
  OOS: 2023-2025

Academic basis:
  - Wu et al. (2025): 138K+ press releases 2005-2023; FinBERT best model;
    structural soft-information as informative as hard EPS surprise;
    prices fully reflect content at market open → OPG execution matches H174
  - H174 CONFIRMED: dual filter (score >= 0.18 + surprise >= 0.02) → OOS WR=81.8%
  - H163 CONFIRMED: full-text FinBERT on 8-K → OOS WR=80.8%
"""

import json
import re
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

IS_END    = pd.Timestamp("2022-12-31")
OOS_START = pd.Timestamp("2023-01-01")

GAP_THRESH   = 0.03   # 3% overnight gap to flag earnings event
HOLD_DAYS    = 20     # trading days holding period
LOOKBACK_Q   = 4      # quarters for baseline surprise
MIN_PRIOR    = 2      # minimum prior scored events before computing surprise
SCORE_GATE   = 0.18   # composite FinBERT gate (same as H174)
SURPRISE_GATE = 0.02  # EPS surprise gate (same as H174)

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

EDGAR_HEADERS = {
    "User-Agent": "George NanoClaw george@nanoclaw.ai",
    "Accept-Encoding": "gzip, deflate",
}

# ─── FinBERT setup ────────────────────────────────────────────────────────────
try:
    from transformers import pipeline as hf_pipeline
    FINBERT = hf_pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        return_all_scores=True,
        truncation=True,
        max_length=512,
    )
    print("  FinBERT loaded.")
except Exception as e:
    print(f"  FinBERT unavailable: {e}")
    FINBERT = None


def finbert_score(text: str) -> float:
    """Returns net positive score: P(positive) - P(negative)."""
    if not text or FINBERT is None:
        return float("nan")
    text = text[:2000]  # truncate to manageable size for 512-token limit
    try:
        results = FINBERT(text)[0]
        scores = {r["label"]: r["score"] for r in results}
        return scores.get("positive", 0.0) - scores.get("negative", 0.0)
    except Exception:
        return float("nan")


# ─── Section extraction ────────────────────────────────────────────────────────
_HIGHLIGHT_PAT = re.compile(
    r"(?i)(?:highlight|key\s+result|financial\s+highlight|summary|selected\s+data)"
    r"(.*?)(?=\n\n[A-Z][A-Z\s]{3,}|\Z)",
    re.DOTALL,
)
_RESULTS_PAT = re.compile(
    r"(?i)(?:financial\s+result|revenue|quarterly\s+result|operating\s+result|"
    r"income\s+from\s+operations|net\s+income|earnings\s+per\s+share|eps)"
    r"(.*?)(?=\n\n[A-Z][A-Z\s]{3,}|\Z)",
    re.DOTALL,
)
_GUIDANCE_PAT = re.compile(
    r"(?i)(?:guidance|outlook|forecast|forward.looking|expect|anticipate|"
    r"full.year|fiscal\s+\d{4})"
    r"(.*?)(?=\n\n[A-Z][A-Z\s]{3,}|\Z)",
    re.DOTALL,
)


def extract_section(text: str, pattern: re.Pattern, max_chars: int = 1500) -> str:
    m = pattern.search(text)
    if m:
        return m.group(0)[:max_chars].strip()
    return ""


def section_weighted_score(text: str) -> dict:
    """Score three sections separately and return composite + individual scores."""
    highlights = extract_section(text, _HIGHLIGHT_PAT)
    results    = extract_section(text, _RESULTS_PAT)
    guidance   = extract_section(text, _GUIDANCE_PAT)

    s_h = finbert_score(highlights) if highlights else float("nan")
    s_r = finbert_score(results)    if results    else float("nan")
    s_g = finbert_score(guidance)   if guidance   else float("nan")

    # Fall back to full-text score for missing sections
    s_full = finbert_score(text[:2000])

    def fill(v, fallback):
        return v if np.isfinite(v) else fallback

    s_h = fill(s_h, s_full)
    s_r = fill(s_r, s_full)
    s_g = fill(s_g, s_full)

    composite = 0.30 * s_h + 0.20 * s_r + 0.50 * s_g

    return {
        "score_highlights": round(s_h, 4),
        "score_results":    round(s_r, 4),
        "score_guidance":   round(s_g, 4),
        "composite":        round(composite, 4),
        "has_highlights":   bool(highlights),
        "has_results":      bool(results),
        "has_guidance":     bool(guidance),
    }


# ─── EDGAR pipeline ───────────────────────────────────────────────────────────
def load_cik_map() -> dict:
    cache = CACHE_DIR / "sec_cik_map.json"
    if cache.exists():
        return json.loads(cache.read_text())
    resp = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers=EDGAR_HEADERS, timeout=30
    )
    data = resp.json()
    mapping = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}
    cache.write_text(json.dumps(mapping))
    return mapping


def get_8k_filings(ticker: str, cik: str) -> list:
    cache = CACHE_DIR / f"h293_8k_list_{ticker}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
        sub  = resp.json()
        filings = sub.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        dates   = filings.get("filingDate", [])
        accnos  = filings.get("accessionNumber", [])
        docs    = filings.get("primaryDocument", [])
        result  = [
            {"date": d, "accession": a.replace("-", ""), "doc": doc}
            for f, d, a, doc in zip(forms, dates, accnos, docs)
            if f == "8-K"
        ]
        cache.write_text(json.dumps(result))
        return result
    except Exception:
        return []


def fetch_8k_text(ticker: str, cik_int: str, accession: str, doc: str) -> str:
    cache = CACHE_DIR / f"h293_8k_{ticker}_{accession}.txt"
    if cache.exists():
        return cache.read_text()[:50_000]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik_int)}/{accession}/{doc}"
    try:
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
        raw  = resp.text
        text = re.sub(r"<[^>]{0,500}>", " ", raw)
        text = re.sub(r"\s{3,}", "\n\n", text)[:50_000]
        cache.write_text(text)
        time.sleep(0.1)
        return text
    except Exception:
        return ""


# ─── OHLCV helpers ────────────────────────────────────────────────────────────
def load_ohlcv() -> dict:
    result = {}
    start, end = "2017-01-01", "2026-06-01"
    to_dl = []
    for t in UNIVERSE:
        p = CACHE_DIR / f"h293_ohlcv_{t}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            result[t] = df
        else:
            to_dl.append(t)
    if to_dl:
        print(f"  Downloading OHLCV for {len(to_dl)} tickers…")
        batch = yf.download(to_dl, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    df = df.dropna()
                    df.to_parquet(CACHE_DIR / f"h293_ohlcv_{t}.parquet")
                    result[t] = df
                except Exception:
                    pass
    return result


def get_earnings_dates(ticker: str) -> list:
    cache = CACHE_DIR / f"h163_earndates_{ticker}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)["date"].tolist()
    try:
        df = yf.Ticker(ticker).earnings_dates
        if df is None or df.empty:
            return []
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.dropna(subset=["Reported EPS"])
        dates = sorted(df.index.tolist())
        pd.DataFrame({"date": dates}).to_parquet(cache)
        return dates
    except Exception:
        return []


def compute_return(ticker: str, entry_date, ohlcv: dict, hold: int = HOLD_DAYS):
    if ticker not in ohlcv:
        return None
    df = ohlcv[ticker].sort_index()
    future = df[df.index >= entry_date]
    if len(future) < hold:
        return None
    entry = future.iloc[0]["open"]
    exit_ = future.iloc[hold - 1]["close"]
    return (exit_ - entry) / entry if entry > 0 else None


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("H293 — Press Release Structure Signal (Section-Weighted FinBERT)")
    print("=" * 70)

    if FINBERT is None:
        print("ERROR: FinBERT unavailable. Install: pip install transformers torch")
        return

    # Step 1: OHLCV + earnings gaps
    print("\n[1] Loading OHLCV…")
    ohlcv = load_ohlcv()
    earnings_map = {t: get_earnings_dates(t) for t in UNIVERSE}
    print(f"  {len(ohlcv)} tickers loaded")

    def is_earnings_gap(ticker, gap_date, window=3):
        return any(abs((gap_date - ed).days) <= window
                   for ed in earnings_map.get(ticker, []))

    gap_events = []
    for t, df in ohlcv.items():
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        for idx, g in gap_pct[gap_pct > GAP_THRESH].items():
            if is_earnings_gap(t, idx):
                gap_events.append({"ticker": t, "date": idx, "gap_pct": g})

    events = pd.DataFrame(gap_events).sort_values("date").reset_index(drop=True)
    print(f"  Earnings gap events: {len(events)}")

    # Step 2: Load/build section-weighted FinBERT scores from 8-Ks
    score_cache = CACHE_DIR / "h293_section_scores.parquet"
    if score_cache.exists():
        print("\n[2] Loading cached section scores…")
        score_df = pd.read_parquet(score_cache)
    else:
        print("\n[2] Downloading 8-K filings and computing section scores…")
        print("    (This takes 30-60 min on first run)")
        cik_map = load_cik_map()
        rows = []
        for t in UNIVERSE:
            cik = cik_map.get(t)
            if not cik:
                continue
            filings = get_8k_filings(t, cik)
            cik_int = str(int(cik))
            for f in filings:
                fdate = pd.Timestamp(f["date"])
                if fdate < pd.Timestamp("2017-01-01"):
                    continue
                text = fetch_8k_text(t, cik_int, f["accession"], f["doc"])
                if len(text) < 200:
                    continue
                scored = section_weighted_score(text)
                rows.append({
                    "ticker": t, "date": fdate,
                    **scored
                })
        score_df = pd.DataFrame(rows).sort_values(["ticker", "date"])
        score_df.to_parquet(score_cache)
    print(f"  Scored filings: {len(score_df)}")

    # Step 3: Compute per-event composite + surprise signal
    print("\n[3] Computing composite scores and surprise signals…")
    score_df["date"] = pd.to_datetime(score_df["date"])
    results = []

    for _, ev in events.iterrows():
        t, ev_date = ev["ticker"], ev["date"]

        # Find nearest 8-K score ≤ event date (within 14 days)
        ticker_scores = score_df[score_df["ticker"] == t].sort_values("date")
        prior = ticker_scores[
            (ticker_scores["date"] >= ev_date - pd.Timedelta(days=14)) &
            (ticker_scores["date"] <= ev_date)
        ]
        if prior.empty:
            continue
        current = prior.iloc[-1]
        composite = current["composite"]

        # Surprise: composite vs prior LOOKBACK_Q baseline
        baseline_rows = ticker_scores[ticker_scores["date"] < current["date"]].tail(LOOKBACK_Q)
        if len(baseline_rows) < MIN_PRIOR:
            surprise = float("nan")
        else:
            surprise = composite - baseline_rows["composite"].mean()

        # Forward return (20-day hold from next open)
        ret = compute_return(t, ev_date, ohlcv)
        if ret is None:
            continue

        results.append({
            "ticker": t,
            "date": ev_date,
            "composite": composite,
            "score_guidance": current.get("score_guidance", float("nan")),
            "surprise": surprise,
            "has_guidance": current.get("has_guidance", False),
            "ret": ret,
            "period": "IS" if ev_date <= IS_END else "OOS",
        })

    df_results = pd.DataFrame(results)
    print(f"  Total events with scores: {len(df_results)}")

    # Step 4: Threshold sweep
    def sweep(data, label):
        print(f"\n  {label} (n={len(data)})")
        print(f"  {'Composite':>10} {'Surp':>6} {'n':>5} {'WR%':>7} {'MeanRet%':>10}")
        print("  " + "-" * 45)
        best = None
        for c_thr in [0.10, 0.14, 0.18, 0.22, 0.26]:
            for s_thr in [0.0, 0.01, 0.02, 0.03]:
                sub = data[
                    (data["composite"] >= c_thr) &
                    (data["surprise"].fillna(-99) >= s_thr)
                ]
                if len(sub) == 0:
                    continue
                wr = (sub["ret"] > 0).mean()
                mr = sub["ret"].mean()
                n  = len(sub)
                flag = " ← H174 gate" if (c_thr == 0.18 and s_thr == 0.02) else ""
                confirm = "✓" if (wr > 0.818 and n >= 15) else ""
                print(f"  c≥{c_thr:.2f} s≥{s_thr:.2f} {n:>5} {wr*100:>7.1f} {mr*100:>10.2f} {confirm}{flag}")
                if confirm and (best is None or wr > best["wr"]):
                    best = {"c": c_thr, "s": s_thr, "n": n, "wr": wr, "mr": mr}
        return best

    is_data  = df_results[df_results["period"] == "IS"]
    oos_data = df_results[df_results["period"] == "OOS"]

    print(f"\n{'=' * 60}")
    print("RESULTS — H293 Section-Weighted FinBERT")
    print(f"{'=' * 60}")
    sweep(is_data, "In-Sample (2018-2022)")
    best_oos = sweep(oos_data, "Out-of-Sample (2023-2025)")

    # H174 baseline comparison at gate (0.18, 0.02)
    oos_gate = oos_data[
        (oos_data["composite"] >= SCORE_GATE) &
        (oos_data["surprise"].fillna(-99) >= SURPRISE_GATE)
    ]
    gate_wr = (oos_gate["ret"] > 0).mean() if len(oos_gate) > 0 else float("nan")
    gate_mr = oos_gate["ret"].mean()        if len(oos_gate) > 0 else float("nan")

    print(f"\nAt H174 gate (composite≥0.18, surprise≥0.02):")
    print(f"  OOS: n={len(oos_gate)}, WR={gate_wr*100:.1f}%, MeanRet={gate_mr*100:.2f}%")
    print(f"  H174 baseline: WR=81.8%, n=22")
    print(f"  Guidance-section coverage: {oos_data['has_guidance'].mean()*100:.0f}% of events")

    verdict = "CONFIRMED" if (gate_wr > 0.818 and len(oos_gate) >= 15) else "NOT CONFIRMED"
    print(f"\nVERDICT: {verdict}")

    # Save
    out_path = RESULT_DIR / "h293_results.json"
    out_path.write_text(json.dumps({
        "hypothesis": "H293",
        "description": "Press Release Structure PEAD (section-weighted FinBERT)",
        "source": "arXiv:2509.24254",
        "is_period": "2018-2022", "oos_period": "2023-2025",
        "gate_composite": SCORE_GATE, "gate_surprise": SURPRISE_GATE,
        "oos_n": len(oos_gate), "oos_wr": round(gate_wr, 4) if np.isfinite(gate_wr) else None,
        "oos_mean_ret": round(gate_mr, 4) if np.isfinite(gate_mr) else None,
        "h174_baseline_wr": 0.818, "h174_baseline_n": 22,
        "verdict": verdict,
    }, indent=2))
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
