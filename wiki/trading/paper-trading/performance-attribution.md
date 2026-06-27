---
title: Multi-Strategy Performance Attribution & Drawdown Analysis
added: 2026-06-27
category: paper-trading
---

# Multi-Strategy Performance Attribution & Drawdown Analysis

Practitioner guide for decomposing P&L across strategy sleeves, measuring drawdowns, and deciding when to pause or rebalance in a live blended portfolio.

## 1. Brinson Attribution Adapted for Quant Sleeves

The classical Brinson-Hood-Beebower model splits return into **allocation effect** (did we weight winning strategies correctly?) and **selection effect** (did the strategy beat its own average?). For a multi-strategy quant book this adapts cleanly:

```
Sleeve P&L = (Actual Weight - Target Weight) × Strategy Return   [Allocation Effect]
           + Actual Weight × (Strategy Return - Strategy Mean)    [Selection Effect]
```

```python
def sleeve_attribution(daily_returns_df, actual_weights_df, target_weights):
    """
    daily_returns_df : columns = strategy names, index = dates
    actual_weights_df: same shape — daily realized weights
    target_weights   : dict {strategy: float}
    Returns DataFrame of allocation_effect and selection_effect per sleeve per day.
    """
    attr = {}
    for strat in daily_returns_df.columns:
        tw = target_weights[strat]
        aw = actual_weights_df[strat]
        r  = daily_returns_df[strat]
        attr[f'{strat}_alloc']  = (aw - tw) * r
        attr[f'{strat}_select'] = aw * (r - r.mean())
        attr[f'{strat}_total']  = attr[f'{strat}_alloc'] + attr[f'{strat}_select']
    return pd.DataFrame(attr)
```

**Production portfolio allocations (target weights):**

| Strategy | Target | Typical monthly allocation swing |
|----------|--------|----------------------------------|
| H026 ETF rotation | 27% | ±5% → ±1.2%/mo attribution |
| H041a 19-asset top-1 | 22% | ±4% → ±0.9%/mo |
| H045 bond rotation | 21% | ±3% → ±0.6%/mo |
| XLK IBS | 20% | low drift (daily execution) |
| SMH IBS | 8% | low drift |
| IGV IBS | 2% | low drift |
| H174 PEAD | event | contributes only on trade months |

**Key insight:** Monthly rebalancing decision rule — if a sleeve's selection effect is consistently negative (i.e., the strategy underperforms its own mean for 3+ consecutive months), check for regime shift, not just bad luck.

---

## 2. Regime Attribution

Strategies don't have single Sharpes — they have regime-conditional Sharpes. Track separately.

```python
def regime_attribution(daily_returns_df, spy_prices, vix_series):
    sma200   = spy_prices.rolling(200).mean()
    is_bull  = spy_prices > sma200
    is_calm  = vix_series < 25

    regime = pd.Series('bear_volatile', index=daily_returns_df.index)
    regime[is_bull &  is_calm] = 'bull_calm'
    regime[is_bull & ~is_calm] = 'bull_stressed'
    regime[~is_bull & is_calm] = 'bear_calm'

    results = {}
    for strat in daily_returns_df.columns:
        r = daily_returns_df[strat]
        results[strat] = {
            reg: r[regime == reg].mean() / r[regime == reg].std() * np.sqrt(252)
            for reg in regime.unique()
            if (regime == reg).sum() > 10
        }
    return pd.DataFrame(results).T
```

**Confirmed regime profiles for our production strategies:**

| Strategy | bull_calm | bull_stressed | bear_calm | bear_volatile |
|----------|-----------|---------------|-----------|---------------|
| H026 ETF rotation | ~2.8 | ~1.4 | ~0.8 | Weak (exits to BIL) |
| H045 bond rotation | Moderate | Strong (flight-to-quality) | Strong | Strong |
| H192-D BAB | Positive | Strong | ~1.8 | ~1.8 |
| H174 PEAD | Regime-neutral | Regime-neutral | — | — |
| IBS mean-reversion | Moderate | High vol → more signals | Moderate | Very strong |

**MRP (Minimum Regime Performance) threshold:**
- MRP > 0.0 = acceptable (no regime where strategy structurally loses)
- MRP > 0.4 = robust (positive Sharpe in all four regimes)
- MRP < 0.0 for 2+ regimes = consider tactical pause or allocation cut

---

