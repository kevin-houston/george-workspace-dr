---
added: 2026-06-11
category: tools/multi-agent-trading
url: https://github.com/FinStep-AI/ContestTrade
arxiv: 2508.00554
license: Apache 2.0
status: active (V2.0 released, US market support added)
---

# ContestTrade — Multi-Agent Trading via Internal Contest Mechanism

**ContestTrade** (FinStep-AI) is a multi-agent event-driven trading framework with a published arXiv paper (arXiv:2508.00554, Zhao et al. 2025). The novel design element is an **internal contest mechanism** — rather than agent consensus or debate, agents compete in two rounds and only winning insights advance to the next stage.

---

## Architecture — dual-stage contest pipeline

```
Raw Market Data
      ↓
[Stage 1: Data Team]
  N × Data Analysis Agents → "Text Factors"
  ↓ Internal Contest (factor quality scoring)
  Best factor portfolio selected
      ↓
[Stage 2: Research Team]
  N × Research Agents (each with unique "Trading Belief")
  → parallel deep analysis + trade proposals
  ↓ Internal Contest (proposal quality scoring)
  Unified asset allocation strategy output
```

**Stage 1 — Data Processing:**
- Multiple Data Analysis Agents work in parallel
- Each converts raw data into structured "text factors" (news impact, capital flow, policy signals, announcements)
- Internal contest evaluates factor quality → optimal factor portfolio selected

**Stage 2 — Research Decision:**
- Multiple Research Agents with distinct "Trading Beliefs" analyze the factor portfolio
- Each submits a trade proposal (up to 5 signals per belief)
- Second internal contest evaluates proposals → synthesizes unified allocation

---

## Trading Beliefs (customizable agent personalities)

Each Research Agent runs a distinct "belief" — the user defines these in `belief_list.json`:

```json
[
  "Focus on short-term event-driven opportunities: prioritize company announcements, M&A, order surges, tech breakthroughs; prefer small/mid-cap high-volatility momentum stocks.",
  "Focus on steady certainty events: dividends, buybacks, confirmed earnings beats, major contracts; prefer large-cap low-volatility blue chips."
]
```

The system runs one Research Agent per belief and outputs signals from each. This is how the diversity of multi-agent perspectives is achieved — not by model architecture variation but by prompt-level belief differentiation.

---

## Setup

```bash
git clone https://github.com/FinStep-AI/ContestTrade.git
conda create -n contesttrade python=3.10 && conda activate contesttrade
pip install -r requirements.txt
# OR Docker:
docker run -it --rm --name contest_trade -v $(pwd)/config.yaml:/ContestTrade/config.yaml finstep/contesttrade:v2.0
```

**config.yaml keys:**

| Key | Required | Purpose |
|-----|----------|---------|
| `LLM` | ✅ | General LLM API (any OpenAI-compatible) |
| `LLM_THINKING` | Optional | Complex reasoning model |
| `VLM` | Optional | Visual language model for chart analysis |
| `TUSHARE_KEY` | Optional | China market data (better performance) |
| `BOCHA_KEY` / `SERP_KEY` | Optional | Web search for news |

**Data sources:**
- AKShare (default, free) — primarily China A-share market
- Tushare (optional, paid) — better China coverage
- US stock market support added in V2.0 (maturity unclear vs. China-focused baseline)

**Run:**
```bash
python -m cli.main run
# → Interactive CLI: select market, select analysis time
# → Outputs: trading signals + research reports (Markdown) in agents_workspace/results/
```

---

## Key differences vs. other multi-agent frameworks

| Framework | Multi-agent design | Primary focus |
|-----------|-------------------|---------------|
| **ContestTrade** | Internal contest — competition selects best agents | Event-driven, stock selection |
| MarketSenseAI (H280) | 4 specialist agents + synthesis | Monthly equity signals, S&P 500 |
| H274 PEAD upgrade | 3-agent debate, all-must-agree | PEAD confirmation, 8-K NLP |
| TradingAgents | Hierarchical multi-agent | General equity analysis |

The contest mechanism is architecturally distinct: rather than requiring consensus or running a synthesis agent on all outputs, it uses a scoring/selection layer to promote the best-performing agents. This resembles evolutionary selection more than human committee dynamics.

---

## Relevance to George's work

**Architectural inspiration:**
- The dual-contest pipeline is a novel design pattern for H280 (MarketSenseAI replication) and future multi-agent hypotheses. Instead of MarketSenseAI's flat 4-agent synthesis, a contest layer could select the 1-2 most credible agents before synthesis.
- Could inform an H280b variant: contest-filtered agent outputs → synthesis, rather than equal-weight synthesis

**Event-driven alignment:**
- ContestTrade's core focus (news, announcements, capital flow, policy signals) maps directly to PEAD (H163/H174). The data-team → factor-portfolio → research-team pipeline is essentially what H274 is building, with the contest mechanism as an additional filter layer.

**arXiv paper (2508.00554):**
- Published August 2025. Contains actual backtesting results and methodology. Worth reading for:
  - Contest mechanism performance vs. standard multi-agent (does it actually beat consensus?)
  - Chinese vs. US market results comparison
  - Statistical rigor (IS/OOS split, transaction costs)

**Practical usability for us:**
- US stock support is V2.0-new — less mature than China-focused baseline
- Default data source (AKShare) is China-focused; US integration requires additional config
- Not immediately pluggable into our yfinance/EDGAR/Alpaca stack
- Docker deployment is convenient but adds infrastructure overhead

**Priority**: Medium. Read the arXiv paper first — if the contest mechanism shows statistically significant improvement over standard multi-agent debate, it's worth designing an H-number that tests this on our universe.

---

## Cross-references

- [Multi-Agent LLM Trading Systems](multi-agent-llm-trading.md) — TradingAgents, MarketSenseAI; H274/H280 designs
- [Event-Driven Strategies](../algorithms/event-driven.md) — PEAD H163/H174; ContestTrade's event-driven focus overlaps
- [Machine Learning for Trading](ml-for-trading.md) — LLM-in-the-loop approaches; H279/H280/H281 designs
