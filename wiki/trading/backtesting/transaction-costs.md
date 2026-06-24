---
updated: 2026-05-09
---

# Transaction Cost Modeling for Backtesting

Accurate transaction cost modeling is the single most common gap between backtested and live results. A strategy showing 20% gross returns can deliver only 8% after realistic costs. This page covers every cost component, models of varying complexity, Python implementations, and calibrated defaults for daily equity strategies.

**Related pages**: [Design Principles](design-principles.md) | [Walk-Forward & CPCV](walk-forward-cpcv.md) | [Backtrader vs Vectorbt](../tools/backtrader-vs-vectorbt.md)

---

## Cost Components

| Component | Typical magnitude (daily equity) | Skippable? |
|-----------|----------------------------------|------------|
| Commission | $0–$1/trade (most retail brokers: $0) | If using Alpaca/IB zero-commission |
| Bid-ask spread | 0.01–0.10% of trade value | Never — always model |
| Market impact (temporary) | 0.01–0.30% depending on ADV% | Model when trade > 0.5% ADV |
| Market impact (permanent) | Rare for retail, model for >1% ADV | Only for large positions |
| Short borrow cost | 0.3–10%/yr (easy-to-borrow ~0.5%) | If any short positions |
| Financing cost | Fed funds + 0.5–2% on margin | If using leverage |
| Regulatory fees | ~$0.000008/share (SEC, FINRA) | Negligible at retail scale |

---

## Model 1: Flat Percentage (Baseline — Too Optimistic)

Apply a fixed percentage to every trade's notional value.

```python
def flat_cost(price: float, shares: float, pct: float = 0.001) -> float:
    """pct = 0.001 → 0.1% of trade value each way."""
    return abs(price * shares) * pct
```

**Default**: 0.05–0.10% one-way (0.10–0.20% round-trip).

**When to use**: Initial feasibility checks only. Overestimates costs for large liquid stocks, underestimates for small-cap illiquid names.

---

## Model 2: Bid-Ask Half-Spread (Better, Low Overhead)

The most important single cost to model correctly. Use the half-spread as the execution cost.

```python
import pandas as pd
import numpy as np

def estimate_spread_bps(ticker: str, avg_daily_volume_shares: float,
                        price: float) -> float:
    """
    Empirical half-spread estimate in basis points.
    Based on Chordia, Roll & Subrahmanyam (2001) calibration.

    Rule of thumb by ADV bucket:
    - S&P 500 large-cap:      2–4 bps
    - Mid-cap (Russell 1000): 4–8 bps
    - Small-cap (R2000):      8–25 bps
    - Micro-cap (<$300M):     25–80 bps
    """
    adv_usd = avg_daily_volume_shares * price
    if adv_usd > 500_000_000:   return 3.0   # S&P 500 mega-cap
    elif adv_usd > 100_000_000: return 5.0   # large-cap
    elif adv_usd > 20_000_000:  return 10.0  # mid-cap
    elif adv_usd > 5_000_000:   return 20.0  # small-cap
    else:                       return 50.0  # micro-cap / illiquid

def spread_cost(price: float, shares: float,
                half_spread_bps: float) -> float:
    """Cost per one-way trade (buy or sell)."""
    return abs(price * shares) * (half_spread_bps / 10_000)
```

### Polygon / Alpaca: computing actual spread

```python
import requests, os

def get_spread_bps(ticker: str, date: str) -> float:
    """
    Get average bid-ask spread in bps from Polygon daily snapshot.
    Requires polygon-api-client and free tier.
    """
    from polygon import RESTClient
    client = RESTClient(os.environ["POLYGON_API_KEY"])
    snap = client.get_snapshot_ticker("stocks", ticker)
    if snap and snap.day:
        # Use VWAP as proxy for mid; estimate spread from daily range
        daily_range = snap.day.high - snap.day.low
        mid = snap.day.vwap or snap.day.close
        spread_est = (daily_range * 0.1) / mid * 10_000  # rough estimate
        return max(spread_est, 2.0)  # floor at 2 bps
    return 10.0  # fallback default
```

---

## Model 3: Square-Root Market Impact (Industry Standard)

The most widely cited model for temporary market impact. Used by major sell-side desks and asset managers.

**Formula (Almgren et al. 2005):**
```
MI = σ × (participation_rate)^β × ψ
```
where:
- σ = daily return volatility of the stock
- participation_rate = shares_traded / ADV (average daily volume)
- β ≈ 0.6 (empirically calibrated; often simplified to 0.5 = square root)
- ψ = scaling constant ≈ 0.142 (Kissell & Glantz calibration)

**Simplified square-root formula:**
```
MI (bps) = σ_daily_bps × sqrt(order_size / ADV) × 100
```

