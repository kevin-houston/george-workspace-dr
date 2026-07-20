#!/usr/bin/env python3
"""
H421: 10-K Item 1A Risk-Factor Sentiment as PEAD Candidate Pre-Filter
======================================================================
Source: Choi, S.S. (Jul 2026). 'How Much of a 10-K Matters? Aggregation-Dependent
  Value of Full-Text versus Risk-Factor Sentiment.' arXiv:2607.14174.

Key finding: The optimal 10-K text section depends on aggregation level.
  - Full 10-K text: better at SECTOR and PORTFOLIO level (broad diversification)
  - Item 1A (Risk Factors) text only: better at INDIVIDUAL FIRM level for both
    return AND volatility prediction (1,383 filings, 94 Nasdaq-100 tech firms, 2006-2023)
  - Loughran-McDonald dictionary FAILS: consistently negatively correlated with price
    at every aggregation level tested → supervised FinBERT is the right tool.

H421 design — annual 10-K Item 1A pre-filter for PEAD universe:
  The H174 pipeline uses 8-K press releases scored at earnings announcements.
  H421 tests whether adding the PRIOR annual 10-K Item 1A sentiment as an
  additional gate removes low-quality candidates BEFORE the earnings event:

  Gate logic:
    1. At each earnings announcement, check last annual 10-K filed in prior 365d
    2. Extract Item 1A text using EdgarTools (sec-edgar-downloader)
    3. Score with FinBERT → 10K_sentiment
    4. Only proceed with H174 8-K scoring if 10K_sentiment >= threshold
       (positive annual risk disclosure reduces downside surprise probability)

  This is a PRE-FILTER, not a score blend. It reduces false positives by checking
  annual firm-level risk posture before the earnings announcement.

Variants:
  A: 10K_sentiment >= 0.05 pre-filter (lenient)
  B: 10K_sentiment >= 0.10 pre-filter (moderate)
  C: No 10K sentiment — use 10K_vol_percentile < 50 (low textual volatility)
  D: 10K length-adjusted sentiment (control for document length)

Data pipeline:
  - Download 10-K via EdgarTools: doc.get_filing('10-K').get_latest()
  - Extract Item 1A via regex: r'ITEM\\s*1A[^\\n]*RISK FACTORS(.+?)ITEM\\s*1B'
  - Score chunks with ProsusAI/finbert (same model as H174)
  - Cache 10-K scores in backtesting/data/10k_item1a_cache.json

Confirmation gate:
  OOS WR >= 0.818 (same as H174 baseline) AND n >= 15 OOS trades
  (filter must not shrink universe below statistical significance)

IS: H174 historical universe  OOS: 2021-2026
Note: 10-K filings arrive annually — sentiment is stale for most of the year.
  This creates a known staleness artifact that the backtest must account for.
  Update 10K_sentiment only when a new 10-K is filed, hold constant otherwise.

Related: H174 CONFIRMED (dual filter FinBERT >= 0.18 + EPS surprise >= 0.02, WR=81.8%)
         H421 (this stub — annual 10-K Item 1A pre-filter)
"""

import json
import re
from pathlib import Path

HYPOTHESIS = "H421"
GATE_WR = 0.818
GATE_N = 15
IS_START = "2013-01-01"
OOS_START = "2021-01-01"
CACHE_PATH = Path("backtesting/data/10k_item1a_cache.json")

ITEM_1A_PATTERN = re.compile(
    r'ITEM\s*1A[^\n]*RISK\s*FACTORS(.+?)ITEM\s*1B',
    re.IGNORECASE | re.DOTALL
)

VARIANTS = {
    "A": {"threshold": 0.05, "description": "lenient 10K sentiment pre-filter"},
    "B": {"threshold": 0.10, "description": "moderate 10K sentiment pre-filter"},
    "C": {"threshold": None, "use_vol": True, "description": "10K textual volatility < 50th pct"},
    "D": {"threshold": 0.10, "length_adjusted": True, "description": "length-adjusted sentiment"},
}


def extract_item_1a(text: str) -> str:
    """Extract Item 1A Risk Factors text from 10-K filing."""
    match = ITEM_1A_PATTERN.search(text)
    if match:
        return match.group(1).strip()[:50000]  # cap at 50k chars
    return ""


def load_10k_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


if __name__ == "__main__":
    print("H421 is a design stub — 10-K Item 1A PEAD pre-filter.")
    print(f"Gate: OOS WR >= {GATE_WR:.1%} AND n >= {GATE_N} trades")
    print("Source: arXiv:2607.14174 Choi 2026 — Item 1A best at firm-level prediction")
    print("Key insight: full 10-K beats Item 1A at portfolio level, reverses at firm level")
    print("Data dependency: EdgarTools for 10-K download + FinBERT for scoring")
    print(f"Cache path: {CACHE_PATH}")
    print("\nVariants:")
    for var, cfg in VARIANTS.items():
        print(f"  {var}: {cfg['description']}")
