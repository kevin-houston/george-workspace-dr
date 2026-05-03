# Knowledge Base Index
**Last compiled:** 2026-04-12
**Topics:** 13

| Topic | File | Summary |
|-------|------|---------|
| Trading Strategies Leaderboard | trading-strategies-leaderboard.md | Master reference of all ~7,000+ backtested strategies with Sharpe ratios, CAGRs, and category champions. Includes the full ranked table and meta-lessons. |
| PEAD Strategy | pead-strategy.md | Post-Earnings Announcement Drift: the highest portfolio Sharpe strategy (2.394). Signal definition, implementation, R26 LLM filter findings, R30 elastic net results, and R28/R31 upcoming enhancements. |
| Pairs Trading | pairs-trading.md | Statistical arbitrage: 10-pair portfolio Sharpe 0.964, Max DD -11.90%, SPY correlation 0.05. Z-score mechanics, best pairs book, R29 LLM semantic filter design with factor residual decomposition. |
| Dividend Strategies | dividend-strategies.md | Dividend raise signal (Sharpe 4.403 — highest in corpus), covered calls around ex-div (2.643), dividend capture (1.578), Dogs of the Dow. Mechanics and implementation guide. |
| Crypto Momentum | crypto-momentum.md | SOL 20d momentum (Sharpe 1.682, CAGR 205.8%, Max DD -71.4%). Market inefficiency findings, sizing constraints (2-5% max), BTC consistency advantage. |
| Options Strategies | options-strategies.md | R25 covered calls and R28 deep dive (bull put spreads, iron condors, VIX puts, wheel). IV rank as the master filter. R32 index put-writing design with VIX-Kelly hybrid sizing. |
| ML for Trading | ml-for-trading.md | Random Forest on XOM Sharpe 1.744 (best ML). TimesFM zero-shot = buy-and-hold (no alpha). ModernTCN wins DL benchmark but directional accuracy ~50% across all architectures. |
| LLM Signal Research | llm-signal-research.md | R26 findings: LLM IndicatorAgent hurts PEAD (confirmed 0.716 vs rejected 0.904). When LLM helps (pairs, RAG-grounded) vs hurts (bare technical filtering, regime timing). FINSABER, QuantAgent, FinBERT sentinel. |
| Research Agenda | research-agenda.md | Active pipeline: R28-R32 COMPLETED 2026-04-11. R33 (LLM Financial Statement Analysis + PEAD catalyst) is next — highest priority. Design specs and hypotheses for all rounds. |
| AI Research Papers | ai-research-papers.md | Curated index of papers from dream cycle research: Kim/Muhn/Nikolaev (2024) LLM financial statements, QuantAgent, FINSABER, PEAD.txt, Attention Factors, TradingAgents, mem-agent, ERL, AlphaLogics, and others. Each with application to Kevin's work. |
| Portfolio Allocation | portfolio-allocation.md | Recommended allocation: 25% PEAD, 25% Pairs, 15% Dividend Raise, 15% Risk Parity, 10% Crypto, 5% ETF Macro, 5% Pre-Holiday. Rationale, rebalancing rules, macro overlay rules. |
| Heuristics | heuristics.md | Generalizable lessons distilled from all past research and engineering work. Organized by domain: Tools & Environment, Research & Backtesting, Podcast Pipeline, Memory & Self-Improvement. |
| Tools & APIs | tools-and-apis.md | External services and APIs: ChartLibrary (chart pattern similarity search, 24M embeddings, MCP server, free sandbox tier). |

---

## Quick Reference: Top 5 Strategies by Sharpe

| Rank | Strategy | Sharpe | Category |
|------|----------|--------|----------|
| 1 | Div Raise >=10% hold-40d | +4.403 | Dividend |
| 2 | Div Raise >=5% hold-40d | +3.400 | Dividend |
| 3 | CC around Ex-Div 10d | +2.643 | Dividend+Options |
| 4 | Bull Put Spread XOM | +2.584 | Options |
| 5 | PEAD Portfolio | +2.394 | PEAD |

## Quick Reference: Active Research Queue

| Round | Topic | Status |
|-------|-------|--------|
| R28 | TradingAgents multi-agent overlay on PEAD | COMPLETED 2026-04-11 |
| R29 | LLM semantic filter on equity pairs | COMPLETED 2026-04-11 |
| R31 | Text-based PEAD (FinBERT on transcripts) | COMPLETED 2026-04-11 |
| R32 | Systematic SPX put-writing, VIX-Kelly sizing | COMPLETED 2026-04-11 |
| R33 | LLM Financial Statement Analysis + PEAD catalyst | QUEUED — next (highest priority) |
