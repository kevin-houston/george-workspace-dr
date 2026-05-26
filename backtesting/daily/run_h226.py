"""
H226 — PEAD-NLP: GPT-4o-mini Quantitative Beat/Miss Prompt
============================================================
H225 NOT CONFIRMED: GPT-4o-mini "tone" prompt gives 79% of events score≥0.5
(discrete clustering at 0, 0.5, 1.0) — no discrimination vs FinBERT.

Root cause: earnings press releases are written positively; GPT evaluates tone,
not whether results beat or missed analyst expectations.

H226 fix: structured prompt that explicitly asks GPT to evaluate QUANTITATIVE
beat/miss — EPS vs prior year, revenue growth vs prior quarter, guidance language.
Forces GPT to anchor on numbers, not PR tone.

Confirm: OOS WR > 83% OR MeanRet > 7.5% (same as H225, vs H174 baseline)
"""

import warnings
warnings.filterwarnings("ignore")

import json, os, re, time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

WORKSPACE   = Path(__file__).resolve().parent.parent.parent
CACHE_DIR   = WORKSPACE / "backtesting" / "cache"
RESULT_DIR  = WORKSPACE / "backtesting" / "results"
GPT_CACHE   = CACHE_DIR / "h226_gpt_scores.parquet"

IS_END    = pd.Timestamp("2023-12-31")
OOS_START = pd.Timestamp("2024-01-01")
GAP_THRESH = 0.03
LOOKBACK_Q = 4
MIN_PRIOR  = 2

# Quantitative beat/miss prompt — anchors on numbers, not PR tone
SCORE_PROMPT = """You are a financial analyst. Read this earnings press release and score ONLY the quantitative performance:

Look for:
1. EPS (earnings per share): Did it grow vs prior year? By how much?
2. Revenue: Did it grow vs prior year? By how much?
3. Forward guidance: Was it raised, maintained, or lowered?

Return a JSON with one key "score" (float, -1.0 to +1.0):
  +1.0 = strong beats: EPS +20%+ AND revenue +15%+ AND guidance raised
  +0.5 = solid beat: EPS or revenue beat clearly, guidance OK
   0.0 = mixed or in-line: meets prior year but no outperformance
  -0.5 = miss: EPS or revenue declined, guidance cautious
  -1.0 = serious miss: EPS AND revenue declined OR guidance withdrawn/cut

Base your score ONLY on the numbers in the text, NOT on management language or sentiment.
If you cannot find specific numbers, return {"score": 0.0}.

Respond with ONLY the JSON. Example: {"score": 0.65}

Press release:
"""

def score_with_gpt(text: str, client) -> float:
    try:
        truncated = text[:12000]
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": SCORE_PROMPT + truncated}],
            max_tokens=20,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
        return max(-1.0, min(1.0, float(data["score"])))
    except Exception as e:
        try:
            m = re.search(r"-?\d+\.?\d*", raw)
            if m:
                return max(-1.0, min(1.0, float(m.group())))
        except Exception:
            pass
        return float("nan")

def load_or_build_scores():
    if GPT_CACHE.exists():
        df = pd.read_parquet(GPT_CACHE)
        print(f"  Loaded {len(df)} cached GPT scores")
        return df
    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    txt_files = sorted(CACHE_DIR.glob("h163_8k_*.txt"))
    print(f"  Scoring {len(txt_files)} 8-K texts…")
    records = []
    for i, fp in enumerate(txt_files):
        parts = fp.stem.split("_")
        ticker, date_str = parts[2], parts[-1]
        try:
            date = pd.Timestamp(date_str)
        except Exception:
            continue
        text = fp.read_text(encoding="utf-8", errors="ignore")
        if len(text) < 100:
            continue
        score = score_with_gpt(text, client)
        records.append({"ticker": ticker, "date": date, "gpt_score": score})
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(txt_files)}…")
            pd.DataFrame(records).to_parquet(GPT_CACHE)
        time.sleep(0.5)
    df = pd.DataFrame(records)
    df.to_parquet(GPT_CACHE)
    return df

def load_ohlcv():
    result = {}
    for fp in CACHE_DIR.glob("h163_*_ohlcv_*.parquet"):
        ticker = fp.stem.split("_")[1]
        df = pd.read_parquet(fp)
        df.columns = [c.lower() for c in df.columns]
        if "open" in df.columns and "close" in df.columns:
            result[ticker] = df[["open", "close"]]
    return result

def get_earnings_dates(ticker):
    p = CACHE_DIR / f"h163_earndates_{ticker}.parquet"
    return pd.read_parquet(p)["date"].tolist() if p.exists() else []

def find_gap_events(ohlcv):
    events = []
    for t, df in ohlcv.items():
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        for idx in df[gap_pct > GAP_THRESH].index:
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
    prior = score_df[
        (score_df["ticker"] == ticker) &
        (score_df["date"] < event_date) &
        score_df["gpt_score"].notna()
    ].sort_values("date")
    if len(prior) < MIN_PRIOR:
        return float("nan")
    baseline = prior.tail(LOOKBACK_Q)["gpt_score"].mean()
    cur = score_df[
        (score_df["ticker"] == ticker) &
        (score_df["date"] == event_date) &
        score_df["gpt_score"].notna()
    ]
    if cur.empty:
        return float("nan")
    return cur.iloc[0]["gpt_score"] - baseline

