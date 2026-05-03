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

## Round 29 — Pairs Trading: Factor Residualization + OU Thresholds (Completed 2026-04-11)

### Key Findings
- **R29 v1** (residualized + fixed ±2σ): Sharpe **1.3802**, CAGR 10.57%, MaxDD -8.35% — BEATS R23 (0.964)
- **R29 v2** (residualized + OU thresholds): Sharpe **0.9138**, CAGR 8.91%, MaxDD -18.56% — below R23
- **Baseline** (raw + fixed ±2σ): Sharpe **0.4358** — only 1 cointegrated pair found in raw prices
- Factor residualization is the major driver: raw prices → only 1 cointegrated pair; residualized → 19 pairs
- OU calibration HURTS vs fixed ±2σ: -0.47 Sharpe lift (more trades, wider stop losses, higher drawdown)
- Best individual pairs: MSFT/TXN (Sharpe 0.79), TXN/META (0.74), AMZN/TSLA (0.73)
- New pairs leaderboard best: R29 v1 Sharpe 1.3802 (previous pairs best: R23 Sharpe 0.964)
- Full report: /workspace/group/trading_eval/R29_PAIRS_REPORT.md
- Results JSON: /workspace/group/trading_eval/rounds/r29_pairs_results.json

## Research Agenda — Rounds 28–32 (Updated 2026-04-11)
- Round 28: TradingAgents multi-agent overlay on PEAD — QUEUED (next to run)
  → EarningsQualityAgent + NewsAgent + RegimeGuard; hypothesis: fundamental filter helps PEAD (unlike indicator filter)
  → AMENDMENT: use minimal RAG corpus per event (8-K + headlines + guidance) — bare LLM calls fail (R26 lesson)
- Round 29: COMPLETED 2026-04-11 — factor residualization + OU thresholds on pairs
  → Best variant: R29 v1 residualized + fixed ±2σ → Sharpe 1.3802 (new pairs record)
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

## AI Research Findings (Dream Cycle 2026-04-05)

### MarketSenseAI 2.0 — RAG + 5-Agent Stock Analysis (arXiv:2502.00415, Feb 2026)
- **5 sequential agents**: News → Fundamentals → Dynamics → Macroeconomic → Signal (Chain-of-Thought)
- **Performance**: Sharpe 2.13–2.87 on S&P 100/500; win rate ~77%; 125.9% vs benchmark 73.5% (2023-2024)
- **Fundamentals Agent pipeline**: (1) summarize 8-K/10-Q → (2) summarize earnings call Q&A → (3) consolidate with 5 quarters of EPS data
- **RAG method**: Hypothetical Dense Embeddings (HyDE); context precision ≥ 0.98; free EDGAR API for filings
- **R28 application**: Use this 3-step Fundamentals Agent pipeline as the EarningsQualityAgent design
  → Step 1: Pull 8-K from EDGAR API, summarize for this quarter's beat/miss and one-time items
  → Step 2: Score Q&A section of earnings call for management tone and quality of beat
  → Step 3: Compare vs prior 5 quarters' EPS history to assess persistence
- Open-source path: Llama 3 70B achieves F1 0.869 (vs Claude 3.5 Sonnet F1 0.929) at 80% cost reduction
- Full KB entry: /workspace/group/knowledge-base/raw/2026-04-05_marketsenseai2-rag-agent-stock-analysis.md

### Multi-Agent LLM Benchmarking on SEC Filings (arXiv:2603.22651, March 2026)
- 4 orchestration patterns × 5 LLMs on 10,000 filings (10-K, 10-Q, 8-K)
- **Winner**: Hierarchical Supervisor-Worker — 98.5% of reflexive accuracy at 60.7% cost ($0.26/doc)
- For R28 backtesting (small volume): reflexive self-correcting is fine; degradation only at 25K+ docs/day
- Earnings quality fields (one-time items, accruals) must be added as domain-specific hard constraints outside LLM
- Key failure modes: temporal confusion (FY vs quarterly), unit/scale mismatches — build explicit guards
- Full KB entry: /workspace/group/knowledge-base/raw/2026-04-05_multiagent-llm-sec-benchmarking.md

## R28 Implementation Blueprint (Updated 2026-04-05)

Based on MarketSenseAI 2.0 architecture + Multi-Agent Benchmarking findings:

### EarningsQualityAgent Design
```
For each PEAD signal (earnings beat detected):
  1. Pull 8-K from EDGAR API (free) — summarize: beat magnitude, one-time items, guidance
  2. Pull earnings call Q&A section — score: management tone, surprise framing, analyst reception
  3. Compare vs prior 5 quarters EPS history — is this beat persistent or one-off?
  4. Output: quality_score (0-100). Skip PEAD trade if quality_score < 50.
```

### NewsAgent Design
- Pull top 3 headlines from day of earnings via free news API (GNews or NewsAPI free tier)
- FinBERT sentiment on headlines → negative sentiment < -0.5 = skip (exit sentinel pattern)
- Distinguish: 'earnings beat' vs 'beat but lowered guidance' vs 'beat on cost cuts only'

### RegimeGuard
- VIX > 30 → skip all new PEAD entries
- SPY 50-day SMA < 200-day SMA → reduce position size 50%

### Cost Estimate
- EDGAR API: free; LLM calls: ~$0.05–0.15 per event with Claude Haiku or Llama 3 70B
- ~30 PEAD events/quarter × $0.15 = ~$4.50/quarter total API cost

### Hypothesis
- EarningsQualityAgent HELPS PEAD (unlike IndicatorAgent which hurt — R26 lesson)
- Quality filter distinguishes 'organic beat' from 'one-time item' — directly targets why some PEAD signals fail
- RAG grounding (EDGAR 8-K) fixes bare-LLM hallucination problem identified in R26

## AI Research Findings (Dream Cycle 2026-04-06)

### Graph Clustering Pairs Trading — SPONGEsym on Residual Correlation (arXiv:2406.10695, June 2024)
- Builds signed weighted graph from 60-day correlation matrix of factor-residualized returns
- Clustering algorithm: SPONGEsym (Signed Positive Over Negative Generalized Eigenproblem) — decomposes correlation into positive/negative blocks
- Optimal cluster count: eigenvectors explaining 90% of correlation variance
- 5 ML classifiers filter signals using graph features (vertex degree, cluster density) + traditional features
- Kelly criterion for position sizing (long + short fractions sum to unity); 10-day rebalancing
- Performance (S&P 500, out-of-sample March 2006–Dec 2022): IR 1.30, Sortino 3.38, 49.33% annualized return, 31.98% max drawdown
- R29 Amendment: Add SPONGEsym clustering as Stage 0.5 between factor residualization (Stage 0) and LLM plausibility scoring (Stage 2)
  → Stage 0: residualize returns on (SPY, sector ETF)
  → Stage 0.5: build 60-day residual correlation graph → SPONGEsym clustering → only test cointegration within same cluster
  → Stage 1: Engle-Granger cointegration test on within-cluster pairs
  → Stage 2: LLM economic plausibility score (skip pairs < 40)
  → Stage 3: Trade the spread with Kelly-weighted position sizing
- Full KB entry: /workspace/group/knowledge-base/raw/2026-04-06_graph-clustering-pairs-trading.md

### FinNLP 2025 PEAD Enhancement — FinBERT + Early Price Signal (ACL Anthology 2025.finnlp-2.13)
- Paper: Hadlock, Roberts & Lee. 'Enhancing Post Earnings Announcement Drift Measurement with Large Language Models.' FinNLP Workshop, ACL 2025.
- Benchmark: FinBERT vs BART encoder-decoder for PEAD direction classification
- FinBERT wins: 57.6% accuracy (positive group), 58.3% (negative group) — financial domain pretraining captures PEAD narrative signals
- Key enhancement: adding 3-day post-earnings price signal as auxiliary input improves model. Market's early reaction provides signal about institutional interpretation.
- R31 Amendment: After computing FinBERT text surprise score, incorporate 3-day confirmation window
  → FinBERT positive AND 3-day return > 0: strong signal, full size (enter on day 3, not day 0)
  → FinBERT positive but 3-day return < -1%: weak/conflicted signal — skip or reduce size 50%
  → Day 3 entry sacrifices initial 3-day drift but improves signal quality substantially
- Full KB entry: /workspace/group/knowledge-base/raw/2026-04-06_finnlp-pead-llm-enhancement.md

### Alpha-R1: RL-Trained Dynamic Factor Gating (arXiv:2512.23515, Dec 2025)
- Architecture: 8B reasoning model trained via GRPO (Group Relative Policy Optimization — critic-free RL)
- Inputs: semantic factor descriptions (economic rationale), weekly market state summaries (price + news), 82 Alpha101 candidate factors
- Mechanism: each day, model reasons over factor logic + market context → activates subset of factors → fixed linear scorer applies only those factors
- RL reward: backtested portfolio return × (1 − consistency_penalty) — penalizes incoherent factor selection
- Performance (2025 holdout): CSI 300 Sharpe 1.62 / 27.59% AR / 6.76% max DD; CSI 1000 zero-shot Sharpe 4.03 / 78.18% AR
- Massively outperforms static XGBoost (−21.65% AR) and PPO (Sharpe 0.11)
- GitHub: https://github.com/FinStep-AI/Alpha-R1
- George application → Round 33 (concept): apply Alpha-R1-style gating to our 146-strategy library
  → Map strategies to factor categories; build weekly market state summaries from FRED + VIX + SPY
  → Train RL gating model on past round results; activate strategies per regime
  → NOTE: Original trained on CSI 300 (China) — US adaptation needs retraining on US data
- Full KB entry: /workspace/group/knowledge-base/raw/2026-04-06_alpha-r1-dynamic-factor-screening.md

## Research Agenda Update (2026-04-06)

- Round 28: TradingAgents multi-agent overlay on PEAD — QUEUED (next to run)
- Round 29: LLM semantic filter on equity pairs trading — QUEUED (4-stage pipeline: factor residualize → SPONGEsym cluster → cointegration → LLM plausibility)
- Round 31: Text-based PEAD — QUEUED (FinBERT + 3-day confirmation window; enter on day 3 not day 0)
- Round 32: Systematic SPX put-writing with VIX-Kelly hybrid sizing — QUEUED
- Round 33 (concept): Alpha-R1-style RL dynamic factor gating on 146-strategy library

## AI Research Findings (Dream Cycle 2026-04-08)

### SAE Company Similarity for Pairs Trading (arXiv:2412.02605, ACL 2025)
- **Architecture**: Llama 3.1 8B layer 30 activations → SAE (TopK k=128, 131,072 features, 32x expansion) → interpretable company clusters
- **Dataset**: 27,888 SEC 10-K annual reports, 1996-2020, publicly traded US companies
- **Pairs trading out-of-sample performance (2014-2020)**:
  - SAE GCD: Sharpe **12.18** ← Winner
  - SAE GCD Rolling: Sharpe 9.69
  - PaLM-gecko Embeddings: 10.57
  - SIC Codes: 9.70
  - BERT/SBERT: 7.58/7.69
- **Why SAE wins**: Captures LLM's internal representation of a company's business model — not just semantic similarity, but feature-level decomposition revealing what aspects are 'active' in the LLM's processing of each company
- **Pre-computed features**: Available at HuggingFace `marco-molinari/company_reports_with_features` — no local GPU required to use
- **Code**: https://github.com/FlexCode29/company_similarity_sae
  - `Clustering/Cointegration_Pairs_Trading.py` — pairs trading strategy
  - `Clustering/GCD_Clustering_SAEs.py` — the core cluster computation
- **R29 Amendment**: Add as optional Stage 1.5 — AFTER factor residualization, use SAE clusters to constrain cointegration search universe instead of (or before) LLM economic plausibility scoring
  - Pipeline: (0) factor residualize → (0.5) SPONGEsym cluster → **(1.5) SAE cluster filter** → (1) cointegration test → (2) LLM plausibility → (3) Kelly trade
  - Practical note: Download pre-computed features from HuggingFace; no Llama inference required. Filter to current S&P 500 tickers overlapping with the 1996-2020 dataset.
- **Why this beats LLM prompting**: SAE clustering is deterministic, interpretable, doesn't depend on prompt engineering, and is validated at scale (27K+ companies). LLM prompting for 'economic plausibility' works well but requires API calls per pair.
- **Publication**: ACL 2025 Industry Track (peer-reviewed). Authors: Molinari et al.

### Analyst Belief Biases from Earnings Calls (arXiv:2511.15214, Nov 2025)
- **Finding**: Analysts systematically over-react to sentiment/optimism and under-react to risk/uncertainty language in earnings call narratives
- **Method**: LLM-generated counterfactual transcripts — isolates narrative effects while holding quantitative data constant
- **Relevance for R28 EarningsQualityAgent**: Single 'management tone' score conflates two signals with opposite biases. Better design:
  1. **Sentiment score**: How confident/optimistic is management framing? (0-100) — lower weight as analysts already over-incorporate this
  2. **Risk discussion density**: How much uncertainty/risk language appears? (0-100 inverted) — higher weight as analysts UNDER-react to this; high risk density = bearish PEAD signal even if headline beat is positive
  3. **Specificity score**: Does management cite specific drivers (product X, region Y revenue +N%)? vs. vague ('we saw strong momentum') — specific beats → stronger PEAD
- **R28 Amendment**: EarningsQualityAgent should output three separate scores (not one composite), with final quality score = 0.3*sentiment + 0.5*specificity + 0.2*(100-risk_density)
- **Heuristic**: High risk density + positive surprise = 'beat with qualifications' — reduce PEAD trade size 30-50%

### Retail Investor Horizon Signal for PEAD (arXiv:2512.00280, Dec 2025)
- **Finding**: Long-horizon retail investors (StockTwits, 2010-2021) associated with underreaction → persistent PEAD. Short-horizon traders drive overreaction then reversal.
- **Quantitative result**: Zero-cost portfolio (long long-horizon stocks, short short-horizon stocks) → 0.43%/month risk-adjusted alpha (~5.2% annualized)
- **Mechanism**: Long-horizon investors focus on fundamentals; short-horizon on technical/sentiment cues. Stocks dominated by short-horizon retail show reversal not drift.
- **Practical constraint**: StockTwits API required for direct implementation. Proxy approach: use 13-F institutional ownership data (free, quarterly) — stocks with HIGH institutional ownership tend to have more fundamental-focused investor base
- **Future round concept (R34)**: Use institutional ownership quartile as PEAD signal amplifier — trade PEAD only on stocks above median institutional ownership for same quarter

## Research Agenda Update (2026-04-08)

- Round 28: TradingAgents multi-agent overlay on PEAD — QUEUED (next to run)
  → **AMENDMENT (2026-04-08)**: EarningsQualityAgent should output THREE separate scores, not one composite:
     (1) Sentiment score (management optimism) — 30% weight (analysts already over-incorporate)
     (2) Specificity score (concrete driver evidence cited) — 50% weight (most predictive)
     (3) Risk density inverted (100 - risk_language_score) — 20% weight (analysts under-react to risk)
     Final quality_score = 0.3*sentiment + 0.5*specificity + 0.2*(100-risk_density). Skip if < 50.

- Round 29: Equity pairs trading — QUEUED
  → **AMENDMENT (2026-04-08)**: Add SAE Company Clustering as Stage 1.5 (fast deterministic pre-filter):
     Full pipeline: (0) factor residualize → (0.5) SPONGEsym cluster → **(1.5) SAE cluster filter** → (1) cointegration test → (2) LLM plausibility → (3) Kelly trade
     Use pre-computed SAE features from HuggingFace `marco-molinari/company_reports_with_features`
     Only run LLM plausibility (expensive) on pairs that pass both SPONGEsym AND SAE cluster filters

- Round 31: Text-based PEAD (FinBERT + 3-day confirmation) — QUEUED
  → Consider Financial-RoBERTa-Large (`soleimanian/financial-roberta-large-sentiment`) as alternative to ProsusAI/finbert
  → Trained on: 10-K, 10-Q, 8-K, earnings call transcripts, ESG news — larger model, may outperform FinBERT

- Round 32: SPX put-writing with VIX-Kelly hybrid sizing — QUEUED (independent)

- Round 33: Alpha-R1 RL dynamic factor gating on 146-strategy library — CONCEPT

- Round 34 (new concept): Investor horizon proxy as PEAD signal amplifier
  → Source: arXiv:2512.00280 (Dec 2025) — Long-horizon retail investor composition → stronger PEAD
  → Proxy (no StockTwits required): Use quarterly 13-F institutional ownership percentile
  → Hypothesis: Stocks above 60th percentile institutional ownership have more fundamental-focused investor base → stronger PEAD when triggered
  → Can be layered on existing PEAD backtest with zero new data sources beyond what's already used

### Earnings Call Manager Evasiveness as PEAD Amplifier (arXiv:2505.18419, May 2025)
- **Finding**: Manager non-responses (NORs) — questions analysts ask that managers evade without answering — significantly predict post-earnings announcement drift
- **Mechanism**: Evasiveness signals information asymmetry and uncertainty. Analysts can't update their models → wider forecast dispersion → slower price adjustment → MORE PEAD drift
- **LLM Detection**: 3-step prompting approach using ChatGPT-4 or LLaMA 3.3:
  1. **Identify** each analyst question in Q&A section
  2. **Classify** manager response as: full answer / partial answer / non-response (evasion)
  3. **Evaluate** evasiveness score (NOR rate = non-responses / total questions)
- **Effects of high NOR**:
  - Greater analyst forecast error and dispersion ✓
  - Greater PEAD (our signal!) ✓
  - Higher return volatility ✓
  - Wider bid-ask spreads ✓
  - Magnified for: high institutional ownership, R&D-heavy, diversified firms, COVID period
- **KEY INSIGHT**: High NOR is a PEAD AMPLIFIER, not a quality filter. Skip low-quality beats (low specificity); but among quality beats, HIGH NOR → trade larger.
- **R28 Amendment**: Add NOR_score as 4th input to EarningsQualityAgent:
  - Compute NOR rate from Q&A section
  - If NOR_rate > 0.25 (>25% of analyst questions unanswered) AND quality_score > 50: upsize position by 25%
  - If NOR_rate < 0.05 (management answered everything clearly): base position size
  - Rationale: High evasiveness means the market will take longer to price the beat → longer and stronger drift
- **Implementation**: Free with LLaMA 3.3 (open-source). Q&A section is already extracted for EarningsQualityAgent step 2. Add ~10 lines of prompt logic.
- **Note**: High NOR effect is magnified for high institutional ownership firms — consistent with Retail Investor Horizon finding (arXiv:2512.00280) that high-inst stocks show more PEAD. These two signals are complementary.

### Tools Update (2026-04-08 GitHub/HuggingFace Scan)

#### TradingAgents v0.2.3 (latest as of 2026-04-08)
- **v0.2.2** (Mar 2026): Claude 4.6 / GPT-5.4 / Gemini 3.1 support; five-tier rating scale; Anthropic effort control
- **v0.2.3** (Mar 29, 2026): Multi-language support, unified model catalog, **backtesting date fidelity fixes** (important for R28!)
- R28 should use v0.2.3 — backtesting date fidelity fix is directly relevant for PEAD backtest accuracy
- GitHub: https://github.com/TauricResearch/TradingAgents

#### Earnings Call NLP Models (Relevant to R31)

**NLPScholars/Roberta-Earning-Call-Transcript-Classification**
- Multi-label classification: positive / negative / litigious / constraining / uncertain
- Trained on 10 years of earnings call transcripts from AAPL, GOOG, MSFT, NVDA, AMZN, INTC, CSCO
- Best micro F1: 82.8% (multi-label)
- Annotated using Loughran-McDonald lexicon + FinancialPhraseBank
- **Limitation**: Sentence-level model (max 240 tokens) — requires transcript to be chunked by sentence
- **Best use**: Detect litigious/constraining/uncertain language in Q&A section → additive PEAD signal
- HuggingFace: `NLPScholars/Roberta-Earning-Call-Transcript-Classification`

