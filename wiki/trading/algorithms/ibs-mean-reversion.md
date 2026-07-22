---
added: 2026-05-28
updated: 2026-07-22
category: algorithms
tags: [mean-reversion, intraday, ETF, IBS, daily-bar, tech-sector, microstructure]
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

---

## Microstructure Mechanism — Why IBS Works (2025–2026 Research)

### The FRI Sign/Magnitude Decomposition (arXiv:2606.29591)

Portnaya (Jun 2026) decomposes SPY's lag-1 autocorrelation using the Fourier-Residue Identity into two orthogonal channels:

| Channel | What it tests | SPY lag-1 result |
|---------|---------------|------------------|
| **Sign channel (k=2)** | Does yesterday's direction predict today's direction? | p = 0.11 — NOT significant |
| **Magnitude channel (k=4)** | Does yesterday's move SIZE predict today's move size? | p < 10⁻¹² — overwhelmingly significant |

The canonical short-term reversal at lag-1 is entirely magnitude compression, not directional reversal.

IBS operates at a different but related channel: it measures not the *size* of the prior day's close-to-close return, but the *position* of the close within the day's range (close − low) / (high − low). When IBS is low:
- The day had a large intraday sell-off (H/L range was wide)
- Sellers dominated throughout the session, pushing close to the session low
- This creates the conditions for magnitude compression the following day: sellers are exhausted, bid-ask spread normalizes, liquidity replenishes

