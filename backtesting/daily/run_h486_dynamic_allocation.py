# H486 — Dynamic Multi-Strategy Capital Allocation via Online Portfolio Selection
# Source: universal-portfolios (Marigold, github.com/Marigold/universal-portfolios, 858 stars)
# Wiki: wiki/trading/paper-trading/dynamic-strategy-allocation.md (2026-08-02)
# Hypothesis: Replace the current STATIC target-weight blend across production sleeves
# (H026 27% / H041a 22% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%) with an
# Online Portfolio Selection (OPS) algorithm that dynamically reweights sleeves based on
# their recent NAV trajectories — same family of algorithm, applied to strategies-as-
# instruments instead of assets-as-instruments.
#
# Design (3 phases):
#
# Phase 1 — Data prep:
#   Build nav_df: DataFrame indexed by date, columns = strategy sleeve names
#   (H026, H041a, H045, H174_PEAD, XLK_IBS, SMH_IBS, IGV_IBS), values = cumulative NAV
#   per sleeve. strategy_accounts.json paper-trading history is too short for a real
#   backtest — source each sleeve's own run_hNNN.py OOS equity curve output instead,
#   resampled to a common daily/monthly frequency.
#
# Phase 2 — Baseline replication:
#   Reproduce the current static blend as the OOS Sharpe 4.158 / MaxDD -3.60% baseline.
#   Sanity check — must match the known number before proceeding to Phase 3.
#   Confirm production H174 weight (not documented in the current static blend note)
#   before finalizing the baseline sleeve list.
#
# Phase 3 — OPS backtest:
#   pip install universal-portfolios
#   Run OLMAR(window=5, eps=10) and CRP() from universal.algos against nav_df.
#   Compare resulting OOS Sharpe / MaxDD / turnover vs. the static baseline.
#
# Gate: dynamically-reweighted blend OOS Sharpe > 4.158 AND MaxDD not worse than -5.00%
# (baseline -3.60% + 1.4pp tolerance, matching the standard 5pp-improvement-or-no-regression
# gate pattern used elsewhere in the hypothesis log).
#
# Known risk: OPS algorithms assume free daily rebalancing into any "asset" — our sleeves
# have mismatched native cadences (H026/H041a/H045 monthly, IBS sleeves near-daily, PEAD
# event-driven). If Phase 3 passes the gate on paper, a follow-up step must confirm the
# *achievable* rebalance frequency (e.g. weekly target-weight recompute feeding into each
# sleeve's existing monthly/daily scripts) doesn't erode the improvement via added
# turnover/transaction costs — see transaction-costs.md gate methodology.
#
# TODO: implement nav_df builder sourcing each sleeve's OOS equity curve
# TODO: implement Phase 2 baseline replication + sanity check against known Sharpe 4.158
# TODO: implement Phase 3 OLMAR/CRP backtest via universal-portfolios
# See wiki/trading/paper-trading/dynamic-strategy-allocation.md for full research context
pass
