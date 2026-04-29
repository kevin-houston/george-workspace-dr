---
updated: 2026-04-29
status: active
broker: Alpaca Paper ($ALPACA_API_KEY / $ALPACA_SECRET)
started: 2026-04-28
script: backtesting/paper_trading/h112_monthly.py
monitor: backtesting/paper_trading/monitor.py
log: backtesting/paper_trading/h112_monthly_trades.json
---

# H122 Alpaca Paper Portfolio

Production momentum rotation portfolio running on Alpaca paper trading.
Target → real money once 4–8 weeks of paper validation clears.

## Strategy Architecture

Total equity split: **rotation 70% + IBS 30%** (IBS handled manually via `run_daily.py`; rotation auto-rebalances monthly).

| Sub-strategy | Base Weight | Assets | n_hold | Notes |
|---|---|---|---|---|
| H041a | 22% | 19 global equity ETFs (SPY, QQQ, TLT, GLD, IEF, EFA, EEM, BIL, Pacific Rim, Europe) | top-1 | No TSMOM filter |
| H026 | 27% (vol-adjusted) | 25 sector/commodity/bond ETFs | top-1 | TSMOM filter: 12m > 0 required |
| H045 | 21% | 13 fixed income ETFs (SHY→TLT, HYG, LQD, BKLN, EMB, BIL, MBB, FLOT, PCY) | top-2 | No TSMOM filter |

**IBS (not auto-managed):** XLK 20%, SMH 8%, IGV 2%

## Signal: Rank Ensemble (H120)

All three rotation sub-strategies use the same ranking formula:

```
score = rank(12m_return) + rank(6m_return) + rank(3m_return) + rank(1/6m_vol)
```

Each lookback ranked independently (1..N) then summed — prevents 12m absolute returns from dominating. TSMOM filter for H026 uses 12m sign check only (unchanged).

Confirmed +28% OOS improvement over 12m-only signal (H119 backtest).

## H026 Vol-Targeting (H122)

After accumulating ≥3 months of log history, H026 weight scales dynamically:

```
scale     = clamp(15% / realized_6m_vol_H026, 0.5x, 2.0x)
H026_eff  = 27% × scale
# then all three rotation weights renorm so they still sum to 70%
```

`15%` is the approximate long-run annualized vol of H026 from backtests.
Until 3 months of history exist, falls back to fixed 27%.

**Why H026 only:** Targeting all three or risk-parity both hurt OOS badly in H121 backtest. H026 (sector rotation) benefits because its concentrated top-1 selection amplifies drawdowns during high-vol regimes.

## Rebalance Schedule

- **When:** First trading day of each month, 9:45 AM CT
- **How:** `python3 h112_monthly.py` (auto-detects first trading day)
- **Force:** `--force` to override date guard
- **Dry-run:** `--dry-run` to preview orders without submitting

## Backtest Reference Numbers

| Hypothesis | OOS Cumul | AltOOS Cumul | OOS Sharpe | MaxDD | NegYrs |
|---|---|---|---|---|---|
| H116 (baseline + TSMOM) | 6.56 | 14.94 | 3.845 | -3.6% | 0 |
| H120 (+ rank ensemble) | 24.77 | 85.99 | 4.354 | -3.5% | 0 |
| H122 (+ H026 vol-target) | 27.88 | 103.53 | 4.535 | -3.8% | 0 |

OOS = 2018-01-01 onwards. AltOOS = 2013-01-01 onwards. Cumul = × initial equity.

## Performance Tracking

Paper account started 2026-04-28. Current inception P&L visible via:

```bash
python3 monitor.py --brief   # equity + P&L snapshot
python3 monitor.py           # full positions + drift from target
python3 monitor.py --signal  # recompute live signal (slow)
```

### Trade Log Summary

The JSON log at `h112_monthly_trades.json` stores each rebalance with:
- `date`, `equity`, `eff_weights`, `h026_scale`, `signals`, `trades`

## May 1 2026 Rebalance Preview (H122 signal)

Expected signal based on April 29 data (subject to final-day price changes):

| Sub | Selection | Basis |
|---|---|---|
| H041a | EWT (Taiwan) | QQQ large but EWT leads rank ensemble on tech semiconductor momentum |
| H026 | DBC (commodity basket) | TSMOM filter passes; commodity momentum ranks highest |
| H045 | FLOT + HYG | Floating rate + HY bonds lead fixed income rank |

H026 vol-scale will be 1.0 for May 1 (only 1 log entry — need ≥3).

## Files

| File | Purpose |
|---|---|
| `h112_monthly.py` | Main rebalancer (H122 production) |
| `monitor.py` | Portfolio monitor / signal recomputer |
| `h112_monthly_trades.json` | Persistent trade log |
| `kalshi_cpi.py` | Kalshi CPI nowcasting (pending credentials) |