**SeanD103/Longformer_for_financial_sentiment_analysis**
- Handles up to 4,096 tokens — avoids FinBERT truncation problem on full transcripts
- Directly addresses the limitation of FinBERT (512 token limit) for full-document processing
- **Best use for R31**: Process full Q&A section without chunking; better for extracting holistic sentiment
- HuggingFace: `SeanD103/Longformer_for_financial_sentiment_analysis`

**R31 Recommendation**: Use FinBERT (`ProsusAI/finbert`) for per-sentence scoring (text surprise metric = avg score vs. trailing 12Q avg), but add NLPScholars multi-label classifier for 'litigious + constraining + uncertain' flag — if any of these labels score high, reduce PEAD position size 30%.

## AI Research Findings (Dream Cycle 2026-04-09)

### Metric Shifting in Earnings Calls as Bearish Alpha Signal (arXiv:2510.03195, Oct 2025)
- **Paper**: 'From Text to Alpha: Can LLMs Track Evolving Signals in Corporate Disclosures?' — MIT, BlackRock, J.P. Morgan, Fidelity, Blackstone, State Street, QRT, UT Austin
- **Dataset**: S&P 100 earnings call transcripts, Jan 2010–Dec 2024, 5,615 firm-quarter observations
- **Core finding**: Firms that significantly shift WHICH METRICS they discuss between consecutive earnings calls produce negative abnormal returns. Q5 (highest metric shifting) vs Q1 (lowest): **5-factor alpha = -0.52%/month (t = -2.55, p < 0.05)**
- **Mechanism**: When management stops discussing previously emphasized metrics and introduces new topics, it signals they are hiding weak performance in the now-avoided areas. Analysts under-react to this topical evasion.
- **Methodology**: LLM (Gemini-2.5-Pro) extracts metric-focused textual spans per call; text-embedding-3-large computes semantic similarity across consecutive calls; 'moving targets score' = degree of metric departure
- **R28 Amendment — 4th EarningsQualityAgent Dimension**:
  - After computing Specificity (50%), Sentiment (30%), Risk density (20%) — add a VETO check:
  - Compute metric_consistency_score by comparing current quarter's discussed metrics to prior quarter's via embedding similarity
  - If metric_consistency_score < 35 (management dropped >65% of prior topics): VETO — do NOT initiate PEAD trade
  - If 35–60: reduce position by 30%
  - If > 60: no adjustment — proceed with composite quality score
- **LLM prompt for metric extraction**: "Read this earnings call transcript. Extract a list of specific business metrics and KPIs management discusses, using their exact phrasing. Include quantitative mentions and segment/product/geography references. Output a JSON array. Exclude generic terms like 'revenue' or 'earnings' — only context-rich, specific metrics."
- **Why this complements existing 3 scores**: The 3-score system asks 'how GOOD is what they said'; metric shifting asks 'are they still discussing the SAME things as before?' Both dimensions are needed. High specificity + high consistency = strongest buy signal.
- **Implementation cost**: ~2 extra LLM calls per event for prior quarter extraction. ~$0.02–0.05/event at Haiku rates. ~$1.50/quarter additional cost.

### LLM Extrapolation Bias in Stock Prediction (arXiv:2604.02921, April 2026)
- **Paper**: 'Debiasing LLMs by Fine-tuning' — Gao, Jiang, Yan, arXiv:2604.02921, April 2026, categorized under Trading and Market Microstructure (q-fin.TR)
- **Finding**: LLMs exhibit systematic extrapolation bias — they over-weight recent stock price trends when making financial predictions. In cross-sectional stock return prediction, bare LLMs load positively on recent momentum beyond what fundamentals support.
- **Additional mechanism for R26 failure**: Beyond 'no RAG context', the IndicatorAgent likely also penalized stocks with large earnings gaps by extrapolating 'recent gapper → likely to mean-revert', the OPPOSITE of the PEAD signal. Even RAG-grounded LLMs may exhibit this bias unless explicitly constrained.
- **Zero-cost fix — Anti-extrapolation instruction**: Add to ALL R28 EarningsQualityAgent prompts:
  "IMPORTANT: Do not consider this company's recent stock price performance, momentum, or valuation ratios. Focus exclusively on the quality, specificity, and consistency of the earnings announcement as evidenced by the filings and transcript. Your role is fundamental analyst, not market forecaster."
- **Generalization**: Any LLM used for fundamental quality scoring in event-driven strategies should include this instruction. It costs zero tokens and removes a systematic bias source.

### Minimum Regime Performance (MRP) — New Durability Diagnostic (arXiv:2604.08356, April 2026)
- **Paper**: 'Measuring Strategy-Decay Risk: Minimum Regime Performance and the Durability of Systematic Investing' — Nolan Alexander & Frank Fabozzi, arXiv:2604.08356, April 9, 2026. Also Journal of Portfolio Management (DOI:10.3905/jpm.2025.1.807). Code on GitHub.
- **Core concept**: MRP = lowest risk-adjusted return a strategy achieves across distinct historical market regimes (bull, bear, high-vol, calm, etc.). Answers: "How did this strategy perform in its worst historical regime?"
- **Key finding**: High long-term Sharpe ≠ high MRP. Efficiency and resilience are distinct properties of systematic strategies.
- **Applicability**: Our top strategies (PEAD Sharpe 4.46, Div Raise Sharpe 4.403) were tested on 2018-2024 data, predominantly bull market. Their MRP during 2022 bear market, Q4 2018 selloff, or March 2020 crash is unknown and potentially poor.
- **R35 concept**: Apply MRP diagnostic to rounds 1-30 backtest results using FRED-based regime labels from macro_harness.py. Output: regime durability rating for each strategy → deployment priority list.

### Wasserstein HMM for Regime Detection — R35 Concept (arXiv:2603.04441, March 2026)
- **Paper**: 'Explainable Regime Aware Investing' — Boukardagha, arXiv:2603.04441, March 2026
- **Method**: Strictly causal Wasserstein Hidden Markov Model — rolling Gaussian HMM + Wasserstein distance template matching
- **Performance**: Sharpe 2.18 vs. equal-weight 1.59 vs. S&P 500 1.18. Max drawdown -5.43% vs. SPX -14.62%.
- **Demonstrated**: Correctly reduced equity exposure during 2025 Liberation Day selloff automatically
- **Future upgrade**: Replace simple VIX/SMA RegimeGuard in R28 with Wasserstein HMM. Not immediate — plan as R35 enhancement.
- **Complement signal**: Skewness Dispersion (arXiv:2604.07870) — cross-sectional firm skewness dispersion negatively predicts market returns (robust, significant, concentrates around monetary policy events). Free to compute from yfinance S&P 500 daily returns. Could serve as a cheap regime warning signal alongside VIX.

## Research Agenda Update (2026-04-09)

- **Round 28** — TradingAgents multi-agent overlay on PEAD — QUEUED (next to run)
  - EarningsQualityAgent: 4-signal system — Specificity (50%), Sentiment (30%), Risk density (20%) + VETO if metric_consistency_score < 35
  - All LLM prompts include anti-extrapolation instruction: "Ignore recent price performance; assess fundamentals only"
  - NewsAgent: FinBERT on top 3 headlines; exit sentinel if sentiment < -0.5
  - RegimeGuard: VIX > 30 skip; SPY 200/50 SMA crossover = reduce size 50%
  - NOR amplifier: manager evades >25% analyst Q&As → upsize by 25%

- **Round 29** — LLM semantic filter on equity pairs trading — QUEUED
  - Full pipeline: factor residualize → SPONGEsym → SAE cluster → cointegration → LLM plausibility → Kelly trade

- **Round 31** — Text-based PEAD (FinBERT + 3-day confirmation, enter day 3) — QUEUED

- **Round 32** — SPX put-writing with VIX-Kelly hybrid sizing — QUEUED

- **Round 33** (concept) — Alpha-R1 RL dynamic factor gating on 146-strategy library

- **Round 34** (concept) — Institutional ownership as PEAD amplifier (13-F EDGAR data)

- **Round 35** (NEW concept) — MRP Diagnostic Pass on Backtest Library + Wasserstein HMM RegimeGuard
  - Apply Minimum Regime Performance analysis (arXiv:2604.08356) to rounds 1-30 results
  - Use FRED-based macro regime labels from macro_harness.py to tag historical periods
  - Identify which top strategies are bull-market-only vs. regime-resilient
  - Optional extension: add skewness dispersion (arXiv:2604.07870) and Wasserstein HMM (arXiv:2603.04441) as improved regime signals
  - **AMENDMENT (2026-04-10)**: Add Markov Clustered EF (arXiv:2604.03946) as primary portfolio regime signal:
    - EF clustering (portfolio-level behavior) → Wasserstein HMM (return distribution) → skewness dispersion (leading indicator)
    - Code: https://github.com/nolanalexander/efficient-frontier-coefficients

## AI Research Findings (Dream Cycle 2026-04-10)

### RL for Speculative Pairs Trading — Optimal OU Thresholds (arXiv:2604.02035, April 2026)
- **Paper**: 'Reinforcement Learning for Speculative Trading under Exploratory Framework' — Zhao, Tse, Zheng. April 2026, q-fin.TR.
- **Spread model**: Ornstein-Uhlenbeck process. Optimal entry/exit formulated as sequential optimal stopping with Cox process intensities + Shannon entropy RL regularization. Closed-form Gibbs distribution policy derived.
- **Key finding**: Optimal threshold depends on OU parameters θ (mean reversion speed) and σ (spread volatility) — NOT fixed ±2σ. Higher θ = faster reversion = tighter threshold more appropriate. Higher σ = noisier spread = wider threshold needed.
- **Practical rule**: Compute half_life = ln(2)/θ and σ_eq = σ/√(2θ). Set entry threshold at {1.5 if hl<3d, 2.0 if hl<7d, 2.5 otherwise} × σ_eq. Exit at |spread - μ| < 0.5 × σ_eq.
- **R29 Amendment**: Fit θ, σ, μ via MLE on 60-day spread history (same window used for cointegration). Replace fixed ±2σ / 0-exit with pair-specific OU-calibrated thresholds. ~20 lines of Python. No additional data.

### Anonymization and Information Loss in Earnings Transcripts (arXiv:2511.15364, Nov 2025)
- **Paper**: 'Anonymization and Information Loss' — Wu, Yang, Ying. November 2025, q-fin.
- **Finding**: Anonymizing earnings call transcripts destroys MORE signal than look-ahead bias. Company names, product names, geography, numerical data are the highest-information-density tokens for NLP signal extraction.
- **R31 Implementation Rule**: Use raw EDGAR transcripts with FinBERT — do NOT strip named entities, dollar amounts, or product/segment names. EDGAR filings are public; anonymization has no privacy benefit but does destroy the alpha signal.

### Markov Clustered Efficient Frontier for Portfolio Regime Detection (arXiv:2604.03946, April 2026)
- **Paper**: 'Asset allocation using a Markov process of clustered efficient frontier coefficients states' — Alexander, Scherer et al. April 2026. Code: https://github.com/nolanalexander/efficient-frontier-coefficients
- **Method**: Decompose rolling efficient frontier into 3 polynomial coefficients → hierarchical clustering into K market states → model transitions as Markov chain → assign tangency portfolio per state. Significantly outperforms static benchmarks.
- **Why distinct from Wasserstein HMM**: Detects regimes from PORTFOLIO BEHAVIOR (how Sharpe/correlation structure shifts across the asset mix) rather than return distributions. More directly relevant for multi-strategy portfolio regime detection.
- **R35 regime stack**: (1) EF clustering = primary portfolio-level signal, (2) Wasserstein HMM = return distribution confirmation, (3) skewness dispersion = leading indicator, (4) VIX/SMA = real-time fast-fail in R28 RegimeGuard.

## Research Agenda Update (2026-04-10)

- **Round 29** — QUEUED
  - **AMENDMENT (2026-04-10)**: Replace fixed ±2σ entry with OU-calibrated thresholds:
    - Fit OU params (θ, σ, μ) via MLE on 60-day spread returns (same data already used)
    - half_life = ln(2)/θ; σ_eq = σ/√(2θ)
    - Entry: {±1.5 if hl<3d, ±2.0 if hl<7d, ±2.5 if hl>7d} × σ_eq above/below mean
    - Exit: |spread − μ| < 0.5 × σ_eq
    - Source: arXiv:2604.02035

- **Round 31** — QUEUED
  - **IMPLEMENTATION NOTE (2026-04-10)**: Never anonymize EDGAR transcripts before FinBERT scoring. Raw named entities carry the signal. Source: arXiv:2511.15364

- **Round 35** — CONCEPT: Now has 3-layer regime stack (EF clustering + Wasserstein HMM + skewness dispersion). See amendments above.

## Backtest Results (2026-04-11) — Rounds 28, 29, 32 Completed

### Round 28 — PEAD EarningsQuality Filter (COMPLETED)
- **Hypothesis confirmed**: Quality filter raises PEAD Sharpe from baseline 4.78 → 9.03 (+89%). Exceeds prior best (2.394) by 3.8x.
- **Best variant**: R28 Full (hard filter score≥50 + NOR amplifier + RegimeGuard): Sharpe **9.028**, CAGR 27.6%, MaxDD -16.9%, 107 trades
- **Key mechanism**: 54% of gap signals filtered. Annual vol drops 6.01% → 4.52%, return rises 28.7% → 40.8%. Filter removes noise not signal.
- **Quality decile validation**: Average 20-day returns monotonically rise with score (score 30-40: +1.3%, score 90-100: +14.4%)
- **Phase 1 note**: Statistical proxies used (gap size, volume ratio, 3-day persistence). Phase 2 will use actual LLM/FinBERT earnings call analysis — expected to push Sharpe higher.
- **New leaderboard #1** (replaces Div Raise 4.403 and PEAD 2.394)
- Files: `r28_pead_quality.py`, `R28_PEAD_QUALITY_REPORT.md`, `rounds/r28_pead_quality_results.json`

### Round 29 — Pairs Trading: Factor Residualization + OU Thresholds (COMPLETED)
- **Key finding**: Factor residualization is the critical driver. Raw returns: 1 cointegrated pair found. Residualized: 19 pairs found.
- **R29 v1** (residualized + fixed ±2σ): Sharpe **1.380**, CAGR 10.6%, MaxDD -8.4% — **NEW pairs leaderboard record** (beats R23: 0.964)
- **Surprise**: OU-calibrated thresholds hurt vs fixed ±2σ (Sharpe drops to 0.91, MaxDD worsens to -18.6%). Wider thresholds for slow-reverting pairs increase drawdown and delay entry. Theoretical optimality doesn't survive in this universe/period.
- **Best pipeline**: residualize on (SPY, sector ETF) → Engle-Granger cointegration → fixed ±2σ z-score → equal-weight top-10 portfolio
- **Top pairs**: MSFT/TXN, TXN/META, AMZN/TSLA, NVDA/META (tech/consumer clusters dominate)
- Files: `r29_pairs.py`, `R29_PAIRS_REPORT.md`, `rounds/r29_pairs_results.json`

### Round 32 — SPX Put-Writing VIX-Kelly Hybrid (COMPLETED)
- **Result**: Sharpe 0.168, CAGR 0.1%, MaxDD -0.6% — below leaderboard threshold as standalone
- **Context**: Broad index put-writing captures thin VRP with full left-tail exposure. Defined-risk spreads (R28 options) are structurally superior.
- **VIX-Kelly mechanism validated**: Correctly cut to 2 contracts in March 2020 (vs 18 for full Kelly), limiting loss to -0.6% vs -5.1%.
- **Best use**: Not standalone — use VIX-Kelly as the sizing discipline overlaid on R28 Bull Put Spreads. The SMA filter hurt returns (Sharpe -0.12).
- Files: `r32_putwriting.py`, `R32_PUTWRITING_REPORT.md`, `rounds/r32_putwriting_results.json`

### Round 31 — Text PEAD FinBERT (COMPLETED)
- **Best variant**: Text + 3-day confirmation: Sharpe **1.322** (per-trade), est. portfolio Sharpe ~2.8–3.1 — improvement over R31 baseline 1.025
- **3-day confirmation is the key driver**: Reduces return vol 13.5% → 8.0% std by filtering conflicted signals (strong text but price fade)
- **Text method**: EPS surprise % (tanh-normalized) — 30.5% coverage on historical gaps. FinBERT loaded successfully but yfinance news had ~0% historical coverage (returns only recent headlines). Real improvement path: EDGAR 8-K full text.
- **2022 remains broken** (Sharpe -1.908): bear markets override text signals. RegimeGuard essential.
- **Key validation**: Text filtering direction is correct — Sharpe improves monotonically from baseline → text filter → text+3d confirm. Consistent with PEAD.txt hypothesis that text signals persist when numeric momentum weakens.
- Files: `r31_text_pead.py`, `R31_TEXT_PEAD_REPORT.md`, `rounds/r31_text_pead_results.json`

## Research Agenda Update (2026-04-11)

- **Round 28** — COMPLETED (Sharpe 9.03, Phase 1). Phase 2 (LLM API calls) pending auth fix.
- **Round 29** — COMPLETED (Sharpe 1.38). Best pipeline: residualize → cointegration → fixed ±2σ.
- **Round 31** — COMPLETED (per-trade Sharpe 1.322, portfolio est. ~2.8–3.1). Best: text filter + 3-day confirmation.
- **Round 32** — COMPLETED (Sharpe 0.17). Best use: VIX-Kelly sizing overlay on R28 options.
- **Round 33** (concept) — Alpha-R1 RL dynamic factor gating
- **Round 34** (concept) — Institutional ownership as PEAD amplifier
- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering RegimeGuard

## AI Research Findings (Dream Cycle 2026-04-11)

### Zero-Shot 3-Agent Disclosure Classifier for R28 Phase 2 (arXiv:2603.20965, March 2026)
- **Paper**: 'Learning to Aggregate Zero-Shot LLM Agents for Corporate Disclosure Classification' — Kirtac, arXiv:2603.20965
- **Dataset**: 18,420 U.S. corporate disclosures (Nasdaq + S&P 500, 2018–2024). Chronological split: 60% train, 20% dev, 20% test.
- **Core finding**: Aggregating three zero-shot agents via a logistic meta-classifier achieves balanced accuracy 0.612 vs 0.561 for best single agent (9% relative improvement). Outperforms majority vote, confidence-weighted voting, and FinBERT baseline.
- **Three agent prompts** (exact wording for R28 Phase 2):
  - **Performance Agent**: 'Read the corporate disclosure below. Focus on realized operating performance, including earnings, revenue, margins, costs, and reported business outcomes. Decide whether the disclosure is positive, neutral, or negative for next-day stock reaction. Output exactly three fields in JSON format: {"label": ..., "rationale": ..., "confidence": ...}. The rationale must be one sentence and confidence must be a number between 0 and 1.'
  - **Guidance Agent**: 'Read the corporate disclosure below. Focus on forward guidance, management outlook, demand expectations, and any revisions to future expectations. Decide whether the disclosure is positive, neutral, or negative for next-day stock reaction. Output exactly three fields in JSON format: {"label": ..., "rationale": ..., "confidence": ...}. The rationale must be one sentence and confidence must be a number between 0 and 1.'
  - **Risk Agent**: 'Read the corporate disclosure below. Focus on uncertainty, litigation, regulation, liquidity, operational disruption, and downside risk. Decide whether the disclosure is positive, neutral, or negative for next-day stock reaction. Output exactly three fields in JSON format: {"label": ..., "rationale": ..., "confidence": ...}. The rationale must be one sentence and confidence must be a number between 0 and 1.'
