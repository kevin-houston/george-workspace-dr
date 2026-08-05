"""
H491 STUB -- Conditional skip-month momentum (Dikhit 2026 follow-up)

Source: Dikhit, "The Informational Role of the Most Recent Month in
Industry-Level Momentum Strategies" (Zenodo preprint, Jan 2026).

Hypothesis: unconditional skip-month (12-1) discards signal that the
H277/H336/H487/H488/H490 family already flagged as costly on some universes.
Dikhit's finding: the most recent month carries momentum-continuation signal
WHEN it was itself above-average -- i.e. skip only when recent-month return
was below the stock's own trailing average, otherwise include it (use 12-0).

Plan (not yet implemented -- this is a build stub from the 2026-08-05 dream
cycle scan):

1. Reuse the H490 ADDV-ranked NASDAQ superset loader (or H198 30-stock /
   H417 60-stock universe -- pick whichever gives the cleanest A/B against an
   existing confirmed baseline) and its IS 2013-2020 / OOS 2021-2026 split.
2. For each month t, compute recent_month_return = r[t-1].
   Compute trailing_avg = mean(r[t-13:t-1]) per stock (12-month trailing avg
   excluding the most recent month).
3. Conditional signal:
   - If recent_month_return >= trailing_avg: use 12-0 (include most recent
     month in the momentum ranking window)
   - Else: use 12-1 (skip most recent month, as standard)
4. Rank stocks monthly by the resulting conditional-window return, same
   monthly rebalance / top-N selection as the comparison baseline.
5. Gate: OOS Sharpe > best of {H198 baseline 1.174, H417 Var C 5.855,
   H490 Var A 1.044} depending on which universe is chosen as the base --
   pick the SAME baseline gate as whichever universe this ends up testing,
   for a fair like-for-like comparison per this log's established practice.

TODO before running: finalize universe choice, write the trailing_avg /
conditional-window logic, wire into the existing run_hNNN.py IS/OOS harness
used by H487-H490. Flagged medium risk (new script, not yet executed) per
dream_cycle staging policy -- apply_status should be 'flagged' for manual
build-out, not auto-run, since it needs universe/gate decisions a human or a
full research session should make rather than the 4am build phase.
"""

raise NotImplementedError("H491 stub -- needs universe choice and conditional-window logic before this can run. See dream_cycle/staged/2026-08-05/6_dikhit_skipmonth_momentum.json for the full plan.")
