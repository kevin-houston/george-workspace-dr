# Trading Eval Framework Upgrade — Plan
**Created:** 2026-04-01
**Purpose:** Re-instrument all eval harnesses to produce standardized trade logs,
enabling a permanently rerunnable analysis layer that never requires re-running
harnesses to add new metrics.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Harness Layer  (one file per strategy category)         │
│  Inherits from base_harness.py                           │
│  Outputs: trade_logs/{strategy}_r{nn}.trades.jsonl       │
│  Rule: NO metrics computed here — data only              │
└──────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────┐
│  Analysis Layer  (analysis_layer.py)                     │
│  Reads any .trades.jsonl file                            │
│  Computes: Sharpe, Sortino, Calmar, skew, SPY corr,      │
│            regime-conditional stats, cross-strategy corr │
│  Add new metrics here — never re-run harnesses for this  │
└──────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────┐
│  Report Layer                                            │
│  Updates MASTER_REPORT.md, NANOCLAW_DIARY.md             │
│  Publishes to here.now dashboard                         │
└──────────────────────────────────────────────────────────┘
```

**Key principle:** A harness re-run is only needed when strategy *logic* changes,
parameters change, or the time period extends. Never for adding metrics.

---

## Step 1 — Framework Foundation ✅ In Progress

- [x] `TRADE_LOG_SCHEMA.md` — standardized record format with required/optional fields
- [x] `base_harness.py` — TradeLogger, shared fetch_data, BS functions, vol helpers, regime calendar
- [x] `analysis_layer.py` — full metrics engine reading any `.trades.jsonl`
- [x] `__init__.py` — makes framework a proper importable package
- [x] Proof-of-concept: `r28_v2.py` using the new base — validates end-to-end pipeline ✅ CONFIRMED WORKING

---

## Step 2 — Priority Re-Runs (Active Paper Trading Strategies)

Re-run these harnesses first because they have live capital deployed and regime
analysis has direct decision value.

- [x] PEAD — `pead_v2.py` → 112 variant trade logs (gap2-5%, hold5-60d, filters)
- [x] Pairs — `pairs_v2.py` → `pairs_r23.trades.jsonl` (10,721 trades, R20-R23)
- [x] Dividend Raise Signal — `dividend_v2.py` → `div_raise_signal_r27.trades.jsonl` (4,795 trades)
- [x] Dividend Capture — `dividend_v2.py` → `div_capture_r27.trades.jsonl` (41,861 trades)
- [x] Dogs of Dow — `dividend_v2.py` → `dogs_of_dow_r27.trades.jsonl` (165 trades)
- [x] CC around Ex-Div — `dividend_v2.py` → `div_cc_exdiv_r27.trades.jsonl` (10,406 trades)
- [x] Options R25 Covered Call — `options_v2.py` → `covered_call_r25.trades.jsonl` (710 trades)
- [x] Options R25 CSP — `options_v2.py` → `cash_secured_put_r25.trades.jsonl` (710 trades)
- [x] Options R28 — `r28_v2.py` → bull_put_spread, iron_condor, wheel (3,760 trades)

✅ STEP 2 COMPLETE — 122 total .trades.jsonl files, analysis layer validated on priority set

---

## Step 3 — Full Archive Re-Runs (via Dream Cycle)

Lower urgency — scheduled overnight via dream cycle, one or two per night.

- [ ] R1-R2: Forex rounds
- [ ] R3: Crypto
- [ ] R4-R6: Seasonals / Commodities
- [ ] R8-R14: ML, Factor, Multi-Asset, International
- [ ] R15-R22: Macro overlays, Leveraged ETFs
- [ ] R24-R26: LLM signal filtering rounds

---

## Known Limitation (v1.0): Portfolio-Level Metrics

When a strategy spans multiple tickers (e.g. 30 stocks), the analysis layer currently
chains all 815 trades into a single equity curve. This distorts CAGR, total return,
and max drawdown — they're treated as a single sequential portfolio, not 30 parallel ones.

*Metrics that ARE reliable now:* Sharpe, Sortino, win rate, profit factor, SPY correlation,
regime-conditional Sharpe, skewness, kurtosis — all computed from individual trade return
distributions. These are the high-value outputs.

*Fix needed (Step 4):* Add portfolio-aware equity curve computation — group trades by
entry month, average returns within each month (parallel positions), then compound monthly.
This will make CAGR, drawdown, and Calmar meaningful for multi-ticker strategies.

---

## Step 4 — Analysis Layer Expansion (future, no re-runs needed)

These can be added to `analysis_layer.py` at any time without touching harnesses:

- [ ] Portfolio optimizer — max Sharpe allocation across all strategies
- [ ] Correlation heatmap — cross-strategy correlation matrix
- [ ] Regime sensitivity table — all strategies × all regimes in one view
- [ ] Rolling Sharpe chart — detect strategy decay over time
- [ ] Kelly fraction calculator — optimal position sizing per strategy
- [ ] Drawdown duration analysis — how long underwater per regime
- [ ] VaR / CVaR — tail risk quantification

---

## What Forces a Harness Re-Run (document for future reference)

| Trigger | Action Required |
|---|---|
| Adding a new metric (Sortino, regime stats, etc.) | Update analysis_layer.py only — no re-run |
| Changing regime definitions | Update analysis_layer.py only — no re-run |
| Extending time period (e.g. 2025 → 2026) | Re-run affected harnesses only |
| Bug fix in strategy logic | Re-run that harness only |
| Changing strategy parameters | Re-run that harness only |
| Adding a new strategy | New harness file, no existing re-runs |

---

## Files Created

| File | Status | Description |
|---|---|---|
| `framework/TRADE_LOG_SCHEMA.md` | ✅ Done | Schema specification |
| `framework/base_harness.py` | ✅ Done | Base module with TradeLogger |
| `framework/analysis_layer.py` | 🔄 In Progress | Full metrics engine |
| `framework/__init__.py` | ⏳ Pending | Package init |
| `framework/r28_v2.py` | ⏳ Pending | R28 proof-of-concept |
| `trade_logs/` | ✅ Created | Directory for all .trades.jsonl files |
