---
updated: 2026-05-25
sources_indexed: 2
pages: 87
---

# Wiki Index

Content catalog — updated on every ingest. Read this first when answering queries.

## How to use this index

Each entry: `[Page title](path.md) — one-line summary`

When answering a query:
1. Scan the relevant category sections here
2. Open the linked pages that look relevant
3. Synthesize; cite by page title

---

## Categories

### Trading & Prediction Markets

- [Project Index](trading/index.md) — phases, decisions, API access status
**Algorithms / Strategies**
- [Momentum Strategies](trading/algorithms/momentum-strategies.md) — H026/H149 ETF rotation production (382×, Sharpe 3.007); H198 CONFIRMED 6-1m (OOS Sharpe 1.174); H215 CONFIRMED alpha101 (OOS 1.321); H217 CONFIRMED median alpha101 (OOS 1.559); H220 CONFIRMED ETF TSMOM (OOS 0.961); H202/H218/H219 NOT CONFIRMED
- [Pairs Trading / Stat Arb](trading/algorithms/pairs-trading.md) — ETF pairs (H152–H160) ALL NOT CONFIRMED; family EXHAUSTED at daily frequency; cointegration breaks OOS for all tested pairs
- [Event-Driven Strategies](trading/algorithms/event-driven.md) — PEAD: H163 CONFIRMED (FinBERT NLP on 8-K press releases, 80.8% OOS win rate), H174 CONFIRMED (dual filter deployed), H161/H162 PARTIAL; H170 0DTE iron condor partial sim
- [Short-Term Reversal](trading/algorithms/short-term-reversal.md) — industry-adjusted reversal REV^IN; 0.53%/month globally; SSRN:6630998; H181 CONFIRMED (OOS Sharpe 1.138)
- [Low-Volatility Anomaly](trading/algorithms/low-volatility.md) — H190–H196 completed; BAB H192-D sector-neutral CONFIRMED (OOS Sharpe 1.367); Low-Vol H191-C hybrid CONFIRMED (Sharpe 1.110); STORM H195 CONFIRMED (0.963); scale test H196 NOT CONFIRMED; research closed 2026-05-13; H205 TOM-BAB overlay queued
- [Options Income Strategies](trading/algorithms/options-income-strategies.md) — iron condor, CSP/wheel, covered calls, VRP harvesting; win rates, returns, LEAN implementation notes
- [Position Sizing & Portfolio Construction](trading/algorithms/position-sizing.md) — Kelly criterion (single + multivariate), vol-targeting, cross-strategy correlation matrix (BAB/MOM/REV/PEAD/TOM), multi-strategy blending scaffold for confirmed portfolio; updated 2026-05-21
- [BSM as Flat Limit of Information Geometry (Dean 2026)](trading/algorithms/bsm-information-geometry.md) — SSRN 6630259; smile = manifold curvature; zero-free-parameter LEAPS prediction within 19%; SABR β=1 from Čencov's theorem; bifurcation at |ρ|=√(2/3)≈0.816
- [151 Trading Strategies (Kakushadze & Serur)](trading/strategies/151-trading-strategies.md) — comprehensive strategy catalog; 151+ strategies with formulas; Tier 1/2/3 implementation priority
- [Calendar Anomalies](trading/algorithms/calendar-anomalies.md) — TOM H201 CONFIRMED (OOS Sharpe 0.740); Halloween/FOMC/January/Weekend effects; H205–H208 queued; composite calendar strategy; academic debate on TOM persistence ← new 2026-05-17
- [Deep RL for Trading](trading/algorithms/deep-rl-trading.md) — FinRL/stable-baselines3 framework; PPO/DDPG/TD3; gym environment design; honest OOS benchmarks; H204 NOT CONFIRMED; DL-TSMOM benchmark VSN+LSTM (H223 design note) ← new 2026-05-16
- [Regime Detection](trading/algorithms/regime-detection.md) — VIX threshold, Markov Switching, HMM, Statistical Jump Model (arXiv:2402.05272); H165/H205-B application code; regime-conditional BAB ← new 2026-05-19
- [Factor Models & Cross-Sectional Alpha](trading/algorithms/factor-models.md) — Fama-French 3/5/6-factor (Kenneth French Library); alphalens-reloaded tearsheets; Fama-MacBeth regression; cross-sectional feature engineering for H202-XL ← new 2026-05-20
- [WorldQuant 101 Alphas — Overlap Analysis](trading/algorithms/alpha101-overlap.md) — 40 OHLCV-only signals buildable free; H215/H216 CONFIRMED; ~60 signals blocked (VWAP/intraday required) ← new 2026-05-22
- [Quality Factor (QMJ, Piotroski, GP/Assets)](trading/algorithms/quality-factor.md) — AQR QMJ; Piotroski F-Score 9-criteria; Novy-Marx GP/Assets; FMP API implementation; H221/H222 designs; corr(quality, BAB) ~0.4–0.6 = independent alpha ← new 2026-05-24