## 3. Drawdown Analysis

### Core metrics

```python
def drawdown_stats(equity_curve):
    ec  = pd.Series(equity_curve)
    hwm = ec.cummax()                        # high-water mark
    dd  = (ec - hwm) / hwm                   # drawdown series

    max_dd     = dd.min()
    trough_dt  = dd.idxmin()

    # Peak date (most recent peak before trough)
    peak_dt    = ec[:trough_dt].idxmax()
    duration   = (trough_dt - peak_dt).days

    # Recovery: first date after trough that exceeds prior high-water mark
    post_trough = ec[trough_dt:]
    hwm_at_trough = hwm[trough_dt]
    recovered   = post_trough[post_trough >= hwm_at_trough]
    recovery_days = (recovered.index[0] - trough_dt).days if len(recovered) > 0 else None

    ann_return  = (ec.iloc[-1] / ec.iloc[0]) ** (252 / len(ec)) - 1
    calmar      = ann_return / abs(max_dd)

    return {
        'max_dd_pct'    : max_dd,
        'peak_date'     : peak_dt,
        'trough_date'   : trough_dt,
        'duration_days' : duration,
        'recovery_days' : recovery_days,
        'calmar_ratio'  : calmar,
    }
```

**Production portfolio benchmarks (OOS 2004–2025):**

| Metric | Production blend | SPY alone |
|--------|-----------------|-----------|
| MaxDD | −3.6% | −55.2% (GFC) |
| MaxDD duration | ~18 days | ~370 days |
| Recovery time | 28–45 trading days | 1,500+ days |
| Calmar ratio | 6.5+ | ~0.5 |

### Underwater curve analysis

```python
def underwater_periods(equity_curve, threshold_pct=-0.05):
    """Find all periods equity stayed > threshold below its high-water mark."""
    ec = pd.Series(equity_curve)
    dd = (ec - ec.cummax()) / ec.cummax()
    in_dd = dd < threshold_pct

    periods, start = [], None
    for dt, flag in in_dd.items():
        if flag and start is None:
            start = dt
        elif not flag and start is not None:
            periods.append({
                'start': start, 'end': dt,
                'depth': dd[start:dt].min(),
                'duration_days': (dt - start).days
            })
            start = None
    return periods
```

### Drawdown action thresholds

| Portfolio drawdown | Action |
|--------------------|--------|
| < −8% | Normal cycle — no action |
| −8% to −15% | Review strategy correlations; check regime state |
| −15% to −25% | Consider reducing highest-vol sleeve 25%; file incident log |
| > −25% | Yellow flag — if recovery > 90 trading days, pause one strategy |

**Why portfolio MaxDD << sleeve MaxDD:**
Strategy drawdowns are not perfectly correlated. From OOS correlation analysis:

| Pair | DD correlation |
|------|---------------|
| H026 DD vs H181 DD | −0.10 (negative — they hedge each other) |
| H026 DD vs H198 DD | +0.45 (both momentum → correlated) |
| H174 PEAD vs H026 | +0.05 (event-driven vs trend — orthogonal) |
| IBS vs monthly sleeves | ~0.21 (daily vs monthly horizon — low) |

Portfolio MaxDD ≈ 30–50% of worst-sleeve MaxDD due to this diversification. If portfolio DD suddenly matches a single sleeve's DD, it signals the diversification has broken (regime transition or strategy failure).

---

## 4. Weekly & Monthly Monitoring Checklist

### Daily (automated)

```python
DAILY_FLAGS = {
    'portfolio_drawdown'    : ('> -0.08', 'check regime'),
    'any_sleeve_drawdown'   : ('> -0.15', 'review sleeve'),
    'alpaca_buying_power'   : ('< 10k', 'check margin'),
    'open_pead_positions'   : ('> 5', 'check concentration'),
}
```

### Weekly (Friday EOD)

| Metric | Flag threshold | Action |
|--------|---------------|--------|
| Rolling 60-day portfolio Sharpe | < 0.5 | Review signal decay |
| Per-strategy Information Ratio (annualized) | < 0.8 | Reduce 25% or pause |
| Slippage vs. budget | > +0.5% of trade notional | Check fills / order routing |
| Turnover vs. backtest IS | > 20% above estimate | Capacity / execution concern |
| Win rate per strategy (if ≥ 20 trades) | < 45% | Regime check; consider pause |

### Monthly (after rebalance)

