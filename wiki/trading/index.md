---
updated: 2026-06-28 (ai-model-benchmarks.md expanded — PolyBench+PolySwarm+PredictionMarketBench added)
status: active
phase: 2→3 — backtesting complete, paper trading active
---

# Trading & Prediction Markets Project

Goal: establish an income stream for Kevin via algorithmic securities trading and prediction markets. Work autonomously — research nightly, build incrementally, paper trade to prove results, then go live.

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Done | Research & wiki-building |
| 2 | Active | Backtesting infrastructure + hypothesis testing |
| 3 | Pending | Paper trading (Alpaca) |
| 4 | Pending | Live trading |

## Wiki sections

- [Algorithms](algorithms/) — trading strategy catalog
  - [Position Sizing & Portfolio Construction](algorithms/position-sizing.md) ← new 2026-04-27
  - [Momentum Strategies](algorithms/momentum-strategies.md) ← updated 2026-05-14 (H198 CONFIRMED: 6-1m stock momentum OOS Sharpe 1.174; H217 CONFIRMED: median alpha101 OOS 1.559 — strongest confirmed stock signal; H228 CONFIRMED: H217+H181 blend OOS 1.572)
  - [Pairs Trading / Stat Arb](algorithms/pairs-trading.md) ← updated 2026-06-21 (ETF+statistical pairs EXHAUSTED H152-H200; LLM SEMANTIC PAIRS new direction — H316 queued; Moira arXiv:2605.01954 HRL+LLM; LLM-Augmented Semantic Networks arXiv:2604.19476; 2-stage embedding+GPT-4o pipeline; $0.07/run for 30-stock universe; link_strength≥6 filter)
  - [Event-Driven Strategies](algorithms/event-driven.md) ← updated 2026-05-05 (H163 **CONFIRMED** — FinBERT NLP signal real; H161/H162 PARTIAL CONFIRMED; H168 IN-PROGRESS)
  - [Short-Term Reversal](algorithms/short-term-reversal.md) ← new 2026-05-07 (industry-adjusted reversal 0.53%/month globally; SSRN:6630998; H181 queued)
  - [Options Income Strategies](algorithms/options-income-strategies.md) ← updated 2026-05-21 (+ debit spreads: bull call/bear put setup, IV/DTE criteria, management rules, earnings play guidance; iron condor adjustment/rolling mechanics: untested-side roll, tested-side roll, BWB conversion; earnings straddle IV-expansion trade; paper trade annotations WMT/DLTR/SPY)
  - [Low-Volatility Anomaly](algorithms/low-volatility.md) ← updated 2026-05-18 (H205 design + regime-conditional BAB risk flag added; ScienceDirect May 2025 Asia study noted)
  - [BSM & Information Geometry](algorithms/bsm-information-geometry.md) ← 2026-04-28 (Dean 2026: smile = manifold curvature; skew prediction within 19% zero free params; LEAPS trading implications)
  - [Deep RL for Trading](algorithms/deep-rl-trading.md) ← new 2026-05-16 (FinRL/stable-baselines3 framework; PPO/DDPG/TD3; gym environment design; honest OOS benchmarks; H204 queued — PPO vs H198 momentum baseline)
  - [Calendar Anomalies](algorithms/calendar-anomalies.md) ← updated 2026-05-18 (Schroeder 2025 SEC disclosure mechanism for Halloween effect; H206 success gates set; H205 design note updated)
  - [Regime Detection](algorithms/regime-detection.md) ← updated 2026-05-26 (QuhiQuhihi/regime_model added — Two Sigma GMM+HMM multi-asset + GGS single-asset; runnable reference for H165 full / H205-B)
  - [Factor Models & Cross-Sectional Alpha](algorithms/factor-models.md) ← new 2026-05-20
  - [WorldQuant 101 Alphas — Overlap Analysis](algorithms/alpha101-overlap.md) ← new 2026-05-22 (H215 CONFIRMED alpha101 OOS 1.321; H216 CONFIRMED-weak vol-price divergence OOS 0.823; VWAP signals blocked on free tier; 40 OHLCV-only signals buildable)
  - [Quality Factor (QMJ)](algorithms/quality-factor.md) ← new 2026-05-24 (Piotroski F-Score 9-criteria; Novy-Marx GP/Assets; AQR QMJ datasets; FMP API implementation; H221/H222 designs; BAB correlation ~0.4–0.6 = independent alpha)
  - [Market Microstructure & HFT](algorithms/market-microstructure.md) ← new 2026-05-25 (Microprice/Stoikov 2017; Avellaneda-Stoikov market making; not actionable without L2 order book data; future execution layer for intraday entries)
  - [IBS Mean-Reversion](algorithms/ibs-mean-reversion.md) ← new 2026-05-28 (Internal Bar Score strategy; PRODUCTION — XLK 20%/SMH 8%/IGV 2%; formula, per-ETF params, H062–H149 hypothesis log, arxiv:2306.12434)
  - [Technical Analysis & Chart Patterns](algorithms/technical-analysis-patterns.md) ← new 2026-05-29 (H234 CONFIRMED inside-bar coiled-spring OOS 1.770 — strongest confirmed hypothesis; NR7/NR4 reference; TA-Lib vs pandas-ta-classic library guide; H233/H235 MACD+RSI+Stochastic+ROC feature pipeline; ZHAW arXiv:2208.07168 MACD 44% importance)
  - [Long/Short Equity](algorithms/long-short-equity.md) ← new 2026-06-02 (dollar-neutral L/S construction; 130/30; borrow costs ~0.75%/yr large-cap; H243 design: top/bottom quintile EW on 200-stock universe; momentum crash risk + Daniel/Moskowitz 2016; sector-neutral L/S variant; backtesting mistake table)
  - [Factor Momentum & Style Rotation](algorithms/factor-momentum-style-rotation.md) ← new 2026-06-06 (Gupta & Kelly 2019 IS Sharpe 0.84 long-short; H255 NOT CONFIRMED long-only ETF Corr=0.89 all US equity; H256 NOT CONFIRMED GEM/PACS/GEM+Sector all < SPY OOS 2015-2025; look-ahead bias trap: unlagged 12m signal inflated OOS Sharpe 3×; multi-asset extensions with bonds+commodities queued)
  - [Commodity Trend Following](algorithms/commodity-trend-following.md) ← new 2026-06-07 (H261 NOT CONFIRMED UNG MaxDD -78%; H261b CONFIRMED Top-2 OOS Sharpe 0.922 Corr(SPY)=0.218; 2022 +26.7% vs SPY -18.2%; K-1 tax flags; roll yield mechanics; IS/OOS disconnect documented; H262 multi-horizon signal queued)
  - [Merger Arbitrage & Special Situations](algorithms/merger-arbitrage-special-situations.md) ← new 2026-06-25 (H310 root cause: antitrust regime shift; deal-break mechanics; ML feature engineering; ETF vs individual deal; H331/H333 queued)
  - [Volatility Risk Premium (VRP)](algorithms/volatility-risk-premium.md) ← new 2026-06-09
  - [SPX Dispersion Trading & Variance Risk Premium](algorithms/spx-dispersion-variance.md) ← new 2026-06-19 (H309 Phase 2 design; implied correlation premium 6-18pp historically; DSPX/COR3M signals; vega-neutral construction; Polygon IV integration path; dirty dispersion z1/z2/z3 thresholds; correlation convexity risk; factor-dispersion variant via sector ETFs)
  - [Fixed Income / Bond ETF Rotation](algorithms/fixed-income-bond-rotation.md) ← new 2026-06-20 (H045 PRODUCTION 21% portfolio; 13-ETF universe SHY/HYG/IEI/TIP/IEF/TLT/BIL + 6 more; 3m+6m+12m rank ensemble; OOS Sharpe 1.351 MaxDD -6.3%; carry FAILS — ETF dividends ≠ forward carry; 2022 rate shock survived via TSMOM filter; H314/H315 queued)
  - [Value Factors (FCF Yield, COWZ, H284/H286)](algorithms/value-factors.md) ← new 2026-06-13 (FCF yield beats B/M; COWZ/SPY cross-momentum H286 CONFIRMED Corr(SPY)=0.596; FMP API; value vs momentum tension) (IV > RV 85% of time; VRP ~2-4 vol points; short-vol Sharpe ~1.0; CSP/iron condor/delta-hedged straddle mechanics; VIX contango harvesting SVXY; Volmageddon/COVID risk lessons; H266 iron condor queued; VRP + IBS synergy noted)
  - [Behavioral Finance Signals](algorithms/behavioral-finance-signals.md) ← new 2026-06-14 (52-week high anchoring George & Hwang 2004; H291 NOT CONFIRMED large-cap 2018-2025; works in small-cap/bear regimes; Return Seasonality H292 CONFIRMED OOS 0.970; Factor MAX H295 NOT CONFIRMED ETF level)
  - [Market Timing Overlays](algorithms/market-timing-overlays.md) ← new 2026-06-15 (VIX term structure H296 CONFIRMED OOS 1.116 MaxDD -18.6%; SPY 200MA; VIX level thresholds; composite signal; rate cycle overlay; production integration guide for daily vs monthly rotation systems)
  - [Cryptocurrency Trading Strategies](algorithms/crypto-trading-strategies.md) ← new 2026-06-16 (cross-sectional momentum top-30 universe Sharpe 1.51 28d lookback; BTC 50d MA Sharpe 1.9 vs B&H 1.3; funding rate carry 6.45 full-sample but declining; Monday effect +0.51%; halving cycle positioning; ccxt/pycoingecko implementation; H302/H303 queued; max 5% portfolio allocation)
  - [Multi-Agent LLM Trading](algorithms/multi-agent-llm-trading.md) ← merged 2026-06-21 (taxonomy LLM-as-signal vs decision-maker; TradingAgents 84.9k★; HedgeAgents; Expert Investment Teams; Agent Market Arena; MadEvolve evolutionary; coordination patterns + CBS cost metric; NautilusTrader; reproducibility crisis 0/19 fully reproducible; H274 PEAD upgrade; H318 meta-learner; Self-Driving Portfolio Ang/BlackRock)
