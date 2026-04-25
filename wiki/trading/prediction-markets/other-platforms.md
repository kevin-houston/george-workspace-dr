---
updated: 2026-04-25
---

# Other Prediction Market Platforms

## PredictIt

- CFTC DCM + DCO approval (September 2025, upgraded from no-action letter)
- Focus: US political markets (elections, policy, congressional votes)
- Free read-only JSON API: `predictit.org/api/marketdata/all/` — 60-second refresh
- **No programmatic trading API** — orders must be placed manually via web UI
- **Verdict**: Data source only; not viable for algorithmic trading

## Manifold Markets

- Play money (Mana) only — no cash value since March 2025 (Sweepcash model sunset)
- No financial risk; good sandbox for learning prediction market dynamics
- **Verdict**: Educational only

## Interactive Brokers / CME ForecastTrader

- CME-listed event contracts (economic, FX, equities, crypto)
- Access via IBKR account; commission-free (spread-based)
- Contracts: $1–$99, settle at $100
- Markets: CPI, unemployment, Fed decisions, S&P 500 levels, Bitcoin ranges
- IBKR API + TWS integration
- **Verdict**: Good for traders who want institutional clearing and IBKR's existing infrastructure. Competes directly with Kalshi's economic contracts. Moderate liquidity.

## Emerging platforms (2025–2026)

| Platform | Launch | Notes |
|----------|--------|-------|
| OG Markets | Feb 2026 | Multi-outcome contracts; Gen-Z positioning; early stage |
| FanDuel Predicts | Dec 2025 | All 50 states; sports-focused; Flutter Entertainment |
| DraftKings Predictions | Dec 2025 | 38 states; DFS ecosystem integration |

**Assessment**: All emerging platforms are retail-focused with limited/no trading APIs. Kalshi and Polymarket remain the only institutional-grade options for algorithmic strategies.

## Leveraged/Perpetual prediction markets (emerging)

- **Kalshi Timeless** (launching April 27, 2026): perpetual contracts with funding rates
- **Polymarket leveraged products**: 1x–3x leverage, 24/7, no expiration
- New strategy category: funding rate arbitrage (similar to crypto perp funding arb)
