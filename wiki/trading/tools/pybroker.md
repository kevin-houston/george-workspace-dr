---
updated: 2026-08-21
stars: 3500
url: https://github.com/edtechre/pybroker
---

# PyBroker — ML-Focused Backtesting Engine with Bootstrap Metrics & Walkforward Analysis

**edtechre/pybroker** (3.5k stars, Python, Apache 2.0 with Commons Clause, active — 1,239+ commits on master)

NumPy/Numba-accelerated backtesting framework built specifically for ML-driven strategies. PyPI package name is `lib-pybroker` (not `pybroker` — a naming quirk worth flagging so a future install doesn't grab the wrong package):

```bash
pip install -U lib-pybroker
```

Docs: [www.pybroker.com](https://www.pybroker.com/en/latest/) — 18+ tutorial notebooks covering data sources through multi-symbol models.

## Why it matters for this pipeline

Two features map directly onto open weaknesses in our own hypothesis-testing process:

1. **Bootstrap confidence intervals on Sharpe/Profit Factor, not just point estimates.** PyBroker uses the bias-corrected and accelerated (BCa) bootstrap, resampled *per-bar* (not per-trade, which would overstate confidence when trades cluster), to produce a confidence interval around Sharpe and Profit Factor. Every `run_hNNN.py` script in `backtesting/daily/` currently reports a single point-estimate OOS Sharpe against a fixed gate (e.g. 1.174) — a hypothesis that clears the gate at 1.18 and one that clears it at 2.50 are treated identically as "CONFIRMED," with no sense of how much of that gap is noise. A BCa interval would let the hypothesis-log distinguish "robustly clears the gate" from "clears by a margin bootstrap can't distinguish from zero."
2. **Walkforward Analysis as a first-class primitive**, not a script we hand-roll per hypothesis. PyBroker partitions historical data into rolling train/test windows and walks forward, retraining at each step — the same pattern our IS/OOS split approximates with a single static cut. A rolling walkforward harness would surface regime-dependent overfitting (the exact failure mode behind H435-H437's "H026 canonical OOS degrading 2024-2026" finding) earlier and more systematically than a single-split IS/OOS test.

Neither feature would have caught the `as_of`-date look-ahead bug family (H510-H514, H343-H346, H355-H356) — that was a data-plumbing bug, not a statistical-power problem — but they're complementary: once a signal is look-ahead-clean, bootstrap CIs would flag *which* of our "CONFIRMED" verdicts are actually marginal.

## Key Features

- `Strategy` / `StrategyConfig` — core backtest object, NumPy/Numba-vectorized execution loop
- `ctx.indicator(...)`, `ctx.buy_shares`, `ctx.sell_all`, `ctx.hold_bars` — rule-based execution API (see example below)
- Model registration (`pybroker.model(...)`) for ML-based strategies — predictions available inside `exec_fn` alongside indicators
- Walkforward Analysis — [Training a Model notebook](https://www.pybroker.com/en/latest/notebooks/6.%20Training%20a%20Model.html#Walkforward-Analysis), splits data into N windows, retrains per window
- Bootstrap metrics — [Evaluating with Bootstrap Metrics notebook](https://www.pybroker.com/en/latest/notebooks/3.%20Evaluating%20with%20Bootstrap%20Metrics.html), BCa confidence intervals on Sharpe/Profit Factor
- Data sources: Alpaca, Yahoo Finance (`YFinance`), AKShare, or custom provider adapters — Alpaca integration is a direct match for our existing paper account
- Data/indicator/model caching (`pybroker.enable_data_source_cache(...)`) to avoid re-downloading on every run
- Parameter optimization via Optuna integration
- Multi-timeframe signal support (daily/weekly/monthly in one strategy)

## Minimal working example (rule-based)

```python
import pybroker
from pybroker import Strategy, StrategyConfig, YFinance

pybroker.enable_data_source_cache("my_strategy")

config = StrategyConfig(initial_cash=500_000)
strategy = Strategy(YFinance(), "3/1/2017", "3/1/2022", config)

def buy_low(ctx):
    if ctx.long_pos():
        return
    if ctx.bars >= 2 and ctx.close[-1] < ctx.low[-2]:
        ctx.buy_shares = ctx.calc_target_shares(0.25)
        ctx.buy_limit_price = ctx.close[-1] - 0.01
        ctx.hold_bars = 3

strategy.add_execution(buy_low, ["AAPL", "MSFT"])
result = strategy.backtest()
print(result.metrics_df)
```

`result.metrics_df` gives the standard point-estimate metrics; bootstrap CIs are a separate call (`strategy.backtest(..., calc_bootstrap=True)` in recent versions, or a dedicated `result.bootstrap` accessor per the Evaluating with Bootstrap Metrics notebook — confirm exact API against the installed version before scripting against it).

## Limitations / what it doesn't solve

- License is "Apache 2.0 with Commons Clause" — Commons Clause restricts *selling* the software; irrelevant for internal research use, worth noting only if this project were ever externally productized.
- Bootstrap and walkforward are still statistical-power tools, not look-ahead-bias detectors — they would not have caught the OB `as_of` bug class; that requires the kind of manual "does this function receive a future date" audit already documented in the H510-H514 correction chain.
- Adds a second backtesting API alongside our existing pandas/yfinance/vectorbt-adjacent hand-rolled `run_hNNN.py` pattern — not a drop-in replacement, would need a parallel-run validation phase before any hypothesis-log verdict trusted its bootstrap CI over the current point estimate.

## Relevance to pipeline

- Best near-term use: retrofit `evaluate()`-style functions in a *few* recent `run_hNNN.py` scripts with PyBroker's bootstrap Sharpe CI as a sanity check, without migrating the whole pipeline off pandas.
- Longer-term candidate: a shared `walkforward_gate.py` helper using PyBroker's windowing, replacing each script's bespoke single-split IS/OOS logic — would make the WF ratio (already tracked ad hoc in several hypothesis-log entries, e.g. H310's WF 13-19x regime-shift flag) a built-in, comparable number instead of a per-hypothesis afterthought.
- Not relevant to the options/dispersion family (H309, H266) the way qf-lib is — PyBroker has no event-driven options/assignment modeling; qf-lib remains the right tool there.
