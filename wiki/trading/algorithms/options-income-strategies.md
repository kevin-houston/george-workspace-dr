---
updated: 2026-07-27
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

---

## Strategy 6: 0DTE (Zero Days to Expiration) Iron Condor

**The fastest-growing segment of index options — systematic premium collection using same-day expiry SPX/SPXW contracts.**

### Market Context (2025–2026)

0DTE options now represent **~60% of total SPX options volume** (CBOE data, 2025), up from near-zero in 2021. Approximately 50% of 0DTE activity originates from retail traders. This structural shift creates systematic opportunities but also concentrated gamma risk:

- SPX and SPXW have expirations every weekday (Mon–Fri), enabling daily premium collection
- Monday/Wednesday/Friday use SPXW (weekly); Tuesday/Thursday use standard SPX
- **Same-day settlement** — cash-settled at close; no assignment risk overnight (European-style)

### Gamma Dynamics — The Core Risk

The fundamental physics of 0DTE: gamma ∝ 1/√T, meaning gamma magnitude escalates exponentially as expiration approaches.

| Time Remaining | Gamma Level (vs 7-DTE equivalent) | Risk Level |
|---|---|---|
| 4+ hours (open–11am) | 1–2× | Low |
| 2–4 hours (11am–2pm) | 3–5× | Moderate |
| 1 hour (2–3pm) | 5–10× | High |
| < 30 min (3:30pm+) | 10×+ | Extreme — gamma spike |

**Theta acceleration profile**: morning decay is slow; by 2 PM decay doubles hourly; by 3:30 PM it is 4–5× the morning rate. This creates an asymmetric P&L window: enter after 2 PM to capture the steepest theta without holding through the extreme gamma hour unless the position is safely OTM.

**Dealer positioning cascade**: When 0DTE contracts represent >50% of total market gamma exposure, intraday price dynamics are driven by dealer hedging of these contracts — not longer-dated technical levels. Dealers long gamma from selling 0DTEs buy weakness/sell strength (dampening). Dealers short gamma amplify moves.

### Pin Risk — Strike Magnetism

Near expiration, open interest concentration at specific strikes creates a "magnetic" pull:

```python
# FlashAlpha Pin Score composite (0-100)
pin_score = (
    0.30 * oi_concentration_top3_strikes   # OI concentrated at 3 strikes
  + 0.25 * distance_to_highest_gamma       # proximity to peak-gamma strike
  + 0.25 * (1 - time_remaining / 4)        # proximity to close (0=4hr+ remaining)
  + 0.20 * gamma_magnitude_percentile       # absolute gamma level
)
# Pin score > 70 with < 2 hours remaining → strong magnet to nearest strike
# Exogenous news catalyst overrides; max pain mechanics apply in calm sessions
```

### Entry Parameters (Systematic Approach)

The optimal premium-selling window for a 0DTE iron condor:

| Parameter | Recommendation | Rationale |
|---|---|---|
| **Entry time** | 1:00–2:44 PM ET | Captures steepest theta decay; gamma still manageable |
| **Expiry** | Same-day (0DTE) | Cash-settled; no overnight risk |
| **Structure** | Iron condor (4-leg spread) | Defined risk; collects premium both sides |
| **Short strike OTM** | 0.20–0.32% OTM | SPX closes within 0.2% of 2pm price 65.6% of the time |
| **Spread width** | $5 wide (SPXW) | Margin efficient; ~$196 premium on $304 max loss (64.4% R/R) |
| **Short delta** | ~0.10–0.15 each side | Aggressive; higher probability than 45-DTE 16-delta |
| **Premium target** | $1.00–$2.00 per spread | At least $196 total; avoid if spread <$0.80 |

**Key probability finding (Option Alpha, 180-day sample)**: SPX closes within 0.2% of its 2pm level 65.6% of the time. A 0.2% OTM iron condor entered at 2:44pm therefore has ~68% historical max-profit probability. At 64.4% risk-reward, this yields a positive expected value of ~$36/trade.

### Management Rules

