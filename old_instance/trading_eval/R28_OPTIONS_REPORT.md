# R28 — Options Deep Dive: Wheel / Multi-Leg / Greeks
**Date**: 2026-04-01
**Universe**: 30 tickers (large-cap, multi-sector) + ^VIX
**Period**: 2020-01-01 — 2025-12-31
**Framework**: Black-Scholes simulation, IV = realized_vol × 1.03 (VRP modeled)

---

## Executive Summary

Six strategies tested. Key finding: **premium-selling with an IV rank filter is the
dominant approach**. The Wheel — the most-hyped retail options strategy — underperforms
buy-and-hold on 27 of 30 names. VIX short puts are surprisingly strong (88.6% win rate).

| Strategy | Avg Sharpe | Best Sharpe | Best Name |
|---|---|---|---|
| Bull Put Spread (IV rank>50%) | +0.744 | +2.584 | XOM |
| VIX Short Put (floor sell) | +0.846 | — | VIX |
| Iron Condor (IV rank>50%) | +0.523 | +1.612 | QCOM |
| VRP Harvest (filtered) | +0.499 | +1.651 | QCOM |
| Gamma Scalping | +0.413 | +1.161 | COST |
| Wheel Strategy | +0.312 | +0.739 | PG |

---

## Strategy 1: Wheel (CSP → CC → repeat)

**Avg Sharpe: +0.312 | Avg vs BH: -0.130/yr**

The wheel generates positive absolute returns but trails simple buy-and-hold on
27 of 30 tickers. The mechanics explain why:
- The CSP leg sells insurance cheaply during calm markets → small premium
- On assignment, the CC leg caps the recovery → you miss the bounce
- After a big drawdown + recovery, the wheel lags badly (NVDA: -0.637/yr vs BH)

The wheel does best on *slow-moving, mean-reverting* names: PG (+0.739), GOOGL (+0.648),
GE (+0.662), NVDA (+0.736, but -0.637 vs BH). Only UNH (+0.029/yr vs BH) and PG
(+0.034/yr vs BH) roughly match buy-and-hold.

**Verdict**: The wheel is a premium-collection strategy disguised as buy-and-hold.
It reduces vol and max drawdown slightly, but gives up significant upside in trending
markets. Best used on high-yield, slow-growth names where upside is limited anyway.

---

## Strategy 2: Iron Condor with IV Rank Filter

**Avg Sharpe: +0.523 | Best: QCOM +1.612, MO +1.593, PG +1.298, XOM +1.287**

Enter iron condor (5%/10% wing width) only when IV rank > 50th percentile.
Win rate: 62.8% average. Max-loss events: varies significantly by name.

Best performers are *low-beta, low-vol names*: PG, MO, KO, XOM. The 5% wings rarely get
breached on defensive stocks. High-beta names (NVDA, TSLA) have max-loss rates >60%
— the wings get blown through frequently.

The IV rank filter matters enormously. Without it, many of these trades would be
entered when options are cheap and the premium doesn't compensate for the risk.

**Verdict**: Strong strategy on low-vol names with IV rank filter. Avoid on high-beta
names — the wing widths need to be wider (10%/20%) to handle vol regime shifts.

---

## Strategy 3: Bull Put Spread with IV Rank Filter

**Avg Sharpe: +0.744 (best among multi-ticker strategies)**

Sell ATM put, buy 5% OTM put. Enter when IV rank > 50%. Normalize by wing width.

Top performers: XOM +2.584, CVX +2.470, GE +2.305, WMT +1.863, MO +1.765.

Interesting split: for value/energy names the spread BEATS the naked put (less
assignment risk from sudden drops). For high-beta names (JPM, IBM, NVDA) the naked
put wins because the wing premium costs too much relative to collected premium.

Rule of thumb: use bull put spread on slow-movers, naked CSP on high-vol names.

**Verdict**: Best all-around strategy for systematic premium selling. Defined risk
makes position-sizing tractable.

---

## Strategy 4: VRP Harvesting (Sell ATM Straddle)

**Without filter: -0.086 avg Sharpe. With IV rank filter (>40%): +0.499**

This is the clearest demonstration of why the IV rank filter is critical:

- Always selling straddles: avg Sharpe -0.086 (slight drag)
- Only selling when options are expensive: avg Sharpe +0.499

The VRP (implied vol > realized vol) is real but not always present. During low-IV
regimes, options are fairly priced or cheap — selling them is a losing proposition.
The IV rank filter isolates the periods when the premium is worth taking.

QCOM filtered: +1.651, MSFT: +1.090, AMZN: +1.093.

