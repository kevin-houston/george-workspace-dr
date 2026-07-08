"""
Shared strategy equity tracker for per-strategy paper trading.

Each strategy maintains its own virtual $5k account independent of the
Alpaca account balance. Orders are still submitted to Alpaca for realistic
fills, but P&L and position tracking live here.
"""

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional

ACCOUNTS_FILE = Path(__file__).parent / "strategy_accounts.json"


# ── Persistence ──────────────────────────────────────────────────────────────

def load() -> dict:
    return json.loads(ACCOUNTS_FILE.read_text())


def save(data: dict):
    data["updated"] = datetime.now().isoformat()
    ACCOUNTS_FILE.write_text(json.dumps(data, indent=2, default=str))


# ── Reads ─────────────────────────────────────────────────────────────────────

def get_cash(strategy_id: str) -> float:
    return load()["strategies"][strategy_id]["cash"]


def get_open_positions(strategy_id: str) -> dict:
    return load()["strategies"][strategy_id]["open_positions"]


def get_open_qty(strategy_id: str, symbol: str) -> float:
    pos = load()["strategies"][strategy_id]["open_positions"].get(symbol)
    return pos["qty"] if pos else 0.0


def is_flat(strategy_id: str, symbol: str) -> bool:
    return symbol not in load()["strategies"][strategy_id]["open_positions"]


def current_equity(strategy_id: str, prices: Optional[dict] = None) -> float:
    """Cash + open positions marked at prices (or entry price if prices=None)."""
    data = load()["strategies"][strategy_id]
    mkt = sum(
        pos["qty"] * (prices or {}).get(sym, pos["entry_price"])
        for sym, pos in data["open_positions"].items()
    )
    return data["cash"] + mkt


def get_equity_history(strategy_id: str) -> list:
    return load()["strategies"][strategy_id]["equity_history"]


def get_closed_trades(strategy_id: str) -> list:
    return load()["strategies"][strategy_id]["closed_trades"]


def summary(strategy_id: str, prices: Optional[dict] = None) -> dict:
    data = load()["strategies"]
    s = data[strategy_id]
    eq = current_equity(strategy_id, prices)
    closed = s["closed_trades"]
    wins = [t for t in closed if t["return"] > 0]
    return {
        "id":            strategy_id,
        "name":          s["name"],
        "equity":        eq,
        "start_equity":  s["start_equity"],
        "total_return":  (eq - s["start_equity"]) / s["start_equity"],
        "cash":          s["cash"],
        "n_open":        len(s["open_positions"]),
        "n_closed":      len(closed),
        "win_rate":      len(wins) / len(closed) if closed else None,
        "avg_return":    sum(t["return"] for t in closed) / len(closed) if closed else None,
        "backtest_sharpe": s.get("backtest_sharpe"),
        "backtest_win_rate": s.get("backtest_win_rate"),
        "status":        s["status"],
        "equity_history": s["equity_history"],
    }


def live_sharpe(strategy_id: str) -> Optional[float]:
    hist = get_equity_history(strategy_id)
    if len(hist) < 5:
        return None
    vals = [h["equity"] for h in hist]
    rets = [(vals[i] - vals[i-1]) / vals[i-1] for i in range(1, len(vals))]
    n = len(rets)
    mu = sum(rets) / n
    var = sum((r - mu)**2 for r in rets) / max(n-1, 1)
    sd = math.sqrt(var) if var > 0 else 0
    return mu / sd * math.sqrt(252) if sd > 0 else None


# ── Writes ────────────────────────────────────────────────────────────────────

