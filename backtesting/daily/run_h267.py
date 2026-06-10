#!/usr/bin/env python3
"""
run_h267.py — H267: PEAD-specific FinBERT fine-tune

Tests whether fine-tuning ProsusAI/finbert on PEAD outcome labels
(gap >= 3% AND 20-trading-day return > 0) improves OOS win rate above
the H174 baseline of 81.8% (threshold=0.18, n=22).

Gate: OOS WR > 85%, n >= 20.

Usage:
    source /workspace/agent/venv/bin/activate
    python3 backtesting/daily/run_h267.py
"""

import json
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────

WORKSPACE    = Path(__file__).resolve().parent.parent.parent
CACHE_DIR    = WORKSPACE / "backtesting" / "cache"
RESULTS_DIR  = WORKSPACE / "backtesting" / "results"

SCORE_CACHE      = CACHE_DIR / "h163_finbert_scores.parquet"
TEXT_CACHE       = CACHE_DIR / "h267_8k_texts.json"
LLM_LABEL_CACHE  = CACHE_DIR / "h267_llm_labels.json"
DATASET_PATH     = CACHE_DIR / "h267_labeled_dataset.parquet"
MODEL_DIR        = CACHE_DIR / "h267_finbert_finetuned"
RESULTS_PATH     = RESULTS_DIR / "h267_results.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

H174_BASELINE_WR = 0.818
H174_BASELINE_N  = 22
OOS_CUTOFF       = pd.Timestamp("2023-01-01")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Load events from score cache
# ─────────────────────────────────────────────────────────────────────────────

