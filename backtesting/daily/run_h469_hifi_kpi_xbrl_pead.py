#!/usr/bin/env python3
"""
H469 — HiFi-KPI Structured iXBRL KPI Extraction as H174 Signal Layer

Source: arXiv:2502.15411 (Feb 2026, v3)
        "HiFi-KPI: A Dataset for Hierarchical KPI Extraction from Earnings Filings"

Hypothesis: H174 uses raw EPS surprise as a binary gate (>= 0.02). The HiFi-KPI paper
shows that KPIs are structured, hierarchically organized, and linkable to iXBRL taxonomies.
More precisely: SEC EDGAR XBRL API already provides machine-readable EPS and revenue figures
for all 10-Q/8-K filings — no LLM extraction required. H469 adds a RELATIVE KPI magnitude
as a continuous multiplier: bigger EPS beat relative to consensus → larger expected PEAD
drift → scale position by min(2.0, 1.0 + EPS_beat_pct). This upgrades H174's binary EPS
surprise gate to a continuous magnitude signal without adding LLM cost.

Variants:
  A: H174 base + EPS magnitude scaling: size = min(2.0, 1.0 + EPS_beat_pct)
  B: H174 base + binary EPS gate: EPS_beat_pct > 5% required
  C: H174 base + revenue beat gate: rev_beat_pct > 0% required
  D: H174 base + composite: avg(EPS_beat, rev_beat) as continuous multiplier
  E: H174 baseline (FinBERT >= 0.18 + EPS surprise >= 0.02)

IS: 2022-2023, OOS: 2024-2026
Gate: OOS WR >= 0.818 AND OOS MeanRet >= 6.89% (H174 baseline) at n >= 15

Complement to:
  H427: Event taxonomy type filter (SAME paper arXiv:2607.08346, already staged 2026-07-22)
  H471: Unstructured earnings call KPI extraction (arXiv:2605.03147)

Pipeline: H427 (event type) → H469 (KPI magnitude) → H471 (call qualitative KPIs)

TODO: Build structured KPI pipeline:
  1. For each H174 qualifying event, pull EDGAR XBRL EPS actual (us-gaap/EarningsPerShareBasic)
  2. Pull FMP consensus EPS from earnings_surprises endpoint (already used in PEAD pipeline)
  3. Compute EPS_beat_pct = (actual - consensus) / abs(consensus)
  4. Cross-validate: flag |EPS_beat_pct| > 3.0 as data quality suspect
  5. Run IS/OOS evaluation for Vars A-E
"""

# STUB — not yet implemented.
# Prerequisites:
#   1. Verify EDGAR XBRL EPS coverage for H174 event universe (expect ~85% for S&P 500)
#   2. Cross-reference with FMP consensus EPS (already fetched in pead_overnight.py)
#   3. Implement EPS_beat_pct calculation and data quality filter
#   4. Implement position_size_multiplier = min(2.0, max(1.0, 1.0 + EPS_beat_pct))
#   5. Backtest A/B/C/D/E on H174 confirmed event set
#
# EDGAR XBRL fetch example:
#   GET https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json
#   → data['facts']['us-gaap']['EarningsPerShareBasic']['units']['USD/shares']
#   Filter to filings matching the earnings date; take the reported value.
#
# Zero LLM cost. Purely structured XBRL data. Complements H427/H471.

print("H469 stub — implementation pending.")
print("Source: arXiv:2502.15411 — HiFi-KPI Structured iXBRL KPI Extraction")
print("Gate: OOS WR >= 0.818 AND MeanRet >= 6.89% at n >= 15")
print("Next step: Implement EDGAR XBRL EPS pull + FMP consensus cross-check.")
print("Note: Complements H427 (event taxonomy) and H471 (call KPIs) — different signal axis.")
