---
added: 2026-05-28
updated: 2026-05-28
category: algorithms
tags: [mean-reversion, intraday, ETF, IBS, daily-bar, tech-sector]
production: true
---

# IBS (Internal Bar Strength) Mean-Reversion Strategy

## What is IBS?

Internal Bar Strength (IBS) measures where the day's closing price falls within the session's high-low range:

```
IBS = (Close − Low) / (High − Low)
```

The result oscillates between 0 and 1:
- **IBS near 0** → close near the low of day (oversold, mean-reversion entry signal)
- **IBS near 1** → close near the high of day (overbought, exit signal)

IBS is purely price-derived from OHLC data — no parameters to estimate, no lags.

## Why it works

The signal exploits intraday mean reversion in ETFs. When institutional sellers drive prices to the low of a day's range and close there, the next day's open and the following days tend to recover. The effect is strongest in equity indices and broad-market ETFs. Academic research confirms persistence across decades:

- **Pagonidis (2013)** — *"The IBS Effect: Mean Reversion in Equity ETFs"* (Semantic Scholar). Documents a consistent daily mean-reversion edge in US equity ETFs with Sharpe ratios materially above passive.
- **Pandey & Joshi (2023)** — *arXiv:2306.12434* — "Using Internal Bar Strength as a Key Indicator for Trading Country ETFs." Applied to a basket of country ETFs over 10 years; reports Sharpe ratios up to 3.9 with straightforward IBS rules. Confirms the edge is geographically broad but weakens in commodity-heavy markets (oil exporters, gold miners).

## Standard parameters (literature baseline)

| Threshold | Typical value | Interpretation |
|-----------|---------------|----------------|
| Buy (entry) | IBS < 0.2 | Last close near session low → oversold |
| Sell (exit) | IBS > 0.8 | Current close near session high → overbought |
| Max hold | varies | Safety exit if IBS does not reach sell threshold |

Literature results (QuantifiedStrategies SPY backtest): CAGR 15.3%, Sharpe ~1.7, 74% win rate, invested only ~36% of the time.

## Our implementation — production parameters

Through H062–H075 we found that tech-sector ETFs have distinct optimal parameters compared to SPY. The key insight (H069): XLK and SMH have **opposite** optimal exit thresholds — XLK bounces slowly to IBS 0.90 over 7 days, while SMH is more volatile and exits at IBS 0.75 in 6 days. IGV requires a positive gap filter (software stocks that gap up but close low are more likely to continue rising).

| Ticker | Buy threshold | Sell threshold | Max hold (days) | Gap filter | Production weight |
|--------|--------------|----------------|-----------------|------------|-------------------|
| XLK    | < 0.15       | > 0.90         | 7               | ≥ −1.0%    | 20%               |
| SMH    | < 0.20       | > 0.75         | 6               | ≥ −0.5%    | 8%                |
| IGV    | < 0.30       | > 0.75         | 5               | ≥ +0.25%   | 2%                |

**Total IBS budget:** 30% of portfolio (remaining 70% is rotation strategies H041a/H026/H045).

### Entry rule (signal day → next open)
```
if ibs[t-1] < buy_threshold AND (open[t] - close[t-1]) / close[t-1] >= gap_filter:
    enter LONG at open[t]
```

### Exit rule (any subsequent day)
```
if ibs[t] > sell_threshold OR days_held >= max_hold:
    exit at close[t]
```

Note: entry uses the **open** on the day after the signal (to avoid look-ahead bias — the close that generates the signal is not tradeable at that price). Exit uses the **close** on the exit day.

### Gap filter rationale
- XLK and SMH use a **negative** gap filter (−1.0%, −0.5%): the stock is allowed to gap down slightly — we want the oversold condition to persist into the open, not gap back up immediately.
- IGV uses a **positive** gap filter (+0.25%): software stocks that gap up *but* closed near the session low are the ones with real bounce potential. A gap-down IGV open typically continues lower.

## Hypothesis development log