**Tools**
- [Qlib](trading/tools/qlib.md) — Microsoft's AI quant platform; ML strategies, production-grade
- [Backtrader vs Vectorbt](trading/tools/backtrader-vs-vectorbt.md) — framework comparison; H116 ETF rotation implementations for both; Vectorbt v1.0 (2026-04-22)
- [LEAN / QuantConnect](trading/tools/lean-quantconnect.md) — open-source backtesting + live trading engine; best for options; requires Docker (pending install)
- [Kraken CLI](trading/tools/kraken-cli.md) — official Kraken AI-native CLI; 151 MCP tools, paper trading built-in, crypto/forex/xStocks
- [NLP & Alternative Data](trading/tools/nlp-alternative-data.md) — FinBERT, financial NLP models, EDGAR 8-K pipeline, AlphaVantage transcripts; H163/H168/H171 tooling
- [Machine Learning for Trading](trading/tools/ml-for-trading.md) — LightGBM/XGBoost cross-sectional prediction, ModernFinBERT (H176 upgrade), Alphalens-Reloaded IC/ICIR, TA-Lib, skfolio CPCV, mlfinlab license warning
- [OpenAlgo](trading/tools/openalgo.md) — open-source algo trading platform; India-only now, US broker support on 2026 roadmap
- [LiveKit](trading/tools/livekit.md) — open-source real-time voice/video/data framework for AI agents; WebRTC media server + agent SDK + cloud hosting; relevant for voice trading interface and agent-to-agent comms
- [Portfolio Optimization Libraries](trading/tools/portfolio-optimization.md) — PyPortfolioOpt v1.6.0, Riskfolio-Lib v7.2.1, skfolio v0.20.1; HRP, risk parity, NCO, walk-forward CV; strategy blending code for H026+BAB+MOM+TOM ← new 2026-05-16
- [Investing Algorithm Framework (IAF)](trading/tools/investing-algorithm-framework.md) — define→backtest→deploy; dual vector+event-driven modes; tiered SQLite storage for 10k+ runs; HTML dashboard; Monte Carlo testing; CCXT live (crypto); Alpaca needs custom executor ← new 2026-05-20
- [NextTrade](trading/tools/nexttrade.md) — TypeScript GUI-based strategy builder; genetic algo optimization; abandoned (→NexusTrade SaaS); Tradier broker only; NOT relevant to our stack ← new 2026-05-20
- [Quant Firm Open Source Repos](trading/tools/quant-firm-repos.md) — 22 repos from Two Sigma, Man Group, Jane Street, D.E. Shaw, HRT, Optiver, WorldQuant; ArcticDB, dtale, QuantMuse (2.5k stars); open/closed split maps onto competitive moat theory ← new 2026-05-22

