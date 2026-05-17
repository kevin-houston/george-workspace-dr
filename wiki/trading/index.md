---
updated: 2026-05-17 (calendar-anomalies.md added)
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
  - [Momentum Strategies](algorithms/momentum-strategies.md) ← updated 2026-05-14 (H198 CONFIRMED: 6-1m stock momentum OOS Sharpe 1.174; H199 NOT CONFIRMED; H197 behavioral momentum QUEUED)
  - [Pairs Trading / Stat Arb](algorithms/pairs-trading.md) ← updated 2026-05-15 (ETF pairs EXHAUSTED H152-H160; H200 QUEUED — graphical matching stock-level pairs, arXiv:2403.07998, Sharpe 1.23 on S&P 500 2017–2023)
  - [Event-Driven Strategies](algorithms/event-driven.md) ← updated 2026-05-05 (H163 **CONFIRMED** — FinBERT NLP signal real; H161/H162 PARTIAL CONFIRMED; H168 IN-PROGRESS)
  - [Short-Term Reversal](algorithms/short-term-reversal.md) ← new 2026-05-07 (industry-adjusted reversal 0.53%/month globally; SSRN:6630998; H181 queued)
  - [Options Income Strategies](algorithms/options-income-strategies.md) ← 2026-05-05 (iron condor, CSP/Wheel, covered calls, VRP harvesting; H162 PARTIAL CONFIRMED; LEAN integration)
  - [Low-Volatility Anomaly](algorithms/low-volatility.md) ← updated 2026-05-13 (confirmed results H190–H196; BAB dominates Sharpe 1.367; H190 Pareto improvement; STORM closed; research line complete)
  - [BSM & Information Geometry](algorithms/bsm-information-geometry.md) ← 2026-04-28 (Dean 2026: smile = manifold curvature; skew prediction within 19% zero free params; LEAPS trading implications)
  - [Deep RL for Trading](algorithms/deep-rl-trading.md) ← new 2026-05-16 (FinRL/stable-baselines3 framework; PPO/DDPG/TD3; gym environment design; honest OOS benchmarks; H204 queued — PPO vs H198 momentum baseline)
  - [Calendar Anomalies](algorithms/calendar-anomalies.md) ← new 2026-05-17 (H201 CONFIRMED TOM Sharpe 0.740; Halloween/FOMC/Jan/Weekend/EOQ; H205-H208 candidates; composite calendar strategy)
- [Tools](tools/) — open-source libraries (Qlib, Backtrader, Vectorbt, etc.)
  - [Qlib Deep Dive](tools/qlib.md) ← expanded 2026-04-28 (architecture, model zoo, benchmarks, RD-Agent)
  - [Backtrader vs Vectorbt](tools/backtrader-vs-vectorbt.md) ← expanded 2026-04-29 (H116 rotation in Vectorbt, `Portfolio.from_orders` multi-asset pattern)
  - [Kraken CLI](tools/kraken-cli.md) ← expanded 2026-05-01 (all 50 agent skills, MCP service groups, full command reference)
  - [NLP & Alternative Data](tools/nlp-alternative-data.md) ← updated 2026-05-13 (FinBERT transcript benchmark arXiv:2503.01886; yiyanghkust/finbert-tone recommended for earnings calls)
  - [Machine Learning for Trading](tools/ml-for-trading.md) ← updated 2026-05-13 (MASFIN multi-agent debate framework arXiv:2512.21878; 31% drawdown reduction vs single-agent LLM)
  - [LEAN / QuantConnect](tools/lean-quantconnect.md) ← updated 2026-05-15 (Alpaca live trading bridge added — brokerage config, CLI, Phase 3→4 gate; walk-forward optimization section; H007 pending Docker approval)
  - [OpenAlgo](tools/openalgo.md) ← 2026-04-25 (India-only for now; watch for Alpaca/Kraken support in 2026)
  - [Portfolio Optimization](tools/portfolio-optimization.md) ← new 2026-05-16 (PyPortfolioOpt v1.6.0, Riskfolio-Lib v7.2.1, skfolio v0.20.1; HRP, risk parity, NCO, walk-forward CV; strategy blending code for H026+BAB+MOM+TOM)
- [Data Sources](data-sources/) — market data, fundamentals, alt data
  - [Alpaca Markets — Complete Reference](data-sources/alpaca.md) ← new 2026-05-12 (full SDK reference: order types, TIF, WebSocket streams, PDT/IDTBP update, Phase 3→4 checklist)
  - [Alpaca Automation Guide](data-sources/alpaca-automation.md) ← new 2026-04-27 (Phase 3 foundation)
  - [Polygon.io](data-sources/polygon.md) ← expanded 2026-04-28 (API endpoints, WebSocket, pricing, vs Alpaca)
  - [Free / Low-Cost Sources](data-sources/free-data.md) ← expanded 2026-04-28 (Tiingo, EDGAR, Finnhub, FRED, yfinance status)
  - [Sector & Industry Classification](data-sources/sector-classification.md) ← new 2026-05-08 (GICS/SIC sources for H181; SEC EDGAR SIC, GitHub S&P 500 CSV, yfinance caveats, practical build_sector_cache() for 100-500 stocks)
  - [Options Data Sources](data-sources/options-data.md) ← 2026-05-01 (ThetaData/ORATS/FlashAlpha pricing; Alpaca indicative feed; vollib/py_vollib/QuantLib; IV surface + SVI fitting; free EOD options data on GitHub)
- [Prediction Markets](prediction-markets/) — Kalshi, Polymarket, etc.
  - [Kalshi](prediction-markets/kalshi.md) ← expanded 2026-04-29 (full auth/API/WebSocket, RSA signing, CPI nowcasting implementation, fee modeling, rate limits, Timeless perps)
  - [Algorithmic Strategies](prediction-markets/algorithmic-strategies.md) ← updated 2026-05-13 (PolyBench arXiv:2604.14199 — LLMs near-random on binary markets; edge only on economic data + structured context)
  - [Other Platforms](prediction-markets/other-platforms.md) ← expanded 2026-05-02 (IBKR ForecastTrader full API, Kalshi Timeless mechanics, emerging platforms)
  - [Polymarket](prediction-markets/polymarket.md) ← 2026-04-29 (full CLOB API, Ethereum auth, order placement, WebSocket streaming, fee comparison vs Kalshi, cross-platform arb scanner)
- [Backtesting](backtesting/) — setup, results, methodology
  - [Design Principles](backtesting/design-principles.md) ← expanded 2026-05-05 (IS/OOS framework, bias taxonomy, confirmation criteria, deflated Sharpe, López de Prado)
  - [Walk-Forward & CPCV](backtesting/walk-forward-cpcv.md) ← new 2026-05-07 (WFO variants, CPCV algorithm, purging/embargoing, DSR formulas, Python libs: timeseriescv/skfolio/mlfinlab, when to use what)
  - [Transaction Cost Modeling](backtesting/transaction-costs.md) ← new 2026-05-09 (spread/impact/borrow models, square-root MI, vectorbt/backtrader defaults, per-strategy calibration table)
- [Paper Trading](paper-trading/) — Alpaca results log
  - [H149 Alpaca ETF Rotation](paper-trading/h122-alpaca.md) ← active (100% H026, $102k paper)
  - [PEAD-NLP Alpaca Deployment](paper-trading/pead-nlp-alpaca.md) ← new 2026-05-06 (H163/H174 live pipeline: gap detection, 8-K scoring, OPG orders)
- [Research Log](research-log/) — nightly research summaries
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
