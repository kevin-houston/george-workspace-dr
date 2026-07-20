#!/usr/bin/env python3
"""
H420: Convex Tail Overlay — Put Options + Trend-Following CVaR Framework
=========================================================================
Source: Noguer I Alonso & Al Fallouji (Jul 2026). 'Tail Risk Management with
  Puts and Trend Following: A CVaR Framework.' arXiv:2607.00883.

Key finding: Combining long OTM SPY puts with trend-following momentum overlays
reduces terminal CVaR better than either approach alone. The temporal separation
is crucial: convex insurance responds immediately to market jumps; trend-following
activates after signal crosses zero but strengthens during extended drawdowns
without additional premium cost.

Diagnostic axes from paper:
  1. Conditional convexity (put jump-response)
  2. Tail-event reliability (put coverage in crash months)
  3. Non-stress carry (trend-following income when puts not triggered)
  4. Drawdown persistence (trend-following behavior in multi-month corrections)

H420 design:
  - Base: production portfolio H041a/H026/H045/IBS (OOS Sharpe 4.158)
  - Overlay A: Roll 1% OTM monthly SPY put (1% notional hedge cost budget)
  - Overlay B: SPY 200d MA trend gate (existing H301 Var D = +27.4% Sharpe vs H026 standalone)
  - Overlay C: VIX<20 regime gate (H362 pattern — 29% MDD improvement on H354)
  - Goal: Reduce MaxDD from -3.60% toward -2% while maintaining Sharpe > 3.5

Implementation note: Production portfolio already has -3.60% MaxDD (extremely low).
The thesis question is whether a put overlay provides ADDITIONAL protection beyond
what the H416 drift gate + H362 VIX gate already achieve. Null hypothesis: existing
per-stock drift gates already provide convex protection equivalent to bought puts.

Confirmation gate:
  OOS Sharpe > 3.5 (80% of baseline 4.158) AND MaxDD < -2.5% (improvement from -3.60%)
  The tight MaxDD gate is key — if puts cost more than they save at this already-low
  drawdown level, the overlay is not economically justified.

Variants:
  A: SPY 1% OTM monthly put, 1% notional budget (roll cost ~3-5% annual drag)
  B: VIXCLS-triggered put buying (only buy puts when VIX < 15, cheap vol environment)
  C: Trend-following only (SPY >/<200d MA position sizing: 100%/50% production)
  D: Hybrid A+C (put + trend gate combined)

IS: 2013-2020  OOS: 2021-2026
Data: SPY options from Polygon.io (requires paid tier) or ThetaData for monthly cost est.

Note: Full implementation requires Polygon options data for realistic premium costs.
This stub establishes the design; the build phase should note data dependency.
"""

HYPOTHESIS = "H420"
GATE_SHARPE = 3.5
GATE_MDD = -0.025
IS_START = "2013-01-01"
OOS_START = "2021-01-01"

if __name__ == "__main__":
    print("H420 is a design stub — full implementation requires Polygon options data.")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} AND MaxDD < {abs(GATE_MDD)*100:.1f}%")
    print("Source: arXiv:2607.00883 Noguer & Al Fallouji 2026 CVaR tail risk framework")
    print("Production portfolio baseline: OOS Sharpe 4.158, MaxDD -3.60%")
    print("Key question: does a put overlay add value at this already-low MDD level?")
