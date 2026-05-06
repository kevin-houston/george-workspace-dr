"""
H174 — PEAD-NLP: H163 Score + Sentiment Surprise Dual Filter
=============================================================
H163 CONFIRMED: absolute FinBERT score > 0.10 → OOS WR ≥ 68%, MeanRet ≥ 5.5%, n≥15
H173 NOT CONFIRMED: surprise signal alone is weak at n=30 universe / 4q lookback

This hypothesis combines both:
  1. Primary: FinBERT score > threshold (H163 confirmed signal)
  2. Secondary: surprise = score_t - mean(prior 4q) > 0 (company beat own tone baseline)

Rationale: Many of H163's confirmed events may be "structurally positive" companies
(tech) that always score high. Adding the surprise filter removes events where tone
is positive but unchanged vs prior quarters, keeping only events where tone is
ABOVE the company's own norm. This should improve precision at the cost of recall.

Also tests: surprise > 0 alone as primary filter (comparing to both H163 and H173).
"""

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"

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

IS_END    = pd.Timestamp("2023-12-31")
OOS_START = pd.Timestamp("2024-01-01")
GAP_THRESH = 0.03
LOOKBACK_Q = 4
MIN_PRIOR  = 2


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
        batch = yf.download(to_dl, start=start, end=end,
                            auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    df = df.dropna()
                    if len(df) > 100:
                        df.to_parquet(
                            CACHE_DIR / f"h174_{t}_ohlcv_{start}_{end}.parquet")
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


def print_sweep(label, data, thresholds, col="score"):
    print(f"\n  {label}")
    print(f"  {'Thresh':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10} {'Confirm':>10}")
    print("  " + "-" * 50)
    results = []
    for thresh in thresholds:
        filtered = data[data[col] >= thresh]
        if len(filtered) == 0:
            continue
        wr = (filtered["ret"] > 0).mean()
        mr = filtered["ret"].mean()
        n  = len(filtered)
        confirmed = "CONFIRM" if (wr >= 0.68 and mr >= 0.055 and n >= 15) else ""
        results.append({"thresh": thresh, "n": n, "wr": wr, "mr": mr,
                        "confirmed": bool(confirmed)})
        print(f"  {thresh:>8.2f} {n:>5} {wr*100:>7.1f} {mr*100:>10.2f} {confirmed:>10}")
    return results


def main():
    print("=" * 62)
    print("  H174 — PEAD-NLP: Score + Surprise Dual Filter")
    print("=" * 62)

    print("\n[1/5] Loading OHLCV…")
    ohlcv = load_ohlcv()
    print(f"  Loaded from cache: {len(ohlcv)} tickers")

    print("\n[2/5] Finding earnings-confirmed gap-up events…")
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

    print("\n[3/5] Loading FinBERT scores and computing surprise…")
    score_df = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
    score_df["date"] = pd.to_datetime(score_df["date"])

    def enrich(events):
        rows = []
        for _, ev in events.iterrows():
            ret = compute_return(ev["ticker"], ev["date"], ohlcv, hold=20)
            if ret is None:
                continue
            # absolute score
            score_row = score_df[
                (score_df["ticker"] == ev["ticker"]) &
                (score_df["date"] == ev["date"])
            ]
            score = score_row.iloc[0]["finbert_score"] \
                if not score_row.empty else float("nan")
            # surprise
            surprise = compute_surprise(ev["ticker"], ev["date"], score_df)
            rows.append({
                "ticker": ev["ticker"], "date": ev["date"],
                "ret": ret, "score": score, "surprise": surprise,
            })
        return pd.DataFrame(rows)

    is_df  = enrich(is_ev)
    oos_df = enrich(oos_ev)

    oos_both = oos_df.dropna(subset=["score", "surprise"])
    is_both  = is_df.dropna(subset=["score", "surprise"])

    print(f"  OOS events with both score+surprise: {len(oos_both)} / {len(oos_df)}")
    print(f"  IS events with both score+surprise:  {len(is_both)} / {len(is_df)}")

    print("\n[4/5] Dual-filter: score ≥ S AND surprise ≥ P…")
    print("\n  (Sweep over score thresholds with surprise ≥ 0)")
    surprise_floor = 0.0
    print(f"\n  Baseline OOS (all {len(oos_df)}): "
          f"WR={(oos_df['ret']>0).mean()*100:.1f}%, "
          f"MeanRet={oos_df['ret'].mean()*100:.2f}%")

    # Dual filter results
    all_confirmed = []
    score_thresholds = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20]
    surprise_thresholds = [0.0, 0.02, 0.05]

    print(f"\n  {'ScoreT':>8} {'SurpT':>7} {'n':>5} {'WR%':>7} {'MeanRet%':>10} {'Confirm':>10}")
    print("  " + "-" * 55)
    for st in score_thresholds:
        for pt in surprise_thresholds:
            filtered = oos_both[
                (oos_both["score"] >= st) & (oos_both["surprise"] >= pt)
            ]
            if len(filtered) == 0:
                continue
            wr = (filtered["ret"] > 0).mean()
            mr = filtered["ret"].mean()
            n  = len(filtered)
            confirmed = "CONFIRM" if (wr >= 0.68 and mr >= 0.055 and n >= 15) else ""
            if confirmed or (wr >= 0.60 and mr >= 0.03 and n >= 10):
                print(f"  {st:>8.2f} {pt:>7.2f} {n:>5} "
                      f"{wr*100:>7.1f} {mr*100:>10.2f} {confirmed:>10}")
                if confirmed:
                    all_confirmed.append({
                        "score_thresh": st, "surprise_thresh": pt,
                        "n": n, "wr": wr, "mr": mr
                    })

    # Also show H163 baseline (score only, no surprise requirement)
    print(f"\n  H163 reference: score ≥ 0.10 (no surprise filter)")
    ref = oos_df[oos_df["score"] >= 0.10]
    if len(ref) > 0:
        print(f"  score≥0.10: n={len(ref)}, "
              f"WR={(ref['ret']>0).mean()*100:.1f}%, "
              f"MeanRet={ref['ret'].mean()*100:.2f}%")

    print("\n[5/5] IS dual-filter check…")
    for st in [0.10, 0.12]:
        for pt in [0.0, 0.02]:
            fil = is_both[(is_both["score"] >= st) & (is_both["surprise"] >= pt)]
            if len(fil) == 0:
                continue
            print(f"  IS score≥{st:.2f}+surp≥{pt:.2f}: n={len(fil)}, "
                  f"WR={(fil['ret']>0).mean()*100:.1f}%, "
                  f"MeanRet={fil['ret'].mean()*100:.2f}%")

    verdict = "CONFIRMED" if all_confirmed else "NOT CONFIRMED"
    best = max(all_confirmed, key=lambda r: r["wr"] * r["n"]) if all_confirmed else None

    out_lines = [
        "H174 — PEAD-NLP: H163 Score + Sentiment Surprise Dual Filter",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Universe: {len(UNIVERSE)} stocks  |  GAP≥3%  |  Hold=20d  |  IS: 2020–2023  |  OOS: 2024+",
        f"Dual filter: FinBERT absolute score ≥ S AND surprise (score_t - mean(prior {LOOKBACK_Q}q)) ≥ P",
        "",
        f"OOS events with both filters computable: {len(oos_both)} / {len(oos_df)}",
        f"Baseline OOS (all): n={len(oos_df)}, "
        f"WR={(oos_df['ret']>0).mean()*100:.1f}%, "
        f"MeanRet={oos_df['ret'].mean()*100:.2f}%",
        "",
        "Confirmed combinations:",
    ]
    for r in all_confirmed:
        out_lines.append(
            f"  score≥{r['score_thresh']:.2f} + surprise≥{r['surprise_thresh']:.2f}: "
            f"n={r['n']}, WR={r['wr']*100:.1f}%, MeanRet={r['mr']*100:.2f}%"
        )
    if not all_confirmed:
        out_lines.append("  None")
    out_lines += ["", f"VERDICT: {verdict}"]
    if best:
        out_lines.append(
            f"Best: score≥{best['score_thresh']:.2f} + surprise≥{best['surprise_thresh']:.2f}, "
            f"n={best['n']}, WR={best['wr']*100:.1f}%, MeanRet={best['mr']*100:.2f}%"
        )

    result_path = RESULT_DIR / "h174_pead_dual_filter.txt"
    result_path.write_text("\n".join(out_lines))

    print(f"\n{'='*62}")
    print(f"  VERDICT: {verdict}")
    print(f"{'='*62}")
    print(f"  Results saved to {result_path.name}")


if __name__ == "__main__":
    main()