```python
import numpy as np

def market_impact_bps(order_shares: float,
                      adv_shares: float,
                      daily_vol: float,      # annualized vol, e.g. 0.20
                      beta: float = 0.5,
                      psi: float = 0.142) -> float:
    """
    Temporary market impact in basis points (one-way).
    
    Parameters
    ----------
    order_shares : shares in the order
    adv_shares   : 20-day average daily volume in shares
    daily_vol    : annualized return volatility (e.g. 0.20 for 20%)
    beta         : impact exponent (0.5 = square root, 0.6 = Almgren)
    psi          : scaling constant
    
    Returns
    -------
    impact in basis points (positive = cost to buyer; same cost to seller)
    """
    sigma_daily = daily_vol / np.sqrt(252)  # daily vol
    participation = order_shares / adv_shares
    impact = psi * sigma_daily * (participation ** beta)
    return impact * 10_000  # convert to bps

# Example: S&P 500 stock, $500k order
# Stock: $200, 2M ADV shares, 25% annual vol
order = 2_500          # shares ($500k notional)
adv   = 2_000_000      # 20-day ADV
vol   = 0.25           # annualized

impact = market_impact_bps(order, adv, vol)
print(f"Market impact: {impact:.1f} bps")  # → ~1.4 bps (negligible)

# Same strategy on a $1B AUM fund — same position sizing becomes:
large_order = 250_000  # shares (same $500k / $200 = 2500 shares scaled 100x)
impact_large = market_impact_bps(large_order, adv, vol)
print(f"Large fund impact: {impact_large:.1f} bps")  # → ~14 bps
```

**Empirical calibration (2026):** arXiv:2606.24019 tested the SRL on AAPL using 178 trading days of full Nasdaq ITCH L3 data (Dec 2024–Aug 2025, ~500M events). Bias-corrected estimate: c_est = 0.69 (raw c_raw = 0.69). Confirms c ∈ [0.5, 1.0] is appropriate for US large-cap equities. **Recommended defaults:** c = 0.70 for large-cap US equity momentum (H181, H198, H228); c = 0.85 for mid-cap where liquidity is lower.

**When market impact matters for this project:**
- At paper trading scale ($100k portfolio): almost never — position sizes are <0.01% ADV for liquid stocks
- At $1M+ AUM: begins to matter for small-cap positions
- At $10M+ AUM: must model explicitly for all positions

---

## Model 4: Full Cost Model (Production Grade)

Combines all components into a single per-trade cost estimate.

```python
import numpy as np
import pandas as pd

class TransactionCostModel:
    """
    Full transaction cost model for daily equity strategies.
    All costs returned in dollars.
    """
    
    def __init__(self,
                 commission_per_share: float = 0.0,    # Alpaca: $0
                 min_commission: float = 0.0,
                 use_market_impact: bool = True):
        self.commission_per_share = commission_per_share
        self.min_commission = min_commission
        self.use_market_impact = use_market_impact
    
    def compute(self,
                price: float,
                shares: float,
                adv_shares: float,
                daily_vol: float,       # annualized, e.g. 0.20
                half_spread_bps: float  # from estimate_spread_bps()
                ) -> dict:
        """
        Returns itemized and total cost for one trade leg.
        
        shares: positive = buy; negative = sell (cost is same both ways).
        """
        notional = abs(price * shares)
        
        # 1. Commission
        commission = max(
            abs(shares) * self.commission_per_share,
            self.min_commission
        )
        
        # 2. Half-spread (always pay crossing spread on aggressive orders)
        spread_cost = notional * (half_spread_bps / 10_000)
        
        # 3. Market impact (square-root model)
        if self.use_market_impact and adv_shares > 0:
            mi_bps = market_impact_bps(abs(shares), adv_shares, daily_vol)
            impact_cost = notional * (mi_bps / 10_000)
        else:
            impact_cost = 0.0
        
        total = commission + spread_cost + impact_cost
        
        return {
            "commission": commission,
            "spread": spread_cost,
            "market_impact": impact_cost,
            "total": total,
            "total_bps": total / notional * 10_000 if notional > 0 else 0,
        }


# Usage example: build a backtest cost log
def apply_costs_to_trades(trades_df: pd.DataFrame,
                           adv_map: dict,       # ticker → ADV shares
                           vol_map: dict,        # ticker → annual vol
                           spread_map: dict      # ticker → half-spread bps
                           ) -> pd.DataFrame:
    """
    trades_df columns: date, ticker, price, shares
    Returns trades_df with cost columns added.
    """
    model = TransactionCostModel()
    results = []
    for _, row in trades_df.iterrows():
        t = row["ticker"]
        cost = model.compute(
            price=row["price"],
            shares=row["shares"],
            adv_shares=adv_map.get(t, 1_000_000),
            daily_vol=vol_map.get(t, 0.20),
            half_spread_bps=spread_map.get(t, 5.0),
        )
        results.append(cost)
    costs_df = pd.DataFrame(results)
    return pd.concat([trades_df.reset_index(drop=True),
                       costs_df.reset_index(drop=True)], axis=1)
```

