---
created: 2026-06-11
updated: 2026-06-11
category: paper-trading
tags: [execution, slippage, transaction-costs, alpaca, paper-trading, live-graduation]
---

# Execution Quality & Slippage Analysis

How to measure, track, and interpret execution quality for the three live paper-trading strategies. Critical for the paper→live graduation gate — a strategy that looks great in backtest but has poor fill quality in paper trading will be worse live.

**Related pages**: [Transaction Cost Modeling](../backtesting/transaction-costs.md) | [Live Graduation Criteria](live-graduation-criteria.md) | [Alpaca Reference](../data-sources/alpaca.md)

---

## Why Execution Quality Matters

Backtests fill at "the close" or "the open." Live trading does not. The gap between theoretical and realized fills (slippage) compounds across every trade and degrades strategy Sharpe. For our portfolio:

| Strategy | Monthly trades | Round-trip slippage assumption | Annual drag estimate |
|----------|---------------|-------------------------------|----------------------|
| H026 ETF rotation | ~2–4 | 4–6 bps (S&P sector ETFs) | ~0.1–0.2%/yr |
| H181 reversal | ~6–10 | 8–15 bps (large-cap stocks) | ~0.3–0.5%/yr |
| PEAD-NLP (H163/H174) | 2–6 | 15–25 bps (gap fill at open) | ~0.3–0.6%/yr |

At $100k AUM these are immaterial. At $500k+ they warrant monitoring.

---

## Alpaca Paper Trading: What It Simulates (and What It Doesn't)

From Alpaca's official documentation:

**Simulated accurately:**
- Order routing logic (limit/market/stop mechanics)
- Partial fill events (random 10% of the time when order eligible)
- PDT rules and margin calculations
- Queue position approximation

**NOT simulated:**
- Price slippage from order latency
- Real market impact from large orders exceeding available liquidity at NBBO
- Intraday price drift between order submission and fill time
- Dividends (paper account does NOT pay dividends)

**Practical implication for our strategies:**
Paper P&L is therefore *optimistic* vs live trading. The paper account fills market orders at NBBO at the moment the order becomes marketable — there is no adverse price movement modeled. In live trading on Alpaca, PFOF (Payment For Order Flow) routing means market orders on retail accounts typically fill within 0.5–2 bps of NBBO for liquid stocks, but during volatile opens (PEAD gap entries especially) slippage can be 10–30 bps.

---

## Standard Execution Benchmarks

| Benchmark | Definition | Best for |
|-----------|-----------|---------|
| Arrival price (IS) | Price at order submission time | General benchmark; captures full slippage |
| VWAP | Volume-weighted average of the day | Large institutional orders spread across day |
| TWAP | Time-weighted average | Smaller orders, less market impact |
| Open price | Official 9:30 AM open | OPG (at-the-open) orders |
| Close price | Official 4:00 PM close | End-of-day fills; ETF rotation rebalances |

For our strategies:
- **H026/H181** use MOC (market-on-close) or equivalent — compare to 4:00 PM close
- **PEAD-NLP** uses OPG (at-the-open) — compare to official open price

---

## Measuring Implementation Shortfall (IS)

Implementation shortfall = difference between paper account fill price and arrival/benchmark price.

**Formula:**
```
IS (bps) = (fill_price - benchmark_price) / benchmark_price × 10,000
```
Positive IS = paid more than benchmark (slippage cost for buys, or shortfall for sells).

### Python: Extract fills and compute IS

