"""
H495 — Janus-Q Event-Type Annotation as a Third PEAD Filter Layer
====================================================================
Direct follow-up to H494's explicit recommendation: "the highest-value next
step is substituting the EDGAR 8-K text already fetched for H163/H174 (PEAD)
as the LLM's input in place of point-in-time price statistics, since that
pipeline already solves the historical-text-availability problem."

This is NOT a repeat of H225 (NOT CONFIRMED, 2026-05-25/26), which replaced
H174's FinBERT tone SCORE with a GPT-4o-mini tone score and failed badly
(WR 58.1%, n=43 vs H174's WR 81.8%, n=22) because "GPT-4o-mini too
undiscriminating... applies loose interpretation of 'positive sentiment'
without fine-tuned financial calibration." H495 keeps FinBERT + surprise as
the base dual filter entirely intact and instead asks GPT-4o-mini a
narrower, more structured question: classify the 8-K's dominant EVENT
TYPE (not sentiment) and gate out event types that are not genuinely
earnings/guidance-driven (e.g. litigation notices, restructuring, M&A,
buyback announcements bundled into the same 8-K that happen to coincide
with an earnings-window gap).

Source: arXiv:2602.19919 (Janus-Q), queued in this log as H287 (QUEUED,
2026-06-12): "classify H174 8-K text into 10 event types (EarningsBeat/
Miss/GuidanceRaise/Cut/etc) via GPT-4o-mini; compute IS CAR per event type;
OOS entry only when event type has mean IS CAR >5%." This script implements
that design (H287) under the H495 log slot, using today's exact H174
dual-filter event set for parity.

Design:
  1. Reproduce H174's exact IS/OOS enriched event set (score>=thresh AND
     surprise>=thresh dual filter), using the same OHLCV/earnings-date/
     FinBERT-score infrastructure as run_h174.py.
  2. For each event with cached 8-K text (backtesting/cache/h163_8k_*.txt,
     195 texts already fetched — no new EDGAR calls needed), send the first
     ~4000 chars to GPT-4o-mini and ask it to classify into one of 10 event
     types (Tier 1: EarningsBeat, RevenueUpside, GuidanceRaise; Tier 2:
     ProductLaunch, ContractWin, Buyback/CapitalReturn; Exclusions:
     GuidanceCut, Litigation/Legal, Restructuring/Layoffs, Other/Mixed).
  3. Variant A: Tier-1-only gate (must be EarningsBeat/RevenueUpside/
     GuidanceRaise). Variant B: Tier-1 OR Tier-2. Variant C: Tier-1 AND not
     in Exclusions (redundant safety net). Variant D: baseline H174 dual
     filter, no event-type gate (score>=0.18 & surprise>=0.02, n=22 per log).
  4. Responses cached to backtesting/results/h495_event_type_cache.json
     keyed by (ticker, date) so reruns are free.

Universe/IS/OOS: identical to H174 (30-stock universe, IS <=2023-12-31,
OOS >=2024-01-01, hold=20 trading days, GAP_THRESH=3%).
Gate: OOS WR > 81.8% (H174 baseline) AND n >= 15 (per H287's original spec).
"""
import warnings
warnings.filterwarnings("ignore")

import json, os, re, time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from openai import OpenAI

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)
EVENT_CACHE_PATH = RESULT_DIR / "h495_event_type_cache.json"

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

IS_END     = pd.Timestamp("2023-12-31")
OOS_START  = pd.Timestamp("2024-01-01")
GAP_THRESH = 0.03
SCORE_THRESH    = 0.18
SURPRISE_THRESH = 0.02
LOOKBACK_Q = 4
MIN_PRIOR  = 2
MODEL      = "gpt-4o-mini"

H174_OOS_WR      = 0.818
H174_OOS_MEANRET = 0.0689
MIN_N            = 15

TIER1 = {"EarningsBeat", "RevenueUpside", "GuidanceRaise"}
TIER2 = {"ProductLaunch", "ContractWin", "CapitalReturn"}
EXCLUDE = {"GuidanceCut", "Litigation", "Restructuring", "Other"}
VALID_TYPES = TIER1 | TIER2 | EXCLUDE

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ── Reuse H174/H163 infra ──────────────────────────────────────────────────────