| Metric | Flag threshold | Action |
|--------|---------------|--------|
| Strategy correlation matrix (30-day rolling) | Any pair > 0.75 | Consolidate redundant sleeves |
| Regime attribution (MRP) | Any regime Sharpe < 0 | Reduce allocation 50% |
| Cumulative slippage drag | > 0.5% annualized above backtest | Audit execution |
| Per-strategy OOS Sharpe (6-month rolling) | < 0.5 | Formal review; H-number audit |

```python
def weekly_monitoring_report(strategy_returns, actual_weights, orders_log):
    """
    strategy_returns : DataFrame, columns = strategies, daily
    actual_weights   : DataFrame, same shape
    orders_log       : DataFrame with columns: strategy, fill_price, mid_price
    """
    report = {}
    for strat in strategy_returns.columns:
        last_60 = strategy_returns[strat].tail(60)
        sharpe  = last_60.mean() / last_60.std() * np.sqrt(252) if last_60.std() > 0 else 0
        win_rate = (last_60 > 0).mean()

        fills = orders_log[orders_log['strategy'] == strat].tail(20)
        slippage_bps = ((fills['fill_price'] - fills['mid_price']).abs().mean() * 1e4
                        if len(fills) > 0 else 0)

        report[strat] = {
            'rolling_sharpe_60d' : round(sharpe, 2),
            'win_rate_60d'       : round(win_rate, 3),
            'slippage_bps'       : round(slippage_bps, 1),
            'open_pnl'           : strategy_returns[strat].sum(),
        }
    return pd.DataFrame(report).T
```

---

## 5. Python Library Landscape

| Library | Stars | Best for | Gap |
|---------|-------|----------|-----|
| **quantstats** | ~4,500 | 50+ metrics, HTML tearsheets, rolling Sharpe — `qs.reports.html(returns, benchmark=spy)` | Single return series only; no multi-strategy attribution |
| **pyfolio** | ~5,200 (archived 2021) | Sector attribution, factor exposure (via Alphalens) | No maintenance since 2021; breaks on Python 3.11+ |
| **riskfolio-lib** | ~3,700 | 24 risk measures, HRP/NCO portfolio construction, regime-conditional optimization | No performance attribution — construction tool only |
| **skfolio** | ~1,300 | Walk-forward CV, ensemble portfolio optimization | Attribution missing |
| **empyrical** | ~1,200 | Standardized risk/return metric functions used internally by pyfolio | Low-level; no visualization |

**Recommended stack:**
1. `quantstats` for per-strategy tearsheets (`qs.reports.html(sleeve_returns, benchmark=spy_returns)`)
2. Custom pandas `sleeve_attribution()` + `regime_attribution()` for blended P&L decomposition
3. `riskfolio-lib` only if optimizing weights (not needed for fixed-weight production blend)

```bash
pip install quantstats riskfolio-lib  # empyrical installed as quantstats dep
```

---

## 6. When to Pause a Strategy

**Statistical threshold (sequential probability ratio test):**

H₀: strategy has Sharpe ≥ 0.5 (acceptable)
H₁: strategy has Sharpe < 0 (failing)

SPRT boundaries (from `live-graduation-criteria.md`):
- Continue if LLR > log(1 − β) / α
- Stop/pause if LLR < log(β / (1 − α))
- Typical α = 0.05, β = 0.20 → need ~40 trades to reject H₀ at 5% significance

**Practical heuristic (if not running SPRT):**

```
Pause condition (ANY of):
  1. Rolling 60-day Sharpe < 0 for 3 consecutive months
  2. Win rate < 40% over 40+ trades
  3. Drawdown exceeds 2× historical MaxDD
  4. Regime attribution: MRP < -0.5 in current regime (strategy structurally wrong for regime)
```

**Resume condition:**
- Regime shifts back to strategy's favored state AND
- 3 confirmed live trades positive after pause

---

## See Also

- [Strategy Blending & Correlation Management](../backtesting/strategy-blending-correlation.md) — correlation matrix, IC-weighted blending
- [Live Graduation Criteria & Performance Attribution](live-graduation-criteria.md) — SPRT test, trade count gates
- [Risk Controls & Live Trading Monitoring](risk-controls-and-monitoring.md) — circuit breakers, kill switch
- [Execution Quality & Slippage Analysis](execution-quality.md) — slippage budget per strategy
