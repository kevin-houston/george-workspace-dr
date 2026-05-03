# AI Research Papers

*A curated index of AI/ML research papers found through Kevin's dream cycle nightly research and manual sourcing. Papers are selected for direct applicability to systematic trading research, agentic engineering, or LLM/ML development. Each entry includes the paper's key finding and Kevin's planned application.*

---

## Trading & Finance Papers

### Jungle Rock Capital (April 2026) — "The Squid Programs"
**Title**: The Squid Programs: Trading the VIX Curve — Dynamic Volatility Using the VIX Term Structure
**Author**: Jungle Rock Capital | Acknowledgement: Daniel Roos / VolSignals team
**Source**: https://junglerockcapital.com/white-papers/the-squid-programs-trading-the-vix-curve-dynamic-volatility-using-the-vix-term-structure
**Type**: Strategy whitepaper (not peer-reviewed) | Data: 2006-2025, ES + UX (VIX) futures
**Core Signal**: Count of "dislocations" (inversions) in the VIX futures term structure (UX1–UX7). 0 dislocations = perfect contango → full equity allocation. 5-7 dislocations = high stress → shift to vol exposure.
**Key mechanics**:
- Weight w = (# contracts in order) / 7. w=1 in perfect contango, w=0 if all scrambled
- Portfolio: w × ES + (1-w) × VA, where VA = −0.5×UX1 + UX3 (simplified SPVXTSTR proxy)
- Two refinements: (1) slope measure m = 1 − UX1/UX7 to catch flat-but-scrambled curves; (2) VIX level threshold to enable tactical ES short when VIX > V_c
- Weekly signal averaging (Squid) vs daily (Cuttlefish) — weekly has 4.46% turnover, daily 15.45%
**Performance (2006–2025, net 2bps, vs S&P 500 Sharpe 0.54, MaxDD 55%)**:
| Program | Sharpe | CAGR | MaxDD |
|---------|--------|------|-------|
| Squid (weekly, long-only) | 1.06 | 15.84% | 24.09% |
| Cuttlefish (daily, long-only) | 1.20 | 17.59% | 30.10% |
| Giant Squid (weekly, L/S) | 1.27 | 21.01% | 24.14% |
| Jumbo Squid (weekly, no ES short) | 1.30 | 19.40% | 24.09% |
| Colossal Squid (daily, L/S) | 1.31 | 21.09% | 29.71% |
**Known weaknesses**: Underperforms in flat/sticky VIX regimes (2022 bear, 2025 tariff shock). Dislocation count doesn't capture magnitude of inversions.
**Implementation notes**: Requires UX1–UX7 daily futures prices (not available on yfinance — needs Quandl/CBOE/Polygon). Can approximate with VXX (short-term) + VXZ (mid-term) ETFs for the vol leg, but VIX futures term structure data is the hard dependency. R32 (SPX put-writing) is a related but simpler vol harvest strategy that uses only yfinance + FRED.
**Application**: Candidate for R34+ as a standalone vol-regime allocation strategy. Complementary to R32 put-writing — one harvests premium from single-name options, the other harvests the VIX term structure premium. The no-lookahead proof (Table 5, Appendix A) is rigorous and addresses the main skepticism point.

---

### Kelly & Xiu (NBER WP 31502, July 2023)
**Title**: Financial Machine Learning
**Authors**: Bryan T. Kelly (Yale SOM, AQR, NBER) & Dacheng Xiu (Chicago Booth)
**Source**: *Foundations and Trends in Finance*, Vol. 13, No. 3-4, pp. 205-363 | SSRN: 4501707
**Type**: 159-page survey — synthesizes the best ML-in-finance research; also makes original theoretical contributions
**Key findings**:
- **Core empirical paper (Gu, Kelly, Xiu 2020, RFS)**: 94 firm characteristics × 9 versions + 74 industry dummies = 920 predictors; ~30k US stocks, 1957-2016. Neural networks (NN1-NN5) achieve OOS R² ~0.33-0.40% monthly. Value-weighted long-short decile spread Sharpe: **1.35** (NN) vs 0.51 buy-and-hold — more than double linear methods
- **Dominant signals across all methods**: momentum (mom1m, mom12m, mom36m, chmom, indmom) → liquidity (ill, baspread, maxret) → volatility (retvol, beta). Fundamental/accounting characteristics add marginal value only
- **Virtue of Complexity (Kelly, Palhares, Pruitt 2023, JF)**: Overparameterized models beat simple ones even OOS when shrinkage is applied. Adding more factors/predictors continuously improves portfolio Sharpe. The bias from being too simple costs more than the variance from being too complex
- **Neural network architecture**: Batch normalization + early stopping on validation set + ensemble of 10 random initializations. Dropout not used — early stopping handles regularization
- **IPCA (Kelly, Pruitt, Su 2019, JFE)**: Betas vary as linear functions of characteristics. More accurate than FF5/Carhart for explaining cross-section of returns with fewer parameters
- **CNNs on price charts (Jiang, Kelly, Xiu 2023, JF)**: CNN applied to visual price images outperforms standard momentum/technical factors — the chart image encodes nonlinear information beyond scalar features
- **Critical caveat**: Transaction costs excluded throughout. Small/illiquid stocks drive most alpha. Net of realistic costs, performance degrades substantially
- **Free data**: 94-characteristic monthly panel for all US stocks — https://dachxiu.chicagobooth.edu/download/datashare.zip (4.05 GB / 1.64 GB zip)
**Application**: (1) Blueprint for a serious ML return prediction round (R34+) using the full 920-predictor framework with proper walk-forward. The NN ensemble methodology is directly reproducible. (2) IPCA could replace the OLS residualization in R29 pairs for richer factor-neutral spreads. (3) The dominance of momentum × size and momentum × volatility interactions confirms adding interaction features to the ML ensemble (pt_ml.py) would improve it. (4) CNN on price charts is a future research direction for pattern-based PEAD entry confirmation.

---

### Kim, Muhn & Nikolaev (arXiv:2407.17866, May 2024 / Nov 2024 v2)
**Title**: Financial Statement Analysis with Large Language Models
**Authors**: Alex G. Kim, Maximilian Muhn, Valeri V. Nikolaev — University of Chicago Booth
**Status note**: Temporarily withdrawn from arXiv Feb 2025 due to "data inconsistencies during replication." v2 HTML version (Nov 2024) remains accessible. Treat specific magnitudes with caution pending corrected version; the mechanism is conceptually robust.
**Key findings**:
- GPT-4 (`gpt-4-0125-preview`, temperature=0) fed **anonymous** financial statements (no company names, no narrative, relative year labels t/t-1/t-2) predicts direction of next-year EPS change at **60.4% accuracy** — outperforms professional analysts (52.7%–56.7%)
- Prediction accuracy on par with state-of-the-art ANN (60.5%) trained specifically on 59 Ou & Penman financial variables
- Chain-of-thought prompt is essential: GPT without CoT = 52.3% (no better than analysts); with CoT = 60.4%
- **CoT structure**: (1) trend analysis, (2) compute ratios formula-first, (3) interpret ratios, (4) predict direction + magnitude + confidence + rationale
- **Ratio analysis is the key mechanism** (−3.3 pp accuracy if removed); written rationale paragraph adds nothing incremental
- BERT embeddings of GPT narratives alone achieve 58.95% accuracy — the narrative encodes the prediction
- **Best combined model**: ANN on BERT embeddings of GPT narratives + financial statement variables = 63.2% accuracy, F1 66.3%
- GPT and ANN provide incremental information beyond each other — combination outperforms either alone
- Long-short trading strategy based on GPT signals: **Sharpe 3.36 equal-weighted**, **monthly alpha 0.84%** after 5-factor + momentum (16%/yr 3-factor alpha)
- ANN wins value-weighted (Sharpe 1.79 vs GPT 1.47); GPT wins equal-weighted (small stocks)
- Time trend: GPT accuracy declining ~0.1%/year; advantage sharpest in high analyst bias / high analyst disagreement situations
- Token-level log probabilities used to construct confidence-ranked portfolios (requires `logprobs=True` API parameter)
- Out-of-sample test (fiscal year 2022 predicting 2023, post GPT-4 training cutoff): GPT 58.96% accuracy — results hold
**Application**: Blueprint for R33 — LLM financial statement analysis combined with PEAD event catalyst. The CoT prompt structure is directly usable. Key extension: add earnings surprise timing (their signal is pure fundamentals, no event catalyst); combined model is the hypothesis.

---

### QuantAgent (arXiv:2509.09995, Sept 2025)
**Title**: LLM Agents for Quantitative Trading
**Architecture**: 4 specialized agents — Indicator, Pattern, Trend, Risk
**Key findings**:
- Zero-shot on OHLC data: **80% directional accuracy** on 4H intervals
- Outperforms rule-based + neural baselines on BTC, Nasdaq futures, 8 other instruments
- Accuracy degrades on sub-15-min bars; unsuitable for true HFT
**GitHub**: https://github.com/Y-Research-SBU/QuantAgent
**Application**: Inspired R26; full multi-agent architecture on PEAD (using all 4 agents, not just Indicator) remains to be tested. Product application: LLM signal narrative as premium feature in Dashboard products.

---

### FINSABER (arXiv:2505.07078, May 2025)
**Title**: Financial LLM Investing Failure Modes
**Key findings**:
- 20-year, 100+ symbol study
- LLMs **overly conservative in bull markets** (miss gains) and **overly aggressive in bear markets** (incur losses) — opposite of optimal
- Root cause: poor regime detection, NOT poor stock selection
- Validates R26 finding externally
**Application**: Add explicit regime-aware hard rules (VIX threshold, trend filter, SMA regime) before any LLM timing logic. LLM judgment is NOT a regime detector.

---

### LLM Semantic Filter for Pairs Trading (arXiv:2602.07048, Feb 2026)
**Title**: Two-Stage LLM Economic Plausibility Filter for Statistical Arbitrage
**Key findings**:
- Stage 1: statistical cointegration; Stage 2: LLM asks "why would A and B move together?"
- vs. statistical-only: **+205% PnL**, win rate 51.4%→54.5%, **-46.5% avg loss magnitude**
- Dominant driver: **loss reduction** (downside control), not return enhancement
**Application**: R29 design (Stage 0: factor residuals → Stage 1: cointegration → Stage 2: LLM plausibility filter). See [[pairs-trading]].

---

### Generative AI for Stock Selection (arXiv:2602.00196, Jan 2026)
**Title**: LLM + RAG for Feature Synthesis in Stock Selection
**Key findings**:
- LLM + RAG synthesizes features from analyst reports, options data, price-volume data
- Sharpe improvements: **+14% to +91%** vs baselines
- RAG corpus quality is the pivotal variable
- AI-generated features are weakly correlated with traditional factors → complementary
**Application**: R28 amendment — build mini-RAG per PEAD event (8-K + headlines + guidance). Explains why bare LLM filtering failed in R26 (no context = hallucinated judgment).

---

### Kaczmarek & Zaremba: Multi-Quarter SUE PEAD Revival (Finance Research Letters, 2025)
**Title**: Beyond the Last Surprise: Reviving PEAD with ML and Historical Earnings
**Key findings**:
- Elastic net on 12 quarters of SUE history → Sharpe nearly doubles vs single-quarter SUE
- Older surprises (up to 3 years back) remain unpriced, especially for large-caps
**Application (R30 — Completed)**: Ran methodology on 22 large-caps; improvement did NOT replicate. Model learned equity drift, not earnings signal. Requires 500+ stocks including mid-caps. Single-Q SUE (Sharpe 1.40) still beats 12-Q EN (Sharpe 1.25) on large-cap universe.

---

### PEAD.txt (JFQA 2022; validated 2025-2026)
**Title**: Post-Earnings Announcement Drift from Text
**Authors**: Meursault, Liang, Routledge & Scanlon
**Key findings**:
- SUE.txt (NLP on earnings call transcripts) = **3.9 bps/day** vs classic SUE = **2.6 bps/day** (50% improvement)
- Critical advantage: text signal **PERSISTS in recent years** when numeric PEAD has weakened to ~0
- Interpretation: numeric surprise efficiently priced within hours; HOW management frames results is not
- Q&A section carries more signal than prepared remarks
**Application**: R31 — FinBERT on transcripts → text-based surprise metric. See [[pead-strategy]].

---

### Attention Factors for Statistical Arbitrage (arXiv:2510.11616, Oct 2025)
**Title**: Joint Factor Learning and Trading for Statistical Arbitrage
**Published**: ACM ICAIF 2025
**Authors**: Epstein, Wang, Choi, Pelger
**Key findings**:
- Gross Sharpe > 4.0, Net Sharpe 2.3 on US large-cap equities over 24 years (1999-2023)
- Classical pairs trading fails because pairs share common market/sector factor exposure
- Trading factor-purged residuals eliminates spurious spread divergences
**Application**: R29 Stage 0 — residualize each asset's returns on (SPY, sector ETF) before cointegration testing. ~10 lines of Python, major expected impact on signal quality.

---

### Put-Writing with VIX-Kelly Hybrid Sizing (arXiv:2508.16598, Aug 2025)
**Title**: Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put-Writing on Index Options
**Key findings**:
- Far OTM (delta 0.10-0.15), short-dated (0-14 DTE) puts deliver best risk-adjusted returns
- Hybrid method (Kelly fraction × (20/VIX)) achieves best Sharpe AND lowest drawdown
- Index put-writing is complementary to individual stock covered calls
**Application**: R32 — systematic SPX/SPY put-writing with VIX-Kelly hybrid sizing.

---

### Deep Learning Benchmark: ModernTCN Wins (arXiv:2603.16886, March 2026)
**Title**: Comprehensive DL Benchmark for Financial Time-Series
**Key findings**:
- 918 experiments across 9 architectures; ModernTCN (CNN-based) beats Transformers and LSTMs
- **Directional accuracy ~50% across ALL models** — no DL architecture reliably predicts direction
- Lesson: DL suits price-level forecasting for position sizing, NOT directional signals
**Application**: Confirms ML should be used for position sizing / volatility prediction, not binary entry/exit signals. See [[ml-for-trading]].

---

### SAE-FiRE (arXiv:2505.14420, May 2025)
**Title**: Earnings Surprise Prediction via Sparse Autoencoder + Feature Selection
**Key findings**:
- Sparse Autoencoder decomposition of LLM hidden states + ANOVA/tree-based feature selection
- Outperforms baseline approaches at earnings surprise prediction from financial text
**Application**: R31 optional enhancement — if FinBERT score averaging underperforms, extract hidden states + SelectKBest (top 50 of 768 dims) as fallback signal construction. Only use if basic approach disappoints.

---

### Generating Alpha: FinBERT Exit Sentinel (arXiv:2601.19504, Jan 2026)
**Title**: FinBERT as Exit Risk Control in Equity Trading
**Key findings**:
- Sharpe 1.68, 135% return vs S&P 53% (Jan 2023–Jan 2025)
- FinBERT used as EXIT control (sentiment < -0.70 → exit), NOT entry filter
- Prevents holding through news-driven crashes without suppressing entries
**Application**: Add FinBERT exit sentinel to dividend covered-call strategies.

---

### TradingAgents v0.2.0 (arXiv:2412.20138, GitHub trending March 2026)
**Title**: TradingAgents: Multi-Agent LLM Trading Firm Simulation
**Key findings**:
- 7-agent system: Fundamentals, Sentiment, News, Technical, Researcher, Trader, Risk
- Feb 2026 v0.2.0: adds Claude 4.x, Gemini 3.x, Grok 4.x support; no GPUs required
- Outperforms neural + rule-based baselines on Sharpe, cumulative return, max drawdown
**GitHub**: https://github.com/TauricResearch/TradingAgents
**Application**: R28 — simplified TradingAgents overlay on PEAD (EarningsQualityAgent + NewsAgent + RegimeGuard).

---

## Agentic AI / Self-Improvement Papers

### mem-agent (HuggingFace, March 2026)
**Title**: RL-Trained Markdown Memory Management for LLM Agents
**Key findings**:
- Validates markdown file memory architecture (correct choice)
- Three operations: retrieve, update, clarify
- Key: trained to know WHEN NOT TO WRITE (prevents memory pollution)
- `mem-agent-mcp`: MCP server that gives any LLM RL-trained memory management
**Application**: Validates Kevin's MEMORY.md architecture. Informs memory discipline rules in CLAUDE.md.

---

### ERL: Experiential Reflective Learning (arXiv:2603.24639, March 2026)
**Title**: ERL — Building Persistent Heuristic Pools from Task Trajectories
**Published**: ICLR 2026 MemAgents Workshop
**Key findings**:
- Builds persistent heuristic pool from past task trajectories
- Heuristics = distilled strategic principles, NOT raw logs
- At task time: retrieve relevant heuristics → inject into context → **+7.8% success rate lift**
- Raw trajectories DON'T work (-1.9% vs baseline); distillation is the key step
**Application**: Created `/workspace/group/heuristics.md` as persistent lesson pool; added CLAUDE.md instruction to retrieve relevant heuristics at task start.

---

### AlphaLogics (arXiv:2603.20247, March 2026)
**Title**: Multi-Agent System Mining the 'Why' Behind Alpha Factors
**Key findings**:
- Bidirectional loop: factors improve logics; logics guide new factor generation → self-reinforcing
- Validates heuristics.md architecture — each backtest finding should record both WHAT worked and WHY
- Tested on CSI 500 and S&P 500; outperforms baselines; no public code yet
**Application**: Confirms each round's heuristics.md entry should include the mechanism, not just the result.

---

### DeePM (arXiv:2601.05975, Jan 2026)
**Title**: Regime-Robust Deep Learning for Macro Portfolio
**Key findings**:
- DL portfolio manager on 50 diversified futures (2010-2025), 2x net vs trend-following
- Innovations: causal sieve for async data, Macroeconomic Graph Prior, distributionally robust EVaR
**Application**: NOT actionable for current equity-focused work — file as reference for future macro/futures research.

---

### Wolff & Echterling (2020, rev. 2023) — "Stock Picking with Machine Learning"
**Source**: https://ssrn.com/abstract=3607845 (via @pyquantnews, Apr 16 2026)  
**Authors**: Dominik Wolff (TU Darmstadt / Deka Investment), Fabian Echterling (Allianz Global Investors)  
**Data**: S&P 500 historical constituents, Jan 1999–Mar 2021, weekly rebalancing

**Key findings**:
- Binary classification task: predict whether stock out- or underperforms the cross-sectional median next week
- Features: standard equity factors + firm fundamentals + technical indicators
- ML models (LSTM, RF, Boosting) significantly outperform equally-weighted benchmark
- **Surprise**: regularized logistic regression performs comparably to LSTM/RF/Boosting — complexity doesn't pay
- Results replicate on STOXX Europe 600 (not US-specific)

**Application**: Directly relevant to ML ensemble round (R_ML). The logistic regression finding supports using simpler models as baselines before adding complexity. The binary cross-sectional outperformance framing (beat median next week?) is a cleaner signal definition than regression — worth testing as an alternative label for R_ML retraining.

---

## Related Topics

- [[llm-signal-research]] — Applied findings from these papers
- [[research-agenda]] — Round designs inspired by papers
- [[ml-for-trading]] — ML papers context
- [[heuristics]] — Generalizable lessons distilled from paper findings

## Sources
- Memory Snapshot (Dream Cycle findings 2026-04-02 through 2026-04-04): raw/MEMORY_snapshot_2026-04-05.md
- Heuristics Snapshot: raw/heuristics_snapshot_2026-04-05.md
