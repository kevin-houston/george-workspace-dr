---
title: smart-money-concepts — ICT Price Action Indicators (Python)
added: 2026-06-28
source: https://github.com/joshyattridge/smart-money-concepts
stars: 1788
category: tools/ta-indicators
---

# smart-money-concepts

**GitHub:** joshyattridge/smart-money-concepts | **Stars:** 1,788 | **Install:** `pip install smartmoneyconcepts`

Python library implementing ICT (Inner Circle Trader) Smart Money Concepts as vectorized pandas/numpy indicators. Clean, drop-in with yfinance OHLCV data.

## What is ICT / Smart Money Concepts?

ICT = Inner Circle Trader, a retail trading methodology by Michael J. Huddleston. Core thesis: institutional "smart money" leaves footprints in price action through specific patterns. Retail traders can exploit these by reading order flow rather than lagging indicators.

**Important caveat:** ICT/SMC concepts have no peer-reviewed academic backing. Popular in retail communities; effectiveness at scale is unvalidated.

## Indicators Available

### Fair Value Gap (FVG)
```python
smc.fvg(ohlc, join_consecutive=False)
```
Price imbalance: prior candle high < next candle low (bullish) or prior low > next high (bearish). Theory: institutions left unfilled orders in the gap; price returns to "fill" it.

Returns: `FVG` (1/-1), `Top`, `Bottom`, `MitigatedIndex`

### Swing Highs and Lows
```python
smc.swing_highs_lows(ohlc, swing_length=50)
```
Highest high / lowest low over N candles before and after. Foundation for BOS/CHoCH and order block detection.

### Break of Structure (BOS) & Change of Character (CHoCH)
```python
smc.bos_choch(ohlc, swing_highs_lows, close_break=True)
```
- **BOS** = continuation signal: price breaks prior swing high (bullish) or low (bearish)
- **CHoCH** = reversal signal: price breaks in the *opposite* direction from recent structure

Returns: `BOS`, `CHOCH` (1/-1), `Level`, `BrokenIndex`

### Order Blocks (OB)
```python
smc.ob(ohlc, swing_highs_lows, close_mitigation=False)
```
Consolidation zone immediately before a strong impulse move. Theory: institutional accumulation/distribution zone; price returns and finds support/resistance.

Returns: `OB` (1/-1), `Top`, `Bottom`, `OBVolume`, `Percentage` (strength proxy)

### Liquidity
```python
smc.liquidity(ohlc, swing_highs_lows, range_percent=0.01)
```
Cluster of highs or lows within `range_percent` of each other — represents dense stop-loss concentration. Theory: smart money "hunts" these stops before reversing.

Returns: `Liquidity` (1/-1), `Level`, `End`, `Swept`

### Previous High / Low
```python
smc.previous_high_low(ohlc, time_frame="1D")
```
Higher-timeframe reference levels. `BrokenHigh`/`BrokenLow` flags when breached.

### Sessions
```python
smc.sessions(ohlc, session, start_time, end_time, time_zone="UTC")
```
Marks candles within named sessions: Sydney, Tokyo, London, New York, plus kill zones (Asian kill zone, London open kill zone, New York kill zone, London close kill zone). Useful for intraday timing of entry.

### Retracements
```python
smc.retracements(ohlc, swing_highs_lows)
```
Current and deepest retracement % from the last swing high/low.

## Integration with yfinance

```python
import yfinance as yf
from smartmoneyconcepts import smc

df = yf.download("SPY", period="1y", interval="1d")
df.columns = [c[0].lower() for c in df.columns]  # lowercase multiindex → flat lowercase
ohlc = df[["open","high","low","close","volume"]]

fvg = smc.fvg(ohlc)
swings = smc.swing_highs_lows(ohlc, swing_length=10)
bos = smc.bos_choch(ohlc, swings)
ob  = smc.ob(ohlc, swings)
```

## Potential Hypothesis Applications

### H343 — FVG Filter on H198 Momentum
At month-end rebalance, among H198 top-ranked momentum stocks, enter only those where:
- A bullish FVG exists on daily bars within last 20 candles
- FVG has not yet been mitigated (`MitigatedIndex` is NaN)

Thesis: FVG = unfilled institutional order → provides near-term support → lowers false-positive momentum entries that reverse immediately.

### H344 — Order Block Entry Timing for PEAD
After H174 flags an 8-K as positive (score ≥ 0.18), wait for price to pull back into the nearest bullish Order Block before entering rather than OPG market order.

Possible improvement: better fill price, lower slippage, reduces chasing.

### H345 — CHoCH as Momentum Exit Signal
When H198 momentum position shows bearish CHoCH on daily bars, treat as early exit signal rather than waiting for month-end rebalance.

## Assessment

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Implementation quality | High | Clean vectorized pandas/numpy; v0.0.27 |
| Academic validation | None | ICT methodology is retail, not peer-reviewed |
| Forex vs equity | Designed for forex | EURUSD test data; unclear equity performance |
| Ease of use | High | pip install; drop-in with yfinance |
| Backtesting framework | None | Just indicators; you bring the backtest loop |
| Stars / community | 1,788 | Active, maintained |

**Recommendation:** Low-cost option to add price-action features to H198/H174 entry logic. Worth an H343 quick test (FVG filter on monthly momentum). No high expectations on standalone basis given lack of academic validation, but as a confirmation layer it's worth one sprint.

## Related Pages
- [Technical Analysis Patterns](../algorithms/technical-analysis-patterns.md)
- [Event-Driven Strategies](../algorithms/event-driven.md)
- [Momentum Strategies](../algorithms/momentum-strategies.md)
- [Market Microstructure & HFT](../algorithms/market-microstructure.md)