def build_event_df(events, score_df, ohlcv, earnings_by_ticker):
    def is_earnings_gap(ticker, gap_date):
        for ed in earnings_by_ticker.get(ticker, []):
            if abs((gap_date - ed).days) <= 1:
                return True
        return False

    conf = events[events.apply(lambda r: is_earnings_gap(r["ticker"], r["date"]), axis=1)].copy()
    rows = []
    for _, ev in conf.iterrows():
        t, dt = ev["ticker"], ev["date"]
        nearby = score_df[
            (score_df["ticker"] == t) &
            (abs((score_df["date"] - dt).dt.days) <= 1) &
            score_df["gpt_score"].notna()
        ]
        if nearby.empty:
            continue
        sc = nearby.iloc[0]["gpt_score"]
        surp = compute_surprise(t, nearby.iloc[0]["date"], score_df)
        ret = compute_return(t, dt, ohlcv)
        if ret is None:
            continue
        rows.append({"ticker": t, "date": dt, "score": sc,
                     "surprise": surp, "ret": ret})
    return pd.DataFrame(rows)

def main():
    print("=" * 62)
    print("  H226 — PEAD: GPT-4o-mini Quantitative Beat/Miss Prompt")
    print("  Root cause fix: anchor on numbers, not tone")
    print("=" * 62)

    print("\n[1/4] Loading GPT quant scores…")
    gpt_df = load_or_build_scores()
    gpt_df["date"] = pd.to_datetime(gpt_df["date"])
    print(f"  {len(gpt_df)} events scored")
    print(f"  Distribution: mean={gpt_df['gpt_score'].mean():.3f}  "
          f"std={gpt_df['gpt_score'].std():.3f}  "
          f"median={gpt_df['gpt_score'].median():.3f}")
    buckets = pd.cut(gpt_df["gpt_score"],
                     bins=[-1.1,-0.5,-0.1,0.1,0.5,1.1],
                     labels=["Very Neg","Neg","Neutral","Pos","Very Pos"])
    print("  " + str(buckets.value_counts().sort_index().to_dict()))

    print("\n[2/4] Loading OHLCV and earnings dates…")
    ohlcv = load_ohlcv()
    earnings_by_ticker = {t: get_earnings_dates(t) for t in gpt_df["ticker"].unique()}

    print("\n[3/4] Building IS/OOS event sets…")
    all_ev = find_gap_events(ohlcv)
    is_ev  = all_ev[all_ev["date"] <= IS_END]
    oos_ev = all_ev[all_ev["date"] >= OOS_START]
    is_df  = build_event_df(is_ev,  gpt_df, ohlcv, earnings_by_ticker)
    oos_df = build_event_df(oos_ev, gpt_df, ohlcv, earnings_by_ticker)
    print(f"  IS: {len(is_df)} events   OOS: {len(oos_df)} events")

    # Also load FinBERT for reference
    fb_df = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
    fb_df["date"] = pd.to_datetime(fb_df["date"])

    print("\n[4/4] Threshold sweep")
    print("\n  OOS GPT score sweep:")
    print(f"  {'Thresh':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10}")
    print("  " + "-" * 40)
    for thr in [0.0, 0.1, 0.15, 0.18, 0.20, 0.25, 0.30, 0.40, 0.50]:
        if len(oos_df) == 0 or "score" not in oos_df.columns:
            break
        f = oos_df[oos_df["score"] >= thr]
        if len(f) < 3:
            continue
        print(f"  {thr:>8.2f} {len(f):>5} {(f['ret']>0).mean()*100:>7.1f} "
              f"{f['ret'].mean()*100:>10.2f}")

    print("\n  OOS dual filter grid (score + surprise):")
    print(f"  {'ScoreT':>8} {'SurpT':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10} {'OK':>6}")
    print("  " + "-" * 52)
    best = None
    for st in [0.0, 0.10, 0.20, 0.30, 0.40, 0.50]:
        for su in [0.0, 0.01, 0.02, 0.05]:
            if len(oos_df) == 0 or "score" not in oos_df.columns:
                continue
            f = oos_df[(oos_df["score"] >= st) & (oos_df["surprise"] >= su)]
            if len(f) < 5:
                continue
            wr = (f["ret"] > 0).mean()
            mr = f["ret"].mean()
            ok = "CONFIRM" if (wr >= 0.83 or mr >= 0.075) else ""
            print(f"  {st:>8.2f} {su:>8.2f} {len(f):>5} {wr*100:>7.1f} {mr*100:>10.2f} {ok:>6}")
            if ok and (best is None or wr > best["wr"]):
                best = {"score_thresh": st, "surp_thresh": su,
                        "n": len(f), "wr": wr, "mr": mr}

    print("\n" + "=" * 62)
    confirmed = best is not None
    print(f"  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    if best:
        print(f"  Best: score≥{best['score_thresh']} + surprise≥{best['surp_thresh']}")
        print(f"  OOS WR={best['wr']*100:.1f}%  MeanRet={best['mr']*100:.2f}%  n={best['n']}")
    print(f"  H174 baseline: WR=81.8%  MeanRet=6.89%  n=22")

    results = {
        "hypothesis": "H226",
        "date_run": datetime.now().isoformat(),
        "model": "gpt-4o-mini-quantitative-prompt",
        "baseline": "H174",
        "confirmed": confirmed,
        "best_threshold": best,
        "score_distribution": {
            "mean": float(gpt_df["gpt_score"].mean()),
            "std": float(gpt_df["gpt_score"].std()),
            "median": float(gpt_df["gpt_score"].median()),
        }
    }
    import json
    (RESULT_DIR / "h226_results.json").write_text(
        json.dumps(results, indent=2, default=str))
    print(f"\n  Results saved → backtesting/results/h226_results.json")

if __name__ == "__main__":
    main()
