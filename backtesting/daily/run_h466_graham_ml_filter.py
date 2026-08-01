#!/usr/bin/env python3
"""
H466 — Quant Convergence: Graham Value Rules as ML Noise Filter on H198

Source: arXiv:2606.24575 (Yamazaki & Garrido-Lestache, Jun 2026)
        'Quant Convergence: Bridging Classical Value Investing and
         Modern Factor Models for Systematic Equity Selection'

Key paper findings:
- Graham Random Forest: 232.13% return (2022-2026), Calmar Ratio 1.38
- Complex AutoGluon: 222.68% return but 39.78% drawdown (overweighted volatile tech)
- Combined RF (momentum + Graham): 202.91% return, lowest MaxDD of all models
- Graham rules act as 'low-pass filter' suppressing momentum noise
- Test window (Mar 2022 - Mar 2026) includes 2022 crash + tech recovery

H198 adaptation:
- Universe: H198 30-stock NASDAQ large-cap
- NOTE: Strict Graham P/E<15 will likely eliminate ALL 30 NASDAQ large-cap stocks
- Relaxed Graham proxy: (a) P/E < 35, (b) P/B < 5, (c) positive 3yr EPS CAGR
- Data: FMP API quarterly fundamentals with 90-day reporting lag

Variants:
  A: Strict Graham (P/E<15, P/B<1.5) filter then 6-1m momentum top-6
  B: Relaxed Graham (P/E<35, P/B<5, positive 3yr EPS CAGR) then 6-1m momentum top-6
  C: Combined score: 0.6×momentum_rank + 0.4×graham_quality_score, top-6
  D: Pure Graham quality rank, top-6 (no momentum) — standalone value test
  E: H198 6-1m momentum baseline, top-6

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 baseline) AND MaxDD improvement

Data:
- FMP API ($FMP_API_KEY): P/E, P/B, current ratio, debt-to-equity, EPS growth
- Quarterly refresh with 90-day reporting lag applied

CAUTION:
- Strict Graham filters (Var A) expected to fail on NASDAQ large-cap (AAPL P/E~30)
- Cross-ref H337 NOT CONFIRMED: quality factor (GP/A, ROE) on H198 also failed
  Root cause: 30-stock large-cap NASDAQ universe has minimal cross-sectional quality variation
- Primary interest: Var B and C — can relaxed Graham improve risk profile without killing alpha?

VERDICT (2026-07-31): NOT RUNNABLE. FMP /stable/key-metrics and /stable/ratios are
reachable (HTTP 200) but hard-capped to the 5 most recent ANNUAL periods on the
current subscription tier: period=quarter -> 402, limit>5 -> 402, and year/from/to
filters are silently ignored (always returns the same 5 most recent rows, e.g.
2021-2025 for AAPL). No historical fundamentals reach back to the IS window
(2013-2020). Legacy /api/v3/key-metrics/{ticker} is fully decommissioned (403).
See wiki/trading/backtesting/hypothesis-log.md H466 entry for full detail.
Revisit only with an upgraded FMP plan or a free EDGAR-XBRL-based fundamentals
pipeline (unbuilt, out of scope for this pass).
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def fetch_fmp_fundamentals(tickers: list, start_year: int = 2012) -> pd.DataFrame:
    """
    Fetch quarterly P/E, P/B, current ratio, EPS CAGR from FMP API.
    Apply 90-day reporting lag before using in signal.
    """
    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        raise ValueError("FMP_API_KEY not set")

    # TODO: Implement FMP quarterly fundamental fetch
    # Endpoint: https://financialmodelingprep.com/api/v3/key-metrics/{ticker}?period=quarter&apikey={key}
    # Fields: peRatio, pbRatio, currentRatio, revenuePerShare, netIncomePerShare
    raise NotImplementedError("FMP fundamentals fetch not yet implemented")


def graham_quality_score(pe: float, pb: float, current_ratio: float,
                         eps_cagr_3yr: float, relaxed: bool = True) -> float:
    """
    Score 0-1 based on Graham criteria (1=fully Graham-compliant).
    relaxed=True uses sector-adjusted thresholds for large-cap tech.
    """
    if relaxed:
        # Relaxed thresholds for NASDAQ large-cap
        pe_ok = pe < 35 if not np.isnan(pe) else False
        pb_ok = pb < 5 if not np.isnan(pb) else False
        eps_ok = eps_cagr_3yr > 0 if not np.isnan(eps_cagr_3yr) else False
        score = (float(pe_ok) + float(pb_ok) + float(eps_ok)) / 3.0
    else:
        # Strict Graham
        pe_ok = pe < 15 if not np.isnan(pe) else False
        pb_ok = pb < 1.5 if not np.isnan(pb) else False
        cr_ok = current_ratio > 2.0 if not np.isnan(current_ratio) else False
        score = (float(pe_ok) + float(pb_ok) + float(cr_ok)) / 3.0
    return score


def main():
    print("H466 Graham ML Filter: stub implementation")
    print("TODO: Connect FMP fundamentals, run 5 variants, report OOS Sharpe vs H198 gate 1.174")
    sys.exit(0)


if __name__ == "__main__":
    main()
