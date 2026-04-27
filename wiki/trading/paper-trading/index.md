---
updated: 2026-04-26
status: active
---

# Paper Trading Log

Tracks paper trades entered for strategy validation before going live.
Engine: BSM pricing via Massive.com (real SPY price) + our iron condor model.
Data file: `backtesting/paper_trading/trades.json`

## Open Positions

### Options (Iron Condor)

| ID | Strategy | Entered | Expiry | DTE | SPY Entry | Strikes | Credit | Max Loss | Status |
|----|----------|---------|--------|-----|-----------|---------|--------|----------|--------|
| IC-2026-04-26-001 | Iron Condor | 2026-04-26 | 2026-06-12 | 47 | $713.94 | $645p/$670p/$775c/$800c | $5.33 ($533) | $1,967 | Open |

### ETF Rotation (H016 — Momentum+Carry Blend)

| Month | Holdings | Weight | Cash (→SHY) | SPY Score | TLT Score | GLD Score |
|-------|----------|--------|-------------|-----------|-----------|-----------|
| 2026-04 | SPY + TLT | 50/50 | GLD | 4.0 (mom +30.2%, vol 16.8%) | 4.0 (mom +1.3%, vol 10.5%) | 4.0 (mom +42.6%, vol 28.0%) |

Signal file: `backtesting/paper_trading/h016_positions.json`

## Closed Positions

_(none yet)_

## Rules

- **Entry**: 45 DTE, 16-delta short strikes, $25 wings
- **Target exit**: 50% of credit received
- **Stop loss**: debit to close = 2× initial credit (Tastytrade rule)
- **DTE exit**: 21 DTE if neither target nor stop triggered
- **Pricing**: BSM model (VIX as flat-term IV); real market prices used when Massive has data

## Notes

- 2026-04-26: H016 April signal computed — 3-way tie (all scores 4.0). GLD excluded because its high vol (+28%) cancels its top momentum (+42.6%). SPY + TLT held 50/50; GLD → SHY.
- 2026-04-26: First paper trade entered (IC-2026-04-26-001). Massive free tier doesn't yet list Jun 12 contracts in reference API; BSM model prices used for all four legs. Real prices will auto-populate once contracts appear (~60 DTE out).
- Massive.com API key active (`$MASSIVE_KEY`). Polygon.io backend, free tier: delayed stock prices + recent contract reference. Historical options data requires paid plan.
