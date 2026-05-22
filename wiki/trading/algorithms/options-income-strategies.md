---
updated: 2026-05-21
focus: income generation + directional defined-risk
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

### H162 Backtest Result — Covered Calls Around Ex-Dividend Date (PARTIAL CONFIRMED)

**Design**: Universe: 50 large-cap dividend payers, 3509 quarterly ex-date events (IS=1961, OOS=1548). Entry: 10 trading days before ex-date, sell 2% OTM call + long stock. Exit: ex-date. Black-Scholes + 20-day HV as IV proxy.

**OOS results** (2018–2026): WR=68.3%, MeanRet=0.62%, t=6.47. Portfolio Sharpe=2.015, MaxDD=−16.17%, Corr(SPY)=0.167. vs. JEPI: 2.015 vs 1.047 (1.9× better, Ernesto R25 claimed 3×).

**Critical finding — call leg loses money OOS**:
- Call leg: WR=71.4% but MeanRet=−0.14%, t=−1.92
- Stock drift before ex-dates (WR=58.3%, MeanRet=0.76%) is the real driver
- Covered call REDUCES mean return (0.62% vs 0.76%) but improves win rate via premium cushion
- Covered call cumul (2.42×) < Stock-only (3.09×) — options cap upside without compensating

**What this means for covered call strategies**:
- The IV risk premium on short-dated (10-day) individual stock calls is NEGATIVE — the options are being sold at a discount to realized vol
- The strategy works as "stock drift + defensive cushion" not "premium income"
- Best with longer hold (15d) or lower OTM strike (3%) where the premium / intrinsic ratio improves

**Caveats**: (1) Sharpe inflated — exit-day P&L model (true ~1.0–1.5); (2) No actual options data — BS+HV proxy; real bid-ask eats 0.2–0.4% per trade; (3) Comparison to JEPI is rough (different inception).

Script: `backtesting/daily/run_h162.py`. Results: `backtesting/results/h162_covered_calls_exdiv.txt`.

### When Covered Calls Work
- Extended flat or modestly declining markets (delta-neutral to bearish)
- Already-owned positions you're willing to sell at a target price
- Tax-deferred accounts (eliminates the short-term gains problem)
- Around corporate events (ex-dividend) where stock drift adds to premium return

### Parameters That Matter
- Strike selection: 0.20-0.30 delta OTM (balances premium vs. upside preservation)
- DTE: 20-45 days (weekly = too much gamma risk; monthly is optimal)
- Rolling: Roll when underlying approaches strike; roll forward in time + up in strike
- Event timing: Sell before ex-dividend dates to capture pre-ex positive drift

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

---

## Strategy 5: Vertical Debit Spreads (Bull Call / Bear Put)

The **directional counterpart** to income strategies. Use when you have a directional thesis but want defined risk cheaper than buying a naked option. This is what the active paper trades (WMT, DLTR) use.

### Structure

**Bull Call Spread**: Buy lower-strike call + sell higher-strike call. Net debit = cost.  
**Bear Put Spread**: Buy higher-strike put + sell lower-strike put. Net debit = cost.

```
Max profit  = spread_width - debit_paid          (reached when price > short strike at expiry)
Max loss    = debit_paid                          (price below long strike at expiry)
Breakeven   = long_strike + debit_paid
ROI at max  = max_profit / debit_paid × 100%
```

### Entry Criteria

| Parameter | Guideline | Reasoning |
|-----------|-----------|-----------|
| **DTE** | 25–45 days | 25-40 DTE gives 57% higher returns than <15 DTE; 45 DTE standard |
| **IV Rank** | < 30% | BUYING premium — want cheap options, low IV; opposite of sellers |
| **Long strike delta** | 0.45–0.55 | ATM or slightly OTM; maximize directional exposure |
| **Short strike delta** | 0.15–0.25 | Caps cost and max loss; OTM defines profit zone |
| **Spread width** | Ticker-dependent | $5 for $50–150 stocks; $10 for $150–500; $15–25 for $500+ |
| **Bid-ask spread** | < 3% of option price | Liquid markets only |

### IV Considerations (Critical Difference from Sellers)

- **Debit spreads are long vega** — you benefit from IV expansion, hurt by IV crush
- **Never buy debit spreads into earnings** if you plan to hold through the announcement: IV crush post-announcement can turn a directional win into a loss
- **Enter in low-IV regimes**: IV Rank < 30 means options are cheap relative to trailing history — better risk/reward on the debit
- If entering near an earnings catalyst, plan to exit BEFORE the announcement to capture IV expansion without the crush

### Management Rules

| Scenario | Action |
|----------|--------|
| Profit hits 50–70% of max gain | Close — 73% probability of reaching max profit if 50% target hit; risk/reward degrades |
| Profit at 80% of max gain with 2+ weeks left | Close — residual upside not worth gamma risk |
| Loss reaches 50% of debit paid | Close — cut losers early, protect capital |
| 10–12 DTE remaining (no profit) | Close — theta decay accelerates, spread value collapses |
| Underlying makes strong adverse move | Close at 50% loss stop; don't wait for expiry |

### Entry Around Earnings

Earnings-driven debit spreads require special handling:

```python
# Entry rule for earnings catalyst play
entry_days_before_earnings = 7–14   # enter after IV has started rising
exit_rule = "close 1 day BEFORE announcement"  # capture IV expansion, avoid crush

# IV-expansion trade (pre-earnings only)
# After announcement → IV crush kills long vega; close regardless of direction
```