def load_events() -> pd.DataFrame:
    log("Step 1: Loading events from h163 score cache...")
    df = pd.read_parquet(SCORE_CACHE)
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["ticker", "date"]).sort_values("date").reset_index(drop=True)
    log(f"  Loaded {len(df)} events, date range: {df['date'].min().date()} to {df['date'].max().date()}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Compute PEAD outcomes via yfinance
# ─────────────────────────────────────────────────────────────────────────────

def compute_pead_outcomes(events: pd.DataFrame) -> pd.DataFrame:
    log("Step 2: Computing PEAD outcomes (gap >= 3% AND 20-trading-day return > 0)...")

    outcomes = []
    for ticker in events["ticker"].unique():
        ticker_events = events[events["ticker"] == ticker].sort_values("date")
        min_date = ticker_events["date"].min() - timedelta(days=30)
        max_date = ticker_events["date"].max() + timedelta(days=90)

        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(
                start=min_date.strftime("%Y-%m-%d"),
                end=max_date.strftime("%Y-%m-%d"),
                auto_adjust=True
            )
            if not hist.empty:
                hist.index = pd.to_datetime(hist.index).tz_localize(None)
        except Exception as e:
            log(f"  {ticker}: yfinance fetch error -- {e}")
            hist = pd.DataFrame()

        for _, row in ticker_events.iterrows():
            event_date = row["date"]

            if hist.empty:
                outcomes.append({"ticker": ticker, "date": event_date, "label": np.nan,
                                  "gap": np.nan, "ret20": np.nan})
                continue

            future = hist.loc[hist.index >= event_date]
            if future.empty:
                outcomes.append({"ticker": ticker, "date": event_date, "label": np.nan,
                                  "gap": np.nan, "ret20": np.nan})
                continue

            event_row_idx = future.index[0]
            past = hist.loc[hist.index < event_row_idx]
            if past.empty:
                outcomes.append({"ticker": ticker, "date": event_date, "label": np.nan,
                                  "gap": np.nan, "ret20": np.nan})
                continue

            prev_close  = past["Close"].iloc[-1]
            event_open  = hist.loc[event_row_idx, "Open"]
            gap         = float(event_open / prev_close - 1)

            future_from_event = hist.loc[hist.index >= event_row_idx]
            if len(future_from_event) < 20:
                outcomes.append({"ticker": ticker, "date": event_date, "label": np.nan,
                                  "gap": gap, "ret20": np.nan})
                continue

            close_20d = float(future_from_event["Close"].iloc[19])
            ret20     = float(close_20d / event_open - 1)
            label     = 1 if (gap >= 0.03 and ret20 > 0) else 0

            outcomes.append({"ticker": ticker, "date": event_date, "label": label,
                              "gap": gap, "ret20": ret20})

        log(f"  {ticker}: {len(ticker_events)} events")

    df_out = pd.DataFrame(outcomes)
    valid = df_out["label"].notna()
    pos   = int((df_out.loc[valid, "label"] == 1).sum())
    neg   = int((df_out.loc[valid, "label"] == 0).sum())
    log(f"  Valid outcomes: {int(valid.sum())}  (label=1: {pos}, label=0: {neg})")
    return df_out


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Fetch 8-K Exhibit 99.1 texts from EDGAR
# ─────────────────────────────────────────────────────────────────────────────

def fetch_8k_exhibit_text(ticker: str, event_date) -> str | None:
    """
    Fetch Exhibit 99.1 (earnings press release) from the 8-K closest to event_date.
    This is the actual earnings text, not the 8-K cover page.
    Falls back to the full 8-K markdown if no Exhibit 99.1 found.
    """
    try:
        import edgar
        edgar.set_identity("george-nanoclaw george@nanoclaw.com")
        from edgar import Company

        if isinstance(event_date, pd.Timestamp):
            event_date = event_date.date()

        company      = Company(ticker)
        filings      = company.get_filings(form="8-K")
        window_start = event_date - timedelta(days=10)
        window_end   = event_date + timedelta(days=10)

        for filing in filings[:30]:
            fd = filing.filing_date
            if hasattr(fd, 'date'):
                fd = fd.date()
            elif isinstance(fd, str):
                try:
                    fd = datetime.strptime(fd[:10], "%Y-%m-%d").date()
                except Exception:
                    continue

            if not (window_start <= fd <= window_end):
                continue

            # Try Exhibit 99.1 first (earnings press release)
            try:
                attachments = filing.attachments
                for att in attachments:
                    desc_upper = str(getattr(att, 'description', '') or '').upper()
                    doc_upper  = str(getattr(att, 'document', '') or '').upper()
                    if 'EX-99.1' in desc_upper or ('EX991' in doc_upper or 'EX-99' in desc_upper):
                        try:
                            text = att.text()
                            if text and len(text) > 500:
                                # Truncate to 12000 chars, enough for key financial info
                                return text[:12000]
                        except Exception:
                            pass
                        try:
                            text = att.markdown()
                            if text and len(text) > 500:
                                return text[:12000]
                        except Exception:
                            pass
            except Exception:
                pass

            # Fallback: full 8-K markdown
            try:
                text = filing.markdown()
                if text and len(text) > 500:
                    return text[:8000]
            except Exception:
                pass

    except Exception:
        pass
    return None


def fetch_all_8k_texts(events: pd.DataFrame) -> dict:
    """Fetch 8-K Exhibit 99.1 texts for all events, using cache."""
    texts = {}
    if TEXT_CACHE.exists():
        with open(TEXT_CACHE) as f:
            texts = json.load(f)
        log(f"  Loaded {len(texts)} cached entries from {TEXT_CACHE.name}")

    needs_fetch = []
    for _, row in events.iterrows():
        key = f"{row['ticker']}_{row['date'].strftime('%Y-%m-%d')}"
        if key not in texts:
            needs_fetch.append((row['ticker'], row['date'], key))

    if not needs_fetch:
        log(f"  All {len(texts)} 8-K entries already cached.")
        return texts

    log(f"  Fetching Exhibit 99.1 texts for {len(needs_fetch)} events...")
    fetched = 0
    failed  = 0

    for i, (ticker, event_date, key) in enumerate(needs_fetch):
        if (i + 1) % 10 == 0:
            log(f"  Progress: {i+1}/{len(needs_fetch)} fetched={fetched} failed={failed}")
        try:
            text = fetch_8k_exhibit_text(ticker, event_date)
            if text:
                texts[key] = text
                fetched += 1
            else:
                texts[key] = None
                failed += 1
        except Exception as e:
            texts[key] = None
            failed += 1

        if (i + 1) % 20 == 0:
            with open(TEXT_CACHE, "w") as f:
                json.dump(texts, f)
            log(f"  Cache checkpoint saved ({len(texts)} entries)")

        time.sleep(0.3)

    with open(TEXT_CACHE, "w") as f:
        json.dump(texts, f)

    total_with_text = sum(1 for v in texts.values() if v)
    log(f"  Fetch complete: {total_with_text} texts retrieved, {failed} missing/failed")
    return texts


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: LLM labeling with GPT-4o-mini
# ─────────────────────────────────────────────────────────────────────────────

def llm_label_events(texts: dict, events: pd.DataFrame) -> dict:
    """Call GPT-4o-mini to rate each earnings press release. Returns dict key->score (0-3)."""
    llm_labels = {}
    if LLM_LABEL_CACHE.exists():
        with open(LLM_LABEL_CACHE) as f:
            llm_labels = json.load(f)
        log(f"  Loaded {len(llm_labels)} cached LLM labels")

    needs_label = []
    for _, row in events.iterrows():
        key  = f"{row['ticker']}_{row['date'].strftime('%Y-%m-%d')}"
        text = texts.get(key)
        if text and key not in llm_labels:
            needs_label.append((key, text))

    if not needs_label:
        log(f"  All available texts already labeled ({len(llm_labels)} labels).")
        return llm_labels

    log(f"  Calling GPT-4o-mini for {len(needs_label)} events...")

    from openai import OpenAI
    client = OpenAI()

    PROMPT_TEMPLATE = (
        "Rate this earnings press release on a scale of 0-3 for likely positive "
        "post-earnings drift:\n"
        "0 = negative/disappointing results\n"
        "1 = mixed/in-line with expectations\n"
        "2 = modestly positive beat on revenue or EPS\n"
        "3 = strong beat with raised guidance\n"
        "Respond with ONLY a single integer (0, 1, 2, or 3).\n\n"
        "Press release:\n{text}"
    )

    success = 0
    errors  = 0

    for i, (key, text) in enumerate(needs_label):
        if (i + 1) % 10 == 0:
            log(f"  LLM progress: {i+1}/{len(needs_label)} success={success} errors={errors}")

        # Pass first 2000 chars but skip the boilerplate header
        # Look for financial content start
        text_lower = text.lower()
        start_idx  = 0
        for kw in ['announces', 'reports', 'fourth quarter', 'third quarter',
                   'second quarter', 'first quarter', 'q4', 'q3', 'q2', 'q1',
                   'net sales', 'revenue', 'earnings per share']:
            idx = text_lower.find(kw)
            if idx > 0 and idx < 5000:
                start_idx = max(0, idx - 100)
                break

        prompt_text = text[start_idx:start_idx + 2500]

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(text=prompt_text)}],
                max_tokens=5,
                temperature=0,
            )
            raw = response.choices[0].message.content.strip()
            # Parse: first digit in response
            digits = [c for c in raw if c.isdigit()]
            if digits:
                score = int(digits[0])
                if 0 <= score <= 3:
                    llm_labels[key] = score
                    success += 1
                else:
                    log(f"  Out-of-range score for {key}: {score}")
                    errors += 1
            else:
                log(f"  No digit in LLM response for {key}: '{raw}'")
                errors += 1
        except Exception as e:
            log(f"  LLM error for {key}: {e}")
            errors += 1
            time.sleep(2)

        if (i + 1) % 20 == 0:
            with open(LLM_LABEL_CACHE, "w") as f:
                json.dump(llm_labels, f)

        time.sleep(0.2)

    with open(LLM_LABEL_CACHE, "w") as f:
        json.dump(llm_labels, f)

    log(f"  LLM labeling done: {success} labeled, {errors} errors. Total: {len(llm_labels)}")
    return llm_labels


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Build labeled dataset
# ─────────────────────────────────────────────────────────────────────────────

