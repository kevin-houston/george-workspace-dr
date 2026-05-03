# Portfolio Allocation

*The recommended multi-strategy portfolio allocation based on all backtested strategies as of 2026-04-05. The key design principle is combining high-Sharpe strategies (PEAD, dividend raise) with market-neutral anchors (pairs) to limit crash correlation, while using small crypto allocation for convex upside. Expected combined portfolio: Sharpe ~1.4-1.8, Max DD ~15-20%.*

---

## Recommended Allocation

| Allocation | Strategy | Expected Sharpe | Corr to SPY | Notes |
|------------|----------|-----------------|-------------|-------|
| 25% | PEAD Portfolio | +2.394 | ~0.30 | Best standalone Sharpe; new anchor strategy |
| 25% | Pairs Portfolio (US + EWC/EWA) | +0.964 | ~0.05 | Market neutral anchor; hedges PEAD crash risk |
| 15% | Dividend Raise Signal (>=10%, 40d) | +4.403 | ~0.30 | Highest single-strategy Sharpe |
| 15% | Risk Parity SPY/TLT/GLD | +0.865 | +0.47 | Drawdown smoother |
| 10% | Crypto Momentum (small!) | +1.682 | ~0.30 | High-CAGR convex exposure; size strictly limited |
| 5% | ETF Macro Overlay | +0.753 | +0.50 | Market exposure overlay |
| 5% | Pre-Holiday Effect | +0.553 | ~0.20 | Small but consistent; simple to implement |

**Expected combined portfolio**: Sharpe ~1.4-1.8 (diversification benefit), Max DD ~15-20%

---

## Design Rationale

### PEAD as the New Anchor
Previous anchor was Pairs (market neutral). PEAD is now co-equal anchor because:
- Highest portfolio Sharpe tested (+2.394)
- Simple to implement (buy gap >5% on earnings, hold 20 days)
- PEAD's crash correlation risk (-26.9% Max DD) is hedged by the market-neutral pairs book

### Pairs as the Market-Neutral Hedge
- SPY correlation ~0.05 — effectively zero
- When PEAD hits systemic drawdown (all earnings plays hit simultaneously in COVID-type crashes), pairs portfolio provides ballast
- The 10-pair book should include EWC/EWA (international commodity pair with Max DD -9.5%)

### Dividend Raise at 15%
- Sharpe +4.403 makes it the highest single-strategy — deserves significant allocation
- Correlated with PEAD (~0.30 to SPY) so does NOT get highest allocation
- Stagger with PEAD signals to avoid event-day correlation (dividend raises happen outside earnings calendar)

### Risk Parity as Drawdown Smoother
- SPY/TLT/GLD vol-weighted monthly rebalance
- Doesn't generate excess returns on its own (+0.865) but reduces overall portfolio drawdown
- TLT and GLD are genuinely uncorrelated in most equity drawdowns

### Crypto at 10% Strictly
At 10% allocation with -71.4% Max DD:
- Worst-case portfolio impact: -7.1%
- Expected contribution at 5% allocation: ~10% CAGR to portfolio
- Never increase above 10%; the 2022 crypto winter is the reference scenario

---

## Paper Trading Status

| Strategy | Paper Trading Status | Notes |
|----------|---------------------|-------|
| PEAD Portfolio | Planned (R29 pilot, now post-R28) | Robinhood; needs live market data access |
| Pairs Portfolio | Not yet started | Pairs need manual tracking |
| Dividend Raise Signal | Not yet started | Requires dividend announcement monitoring |
| Risk Parity | Not yet started | Monthly rebalance; simple to implement |
| Crypto Momentum | Not yet started | Robinhood supports crypto |

**Infrastructure note**: Live market data and Robinhood API access must run on the MX Linux host (not in container — container cannot fetch live prices).

---

## Strategies Explicitly Excluded

| Strategy | Why Excluded |
|----------|-------------|
| PEAD short side | Short avg Sharpe -0.294; negative gaps mean-revert |
| Short VIX outright | Sharpe -4.975; Feb 2018/Mar 2020 fatal |
| Protective puts on PEAD | Collapses Sharpe from 4.46 → 0.25 |
| Dividend Cut Short | Sharpe -2.937; cuts = restructuring bounce |
| High Yield Screen | Max DD -45%; value traps |
| Leveraged ETF shorting | Max DD -98.8% in trending markets |
| Forex (unlevered) | Sharpe only 0.280; low risk-adjusted return |

---

## Rebalancing Rules

- **PEAD**: Continuous — signals fire on each earnings event; hold 20 days, max 10 concurrent positions
- **Dividend Raise**: Continuous — enter on ex-date when >=10% raise announced; hold 40 days
- **Pairs**: Continuous — z-score based entry/exit; roll positions as signals fire
- **Risk Parity**: Monthly rebalance — vol-weight SPY/TLT/GLD based on 20-day realized vol
- **Crypto**: Monthly review — hold if 20d or 30d momentum positive; exit if momentum flips negative
- **ETF Macro Overlay**: Weekly — check oil regime (WTI momentum) and VIX; adjust sector ETF exposure
- **Pre-Holiday**: Calendar-based — buy 2 days before each of 8 US market holidays; sell on open after

---

## Macro Overlay Rules (All Strategies)

From equity macro research (R11-R18):
- **Oil regime**: If WTI 10-50 day momentum is negative → reduce equity exposure 30%
- **VIX > 25**: Reduce all risky positions (PEAD, crypto) by 50%
- **VIX > 30**: Apply RegimeGuard — skip new PEAD signals entirely (per R28 design)
- **Gold flight (GoldFlight_120)**: If gold momentum rising → add GLD exposure from equities

---

## Related Topics

- [[trading-strategies-leaderboard]] — Full Sharpe context for all strategies
- [[pead-strategy]] — PEAD implementation detail
- [[pairs-trading]] — Pairs book construction
- [[dividend-strategies]] — Dividend raise signal mechanics
- [[crypto-momentum]] — Sizing considerations
- [[options-strategies]] — CC overlay potential

## Sources
- Master Trading Report (Portfolio Construction section): raw/master_trading_report_2026-04-05.md
- Memory Snapshot (paper trading status): raw/MEMORY_snapshot_2026-04-05.md