```python
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

def get_alpaca_client():
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True,
    )

def fetch_recent_fills(client, days_back=90):
    """Fetch all filled orders from the past N days."""
    req = GetOrdersRequest(
        status=QueryOrderStatus.CLOSED,
        limit=500,
        after=(datetime.utcnow() - timedelta(days=days_back)).isoformat(),
    )
    orders = client.get_orders(req)
    
    fills = []
    for o in orders:
        if o.filled_qty and float(o.filled_qty) > 0 and o.filled_avg_price:
            fills.append({
                "order_id":     o.id,
                "symbol":       o.symbol,
                "side":         str(o.side).split(".")[-1],
                "qty":          float(o.filled_qty),
                "fill_price":   float(o.filled_avg_price),
                "submitted_at": o.submitted_at,
                "filled_at":    o.filled_at,
                "order_type":   str(o.type).split(".")[-1],
                "tif":          str(o.time_in_force).split(".")[-1],
                "limit_price":  float(o.limit_price) if o.limit_price else None,
            })
    return pd.DataFrame(fills)

def get_benchmark_prices(symbols, dates):
    """
    Fetch OHLCV for given symbols/dates.
    Returns dict: (symbol, date) -> {open, close, vwap}
    """
    benchmarks = {}
    for sym in symbols:
        try:
            dates_list = sorted(set(d.date() for d in dates if d))
            start = min(dates_list) - timedelta(days=1)
            end   = max(dates_list) + timedelta(days=1)
            df = yf.download(sym, start=start, end=end, progress=False, auto_adjust=False)
            for d in dates_list:
                ts = pd.Timestamp(d)
                if ts in df.index:
                    benchmarks[(sym, d)] = {
                        "open":  float(df.loc[ts, "Open"]),
                        "close": float(df.loc[ts, "Close"]),
                        "high":  float(df.loc[ts, "High"]),
                        "low":   float(df.loc[ts, "Low"]),
                        # VWAP approximation from OHLCV
                        "vwap":  float((df.loc[ts, "High"] + df.loc[ts, "Low"] + df.loc[ts, "Close"]) / 3),
                    }
        except Exception as e:
            print(f"  {sym}: fetch error {e}")
    return benchmarks

def compute_is(fills_df, benchmarks):
    """
    Compute Implementation Shortfall relative to open and close prices.
    
    For OPG orders: compare to open
    For EOD/MOC orders: compare to close
    For intraday market orders: compare to open (best approximation)
    
    Returns DataFrame with IS metrics per order.
    """
    results = []
    for _, row in fills_df.iterrows():
        sym = row["symbol"]
        filled_at = row["filled_at"]
        if filled_at is None:
            continue
        trade_date = filled_at.date()
        bench = benchmarks.get((sym, trade_date), {})
        
        # Select appropriate benchmark
        tif = row.get("tif", "")
        if tif in ("opg", "moo"):
            ref_price = bench.get("open")
            ref_label = "open"
        elif tif in ("moc", "cls"):
            ref_price = bench.get("close")
            ref_label = "close"
        else:
            ref_price = bench.get("open")   # intraday: use open as proxy
            ref_label = "open (proxy)"
        
        fill = row["fill_price"]
        side = row["side"].lower()
        
        if ref_price and ref_price > 0:
            # IS: positive = paid more (cost to buyer) / received less (cost to seller)
            if side == "buy":
                is_bps = (fill - ref_price) / ref_price * 10_000
            else:
                is_bps = (ref_price - fill) / ref_price * 10_000
            
            results.append({
                **row.to_dict(),
                "benchmark":     ref_price,
                "benchmark_type": ref_label,
                "is_bps":        round(is_bps, 2),
                "date":          trade_date,
            })
    
    return pd.DataFrame(results)

# --- Run it ---
if __name__ == "__main__":
    client = get_alpaca_client()
    
    print("Fetching fills...")
    fills = fetch_recent_fills(client, days_back=120)
    print(f"  {len(fills)} fills found")
    if fills.empty:
        print("No fills found.")
        exit()
    
    # Get benchmark prices for all symbols/dates
    symbols = fills["symbol"].unique().tolist()
    dates   = fills["filled_at"].dropna().tolist()
    
    print(f"Fetching benchmark prices for {len(symbols)} symbols...")
    benchmarks = get_benchmark_prices(symbols, dates)
    
    is_df = compute_is(fills, benchmarks)
    
    print("\n=== Execution Quality Summary ===")
    print(f"Orders analyzed: {len(is_df)}")
    print(f"Mean IS: {is_df['is_bps'].mean():.2f} bps")
    print(f"Median IS: {is_df['is_bps'].median():.2f} bps")
    print(f"Std IS: {is_df['is_bps'].std():.2f} bps")
    print(f"Max IS (worst single fill): {is_df['is_bps'].max():.2f} bps")
    
    print("\nBy order type:")
    print(is_df.groupby("order_type")["is_bps"].agg(["mean","median","count"]).round(2))
    
    print("\nBy symbol (top 10 by slippage):")
    sym_is = is_df.groupby("symbol")["is_bps"].mean().sort_values(ascending=False)
    print(sym_is.head(10).round(2))
```

---

## Per-Strategy Expected Slippage Benchmarks

### H026 ETF Rotation (Monthly MOC rebalances)

Fill target: **close price +/- 2 bps**. Highly liquid sector ETFs (XLK, XLE, etc.) have narrow spreads.

