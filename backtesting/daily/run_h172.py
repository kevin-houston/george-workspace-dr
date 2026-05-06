"""
H172 — PEAD-NLP: Fine-tuned FinBERT Embedding Classifier
=========================================================
Instead of using FinBERT's zero-shot sentiment score (positive_prob - negative_prob),
extract the CLS-token embedding from FinBERT's last hidden state (768-dim) and train
a logistic regression classifier on IS events to predict WIN (20-day return > 0).

Rationale: FinBERT's internal representation captures more textual nuance than the
3-class sentiment head. With ~100 IS training samples, a well-regularized logistic
regression on frozen embeddings is more robust than full fine-tuning.

Architecture:
  FinBERT (frozen) → CLS embedding (768-dim) → LogisticRegression (C=0.01, L2)

Comparison baseline: H163 zero-shot FinBERT
  - Baseline OOS: n=85, WR=57.6%, MeanRet=1.95%
  - Best threshold: WR≥68%, MeanRet≥5.5%, n≥15

Confirm if: filtered OOS WR ≥ 68%, MeanRet ≥ 5.5%, retained n ≥ 15
"""

import warnings
warnings.filterwarnings("ignore")

import re
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

EMBED_CACHE = CACHE_DIR / "h172_embeddings.parquet"

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
MAX_TOKENS = 512


