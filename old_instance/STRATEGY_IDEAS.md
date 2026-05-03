# Trading Strategy Ideas — Research Compendium
**Generated: 2026-04-02**
**Purpose:** Catalog of strategies NOT yet backtested in the claws framework, organized by category for future evaluation rounds.

Strategies already tested (see MASTER_REPORT.md) are excluded: PEAD, pairs trading (z-score), RSI mean reversion, VIX mean reversion, crypto momentum, dual momentum ETF, momentum factor 6-1, UPRO/IEF leverage, oil/energy macro overlay, ETF sector rotation, covered calls, bull put spreads, iron condors, wheel strategy, VRP harvest, gamma scalping, VIX short puts, commodity seasonals, risk parity, Dogs of the Dow, dividend raise signal, dividend capture, ML ensemble (RF/XGB/GBM/logistic), LLM signal filtering.

---

## Table of Contents
1. [Momentum / Trend Following / Breakout](#1-momentum--trend-following--breakout)
2. [Mean Reversion / Statistical Arbitrage](#2-mean-reversion--statistical-arbitrage)
3. [Market Microstructure](#3-market-microstructure)
4. [Event-Driven](#4-event-driven)
5. [Fundamental / Value](#5-fundamental--value)
6. [Alternative Data](#6-alternative-data)
7. [Volatility / Derivatives](#7-volatility--derivatives)
8. [Options Structures](#8-options-structures)
9. [ML / AI](#9-ml--ai)
10. [Crypto / DeFi](#10-crypto--defi)

---

## 1. Momentum / Trend Following / Breakout

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 1 | **Time-Series Momentum (TSMOM)** | Goes long assets with positive recent returns and short those with negative, applied across futures. Captures return persistence over 1-12 month horizons. Foundational paper by Moskowitz, Ooi & Pedersen. | [SSRN](https://pages.stern.nyu.edu/~lpederse/TimeSeriesMomentum.pdf) |
| 2 | **52-Week High Momentum** | Buys stocks near their 52-week high and sells those far from it. Exploits anchoring bias — investors underreact when prices are near historical extremes. George & Hwang (2004). | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1104491) |
| 3 | **Analyst Revision Momentum** | Buys stocks with upward analyst estimate revisions, shorts those with downward. Revision breadth and magnitude both predict returns as information diffuses across the market. | [Investopedia](https://www.investopedia.com/terms/e/estimaterevision.asp) |
| 4 | **Insider Buying Momentum** | Tracks clusters of legal insider purchases (SEC Form 4) to identify positive private-information signals. Heavy insider buying over 1-3 months predicts outperformance, especially in small caps. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1364810) |
| 5 | **Cross-Asset Momentum** | Applies momentum across equities, bonds, commodities, and currencies simultaneously. Diversification across asset classes reduces crash risk inherent in single-asset momentum. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2363911) |
| 6 | **Managed Futures / CTA-Style Trend Following** | Trades long/short across 50+ futures markets using MA crossover or breakout signals at multiple timeframes. Core strategy of large CTAs (Man AHL, Winton). Tends to perform well in crises due to convex payoff. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2993026) |
| 7 | **Turtle Trading (Donchian Breakout)** | Richard Dennis system: enter on 20d or 55d Donchian channel breakouts with ATR position sizing and trailing stops. One of the first systematized trend-following approaches. | [Investopedia](https://www.investopedia.com/articles/trading/08/turtle-trading.asp) |
| 8 | **Bollinger Band Squeeze Breakout** | Identifies low-vol periods when Bollinger Bands contract ("squeeze") and trades the directional breakout. Compression signals consolidation; expansion often leads to strong moves. | [Investopedia](https://www.investopedia.com/articles/trading/05/boltinger.asp) |
| 9 | **Adaptive Moving Average (KAMA)** | Perry Kaufman's AMA adjusts smoothing speed based on market noise via the efficiency ratio. Reduces whipsaws in ranging markets while staying responsive during trends. | [Investopedia](https://www.investopedia.com/terms/k/kaufmanefficiency-ratio.asp) |
| 10 | **Meb Faber Tactical Asset Allocation** | 10-month SMA timing rule across diversified asset classes (US/intl stocks, bonds, REITs, commodities). Reduces drawdowns substantially vs buy-and-hold while capturing most upside. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461) |
| 11 | **Commodity Carry + Momentum** | Combines roll yield (carry) and price momentum to trade commodity futures. Carry captures term structure signal; momentum captures trend. Together more robust than either alone. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1720856) |
| 12 | **Currency Momentum** | Long currencies with recent appreciation, short those with depreciation over 1-12 month lookbacks. Distinct from carry trade; provides diversification when combined with rate-differential strategies. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1809776) |
| 13 | **Opening Range Breakout (ORB)** | Trades intraday breakouts above/below the high/low of the first 15-30 minutes. Popularized by Toby Crabel — early-session range expansion predicts the day's directional bias. | [Investopedia](https://www.investopedia.com/terms/o/openingrange.asp) |
| 14 | **Hurst Exponent Regime Detection** | Uses the Hurst exponent to classify trending (H > 0.5) vs mean-reverting (H < 0.5) regimes. Only applies trend signals when regime favors persistence, reducing whipsaw losses. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3400552) |
| 15 | **Industry/Sector Momentum** | Ranks industries by recent returns; long top, short laggards. Moskowitz & Grinblatt (1999) showed much of stock momentum is explained by industry momentum — a more concentrated signal. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=141370) |
| 16 | **Risk Parity with Trend Filter** | Inverse-vol allocation (risk parity) with a trend overlay — move to cash when an asset is in downtrend. Combines diversification of risk parity with drawdown protection from trend signals. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2126478) |
| 17 | **Residual Momentum (iMom)** | Sorts stocks on momentum in idiosyncratic returns after stripping factor exposures. More persistent, less volatile, and avoids the severe crashes of conventional momentum. Blitz et al. (2011). | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2319861) |
| 18 | **VRP Momentum Overlay** | Harvests the implied-vs-realized vol spread but adds a momentum timing layer — fully allocated when VRP is wide and trending, reduced when spread compresses. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2497759) |

---

## 2. Mean Reversion / Statistical Arbitrage

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 19 | **Ornstein-Uhlenbeck Mean Reversion** | Models prices as a continuous-time stochastic process reverting to a long-run mean. Provides rigorous framework for estimating reversion speed and equilibrium price for pairs/single-asset signals. | [Wikipedia](https://en.wikipedia.org/wiki/Ornstein%E2%80%93Uhlenbeck_process) |
| 20 | **Bollinger Band Mean Reversion** | Enters when price touches/breaches Bollinger Bands (2 SD from MA), exits at mean. One of the most widely used mean-reversion frameworks across asset classes. | [Investopedia](https://www.investopedia.com/terms/b/bollingerbands.asp) |
| 21 | **Cointegration-Based Basket Trading** | Constructs a basket of securities whose linear combination is stationary, then trades deviations. More stable hedge ratios and better diversification than simple pairs trading. | [Wikipedia](https://en.wikipedia.org/wiki/Cointegration) |
| 22 | **ETF/NAV Arbitrage** | Exploits price discrepancies between an ETF's market price and its real-time net asset value (iNAV). Buy the cheap side, sell the expensive side as prices converge. | [Investopedia](https://www.investopedia.com/terms/e/etf-arbitrage.asp) |
| 23 | **Index Arbitrage** | Trades the spread between index futures and the underlying cash basket. When futures deviate from theoretical fair value (cost-of-carry), buy undervalued / sell overvalued. | [Investopedia](https://www.investopedia.com/terms/i/indexarbitrage.asp) |
| 24 | **Convertible Arbitrage** | Long convertible bond, short underlying equity to isolate mispricing of the embedded option. Captures credit spread, volatility, and gamma with dynamic delta hedging. | [Investopedia](https://www.investopedia.com/terms/c/convertiblearbitrage.asp) |
| 25 | **Dispersion Trading** | Sells index options, buys single-stock options. Profits when realized correlation among components is lower than implied by index option prices — harvests the correlation risk premium. | [Wikipedia](https://en.wikipedia.org/wiki/Dispersion_trading) |
| 26 | **Correlation Trading** | Directly trades correlation via variance swaps, correlation swaps, or structured option positions. Profits from the tendency of implied correlation to overstate realized correlation. | [Investopedia](https://www.investopedia.com/terms/c/correlationcoefficient.asp) |
| 27 | **PCA Eigenportfolio Stat Arb** | Uses principal component analysis to decompose returns into factors, then trades residual mispricings. Long-short portfolios orthogonal to dominant market factors. | [Wikipedia](https://en.wikipedia.org/wiki/Principal_component_analysis#Finance) |

---

## 3. Market Microstructure

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 28 | **Avellaneda-Stoikov Market Making** | Optimal market-making model placing limit orders on both sides, dynamically adjusting quotes based on inventory risk and asset volatility. Maximizes P&L while penalizing inventory accumulation. | [NYU Paper](https://math.nyu.edu/~avellane/HighFrequencyTrading.pdf) |
| 29 | **Order Flow Imbalance (OFI) Trading** | Measures net buy vs sell pressure at the top of the limit order book to predict short-term price moves. Persistent excess buy volume signals upward pressure and vice versa. | [Wikipedia](https://en.wikipedia.org/wiki/Order_flow_trading) |
| 30 | **LOB Queue Position Strategy** | Exploits informational content of queue position and depth at various price levels. Early queue priority at favorable prices + monitoring book shape anticipates short-term moves. | [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0927539813000649) |
| 31 | **VPIN (Volume-Synchronized Probability of Informed Trading)** | Estimates informed trading probability in real time using volume clocks. High VPIN signals toxic order flow and elevated adverse selection — widen quotes or reduce exposure. | [Wikipedia](https://en.wikipedia.org/wiki/VPIN) |
| 32 | **Latency Arbitrage** | Exploits timing differences across venues by acting on stale quotes before they update. Core HFT strategy relying on microsecond speed advantages and colocation. | [Wikipedia](https://en.wikipedia.org/wiki/Latency_arbitrage) |
| 33 | **Kyle's Lambda / Price Impact Trading** | Uses Kyle (1985) model to estimate price impact per unit of order flow. Trade when lambda is low (cheap to move size), abstain when impact costs are high. | [Wikipedia](https://en.wikipedia.org/wiki/Kyle%27s_lambda) |

---

## 4. Event-Driven

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 34 | **Spin-Off Investing** | Spun-off companies tend to outperform over 1-2 years due to forced selling by index funds, analyst neglect, and focused management with aligned incentives. | [Investopedia](https://www.investopedia.com/articles/investing/073115/spin-offs-what-are-they-and-how-invest-them.asp) |
| 35 | **Index Rebalancing Effect** | When stocks are added to/removed from major indices, passive funds must buy/sell, creating predictable short-term price pressure. Front-run additions, fade removals. | [Investopedia](https://www.investopedia.com/terms/i/index-effect.asp) |
| 36 | **Share Buyback Announcement Drift** | Stocks announcing repurchase programs outperform over 6-12 months — buybacks signal management confidence in undervaluation. Strongest for value stocks with high completion rates. | [Investopedia](https://www.investopedia.com/articles/02/041702.asp) |
| 37 | **Activist Investor Following (13D Filings)** | Take positions in activist targets (13D filings). Activist stakes typically cause 5-7% immediate pop with further gains if the campaign succeeds (board seats, operational changes). | [Investopedia](https://www.investopedia.com/terms/a/activist-investor.asp) |
| 38 | **IPO Lock-Up Expiration** | IPO insiders can't sell for 90-180 days. As lock-up expiration approaches, anticipated supply increase creates predictable downward pressure — short-selling opportunity. | [Investopedia](https://www.investopedia.com/terms/l/lockup-period.asp) |
| 39 | **Secondary Offering Effect** | Secondary offerings typically cause 2-4% decline from dilution. Mean-reversion traders buy the dip if proceeds fund growth rather than insider exits. | [Investopedia](https://www.investopedia.com/terms/s/secondaryoffering.asp) |
| 40 | **Credit Rating Change Trading** | Upgrades/downgrades create tradable moves in equities and bonds. Downgrades to junk are especially impactful — forced institutional selling of non-investment-grade bonds creates dislocations. | [Investopedia](https://www.investopedia.com/terms/c/creditrating.asp) |
| 41 | **FDA Approval Trading (PDUFA Dates)** | Trade biotech/pharma around FDA decision dates. Stocks can move 30-100% on approval/rejection. Strategies include pre-event positioning or selling vol premium after the binary resolves. | [Investopedia](https://www.investopedia.com/terms/p/pdufa.asp) |
| 42 | **Patent Cliff Strategy** | Short pharma companies approaching key patent expiry without a strong pipeline; long generic manufacturers poised to capture market share. | [Investopedia](https://www.investopedia.com/terms/p/patent-cliff.asp) |
| 43 | **Short Squeeze Detection** | Identify stocks with very high short interest, rising borrow costs, and improving fundamentals. Forced covering creates rapid upward dislocations that momentum traders exploit. | [Investopedia](https://www.investopedia.com/terms/s/shortsqueeze.asp) |
| 44 | **Distressed Debt / Bankruptcy Emergence** | Buy equity or debt of companies emerging from Chapter 11. Post-emergence equities are mispriced because new shares go to former creditors who may not want equity exposure. | [Investopedia](https://www.investopedia.com/terms/d/distressedsecurities.asp) |

---

## 5. Fundamental / Value

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 45 | **13F Filing Replication** | Replicate top hedge fund managers' highest-conviction long positions from quarterly SEC 13F filings. Despite 45-day delay, elite manager picks still generate alpha. | [Investopedia](https://www.investopedia.com/terms/f/form-13f.asp) |
| 46 | **SEC Filing NLP (8-K / 10-K Parsing)** | NLP on SEC filings to detect risk factor changes, tone shifts between consecutive 10-Ks, or abnormal language complexity (correlated with obfuscation of bad news). Predicts future returns. | [Investopedia](https://www.investopedia.com/terms/1/10-k.asp) |
| 47 | **Conference Call Tone Analysis** | Sentiment/vocal analysis of earnings call transcripts. Evasive language and negative tone shifts in Q&A (vs prepared remarks) predict negative earnings surprises and stock declines. | [Investopedia](https://www.investopedia.com/terms/e/earnings-call.asp) |

---

## 6. Alternative Data

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 48 | **Satellite Imagery (Parking Lots / Oil Tanks)** | Satellite images of retail parking lots estimate foot traffic before earnings; oil tank shadow lengths estimate crude inventory. Physical-world edge days/weeks ahead of official reports. | [Investopedia](https://www.investopedia.com/terms/a/alternative-data.asp) |
| 49 | **Credit Card Transaction Signals** | Aggregated anonymized card transaction data from payment processors nowcasts company revenue in near-real-time. Millions of consumers allow estimation of same-store sales before earnings. | [NBER](https://www.nber.org/papers/w26483) |
| 50 | **Social Media Sentiment (Reddit/Twitter/StockTwits)** | NLP on retail platforms — mention volume, sentiment polarity, unusual spikes. The GameStop/WSB episode demonstrated the alpha and risk in these signals. | [arXiv](https://arxiv.org/abs/2105.09404) |
| 51 | **Google Trends Momentum** | Search volume for financially relevant queries (ticker symbols, "recession") proxies retail attention. Rising search interest predicts short-term price moves and increased volatility. | [Nature](https://www.nature.com/articles/srep01684) |
| 52 | **Congressional Trading (STOCK Act)** | Track disclosed trades by US Congress members. Studies show statistically significant abnormal returns from mimicking these trades — informational advantage from policy knowledge. | [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3555234) |
| 53 | **Options Flow / Unusual Activity** | Monitor real-time options flow for unusual volume, large blocks, aggressive sweeps indicating informed positioning ahead of catalysts. Filter by size, delta, expiry. | [CBOE](https://www.cboe.com/insights/posts/options-order-flow-as-predictive-signal/) |
| 54 | **Shipping / AIS Data Trading** | Track global vessel movements via AIS transponders to estimate commodity flows, trade volumes, port congestion in real time. Useful for commodities and macro before official data. | [NBER](https://www.nber.org/papers/w28910) |
| 55 | **Web Traffic / App Usage Scraping** | Track website visits (SimilarWeb) or app downloads to estimate revenue before earnings. Sharp increase in e-commerce traffic can predict revenue beat. | [Investopedia](https://www.investopedia.com/terms/a/alternative-data-providers.asp) |
| 56 | **News Sentiment NLP (Real-Time)** | NLP on live news feeds to quantify article tone and extract event signals faster than humans. Ranges from sub-second headline reaction to multi-day aggregated sentiment scoring. | [Investopedia](https://www.investopedia.com/terms/n/natural-language-processing-nlp.asp) |

---

## 7. Volatility / Derivatives

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 57 | **Variance Swap** | Pays the difference between realized variance and a fixed strike. Pure exposure to realized vol without delta-hedging complications. | [Investopedia](https://www.investopedia.com/terms/v/varianceswap.asp) |
| 58 | **Volatility Skew Trading** | Trades IV differences between OTM puts and OTM calls (the skew). Profit when skew reverts to historical norms using verticals or risk reversals. | [Options Education](https://www.optionseducation.org/advancedconcepts/volatility-skew) |
| 59 | **VIX Futures Term Structure (Roll Yield)** | Exploits persistent contango in VIX futures by shorting front-month / longing back-month. Profits from roll yield as futures converge to spot VIX. | [CBOE](https://www.cboe.com/tradable_products/vix/vix_futures/) |
| 60 | **Volatility Surface Arbitrage** | Identifies mispricings across the IV surface (strike + tenor). Trade option combos where market-implied local vols violate no-arbitrage conditions. | [ScienceDirect](https://www.sciencedirect.com/topics/economics-econometrics-and-finance/volatility-surface) |
| 61 | **Systematic Volatility Risk Premium Carry** | Systematically sell delta-hedged options or variance swaps to harvest the persistent implied-vs-realized spread. Insurance-like carry with periodic large drawdowns. | [AQR](https://www.aqr.com/Insights/Research/Journal-Article/Volatility-Managed-Portfolios) |
| 62 | **Convexity (Long Volatility) Strategy** | Buy straddles/strangles, dynamically delta-hedge to profit from realized vol exceeding implied. Convex payoffs benefit from large moves regardless of direction. | [Investopedia](https://www.investopedia.com/terms/l/long-straddle.asp) |
| 63 | **Tail Risk Hedging (Systematic)** | Allocate a small % to deep OTM puts or VIX calls for crash protection. Persistent drag on returns but convex payoffs during crashes. Portfolio-level, not standalone. | [Investopedia](https://www.investopedia.com/terms/t/tailrisk.asp) |
| 64 | **CBOE BuyWrite Index (BXM)** | Hold S&P 500, systematically write ATM monthly calls. Historically delivers lower volatility and competitive risk-adjusted returns vs index alone. | [CBOE](https://www.cboe.com/products/strategy-benchmark-indexes/buywrite-indexes/cboe-s-p-500-buywrite-index-bxm) |
| 65 | **CBOE PutWrite Index (PUT)** | Systematically sell ATM S&P 500 puts collateralized by T-bills. Harvests VRP with historically favorable risk-adjusted returns and lower drawdowns than equities. | [CBOE](https://www.cboe.com/products/strategy-benchmark-indexes/putwrite-indexes/cboe-s-p-500-putwrite-index-put) |
| 66 | **VIX Call Spread (Tail Hedge)** | Buy VIX calls, sell further OTM VIX calls. More cost-efficient than outright VIX calls for hedging portfolio drawdowns during market stress. | [CBOE](https://www.cboe.com/tradable_products/vix/vix_options/) |

---

## 8. Options Structures

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 67 | **Calendar Spread (Horizontal)** | Sell near-term option, buy longer-dated at same strike. Profit from faster time decay of short leg. Benefits from stable prices and rising IV. | [Investopedia](https://www.investopedia.com/terms/c/calendarspread.asp) |
| 68 | **Diagonal Spread** | Options at different strikes AND expirations — directional bias with time-decay benefit. Often used as a modified covered call without owning shares. | [Investopedia](https://www.investopedia.com/terms/d/diagonalspread.asp) |
| 69 | **Jade Lizard** | Sell OTM put + OTM call spread for net credit exceeding call spread width. Eliminates upside risk entirely while retaining downside risk similar to a short put. | [tastylive](https://www.tastylive.com/concepts-strategies/jade-lizard) |
| 70 | **Broken Wing Butterfly** | Asymmetric butterfly where one wing is wider, creating net credit. Wide profit zone on one side with limited risk — directional-neutral income strategy. | [tastylive](https://www.tastylive.com/concepts-strategies/broken-wing-butterfly) |
| 71 | **Ratio Spread** | Buy one option, sell multiple at different strike. Can be zero cost or credit, but introduces naked exposure on extra short contracts. | [Investopedia](https://www.investopedia.com/terms/r/ratiospread.asp) |
| 72 | **Risk Reversal** | Buy OTM call, sell OTM put (or vice versa). Synthetic directional position; also used to express views on IV skew between puts and calls. | [Investopedia](https://www.investopedia.com/terms/r/riskreversal.asp) |
| 73 | **Collar Strategy** | Hold stock + buy protective put + sell covered call to offset put cost. Caps both upside and downside — popular for concentrated stock hedging. | [Investopedia](https://www.investopedia.com/terms/c/collar.asp) |
| 74 | **Iron Butterfly** | Sell ATM straddle + buy OTM wings. Like iron condor but short strikes at same price — higher premium, narrower profit zone. | [Investopedia](https://www.investopedia.com/terms/i/ironbutterfly.asp) |
| 75 | **Short Strangle** | Sell OTM put + OTM call simultaneously. Profits when underlying stays in range. Undefined risk on both sides if moves are large. | [Investopedia](https://www.investopedia.com/terms/s/strangle.asp) |
| 76 | **0DTE (Zero Days to Expiration)** | Trade options on expiration day to exploit extreme theta decay and gamma. Sell iron condors or credit spreads intraday for rapid premium capture with same-day resolution. | [CBOE](https://www.cboe.com/insights/posts/growth-in-0dte-options/) |
| 77 | **Ratio Put Backspread** | Sell one ATM put, buy multiple OTM puts. Unlimited downside profit potential — crash protection that can be established for small credit or zero cost. | [Investopedia](https://www.investopedia.com/terms/r/ratio-put-backspread.asp) |
| 78 | **Poor Man's Covered Call (PMCC)** | Replace stock with deep ITM LEAPS call, sell short-term OTM calls against it. Mimics covered call with far less capital — leveraged income generation. | [Investopedia](https://www.investopedia.com/terms/p/pmcc-poor-mans-covered-call.asp) |

---

## 9. ML / AI

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 79 | **LSTM Price Prediction** | Long Short-Term Memory recurrent neural networks capture temporal dependencies in price series. Learns to retain/forget info over variable horizons — well-suited for sequential financial data. | [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0957417420302621) |
| 80 | **Transformer-Based Forecasting** | Self-attention mechanism weighs relevance of all past timesteps simultaneously rather than sequentially. Often outperforms RNNs on longer sequences in financial time series. | [arXiv](https://arxiv.org/abs/2106.12950) |
| 81 | **Reinforcement Learning Portfolio Optimization** | RL agent (PPO, DDPG) learns position-sizing and allocation by maximizing risk-adjusted reward. Learns policy directly from market state without explicit price prediction. | [arXiv](https://arxiv.org/abs/1907.03665) |
| 82 | **FinBERT / NLP Sentiment Models** | Fine-tuned BERT models for finance-specific language applied to news, earnings calls, analyst reports. Extracts sentiment scores as alpha signals. | [arXiv](https://arxiv.org/abs/1908.10063) |
| 83 | **Graph Neural Networks (Supply Chain Alpha)** | Models inter-company relationships (supplier/customer/competitor) as a graph. GNNs propagate earnings surprise or momentum through the network, capturing lead-lag effects. | [arXiv](https://arxiv.org/abs/2201.01286) |
| 84 | **Autoencoder Anomaly Detection** | Trained on normal regime data; abnormal conditions produce high reconstruction error. Flags regime changes, dislocations, or mean-reversion opportunities when market deviates from learned patterns. | [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0925231220300606) |
| 85 | **GAN Synthetic Data Augmentation** | GANs produce realistic synthetic market data for training, addressing chronic sample shortage in financial ML. Reduces overfitting and improves robustness in backtesting. | [arXiv](https://arxiv.org/abs/1907.06673) |
| 86 | **Temporal Fusion Transformer** | Multi-horizon attention model combining static covariates, known future inputs, and observed time series with interpretable attention weights. Provides predictions AND feature importance. | [arXiv](https://arxiv.org/abs/1912.09363) |

---

## 10. Crypto / DeFi

| # | Strategy | Description | Reference |
|---|----------|-------------|-----------|
| 87 | **DEX Arbitrage** | Exploit price discrepancies for the same token across decentralized exchanges (Uniswap, SushiSwap, Curve) or between pools. Executed atomically in a single transaction — zero inventory risk. | [arXiv](https://arxiv.org/abs/2101.05511) |
| 88 | **MEV Extraction (Maximal Extractable Value)** | Capture value from transaction ordering within a block — sandwich attacks, backrunning, liquidation sniping. Searchers compete via Flashbots for profitable bundles. | [arXiv](https://arxiv.org/abs/2101.05511) |
| 89 | **Funding Rate Arbitrage** | Long spot + short perps (or vice versa) when perpetual futures funding rates are elevated. Delta-neutral carry trade earning the funding differential. | [Paradigm](https://www.paradigm.xyz/2021/05/everlasting-options) |
| 90 | **On-Chain Analytics (Whale Watching)** | Monitor blockchain for large wallet movements, exchange inflows/outflows, smart contract interactions. Token surge to exchanges often precedes sell-off; outflows signal accumulation. | [Glassnode](https://glassnode.com/insights/on-chain-signals) |
| 91 | **Cross-Chain Arbitrage** | Exploit price differences for the same asset across blockchains (e.g., ETH on Ethereum vs wrapped ETH on Arbitrum/Solana). Profits depend on bridge speed and fees. | [arXiv](https://arxiv.org/abs/2112.01472) |

---

## Priority Recommendations for Next Backtest Rounds

Based on data availability, implementation feasibility, and expected edge, these are the highest-priority strategies to evaluate next:

### Tier 1 — High Priority (data available, clear signal, backtestable)
| Strategy | Why |
|----------|-----|
| Share Buyback Announcement Drift (#36) | Event dates from SEC, similar to PEAD mechanism |
| Index Rebalancing Effect (#35) | Predictable dates, mechanical flow signal |
| 52-Week High Momentum (#2) | Simple price signal, easy to backtest |
| Residual Momentum / iMom (#17) | Academically robust improvement on existing momentum factor |
| Congressional Trading (#52) | Public data (STOCK Act), documented alpha |
| Meb Faber TAA (#10) | Simple SMA rule, multi-asset, data available |
| CBOE PutWrite Index replication (#65) | Benchmark exists, can compare directly |
| Insider Buying Momentum (#4) | SEC Form 4 data available |
| 0DTE Strategies (#76) | Rapidly growing market, extreme theta/gamma dynamics |
| Funding Rate Arbitrage (#89) | Exchange API data, clear carry signal |

### Tier 2 — Medium Priority (some data friction, promising edge)
| Strategy | Why |
|----------|-----|
| Spin-Off Investing (#34) | Requires event identification, but well-documented anomaly |
| Time-Series Momentum / TSMOM (#1) | Needs multi-asset futures data |
| Dispersion Trading (#25) | Requires single-stock options data |
| Activist Investor Following (#37) | 13D filing data, strong short-term returns |
| Conference Call Tone Analysis (#47) | Transcript data increasingly available |
| Google Trends Momentum (#51) | Free data, documented signal |
| Calendar Spread (#67) | Needs options chain history |
| IPO Lock-Up Expiration (#38) | Event dates findable, mechanical selling pressure |

### Tier 3 — Longer Term (infrastructure/data intensive)
| Strategy | Why |
|----------|-----|
| Satellite Imagery (#48) | Expensive data, complex pipeline |
| DEX/MEV Arbitrage (#87, #88) | Requires on-chain infrastructure |
| LSTM/Transformer Models (#79, #80) | GPU training, risk of overfitting |
| Market Microstructure (#28-33) | Requires tick-level data and ultra-low latency |
| Credit Card Transaction Data (#49) | Expensive vendor data |

---

**Total strategies cataloged: 91**
**Categories covered: 10**
**Already tested (MASTER_REPORT.md): ~35 strategy variants**
**Net new ideas: 91**
