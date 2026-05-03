# Multi-Agent LLM Architectures for SEC Financial Document Processing
**Source:** https://arxiv.org/abs/2603.22651
**Date found:** 2026-04-05
**Relevance:** Benchmarks 4 orchestration patterns × 5 LLMs on 10,000 SEC filings (10-K, 10-Q, 8-K). Provides the cost-accuracy tradeoff map for building an EarningsQualityAgent in R28.

## Key Findings
- **4 patterns tested**: Sequential Pipeline, Parallel Fan-Out, Hierarchical Supervisor-Worker, Reflexive Self-Correcting
- **Winner on cost-accuracy frontier**: Hierarchical Supervisor-Worker — achieves 98.5% of reflexive F1 (0.929 vs 0.943) at 60.7% of the cost ($0.261 vs $0.430/doc)
- **Budget option**: Hierarchical-Optimized (semantic caching + model routing) recovers 89% of reflexive gains at 1.15× sequential cost ($0.148/doc, F1 0.924)
- **Reflexive self-correcting**: Best accuracy but degrades catastrophically above 25K docs/day — not suitable for large-scale batch backtests

## LLM Performance by Model
- Claude 3.5 Sonnet: F1 0.929 (hierarchical), $0.261/doc
- GPT-4o: F1 0.921 (hierarchical), $0.290/doc
- Llama 3 70B: F1 0.869 (hierarchical), $0.054/doc — best open-source option
- Mixtral 8x22B: F1 0.843 (hierarchical), $0.044/doc — cheapest

## Key Error Modes to Watch
- Cross-table reference failures (28% of sequential errors)
- Ambiguous disclosure resolution (39% of reflexive errors)
- Temporal confusion: FY vs quarterly data — build explicit date-parsing guards
- Unit/scale mismatches (thousands vs millions) — plague all architectures

## Practical Application for R28 EarningsQualityAgent
1. Use **hierarchical orchestration**: supervisor routes to specialized sub-agents by field type
2. Earnings quality fields (accruals, one-time items) are NOT in the benchmark's 25 fields — must add domain-specific prompt logic as **hard constraints outside the LLM pipeline**
3. For backtesting (small volume, ~100-300 filings): **reflexive pattern is fine** — degradation only kicks in at 25K+ docs/day
4. Cost budget: ~$0.15–0.26 per filing at production quality; Llama 3 70B saves ~80% with modest accuracy loss
5. Implement confidence-gated retries: flag low-confidence extractions for re-processing with a stronger model
