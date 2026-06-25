"""
H333 — FinBERT on M&A Announcement 8-K for Deal-Break Risk Scoring
===================================================================
Source: SSRN:4765067 (Halskov) — "Machine Learning Proxies for Merger Arbitrage
Expected Return Decomposition" (2025)

H310 (merger arb via MNA/MRGR ETFs) NOT CONFIRMED due to antitrust regime shift
artifact. The ETF approach cannot distinguish high-risk (likely-to-break) deals
from low-risk ones.

This hypothesis applies the H163/H174 FinBERT NLP approach to M&A announcement
8-K filings (Item 1.01 Business Combinations) to classify deal-break risk at
announcement. Negative language around regulatory uncertainty, financing conditions,
and material adverse change (MAC) clauses → lower score → skip deal.

Pipeline (analogous to H174 PEAD):
  1. Fetch 8-K Item 1.01 filings from EDGAR ($500M+ US targets, 2013-2026).
  2. Run ProsusAI/finbert on filing text (same model as H163/H174).
  3. Compute deal_score = mean positive sentiment of 8-K paragraphs.
  4. Gate: only enter spread trade when deal_score >= threshold.
  5. Hold until deal closes/breaks; apply TC = 10bps.

IS: 2013-2020 (threshold calibration)
OOS: 2021-2026 (single run)
Gate: OOS Sharpe > 0.65 (ETF approach benchmark) AND WF ratio > 0.80

Data:
  - EDGAR full-text search API ($EDGAR_KEY active): search 'business combination'
    'merger agreement' 'acquisition' in 8-K form type.
  - Price data: yfinance (target ticker from 8-K).
  - Deal consideration: proxy statement DEF14A (EDGAR).

Expected universe: ~20-40 qualifying OOS events (small — WR is primary metric).
"""
import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from pathlib import Path
from transformers import pipeline

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

IS_START  = pd.Timestamp("2013-01-01")
IS_END    = pd.Timestamp("2020-12-31")
OOS_START = pd.Timestamp("2021-01-01")
OOS_END   = pd.Timestamp("2026-04-30")

MIN_DEAL_SIZE_M = 500   # $500M minimum deal size
SCORE_THRESHOLD = 0.18  # calibrate on IS (same starting point as H174)
TC_BPS          = 10    # one-way; merger arb is buy-target, usually one-way
HOLD_MAX_DAYS   = 252   # max hold = 12 months (deals rarely take longer)

# STUB — EDGAR M&A 8-K fetching + FinBERT scoring implementation pending
raise NotImplementedError(
    "H333 stub — implement EDGAR 8-K fetcher for Item 1.01 (Business Combinations).\n"
    "Use full-text search: form_type=8-K, query='merger agreement OR acquisition'.\n"
    "Extract deal parties and consideration from filing text.\n"
    "FinBERT pipeline is identical to H163 — reuse scoring function."
)
