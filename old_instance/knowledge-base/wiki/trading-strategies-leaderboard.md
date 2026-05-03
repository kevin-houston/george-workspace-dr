# Trading Strategies Leaderboard

*The master reference for all backtested strategies across Kevin's systematic trading research program. Covers ~7,000+ backtests across equities, options, forex, crypto, commodities, ML, and LLM signal filtering. Sharpe ratios are from walk-forward or out-of-sample backtests; all equity strategies use Fortune 100 universe (2015-2025) unless noted.*

---

## The Full Leaderboard

| Rank | Strategy | Category | Sharpe | CAGR | Max DD | Notes |
|------|----------|----------|--------|------|--------|-------|
| 1 | Div Raise >=10% hold-40d (R27) | Dividend | +4.403 | ~15% | N/A | Highest single-strategy Sharpe in corpus |
| 2 | Div Raise >=5% hold-40d (R27) | Dividend | +3.400 | ~12% | N/A | More signals, still strong |
| 3 | PEAD Portfolio | PEAD | +2.394 | ~38% | -26.9% | 30-stock equal-weight gap signals |
| 4 | CC around Ex-Div 10d (R27) | Dividend+Opts | +2.643 | ~9% | N/A | Sell calls pre-ex-div |
| 5 | Bull Put Spread XOM (R28) | Options | +2.584 | N/A | N/A | IV rank filter, best put spread |
| 6 | Bull Put Spread CVX (R28) | Options | +2.470 | N/A | N/A | Energy sector defined-risk |
| 7 | SOL 20d Momentum | Crypto | +1.682 | 205.8% | -71.4% | High CAGR, extreme drawdown |
| 8 | RF on XOM (best ML) | ML | +1.744 | N/A | N/A | Random Forest, walk-forward |
| 9 | Div Capture buy-3d sell+5d | Dividend | +1.578 | ~6% | N/A | Pre-ex-div momentum |
| 10 | Ex-Div Drift hold-20d | Dividend | +1.511 | ~6% | N/A | Post-ex-div continuation |
| 11 | PEAD gap5% 20d (single) | PEAD | +1.137 | N/A | N/A | 67.8% win rate, p=0.000 |
| 12 | Corn Seasonal | Commodity | +1.175 | 18.3% | -14.2% | Calendar-driven, low DD |
| 13 | Dogs of the Dow top-10 | Dividend | +1.203* | 15.3% | N/A | *annual Sharpe, p=0.003 |
| 14 | BTC 30d Momentum | Crypto | +1.298 | 87.4% | N/A | Most consistent crypto |
| 15 | VIX Short Put (R28) | Options | +0.846 | N/A | N/A | 88.6% WR, structural floor |
| 16 | Pairs Portfolio (R23) | Stat Arb | +0.964 | 6.82% | -11.90% | Best deployable, market neutral |
| 17 | EWC/EWA Country Pair | International | +0.937 | 8.91% | -9.5% | Canada/Australia commodity pair |
| 18 | Risk Parity Lite | Multi-Asset | +0.865 | 9.1% | -22.28% | SPY/TLT/GLD vol-weighted |
| 19 | JNJ/UNH pair (best single) | Stat Arb | +0.857 | 16.45% | -30.41% | Best individual equity pair |
| 20 | Covered Calls IBM (R25) | Options | +0.836 | ~9.2% | -16.1% | Best static CC strategy |
| 21 | ETF Macro Overlay | ETF Rotation | +0.753 | 12.4% | -18.3% | Oil/energy + macro signal |
| 22 | Bull Put Spread avg (R28) | Options | +0.744 | N/A | N/A | Best avg across 30 tickers |
| 23 | EWT Taiwan | International | +0.615 | 11.08% | N/A | Semiconductor dominance |
| 24 | OilMom_10_50 (R18) | Equity Macro | +0.640 | 8.2% | -28.0% | Oil regime × equity strategy |
| 25 | Dual Momentum (ETF) | ETF Rotation | +0.628 | 10.8% | -21.4% | Absolute + relative mom |
| 26 | VIX Mean Reversion | Volatility | +0.483 | 6.3% | -19.1% | Short VIX after spikes |
| 27 | Iron Condor avg (R28) | Options | +0.523 | N/A | N/A | IV rank>50%, 62.8% WR |
| 28 | Covered Calls avg (R25) | Options | +0.533 | ~6-8% | ~-18% | Across Fortune 100 div stocks |
| 29 | ML Ensemble avg | ML | +0.527 | N/A | N/A | Beats B&H 25-35% of stocks |
| 30 | Pre-Holiday Effect | Seasonal | +0.553 | ~4% | -8.2% | Only stat-sig seasonal (p=0.042) |
| 31 | GoldFlight_120 (R16) | Equity Macro | +0.559 | 18.1% | -38.0% | Gold regime filter |
| 32 | VRP Harvest filtered (R28) | Options | +0.499 | N/A | N/A | IV rank filter critical |
| 33 | Gamma Scalping avg (R28) | Options | +0.413 | N/A | N/A | Edge real; complex operationally |
| 34 | Lev Momentum UPRO/IEF | Leveraged ETF | +0.422 | 8.9% | -52.5% | SPY > 50d MA: UPRO else IEF |
| 35 | Inflation Protection | Fixed Income | +0.462 | 5.1% | -11.3% | TIP/IEF rotation, SPY corr -0.12 |
| 36 | Wheel Strategy avg (R28) | Options | +0.312 | N/A | N/A | -0.130/yr vs BH; skip on growth |
| 37 | Momentum Factor 6-1 | Factor | +0.357 | 5.8% | -24.1% | Classic factor, alive but dim |
| 38 | RSI Tight Forex (R2) | Forex | +0.280 | 0.59% | -6.0% | Best forex, low CAGR unlevered |
| 39 | Mean Rev 40-day Forex (R1) | Forex | +0.200 | 0.93% | -7.1% | Z-score reversion, EUR/GBP |