**Connection to H428 (proposed):** Use the magnitude channel (prior day's range size relative to its recent average) to SIZE IBS positions. A day where IBS < 0.15 AND the intraday range was unusually large (magnitude outlier) may signal a stronger bounce than the same IBS on a quiet, narrow-range day — but also carries more gap risk. The H428 design investigates the optimal sizing function.

See [Market Microstructure & HFT](market-microstructure.md) §3 for the full FRI math.

---

### Asymmetric Liquidity Replenishment (arXiv:2511.06177)

Vlasiuk & Smirnov (Nov 2025) — *"Push-response anomalies in high-frequency S&P 500 price series"* — analyzed 1,500 trading days of SPY NBBO data.

**Key finding directly validating IBS buy entries:**

> "Large negative pushes are followed by stronger positive responses than equally large positive pushes, consistent with asymmetric liquidity replenishment after sell-side shocks."

Mechanism: after sustained institutional selling drives the close to the daily low (IBS → 0), the ask-side order book replenishes faster than after equally large buy-side pressure. Sellers exhaust supply; buy-side liquidity re-enters at lower prices. The IBS entry captures the moment AFTER the sell-side shock, before the liquidity replenishment.

Quantified pattern: for "pushes" beyond ~5,000 ticks in magnitude, conditional next-period responses are systematically positive after downward pushes. Smaller pushes show near-zero conditional response — confirming IBS matters most on HIGH-magnitude sell days (large range, close near low).

**Practical size filter derived from this:** Require minimum daily range (e.g., H/L range > 0.5× 20-day ATR) on signal days to ensure the magnitude is large enough to trigger asymmetric replenishment.

```python
def range_above_atr_filter(ohlc: pd.DataFrame, atr_mult: float = 0.5, window: int = 20) -> pd.Series:
    """True when today's H/L range exceeds atr_mult × ATR(window). Filters for meaningful IBS signals."""
    daily_range = ohlc["High"] - ohlc["Low"]
    atr = daily_range.rolling(window).mean()
    return daily_range > atr_mult * atr
```

---

### Daytime vs Overnight Return Decomposition (MDPI Risks, 2026)

A 2026 MDPI *Risks* study examined 24 overnight vs. daytime strategies across 10 sector ETFs over 27 years (1999–2025):

| Return period | Character | ETF direction |
|--------------|-----------|---------------|
| **Overnight** (close → next open) | Persistent positive drift, low volatility | Positive in all 10 ETFs |
| **Daytime** (open → close) | Near-zero drift unconditionally | Losses in 8/10 ETFs for raw long |

IBS is a **daytime strategy** (entry at next morning's open, exit at close). The unconditional daytime long has near-zero expected return, but IBS SELECTS specific days where prior session's sell-side pressure creates a mean-reversion edge within the daytime window.

**Implication:** An IBS-plus-overnight composite strategy is theoretically sound. If the bounce begins overnight (positive drift), the open-of-day entry misses that leg. For extreme IBS signals (IBS < 0.10), consider entering at the **prior close** to capture both the overnight positive drift AND the subsequent daytime reversal. Transaction costs are binding at this frequency — viable only with execution costs ≤ 2 bps.

---

## Enhancement Paths — Staged Hypotheses

### H428: FRI Magnitude-Sized IBS

**Proposed hypothesis** (staged 2026-07-22):

Use the FRI magnitude channel directly for position sizing. Replace fixed-weight IBS entry with size that adjusts for prior-day range magnitude:

```python
def magnitude_sized_ibs_weight(ohlc: pd.DataFrame, lookback: int = 20) -> float:
    """
    Size IBS positions inversely proportional to recent range magnitude.
    After EXTREME ranges, uncertainty is higher — size smaller.
    After NORMAL ranges where close lands near low, size normally.
    """
    daily_range = (ohlc["High"] - ohlc["Low"]) / ohlc["Close"]
    range_z = (daily_range.iloc[-1] - daily_range.rolling(lookback).mean().iloc[-1]) \
              / daily_range.rolling(lookback).std().iloc[-1]
    # Z=0 → normal → full size; Z=+2 → extreme → half size
    return float(1.0 / (1.0 + 0.5 * max(range_z, 0)))

# Usage within IBS signal day check:
# if ibs[t-1] < buy_threshold:
#     position_size = base_weight * magnitude_sized_ibs_weight(ohlc)
```

**Gate:** OOS Sharpe > current IBS baseline (XLK standalone ~1.4–1.7)

**Economic rationale:** On extreme sell-off days (large range, close near low), the magnitude channel signal is strong but overnight gap uncertainty is also higher. Normal range days where close just happens to land near the low are cleaner signals with less gap risk — they should be sized up relative to extreme-magnitude days.

---

### IBS + OB Exit Filter

H343–H346 (OB filter on H198/H026/H041a universes) showed that Order Block exit timing increases OOS Sharpe by 0.3–0.8 across every universe tested. The OB pattern identifies swing highs that provide resistance — when price approaches a prior OB zone, it signals optimal exit timing.

**Application to IBS exit:**

Currently, IBS exits when IBS > sell_threshold OR max_hold days reached. Adding an OB resistance check:

```python
from smartmoneyconcepts import smc

def ibs_ob_exit(ohlc: pd.DataFrame, sell_threshold=0.90) -> bool:
    """
    Exit IBS long when EITHER:
    1. IBS > sell_threshold (standard rule), OR
    2. Price approaches a recent bearish Order Block overhead
    """
    current_ibs = (ohlc["Close"].iloc[-1] - ohlc["Low"].iloc[-1]) \
                / (ohlc["High"].iloc[-1] - ohlc["Low"].iloc[-1])
    
    swing_hl = smc.swing_highs_lows(ohlc, swing_length=3)
    ob_data = smc.ob(ohlc, swing_highs_lows=swing_hl)
    bearish_obs = ob_data[(ob_data["OB"] == -1) & (ob_data["Top"] > ohlc["Close"].iloc[-1])]
    nearest_resist = bearish_obs["Top"].min() if len(bearish_obs) > 0 else float("inf")
    close_to_resist = ohlc["Close"].iloc[-1] >= nearest_resist * 0.99
    
    return current_ibs > sell_threshold or close_to_resist
```

Requires `pip install smartmoneyconcepts`. See [Smart Money Concepts Library](../tools/smart-money-concepts.md).

---

### IBS + RSI(2) Composite

Combining IBS with 2-period RSI as a secondary confirmation requires BOTH:
1. IBS < buy_threshold (close near day's low)
2. RSI(2) < 10 (extreme short-term oversold)

From QuantifiedStrategies backtests on SPY/NDQ: standalone IBS hits ~74% win rate at ~36% time invested; IBS + RSI(2) < 10 reaches ~80% win rate at ~20% time invested with higher average gain per trade. Sharpe improves because false signals in trending markets (when IBS triggers but momentum continues) are filtered out by RSI(2).

```python
def ibs_rsi2_signal(ohlc: pd.DataFrame, ibs_thresh=0.20, rsi_thresh=10) -> bool:
    """Dual-filter: both IBS and RSI(2) must confirm oversold condition."""
    closes = ohlc["Close"]
    ibs = (closes.iloc[-1] - ohlc["Low"].iloc[-1]) / (ohlc["High"].iloc[-1] - ohlc["Low"].iloc[-1])
    
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(2).mean()
    loss = (-delta.clip(upper=0)).rolling(2).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi2 = 100 - (100 / (1 + rs))
    
    return float(ibs) < ibs_thresh and float(rsi2.iloc[-1]) < rsi_thresh
```

**Limitation:** RSI(2) becomes more restrictive during strong trends, reducing trade count substantially. Verify win-rate improvement on XLK/SMH/IGV specifically before production deployment.

---

### Multi-ETF Basket Diversification

Going long on multiple ETFs simultaneously when they independently trigger IBS increases portfolio-level Sharpe. The diversification works because IBS triggers on XLK, SMH, and IGV are not synchronized (different sector dynamics, different H/L patterns on any given day).

Production allocation already uses this (XLK/SMH/IGV independent with fixed budget), but the budget scales correctly: position size per ETF scales inversely with the number of simultaneous triggers to keep total IBS exposure at 30% regardless.

Potential additions to the basket:
- **QQQ**: broad tech, complements XLK's sector-concentrated exposure
- **SPY as context**: SPY IBS < 0.20 as a portfolio-wide signal amplifier (increase sizing on XLK/SMH/IGV when SPY also shows extreme daily selling)

---

## Updated Production Portfolio Context (2026-07-22)

The current production blend (H041a 22% / H026 27% / H045 21% / IBS 30%) achieves OOS Sharpe **4.158**, MaxDD −3.60%, zero negative years 2004–2025. IBS contribution:

| Blend component | Weight | Approx standalone OOS Sharpe | Corr to rotation |
|----------------|--------|------------------------------|-----------------|
| H041a (stock momentum) | 22% | ~2.5 | ~0.60 |
| H026 (ETF rotation) | 27% | ~3.0 | 1.00 |
| H045 (bond rotation) | 21% | ~1.35 | ~0.20 |
| **IBS (XLK 20% / SMH 8% / IGV 2%)** | **30%** | **~1.5–1.7** | **~0.15–0.25** |

IBS's outsized portfolio Sharpe contribution relative to its standalone Sharpe is entirely due to **frequency orthogonality**: momentum operates at 1–12 month horizons; IBS at 1–7 day horizons. These don't compete for the same trades. In months where momentum has a drawdown, IBS fires independently 2–4 times and partially offsets losses.

Paper trading live since 2026-05-28. XLK and SMH entries have executed. H149 confirmed 70% rotation / 30% IBS is the optimal budget split.

---

## Related wiki pages

- [Momentum Strategies](momentum-strategies.md) — H026/H041a rotation leg
- [Short-Term Reversal](short-term-reversal.md) — industry-adjusted reversal (H181), related mean-reversion family; FRI analysis applies to both
- [Market Microstructure & HFT](market-microstructure.md) — FRI sign/magnitude decomposition §3; push-response asymmetry; trend decay §4
- [Smart Money Concepts (ICT)](smart-money-concepts-ict.md) — OB filter; H343–H346 results; exit timing via swing levels
- [Factor Models & Cross-Sectional Alpha](factor-models.md)
- [Regime Detection](regime-detection.md) — IBS works better when regime gate is active
- [Strategy Blending & Correlation Management](../backtesting/strategy-blending-correlation.md) — IBS orthogonality is the source of Sharpe 2.5→4.16 jump

## Sources

- Pandey & Joshi (2023): [arXiv:2306.12434 — Using Internal Bar Strength as a Key Indicator for Trading Country ETFs](https://arxiv.org/abs/2306.12434)
- Pagonidis (2013): [The IBS Effect: Mean Reversion in Equity ETFs (Semantic Scholar)](https://www.semanticscholar.org/paper/The-IBS-Effect%3A-Mean-Reversion-in-Equity-ETFs-Pagonidis/1e11292ec9a87a9e3e19de87a28542a381cc774b)
- Portnaya (Jun 2026): [arXiv:2606.29591 — The Bounce Has No Direction: Sign, Magnitude, and the Microstructure of Equity Return Predictability](https://arxiv.org/abs/2606.29591)
- Vlasiuk & Smirnov (Nov 2025): [arXiv:2511.06177 — Push-response anomalies in high-frequency S&P 500 price series](https://arxiv.org/abs/2511.06177)
- MDPI Risks (2026): [Overnight vs. Daytime Static and Momentum Strategies Across Sector ETFs](https://www.mdpi.com/2227-9091/14/4/84)
- QuantifiedStrategies: [IBS Indicator Strategy](https://www.quantifiedstrategies.com/internal-bar-strength-ibs-indicator-strategy/) | [IBS + RSI](https://www.quantifiedstrategies.com/sp-500-mean-reversion-using-ibs-and-rsi/)
- Alvarez Quant Trading: [IBS for Mean Reversion](https://alvarezquanttrading.com/blog/internal-bar-strength-for-mean-reversion/)
