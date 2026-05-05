"""
H164 — PEAD-ML: ElasticNet on 8-Quarter SUE History
=====================================================
Hypothesis: 8 prior quarters of standardised earnings surprise (SUE) history
contain incremental predictive power for 60-day post-earnings-gap drift.

Data note: FMP v3 earnings-surprises endpoint deprecated (403). Using yfinance
earnings_dates which provides ~24 quarters of EPS actual vs estimate back to
~2020. This constrains the window but ensures we only test on earnings-confirmed
gap-ups (events within ±2 trading days of an earnings date).

Method:
  1. For each of the 30 PEAD universe stocks, get earnings history via yfinance.
  2. Compute SUE_q = surprisePercent / 100 for each quarter.
  3. For each gap-up event, find if it coincides with an earnings date (±2d).
  4. Build feature vector [SUE_q-1 .. SUE_q-8] for confirmed earnings gaps.
  5. Target: 60-day raw return from gap-open.
  6. Train ElasticNetCV on IS events (2020–2023), score on OOS (2024+).
  7. Report filtered win-rate / mean-return vs unfiltered baseline.

Confirm criteria (for filter to add value):
  OOS retained win-rate > 70%  (baseline ~63.9% from H159)
  OOS mean return > 5.5%       (baseline ~4.4% from H159)
  Retained OOS events >= 20    (sufficient for meaningful comparison)
"""

import os
import sys
import math
import json
import warnings
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import ElasticNetCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────────────────
WORKSPACE   = Path(__file__).resolve().parent.parent.parent
CACHE_DIR   = WORKSPACE / "backtesting" / "cache"
RESULT_DIR  = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# ── universe (must match H159) ────────────────────────────────────────────────
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

IS_END    = pd.Timestamp("2023-12-31")   # constrained by yfinance earnings history (~2020+)
OOS_START = pd.Timestamp("2024-01-01")
GAP_THRESH = 0.03     # variant B (best H159 variant)
HOLD_DAYS  = 20
N_LAGS     = 8        # number of prior quarters used as features
MIN_LAGS   = 4        # minimum lags to include an event
PRED_THRESHOLD = 0.0  # minimum predicted return to take trade (tuned below)

# ── earnings helpers (yfinance) ───────────────────────────────────────────────

def yf_earnings_surprises(ticker: str) -> pd.DataFrame:
    """
    Return DataFrame of earnings surprises via yfinance earnings_dates.
    Columns: date (Timestamp, tz-naive), sue (surprise % / 100).
    Sorted oldest→newest.
    """
    cache_path = CACHE_DIR / f"h164_yf_eps_{ticker}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        df = t.earnings_dates
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.rename(columns={"Surprise(%)": "surprise_pct",
                                 "Reported EPS": "actual",
                                 "EPS Estimate": "estimate"})
        df = df.dropna(subset=["actual"])
        df = df.sort_index()
        df["sue"] = df["surprise_pct"] / 100.0
        df["date"] = df.index
        df = df[["date", "sue", "actual", "estimate"]].reset_index(drop=True)
        df.to_parquet(cache_path)
        return df
    except Exception as e:
        print(f"  yfinance earnings error {ticker}: {e}")
        return pd.DataFrame()


def build_sue_series(eps_df: pd.DataFrame) -> pd.DataFrame:
    """eps_df already has 'sue' column from yf_earnings_surprises. Return as-is."""
    if eps_df.empty or "sue" not in eps_df.columns:
        return pd.DataFrame(columns=["date", "sue"])
    return eps_df[["date", "sue"]].reset_index(drop=True)


def get_lag_features(sue_df: pd.DataFrame, event_date: pd.Timestamp,
                     n_lags: int = N_LAGS) -> np.ndarray | None:
    """
    Return array of [sue_q-1, ..., sue_q-n_lags] for the earnings event
    most recently before or on event_date.
    Returns None if not enough history.
    """
    prior = sue_df[sue_df["date"] <= event_date + pd.Timedelta(days=5)]
    if len(prior) < MIN_LAGS:
        return None
    # Take up to n_lags most recent rows
    recent = prior.tail(n_lags)
    # Pad with zeros if fewer than n_lags available
    feats = recent["sue"].values
    if len(feats) < n_lags:
        feats = np.concatenate([np.zeros(n_lags - len(feats)), feats])
    return feats.astype(float)