---

## What Doesn't Work

| Strategy | Why It Fails |
|----------|-------------|
| Short VIX outright | Sharpe -4.975; Feb 2018/Mar 2020 fatal |
| Protective puts on PEAD | Insurance cost collapses Sharpe 4.46→0.25 |
| Div Cut Short | Cuts = restructuring in bull mkt → bounce |
| Short leveraged ETFs | Max DD -98.8% in trending markets |
| Cross-country L/S momentum | Crisis correlation wipes diversification |
| Low volatility factor | Inverted 2016-2026 (high-vol dominated) |
| Small cap factor | Large cap outperformance era |
| Kalman filter on stable pairs | Over-adapts, destroys stable edge |
| Macro regime on candle patterns | Candles are micro-momentum (regime-agnostic) |
| LLM filter on PEAD | Confirmed signals underperform rejected signals |
| Straddle sell without IV rank filter | Avg Sharpe -0.086; filter is non-optional |
| Wheel strategy on growth stocks | Missed recoveries → -0.130/yr vs BH |
| ML on tech stocks | High-vol too noisy for ML signals |

---

## Key Meta-Lessons

1. **Market structure determines strategy type**: Equities (growth premium → momentum); Forex (zero-sum → mean reversion); Crypto (retail-dominated, inefficient → both work)
2. **Diversification is the only free lunch**: Single pair Max DD -30 to -50%; 10-pair portfolio Max DD -11.90%
3. **Macro regime is a consistent edge multiplier**: Adding macro filter to any equity strategy averages +0.15 Sharpe lift; oil regime is the most predictive signal
4. **Formal tests often fail on real data**: Engle-Granger on 10 years = 0/75 cointegrated pairs; use rolling z-score, not academic purity
5. **Sharpe ≠ best strategy**: Crypto Sharpe 1.682 with Max DD -71% is not deployable at full size; pairs Sharpe 0.964 with Max DD -11.90% is deployable at 30-50% allocation
6. **IV rank filter is the master key for options**: All premium-selling strategies improve dramatically when filtered by IV rank

---

## Category Champions (Sharpe)

| Category | Best Strategy | Sharpe |
|----------|--------------|--------|
| Dividend | Div Raise >=10% hold-40d | +4.403 |
| PEAD | PEAD Portfolio | +2.394 |
| Options (individual) | Bull Put Spread XOM | +2.584 |
| Crypto | SOL 20d Momentum | +1.682 |
| ML | Random Forest on XOM | +1.744 |
| Commodity | Corn Seasonal Nov-Feb | +1.175 |
| Stat Arb | Pairs Portfolio (10-pair) | +0.964 |
| International | EWC/EWA Pair | +0.937 |
| Multi-Asset | Risk Parity Lite | +0.865 |
| ETF Rotation | ETF Macro Overlay | +0.753 |
| Leveraged ETF | UPRO/IEF Momentum Switch | +0.422 |
| Forex | RSI Tight | +0.280 |

---

## Related Topics

- [[pead-strategy]] — Full PEAD detail
- [[dividend-strategies]] — Dividend signal mechanics
- [[pairs-trading]] — Stat arb detail
- [[options-strategies]] — R25 and R28 options detail
- [[crypto-momentum]] — Crypto sizing considerations
- [[portfolio-allocation]] — Recommended allocation weights

## Sources
- Master Trading Report: raw/master_trading_report_2026-04-05.md
- Memory Snapshot: raw/MEMORY_snapshot_2026-04-05.md