**Verdict**: IV rank is the key lever. Don't sell premium blindly — wait for elevated
implied vol. The VRP exists as a persistent edge but requires timing.

---

## Strategy 5: Gamma Scalping

**Avg Sharpe: +0.413 | RV > IV in 47% of months**

Buy ATM straddle, delta-hedge every 5 days, profit when realized vol > implied vol.

Surprisingly decent results given we modeled IV as 3% above RV (headwind). The
discrete rehedging captures some path-dependency gains even when average RV ≤ IV.
Best names: COST +1.161, AAPL +0.907, GOOGL +0.964 — names with frequent directional
moves that allow gamma gains to accumulate between hedge intervals.

RV > IV in only 47% of months — confirming the VRP headwind. Yet positive Sharpe
overall suggests the rehedging process extracts value from realized path volatility.

**Verdict**: Works best on highly directional names. Sharpe +0.413 average is real
but operationally complex. Not a scalable retail strategy; better suited for
market makers with low transaction costs.

---

## Strategy 6: VIX Options

| Sub-strategy | Sharpe | Win Rate | n_trades |
|---|---|---|---|
| Long VIX Call (tail hedge, VIX<25) | +0.147 | 14.3% | 70 |
| Short VIX Put (floor sell) | **+0.846** | **88.6%** | 70 |
| Tactical Long on Spike (>10% VIX jump) | +0.212 | 24.4% | 127 |

**Short VIX Put is the standout**: 88.6% win rate, Sharpe +0.846.

The mechanism is structural: VIX has a practical floor around 9-10 (even in
ultra-calm markets like 2017, VIX barely touched 9). Selling 20% OTM puts gives
strikes around 12-15 that are almost never breached. You collect consistent premium
with minimal assignment risk.

**Long VIX Call**: Classic tail-hedge behavior. 14.3% win rate but winners are large
(VIX can 3-5× in a month). Average Sharpe barely positive because you're paying
expensive vol-of-vol. Works as portfolio insurance, not standalone P&L.

**Tactical Long on Spikes**: Attempting to catch second-leg vol moves after >10% VIX
jump. 24.4% win rate, Sharpe +0.212. Modest edge — VIX can spike further but
mean-reversion often kicks in within 5 days.

**Verdict**: Short VIX puts are underrated. The vol floor is structural, not
statistical — combine with position sizing relative to portfolio notional.

---

## Comparative Context (full leaderboard)

Placing R28 results vs top strategies from all rounds:

| Strategy | Sharpe | Category |
|---|---|---|
| Dividend Raise Signal (≥10%, 40d) | +4.403 | R27 Dividends |
| CC around Ex-Div Date | +2.643 | R27 Dividends |
| Bull Put Spread XOM (R28) | +2.584 | R28 Options |
| Dividend Capture (3d before, 5d after) | +1.578 | R27 Dividends |
| Bull Put Spread CVX (R28) | +2.470 | R28 Options |
| Iron Condor QCOM (R28) | +1.612 | R28 Options |
| VRP Harvest QCOM filtered (R28) | +1.651 | R28 Options |
| PEAD Momentum | +1.137 | R7 |
| VIX Short Put (R28) | +0.846 | R28 Options |
| Bull Put Spread avg (R28) | +0.744 | R28 Options |

---

## What Doesn't Work

- **Wheel on growth stocks**: Missed recovery after assignment kills returns
- **Always-sell straddle (no filter)**: Slightly negative on average — need IV rank
- **Gamma scalping at retail scale**: High transaction costs would erase the edge
- **Long VIX calls as P&L strategy**: Lottery ticket behavior; only viable as hedge

---

## Implementation Priority

| Priority | Strategy | Why |
|---|---|---|
| 1 | Bull Put Spread on XOM, CVX, GE, MO (IV rank>50%) | Best avg Sharpe, defined risk |
| 2 | Short VIX Puts (20% OTM, monthly) | Structural floor, 88.6% WR |
| 3 | Iron Condor on PG, KO, MO (IV rank>50%) | Low max-loss rate |
| 4 | VRP Harvest on QCOM, AMZN, MSFT (IV filtered) | VRP edge confirmed |
| — | Wheel strategy | Underperforms BH; skip unless yield-focused |

---

## Literature Research Queue (dream cycle)

Following areas to research over time:
- Carr & Wu (2009) — Variance risk premiums
- Simon & Campasano (2014) — VIX vs. realized vol gap magnitude
- Bakshi & Kapadia (2003) — Delta-hedged gains
- Cboe VIX options white papers — term structure strategies
- Put/call skew as market timing signal (not evaluated in R28)
- Term structure of VIX futures (VX1-VX2 roll) as entry signal for condors
