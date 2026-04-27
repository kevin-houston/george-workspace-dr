---
updated: 2026-04-25
source: sources/ssrn-3247865-151-trading-strategies.pdf
---

# 151 Trading Strategies — Kakushadze & Serur (2018)

**Citation**: Kakushadze, Z. & Serur, J.A. (2018). *151 Trading Strategies*. SSRN 3247865.  
**Pages**: 361 | **Formulas**: 550+ | **References**: ~2,000  
**Scope**: Stocks, Options, ETFs, Fixed Income, Indexes, Volatility, FX, Commodities, Structured Assets, Convertibles, Crypto, Global Macro, Infrastructure, Tax Arbitrage

## Summary

Encyclopedic reference covering 151+ quantitative trading strategies across virtually every asset class. Each strategy is described mathematically with formulas. Appendix A contains R source code for intraday mean-reversion and momentum backtesting with full out-of-sample discipline.

Key methodological notes from Appendix A:
- **Out-of-sample discipline**: universe selection, risk model, and signal are all strictly backward-looking
- **Delay-0 vs Delay-1**: mean-reversion trades on overnight return (borderline in-sample); momentum uses prior day's close-to-open (delay-1, 100% OOS)
- **Transaction costs**: Almgren et al. (2005) model — 10 bps mean cost; τᵢ = ζσᵢ/Aᵢ where Aᵢ = ADDV
- **Universe**: top N stocks by ADDV, recomputed every 21 trading days
- **Optimization**: mean-variance with dollar-neutrality constraint and position bounds

---

## Strategies by Chapter

### Chapter 2: Options (~55 strategies)
Covered calls, spreads, butterflies, condors, straddles, ratio spreads, seagull spreads, collars, synthetics. Mathematical payoff diagrams with formulas. Not currently in backtest scope (need options pricing + IV data).

### Chapter 3: Stocks (§3.1–3.21)

