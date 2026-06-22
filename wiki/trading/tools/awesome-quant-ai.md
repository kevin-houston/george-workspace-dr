---
added: 2026-06-21
updated: 2026-06-21
type: resource-list
source: https://github.com/leoncuhk/awesome-quant-ai
stars: 377
license: Apache-2.0
---

# awesome-quant-ai

Curated list of resources for quantitative investment and trading strategies using AI/ML. GitHub: https://github.com/leoncuhk/awesome-quant-ai

---

## Strategy Taxonomy

10 categories covered:

| Category | Description |
|----------|-------------|
| Statistical Arbitrage | Pairs, cointegration, mean-reversion |
| Factor Investing | Alpha factors, ML factor construction |
| High-Frequency Trading | Market microstructure, order flow |
| Trend Following | CTA-style momentum, breakout |
| Volatility Trading | Vol surface modeling, variance risk premium |
| Risk Parity | Equal-risk contribution, regime-adaptive |
| Macro | Rate regimes, cross-asset allocation |
| Event-Driven | Earnings, M&A, NLP on filings |
| ML/AI | Deep learning, RL, LLM agents |
| Multi-Strategy | Portfolio construction, ensemble methods |

## Trading Paradigms Comparison

| Paradigm | Signal Source | Execution | Timescale | Our Work |
|----------|--------------|-----------|-----------|----------|
| Quantitative | Statistical/mathematical models | Rule-based | Daily–monthly | H026, H045, H041a, H292 |
| Algorithmic | Technical signals + rule triggers | Automated orders | Intraday–daily | H301, H274 |
| AI-Agent | LLM reasoning + multi-agent debate | Autonomous | Any | H274, H279–H281 |

## Frontier Section (2025–2026)

### LLM-Based Trading Agents
- **TradingAgents** (arXiv:2412.20138) — multi-agent debate architecture; in our wiki at [multi-agent-llm-trading.md](../algorithms/multi-agent-llm-trading.md)
- **FinRobot** — cross-institutional financial AI agent
- **FinGPT** — open-source financial LLM (vs proprietary Bloomberg GPT)
- **FinRL** — DRL for finance; includes trading environment gym wrappers
- **Vibe-Trading** — already our MCP stack (`mcp__vibe-trading__*`); featured as notable platform

### Time-Series Foundation Models
Pre-trained on massive TS corpora; zero-shot or fine-tune for price forecasting:

| Model | Source | Notes |
|-------|--------|-------|
| Chronos | Amazon | General TS; probabilistic; strong zero-shot |
| TimesFM | Google | 200M param; univariate patching |
| Moirai | Salesforce | Multi-variate; unified input space |
| Lag-Llama | Mila | Lag-based tokenization; pretrained |
| PatchTST | PatchTST paper | Patch-based transformer; supervised |
| TimeGPT | Nixtla | API-first; instant inference |

**Relevance:** H279/H280 explore LLM signals; TS foundation models are an adjacent path worth prototyping — could serve as a price-forecast signal layer feeding our existing alpha rotation framework.

### Diffusion Models for Synthetic Data
- **DeepMarket** — generates realistic synthetic limit order book data
- **FinDiff** — tabular financial data generation (augmentation, privacy)
- **FTS-Diffusion** — financial time series diffusion; realistic OHLCV generation

**Relevance:** Synthetic data solves the data scarcity problem for rare-regime training (e.g., crash conditions). Could augment backtests without look-ahead — data is generated offline.

### On-Chain / DeFi
- **Flashbots** — MEV research; auction mechanisms
- **DefiLlama** — DeFi TVL and protocol analytics data source

## Data Providers Highlighted

New sources not in our current stack:
- **CoinPaprika** — comprehensive crypto market data (price, volume, exchange data)
- **DexPaprika** — DEX/on-chain liquidity data from decentralized exchanges
- **Adanos** — alternative data platform (sentiment, news, events)

Existing sources confirmed: Polygon, FRED, Alpaca, EDGAR, Yahoo Finance.

## Notable Papers Referenced

Cross-referenced with our hypothesis log:
- arXiv:2412.20138 (TradingAgents) — H274, in [multi-agent-llm-trading.md](../algorithms/multi-agent-llm-trading.md)
- arXiv:2510.26228 (LLM momentum filter) — **H279** (staged)
- arXiv:2604.17327 (MarketSenseAI 4-agent) — **H280** (staged)
- arXiv:2606.08283 (macro-LLM ETF tilt) — **H281** (staged)
- SSRN:6630998 (Stosik & Zaremba cross-sectional momentum) — H181, H313 tested

## Relevance to Project

This repo is a navigator for the AI quant research frontier. Key connections:

- **Stat arb / pairs trading** — same fundamental approach as H152–H160/H246 (our failures). The repo lists cointegration tools but doesn't address the structural break problem. Our H316 (LLM semantic pre-filter) is a proposed fix not covered here.
- **Event-driven NLP** — aligns with H163/H174 (FinBERT 8-K confirmed) and H175 (speaker-weighted, not confirmed)
- **LLM agent paradigm** — the 3 staged hypotheses (H279–H281) draw on papers this repo curates
- **TS foundation models** — an unexplored angle; Chronos/TimesFM could plug in as a signal layer alongside momentum without replacing the existing alpha framework
- **Synthetic data** — diffusion models could help with regime simulation for strategy stress-testing

## See Also

- [Quant Firm Repos](quant-firm-repos.md) — curated list of quant firm open-source repos
- [Multi-Agent LLM Trading](../algorithms/multi-agent-llm-trading.md) — deep dive on TradingAgents, HedgeAgents, MadEvolve
- [Pairs Trading — KidQuant Notebook](../../sources/pairs-trading-kidquant.ipynb) — classic cointegration tutorial (see H152–H160 for why IS cointegration fails OOS)
- [Hypothesis Log](../backtesting/hypothesis-log.md) — H279/H280/H281 staged from this source