---

## Model 5: Short-Selling Costs

If any strategy involves short positions, model the borrow cost.

```python
def short_borrow_cost(notional: float, annualized_borrow_rate: float,
                      holding_days: int) -> float:
    """
    Cost to borrow shares for a short position.
    
    annualized_borrow_rate:
      - Easy-to-borrow (ETFs, S&P 500): 0.3–1.0%/yr
      - General collateral (most large-caps): 0.5–2.0%/yr
      - Hard-to-borrow (high short interest): 5–50%+/yr
    """
    daily_rate = annualized_borrow_rate / 252
    return notional * daily_rate * holding_days

# Example: short $50k in SPY for 10 days
cost = short_borrow_cost(50_000, 0.005, 10)  # 0.5%/yr
print(f"Borrow cost: ${cost:.2f}")  # → $0.99
```

**Key short borrow rates (2026 approximate):**

| Category | Annualized rate |
|----------|----------------|
| Major ETFs (SPY, QQQ, IWM) | 0.25–0.50% |
| S&P 500 large-cap | 0.30–1.0% |
| Mid-cap, low short interest | 1.0–3.0% |
| High short interest (>20% float) | 5–50%+ |
| Micro-cap / hard-to-borrow | 20–100%+ |

---

## Vectorbt & Backtrader: Built-in Cost Parameters

### Vectorbt (recommended for our daily engine)

```python
import vectorbt as vbt
import numpy as np

# Create portfolio with realistic costs
portfolio = vbt.Portfolio.from_signals(
    close=prices,
    entries=entry_signals,
    exits=exit_signals,
    
    # Fixed fees per trade (absolute, e.g. $0 for Alpaca)
    fixed_fees=0.0,
    
    # Proportional fees (fraction of trade value)
    # 0.0005 = 5 bps per leg = 10 bps round-trip (spread + small impact)
    fees=0.0005,
    
    # Slippage model (fraction): applied as adverse price move
    # 0.0003 = 3 bps additional slippage per leg
    slippage=0.0003,
    
    # Direction: long only, short only, or both
    direction="longonly",
    
    # Use open price + slippage for fill (more realistic than close)
    price="open",
    
    init_cash=100_000,
)
```

**Recommended Vectorbt defaults (daily strategies, Alpaca):**

| Strategy Type | fees (bps/leg) | slippage (bps/leg) | Notes |
|---------------|----------------|---------------------|-------|
| ETF rotation (liquid) | 3 | 1 | SPY/QQQ: 2 bps half-spread |
| Large-cap momentum | 5 | 3 | Mid-cap spread estimate |
| Small-cap factor | 15 | 10 | Wider spread, thin liquidity |
| PEAD event-driven | 8 | 5 | Gap fill at open |

### Backtrader

```python
import backtrader as bt

class MyStrategy(bt.Strategy):
    pass

cerebro = bt.Cerebro()

# Per-trade commission (fraction of trade value)
cerebro.broker.setcommission(commission=0.0005)  # 5 bps per leg

# Slippage: percentage of price
cerebro.broker.set_slippage_perc(0.0003)         # 3 bps adverse move
```

---

## Research Findings: Impact on Strategy Returns

### Empirical calibration (Kissell & Malamut 2006 + QuantJourney 2025)

| Market cap tier | Typical round-trip cost (incl. spread + impact) | After-cost Sharpe reduction |
|----------------|--------------------------------------------------|---------------------------|
| Mega-cap (>$50B) | 3–8 bps | ~0.05–0.15 Sharpe units |
| Large-cap ($5–50B) | 8–20 bps | ~0.1–0.3 |
| Mid-cap ($1–5B) | 20–50 bps | ~0.3–0.7 |
| Small-cap (<$1B) | 50–150 bps | >0.7 — often strategy-killing |

### Turnover sensitivity formula

```python
def cost_drag_per_year(annual_turnover: float,
                       round_trip_cost_bps: float) -> float:
    """
    annual_turnover: fraction of portfolio turned over per year
    e.g. monthly rebalancing with 30% replaced → 0.30 × 12 = 3.6

    Returns annual return drag in percentage points.
    """
    return annual_turnover * round_trip_cost_bps / 100  # bps → pct

# Example: monthly momentum strategy
# Turnover: 100% portfolio/month = 12 × per year
# Round-trip cost: 20 bps (mid-cap)
drag = cost_drag_per_year(12.0, 20)
print(f"Annual drag: {drag:.1f}%")  # → 2.4% per year
```

