# MarketSenseAI 2.0: LLM Agents + RAG for Stock Analysis
**Source:** https://arxiv.org/abs/2502.00415
**Date found:** 2026-04-05
**Relevance:** 5-agent RAG system for stock analysis achieves Sharpe 2.13–2.87 on S&P 100/500 with monthly rebalancing. The Fundamentals Agent processes SEC filings + earnings call transcripts sequentially — the exact data pipeline needed for R28's EarningsQualityAgent.

## Key Findings
- Sharpe ratios: **2.13–2.87** (equally- to cap-weighted) on S&P 100 (2023-2024) vs benchmark 1.89–2.52
- S&P 500 (2024): Sharpe **2.4–2.87** vs benchmark 1.33–2.26
- Win rate **~77–78%** across all configurations; ~35 buy signals/month for S&P 100
- Monthly rebalancing; cumulative return 125.9% vs benchmark 73.5% over 2023-2024

## Architecture (5 Sequential Agents)
1. **News Agent**: Daily articles → progressive summary
2. **Fundamentals Agent**: 10-Q/10-K/8-K → sequential LLM processing: (a) filing summary → (b) earnings call summary → (c) consolidation with 5 quarters of numerical data
3. **Dynamics Agent**: Price, volatility, Sharpe vs peers/S&P 500
4. **Macroeconomic Agent**: Central bank + institutional macro reports
5. **Signal Agent**: Chain-of-Thought synthesis → buy/hold/sell with reasoning

## RAG Details
- **Retrieval method**: Hypothetical Dense Embeddings (HyDE) — generates a hypothetical answer then retrieves documents semantically similar to it
- Context precision ≥ 0.98; HyDE outperforms simple retrieval in answer relevancy (0.76 vs 0.48)
- Storage: Pinecone vector DB + LlamaIndex; sentence-transformers for embeddings
- EDGAR API (free) for SEC filings; earnings transcripts via RapidAPI aggregators

## Practical Application for R28
- **EarningsQualityAgent design**: Follow the Fundamentals Agent's 3-step pipeline: (1) summarize 8-K/10-Q, (2) summarize earnings call Q&A, (3) consolidate with 5 quarters of EPS history
- **Free data path**: EDGAR EFTS API for 8-K filings, SeekingAlpha/Motley Fool for transcript fragments, FRED for macro context
- Open-source LLM substitution: quality drops modestly (Llama 3 70B F1 0.869 vs GPT-4o F1 0.921 on extraction tasks) — use Claude/GPT for quality ratings, Llama for summarization
- HyDE retrieval can be implemented with sentence-transformers + FAISS (fully local, free)
