---
created: 2026-08-26
updated: 2026-08-26
type: tool_note
category: Tools
url: https://github.com/ArturSepp/OptimalPortfolios
---

# ArturSepp/OptimalPortfolios + ArturSepp/factorlasso — Portfolio Construction & Factor-Selection Libraries

Two Python libraries from the same GitHub author (Artur Sepp), surfaced via a dream-cycle GitHub-trending scan on 2026-08-26 and verified real/legitimate via direct GitHub API calls before logging (hallusquatting-defense checklist per persona.md: checked star count, license, and recent commit activity rather than trusting search-snippet metadata).

## OptimalPortfolios

- **Repo**: https://github.com/ArturSepp/OptimalPortfolios
- **Verified**: 92 stars, MIT license, created 2023-07-08, last pushed 2026-08-24 (2 days before this note) — actively maintained, not abandoned.
- **What it does**: pip-installable library implementing multiple portfolio-optimization methods over pandas/numpy return data — max-Sharpe, minimum-variance, risk-parity, and robust/shrinkage-covariance variants.
- **Relevance**: George's production portfolio blend (H041a 22% / H026 27% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%) is currently hand-tuned via backtested Sharpe comparison across the H-series, not derived from a formal optimizer. This library is a candidate tool for a future hypothesis testing whether a risk-parity or shrinkage-covariance re-weighting of the existing 6 confirmed strategies improves the blended Sharpe (currently 4.158) or reduces MaxDD (currently -3.60%) versus the hand-tuned weights.

## factorlasso

- **Repo**: https://github.com/ArturSepp/factorlasso
- **Verified**: 24 stars, GPL-3.0 license, created 2026-03-22, last pushed 2026-08-23 (3 days before this note) — newer and smaller than OptimalPortfolios but actively developed.
- **What it does**: LASSO-based factor selection — identifies which candidate factors genuinely explain a return series' variance (non-zero LASSO coefficient) versus which are statistically redundant/collinear noise.
- **Relevance**: could formalize the correlation-diagnostic work George already does ad hoc across the H-series (e.g. H241/H354/H361/H362 Corr(SPY) checks, H313's sector-neutral collinearity finding, H470's cross-strategy correlation matrix). A future hypothesis could apply factorlasso across the full set of confirmed signals feeding the production blend to check for redundancy the manual correlation checks may have missed.

## Adoption status

Reference/tools note only as of 2026-08-26 — no package installed, no change to the production blend or any backtest script. Before installing either package, verify the exact PyPI package name (not just the GitHub repo name) exists on pypi.org per the standing pip-install security checklist, then run pip-audit after installation.

## See Also

- [QuantStats notes](quantstats-notes.md) — prior tool-adoption precedent for portfolio analytics tooling, same evaluation pattern (verify real, low-effort integration, no forced adoption)
- wiki/trading/backtesting/hypothesis-log.md — H510-H514 blast-radius correction family, the correlation/redundancy question this tooling could help formalize
