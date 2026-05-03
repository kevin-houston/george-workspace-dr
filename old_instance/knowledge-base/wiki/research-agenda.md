# Research Agenda

*The active queue of trading research rounds, hypotheses, and design specs. Rounds 1-30 are complete; Rounds 28-32 are the active pipeline as of 2026-04-05. Each round builds on prior findings — the sequencing matters because R28 tests whether fundamental LLM filtering helps PEAD (R26 showed technical filtering hurt it), and R29 tests LLM on pairs (predicted to work based on different mechanism).*

---

## Status Overview

| Round | Topic | Status | Priority |
|-------|-------|--------|----------|
| R28 | TradingAgents multi-agent overlay on PEAD | COMPLETED 2026-04-11 | Done |
| R29 | LLM semantic filter on equity pairs trading | COMPLETED 2026-04-11 | Done |
| R30 | Multi-quarter SUE elastic net | COMPLETED 2026-04-03 | Done |
| R31 | Text-based PEAD (PEAD.txt methodology) | COMPLETED 2026-04-11 | Done |
| R32 | Systematic SPX put-writing with VIX-Kelly sizing | COMPLETED 2026-04-11 | Done |
| R33 | LLM Financial Statement Analysis + PEAD catalyst | QUEUED — next | Highest |

---

## Round 28: TradingAgents Multi-Agent Overlay on PEAD

**Status**: QUEUED (next to run)
**Inspired by**: TradingAgents v0.2.0 (arXiv:2412.20138, GitHub trending March 2026)
**Hypothesis**: Fundamental/news LLM filter HELPS PEAD (unlike IndicatorAgent which hurt it, per R26)

### Rationale
R26 showed IndicatorAgent filtering hurts PEAD (-0.055 Sharpe) because it uses technical metrics (RSI, SMA, volatility) — exactly what PEAD bypasses. The correct filter should be fundamental quality: Is the earnings gap driven by a real beat or a one-time item? Are institutions actually buying?

### Architecture
1. **EarningsQualityAgent**: Revenue beat %, EPS surprise %, guidance direction. Rates organic beat (buy) vs. one-time item (skip). Score 0-100.
2. **NewsAgent**: Top 3 headlines for the stock on earnings day → sentiment score
3. **RegimeGuard**: Hard rule — skip if VIX > 30 at signal date (already validated in macro harness)

### Key Amendment (from R26 + arXiv:2602.00196 lesson)
Use **mini-RAG corpus per earnings event** (8-K + headlines + guidance) — bare LLM calls hallucinate judgment without grounding. RAG provides the context that makes "organic vs. one-time" distinguishable.

### Data
- Existing PEAD event dataset: 80 events, 15 large-caps, 2021-2025 (from R26)
- ~80 LLM calls total (low cost: ~$0.24 at Claude Haiku prices)

### Success Criteria
- Filtered PEAD Sharpe > 2.394 = hypothesis confirmed
- Filtered PEAD Sharpe < 2.394 = PEAD is filter-resistant (publish as finding)

---

## Round 29: LLM Semantic Filter on Pairs Trading

**Status**: QUEUED (after R28)
**Inspired by**: arXiv:2602.07048 (Feb 2026)
**Hypothesis**: LLM economic plausibility scoring improves pairs by eliminating spurious pairs, reducing average loss magnitude ~40-50%

### Architecture
**Stage 0 — Factor Residual Decomposition** (Amendment from arXiv:2510.11616):
- Before cointegration: `residual_i = return_i - beta_mkt * mkt_return - beta_sector * sector_return`
- Test cointegration on RESIDUALS, not raw prices
- Eliminates spurious pairs caused by factor/sector rotation

**Stage 1 — Statistical Pair Selection**:
- Cointegration screening on S&P 500 (top 50 by market cap)
- Select top 20 pairs by cointegration strength (p < 0.05) on residuals
- Z-score signals: entry z > 2.0, exit z < 0.5

**Stage 2 — LLM Semantic Filter**:
- For each pair, prompt Claude: *"Is there a plausible economic mechanism explaining why A and B should track each other over time? Score 0-100."*
- Skip pairs scoring < 40

