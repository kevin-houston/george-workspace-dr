#!/usr/bin/env python3
"""
H517 — OPT LLM Sentiment Scoring Upgrade for H174 PEAD Pipeline
===================================================================
Source: arXiv:2412.19245 (Kirtac & Germano) — "Sentiment Trading with Large
Language Models"

The paper benchmarks FinBERT, BERT, OPT, and the Loughran-McDonald
dictionary on 965,375 US financial news articles (2010-2023) for next-day
return prediction. OPT scored highest on both classification accuracy
(74.4% vs FinBERT's 72.2%) and long-short strategy Sharpe (3.05 vs
FinBERT's 2.07) on that general-news benchmark.

Universe: same H163/H174 30-stock 8-K event set.
IS/OOS: same split as H174.
Gate: OOS WR > 81.8% AND MeanRet > 6.89% AND n >= 20 events (H174's gate).

Variants:
  A: OPT sentiment score alone, threshold re-calibrated to OPT's score distribution
  B: OPT score replacing FinBERT in H174's dual filter (OPT >= threshold AND surprise >= 0.02)
  C: FinBERT x OPT ensemble (product or average of both scores)
  D: OPT score >= threshold AND FinDPO score >= 0.50 (once H481/FinDPO is built)

CAVEAT: the paper's dataset is general financial news, not EDGAR 8-K press
releases — H163/H174's domain is narrower, so the reported 3.05 Sharpe is a
reason to test, not a result to cite directly. Transfer needs validation on
the same OOS event set used by H174.

STATUS: PROPOSED — not yet runnable. Before running:
  1. Verify the exact OPT model name/checkpoint on HuggingFace (hallusquatting
     defense per standing instructions) before any pip/model install.
  2. Run `pip-audit` after any new model package install.
  3. If both H481 (FinDPO) and H517 (OPT) get built, run a single 3-way
     bake-off (FinBERT baseline vs FinDPO vs OPT) rather than two isolated
     backtests.
"""

raise NotImplementedError(
    "H517 is a staged proposal — OPT sentiment scoring pipeline not yet built. "
    "See wiki/trading/backtesting/hypothesis-log.md#H517 for design details."
)
