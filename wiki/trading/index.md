---
updated: 2026-06-11 (superforecasting-methods.md new — Ten Commandments, domain bias table, calibration layer, LLM benchmarks, H185 integration; ai-model-benchmarks.md indexed; research-log/2026-06-11.md updated)
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
  - [Pairs Trading / Stat Arb](algorithms/pairs-trading.md) ← updated 2026-05-15 (ETF pairs EXHAUSTED H152-H160; H200 QUEUED — graphical matching stock-level pairs, arXiv:2403.07998, Sharpe 1.23 on S&P 500 2017–2023)
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
  - [Volatility Risk Premium (VRP)](algorithms/volatility-risk-premium.md) ← new 2026-06-09 (IV > RV 85% of time; VRP ~2-4 vol points; short-vol Sharpe ~1.0; CSP/iron condor/delta-hedged straddle mechanics; VIX contango harvesting SVXY; Volmageddon/COVID risk lessons; H266 iron condor queued; VRP + IBS synergy noted)
- [**Shared Evaluation Checklist**](shared-eval-checklist.md) ← new 2026-06-09 (7-point standard agreed by George + Ernesto: look-ahead guard, NLP timestamp, cost model, soft OOS gate, regime coverage, survivorship bias, after-tax flag)
- [Tools](tools/) — open-source libraries (Qlib, Backtrader, Vectorbt, etc.)
  - [Qlib Deep Dive](tools/qlib.md) ← expanded 2026-04-28 (architecture, model zoo, benchmarks, RD-Agent)
  - [Backtrader vs Vectorbt](tools/backtrader-vs-vectorbt.md) ← expanded 2026-04-29 (H116 rotation in Vectorbt, `Portfolio.from_orders` multi-asset pattern)
  - [Kraken CLI](tools/kraken-cli.md) ← expanded 2026-05-01 (all 50 agent skills, MCP service groups, full command reference)
  - [NLP & Alternative Data](tools/nlp-alternative-data.md) ← updated 2026-06-09 (BloombergGPT arXiv:2303.17564 — domain gap vs general models; LLM annotators arXiv:2403.18152 — right role in quant stack)
  - [Quant Firm Open Source Repos](tools/quant-firm-repos.md) ← new 2026-05-22 (22 repos from Two Sigma, Man Group, Jane Street, D.E. Shaw, HRT, Optiver, WorldQuant; ArcticDB + dtale + WorldQuant 101 alphas flagged as high-priority)
  - [xang1234/stock-screener](tools/stock-screener.md) ← new 2026-05-27 (self-hosted multi-market screener: 10 markets, Minervini/CANSLIM/Setup Engine methodologies, 197 IBD industry groups, market breadth, AI chatbot, MCP integration; Docker + FastAPI + React)
  - [Machine Learning for Trading](tools/ml-for-trading.md) ← updated 2026-06-09 (FinAgent arXiv:2402.18485 structured pipeline agent; Alpha-GPT arXiv:2308.00016 human-AI factor mining loop; LLM ideation vs execution gap arXiv:2409.04109)
  - [QuantMind](tools/quant-mind.md) ← new 2026-06-10 (LLMQuant arXiv paper ingestion framework; NeurIPS 2025; paper_flow API; dream cycle integration candidate; ~$0.09/night for 30 papers; memory layer in development)
  - [Multi-Agent LLM Trading Systems](tools/multi-agent-llm-trading.md) ← new 2026-06-10 (TradingAgents arXiv:2412.20138 84.9k★; HedgeAgents arXiv:2502.13165 Sharpe 2.41 caveated; Expert Investment Teams arXiv:2602.23330 fine-grained decomposition; Agent Market Arena arXiv:2510.11695 framework > LLM backbone; reliability taxonomy arXiv:2603.27539 CBS metric; NautilusTrader 23.4k★ Rust engine; H274 multi-agent PEAD upgrade proposal)
  - [AI-Trader](tools/ai-trader.md) ← new 2026-06-11 (HKUDS agent-native social trading platform; signal publishing, copy-trading, collective intelligence; companion to Vibe-Trading; Polymarket paper trading live; MIT self-hostable; register George via one-message SKILL.md integration)
  - [ContestTrade](tools/contesttrade.md) ← new 2026-06-11 (FinStep-AI multi-agent trading via internal contest mechanism; arXiv:2508.00554; dual-stage: Data Team → factor contest → Research Team → proposal contest → allocation; event-driven stock selection; US market support in V2.0; Apache 2.0)
  - [QuantMuse](tools/quantmuse.md) ← new 2026-06-11 (comprehensive quant trading framework; FactorCalculator/FactorScreener API; BacktestEngine; LLM/ML integration; C++ execution backend; 8+ built-in strategies; Yahoo Finance free by default; MIT)
  - [LEAN / QuantConnect](tools/lean-quantconnect.md) ← updated 2026-05-15 (Alpaca live trading bridge added — brokerage config, CLI, Phase 3→4 gate; walk-forward optimization section; H007 pending Docker approval)
  - [OpenAlgo](tools/openalgo.md) ← 2026-04-25 (India-only for now; watch for Alpaca/Kraken support in 2026)
  - [Portfolio Optimization](tools/portfolio-optimization.md) ← new 2026-05-16 (PyPortfolioOpt v1.6.0, Riskfolio-Lib v7.2.1, skfolio v0.20.1; HRP, risk parity, NCO, walk-forward CV; strategy blending code for H026+BAB+MOM+TOM)
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
- [Prediction Markets](prediction-markets/) — Kalshi, Polymarket, etc.
  - [Kalshi](prediction-markets/kalshi.md) ← expanded 2026-04-29 (full auth/API/WebSocket, RSA signing, CPI nowcasting implementation, fee modeling, rate limits, Timeless perps)
  - [Algorithmic Strategies](prediction-markets/algorithmic-strategies.md) ← updated 2026-05-13 (PolyBench arXiv:2604.14199 — LLMs near-random on binary markets; edge only on economic data + structured context)
  - [Economic Nowcasting Playbook](prediction-markets/nowcasting-playbook.md) ← new 2026-05-27 (per-release operational playbook: CPI/NFP/FOMC/PCE/GDP; Cleveland Fed + Atlanta GDPNow + NY Fed nowcast sources; shelter lag model; ADP→NFP pipeline; Brier score tracking; H185 implementation path)
  - [Other Platforms](prediction-markets/other-platforms.md) ← expanded 2026-05-02 (IBKR ForecastTrader full API, Kalshi Timeless mechanics, emerging platforms)
  - [Polymarket](prediction-markets/polymarket.md) ← 2026-04-29 (full CLOB API, Ethereum auth, order placement, WebSocket streaming, fee comparison vs Kalshi, cross-platform arb scanner)
  - [AI Model Benchmarks](prediction-markets/ai-model-benchmarks.md) ← new 2026-05-29 (Prediction Arena arXiv:2604.07355 — 6 models with real capital; all lost money on Kalshi weather-dominated set; Polymarket better venue for AI agents; grok-4-20 only profitable prior run +10.9%)
  - [Superforecasting Methods](prediction-markets/superforecasting-methods.md) ← new 2026-06-11 (Ten Commandments, reference class forecasting, Bayesian updating, calibration layer for LLMs, domain bias table arXiv:2602.19520, LLM benchmark landscape arXiv:2512.16030/2507.04562/2506.01578, H185 gates)
