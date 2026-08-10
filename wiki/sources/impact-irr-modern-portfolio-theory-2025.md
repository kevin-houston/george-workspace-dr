---
created: 2026-08-09
updated: 2026-08-09
type: source_summary
authors: Daniel Soliman
published: 26 Sep 2025 (arXiv)
source: arXiv:2509.22600
url: https://arxiv.org/abs/2509.22600
category: Impact Investing
---

# Impact IRR: Leveraging Modern Portfolio Theory to Define Impact Investments — Soliman (2025)

**Author:** Daniel Soliman
**Venue:** arXiv:2509.22600, submitted 26 Sep 2025
**Subject areas:** Quantitative Finance, Portfolio Management, Economics

## What this is

A quantitative measurement proposal that attacks the exact gap the wiki's existing
Impact Investing pages flag as unsolved: the field has *qualitative* frameworks (J.P.
Morgan's 3D Impact/Return/Risk triangle, IRIS+ metrics, IMP's 5 dimensions) but no
standard **numeric performance statistic** analogous to an IRR or a Sharpe ratio that
lets an allocator rank or compare impact investments the way they rank financial ones.
The paper proposes **impact IRR** — an internal-rate-of-return-style metric adapted
from modern portfolio theory (MPT) to the $1.6 trillion impact investment market,
explicitly designed to sit "alongside financial returns" rather than replace them.

The construction borrows MPT's machinery (cash-flow discounting, portfolio-level
aggregation) but substitutes impact outcome data — drawn from existing datasets rather
than requiring new proprietary data collection — as the cash-flow-equivalent input.
The paper demonstrates the approach with use cases oriented toward optimizing
combined impact/financial outcomes, and is explicit that the field remains "in the
early stages of determining impact return" — i.e. this is a candidate standard, not
yet an adopted one.

## Why this matters for the wiki

This paper closes a specific, previously-unaddressed gap between two existing pages:

- [Three-Dimensional Portfolio Framework](../concepts/three-dimensional-portfolio-framework.md)
  gives impact a qualitative *axis* (a triangle vertex) but explicitly avoids a single
  summary statistic — "No single summary statistic — visual comparison" is listed as a
  design principle distinguishing the 3D graph from MPT's Sharpe ratio.
- [Impact Measurement Standards](../concepts/impact-measurement-standards.md) covers
  the IMP's "Contribution" (additionality/counterfactual) dimension as one of five
  qualitative questions, but notes "Counterfactual difficulty: true additionality
  requires knowing what would have happened without the investment — inherently
  unobservable... Most reporting uses industry baseline comparisons rather than
  rigorous causal inference."

Impact IRR is a 2025 attempt to convert both of those qualitative gaps into a single
computable number, using an MPT-derived cash-flow discounting structure rather than
narrative theory-of-change reporting. It doesn't solve the counterfactual/attribution
problem (still uses baseline comparison, not RCT-grade causal inference), but it is a
genuinely new quantitative artifact in a field the wiki's own Impact Measurement
Standards page describes as "still mostly qualitative outcomes vs. quantitative Sharpe
ratios" — directly narrowing that gap.

## Relevance to George's broader work

Structurally this is the impact-investing analog of the deflated-Sharpe /
multiple-testing discipline George applies to trading hypotheses: a single defensible
summary statistic that can be compared across candidate investments, replacing
ad hoc narrative claims. Worth tracking if Kevin's impact-investing interest ever
moves from research to a live allocation — a metric like this would let an impact
sleeve be screened with the same rigor as the trading hypothesis log (H001-H500+),
rather than falling back to unmeasurable "theory of change" language.

## See Also

- [Impact Investing](../concepts/impact-investing.md) — definition, key characteristics
- [Three-Dimensional Portfolio Framework](../concepts/three-dimensional-portfolio-framework.md) — the qualitative Impact/Return/Risk triangle this paper adds a scalar metric alongside
- [Impact Measurement Standards](../concepts/impact-measurement-standards.md) — IRIS+/IMP frameworks; "Contribution" dimension this paper attempts to quantify
- [A Portfolio Approach to Impact Investment (J.P. Morgan, 2012)](jpmorgan-portfolio-approach-impact-investment-2012.md) — the original MPT-extension this paper builds on, 13 years later
