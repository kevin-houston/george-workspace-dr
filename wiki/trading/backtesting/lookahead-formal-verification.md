---
type: backtesting-methodology
title: Look-Ahead-Freedom as Temporal Non-Interference
description: Formal computer-science treatment of look-ahead bias detection in backtesting and agentic trading pipelines. Linear-time type-and-effect checker catches leaks that statistical detectors miss.
tags: [backtesting, look-ahead-bias, formal-verification, agentic-trading, pipeline-integrity]
updated: 2026-07-20
---

# Look-Ahead-Freedom as Temporal Non-Interference

**Source:** arXiv:2607.04958 (Xavier Fonseca, July 2026)

## Background

Look-ahead bias is the most dangerous systematic error in quantitative backtesting — it produces strategies that appear to work but exploit future data not available at decision time. Prior detection methods relied on domain-specific heuristics (e.g., checking `.shift(1)` calls) or post-hoc statistical tests that catch only the most obvious leaks.

Fonseca (2026) reframes look-ahead detection as a formal computer-science problem, establishing it is equivalent to verifying **temporal non-interference** over a time-indexed information lattice.

## Core Theoretical Result

### The Decidability Boundary

The paper establishes a sharp boundary for look-ahead-freedom verification:

- **When data availability depends on values** (e.g., "fetch data only if price > threshold"): look-ahead-freedom is **Π₀¹-hard** (undecidable). No algorithm can guarantee detection in the general case.
- **Value-independent scenarios** (the practical fragment): look-ahead-freedom **is decidable** in linear time.

The value-independent practical fragment covers:
- Windowing operations (rolling windows, expanding windows)
- Resampling (daily → monthly, etc.)
- Point-in-time joins (e.g., fundamental data with as-of dates)
- Vintage reads (accessing data as it existed at a past date)
- Agentic retrieval (LLM queries against time-indexed corpora)

This covers virtually all operations in systematic trading backtests.

### The Type-and-Effect System

The verification approach uses a **type-and-effect system** where:
- Every data operation carries a **temporal type**: its valid time range as seen from the decision point
- Operations that combine data from incompatible temporal types are flagged as potential leaks
- The checker runs in **O(n)** time in the number of pipeline operations

Empirical validation shows:
- An artifact demonstrating linear scaling in practice
- An independent oracle witnesses no leak in any accepted pipeline
- The checker catches every planted leak that statistical differential-testing and tiling detectors miss

## Why Statistical Detectors Are Insufficient

Conventional look-ahead detection methods used in practice:
1. **Differential testing**: Run with/without future data; large change = possible leak
2. **Tiling detectors**: Check that training windows don't overlap test windows
3. **Code review**: Manual inspection for `.shift(1)` omissions

All three fail silently on:
- Indirect leaks through cached intermediate computations
- Leaks through external lookups (EDGAR filing timestamps, analyst consensus)
- Agentic retrieval where LLM knowledge cutoff isn't enforced
- Point-in-time joins where "as_of" date is incorrectly computed

The type-and-effect checker catches all of these by tracking temporal provenance through the computation graph.

## Relevance to George's Pipeline

### Known Look-Ahead Incidents

The **H256 look-ahead bias incident** (unlagged 12m signal inflated GEM+Sector OOS Sharpe from 0.646 to 1.956) is the canonical failure mode. Root cause: `.shift(1)` missing on the momentum signal computation, causing same-month-end return data to influence portfolio formation. A formal verifier would catch this as a type mismatch — the signal carries temporal type "end-of-month t" but it's combined with returns from "month t" portfolio.

### H174 PEAD Pipeline

The PEAD pipeline (pead_overnight.py, pead_intraday.py) has several potential temporal non-interference violation points:
- **EDGAR 8-K scoring**: The FinBERT score must only use filings whose `period_of_report` ≤ decision date AND whose `filed_date` ≤ decision date
- **EPS surprise computation**: Must use consensus as it existed before filing date, not ex-post consensus
- **Alpaca price data**: Open price for gap detection must be the actual next-day open, not same-day close

A formal verifier would annotate each of these data streams with their temporal type and reject any computation that combines incompatible types.

### Agentic Trading (H274 Multi-Agent PEAD)

The paper explicitly addresses **agentic retrieval** — a novel look-ahead source where an LLM agent can inadvertently retrieve future context from a knowledge base. Fonseca's framework treats LLM tool calls as temporal data operations with an effective "knowledge horizon" that must be bounded to the decision timestamp.

For H274 (multi-agent PEAD debate), this implies:
- Each agent's retrieval from the wiki/memory system must be bounded to data available before decision time
- LLM training knowledge cutoff must be treated as a temporal bound, not just a disclaimer

## Practical Application Protocol

Pending a full implementation of the type-and-effect checker, approximate safeguards:

### In Python Backtests