**Backtest**:
- S&P 500 daily data, 2020-2025 (5 years)
- Universe: top 50 stocks by market cap
- Position sizing: 5% per pair, max 4 concurrent pairs
- Hold limit: 20 days

### Key Distinction from R26
R26 asked "is the chart overbought?" (wrong for event-driven). R29 asks "does an economic mechanism exist?" (semantic assessment of pair quality, not chart aesthetics).

---

## Round 30: Multi-Quarter SUE Elastic Net (COMPLETED)

**Status**: COMPLETED 2026-04-03 — results disappointing
**Result**: EN 12-Q Sharpe 0.493 vs Single-Q baseline 0.640. Paper's 2x improvement did NOT replicate.

**Why it failed**: The model learned positive equity drift (long 98.5% of signals) on 22 large-caps in a bull market — not the earnings signal. When frequency-adjusted, both models produce ~Sharpe 1.21-1.22 annualized.

**Verdict**: Single-Q SUE (Sharpe 1.40) beats 12-Q EN (Sharpe 1.25). Real fix requires 100-200+ stocks including mid-caps (K&Z likely used 500+ names where negative drift exists in short leg).

Full reports: R30_SUE_REPORT.md, R30B_SUE_LONGSHORT_REPORT.md in `/workspace/group/trading_eval/`

---

## Round 31: Text-Based PEAD

**Status**: QUEUED (can run in parallel with R28/R29 — different data source)
**Inspired by**: PEAD.txt (JFQA 2022, Meursault, Liang, Routledge & Scanlon)
**Hypothesis**: FinBERT on earnings call transcripts produces 50% stronger daily alpha than numeric SUE, and PERSISTS in recent years when numeric PEAD has weakened to ~0

### Signal Construction
- FinBERT (`ProsusAI/finbert`) scores earnings call transcript sentences
- Text surprise = this_quarter_score − trailing_12Q_avg_score
- Score > 0 = management tone more positive than usual = long signal
- **Weight Q&A section 1.5x** — carries more signal than prepared remarks (management has less control)

### Expected Results
- Paper: SUE.txt = 3.9 bps/day vs classic SUE = 2.6 bps/day (50% improvement)
- Critical advantage: signal persists when numeric PEAD has decayed

### Optional Enhancement (SAE-FiRE, arXiv:2505.14420)
If FinBERT score averaging (Approach A) underperforms: extract hidden states + SelectKBest (top 50 of 768 dims). Only use if basic approach disappoints — adds complexity and needs labeled training set (~50+ transcripts).

---

## Round 32: Systematic SPX Put-Writing with VIX-Kelly Sizing

**Status**: QUEUED (independent of R28/R29/R31 — can run anytime)
**Inspired by**: arXiv:2508.16598 (Aug 2025)
**Hypothesis**: Far OTM SPX/SPY put-writing with VIX-Kelly hybrid sizing harvests the volatility risk premium systematically

### Key Design Parameters
- Puts: delta 0.10-0.15, short-dated (0-14 DTE)
- Sizing: Kelly fraction × (20/VIX) — hybrid method wins vs. fixed or VIX-only
- Cap: 2x base size maximum
- Complement: orthogonal to R25 covered calls (individual stocks vs. index VRP)

### Infrastructure Required
Only yfinance + FRED — can run immediately without additional data subscriptions.

---

## Round 33: LLM Financial Statement Analysis + PEAD Catalyst

**Status**: QUEUED — next to run
**Inspired by**: Kim, Muhn & Nikolaev (arXiv:2407.17866, 2024) — sourced Apr 12, 2026
**Hypothesis**: Combining GPT-4 fundamental analysis of earnings releases with the PEAD event catalyst produces higher Sharpe than either alone. Kim et al. show pure fundamentals beat analysts; PEAD shows the event catalyst alone generates drift. The combination should amplify signal quality and reduce false positives.

