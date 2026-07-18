#!/usr/bin/env python3
"""
H413: BAB × Lagged Realized Volatility Regime Gate
====================================================
Source: Barroso, Detzel & Maio (2025). 'The Volatility Puzzle of the Beta Anomaly.'
  Journal of Financial Economics, Vol. 165. SSRN 3882108.

Key finding: BAB Sharpe ratios rise after LOW-vol months. After high-vol months,
the BAB premium is crowded by institutional inflows and forward alpha is depleted.

H413 design:
  - Base signal: H192-D sector-neutral BAB (rank beta within GICS sector; long low-beta)
  - Gate: hold BAB only when trailing 21d SPY realized vol < rolling median
    → route to BIL otherwise
  - Confirm gate: OOS Sharpe > 1.5 (vs H192-D baseline 1.367)

Variants:
  A: vol_gate_21d (trailing 21d SPY vol vs expanding median)
  B: vol_gate_63d (trailing 63d SPY vol vs expanding median)
  C: vol_gate_21d + SPY>200MA (both conditions must hold)
  D: vol_percentile<40 (stricter than median)

IS: 2013-2020  OOS: 2021-2026  Universe: H198 30-stock NASDAQ large-cap
Reuse H192-D beta computation (corr_60m x vol_ratio).
"""

HYPOTHESIS = "H413"
GATE_SHARPE = 1.5
IS_START = "2013-01-01"
OOS_START = "2021-01-01"
UNIVERSE = "H198_30_stock"

if __name__ == "__main__":
    print("H413 is a design stub — full implementation pending.")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    print("Source: Barroso et al. 2025 JFE — volatility puzzle of BAB")
