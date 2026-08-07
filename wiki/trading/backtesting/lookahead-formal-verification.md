---
type: backtesting-methodology
title: Look-Ahead-Freedom as Temporal Non-Interference
description: Formal computer-science treatment of look-ahead bias detection in backtesting and agentic trading pipelines. Linear-time type-and-effect checker catches leaks that statistical detectors miss.
tags: [backtesting, look-ahead-bias, formal-verification, agentic-trading, pipeline-integrity]
updated: 2026-08-07
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
---

## Research Lead: Lookahead Propensity (LAP) — A Concrete Statistical Test for LLM Memorization Leaks (arXiv:2512.23847, flagged 2026-08-04)

"Detecting Lookahead Bias in LLM Forecasts" (Zhenyu Gao, Wenxi Jiang, Yutong Yan; submitted Dec 2025, revised Jun 2026) fills a specific gap this page already names but doesn't resolve: Fonseca's formal type-and-effect checker (above) explicitly addresses agentic retrieval and knowledge-cutoff leaks in principle, but implementing a full type-and-effect verifier is a heavier lift than George's pipeline currently has. This paper offers a lighter-weight, immediately runnable statistical test for exactly one leak category: **has an LLM silently memorized the realized outcome of a specific firm-date pair from its training data, rather than genuinely inferring it from the input text?**

### The method

1. **Lookahead Propensity (LAP)**: a per-(firm, date) score estimating how likely it is the LLM's training corpus contained information about the *realized* outcome (not just the input text being scored). Measured via date-only recall queries -- asking the model what it "knows" about a firm/date without revealing the outcome, and checking whether it leaks post-hoc information.
2. **Regression test**: run `forecast_accuracy ~ LAP + LLM_forecast + LAP*LLM_forecast`. A significant positive interaction term means forecast accuracy is inflated specifically on high-LAP pairs -- i.e., the model does better exactly where it's more likely to have memorized the answer.
3. **Temporal validation**: the diagnostic signature of genuine contamination is that this interaction effect is large during the training period and **collapses to approximately zero immediately after the training-data cutoff**. If accuracy on high-LAP pairs stays elevated post-cutoff, that's evidence of real signal, not memorization.

Tested on two applications directly analogous to George's own pipeline: news headlines predicting stock returns, and **earnings call transcripts predicting capital expenditures** -- functionally the same task shape as H163/H174's 8-K text scoring for PEAD.

### Direct applicability to H163/H174

The FinBERT model (`ProsusAI/finbert`) used in `pead_overnight.py`/`pead_intraday.py` has a fixed, known training cutoff. This gives George a concrete, cheap audit to run against the existing H174 track record (81.8% OOS win rate, n=22):

- Split H174's confirmed events into pre-cutoff and post-cutoff subsets relative to FinBERT's training data cutoff date.
- If win rate / mean return is concentrated in the pre-cutoff subset and degrades toward the post-cutoff subset, that's the LAP contamination signature -- meaning some of H174's apparent edge may be the model recognizing rather than analyzing specific 8-Ks it saw in training.
- If win rate is stable (or improves) across the cutoff boundary, that's a genuine positive finding this page doesn't currently have: independent evidence H174's edge is real text-based signal, not memorization. n=22 is thin for a clean split, but it's the right test to run before scaling H174 further or before H274's agentic debate design pulls in a more capable general-purpose LLM (which has a *much* larger and more recent training corpus, and correspondingly higher LAP risk than a narrow FinBERT classifier).

### Why this is lower risk for H274 than for H174

H174 uses FinBERT, a relatively narrow sentiment classifier with a specific, dated training cutoff and no general world-knowledge memorization incentive. H274's proposed multi-agent debate design (see multi-agent-llm-trading.md) would likely use general-purpose LLMs with much broader training corpora and more recent cutoffs -- exactly the profile this paper flags as higher-LAP-risk. **Any H274 implementation should budget a LAP-style audit before going to paper trading**, not just the existing look-ahead formal-verification checklist items (EDGAR filed-date gating, `.shift(1)` discipline), since those catch pipeline-structural leaks but not model-memorization leaks.

### Practical protocol (approximate, pending full LAP implementation)

```python
# Cheap proxy check before a full LAP implementation:
# 1. Identify the LLM's training cutoff date
# 2. Split historical signal-generation events into pre/post cutoff
# 3. Compare OOS win rate / mean return across the split
# Large pre-cutoff outperformance that vanishes post-cutoff = contamination signature
```

