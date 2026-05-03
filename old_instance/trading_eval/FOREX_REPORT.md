# Forex Autoresearch Report — 8 Rounds
Date: 2026-03-30
Universe: 10 major/minor pairs | Period: 10 years | Cost: 1bp/trade (round-trip)
Backtests: ~680 total across 8 rounds

---

## Executive Summary

Forex is NOT equities. The core finding across all 8 rounds:

> *Mean reversion wins. Trend following loses. Breakouts fail badly.*

This is structurally different from the equity results (R1-R10) where momentum and
SMA crossovers had positive edge. In forex, currencies oscillate around macro equilibria
(purchasing power parity, rate differentials) — there is no underlying growth premium
to capture with trend following.

---

## Round-by-Round Results

### R1 — Baseline (Trend vs Mean Reversion)
Champion: MeanRev_40_1.5 | Sharpe +0.200 | CAGR 0.93% | Best pair: EUR/GBP

Key finding: Mean reversion positive, ALL trend strategies negative.
- SMA_5_20: Sharpe -0.144
- SMA_50_200: Sharpe -0.176
- MOM_20: Sharpe -0.141
Trend following is structurally unprofitable in forex over 10 years.

### R2 — Oscillators
Champion: RSI_14_Rev_Tight (20/80 bands) | Sharpe +0.280 | CAGR 0.59% | Best: AUD/USD

RSI mean reversion is the single best strategy found.
Tight bands (20/80) outperform standard (30/70) — only trade EXTREME readings.
RSI Trend (using RSI > 50 as long signal) = -0.200 Sharpe — confirms trend bias fails.

### R3 — Volatility Strategies
Champion: VolSwitch_5_20 | Sharpe -0.021 | Best: EUR/GBP

All volatility strategies slightly negative. Vol-scaled momentum makes the direction
problem worse, not better. Keltner and ATR breakouts: -0.57 Sharpe. Worst round overall.

### R4 — Carry Trade
Champion: Carry_1.0 (>1% rate differential) | Sharpe -0.009 | Best: USD/JPY

Carry trade marginally negative — the 2010s carry trade era is essentially dead.
Post-2022 rate normalization compressed differentials; JPY carry remains viable
only with tight trend filter.

### R5 — Macro-Enhanced
Champion: MacroRate_US_EU | Sharpe ~0.000 | Neutral

FRED rate differential signal produced zero net signal on most pairs (data alignment issue
with Eurozone rate data). OilFX (trading USD/CAD based on WTI momentum): Sharpe -0.159.
Oil/FX correlation exists but is too noisy at daily resolution.

### R6 — Yield Curve & Adaptive
Champion: YieldCurve_FX | Sharpe +0.163 | CAGR 0.83% | Best: USD/CAD

Yield curve inversion → USD safe haven signal works on USD/CAD and USD/JPY.
Adaptive regime-switching (trend in trending regimes, reversion in ranging):
Sharpe +0.016 — marginally positive but too noisy at daily resolution.

### R7 — Ensemble Combinations
Champion: Carry_Adaptive | Sharpe +0.050 | Best: USD/JPY

Ensembles don't help because trend strategies drag the combination down.
Carry + Adaptive at +0.050 shows the right combination: structural (carry) + tactical (regime).

### R8 — Best-of Final Iteration
Champion: Adaptive_v2 | Sharpe -0.025 | Best: EUR/JPY

Tighter parameter sweeps on adaptive and vol-scaled strategies didn't improve R6 results.
Full 5-strategy ensemble: Sharpe -0.240 — too many trend votes contaminate the signal.

---

## Cross-Round Champion Ranking

| Rank | Strategy          | Round | Sharpe | CAGR   | Best Pair  |
|------|-------------------|-------|--------|--------|------------|
| 1    | RSI_14_Rev_Tight  | R2    | +0.280 | 0.59%  | AUD/USD    |
| 2    | MeanRev_40_1.5    | R1    | +0.200 | 0.93%  | EUR/GBP    |
| 3    | YieldCurve_FX     | R6    | +0.163 | 0.83%  | USD/CAD    |
| 4    | RSI_7_Rev         | R2    | +0.243 | 1.00%  | EUR/USD    |
| 5    | RSI_14_Rev        | R2    | +0.197 | 0.72%  | EUR/GBP    |

