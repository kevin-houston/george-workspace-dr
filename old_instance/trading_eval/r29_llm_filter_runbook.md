# R29 LLM Semantic Filter — Implementation Runbook

Date: 2026-04-28
Baseline: R29 v1 (residualized + fixed ±2σ): Sharpe 1.3802
Target: Sharpe 1.8–2.4 (expected from arXiv:2602.07048 loss-reduction mechanism)

## Prerequisites
- R29 v1 already completed: /workspace/group/trading_eval/r29_pairs.py
- R29 v1 results: /workspace/group/trading_eval/rounds/r29_pairs_results.json
- 19 cointegrated pairs already identified from residualized returns
- yfinance data, SPY+sector ETF residuals already computed

## Full Pipeline (6 Stages)

### Stage 0 — Factor Residualization (DONE in R29 v1)
- Rolling 60-day OLS: residual_i = return_i - beta_mkt*SPY - beta_sector*sector_ETF
- Already validated: finds 19 cointegrated pairs (vs 1 on raw returns)

### Stage 0.5 — Asymmetric Beta Filter (NEW from arXiv:2604.22933)
- For each candidate pair (A, B): compute upside_beta_A, downside_beta_A, upside_beta_B, downside_beta_B
  - upside_beta = OLS coefficient of residual_A on residual_B using ONLY days when SPY > 0
  - downside_beta = OLS coefficient using ONLY days when SPY < 0
- Pair-level asymmetry check: |upside_beta_A - upside_beta_B| < 0.4 AND |downside_beta_A - downside_beta_B| < 0.4
- Skip pairs that fail this check — their spread is driven by regime asymmetry, not genuine mean-reversion
- Rolling 63-day window

### Stage 1 — Engle-Granger Cointegration (DONE in R29 v1)
- Test cointegration on residualized return series
- Keep top-100 pairs by p-value rank (extend from 19 to 100 by loosening threshold)

### Stage 1.5 — SAE Company Similarity Filter (from arXiv:2412.02605)
- Download pre-computed SAE features: huggingface.co/marco-molinari/company_reports_with_features
- Filter candidate pairs to same SAE cluster (k-nearest SAE feature neighbors)
- Reduces LLM API cost by eliminating semantically distant pairs before expensive LLM call

### Stage 2 — LLM Plausibility Re-Ranking (TOP-K, not binary threshold)
- For each pair passing Stage 1.5: query LLM with anonymized prompt
- **Anonymization** (MANDATORY, arXiv:2603.17692): Replace tickers with business descriptions from SEC 10-K first paragraph
  - Example: 'COMPANY_A is a large-cap US technology company specializing in enterprise software and cloud computing platforms. COMPANY_B is a large-cap US semiconductor company focused on analog and embedded processors for industrial and automotive applications.'
- **Goal-blind prompt** (MANDATORY, arXiv:2602.09504): Do NOT mention 'trading', 'PEAD', 'spread', 'arbitrage'
  - Frame as: 'Evaluate the economic relationship between these two companies as a fundamental analyst.'
- **6-Category Taxonomy prompt** (arXiv:2604.19476):
  ```
  COMPANY_A: [description]. COMPANY_B: [description].
  Classify the economic relationship between these two companies and assess its strength.
  Output JSON: {
    "relationship_type": <one of: competitor, supply_chain, peer, substitute, complement, unrelated>,
    "mechanism_strength": <0-100>,
    "expected_co_movement_sign": <+1 if they move together over time, -1 if they diverge>
  }
  Focus exclusively on structural economic relationships. Do not reference recent price performance.
  ```
- **Veto rules**:
  - Skip if relationship_type in ['competitor', 'substitute', 'unrelated'] AND mechanism_strength < 60
  - Skip if expected_co_movement_sign = -1 AND observed spread direction implies +1 movement
- **Re-ranking**: Rank surviving pairs by mechanism_strength DESC. Trade TOP-20.
- **VIX kill switch** (MANDATORY, arXiv:2604.10996): If VIX > 25, SKIP LLM stage entirely — use Stage 1.5 SAE-filtered pairs directly
- **Model**: Claude-Sonnet-4.6 preferred; Claude-Haiku as fallback if quota limited

### Stage 3 — Trade Execution
- Fixed ±2σ z-score entry/exit (NOT OU-calibrated — R29 v1 confirmed fixed wins)
- Entry: |z-score| > 2.0; Exit: |z-score| < 0.5
- Equal-weight across top-20 pairs
- Rebalancing: Monthly (lower turnover than daily; reduces implementation cost)

### CMMD Contamination Check (VALIDATION BEFORE CLAIMING IMPROVEMENT)
- Run same LLM prompts on Llama-3.1-8B-Instruct (different training cutoff)
- Compare signal quality: 2018-2022 (likely in LLM training) vs 2023-2025 (less memorized)
- If Sharpe significantly higher in 2018-2022 → contamination flag → discount Sharpe claim
- Source: arXiv:2603.26797 (MemGuard-Alpha)

## Expected Cost
- 100 LLM calls per rebalancing × $0.003/call (Sonnet-4.6) × 12 months = ~$3.60/year
- SAE feature download: one-time, free from HuggingFace
- No new data sources required

## Hypothesis
- R29 LLM filter Sharpe target: 1.8–2.4 (vs R29 v1 baseline 1.38)
- Primary mechanism: 46.5% reduction in large loser trades (arXiv:2602.07048)
- Secondary mechanism: Exclusion of competitor/substitute pairs that diverge (arXiv:2604.19476)
- Tertiary mechanism: Asymmetric beta pre-filter removes regime-driven spurious spreads (arXiv:2604.22933)