def load_ohlcv():
    result = {}
    start, end = "2019-01-01", "2026-04-30"
    to_dl = []
    for t in UNIVERSE:
        for pfx in [f"h{i:03d}" for i in range(155, 175)]:
            for suf in ["ohlcv", "ohlc"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_{start}_{end}.parquet"
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
        print(f"  Downloading {len(to_dl)} tickers…")
        batch = yf.download(to_dl, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    df = df.dropna()
                    if len(df) > 100:
                        df.to_parquet(CACHE_DIR / f"h495_{t}_ohlcv_{start}_{end}.parquet")
                        result[t] = df
                except Exception:
                    pass
    return result


def get_earnings_dates(ticker):
    cache_path = CACHE_DIR / f"h163_earndates_{ticker}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)["date"].tolist()
    try:
        tk = yf.Ticker(ticker)
        df = tk.earnings_dates
        if df is None or df.empty:
            return []
        df = df.copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.dropna(subset=["Reported EPS"])
        dates = sorted(df.index.tolist())
        pd.DataFrame({"date": dates}).to_parquet(cache_path)
        return dates
    except Exception:
        return []


def find_gap_events(ohlcv):
    events = []
    for t, df in ohlcv.items():
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        for idx, row in df[gap_pct > GAP_THRESH].iterrows():
            events.append({"ticker": t, "date": idx, "gap_pct": gap_pct[idx]})
    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def compute_return(ticker, entry_date, ohlcv, hold=20):
    if ticker not in ohlcv:
        return None
    df = ohlcv[ticker].sort_index()
    future = df[df.index >= entry_date]
    if len(future) < hold:
        return None
    entry = future.iloc[0]["open"]
    exit_ = future.iloc[hold - 1]["close"]
    return (exit_ - entry) / entry if entry > 0 else None


def compute_surprise(ticker, event_date, score_df):
    ticker_scores = score_df[
        (score_df["ticker"] == ticker) &
        (score_df["date"] < event_date) &
        score_df["finbert_score"].notna()
    ].sort_values("date")
    if len(ticker_scores) < MIN_PRIOR:
        return float("nan")
    baseline = ticker_scores.tail(LOOKBACK_Q)["finbert_score"].mean()
    current_row = score_df[
        (score_df["ticker"] == ticker) &
        (score_df["date"] == event_date) &
        score_df["finbert_score"].notna()
    ]
    if current_row.empty:
        return float("nan")
    return current_row.iloc[0]["finbert_score"] - baseline


# ── Event-type classification (GPT-4o-mini, cached) ────────────────────────────

if EVENT_CACHE_PATH.exists():
    event_cache = json.loads(EVENT_CACHE_PATH.read_text())
else:
    event_cache = {}

TAXONOMY_PROMPT = """You are classifying the DOMINANT subject matter of an SEC 8-K filing exhibit \
(press release) that was filed around an earnings date, into exactly ONE of these 10 categories:

Tier 1 (core earnings-beat signal):
- EarningsBeat: primarily reports EPS/net income results beating expectations
- RevenueUpside: primarily reports revenue/sales results beating expectations
- GuidanceRaise: primarily raises forward guidance/outlook

Tier 2 (secondary positive signal):
- ProductLaunch: primarily announces a new product/service launch
- ContractWin: primarily announces a new major contract/partnership win
- CapitalReturn: primarily announces a buyback/dividend increase

Exclusions (not a genuine earnings-beat driver, even if it coincides with an earnings-window gap):
- GuidanceCut: primarily cuts/lowers forward guidance
- Litigation: primarily about a lawsuit, legal settlement, or court filing (NOT earnings-related)
- Restructuring: primarily about layoffs, restructuring, executive departures, or M&A
- Other: none of the above clearly dominates, or the text is boilerplate/unclear

Respond with ONLY the single category name from the list above, nothing else.

TEXT:
{text}
"""

def classify_event_type(ticker, event_date, text):
    key = f"{ticker}_{event_date.date()}"
    if key in event_cache:
        return event_cache[key]
    snippet = text[:4000]
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": TAXONOMY_PROMPT.format(text=snippet)}],
            temperature=0,
            max_tokens=12,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"[A-Za-z]+", raw)
        label = m.group() if m else "Other"
        if label not in VALID_TYPES:
            # fuzzy-match common near-misses
            label_l = label.lower()
            match = next((v for v in VALID_TYPES if v.lower() == label_l), None)
            label = match if match else "Other"
    except Exception as e:
        print(f"    LLM error {ticker} {event_date.date()}: {e}")
        label = "Other"
    event_cache[key] = label
    return label


def get_cached_8k_text(ticker, event_date):
    p = CACHE_DIR / f"h163_8k_{ticker}_{event_date.date()}.txt"
    if p.exists():
        content = p.read_text(encoding="utf-8", errors="ignore")
        return content if len(content) > 100 else None
    return None


# ── Stats helpers ───────────────────────────────────────────────────────────────

def wr(s):
    return float((s > 0).mean()) if len(s) else 0.0

def mean_ret(s):
    return float(s.mean()) if len(s) else 0.0


def main():
    print("=" * 70)
    print("  H495 — Janus-Q Event-Type Annotation as H174 Third Filter Layer")
    print("=" * 70)

    print("\n[1/6] Loading OHLCV…")
    ohlcv = load_ohlcv()
    print(f"  Loaded: {len(ohlcv)} tickers")

    print("\n[2/6] Finding earnings-confirmed gap-up events…")
    all_events = find_gap_events(ohlcv)
    earnings_by_ticker = {t: get_earnings_dates(t) for t in UNIVERSE}

    def is_earnings_gap(ticker, gap_date, window=3):
        for ed in earnings_by_ticker.get(ticker, []):
            if abs((gap_date - ed).days) <= window:
                return True
        return False

    conf_events = all_events[
        all_events.apply(lambda r: is_earnings_gap(r["ticker"], r["date"]), axis=1)
    ].copy()

    is_ev  = conf_events[conf_events["date"] <= IS_END]
    oos_ev = conf_events[conf_events["date"] >= OOS_START]
    print(f"  IS={len(is_ev)}  OOS={len(oos_ev)}")

    print("\n[3/6] Loading FinBERT scores, computing surprise + returns…")
    score_df = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
    score_df["date"] = pd.to_datetime(score_df["date"])

    def enrich(events):
        rows = []
        for _, ev in events.iterrows():
            ret = compute_return(ev["ticker"], ev["date"], ohlcv, hold=20)
            if ret is None:
                continue
            score_row = score_df[(score_df["ticker"] == ev["ticker"]) & (score_df["date"] == ev["date"])]
            score = score_row.iloc[0]["finbert_score"] if not score_row.empty else float("nan")
            surprise = compute_surprise(ev["ticker"], ev["date"], score_df)
            rows.append({"ticker": ev["ticker"], "date": ev["date"], "ret": ret,
                         "score": score, "surprise": surprise})
        return pd.DataFrame(rows)

    is_df  = enrich(is_ev)
    oos_df = enrich(oos_ev)

    print("\n[4/6] Applying H174 dual filter (score>=0.18 AND surprise>=0.02)…")
    is_dual  = is_df.dropna(subset=["score", "surprise"])
    is_dual  = is_dual[(is_dual["score"] >= SCORE_THRESH) & (is_dual["surprise"] >= SURPRISE_THRESH)]
    oos_dual = oos_df.dropna(subset=["score", "surprise"])
    oos_dual = oos_dual[(oos_dual["score"] >= SCORE_THRESH) & (oos_dual["surprise"] >= SURPRISE_THRESH)]
    print(f"  IS dual-filter events:  n={len(is_dual)}")
    print(f"  OOS dual-filter events: n={len(oos_dual)}  (H174 baseline log value: n=22)")
    baseline_oos_wr = wr(oos_dual["ret"])
    baseline_oos_mr = mean_ret(oos_dual["ret"])
    print(f"  OOS baseline: WR={baseline_oos_wr*100:.1f}%  MeanRet={baseline_oos_mr*100:.2f}%")

    print(f"\n[5/6] Classifying event types via {MODEL} (cached to {EVENT_CACHE_PATH.name})…")
    t0 = time.time()
    n_scored, n_missing_text = 0, 0

    def classify_df(df):
        nonlocal n_scored, n_missing_text
        labels = []
        for _, row in df.iterrows():
            text = get_cached_8k_text(row["ticker"], row["date"])
            if text is None:
                n_missing_text += 1
                labels.append(None)
                continue
            label = classify_event_type(row["ticker"], row["date"], text)
            n_scored += 1
            labels.append(label)
        out = df.copy()
        out["event_type"] = labels
        return out

    is_dual  = classify_df(is_dual)
    oos_dual = classify_df(oos_dual)
    EVENT_CACHE_PATH.write_text(json.dumps(event_cache, indent=0))
    elapsed = time.time() - t0
    print(f"  Classified {n_scored} events ({n_missing_text} missing cached 8-K text) in {elapsed:.0f}s")

    print("\n  OOS event-type distribution (dual-filter set):")
    print(oos_dual["event_type"].value_counts(dropna=False).to_string())

    print("\n[6/6] Evaluating variants…")

    def eval_variant(tag, df_is, df_oos, is_baseline=False):
        if len(df_oos) == 0:
            print(f"  {tag:<40} n=0 SKIP")
            return {"n_is": len(df_is), "n_oos": 0, "skip": True, "pass_gate": False}
        oos_wr = wr(df_oos["ret"])
        oos_mr = mean_ret(df_oos["ret"])
        is_wr  = wr(df_is["ret"]) if len(df_is) else 0.0
        is_mr  = mean_ret(df_is["ret"]) if len(df_is) else 0.0
        # Gate requires a GENUINE improvement over the H174 baseline it is being
        # compared to, not merely matching it (floating-point equality with the
        # baseline itself must not register as a "pass" — this variant IS the
        # baseline reproduction, used only to confirm script fidelity).
        passes = (not is_baseline) and (oos_wr > H174_OOS_WR + 1e-9) and (len(df_oos) >= MIN_N)
        print(f"  {tag:<40} IS(n={len(df_is):>2} WR={is_wr*100:5.1f}% Ret={is_mr*100:5.2f}%)  "
              f"OOS(n={len(df_oos):>2} WR={oos_wr*100:5.1f}% Ret={oos_mr*100:5.2f}%)  "
              f"{'PASS' if passes else 'fail'}")
        return {
            "n_is": len(df_is), "n_oos": len(df_oos),
            "is_wr": round(is_wr, 3), "is_mean_ret": round(is_mr, 4),
            "oos_wr": round(oos_wr, 3), "oos_mean_ret": round(oos_mr, 4),
            "pass_gate": passes,
        }

    results_all = {}

    # Variant D: baseline (no event-type gate) — reproduction check only, cannot "pass" its own gate
    results_all["D_baseline_dual_filter"] = eval_variant(
        "D (baseline dual filter, no event gate)", is_dual, oos_dual, is_baseline=True)

    # Variant A: Tier-1 only
    is_a  = is_dual[is_dual["event_type"].isin(TIER1)]
    oos_a = oos_dual[oos_dual["event_type"].isin(TIER1)]
    results_all["A_tier1_only"] = eval_variant("A (Tier-1: EarningsBeat/RevUpside/GuidanceRaise)", is_a, oos_a)

    # Variant B: Tier-1 OR Tier-2
    is_b  = is_dual[is_dual["event_type"].isin(TIER1 | TIER2)]
    oos_b = oos_dual[oos_dual["event_type"].isin(TIER1 | TIER2)]
    results_all["B_tier1_or_tier2"] = eval_variant("B (Tier-1 OR Tier-2)", is_b, oos_b)

    # Variant C: not in Exclusions (safety net, keeps Other too)
    is_c  = is_dual[~is_dual["event_type"].isin(EXCLUDE)]
    oos_c = oos_dual[~oos_dual["event_type"].isin(EXCLUDE)]
    results_all["C_exclude_negative_types"] = eval_variant("C (exclude GuidanceCut/Litigation/Restructuring/Other)", is_c, oos_c)

    any_pass = any(v.get("pass_gate", False) for v in results_all.values())
    verdict = "CONFIRMED" if any_pass else "NOT CONFIRMED"

    print(f"\nGate: OOS WR > {H174_OOS_WR*100:.1f}% AND n >= {MIN_N}")
    print(f"Baseline (D): OOS WR={baseline_oos_wr*100:.1f}%, MeanRet={baseline_oos_mr*100:.2f}%, n={len(oos_dual)}")
    print(f"Verdict: {verdict}")

    # Correlation to production blend / SPY estimate (event-count too small for
    # monthly return series regression — report qualitative/structural estimate)
    results = {
        "hypothesis": "H495",
        "description": "Janus-Q (arXiv:2602.19919) event-type taxonomy classification via GPT-4o-mini as a third filter layer on top of H174's FinBERT+surprise dual filter (implements H287's queued design)",
        "source": "arXiv:2602.19919 (Janus-Q); queued as H287 (2026-06-12); direct follow-up to H494's explicit recommendation to use EDGAR 8-K text (not price stats) as LLM input",
        "model": MODEL,
        "universe": UNIVERSE,
        "is_end": str(IS_END.date()),
        "oos_start": str(OOS_START.date()),
        "score_thresh": SCORE_THRESH,
        "surprise_thresh": SURPRISE_THRESH,
        "h174_baseline_oos_wr": H174_OOS_WR,
        "h174_baseline_oos_meanret": H174_OOS_MEANRET,
        "gate": f"OOS WR > {H174_OOS_WR} AND n >= {MIN_N}",
        "n_events_classified": n_scored,
        "n_missing_cached_text": n_missing_text,
        "oos_event_type_distribution": oos_dual["event_type"].value_counts(dropna=False).to_dict(),
        "variants": results_all,
        "verdict": verdict,
    }
    (RESULT_DIR / "h495_results.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\nSaved → h495_results.json")


if __name__ == "__main__":
    main()
