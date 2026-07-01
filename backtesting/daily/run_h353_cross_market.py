"""
H353 — Cross-Market Alpha: A-Share Microstructural Signals on US S&P 500
=========================================================================
Source: arXiv:2601.06499 (Du, Walter & Ulrich, Jan 2026)

Hypothesis:
  17 price-volume/microstructural signals derived from Chinese A-share markets
  transfer to US S&P 500 after controlling for 151 established factors.
  Test whether these signals improve H198 (6-1m momentum, OOS Sharpe 1.174).

Design:
  Universe: H198 30-stock NASDAQ large-cap
  IS: 2013-2020, OOS: 2021-2026 (same as H198 canonical split)
  Signals to implement (from paper Table 2, need to fetch full paper):
    1. Rank of delayed price-gap correlation (RDPGC)
    2. Overnight gap return
    3. Volume-intraday correlation
    [remaining 14 signals — need full paper]
  Blend: 0.7*H198_momentum + 0.3*cross_market_composite
  Gate: OOS Sharpe > 1.174 (H198 baseline) AND Corr(SPY) < 0.85

TODO: fetch full paper for all 17 signal definitions
Script: backtesting/daily/run_h353_cross_market.py (to be written)
"""

# STUB — signal definitions needed from full paper
print('H353 Cross-Market Alpha stub — need full paper for 17 signal definitions')
print('Fetch: https://arxiv.org/pdf/2601.06499 for Table 2 signal list')