| Hypothesis | Status | Key finding |
|-----------|--------|-------------|
| H062 | Explored | First IBS introduction; SPY-calibrated params tested on QQQ |
| H063 | Preliminary | Reconstruction errors (momentum signal incorrect); fixed in H064 |
| H064 | Fixed | Correct IS/OOS reconstruction baseline established |
| H065 | CONFIRMED | XLK=20% + SMH=8% chosen over alternatives; WF worst 2.395 |
| H066 | Fine-grid | Fine-grid split testing of XLK/SMH at 28% and 32% total IBS |
| H067 | CONFIRMED | XLK+SMH IBS removes H045 upper-bound constraint; portfolio OOS 2.379 |
| H069 | CONFIRMED | Tech-specific params; XLK/SMH differ in exit speed; OOS +7.2% vs SPY params |
| H074 | CONFIRMED | IGV IBS: buy=0.30/sell=0.75/hold=5/gap=+0.25%; OOS 1.442, Deg +130% |
| H075 | PARTIAL | IGV at 2% portfolio weight; MaxDD improves, OOS +0.053 on primary, AltOOS marginal |
| H149 | CONFIRMED | Re-split analysis: 70% rotation / 30% IBS is optimal; pure H026 at 100% underperforms the blend |

## Portfolio context

The IBS tranche provides **daily liquidity and smoother returns** that complement the monthly-rebalanced rotation strategies. Key portfolio statistics (H149, OOS 2018–2026):

- Rotation (H026) alone: Sharpe ~2.2
- IBS alone (XLK+SMH+IGV, 30%): Sharpe ~1.4–1.7
- Blend (70% rotation + 30% IBS): Sharpe ~3.1–3.4
- Correlation of IBS returns to H026 monthly returns: low (different frequencies, different assets)

The diversification benefit is real: the IBS tranche catches intraday oversold bounces in tech, while H026 rotates across sectors/assets on monthly momentum. In drawdown periods for H026 (sector rotation misses), IBS may still fire frequently.

## Code reference

`/workspace/agent/backtesting/daily/run_h149.py` — production parameter sweep and final portfolio weight optimization.

Key function: `ibs_equity_curve(ohlc, buy, sell, hold, gap)` — takes OHLC DataFrame and the four parameters, returns an equity curve.

## Limitations and risks

1. **Intraday vol collapse** — In extremely low-volatility regimes (H/L range near zero), IBS becomes undefined (0/0). Production code fills to 0.5 (neutral) on doji days.
2. **Gap-open risk** — Entry is at the next day's open. A large overnight gap in either direction can materially change the risk/reward. The gap filter partially controls this (requiring gap ≥ threshold).
3. **Regime sensitivity** — IBS underperforms during strong trending markets (2020 COVID recovery, 2023 AI rally). The effect is strongest in volatile or sideways markets. Since we're using it in tech ETFs specifically in bear/sideways regime legs, this is partially mitigated.
4. **Commodity ETFs** — Pandey & Joshi confirm IBS breaks down in commodity-heavy markets. We deliberately exclude GLD, SLV, USO, DBC from the IBS tranche.
5. **Capacity** — This strategy scales poorly to large capital. The edge comes from intraday range movements in liquid ETFs; at institutional size slippage erodes returns. At paper/small-account size it is not a concern.

## Related wiki pages

- [Momentum Strategies](momentum-strategies.md) — H026/H041a rotation leg
- [Short-Term Reversal](short-term-reversal.md) — industry-adjusted reversal (H181), related mean-reversion family
- [Factor Models & Cross-Sectional Alpha](factor-models.md)
- [Regime Detection](regime-detection.md) — IBS works better when regime gate is active

## Sources

- Pandey & Joshi (2023): [arXiv:2306.12434 — Using Internal Bar Strength as a Key Indicator for Trading Country ETFs](https://arxiv.org/abs/2306.12434)
- Pagonidis (2013): [The IBS Effect: Mean Reversion in Equity ETFs (Semantic Scholar)](https://www.semanticscholar.org/paper/The-IBS-Effect%3A-Mean-Reversion-in-Equity-ETFs-Pagonidis/1e11292ec9a87a9e3e19de87a28542a381cc774b)
- QuantifiedStrategies: [IBS Indicator Strategy](https://www.quantifiedstrategies.com/internal-bar-strength-ibs-indicator-strategy/)
- Alvarez Quant Trading: [IBS for Mean Reversion](https://alvarezquanttrading.com/blog/internal-bar-strength-for-mean-reversion/)
