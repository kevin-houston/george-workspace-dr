---
aka: Impact/Return/Risk Triangle, 3D Portfolio Graph, Target Portfolio Graph
origin: J.P. Morgan Social Finance (Saltuk & El Idrissi, 2012)
tags: impact-investing, portfolio-theory, visualization, framework
updated: 2026-08-09
---

# Three-Dimensional Portfolio Framework (Impact / Return / Risk)

## Overview

An extension of Markowitz's modern portfolio theory (MPT) that adds **impact** as a third dimension alongside return and risk. Developed by J.P. Morgan Social Finance and published in [A Portfolio Approach to Impact Investment (2012)](../sources/jpmorgan-portfolio-approach-impact-investment-2012.md).

MPT distils multi-dimensional investment information into a two-parameter (risk/return) graph. Impact investors need a third axis because impact performance is a real dimension of their investment mandate — not a constraint or a trade-off, but a co-equal performance dimension.

---

## The Graph

Each investment is represented as a **triangle** (or polygon) with three vertices:

```
        Impact
          /\
         /  \
        /    \
  Risk /______\ Return
```

- Each vertex represents **how much** of that dimension the investment delivers
- Vertices closer to the edge of the triangle = stronger on that dimension
- The shape of the triangle encodes the investment's profile

**Target zone**: A shaded area (not a single line) representing acceptable ranges across all three dimensions. Individual investments don't need to match the target — the **aggregate portfolio** does.

**Aggregate**: Overlay individual investment triangles or compute a notional-weighted average to produce one aggregate triangle. Compare aggregate to target zone.

---

## Extended Version: Six Dimensions

Each axis can be split into two sub-components:

| Axis | Sub-component 1 | Sub-component 2 |
|------|----------------|----------------|
| Return | Income | Appreciation |
| Risk | Products | Process |
| Impact | Ecosystem | Investment |

Result: a hexagon rather than triangle. Useful when the portfolio warrants finer-grained analysis; keep the three-axis version for high-level aggregation across large portfolios.

---

## Investor Archetypes (from paper's illustrations)

| Archetype | Graph shape |
|-----------|------------|
| J.P. Morgan Social Finance (balanced) | Moderate range on all three axes; no extreme trade-offs |
| High-risk investor | Wide range on Risk axis; accepts higher risk for impact |
| "Non-negative impact" (SRI-style) | Tight return/risk profile; impact axis narrow (just excludes negatives) |

---

## Key Design Principles

1. **No implied correlation** — the paper explicitly states no particular correlation or relationship is assumed between impact, return, and risk. They are independent axes.
2. **Portfolio-level not investment-level targets** — individual investments can be outside target zone so long as the aggregate sits within it.
3. **Complementary tool** — never use on a standalone basis; always alongside detailed investment understanding.
4. **Deal-by-deal analysis** — do not generalize return expectations across the impact asset class; analyze each deal's economics separately.

---

## Relationship to Modern Portfolio Theory

| MPT | 3D Framework |
|-----|-------------|
| Two axes: Risk, Return | Three axes: Risk, Return, Impact |
| Efficient frontier | Target portfolio zone |
| Portfolio variance minimization | Portfolio profile alignment with mandate |
| Sharpe ratio as summary statistic | No single summary statistic — visual comparison |

The 3D framework does not replace MPT; it extends it for the specific context where a non-financial performance dimension (impact) is a genuine portfolio objective, not just a constraint.

**2025 update:** [Impact IRR](../sources/impact-irr-modern-portfolio-theory-2025.md)
(Soliman, arXiv:2509.22600) is a more recent attempt to add back a single summary
statistic — an MPT-derived internal-rate-of-return analog for the impact dimension —
13 years after this framework explicitly chose visual/triangle comparison over a
scalar metric. Worth reading alongside this page as the two live options (visual
multi-axis vs. scalar IRR-style) for summarizing impact performance.

---

## Cross-references
- [A Portfolio Approach to Impact Investment (J.P. Morgan, 2012)](../sources/jpmorgan-portfolio-approach-impact-investment-2012.md)
- [Impact Investing](impact-investing.md)