```python
# Standard look-ahead guard pattern
# CORRECT: shift signal by 1 period before using to form portfolio
portfolio_weights = signal.shift(1)  # t-1 signal → t returns

# WRONG: using same-period signal (classic leak)
portfolio_weights = signal  # t signal uses t end-of-day data → leaks

# CORRECT: point-in-time fundamental data join
# Use data.asof(decision_date) not data.loc[decision_date]
eps = fundamentals.asof(rebalance_date)

# CORRECT: EDGAR filing date check
# Exclude filings where filed_date > decision_date even if period_of_report covers decision period
valid_filings = filings[filings['filed'] <= decision_date]
```

### Integration with Shared Eval Checklist

See [Shared Strategy Evaluation Checklist](../shared-eval-checklist.md) — Point 1 (Look-Ahead Guard) is specifically about temporal non-interference:
- NLP timestamp: 8-K scored only using text available before market open
- Point-in-time fundamental data (`.asof()` not `.loc[]`)
- No forward-fill of signals beyond their valid horizon
- EDGAR filed-date gating (not period_of_report alone)

## Connection to OpenFinGym (H390)

The OpenFinGym framework (arXiv:2606.26350; see [OpenFinGym](../../ai-industry/openfinGym-2026.md)) provides a containerized runtime with a host-side verifier that independently validates temporal non-interference. Running H174/H026 through OpenFinGym is the closest current approximation to the formal verification approach described here.

## Summary

| Property | Statistical Detectors | Type-and-Effect Checker |
|---|---|---|
| Completeness | Partial (misses indirect leaks) | Complete for practical fragment |
| Runtime | O(n²) or worse | O(n) linear |
| Agentic retrieval | Not addressed | Explicitly handled |
| Point-in-time joins | Fragile | First-class support |
| False positive rate | High (differential testing) | Low (type-directed) |

**Key takeaway:** Until a formal verifier is integrated into the backtesting pipeline, the `.shift(1)` discipline, EDGAR filed-date gating, and OpenFinGym validation are the best available safeguards. The H256 incident pattern (inflated OOS due to missing shift) should be treated as the canonical failure mode to guard against in all new hypotheses.

## Cross-References

- [Backtesting Design Principles](design-principles.md) — bias taxonomy, IS/OOS framework
- [Shared Strategy Evaluation Checklist](../shared-eval-checklist.md) — Point 1: look-ahead guard
- [Walk-Forward & CPCV](walk-forward-cpcv.md) — proper IS/OOS separation
- [Multiple Testing & Statistical Significance](multiple-testing.md) — avoiding data snooping
- [OpenFinGym (H390)](../../ai-industry/openfinGym-2026.md) — containerized independent verifier
- [LLM Alpha Validation Checklist](../algorithms/llm-alpha-validation.md) — agentic pipeline integrity
- [Regime-Conditional Distributional Strategy Evaluation](regime-conditional-strategy-eval.md) — formal distributional comparison

---

## Research Lead: Mask-First Tradability Design Pattern (arXiv:2507.07107, flagged 2026-08-02)

A 2026 Chinese A-share ML factor study ("Machine Learning Enhanced Multi-Factor Quantitative Trading," arXiv:2507.07107) documents a specific look-ahead bug class worth generalizing: non-tradable closing prices (in their market, daily price-limit halts) leaking into rolling-window factor calculations *before* any tradability filter is applied -- the model then learns predictive patterns on prices it could never have actually traded on. Their fix, a "mask-first design," constructs a Boolean tradability mask at data-load time and threads it through every downstream window calculation, rather than filtering only at final portfolio construction. In their own ablation, removing the mask alone cost -0.44 realized Sharpe (2.05 synthetic-panel Sharpe vs. 1.63 real A-share Sharpe with the mask in place) and inflated their in-sample information coefficient by 18% relative to the masked version -- i.e. the unmasked pipeline looked better exactly because it was cheating.

**Why it matters here**: US large-cap equities don't have China's price-limit halt mechanism, but the same bug class applies to any `run_hNNN.py` script computing rolling-window signals (12m momentum, IBS z-scores, drift-fraction gates, etc.) over a price series that includes halted trading, delisted tickers mid-window, or thinly-traded days where the "close" wasn't really achievable at scale. `survivorship-bias.md` covers delisting at the universe-construction level; this pattern is a complementary check at the signal-computation level -- worth an explicit "is every price in this rolling window one we could have actually traded at" audit pass on the existing hypothesis scripts, not just at entry/exit.

**Action needed before staging a hypothesis**: audit 2-3 existing high-conviction production scripts (h112_monthly.py, h181_monthly.py) for whether any rolling-window signal calculation could include a non-tradable price point given our data sources (yfinance/Alpaca), before deciding whether this is a real gap or already handled implicitly by using adjusted-close from a survivorship-bias-free source.