**Key insight from WMT-CS-2026-04-27**: WMT spread entered at $3.27 on April 27, earnings May 21. WMT dropped ~7% post-earnings due to missed guidance. Spread collapsed from $3.27 → ~$0.23. Loss: -$304/contract (-93%). Illustrates that:
1. Directional thesis was wrong (bullish vs reality of miss)
2. 29 DTE remaining — no recovery path when 7% below long strike
3. Correct action: close for $0.23 salvage rather than expire worthless

### Python: Debit Spread Monitor

```python
def monitor_debit_spread(long_call_price, short_call_price, entry_debit, dte_remaining):
    """Returns action recommendation for an open debit spread."""
    current_value = long_call_price - short_call_price
    pnl_pct = (current_value - entry_debit) / entry_debit

    if pnl_pct >= 0.50:
        return "CLOSE — 50%+ profit target hit"
    if pnl_pct <= -0.50:
        return "CLOSE — 50% loss stop hit"
    if dte_remaining <= 10:
        return "CLOSE — theta decay accelerating, 10 DTE"
    return f"HOLD — P&L {pnl_pct:+.1%}, {dte_remaining}d remaining"
```

---

## Iron Condor: Adjustment & Rolling Mechanics

When a condor is tested (one short strike breached), there are three main adjustment paths. Trigger: short strike delta reaches 0.30–0.35 (was sold at 0.16).

### Adjustment 1: Roll the Untested Side (Preferred)

Buy back the untested (profitable) spread. Re-sell closer to current price to collect additional credit.

```python
# Roll untested side
untested_credit_available = original_untested_spread_value * (1 - pct_decay)
if untested_credit_available >= 0.25:          # worth rolling if >$25 credit
    buy_to_close(untested_spread)
    sell_to_open(new_spread, at_current_delta=0.16)
    net_additional_credit = new_spread.credit - untested_spread.close_cost
```

- **Best for**: Slow, gradual moves. Widens the profit zone on the unaffected side.
- **Risk**: If market reverses, now threatened from the re-sold side too.

### Adjustment 2: Roll the Tested Side Out in Time

Close the tested side and re-open same strikes in the next expiry cycle (typically 30 days further) for additional credit.

```
Roll only if: collected_credit_new_expiry > loss_on_close_current_expiry
Net effect: extend the trade's time horizon, buy price time to return to range
```

- **Best for**: When you believe the move is temporary and price will revert.
- **Credit requirement**: Roll must be for a net credit or zero cost.

### Adjustment 3: Convert to Broken-Wing Butterfly (BWB)

Move the long strike of the tested side closer to the short strike (widening one wing, narrowing the other). Creates asymmetric risk profile that favors one direction.

```
Original condor: short 470P / long 460P | short 530C / long 540C
BWB (call side tested): widen call wing → short 530C / long 545C (was 540)
Effect: collect additional credit; reduced max loss on call side, increased on put side
```

### Do Nothing (with Time Stop)

If the tested strike was barely breached and DTE < 21, the 21-DTE exit rule takes over. Exit the whole trade per the original management rule.

### Decision Matrix

| Situation | Action |
|-----------|--------|
| Early test (>30 DTE), gradual move | Roll untested side for credit |
| Mid-trade test (15–30 DTE), strong trend | Roll tested side out in time |
| Near expiry (<15 DTE), near loss limit | Close entire position |
| Loss approaching 2× credit | Close — never fight it further |
| Strong reversal back to range | Close tested side only, keep profitable side |

---

## Earnings Volatility Plays

### Long Straddle/Strangle Before Earnings (IV Expansion Trade)

Different from the debit spread above — this is a **pure volatility bet** not directional.

```
Entry: 21–28 days before earnings announcement
Exit: 1–3 days BEFORE announcement (capture IV expansion, avoid crush)
IV entry filter: IV Percentile < 30th percentile of trailing 1-year range
```

- **Straddle**: Buy ATM call + ATM put. Higher cost, narrower breakeven. Best when you expect a large move but don't know direction.
- **Strangle**: Buy OTM call + OTM put. Cheaper, wider breakeven. Lower probability but better risk/reward if move is large.

**IV Crush Warning**: IV drops 30–50%+ immediately after announcement regardless of stock movement. A stock that moves 5% post-earnings can still be a loser on a long straddle if IV crush is 40%.

```python
# IV crush estimate
implied_move = (straddle_price / stock_price) * 100    # market's expected move
if actual_move_pct < implied_move * 0.7:
    # IV crush likely to outweigh directional gain — exit before announcement
    pass
```

### When NOT to Trade Earnings Options

- When IV Rank > 70% at entry — overpaying for vol
- When historical IV crush > 50% for this ticker (tech stocks, NVDA, META, TSLA regularly crush 40–60%)
- Within 3 days of announcement — theta decay too aggressive on long options

---

## Recommended Implementation Order

1. **Iron condor on SPY/QQQ** — most documented edge, defined risk, good LEAN support
2. **Bull call spread on directional stock thesis** — defined-risk directional plays around earnings; size max loss < 2% equity
3. **Put spread selling (16-delta, 45-DTE)** — simpler than condor, high win rate
4. **Covered calls on existing ETF positions** — low complexity, income from holdings
5. **VRP harvesting with VIX hedge** — highest potential but requires more infrastructure

All require options data beyond Polygon free tier. Start with QuantConnect's built-in data for LEAN backtesting, then purchase ThetaData for production-grade research.

**Active paper trades reference:** IC-2026-04-26-001 (SPY condor, 47 DTE at entry), WMT-CS-2026-04-27 (bull call $130/$140, deep OTM post-earnings — close), DLTR-CS-2026-04-27 (bull call $100/$115, earnings ~Jun 2–3), DLTR-RR-2026-04-27 (risk reversal, put leg approaching $95 assignment threshold).
