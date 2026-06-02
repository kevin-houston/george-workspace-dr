'''
H244 — PEAD Multi-modal NLP
============================
Source 1: arXiv:2605.25894 — Predicting Stock Price Direction on Earnings Announcement
  Days using Multi-modal Deep Learning (FinBERT + fundamentals + TA features)
Source 2: arXiv:2509.24254 — Extracting the Structure of Press Releases for Predicting
  Earnings Announcement Returns (138K releases, 2005-2023: press release text as informative
  as EPS surprise for direction prediction)

H174 baseline: OOS WR=81.8%, MeanRet=6.89%, n=22, FinBERT score>=0.18 + surprise>=0.02

Hypothesis: Add press release structural features to H174's binary filter:
  1. Press release tone richness — ratio of strongly positive to hedging terms
  2. Explicit guidance reiteration flag — does PR confirm/raise guidance?
  3. Revenue vs earnings emphasis — revenue beat + EPS beat more predictive than EPS alone
  4. Multi-modal fusion weight: FinBERT_score * (1 + press_guidance_flag * 0.3)

Note: This hypothesis requires downloading press releases from EDGAR (8-K Item 8.01 'Other Events'
or company-specific press release exhibits). The H163/H174 pipeline already downloads 8-K text
from EDGAR — the press release is typically Exhibit 99.1 in the same filing.

Confirm: OOS WR > 81.8% OR OOS MeanRet > 6.89% on same universe as H174 (n >= 15 events)
'''

# TODO: Implement H244
# Scaffold:
#   1. Extend pead_overnight.py to also parse Exhibit 99.1 (press release) from the same 8-K URL
#   2. Build press release structural features:
#      - Count positive/negative financial terms (beat, exceeded, growth, record vs missed, headwinds)
#      - Detect guidance language (outlook, guidance, expects, projects)
#      - Revenue surprise check (compare revenue estimate from FMP vs reported)
#   3. Fuse: combined_score = finbert_score * (1 + 0.3 * guidance_flag) * (1 + 0.2 * revenue_beat_flag)
#   4. Threshold: combined_score >= 0.18, EPS surprise >= 0.02 (same as H174)
#   5. Backtest on H163's 8-K cache (2021-2026 OOS period)
#   6. Report: WR, MeanRet, n_events (compare to H174 baseline)

print('H244 scaffold — implementation needed (see design comments)')
print('Key dependencies: EDGAR 8-K exhibit parser, revenue surprise from FMP API')
print('Baseline to beat: H174 OOS WR=81.8%, MeanRet=6.89%, n=22')