```python
# H026 benchmark check
H026_BENCHMARK_BPS = 3.0   # expected max slippage (each leg)
H026_WARNING_BPS   = 8.0   # alert if any single fill exceeds this

def check_h026_quality(is_df):
    h026_etfs = ['XLK','XLE','XLF','XLV','XLI','XLB','XLU','XLRE','XLY','XLP','XLC',
                 'BIL','GLD','TLT','IEF','TIP','DBC','AGG','GDX','DBA','SLV','UNG']
    h026_fills = is_df[is_df['symbol'].isin(h026_etfs)]
    if h026_fills.empty:
        return "No H026 fills to analyze"
    mean_is = h026_fills['is_bps'].mean()
    flags = h026_fills[h026_fills['is_bps'] > H026_WARNING_BPS]
    return {
        "strategy": "H026",
        "n_fills": len(h026_fills),
        "mean_is_bps": round(mean_is, 2),
        "flag_count": len(flags),
        "status": "OK" if mean_is < H026_BENCHMARK_BPS else "ELEVATED",
    }
```

**Typical actual fills (paper, from Alpaca orders log):**
- SMH buy 2026-06-08: filled $598.687 vs open $598.60 → IS = +1.5 bps ✓
- XLK buy 2026-06-08: filled $185.203 vs open $185.15 → IS = +2.9 bps ✓

### H181 Reversal (Monthly MOC rebalances, 30 large-cap stocks)

Fill target: **close price +/- 5 bps**. Mid-cap exposure (some names less liquid than mega-cap).

```python
H181_BENCHMARK_BPS = 8.0    # large-cap stocks, slightly wider spread than ETFs
H181_WARNING_BPS   = 20.0   # alert threshold

# Strategy holds ~6 stocks at once; rebalances first trading day of month
# Check 30-stock universe: AAPL, MSFT, NVDA, etc. (8 GICS sectors)
```

### PEAD-NLP (Event-driven, OPG/market orders at 9:32 AM)

Fill target: **official open price +/- 15 bps**. Gap events can have significant bid-ask spread at open; fill quality is most sensitive here.

```python
PEAD_BENCHMARK_BPS = 15.0   # acceptable slippage at open on gap day
PEAD_WARNING_BPS   = 40.0   # gap fill can be wide; flag if > 40 bps

# Note: PEAD strategy relies on the gap itself (stock up >3% at open)
# The edge is the *post-open* continuation, not the fill quality per se
# But poor fill quality erodes the 6.89% mean return from H174 baseline
# At 40 bps slippage that's still only 0.4% drag on a 6.89% mean trade
```

---

## Gap Between Paper and Live: What to Expect

When we graduate to live trading on Alpaca, expect:

| Order type | Paper fill quality | Expected live degradation |
|------------|-------------------|--------------------------|
| Market (liquid ETF) | NBBO mid | −1 to −3 bps (PFOF routing) |
| Market (large-cap stock) | NBBO mid | −2 to −5 bps |
| Market at open (gap stock) | Official open | −5 to −25 bps (volatile open) |
| Limit order (ETF) | At limit | 0 bps if fills; partial risk |
| MOC order (ETF) | Official close | −1 to −2 bps (closing auction) |

**Best practices for live transition:**
1. Switch ETF rotation rebalances to MOC orders — lowest slippage at official close
2. For PEAD entries, consider limit order at open price + 0.1% rather than pure market
3. Use `time_in_force="opg"` (at-open) not plain `"day"` for morning entries

---

## Slippage Budgeting for Strategy Sharpe Estimates