def build_dataset(events: pd.DataFrame, outcomes_df: pd.DataFrame,
                  texts: dict, llm_labels: dict) -> pd.DataFrame:
    log("Step 5: Building labeled dataset...")

    rows = []
    for _, ev in events.iterrows():
        ticker = ev["ticker"]
        date   = ev["date"]
        key    = f"{ticker}_{date.strftime('%Y-%m-%d')}"

        match = outcomes_df[(outcomes_df["ticker"] == ticker) & (outcomes_df["date"] == date)]
        if match.empty or pd.isna(match.iloc[0]["label"]):
            continue

        outcome_label = int(match.iloc[0]["label"])
        gap   = float(match.iloc[0]["gap"])   if not pd.isna(match.iloc[0].get("gap", np.nan))   else None
        ret20 = float(match.iloc[0]["ret20"]) if not pd.isna(match.iloc[0].get("ret20", np.nan)) else None

        text      = texts.get(key)
        llm_score = llm_labels.get(key)

        rows.append({
            "ticker":         ticker,
            "date":           date,
            "finbert_score":  ev["finbert_score"],
            "outcome_label":  outcome_label,
            "gap":            gap,
            "ret20":          ret20,
            "has_text":       bool(text),
            "llm_score":      llm_score,
            "text_key":       key,
        })

    df = pd.DataFrame(rows)
    df.to_parquet(DATASET_PATH, index=False)

    log(f"  Dataset: {len(df)} events with outcomes")
    log(f"  With 8-K text: {int(df['has_text'].sum())}")
    log(f"  With LLM score: {int(df['llm_score'].notna().sum())}")
    log(f"  Label distribution: 1={int((df['outcome_label']==1).sum())} "
        f"0={int((df['outcome_label']==0).sum())}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Fine-tune FinBERT
# ─────────────────────────────────────────────────────────────────────────────

def finetune_finbert(dataset: pd.DataFrame, texts: dict) -> str | None:
    """Fine-tune ProsusAI/finbert on IS data (date < 2023-01-01)."""
    log("Step 6: Fine-tuning FinBERT on IS data (date < 2023-01-01)...")

    import torch
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                               TrainingArguments, Trainer)
    from datasets import Dataset as HFDataset

    is_df = dataset[(dataset["date"] < OOS_CUTOFF) & (dataset["has_text"] == True)].copy()
    log(f"  IS events with text: {len(is_df)}")

    if len(is_df) < 5:
        log(f"  Aborting fine-tune: only {len(is_df)} IS training examples (need >= 5).")
        return None

    train_texts, train_labels = [], []
    for _, row in is_df.iterrows():
        key  = row["text_key"]
        text = texts.get(key)
        if text:
            # Skip boilerplate; extract earnings content
            text_lower = text.lower()
            start_idx  = 0
            for kw in ['announces', 'reports', 'fourth quarter', 'third quarter',
                       'second quarter', 'first quarter', 'net sales', 'revenue']:
                idx = text_lower.find(kw)
                if idx > 0 and idx < 5000:
                    start_idx = max(0, idx - 100)
                    break
            train_texts.append(text[start_idx:start_idx + 512])
            train_labels.append(int(row["outcome_label"]))

    log(f"  Training samples: {len(train_texts)}")
    log(f"  Label dist: 1={sum(train_labels)} 0={len(train_labels)-sum(train_labels)}")

    val_df = dataset[(dataset["date"] >= OOS_CUTOFF) & (dataset["has_text"] == True)].copy()
    val_texts, val_labels = [], []
    for _, row in val_df.iterrows():
        key  = row["text_key"]
        text = texts.get(key)
        if text:
            text_lower = text.lower()
            start_idx  = 0
            for kw in ['announces', 'reports', 'fourth quarter', 'third quarter',
                       'second quarter', 'first quarter', 'net sales', 'revenue']:
                idx = text_lower.find(kw)
                if idx > 0 and idx < 5000:
                    start_idx = max(0, idx - 100)
                    break
            val_texts.append(text[start_idx:start_idx + 512])
            val_labels.append(int(row["outcome_label"]))

    log(f"  Validation samples (OOS with text): {len(val_texts)}")

    log("  Loading ProsusAI/finbert tokenizer + model...")
    tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    model     = AutoModelForSequenceClassification.from_pretrained(
        "ProsusAI/finbert", num_labels=2, ignore_mismatched_sizes=True
    )

    def make_dataset(texts_list, labels_list):
        enc = tokenizer(texts_list, truncation=True, padding=True,
                        max_length=512, return_tensors=None)
        enc["labels"] = labels_list
        return HFDataset.from_dict(enc)

    train_ds = make_dataset(train_texts, train_labels)
    eval_ds  = make_dataset(val_texts, val_labels) if val_texts else None

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(MODEL_DIR),
        num_train_epochs=3,
        per_device_train_batch_size=4,
        per_device_eval_batch_size=4,
        learning_rate=2e-5,
        weight_decay=0.01,
        eval_strategy="epoch" if eval_ds else "no",
        save_strategy="epoch",
        load_best_model_at_end=(eval_ds is not None),
        logging_steps=5,
        use_cpu=True,
        report_to="none",
        save_total_limit=1,
        dataloader_num_workers=0,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
    )

    log("  Starting training (CPU, 3 epochs, batch=4)...")
    t0 = time.time()
    trainer.train()
    elapsed = time.time() - t0
    log(f"  Training complete in {elapsed:.0f}s ({elapsed/60:.1f} min).")

    model.save_pretrained(str(MODEL_DIR))
    tokenizer.save_pretrained(str(MODEL_DIR))
    log(f"  Model saved to {MODEL_DIR}")
    return str(MODEL_DIR)


