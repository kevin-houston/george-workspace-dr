---
updated: 2026-05-17
status: active
---

# Paper Trading Index

## Active Strategies

### [H181 Industry-Adjusted Short-Term Reversal](h181-alpaca.md) — ACTIVE
**Production: 30-stock equal-weight reversal portfolio.** First trading day of month rebalance via Alpaca paper.
- Universe: 30 large-cap S&P 500 stocks (8 GICS sectors)
- Signal: REV^IN = prior-month return minus equal-weight GICS-sector average; long bottom-6
- Position sizing: equal-weight, 1/6 equity per stock (~16.7% each)
- OOS (2021–2026): Sharpe 1.138, CAGR 24.6%, MaxDD −18.4%, 1 negative year
- Script: `backtesting/paper_trading/h181_monthly.py`
- Started: 2026-05-10; Corr(H026) = 0.293 — genuine diversification
- **Path to real money:** 2 months paper validation (gate: results within 1.5σ of OOS mean)

### [H149 Alpaca ETF Rotation](h122-alpaca.md) — ACTIVE
**Production: 100% H026 sector rotation.** First trading day of month rebalance via Alpaca paper.
- Universe: 25 ETFs (11 S&P sectors + commodities + bonds)
- Signal: rank(3m) + rank(6m) + rank(12m) + rank(inv_vol); top-1 with 12m > +5% TSMOM filter
- Safe harbor: BIL when no sector qualifies
- OOS (2018+): 382.9× cumulative return, Sharpe 3.007, MaxDD −9.6%, 0 negative years
- Script: `backtesting/paper_trading/h112_monthly.py`
- Started: 2026-04-28 (H122 triple-strategy); H149 single-strategy active from 2026-05-01
- **Path to real money:** 4–8 weeks paper validation, then flip `paper=False` in Alpaca config

### [PEAD-NLP Event-Driven](pead-nlp-alpaca.md) — ACTIVE
**Production: H163/H174 FinBERT earnings gap strategy.** Event-driven; fires on earnings releases that meet both filters.
- Signal: Buy stocks gapping ≥ 3% at earnings open with FinBERT score ≥ 0.18 AND sentiment surprise ≥ 0.02
- Hold period: 20 trading days from entry open; exit at close on day 20
- OOS: n=22 events, WR 81.8%, MeanRet 6.89% (dual-filter variant)
- Script: `backtesting/paper_trading/pead_pipeline/`
- Started: 2026-05-06
- **Path to real money:** 10 live trades minimum; within 1.5σ of OOS WR (81.8%)

### Iron Condor (Options) — INACTIVE
BSM pricing via Massive.com. Last open position: IC-2026-04-26-001 (SPY Jun 12, $645p/$670p/$775c/$800c, $533 credit). Monitoring only.

---

## Open Positions

### Options (Iron Condor)

| ID | Strategy | Entered | Expiry | DTE | SPY Entry | Strikes | Credit | Max Loss | Status |
|----|----------|---------|--------|-----|-----------|---------|--------|----------|--------|
| IC-2026-04-26-001 | Iron Condor | 2026-04-26 | 2026-06-12 | 47 | $713.94 | $645p/$670p/$775c/$800c | $5.33 ($533) | $1,967 | Open |

### ETF Rotation (H149 — H026 Sector Momentum)

| Month | Holdings | Signal |
|-------|----------|--------|
| 2026-04 (old H122) | EWH (H041a) + IBB (H026) + HYG/BIL (H045) | Launched 2026-04-28 under old triple-strategy |
| 2026-05 (H149) | Run May 1 — check h112_monthly.py output for current holding | Pure H026 top-1 sector |

---

## Closed Positions

_(none yet)_

---

## Iron Condor Rules

- **Entry**: 45 DTE, 16-delta short strikes, $25 wings
- **Target exit**: 50% of credit received
- **Stop loss**: debit to close = 2× initial credit (Tastytrade rule)
- **DTE exit**: 21 DTE if neither target nor stop triggered
- **Pricing**: BSM model (VIX as flat-term IV); real market prices used when Massive has data

---

## Notes

- 2026-04-28: Paper account launched with old H122 triple-strategy (H041a 22% + H026 27% + H045 21%).
- 2026-04-30: Production code updated to H149 (100% H026). First H149 rebalance: May 1.
- 2026-04-26: IC-2026-04-26-001 entered. Massive free tier BSM-priced; real prices will populate ~60 DTE out.
- Massive.com API key active (`$MASSIVE_KEY`). Polygon.io backend, free tier: delayed stock prices + recent contract reference. Historical options data requires paid plan.
