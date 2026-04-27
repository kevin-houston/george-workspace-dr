---
updated: 2026-04-26
focus: income generation
priority: high (Kevin's explicit focus: equities + options)
---

# Options Income Strategies — Algorithmic Implementation

Goal: generate systematic income via options premium collection. Ranked by evidence strength and implementability.

**Related pages**: [LEAN / QuantConnect](../tools/lean-quantconnect.md) — backtesting engine for these strategies | [Options Data Sources](../data-sources/options-data.md) — where to get historical Greeks/IV | [Hypothesis Log](../backtesting/hypothesis-log.md) — H007 (iron condor backtest, pending)

---

## Strategy 1: Iron Condor / Iron Butterfly

**The best-supported mechanical strategy for income generation.**

### Structure
Short OTM call + long further OTM call + short OTM put + long further OTM put  
Net credit at entry; profitable if underlying stays within the short strikes at expiration.

### Published Performance (Backtested)
- **16-delta shorts, 45-DTE on SPY**: 78-83% win rate across ~5,000 trades over 14 years (tastytrade research)
- **30-60 DTE, 16-delta/5-delta structure**: 77.6% win rate
- **Tighter wings (25-30 delta)**: 55-60% win rate, larger premium
- **Wider wings (10-delta shorts)**: 80-85% win rate, smaller premium
- **Return per trade**: 10-20% of capital at risk
- **Monthly income potential**: 5-8% on deployed capital with proper management

### Management Rules (tastytrade research-backed)
| Rule | Action |
|------|--------|
| Winner | Close at 50% of max credit |
| Loser | Close when loss = 2× original credit |
| Time | Exit at 21 DTE regardless if underwater |

### Best Conditions
- **Thrives in**: Elevated but stable IV (IV Rank 30-70%), range-bound markets
- **Fails in**: Strong directional trends, volatility regime shifts (low → high)

### Entry Filter
Enter only when **IV Rank > 30%** (IV Rank = (current IV − 52wk low IV) / (52wk high − 52wk low))

### Position Sizing
- Risk 1-3% of portfolio per condor
- Limit total short premium exposure to 30% of portfolio net liquidation value
- Delta/theta ratio target: 0.3-0.5

### Algorithmic Entry Logic
```python
# Entry signal (daily scan)
if iv_rank > 30 and days_to_expiry between 30 and 60:
    short_call = find_strike(delta=-0.16)
    long_call  = find_strike(delta=-0.05)
    short_put  = find_strike(delta=+0.16)
    long_put   = find_strike(delta=+0.05)
    credit = (short_call.bid + short_put.bid) - (long_call.ask + long_put.ask)
    if credit > min_credit_threshold:
        enter_condor(...)

# Exit signal (daily check)
current_value = mark_to_market(condor)
if current_value <= entry_credit * 0.50:   # winner
    close_position()
if current_value >= entry_credit * 2.0:    # loser
    close_position()
if days_remaining <= 21:                    # time stop
    close_position()
```

### Backtesting Notes
- Use 56% of bid-ask width as slippage assumption for 4-leg spreads
- Model overlapping positions (realistic: run multiple condors with different expirations simultaneously)
- Filter for open interest > 500 on short strikes

---

## Strategy 2: Cash-Secured Put (CSP) / Put Spread Selling

### Structure
Sell OTM put (or put spread for defined risk). Obligation to buy 100 shares at strike if assigned.

### Published Performance
- SPY 30-delta put, 45-DTE: 65-70% win rate
- SPY put spreads (2024 backtest): 93% win rate, 106% return on capital for diagonal puts
- 16-delta puts with 50% profit exit: >70% probability of profit (POP)

### IV Entry Filter
tastytrade finding: **theta/vega ≥ 30%** is the optimal entry threshold.  
- High IV environments make this easier to achieve
- In low IV (VIX < 15), avoid selling puts — premium doesn't compensate for risk

### Best Underlyings
- Liquid ETFs: SPY, QQQ, IWM, GLD, TLT
- Liquid large-caps with high IV: AAPL, NVDA, TSLA (but stock risk!)
- Avoid illiquid stocks (bid-ask spreads eat all premium)

### The Wheel: CSP → Covered Call Cycle
1. Sell CSP at or below current price
2. If assigned: own shares → sell covered call
3. If called away: restart CSP
4. If not assigned: keep premium, sell next CSP

**Critical Finding (spintwig backtest)**: On SPY, 94-99% of wheel returns come from the underlying stock position, not options premium. The wheel strategy frequently **underperforms buy-and-hold** on SPY over long periods. Works better on high-IV individual stocks where premium justifies the complexity.

---

## Strategy 3: Systematic Covered Call (BXM/BXMD Approach)

### Structure
Own 100 shares of underlying; sell OTM monthly call. Repeat.

### Historical Performance
- CBOE BXM Index (ATM monthly covered calls on SPX): Slightly outperformed S&P 500 in 2000-2003 bear market; **underperformed significantly in 2004-2013 bull market**
- QQQ systematic covered calls: 0.39-1.76% premium per contract → 46-72% annualized **on the premium alone** — but ignores capped stock gains
- **Long-term conclusion**: Covered calls sacrifice too much upside to justify the strategy in buy-and-hold environments

### When It Works
- Extended flat or modestly declining markets (delta-neutral to bearish)
- Already-owned positions you're willing to sell at a target price
- Tax-deferred accounts (eliminates the short-term gains problem)

### Parameters That Matter
- Strike selection: 0.20-0.30 delta OTM (balances premium vs. upside preservation)
- DTE: 20-45 days (weekly = too much gamma risk; monthly is optimal)
- Rolling: Roll when underlying approaches strike; roll forward in time + up in strike

---

## Strategy 4: Volatility Risk Premium (VRP) Harvesting

### The Edge
IV consistently exceeds realized volatility:
- 1990-2018 average: IV = 19.3%, realized vol = 15.1%  
- **4.2% structural spread** = the VRP edge

### Implementation
Sell ATM straddle/strangle; delta-hedge daily to isolate the vol premium:
```
P&L = Theta collected - Gamma losses from hedging
Expected P&L > 0 when IV > realized_vol
```

### Risk Profile (Critical Warning)
- Return distribution is **extremely left-skewed**
- Historic losses: up to **-800%** in single extreme events (2008, March 2020)
- Requires: substantial margin reserves, VIX call hedges, strict position limits
- **Not suitable without hedging** — unhedged VRP selling = picking up pennies in front of a steamroller

### Hedged VRP Implementation
- Sell OTM puts + buy same-expiry VIX calls as tail hedge
- VIX calls overcompensate for put losses during spikes
- Net Sharpe ratio: 1.19 vs. 0.33 for unhedged (AQR research)

### tastytrade Mechanical Rules
| Parameter | Value |
|-----------|-------|
| Entry | IV Rank > 50% |
| Structure | 16-delta strangle, 45 DTE |
| Exit winner | 50% of max credit |
| Exit loser | 2× credit lost |
| Delta management | Adjust when portfolio delta exceeds 30% of theta |

---

## LEAN (QuantConnect) Options Capabilities

LEAN is the right engine for backtesting these strategies. Key features:

| Feature | Status |
|---------|--------|
| Greeks (delta, gamma, theta, vega) | ✅ Daily pre-calculated; real-time in algo |
| IV calculation | ✅ Per-contract, Black-Scholes |
| Option chain filtering | ✅ By delta, DTE, IV range |
| Early assignment (American-style) | ✅ Auto: assigns if >5% ITM near expiry |
| SPX (European-style) | ✅ Supported |
| Multi-leg orders | ✅ Combo orders supported |
| IV surface / skew modeling | ⚠️ Not natively; would need custom indicator |
| Pin risk | ❌ Not modeled |
| Intraday Greeks | ⚠️ Daily granularity only in backtest |

LEAN requires Docker for local backtesting. Cloud alternative via QuantConnect (10 free backtests/day on free tier, up to 10 years minute data).

---

## Data Sources for Options Backtesting

| Source | Cost | Greeks History | IV History | Goes Back |
|--------|------|----------------|------------|-----------|
| **ThetaData** | Paid (cheapest) | ✅ 1st-3rd order | ✅ | 2005 |
| **ORATS** | Paid (~$100 trial) | ✅ Full surface | ✅ Parameterized | 2007 |
| **Polygon.io free** | Free | ❌ Current only | ❌ | 2014 (EOD only) |
| **Alpaca** | Free | ✅ Real-time only | ✅ Real-time only | Feb 2024 |
| **QuantConnect data** | Free (via LEAN) | ✅ Minute | ✅ | ~2010 |

**Recommendation**: Start with QuantConnect's built-in data (free, decent Greeks history). For production backtesting of options strategies, upgrade to ThetaData.

---

## Backtesting Pitfalls — Specific to Options

| Pitfall | Impact | Fix |
|---------|--------|-----|
| **Bid-ask spread underestimation** | Overstates returns by 2-5% annually | Use 75% of B/A for 1-leg; 56% for 4-leg |
| **Survivorship bias** | +1-4% annual return overstatement | Use point-in-time universe |
| **Path dependency ignored** | Underestimates drawdowns | Model overlapping positions simultaneously |
| **Gamma near expiry** | Underestimates tail risk | Model intraday moves near OPEX |
| **Early assignment not modeled** | Misses stock holding costs | Use LEAN's assignment model |
| **Look-ahead bias** | Artificially inflates results | IV/Greeks only from prior day close |
| **Overfitting DTE/delta** | Strategy fails OOS | Walk-forward validation required |
| **Vol regime ignored** | 2008/2022 strategy blowup | Tag by VIX regime; test each separately |

---

## Recommended Implementation Order

1. **Iron condor on SPY/QQQ** — most documented edge, defined risk, good LEAN support
2. **Put spread selling (16-delta, 45-DTE)** — simpler than condor, high win rate
3. **Covered calls on existing ETF positions** — low complexity, income from holdings
4. **VRP harvesting with VIX hedge** — highest potential but requires more infrastructure

All require options data beyond Polygon free tier. Start with QuantConnect's built-in data for LEAN backtesting, then purchase ThetaData for production-grade research.