- [Backtesting](backtesting/) — setup, results, methodology
  - [Design Principles](backtesting/design-principles.md) ← expanded 2026-05-05 (IS/OOS framework, bias taxonomy, confirmation criteria, deflated Sharpe, López de Prado)
  - [Walk-Forward & CPCV](backtesting/walk-forward-cpcv.md) ← new 2026-05-07 (WFO variants, CPCV algorithm, purging/embargoing, DSR formulas, Python libs: timeseriescv/skfolio/mlfinlab, when to use what)
  - [Transaction Cost Modeling](backtesting/transaction-costs.md) ← new 2026-05-09 (spread/impact/borrow models, square-root MI, vectorbt/backtrader defaults, per-strategy calibration table)
  - [Multiple Testing & Statistical Significance](backtesting/multiple-testing.md) ← new 2026-05-26 (DSR, PBO, block bootstrap, White Reality Check; BH FDR correction; Harvey-Liu-Zhu t-ratio thresholds; pipeline application table)
  - [Signal Half-Life & Alpha Decay Measurement](backtesting/signal-halflife.md) ← new 2026-05-31 (AR(1)/regression half-life formula, rolling IC decay diagnostics, hyperbolic vs exponential fits, AI-driven compression from 58→18 months, IS window guidance, per-strategy decay table)
  - [Survivorship Bias & Universe Construction](backtesting/survivorship-bias.md) ← new 2026-06-03 (bias types + magnitude: Ranse 2025 +4.94pp returns/+0.097 Sharpe; Shumway 1997 delistings = 40% of momentum profits; fja05680/sp500 free repo ★854; Norgate Platinum for production; PIT universe builder; H241–H246 bias impact assessment; common mistakes table)
  - [Regime Detection Signals — Practical Data Guide](backtesting/regime-detection-signals.md) ← new 2026-06-04 (SPY 200MA + VIX FRED + T10Y2Y fetch code; four-state composite H249-style; continuous score Xiong 2026; FRED release-lag rules; filtered vs smoothed HMM probabilities; H165a/H249/H205 confirmed results table)
- [Paper Trading](paper-trading/) — Alpaca results log
  - [H149 Alpaca ETF Rotation](paper-trading/h122-alpaca.md) ← active (100% H026, $102k paper)
  - [PEAD-NLP Alpaca Deployment](paper-trading/pead-nlp-alpaca.md) ← new 2026-05-06 (H163/H174 live pipeline: gap detection, 8-K scoring, OPG orders)
  - [H181 Industry Reversal Alpaca](paper-trading/h181-alpaca.md) ← active (H181 live deployment log)
  - [Live Graduation Criteria & Performance Attribution](paper-trading/live-graduation-criteria.md) ← new 2026-05-30 (SPRT test for strategy validation, minimum trade counts, regime coverage gates, paper→live execution attribution, Alpaca migration steps)
  - [Tax & After-Tax Return Modeling](paper-trading/tax-and-after-tax-returns.md) ← new 2026-06-05 (STCG/LTCG rates for IL, wash sale rule for algo trading, HIFO lot selection, after-tax Sharpe formula, expected ~40% tax drag on STCG monthly-rebalanced strategies, IRS Form 8949 reporting)
  - [Execution Quality & Slippage Analysis](paper-trading/execution-quality.md) ← new 2026-06-11 (IS/VWAP benchmarks, Alpaca paper fill mechanics, per-strategy slippage budgets H026/H181/PEAD, paper→live degradation estimates, graduation gate thresholds)
- [Research Log](research-log/) — nightly research summaries
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