| Trigger | Action |
|---|---|
| Profit hits 50% of max credit | Close — do not hold to expiry; gamma risk increases too fast |
| Underlying approaching short strike (delta ≥ 0.30) | Roll untested side in, close tested side; or close entirely |
| Dealer GEX risk score > 75 (negative gamma regime) | **Do not enter** — dealer flows amplify adverse moves |
| Last 30 min (3:30–4pm ET) | Close any open position; extreme gamma spike window |
| Strong trending day (gap up/down >0.5% from 2pm level) | Skip the day — directional momentum kills condors |

### VRP Context for 0DTE

0DTE options capture the shortest end of the volatility term structure. The VRP (IV minus realized vol) is structurally present in short-dated options:

- **Realized-vs-implied spread**: 0DTE implied vol typically 2–5% above same-day realized vol in calm regimes
- **Put side asymmetry**: Put-side VRP is 2–5× larger than call-side VRP in ~80% of environments → selling symmetric condors underutilizes the put premium; some practitioners run asymmetric structures (wider/deeper put spread)
- **VRP z-score filter**: Only enter when VIX IV minus 20d realized vol > 1.5% (z > 0.5 threshold). In low-VRP environments the theta collection doesn't compensate for gamma risk

```python
# 0DTE entry filter: VRP check
import numpy as np

def vrp_z_score(vix: float, spy_returns: pd.Series, window: int = 20) -> float:
    """Compute VRP as VIX/sqrt(252) - trailing realized daily vol (annualized)."""
    realized_vol = spy_returns.rolling(window).std().iloc[-1] * np.sqrt(252) * 100
    vrp = vix - realized_vol                    # positive = IV > RV = premium environment
    vrp_hist = vix - spy_returns.rolling(window).std() * np.sqrt(252) * 100
    return (vrp - vrp_hist.mean()) / vrp_hist.std()

# Enter 0DTE condor only if:
# vrp_z_score(vix, spy_ret) > 0.5 AND current GEX dealer risk < 50
```

### Performance Data

| Study | Period | Strategy | Win Rate | Notes |
|---|---|---|---|---|
| CBOE / Schwartz (2026) | Current market | 0DTE SPX IC, $5 wide | N/A | 62% of SPX volume is 0DTE; structural shift |
| Option Alpha (2024) | 180 days | 0.2% OTM 2pm entry | ~68% | Max profit probability; $36 EV/trade |
| ApexVol research | 2013–2025 | Iron condor 15–20 delta | 65–70% | 80% WR with 50% profit management |
| Degese backtest (2024) | 1 year | 0DTE SPY condor, 11am entry | Positive | SPY daily; 0.32% OTM $5 wide |

**Key caveat**: All 0DTE backtests require intraday options data at ≥5-minute granularity. Monthly-snapshot approaches miss the critical gamma dynamics. ORATS, CBOE DataShop, or ThetaData intraday feed required for production-grade backtesting.

### Risk Profile — What Kills 0DTE Condors

| Risk | Trigger | Frequency | Impact |
|---|---|---|---|
| Gap move >0.5% after entry | Fed surprise, CPI shock, geopolitical event | ~15 trading days/year | Full max loss or worse if gamma amplifies |
| Slow trending day | SPX grinds 0.4% to one side over 2 hours | ~20% of trading days | Partial loss; need to manage tested side |
| Negative GEX regime | Dealers short gamma; moves amplify | Volatile regimes | Positive-feedback loops; stop logic critical |
| 3:30pm gamma spike | Random end-of-day liquidity event | Rare but devastating | Always close by 3:30pm |

### Capital Requirements & Position Sizing

- **Buying power**: Each $5 wide SPX 0DTE IC requires ~$304 per spread (defined risk)
- **Scaling**: Run 1–3 condors per $10k of portfolio risk capital; never exceed 15% of notional in all short-vol positions combined
- **Account type**: Cash-settled SPX contracts avoid pattern day trader rules for accounts <$25k (treated as index options, not pattern-day-trader equity trades)

### Implementation Checklist

```
Pre-entry (2pm ET daily):
□ Check SPX 0DTE IV / 7DTE IV ratio > 1.0 (intraday event premium present)
□ Compute VRP z-score > 0.5
□ Verify dealer GEX risk score < 50 (FlashAlpha or equivalent)
□ Confirm no scheduled FOMC/CPI/NFP release in final 2 hours
□ Select short strikes 0.20-0.32% OTM each side

Entry (2:00–2:44pm ET):
□ Enter 4-leg IC; collect ≥ $196 net credit on $5 wide SPXW
□ Set automatic close at 50% of max credit (GTC)
□ Set automatic close at 150% of max loss (stop loss)

Exit:
□ Close all positions by 3:30pm regardless of P&L (gamma spike window)
□ Never hold to expiry
```