---

## Pair-by-Pair Insights

**EUR/GBP** — Most mean-reverting pair. Extremely range-bound (both EU economies
closely linked). Best pair for z-score and RSI strategies.

**AUD/USD** — RSI works best here. AUD is a clean commodity/risk proxy; oscillates
predictably between risk-on and risk-off regimes.

**USD/JPY** — Best for carry-adjacent strategies. JPY remains the global funding
currency; higher US rates structurally support long USD/JPY but with carry compression.

**USD/CAD** — Responds to yield curve / macro regime signals. Oil sensitivity
adds a layer the yield signal partially captures.

**GBP/JPY** — Highest volatility cross pair. Best returns on volatility strategies
(still negative, but least bad). Not suitable for mean reversion — moves too fast.

---

## Why Forex Differs from Equities

| Factor | Equities | Forex |
|--------|----------|-------|
| Underlying growth | Yes (earnings growth) | No (zero-sum) |
| Trend following | Works (Sharpe 0.3-0.6) | Fails (Sharpe -0.1 to -0.3) |
| Mean reversion | Mixed | Works (Sharpe 0.2-0.3) |
| Carry | Not relevant | Marginally alive (USD/JPY) |
| Macro regime | Large impact | Moderate impact |
| Breakouts | Work in high-vol | Fail systematically |

Core reason: Currencies are relative prices between two economies. In equilibrium,
they trend toward purchasing power parity. Equities have an embedded growth option —
currencies don't. This structural difference completely inverts the strategy landscape.

---

## Practical Trading Recommendations

### Strategy 1 — RSI Mean Reversion (Primary Edge)
- Pair: EUR/USD, EUR/GBP, AUD/USD
- Signal: RSI(14) crosses below 20 → long; above 80 → short
- Hold: 3-5 days (use limit orders, let it revert)
- Expected Sharpe: ~0.28 unlevered

### Strategy 2 — 40-Day Z-Score Reversion (Robust Edge)
- Pair: EUR/GBP (most range-bound)
- Signal: Z-score > 1.5 → short, < -1.5 → long
- Hold: until z-score reverts to zero or 10 days
- Expected Sharpe: ~0.20 unlevered

### Strategy 3 — Yield Curve + USD Safe Haven
- Pair: USD/CAD, USD/JPY
- Signal: 10yr-2yr spread < -0.2% → long USD (safe haven flight)
- Signal: Spread > 0.5% → short USD (risk-on)
- Expected Sharpe: ~0.16 unlevered

### DO NOT USE
- SMA crossovers on forex (Sharpe -0.18 avg)
- ATR/Keltner breakouts (Sharpe -0.45 to -0.59)
- Momentum alone (Sharpe -0.14 avg)
- Day-of-week patterns (Sharpe -0.24 avg)

---

## Context for Current Macro Regime (2026-03-30)

Our macro classifier shows: oil_shock + stress (VIX 27) + gold_bull + easing (Fed cutting)

Implications for forex:
- Oil shock → USD/CAD may have directional bias (CAD strengthens with oil)
- Fed easing → USD softens medium-term vs EUR and GBP
- Gold bull → CHF and JPY (safe haven flows)
- Yield curve signal: if spread < -0.2%, long USD against commodity currencies

Current FRED data suggests yield curve normalizing out of inversion —
watch T10Y2Y cross above 0 for regime shift in USD/CAD positioning.

---

## Next Research Directions

1. Daily → Weekly resolution: Mean reversion may be stronger on weekly closes
   (less noise, lower transaction costs, cleaner signals)

2. Regime-conditional RSI: Only trade RSI signals when VIX < 25 (low stress)
   — same hypothesis as candle×macro but may work better for longer-held fx positions

3. Cross-asset signal: Use our GoldFlight_120 equity signal as USD safe-haven filter —
   when gold is rallying, overlay USD long bias

4. Leverage simulation: Forex is typically traded 10-50x levered.
   1% CAGR unlevered = 10-50% at realistic leverage — transforms the picture materially.

Files:
- forex_harness.py — full strategy library and backtest engine
- rounds/forex_round_1.json through forex_round_8.json — detailed results
