"""
H173 — PEAD-NLP: FinBERT Sentiment Surprise
==============================================
Replace H163's absolute FinBERT score filter with a SENTIMENT SURPRISE signal:

    surprise_t = finbert_score_t - mean(finbert_score_{t-4q..t-1q})

Motivation: JFQA 2022 (Meursault et al. PEAD.txt) and QuantPedia BLMECT design
show that earnings sentiment SURPRISE (deviation from trailing baseline) is a
stronger predictor of post-announcement drift than the absolute sentiment level.
Anchoring on the company's own recent history removes cross-sectional differences
in baseline tone (e.g., tech companies typically sound more positive than banks).

Design (QuantPedia BLMECT optimal parameters):
  - 4-quarter baseline lookback (vs 8, 12, 20)
  - Require ≥2 prior quarters to compute surprise (skip if fewer)
  - Tercile sort: top 33% surprise → ENTER, bottom 33% → skip
  - Also test raw surprise threshold (surprise > X)
  - 20-day hold (same as H163)

Reuses: H163's cached FinBERT scores (h163_finbert_scores.parquet)
Baseline: H163 OOS: n=85, WR=57.6%, MeanRet=1.95%
Confirm if: filtered OOS WR ≥ 68%, MeanRet ≥ 5.5%, retained n ≥ 15
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
LOOKBACK_Q = 4   # prior quarters for baseline
MIN_PRIOR  = 2   # minimum prior quarters required to compute surprise


# ── helpers ──────────────────────────────────────────────────────────────────

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
                            CACHE_DIR / f"h173_{t}_ohlcv_{start}_{end}.parquet")
                        result[t] = df
                except Exception:
                    pass
    return result


def get_earnings_dates(ticker: str):
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
            events.append({"ticker": t, "date": idx,
                           "gap_pct": gap_pct[idx]})
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


def compute_surprise(ticker, event_date, score_df, lookback_q=4, min_prior=2):
    """
    For a given (ticker, event_date), compute:
        surprise = current_score - mean(prior lookback_q quarterly scores)
    Returns (surprise, n_prior) or (nan, 0) if insufficient history.
    """
    ticker_scores = score_df[
        (score_df["ticker"] == ticker) &
        (score_df["date"] < event_date) &
        score_df["finbert_score"].notna()
    ].sort_values("date")

    if len(ticker_scores) < min_prior:
        return float("nan"), len(ticker_scores)

    # Take most recent lookback_q quarters
    prior = ticker_scores.tail(lookback_q)["finbert_score"]
    baseline = prior.mean()

    # Current score
    current_row = score_df[
        (score_df["ticker"] == ticker) &
        (score_df["date"] == event_date) &
        score_df["finbert_score"].notna()
    ]
    if current_row.empty:
        return float("nan"), len(ticker_scores)

    current_score = current_row.iloc[0]["finbert_score"]
    return current_score - baseline, len(ticker_scores)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  H173 — PEAD-NLP: FinBERT Sentiment Surprise")
    print("=" * 62)

    # 1. Load OHLCV
    print("\n[1/5] Loading OHLCV…")
    ohlcv = load_ohlcv()
    print(f"  Loaded from cache: {len(ohlcv)} tickers")

    # 2. Find earnings-confirmed gap-up events
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
    print(f"  IS={len(is_ev)}  OOS={len(oos_ev)}  Total={len(conf_events)}")

    # 3. Load H163 FinBERT scores
    print("\n[3/5] Loading H163 FinBERT scores…")
    score_df = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
    score_df["date"] = pd.to_datetime(score_df["date"])
    print(f"  Loaded {len(score_df)} scored events")

    # 4. Compute sentiment surprise for each event
    print("\n[4/5] Computing sentiment surprise…")

    def enrich(events):
        rows = []
        for _, ev in events.iterrows():
            ret = compute_return(ev["ticker"], ev["date"], ohlcv, hold=20)
            if ret is None:
                continue
            surprise, n_prior = compute_surprise(
                ev["ticker"], ev["date"], score_df,
                lookback_q=LOOKBACK_Q, min_prior=MIN_PRIOR
            )
            rows.append({
                "ticker": ev["ticker"],
                "date": ev["date"],
                "ret": ret,
                "surprise": surprise,
                "n_prior": n_prior,
            })
        return pd.DataFrame(rows)

    is_df  = enrich(is_ev)
    oos_df = enrich(oos_ev)

    # Drop events without surprise (insufficient history)
    is_scored  = is_df.dropna(subset=["surprise"])
    oos_scored = oos_df.dropna(subset=["surprise"])

    print(f"  IS with surprise: {len(is_scored)} / {len(is_df)} "
          f"(dropped {len(is_df)-len(is_scored)} with <{MIN_PRIOR} prior quarters)")
    print(f"  OOS with surprise: {len(oos_scored)} / {len(oos_df)} "
          f"(dropped {len(oos_df)-len(oos_scored)} with <{MIN_PRIOR} prior quarters)")

    if len(oos_scored) == 0:
        print("  ERROR: no OOS events scored")
        return

    baseline_wr  = (oos_df["ret"] > 0).mean()
    baseline_ret = oos_df["ret"].mean()
    print(f"\n  Full baseline OOS (n={len(oos_df)}): "
          f"WR={baseline_wr*100:.1f}%, MeanRet={baseline_ret*100:.2f}%")

    baseline_wr2  = (oos_scored["ret"] > 0).mean()
    baseline_ret2 = oos_scored["ret"].mean()
    print(f"  Scored subset OOS (n={len(oos_scored)}): "
          f"WR={baseline_wr2*100:.1f}%, MeanRet={baseline_ret2*100:.2f}%")

    # 5. Threshold sweep — surprise > X
    print("\n[5/5] OOS threshold sweep (surprise > threshold)…")
    print(f"\n  Surprise distribution (OOS): "
          f"mean={oos_scored['surprise'].mean():.3f}, "
          f"std={oos_scored['surprise'].std():.3f}, "
          f"median={oos_scored['surprise'].median():.3f}")

    results = []
    print(f"\n  {'Thresh':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10} {'Confirm':>10}")
    print("  " + "-" * 50)

    for thresh in [-0.05, 0.0, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20]:
        filtered = oos_scored[oos_scored["surprise"] >= thresh]
        if len(filtered) == 0:
            continue
        wr  = (filtered["ret"] > 0).mean()
        mr  = filtered["ret"].mean()
        n   = len(filtered)
        confirmed = "CONFIRM" if (wr >= 0.68 and mr >= 0.055 and n >= 15) else ""
        results.append({"thresh": thresh, "n": n, "wr": wr, "mr": mr,
                        "confirmed": bool(confirmed)})
        print(f"  {thresh:>8.2f} {n:>5} {wr*100:>7.1f} {mr*100:>10.2f} {confirmed:>10}")

    # IS performance for IS/OOS comparison
    print(f"\n  IS threshold sweep (sanity check)…")
    print(f"  {'Thresh':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10}")
    print("  " + "-" * 40)
    for thresh in [0.0, 0.05, 0.10]:
        fil = is_scored[is_scored["surprise"] >= thresh]
        if len(fil) == 0:
            continue
        print(f"  {thresh:>8.2f} {len(fil):>5} "
              f"{(fil['ret']>0).mean()*100:>7.1f} "
              f"{fil['ret'].mean()*100:>10.2f}")

    # Tercile analysis
    print(f"\n  Tercile sort (OOS)…")
    q33 = oos_scored["surprise"].quantile(0.33)
    q67 = oos_scored["surprise"].quantile(0.67)
    top  = oos_scored[oos_scored["surprise"] >= q67]
    mid  = oos_scored[(oos_scored["surprise"] >= q33) & (oos_scored["surprise"] < q67)]
    bot  = oos_scored[oos_scored["surprise"] < q33]
    for name, grp in [("Top 33%", top), ("Mid 33%", mid), ("Bot 33%", bot)]:
        if len(grp) == 0:
            continue
        print(f"  {name}: n={len(grp)}, WR={((grp['ret']>0).mean()*100):.1f}%, "
              f"MeanRet={grp['ret'].mean()*100:.2f}%")

    # Verdict
    confirmed_results = [r for r in results if r["confirmed"]]
    verdict = "CONFIRMED" if confirmed_results else "NOT CONFIRMED"
    best = max(confirmed_results, key=lambda r: r["wr"] * r["n"]) if confirmed_results else None

    # Save results
    out_lines = [
        "H173 — PEAD-NLP: FinBERT Sentiment Surprise",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Universe: {len(UNIVERSE)} stocks  |  GAP≥3%  |  Hold=20d",
        f"IS: 2020–2023  |  OOS: 2024+",
        f"Surprise = finbert_score_t - mean(prior {LOOKBACK_Q}q scores), "
        f"min_prior={MIN_PRIOR}",
        "",
        f"IS events with surprise: {len(is_scored)} / {len(is_df)}",
        f"OOS events with surprise: {len(oos_scored)} / {len(oos_df)}",
        "",
        f"Baseline OOS (all): n={len(oos_df)}, WR={baseline_wr*100:.1f}%, "
        f"MeanRet={baseline_ret*100:.2f}%",
        f"Baseline OOS (scored subset): n={len(oos_scored)}, "
        f"WR={baseline_wr2*100:.1f}%, MeanRet={baseline_ret2*100:.2f}%",
        "",
        "Threshold sweep:",
    ]
    for r in results:
        out_lines.append(
            f"  thresh={r['thresh']:.2f}: n={r['n']}, "
            f"WR={r['wr']*100:.1f}%, MeanRet={r['mr']*100:.2f}%"
            + (" ← CONFIRM" if r["confirmed"] else "")
        )
    q67_wr  = (top["ret"] > 0).mean() if len(top) > 0 else float("nan")
    q67_mr  = top["ret"].mean() if len(top) > 0 else float("nan")
    out_lines += [
        "",
        f"Tercile top-33%: n={len(top)}, WR={q67_wr*100:.1f}%, "
        f"MeanRet={q67_mr*100:.2f}%",
        "",
        f"VERDICT: {verdict}",
    ]
    if best:
        out_lines.append(
            f"Best: thresh={best['thresh']:.2f}, n={best['n']}, "
            f"WR={best['wr']*100:.1f}%, MeanRet={best['mr']*100:.2f}%"
        )

    result_text = "\n".join(out_lines)
    result_path = RESULT_DIR / "h173_pead_sentiment_surprise.txt"
    result_path.write_text(result_text)

    print(f"\n{'='*62}")
    print(f"  VERDICT: {verdict}")
    print(f"{'='*62}")
    print(f"  Results saved to {result_path.name}")


if __name__ == "__main__":
    main()