### Background
Kim et al. (2024) demonstrated:
- GPT-4 with CoT on anonymous financial statements: 60.4% accuracy predicting EPS direction, Sharpe 3.36 (equal-weighted L-S)
- The mechanism is ratio analysis — LLM computes operating margin, asset/inventory turnover, current ratio, then synthesizes
- GPT and ANN provide incremental signal; combined model (GPT narratives + ANN) is best at 63.2% accuracy
- Limitation: their strategy is purely fundamentals-driven with annual rebalancing — no event catalyst, no earnings surprise integration

### Design

**Signal construction (two layers):**

**Layer 1 — GPT Fundamental Score (pre-earnings):**
- At Q-4 (4 weeks before earnings), feed GPT-4 the last 2 annual balance sheets + 3 annual income statements (anonymized, Compustat-style)
- CoT prompt: trend analysis → ratio computation → interpretation → predict EPS direction + magnitude + confidence
- Extract: binary direction (up/down), magnitude (large/moderate/small), confidence score, log-probability
- Score = log-probability × magnitude_weight (large=1.0, moderate=0.6, small=0.3)

**Layer 2 — PEAD Catalyst Filter (post-earnings):**
- At earnings release, compute SUE (standardized unexpected earnings) = (actual EPS − consensus) / std(prior SUE)
- Require sign alignment: GPT predicted UP + SUE > +1σ → strong long; GPT predicted DOWN + SUE < −1σ → strong short
- Misalignment (GPT UP + SUE negative): skip — conflicting signals

**Portfolio construction:**
- Universe: S&P 500 + Russell 1000, December AND non-December fiscal year-end (expand beyond Kim et al.)
- Long: top quintile aligned positive signals (GPT score × SUE product)
- Short: top quintile aligned negative signals
- Holding period: 20 trading days post-announcement (PEAD window from R28)
- Sizing: equal-weight within quintile; cap 5% per position
- Rebalance: at each earnings event (not calendar-based)

**Baseline comparisons:**
- PEAD alone (SUE > 1σ, 20-day hold) — from R28
- GPT alone (annual rebalance, Kim et al. methodology) — replicate their approach
- Combined (the hypothesis)

### Infrastructure Required
- Compustat quarterly/annual financials (balance sheet + income statement)
- I/B/E/S consensus estimates for SUE calculation
- GPT-4 API with logprobs enabled
- Estimated API cost: ~$0.15 per firm-quarter at ~1,500 tokens per call

### Key Hypotheses
1. Combined signal Sharpe > PEAD alone Sharpe (R28 baseline: ~9.03 portfolio Sharpe)
2. GPT fundamental filter reduces PEAD false positives (earnings beats not backed by improving fundamentals)
3. Large-magnitude + high-confidence GPT predictions produce the most reliable PEAD follow-through
4. The combination is especially powerful for small/mid-caps where analyst coverage is thin

### Expected Timeline
One agent session with pre-loaded Compustat data. GPT API calls are the bottleneck (~500-2,000 firm-quarters depending on universe size).

---

## Research Gaps (Not Yet Addressed)

1. **Intraday patterns**: 1H, 4H bars completely unexplored
2. **Alternative data**: Options flow, insider transactions, short interest — none tested
3. **Event-driven (M&A, spin-offs, index additions)**: Requires event data feed
4. **0DTE options (SPX)**: Needs historical intraday options chain data
5. **Broader PEAD universe**: 100-200 stocks including mid-caps (would enable long-short)
6. **LLM regime assessment**: Portfolio-level "is PEAD favorable right now?" switch — untested

---

## Related Topics

- [[pead-strategy]] — R28, R30, R31 context
- [[pairs-trading]] — R29 design detail
- [[options-strategies]] — R32 context
- [[llm-signal-research]] — R26, R28, R29 LLM layer design
- [[ai-research-papers]] — Papers inspiring each round

## Sources
- Master Trading Report (Design Specs sections): raw/master_trading_report_2026-04-05.md
- Memory Snapshot (R28-R32, updated 2026-04-04): raw/MEMORY_snapshot_2026-04-05.md