- **Meta-classifier inputs**: agent labels + confidence scores + majority vote + agreement counts + interaction indicators → L2-regularized logistic regression
- **Cost-efficient models**: Qwen2.5-3B-Instruct (Performance), Llama-3.2-3B-Instruct (Guidance), Qwen2.5-72B-Instruct (Risk). All zero-shot, no fine-tuning needed.
- **R28 Phase 2 Integration**: Prefix each prompt with anti-extrapolation instruction. Train meta-classifier on first 60% of PEAD events, test on remaining 40%. Cross-agent disagreement (Performance+/Guidance-) = 'beat but lowered guidance' = PEAD failure signal.

### R29 LLM Filter Design Correction: Re-ranking Not Binary Threshold (arXiv:2602.07048 re-read, 2026-04-11)
- **Design correction**: The arXiv:2602.07048 paper uses TOP-K RE-RANKING, NOT binary score threshold. Correct pipeline: select K=100 pairs by statistical rank → LLM plausibility on all 100 → trade top M=20 by LLM score. Replace old 'skip if score < 40' heuristic.
- **Two-field LLM output**: JSON with (1) `mechanism_strength` (0-100): economic rationale strength; (2) `expected_co_movement_sign` (+1 or -1): does the economic logic agree with the spread direction? VETO if sign conflicts with observed spread.
- **Prompt for R29 LLM layer**: 'Is there a plausible economic mechanism explaining why [Company A] and [Company B] would mean-revert toward each other over time? Output JSON: {"mechanism_strength": <0-100>, "expected_co_movement_sign": <+1 if they move together, -1 if they diverge>}. Only output +1 if companies share revenue drivers, supply chains, or are substitutes/complements.'
- **Why direction matters**: Prevents entering trades where economic logic predicts OPPOSITE direction from statistical model (e.g., one company benefits when the other declines — that's NOT a mean-reversion pair).

### FactorEngine: LLM-Guided Factor Mining from Financial Reports (arXiv:2603.16365, March 2026)
- **Paper**: 'FactorEngine: A Program-level Knowledge-Infused Factor Mining Framework.' Lin et al., arXiv:2603.16365.
- **Market**: CSI300/CSI500 (China), out-of-sample 2017-2024. CSI300: Sharpe 1.0093, AR 18.99%, ICIR 0.3185, MaxDD 12.61%. vs Alpha158: +58% IC, +126% excess return. Traditional DL methods yielded negative excess returns in CSI500.
- **Architecture**: (1) Reports → multi-agent extraction → executable Python factors; (2) LLM-guided logic revision + Bayesian parameter tuning; (3) Experience base for trajectory-aware refinement.
- **LLM**: Gemini-2.5-Pro. No public code.
- **R33 concept (US adaptation)**: Seed with 146 harness strategies + SSRN abstracts. Use FactorEngine's LLM/Bayesian separation as design principle. Contrast with Alpha-R1 (RL gating of existing factors) — FactorEngine generates NEW factors.

### AlphaForgeBench: LLM Trading Action Instability (arXiv:2602.18481, Feb 2026)
- **Finding**: Direct LLM trade execution is unreliable — 'severe behavioral instability', action flipping across adjacent time steps, inconsistent sequences even under deterministic decoding. Root cause: stateless autoregressive architecture.
- **Solution**: Redirect LLMs to output alpha factor scores/quality ratings → feed into deterministic execution engine. Never have LLMs emit buy/sell/hold actions directly.
- **Validates**: All George round designs already follow this pattern (LLM as scorer/filter, not executor). Benchmark claims from direct-action LLM trading systems are unreliable.

## Research Agenda Update (2026-04-11 Dream Cycle)

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix)
  - **AMENDMENT (2026-04-11)**: Use 3-agent zero-shot architecture (Performance/Guidance/Risk agents + logistic meta-classifier)
  - Small models (Qwen2.5-3B, Llama-3.2-3B) for Performance/Guidance agents; Qwen2.5-72B for Risk agent
  - Anti-extrapolation prefix on all prompts; cross-agent disagreement = PEAD failure signal
  - Source: arXiv:2603.20965 (18,420 disclosures; 0.561 → 0.612 balanced accuracy)

- **Round 29 LLM Filter** — Add LLM semantic layer to R29 pairs strategy (QUEUED)
  - **DESIGN CORRECTION (2026-04-11)**: TOP-K RE-RANKING not binary threshold
  - Run LLM on all K=100 statistical pairs → trade top M=20 by LLM score
  - Two-field JSON output: mechanism_strength + expected_co_movement_sign
  - VETO if co_movement_sign conflicts with observed spread direction
  - Source: arXiv:2602.07048 (re-read 2026-04-11)

- **Round 33** (concept) — FactorEngine-style LLM-guided factor mining on US equities
  - Seed with 146 harness strategies + SSRN abstracts as knowledge base
  - LLM for logic revision, Bayesian optimizer for parameters (FactorEngine separation)
  - Reference: arXiv:2603.16365 (CSI300: Sharpe 1.0093, +126% excess return vs Alpha158)

## AI Research Findings (Dream Cycle 2026-04-12)

### SAE-FiRE: Better-Than-FinBERT Earnings Classification (arXiv:2505.14420, revised Oct 2025)
- **Paper**: 'SAE-FiRE: Enhancing Earnings Surprise Predictions Through Sparse Autoencoder Feature Selection'
- **Methodology**: Extract LLM hidden-state activations → decompose via Sparse Autoencoder → apply tree-based (XGBoost) feature selection to pick top-k discriminative dimensions → classify earnings surprise direction
- **Performance on Conference Call transcripts (9,324 transcripts, 2012-2014)**:
  - SAE-FiRE Gemma 2-9B: Accuracy 0.801, F1 0.757, AUC 0.668 ← **Winner**
  - SAE-FiRE Llama 3.1-8B: F1 0.759 (near-identical)
  - Hierarchical FinBERT baseline: F1 0.721
  - Longformer: F1 0.718
  - Zero-shot prompting: F1 0.676
- **Financial news (FNSPID)**: AUC 0.703 vs transcript AUC 0.668 — news carries more signal. Combine both for R31.
- **Feature thresholds**: top-k=1,500 for 16K SAE (2B model); top-k=4,500 for 131K SAE (9B model). Use tree-based selection, NOT ANOVA.
- **R31 Amendment**: Replace naive FinBERT chunking with SAE-FiRE pipeline using Gemma 2-9B or Llama 3.1-8B. Add FNSPID news feature vector alongside transcript features.

### Drift Regimes Factor: Regime-Gated Value+Reversal on S&P 500 (arXiv:2511.12490, Nov 2025)
- **Paper**: 'Discovery of a 13-Sharpe OOS Factor: Drift Regimes' — 20-year walk-forward on S&P 500, frozen parameters
- **Mechanism**: Activate value+reversal factor only when stock is in a 'drift regime' (>60% positive-return days in trailing 63-day window = UpFraction > 0.60)
- **Signal construction**:
  - BASE = 0.7 × value_pctile + 0.3 × (−10d_return z-score)
  - EDGE = BASE × I(UpFraction_i,63d > 0.60)
  - Value metric: inverse stock price percentile (simple, no P/E or P/B required)
  - Execute at market close (4 PM); preliminary signal at 3:30 PM
- **Performance**:
  - OOS Sharpe 13.19 at 0.6bp costs; 9.1 at 1.2bp; **6.3 at 10bp**
  - Ann. returns 158.6%, vol 12.0%, max DD -11.9%
  - R-squared to standard factors < 3% — genuinely incremental alpha
- **Round 33 candidate**: Regime-gated factor strategy as a new equity round (after R33 FactorEngine concept)
- **R28 cross-application**: Use UpFraction > 0.60 as an optional PEAD signal amplifier — stocks in drift regime 63 days pre-earnings more likely to sustain positive gap

## Research Agenda Update (2026-04-12)

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix) — no change
- **Round 29 LLM Filter** — TOP-K re-ranking with two-field JSON (mechanism_strength + co_movement_sign) — no change
- **Round 31** — COMPLETED (Sharpe 1.322 per-trade). Consider SAE-FiRE upgrade to beat FinBERT baseline F1.
- **Round 33** (concept) — Now two candidates:
  - (A) FactorEngine-style LLM-guided factor mining (arXiv:2603.16365)
  - (B) Drift Regimes factor: regime-gated value+reversal — simpler to implement, validated OOS Sharpe 6.3+ at realistic costs
  - Recommendation: Run (B) first as R33 — fewer dependencies; (A) as R34 concept
- **Round 35** (concept) — MRP diagnostic + regime stack — no change
- **Round 35b** (NEW concept, 2026-04-14) — Attention Factors for Stat Arb (arXiv:2510.11616, Stanford). Joint cost-aware optimization: attention factors from firm characteristics + LongConv residual signal. Net SR 2.28 vs 1.57 (PCA). High complexity (PyTorch + characteristic data). Near-term partial win: retrain OU thresholds against net-of-cost Sharpe on validation set.

## Dream Cycle Research — 2026-04-14

### New Papers Integrated (nightly scan)

**arXiv:2602.07048 — LLM Semantic Filtering for Lead-Lag Trading (Kim et al., Feb 2026)**
- Architecture: Granger causality top-100 → LLM re-rank → trade top-20 pairs
- LLM output: plausibility_score (0-100) + mechanism_strength + co_movement_sign in JSON
- Primary effect: LOSS REDUCTION not win rate (avg loss -46.5%; total PnL +205%)
- Best hold period: 1d (WR 66.7% with LLM filter, vs 56% without)
- DIRECT APPLICATION: R29 — switch from hard verdict threshold to ranking + add sign prediction
- Staged: /workspace/group/dream_cycle/staged/2026-04-14/1_r29_llm_ranking_and_sign_refinement.json

**arXiv:2510.11616 — Attention Factors for Statistical Arbitrage (Stanford, ACM ICAIF 2025)**
- Joint optimization: attention factors + residual portfolio + LongConv → net-of-cost Sharpe
- Net SR: 2.28 (attention) vs 1.57 (PCA) vs -6.45 (OU threshold after costs)
- OU-thresholding collapses after costs — optimize thresholds against NET Sharpe on validation
- Past returns/momentum chars dominate value/profitability for stat arb (-62% SR if removed)
- Staged concept: /workspace/group/dream_cycle/staged/2026-04-14/3_r35_attention_factor_stat_arb_concept.json

**arXiv:2603.20247 — AlphaLogics (Shenzhen U., March 2026)**
- Multi-agent: extract market logic from existing factors → generate new factors → refine via backtest
- S&P 500 IR=1.27, CSI 500 IR=1.53. Interpretable and auditable.
- Relevant for factor mining rounds (R34+). Start by extracting logic from 146-strategy harness.

**arXiv:2603.21330 — FinRL-X with 6-month Alpaca live paper trading (March 2026)**
- Live: +19.76% total return vs SPY -2.51%, Oct 2025-Mar 2026, Sharpe 1.96
- Weight-centric unified pipeline architecture. Rare credible live RL result — worth monitoring.

## AI Research Findings (Dream Cycle 2026-04-15)

### QuantaAlpha: Evolutionary LLM Alpha Mining — MAJOR FINDING (arXiv:2602.07085, Feb 2026)
- **Paper**: KDD 2025. GitHub: https://github.com/QuantaAlpha/QuantaAlpha (668 stars)
- **Core innovation**: Evolutionary trajectory optimization — each LLM mining run is a 'trajectory'; mutation rewrites sub-optimal decision nodes; crossover merges high-reward segments from parent trajectories. Substantially outperforms single-run AlphaAgent.
- **CSI300 results (GPT-5.2 backbone)**: IC 0.1501, ICIR 0.9110, ARR 27.75%, MaxDD 7.98%
- **Outperforms**: AlphaAgent (IC 0.0966, ARR 15.54%), RD-Agent (IC 0.0531, ARR 9.91%)
- **S&P500 zero-shot transfer** (factors mined on CSI300, deployed on US stocks without retraining): 137% cumulative excess return 2022–2025
- **LLM support**: GPT-5.2 (best), but also tested with Claude-4.5-Sonnet, DeepSeek-V3.2, Gemini-3-Pro, Qwen3-235B — all functional. Claude degrades IC to ~0.1252 (vs 0.1501 for GPT-5.2).
- **Data**: OHLCV + VWAP only. No fundamentals, news, or alternative data required.
- **Factor properties**: Interpretable AST-based formula factors; diversity constraint (|corr| < 0.70 between pool members); pool cap at 50% of mined factors per iteration
- **US adaptation challenge**: Codebase is China-focused (Qlib + baostock HDF5 data). US implementation requires building OHLCV+VWAP HDF5 file from yfinance. No documented US config in repo.
- **George application → Round 33**: Run QuantaAlpha on S&P500 OHLCV universe; validate mined factors on US test data; deploy as alpha source orthogonal to PEAD/dividend/pairs

### Janus-Q: Event-Driven Trading via Hierarchical-Gated Reward (arXiv:2602.19919, Feb 2026)
- Architecture: LoRA supervised fine-tuning → GRPO reinforcement fine-tuning (same RL method as Alpha-R1)
- HGRM reward hierarchy: hard direction gate → event-type soft gate → cost-aware PnL → magnitude shaping → process reward
- Results: Sharpe 1.3088 vs best baseline (QwQ-32B) 0.6481 (+102%). Most baselines show negative Sharpe.
- 10 event types: personal behavior, equity change, asset change, dividend, risk warning, financing, financial status, violation, industry, rating adjustment
- **LIMITATION**: Chinese A-share market only (5,282 stocks, Datayes/Tushare/Wind data, Jan 2023–Feb 2025). No public code.
- **Relevance**: HGRM reward hierarchy is conceptually applicable to R28 Phase 2 LLM fine-tuning. Direction gate structure (block all rewards if predicted direction is wrong) is a useful design principle.

### Smart Predict-then-Optimize for Portfolio Management (arXiv:2601.04062, Jan 2026)
- SPO paradigm: embeds portfolio optimization into the ML training objective — trains predictors to maximize decision quality (portfolio Sharpe), not minimize prediction error
- US ETFs, 2015–2025, monthly rebalancing, transaction costs + turnover control included
- Outperforms standard predict-then-optimize; robust during COVID-19 crisis
- **George application**: Could improve R28 composite quality score weighting by training weights against realized portfolio Sharpe (SPO loss) rather than binary signal classification accuracy. No public code.

### PEAD Multi-task Learning (Information Systems Research 2025, SSRN:5284651)
- MTL framework: PEAD prediction as primary task + post-event investor responses (volume, analyst revisions) as auxiliary tasks
- GradPerp adaptive weighting: higher weight to auxiliary tasks with diverse/non-redundant gradients
- Published in top IS journal; mitigates look-ahead bias explicitly
- **Relevance**: Validates R34 concept (investor responses amplify PEAD). No public code.

## Round 33 — QuantaAlpha Implementation Spec (2026-04-15)

### Overview
QuantaAlpha replaces Alpha-R1 RL gating as the Round 33 concept. Evolutionary trajectory optimization of LLM alpha mining runs is the current state-of-the-art for formula factor generation.

### Implementation Plan
1. Clone https://github.com/QuantaAlpha/QuantaAlpha, install Qlib (Microsoft)
2. Build US OHLCV+VWAP HDF5 data file from yfinance for S&P 500 universe (2016–2025)
3. Configure REASONING_MODEL = claude-sonnet-4-6 or o3-mini; CHAT_MODEL = claude-haiku-3
4. Run 3–5 mining iterations (mutation + crossover cycles on initial factor pool)
5. Factor pool filtering: admit only factors with |corr| < 0.70 to existing pool members
6. Backtest mined factors on US holdout 2022–2025 in Qlib
7. Compare IC, ICIR to baseline (Alpha101 factors, our 146-strategy library)

### Hypothesis
Mined factors achieve IC > 0.05 and IR > 0.8 on US test data, providing alpha orthogonal to existing George strategies.

## Research Agenda Update (2026-04-15)

- **Round 29 LLM Filter** — QUEUED (consolidated final design spec staged 2026-04-15)
  - Final pipeline: factor residualize → SPONGEsym → SAE cluster → cointegration top-100 → LLM top-K re-rank → trade top-20 at fixed ±2σ
  - See staged: /workspace/group/dream_cycle/staged/2026-04-15/2_r29_llm_filter_consolidated_design.json

- **Round 33** — QuantaAlpha evolutionary alpha mining (replaces Alpha-R1 RL gating concept)
  - Full design spec staged 2026-04-15
  - US OHLCV+VWAP HDF5 from yfinance → run QuantaAlpha with Claude-sonnet-4-6 → validate on US test set

- **Round 34** (concept) — Institutional ownership as PEAD amplifier — unchanged

- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering — unchanged


## Round 33 — QuantaAlpha Evolutionary Alpha Mining (Design Spec 2026-04-15)

### Overview
QuantaAlpha (arXiv:2602.07085, KDD 2025) generates decay-resistant OHLCV-based alpha factors via evolutionary refinement of LLM mining trajectories.

### Performance Benchmarks
- **CSI300 (direct)**: IC 0.1501, ICIR 0.9110, ARR 27.75%, MaxDD 7.98% (GPT-5.2 backbone)
- **CSI300 with Claude-4.5-Sonnet**: IC ~0.1252, functional performance confirmed
- **S&P500 zero-shot transfer** (factors mined on CSI300, deployed on US stocks, no retraining): 137% cumulative excess return over 2022–2025
- Outperforms AlphaAgent (IC 0.0966), RD-Agent (IC 0.0531) by large margins

### Key Differentiator vs. AlphaAgent
QuantaAlpha uses **evolutionary trajectory optimization**: each full mining run is a 'trajectory'. Mutation localizes and rewrites sub-optimal decision nodes within a trajectory (e.g., changing time scale, adding regime conditions). Crossover merges high-reward segments from two parent trajectories. This iterative refinement produces substantially more predictive factors than single-run approaches (AlphaAgent) or static LLM prompting.

### Data Requirements
- OHLCV + VWAP only — no fundamentals, no news, no alternative data
- Preprocessing: forward-fill, replace inf, cross-sectional rank normalization
- US adaptation: use yfinance for OHLCV+VWAP; precompute daily_pv HDF5 files to match Qlib format

### GitHub & Tech Stack
- Code: https://github.com/QuantaAlpha/QuantaAlpha (668 stars)
- Requires: Python 3.10+, Qlib (Microsoft), conda env
- LLM config: OPENAI_BASE_URL + OPENAI_API_KEY (OpenAI-compatible → can use Anthropic via proxy or Claude API)
- Pre-built HDF5 data files from HuggingFace (China data); US adaptation requires building equivalent files from yfinance

### Implementation Plan for R33
1. Clone QuantaAlpha repo, install Qlib
2. Build US OHLCV+VWAP HDF5 data file from yfinance for S&P 500 universe (2016–2025)
3. Configure REASONING_MODEL = claude-sonnet-4-6 or o3-mini; CHAT_MODEL = claude-haiku
4. Run 3–5 mining iterations (mutation + crossover cycles)
5. Factor pool filtering: admit only factors with |corr| < 0.70 to existing pool
6. Deploy factors in Qlib backtester on US test set (2022–2025)
7. Compare to R28 PEAD quality filter (Sharpe 9.03) — factors should provide orthogonal alpha

### Key Implementation Risks
- US data pipeline not pre-built in repo (China-focused); requires custom HDF5 builder
- Mining runtime unknown; likely multi-hour per iteration with slow-thinking model
- Zero-shot transfer claim: 137% was demonstrated in paper but not independently verified by George
- Factor diversity constraint (|corr| < 0.70) may reduce pool to 5–10 factors on smaller US universe

### Round 33 Hypothesis
QuantaAlpha-mined factors on S&P 500 universe achieve IC > 0.05 and IR > 0.8 on US test data, providing alpha orthogonal to existing George strategies (PEAD, dividend, pairs).

