---
title: Risk Controls & Live Trading Monitoring
added: 2026-06-17
category: paper-trading
---

# Risk Controls & Live Trading Monitoring

Operational risk management for live algorithmic trading. Covers portfolio-level controls, circuit breakers, kill-switch implementation, and real-time monitoring via Alpaca.

**Prerequisite:** `paper-trading/live-graduation-criteria.md` — SPRT gates and minimum trade counts before going live.

---

## Risk Budget Framework

Risk is allocated at three levels: per-trade, per-strategy, and portfolio-wide. Each level has independent limits — a trade can be within its per-trade limit but still be blocked if the portfolio is at its weekly cap.

| Level | Metric | Soft Limit (reduce) | Hard Limit (halt) |
|-------|--------|---------------------|-------------------|
| Per-trade | % of portfolio at risk | 2% | 3% |
| Per-strategy | Daily P&L | -3% of portfolio | -5% of portfolio |
| Portfolio | Daily P&L | -5% | -8% |
| Portfolio | Weekly P&L | -8% | -12% |
| Portfolio | Max drawdown from HWM | -15% | -20% |

These thresholds are calibrated to our confirmed strategy Max Drawdowns:
- H026 rotation: MaxDD ~-12.5% → daily -5% soft stop is approximately 1 standard bad week
- H174 PEAD: median hold 20 days → weekly limit most relevant
- H181 reversal: daily turnover → daily limit most relevant

---

## Circuit Breaker Tiers

### Tier 1 — Reduce (soft trigger)
- Cut all new position sizes by 50%
- Log the event; do NOT close existing positions
- Typically: portfolio down >3% intraday, or single strategy losing streak (3+ consecutive losses at >1% each)

### Tier 2 — Pause (medium trigger)
- No new entries for the rest of the session
- Hold existing positions through their normal exit logic
- Send alert to Kevin (Telegram)
- Trigger: portfolio down >5% intraday, or weekly loss >8%

### Tier 3 — Close All (hard trigger)
- Close all open positions at market
- Cancel all open orders
- Disable all scheduled trading tasks until manual re-enable
- Send urgent alert
- Trigger: portfolio down >8% intraday, or max drawdown from HWM >20%

---

## Kill-Switch Implementation (Alpaca)

```python
"""
Emergency kill switch — close all positions and cancel all orders.
Call this from monitoring script or manually when Tier 3 is reached.
"""
import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import ClosePositionRequest

def kill_switch(reason: str = "manual override"):
    client = TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True  # set to False for live
    )

    # Cancel all open orders first
    client.cancel_orders()

    # Close all positions at market
    client.close_all_positions(cancel_orders=True)

    print(f"[KILL SWITCH ACTIVATED] Reason: {reason}")
    # TODO: send Telegram alert here
```

---

## Position Sizing — ATR-Based (Volatility-Scaled)

Size each trade so that 1 ATR move (14-day) equals exactly 1% of portfolio.

```python
import numpy as np

def atr_position_size(portfolio_value: float, current_price: float,
                      atr_14: float, risk_pct: float = 0.01) -> int:
    """
    Returns number of shares so that 1 ATR move = risk_pct of portfolio.
    Example: $100k portfolio, $200 stock, ATR=$5 → 200 shares ($40k notional)
    """
    dollar_risk = portfolio_value * risk_pct
    shares = int(dollar_risk / atr_14)
    # Cap at 10% notional per position
    max_shares = int(portfolio_value * 0.10 / current_price)
    return min(shares, max_shares)
```

For monthly-rebalance strategies (H026, H045), position sizing is implicit — we always allocate the full strategy's weight. The risk controls apply at the portfolio level, not per-trade.

---

## Portfolio Heat Monitoring

"Portfolio heat" = total dollars at risk across all open positions, assuming max adverse excursion = 2 × ATR per position. Should stay below 15% of portfolio value.

```python
def portfolio_heat(positions: list, atr_map: dict, portfolio_value: float) -> float:
    """
    positions: list of {symbol, qty, current_price}
    atr_map: {symbol: 14-day ATR}
    Returns heat as fraction of portfolio (0.0 to 1.0).
    """
    total_risk = 0.0
    for pos in positions:
        sym = pos["symbol"]
        atr = atr_map.get(sym, pos["current_price"] * 0.02)  # 2% fallback
        dollar_risk = pos["qty"] * atr * 2  # 2x ATR = max expected move
        total_risk += dollar_risk
    return total_risk / portfolio_value
```