- [**Shared Evaluation Checklist**](shared-eval-checklist.md) ← new 2026-06-09 (7-point standard agreed by George + Ernesto: look-ahead guard, NLP timestamp, cost model, soft OOS gate, regime coverage, survivorship bias, after-tax flag)
- [Tools](tools/) — open-source libraries (Qlib, Backtrader, Vectorbt, etc.)
  - [Qlib Deep Dive](tools/qlib.md) ← expanded 2026-04-28 (architecture, model zoo, benchmarks, RD-Agent)
  - [Backtrader vs Vectorbt](tools/backtrader-vs-vectorbt.md) ← expanded 2026-04-29 (H116 rotation in Vectorbt, `Portfolio.from_orders` multi-asset pattern)
  - [Kraken CLI](tools/kraken-cli.md) ← expanded 2026-05-01 (all 50 agent skills, MCP service groups, full command reference)
  - [NLP & Alternative Data](tools/nlp-alternative-data.md) ← updated 2026-06-17 (BloombergGPT; LLM annotators; LLM forecasting regime-dependence arXiv:2605.05211 — validates H163/H174 fixed-threshold; 8-K language drift arXiv:2510.03195 — quarterly WR monitoring needed)
  - [Quant Firm Open Source Repos](tools/quant-firm-repos.md) ← updated 2026-06-21 (22 repos from Two Sigma, Man Group, Jane Street, D.E. Shaw, HRT, Optiver, WorldQuant; ArcticDB + dtale + WorldQuant 101 alphas flagged as high-priority; StockSharp/AlgoTrading: 1,000+ C#/Python strategy examples — reference for signal logic)
  - [awesome-quant-ai](tools/awesome-quant-ai.md) ← new 2026-06-21 (curated AI/ML quant resources; LLM agents, TS foundation models Chronos/TimesFM/Moirai, diffusion synthetic data, DeFi; strategy taxonomy + paradigms comparison; cross-refs H279–H281 staged)
  - [xang1234/stock-screener](tools/stock-screener.md) ← new 2026-05-27 (self-hosted multi-market screener: 10 markets, Minervini/CANSLIM/Setup Engine methodologies, 197 IBD industry groups, market breadth, AI chatbot, MCP integration; Docker + FastAPI + React)
  - [Machine Learning for Trading](tools/ml-for-trading.md) ← updated 2026-06-09 (FinAgent arXiv:2402.18485 structured pipeline agent; Alpha-GPT arXiv:2308.00016 human-AI factor mining loop; LLM ideation vs execution gap arXiv:2409.04109)
  - [QuantMind](tools/quant-mind.md) ← new 2026-06-10 (LLMQuant arXiv paper ingestion framework; NeurIPS 2025; paper_flow API; dream cycle integration candidate; ~$0.09/night for 30 papers; memory layer in development)
  - [Multi-Agent LLM Trading](algorithms/multi-agent-llm-trading.md) ← merged 2026-06-21 (TradingAgents 84.9k★; HedgeAgents; Expert Investment Teams; Agent Market Arena; MadEvolve evolutionary; NautilusTrader 23.4k★ Rust; reliability taxonomy CBS metric; reproducibility crisis 0/19 fully reproducible; H274 PEAD upgrade; H318 meta-learner; Self-Driving Portfolio Ang/BlackRock) [formerly also at tools/multi-agent-llm-trading.md — merged]
  - [Time-Series Foundation Models](algorithms/ts-foundation-models.md) ← new 2026-06-21 (Chronos-2 #1 GIFT-Eval; TimesFM 2.5 16k context + quantile head; Moirai any-variate ICML oral; FinTSB benchmark 15-25% over ARIMA; TS-RAG +6.51% via retrieval; financial verdict: feature engineering use case, not standalone signal; H318/H320+ integration patterns)
  - [qf-lib](tools/qf-lib.md) ← new 2026-06-24 (quarkfin/qf-lib 943★; event-driven Python backtester; broker + data vendor integrations; Crypto/Stocks/Futures; actively maintained 2026; alternative to backtrader with better data integration layer)
  - [RustQuant](tools/rust-quant.md) ← new 2026-06-24 (avhz/RustQuant 1773★; Rust quantitative finance library; options pricing, stochastic processes, ML; QuantLib-comparable but Rust-native; useful for fast options Greeks computation in hybrid Python/Rust workflows)
  - [whchien/ai-trader](tools/whchien-ai-trader.md) ← new 2026-06-24 (744★; Backtrader-powered backtesting + MCP server; `pip install ai-trader`; 20+ strategies; YAML config; US/TW/crypto/forex; MCP lets Claude run backtests via natural language; NOT the same as HKUDS/AI-Trader social platform)
  - [rohonchain — Polymarket Arbitrage Math](tools/rohonchain-polymarket.md) ← new 2026-06-24 (Roan @RohOnChain; Polymarket CLOB arb; Bregman projections + Frank-Wolfe + Kelly sizing; $40M extracted by top bots; low relevance to equity pipeline — different asset class)
  - [AI-Trader](tools/ai-trader.md) ← new 2026-06-11 (HKUDS agent-native social trading platform; signal publishing, copy-trading, collective intelligence; companion to Vibe-Trading; Polymarket paper trading live; MIT self-hostable; register George via one-message SKILL.md integration)
  - [ContestTrade](tools/contesttrade.md) ← new 2026-06-11 (FinStep-AI multi-agent trading via internal contest mechanism; arXiv:2508.00554; dual-stage: Data Team → factor contest → Research Team → proposal contest → allocation; event-driven stock selection; US market support in V2.0; Apache 2.0)
  - [QuantMuse](tools/quantmuse.md) ← new 2026-06-11 (comprehensive quant trading framework; FactorCalculator/FactorScreener API; BacktestEngine; LLM/ML integration; C++ execution backend; 8+ built-in strategies; Yahoo Finance free by default; MIT)
  - [LEAN / QuantConnect](tools/lean-quantconnect.md) ← updated 2026-05-15 (Alpaca live trading bridge added — brokerage config, CLI, Phase 3→4 gate; walk-forward optimization section; H007 pending Docker approval)
  - [OpenAlgo](tools/openalgo.md) ← 2026-04-25 (India-only for now; watch for Alpaca/Kraken support in 2026)
  - [Portfolio Optimization](tools/portfolio-optimization.md) ← new 2026-05-16 (PyPortfolioOpt v1.6.0, Riskfolio-Lib v7.2.1, skfolio v0.20.1; HRP, risk parity, NCO, walk-forward CV; strategy blending code for H026+BAB+MOM+TOM)
  - [Awesome Finance MCP](tools/awesome-finance-mcp.md) ← new 2026-06-18 (curated finance MCP servers; HIGH: install Alpaca MCP + FMP MCP; already live: Massive MCP; medium: CCXT/QuantConnect/TradingView/Alpha Vantage MCPs)
- [Data Sources](data-sources/) — market data, fundamentals, alt data
  - [Alpaca Markets — Complete Reference](data-sources/alpaca.md) ← new 2026-05-12 (full SDK reference: order types, TIF, WebSocket streams, PDT/IDTBP update, Phase 3→4 checklist)
  - [Alpaca Automation Guide](data-sources/alpaca-automation.md) ← new 2026-04-27 (Phase 3 foundation)
  - [Polygon.io](data-sources/polygon.md) ← expanded 2026-04-28 (API endpoints, WebSocket, pricing, vs Alpaca)
  - [Free / Low-Cost Sources](data-sources/free-data.md) ← expanded 2026-04-28 (Tiingo, EDGAR, Finnhub, FRED, yfinance status)
  - [Crypto Data Sources](data-sources/crypto-data-sources.md) ← new 2026-06-08 (yfinance crypto reliability + SOL gap; CoinGecko pycoingecko; ccxt unified 107-exchange API; Binance public REST; Kraken asset codes; migration path for H264b)
  - [Sector & Industry Classification](data-sources/sector-classification.md) ← new 2026-05-08 (GICS/SIC sources for H181; SEC EDGAR SIC, GitHub S&P 500 CSV, yfinance caveats, practical build_sector_cache() for 100-500 stocks)
  - [Options Data Sources](data-sources/options-data.md) ← 2026-05-01 (ThetaData/ORATS/FlashAlpha pricing; Alpaca indicative feed; vollib/py_vollib/QuantLib; IV surface + SVI fitting; free EOD options data on GitHub)
  - [Earnings Calendar & Corporate Events](data-sources/earnings-events.md) ← new 2026-05-23 (FMP/Finnhub/yfinance/API Ninjas free tier APIs; SEC EDGAR XBRL EPS extraction; EdgarTools; EPS surprise formulas; PEAD hybrid stack upgrade path for pead_overnight.py; earnings transcript sources for H174)
  - [SEC EDGAR XBRL Fundamentals](data-sources/edgar-fundamentals.md) ← new 2026-05-25 (CompanyFacts API 2009–present, 15yr history free; us-gaap tag reference for Piotroski/quality; Python builder for H222 full IS/OOS; rate limits; comparison vs FMP/yfinance)
  - [Alternative Data Sources](data-sources/alternative-data.md) ← new 2026-06-12 (Tier 0 keys in env: NewsAPI+Finnhub+AV; Tier 1 free: ApeWisdom Reddit, congressional S3, pytrends, Wikipedia; Tier 2 paid: Quiver $30/mo; signal taxonomy; H279/PEAD integration patterns; data quality caveats)
- [Prediction Markets](prediction-markets/) — Kalshi, Polymarket, etc.
  - [Kalshi](prediction-markets/kalshi.md) ← expanded 2026-04-29 (full auth/API/WebSocket, RSA signing, CPI nowcasting implementation, fee modeling, rate limits, Timeless perps)
  - [Algorithmic Strategies](prediction-markets/algorithmic-strategies.md) ← updated 2026-05-13 (PolyBench arXiv:2604.14199 — LLMs near-random on binary markets; edge only on economic data + structured context)
  - [Economic Nowcasting Playbook](prediction-markets/nowcasting-playbook.md) ← new 2026-05-27 (per-release operational playbook: CPI/NFP/FOMC/PCE/GDP; Cleveland Fed + Atlanta GDPNow + NY Fed nowcast sources; shelter lag model; ADP→NFP pipeline; Brier score tracking; H185 implementation path)
  - [Other Platforms](prediction-markets/other-platforms.md) ← expanded 2026-05-02 (IBKR ForecastTrader full API, Kalshi Timeless mechanics, emerging platforms)
  - [Polymarket](prediction-markets/polymarket.md) ← 2026-04-29 (full CLOB API, Ethereum auth, order placement, WebSocket streaming, fee comparison vs Kalshi, cross-platform arb scanner)
  - [AI Model Benchmarks](prediction-markets/ai-model-benchmarks.md) ← updated 2026-06-28 (Prediction Arena arXiv:2604.07355 — 6 models with real capital; all lost money Kalshi; grok-4-20 only profitable +10.9%; + PolyBench arXiv:2604.14199 — 7 LLMs negative expected return, raw LLM calibration near-random; + PolySwarm arXiv:2604.03888 — 50-agent swarm + KL divergence aggregation + latency arb + quarter-Kelly; + PredictionMarketBench arXiv:2602.00133 — Kalshi LOB replay backtester GitHub:Oddpool/PredictionMarketBench; fee management key: post-only +1.67% vs LLM taker -2.77%)
  - [Superforecasting Methods](prediction-markets/superforecasting-methods.md) ← new 2026-06-11 (Ten Commandments, reference class forecasting, Bayesian updating, calibration layer for LLMs, domain bias table arXiv:2602.19520, LLM benchmark landscape arXiv:2512.16030/2507.04562/2506.01578, H185 gates)
  - [Automated Trading Pipeline](prediction-markets/automated-pipeline.md) ← new 2026-06-26 (event-driven loop; ryanfrigo/OctagonAI reference repos; APScheduler vs NanoClaw schedule_task; SQLite schema; position sizing + drawdown halt; CPI nowcast→order pipeline; graduation gates; 5 known failure modes; integration checklist)
- [Backtesting](backtesting/) — setup, results, methodology
  - [Design Principles](backtesting/design-principles.md) ← expanded 2026-05-05 (IS/OOS framework, bias taxonomy, confirmation criteria, deflated Sharpe, López de Prado)
  - [Walk-Forward & CPCV](backtesting/walk-forward-cpcv.md) ← new 2026-05-07 (WFO variants, CPCV algorithm, purging/embargoing, DSR formulas, Python libs: timeseriescv/skfolio/mlfinlab, when to use what)
  - [Transaction Cost Modeling](backtesting/transaction-costs.md) ← new 2026-05-09 (spread/impact/borrow models, square-root MI, vectorbt/backtrader defaults, per-strategy calibration table)
  - [Multiple Testing & Statistical Significance](backtesting/multiple-testing.md) ← new 2026-05-26 (DSR, PBO, block bootstrap, White Reality Check; BH FDR correction; Harvey-Liu-Zhu t-ratio thresholds; pipeline application table)
  - [Signal Half-Life & Alpha Decay Measurement](backtesting/signal-halflife.md) ← new 2026-05-31 (AR(1)/regression half-life formula, rolling IC decay diagnostics, hyperbolic vs exponential fits, AI-driven compression from 58→18 months, IS window guidance, per-strategy decay table)
  - [Survivorship Bias & Universe Construction](backtesting/survivorship-bias.md) ← new 2026-06-03 (bias types + magnitude: Ranse 2025 +4.94pp returns/+0.097 Sharpe; Shumway 1997 delistings = 40% of momentum profits; fja05680/sp500 free repo ★854; Norgate Platinum for production; PIT universe builder; H241–H246 bias impact assessment; common mistakes table)
  - [Regime Detection Signals — Practical Data Guide](backtesting/regime-detection-signals.md) ← new 2026-06-04 (SPY 200MA + VIX FRED + T10Y2Y fetch code; four-state composite H249-style; continuous score Xiong 2026; FRED release-lag rules; filtered vs smoothed HMM probabilities; H165a/H249/H205 confirmed results table)
  - [Strategy Blending & Correlation Management](backtesting/strategy-blending-correlation.md) ← new 2026-06-23 (H026/H041a/H045 correlation matrix OOS; IC-weighted blending code; meta-learning failure analysis from H318; production blend rationale 40/30/30 static near-optimal; corr gate for new strategy admission; IBS daily sleeve is source of Sharpe 2.5→4.16 jump; next addition candidates: H309 dispersion + H174 PEAD)
  - [Options Backtesting Methodology](backtesting/options-backtesting-methodology.md) ← new 2026-06-24 (4 data tiers: synthetic BSM/VIX, LEAN free, ThetaData $80/mo, ORATS $99/mo; py_vollib 413★ for Greeks; Greek P&L decomposition Δ+Γ+Θ+V; VRP free synthetic signal; iron condor + dispersion methodology; 8-item common mistakes table; H266/H309/H329 integration paths)
- [Paper Trading](paper-trading/) — Alpaca results log
  - [H149 Alpaca ETF Rotation](paper-trading/h122-alpaca.md) ← active (100% H026, $102k paper)
  - [PEAD-NLP Alpaca Deployment](paper-trading/pead-nlp-alpaca.md) ← new 2026-05-06 (H163/H174 live pipeline: gap detection, 8-K scoring, OPG orders)
  - [H181 Industry Reversal Alpaca](paper-trading/h181-alpaca.md) ← active (H181 live deployment log)
  - [Live Graduation Criteria & Performance Attribution](paper-trading/live-graduation-criteria.md) ← new 2026-05-30 (SPRT test for strategy validation, minimum trade counts, regime coverage gates, paper→live execution attribution, Alpaca migration steps)
  - [Tax & After-Tax Return Modeling](paper-trading/tax-and-after-tax-returns.md) ← new 2026-06-05 (STCG/LTCG rates for IL, wash sale rule for algo trading, HIFO lot selection, after-tax Sharpe formula, expected ~40% tax drag on STCG monthly-rebalanced strategies, IRS Form 8949 reporting)
  - [Execution Quality & Slippage Analysis](paper-trading/execution-quality.md) ← new 2026-06-11 (IS/VWAP benchmarks, Alpaca paper fill mechanics, per-strategy slippage budgets H026/H181/PEAD, paper→live degradation estimates, graduation gate thresholds)
  - [Risk Controls & Live Trading Monitoring](paper-trading/risk-controls-and-monitoring.md) ← new 2026-06-17 (3-tier circuit breakers; kill switch via Alpaca close_all_positions; ATR position sizing; portfolio heat monitoring; correlation guard for PEAD entries; alert checklist; per-strategy risk table)
  - [Multi-Strategy Performance Attribution & Drawdown Analysis](paper-trading/performance-attribution.md) ← new 2026-06-27 (Brinson sleeve attribution; regime-conditional Sharpe table; underwater curve analysis; drawdown action thresholds −8/−15/−25%; SPRT pause criteria; quantstats vs riskfolio-lib landscape; weekly/monthly monitoring checklist)
- [Sources](sources/) — ingested papers and working papers
  - [The Alchemy of Multibagger Stocks](sources/multibagger-yartseva-2025.md) ← new 2026-06-12 (Yartseva 2025; FCF/P = #1 factor; EPS growth NOT sig; small-cap +37.7% vs large +9.7%; asset_growth>EBITDA_growth −22.8pp; near-12m-low entry signal; rate-hike −8-12pp; H285 proposed)
- [Research Log](research-log/) — nightly research summaries
  - [2026-06-26](research-log/2026-06-26.md) — wiki expansion: automated-pipeline.md new (Kalshi live trading infrastructure; APScheduler; SQLite schema; position sizing; CPI nowcast→order pipeline; 5 failure modes; graduation gates); dream cycle: 8 papers reviewed, 2 staged (H334 LLM lead-lag Kalshi arXiv:2602.07048; multi-agent reliability wiki update arXiv:2603.27539 + Profit Mirage arXiv:2510.07920)
  - [2026-06-25](research-log/2026-06-25.md) — wiki expansion: merger-arbitrage-special-situations.md new (H310 root cause documented; deal mechanics, ML features, regulatory regimes; H331/H332/H333 staged); dream cycle: 18 papers reviewed, 4 staged (multi-modal PEAD H331, QuantaAlpha evolutionary H332, regime-aware agent comms wiki, merger arb NLP H333)
  - [2026-06-23](research-log/2026-06-23.md) — wiki expansion: strategy-blending-correlation.md new (H026/H041a/H045 OOS correlation matrix; IC-weighted blending; meta-learning failure analysis H318; production blend 40/30/30 static near-optimal; IBS orthogonality = source of 2.50→4.16 Sharpe jump; next additions: H309 dispersion, H174 PEAD); H318 NOT CONFIRMED logged; dream cycle scan: arXiv/GitHub 5-angle scan
  - [2026-06-20](research-log/2026-06-20.md) — wiki expansion: fixed-income-bond-rotation.md new (H045 PRODUCTION framework; 3m+6m+12m rank ensemble; carry FAILS — ETF dividends ≠ forward carry; SHY dominates OOS 72% of months; H314/H315 queued); dream cycle: H316 LLM pair selection (Moira arXiv:2605.01954), H317 multi-modal PEAD (arXiv:2605.25894), H319 semantic network, H320 crash filter; Self-Driving Portfolio + reproducibility audit wiki updates
  - [2026-06-19](research-log/2026-06-19.md) — wiki expansion: spx-dispersion-variance.md new (H309 PARTIAL; implied correlation premium 6-18pp; DSPX/COR3M signals; vega-neutral construction; Polygon IV integration path; correlation convexity risk)
  - [2026-06-17](research-log/2026-06-17.md) — wiki expansion: risk-controls-and-monitoring.md new (3-tier circuit breakers; ATR sizing; kill switch; correlation guard for PEAD entries); multi-agent-llm-trading.md (algorithms/ view) expanded with reproducibility audit + Self Driving Portfolio
  - [2026-06-16](research-log/2026-06-16.md) — wiki expansion: crypto-trading-strategies.md new (cross-sectional momentum Sharpe 1.51, BTC MA Sharpe 1.9, funding rate carry Sharpe 6.45→negative 2025, Monday effect, halving cycle, ccxt/pycoingecko implementation; H302/H303 queued); dream cycle: arXiv/GitHub scan Phase 2
  - [2026-06-13](research-log/2026-06-13.md) — wiki expansion: value-factors.md new (FCF yield, COWZ, H284/H285/H286 synthesis, value vs momentum tension); dream cycle: H293 press release structure PEAD (arXiv:2509.24254), H294 behavioral multi-factor MLP (arXiv:2508.14656), time-series foundation models wiki (Chronos/TimesFM/Lag-Llama)
  - [2026-06-11](research-log/2026-06-11.md) — wiki expansion: execution-quality.md new (IS benchmarks, paper fill mechanics, slippage budgets, graduation gates); dream cycle: H279 LLM momentum filter arXiv:2510.26228, H280 MarketSenseAI arXiv:2604.17327, H281 macro-LLM ETF arXiv:2606.08283, hyperbolic alpha decay wiki arXiv:2512.11913
  - [2026-06-08](research-log/2026-06-08.md) — wiki expansion: crypto-data-sources.md new (yfinance fragility, ccxt/CoinGecko migration path); dream cycle: H264b trailing-stop crypto, H265 drift-regime factor (arXiv:2511.12490 OOS Sharpe >13 — skeptical replication candidate), QuantStats wiki staged
  - [2026-06-07](research-log/2026-06-07.md) — wiki expansion: commodity-trend-following.md new (H261b Corr(SPY)=0.218 lowest of any confirmed H; K-1 tax flags; dream cycle: H262 Bayesian short+long CTA; AI alpha decay half-life 12m update; FinCall-Surprise multi-modal PEAD assessment)
  - [2026-06-06](research-log/2026-06-06.md) — wiki expansion: factor-momentum-style-rotation.md new (Gupta & Kelly 2019 Sharpe 0.84; H255/H256 failure analysis; look-ahead bias 3× inflation; multi-asset extensions); indexed regime-detection-signals.md; dream cycle: H257 multi-asset composite momentum, H258 text-to-alpha LLM disclosure, H259 FactorMAD debate, H260 PEAD 12q ML
  - [2026-05-31](research-log/2026-05-31.md) — wiki expansion: signal-halflife.md new (AR(1) half-life formula, rolling IC diagnostics, hyperbolic decay, AI compression 58→18 months, IS window table); dream cycle: H238 BlindTrade LLM portfolio, H239 LLM time-capsule factor, LLM reality-check wiki update, PEAD fine-grained decomposition staged
  - [2026-05-30](research-log/2026-05-30-live-graduation.md) — wiki expansion: live-graduation-criteria.md new; dream cycle scan: drift-regime reversal H237, GT-Score backtesting objective, AlphaAgent LLM mining staged
  - [2026-05-29](research-log/2026-05-29.md) — wiki expansion: technical-analysis-patterns.md new (H234 coiled-spring OOS 1.770 strongest confirmed; TA-Lib vs pandas-ta-classic library guide; NR7/NR4 reference; MACD/RSI/Stochastic/ROC feature pipeline for H233/H235; ZHAW arXiv:2208.07168); dream cycle scan complete
  - [2026-05-28](research-log/2026-05-28.md) — wiki expansion: ibs-mean-reversion.md new (IBS formula, per-ETF production params XLK/SMH/IGV, H062–H149 log, arxiv:2306.12434); dream cycle scan complete
  - [2026-05-27](research-log/2026-05-27.md) — wiki expansion: nowcasting-playbook.md new (CPI/NFP/FOMC/PCE/GDP per-release workflow, Cleveland Fed + GDPNow sources, Brier tracking, H185 path); xang1234/stock-screener noted; dream cycle scan complete
  - [2026-05-26](research-log/2026-05-26.md) — wiki expansion: multiple-testing.md new; QuhiQuhihi/regime_model noted in regime-detection.md; H217–H226 logged (backlog); H228 DESIGNED+RUN+CONFIRMED (blend alpha101+reversal OOS 1.572); dream cycle complete
  - [2026-05-25](research-log/2026-05-25.md) — wiki expansion: edgar-fundamentals.md new (EDGAR XBRL API, 15yr history, H222 unblock path); dream cycle: H223 multi-window momentum, H224 AlphaCrafter factor ensemble, H225 GPT-4o PEAD upgrade staged
  - [2026-05-24](research-log/2026-05-24.md) — H217 CONFIRMED (median alpha101 OOS 1.559); H218/H219 NOT CONFIRMED; H220 CONFIRMED (ETF TSMOM OOS 0.961); H221 NOT CONFIRMED (drift regime too restrictive for 30-stock universe, avg 3.6/30 eligible); H222 CONFIRMED-WEAK (quality factor F-Score 2.329/GP-Assets 2.308 OOS but bullish test period only); wiki: quality-factor.md new; dream cycle: H221/H222/H223 staged
  - [2026-05-23](research-log/2026-05-23.md) — H215 CONFIRMED (alpha101 OOS Sharpe 1.321); H216 CONFIRMED-weak (vol-price divergence OOS 0.823, below SPY); blend H215+H198 OOS Sharpe 1.397; wiki: earnings-events.md new; dream cycle: SUE.txt + BlindTrade + factor momentum multi-window staged
  - [2026-05-21](research-log/2026-05-21.md) — H205/H206/H207/H208 NOT CONFIRMED (full calendar family closed); H202-XL NOT CONFIRMED (OOS 1.106)
  - [2026-05-20](research-log/2026-05-20.md) — wiki expansion: Factor Models/Fama-French page (new, H202-XL prep); dream cycle scan: 5 angles across arXiv + GitHub
  - [2026-05-19](research-log/2026-05-19.md) — wiki expansion: regime-detection.md; H206 NOT CONFIRMED (Halloween Effect); H204 NOT CONFIRMED (Deep RL PPO); surprise: summer TOM (Sharpe 0.699) > Halloween TOM (Sharpe 0.435)
  - [2026-05-18](research-log/2026-05-18.md) — wiki expansion + arXiv scan: H205 design finalized (4 staged proposals); Schroeder 2025 confirms structural Halloween mechanism for H206; 3 convergent papers support H202-XL large-universe gradient boosting; run_h205.py backtest queued for tonight
  - [2026-05-17](research-log/2026-05-17.md) — H202 NOT CONFIRMED (bias mask trivial on 30 stocks; XGBoost +0.104 Sharpe but below threshold); H203 NOT CONFIRMED (HRP over-indexes on TOM 74%; MaxDD -7.1% but Sharpe 1.066); H205 queued (TOM overlay on BAB)
  - [2026-05-15](research-log/2026-05-15.md) — H200 NOT CONFIRMED (graphical pairs, 0/15 cointegrated); H201 CONFIRMED (TOM, OOS Sharpe 0.740); pairs family EXHAUSTED; H202 queued
  - [2026-05-14](research-log/2026-05-14.md) — H198 CONFIRMED (6-1m stock momentum, OOS Sharpe 1.174); H199 NOT CONFIRMED (sector-neutral hurts momentum)
  - [2026-05-13](research-log/2026-05-13.md) — H193 NOT CONFIRMED (BAB+reversal blend); H196 NOT CONFIRMED (STORM scale); wiki: low-volatility.md closed
  - [2026-05-12](research-log/2026-05-12.md) — H192 CONFIRMED (BAB: sector-neutral H192-D OOS Sharpe 1.367); Alpaca.md full rewrite; H193 queued

## Key decisions log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-24 | Start with research phase, paper trading before real money | Prudent — prove before risking capital |
| 2026-04-24 | Focus: equities and options first | Kevin's priority |
| 2026-04-24 | Data: Polygon.io free tier + Alpaca free tier | Both accounts exist; keys in OneCLI |
| 2026-04-24 | Paper trading via Alpaca | Kevin has existing paper account |
| 2026-04-24 | Backtesting must model macro regimes + after-tax returns | Kevin's requirement — real-world accuracy |
| 2026-04-26 | yfinance as data fallback (Alpaca SDK not installable in container) | Alpaca module unavailable; yfinance works for EOD |
| 2026-04-26 | BIL preferred over TLT as risk-off refuge in dual momentum (H006 result) | TLT has duration risk; BIL immune to rate-hike bears |
| 2026-04-27 | H020 (5-asset rotation) supersedes H016 as primary ETF strategy | Sharpe 1.23 vs 0.78; 6.7% OOS degradation (vs 50% typical); generalizes across universes |
| 2026-04-27 | H018 blend (H020 + H009, 50/50) is the target portfolio for Phase 3 | Sharpe 1.255, MaxDD -18.4%, corr=0.31 — diversification benefit confirmed |
| 2026-04-27 | Use alpaca-py (not alpaca-trade-api) for all Alpaca automation | legacy SDK deprecated Dec 2022 |

## API access

| Service | Env var | Status |
|---------|---------|--------|
| Polygon.io | `$POLYGON_API_KEY` | ✓ Tested — free tier, EOD bars |
| FRED | `$FRED_API_KEY` | ✓ Tested — macro data (Fed funds, GDP, etc.) |
| Alpha Vantage | `$ALPHA_VANTAGE_API_KEY` | ✓ Present |
| Financial Modeling Prep | `$FMP_API_KEY` | ✓ Present — fundamentals |
| NewsAPI | `$NEWSAPI_KEY` | ✓ Present — sentiment/news |
| EDGAR | `$EDGAR_KEY` | ✓ Present |
| OpenAI | `$OPENAI_API_KEY` | ✓ Present — ML/NLP tasks |
| Alpaca (paper) | `$ALPACA_API_KEY` + `$ALPACA_SECRET` | ✓ Active — $102k portfolio, $204k buying power |
| GitHub | `$GITHUB_TOKEN` | ✓ Active |
| Massive.com | `$MASSIVE_KEY` | ✓ Active — delayed prices, options contract reference; Polygon backend |
