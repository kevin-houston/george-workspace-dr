# Trade Log Schema — v1.0
**Established:** 2026-04-01
**Purpose:** Standardized trade record format for all NanoClaw trading eval harnesses (R29+).
Retroactive re-runs of R1-R28 should also adopt this schema.

---

## Core Principle

Harnesses produce **data**. The analysis layer produces **insights**.

A harness outputs one file: `{name}.trades.jsonl` — one JSON record per line, one line
per trade. No Sharpe ratios, no win rates, no summaries inside the harness output.
All derived metrics are computed by `analysis_layer.py` on demand.

This means: to add a new metric, you update the analysis layer. You never need to
re-run a harness unless the strategy logic itself changes.

---

## Trade Record Format

Each line in a `.trades.jsonl` file is a valid JSON object with these fields:

### Required Fields

| Field | Type | Description |
|---|---|---|
| `round` | int | Eval round number (1-28+) |
| `strategy` | str | Strategy identifier, snake_case (e.g. `pead_gap5_20d`) |
| `ticker` | str | Primary instrument (e.g. `AAPL`, `XOM`, `^VIX`) |
| `entry_date` | str | ISO 8601 date of trade entry (e.g. `2022-03-14`) |
| `exit_date` | str | ISO 8601 date of trade exit |
| `return_pct` | float | Fractional return for this trade (0.05 = 5%) |
| `hold_days` | int | Calendar days held |

### Optional but Strongly Recommended

| Field | Type | Description |
|---|---|---|
| `category` | str | Strategy category (`pead`, `pairs`, `options`, `dividend`, `crypto`, etc.) |
| `entry_price` | float | Price at entry |
| `exit_price` | float | Price at exit |
| `direction` | str | `long` or `short` |
| `params` | dict | Strategy parameters used for this trade |
| `notes` | str | Human-readable context (e.g. `"assigned at 185.00"`) |

### Options-Specific Fields (add when applicable)

| Field | Type | Description |
|---|---|---|
| `option_type` | str | `call`, `put`, `straddle`, `condor`, `spread` |
| `strike` | float | Primary strike price |
| `expiry_date` | str | Option expiration date |
| `premium_collected` | float | Premium collected (if selling) |
| `premium_paid` | float | Premium paid (if buying) |
| `iv_at_entry` | float | Implied vol estimate at entry |
| `iv_rank_at_entry` | float | IV rank (0-100) at entry |

### Pairs-Specific Fields

| Field | Type | Description |
|---|---|---|
| `leg_a` | str | First leg ticker |
| `leg_b` | str | Second leg ticker |
| `spread_zscore` | float | Z-score at entry |

---

## Example Records

### PEAD trade
```json
{"round": 7, "strategy": "pead_gap5_20d", "category": "pead",
 "ticker": "AAPL", "entry_date": "2022-03-14", "exit_date": "2022-04-11",
 "return_pct": -0.0312, "hold_days": 28, "direction": "long",
 "entry_price": 150.62, "exit_price": 145.92,
 "params": {"gap_threshold": 0.05, "hold_days": 20}}
```

### Bull put spread
```json
{"round": 28, "strategy": "bull_put_spread", "category": "options",
 "ticker": "XOM", "entry_date": "2022-06-01", "exit_date": "2022-07-01",
 "return_pct": 0.1823, "hold_days": 30, "direction": "short_put",
 "entry_price": 95.40, "option_type": "spread",
 "strike": 95.40, "expiry_date": "2022-07-01",
 "premium_collected": 0.0412, "iv_rank_at_entry": 72.3,
 "params": {"iv_rank_threshold": 50, "wing_width": 0.05}}
```

### Pairs trade
```json
{"round": 23, "strategy": "pairs_zscore_2sd", "category": "pairs",
 "leg_a": "JNJ", "leg_b": "UNH", "ticker": "JNJ_UNH",
 "entry_date": "2021-08-10", "exit_date": "2021-09-03",
 "return_pct": 0.0241, "hold_days": 24,
 "spread_zscore": 2.14,
 "params": {"entry_z": 2.0, "exit_z": 0.5, "window": 60}}
```

---

## File Naming Convention

```
trading_eval/trade_logs/{strategy_name}_r{round:02d}.trades.jsonl
```

Examples:
- `trade_logs/pead_gap5_r07.trades.jsonl`
- `trade_logs/bull_put_spread_r28.trades.jsonl`
- `trade_logs/wheel_r28.trades.jsonl`
- `trade_logs/corn_seasonal_r12.trades.jsonl`

---

## What the Analysis Layer Computes From This

Given any `.trades.jsonl` file, `analysis_layer.py` automatically computes:

- Sharpe ratio (annualized)
- Sortino ratio (downside deviation only)
- Calmar ratio (CAGR / max drawdown)
- Return skewness and kurtosis
- Max drawdown and recovery time
- Max consecutive losing trades
- Win rate, avg win, avg loss, profit factor
- SPY correlation (matched by trade period)
- Regime-conditional Sharpe (bull / bear / crisis / high-vol / low-vol)
- Cross-strategy correlation matrix (when multiple strategies present)
- Kelly fraction and suggested position size

---

## Versioning

This is schema v1.0. If fields are added, increment to v1.1. If fields are removed
or renamed, increment to v2.0. The analysis layer must handle missing optional fields
gracefully (use `record.get('field', None)` throughout).