**Data Sources**
- [Polygon.io](trading/data-sources/polygon.md) — market data (free: EOD only; paid: options, ticks, Greeks)
- [Alpaca](trading/data-sources/alpaca.md) — broker + data; paper trading; 10yr 1-min data free
- [Alpaca Automation Guide](trading/data-sources/alpaca-automation.md) — Phase 3 foundation; alpaca-py patterns, order execution, portfolio tracking
- [Free Data Sources](trading/data-sources/free-data.md) — EDGAR (EdgarTools), Alpha Vantage, Finnhub, FRED, Tiingo; yfinance status
- [Options Data Sources](trading/data-sources/options-data.md) — ThetaData (cheapest), ORATS (best IV surface), Polygon/Alpaca (real-time only; no history)
- [Sector & Industry Classification](trading/data-sources/sector-classification.md) — GICS/SIC sources; SEC EDGAR SIC, GitHub S&P 500 CSV, yfinance caveats; build_sector_cache() for 100-500 stocks; H181
- [Earnings Calendar & Events](trading/data-sources/earnings-events.md) — FMP/Finnhub/yfinance earnings APIs; SEC EDGAR XBRL EPS extraction; EdgarTools; EPS surprise formulas; PEAD stack upgrade path for pead_overnight.py ← new 2026-05-23

**Backtesting**
- [Backtesting Design Principles](trading/backtesting/design-principles.md) — IS/OOS framework, bias taxonomy, confirmation criteria, deflated Sharpe, López de Prado
- [Walk-Forward & CPCV](trading/backtesting/walk-forward-cpcv.md) — walk-forward variants, CPCV algorithm, purging/embargoing, DSR formulas; Python libs: timeseriescv/skfolio
- [Transaction Cost Modeling](trading/backtesting/transaction-costs.md) — spread/impact/borrow cost models, square-root market impact, vectorbt/backtrader defaults, per-strategy calibration table
- [Hypothesis Log](trading/backtesting/hypothesis-log.md) — H001–H222 (frontier: H221 drift-regime-reversal, H222 Piotroski quality); H217 CONFIRMED (median alpha101 OOS 1.559); H220 CONFIRMED (ETF TSMOM 0.961); H215 CONFIRMED (alpha101 OOS 1.321); H181 reversal (Sharpe 1.138); H192-D BAB (Sharpe 1.367); H198 momentum (Sharpe 1.174); H201 TOM (Sharpe 0.740); calendar family closed H205–H208 NOT CONFIRMED

**Paper Trading**
- [Paper Trading Index](trading/paper-trading/index.md) — active strategies, open positions, iron condor rules
- [H149 Alpaca ETF Rotation](trading/paper-trading/h122-alpaca.md) — production strategy log; H026 100% rotation; started 2026-04-28
- [PEAD-NLP Alpaca Deployment](trading/paper-trading/pead-nlp-alpaca.md) — H163/H174 live pipeline: gap detection, 8-K scoring, OPG orders; started 2026-05-06
- [H181 Industry-Adjusted Reversal Deployment](trading/paper-trading/h181-alpaca.md) — H181 live pipeline: 30-stock equal-weight monthly reversal; started 2026-05-10

**Prediction Markets**
- [Kalshi](trading/prediction-markets/kalshi.md) — primary prediction market platform; CFTC-regulated, economic events, RSA-PSS auth, CPI/NFP strategies live
- [Polymarket](trading/prediction-markets/polymarket.md) — secondary; highest global volume, blockchain-based, US re-entry Dec 2025
- [Other Prediction Market Platforms](trading/prediction-markets/other-platforms.md) — PredictIt, Manifold, IBKR ForecastTrader (full API), Kalshi Timeless mechanics
- [Prediction Market Algorithmic Strategies](trading/prediction-markets/algorithmic-strategies.md) — Kelly criterion, event modeling, arbitrage, NLP; cross-market arb, Timeless funding arb

