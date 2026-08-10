---
title: Impact Measurement Standards
aka: IRIS+, IMP, impact metrics, impact KPIs
tags: impact-investing, measurement, standards, GIIN, IRIS
added: 2026-07-08
updated: 2026-08-09
category: Impact Investing
---

# Impact Measurement Standards

## Why Measurement Matters

Impact investing's core claim — that capital can generate positive social/environmental outcomes alongside financial returns — is only verifiable if impact is systematically measured. Without standardized metrics, "impact" is marketing language, not a performance dimension.

The J.P. Morgan 2012 portfolio approach identified impact measurability as a defining characteristic of impact investing (vs. SRI/philanthropy). In the decade since, the field has converged on two foundational frameworks: IRIS+ and the Impact Management Project.

---

## IRIS+ (GIIN)

**IRIS+** (Impact Reporting and Investment Standards, now version 3.0+) is the GIIN's system for impact measurement and management.

**What it provides:**
- 2,000+ individual metrics covering social, environmental, and governance outcomes
- **Core Metrics Sets**: shortlists of 10-20 key indicators per sector/theme, backed by evidence and best practice — the starting point for any new impact portfolio
- SDG alignment mapping — each metric maps to one or more UN Sustainable Development Goals
- Comparison infrastructure — investors using the same metrics can benchmark across portfolios

**How it works:**
1. Select a Core Metrics Set for your sector (e.g., "Financial Services," "Clean Energy," "Housing")
2. Add supplementary metrics specific to your investment thesis
3. Collect data from investees at agreed intervals
4. Report against targets; compare against sector-level benchmarks

IRIS+ metrics span both **output metrics** (number of people reached) and **outcome metrics** (% of households with reliable electricity). The shift from outputs to outcomes is an ongoing maturation challenge — outputs are easier to count, outcomes require longitudinal tracking.

**Website**: https://iris.thegiin.org

---

## Impact Management Project (IMP) — 5 Dimensions

The IMP (now integrated into the Impact Frontiers consortium) articulates five dimensions for assessing any impact:

| Dimension | Questions to answer |
|---|---|
| **What** | What outcomes are being targeted? Are they positive or negative? How important are they to affected people/planet? |
| **Who** | Who experiences the outcomes? Are they underserved? How many people? |
| **How Much** | What is the scale (depth × breadth)? How long do outcomes persist? |
| **Contribution** | Would these outcomes have happened anyway? (Counterfactual / additionality) |
| **Risk** | What is the probability that impact is realized at claimed level? |

The IMP 5-dimension framework is now embedded in major regulatory guidance (EU SFDR Article 8/9, UK SDR) and standard due diligence templates used by institutional LPs.

**Key insight**: investors who assess all 5 dimensions are making fundamentally different decisions than those who only count "number of people reached" (What + Who, ignoring Contribution and Risk).

---

## Regulatory Frameworks (2024-2025)

The impact measurement landscape has been significantly shaped by regulation:

**EU SFDR (Sustainable Finance Disclosure Regulation)**
- Article 6: no sustainability claim
- Article 8: "promotes" environmental/social characteristics (ESG integration)
- Article 9: "sustainable investment objective" (closest to impact investing proper)
- Requires disclosure of Principal Adverse Impacts (PAIs) — a mandatory list of environmental/social harm metrics

**UK SDR (Sustainable Disclosure Requirements)**
- Labels: Sustainability Focus, Sustainability Improvers, Sustainability Impact, Sustainability Mixed Goals
- "Sustainability Impact" label most analogous to impact investing — requires measurable positive outcomes in the real world

**SEC Climate Rules (US, 2024-2026)**
- Require material climate risk disclosure, Scope 1/2 GHG emissions
- Still contested as of 2026 (litigation ongoing); Scope 3 disclosure requirements delayed

---

## Common Metrics by Sector

| Sector | Key IRIS+ metrics |
|---|---|
| Financial inclusion | # people with access to financial services; % women borrowers; avg loan size |
| Clean energy | MW of clean energy capacity; MtCO2 avoided; # households with clean energy access |
| Affordable housing | # affordable housing units; % households earning <80% AMI; avg. affordability % of income |
| Healthcare | # patient visits; # people vaccinated; # healthcare workers trained |
| Smallholder agriculture | # smallholder farmers reached; % women farmers; crop yield improvement % |

---

## Challenges and Limitations

**Attribution**: impact outcomes are causally complex. A microfinance borrower's income increase is caused by the loan, the borrower's effort, market conditions, family support, and many other factors. Impact investors typically use "theory of change" narratives rather than rigorous causal inference.

**Counterfactual difficulty**: True additionality requires knowing what would have happened without the investment — inherently unobservable. Most reporting uses industry baseline comparisons rather than randomized control trials. A 2025 proposal, [Impact IRR](../sources/impact-irr-modern-portfolio-theory-2025.md) (Soliman, arXiv:2509.22600), attempts to convert this qualitative "Contribution" dimension into a single MPT-derived scalar metric — still baseline-comparison-based rather than RCT-grade, but a step toward the quantitative rigor this section identifies as missing.

**Data collection burden**: investees (especially early-stage ventures in emerging markets) face significant overhead reporting impact KPIs quarterly. This can distort incentives — companies optimize for reported metrics, not underlying outcomes.

**Output vs. outcome gap**: # of people trained (output) vs. % who got jobs and retained them (outcome) — the latter requires multi-year tracking and is much harder to collect.

---

## Analogs to Quant Trading Metrics

For Kevin's trading research context, impact measurement frameworks offer structural parallels:

| Impact investing concept | Trading analog |
|---|---|
| IRIS+ Core Metrics Set | Standard hypothesis evaluation checklist (shared-eval-checklist.md) |
| IMP Contribution / Additionality | IS/OOS generalization (does strategy add value beyond luck/existing factors?) |
| Theory of change | Mechanism explanation (why should this factor work?) |
| Impact Risk | Strategy risk (MaxDD, tail risk, WF ratio) |
| Measurement standardization across portfolios | Shared backtest protocol (canonical IS/OOS, FRED macro data, after-tax) |

Both domains have evolved from idiosyncratic measurement practices toward standardized, comparable metrics — though impact investing is further behind in rigor (still mostly qualitative outcomes vs. quantitative Sharpe ratios).

---

## Cross-references

- [Impact Investing](impact-investing.md) — definition, risks, key characteristics
- [Impact Investing Market Landscape 2025](impact-investing-market-2025.md) — market size, institutional trends
- [Three-Dimensional Portfolio Framework](three-dimensional-portfolio-framework.md) — Impact/Return/Risk graph (J.P. Morgan 2012)
- [Impact IRR (Soliman, 2025)](../sources/impact-irr-modern-portfolio-theory-2025.md) — MPT-derived scalar metric attempting to quantify the Contribution/additionality dimension
- [Shared Strategy Evaluation Checklist](../trading/shared-eval-checklist.md) — trading analog for standardized evaluation
- [Multiple Testing & Statistical Significance](../trading/backtesting/multiple-testing.md) — addresses the "attribution" problem in backtesting