| § | Strategy | Signal | Rebalance | Notes |
|---|----------|--------|-----------|-------|
| 3.1 | **Price Momentum** | 12-1 month cumulative return | Monthly | Long top decile, short bottom; skip 1 month |
| 3.2 | **Earnings Momentum (SUE)** | Standardized Unexpected Earnings | Quarterly | (Eᵢ − E'ᵢ) / σᵢ; needs EDGAR/FMP data |
| 3.3 | **Value (B/P)** | Book-to-Price ratio | Monthly | Long high B/P, short low B/P; needs fundamental data |
| 3.4 | **Low-Volatility Anomaly** | Historical return volatility (6-12 mo) | Monthly | Long low-vol, short high-vol; paradox of lower risk → higher return |
| 3.5 | **Implied Volatility** | Change in call/put IV over past month | Monthly | Long stocks with rising call IV; needs options data |
| 3.6 | **Multifactor Portfolio** | Combination of factors (momentum + value + low-vol) | Monthly | Blend factor rankings; anti-correlated factors add value |
| 3.7 | **Residual Momentum** | Factor-neutralized return residuals | Monthly | Remove MKT/SMB/HML exposure; use residuals as signal |
| 3.8 | **Pairs Trading** | Demeaned returns of 2 correlated stocks | Daily/weekly | Mean-reversion; dollar-neutral |
| 3.9 | **Mean-Reversion (cluster)** | Demeaned returns within sector cluster | Daily | Generalization of pairs to N stocks |
| 3.11 | **Single MA** | Price vs SMA(T) or EMA(T) | Daily | Long when P > MA; short when P < MA |
| 3.12 | **Dual MA Crossover** | SMA(T') vs SMA(T), T' < T | Daily | Long when fast > slow; optional stop-loss |
| 3.13 | **Triple MA** | MA(T1) > MA(T2) > MA(T3) | Daily | Filters false crossover signals |
| 3.14 | **Support & Resistance** | Daily pivot point C = (H+L+C)/3; R = 2C−L; S = 2C−H | Intraday | Long when P > C, exit at R; short when P < C, exit at S |
| 3.15 | **Donchian Channel** | T-day high/low channel | Daily | Buy at T-day low (mean-reversion) or breakout |
| 3.16 | **M&A Arbitrage** | Announced deal spreads | Event-driven | Cash: long target; stock: long target/short acquirer |
| 3.17 | **KNN Single-Stock** | k-nearest-neighbors on price/volume features | Daily | Target: next-T-day return; predict using historical analogues |
| 3.18 | **Stat Arb (MVO)** | Mean-variance optimization; Sharpe-maximizing weights | Daily | Requires covariance matrix; dollar-neutral |
| 3.19 | **Market Making** | Bid-ask spread capture with directional signal | HFT | Requires #1 queue position; not feasible for retail |
| 3.20 | **Alpha Combos** | Combine hundreds of weak alpha signals | Daily | Normalize → demean → regress to remove correlation |

### Chapter 4: ETFs (§4.1–4.6)

| § | Strategy | Signal | Rebalance | Notes |
|---|----------|--------|-----------|-------|
| 4.1 | **Sector Momentum Rotation** | 12-month ETF cumulative return | Monthly | Buy top decile sectors; hold 1-3 months |
| 4.1.1 | **Sector Rotation + MA Filter** | As above, but only buy if ETF > MA(200) | Monthly | Avoids buying downtrending sectors |
| 4.1.2 | **Dual-Momentum Sector Rotation** | Relative (sector) + absolute (SPY vs MA) momentum | Monthly | If SPY < MA(200), hold TLT/GLD instead |
| 4.2 | **Alpha Rotation** | Jensen's alpha from Fama-French regression | Monthly | Rank by alpha instead of raw return |
| 4.3 | **R-Squared** | 1−R² (selectivity) × alpha ranking | Monthly | Low R² = high active management; sort on selectivity × alpha |
| 4.4 | **IBS Mean-Reversion** | IBS = (C−L)/(H−L); sell rich (IBS→1), buy cheap (IBS→0) | Daily | Cross-sectional ETF mean-reversion |
| 4.5 | **Leveraged ETF Decay** | Short both 2× and inverse 2× ETF | Daily | Captures volatility decay; large tail risk |
| 4.6 | **Multi-Asset Trend Following** | Positive cumulative return + MA filter across asset classes | Monthly | ETF-based cross-asset momentum; weight by Rᶜᵘᵐ/σᵢ |

### Chapter 7: Volatility (§7.1–7.6)
VIX futures basis trading, volatility carry (long VXX), volatility risk premium (short realized vol), variance swaps. Requires VIX futures/options data — deferred.

### Chapter 8: FX (§8.1–8.5)
MA with HP filter, carry trade (long high-rate / short low-rate currency), dollar carry, momentum+carry combo, triangular arbitrage. Available via Kraken.

### Chapter 18: Cryptocurrencies (§18.1–18.3)
ANN (neural network) price predictor, Naïve Bayes Bernoulli sentiment analysis. Available via Kraken.

---

## Implementation Priority

See [Hypothesis Log](../backtesting/hypothesis-log.md) for results of all experiments derived from this source.

### Tier 1 — Implement Now (EOD data, no derivatives, clean backtesting)

1. **Dual-Momentum Sector Rotation** (§4.1.2) — H005 (CONFIRMED IS / REJECTED OOS); H006 (BIL variant, CONFIRMED improvement)
   - Symbols: XLK, XLF, XLV, XLE, XLY, XLP, XLI, XLU, XLB + SPY (absolute filter) + TLT (refuge)
   - Data back to 1999 (most sectors); XLRE only from 2015
   
2. **Sector Rotation + MA Filter** (§4.1.1) — H005 variant

3. **Dual MA Crossover on SPY** (§3.12) — H008
   - Parameters: SMA(10)/SMA(30), SMA(50)/SMA(200)
   - Note: H007 is reserved for iron condor LEAN backtest (options)

4. **IBS Mean-Reversion on ETFs** (§4.4) — H009

### Tier 2 — Next Phase

5. **Price Momentum on SPX stocks** (§3.1) — needs universe management, survivorship bias handling
6. **Multi-Asset Trend Following** (§4.6) — needs bonds, commodities ETFs
7. **Pairs Trading** (§3.8) — needs cointegration screening

### Tier 3 — Deferred (require specialized data)

- Options strategies — need IV data (Polygon options free tier limited)
- FX strategies — via Kraken (deferred to phase 2)
- Volatility strategies — VIX futures data
- Earnings momentum — need quarterly EPS from EDGAR/FMP

---

## Key Formulas

**Price momentum selection criterion:**
Rᶜᵘᵐᵢ = P(S) / P(S+T) − 1  (T=12 months, S=1 month skip)

**Sector rotation signal:**
Buy top N by Rᶜᵘᵐᵢ at month-end; hold for holding period

**Dual momentum filter:**
If SPY_close > SMA(SPY, 200): use sector rotation
Else: hold TLT (refuge asset)

**MA crossover signal:**
Long if SMA(T') > SMA(T) where T' < T
Short/flat if SMA(T') < SMA(T)

**IBS mean-reversion:**
IBS = (Close − Low) / (High − Low)
Sell ETFs in top decile IBS; buy ETFs in bottom decile IBS

**Dual-MA stop-loss augmentation (§3.12):**
Liquidate long if P < (1−Δ) × P₁, where Δ = 2%

---

## Backtesting Notes (from Appendix A)

The R code implements a dollar-neutral intraday mean-reversion strategy:
- Universe: top 2000 stocks by 21-day ADDV
- Signal: delay-0 overnight return (close-to-open)
- Risk model: principal component covariance (or heterotic model)
- Optimization: mean-variance with bounds |Hᵢ| ≤ bnds × ADDVᵢ
- Costs: 10 bps per dollar traded (Almgren et al. model)
- Output: Sharpe ratio, annualized return %, cents-per-share

For our Python implementation: adapt the optimization to scipy or use simpler rank-based weights (consistent with academic literature on momentum/mean-reversion).
