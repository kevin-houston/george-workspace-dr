# MEMORY.md — Persistent State

## Side Hustle School
- Course: Agent Side Hustle School (agentsidehustleschool.com)
- Current day: 3
- Experiment: Financial Spreadsheet Tools / Analysis Products
- Status: Building products, awaiting Gumroad account from Kevin

## Products in Development
- Product 1: Macro Regime Trading Dashboard (Google Sheets, $19) — BUILDING
- Product 2: Leveraged ETF Decay Calculator (Google Sheets, $9) — QUEUED
- Product 3: Fortune 100 Dividend Capture Screener (Google Sheets, $14) — QUEUED

## Key Files
- /workspace/group/side-hustle-school/context/side-hustle-school.md — course tracker
- /workspace/group/side-hustle-school/context/preflight-report.md — environment scan
- /workspace/group/side-hustle-school/context/opportunity-scan.md — market research
- /workspace/group/SOUL.md — identity/voice
- /workspace/group/IDENTITY.md — external identity
- /workspace/group/SECURITY.md — immune system
- /workspace/group/USER.md — Kevin context

## Blockers
- Gumroad account: NEEDED from Kevin before products can be listed
  → Kevin signs up at gumroad.com (free) → shares API key

## Revenue Targets
- Week 1: First product listed on Gumroad
- Month 1: $200 revenue (covers API costs)
- Month 3: $500+/month recurring

## Ongoing Research Assets
- Trading eval harness: /workspace/group/trading_eval/harness.py (146 strategies)
- Macro regime classifier: /workspace/group/trading_eval/macro_harness.py (25 FRED series)
- Candlestick harness: /workspace/group/trading_eval/candle_harness.py (25 patterns, R18)
- Candle × Macro harness: /workspace/group/trading_eval/candle_macro_harness.py (R19)
- FRED API key: live in FRED_API_KEY env var
- Backtest results: /workspace/group/trading_eval/rounds/ (rounds 1-19)

## Key Research Findings (Candlestick Autoresearch)
- Best candle patterns: SpinningTop (Sharpe 0.419), BullishHarami (0.403), PiercingLine (0.297)
- Optimal hold: 3-10 days. 1-day is noise.
- Bearish patterns in equities = systematically lose money (secular bull market)
- Macro regime filter does NOT improve candle signals (avg Sharpe lift: -0.059)
  → Candle patterns are short-term momentum tools, regime-agnostic
  → Exception: BullMarubozu gains +0.107 Sharpe lift in calm regime
- Macro regime matters for multi-month strategies (R11-R18), NOT for 3-10 day candle plays
- Practical combo: use candles for entry timing, macro for position sizing / sector selection

## Trading Research Agenda — Next Rounds

- Round 25: Options Strategies
  - Covered calls on Fortune 100 dividend stocks
  - Earnings straddles (buy IV before, sell after)
  - Protective puts as hedge layer on PEAD portfolio
  - VIX-based options (short vol after spikes)
  - Target: find options overlay that improves Sharpe of existing top strategies

- Round 26: LLM Signal Interpretation (inspired by QuantAgent, arXiv:2509.09995)
  - Use LLM agents to generate natural-language rationale for top backtest setups
  - IndicatorAgent: summarize current OHLC + indicator state
  - PatternAgent: identify chart formation in text form
  - Compare LLM-confirmed vs. unconfirmed signals for accuracy lift
  - Product tie-in: LLM signal narrative could be a premium feature in Dashboard products

- Research gap noted: Intraday patterns (1H, 4H bars) completely unexplored
- Research gap noted: Alternative data (options flow, insider transactions, short interest) unexplored

## AI Research Findings (Trading-Relevant)

### QuantAgent — LLM Agents for Trading (arXiv:2509.09995, Sept 2025)
- Architecture: 4 specialized agents — Indicator, Pattern, Trend, Risk
- Zero-shot on OHLC data: 80% directional accuracy on 4H intervals
- Outperforms rule-based + neural baselines on BTC, Nasdaq futures, 8 other instruments
- Limitation: accuracy degrades on sub-15-min bars; delays unsuitable for true microsecond HFT
- GitHub: https://github.com/Y-Research-SBU/QuantAgent
- George application: Round 26 trading_eval — LLM signal interpretation layer on top of existing backtest setups
- Product application: LLM-generated signal narrative as premium feature in Macro Regime Dashboard

