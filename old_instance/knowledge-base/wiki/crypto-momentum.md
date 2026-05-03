# Crypto Momentum Strategies

*Crypto is the highest raw-Sharpe category tested (SOL 20d Momentum: +1.682, CAGR 205.8%) and also the most dangerous — Max DD -71.4% during the 2022 crypto winter. The market is structurally less efficient than equities (72% of strategies profitable vs. ~15-20% in equities), making momentum especially powerful. However, position sizing must be kept extremely small (2-5% of portfolio) to avoid crypto's fat-tail drawdown risk contaminating a broader portfolio.*

---

## Results Summary

| Strategy | Coin | Sharpe | CAGR | Max DD | Notes |
|----------|------|--------|------|--------|-------|
| 20d Momentum | SOL | +1.682 | 205.8% | -71.4% | Best Sharpe; institutional adoption tailwinds 2021-2024 |
| 30d Momentum | BTC | +1.298 | 87.4% | N/A | Most consistent; positive across ALL momentum windows |
| 20d Momentum | ETH | ~1.1-1.3 | N/A | N/A | Strong institutional buying |
| Various | BNB, XRP, ADA, AVAX, DOGE | Lower | N/A | N/A | More volatile, less consistent |

*Universe tested: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, DOGE | 3 dedicated rounds | 277 strategies*

---

## Key Findings

1. **72% of crypto strategies profitable** — versus ~15-20% in equities. This is the least efficient market tested.
2. **Momentum dominates**: 20-day and 30-day momentum windows are optimal
3. **SOL highest Sharpe** due to institutional adoption tailwinds 2021-2024; this may not persist as SOL matures
4. **BTC most consistent**: positive Sharpe across ALL momentum windows tested — steady institutional buying floor
5. **Mean reversion is mixed**: Works on BTC/ETH (more liquid, institutional); fails on altcoins (too directional in trend periods)
6. **Crypto is NOT market-neutral**: Max DD -71.4% during 2022 crypto winter means this is correlated to broad risk-off

---

## Sizing Considerations ⚠️

This is the most important consideration for crypto:

- **Recommended portfolio allocation**: 2-5% maximum
- **Why**: A -71% drawdown on a 10% allocation = -7.1% portfolio drawdown. On a 5% allocation = -3.55%
- **Kelly-implied sizing**: Given Sharpe 1.682 and Max DD -71.4%, Kelly would suggest a small fraction of portfolio
- **The 2022 risk**: All crypto assets crashed simultaneously (BTC -65%, ETH -68%, SOL -95%). Diversifying across coins provides no protection in crypto winters

**Rule of thumb**: Never allocate more than you'd be comfortable losing 70%+ of, because that has happened and will happen again.

---

## Implementation Notes

- **Data source**: Crypto prices available via yfinance (BTC-USD, ETH-USD, SOL-USD, etc.)
- **Signal**: Close-to-close 20d or 30d return > 0 → long; < 0 → flat (no shorting)
- **Execution**: Robinhood supports crypto trading (BTC, ETH, SOL, DOGE, others)
- **Rebalancing**: Daily signal check; enter/exit based on momentum direction
- **No leverage**: Crypto already provides 200%+ CAGR raw; leverage would create unacceptable tail risk

---

## What the High CAGR Means in Practice

SOL 20d Momentum's 205.8% CAGR is not investable at scale. At 5% portfolio allocation:
- Portfolio-level contribution: ~10% CAGR
- Portfolio-level Sharpe contribution: ~0.08 (diluted by 5% weight)
- Portfolio-level Max DD risk: ~3.5% from this allocation

The value of crypto in the portfolio is **convex upside exposure at small size** — not a core allocation.

---

## Unexplored Areas

- Intraday crypto momentum (1H, 4H bars) — completely unexplored; QuantAgent paper showed 80% directional accuracy on BTC 4H intervals using LLM agents
- DeFi yield strategies
- Cross-exchange arbitrage (infrastructure-intensive)
- On-chain signal integration (wallet flows, exchange inflows/outflows)

---

## Related Topics

- [[trading-strategies-leaderboard]] — Full Sharpe context
- [[portfolio-allocation]] — Recommended 10% allocation at small size
- [[ml-for-trading]] — QuantAgent LLM on BTC 4H

## Sources
- Master Trading Report (Crypto section): raw/master_trading_report_2026-04-05.md