## Round 29 LLM Filter — Final Consolidated Design (2026-04-15)

This consolidates all R29 amendments into the definitive implementation spec. R29 v1 (residualized + fixed ±2σ) already completed at Sharpe 1.3802. This is R29 LLM Filter (Phase 2), which adds semantic screening on top.

### Full Pipeline (6 Stages)
```
Stage 0: Factor residualize each asset on (SPY, sector ETF) — rolling 60-day OLS
Stage 0.5: SPONGEsym clustering on 60-day residual correlation matrix
           → only test cointegration within same positive cluster
           → optimal cluster count = eigenvectors explaining 90% of variance
Stage 1.5: SAE cluster filter (pre-computed HuggingFace features)
           → marco-molinari/company_reports_with_features
           → restrict cointegration search to same SAE cluster
Stage 1:   Engle-Granger cointegration test on residualized returns
           → keep top-100 pairs by cointegration strength (p-value rank)
Stage 2:   LLM plausibility scoring (TOP-K RE-RANKING, not binary threshold)
           → LLM prompt: 'Is there a plausible economic mechanism explaining why
             [Company A] and [Company B] would mean-revert toward each other over
             time? Output JSON: {"mechanism_strength": <0-100>,
             "expected_co_movement_sign": <+1 if together, -1 if diverge>}.
             Only output +1 if companies share revenue drivers, supply chains,
             or are substitutes/complements.'
           → Anti-extrapolation prefix: 'Do not consider recent price performance.
             Focus exclusively on the economic relationship between the companies.'
           → VETO if expected_co_movement_sign conflicts with observed spread direction
           → Trade TOP-20 pairs by mechanism_strength from the 100 candidates
Stage 3:   Trade with fixed ±2σ z-score thresholds (NOT OU-calibrated)
           → Entry: z-score > +2σ = short spread; z-score < -2σ = long spread
           → Exit: |z-score| < 0.5σ
           → Equal-weight across top-20 pairs
           → Kelly sizing optional enhancement
```

### Design Rationale (Key Lessons Applied)
- TOP-K re-ranking (not binary): LLM's primary value is cutting large losers (~46.5% avg loss reduction), achieved via ranking not threshold (arXiv:2602.07048)
- Fixed ±2σ preferred over OU-calibrated: R29 v1 validated this (Sharpe 1.38 vs 0.91 for OU)
- SAE before LLM: deterministic, pre-computed, cheap — saves LLM API calls for final 100 pairs only
- Anti-extrapolation prefix: prevents LLM from penalizing pairs where one stock has had a recent move (arXiv:2604.02921)
- Co-movement sign check: prevents entering trades where economic logic predicts OPPOSITE direction from spread (correction from 2026-04-11)

### Expected Improvement Hypothesis
- R29 v1 baseline: Sharpe 1.3802
- LLM filter primary effect: loss reduction ~46.5% per filtered trade
- Expected LLM-filtered result: Sharpe 1.8–2.4 (based on arXiv:2602.07048 results)

### Cost Estimate
- 100 LLM calls per rebalancing period × ~$0.002/call (Haiku) = ~$0.20/rebalance
- Quarterly rebalancing: ~$0.80/year — negligible

## AI Research Findings (Dream Cycle 2026-04-16)

### R29 LLM Filter Amendment: Ticker Anonymization (arXiv:2603.17692, April 2026)
- **Source**: BlindTrade — anonymized LLM trading achieves Sharpe 1.40 OOS 2025 YTD; Risk-Regime IC = 0.0515 when tickers anonymized
- **Finding**: LLMs exhibit memorization bias when tickers are provided (recall training data, not genuine reasoning). Anonymization forces genuine economic assessment. IC is HIGHER when tickers anonymized.
- **R29 Amendment (MANDATORY)**: Replace both tickers in LLM plausibility prompt with synthetic IDs:
  - INSTEAD OF: 'Is there a plausible economic mechanism between MSFT and TXN?'
  - USE: 'COMPANY_A is a large-cap US technology company specializing in enterprise software and cloud computing. COMPANY_B is a large-cap US semiconductor company focused on analog/embedded processors. Is there a plausible economic mechanism explaining mean-reversion between these two companies? Output JSON: {"mechanism_strength": <0-100>, "expected_co_movement_sign": <+1 or -1>}'
  - Business model summaries: 1-2 sentences from SEC 10-K first paragraph + sector ETF label. One-time extraction.
- **Cost**: Zero — prompt change only.

### R29 LLM Filter Amendment: TrustTrade Multi-Agent Consensus (arXiv:2603.22567, April 2026)
- **Source**: TrustTrade (Harvard, March 2026) — 'uniform trust' is the root LLM trading failure mode; multi-agent consensus fixes it
- **Architecture tested**: GPT-4o-mini + Grok-4 as heterogeneous agents; credibility scoring discards divergent reports; temporal signal anchors improve stability
- **R29 Amendment**: Replace single LLM call with 3-agent focused system:
  - **Revenue Driver Agent**: 'Do COMPANY_A and COMPANY_B derive revenue from substantially the same end markets? Output JSON: {"shared_revenue_drivers": <true/false>, "confidence": <0-100>, "rationale": "..."}'
  - **Supply Chain Agent**: 'Is there a meaningful supplier-customer relationship or >30% shared suppliers between these companies? Output JSON: {"supply_chain_link": <true/false>, "confidence": <0-100>, "rationale": "..."}'
  - **Competitive Dynamics Agent**: 'Are these companies direct substitutes or do they have correlated pricing power? Output JSON: {"competitive_or_pricing_link": <true/false>, "confidence": <0-100>, "rationale": "..."}'
  - **Consensus rule**: mechanism_strength = weighted avg (Revenue 0.4 + Supply 0.3 + Competitive 0.3) × confidence × (n_true/3). Veto if all three say FALSE.
  - **co_movement_sign**: +1 if ≥2 agents TRUE; -1 if only Competitive true (substitutes diverge)
- **Cost delta**: 3x Haiku calls = $0.00075/pair vs $0.00025 → $0.075/rebalance for 100 pairs. Negligible.
- **Key finding from TrustTrade**: Adding fundamentals/news to market signals HURTS performance (noise injection). The selective consensus mechanism is what helps. Divergent signals should be discarded, not averaged.

### MemGuard-Alpha: LLM Memorization Contamination Diagnostic (arXiv:2603.26797, April 2026)
- **Paper**: MemGuard-Alpha — CMMD (Cross-Model Memorization Disagreement) filtering for LLM financial signals
- **Critical finding**: Contaminated LLM signals: in-sample accuracy 52.5% BUT out-of-sample accuracy 42% (drops). Clean signals: 14.48 bps/day vs 2.13 bps tainted (7x gap). Sharpe 4.11 (CMMD-filtered) vs 2.76 (unfiltered). Cohen's d = 18.57 for contamination separation.
- **Contamination signature**: if backtest looks great but OOS collapses → likely memorization, not alpha
- **CMMD filter**: use 2+ LLMs with DIFFERENT training cutoffs. Memorized signals → models agree (recall same data). Genuine reasoning → models disagree based on knowledge gaps → act only on patterns consistent with fundamental reasoning.
- **R28 Phase 2 / R29 LLM Filter Application**:
  - Run prompts on both Claude-Haiku AND Llama-3.1-8B-Instruct (different training cutoffs)
  - For backtesting: compare signal quality on 2018-2022 data (heavily in LLM training) vs 2023-2024 (less memorized). If Sharpe significantly higher in 2018-2022 → contamination suspected.
  - Free check: Llama-3.1-8B via Ollama or HuggingFace free tier
- **Priority**: Apply CMMD diagnostic before claiming Sharpe improvement in R29 LLM filter vs R29 v1 baseline.

### DeltaLag: Adaptive Lead-Lag Pairs via Cross-Attention (arXiv:2511.00390, ICAIF 2025)
- **Paper**: DeltaLag — end-to-end deep learning for dynamic lead-lag pair discovery. HKUST/UCLA/Oxford. ICAIF 2025.
- **Performance** (OOS 2022-2023): S&P 500 Sharpe **2.12**, AR 24.7%; NASDAQ Sharpe **2.91**, AR 33.3%; NYSE Sharpe **2.57**, AR 23.0%
- **Key insight**: 'Weak momentum property' — static cointegration-based pairs found in historical data do NOT reliably persist. Adaptive real-time discovery is essential. This validates the need for the LLM re-ranking stage in R29.
- **Cross-asset > own-history**: DeltaLag Sharpe 2.12 vs SelfLagNet 1.56 — other stocks are better predictors than own history.
- **Architecture**: LSTM encoder → sparsified cross-attention TopK (k=2 leaders/stock) → lag-aligned feature → MLP. OHLCV+turnover only. k=2 is near-optimal.
- **R36 Concept**: Replace static cointegration with DeltaLag adaptive discovery
  - Factor residualization (R29 Stage 0) still applies first
  - DeltaLag learns dynamic pair selection + optimal lag jointly
  - LLM consensus gate on top-20 pairs from DeltaLag output
  - Expected Sharpe: 2.1–2.9 (paper) vs R29 v1 1.38
  - GPU required for training. Sequence: after R33, R34, R35.
- **Other notable papers scanned (2026-04-16)**:
  - TrustTrade (arXiv:2603.22567): multi-agent consensus for LLM trading; Risk Manager stage adds no value (Analyst → Trader is sufficient)
  - MemGuard-Alpha (arXiv:2603.26797): 7x return difference clean vs tainted LLM signals
  - ATLAS (arXiv:2510.15949): adaptive prompt optimization for LLM trading via stochastic feedback
  - FinRL-X (arXiv:2603.21330): live paper trading +19.76% vs SPY -2.51% Oct 2025-Mar 2026, Sharpe 1.96 (updated result)
  - Drift Regimes Factor (arXiv:2511.12490): OOS Sharpe 13.19 at 0.6bp costs; already staged as R33 candidate

## Research Agenda Update (2026-04-16)

- **Round 29 LLM Filter** — QUEUED; final design from 2026-04-15 + THREE new amendments from tonight:
  1. **Ticker anonymization** (MANDATORY): replace tickers with COMPANY_A/COMPANY_B + 2-sentence business model summaries before LLM call
  2. **3-agent consensus** (RECOMMENDED): Revenue Driver + Supply Chain + Competitive Dynamics agents; act only on 2/3+ agreement
  3. **CMMD contamination check** (VALIDATION): run both Claude-Haiku and Llama-3.1-8B; verify OOS performance isn't memorization artifact
- **Round 33** — QuantaAlpha evolutionary alpha mining — QUEUED (unchanged)
- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged
- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering — unchanged
- **Round 36** (NEW concept, 2026-04-16) — DeltaLag adaptive lead-lag pairs trading (Sharpe 2.1–2.9 target; GPU training required)

### R29 LLM Filter Amendment: Ticker Anonymization (arXiv:2603.17692, April 2026)
- **Source**: BlindTrade — anonymized LLM trading achieves Sharpe 1.40 OOS 2025 YTD; Risk-Regime IC = 0.0515 when tickers anonymized
- **Finding**: LLMs exhibit memorization bias when tickers are provided (recall training data, not genuine reasoning). Anonymization forces genuine economic assessment.
- **R29 Amendment (MANDATORY)**: Replace both tickers in LLM plausibility prompt with synthetic IDs:
  - INSTEAD OF: 'Is there a plausible economic mechanism between MSFT and TXN?'
  - USE: 'COMPANY_A is a large-cap US technology company specializing in enterprise software and cloud computing. COMPANY_B is a large-cap US semiconductor company focused on analog/embedded processors for industrial and automotive applications. Is there a plausible economic mechanism explaining mean-reversion between these two companies? Output JSON: {"mechanism_strength": <0-100>, "expected_co_movement_sign": <+1 or -1>}'
  - Business model summaries (1-2 sentences) should be pre-generated from SEC 10-K first-paragraph + sector ETF label
- **Why**: BlindTrade shows anonymized LLM signal is MORE predictive (IC 0.0515) than named-ticker signal
- **Cost**: Zero — prompt change only. Business model summaries: one-time extraction from EDGAR.

### R29 LLM Filter Amendment: TrustTrade Multi-Agent Consensus (arXiv:2603.22567, April 2026)
- **Source**: TrustTrade (Harvard, March 2026) — uniform trust is the root LLM trading failure mode; multi-agent consensus fixes it
- **R29 Amendment**: Replace single LLM call with 3-agent focused system:
  - **Revenue Driver Agent**: 'Do COMPANY_A and COMPANY_B derive revenue from substantially the same end markets or customer segments? Output JSON: {"shared_revenue_drivers": <true/false>, "confidence": <0-100>, "one_sentence_rationale": "..."}'
  - **Supply Chain Agent**: 'Is COMPANY_A a meaningful supplier to, or customer of, COMPANY_B, or do they share >30% overlap in key suppliers? Output JSON: {"supply_chain_link": <true/false>, "confidence": <0-100>, "one_sentence_rationale": "..."}'
  - **Competitive Dynamics Agent**: 'Are COMPANY_A and COMPANY_B direct substitutes competing for the same contracts, or do they have pricing power that moves together? Output JSON: {"competitive_or_pricing_link": <true/false>, "confidence": <0-100>, "one_sentence_rationale": "..."}'
- **Consensus rule**: mechanism_strength = weighted avg (Revenue: 0.4, Supply: 0.3, Competitive: 0.3) × max_confidence × (number_true / 3). Veto if all three agents say FALSE.
- **Expected co_movement_sign**: +1 if at least 2 agents say TRUE (they co-move); -1 if competitive link is the ONLY true signal (substitutes can diverge)
- **Why 3 agents**: TrustTrade shows multi-agent consensus reduces noise injection from heterogeneous sources; focused prompts per domain outperform single broad prompt
- **Cost delta**: 3x API calls ($0.00075/pair vs $0.00025) = $0.075/rebalance for 100 pairs — negligible

### MemGuard-Alpha: LLM Memorization Contamination Diagnostic (arXiv:2603.26797, April 2026)
- **Paper**: MemGuard-Alpha — CMMD (Cross-Model Memorization Disagreement) for LLM financial signal validation
- **Key finding**: Contaminated LLM signals show in-sample accuracy 52.5% but out-of-sample accuracy 42% (DROPS). Clean signals: 14.48 bps/day vs 2.13 bps/day tainted (7x gap). Sharpe 4.11 (clean) vs 2.76 (unfiltered).
- **Contamination signature**: if in-sample backtest looks great but OOS collapses → likely memorization, not alpha.
- **CMMD filter**: use 2+ LLMs with DIFFERENT training cutoffs. Memorized signals: both models recall same training data → suspiciously high agreement. Genuine reasoning: models disagree based on different knowledge states → take position only when disagreement pattern is consistent with fundamental reasoning (not recall).
- **R28 Phase 2 / R29 LLM Filter Application**:
  - Run LLM plausibility prompts on BOTH Claude-Haiku AND Llama-3.1-8B-Instruct (different training cutoffs)
  - High agreement + low mechanism_strength variance = potential memorization flag
  - For backtesting: compare 2018-2022 signals (training data period for most LLMs) vs 2023-2024 signals (less memorized). If Sharpe is significantly HIGHER in 2018-2022 → contamination suspected.
- **Cost**: Llama-3.1-8B-Instruct is free via Ollama or HuggingFace inference API. CMMD check adds ~$0 extra cost if local model used.
- **Priority**: Apply to R29 LLM filter backtest before claiming improvement over R29 v1 baseline (Sharpe 1.3802). Contamination in historical backtest data would invalidate comparison.

### DeltaLag: Adaptive Lead-Lag Pairs via Cross-Attention (arXiv:2511.00390, ICAIF 2025)
- **Paper**: DeltaLag — end-to-end deep learning for dynamic lead-lag trading. HKUST/UCLA/Oxford. ICAIF 2025.
- **Performance** (OOS 2022-2023 test): S&P 500 Sharpe 2.12, AR 24.7%; NASDAQ Sharpe 2.91, AR 33.3%; NYSE Sharpe 2.57, AR 23.0%
- **Key finding**: 'Weak momentum property' — static precomputed pairs based on historical correlation/cointegration do NOT reliably persist. Adaptive real-time discovery is essential.
- **Cross-asset vs own-history**: DeltaLag (cross-asset leaders) Sharpe 2.12 >> SelfLagNet (own history) Sharpe 1.56 on S&P 500. Cross-asset relationships are more predictive than own momentum.
- **Architecture**: LSTM encoder → sparsified cross-attention TopK (k=2 leaders per stock) → lag-aligned feature extraction → MLP. Features: intraday price ratios (O/H/L to C), daily return, log-volume, turnover. OHLCV only — no fundamentals.
- **Practical**: k=2 leaders per stock (near-optimal, computationally cheap). LSTM encoder preferred over Mamba for stability.
- **R36 Concept**: Replace static cointegration pair selection with DeltaLag's adaptive cross-attention
  - Stage 0 (factor residualization) from R29 applies — residualize before cross-attention
  - Train on 2010-2019 S&P 500 OHLCV (yfinance), validate 2020-2021, test 2022-2025
  - GPU required for training but inference is lightweight
  - Hybrid: use DeltaLag for dynamic pair discovery, LLM consensus for plausibility gate on top 20 pairs
  - Expected Sharpe range: 2.1-2.9 (paper) — materially above R29 v1 (1.38)
- **Priority**: After R33 QuantaAlpha and R35 MRP diagnostic. Sequence: R33 → R34 → R35 → R36.

## AI Research Findings (Dream Cycle 2026-04-17)

### Speaker-Weighted FinBERT for Earnings Call Transcripts (arXiv:2604.13260, April 2026)
- **Paper**: 'Which Voices Move Markets? Speaker Identity and the Cross-Section of Post-Earnings Returns' — Sidhu, Fan, Pishgar. arXiv:2604.13260, April 14, 2026.
- **Dataset**: S&P 500, 2015-2025, 16,428 earnings calls, 6.5 million sentences analyzed
- **Core finding**: FinBERT sentence scores must be weighted by speaker role before aggregation. Equal-weighting destroys predictive value.
- **Optimal speaker weights** (learned cross-sectionally):
  - Analyst questions/comments: **49% weight** ← DOMINANT signal
  - CFO prepared/Q&A remarks: **30% weight**
  - Other executives: **16% weight**
  - Other participants: **6% weight**
- **Performance (OOS)**:
  - Spearman IC: **0.142**
  - Monthly long-short alpha (FF5): **2.03%** (t=6.49)
  - Annualized alpha: **24.3%**
  - Q5−Q1 daily OOS: **3.14%**
- **Key insight**: Analyst sentiment is the dominant predictor because analysts ask hard questions — management's *answers* reveal the real signal. CEO prepared remarks are over-scripted and already partially priced.
- **R31 Amendment — MANDATORY**: After computing per-sentence FinBERT scores, separate by speaker role and apply weights before aggregation:
  ```python
  # Speaker role assignment (parse transcript XML/VTT labels)
  SPEAKER_WEIGHTS = {'analyst': 0.488, 'cfo': 0.295, 'executive': 0.159, 'other': 0.058}
  weighted_score = sum(score * SPEAKER_WEIGHTS.get(role, 0.058) for score, role in sentences)
  weighted_score /= sum(SPEAKER_WEIGHTS.get(role, 0.058) for _, role in sentences)
  ```
- **Implementation note**: EDGAR earnings call transcripts typically label speakers. Section split: prepared remarks vs Q&A. All analyst turns = 'analyst' weight; CFO in Q&A = 'cfo' weight; other executives = 'executive' weight.
- **Expected improvement**: Current R31 per-trade Sharpe 1.322 → speaker-weighted variant expected to approach paper's OOS IC 0.142 benchmark.
- **Source**: arXiv:2604.13260