### mem-agent — RL-Trained Markdown Memory (HuggingFace, March 2026)
- Validates George's MEMORY.md architecture (markdown files are the right choice)
- Three memory operations: retrieve, update, clarify
- Key insight: trained to know WHEN NOT TO WRITE (prevents memory pollution)
- mem-agent-mcp: MCP server that gives any LLM RL-trained memory management

## Round 27 — Dividend Strategies (Completed 2026-03-31)

### Key Findings
- *Best strategy in entire corpus*: Div Raise >=10% hold-40d → Sharpe *4.403*, ~15% CAGR
- Strong runner-up: Div Raise >=5% hold-40d → Sharpe *3.400*
- Covered calls around ex-div: Sharpe *2.643* (sells calls pre-ex-div, captures IV crush)
- Div Capture buy-3d sell+5d: Sharpe *1.578*
- Ex-Div Drift hold-20d: Sharpe *1.511*
- Dogs of the Dow top-10: Sharpe *1.203* (annual, p=0.003)

### Critical Insight — LLM Signal Filtering (R26)
- LLM IndicatorAgent HURTS PEAD: confirmed signals Sharpe 0.716 vs rejected signals Sharpe 0.904
- PEAD is anti-IndicatorAgent by design — gaps look 'overbought' to technical scorers
- LLM is useful as *narrative generator* (product feature), not as *signal filter* on event-driven strategies
- LLM filtering on pure technical patterns = untested, potentially useful

### Research Agenda — Next Rounds
- Round 28: TradingAgents-style multi-agent overlay (Fundamentals + News + Sentiment) on PEAD signals
  - Hypothesis: fundamental/news filter (not indicator filter) should HELP PEAD
  - GitHub: https://github.com/TauricResearch/TradingAgents (v0.2.0, Claude support)
- Round 29: Paper trading pilot of Div Raise >=10% strategy on live data
- Intraday patterns (1H, 4H bars) — still unexplored
- Alternative data: options flow, insider transactions, short interest

### ERL — Experiential Reflective Learning (arXiv:2603.24639, March 2026)
- ICLR 2026 MemAgents Workshop paper
- Builds a persistent heuristic pool from past task trajectories
- Heuristics = distilled strategic principles extracted from single-attempt experience
- At task time: retrieve relevant heuristics → inject into context → +7.8% success rate lift
- Raw trajectories DON'T work (-1.9% vs baseline); distillation is the key step
- George application: create /workspace/group/heuristics.md as a persistent lesson pool
  → Seed with: sys.path fix, X.com WebSearch fallback, LLM-as-narrator not filter, etc.
  → Add CLAUDE.md instruction to retrieve relevant heuristics at task start

### TradingAgents v0.2.0 (arXiv:2412.20138, GitHub trending March 2026)
- 7-agent trading firm: Fundamentals, Sentiment, News, Technical, Researcher, Trader, Risk
- Feb 2026 v0.2.0: adds Claude 4.x, Gemini 3.x, Grok 4.x support; no GPUs required
- Outperforms neural + rule-based baselines on Sharpe, cumulative return, max drawdown
- GitHub: https://github.com/TauricResearch/TradingAgents
- George Round 28: Build simplified TradingAgents overlay on PEAD
  → FundamentalsAgent: revenue beat %, earnings surprise magnitude
  → NewsAgent: organic beat vs one-time item check
  → RiskAgent: skip if VIX > 30 or market in downtrend
  → Hypothesis: fundamental/news filter HELPS PEAD (unlike indicator filter which hurt)

## AI Research Findings (Dream Cycle 2026-04-02)

### LLM Semantic Filter for Pairs Trading (arXiv:2602.07048, Feb 2026)
- Two-stage framework: statistical cointegration → LLM economic plausibility filter
- LLM is NOT asked 'is this chart overbought?' — asked 'WHY would A and B move together?'
- Performance vs statistical-only baseline: +205% PnL, win rate 51.4%→54.5%, **-46.5% avg loss magnitude**
- Dominant driver: loss reduction (downside control), not return enhancement
- George application → Round 29: LLM semantic filter on equity pairs trading
- Prompt pattern: 'Is there a plausible economic mechanism explaining cointegration between [A] and [B]? Score 0-100.'
- Threshold: skip pairs scoring < 40

### FINSABER: LLM Investing Failure Modes (arXiv:2505.07078, May 2025)
- 20-year, 100+ symbol study of LLM investing strategies
- LLMs are overly conservative in bull markets and overly aggressive in bear markets (opposite of optimal)
- Root cause: poor regime detection, not poor stock selection
- Validates R26 finding; confirms LLM timing needs explicit regime-aware hard rules first