```python
def after_slippage_sharpe(
    gross_sharpe: float,
    annual_turnover: float,         # fraction of portfolio per year (e.g., 12 = 1200%)
    slippage_per_leg_bps: float,    # one-way slippage, basis points
    gross_return_pct: float,        # annualized gross return %
    gross_vol_pct: float,           # annualized volatility %
) -> dict:
    """
    Estimate after-slippage Sharpe ratio.
    
    annual_turnover: 12 → full portfolio replaced 12x/year (monthly rebalancing)
    """
    round_trip_bps = slippage_per_leg_bps * 2
    annual_drag_pct = (annual_turnover * round_trip_bps) / 100
    net_return = gross_return_pct - annual_drag_pct
    net_sharpe = net_return / gross_vol_pct   # simplified (ignores vol change)
    
    return {
        "gross_sharpe":     gross_sharpe,
        "annual_drag_pct":  round(annual_drag_pct, 3),
        "net_return_pct":   round(net_return, 2),
        "net_sharpe":       round(net_sharpe, 3),
        "drag_as_pct_return": round(annual_drag_pct / gross_return_pct * 100, 1),
    }

# Production portfolio breakdown (Sharpe 4.158, ~23.5% CAGR, vol ~5.6%)
print("H026 rotation:")
print(after_slippage_sharpe(
    gross_sharpe=3.007, annual_turnover=1.2,  # ~100% replaced/year (monthly top-1)
    slippage_per_leg_bps=3, gross_return_pct=18, gross_vol_pct=6))
# → drag ≈ 0.072%/yr, net Sharpe ≈ 2.99 (negligible)

print("\nH181 reversal:")
print(after_slippage_sharpe(
    gross_sharpe=1.138, annual_turnover=3.0,  # 6 stocks replaced ~50% per month
    slippage_per_leg_bps=8, gross_return_pct=24.6, gross_vol_pct=21.6))
# → drag ≈ 0.48%/yr, net Sharpe ≈ 1.11 (small but measurable)

print("\nPEAD-NLP (H174):")
print(after_slippage_sharpe(
    gross_sharpe=2.1, annual_turnover=0.7,    # ~14 events/yr at ~5% position each
    slippage_per_leg_bps=20, gross_return_pct=12, gross_vol_pct=5.7))
# → drag ≈ 0.28%/yr, net Sharpe ≈ 2.05 (still excellent)
```

---

## Running the Execution Quality Check

Paste into a Jupyter cell or run as a script:

```python
# Quick execution quality report
import os, sys
sys.path.insert(0, '/workspace/agent/backtesting/paper_trading')
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

client = TradingClient(
    api_key=os.environ["ALPACA_API_KEY"],
    secret_key=os.environ["ALPACA_SECRET"],
    paper=True,
)

# Get last 90 days of fills
req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=200)
orders = client.get_orders(req)

rows = []
for o in orders:
    if o.filled_qty and float(o.filled_qty) > 0 and o.filled_avg_price:
        rows.append({
            "symbol":       o.symbol,
            "side":         str(o.side).split(".")[-1],
            "fill_price":   float(o.filled_avg_price),
            "submitted_at": o.submitted_at,
            "filled_at":    o.filled_at,
            "tif":          str(o.time_in_force).split(".")[-1],
        })
fills = pd.DataFrame(rows)
print(f"Total fills: {len(fills)}")
print(fills.groupby("symbol")[["fill_price"]].count().rename(columns={"fill_price":"fills"}))

# To add IS analysis, run get_benchmark_prices() + compute_is() from above
```

---

## Execution Quality as a Paper→Live Graduation Gate

From [Live Graduation Criteria](live-graduation-criteria.md):

Suggested execution quality gate (to be added to graduation checklist):

| Criterion | Threshold | Check |
|-----------|-----------|-------|
| H026 mean IS | < 8 bps per leg | `check_h026_quality(is_df)` |
| H181 mean IS | < 15 bps per leg | per-fill log analysis |
| PEAD mean IS | < 30 bps per leg | harder to control; monitor trend |
| Fill rate (limit orders) | > 85% same-day | reduce if too many misses |

The paper→live slippage delta (additional degradation) for Alpaca retail accounts is estimated at **+2 to +5 bps per leg** for liquid ETFs, **+5 to +15 bps per leg** for individual stocks, based on published PFOF analysis and academic benchmarks.

---

## Useful References

- Almgren et al. (2005): square-root market impact model — see [Transaction Costs](../backtesting/transaction-costs.md)
- Alpaca Paper Trading docs: https://docs.alpaca.markets/docs/paper-trading (key: no slippage simulated)
- arXiv:2606.08285 (Yao & Zheng, 2026): "Beyond Agent Architecture" — execution assumptions and reproducibility audit for LLM trading systems; the "execution semantic" column in their 30-study evidence matrix is directly applicable to our evaluation
- arXiv:2606.01650 (Pav, 2026): post-selection Sharpe estimation — relevant when we select strategies based on OOS Sharpe; James-Stein shrinkage provides more reliable estimates than raw OOS Sharpe

---

## See Also

- [Live Graduation Criteria](live-graduation-criteria.md)
- [Transaction Cost Modeling](../backtesting/transaction-costs.md)
- [H149 Alpaca ETF Rotation](h122-alpaca.md) — current paper positions
- [PEAD-NLP Alpaca Deployment](pead-nlp-alpaca.md) — PEAD fill log
- [Alpaca Complete Reference](../data-sources/alpaca.md)