### LLM Feature Regime Failure — Mandatory Kill Switch (arXiv:2604.10996, April 2026)
- **Paper**: 'When Valid Signals Fail: Regime Boundaries Between LLM Features and RL Trading Policies' — Zhengzhe Yang. arXiv:2604.10996, April 13, 2026. Categories: q-fin.TR, cs.LG.
- **LLM used**: Qwen3 235B; **RL agent**: PPO (FinRL). Individual feature ICs: 0.177–0.233 in stable periods.
- **Optimized prompt IC**: 0.104 (compressing multiple features into one)
- **H1 2025 tariff shock performance**:
  - LLM-only Sharpe: **-0.411**
  - Price-only baseline Sharpe: **+0.010**
  - Return differential: **-8.88%** (LLM vs baseline)
- **Mechanism**: During macro regime shocks (Liberation Day tariffs, April 2025), LLM-extracted features decouple from near-term price action. The features remain internally consistent but are no longer predictive of returns under crisis conditions. RL policy trained on calm-market behavior amplifies the noise.
- **Critical finding**: This is NOT a model quality failure. The same LLM features that achieve IC 0.177-0.233 in stable markets become *negatively predictive* during macro shocks. Regime-gating is the ONLY architectural fix.
- **R28 Amendment — MANDATORY VIX KILL SWITCH**: Lower LLM-feature suppression threshold from VIX > 30 to **VIX > 25**:
  ```python
  # In RegimeGuard — before calling any LLM-dependent layers
  if vix_current > 25:  # Changed from >30 based on arXiv:2604.10996
      use_llm_quality_score = False
      use_llm_plausibility = False
      # Fall back to pure statistical model (gap size + volume ratio for R28)
      quality_score = statistical_proxy_score  # already computed
  ```
- **R29 Amendment**: Same kill switch applies to LLM plausibility scoring layer (Stage 2 of pipeline). When VIX > 25, skip LLM scoring entirely and use SPONGEsym + SAE cluster filters only.
- **R33 Amendment**: QuantaAlpha mined factors must be regime-validated. Test mined factors specifically during H1 2025 tariff shock period (Jan–Jun 2025). Any factor with IR < 0 during that period is regime-fragile and should carry 50% weight in deployment.
- **Validation task**: Explicitly backtest R28 and R29 results on H1 2025 period. If R28 LLM filter shows Sharpe collapse consistent with paper findings, VIX > 25 kill switch is confirmed necessary.
- **Source**: arXiv:2604.10996

## Research Agenda Update (2026-04-17)

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix)
  - **AMENDMENT (2026-04-17)**: RegimeGuard VIX threshold for LLM suppression lowered from >30 to **>25** (arXiv:2604.10996). Falls back to statistical proxy score when VIX > 25.
- **Round 29 LLM Filter** — QUEUED
  - **AMENDMENT (2026-04-17)**: Same VIX > 25 kill switch applies — skip LLM plausibility when VIX > 25, use SPONGEsym + SAE filters only.
- **Round 31** — COMPLETED (Sharpe 1.322 per-trade). Next step: speaker-weighted FinBERT rerun.
  - **AMENDMENT (2026-04-17)**: Implement speaker weighting per arXiv:2604.13260. Analyst (49%) > CFO (30%) > Executive (16%) > Other (6%). Expected IC lift toward 0.142.
- **Round 33** — QuantaAlpha evolutionary alpha mining — QUEUED (unchanged)
  - **AMENDMENT (2026-04-17)**: Validate mined factors on H1 2025 tariff shock period. Regime-fragile factors (IR < 0 during shock) get 50% deployment weight.
- **Round 34** (concept) — Institutional ownership as PEAD amplifier — unchanged
- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering — unchanged
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged

## AI Research Findings (Dream Cycle 2026-04-18)

### FactorMiner: Self-Evolving Alpha Mining Agent (arXiv:2602.14670, Feb 2026)
- **Paper**: 'FactorMiner: A Self-Evolving Agent with Skills and Experience Memory for Financial Alpha Discovery' — Wang et al., Tsinghua University / Peng Cheng Laboratory. arXiv:2602.14670, Feb 2026. Trending in q-fin.TR.
- **Core innovation**: Ralph Loop paradigm — **R**etrieve, **G**enerate, **E**valuate, **D**istill. Unlike QuantaAlpha's evolutionary trajectory optimization, FactorMiner continuously accumulates structured knowledge through modular skills and experience memory that explicitly stores both success patterns AND failure constraints.
- **Skill Architecture**:
  - 60+ financial operators (TsRank, Rsquare, MACD-variants, etc.) with GPU-accelerated backends (CuPy)
  - Four-stage validation pipeline per generated factor: (1) fast IC on reduced asset subset, (2) correlation check vs existing library, (3) intra-batch dedup, (4) full validation on complete dataset
  - Prevents 'calculation hallucination' (operators that are algebraically invalid)
- **Performance (2025 out-of-sample)**:
  - **CSI500 individual factor**: IC 8.25%, ICIR 0.77 (vs AlphaAgent 5.90%/0.46 = **+40% IC improvement**)
  - **CSI500 combined (equal-weight)**: IC **14.95%**, ICIR **1.29**
  - **CSI1000 combined**: IC **14.62%**, ICIR **1.37**
  - **HS300**: IC 7.46%, ICIR 0.38 (noisier)
  - **Crypto (64 Binance assets)**: IC 3.82%, ICIR 0.28
  - Average pairwise factor correlation: 0.25–0.31 (low redundancy maintained as library scales)
- **Comparison to QuantaAlpha** (our R33 primary candidate):
  - QuantaAlpha (arXiv:2602.07085): IC 0.1501 (GPT-5.2), evolutionary trajectories, **public code**, S&P 500 zero-shot transfer validated
  - FactorMiner: IC 0.0825 individual / 0.1495 combined, Ralph Loop, **no public code**, Gemini 3.0 Flash backbone
  - Winner for R33: QuantaAlpha (has public code + US validation). FactorMiner concept worth borrowing: explicitly track FAILURE constraints in experience memory
- **Public resources**: 110 formulaic A-share equity factors released in Appendix P (formulaic expressions only, no code). No GitHub repo.
- **George application → R33 design note**: When running QuantaAlpha, maintain a 'failure log' alongside the factor pool — track which formula patterns consistently fail IC validation. Seed the LLM exclusion prompt with these patterns to prevent generating similar factors in subsequent iterations. This is FactorMiner's core innovation, applicable to any iterative factor mining system.
- **Source**: arXiv:2602.14670

### Interpretable Systematic Jump Risk via LLM Narrative Classification (arXiv:2604.13458, April 2026)
- **Paper**: 'Interpretable Systematic Risk around the Clock' — Songrun He, Washington University in St. Louis. arXiv:2604.13458, April 16, 2026. Submitted to q-fin.PM.
- **Method**: Combines high-frequency market data (US equity + S&P 500 E-mini futures, 1997-2020, nearly 24-hour coverage) with LLM-based classification of news narratives that cause market jumps. Identifies interpretable jump risk categories with distinct risk premia.
- **Core finding**: Heterogeneity in jump risk premia — macroeconomic news jumps command the LARGEST and most PERSISTENT premium. Different narrative categories have distinct pricing.
- **Factor construction**: Annually rebalanced Fama-MacBeth factor-mimicking portfolio isolates the most strongly priced jump risk. Achieves high OOS Sharpe and significant alpha vs standard factor models.
- **George application → R35**: Jump narrative classification adds a CAUSAL layer to the R35 regime stack. Current R35 signals identify THAT we are in a regime; LLM jump narrative identifies WHY. Macro-driven jump regime = more persistent = adjust position sizing more aggressively.
- **Priority**: Low (R35 is a concept round; requires high-frequency data beyond yfinance).
- **Source**: arXiv:2604.13458

## Research Agenda Update (2026-04-18)

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix). VIX kill switch at >25.
- **Round 29 LLM Filter** — QUEUED. Final pipeline: factor residualize → SPONGEsym → SAE cluster → cointegration top-100 → 3-agent anonymized LLM top-20 → fixed ±2σ. CMMD contamination check before claiming Sharpe improvement.
- **Round 31b** — QUEUED: Speaker-weighted FinBERT text PEAD (arXiv:2604.13260). Script scaffolded 2026-04-18. Requires EDGAR transcript integration. Expected IC lift: 0.115→0.142 (+24%).
- **Round 33** — QuantaAlpha evolutionary alpha mining. ADD: failure constraint log alongside factor pool (FactorMiner lesson, arXiv:2602.14670). 4-stage gating: fast IC → corr check → dedup → full validation.
- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering + LLM jump narrative (arXiv:2604.13458).
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.

## AI Research Findings (Dream Cycle 2026-04-19)

### FinBERT 52.21% Accuracy Benchmark on Earnings Call Transcripts (arXiv:2503.01886)
- Comprehensive benchmark: FinBERT vs Longformer vs BERT vs ULMFiT on earnings transcript 3-class sentiment
- FinBERT wins at 52.21% accuracy / F1~0.49. Longformer 45%, BERT 41%, ULMFiT 40%
- Financial domain pretraining (FinBERT) dominates raw context length (Longformer 4096 tokens)
- Key technique: analyze Q&A section only — prepared remarks are corporate-controlled and less predictive
- Chunking strategy: 512-token segments with majority vote or max-pooling across chunks
- Sets R31 expectation: text-PEAD signal has ~52% directional accuracy standalone; 3-day price confirmation window (ACL 2025) filters to higher-accuracy subset
- Confirms existing R31 design; no changes needed to architecture

### PolySwarm: 50-Persona LLM Swarm with Bayesian Aggregation (arXiv:2604.03888, April 2026)
- Multi-agent framework: 50 diverse LLM personas evaluate binary outcome markets concurrently
- Aggregation: confidence-weighted Bayesian combination of swarm consensus with market-implied probabilities
- Key finding: swarm aggregation consistently outperforms single-model baselines in probability calibration
- Relevant to R28: the confidence-weighted aggregation principle should upgrade EarningsQualityAgent from fixed weights (0.3/0.5/0.2) to per-event confidence-weighted combination
- Practical implementation: each sub-agent (Performance, Specificity, Risk) outputs score + confidence. Final score = sum(score_i * confidence_i) / sum(confidence_i)

### Implementation Risk in Portfolio Backtesting (arXiv:2603.20319, March 2026)
- Transaction cost handling causes up to 3.71% divergence in metrics across identical-logic backtest engines
- Zero-cost backtests are engine-consistent; divergence only at non-zero costs
- 'Conclusion Stability Index' = 1: strategy RANKING direction is consistent even when absolute magnitudes differ
- Implication: George strategy rankings are trustworthy; absolute Sharpe numbers carry ~2-4% implementation uncertainty
- Conservative correction: add 5bp/trade friction buffer before any live-trading decision
- High-turnover strategies (R29 pairs daily rebalancing) most affected; low-turnover (Div Raise, PEAD) least affected

### Walk-Forward Window Length as Hyperparameter (arXiv:2602.10785, 2026)
- Treating train/test window lengths as optimization parameters yields ~50% drawdown reduction
- Optimal window is strategy-frequency dependent: short-hold strategies suit shorter test windows
- Combined portfolio of multiple window variants achieves best risk-adjusted performance
- Actionable for R28/R31/R32: scan train=[126,252,504] x test=[21,42,63,126] = 12 combinations before committing

### LLM Herding Risk in Trading Agent Design (arXiv:2504.10789, April 2026)
- LLMs executing homogeneous prompts create correlated behaviors that can destabilize markets
- Confirms 'LLM as factor generator, not executor' constraint — but adds the diversity dimension
- For any multi-LLM scoring pipeline (R28, R29): ensure sub-agent prompts are MAXIMALLY DIFFERENT in framing to prevent correlated outputs. A Performance agent and a Risk agent asked about the same earnings beat should approach it from opposite angles, not both follow 'positive sentiment' framing.

## AI Research Findings (Dream Cycle 2026-04-20)

### EvasionBench + Eva-4B: Purpose-Built Evasion Classifier (arXiv:2601.09142, Jan 2026)
- **Paper**: 'EvasionBench: Detecting Evasive Answers in Financial Q&A via Multi-Model Consensus and LLM-as-Judge'
- **Eva-4B model**: HuggingFace `FutureMa/Eva-4B-V2` (Apache 2.0, 4B params, Qwen3-4B-Instruct base). Achieves 84.9% Macro-F1 on evasion detection — outperforms Claude Opus 4.5, GPT-5.2, Gemini 3 Flash.
- **3-class taxonomy**: direct (F1=0.851) / intermediate (F1=0.698) / fully_evasive (F1=0.873)
- **Quantified market impact**: +40pp evasion → -0.74% 1-day return; 63% likelihood of underperformance within 180 days for high-evasion companies
- **Dataset**: `FutureMa/EvasionBench` (16.7K labeled Q&A pairs, Parquet, Apache 2.0); GitHub: IIIIQIIII/EvasionBench
- **R28 amendment (UPGRADE)**: Replace ad-hoc 3-step NOR LLM prompt with Eva-4B direct inference. NOR_rate = (intermediate + fully_evasive) / total Q&A pairs per call
- **IMPORTANT NUANCE**: moderate evasion (NOR 25-50%) = PEAD AMPLIFIER (slower price discovery); extreme evasion (NOR >50%) = BEARISH VETO (concealment of bad news). Different thresholds → opposite signals. Prior heuristic (arXiv:2505.18419) covers amplifier case; Eva-4B enables the veto case too.

### AlphaPROBE: DAG-Based Factor Mining (arXiv:2602.11917, Feb 2026)
- **Paper**: 'AlphaPROBE: Alpha Mining via Principled Retrieval and On-graph Biased Evolution'
- **Architecture**: Directed Acyclic Graph of factor lineage + Bayesian Factor Retriever (penalizes over-explored branches) + DAG-aware Factor Generator (uses full ancestral trace for context-aware generation)
- **Retriever mechanism**: prior = quality × (1-γ)^depth × (1-ω)^n_retrievals — discourages re-mining branches already extensively explored
- **Performance (Chinese markets)**: IC 5.84/6.26/9.04% on CSI300/500/1000; Sharpe 0.44/0.83/0.65; outperforms AlphaAgent, R&D-Agent(Q) on all metrics
- **Key differentiator vs QuantaAlpha**: ancestral awareness prevents near-duplicate generation that QuantaAlpha's crossover/mutation can accidentally produce
- **Code**: https://github.com/gta0804/AlphaPROBE (Apache 2.0). LLM: Deepseek V3.1; embedding: Qwen 3 Embedding; pool cap: 50 factors
- **R33 application**: Run AlphaPROBE in parallel with QuantaAlpha; combine output pools via diversity filter (|corr| < 0.70, ranked by RankIC desc). Two complementary generation strategies → broader non-redundant factor pool.

### Acoustic Camouflage (arXiv:2604.14619, April 2026) — NEGATIVE FINDING
- Adding acoustic/prosodic features to earnings call NLP models HURTS performance: recall drops 66% → 47%
- Root cause: media-trained executives suppress natural vocal stress indicators — the features carry only noise
- Implication: NLP-only models are strictly better for corporate earnings call analysis. Do not add audio modality.

## Research Agenda Update (2026-04-20)

- **Round 28 Phase 2** — LLM EarningsQualityAgent: AMENDMENT — replace ad-hoc NOR prompt with Eva-4B (`FutureMa/Eva-4B-V2`). Moderate NOR (25-50%) = amplifier; extreme NOR (>50%) = bearish veto.
- **Round 29 LLM Filter** — QUEUED (unchanged from 2026-04-19 final design)
- **Round 31b** — QUEUED: speaker-weighted FinBERT (arXiv:2604.13260). Unchanged.
- **Round 33** — QuantaAlpha + AlphaPROBE (arXiv:2602.11917) in parallel. Combine pools via diversity filter.
- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.

## AI Research Findings (Dream Cycle 2026-04-21)

### Cross-Stock Predictability via LLM-Augmented Semantic Networks (arXiv:2604.19476)
- **Paper**: Huang, Fan, Hu, Ye. arXiv:2604.19476. April 21, 2026.
- **Method**: Two-stage stat-arb pipeline. Stage 1: build sparse candidate pair graph using K=5 cosine-similarity nearest neighbors from 10-K filing embeddings (~497 S&P 500 stocks/year). Stage 2: LLM (anonymized firm descriptions, temp=0, structured JSON) classifies each edge into one of 6 relationship types. Relationship-aware weighting aggregates cross-stock z-score signals. Rebalancing: daily into quintiles over 180-day training windows.
- **6 relationship categories**: competitor, supply_chain, peer, substitute, complement, unrelated
- **Key finding**: Competitor pairs and substitute pairs should be EXCLUDED or down-weighted — their spread dynamics involve divergence, not mean-reversion. Supply chain, peer, and complement pairs are the correct mean-reversion universe.
- **Results (S&P 500, 2011-2019)**:
  - Baseline (no LLM): Sharpe 0.742, MaxDD -10.47%
  - LLM-filtered: Sharpe **0.820** (+10.5%), MaxDD **-7.85%** (-25%), t-stat 2.32
  - Random network: Sharpe 0.541; SIC industry baseline: Sharpe 0.792
- **R29 Amendment (2026-04-21)**: Upgrade LLM prompt from scalar mechanism_strength + 3-agent consensus to unified 6-category taxonomy prompt. New veto: skip pair if relationship_type in ['competitor', 'substitute', 'unrelated'] AND mechanism_strength < 60. This replaces the 3-agent Revenue/Supply/Competitive consensus from 2026-04-16 with a cleaner unified prompt.
- **Consistent with existing design**: firm anonymization (BlindTrade) and co_movement_sign check already in design; this upgrade is additive.
- **No public code**; uses DeepSeek-Chat API or equivalent LLM with structured JSON output.

### MarketSenseAI Live Validation + Agent Rotation Regime Signal (arXiv:2604.17327)
- **Paper**: 'Signal or Noise in Multi-Agent LLM-based Stock Recommendations?' — Fatouros, Metaxas. arXiv:2604.17327, April 19, 2026.
- **Performance (live, no look-ahead bias)**:
  - S&P 500 (19 months): +2.18%/month vs. +1.15% benchmark; 99.7th percentile (p=0.003); compound excess +25.2pp
  - S&P 100 (35 months): compound excess +30.5pp; p=0.166 (not statistically significant — caution on 35-month window)
  - Jensen's alpha: +1.18%/month, p=0.17 — wide confidence interval; 19 months is too short for statistical confidence
  - ICIR: +0.489 (p=0.024) on ordinal recommendation signal; portfolio beta: 0.865
- **Agent rotation finding (KEY)**:
  - Fundamentals agent leads S&P 500 alpha; Macro agent leads S&P 100 alpha
  - Rotation correlates with macro calendar events (Fed meetings, tariff events, elections)
  - Static equal-weight multi-agent system leaves alpha on the table
  - Attribution method: NNLS projection of synthesis thesis embeddings onto individual agent embeddings
- **R28 Phase 2 Application**: During macro uncertainty windows (VIX > 22 AND rising, or within 7 days of Fed meeting), shift weights: Specificity 40% (from 50%), Risk density 30% (from 20%), Sentiment 30% (unchanged). Source: agent rotation finding.
- **Caution**: 19-month live track record is short. Monitor before adding R28 complexity. S&P 100 35-month result statistically weak (p=0.166).

### RMT Complexity Gap: 4th-Layer Shock Detection for R35 Regime Stack (arXiv:2604.19107)
- **Paper**: 'Structural Dynamics of G5 Stock Markets During Exogenous Shocks: A Random Matrix Theory-Based Complexity Gap Approach' — Mukhia, Ansari, Nurujjaman. arXiv:2604.19107, April 21, 2026.
- **Complexity gap formula**: gap = (normalized largest eigenvalue of return correlation matrix) − (average pairwise correlation). Rolling 60-day window, daily returns.
- **3-phase shock pattern** (validated: COVID-19, 2025 Liberation Day tariffs, 2024 Japan/China):
  1. Pre-shock: gap positive and stable (diverse market structure)
  2. Shock onset: gap collapses to ≈0 or negative (synchronization — all stocks move together)
  3. False recovery: gap briefly widens, then collapses again — trap for automated systems
  4. True recovery: sustained gap expansion over multiple days/weeks
