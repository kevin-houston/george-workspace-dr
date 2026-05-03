# R29 LLM Filter v2 — Implementation Spec

**Source:** arXiv:2602.07048 (Kim et al., Feb 2026) — "LLM as a Risk Manager: LLM Semantic Filtering for Lead-Lag Trading in Prediction Markets"
**Staged:** 2026-04-14 | **Applied to spec:** 2026-04-15

---

## Core Finding

The LLM's primary contribution in pairs/lead-lag filtering is **LOSS REDUCTION** (~46.5% avg loss cut), not win rate improvement (+3pp). The current binary threshold architecture (score >= 40 → trade) is suboptimal. Switch to **continuous ranking + top-N selection**.

**Paper result:** Granger top-100 → LLM re-rank → trade top-20. Win rate: 51.4%→54.5%. Avg loss: -$649→-$347. Total PnL: +205%.

---

## Changes Required for R29 LLM Filter

### 1. Remove hard binary verdict — replace with plausibility_score ranking
- ❌ Current: `"verdict": "pass/fail"` with threshold >= 40
- ✅ New: `"plausibility_score": <0-100>` used for RANKING, not thresholding
- Selection logic: rank all candidates by plausibility_score DESC → keep top N (suggest N=10-15 out of all candidates)

### 2. Add co-movement sign prediction
- New field: `"co_movement_sign": +1 or -1`
- LLM predicts whether pair should be positively (+1) or negatively (-1) correlated
- If `co_movement_sign != stat_sign` (from cointegration) → **skip pair** (conservative start)
- This corrects cases where statistical sign is wrong due to noise or regime shift

### 3. Add mechanism_strength field
- Values: `"strong"` / `"moderate"` / `"weak"`
- Use as secondary sort key after plausibility_score

---

## Updated Prompt Structure

```
Given this pair of stocks/assets:
- Asset A (Leader): {leader_ticker} — {leader_description}
- Asset B (Follower): {follower_ticker} — {follower_description}
- Statistical relationship: cointegration spread z-score, historical correlation sign: {stat_sign}

Your task:
1. Assess whether a plausible ECONOMIC mechanism exists for Asset A to lead Asset B's price movements.
2. Predict the expected DIRECTION of co-movement when Asset A moves: +1 (same direction) or -1 (opposite direction).
3. Assign a PLAUSIBILITY SCORE from 0-100 reflecting how confident you are in the economic mechanism (not the statistical correlation).
4. Assign MECHANISM STRENGTH: 'strong' (direct causal link, e.g., supplier-customer, same commodity), 'moderate' (indirect, e.g., sector peers, shared macro factor), 'weak' (speculative).

Focus on business relationships: supply chains, competition, shared input costs, common demand drivers, regulatory exposure. Ignore pure price correlation. Return structured JSON only.

Output format:
{"plausibility_score": <0-100>, "mechanism_strength": "strong|moderate|weak", "co_movement_sign": <+1 or -1>, "mechanism_summary": "<1-2 sentence explanation>"}
```

---

## Selection Logic

```python
# After scoring all candidate pairs:
ranked = sorted(candidates, key=lambda x: x['plausibility_score'], reverse=True)
top_n = ranked[:N]  # N = 10-15 (tunable)

# Filter mismatched signs (conservative):
tradeable = [p for p in top_n if p['co_movement_sign'] == p['stat_sign']]
```

---

## Key Paper Details (Kim et al. 2026)
- Dataset: Prediction market pairs, 18 rolling evaluation windows
- Best hold period: 1d (WR 66.7% hybrid)
- Model: GPT-5-nano; results robust across GPT-5-mini
- Effect robust: +205% PnL vs pure statistical filtering