def open_buy(strategy_id: str, symbol: str, qty: float, price: float,
             order_id: str = "", note: str = ""):
    """Record a new long entry. Deducts cost from cash. Accumulates if position exists."""
    data = load()
    s = data["strategies"][strategy_id]
    cost = qty * price
    s["cash"] = round(s["cash"] - cost, 4)
    existing = s["open_positions"].get(symbol)
    if existing:
        # Accumulate: weighted-average entry price, summed qty and cost_basis
        new_qty = round(existing["qty"] + qty, 6)
        new_cost = round(existing["cost_basis"] + cost, 4)
        s["open_positions"][symbol] = {
            "qty":         new_qty,
            "entry_price": round(new_cost / new_qty, 4),
            "entry_date":  existing["entry_date"],
            "cost_basis":  new_cost,
            "order_id":    order_id or existing.get("order_id", ""),
            "note":        note or existing.get("note", ""),
        }
    else:
        s["open_positions"][symbol] = {
            "qty":         round(qty, 6),
            "entry_price": round(price, 4),
            "entry_date":  date.today().isoformat(),
            "cost_basis":  round(cost, 4),
            "order_id":    order_id,
            "note":        note,
        }
    save(data)


def partial_sell(strategy_id: str, symbol: str, qty: float, price: float,
                 order_id: str = "", reason: str = ""):
    """Record a partial position reduction without closing it. Adds proceeds to cash."""
    data = load()
    s = data["strategies"][strategy_id]
    pos = s["open_positions"].get(symbol)
    if pos is None:
        return
    proceeds = qty * price
    s["cash"] = round(s["cash"] + proceeds, 4)
    new_qty = round(pos["qty"] - qty, 6)
    # Reduce cost_basis proportionally
    new_cost = round(pos["cost_basis"] * (new_qty / pos["qty"]) if pos["qty"] > 0 else 0, 4)
    if new_qty <= 0:
        s["open_positions"].pop(symbol)
    else:
        s["open_positions"][symbol] = {
            **pos,
            "qty":        new_qty,
            "cost_basis": new_cost,
        }
    save(data)


def close_sell(strategy_id: str, symbol: str, price: float,
               order_id: str = "", reason: str = "") -> Optional[dict]:
    """Record a position close. Adds proceeds to cash. Returns trade record or None."""
    data = load()
    s = data["strategies"][strategy_id]
    pos = s["open_positions"].pop(symbol, None)
    if pos is None:
        return None
    proceeds = pos["qty"] * price
    pnl = proceeds - pos["cost_basis"]
    ret = pnl / pos["cost_basis"] if pos["cost_basis"] > 0 else 0.0
    s["cash"] = round(s["cash"] + proceeds, 4)
    trade = {
        "symbol":      symbol,
        "entry_date":  pos["entry_date"],
        "exit_date":   date.today().isoformat(),
        "entry_price": pos["entry_price"],
        "exit_price":  round(price, 4),
        "qty":         pos["qty"],
        "pnl":         round(pnl, 2),
        "return":      round(ret, 6),
        "reason":      reason,
        "order_id":    order_id,
    }
    s["closed_trades"].append(trade)
    save(data)
    return trade


def snapshot_equity(strategy_id: str, prices: Optional[dict] = None) -> float:
    """Record today's equity to history. Returns current equity."""
    data = load()
    s = data["strategies"][strategy_id]
    mkt = sum(
        pos["qty"] * (prices or {}).get(sym, pos["entry_price"])
        for sym, pos in s["open_positions"].items()
    )
    eq = round(s["cash"] + mkt, 2)
    today = date.today().isoformat()
    hist = s["equity_history"]
    if hist and hist[-1]["date"] == today:
        hist[-1]["equity"] = eq
    else:
        hist.append({"date": today, "equity": eq})
    save(data)
    return eq


def add_strategy(strategy_id: str, name: str, description: str,
                 backtest_sharpe: Optional[float] = None,
                 backtest_oos_period: str = "",
                 script: str = ""):
    """Register a new strategy with a fresh $5k account."""
    data = load()
    start = data["start_equity_per_strategy"]
    data["strategies"][strategy_id] = {
        "id": strategy_id, "name": name, "description": description,
        "backtest_sharpe": backtest_sharpe,
        "backtest_oos_period": backtest_oos_period,
        "script": script,
        "start_equity": start, "cash": start,
        "open_positions": {}, "closed_trades": [],
        "equity_history": [], "status": "active",
    }
    save(data)
    print(f"  Added strategy {strategy_id}: ${start:.0f} cash")