---

## Real-Time Monitoring via Alpaca REST

For strategies with intraday activity, poll every 30 seconds:

```python
import time
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AccountStatus

def monitor_portfolio(client: TradingClient, drawdown_limit: float = 0.08):
    """
    Check portfolio daily P&L. Trigger halt if drawdown_limit exceeded.
    drawdown_limit: fraction of portfolio (e.g. 0.08 = -8%)
    """
    account = client.get_account()
    equity = float(account.equity)
    last_eq = float(account.last_equity)

    daily_pnl_pct = (equity - last_eq) / last_eq if last_eq > 0 else 0

    print(f"Equity: ${equity:,.0f} | Daily P&L: {daily_pnl_pct:.2%}")

    if daily_pnl_pct < -drawdown_limit:
        kill_switch(reason=f"Daily P&L {daily_pnl_pct:.2%} below -{drawdown_limit:.0%} limit")
        return False

    return True
```

For strategies with no intraday activity (H026, H045 monthly), a daily check at 3:45 PM CT is sufficient.

---

## Correlation Guard (Pre-Entry Check)

Before entering a new position, check that it doesn't add redundant exposure to an existing holding.

```python
import pandas as pd

def correlation_guard(new_symbol: str, existing_symbols: list,
                      returns_df: pd.DataFrame, corr_limit: float = 0.75) -> bool:
    """
    Block entry if new_symbol is >corr_limit correlated with any existing position.
    returns_df: rolling 60-day daily returns, columns = ticker symbols
    """
    if new_symbol not in returns_df.columns or not existing_symbols:
        return True  # allow if no data

    new_rets = returns_df[new_symbol]
    for sym in existing_symbols:
        if sym not in returns_df.columns:
            continue
        corr = new_rets.corr(returns_df[sym])
        if corr > corr_limit:
            print(f"BLOCKED: {new_symbol} ↔ {sym} corr={corr:.2f} > {corr_limit}")
            return False
    return True
```

Note: Most of our ETF rotation strategies are already sector-diversified. This guard is most useful for PEAD (H174) when multiple earnings plays fire in the same sector simultaneously.

---

## Alert System

Alerts fire via `mcp__nanoclaw__send_message` (George's Telegram integration) or Alpaca email.

**Minimum alerting checklist:**
- [ ] Tier 2 or 3 circuit breaker triggered
- [ ] Kill switch activated
- [ ] Any single trade loss > 2% of portfolio
- [ ] Strategy underperforming its expected Sharpe by >1σ over 30 days
- [ ] API connection lost (Alpaca WebSocket disconnect)
- [ ] Unexpected cash balance (trade failed silently)

---

## Manual Override Checklist

Before re-enabling trading after a halt:

1. Identify root cause of drawdown (market-wide vs strategy-specific)
2. Check regime state: SPY vs 200MA, VIX level
3. Review all open positions for thesis validity
4. Confirm circuit breaker limit wasn't a false positive (data error, split-adjusted price gap)
5. If strategy-specific: re-run last 60 days of backtest with updated data to confirm no regime break
6. Re-enable with 50% capital for first 5 trading days after halt

---

## Per-Strategy Risk Summary

| Strategy | Live Status | Daily Limit | Max DD | Notes |
|----------|-------------|-------------|--------|-------|
| H026 ETF rotation | Paper active | -5% | -12.5% | Monthly rebalance — daily limit rarely binding |
| H174 PEAD | Paper active | -3% | Per-trade 2% | Each trade independent; portfolio heat monitor relevant |
| H181 reversal | Paper active | -3% | Per-trade 2% | Intraday; needs 30-min polling |
| H301 200MA overlay | Pending approval | -5% | -12.4% | SPY 200MA kills entries in bear markets |
| H045 bonds | Paper active | -5% | ~-8% | BIL allocation absorbs most regime risk |

---

## See Also

- `paper-trading/live-graduation-criteria.md` — SPRT test, minimum trade counts
- `paper-trading/execution-quality.md` — slippage budgets, IS/VWAP benchmarks
- `paper-trading/tax-and-after-tax-returns.md` — HIFO lot selection, wash sale
- `backtesting/transaction-costs.md` — cost models for strategy simulation