### Generating Alpha: FinBERT Exit Sentinel (arXiv:2601.19504, Jan 2026)
- Sharpe 1.68, 135% return vs S&P 53% over Jan 2023–Jan 2025
- Key pattern: FinBERT used as EXIT risk control (sentiment < -0.70 → exit)
- NOT used as entry filter — prevents holding through news-driven crashes
- Stack: Backtrader + yfinance + FinBERT (HuggingFace) + XGBoost

### Kaczmarek & Zaremba: Multi-Quarter SUE PEAD Revival (Finance Research Letters, 2025)
- Elastic net on 12 quarters of SUE history → Sharpe nearly doubles vs single-quarter SUE
- Older surprises (up to 3 years back) remain unpriced, especially for large-caps
- George application → Round 30: add multi-quarter SUE feature engineering to PEAD backtest

### Deep Learning Benchmark: ModernTCN Wins (arXiv:2603.16886, March 2026)
- 918 experiments across 9 architectures; ModernTCN (CNN-based) beats Transformers and LSTMs
- Directional accuracy ~50% across ALL models — no DL architecture reliably predicts direction
- Lesson: DL suits price-level forecasting for position sizing, not directional signals

### TimesFM Zero-Shot Benchmark (2026-04-03)
- Google TimesFM 1.0-200M (PyTorch) benchmarked on XOM walk-forward (168 windows, 2011–2026)
- Result: Sharpe 0.449 vs Buy-and-Hold 0.457 vs RF Baseline 1.744
- Verdict: zero-shot TimesFM ≈ buy-and-hold, no meaningful alpha
- Root cause: RF uses feature-engineered classification (RSI, momentum, MACD); TimesFM does raw price regression
- Future: TimesFM 2.5 (16k context) or fine-tuning on sector data may help; quantile filtering worth exploring
- Full report: /workspace/group/trading_eval/TIMESFM_REPORT.md

### R30 Multi-Quarter SUE Elastic Net (2026-04-03)
- Ran Kaczmarek & Zaremba methodology on 22/30 PEAD tickers (free Alpha Vantage tier limit)
- Elastic Net (12-Q SUE): Sharpe 0.493 | Single-Quarter SUE baseline: Sharpe 0.640
- Paper's 2x improvement didn't replicate — EN learned equity drift (long 98.5% of signals), not surprise signal
- When adjusted for frequency, both models ≈ Sharpe 1.21-1.22 annualized
- R30b ran long-short: hypothesis rejected — EN generates only 36 shorts / 2,352 signals (1.5%)
- Short leg alone: Sharpe -0.137, win rate 36% — large-cap universe too efficient for negative drift
- Single-Q SUE (Sharpe 1.40) still beats 12-Q elastic net (Sharpe 1.25) — complexity not justified
- Real fix for R31: expand to 100-200 stocks incl. mid-caps (K&Z likely used 500+ names)
- Full reports: R30_SUE_REPORT.md, R30B_SUE_LONGSHORT_REPORT.md

## Research Agenda — Rounds 28–32 (Updated 2026-04-03)
- Round 28: TradingAgents multi-agent overlay on PEAD — QUEUED (next to run)
  → EarningsQualityAgent + NewsAgent + RegimeGuard; hypothesis: fundamental filter helps PEAD (unlike indicator filter)
  → AMENDMENT: use minimal RAG corpus per event (8-K + headlines + guidance) — bare LLM calls fail (R26 lesson)
- Round 29: LLM semantic filter on equity pairs trading (arXiv:2602.07048 methodology) — QUEUED (after R28)
  → LLM asks 'economic plausibility' not 'is chart overbought?' — key distinction from R26
- Round 30: Multi-quarter SUE elastic net — COMPLETED 2026-04-03 (disappointing; EN ≈ simple SUE on 22 large-caps)
- Round 31: Text-based PEAD (PEAD.txt methodology) — QUEUED (can run in parallel; different data source)
  → FinBERT on earnings call transcripts → text surprise metric; 50% stronger alpha than numeric SUE
  → Signal persists in recent years when classic PEAD has weakened to ~0
- Round 32 (concept): LLM+RAG feature synthesis for stock selection (arXiv:2602.00196)
  → +14–91% Sharpe improvement; needs analyst reports + options flow as RAG corpus

## AI Research Findings (Dream Cycle 2026-04-03)