**Research Logs**
- [Research Log 2026-04-24](trading/research-log/2026-04-24.md) — session 1: tools and data sources
- [Research Log 2026-04-25](trading/research-log/2026-04-25.md) — session 2: prediction markets deep dive
- [Research Log 2026-04-26](trading/research-log/2026-04-26.md) — session 3: options income strategies, LEAN eval, H006 (BIL safe-haven), iron condor scaffold
- [Research Log 2026-04-27](trading/research-log/2026-04-27.md) — session 4: position sizing, alpaca automation, H018 blend
- [Research Log 2026-04-28](trading/research-log/2026-04-28.md) — session 5: Qlib expansion, Polygon deep dive, H113/H114, H115/H116 major upgrade
- [Research Log 2026-04-29](trading/research-log/2026-04-29.md) — session 6: Vectorbt H116 impl, Kalshi API deep dive, paper trading launch
- [Research Log 2026-04-30](trading/research-log/2026-04-30.md) — session 7: momentum + pairs strategy wiki pages, H149 production code
- [Research Log 2026-05-01](trading/research-log/2026-05-01.md) — session 9: H152 GDX/SIL pairs, Kraken CLI expansion
- [Research Log 2026-05-02](trading/research-log/2026-05-02.md) — session 10: H155 Kalman TLT/IEF, H156 stock momentum, prediction market expansions
- [Research Log 2026-05-03](trading/research-log/2026-05-03.md) — nightly: event-driven wiki, arXiv scan, H163–H167 dream cycle proposals
- [Research Log 2026-05-04](trading/research-log/2026-05-04.md) — session 12: NLP libraries, FinBERT setup, edgartools, 0DTE iron condor partial sim (H170)
- [Research Log 2026-05-05](trading/research-log/2026-05-05.md) — H163 CONFIRMED (FinBERT NLP), H174 CONFIRMED, H161/H162 PARTIAL, pairs family exhausted H152-H160
- [Research Log 2026-05-06](trading/research-log/2026-05-06.md) — H174 deployed to Alpaca paper trading; PEAD-NLP live pipeline built
- [Research Log 2026-05-07](trading/research-log/2026-05-07.md) — H178/H179 NOT CONFIRMED; short-term-reversal and walk-forward/CPCV wiki pages
- [Research Log 2026-05-08](trading/research-log/2026-05-08.md) — H181 CONFIRMED industry-adjusted reversal (OOS Sharpe 1.138); sector classification data sources wiki
- [Research Log 2026-05-09](trading/research-log/2026-05-09.md) — H184 NOT CONFIRMED composite FinBERT; transaction cost modeling wiki; dream cycle scan
- [Research Log 2026-05-10](trading/research-log/2026-05-10.md) — ML-for-trading wiki; dream cycle build phase; H184 NOT CONFIRMED summary
- [Research Log 2026-05-11](trading/research-log/2026-05-11.md) — low-volatility anomaly wiki (Blitz & Vliet, BAB, min-var); dream cycle: PEAD.txt/PolySwarm/Spectre staged
- [Research Log 2026-05-12](trading/research-log/2026-05-12.md) — H192 CONFIRMED (BAB: sector-neutral H192-D Sharpe 1.367); Alpaca.md full rewrite; H193 queued
- [Research Log 2026-05-13](trading/research-log/2026-05-13.md) — H193 NOT CONFIRMED (BAB+reversal blend); H196 NOT CONFIRMED (STORM scale); low-volatility.md research closed
- [Research Log 2026-05-14](trading/research-log/2026-05-14.md) — H198 CONFIRMED (6-1m stock momentum, OOS Sharpe 1.174); H199 NOT CONFIRMED (sector-neutral hurts momentum)
- [Research Log 2026-05-15](trading/research-log/2026-05-15.md) — H200 NOT CONFIRMED (graphical pairs, 0/15 cointegrated); H201 CONFIRMED (TOM, OOS Sharpe 0.740); pairs family EXHAUSTED; H202 queued
- [Research Log 2026-05-24](trading/research-log/2026-05-24.md) — H217 CONFIRMED (median alpha101 OOS 1.559); H218/H219 NOT CONFIRMED; H220 CONFIRMED (ETF TSMOM 0.961); quality-factor.md wiki new; H221/H222 staged
- [Research Log 2026-05-23](trading/research-log/2026-05-23.md) — H215 CONFIRMED (alpha101 OOS 1.321); H216 CONFIRMED-weak (vol-price divergence, below SPY); blend H215+H198 OOS 1.397; earnings-events.md wiki new
- [Research Log 2026-05-21](trading/research-log/2026-05-21.md) — H205/H206/H207/H208 NOT CONFIRMED (full calendar family closed); H202-XL NOT CONFIRMED (OOS 1.106)
- [Research Log 2026-05-20](trading/research-log/2026-05-20.md) — factor-models.md wiki new (Fama-French H202-XL prep); dream cycle scan: 5 arXiv/GitHub angles
- [Research Log 2026-05-19](trading/research-log/2026-05-19.md) — regime-detection.md wiki new; H206 NOT CONFIRMED (Halloween Effect); H204 NOT CONFIRMED (Deep RL PPO)
- [Research Log 2026-05-18](trading/research-log/2026-05-18.md) — H205 design finalized; arXiv scan: 3 papers support H202-XL large-universe gradient boosting
- [Research Log 2026-05-17](trading/research-log/2026-05-17.md) — H202 NOT CONFIRMED (XGBoost +0.104 Sharpe, below threshold); H203 NOT CONFIRMED (HRP over-weights TOM 74%); H205 queued; calendar-anomalies wiki new