### Data Sources for 0DTE Backtesting

| Source | Cost | Granularity | Notes |
|---|---|---|---|
| **CBOE DataShop** | Per-request pricing | 1-min intraday | Authoritative source; expensive for full history |
| **ThetaData** | $80/mo (starter) | 1-min Greeks | 2005+; best value for systematic research |
| **ORATS** | ~$100/trial | EOD + intraday | IV surface parameterized; good for surface research |
| **0DTESPX.com** | Freemium | Simulation | SPX-specific simulator + paper trading |
| **FlashAlpha API** | $239–$1,199/mo | Real-time | GEX/dealer flow; useful for live filtering |

### Why 0DTE Is Different From 45-DTE Condors

| Dimension | 45-DTE Iron Condor | 0DTE Iron Condor |
|---|---|---|
| **Theta collection** | Slow and steady | Explosive in final 2–3 hours |
| **Gamma risk** | Manageable (20–30 DTE peak) | Extreme near expiry |
| **Backtesting data** | EOD data sufficient | Needs intraday (≥5min) |
| **Capital per trade** | $304–$1,000 typical | $304–$500 (SPX $5 wide) |
| **Regime sensitivity** | Moderate | High — dangerous in trending/vol-spike days |
| **Pattern day trader rules** | Applies to SPY options | **Not applicable** to SPX (cash-settled index) |
| **Max trades/year** | ~10–12 (cycle-based) | Up to 252 (daily) |
| **Compounding** | Monthly reinvestment | Daily — but premium is small |

**Bottom line**: 0DTE condors offer a structurally sound premium-collection mechanism with daily compounding potential, but require intraday monitoring, strict exit rules, and a VRP/gamma filter for entry. Do NOT hold to expiry. The primary edge is the same VRP that drives 45-DTE condors, compressed into a single day — with proportionally higher gamma risk that demands active management.

---

## Reference: CME Group "25 Proven Strategies for Options on Futures" (2022)

**Source:** `sources/cme-group-25-proven-strategies-options-futures.pdf`

Quick-reference booklet covering all major option structures. Organized by two categories:

**Directional** (strategies 1–12): Long/Short Futures, Long/Short Synthetic Futures, Long/Short Risk Reversal, Long/Short Call, Long/Short Put, Bull Spread, Bear Spread

**Precision** (strategies 13–25): Long/Short Butterfly, Long/Short Iron Butterfly, Long/Short Straddle, Long/Short Strangle, Ratio Call/Put Spread, Call/Put Ratio Backspread, Box/Conversion

Each entry covers: when to use, profit/loss characteristics, decay characteristics, synthetics, and a pattern evolution diagram (4-month / 1-month / expiration P&L lines). Key to diagrams: purple = 4 months to expiry, gold = 1 month, green = at expiration.

---

## Neural Surrogate Options Pricing — Error-Bounded Fast Inference

**Source:** arXiv:2606.15502 — 'Fast, Reliable, and Error-Bounded Option Pricing with Pretrained Neural Networks: A GJR-GARCH Study' by Thijs van den Berg (Jun 2026)

This paper provides a principled recipe for replacing slow Monte Carlo option pricing with neural surrogates that have *quantified error guarantees* — solving the reliability problem that blocks neural options pricing from production use.

### The Problem
Many realistic volatility models (GJR-GARCH, Heston with stochastic vol-of-vol, rough volatility) have no closed-form option price. Monte Carlo simulation is accurate but slow (seconds per option, not microseconds). Prior neural surrogate approaches are fast but offer no error bounds — if the surrogate is wrong, you don't know by how much.

### The Solution: Mixture Density Network + Distribution-Free Error Bound

**Architecture:**
- A **Mixture Density Network (MDN)** maps (model parameters, maturity) → terminal return density as a Gaussian mixture
- Option prices, implied volatilities, and Greeks all follow in **closed form** from this Gaussian mixture (no Monte Carlo needed at inference)
- The CDF-matching loss aligns training to pricing error, not density fitting per se

