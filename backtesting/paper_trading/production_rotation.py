#!/usr/bin/env python3
"""
Production Portfolio — Monthly Rotation Paper Trader
H041a (22%) + H026 (27%) + H045 (21%)

Signal for all three: rank(12m_momentum) + rank(inv_6m_vol)
Rebalances on the first trading day of each month.
IBS strategies (XLK 20%, SMH 8%, IGV 2%) are handled by h112_daily_ibs.py — NOT here.

State: production_rotation_state.json
Trades log: production_rotation_trades.json

Usage:
    python3 production_rotation.py             # normal run (skips if already ran this month)
    python3 production_rotation.py --force     # force rebalance regardless of last-run date
    python3 production_rotation.py --dry-run   # show signals and orders, submit nothing
    python3 production_rotation.py --status    # show current holdings and P&L only
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# ── Strategy definitions ─────────────────────────────────────────────────────

STRATEGIES = {
    "H041a": {
        "weight":   0.22,
        "universe": ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"],
        "top_n":    2,
        "label":    "Multi-Asset Rotation (7-asset, top-2)",
    },
    "H026": {
        "weight":   0.27,
        "universe": ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        "top_n":    3,
        "label":    "Sector ETF Rotation (11-sector, top-3)",
    },
    "H045": {
        "weight":   0.21,
        "universe": ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"],
        "top_n":    2,
        "label":    "Bond ETF Rotation (7-bond, top-2)",
    },
}

# IBS symbols — these are managed by h112_daily_ibs.py, not here.
# We track them so we don't accidentally exit IBS positions.
IBS_SYMBOLS = {"XLK", "SMH", "IGV"}

STATE_FILE  = Path(__file__).parent / "production_rotation_state.json"
TRADES_FILE = Path(__file__).parent / "production_rotation_trades.json"
MIN_ORDER_USD = 5.0   # skip orders smaller than this


# ── Alpaca helpers ────────────────────────────────────────────────────────────

def get_client() -> TradingClient:
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True,
    )


def get_equity(client: TradingClient) -> float:
    return float(client.get_account().equity)


def get_all_positions(client: TradingClient) -> dict[str, dict]:
    """Returns {symbol: {qty, market_value, avg_cost, unrealized_pl}}"""
    out = {}
    try:
        for p in client.get_all_positions():
            out[p.symbol] = {
                "qty":           float(p.qty),
                "market_value":  float(p.market_value),
                "avg_cost":      float(p.avg_entry_price),
                "unrealized_pl": float(p.unrealized_pl),
            }
    except Exception as e:
        print(f"  Warning: could not fetch positions: {e}")
    return out


# ── Signal computation ────────────────────────────────────────────────────────

def compute_signal(universe: list) -> tuple[pd.Series | None, pd.Series | None]:
    """
    Download ~15 months of daily prices, compute monthly resamples,
    return (score_series, latest_prices).
    score = rank(12m_mom) + rank(inv_6m_vol), higher = better.
    """
    try:
        raw = yf.download(universe, period="450d", auto_adjust=True, progress=False)
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        closes = closes.dropna(how="all")
    except Exception as e:
        print(f"  Signal fetch failed: {e}")
        return None, None

    if len(closes) < 250:
        print(f"  Insufficient price history ({len(closes)} days)")
        return None, None

    monthly = closes.resample("ME").last()
    monthly_rets = closes.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)

    if len(monthly) < 14:
        print(f"  Insufficient monthly bars ({len(monthly)})")
        return None, None

    # 12-month momentum (skip last 1 month — standard Jegadeesh-Titman)
    mom_12 = (monthly.iloc[-2] / monthly.iloc[-14] - 1).dropna()
    # 6-month realised vol
    vol_6  = monthly_rets.iloc[-7:-1].std().dropna() * np.sqrt(12)

    common = mom_12.index.intersection(vol_6.index)
    if len(common) < 2:
        print(f"  Not enough common tickers for signal ({len(common)})")
        return None, None

    score = mom_12[common].rank() + vol_6[common].rank(ascending=False)
    latest_prices = closes.iloc[-1]
    return score, latest_prices


def select_holdings(strategy_name: str, config: dict) -> tuple[list[str], dict] | tuple[None, None]:
    """Returns (top_tickers, signal_detail) or (None, None) on failure."""
    score, prices = compute_signal(config["universe"])
    if score is None:
        return None, None
    top = list(score.nlargest(config["top_n"]).index)
    detail = {
        sym: {
            "score":    round(float(score.get(sym, float("nan"))), 4),
            "selected": sym in top,
            "price":    round(float(prices.get(sym, float("nan"))), 4),
        }
        for sym in config["universe"]
        if sym in score.index
    }
    return top, detail


# ── State management ──────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_rebalance": None, "holdings": {}}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def already_ran_this_month(state: dict) -> bool:
    last = state.get("last_rebalance")
    if not last:
        return False
    last_dt = date.fromisoformat(last)
    today   = date.today()
    return last_dt.year == today.year and last_dt.month == today.month


def append_trade(trade: dict):
    log = json.loads(TRADES_FILE.read_text()) if TRADES_FILE.exists() else []
    log.append(trade)
    TRADES_FILE.write_text(json.dumps(log, indent=2, default=str))


# ── Order execution ───────────────────────────────────────────────────────────

def submit_order(
    client: TradingClient,
    symbol: str,
    qty: float,
    side: OrderSide,
    dry_run: bool,
) -> str | None:
    if dry_run:
        print(f"    [DRY RUN] would {side.value} {qty:.4f} {symbol}")
        return "dry-run"
    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=TimeInForce.DAY,
        ))
        return str(order.id)
    except Exception as e:
        print(f"    ✗ order failed: {e}")
        return None


# ── Status display ────────────────────────────────────────────────────────────

def show_status(client: TradingClient, state: dict):
    equity   = get_equity(client)
    positions = get_all_positions(client)
    holdings  = state.get("holdings", {})

    print(f"\n{'═'*60}")
    print(f"  Production Rotation — Status")
    print(f"  Account equity: ${equity:,.2f}")
    print(f"  Last rebalance: {state.get('last_rebalance', 'never')}")
    print(f"{'═'*60}")

    for name, config in STRATEGIES.items():
        held = holdings.get(name, {}).get("holdings", [])
        alloc = equity * config["weight"]
        print(f"\n  {name} ({config['weight']:.0%} = ${alloc:,.0f}): {config['label']}")
        if not held:
            print(f"    No recorded holdings — not yet rebalanced")
            continue
        for sym in held:
            pos = positions.get(sym)
            if pos:
                print(f"    {sym:<6}  {pos['qty']:.4f} sh  MV ${pos['market_value']:,.0f}  "
                      f"P&L {pos['unrealized_pl']:+,.0f}")
            else:
                print(f"    {sym:<6}  (no Alpaca position found)")


# ── Main rebalance ────────────────────────────────────────────────────────────

def rebalance(dry_run: bool = False, force: bool = False):
    today  = date.today().isoformat()
    state  = load_state()
    client = get_client()
    equity = get_equity(client)

    print(f"\n{'═'*60}")
    print(f"  Production Rotation Rebalance — {today}")
    print(f"  Account equity: ${equity:,.2f}")
    print(f"  Last rebalance: {state.get('last_rebalance', 'never')}")
    print(f"{'═'*60}")

    if not force and already_ran_this_month(state):
        print(f"\n  Already rebalanced this month ({state['last_rebalance']}). "
              f"Use --force to override.")
        return

    current_positions = get_all_positions(client)
    prev_holdings     = state.get("holdings", {})

    # Collect all symbols that were previously rotation-held
    prev_rotation_symbols: set[str] = set()
    for h in prev_holdings.values():
        prev_rotation_symbols.update(h.get("holdings", []))

    # ── Compute new signals ───────────────────────────────────────────────────
    new_holdings: dict[str, dict] = {}
    all_target_symbols: set[str] = set()
    target_values: dict[str, float] = {}   # symbol -> total target USD value

    for name, config in STRATEGIES.items():
        print(f"\n  Computing signal for {name}…")
        top, detail = select_holdings(name, config)
        if top is None:
            print(f"  ✗ Signal failed — keeping prior holdings")
            top    = prev_holdings.get(name, {}).get("holdings", [])
            detail = {}

        alloc   = equity * config["weight"]
        per_pos = alloc / config["top_n"] if top else 0.0

        print(f"  {name} → top picks: {top}")
        if detail:
            for sym, d in sorted(detail.items(), key=lambda x: -x[1]["score"]):
                flag = " ← SELECTED" if d["selected"] else ""
                print(f"    {sym:<6}  score={d['score']:.2f}  price=${d['price']:.2f}{flag}")

        new_holdings[name] = {
            "holdings":  top,
            "alloc_usd": round(alloc, 2),
            "per_pos":   round(per_pos, 2),
            "detail":    detail,
        }

        for sym in top:
            all_target_symbols.add(sym)
            target_values[sym] = target_values.get(sym, 0) + per_pos

    # ── Determine exits (was in rotation, no longer selected) ────────────────
    exits = prev_rotation_symbols - all_target_symbols - IBS_SYMBOLS
    print(f"\n  Exits (no longer selected): {sorted(exits) or 'none'}")

    # ── Print order plan ──────────────────────────────────────────────────────
    print(f"\n  Target positions:")
    for sym, target_val in sorted(target_values.items()):
        pos = current_positions.get(sym, {})
        # Subtract any IBS-managed portion if symbol overlaps
        ibs_mv  = pos.get("market_value", 0) if sym in IBS_SYMBOLS else 0
        curr_mv = pos.get("market_value", 0) - ibs_mv
        diff    = target_val - curr_mv
        print(f"    {sym:<6}  target=${target_val:,.0f}  curr_rotation=${curr_mv:,.0f}  diff={diff:+,.0f}")

    # ── Submit exits ──────────────────────────────────────────────────────────
    trades = []

    for sym in sorted(exits):
        if sym in IBS_SYMBOLS:
            continue
        pos = current_positions.get(sym)
        if not pos or pos["qty"] <= 0:
            continue
        qty = pos["qty"]
        print(f"\n  EXIT {sym}: sell {qty:.4f} sh (rotation exit)")
        order_id = submit_order(client, sym, qty, OrderSide.SELL, dry_run)
        if order_id:
            trades.append({
                "date": today, "symbol": sym, "action": "SELL",
                "qty": qty, "reason": "rotation_exit", "order_id": order_id,
            })

    # ── Submit buys/adjustments ───────────────────────────────────────────────
    for sym, target_val in sorted(target_values.items()):
        pos     = current_positions.get(sym, {})
        ibs_mv  = pos.get("market_value", 0) if sym in IBS_SYMBOLS else 0
        curr_mv = pos.get("market_value", 0) - ibs_mv
        diff    = target_val - curr_mv

        if abs(diff) < MIN_ORDER_USD:
            print(f"\n  {sym}: change ${diff:+,.0f} below threshold, skipping")
            continue

        # Estimate price from positions or yfinance
        if pos.get("avg_cost"):
            price = pos["avg_cost"]
        else:
            try:
                raw   = yf.download(sym, period="2d", auto_adjust=True, progress=False)
                price = float(raw["Close"].iloc[-1]) if not isinstance(raw.columns, pd.MultiIndex) else float(raw["Close"][sym].iloc[-1])
            except Exception:
                print(f"\n  {sym}: price fetch failed, skipping")
                continue

        qty  = abs(round(diff / price, 4))
        side = OrderSide.BUY if diff > 0 else OrderSide.SELL

        print(f"\n  {side.value} {qty:.4f} {sym} @ ~${price:.2f} "
              f"(${abs(diff):,.0f}) — rotation target")

        order_id = submit_order(client, sym, qty, side, dry_run)
        if order_id:
            trades.append({
                "date":     today,
                "symbol":   sym,
                "action":   side.value,
                "qty":      qty,
                "est_price": round(price, 4),
                "est_value": round(abs(diff), 2),
                "order_id": order_id,
            })

    # ── Persist ───────────────────────────────────────────────────────────────
    if not dry_run:
        state.update({
            "last_rebalance": today,
            "equity_at_rebalance": round(equity, 2),
            "holdings": new_holdings,
        })
        save_state(state)

        for t in trades:
            append_trade(t)

        print(f"\n✓ Rebalance complete — {len(trades)} orders submitted")
        print(f"  Holdings: {', '.join(sorted(all_target_symbols))}")
    else:
        print(f"\n[DRY RUN] {len(trades)} orders would be submitted")

    return trades


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force",   action="store_true")
    parser.add_argument("--status",  action="store_true")
    args = parser.parse_args()

    client = get_client()

    if args.status:
        show_status(client, load_state())
        return

    rebalance(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