**Not staged as a new hypothesis** -- this is an audit methodology for existing (H174) and proposed (H274) LLM-based strategies, not a new alpha signal. Filed as a pre-requisite check: run before H274 implementation, and as a retroactive sanity check on H174's existing track record.

## See Also (LAP addition)

- [LLM Alpha Validation Checklist](../algorithms/llm-alpha-validation.md) — natural home for a LAP-audit step alongside the existing look-ahead audit test
- [PEAD — Post-Earnings Announcement Drift](../algorithms/pead.md) — H174 pipeline this audit would run against
- [Multi-Agent LLM Trading](../algorithms/multi-agent-llm-trading.md) — H274 design, higher LAP risk than H174 per above

---

## Research Lead: FinCAD — Inference-Time Mitigation for Parametric Look-Ahead Bias (2026-08-06)

**Source**: Li, Wang & Ma (University of Edinburgh), "Summoning the Oracle to Slay It: Mitigating Look-Ahead Bias in Financial Backtesting with Large Language Models," arXiv:2605.24564, submitted May 23 2026.

Where this page's Fonseca formalization (arXiv:2607.04958) treats look-ahead bias as a temporal-non-interference property to *detect* via a type-and-effect checker on data pipelines, FinCAD addresses a distinct sub-class this page hadn't yet covered: **parametric look-ahead bias** -- an LLM's pretraining corpus already contains the realized outcome of a historical event (e.g. "AAPL rose 8% after its Q3 2019 earnings beat"), so any backtest asking that LLM to forecast or score that same historical event risks the model silently recalling the answer rather than reasoning from the point-in-time inputs it's given. This leak lives inside model parameters, not the data pipeline -- so pipeline-level point-in-time joins and embargo windows (this page's usual toolkit) cannot catch it.

### The fix, not just the diagnosis

FinCAD is an inference-time adaptation of Context-Aware Decoding: it pairs (1) an adversarial bias-discovery pipeline that learns a model-specific "memory-activating" prior prompt per (entity, date), with (2) a decoding-time penalty that suppresses tokens consistent with the memorized outcome, scaled by how much that specific (entity, date) pair appears memorized, and decaying to zero for genuinely out-of-sample dates.

**Reported results** (5 open-weight 7-14B LLMs × 5 mega-cap equities): in-sample backtest returns on memorized dates cut by up to -67.1%; true 2025 OOS returns and Sharpe left within ~0.10 of an uncorrected baseline; general-purpose reasoning benchmarks preserved within 1.7 points.

### Relevance to George's LLM-alpha pipeline

Every hypothesis that puts an LLM in the forecast/scoring loop over historical data is exposed to this failure mode, and none of the existing gates catch it directly:

- **H174 PEAD FinBERT scorer** — lower risk: FinBERT is a small BERT-class classifier fine-tuned on sentiment labels, not a generative LLM with broad pretraining recall of specific stock-move outcomes, but the general concern (does the model's score reflect the text, or a memorized prior about that company/date?) is the same class of question.
- **H185 Kalshi/Polymarket LLM forecasting** (queued, PolySwarm Phase 2) — high risk: if backtested against resolved historical markets, a frontier LLM may already "know" how many of them resolved.
- **H381-H384 LLM alpha-mining agents** (AlphaLogics, FactorEngine, HMM+RL, ReCAP) — the Agentic Trading Survey (arXiv:2605.19337, already in wiki) flags exactly this class of leak as part of the reproducibility crisis; FinCAD is a concrete tool to add to the LLM Alpha Validation Checklist's look-ahead audit step.
- **H408 agentic earnings retrieval** — any backtest over historical earnings-call transcripts with a generative LLM in the loop shares the same exposure.

### Caveat

Tested only on open-weight 7-14B models where CAD needs decoding-time logit access. George's stack primarily calls frontier closed-weight models (GPT-4o-class via `$OPENAI_API_KEY`, Claude) through standard chat-completion APIs that do not expose the sampling internals FinCAD's penalty operates on -- so FinCAD as implemented is **not directly applicable** to George's current LLM-alpha designs without either (a) an open-weight model substitution for the backtest-scoring step, or (b) a black-box analog. See HindsightBench (companion research lead, this same 2026-08-06 scan) for a black-box detection method that doesn't require logit access -- useful as a cheaper first gate even where FinCAD's fix can't be applied directly.