# ── data helpers (shared with H163) ──────────────────────────────────────────

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
                            CACHE_DIR / f"h172_{t}_ohlcv_{start}_{end}.parquet")
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
                           "gap_pct": gap_pct[idx], "entry_px": row["open"]})
    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def get_8k_text(ticker, event_date, window_days=5):
    text_cache = CACHE_DIR / f"h163_8k_{ticker}_{event_date.date()}.txt"
    if text_cache.exists():
        raw = text_cache.read_text(errors="ignore")
        raw = re.sub(r"[│╭╮╰╯─││╭╮╰╯─]", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw if len(raw) > 100 else None
    return None


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


# ── FinBERT embedding extractor ───────────────────────────────────────────────

def load_finbert():
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    print("  Loading ProsusAI/finbert (embedding mode)…")
    tok = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    model = AutoModelForSequenceClassification.from_pretrained(
        "ProsusAI/finbert", output_hidden_states=True
    )
    model.eval()
    return tok, model


def get_cls_embedding(text, tokenizer, model):
    """Extract CLS token embedding from FinBERT's last hidden state."""
    import torch
    inputs = tokenizer(
        text, return_tensors="pt", truncation=True,
        max_length=MAX_TOKENS, padding=True
    )
    with torch.no_grad():
        outputs = model(**inputs)
    # last hidden state: [batch, seq_len, 768] → CLS token is [0, 0, :]
    cls = outputs.hidden_states[-1][0, 0, :].numpy()
    return cls


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  H172 — PEAD-NLP: FinBERT Embedding Classifier")
    print("=" * 62)

    # 1. Load OHLCV
    print("\n[1/6] Loading OHLCV…")
    ohlcv = load_ohlcv()
    print(f"  Loaded from cache: {len(ohlcv)} tickers")

    # 2. Find earnings-confirmed gap-up events
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
    print(f"  IS={len(is_ev)}  OOS={len(oos_ev)}  Total={len(conf_events)}")

    # 3. Load FinBERT
    print("\n[3/6] Loading FinBERT model…")
    tokenizer, finbert = load_finbert()

    # 4. Extract embeddings (cached)
    print("\n[4/6] Extracting CLS embeddings…")
    if EMBED_CACHE.exists():
        cached_df = pd.read_parquet(EMBED_CACHE)
        embed_dict = {}
        for _, row in cached_df.iterrows():
            key = (row["ticker"], str(row["date"])[:10])
            embed_dict[key] = np.array([row[f"e{i}"] for i in range(768)])
        print(f"  Loaded {len(embed_dict)} cached embeddings")
    else:
        embed_dict = {}

    all_events_list = pd.concat([is_ev, oos_ev]).copy()
    n_new = 0
    for _, ev in all_events_list.iterrows():
        key = (ev["ticker"], str(ev["date"].date()))
        if key in embed_dict:
            continue
        text = get_8k_text(ev["ticker"], ev["date"])
        if text is None:
            continue
        emb = get_cls_embedding(text, tokenizer, finbert)
        embed_dict[key] = emb
        n_new += 1
        if n_new % 10 == 0:
            print(f"    Embedded {n_new} new texts…")

    if n_new > 0:
        rows = []
        for (t, d), emb in embed_dict.items():
            row = {"ticker": t, "date": d}
            row.update({f"e{i}": v for i, v in enumerate(emb)})
            rows.append(row)
        pd.DataFrame(rows).to_parquet(EMBED_CACHE, index=False)
        print(f"  Saved {len(embed_dict)} embeddings to cache")
    else:
        print(f"  All {len(embed_dict)} embeddings from cache")

    # 5. Build labeled dataset
    print("\n[5/6] Building labeled dataset and training classifier…")

    def build_dataset(events):
        X, y, meta = [], [], []
        for _, ev in events.iterrows():
            key = (ev["ticker"], str(ev["date"].date()))
            if key not in embed_dict:
                continue
            ret = compute_return(ev["ticker"], ev["date"], ohlcv, hold=20)
            if ret is None:
                continue
            label = 1 if ret > 0 else 0
            X.append(embed_dict[key])
            y.append(label)
            meta.append({"ticker": ev["ticker"], "date": ev["date"],
                         "ret": ret, "label": label})
        return np.array(X), np.array(y), pd.DataFrame(meta)

    X_is, y_is, meta_is = build_dataset(is_ev)
    X_oos, y_oos, meta_oos = build_dataset(oos_ev)

    print(f"  IS: n={len(y_is)}, WR={y_is.mean()*100:.1f}%")
    print(f"  OOS: n={len(y_oos)}, WR={y_oos.mean()*100:.1f}%")

    if len(y_is) < 10:
        print("  ERROR: insufficient IS training data")
        return

    # Train logistic regression with strong L2 regularization
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    # C=0.01 → strong regularization to avoid overfit on ~100 samples
    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(C=0.01, max_iter=1000, random_state=42))
    ])
    clf.fit(X_is, y_is)

    is_acc = clf.score(X_is, y_is)
    oos_acc = clf.score(X_oos, y_oos) if len(y_oos) > 0 else float("nan")
    print(f"  IS accuracy: {is_acc*100:.1f}%  OOS accuracy: {oos_acc*100:.1f}%")

    # IS/OOS gap check — overfitting signal
    if is_acc - oos_acc > 0.20:
        print(f"  WARNING: large IS/OOS accuracy gap ({is_acc-oos_acc:.2f}) — possible overfit")

    # 6. Threshold sweep on OOS
    print("\n[6/6] OOS threshold sweep…")
    if len(y_oos) == 0:
        print("  No OOS events scored — cannot evaluate")
        return

    probs = clf.predict_proba(X_oos)[:, 1]  # P(WIN)
    meta_oos = meta_oos.copy()
    meta_oos["prob_win"] = probs

    results = []
    baseline_wr = y_oos.mean()
    baseline_ret = meta_oos["ret"].mean()

    print(f"\n  Baseline OOS: n={len(y_oos)}, WR={baseline_wr*100:.1f}%, "
          f"MeanRet={baseline_ret*100:.2f}%")
    print(f"\n  {'Thresh':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10} {'Confirm':>10}")
    print("  " + "-" * 50)

    for thresh in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        filtered = meta_oos[meta_oos["prob_win"] >= thresh]
        if len(filtered) == 0:
            continue
        wr = (filtered["ret"] > 0).mean()
        mr = filtered["ret"].mean()
        n = len(filtered)
        confirmed = "CONFIRM" if (wr >= 0.68 and mr >= 0.055 and n >= 15) else ""
        results.append({"thresh": thresh, "n": n, "wr": wr, "mr": mr,
                        "confirmed": bool(confirmed)})
        print(f"  {thresh:>8.2f} {n:>5} {wr*100:>7.1f} {mr*100:>10.2f} {confirmed:>10}")

    # Save results
    best = None
    confirmed_results = [r for r in results if r["confirmed"]]
    if confirmed_results:
        best = max(confirmed_results, key=lambda r: r["wr"] * r["n"])

    verdict = "CONFIRMED" if confirmed_results else "NOT CONFIRMED"

    out_lines = [
        "H172 — PEAD-NLP: FinBERT Embedding Classifier",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Universe: {len(UNIVERSE)} stocks  |  GAP≥3%  |  Hold=20d",
        f"IS: 2020–2023  |  OOS: 2024+",
        f"Method: Logistic regression on FinBERT CLS embeddings (768-dim, C=0.01)",
        "",
        f"Training set: IS n={len(y_is)}, WR={y_is.mean()*100:.1f}%",
        f"IS accuracy: {is_acc*100:.1f}%  |  OOS accuracy: {oos_acc*100:.1f}%",
        "",
        f"Baseline OOS:  n={len(y_oos)}  WR={baseline_wr*100:.1f}%  "
        f"MeanRet={baseline_ret*100:.2f}%",
        "",
        "Threshold sweep:",
    ]
    for r in results:
        out_lines.append(
            f"  thresh={r['thresh']:.2f}: n={r['n']}, "
            f"WR={r['wr']*100:.1f}%, MeanRet={r['mr']*100:.2f}%"
            + (" ← CONFIRM" if r["confirmed"] else "")
        )
    out_lines += [
        "",
        f"VERDICT: {verdict}",
    ]
    if best:
        out_lines.append(
            f"Best confirmed: thresh={best['thresh']:.2f}, "
            f"n={best['n']}, WR={best['wr']*100:.1f}%, "
            f"MeanRet={best['mr']*100:.2f}%"
        )

    result_text = "\n".join(out_lines)
    result_path = RESULT_DIR / "h172_pead_finbert_embed.txt"
    result_path.write_text(result_text)

    print(f"\n{'='*62}")
    print(f"  VERDICT: {verdict}")
    print(f"{'='*62}")
    print(f"  Results saved to {result_path.name}")


if __name__ == "__main__":
    main()