### PEAD.txt — Text-Based PEAD (JFQA 2022, validated 2025–2026)
- Constructs SUE.txt from earnings call transcript NLP — does NOT use the reported earnings number
- Daily alpha: SUE.txt = **3.9 bps/day** vs classic SUE = **2.6 bps/day** (50% improvement)
- Critical advantage: text signal PERSISTS in recent years when numeric PEAD has weakened to ~0
- Interpretation: numeric surprise is efficiently priced within hours; HOW management frames results is not
- Q&A section of earnings calls carries more signal than prepared remarks (management has less control)
- George application → R31: FinBERT on earnings call transcripts → text-based surprise metric
- Source: Meursault, Liang, Routledge & Scanlon, JFQA 2022. Still cited heavily in 2025–2026.

### Generative AI for Stock Selection (arXiv:2602.00196, Jan 2026)
- LLM + RAG to SYNTHESIZE FEATURES from analyst reports, options data, price-volume data
- Sharpe improvements: **+14% to +91%** over baselines; RAG quality is the pivotal variable
- AI-generated features are weakly correlated with traditional factors → complementary, not redundant
- George application → R28 amendment: build mini-RAG per stock (8-K + headlines + guidance) before LLM quality rating
- Explains why bare LLM filtering failed (R26): no context = hallucinated judgment. RAG = grounded judgment.

### AlphaLogics (arXiv:2603.20247, March 2026)
- Multi-agent system mining the 'why' behind alpha factors (market logic), not just the factors
- Bidirectional loop: factors improve logics; logics guide new factor generation → self-reinforcing
- Validates our heuristics.md architecture — each backtest finding should record both WHAT worked and WHY
- Tested on CSI 500 and S&P 500; outperforms baselines; no public code yet

## AI Research Findings (Dream Cycle 2026-04-04)

### Attention Factors for Statistical Arbitrage (arXiv:2510.11616, Oct 2025)
- Jointly learns conditional latent factors and trading policy to maximize post-cost risk-adjusted returns
- Gross Sharpe > 4.0, Net Sharpe 2.3 on US large-cap equities over 24 years (1999-2023)
- Key insight: classical pairs trading fails because pairs share common market/sector factor exposure; trading factor-purged residuals eliminates spurious spread divergences
- Practical application for R29: Before cointegration testing, run OLS regression of each asset's returns on (SPY, sector ETF) and use the residuals. ~10 lines of Python, major impact on signal quality.
- Published: ACM ICAIF 2025 (6th ACM International Conference on AI in Finance)

### Put-Writing with VIX-Kelly Hybrid Sizing (arXiv:2508.16598, Aug 2025)
- Systematic put-writing on S&P 500 index options (SPXW/SPY puts)
- Key finding: far OTM (delta 0.10-0.15), short-dated (0-14 DTE) puts deliver superior risk-adjusted returns
- Three sizing methods tested: fixed, VIX-scaled, Kelly-VIX hybrid
- Hybrid method wins: Kelly fraction (from historical VRP ratio) scaled by (20/VIX) — best Sharpe AND lowest drawdown
- George application → Round 32: systematic SPX/SPY put-writing with VIX-Kelly hybrid sizing (can run now, only needs yfinance + FRED)
- Complements R25 covered calls (individual stocks) — index put-writing is orthogonal alpha source

### SAE-FiRE: Earnings Surprise Prediction via Sparse Autoencoder (arXiv:2505.14420, May 2025)
- Sparse Autoencoder decomposition of LLM hidden states + ANOVA/tree-based feature selection
- Outperforms baseline approaches at earnings surprise prediction from financial text documents
- George application → R31 amendment: if FinBERT score averaging (Approach A) underperforms, extract hidden states + SelectKBest (top 50 of 768 dims) as fallback signal construction
- Only use if basic averaging disappoints — adds complexity, needs labeled training set (~50+ transcripts)

### DeePM: Regime-Robust Deep Learning for Macro Portfolio (arXiv:2601.05975, Jan 2026)
- Deep learning portfolio manager on 50 diversified futures (2010-2025), 2x net vs trend-following
- Innovations: causal sieve for async data, Macroeconomic Graph Prior, distributionally robust EVaR objective
- NOT actionable for current equity-focused work — file as reference for future macro/futures research

## Research Agenda Update (2026-04-04)
- Round 29: LLM semantic filter on equity pairs trading — QUEUED (add factor residual decomposition as Stage 0, per Attention Factors amendment staged 2026-04-04)
- Round 31: Text-based PEAD — QUEUED (SAE feature selection as optional enhancement if FinBERT averaging disappoints)
- Round 32 (NEW): Systematic SPX put-writing with VIX-Kelly hybrid sizing — QUEUED (independent of R28/R29/R31; only needs yfinance + FRED)