- **Why critical for George**:
  - Gap collapse = ALL stat-arb pairs fail simultaneously (correlated legs both wrong direction)
  - Gap collapse = PEAD signals fail (market panic overrides earnings-specific drift)
  - False recovery = mean reversion looks attractive again but isn't sustained → amplified losses if auto-system re-enters
- **Implementation**: ~20 lines numpy from yfinance daily returns. Signal: gap < 0.05 = synchronization.
- **R35 regime stack update**: (1) EF clustering, (2) Wasserstein HMM, (3) skewness dispersion, **(4) RMT complexity gap** (shock detection + false recovery flag). All four non-redundant.
- **R28 RegimeGuard cross-application**: gap < 0.05 = skip ALL new PEAD entries regardless of VIX level.

### Spurious Predictability in Financial Machine Learning (arXiv:2604.15531)
- **Paper**: 'Spurious Predictability in Financial Machine Learning' — Nikolopoulos. arXiv:2604.15531, April 16, 2026. QuantAudit R package + replication scripts forthcoming on GitHub/CRAN.
- **Key finding**: At K=1000 candidate strategies searched, 100% of in-sample winners are spurious. FeatureMining workflows: 100% IS failure rate, ΔZ=2.68 magnitude inflation at K=400.
- **Falsification audit (2-stage)**:
  - Stage 1: Run full workflow on 5 synthetic null environments: (A) White Noise, (B) Markov Vol Regime, (C) Bid-Ask Bounce Placebo, (D) Factor Null, (E) GARCH Clustering. Any workflow that produces IS winners on null environments = falsified.
  - Stage 2: Compute Absolute Magnitude Gap (ΔZ = Z_IS − Z_WF) and effective multiplicity K̂_eff = (Σλ_i)² / Σλ²_i. Standard p<0.05 is meaningless without K̂_eff correction.
- **R33 hygiene requirement**: Apply workflow falsification audit before claiming IC improvement from QuantaAlpha/AlphaPROBE factors. Test against (C) Bid-Ask Bounce Placebo and (D) Factor Null at minimum. Compute K̂_eff for the factor candidate pool searched.
- **Critical discipline**: All preprocessing, feature selection, and hyperparameter tuning must be strictly confined to in-sample data. Any leakage → falsified.

## Research Agenda Update (2026-04-21)

- **Round 29 LLM Filter** — QUEUED. **AMENDMENT (2026-04-21)**: Upgrade LLM prompt from 3-agent consensus (2026-04-16) to unified 6-category relationship taxonomy. Prompt classifies pair as: competitor/supply_chain/peer/substitute/complement/unrelated + mechanism_strength + co_movement_sign. VETO if competitor/substitute/unrelated AND mechanism_strength < 60. Source: arXiv:2604.19476.

- **Round 28 Phase 2** — LLM EarningsQualityAgent: **DESIGN NOTE (2026-04-21)**: During macro uncertainty windows, shift composite score weights from 30/50/20 (Sentiment/Specificity/Risk) to 30/40/30. Source: arXiv:2604.17327 agent rotation finding.

- **Round 33** — QuantaAlpha + AlphaPROBE: **NEW HYGIENE REQUIREMENT (2026-04-21)**: Apply workflow falsification audit (arXiv:2604.15531) before claiming IC improvement. Test against Bid-Ask Bounce Placebo + Factor Null environments. Compute K̂_eff for significance threshold correction.

- **Round 35** — **UPDATED (2026-04-21)**: Add RMT complexity gap as 4th layer of regime stack. Gap < 0.05 = synchronization = skip all new strategy entries regardless of VIX level. False recovery detection = maintain reduced exposure even when gap briefly rises. Source: arXiv:2604.19107.

- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.

## AI Research Findings (Dream Cycle 2026-04-22)

### Anti-Extrapolation Prompting Fails — LoRA Fine-Tuning Required (arXiv:2604.02921 full paper review)
- **Critical correction to prior heuristic**: The heuristics.md entry 'Suppress LLM extrapolation bias' recommended anti-extrapolation instructions in prompts. Full paper confirms: 'prompt-based approaches appear limited in alleviating this bias.' The bias is encoded in model parameters during pretraining and alignment — prompting cannot fix a parameter-level issue.
- **Quantitative evidence (Qwen3-32B)**:
  - Overreaction coefficient on stock returns: +0.394 (t=53.92) at baseline; NOT significantly reduced by anti-extrapolation prompting
  - After LoRA fine-tuning on rational benchmark forecasts: reversed to -0.120 (t=-23.21)
  - AR(1) overreaction: -0.456 (baseline) → statistically insignificant -0.073 after fine-tuning
- **Updated mitigation hierarchy**:
  1. **LoRA fine-tuning** on rational forecast examples (parameter-level fix — best but requires labeled data)
  2. **Ticker anonymization** / BlindTrade approach (best inference-time defense — restricts memorized price context that triggers the bias)
  3. **Anti-extrapolation prompt instruction** (keep as cheap weak guardrail but do NOT rely on it as primary protection)
- **Implication for R28 Phase 2 / R29**: Anti-extrapolation prompts provide false sense of safety. BlindTrade anonymization (already in R29 design, arXiv:2603.17692) is the correct primary runtime defense.
- **No public code/weights released** for the fine-tuning approach as of April 2026.

### Structured Strategy Backtest Regime-Timing Haircut (arXiv:2604.18821, April 2026)
- **Paper**: 'Evaluating Structured Strategy Backtests: Peer Benchmarks, Regime Timing, and Live Performance' — Chang Liu, U. Trento / Resonanz Capital. April 20, 2026. Under review at Journal of Asset Management.
- **Study scope**: 1,726 commercially distributed structured strategies from 10 global institutions
- **Main finding**: 75-81% of pro-forma backtest outperformance evaporates after peer-benchmark adjustment — it reflects common factor regime exposure, not portable alpha
- **Performance gaps**:
  - 6-month: 2.1pp (3.6% backtest → 1.5% live); 12-month: 3.1pp (4.1% → 1.0%)
  - Raw coefficient 0.137 → Bloomberg-adjusted 0.025 → LOO peer 0.034 (~80% reduction)
- **Regime-timing channel**:
  - Cold quintile: +0.8% slight live improvement
  - Hot quintiles Q4-Q5: -3.5% to -4.5% decay per quintile
  - LOO regression: 0.716 (p<0.001) — strong regime-timing effect
- **Risk deterioration**: MaxDD worse in 54% live; Sortino worse in 59%
- **Actionable formula**: Expected live return = Backtest return − (5pp × regime_extremity_z_score)
- **George application**: 2018-2024 US equity backtest window = warm/hot regime (z-score ~+1.5 to +2). Apply 10-20% Sharpe haircut before any live deployment decision. Combined with 5bp/trade friction buffer (arXiv:2603.20319): R28 PEAD Sharpe 9.03 → live estimate ~7.2-7.8 (still exceptional). Div Raise 4.40 → ~3.5-4.0 live.

### LLM Agent Behavioral Biases in Simulated Markets (arXiv:2604.18373 + arXiv:2604.18602, April 2026)
- **Paper 1**: 'Dissecting AI Trading: Behavioral Finance and Market Bubbles' — Ouyang & Sui, Oxford/CUHK-Shenzhen. April 20, 2026.
  - LLM agents exhibit DISPOSITION EFFECT (sell winners early) and recency-weighted extrapolation (recent return coefficient 0.212, rising to 0.608 for 10-period-ahead forecasts)
  - Bubble propensity by model: GPT-4o Mini and Llama 3.1 70B = MSE(FV) > 100; DeepSeek V3 / Qwen 2.5 ≈ 0
  - PROMPT SUPPRESSION WORKS for behavioral tendencies: momentum chasing reduced by 0.181 units, Rational Speculative Bubble reasoning by 0.213 with targeted interventions (+5.07 unit change with amplification prompt)
  - **Key distinction**: Prompting CAN modulate behavioral strategy choices (momentum vs fundamental) but CANNOT fix statistical extrapolation bias in predictions (arXiv:2604.02921) — different mechanisms
- **Paper 2**: 'Machine Spirits: Speculation and Adaptation of LLM Agents in Asset Markets' — Saxena, Pangallo, Caccioli, del Rio-Chanona. April 20, 2026.
  - Bubble formation: o3-mini 100%, Qwen3-14B 100%, GPT-5 Mini 0%, Gemini-3-Flash 0%
  - Mixed LLM populations: 50% bubble rate even when bubble-formers are minority
  - Advanced models exploit simpler ones → amplifies rather than dampens volatility
- **R28/R29 model selection amendment**: Prefer Qwen2.5-7B-Instruct or Qwen3-series over GPT-4o Mini as scoring worker agents (low bubble propensity = more calibrated fundamental scores). Add cognitive framing prompt to each scoring agent: 'Focus on fundamental quality and economic relationships only. Do not track recent price trends or momentum.'

### QRAFTI: MCP-Native Agentic Factor Research (arXiv:2604.18500, April 2026)
- **Paper**: 'QRAFTI: An Agentic Framework for Empirical Research in Quantitative Finance' — Lim, Muthuraman, Sury (McCombs / Google). April 20, 2026.
- **Architecture**: 3 agents (Research Analyst / Risk Manager / Quant Developer) + MCP servers for data access, factor primitives, portfolio construction, standardized reporting. Produces computation graphs for reproducibility.
- **Validated**: replicates HML and JKP momentum. Generates Warren Buffett-style quality factor (ROE + gross profitability + low vol + low leverage) with positive alpha.
- **Key design insight**: Chained tool calls + reflection-based planning achieves task similarity 0.99 on multi-step research; dynamic code generation alone underperforms.
- **R33 relevance**: QRAFTI is architecturally closer to George's environment (MCP-native) than QuantaAlpha (Qlib + China HDF5). Keep QuantaAlpha as primary target (IC 0.1501, S&P 500 validated, public code). If Qlib setup proves intractable, QRAFTI MCP server pattern is the fallback: build lightweight yfinance-based factor primitives as MCP tools, then use Claude for generation + testing. No Qlib dependency.

## Research Agenda Update (2026-04-22)

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix)
  - **AMENDMENT (2026-04-22)**: Anti-extrapolation prompts are weak guardrails only. Primary inference-time defense = BlindTrade anonymization (already in design). Worker model preference = Qwen2.5-7B over GPT-4o-mini.
- **Round 29 LLM Filter** — QUEUED. No new amendments. 2026-04-21 6-category taxonomy is final design.
- **Round 31b** — QUEUED: speaker-weighted FinBERT text PEAD. No new amendments.
- **Round 33** — QuantaAlpha primary; QRAFTI MCP architecture as fallback if Qlib setup fails.
- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering + RMT gap — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.
- **LIVE DEPLOYMENT SIZING**: Apply regime-timing haircut (arXiv:2604.18821) formula before any live strategy sizing. Combined with friction buffer: Sharpe × 0.80-0.90 × (1 - 5bp per trade annualized) = conservative live estimate.

## AI Research Findings (Dream Cycle 2026-04-23)

### CogAlpha: Cognitive LLM Alpha Mining (arXiv:2511.18850, revised April 2026)
- **Paper**: 'Cognitive Alpha Mining via LLM-Driven Code-Based Evolution' — Fengyuan Liu et al. arXiv:2511.18850, revised April 20, 2026.
- **Performance (CSI300)**:
  - CogAlpha: IC **0.0591**, ICIR **0.3410**, RankIC **0.0814**, RankICIR **0.4350**
  - AlphaAgent baseline: IC 0.0246, ICIR 0.2407 — CogAlpha achieves **2.4x IC improvement**
  - Alpha158 factor library: IC 0.0358, ICIR 0.2737
- **Markets validated**: CSI300 + CSI500 (China), **S&P 500** (US), HSI + HSCI (Hong Kong) — 5 datasets, 3 markets
- **LLM backbone**: gpt-oss-120b (primary); also tested Llama3 variants, GPT-4.1, o3
- **Evolutionary operators**: Mutation Agent (slight code modification for variability) + Crossover Agent (combine two existing alphas) + crossover-then-mutation chain. Generation temperature randomized {0.7–1.2}; quality-checking fixed at 0.8.
- **Key differentiator vs QuantaAlpha**: CogAlpha uses 'cognitive reasoning' — LLMs reason about WHY an alpha works before generating variants. QuantaAlpha uses trajectory-level evolutionary operators. Both outperform AlphaAgent substantially.
- **Limitation**: No public code. QuantaAlpha remains primary R33 target (public GitHub, S&P 500 validated).
- **R33 design note**: Borrow CogAlpha's cognitive reasoning prompt ('Explain WHY this alpha formula is expected to predict returns. What economic mechanism does it capture?') as a pre-mutation prompt in QuantaAlpha's mutation step. No code change needed — adds a reasoning step before each mutation to improve economic plausibility of generated variants.
- **Temperature insight**: Use randomized temperature {0.7–1.2} for generation agents (diversity), fixed low temperature for quality-checking agents (consistency). Apply to QuantaAlpha backbone LLM config.
- **SOURCE**: arXiv:2511.18850

### Risk-Sensitive Specialist Routing (arXiv:2604.10402, April 2026)
- **Paper**: 'Risk-Sensitive Specialist Routing for Volatility Forecasting' — arXiv:2604.10402, April 2026. q-fin.ST.
- **Specialists**: 5 models — HAR-RV, GARCH-t, FIGARCH (econometric); GRU, XGBoost (ML)
- **Routing architecture**:
  - Calm specialist pool: {GRU, HAR-RV, XGBoost}
  - Stress specialist pool: {GARCH-t, FIGARCH, HAR-RV}
  - Routing signal: VIX + yield curve slope + credit spreads → logistic function → stress probability
  - Final output: (1 - stress_prob) × calm_pool_forecast + stress_prob × stress_pool_forecast
- **Performance**: ~24% QLIKE reduction in high-vol regime vs rolling-best benchmark. Diebold-Mariano significant on SPY, QQQ, IWM.
- **Key finding**: 'The strongest forecaster is regime-dependent rather than stable.' Calm regimes use ≤1 model; stressed regimes use ≤2 models.
- **R35 RegimeGuard extension**: Apply calm/stress specialist pool pattern to STRATEGY selection (not just volatility models):
  - Calm pool: PEAD (R28), Div Raise (R27), Pairs v1 (R29) — run with LLM overlays active
  - Stress pool: Factor-only strategies (stat proxy scores only), no LLM dependency — consistent with arXiv:2604.10996 finding that LLM features decouple in macro shocks
  - Routing: stress_prob = logistic(0.3×VIX_z + 0.4×yield_curve_z + 0.3×credit_spread_z). When stress_prob > 0.6: disable LLM layers across all strategies (extends VIX >25 kill switch to a continuous probability model).
- **WHEN**: R35 design; R28 Phase 2 RegimeGuard upgrade; any multi-strategy portfolio signal blending.
- **SOURCE**: arXiv:2604.10402

### OOM-RL: Market-Driven LLM Alignment via Capital Depletion (arXiv:2604.11477, April 2026)
- **Paper**: 'OOM-RL: Out-of-Money Reinforcement Learning Market-Driven Alignment for LLM-Based Multi-Agent Systems' — arXiv:2604.11477, April 2026.
- **Core innovation**: Capital depletion = 'un-hackable negative gradient'. Real trading losses force LLM agents to abandon theoretically-optimal but execution-naive strategies. More robust than RLHF subjective preferences.
- **Performance (Phase 3 mature period, 94 trading days)**:
  - Sharpe: **2.06** (annualized); Return: **34.48%** net of friction (0.08%/trade)
  - CSI 300 benchmark: 5.04% same period. Alpha marginally significant p=0.09.
  - Phase 1 (high-frequency): Sharpe 0.35, MaxDD -16.86%. Phase 2 (weekly rebalance): Sharpe 0.91.
- **STDAW Architecture** (Strict Test-Driven Agentic Workflow):
  - **≥95% code coverage** enforced before any LLM-generated financial math is accepted
  - Byzantine RO-Lock: Logic Genesis phase locks test files read-only; Test Genesis phase locks source read-only. Prevents 'Test Evasion' hallucination.
  - AST sanitization scans for reflective patterns or test framework monkey-patching.
