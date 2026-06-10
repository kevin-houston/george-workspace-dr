---
title: Shared Strategy Evaluation Checklist
description: Common standard for both George and Ernesto before any strategy advances to paper trading or production
updated: 2026-06-09
authors: [George, Ernesto]
---

# Shared Strategy Evaluation Checklist

Agreed standard for both George (NanoClaw) and Ernesto to apply before any strategy advances to paper trading or production. Results across both systems are only comparable when this checklist is satisfied.

---

## 1. Look-Ahead Guard

- [ ] All price/return signals use `.shift(1)` (or equivalent) so no future data leaks into the signal at time T
- [ ] For ML features (rolling stats, z-scores, etc.), confirm the rolling window is computed on data available *before* T
- [ ] Document any exception with a written justification

## 2. NLP Timestamp Documentation

For any strategy that uses text-based signals (earnings transcripts, 8-K filings, news, sentiment):

- [ ] Document the source of T=0 (e.g., EDGAR accession timestamp, news publish time, API delivery time)
- [ ] Document market-hour handling: filings/news that arrive after market close → signal fires at *next* open; intraday → document exactly
- [ ] Confirm no text content that postdates T=0 is used in the signal

## 3. Transaction Cost Model

- [ ] Equity strategies: model at minimum **5bps round-trip** (entry + exit) per trade
- [ ] Options strategies: add estimated **bid-ask half-spread** on top of the 5bps baseline
- [ ] Report how many trades are culled once costs are applied (a meaningful cull % is a feature, not a bug)
- [ ] Strategies with turnover > 2x/month must show net-of-cost Sharpe explicitly

## 4. Soft OOS Gate

Before paper trading:
- [ ] Backtest Sharpe documented over the IS period

During paper trading:
- [ ] After 60 days, paper P&L must be within **1 StdDev** of backtest expectation
- [ ] Strategies that breach this gate are paused and reviewed — not automatically killed

For production promotion:
- [ ] OOS Sharpe > **0.8** (hard gate)
- [ ] If near the gate (0.8–0.9), flag as fragile and require additional confirmation period

## 5. Regime Coverage

- [ ] Backtest spans at minimum: **2022 bear market** (rate hike cycle) + **2024 rally**
- [ ] Credit-sensitive strategies (fixed income, sector rotation, rate-linked): add FRED macro overlay (Fed Funds rate, credit spreads, yield curve slope)
- [ ] Regime-conditional strategies: document which states are covered and how many observations per state in IS and OOS

## 6. Universe & Survivorship Bias

- [ ] Document the exact stock universe used (e.g., "SP500 current constituents as of 2026-06," "NASDAQ100 at backtest date")
- [ ] If the universe is based on *current* members, flag as **survivorship-biased** — results are optimistic
- [ ] Preferred: point-in-time constituent lists (e.g., from CRSP, Sharadar, or a dated snapshot)
- [ ] ETF-only universes are survivorship-bias-free by default (document this explicitly)

## 7. After-Tax Flag

- [ ] Note whether reported returns are **pre-tax** or **post-tax**
- [ ] Production targets are post-tax; strategies promoted to production must include a post-tax estimate
- [ ] Short-term gains (hold < 1 year) taxed at ordinary income rate — model at 37% for worst-case planning

---

## Checklist Sign-Off

Before advancing a strategy, record:

```
Strategy: H### / R##
Date evaluated: YYYY-MM-DD
Evaluated by: George / Ernesto
Items passed: all / list exceptions
Notes:
```

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-06-09 | Initial draft — 7-point checklist agreed by George and Ernesto | George |
