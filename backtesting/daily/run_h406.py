#!/usr/bin/env python3
"""
H406: Factor Momentum on Broad WorldQuant Alpha Universe
=========================================================
JPM 2025 (Cakici et al.): factor momentum is the MAIN ML alpha signal on
242 factor characteristics. Once controlled for, no ML method adds
significant alpha. Our H398A implicitly contains factor-momentum (IMOM6,
IMOM12) but on a narrow 4-signal set. H406 tests explicit factor momentum
on a broader universe of WorldQuant 101 signals.

Approach:
  1. Compute 20+ alpha101 signals monthly for H198 30-stock universe
  2. Track 3m/6m/12m momentum of each SIGNAL's cross-sectional IC
  3. Weight signals by their momentum (recent IC winners)
  4. Form composite stock score from momentum-weighted signals
  5. Select top-N stocks by composite score

Gate: OOS Sharpe > 4.068 (H041a/H398A baseline on 2021-2026)
IS:  2013-2020  OOS: 2021-2026
"""

# Full implementation deferred — this is a design stub
# Depends on: backtesting/daily/run_h395.py (alpha101 infrastructure)
#             backtesting/daily/run_h402.py (H041a production baseline)

HYPOTHESIS = "H406"
GATE_SHARPE = 4.068
IS_START = "2013-01-01"
OOS_START = "2021-01-01"
UNIVERSE = "H198_30_stock"  # same as H198/H041a

DESIGN_NOTES = """
Key design decisions:
- Use IC-weighted signal combination (momentum of each signal's IC)
- IC lookback: 3m/6m/12m rolling average IC per signal
- Signals from alpha101 (17 surviving cross-market per arXiv:2601.06499)
- No factor momentum within the 4-signal composite (H398A already optimal)
- Focus on signal diversity: include REVERSAL signals (R1W, R1M) as they
  will have LOW factor momentum in bull markets — self-regulating
- Expected turnover increase: ~30% vs H041a; must net above gate after
  5bp/trade transaction cost model

Connections:
- H215/H217 confirmed alpha101 signals (OOS 1.321/1.559)
- H228 confirmed alpha101+reversal blend (OOS 1.572)
- H398A H041a confirmed 4-factor composite (OOS 4.068) — this is the gate
"""

if __name__ == "__main__":
    print("H406 is a design stub — full implementation pending.")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    print("Build on top of run_h395.py alpha101 infrastructure")
