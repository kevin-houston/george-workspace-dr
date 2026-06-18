---
updated: 2026-06-18
type: tool-guide
source: https://github.com/BlockRunAI/awesome-finance-mcp
---

# Awesome Finance MCP

Curated list of MCP servers and AI skills for finance, trading, and crypto agents. Maintained by BlockRun. Noted by Kevin 2026-06-18.

**Related pages**: [LEAN / QuantConnect](lean-quantconnect.md) | [Alpaca Markets](../data-sources/alpaca.md) | [Crypto Data Sources](../data-sources/crypto-data-sources.md) | [NLP & Alternative Data](nlp-alternative-data.md)

---

## High-Priority for This Project

These are immediately relevant given our existing API keys and active hypotheses:

### 1. Alpaca MCP — `alpacahq/alpaca-mcp-server`
**Stars:** active | **Cost:** Free (commission-free)
- Official Alpaca MCP server — stocks, ETFs, options trading + data analysis
- We run Alpaca paper trading live (PEAD entries/exits, H026 monthly rebalance)
- **Action:** Install this. Replaces manual `requests` calls to Alpaca REST in `pead_open.py` / `pead_exits.py` with native MCP tools

### 2. Financial Modeling Prep MCP — `imbenrabi/Financial-Modeling-Prep-MCP-Server`
**Stars:** active | **Cost:** Freemium (our $FMP_API_KEY works)
- 250+ tools: income statements, balance sheets, cash flow, market insights
- We already call FMP API in `run_h308.py` (FCF/P), `run_h305.py`, and `pead_overnight.py`
- **Action:** Worth installing. Gives us direct MCP access to fundamentals rather than raw requests. Useful for H308 FCF/P fetching and H305 fundamental features

### 3. FRED MCP — `stefanoamorelli/fred-mcp-server`
**Stars:** active | **Cost:** Free ($FRED_API_KEY in env)
- Federal Reserve Economic Data — macro indicators we use for regime detection
- Currently called via raw requests in H249/H285 macro scripts
- **Action:** Low urgency (raw API works fine) but useful for interactive macro queries

### 4. Massive MCP — `massive-com/mcp_massive`
**Stars:** active | **Cost:** Freemium
- **Already installed** as `mcp__massive__*` — stocks, options, forex, crypto
- Confirmed working. This is our primary real-time market data MCP

---

## Medium Priority

### 5. CCXT MCP — `Nayshins/mcp-server-ccxt`
**Stars:** active | **Cost:** Free
- Data from 20+ crypto exchanges via the CCXT library
- Relevant to H276 (NautilusTrader crypto POC) and any future H302/H303 live crypto work
- Already have `ccxt` in crypto-data-sources.md; MCP wrapper adds interactive access

### 6. QuantConnect MCP — `QuantConnect/mcp-server`
**Stars:** active | **Cost:** Freemium
- Algorithmic trading platform integration (LEAN engine)
- Relevant to H007 (Docker approval pending) and Phase 4 live execution via LEAN
- See [LEAN / QuantConnect](lean-quantconnect.md) for context

### 7. TradingView MCP — `atilaahmettaner/tradingview-mcp`
**Stars:** active | **Cost:** Freemium
- Advanced market analysis, multi-exchange
- Useful for IBS mean-reversion monitoring (XLK/SMH/IGV production positions)

### 8. Alpha Vantage MCP — `alphavantage/alpha_vantage_mcp`
**Stars:** active | **Cost:** Freemium ($ALPHA_VANTAGE_API_KEY in env, 25 req/day)
- Stocks, forex, crypto, technical indicators
- Useful for earnings call transcripts (H168) — we've used AV for this already

---

## Skills (Workflow Layer)

These are task-level workflows built on MCP servers:

| Name | Relevance | Notes |
|------|-----------|-------|
| **Equity Research** (`quant-sentiment-ai/claude-equity-research`) | HIGH | Institutional-grade equity research + buy/sell recs; could wrap H217/H228 signals |
| **Trading Terminal** (`degentic-tools/claude-code-trading-terminal`) | MEDIUM | Agent-native trading with sub-agents; Solana/Jupiter focused — not our stack |
| **Trading Skills** (`tradermonty/claude-trading-skills`) | MEDIUM | IBD-style RS Rating for momentum — overlaps H026/H041a |
| **Claude Investor** (`martinxu9/claude-investor`) | LOW | General investment analysis; we have more targeted H-series signals |

---

## Lower Priority / Not Relevant

- **Personal Finance** (LunchMoney, Monarch Money) — not relevant to trading project
- **DeFi / on-chain** (Binance MCP, Armor Wallet, DeFi Trading) — crypto execution not in scope yet
- **Payments / Banking** (Stripe, Qonto, Ramp) — not relevant
- **Korean/HK stock MCPs** — not our market

---

## Recommended Next Steps

1. **Install Alpaca MCP** — submit `ncl groups config add-mcp-server` for `alpacahq/alpaca-mcp-server`. Most immediately useful: gives us native MCP tools for order management alongside existing Alpaca REST code.
2. **Install FMP MCP** — `imbenrabi/Financial-Modeling-Prep-MCP-Server`. Directly useful for H308 FCF/P data and future H305 fundamental features.
3. **Defer FRED MCP** — raw API works; install only if we start doing interactive macro analysis sessions.