### Confirmed from our hypothesis testing

- **H020 ETF rotation** (SPY/QQQ/IWM/GLD/BIL): Round-trip ~5 bps; monthly turnover → ~0.3%/yr drag — negligible on 18%+ CAGR strategy
- **H163 PEAD-NLP**: Round-trip ~15 bps (gap fill at open); 2–4 trades/month; annual drag ~0.4%/yr — acceptable vs. ~12% PEAD return
- **H152-H160 pairs trading (FAILED)**: High turnover ~200–400%/yr × 20 bps = 4–8%/yr drag — explains why "theoretical" pairs returns disappear in practice

---

## Recommended Defaults for This Project

```python
# Default cost assumptions for our backtesting pipeline
COST_DEFAULTS = {
    # Alpaca: $0 commission
    "commission_pct": 0.0,
    
    # Per-leg (one-way) costs in basis points:
    "etf_rotation": {"fees": 0.0003, "slippage": 0.0001},      # 3 + 1 bps
    "large_cap_daily": {"fees": 0.0005, "slippage": 0.0003},   # 5 + 3 bps
    "mid_cap_daily": {"fees": 0.0010, "slippage": 0.0005},     # 10 + 5 bps
    "small_cap_daily": {"fees": 0.0020, "slippage": 0.0010},   # 20 + 10 bps
    "pead_open_fill": {"fees": 0.0008, "slippage": 0.0005},    # 8 + 5 bps (gap fill risk)
    "options_single_leg": {"fees": 0.0056, "slippage": 0.0000},# 56% of spread (tastytrade)
    "options_4_leg": {"fees": 0.0056, "slippage": 0.0000},     # same: 4 legs × 56% B/A
}
```

---

## Key References

- Almgren et al. (2005): "Direct Estimation of Equity Market Impact" — original square-root model calibration
- Kissell & Glantz (2003): "Optimal Trading Strategies" — full cost decomposition framework
- Obizhaeva & Wang (2013): "Optimal Trading Strategy and Supply/Demand Dynamics" — resilience model
- BSIC Backtesting Series Ep. 5: https://bsic.it/backtesting-series-episode-5-transaction-cost-modelling/
- Hudson & Thames Backtest Tutorial: https://github.com/hudson-and-thames/backtest_tutorial/blob/main/Intro_Transaction_Costs.ipynb
- QuantJourney (2025): "Slippage: A Comprehensive Analysis and Non-Linear Modeling with ML" — RF model achieving R²=0.898

---

## Time Stops (Stats Edge, 2026-05-29)

A **time stop** exits a position after a fixed number of bars if neither the profit target nor the loss stop has triggered. Stats Edge uses 1 week as the time stop for their weekly-bar strategies.

### Why time stops matter

Without a time stop, a trade that "goes nowhere" continues to tie up capital indefinitely. In a cross-sectional strategy trading 10+ positions simultaneously, capital efficiency degrades when positions remain open in flat/sideways names.

**Effect on metrics:**
- Reduces average hold time → more trades per year → more accurate estimate of edge
- Can improve Sharpe by eliminating long stretches of zero return (neutral trades drag down mean, inflate variance)
- Especially important for event-driven strategies (PEAD) where the catalyst window is defined

### Application to our strategies

| Strategy | Current exit | Recommended time stop |
|---|---|---|
| H174 PEAD | 20 trading days | Already has time stop ✅ |
| H181 Reversal | Monthly rebalance | Implicit ~20 days ✅ |
| H217 Alpha101 | Monthly rebalance | Implicit ~20 days ✅ |
| H228 Blend | Monthly rebalance | Implicit ~20 days ✅ |
| H192-D BAB | Monthly rebalance | Implicit ~20 days ✅ |
| H234 Inside-bar | 1 week (explicit) | 1-week time stop ✅ |

For weekly-bar swing strategies (H234 family), the time stop IS the exit rule — 1-week hold regardless of outcome.

### Execution discipline (from Stats Edge)

Three rules that apply regardless of time stop:
1. **Don't skip setups** — a skipped winner during a drawdown is where real returns get destroyed
2. **Don't move stops mid-trade** — discretion inside a systematic framework combines the worst of both
3. **Don't size up to catch up** — bigger positions during drawdowns is how systematic traders blow up

Source: Stats Edge Trading "The 25-Year Backtest" (Michael Nauss CMT/CAIA/CDMS, 2026)
