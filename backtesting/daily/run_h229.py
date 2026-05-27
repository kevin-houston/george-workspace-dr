"""
H229 — Speaker-Role Weighted FinBERT on Earnings Call Transcripts
==================================================================
arXiv:2604.13260 (April 2026): 6.5M sentences from 16.4K S&P 500 earnings
calls (2015-2025), FinBERT with speaker-role segmentation.
Monthly L/S alpha: 2.03%, OOS Spearman IC: 0.142.

H168 failed due to low transcript OOS coverage (26.5%). H229 addresses this
by using broader data sourcing (EDGAR 8-K exhibit 99.1 + scraped transcripts).

Signal construction:
  1. CEO/CFO prepared remarks sentiment (bull = positive bias)
  2. Analyst Q&A probe sentiment (negative probes = management under pressure)
  3. Signal = CEO_score - 0.5 × analyst_negative_score
  Long top-6 by composite score, monthly rebalance.

Universe: 30 large-cap (same as H163/H174)
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS WR > 65% AND MeanRet > 3% (must beat H174: WR=81.8%, MR=6.9%)

PREREQUISITE: transcript sourcing must achieve >60% OOS coverage
  Option A: HuggingFace 'lamini/earnings-calls-qa-finance' (check for newer version)
  Option B: SEC EDGAR 8-K exhibit 99.1 text extraction (EdgarTools)
  Option C: Motley Fool/Seeking Alpha scraping (ToS check required)
"""

# SCAFFOLD — implement after verifying transcript coverage
# Step 1: Audit transcript coverage for 30-stock universe, 2021-2026
# Step 2: If coverage < 60%, halt and note as BLOCKED
# Step 3: Extract CEO vs analyst speaker segments
# Step 4: Apply ProsusAI/finbert to each segment type
# Step 5: Build composite score, backtest monthly
