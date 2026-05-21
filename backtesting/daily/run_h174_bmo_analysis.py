"""
H174-BMO — PEAD Dual Filter: WMT Isolated + BMO vs AMC Reporter Split
======================================================================
Uses cached FinBERT scores (h163_finbert_scores.parquet) and OHLCV.
H174 surprise = finbert_score_t - mean(prior 4q finbert scores).
OOS: 2024-01-01 onward.
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

OOS_START    = pd.Timestamp("2024-01-01")
GAP_THRESH   = 0.03
HOLD_DAYS    = 20
SCORE_THRESH = 0.18
SURP_THRESH  = 0.00
LOOKBACK_Q   = 4

# BMO = typically reports before 9:30 AM ET
# These are the tickers the overnight pipeline misses
BMO_TICKERS = {
    "WMT","COST","HD","LOW",
    "JPM","BAC","WFC",
    "JNJ","PFE","MRK",
    "XOM","CVX",
    "UNH",
}
AMC_TICKERS = set(UNIVERSE) - BMO_TICKERS


def load_ohlcv(ticker):
    start, end = "2019-01-01", "2026-04-30"
    for pfx in ["h163", "h159", "h198"]:
        for suf in ["ohlcv", "ohlc"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suf}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.index = pd.to_datetime(df.index)
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                return df
    # Download fallback
    try:
        df = yf.download(ticker, start=start, end="2026-05-20",
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception:
        return None


def load_earn_dates(ticker):
    """Return sorted list of earnings dates (Timestamps, tz-naive)."""
    p = CACHE_DIR / f"h163_earndates_{ticker}.parquet"
    if p.exists():
        df = pd.read_parquet(p)
        col = "date" if "date" in df.columns else df.columns[0]
        dates = pd.to_datetime(df[col]).dt.tz_localize(None)
        return sorted(dates)
    # yfinance fallback
    try:
        df = yf.Ticker(ticker).earnings_dates
        if df is None or df.empty:
            return []
        idx = pd.to_datetime(df.index).tz_localize(None)
        # Only confirmed (Reported EPS not NaN)
        if "Reported EPS" in df.columns:
            idx = idx[df["Reported EPS"].notna().values]
        return sorted(idx)
    except Exception:
        return []


def compute_surprise(ticker, event_date, fb_scores):
    """
    H174 surprise = finbert_score(event) - mean(prior LOOKBACK_Q scores).
    fb_scores: DataFrame with columns [ticker, date, finbert_score].
    """
    sub = fb_scores[fb_scores["ticker"] == ticker].copy()
    sub["date"] = pd.to_datetime(sub["date"]).dt.tz_localize(None)
    sub = sub.sort_values("date")

    ed = pd.Timestamp(event_date).normalize()
    # Find this event's score
    diffs = (sub["date"].dt.normalize() - ed).dt.days.abs()
    if diffs.min() > 5:
        return np.nan
    row_idx = diffs.idxmin()
    score_t = sub.loc[row_idx, "finbert_score"]
    if pd.isna(score_t):
        return np.nan

    # Prior events only
    prior = sub[sub["date"].dt.normalize() < ed - pd.Timedelta(days=5)]
    if len(prior) < 1:
        return np.nan
    prior_scores = prior["finbert_score"].dropna().tail(LOOKBACK_Q)
    if len(prior_scores) == 0:
        return np.nan
    return float(score_t - prior_scores.mean())


def build_events(fb_scores):
    """Build full event table: one row per earnings gap-up event."""
    rows = []
    for ticker in UNIVERSE:
        ohlcv = load_ohlcv(ticker)
        if ohlcv is None or ohlcv.empty:
            continue
        earn_dates = load_earn_dates(ticker)
        if not earn_dates:
            continue

        earn_set = set(pd.Timestamp(d).normalize() for d in earn_dates)

        # Normalize column names to lowercase
        ohlcv.columns = [c.lower() for c in ohlcv.columns]
        closes = ohlcv["close"]
        opens  = ohlcv.get("open", None)
        if opens is None:
            continue

        for i in range(1, len(ohlcv)):
            today     = ohlcv.index[i].normalize()
            prev_close = float(closes.iloc[i - 1])
            today_open = float(opens.iloc[i])

            if prev_close <= 0 or today_open <= 0:
                continue
            gap = (today_open - prev_close) / prev_close
            if gap < GAP_THRESH:
                continue

            # Within ±4 calendar days of an earnings date
            nearby = [d for d in earn_set
                      if abs((today - d).days) <= 4]
            if not nearby:
                continue

            # Forward 20-day return
            fi = i + HOLD_DAYS
            if fi >= len(ohlcv):
                continue
            entry = today_open
            exit_ = float(closes.iloc[fi])
            fwd_ret = (exit_ - entry) / entry

            nearest = min(nearby, key=lambda d: abs((today - d).days))

            # FinBERT score and surprise
            sub = fb_scores[(fb_scores["ticker"] == ticker)]
            sub_dates = pd.to_datetime(sub["date"]).dt.tz_localize(None).dt.normalize()
            diffs = (sub_dates - nearest).dt.days.abs()
            if len(diffs) == 0 or diffs.min() > 5:
                score = np.nan
            else:
                score = float(sub.loc[diffs.idxmin(), "finbert_score"])

            surprise = compute_surprise(ticker, nearest, fb_scores)

            rows.append({
                "ticker":        ticker,
                "date":          today,
                "earn_date":     nearest,
                "gap":           gap,
                "fwd_ret":       fwd_ret,
                "win":           fwd_ret > 0,
                "fb_score":      score,
                "fb_surprise":   surprise,
                "reporter_type": "BMO" if ticker in BMO_TICKERS else "AMC",
            })

    return pd.DataFrame(rows)


def print_group(label, df):
    n = len(df)
    if n == 0:
        print(f"  {label}: n=0")
        return
    wr  = df["win"].mean()
    ret = df["fwd_ret"].mean()
    print(f"  {label}: n={n}, WR={wr:.0%}, MeanRet={ret:.1%}")


def main():
    print("=" * 65)
    print("H174-BMO  PEAD Dual Filter — WMT + BMO vs AMC Analysis")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 65)

    # Load FinBERT scores
    fb_path = CACHE_DIR / "h163_finbert_scores.parquet"
    fb = pd.read_parquet(fb_path)
    fb["date"] = pd.to_datetime(fb["date"])
    if fb["date"].dt.tz is not None:
        fb["date"] = fb["date"].dt.tz_localize(None)
    print(f"FinBERT cache: {len(fb)} rows, tickers: {fb['ticker'].nunique()}")

    # Build events
    print("Building gap events (using cache)…")
    events = build_events(fb)
    print(f"Total gap-up events found: {len(events)}")

    if events.empty:
        print("No events found.")
        return

    oos = events[events["date"] >= OOS_START].copy()
    print(f"OOS events (≥{OOS_START.date()}): {len(oos)}")

    # ── SECTION 1: WMT ────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("SECTION 1 — WMT Earnings Gap Events")
    print("=" * 65)
    wmt = events[events["ticker"] == "WMT"].sort_values("date")
    print(f"WMT gap-up ≥3% events (all history): {len(wmt)}")
    if not wmt.empty:
        print()
        hdr = f"{'Date':<12} {'Gap':>6} {'Score':>7} {'Surp':>7} {'Fwd20d':>8}  Win"
        print(hdr)
        print("-" * 50)
        for _, r in wmt.iterrows():
            oos_tag = " ← OOS" if r["date"] >= OOS_START else ""
            sc = f"{r['fb_score']:.3f}" if not np.isnan(r["fb_score"]) else "  n/a"
            su = f"{r['fb_surprise']:.3f}" if not np.isnan(r["fb_surprise"]) else "  n/a"
            print(f"{str(r['date'].date()):<12} {r['gap']:>5.1%}  {sc:>7} {su:>7} "
                  f"{r['fwd_ret']:>7.1%}   {'✓' if r['win'] else '✗'}{oos_tag}")

    wmt_oos = wmt[wmt["date"] >= OOS_START]
    if len(wmt_oos) > 0:
        print()
        print_group("WMT OOS all gaps", wmt_oos)
        wmt_dual = wmt_oos.dropna(subset=["fb_score","fb_surprise"])
        wmt_dual = wmt_dual[(wmt_dual["fb_score"] >= SCORE_THRESH) &
                            (wmt_dual["fb_surprise"] >= SURP_THRESH)]
        print_group(f"WMT OOS dual-filter (score≥{SCORE_THRESH}, surp≥{SURP_THRESH})",
                    wmt_dual)

    # ── SECTION 2: BMO vs AMC ─────────────────────────────────────────────
    print()
    print("=" * 65)
    print("SECTION 2 — BMO vs AMC Reporter Split (OOS only)")
    print("=" * 65)
    print(f"BMO universe ({len(BMO_TICKERS)}): {sorted(BMO_TICKERS)}")
    print(f"AMC universe ({len(AMC_TICKERS)}): {sorted(AMC_TICKERS)}")
    print()

    oos_scored = oos.dropna(subset=["fb_score", "fb_surprise"])
    oos_dual   = oos_scored[(oos_scored["fb_score"] >= SCORE_THRESH) &
                            (oos_scored["fb_surprise"] >= SURP_THRESH)]

    for rtype in ["BMO", "AMC"]:
        grp     = oos[oos["reporter_type"] == rtype]
        grp_d   = oos_dual[oos_dual["reporter_type"] == rtype]
        print(f"--- {rtype} ---")
        print_group("All gap events", grp)
        print_group(f"Dual-filter (score≥{SCORE_THRESH}, surp≥{SURP_THRESH})", grp_d)
        if len(grp_d) > 0:
            print(f"  Events:")
            for _, r in grp_d.sort_values("date").iterrows():
                print(f"    {r['ticker']:<5} {str(r['date'].date())} "
                      f"gap={r['gap']:.1%} score={r['fb_score']:.3f} "
                      f"surp={r['fb_surprise']:.3f} ret={r['fwd_ret']:.1%} "
                      f"{'✓' if r['win'] else '✗'}")
        print()

    # ── SECTION 3: Full OOS summary ───────────────────────────────────────
    print("=" * 65)
    print("SECTION 3 — Full OOS Summary vs H174 Confirmed")
    print("=" * 65)
    print_group("Full OOS dual-filter (all reporters)", oos_dual)
    print("  H174 confirmed: n=26, WR=80.8%, MeanRet=6.22%")
    bmo_dual = oos_dual[oos_dual["reporter_type"] == "BMO"]
    if len(bmo_dual) > 0:
        print()
        print(f"  Pipeline gap: {len(bmo_dual)} BMO dual-filter events missed by live system")
        print(f"  At 5% equity per trade (~$500 on $10K): "
              f"~${int(500 * bmo_dual['fwd_ret'].mean())} expected value per missed trade")

    # Save
    out = RESULT_DIR / "h174_bmo_analysis.txt"
    lines = []
    lines.append(f"H174-BMO Analysis | Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"OOS dual-filter all: n={len(oos_dual)}, "
                 f"WR={oos_dual['win'].mean():.1%}, MeanRet={oos_dual['fwd_ret'].mean():.1%}")
    for rtype in ["BMO", "AMC"]:
        g = oos_dual[oos_dual["reporter_type"] == rtype]
        lines.append(f"{rtype}: n={len(g)}, "
                     f"WR={g['win'].mean():.1%}" if len(g)>0 else f"{rtype}: n=0")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nResults saved → {out}")


if __name__ == "__main__":
    main()