# ─────────────────────────────────────────────────────────────────────────────
# Step 7: OOS evaluation
# ─────────────────────────────────────────────────────────────────────────────

def oos_evaluation(dataset: pd.DataFrame, texts: dict,
                   model_dir: str | None) -> dict:
    log("Step 7: OOS evaluation...")

    oos_df = dataset[dataset["date"] >= OOS_CUTOFF].copy()
    log(f"  OOS events: {len(oos_df)}")

    results = {}

    # Fine-tuned model scoring
    if model_dir and Path(model_dir).exists():
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        log(f"  Loading fine-tuned model from {model_dir}...")
        ft_tokenizer = AutoTokenizer.from_pretrained(model_dir)
        ft_model     = AutoModelForSequenceClassification.from_pretrained(model_dir)
        ft_model.eval()

        ft_scores, ft_labels = [], []

        for _, row in oos_df.iterrows():
            key  = row["text_key"]
            text = texts.get(key)
            if not text:
                continue

            text_lower = text.lower()
            start_idx  = 0
            for kw in ['announces', 'reports', 'fourth quarter', 'third quarter',
                       'second quarter', 'first quarter', 'net sales', 'revenue']:
                idx = text_lower.find(kw)
                if idx > 0 and idx < 5000:
                    start_idx = max(0, idx - 100)
                    break

            inputs = ft_tokenizer(
                text[start_idx:start_idx + 512],
                return_tensors="pt", truncation=True, max_length=512
            )
            with torch.no_grad():
                logits = ft_model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0].numpy()
            ft_scores.append(float(probs[1]))  # prob of label=1
            ft_labels.append(int(row["outcome_label"]))

        log(f"  Fine-tuned model scored {len(ft_scores)} OOS events")

        if ft_scores:
            thresholds = [0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7]
            sweep = []
            for t in thresholds:
                preds = [1 if s >= t else 0 for s in ft_scores]
                n_pos = sum(preds)
                if n_pos > 0:
                    wins = sum(1 for p, l in zip(preds, ft_labels) if p == 1 and l == 1)
                    sweep.append({"threshold": t, "n": n_pos, "wr": round(wins / n_pos, 4)})
                else:
                    sweep.append({"threshold": t, "n": 0, "wr": 0.0})

            d05 = next(x for x in sweep if x["threshold"] == 0.5)
            results["finetuned_model"] = {
                "n_scored":        len(ft_scores),
                "threshold_0_5":   {"n": d05["n"], "wr": d05["wr"]},
                "threshold_sweep": sweep,
            }
            log(f"  Fine-tuned OOS @ t=0.5: n={d05['n']}, WR={d05['wr']:.1%}")

    else:
        log("  Fine-tuned model not available -- skipping model scoring.")

    # LLM score OOS evaluation
    llm_oos = oos_df[oos_df["llm_score"].notna()].copy()
    if not llm_oos.empty:
        log(f"  LLM score distribution: {dict(llm_oos['llm_score'].value_counts().sort_index())}")
        for t in [1, 2, 3]:
            preds = (llm_oos["llm_score"] >= t).astype(int).tolist()
            lbls  = llm_oos["outcome_label"].tolist()
            n_pos = sum(preds)
            wins  = sum(1 for p, l in zip(preds, lbls) if p == 1 and l == 1)
            wr    = (wins / n_pos) if n_pos > 0 else 0.0
            log(f"  LLM score OOS @ t>={t}: n={n_pos}, WR={wr:.1%}")

        # Primary LLM threshold: >=2
        preds_2 = (llm_oos["llm_score"] >= 2).astype(int).tolist()
        lbls_2  = llm_oos["outcome_label"].tolist()
        n_pos_2 = sum(preds_2)
        wins_2  = sum(1 for p, l in zip(preds_2, lbls_2) if p == 1 and l == 1)
        wr_2    = (wins_2 / n_pos_2) if n_pos_2 > 0 else 0.0

        results["llm_scores_oos"] = {
            "n_oos_scored": len(llm_oos),
            "score_dist":   {int(k): int(v) for k, v in llm_oos["llm_score"].value_counts().sort_index().items()},
            "threshold_2":  {"n": n_pos_2, "wr": round(wr_2, 4)},
        }

    # Original FinBERT OOS (reference baseline)
    orig_oos = oos_df[oos_df["finbert_score"].notna()].copy()
    if not orig_oos.empty:
        fb_preds = (orig_oos["finbert_score"] >= 0.18).astype(int).tolist()
        fb_lbls  = orig_oos["outcome_label"].tolist()
        n_fb_pos = sum(fb_preds)
        wins_fb  = sum(1 for p, l in zip(fb_preds, fb_lbls) if p == 1 and l == 1)
        wr_fb    = (wins_fb / n_fb_pos) if n_fb_pos > 0 else 0.0

        results["original_finbert_oos"] = {
            "n_oos":         len(orig_oos),
            "threshold_018": {"n": n_fb_pos, "wr": round(wr_fb, 4)},
        }
        log(f"  Original FinBERT OOS @ t=0.18: n={n_fb_pos}, WR={wr_fb:.1%}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run():
    log("=" * 65)
    log("H267: PEAD-specific FinBERT fine-tuning")
    log("=" * 65)

    t_start = time.time()

    # Step 1
    events = load_events()

    # Step 2
    if DATASET_PATH.exists():
        existing = pd.read_parquet(DATASET_PATH)
        if len(existing) >= len(events) * 0.7:
            log("Step 2: Reusing cached dataset outcomes...")
            outcomes_df = existing[["ticker","date","outcome_label","gap","ret20"]].copy()
            outcomes_df = outcomes_df.rename(columns={"outcome_label": "label"})
        else:
            outcomes_df = compute_pead_outcomes(events)
    else:
        outcomes_df = compute_pead_outcomes(events)

    # Step 3
    log("Step 3: Fetching 8-K Exhibit 99.1 texts from EDGAR...")
    texts = fetch_all_8k_texts(events)
    total_fetched = sum(1 for v in texts.values() if v)
    fetch_rate    = total_fetched / max(len(events), 1)
    log(f"  EDGAR fetch rate: {total_fetched}/{len(events)} = {fetch_rate:.1%}")
    edgar_failed  = (fetch_rate < 0.5)
    if edgar_failed:
        log("  WARNING: EDGAR fetch rate below 50%.")

    # Step 4
    log("Step 4: LLM labeling with GPT-4o-mini...")
    llm_labels = llm_label_events(texts, events)

    # Step 5
    if DATASET_PATH.exists() and len(pd.read_parquet(DATASET_PATH)) >= len(events) * 0.7:
        log("Step 5: Loading existing labeled dataset and refreshing scores...")
        dataset = pd.read_parquet(DATASET_PATH)
        dataset["has_text"]  = dataset["text_key"].apply(lambda k: bool(texts.get(k)))
        dataset["llm_score"] = dataset["text_key"].apply(lambda k: llm_labels.get(k))
        dataset.to_parquet(DATASET_PATH, index=False)
    else:
        dataset = build_dataset(events, outcomes_df, texts, llm_labels)

    log(f"  Final dataset: {len(dataset)} rows, "
        f"IS={int((dataset['date'] < OOS_CUTOFF).sum())}, "
        f"OOS={int((dataset['date'] >= OOS_CUTOFF).sum())}")

    # Step 6
    if (MODEL_DIR / "config.json").exists():
        log("Step 6: Fine-tuned model already exists -- skipping training.")
        model_dir = str(MODEL_DIR)
    else:
        is_with_text = dataset[(dataset["date"] < OOS_CUTOFF) & (dataset["has_text"] == True)]
        if len(is_with_text) < 5:
            log(f"Step 6: Only {len(is_with_text)} IS texts available -- skipping fine-tune.")
            log("  Relying on LLM scores and original FinBERT for OOS evaluation.")
            model_dir = None
        else:
            model_dir = finetune_finbert(dataset, texts)

    # Step 7
    oos_results = oos_evaluation(dataset, texts, model_dir)

    # Primary result
    primary_method  = None
    primary_n       = 0
    primary_wr      = 0.0

    if "finetuned_model" in oos_results:
        d = oos_results["finetuned_model"]["threshold_0_5"]
        primary_method = "finetuned_finbert_t0.5"
        primary_n, primary_wr = d["n"], d["wr"]
    elif "llm_scores_oos" in oos_results:
        d = oos_results["llm_scores_oos"]["threshold_2"]
        primary_method = "llm_t2"
        primary_n, primary_wr = d["n"], d["wr"]
    elif "original_finbert_oos" in oos_results:
        d = oos_results["original_finbert_oos"]["threshold_018"]
        primary_method = "original_finbert_t0.18"
        primary_n, primary_wr = d["n"], d["wr"]

    gate_wr   = 0.85
    gate_n    = 20
    passes_wr = (primary_wr > gate_wr)
    passes_n  = (primary_n >= gate_n)
    passed    = passes_wr and passes_n

    ds_stats = {
        "total_events":      len(events),
        "events_with_label": int(dataset["outcome_label"].notna().sum()),
        "label_1":           int((dataset["outcome_label"] == 1).sum()),
        "label_0":           int((dataset["outcome_label"] == 0).sum()),
        "events_with_text":  int(dataset["has_text"].sum()),
        "events_with_llm":   int(dataset["llm_score"].notna().sum()),
        "is_count":          int((dataset["date"] < OOS_CUTOFF).sum()),
        "oos_count":         int((dataset["date"] >= OOS_CUTOFF).sum()),
    }

    final_results = {
        "hypothesis":         "H267",
        "description":        "PEAD-specific FinBERT fine-tune",
        "run_date":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset":            ds_stats,
        "edgar_fetch_rate":   round(fetch_rate, 4),
        "edgar_failed":       edgar_failed,
        "model_trained":      model_dir is not None,
        "model_dir":          str(model_dir) if model_dir else None,
        "oos_results":        oos_results,
        "primary_method":     primary_method,
        "primary_n":          primary_n,
        "primary_wr":         primary_wr,
        "baseline": {"method": "H174_dual_filter", "wr": H174_BASELINE_WR, "n": H174_BASELINE_N},
        "gate": {
            "wr_threshold": gate_wr,
            "n_threshold":  gate_n,
            "passes_wr":    passes_wr,
            "passes_n":     passes_n,
            "passed":       passed,
        },
        "elapsed_seconds": round(time.time() - t_start, 1),
    }

    RESULTS_PATH.write_text(json.dumps(final_results, indent=2, default=str))
    log(f"\nResults saved to {RESULTS_PATH}")

    # Summary
    log("")
    log("=" * 65)
    log("H267 SUMMARY")
    log("=" * 65)
    log(f"  Dataset size:            {len(events)} events")
    log(f"  Events with outcome:     {ds_stats['events_with_label']}")
    log(f"  Label=1 (PEAD hit):      {ds_stats['label_1']}")
    log(f"  Label=0 (miss):          {ds_stats['label_0']}")
    log(f"  Events with 8-K text:    {ds_stats['events_with_text']} "
        f"(EDGAR rate {fetch_rate:.1%})")
    log(f"  Events with LLM label:   {ds_stats['events_with_llm']}")
    log(f"  IS / OOS split:          {ds_stats['is_count']} / {ds_stats['oos_count']} "
        f"(cutoff 2023-01-01)")
    log("")
    log(f"  Model trained:           {'YES' if model_dir else 'NO (insufficient data)'}")
    log("")
    log(f"  H174 baseline:           WR={H174_BASELINE_WR:.1%}, n={H174_BASELINE_N}")
    log(f"  H267 primary ({primary_method or 'N/A'}):  WR={primary_wr:.1%}, n={primary_n}")
    log("")
    log(f"  Gate:  WR > {gate_wr:.0%} AND n >= {gate_n}")
    log(f"  Passes WR gate:          {'YES' if passes_wr else 'NO'}")
    log(f"  Passes n gate:           {'YES' if passes_n else 'NO'}")
    log(f"  RESULT:                  {'CONFIRMED' if passed else 'NOT CONFIRMED'}")
    log("")
    if "finetuned_model" in oos_results and "threshold_sweep" in oos_results["finetuned_model"]:
        log("  Fine-tuned model threshold sweep:")
        for r in oos_results["finetuned_model"]["threshold_sweep"]:
            marker = " <--" if r["threshold"] == 0.5 else ""
            log(f"    t={r['threshold']:.2f}: n={r['n']}, WR={r['wr']:.1%}{marker}")
    log("=" * 65)
    log(f"Total elapsed: {(time.time()-t_start)/60:.1f} min")


if __name__ == "__main__":
    run()