### Impact Investing

**Sources**
- [A Portfolio Approach to Impact Investment (J.P. Morgan, 2012)](sources/jpmorgan-portfolio-approach-impact-investment-2012.md) — 3D Impact/Return/Risk portfolio framework; practical guide for institutional investors; Saltuk & El Idrissi

**Trading Sources**
- [Phynance — Kakushadze (arXiv:1405.1948, 2014)](sources/phynance-kakushadze-2014.md) — PhD lecture notes: stochastic calculus, Itô/Girsanov/path-integral formulation, BSM full derivation, Greeks, interest rate models (Vasicek/CIR/HJM/BGM), quant interview problems

**Concepts**
- [Impact Investing](concepts/impact-investing.md) — definition, key characteristics, risks, market context; distinguishes from SRI and philanthropy
- [Three-Dimensional Portfolio Framework](concepts/three-dimensional-portfolio-framework.md) — Impact/Return/Risk triangle; extends MPT; target zone, aggregate comparison

**People**
- [Yasemin Saltuk](people/yasemin-saltuk.md) — J.P. Morgan Social Finance lead researcher; impact investing research series

**Organizations**
- [J.P. Morgan Social Finance](orgs/jpmorgan-social-finance.md) — JPM unit est. 2007; proprietary capital + advisory + research

---

### General Tech

- [zenbu.js](tools/zenbu.md) — JS framework for AI-agent-customizable desktop apps; local source, git-tracked, hot-reload; alpha
- [Dograh](tools/dograh.md) — self-hostable voice agent platform (open-source Vapi/Retell alternative); drag-and-drop workflows, bring-your-own LLM/TTS/STT, Docker deploy

### AI Industry

- [The AI Decoupling](concepts/ai-decoupling.md) — vintagedata.org 2026; SaaS/AI ecosystem split; MoE economics, synthetic data moats, token pricing vs. enterprise CFO models; Chinese self-build alternative ← 2026-05-25

---

### Disaster Recovery

- [DR Overview](dr/overview.md) — restore procedure, what survives, what to tell a fresh George
- [Git Backup Setup](dr/git-backup.md) — git repo config, current status, blocked items
- [Session Diary](dr/diary.md) — append-only log of sessions; narrative recovery layer

