---
updated: 2026-07-07
sources_indexed: 4
pages: 195
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
- [IBS Mean-Reversion](trading/algorithms/ibs-mean-reversion.md) — Internal Bar Strength daily mean-reversion on tech ETFs (XLK/SMH/IGV); H062–H112 confirmed; OOS Sharpe 2.129 (2021–2026); 30% production portfolio weight ← new 2026-05-28
- [Market Microstructure & HFT](trading/algorithms/market-microstructure.md) — Stanford MS&E 448; order book dynamics, market impact, adverse selection, HFT strategies; Avellaneda-Stoikov MM model; context for execution cost modeling ← new 2026-05-25
- [Strategic Trading Game — Kearns & Shi (2025)](trading/sources/kearns-shi-2025-strategic-trading.md) — arXiv:2502.07606; N-player execution game; temporary vs permanent market impact; FTPL for CCE; κ=0→potential game (spread orders), κ=2→zero-sum (front-run); relevant for institutional-scale execution ← new 2026-06-13
- [The Alchemy of Multibagger Stocks — Yartseva (2025)](trading/sources/multibagger-yartseva-2025.md) — CAFÉ WP No. 33; FCF yield dominant for 10x returns; near-52w-low entry signal ← new 2026-06-12
- [Technical Analysis Patterns](trading/algorithms/technical-analysis-patterns.md) — H234 inside-bar coiled-spring (OOS Sharpe 1.770, WR 63.9%); NR7/NR4 narrow range; TA feature library (MACD/RSI/Stochastic/ROC) for H233/H235; pandas-ta vs TA-Lib guide ← new 2026-05-29
- [Behavioral Finance Signals](trading/algorithms/behavioral-finance-signals.md) — 52-week high anchoring (H291 NOT CONFIRMED); return seasonality Jul/Nov standout months (H292 CONFIRMED OOS 0.970); disposition effect CGO; lottery stock MAX factor ← new 2026-06-14
- [Market Timing Overlays](trading/algorithms/market-timing-overlays.md) — VIX term structure (H296 CONFIRMED OOS 1.116); SPY 200d MA (H301 Variant D best, +27.4% Sharpe vs H026); yield curve (H300 NOT CONFIRMED); breadth (H299 NOT CONFIRMED); overlay vs standalone trade-off ← new 2026-06-15
- [Cryptocurrency Trading Strategies](trading/algorithms/crypto-trading-strategies.md) — cross-sectional momentum Sharpe 1.51 (28d lookback, top-30 universe); BTC 50d MA Sharpe 1.9 vs B&H 1.3; funding carry declining (6.45→negative 2025); Monday effect +0.51%; halving cycle positioning; ccxt/pycoingecko implementation; H302/H303 queued ← new 2026-06-16
- [Multi-Agent LLM Trading](trading/algorithms/multi-agent-llm-trading.md) — taxonomy LLM-as-signal vs decision-maker; TradingAgents 84.9k★ bull/bear debate; HedgeAgents; Expert Investment Teams fine-grained decomp; Agent Market Arena; MadEvolve evolutionary; NautilusTrader 23.4k★; CBS cost metric; reproducibility crisis (0/19 papers fully reproducible); H274 PEAD integration; H318 meta-learner proposal ← merged 2026-06-21
- [Time-Series Foundation Models](trading/algorithms/ts-foundation-models.md) — Chronos-2 #1 GIFT-Eval (Bolt 250× faster); TimesFM 2.5 200M params 16k context + quantile head; Moirai any-variate ICML oral trained on LOTSA 27B obs; FinTSB 15-25% over ARIMA; TS-RAG +6.51% retrieval-augmented; financial verdict: feature engineering not standalone signal; H318/H320+ integration patterns ← new 2026-06-21
- [SPX Dispersion Trading & Variance Risk Premium](trading/algorithms/spx-dispersion-variance.md) — H309 PARTIAL; implied correlation premium 6-18pp historically; DSPX/COR3M signals; vega-neutral construction; Polygon IV integration path; dirty dispersion z1/z2/z3 thresholds ← new 2026-06-19
- [Merger Arbitrage & Special Situations](trading/algorithms/merger-arbitrage-special-situations.md) — H310 NOT CONFIRMED (ETFs can't discriminate deal-break risk; antitrust regime artifact; 2020-2026 M&A boom inflated OOS); spread mechanics, deal-break risk, H341b FinBERT M&A design queued ← new 2026-06-25
- [Fixed Income / Bond ETF Rotation](trading/algorithms/fixed-income-bond-rotation.md) — H045 PRODUCTION 21% portfolio; 13-ETF universe; 3m+6m+12m rank ensemble; OOS Sharpe 1.351, MaxDD -6.3%; carry FAILS (ETF dividends ≠ forward carry); SHY dominates OOS 72% of months; H314/H315 NOT CONFIRMED ← new 2026-06-20
- [Value Factors](trading/algorithms/value-factors.md) — FCF yield signal (FMP API); COWZ ETF mechanics; H284 CONFIRMED-weak; H286 CONFIRMED Corr(SPY)=0.596; value vs momentum tension; data sources table ← new 2026-06-13
- [Commodity Trend Following](trading/algorithms/commodity-trend-following.md) — H261/H261b/H262 CTA on GLD/SLV/DBC/USO/DBA; UNG excluded (K-1, contango, mean-reverting); H261b CONFIRMED (OOS Sharpe 0.922, Corr(SPY)=0.218, 2022 +26.7%); H262 QUEUED (Bayesian 3m/6m/12m blend) ← new 2026-06-07
- [Factor Momentum & Style Rotation](trading/algorithms/factor-momentum-style-rotation.md) — H255 NOT CONFIRMED (factor ETF, Corr(SPY)=0.894, no escape); H256 NOT CONFIRMED (GEM/PACS/GEM+Sector, all underperform SPY OOS); multi-asset fix → H257 ← new 2026-06-06
- [Long-Short Equity](trading/algorithms/long-short-equity.md) — dollar-neutral L/S construction; H241/H242 NOT CONFIRMED (XGBoost 200-stock, OOS < 1.5 gate); H243 design (top/bottom quintile); short-leg survivorship bias caveats ← new 2026-05-31
- [Volatility Risk Premium](trading/algorithms/volatility-risk-premium.md) — IV > RV ~85% of time; VRP 2–4 vol points; short-vol Sharpe ~1.0; CSP/iron condor/delta-hedged straddle; SVXY vs XIV; Volmageddon/COVID lessons; H266 queued ← new 2026-06-09
- [Shared Strategy Evaluation Checklist](trading/shared-eval-checklist.md) — 7-point pre-production gate (George + Ernesto): look-ahead guard, NLP timestamp, cost model, soft OOS, regime coverage, survivorship bias, after-tax flag ← new 2026-06-09
- [Smart Money Concepts (ICT) — Order Blocks, FVGs, BOS/CHoCH](trading/algorithms/smart-money-concepts-ict.md) — H343-H346/H355/H356 ALL CONFIRMED; Order Blocks as implicit regime detectors; 36/36 param combos pass gate on H198; OB filter portable across stocks, sector ETFs, bond ETFs, low-vol ETFs ← new 2026-06-29
- [AI-Driven Alpha Factor Discovery](trading/algorithms/auto-alpha-discovery.md) — automated alpha mining via LLMs, evolutionary algorithms, and deep learning; H347 Attention Factors, H349 QuantaAlpha, H288 LLM-DSL, H352 TreEvo queued ← new 2026-07-01
- [Low-Volatility Factor ETF Rotation](trading/algorithms/low-volatility-etf-rotation.md) — H354 CONFIRMED (USMV/SPLV/XLU/SPHD/EFAV/EEMV/ACWV; pure 12m top-1 OOS 1.735, zero neg years, +7.0% in 2022); H355 CONFIRMED (OB filter H045 OOS 1.522); H356 CONFIRMED (OB extension OOS 2.312) ← new 2026-07-02

**Tools**
- [Qlib](trading/tools/qlib.md) — Microsoft's AI quant platform; ML strategies, production-grade
- [Backtrader vs Vectorbt](trading/tools/backtrader-vs-vectorbt.md) — framework comparison; H116 ETF rotation implementations for both; Vectorbt v1.0 (2026-04-22)
- [OpenAlice](tools/openalice.md) — full-lifecycle AI trading agent; UTA (CCXT+Alpaca+IBKR), Trading-as-Git, Workspace+MCP, Telegram; TypeScript, 4.4k stars ← 2026-05-28
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
- [awesome-quant-ai](trading/tools/awesome-quant-ai.md) — curated AI/ML quant resources; LLM agents (TradingAgents, FinRL, Vibe-Trading), TS foundation models (Chronos, TimesFM, Moirai), diffusion synthetic data, DeFi; strategy taxonomy + paradigms table; cross-refs H279–H281 staged ← new 2026-06-21
- [ATLAS (atlas-gic)](trading/tools/atlas-gic.md) — self-improving AI trading agents; Karpathy autoresearch (prompts=weights, Sharpe=loss); 4-layer 25-agent architecture; PRISM regime cohorts; JANUS meta-layer (emergent regime detector = H318 analog); Soros reflexivity + MiroFish swarm; ~1975 stars; SaaS atlasagents.co ← new 2026-06-22
- [QuantDinger](trading/tools/quantdinger-notes.md) — self-hosted AI trading platform (Docker); `quantdinger-mcp` PyPI for Claude Code integration; supports Alpaca/IBKR/Kraken/CCXT; full stack overkill given existing setup; MCP package worth testing ← new 2026-06-07
- [QuantStats](tools/quantstats-notes.md) — Python portfolio analytics + HTML tearsheet generator; `pip install quantstats`; takes pandas returns Series → 50+ metrics + SPY benchmark + monthly heatmaps; add `qs.reports.html()` to run_hNNN.py ← new 2026-06-08
- [Kan](tools/kan-notes.md) — self-hosted open-source kanban board (Trello alternative); AGPLv3, ~5k stars; Next.js + tRPC + Postgres; webhooks + admin API; potential task/research dashboard UI ← new 2026-06-08
- [ByteChef](tools/bytechef-notes.md) — open-source visual AI agent orchestration + workflow automation (n8n/Zapier alternative); self-hosted, MCP support, ~839 stars; AGPLv3; AI agent step type built-in ← new 2026-06-27
- [OpenKnowledge AI](tools/openknowledge-ai-notes.md) — agent-first notes app; productized Karpathy "LLM Wiki" concept; import papers/docs, AI queries across corpus; import from URL/PDF/text ← new 2026-06-27
- [rust-trade](tools/rust-trade-notes.md) — Rust quant trading + backtesting system with Tauri desktop UI; MIT, ~449 stars; performance-focused alternative to Python backtesting ← new 2026-06-27
- [/visual-plan Skill](tools/visual-plan-skill.md) — Claude Code skill; scans codebase → auto-wireframes user flow as storyboard; spotted broken/missing UI states; npx skills add ← new 2026-06-27
- [Hyper-Extract](tools/hyper-extract-notes.md) — LLM→structured knowledge extraction; 8 formats (KG, hypergraph, temporal graph, Pydantic); 80+ YAML templates incl. Finance; MCP server; Claude-native (sonnet-4-6); `pip install hyper-extract`; ~2.5k stars ← new 2026-06-26
- [QuantMind](tools/quant-mind-notes.md) — finance-domain knowledge extraction + retrieval; ingests arXiv/news/SEC filings → semantic knowledge graph; RAG + deep research + NL queries; MIT, 1.7k stars; complements Hyper-Extract (retrieval-first vs. structure-first) ← new 2026-07-04
- [Hitchhiker's Guide to Agentic AI](tools/hitchhikers-guide-agentic-ai.md) — practitioner survey (arXiv:2606.24937, Roitman 2026); 5-layer stack: LLM foundations → alignment → agentic systems → multi-agent (MCP/A2A) → production; impl guidance + code examples; ref for H274 multi-agent design, H319 RAG, MCP topology ← new 2026-06-26
- [birdclaw](tools/birdclaw.md) — local-first Twitter/X workspace; SQLite archive of tweets/DMs/likes/bookmarks; AI-ranked inbox (OpenAI); full-text search FTS5; CLI + local web app; MIT; brew install; active dev/schema churn ← new 2026-06-22
- [hermes-gpt](tools/hermes-gpt.md) — local MCP sidecar bridging ChatGPT to Hermes Agent's local tool stack (memory, skills, files); no context stuffing → Codex quota preserved; v0.1.0 read-only by default; write/terminal opt-in ← new 2026-06-22
- [awesome-codex-subagents](tools/awesome-codex-subagents.md) — 166+ specialized Codex subagents in .toml format; 13 categories; 5.2k stars MIT; quant-analyst agent has strong backtest review checklist (lookahead bias, OOS robustness, execution assumptions); Codex-specific but pattern transferable ← new 2026-06-22
- [youtube-fetcher-to-markdown](tools/youtube-fetcher-to-markdown.md) — Claude Code skill; YouTube URL → structured Markdown with YAML frontmatter, chapters, transcript, metadata; no API keys; `npx skills add JimmySadek/youtube-fetcher-to-markdown`; yt-dlp recommended ← new 2026-06-22
- [Agent-Native Clips](tools/agent-native-clips.md) — AI recording companion (transcribe + summarize + search); built on Agent-Native OSS framework (BuilderIO, 1.7k stars, TypeScript); one action → agent + UI + HTTP + MCP + A2A + CLI; clips.agent-native.com ← new 2026-06-22
- [Alexandrie](tools/alexandrie-notes.md) — self-hosted knowledge base; extended Markdown (CodeMirror 6, KaTeX, containers), Kanban, SSO/OIDC, PWA+offline, 5-level per-doc permissions, full-text search; Go+Nuxt+MySQL; one-command Docker deploy; MIT; not a replacement for agent wiki (needs file access) but potential browser-readable companion layer ← new 2026-06-21
- [fireworks-tech-graph](tools/fireworks-tech-graph.md) — Claude Code skill for SVG/PNG architecture diagrams from natural language; 8 styles, 14 types, AI/Agent domain built-ins (RAG/Multi-Agent/Tool Call patterns, 40+ product icons); MIT ← new 2026-06-10
- [claude-code-video-toolkit](tools/claude-code-video-toolkit.md) — AI-native video production; NARRATE→SCORE→GENERATE→COMPOSE→RENDER; ElevenLabs TTS, FLUX, LTX2 video; MIT ← new 2026-06-08
- [Awesome Finance MCP](trading/tools/awesome-finance-mcp.md) — curated finance MCP servers; HIGH: Alpaca MCP + FMP MCP; already live: Massive MCP; medium: CCXT/QuantConnect/TradingView/Alpha Vantage MCPs ← new 2026-06-18
- [AI-Trader](trading/tools/ai-trader.md) — HKUDS agent-native social trading; ai4trade.ai; MIT ← new 2026-06-11
- [qf-lib — Event-Driven Python Backtester](trading/tools/qf-lib.md) — modular Python event-driven backtester; 943 stars; multi-broker integration (Alpaca/Interactive Brokers); data vendor connectors; production-focused alternative to vectorbt ← new 2026-06-24
- [RustQuant — Rust Quantitative Finance Library](trading/tools/rust-quant.md) — QuantLib-comparable Rust library; options pricing (BSM/Heston/SABR), stochastic processes, ML, time series; Python bindings via PyO3; 1,773 stars ← new 2026-06-24
- [whchien/ai-trader — Backtrader + MCP Backtesting](trading/tools/whchien-ai-trader.md) — config-driven Backtrader framework; 20+ built-in strategies; MCP server for natural language backtest commands; 744 stars ← new 2026-06-24
- [smart-money-concepts — ICT Price Action Indicators](trading/tools/smart-money-concepts.md) — joshyattridge; FVG, Order Blocks, BOS/CHoCH, Liquidity, Sessions; 1,788 stars; `pip install smartmoneyconcepts`; clean vectorized pandas/numpy; no academic validation; H343 FVG momentum filter queued ← new 2026-06-28
- [rohonchain — Polymarket Arbitrage Math](trading/tools/rohonchain-polymarket.md) — Roan @RohOnChain; Polymarket CLOB arb; Bregman+Frank-Wolfe+Kelly; $40M bot profits; low relevance to equity pipeline ← new 2026-06-24
- [sairahul1 — AI Agent Loop Architecture](tools/sairahul1-ai-agent-loops.md) — Rahul @sairahul1; build systems that prompt themselves; memory + sub-agent split + stop conditions; applicable to dream cycle + multi-agent trading (H274/H280) ← new 2026-06-24
- [ContestTrade](trading/tools/contesttrade.md) — FinStep-AI contest mechanism (arXiv:2508.00554); US V2.0; Apache 2.0 ← new 2026-06-11
- [QuantMuse](trading/tools/quantmuse.md) — FactorCalculator/FactorScreener/BacktestEngine; C++ execution; MIT ← new 2026-06-11

**Data Sources**
- [Polygon.io](trading/data-sources/polygon.md) — market data (free: EOD only; paid: options, ticks, Greeks)
- [Alpaca](trading/data-sources/alpaca.md) — broker + data; paper trading; 10yr 1-min data free
- [Alpaca Automation Guide](trading/data-sources/alpaca-automation.md) — Phase 3 foundation; alpaca-py patterns, order execution, portfolio tracking
- [Free Data Sources](trading/data-sources/free-data.md) — EDGAR (EdgarTools), Alpha Vantage, Finnhub, FRED, Tiingo; yfinance status
- [Options Data Sources](trading/data-sources/options-data.md) — ThetaData (cheapest), ORATS (best IV surface), Polygon/Alpaca (real-time only; no history)
- [Sector & Industry Classification](trading/data-sources/sector-classification.md) — GICS/SIC sources; SEC EDGAR SIC, GitHub S&P 500 CSV, yfinance caveats; build_sector_cache() for 100-500 stocks; H181
- [Earnings Calendar & Events](trading/data-sources/earnings-events.md) — FMP/Finnhub/yfinance earnings APIs; SEC EDGAR XBRL EPS extraction; EdgarTools; EPS surprise formulas; PEAD stack upgrade path for pead_overnight.py ← new 2026-05-23
- [SEC EDGAR Fundamentals](trading/data-sources/edgar-fundamentals.md) — XBRL financial statement extraction; bulk downloads vs API; financial ratios (P/E, P/B, ROE) for quality/value factors; H221/H222 data pipeline ← new 2026-05-25
- [Alternative Data Sources](trading/data-sources/alternative-data.md) — NewsAPI/Finnhub/ApeWisdom/Congressional/pytrends/Wikipedia; Quiver Quantitative ($30/mo); H279/H280/H281/PEAD signal taxonomy ← new 2026-06-12
- [Crypto Data Sources](trading/data-sources/crypto-data-sources.md) — yfinance→CoinGecko→ccxt migration path; Binance public REST; Kraken asset codes ← new 2026-06-08

**Backtesting**
- [Backtesting Design Principles](trading/backtesting/design-principles.md) — IS/OOS framework, bias taxonomy, confirmation criteria, deflated Sharpe, López de Prado; GT-Score composite objective (98% generalization improvement vs Sharpe-only)
- [Walk-Forward & CPCV](trading/backtesting/walk-forward-cpcv.md) — walk-forward variants, CPCV algorithm, purging/embargoing, DSR formulas; Python libs: timeseriescv/skfolio
- [Transaction Cost Modeling](trading/backtesting/transaction-costs.md) — spread/impact/borrow cost models, square-root market impact, vectorbt/backtrader defaults, per-strategy calibration table
- [Options Backtesting Methodology](trading/backtesting/options-backtesting-methodology.md) — path-dependency, vol surface evolution, 4-tier data (Tier 0 BSM free → Tier 3 ORATS $99/mo); ThetaData/QuantConnect/zipline-reloaded; H309/H266/H329 pipeline ← new 2026-06-24
- [Strategy Blending & Correlation Management](trading/backtesting/strategy-blending-correlation.md) — production portfolio correlation matrix (OOS 2018-2026); H026/H045/IBS/BAB/TOM pairwise corr; diversification budget; when to add vs blend ← new 2026-06-23
- [Multiple Testing & Statistical Significance](trading/backtesting/multiple-testing.md) — Bonferroni/BH corrections; deflated Sharpe ratio; p-hacking taxonomy; minimum backtest length formula ← new 2026-05-26
- [Regime Detection Signals — Practical Data Guide](trading/backtesting/regime-detection-signals.md) — SPY 200MA, VIX threshold (FRED VIXCLS), yield curve (T10Y2Y, DGS10) signals; look-ahead rules; continuous score (Xiong 2026); H249 production pipeline ← new 2026-06-04
- [Signal Half-Life & Alpha Decay](trading/backtesting/signal-halflife.md) — IC decay curves, half-life estimation, AI-driven compression (momentum 84m→12m per arXiv:2605.23905); IS window sizing; H261b insulation argument ← new 2026-05-31
- [Survivorship Bias & Universe Construction](trading/backtesting/survivorship-bias.md) — delisting bias, S&P 500 backfill, CRSP vs point-in-time; impact on H243 short-leg; mitigation strategies ← new 2026-06-03
- [Hypothesis Log](trading/backtesting/hypothesis-log.md) — H001–H376; H373 NOT CONFIRMED (MAX tilt H198 — tech universe kills MAX/momentum heterogeneity); H376 CONFIRMED (MAX composite H198 top-6 EW — 6-0m no-skip OOS 3.120/MaxDD -8.4%/0 neg yrs = major finding); H370 LambdaRankIC stub; H371 HMM+RL stub; production portfolio H041a/H026/H045/IBS — OOS Sharpe 4.158

**Paper Trading**
- [Paper Trading Index](trading/paper-trading/index.md) — active strategies, open positions, iron condor rules
- [H149 Alpaca ETF Rotation](trading/paper-trading/h122-alpaca.md) — production strategy log; H026 100% rotation; started 2026-04-28
- [PEAD-NLP Alpaca Deployment](trading/paper-trading/pead-nlp-alpaca.md) — H163/H174 live pipeline: gap detection, 8-K scoring, OPG orders; started 2026-05-06
- [H181 Industry-Adjusted Reversal Deployment](trading/paper-trading/h181-alpaca.md) — H181 live pipeline: 30-stock equal-weight monthly reversal; started 2026-05-10
- [Live Graduation Criteria](trading/paper-trading/live-graduation-criteria.md) — SPRT statistical test for strategy validation; minimum trade counts; regime coverage gates; performance attribution; Alpaca migration steps; graduation status by strategy ← new 2026-05-30
- [Tax & After-Tax Return Modeling](trading/paper-trading/tax-and-after-tax-returns.md) — short/long-term cap gains, wash-sale rules, tax-loss harvesting, after-tax Sharpe adjustment; strategy-specific tax efficiency rankings ← new 2026-06-05
- [Performance Attribution & Drawdown Analysis](trading/paper-trading/performance-attribution.md) — Brinson attribution adapted for quant sleeves; regime attribution; drawdown decomposition; rebalance decision framework ← new 2026-06-27
- [Execution Quality & Slippage Analysis](trading/paper-trading/execution-quality.md) — fill analysis for paper→live graduation; slippage measurement; OPG vs MARKET comparison ← new 2026-06-11
- [Risk Controls & Live Trading Monitoring](trading/paper-trading/risk-controls-and-monitoring.md) — 3-tier circuit breakers; kill switch via Alpaca close_all_positions; ATR position sizing; portfolio heat monitoring; correlation guard for PEAD entries; per-strategy risk table ← new 2026-06-17

**Prediction Markets**
- [Kalshi](trading/prediction-markets/kalshi.md) — primary prediction market platform; CFTC-regulated, economic events, RSA-PSS auth, CPI/NFP strategies live
- [Polymarket](trading/prediction-markets/polymarket.md) — secondary; highest global volume, blockchain-based, US re-entry Dec 2025
- [Other Prediction Market Platforms](trading/prediction-markets/other-platforms.md) — PredictIt, Manifold, IBKR ForecastTrader (full API), Kalshi Timeless mechanics
- [Prediction Market Algorithmic Strategies](trading/prediction-markets/algorithmic-strategies.md) — Kelly criterion, event modeling, arbitrage, NLP; cross-market arb, Timeless funding arb
- [Nowcasting Playbook](trading/prediction-markets/nowcasting-playbook.md) — CPI/NFP/FOMC prediction market strategies; CME FedWatch implied probability extraction; signal timing; H185 design ← new 2026-05-27
- [AI Model Benchmarks on Prediction Markets](trading/prediction-markets/ai-model-benchmarks.md) — Prediction Arena (arXiv:2604.07355) + PolyBench (every LLM negative return; structured data is differentiator) + PolySwarm (50-agent swarm; H185 Phase 2 analog) + PredictionMarketBench (Kalshi LOB replay; Bollinger +1.67% vs GPT-4.1-nano −2.77%; fee management dominates) ← updated 2026-06-28
- [Prediction Market Automated Pipeline](trading/prediction-markets/automated-pipeline.md) — operational guide for live Kalshi/Polymarket pipeline; APScheduler; George infrastructure; companion to algorithmic-strategies.md and nowcasting-playbook.md ← new 2026-06-26
- [Superforecasting Methods](trading/prediction-markets/superforecasting-methods.md) — Tetlock GJP; reference class forecasting; Bayesian updating; Brier/ECE calibration; LLM benchmarks (KalshiBench ECE 0.120 best); isotonic recalibration ← new 2026-06-11

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
- [Research Log 2026-05-25](trading/research-log/2026-05-25.md) — wiki: SEC EDGAR fundamentals (edgar-fundamentals.md); dream cycle scan: arXiv angles
- [Research Log 2026-05-26](trading/research-log/2026-05-26.md) — wiki: multiple testing & statistical significance; dream cycle scan
- [Research Log 2026-05-27](trading/research-log/2026-05-27.md) — wiki: nowcasting playbook (prediction markets); dream cycle scan
- [Research Log 2026-05-28](trading/research-log/2026-05-28.md) — wiki: IBS mean-reversion & market microstructure; dream cycle scan; H231/H232 proposals
- [Research Log 2026-05-29](trading/research-log/2026-05-29.md) — wiki: technical analysis patterns (TA library, H234); dream cycle scan; H233/H235/H236 proposals
- [Research Log 2026-05-30](trading/research-log/2026-05-30-live-graduation.md) — wiki: live graduation criteria (paper trading); dream cycle scan; H237/GT-Score/AlphaAgent staged
- [Research Log 2026-05-31](trading/research-log/2026-05-31.md) — wiki: signal-halflife.md + long-short-equity.md new; H241/H242 NOT CONFIRMED (XGBoost 200-stock, OOS < 1.5 gate); dream cycle: H238/H239/H240/H243/H244 staged
- [Research Log 2026-06-02](trading/research-log/2026-06-02.md) — H243 NOT CONFIRMED (L/S short-leg problem: losers rose OOS; long-leg Sharpe 1.273); dream cycle scan
- [Research Log 2026-06-03](trading/research-log/2026-06-03.md) — wiki: survivorship-bias.md new; H245 NOT CONFIRMED (low-vol OOS 0.626); H246 NOT CONFIRMED (ETF pairs, structural breaks); dream cycle scan
- [Research Log 2026-06-05](trading/research-log/2026-06-05.md) — wiki: tax-and-after-tax-returns.md new; dream cycle: H253/H254 staged
- [Research Log 2026-06-06](trading/research-log/2026-06-06.md) — wiki: factor-momentum-style-rotation.md new; H255/H256 NOT CONFIRMED (factor ETF / GEM all underperform SPY OOS); dream cycle: H257/H258/H259/H260 staged
- [Research Log 2026-07-07](trading/research-log/2026-07-07.md) — wiki: momentum-strategies.md major expansion H376/H377 6-0m no-skip discovery (OOS 3.120/MaxDD -8.4%/0 neg yrs); dream cycle: 5 proposals staged (H377 stub, H378 SAE-FiRE PEAD, H379 network momentum, PortBench wiki, Kumar wiki)
- [Research Log 2026-07-06](trading/research-log/2026-07-06.md) — wiki: llm-trading-agent-benchmarks-2026.md new (AI Industry expansion; KTD-Fin/Strat-LLM/EarningsInOne synthesized; H376 fast/slow PEAD + H377 network momentum staged); dream cycle scan
- [Research Log 2026-07-05](trading/research-log/2026-07-05.md) — wiki: deep-rl-trading.md expanded (LambdaRankIC/FinRL-X/HMM-RL/ACM-survey; 4 x 2026 papers); dream cycle build phase: H370 LambdaRankIC stub + H371 HMM+RL stub applied; AutoRedTrader adversarial robustness wiki update
- [Research Log 2026-07-04](trading/research-log/2026-07-04.md) — wiki: quant-mind-notes.md new (QuantMind LLM knowledge extraction); dream cycle scan: H370 LambdaRankIC + H371 HMM-RL proposals staged; H364 CONFIRMED, H366 NOT CONFIRMED, H367-H369 stubs
- [Research Log 2026-07-03](trading/research-log/2026-07-03.md) — wiki: llm-finance-benchmarks-2026.md new (BacktestBench/PortBench/ReCAP/HMM-RL benchmarks); dream cycle scan
- [Research Log 2026-07-02](trading/research-log/2026-07-02.md) — H354 CONFIRMED (low-vol ETF rotation USMV/SPLV/XLU/SPHD/EFAV/EEMV/ACWV, pure 12m OOS 1.735, zero neg years); H355 CONFIRMED (OB filter H045 OOS 1.522, MaxDD halved); wiki: low-volatility-etf-rotation.md new
- [Research Log 2026-07-01](trading/research-log/2026-07-01.md) — wiki: auto-alpha-discovery.md new (AI-driven factor discovery taxonomy; H347/H349/H288/H352 queued); dream cycle scan
- [Research Log 2026-06-30](trading/research-log/2026-06-30.md) — wiki expansion + dream cycle; H362 CONFIRMED (low-vol ETF + VIX<20 gate OOS 1.819, MaxDD -8.0%); H363 NOT CONFIRMED (H354 as production satellite; all variants reduce OOS Sharpe from 3.708)
- [Research Log 2026-06-29](trading/research-log/2026-06-29.md) — wiki expansion + dream cycle scan; smart-money-concepts-ict.md new (H343-H346 Order Block family all confirmed; OB as implicit regime detector)
- [Research Log 2026-06-28](trading/research-log/2026-06-28.md) — wiki: ai-model-benchmarks.md expanded (PolyBench/PolySwarm/PredictionMarketBench); dream cycle: H185 Phase 2 PolySwarm design + PredictionMarketBench wiki + FactorEngine/FactorMiner/Hubble cluster applied
- [Research Log 2026-06-27](trading/research-log/2026-06-27.md) — wiki: performance-attribution.md new; 4 tool pages (ByteChef/OpenKnowledge/rust-trade/visual-plan); dream cycle scan
- [Research Log 2026-06-26](trading/research-log/2026-06-26.md) — wiki: prediction-markets/automated-pipeline.md new; Hitchhiker's Guide + Hyper-Extract ingested; dream cycle: AlphaCrafter/Headroom/sairahul1 applied
- [Research Log 2026-06-25](trading/research-log/2026-06-25.md) — wiki: merger-arbitrage-special-situations.md new; dream cycle scan; H338 NOT CONFIRMED (multi-asset trend+carry); H339 NOT CONFIRMED (price-based momentum gates)
- [Research Log 2026-06-24](trading/research-log/2026-06-24.md) — wiki: options-backtesting-methodology.md new; qf-lib/RustQuant/whchien-ai-trader tool pages; dream cycle scan; H337 NOT CONFIRMED; H336 NOT CONFIRMED
- [Research Log 2026-06-23](trading/research-log/2026-06-23.md) — wiki: strategy-blending-correlation.md new; dream cycle scan; H335 NOT CONFIRMED (bond momentum window); H334 NOT CONFIRMED (seasonality × momentum)
- [Research Log 2026-06-21](trading/research-log/2026-06-21.md) — H317 NOT CONFIRMED (multi-modal PEAD); H320 PARTIAL CONFIRMED (LightGBM crash filter, WF caveat); wiki: multi-agent-llm-trading.md + ts-foundation-models.md + awesome-quant-ai.md + ATLAS new; AI model landscape updated
- [Research Log 2026-06-20](trading/research-log/2026-06-20.md) — wiki: fixed-income-bond-rotation.md new (H045 PRODUCTION framework; carry FAILS; SHY dominates 72% OOS); dream cycle: H316 LLM pair selection, H317 multi-modal PEAD, H319 semantic network, H320 crash filter; H314/H315 NOT CONFIRMED
- [Research Log 2026-06-19](trading/research-log/2026-06-19.md) — wiki: spx-dispersion-variance.md new (H309 PARTIAL; implied corr premium 6-18pp; DSPX/COR3M signals; vega-neutral construction; Polygon IV path)
- [Research Log 2026-06-17](trading/research-log/2026-06-17.md) — wiki: risk-controls-and-monitoring.md new (3-tier circuit breakers; ATR sizing; correlation guard; kill switch); multi-agent-llm-trading.md (algorithms) expanded
- [Research Log 2026-06-16](trading/research-log/2026-06-16.md) — nightly: wiki: crypto-trading-strategies.md new (BTC MA Sharpe 1.9, cross-sectional Sharpe 1.51, funding carry declining); H302/H303 queued; dream cycle Phase 2 scan
- [Research Log 2026-06-15](trading/research-log/2026-06-15.md) — nightly: wiki: market-timing-overlays.md new; H298 NOT CONFIRMED (weekly ETF reversal); H299 NOT CONFIRMED (sector breadth); H300 NOT CONFIRMED (yield curve); H301 CONFIRMED (H026+200MA overlay, OOS 1.529)
- [Research Log 2026-06-13](trading/research-log/2026-06-13.md) — wiki: value-factors.md new; dream cycle: H293 press-release PEAD, H294 behavioral MLP, TS foundation models staged
- [Research Log 2026-06-12](trading/research-log/2026-06-12.md) — wiki: alternative-data.md new; multibagger-yartseva-2025.md ingested; dream cycle scan
- [Research Log 2026-06-11](trading/research-log/2026-06-11.md) — wiki: superforecasting-methods.md + execution-quality.md + ai-trader.md + contesttrade.md + quantmuse.md new; dream cycle scan
- [Research Log 2026-06-10](trading/research-log/2026-06-10.md) — wiki: multi-agent-llm-trading.md + quant-mind.md new; dream cycle scan
- [Research Log 2026-06-09](trading/research-log/2026-06-09.md) — wiki: volatility-risk-premium.md + shared-eval-checklist.md new; H266 VRP + H274 multi-agent PEAD staged
- [Research Log 2026-06-08](trading/research-log/2026-06-08.md) — wiki: crypto-data-sources.md + claude-code-video-toolkit.md + QuantStats + Kan new; dream cycle scan
- [Research Log 2026-06-07](trading/research-log/2026-06-07.md) — wiki: commodity-trend-following.md new; H257 CONFIRMED (multi-asset dual momentum); H261 NOT CONFIRMED (UNG MaxDD -78%); H261b CONFIRMED (OOS 0.922, Corr(SPY)=0.218); dream cycle: H262/signal-halflife/FinCall-Surprise applied
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
- [Prediction Arena (arXiv:2604.07355, 2026)](sources/prediction-arena-2026.md) — 57-day live eval of 6 AI models trading Kalshi/Polymarket with real capital; all lost on Kalshi; Polymarket avg −1.1% vs −22.6% on Kalshi; claude-opus-4-6 worst Polymarket performer in Cohort 2

**Concepts**
- [Impact Investing](concepts/impact-investing.md) — definition, key characteristics, risks, market context; distinguishes from SRI and philanthropy
- [Three-Dimensional Portfolio Framework](concepts/three-dimensional-portfolio-framework.md) — Impact/Return/Risk triangle; extends MPT; target zone, aggregate comparison

**People**
- [Yasemin Saltuk](people/yasemin-saltuk.md) — J.P. Morgan Social Finance lead researcher; impact investing research series

**Organizations**
- [J.P. Morgan Social Finance](orgs/jpmorgan-social-finance.md) — JPM unit est. 2007; proprietary capital + advisory + research

---

### General Tech

- [Stock Screener Methodology](trading/tools/stock-screener.md) — Minervini SEPA/CANSLIM criteria; IBD industry groups (relevant to H181); market breadth indicators; MCP integration candidate ← new 2026-05-27
- [zenbu.js](tools/zenbu.md) — JS framework for AI-agent-customizable desktop apps; local source, git-tracked, hot-reload; alpha
- [Dograh](tools/dograh.md) — self-hostable voice agent platform (open-source Vapi/Retell alternative); drag-and-drop workflows, bring-your-own LLM/TTS/STT, Docker deploy
- [mermaid-skill](tools/mermaid-skill.md) — Claude Code `/mermaid` skill; 23 diagram types, bundled syntax refs, weekly auto-sync from mermaid-js upstream ← 2026-05-27
- [Portless (vercel-labs)](tools/portless-notes.md) — replaces localhost port numbers with stable named .localhost URLs; ngrok/Tailscale/Funnel flags; designed for humans + AI agents ← new 2026-06-29
- [aie-talks (Yohei Nakajima)](tools/aie-talks-nakajima.md) — curated AI engineering talks site by BabyAGI creator; relevant to AIEWF 2026 (June 29–July 2 SF) agent infrastructure talks ← new 2026-06-29
- [ai-avatar-system](tools/ai-avatar-system.md) — real-time AI avatar platform; photo upload + 5s voice clone → lip-sync video; Claude/GPT-4/Llama, Whisper, MuseTalk, XTTS v2; MIT ← 2026-05-28

### AI Industry

- [The AI Decoupling](concepts/ai-decoupling.md) — vintagedata.org 2026; SaaS/AI ecosystem split; MoE economics, synthetic data moats, token pricing vs. enterprise CFO models; Chinese self-build alternative ← 2026-05-25
- [AI Model Landscape 2026](ai-industry/model-landscape-2026.md) — frontier model snapshot: GPT-5.5/Claude Opus 4.7/Gemini 3.1/Grok 4/DeepSeek V4 (Huawei Ascend); Claude Fable 5 export-ban lifted June 30 (restored July 1); Claude Sonnet 5 launched June 30 (63.2% SWE-bench Pro, $2/M intro); GPT-5.6 Sol/Terra/Luna in limited preview June 26; SpaceXAI/Cursor context ← updated 2026-06-21 (page needs refresh)
- [AI Agent Frameworks Ecosystem 2026](ai-industry/agent-frameworks-2026.md) — LangGraph (stateful/production), CrewAI (role-based multi-agent), AutoGen (maintenance mode), Agno, PydanticAI; architecture patterns; relevance to George's stack ← 2026-05-29
- [AI Infrastructure / Compute Layer 2026](ai-industry/ai-infrastructure-2026.md) — GPU cloud providers (Lambda/CoreWeave/RunPod/Vast.ai); H100/B200 pricing; vLLM/SGLang/TGI inference servers; cost structure for production LLM apps ← 2026-05-29
- [LLM Evaluation & Benchmarking for Finance 2026](ai-industry/llm-finance-benchmarks-2026.md) — CLQT closed-loop diagnostic benchmark; BacktestBench 18k QA pairs (LLMs fail strategy consistency); PortBench (90% fail vs equal-weight); reproducibility audit (0/19 R3); ReCAP regime-adaptive continual learning; HMM+RL allocation (Sharpe 1.68 vs 0.92 static); guidance on LLM vs deterministic split ← new 2026-07-03
- [LLM Trading Agent Benchmarks 2026](ai-industry/llm-trading-agent-benchmarks-2026.md) — KTD-Fin (arXiv:2605.28359; masking reveals LLM alpha = beta recall; Barra attribution), Strat-LLM (arXiv:2605.06024; regime-mode alignment; high-win-rate trap), EarningsInOne (arXiv:2606.29734; ECT qualitative signal peaks next day = tradeable; speed separation); unified LLM-in-trading value table; H376 implication ← new 2026-07-06
- [LLM Alpha Mining Systems 2026](ai-industry/llm-alpha-mining-systems-2026.md) — AlphaLogics (arXiv:2603.20247; market-logic-driven multi-agent, S&P500 validated, H381); FactorEngine (arXiv:2603.16365; program-level dual-mode LLM+BayesHPO, knowledge-infused bootstrap, H382); Cross-Market Alpha191→US (arXiv:2601.06499; 17/168 survive LASSO on S&P500, H380); ReCAP continual learning (arXiv:2606.00143, H384); HMM+RL regime allocation (arXiv:2605.27848, H383); LLM roles in factor mining vs portfolio allocation dichotomy ← new 2026-07-07

---

### Disaster Recovery

- [DR Overview](dr/overview.md) — restore procedure, what survives, what to tell a fresh George
- [Git Backup Setup](dr/git-backup.md) — git repo config, current status, blocked items
- [Session Diary](dr/diary.md) — append-only log of sessions; narrative recovery layer