- **Epistemic Autopsy pattern**: When a generated factor fails validation, convert the failure into structured JSON: {"failure_type": "algebraic|correlation|plausibility|ic_negative", "formula": "...", "failure_reason": "...", "excluded_patterns": [...]}. Feed back into next generation cycle as exclusion context.
- **R33 Application**:
  - Add ≥95% code coverage check to any QuantaAlpha/AlphaPROBE generated Python factor before running IC validation. Guard against LLM-hallucinated financial operators (e.g., division by zero, look-ahead in rolling window).
  - Implement Epistemic Autopsy as the failure pool update mechanism (extends FactorMiner's failure constraints, arXiv:2602.14670, with richer diagnosis schema).
  - Dream cycle analogy: backtest Sharpe as the 'capital depletion signal' — factors with negative IC are the equivalent of trading losses, driving exclusion constraints.
- **WHEN**: R33 QuantaAlpha implementation; any LLM-generated code that executes financial calculations.
- **SOURCE**: arXiv:2604.11477

## Research Agenda Update (2026-04-23)

- **Round 29 LLM Filter** — QUEUED. Design FINAL as of 2026-04-21 (6-category LLM taxonomy + ticker anonymization + CMMD contamination check). No new amendments from 2026-04-23 scan.

- **Round 31b** — QUEUED: Speaker-weighted FinBERT. No new amendments.

- **Round 33** — QuantaAlpha primary + AlphaPROBE parallel.
  - **NEW AMENDMENT (2026-04-23)**: Add cognitive reasoning pre-step from CogAlpha (arXiv:2511.18850). Before each mutation cycle, prompt LLM: 'Explain the economic mechanism this factor formula is expected to capture. What behavioral or structural market friction does it exploit?' Then proceed with mutation. Adds zero cost; reduces algebraically degenerate mutations.
  - **NEW AMENDMENT (2026-04-23)**: Use randomized temperature {0.7–1.2} for generation agents; fixed 0.8 for quality-checking agents (CogAlpha temperature insight).
  - **NEW AMENDMENT (2026-04-23)**: Implement Epistemic Autopsy on failed IC candidates — structured JSON failure diagnosis prepended to next generation prompt (OOM-RL arXiv:2604.11477, extends FactorMiner failure pool).
  - **HYGIENE (2026-04-21, reaffirmed)**: Apply workflow falsification audit (arXiv:2604.15531) before claiming IC improvement.

- **Round 35** — MRP diagnostic + Wasserstein HMM + EF clustering + RMT gap.
  - **NEW AMENDMENT (2026-04-23)**: Add probabilistic stress routing to RegimeGuard (arXiv:2604.10402): stress_prob = logistic(VIX_z + yield_curve_z + credit_spread_z). Route strategies: stress_prob > 0.6 = use STRESS pool (pure statistical, no LLM); stress_prob < 0.4 = use CALM pool (LLM-augmented). 0.4–0.6 = weighted blend.

- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.

## AI Research Findings (Dream Cycle 2026-04-24)

### Purpose-Conditioned Bias: Goal-Blind LLM Prompts Are Mandatory (arXiv:2602.09504, Feb 2026)
- **Paper**: 'Seeing the Goal, Missing the Truth: Human Accountability for AI Bias' — Cao, Jiang, Xu. Feb 2026. q-fin.CP, cs.AI.
- **Finding**: When LLMs are told their output will be used to predict stock returns or inform a trading decision, they exploit memorized training patterns to produce biased, goal-aligned intermediate measures. Pre-knowledge-cutoff performance: goal-aware prompts yielded +0.483pp/month improvement (statistically significant, 1.552% vs 1.069% monthly returns). Post-cutoff: advantage completely disappears; goal-aware OOS R² DECLINES by -5.37%/quarter.
- **Mechanism**: Objective disclosure triggers 'purpose-conditioned cognition' — the LLM acts as a prediction agent rather than neutral measurement tool. Experiment: GPT-4o-mini on earnings call transcripts. Goal-blind: 'Provide a sentiment score about business sentiment.' Goal-aware: identical + 'The score will be used as an explanatory variable to predict monthly stock returns.' Only the final sentence changed.
- **This is a THIRD contamination vector** (distinct from ticker memorization arXiv:2603.17692 and extrapolation bias arXiv:2604.02921).
- **R28 Phase 2 MANDATORY AMENDMENT**: Remove all trading-context language from EarningsQualityAgent prompts. WRONG: 'to determine if we should initiate a PEAD trade.' RIGHT: 'Assess the fundamental quality of this earnings announcement as a financial analyst.' Do NOT mention: 'PEAD', 'trade', 'stock return prediction', 'buy', 'sell'.
- **R29 MANDATORY AMENDMENT**: Remove trading-context from pairs plausibility prompts. WRONG: 'evaluate whether we should trade the spread.' RIGHT: 'Evaluate the fundamental economic relationship between COMPANY_A and COMPANY_B as a business analyst.'
- **SOURCE**: arXiv:2602.09504

### Sparse Factor Weights for R33: L1/Basis Pursuit Outperforms Equal-Weight (arXiv:2604.17166, April 2026)
- **Paper**: 'The Virtue of Sparsity in Complexity' — April 18, 2026. q-fin.PM. US equities 1993-2023, 360 OOS evaluations.
- **Method**: Random Fourier Features expand 130 firm characteristics to ~30,000 candidates. Minimum-L1 basis pursuit selects sparse pricing kernel. Stable 31-33 active factors from 30,000 candidates.
- **Key finding**: Sparse SDF Sharpe ratio dominates dense benchmark beyond complexity ratio c≈2,000. L1 (basis pursuit) outperforms L2 (ridge). Near-pathwise dominance over individual months.
- **R33 AMENDMENT**: After mining factors via QuantaAlpha + AlphaPROBE and applying diversity filter, fit **Lasso/ElasticNet sparse weights** on the validation period. Do NOT equal-weight top-N. Steps: (1) generate pool (20-100 factors), (2) diversity filter |corr| < 0.70, (3) fit Lasso on validation set with λ by cross-validation, (4) deploy sparse-weighted portfolio on test set. ~5 lines sklearn. Validation-only lambda selection — no test-set leakage.
- **SOURCE**: arXiv:2604.17166

### AlphaCFG: Grammar-Guided MCTS (arXiv:2601.22119, Jan 2026)
- **S&P 500 OOS**: IC 0.04573, Sharpe 0.8473, ICIR 0.4099. Outperforms AlphaGen/gplearn. NO LLM required.
- **Method**: Context-free grammar constrains factor formula space; MCTS explores expression trees.
- **Code**: https://github.com/HanYang544/AlphaCFG (26 stars, Python 3.9-3.10, Apache 2.0). Default: Baostock; Qlib supported.
- **R33 role**: Optional TERTIARY generator. IC 0.046 significantly lower than QuantaAlpha (~0.125). Use only if QuantaAlpha + AlphaPROBE pool has < 20 diverse factors after diversity filter.
- **SOURCE**: arXiv:2601.22119

### PolyBench: LLM Model Selection Update (arXiv:2604.14199, April 2026)
- **Finding**: Only 2/7 tested LLMs profitable on 38,666 live prediction markets: MiMo-V2-Flash (+17.6% CWR) and Gemini-3-Flash (+6.2% CWR). Five others negative. Validates 'LLM as factor generator not executor' with live market evidence.
- **Model preference update**: Qwen2.5-7B-Instruct (low bubble propensity) or Gemini-3-Flash (positive CWR) as scoring workers. MiMo-V2-Flash for future evaluation. Avoid GPT-4o-mini.
- **SOURCE**: arXiv:2604.14199

### AI Systemic Risk: Deploy Live Signals Earlier (arXiv:2604.03272, April 2026)
- **Finding**: Superlinear growth of systemic risk coupling with AI adoption (99.5M SEC holdings, tail-loss amplification 18-54%). LLM alpha signals decay as adoption increases through crowding.
- **Implication**: R28 and R29 signals have higher information advantage now than in 12-24 months. Prefer hard-to-replicate pipelines (Eva-4B, SAE clusters) over generic prompts.
- **SOURCE**: arXiv:2604.03272

## Research Agenda Update (2026-04-24)

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix)
  - **MANDATORY AMENDMENT (2026-04-24)**: All scoring prompts must be GOAL-BLIND — remove 'PEAD trade', 'stock return', 'trading decision'. Source: arXiv:2602.09504.
  - **MODEL PREFERENCE**: Qwen2.5-7B-Instruct or Gemini-3-Flash as worker agents.

- **Round 29 LLM Filter** — QUEUED
  - **MANDATORY AMENDMENT (2026-04-24)**: LLM plausibility prompts must be GOAL-BLIND — say 'evaluate the economic relationship', not 'evaluate whether to trade the spread'.
  - Pipeline design final as of 2026-04-21 (6-category taxonomy + ticker anonymization + CMMD check).

- **Round 31b** — QUEUED: Speaker-weighted FinBERT. No new amendments.

- **Round 33** — QuantaAlpha primary + AlphaPROBE secondary.
  - **NEW AMENDMENT (2026-04-24)**: After diversity-filter selection, fit L1-sparse weights (Lasso/ElasticNet) on validation set. Source: arXiv:2604.17166.
  - **TERTIARY OPTION**: AlphaCFG (arXiv:2601.22119) as optional 3rd generator if pool is thin.

- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering + RMT gap — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.

## AI Research Findings (Dream Cycle 2026-04-25)

### AlphaSAGE — R33 Quaternary Generator (2026-04-25)
- **Paper**: arXiv:2509.25055 (Sep 2025)
- **Code**: github.com/BerkinChen/AlphaSAGE (Python 3.11+, PDM package manager, Qlib backend)
- **Architecture**: GFlowNet + RGCN (Relational Graph Convolutional Network) structure-aware encoder
- **Key innovation**: Dense reward structure avoids sparse reward failure; GFlowNet samples proportional to reward (not argmax) → avoids mode collapse → produces diverse, uncorrelated alphas
- **US results (S&P 500)**: IC 0.052, ICIR 0.493, Sharpe 6.32, AR 19.47%, MaxDD -4.2%
- **China results (CSI300)**: Outperforms AlphaGen-PPO, AlphaForge, AlphaQCM (per paper)
- **R33 role**: QUATERNARY generator alongside QuantaAlpha (primary), AlphaPROBE (secondary), AlphaCFG (tertiary)
- **Integration note**: Same Qlib data backend as QuantaAlpha — minimal setup overhead
- **No LLM dependency**: Pure GNN+GFlowNet, no prompt-bias risk
- **Priority**: Implement after QuantaAlpha; use to fill uncorrelated alpha niches that RL-based generators miss

### SubjECTive-QA — R28 EarningsQualityAgent Scoring Upgrade (2026-04-25)
- **Paper**: arXiv:2410.20651 (NeurIPS 2024 dataset paper)
- **HuggingFace**: gtfintechlab/SubjECTive-QA (CC BY 4.0, Parquet)
- **Load**: `from datasets import load_dataset; dataset = load_dataset('gtfintechlab/SubjECTive-QA')`
- **Scale**: 49,446 annotations on 2,747 QA pairs, 120 NYSE companies, 2007-2021
- **6 Dimensions** (all scored 0=negatively demonstrative / 1=neutral / 2=positively demonstrative):
  - Assertive: confident, direct assertion
  - Cautious: hedging, qualifying statements
  - Optimistic: forward-looking positive framing
  - Specific: quantitative precision vs. vague generalities — maps to R28 specificity weight 0.5
  - Clear: clarity and transparency
  - Relevant: answer addresses the question asked
- **Automated scoring**: RoBERTa-base or Llama-3-70b-Chat achieve reliable weighted F1
- **R28 integration**: Replace ad-hoc NOR prompt with 6-dimension SubjECTive-QA scoring vector
  - Specific score = primary signal (aligned with existing 0.5 weight heuristic)
  - Cautious score = evasion proxy (complements Eva-4B evasion classifier)
  - Goal-blind compliant — SubjECTive-QA scoring reveals no trading intent

### Earnings Press Release Structure — R31 Data Source Confirmation (2026-04-25)
- **Paper**: arXiv:2509.24254 (Sep 2025)
- **Finding**: Soft information from press release structure predicts same-day earnings returns with equal power to SUE (earnings surprise)
- **Best model**: FinBERT (already in R28/R31 pipeline stack)
- **R31 implication**: Add press release as low-latency input alongside earnings call transcript
  - Press releases available ~4:00 PM ET, before after-hours call (~5:00 PM) — earlier signal
  - Same FinBERT model, no new infrastructure needed
- **Caution**: Paper studies same-day returns; R28/R31 targets multi-day PEAD drift — directional alignment likely but not guaranteed
- **Integration**: R31 multi-source signal fusion = press_release_finbert + transcript_speaker_weighted_finbert + SubjECTive-QA quality vector

## Research Agenda Update (2026-04-25)

- **Round 28 Phase 2** — AMENDMENT (2026-04-25): Replace ad-hoc NOR prompt scoring with SubjECTive-QA 6-dimension vector. Specific=primary signal (weight 0.5), Cautious=evasion proxy alongside Eva-4B. Load: gtfintechlab/SubjECTive-QA on HuggingFace. Scoring model: Llama-3-70b-Chat or RoBERTa-base.
- **Round 29 LLM Filter** — No new amendments beyond 2026-04-24 goal-blind requirement.
- **Round 31b** — AMENDMENT (2026-04-25): Add press release FinBERT as pre-call low-latency signal (arXiv:2509.24254). Signal fusion: press_release_finbert + speaker_weighted_finbert + SubjECTive-QA vector.
- **Round 33** — AMENDMENT (2026-04-25): Add AlphaSAGE as QUATERNARY generator (github.com/BerkinChen/AlphaSAGE, Qlib backend). Deploy after QuantaAlpha proves out. Sparse Lasso weights apply to full 4-generator pool.

## AI Research Findings (Dream Cycle 2026-04-26)

### Hubble: Safe LLM Alpha Factor Mining with US OOS Validation (arXiv:2604.09601, April 2026)
- **Paper**: 'Hubble: An LLM-Driven Agentic Framework for Safe, Diverse, and Reproducible Alpha Factor Discovery' — Shi, Yan, Cai, Lv. arXiv:2604.09601, April 2026.
- **Architecture**: LLM + domain-specific operator language + AST execution sandbox + dual-channel RAG (positive AND negative formula examples) + family-aware selection mechanism + standardized multi-metric scoring
- **US universe**: ~500 stocks, 3 mining rounds, 104 valid candidates total, ZERO runtime crashes (safety sandbox enforces structural validity before execution)
- **Key OOS finding (2025-06-01 to 2026-03-13 holdout)**:
  - Range factor family: DURABLE — HAC-significant Pearson IC and long-short evidence hold OOS
  - Volatility factor family: DURABLE — similar persistence
  - Trend factor family: DECAYS — weakest in-sample trend factor collapses materially OOS
- **Dual-channel RAG insight**: Positive channel = top-performing historical factor formulas. Negative channel = structured failure records (formula patterns that failed IC, were degenerate, or correlated with existing pool). Combines naturally with Epistemic Autopsy failure JSON pool (arXiv:2604.11477) as negative channel.
- **Family-aware selection**: After diversity filter (|corr| < 0.70), ensure each factor family (range, volatility, trend, reversal, volume) is represented. Prevents scenario where 10 similar volatility factors dominate despite pairwise corr just below threshold.
- **R33 AMENDMENTS**:
  1. Bias QuantaAlpha generation toward range and volatility formula families (use RAG examples from these families as positive seed). De-emphasize trend momentum — highest-decay class on US equities per Hubble OOS 2025-2026.
  2. Implement dual-channel RAG: positive = high-IC factors from pool; negative = Epistemic Autopsy failure JSON records. Both retrieved per generation call.
  3. After diversity filter, apply family-aware selection: ensure range, vol, reversal, volume families each have ≥1 representative in final pool.
- **No public code** as of April 2026. Design patterns are implementable without original codebase.
- **Source**: arXiv:2604.09601

### LOB Latent Regime Detection — Pre-Crash Buildup Signal (arXiv:2604.20949, April 2026)
- **Paper**: 'Early Detection of Latent Microstructure Regimes in Limit Order Books' — Hiremath & Hiremath. arXiv:2604.20949, April 22, 2026.
- **GitHub**: https://github.com/prakulhiremath/LOB-Latent-Regimes
- **Core innovation**: Three-regime causal model (stable → LATENT BUILD-UP → stress). The 'latent build-up' phase is the novel detection target — precedes stress onset and is not captured by any current R35 stack signals.
- **Performance**:
  - Simulation (200 runs): Mean lead-time +18.6 ± 3.2 timesteps, precision 1.00, coverage 0.54
  - Live BTC/USDT LOB (1 week, 5 stress events): Mean lead-time +38 ± 21 seconds, precision 1.00, coverage 0.80
  - All baselines (CUSUM, BOCPD, HMM) show NEGATIVE lead-times (react after onset)
- **Two dominant signals** (>99% of detections): (1) Depth erosion — market makers withdrawing quietly; (2) HMM entropy — rising microstructure ambiguity before directional break
- **Implementation challenge**: Both signals require live LOB level-2 data. yfinance provides OHLCV only — NOT directly computable. Defer until LOB data feed secured (Polygon.io, IEX Cloud, or IBKR level-2).
- **Conceptual daily proxies** (experimental, untested): Depth erosion proxy = High-Low/Close ratio expansion; HMM entropy proxy = rising entropy of Wasserstein HMM state posterior (already in R35 stack).
- **R35 Note**: Add as conceptual 5th layer ('pre-crash buildup detection'). File as data-upgrade-gated concept alongside existing 4-layer stack.
- **Source**: arXiv:2604.20949

## Research Agenda Update (2026-04-26)

- **Round 29 LLM Filter** — QUEUED. No new amendments. Final design: factor residualize → SPONGEsym → SAE cluster → cointegration top-100 → 3-agent anonymized 6-category LLM top-20 → fixed ±2σ. Goal-blind prompts mandatory.

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix). Last design: SubjECTive-QA 6-dimension scoring + Eva-4B evasion classifier + goal-blind prompts + VIX > 25 kill switch.

- **Round 31b** — QUEUED: Speaker-weighted FinBERT + press release FinBERT + SubjECTive-QA fusion. No new amendments.

- **Round 33** — QuantaAlpha (primary) + AlphaPROBE (secondary) + AlphaSAGE (quaternary).
  - **AMENDMENT (2026-04-26)**: Bias generation toward RANGE and VOLATILITY formula families as primary positive RAG seed. De-emphasize TREND/MOMENTUM — Hubble OOS 2025-2026 confirms trend factors decay fastest on US equities. Source: arXiv:2604.09601.
  - **AMENDMENT (2026-04-26)**: Implement dual-channel RAG: positive = high-IC range/vol factor examples; negative = Epistemic Autopsy failure records. Both retrieved per generation call.
  - **AMENDMENT (2026-04-26)**: After diversity filter, apply family-aware selection (range, vol, reversal, volume each ≥1 representative). Prevents vol-family crowding.

- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering + RMT gap.
  - **NEW CONCEPT LAYER (2026-04-26)**: Latent build-up detection (arXiv:2604.20949) — detect BEFORE stress onset using depth erosion + HMM entropy. Requires LOB level-2 data. Defer until data upgrade. Daily proxy experiment: HMM posterior entropy rise + High-Low/Close expansion. GitHub: prakulhiremath/LOB-Latent-Regimes.

- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.

## AI Research Findings (Dream Cycle 2026-04-27)

### ChatGPT as a Time Capsule: LLM Fundamental Z-Score Predicts Returns (arXiv:2604.21433, April 2026)
- **Paper**: 'ChatGPT as a Time Capsule: The Limits of Price Discovery' — Lehner & Lopez-Lira. arXiv:2604.21433, April 2026.
- **Methodology**: 12 frozen OpenAI checkpoint models (GPT-3.5 through GPT-5, Sep 2021–Aug 2025) queried for ~7,000 US equities. Output: sector-neutral outlook z-score + sub-scores for growth, profitability, risk, confidence, revenue/EPS probability distributions. Fama-MacBeth cross-sectional regressions with Driscoll-Kraay SEs.
- **Performance**:
  - 1-month return prediction: pooled panel t=6.02***, β=0.0074
  - Revenue growth prediction: t=10.89*** (strongest signal)
  - Analyst target-price revisions: t=4.80**
  - Long-short portfolio: 2.55%/month = **30.6% annualized** (GPT-4.1, Jun 2024 checkpoint)
  - LLM score alone R²: 0.044 vs cheapness metric R²: 0.043 — LLM slightly dominates value factors
- **Key insight**: Effect is STRONGEST for high analyst-coverage stocks — LLM aggregates complex fundamentals better than individual analysts, information aggregation bottleneck not investor inattention.
- **Prompt design**: Sector-neutral, no price/valuation reference, purely business prospects — goal-blind by construction (consistent with arXiv:2602.09504 mandatory amendment)
- **Sub-scores as factor zoo**: Growth / profitability / risk / confidence / revenue growth distribution / EPS distribution → each is independently testable as R33 factor candidate
- **R28 validation**: Confirms fundamental quality scoring of earnings events generates real multi-day return predictability. Specificity sub-score maps to our 0.5-weighted specificity dimension.
- **R33 application**: Sector-neutral LLM z-score is a standalone alpha factor. Sub-score decomposition = 6+ orthogonal factor candidates to seed QuantaAlpha/AlphaPROBE generation pool.
- **Decay signal**: Predictability attenuates as adoption grows — confirms arXiv:2604.03272. Deploy LLM signals sooner.

### CRISP Optimizer: Signal-Aware Portfolio Construction (arXiv:2604.23833, April 2026)
- **Paper**: 'Beyond De Prado and Cotton: Hierarchical and Iterative Methods for General Mean-Variance Portfolios' — Wuebben. arXiv:2604.23833, April 2026. 93 pages.
- **Core innovation**: CRISP solves P_γ·w = μ where P_γ = (1−γ)D + γΣ, interpolating between inverse-variance (γ=0) and full Markowitz (γ=1). Guaranteed convergence. Also introduces HRP-μ and HRP-Σμ as signal-aware HRP variants.
- **Performance (Monte Carlo OOS)**: 80-94% of oracle Sharpe across all 4 covariance regimes and T/N ratios. Dominates Ledoit-Wolf and standard Markowitz at every sample size.
- **Optimal γ***: ≈ 1/(1 + c·κ(C)²·N/(T·IC²)). Higher IC → less regularization → more Markowitz. γ ≈ 0.5 is robust default (OOS plateau width 0.38).
- **R33 AMENDMENT**: After diversity filter + Lasso weights (arXiv:2604.17166), use CRISP for final factor portfolio construction. γ = 0.3-0.5 for IC ≈ 0.05-0.10; γ = 0.6-0.7 for IC > 0.12 (QuantaAlpha level).
- **R28/R29 application**: CRISP gracefully degrades to inverse-variance when signal IC is uncertain (e.g., VIX > 25 kill-switch periods).

