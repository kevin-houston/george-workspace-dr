# Pairs Trading (Statistical Arbitrage)

*Pairs trading is Kevin's best risk-adjusted strategy category — the 10-pair portfolio achieves Sharpe +0.964 with Max DD of only -11.90% and near-zero correlation to SPY (~0.05). It exploits mean reversion in price spreads between economically related stocks. While individual pairs have substantial drawdowns (-30 to -50%), a diversified portfolio of 10 uncorrelated pairs produces an exceptional Sharpe-to-drawdown ratio that makes it the preferred market-neutral anchor for the full portfolio.*

---

## Core Mechanics

- **Signal**: Rolling z-score of price spread between two cointegrated stocks
- **Entry**: z-score > 2.0 (spread is 2 standard deviations wide — long underperformer, short outperformer)
- **Exit**: z-score < 0.5 (spread reverts to near-normal)
- **Stop**: z-score > 4.0 (spread too wide — structural break, exit)
- **Window**: 60-day rolling (adapts to regime shifts)
- **Hold limit**: 20 days max

---

## Results

### 10-Pair Portfolio (R23)
- **Sharpe**: +0.964
- **CAGR**: 6.82%
- **Max DD**: -11.90%
- **SPY correlation**: ~0.05 (effectively market neutral)

### Best Individual Pairs
| Pair | Sharpe | CAGR | Max DD | Notes |
|------|--------|------|--------|-------|
| JNJ/UNH | +0.857 | 16.45% | -30.41% | Best individual equity pair |
| EWC/EWA | +0.937 | 8.91% | -9.5% | Canada/Australia; best corr to SPY |
| LMT/NOC | Strong | N/A | N/A | Defense sector |
| DE/BA | Moderate | N/A | N/A | Kalman helps slowly-evolving pair |
| BAC/GS | Moderate | N/A | N/A | Financial sector |
| BAC/WFC | Moderate | N/A | N/A | Regional bank pair |
| CVX/COP | Moderate | N/A | N/A | Energy pair |
| COST/PG | Moderate | N/A | N/A | Consumer staples |
| UPS/BA | Moderate | N/A | N/A | Industrial |
| PFE/UNH | Moderate | N/A | N/A | Healthcare |

The 10-pair book: JNJ/UNH, LMT/NOC, DE/BA, UPS/BA, BAC/GS, BAC/WFC, JNJ/PFE, CVX/COP, COST/PG, PFE/UNH

---

## Technical Implementation Notes

### Why Formal Cointegration Failed
- Engle-Granger test on 10 years of Fortune 100 data: **0/75 pairs passed** cointegration
- Structural breaks (NVDA 10x, Boeing disruption) violate long-run cointegration assumptions
- **Solution**: 60-day rolling z-score — adapts to regime shifts, doesn't require stationary long-run relationship
- Academic purity loses; practical rolling approach wins

### Kalman Filter
- **Helps**: Slowly-evolving pairs (DE/BA: +0.204 Sharpe lift)
- **Hurts**: Stable pairs (JNJ/UNH: -0.696 Sharpe lift)
- Use with caution — only apply where spread dynamics are demonstrably time-varying

### Why Diversification Works So Well
- Individual pair Max DD: -30% to -50%
- 10-pair portfolio Max DD: -11.90% (same period)
- Pairs tend to fail for idiosyncratic reasons (merger, bankruptcy, guidance revision) that are uncorrelated across pairs
- The correlation math is the entire thesis — do not concentrate in similar-sector pairs

---

## What Doesn't Work

- **Tech sector pairs**: NVDA 10x caused structural divergence — avoid growth tech
- **Industrial pairs (Boeing)**: Single-stock disruptions break the spread permanently
- **Kalman on stable pairs**: Over-adapts, destroys edge in well-behaved relationships
- **Cross-country long/short momentum**: Crisis correlation eliminates the diversification at exactly the wrong time

---

## Round 29: LLM Semantic Filter (Queued)

Inspired by arXiv:2602.07048 (Feb 2026) — two-stage framework tested on equity pairs:
- Stage 1: Statistical cointegration screening (top 20 pairs by p-value)
- Stage 2: LLM asks "Is there a plausible economic mechanism explaining why A and B should track each other over time?" Score 0-100; skip pairs scoring < 40

**Paper results on a different dataset**: +205% PnL, win rate 51.4%→54.5%, -46.5% average loss magnitude
**Dominant driver**: Loss reduction (downside control), not return enhancement

**Key distinction from R26**: R26 asked "is the chart overbought?" (technical judgment). R29 asks "does an economic mechanism exist?" (semantic judgment). The LLM is assessing pair QUALITY, not chart aesthetics.

### Round 29 Amendment: Factor Residual Decomposition (Stage 0)
Inspired by Attention Factors for Statistical Arbitrage (arXiv:2510.11616, Oct 2025):
- Before testing cointegration, residualize each asset against market and sector factors
- `residual_i = return_i - beta_mkt * mkt_return - beta_sector * sector_return`
- Test cointegration on RESIDUALS, not raw prices
- Eliminates spurious spread divergences caused by factor moves (e.g., sector rotation widening an oil-stock pair temporarily)
- Classical pairs trading: Net Sharpe <0.5; factor-purged: Net Sharpe 2.3 (paper result)
- ~10 lines of Python; major expected impact on signal quality

---

## Related Topics

- [[trading-strategies-leaderboard]] — Full Sharpe context
- [[llm-signal-research]] — R29 LLM filter design
- [[portfolio-allocation]] — Role in recommended portfolio
- [[research-agenda]] — R29 full design spec

## Sources
- Master Trading Report: raw/master_trading_report_2026-04-05.md
- Memory Snapshot (R29 design, arXiv:2602.07048, arXiv:2510.11616): raw/MEMORY_snapshot_2026-04-05.md
