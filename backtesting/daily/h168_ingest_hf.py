#!/usr/bin/env python3
"""
H168 transcript ingest from HuggingFace: kurry/sp500_earnings_transcripts

Replaces AlphaVantage 25/day bottleneck with a free bulk dataset (33k transcripts,
685 companies, 2005-2025). Converts to H168's expected JSON cache format.

Usage:
    python3 h168_ingest_hf.py [--dry-run]

Writes to: backtesting/cache/h168_transcripts/{TICKER}_{YEAR}Q{Q}.json
Each file: [{"speaker_title": str, "speech": str}, ...]  (H168 native format)

Run once — takes ~30 min to download dataset + convert. Replaces all future
AlphaVantage download passes.
"""

import json
import sys
from pathlib import Path

WORKSPACE       = Path(__file__).resolve().parent.parent.parent
TRANSCRIPT_DIR  = WORKSPACE / "backtesting" / "cache" / "h168_transcripts"
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

TICKER_SET = set(TICKERS)
DRY_RUN    = "--dry-run" in sys.argv


def quarter_label(row) -> str:
    """Convert year + quarter int to H168 cache key, e.g. '2023Q2'."""
    year    = row.get("year")
    quarter = row.get("quarter")
    if year and quarter:
        return f"{year}Q{quarter}"
    # fallback: derive from date field
    if row.get("date"):
        import pandas as pd
        ts = pd.Timestamp(row["date"])
        q  = (ts.month - 1) // 3 + 1
        return f"{ts.year}Q{q}"
    return None


def convert_structured_content(structured_content) -> list[dict]:
    """
    kurry dataset: structured_content = [{speaker, text}, ...]
    H168 format:   [{speaker_title, speech}, ...]
    """
    if not structured_content:
        return []
    segments = []
    for item in structured_content:
        if isinstance(item, dict):
            speaker = item.get("speaker", "") or ""
            text    = item.get("text", "") or item.get("content", "") or ""
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            speaker = str(item[0])
            text    = str(item[1])
        else:
            continue
        if text.strip():
            segments.append({"speaker_title": speaker.strip(), "speech": text.strip()})
    return segments


def run():
    print("Loading kurry/sp500_earnings_transcripts from Hugging Face (streaming)…")
    print("This will take a few minutes to stream through 33k transcripts.")

    from datasets import load_dataset

    ds = load_dataset("kurry/sp500_earnings_transcripts", split="train", streaming=True)

    written  = 0
    skipped  = 0
    existing = 0

    for row in ds:
        symbol = (row.get("symbol") or "").upper()
        if symbol not in TICKER_SET:
            skipped += 1
            continue

        q_label = quarter_label(row)
        if not q_label:
            skipped += 1
            continue

        out_path = TRANSCRIPT_DIR / f"{symbol}_{q_label}.json"
        if out_path.exists():
            existing += 1
            continue

        if DRY_RUN:
            print(f"  [dry-run] would write {out_path.name}")
            written += 1
            continue

        segments = convert_structured_content(row.get("structured_content"))
        if not segments:
            # Fallback: split raw content into one segment
            content = row.get("content", "")
            if content:
                segments = [{"speaker_title": "unknown", "speech": content[:4000]}]

        if not segments:
            skipped += 1
            continue

        out_path.write_text(json.dumps(segments, ensure_ascii=False))
        written += 1

        if written % 50 == 0:
            print(f"  Written: {written}  Existing: {existing}  Skipped (other tickers): {skipped}")

    print(f"\nDone. Written={written}  Already existed={existing}  Skipped={skipped}")
    total = written + existing
    print(f"Total H168 transcript cache: {total} files")
    print(f"Cache path: {TRANSCRIPT_DIR}")


if __name__ == "__main__":
    run()