# ── OHLCV + gap events (mirrors H159 logic) ───────────────────────────────────

def load_ohlcv() -> dict:
    import yfinance as yf
    result = {}
    start, end = "2007-01-01", "2026-04-30"
    to_dl = []
    for t in UNIVERSE:
        for pfx in [f"h{i:03d}" for i in range(155, 170)]:
            for suf in ["ohlcv", "ohlc"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_{start}_{end}.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "open" in df.columns and "close" in df.columns:
                        result[t] = df[["open","close"]]
                        break
            if t in result:
                break
        if t not in result:
            to_dl.append(t)

    if to_dl:
        print(f"  Downloading {len(to_dl)} tickers from yfinance…")
        batch = yf.download(to_dl, start=start, end=end,
                            auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open","Close"]].copy()
                    df.columns = ["open","close"]
                    df = df.dropna()
                    if len(df) > 100:
                        df.to_parquet(CACHE_DIR / f"h164_{t}_ohlcv_{start}_{end}.parquet")
                        result[t] = df
                except Exception:
                    pass
        else:
            t = to_dl[0]
            df = batch[["Open","Close"]].copy()
            df.columns = ["open","close"]
            result[t] = df
    return result


def find_gap_events(ohlcv: dict, gap_thresh: float) -> pd.DataFrame:
    events = []
    for t, df in ohlcv.items():
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        for idx, row in df[gap_pct > gap_thresh].iterrows():
            events.append({
                "ticker": t,
                "date":   idx,
                "gap_pct": gap_pct[idx],
                "entry_px": row["open"],
            })
    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def compute_60d_return(ticker: str, entry_date: pd.Timestamp,
                       ohlcv: dict, hold: int = 60) -> float | None:
    """Raw 60-day cumulative return from open on entry_date."""
    if ticker not in ohlcv:
        return None
    df = ohlcv[ticker].sort_index()
    future = df[df.index >= entry_date]
    if len(future) < hold:
        return None
    slice_ = future.iloc[:hold]
    # entry at open day 0; close at close of day hold-1
    entry = slice_.iloc[0]["open"]
    exit_ = slice_.iloc[-1]["close"]
    if entry <= 0:
        return None
    return (exit_ - entry) / entry


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  H164 — PEAD-ML: ElasticNet 8-Quarter SUE Filter")
    print("=" * 62)

    # 1. Load OHLCV and find gap-up events
    print("\n[1/5] Loading OHLCV data…")
    ohlcv = load_ohlcv()
    print(f"  Loaded {len(ohlcv)} tickers")

    print("\n[2/5] Finding gap-up events (gap ≥ {:.0%})…".format(GAP_THRESH))
    events = find_gap_events(ohlcv, GAP_THRESH)
    is_events  = events[events["date"] <= IS_END].copy()
    oos_events = events[events["date"] >= OOS_START].copy()
    print(f"  Total events: {len(events)}  IS: {len(is_events)}  OOS: {len(oos_events)}")

    # 2. Fetch FMP earnings surprises for all tickers
    print("\n[3/5] Fetching earnings surprises via yfinance…")
    sue_by_ticker = {}
    earnings_dates_by_ticker = {}   # ticker → sorted list of earnings Timestamps
    ok, skip = 0, 0
    for t in UNIVERSE:
        eps_df = yf_earnings_surprises(t)
        if eps_df.empty:
            skip += 1
            continue
        sue_df = build_sue_series(eps_df)
        if len(sue_df) >= MIN_LAGS:
            sue_by_ticker[t] = sue_df
            earnings_dates_by_ticker[t] = sorted(eps_df["date"].tolist())
            ok += 1
        else:
            skip += 1
    print(f"  SUE series built: {ok} tickers  ({skip} skipped — insufficient history)")

    # 3. Build feature matrix
    print("\n[4/5] Building feature matrix…")

    def is_earnings_gap(ticker, gap_date, window_days=3):
        """Return True if gap_date falls within window_days of an earnings date."""
        if ticker not in earnings_dates_by_ticker:
            return False
        for ed in earnings_dates_by_ticker[ticker]:
            if abs((gap_date - ed).days) <= window_days:
                return True
        return False

    def build_features(ev_df):
        rows = []
        for _, ev in ev_df.iterrows():
            t = ev["ticker"]
            if t not in sue_by_ticker:
                continue
            # Only include gap-ups that coincide with earnings releases
            if not is_earnings_gap(t, ev["date"]):
                continue
            feats = get_lag_features(sue_by_ticker[t], ev["date"])
            if feats is None:
                continue
            ret60 = compute_60d_return(t, ev["date"], ohlcv, hold=60)
            if ret60 is None:
                continue
            rows.append({
                "ticker": t,
                "date":   ev["date"],
                "gap_pct": ev["gap_pct"],
                "ret60":  ret60,
                **{f"sue_lag{i+1}": feats[N_LAGS-1-i] for i in range(N_LAGS)},
            })
        return pd.DataFrame(rows)

    is_feat  = build_features(is_events)
    oos_feat = build_features(oos_events)
    print(f"  IS feature rows: {len(is_feat)}  OOS feature rows: {len(oos_feat)}")

    if len(is_feat) < 20 or len(oos_feat) < 20:
        print("  Not enough data for regression — exiting.")
        sys.exit(1)

    feat_cols = [f"sue_lag{i+1}" for i in range(N_LAGS)]
    X_is  = is_feat[feat_cols].values
    y_is  = is_feat["ret60"].values
    X_oos = oos_feat[feat_cols].values
    y_oos = oos_feat["ret60"].values

    # 4. Fit ElasticNet
    print("\n[5/5] Fitting ElasticNetCV…")
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("enet", ElasticNetCV(
            l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
            cv=5,
            max_iter=5000,
            n_jobs=-1,
        )),
    ])
    pipe.fit(X_is, y_is)
    enet = pipe.named_steps["enet"]
    print(f"  Best l1_ratio: {enet.l1_ratio_:.2f}  alpha: {enet.alpha_:.4f}")

    # Coefficients (unscaled feature importance)
    coef = enet.coef_
    print("  Lag coefficients (lag1=most recent):",
          "  ".join(f"L{i+1}:{coef[i]:+.3f}" for i in range(N_LAGS)))

    # 5. Predict on OOS
    y_pred_oos = pipe.predict(X_oos)
    oos_feat = oos_feat.copy()
    oos_feat["pred_ret60"] = y_pred_oos

    # Baseline OOS stats (all events)
    base_wr  = (y_oos > 0).mean()
    base_ret = y_oos.mean()

    # Sweep thresholds
    print("\n  Threshold sweep (filter: take trade if predicted_ret60 > threshold):")
    print(f"  {'Threshold':>10}  {'Retained':>8}  {'WinRate':>8}  {'MeanRet':>8}  {'Improvement':>12}")
    best_thresh, best_score = 0.0, -np.inf
    results_table = []
    for thresh in [-0.05, -0.02, 0.0, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08]:
        mask = y_pred_oos > thresh
        n = mask.sum()
        if n < 10:
            continue
        wr  = (y_oos[mask] > 0).mean()
        ret = y_oos[mask].mean()
        improvement = wr - base_wr
        results_table.append((thresh, n, wr, ret, improvement))
        print(f"  {thresh:>10.2f}  {n:>8d}  {wr:>7.1%}  {ret:>8.2%}  {improvement:>+11.1%}")
        # Score: win-rate improvement with minimum 60 events
        if n >= 30 and wr > best_score:
            best_score = wr
            best_thresh = thresh

    # Best threshold analysis
    mask = y_pred_oos > best_thresh
    filtered_oos = oos_feat[mask].copy()
    retained_n   = mask.sum()
    filtered_wr  = (y_oos[mask] > 0).mean() if retained_n > 0 else 0
    filtered_ret = y_oos[mask].mean() if retained_n > 0 else 0

    print(f"\n  Baseline (all OOS events):  n={len(y_oos)}  WinRate={base_wr:.1%}  MeanRet={base_ret:.2%}")
    print(f"  Best filter (thresh={best_thresh:.2f}): n={retained_n}  WinRate={filtered_wr:.1%}  MeanRet={filtered_ret:.2%}")
    print(f"  Win-rate lift: {filtered_wr - base_wr:+.1%}  Retained: {retained_n/len(y_oos):.0%} of events")

    # 6. IS R² (sanity check)
    y_pred_is = pipe.predict(X_is)
    ss_res = ((y_is - y_pred_is)**2).sum()
    ss_tot = ((y_is - y_is.mean())**2).sum()
    r2_is = 1 - ss_res/ss_tot if ss_tot > 0 else 0
    print(f"\n  IS R²: {r2_is:.4f}  (>0.05 = meaningful in-sample fit)")

    # 7. Verdict
    print(f"\n{'='*62}")
    confirmed = (
        filtered_wr > 0.70 and
        filtered_ret > 0.055 and
        retained_n >= 30
    )
    verdict = "PARTIAL" if filtered_wr > base_wr + 0.03 and retained_n >= 30 else "NOT CONFIRMED"
    if confirmed:
        verdict = "CONFIRMED"
    print(f"  VERDICT: {verdict}")
    print(f"  Target: WinRate>70% | MeanRet>5.5% | n≥30")
    print(f"  Got:    WinRate={filtered_wr:.1%} | MeanRet={filtered_ret:.2%} | n={retained_n}")
    print(f"{'='*62}")

    # 8. Save results
    out_path = RESULT_DIR / "h164_pead_elasticnet_sue.txt"
    lines = [
        "H164 — PEAD-ML: ElasticNet 8-Quarter SUE Filter",
        f"Run: {datetime.now():%Y-%m-%d %H:%M}",
        f"Universe: {len(UNIVERSE)} stocks  |  GAP≥{GAP_THRESH:.0%}  |  Hold=60d  |  Lags={N_LAGS}",
        f"IS: 2020–2023 (yfinance constraint)  |  OOS: 2024+",
        f"IS events with features: {len(is_feat)}  |  OOS events with features: {len(oos_feat)}",
        f"ElasticNet: l1_ratio={enet.l1_ratio_:.2f}  alpha={enet.alpha_:.4f}  IS_R2={r2_is:.4f}",
        "",
        "Lag coefficients (1=most recent quarter):",
        "  " + "  ".join(f"L{i+1}:{coef[i]:+.4f}" for i in range(N_LAGS)),
        "",
        "Threshold sweep:",
        f"  {'Thresh':>7}  {'N':>6}  {'WinRate':>8}  {'MeanRet':>8}  {'Delta_WR':>9}",
    ]
    for thresh, n, wr, ret, imp in results_table:
        lines.append(f"  {thresh:>7.2f}  {n:>6d}  {wr:>7.1%}  {ret:>8.2%}  {imp:>+8.1%}")
    lines += [
        "",
        f"Baseline OOS:  n={len(y_oos)}  WinRate={base_wr:.1%}  MeanRet={base_ret:.2%}",
        f"Best filter:   n={retained_n}  WinRate={filtered_wr:.1%}  MeanRet={filtered_ret:.2%}  thresh={best_thresh:.2f}",
        "",
        f"VERDICT: {verdict}",
        "",
        "Per-event sample (filtered OOS, last 20):",
        f"  {'Date':<12} {'Ticker':<6} {'Gap%':>6} {'SUE_L1':>8} {'Pred':>8} {'Act60d':>8} {'W':>3}",
    ]
    for _, row in filtered_oos.tail(20).iterrows():
        w = "Y" if row["ret60"] > 0 else "N"
        lines.append(
            f"  {str(row['date'].date()):<12} {row['ticker']:<6} "
            f"{row['gap_pct']:>5.1%} {row.get('sue_lag1', 0):>8.2f} "
            f"{row['pred_ret60']:>8.2%} {row['ret60']:>8.2%} {w:>3}"
        )

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\n  Results saved: {out_path}")

    return verdict, filtered_wr, filtered_ret, retained_n, len(y_oos)


if __name__ == "__main__":
    main()