**Error bound:**
- A distribution-free Monte Carlo noise floor of `√(1/(6N))` quantifies the best accuracy achievable at a given simulation budget N
- The out-of-sample error is decomposed into 4 controllable terms: approximation error, estimation error, training noise, and Monte Carlo noise floor
- This means you can certify 'the surrogate is within X% of Monte Carlo at N=10,000 samples'

**GJR-GARCH validation:**
- Out-of-sample CDF error: **1.4 × 10⁻⁴**, within 10% of the theoretical noise floor
- Pricing speed: **few microseconds per option on a single CPU core** (< 1 µs on GPU)
- Comparable accuracy to 100,000-path Monte Carlo, at a 1,000× speed improvement

### Relevance to Options Pipeline

| Use case | Application |
|---|---|
| H309 dispersion trading | Fast Greeks calculation for many component legs |
| Iron condor IV surface fitting | GJR-GARCH surrogate for smile fitting instead of flat BSM |
| Backtesting methodology | Replace Tier 0 (BSM) with Tier 0.5 (MDN-GJR) for free, accurate pricing |
| H266 VRP harvesting | Faster delta-hedged straddle P&L simulation with skew |

**Key constraint**: The surrogate must be retrained when model parameters shift significantly (e.g., after a vol regime change). Retraining time is not reported but is bounded by the Monte Carlo simulation budget.

**Code**: Not yet released publicly (paper is June 2026). The MDN architecture is standard — PyTorch implementation is ~200 lines using `torch.distributions.MixtureSameFamily`.

---

## Puts + Trend Following: Complementary Tail Risk (arXiv:2607.00883, July 2026)

Eccles et al. develop a CVaR framework for combining two distinct forms of tail protection:

**Different phases of stress:**
- **Put options**: immediate convex insurance — reprices within hours of a crash or volatility spike. Best for abrupt events (March 2020 style).
- **Trend following**: slow to engage (signal must cross zero) but strengthens during sustained drawdowns without requiring additional premium. Best for drawn-out bear markets (2022 style).

**Portfolio interpretation:**
- Our IBS strategy (XLK/SMH/IGV, 30% of production portfolio) is structurally similar to writing puts — positive carry in normal markets, sharp losses in crashes.
- Our H026/H041a momentum rotation (49% of portfolio) provides delayed trend-following tail protection — it routes to BIL when momentum deteriorates, but with a 1-month signal lag.
- A small explicit put hedge (1-2% of portfolio budget in OTM SPY puts, ~10% OTM, 3-month tenor) would provide the missing convex crash protection that trend following cannot.

**Gate for H266 design:** Only sell options (iron condors, CSPs) when VRP z-score > 0 AND trend-following sleeve is in defensive mode OR put protection is active. This separates VRP harvesting from crash risk.

**Cross-ref:** [H309 SPX Dispersion](../algorithms/multi-agent-llm-trading.md), [H362 Macro Gate](../algorithms/regime-detection.md), [Backtesting Design Principles](../backtesting/design-principles.md)

---

## Puts + Trend Following: Complementary Tail Risk (arXiv:2607.00883, July 2026)

Eccles et al. develop a CVaR framework for combining two distinct forms of tail protection:

**Different phases of stress:**
- **Put options**: immediate convex insurance — reprices within hours of a crash or volatility spike. Best for abrupt events (March 2020 style).
- **Trend following**: slow to engage (signal must cross zero) but strengthens during sustained drawdowns without requiring additional premium. Best for drawn-out bear markets (2022 style).

**Portfolio interpretation:**
- Our IBS strategy (XLK/SMH/IGV, 30% of production portfolio) is structurally similar to writing puts — positive carry in normal markets, sharp losses in crashes.
- Our H026/H041a momentum rotation (49% of portfolio) provides delayed trend-following tail protection — it routes to BIL when momentum deteriorates, but with a 1-month signal lag.
- A small explicit put hedge (1-2% of portfolio budget in OTM SPY puts, ~10% OTM, 3-month tenor) would provide the missing convex crash protection that trend following cannot.

**Gate for H266 design:** Only sell options (iron condors, CSPs) when VRP z-score > 0 AND trend-following sleeve is in defensive mode OR put protection is active. This separates VRP harvesting from crash risk.
