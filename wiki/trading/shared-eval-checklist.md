---
title: Shared Strategy Evaluation Checklist
description: Common standard for both George and Ernesto before any strategy advances to paper trading or production
updated: 2026-07-08
authors: [George, Ernesto]
---

# Shared Strategy Evaluation Checklist

Agreed standard for both George (NanoClaw) and Ernesto to apply before any strategy advances to paper trading or production. Results across both systems are only comparable when this checklist is satisfied.

---

## 1. Look-Ahead Guard

- [ ] All price/return signals use `.shift(1)` (or equivalent) so no future data leaks into the signal at time T
- [ ] For ML features (rolling stats, z-scores, etc.), confirm the rolling window is computed on data available *before* T
- [ ] Document any exception with a written justification

## 2. NLP Timestamp Documentation

For any strategy that uses text-based signals (earnings transcripts, 8-K filings, news, sentiment):

- [ ] Document the source of T=0 (e.g., EDGAR accession timestamp, news publish time, API delivery time)
- [ ] Document market-hour handling: filings/news that arrive after market close → signal fires at *next* open; intraday → document exactly
- [ ] Confirm no text content that postdates T=0 is used in the signal

## 3. Transaction Cost Model

- [ ] Equity strategies: model at minimum **5bps round-trip** (entry + exit) per trade
- [ ] Options strategies: add estimated **bid-ask half-spread** on top of the 5bps baseline
- [ ] Report how many trades are culled once costs are applied (a meaningful cull % is a feature, not a bug)
- [ ] Strategies with turnover > 2x/month must show net-of-cost Sharpe explicitly

## 4. Soft OOS Gate

Before paper trading:
- [ ] Backtest Sharpe documented over the IS period

During paper trading:
- [ ] After 60 days, paper P&L must be within **1 StdDev** of backtest expectation
- [ ] Strategies that breach this gate are paused and reviewed — not automatically killed

For production promotion:
- [ ] OOS Sharpe > **0.8** (hard gate)
- [ ] If near the gate (0.8–0.9), flag as fragile and require additional confirmation period

## 5. Regime Coverage

- [ ] Backtest spans at minimum: **2022 bear market** (rate hike cycle) + **2024 rally**
- [ ] Credit-sensitive strategies (fixed income, sector rotation, rate-linked): add FRED macro overlay (Fed Funds rate, credit spreads, yield curve slope)
- [ ] Regime-conditional strategies: document which states are covered and how many observations per state in IS and OOS

## 6. Universe & Survivorship Bias

- [ ] Document the exact stock universe used (e.g., "SP500 current constituents as of 2026-06," "NASDAQ100 at backtest date")
- [ ] If the universe is based on *current* members, flag as **survivorship-biased** — results are optimistic
- [ ] Preferred: point-in-time constituent lists (e.g., from CRSP, Sharadar, or a dated snapshot)
- [ ] ETF-only universes are survivorship-bias-free by default (document this explicitly)

## 7. After-Tax Flag

- [ ] Note whether reported returns are **pre-tax** or **post-tax**
- [ ] Production targets are post-tax; strategies promoted to production must include a post-tax estimate
- [ ] Short-term gains (hold < 1 year) taxed at ordinary income rate — model at 37% for worst-case planning

---

## 8. Bear Case / Steelman

Before paper trading, write a short adversarial section:

- [ ] **What's the most likely failure mode?** (e.g., signal decays, data source disappears, regime shifts)
- [ ] **What does this strategy look like if it's just noise?** (i.e., what would the equity curve look like if the IS period was a lucky draw?)
- [ ] **What other confirmed strategies does this correlate with?** Strategies that are "the same bet in different clothing" don't add diversification
- [ ] **Data source dependency:** if the primary data source (EDGAR, Polygon, Massive API, etc.) goes away, is there a fallback?

This does not have to be long — 3–5 bullet points is enough. The goal is to force one honest counterargument before committing paper capital.

---

## Checklist Sign-Off

Before advancing a strategy, record:

```
Strategy: H### / R##
Date evaluated: YYYY-MM-DD
Evaluated by: George / Ernesto
Items passed: all / list exceptions
Bear case summary: [3-5 bullets]
Notes:
```

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-06-09 | Initial draft — 7-point checklist agreed by George and Ernesto | George |
| 2026-06-09 | Added point 8: required bear case / steelman section (Ernesto suggestion) | George |
| 2026-06-21 | Added LLM trading 7-dimension reproducibility audit section (arXiv:2606.08285) | George |
| 2026-07-08 | Added Alpha Illusion 6-test gate (arXiv:2605.16895); full checklist at llm-alpha-validation.md | George |

---

## LLM Trading System — 7-Dimension Reproducibility Audit (arXiv:2606.08285)

For any LLM-based hypothesis (H279, H280, H316-H325+), verify all 7 dimensions:

| Dimension | Gate | Notes |
|-----------|------|-------|
| Point-in-time data | All data must be available at signal date | No forward-looking fundamentals, earnings revisions |
| Temporal split | Strict future cutoff | No val set leakage; IS/OOS boundary must predate any hyperparameter tuning |
| Execution timing | T+1 open or T+1 close (document which) | LLM signal on close d; execution on open d+1 minimum |
| Transaction costs | Explicit $/share or bps assumption | Default: 5bps round-trip for liquid large-cap; document deviations |
| Universe specification | Survivorship-free or documented bias | H198/H217 universe note: known survivorship bias caveat |
| Prompt/parameter transparency | All prompts logged to results JSON | Temperature, model, system prompt version, date |
| Reproducible artifacts | Results JSON + prompt log committed | Required for H316+ LLM hypotheses |

**Source:** arXiv:2606.08285, June 2026. Analyzed 30 LLM trading papers; all 7 dimensions vary widely; friction + execution timing choices material to claimed Sharpe.

---

## LLM Trading System — Alpha Illusion 6-Test Gate (arXiv:2605.16895)

For LLM-based strategies before advancing to paper trading, additionally verify all 6 structural validity tests from Sheng et al. (2025). Full checklist: `wiki/trading/algorithms/llm-alpha-validation.md`

| Test | What to Check | Common Failure |
|------|--------------|----------------|
| Temporal integrity | No future data in LLM context/training | Knowledge base not time-indexed |
| Real-world frictions | 5bps+ commissions, market impact, borrow costs | Costless execution assumed |
| Counterfactual robustness | Beats SPY buy-and-hold AND equal-weight | Cherry-picked benchmark |
| Predictive calibration | High-confidence trades win more often | Confidence uncorrelated with outcome |
| Numerical execution | Positions fillable at stated volume | Requires more liquidity than available |
| Multi-agent disaggregation | Each agent contributes; ablation hurts | One agent carries all alpha |

**Source:** arXiv:2605.16895. Systems audited: FinCon, FinMem, TradingAgents, FinAgent, QuantAgent, FLAG-Trader.
