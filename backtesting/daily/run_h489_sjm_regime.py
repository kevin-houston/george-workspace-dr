"""
H489 — Real Statistical Jump Model regime detection (jump-models library) as a drop-in replacement for the HMM approximation behind H429

STATUS: stub / build-plan, not yet implemented. See dream_cycle/staged/2026-08-03/4_h489_sjm_regime_stub.json for source proposal.

Script scaffold for H489 -- real Statistical Jump Model regime detection, replacing H429's hmmlearn-GaussianHMM approximation.

Phase 1 (dependency check, NOT auto-installed): verify `jump-models` (github.com/Yizhan-Oliver-Shu/jump-models) is available on PyPI via `pip index versions jump-models` or an equivalent package name -- if not on PyPI, install from GitHub source (`pip install git+https://github.com/Yizhan-Oliver-Shu/jump-models`) only after Kevin approval per the standing off-hours package-install security rule (single-author repo, not yet vetted). Run `pip-audit` after install. Do NOT install automatically as part of a scheduled run.

Phase 2 (reuse H429 harness): copy the data loader, feature set, and rolling 5Y window + Wasserstein state-matching wrapper directly from H429's script (find via hypothesis-log.md H429 entry -- likely `backtesting/daily/run_h429_*.py`) rather than rebuilding from scratch. Universe: SPY/TLT/GLD, same as H429. IS/OOS split: match H429 exactly so results are comparable apples-to-apples.

Phase 3 (swap state model): replace the `hmmlearn.GaussianHMM` fit/predict calls with `jump-models`' discrete JM class (start with discrete JM before trying continuous/sparse variants -- matches the paper's baseline configuration). Keep the same rolling-retrain cadence and Wasserstein state-matching logic that made H429 Var C/F pass gate -- this isolates the state-model swap as the only variable.

Phase 4 (variants): run at minimum two variants -- Var A (discrete JM, same rolling window as H429 Var C, 5Y) and Var B (discrete JM, same rolling window as H429 Var F, roll-3Y) -- to directly compare against the two H429 variants that passed gate (Var C OOS Sharpe 1.144 MaxDD -17.2% MaxStateFrac 47%; Var F OOS Sharpe 1.067 MaxDD -16.6% MaxStateFrac 41%).

Gate: matches H429's own dual gate (OOS Sharpe > baseline AND MaxStateFrac meaningfully lower than the HMM equivalent, since MaxStateFrac reduction -- fewer months stuck in a degenerate dominant state -- is the specific mechanism this hypothesis is testing, not just a Sharpe bump). Secondary comparison: is JM's real persistence penalty (in the objective) measurably better than HMM's post-hoc `smooth_regime_labels()` on the same data, or does the difference wash out in practice? Report both regardless of which direction it goes -- a null result (JM ~= HMM+smoothing) is still useful, since it would settle whether the wiki's 'real JM vs. approximation' distinction actually matters in production or is a theoretical nicety.

Known risk: jump-models is a small, single-author, unaudited project -- budget time to read its actual optimization code (not just the paper) before trusting numeric output, since a bug in a niche reference implementation would silently produce misleading backtest results.
"""
