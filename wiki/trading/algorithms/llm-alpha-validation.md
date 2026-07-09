---
title: Alpha Illusion — LLM Trading Agent Validation Checklist
description: 6 structural validity tests from Sheng et al. 2025 (arXiv:2605.16895) that must be passed before LLM trading agent alpha claims are considered deployment evidence
added: 2026-07-08
category: llm-trading
source_paper: arXiv:2605.16895
---

# Alpha Illusion — LLM Trading Agent Validation Checklist

**Source:** Sheng et al. (2025) "The Alpha Illusion: Why LLM-Based Trading Agents Fail in Practice" arXiv:2605.16895

Systems audited in the paper: FinCon, FinMem, TradingAgents, FinAgent, QuantAgent, FLAG-Trader.

The paper documents that LLM trading agent Sharpe ratios reported in literature (often >2.0) routinely fail one or more of these 6 tests when examined. Apply this checklist to all LLM-based hypotheses before advancing to paper trading.

---

## The 6 Structural Validity Tests

### 1. Temporal Integrity (Look-Ahead)

- [ ] All signals use only data available at the time of signal generation
- [ ] Training set does NOT include any data from the OOS evaluation period
- [ ] For RAG systems: the knowledge base must be time-indexed; no documents postdating T=0 are retrievable at T
- [ ] For LLM context windows: confirm no future earnings, prices, or events appear in prompt

*Failure mode:* Agent trained with knowledge of "2022 bear market" but evaluated as if it's 2021.

### 2. Real-World Frictions

- [ ] Commissions and spread modeled (minimum 5bps round-trip per shared-eval-checklist.md)
- [ ] Market impact modeled for any position > 0.5% daily volume
- [ ] Short borrow costs included if strategy has short legs
- [ ] Overnight funding costs for any leveraged or derivative positions
- [ ] Bid-ask half-spread added for options strategies

*Failure mode:* LLM strategy generates 400%+ CAGR assuming costless execution; falls to SPY-like returns with 5bps costs.

### 3. Counterfactual Robustness

- [ ] Strategy outperforms **buy-and-hold SPY** over the OOS period
- [ ] Strategy outperforms **equal-weight** across the universe
- [ ] Strategy outperforms a **random selection** baseline (run 1000 random seeds)
- [ ] Ablation: does removing the LLM component (using a simple rule instead) degrade performance? If not, the LLM is redundant

*Failure mode:* Agent beats a cherry-picked comparison but loses to the 60/40 portfolio.

### 4. Predictive Calibration

- [ ] High-confidence trades (top confidence quartile) outperform low-confidence trades (bottom quartile) in OOS
- [ ] Stated probabilities are calibrated: a "70% confident long" wins ~70% of the time
- [ ] Confidence-sorted bins show monotonic return improvement

*Failure mode:* Agent claims high confidence on losers; confidence score is uncorrelated with outcomes.

### 5. Numerical Execution

- [ ] All required positions can actually be filled: check daily volume vs. position size
- [ ] All instruments are tradeable at the time of signal (no delisted, halted, or thinly-traded instruments)
- [ ] Fill prices are realistic: use VWAP or next-open, not mid-point of bid-ask
- [ ] No implicit assumption of unlimited liquidity at the exact price stated

*Failure mode:* Strategy requires $500k position in a stock with $100k daily volume.

### 6. Multi-Agent Disaggregation (for ensemble systems)

- [ ] Remove each agent from the ensemble; measure performance degradation
- [ ] Every agent should contribute uniquely: removing it should measurably hurt
- [ ] High inter-agent correlation (>0.8) indicates redundancy, not complementarity
- [ ] Ablation should distinguish: is the ensemble better because of collaboration, or because one agent is carrying the rest?

*Failure mode:* 5-agent ensemble; removing 4 of them doesn't hurt — one agent was doing all the work.

---

## Application to George's Confirmed and Proposed Hypotheses

| Hypothesis | Type | Temporal | Frictions | Counterfactual | Calibration | Execution | Multi-Agent | Notes |
|-----------|------|----------|-----------|----------------|-------------|-----------|-------------|-------|
| H274 PEAD multi-agent debate | LLM | ✗ needs check | ✓ via H174 | ✓ vs H174 baseline | ✗ not yet tested | ✓ small-cap excluded | ✗ not ablated | Phase 2 gate: ablate each agent |
| H381 AlphaLogics | LLM | ✗ critical risk | ✗ needs cost model | ✗ vs H198 baseline needed | ✗ N/A (code gen) | ✗ check position sizes | ✗ N/A (generator) | API cost check also needed |
| H382 FactorEngine | LLM | ✗ critical risk | ✗ needs cost model | ✗ vs H198 baseline needed | ✗ N/A | ✗ check sizing | ✗ N/A | Same temporal risk as H381 |
| H383 HMM+RL | ML/RL | ✓ filtered probs | ✗ model rebalancing costs | ✓ vs H311 | ✗ not applicable | ✓ ETF universe liquid | ✗ N/A (single model) | Use filtered not smoothed HMM |
| H384 ReCAP | ML/RL | ✓ change-point | ✗ needs turnover model | ✗ vs H026 baseline needed | ✗ N/A | ✓ ETF universe | ✗ N/A | HIGH RISK — production H026 |

---

## Integration with Shared Evaluation Checklist

This checklist extends `wiki/trading/shared-eval-checklist.md` for LLM-specific systems. Apply in addition to, not instead of, the 7-point gate and the 7-dimension reproducibility audit (arXiv:2606.08285).

**Minimum gate before paper trading for any LLM strategy:**
- All 6 tests must pass, OR
- Any failing test must be explicitly documented with a written justification for why the failure is acceptable in this context

---

## Cross-References

- `wiki/trading/algorithms/multi-agent-llm-trading.md` — synthesis of multi-agent LLM trading research
- `wiki/trading/shared-eval-checklist.md` — shared 7-point gate + LLM reproducibility audit
- H274 (multi-agent PEAD), H381 (AlphaLogics), H382 (FactorEngine), H383 (HMM+RL), H384 (ReCAP)
- arXiv:2606.08285 — "7-Dimension Reproducibility Audit" for LLM trading systems (already in shared-eval-checklist.md)