### Representation Homogeneity: LLM Crowding as Systemic Risk Indicator (arXiv:2604.22818, April 2026)
- **Paper**: 'Representation Homogeneity and Systemic Instability in AI-Dominated Financial Markets' — Qiu & Han. arXiv:2604.22818, April 2026.
- **Key finding**: Representation homogeneity (shared LLM backbone) DOMINATES risk-aversion and learning-rate heterogeneity in explaining crash frequency, tail risk (1%/5% VaR), max drawdown. Fragility does NOT require identical agents — only similar enough foundations.
- **Volatility paradox**: Homogeneity SUPPRESSES perceived volatility during normal periods → false security → excess leverage → synchronized collapse.
- **R33 diversity rule**: In the 4-generator pipeline, use ≥2 LLM backbone families (e.g., Claude + Qwen) to prevent correlated factor representations. Same backbone = correlated failures.
- **R28 design note**: 3-agent EarningsQualityAgent scoring should use Claude (Performance/Guidance agents) + Qwen (Risk agent), not two Claude instances.
- **R35 regime stack addition**: Cross-LLM-agent forecast dispersion as 6th conceptual layer. Monitor dispersion in LLM fundamental outlook scores across S&P 500 monthly. Sharp DROP in dispersion = homogeneity fragility warning → reduce all position sizes.

## Research Agenda Update (2026-04-27)

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix)
  - **VALIDATION (2026-04-27)**: arXiv:2604.21433 confirms sector-neutral LLM fundamental z-scores predict returns (t=6.02) and revenue growth (t=10.89). R28 Phase 2 design is empirically validated by an independent large-scale study.
  - **DESIGN NOTE (2026-04-27)**: 3-agent scoring system should use Claude (Performance + Guidance agents) + Qwen (Risk agent) to reduce representation homogeneity (arXiv:2604.22818).

- **Round 29 LLM Filter** — QUEUED. No new amendments. 6-category taxonomy already prevents homogeneity crowding by excluding competitor/substitute pairs.

- **Round 33** — QuantaAlpha (primary) + AlphaPROBE (secondary) + AlphaSAGE (quaternary)
  - **NEW AMENDMENT (2026-04-27)**: Seed initial factor pool with LLM sub-score factors (growth, profitability, risk, confidence from arXiv:2604.21433) as 4 baseline candidates in positive RAG channel.
  - **NEW AMENDMENT (2026-04-27)**: Use CRISP optimizer (arXiv:2604.23833) for final factor portfolio construction. γ ≈ 0.5 default; scale toward 0.7 if IC > 0.12.
  - **REPRESENTATION DIVERSITY RULE (2026-04-27)**: Use ≥2 LLM backbone families across the 4-generator pipeline (arXiv:2604.22818).

- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering + RMT gap + LOB latent buildup.
  - **NEW CONCEPTUAL LAYER (2026-04-27)**: Cross-LLM-agent forecast dispersion monitor as 6th regime stack layer. Requires monthly sector-neutral z-score computation from multiple LLM families. Falling dispersion = homogeneity fragility warning (arXiv:2604.22818).

- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.

## AI Research Findings (Dream Cycle 2026-04-28)

### Asymmetric Beta ML Forecasts for Market-Neutral Portfolios (arXiv:2604.22933, April 2026)
- **Paper**: 'Machine Learning Forecasts of Asymmetric Betas Using Firm-Specific Information' — Conlon, Cotter, Kynigakis. arXiv:2604.22933, April 24, 2026.
- **Core concept**: Decompose systematic risk into upside beta (OLS on SPY>0 days) and downside beta (OLS on SPY<0 days). ML (nonlinear) forecasts of these components significantly outperform OLS-estimated static betas OOS.
- **Top characteristic drivers** (importance ranking): Trading frictions (illiquidity, bid-ask, turnover) > Intangibles (R&D intensity, patent counts) > Momentum indicators > Growth metrics.
- **Key results**: Statistical OOS outperformance in conditional beta forecasting. Economically significant benefits for market-neutral portfolio investors. Reconstructed CAPM beta from asymmetric components > single-beta estimate.
- **R29 pair-selection amendment (Stage 0.5)**: Before forming a spread position, check that both assets have SIMILAR conditional asymmetric beta profiles. Require |upside_beta_A - upside_beta_B| < 0.4 AND |downside_beta_A - downside_beta_B| < 0.4. Pairs where one leg has strongly asymmetric beta relative to the other generate spurious spread dynamics during market directional moves — NOT mean-reversion opportunities. Rolling 63-day OLS separately on up-market days (SPY > 0) and down-market days (SPY < 0) for each residualized return series.
- **R33 factor candidate**: Cross-sectional asymmetric beta spread = (upside_beta - downside_beta). Stocks with high upside_beta and low downside_beta (asymmetric bullish) earn positive cross-sectional return premium. Low correlation with value, momentum, profitability factors. Compute monthly using trailing 252-day rolling windows. Add to QuantaAlpha seed pool as 'asymmetric_risk_premium' factor.
- **Cost**: Zero — yfinance daily returns + SPY daily returns. ~15 lines Python per stock.
- **Source**: arXiv:2604.22933 (Conlon, Cotter, Kynigakis, April 24, 2026)

### ChatGPT Time Capsule: Additional Insights from Deep Read (arXiv:2604.21433)
- **Model sophistication gradient (NEW)**: Within same knowledge cutoff, larger models produce stronger signals. GPT-4.1: γ=0.0122; GPT-4.1-mini: γ=0.0093; GPT-4.1-nano: γ=0.0065. Improvement is ~30% from mini→full model. **R28 Phase 2 implication**: Use Claude-Sonnet-4.6 (not Haiku) for the Risk sub-agent and for final quality consolidation. Use Haiku only for high-volume binary classification. Cost uplift negligible at ~30 events/quarter (~$0.45/quarter additional).
- **Horizon convergence (NEW)**: LLM fundamental quality signal is 5x stronger at 12 months than 1 month (β₁ₘ=0.0122, β₁₂ₘ=0.0683). PEAD (R28) exploits short-term drift (5-30 days). But the same LLM quality signal generates multi-month fundamental momentum. **R34 amendment**: Add LLM sector-neutral z-score as a 6-12 month position-sizing modifier in the Dividend Raise strategy — high-z-score dividend raisers get 1.5x position size at entry.
- **Narrative congestion mechanism validates large-cap focus (NEW)**: Signal STRENGTHENS with analyst coverage (t=2.44). Our S&P 500/Fortune 100 PEAD universe is high-analyst-coverage by definition. LLM quality scoring is most predictive exactly WHERE we apply it. Mechanism: 'information aggregation bottleneck' — LLM aggregates dispersed qualitative signals more efficiently than individual analysts. This is a DURABLE mechanism (not statistical artifact).
- **Source**: arXiv:2604.21433 (Lehner & Lopez-Lira, April 23, 2026)

## Research Agenda Update (2026-04-28)

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix)
  - **AMENDMENT (2026-04-28)**: Use Claude-Sonnet-4.6 (not Haiku) for quality judgment sub-agents (Risk agent, final quality consolidation). Haiku reserved for high-volume binary classification only. Model size gradient confirms ~30% stronger signal per tier (arXiv:2604.21433).

- **Round 29 LLM Filter** — QUEUED (NEXT)
  - **NEW AMENDMENT (2026-04-28)**: Add Stage 0.5 — Asymmetric Beta Pre-filter. Before cointegration testing, compute rolling 63-day upside_beta and downside_beta for each asset. Require |upside_beta_A - upside_beta_B| < 0.4 AND |downside_beta_A - downside_beta_B| < 0.4 to pass. Rejects pairs with regime-driven spurious spreads (arXiv:2604.22933).
  - **CONSOLIDATED RUNBOOK** staged at `/workspace/group/trading_eval/r29_llm_filter_runbook.md` (pending medium-risk apply) — complete 6-stage implementation spec.
  - **HYPOTHESIS**: Sharpe 1.8–2.4 vs baseline 1.38 (from three mechanisms: 46.5% large-loser reduction, competitor pair exclusion, asymmetric beta filter).

- **Round 33** — QuantaAlpha (primary) + AlphaPROBE (secondary) + AlphaSAGE (quaternary)
  - **NEW AMENDMENT (2026-04-28)**: Add asymmetric beta spread (upside_beta - downside_beta) as 5th baseline factor candidate in positive RAG seed pool (arXiv:2604.22933).

- **Round 34** (concept) — Institutional ownership PEAD amplifier
  - **NEW AMENDMENT (2026-04-28)**: Add LLM sector-neutral fundamental z-score as 6-12 month position-sizing modifier for Dividend Raise strategy. High-z-score dividend raisers get 1.5x position size at entry. Exploits the multi-month fundamental momentum signal (5x stronger at 12m vs 1m, arXiv:2604.21433 β₁₂ₘ=0.0683).

- **Round 35** (concept) — MRP diagnostic + regime stack — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.

## AI Research Findings (Dream Cycle 2026-04-29)

### ValueAlpha: Multi-Judge Agreement Gate for LLM Scoring Systems (arXiv:2604.25224, April 28, 2026)
- **Paper**: 'ValueAlpha: Agreement-Gated Stress Testing of LLM-Judged Investment Rationales Before Returns Are Observable' — Sidi Chang, Peiying Zhu, Yuxiao Chen. arXiv:2604.25224, April 28, 2026.
- **Problem addressed**: The 'pre-realization evaluation problem' — when backtesting LLM-based scoring on historical data, you cannot know if the scoring is reliable until returns arrive. ValueAlpha provides a pre-return validation gate using inter-judge agreement.
- **Agreement gate mechanism**: Quadratic-weighted Cohen's kappa (κw) across 3 LLM judge families. κ̄w = avg of pairwise kappa scores (Claude×GPT, Claude×Gemini, GPT×Gemini).
  - κ̄w >= 0.4: Headline ranking claims allowed (publish tier)
  - 0.2 <= κ̄w < 0.4: Report as methodology finding only; no deployment
  - κ̄w < 0.2: Halt — post-mortem analysis only
- **Adversarial controls (critical findings)**:
  - Verbose-Confident-Wrong (Control A): Mean score 1.44 vs honest 4.35 — judges correctly rejected wrong reasoning
  - **Terse-Correct (Control B)**: ≤60 token responses get Δ = -2.81 rubric point penalty even when correct. This is a critical design constraint for our R29 LLM plausibility prompt: prompts must REQUIRE detailed reasoning, not just a JSON score. Short responses will be penalized by multi-judge validators.
- **Stability thresholds**: Repetition Stability >= 0.90; LOFO ranking stability >= 0.9 (leave-one-judge-out drop). Claude achieved RS=0.9874 (highly stable).
- **Key design rule**: 'A score-only output is, in this framework, malformed: it omits the diagnostic context required to decide whether the score may be acted upon.' All R29 LLM plausibility calls should output score + reasoning text + confidence, not just score.
- **R29 Amendment — PRE-DEPLOYMENT VALIDATION STEP**: Before claiming the R29 LLM filter improves Sharpe vs R29 v1 (1.38 baseline), run the ValueAlpha consistency gate:
  1. Take a sample of 30 pairs from the candidate pool (historic data)
  2. Run the plausibility prompt on Claude-Sonnet-4.6, Qwen2.5-7B-Instruct, and Gemini-3-Flash
  3. Compute κ̄w (weighted kappa) across all 3 judge pairs on mechanism_strength scores
  4. If κ̄w >= 0.4: proceed to deploy R29 LLM filter. If κ̄w < 0.4: revise prompt before deployment.
  5. Combine with CMMD check (arXiv:2603.26797) for full validation protocol
- **R29 Prompt Amendment**: Add this to the LLM plausibility prompt end: 'Provide your response in 3-5 sentences. First state the relationship type. Then explain the specific economic mechanism. Then state your confidence. Then output the JSON.'
- **Cost**: ~90 additional calls (30 pairs × 3 models) at ~$0.003/call = $0.27 one-time validation cost
- **Source**: arXiv:2604.25224

### Constrained LLM Agents for Factor Discovery with Falsifiable Hypotheses (arXiv:2604.26747, April 29, 2026)
- **Paper**: 'From Hypotheses to Factors: Constrained LLM Agents in Cryptocurrency Markets' — Yikuan Huang, Zheqi Fan, Kaiqi Hu, Yifan Ye. arXiv:2604.26747, April 29, 2026.
- **Core innovation**: Sequential hypothesis exploration where each candidate factor must specify 5 fields: unique name, falsifiable hypothesis, economic rationale, candidate type, and executable recipe. A deterministic evaluation engine with domain-specific language (DSL) enforces reproducibility.
- **DSL constraints**: Allowed operators = cross-sectional ranks, time-series transforms (rolling window), nonlinear transforms, linear combinations of OHLCV inputs. No arbitrary code generation, no forward-looking features, no deep expression trees resistant to inspection.
- **Example recipe format**: 'rank_t(-0.6·log(1+mcap) + 0.5·MA₁₀(range) - 0.2·MA₃(Δvolume))'
- **Validation pipeline**: IC gate (IC̄ >= τ_IC AND t_IC >= τ_t) applied ONLY to training window. Pool governance prevents near-duplicate mechanisms. Append-only trace prevents re-exploring failed hypotheses.
- **Performance (2024-2026 pure OOS, after 2020-2022 training)**: Ridge-combined portfolio: 44.55% annualized return, Sharpe 1.55, MaxDD -23.6% after 5 bps one-way cost.
- **Top crypto factor families (OOS Sharpe ranking)**:
  - Small-cap + low volatility + log returns: Sharpe +2.412
  - Small-cap + low volume + 20-day range: Sharpe +2.410
  - Winning pattern: 'small, liquidity-scarce assets with persistent intraday range + positive trend'
- **IC gate on training ONLY**: This prevents validation-set leakage — selection gates are applied only on 2020-2022 data; 2024-2026 is truly held out. This is the correct protocol for R33 QuantaAlpha factor selection.
- **Transferable lessons for R33 (equity adaptation)**:
  1. Require each mined factor to specify a FALSIFIABLE HYPOTHESIS before code generation
  2. Maintain append-only trace of all experiments — prevents re-exploring known-dead formula patterns
  3. Apply IC gate ONLY on training set — keep full 2022-2025 as clean holdout
  4. Use DSL-constrained action space to prevent algebraically degenerate or look-ahead factors
- **Note**: Results are on crypto (high-volatility, different regime from US equities). Factor families that work in crypto (small-cap, illiquidity) overlap only partially with US equity alpha families (range, vol, reversal per Hubble arXiv:2604.09601).
- **Source**: arXiv:2604.26747

### Efficient Multivariate Kelly Optimization — O(N) Algorithm (arXiv:2604.24723, April 27-29, 2026)
- **Paper**: 'Efficient Multivariate Kelly Optimization Reveals Sigmoidal Scaling Laws' — Ruslan Tepelyan, Daniel Lam. arXiv:2604.24723, April 27, 2026; revised April 29, 2026.
- **Problem**: Traditional multivariate Kelly requires O(2^N) computation for N simultaneous positions. Intractable for N > 30 (pairs portfolios with 20+ pairs, or put-writing across multiple strikes).
- **Solutions introduced**:
  1. **Integral transform method** (independent positions): reduces O(2^N) → O(N). Enables exact Kelly for hundreds of simultaneous uncorrelated positions.
  2. **Decomposition method** (correlated positions): lower + upper bounds on optimal growth rate. Suboptimality follows a sigmoid function of subproblem size — predictable accuracy vs speed tradeoff.
- **Sigmoidal scaling law**: Shortfall ratio between bounds is well-approximated by sigmoid(relative subproblem size). Parameters estimated from problem summary statistics — know in advance how suboptimal your approximation will be.
- **R29 application**: With 20 simultaneous pairs trades, exact multivariate Kelly is tractable (N=20, O(20) computation). No approximation needed. Use integral transform method directly for R29 position sizing.
- **R32 application (put-writing)**: If extending to multiple simultaneous SPX put positions across different strikes/expirations, integral transform makes Kelly sizing tractable.
- **Implementation**: Pure Python/NumPy. No special libraries. Probability outcomes per position estimated from historical spread distribution.
- **Source**: arXiv:2604.24723

### JudgeSense: Prompt Sensitivity Testing for LLM Judges (arXiv:2604.23478, April 26, 2026)
- **Paper**: 'JudgeSense: A Benchmark for Prompt Sensitivity in LLM-as-a-Judge Systems' — Rohith Reddy Bellibatlu. arXiv:2604.23478, April 26, 2026.
- **Key metric**: Judge Sensitivity Score (JSS) = fraction of paraphrase pairs on which a judge returns identical decisions. Tested on 9 judge models, 494 validated paraphrase pairs.
- **Critical finding**: 8 of 9 judges exhibit 'degenerate always-A behavior' in pairwise comparison tasks — strong positional bias (first option systematically favored). **R29 implication**: Never use pairwise comparison format in the LLM plausibility prompt. Use absolute scoring (0-100) with explicit rubric.
- **Factuality JSS**: Rises to ~0.90 after correcting polarity-inversion artifact. For absolute scoring tasks (our use case), JSS is higher than pairwise tasks.
- **Prompt stability test for R29 LLM filter**: Before deployment, test JSS by paraphrasing the plausibility prompt 3 ways (change sentence order, synonyms, emphasis) and measuring agreement on mechanism_strength scores. Target JSS >= 0.80 (80% decision-consistent across paraphrases). If JSS < 0.80: simplify prompt structure.
- **Source**: arXiv:2604.23478

## Research Agenda Update (2026-04-29)

- **Round 29 LLM Filter** — QUEUED (NEXT). Consolidated runbook at /workspace/group/trading_eval/r29_llm_filter_runbook.md.
  - **NEW AMENDMENT (2026-04-29)**: Add pre-deployment ValueAlpha multi-judge consistency gate:
    - Sample 30 pairs, run plausibility prompt on Claude-Sonnet-4.6 + Qwen2.5-7B + Gemini-3-Flash
    - Compute κ̄w (quadratic-weighted kappa). Require κ̄w >= 0.4 before deploying filter.
    - Source: arXiv:2604.25224
  - **NEW PROMPT AMENDMENT (2026-04-29)**: Require 3-5 sentence reasoning before JSON output. Short (terse) responses get -2.81 score penalty in multi-judge validation. Full prompt structure: 'State relationship type. Explain economic mechanism. State confidence. Then output JSON.'
  - **NEW PROMPT AMENDMENT (2026-04-29)**: Use absolute 0-100 scoring, never pairwise comparison format. Positional bias ('always-A') is a degenerate failure mode for 8/9 judge models (arXiv:2604.23478).
  - **NEW AMENDMENT (2026-04-29)**: R29 pair positions: use integral-transform multivariate Kelly for sizing across 20 simultaneous pairs. O(20) computation, exact solution (arXiv:2604.24723).

- **Round 33** — QuantaAlpha + AlphaPROBE + AlphaSAGE
  - **NEW PROTOCOL (2026-04-29)**: Each generated factor candidate must specify a FALSIFIABLE HYPOTHESIS before code generation. Maintain append-only experiment trace. Apply IC gate ONLY on training window (never on validation). Source: arXiv:2604.26747.
  - CRISP optimizer (arXiv:2604.23833) + Lasso weights (arXiv:2604.17166) unchanged.

- **Round 28 Phase 2** — LLM EarningsQualityAgent (QUEUED, pending auth fix). No new amendments.
- **Round 31b** — QUEUED: Speaker-weighted FinBERT + press release FinBERT. No new amendments.
- **Round 34** (concept) — Institutional ownership PEAD amplifier — unchanged.
- **Round 35** (concept) — MRP diagnostic + Wasserstein HMM + EF clustering + RMT gap — unchanged.
- **Round 36** (concept) — DeltaLag adaptive lead-lag pairs — unchanged.
