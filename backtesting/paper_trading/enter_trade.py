#!/usr/bin/env python3
"""
Enter a new iron condor paper trade.

Usage:
    python enter_trade.py [--dte 45] [--delta 0.16] [--wing 25] [--qty 1]

Workflow:
  1. Get current SPY price from Massive (delayed)
  2. Compute BSM 16-delta strikes for put spread + call spread
  3. Look up actual OCC tickers via Massive reference API
  4. Log trade to trades.json with entry prices (BSM model prices)
"""

import argparse
import json
import sys
import os
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from massive_client import get_spy_price, find_nearest_contracts, get_option_last_price
from bsm import bsm, delta as bsm_delta, strike_for_delta

TRADES_FILE = Path(__file__).parent / "trades.json"
RISK_FREE = 0.044  # approximate current 3mo T-bill


def find_friday(target_date: date) -> date:
    """Return nearest Friday on or after target_date."""
    days_until_friday = (4 - target_date.weekday()) % 7
    return target_date + timedelta(days=days_until_friday)


def nearest_5(x: float) -> float:
    return round(x / 5) * 5


def load_trades() -> list:
    if TRADES_FILE.exists():
        return json.loads(TRADES_FILE.read_text())
    return []


def save_trades(trades: list):
    TRADES_FILE.write_text(json.dumps(trades, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description="Enter iron condor paper trade")
    parser.add_argument("--dte", type=int, default=45, help="Days to expiration (default 45)")
    parser.add_argument("--delta", type=float, default=0.16, help="Short strike delta (default 0.16)")
    parser.add_argument("--wing", type=float, default=25, help="Wing width in $ (default 25)")
    parser.add_argument("--qty", type=int, default=1, help="Number of contracts (default 1)")
    parser.add_argument("--vix", type=float, default=None, help="Override VIX (auto-computes from BSM if not set)")
    args = parser.parse_args()

    # 1. Get current SPY price
    print("Fetching SPY price from Massive...")
    S = get_spy_price()
    if S is None:
        print("ERROR: Could not get SPY price from Massive API")
        sys.exit(1)
    print(f"  SPY: ${S:.2f}")

    # 2. Find expiry (nearest Friday at target DTE)
    expiry = find_friday(date.today() + timedelta(days=args.dte))
    T = (expiry - date.today()).days / 365.0
    print(f"  Expiry: {expiry} ({(expiry - date.today()).days} DTE)")

    # 3. Compute BSM strikes at target delta
    vix = args.vix if args.vix else 20.0  # default 20 if not provided
    sigma = vix / 100.0
    r = RISK_FREE

    short_put_strike = nearest_5(strike_for_delta(S, T, r, sigma, args.delta, "P"))
    short_call_strike = nearest_5(strike_for_delta(S, T, r, sigma, args.delta, "C"))
    long_put_strike = short_put_strike - args.wing
    long_call_strike = short_call_strike + args.wing

    print(f"\nIron condor strikes (VIX={vix}, delta={args.delta}):")
    print(f"  Long put:   ${long_put_strike:.0f}")
    print(f"  Short put:  ${short_put_strike:.0f}  (delta ~{args.delta})")
    print(f"  Short call: ${short_call_strike:.0f}  (delta ~{args.delta})")
    print(f"  Long call:  ${long_call_strike:.0f}")

    # 4. BSM model prices
    lp_price = bsm(S, long_put_strike, T, r, sigma, "P")
    sp_price = bsm(S, short_put_strike, T, r, sigma, "P")
    sc_price = bsm(S, short_call_strike, T, r, sigma, "C")
    lc_price = bsm(S, long_call_strike, T, r, sigma, "C")
    net_credit = (sp_price - lp_price + sc_price - lc_price)
    print(f"\nBSM model prices:")
    print(f"  Long put:   ${lp_price:.2f}")
    print(f"  Short put:  ${sp_price:.2f}")
    print(f"  Short call: ${sc_price:.2f}")
    print(f"  Long call:  ${lc_price:.2f}")
    print(f"  Net credit: ${net_credit:.2f} x 100 = ${net_credit*100:.0f} per contract")

    # 5. Try to get real market prices from Massive
    print("\nLooking up market prices from Massive...")

    def get_market_price(underlying, exp, right, strike, model_price):
        contracts = find_nearest_contracts(underlying, exp, right, strike, n=1)
        if not contracts:
            return model_price, f"model (no contract found)", None
        ticker = contracts[0]["ticker"]
        actual_strike = contracts[0]["strike_price"]
        mkt = get_option_last_price(ticker)
        if mkt:
            return mkt, f"market ({ticker})", ticker
        return model_price, f"model (no recent trade for {ticker})", ticker

    lp_actual, lp_src, lp_ticker = get_market_price("SPY", expiry, "P", long_put_strike, lp_price)
    sp_actual, sp_src, sp_ticker = get_market_price("SPY", expiry, "P", short_put_strike, sp_price)
    sc_actual, sc_src, sc_ticker = get_market_price("SPY", expiry, "C", short_call_strike, sc_price)
    lc_actual, lc_src, lc_ticker = get_market_price("SPY", expiry, "C", long_call_strike, lc_price)
    net_credit_actual = (sp_actual - lp_actual + sc_actual - lc_actual)

    print(f"  Long put:   ${lp_actual:.2f} ({lp_src})")
    print(f"  Short put:  ${sp_actual:.2f} ({sp_src})")
    print(f"  Short call: ${sc_actual:.2f} ({sc_src})")
    print(f"  Long call:  ${lc_actual:.2f} ({lc_src})")
    print(f"  Net credit: ${net_credit_actual:.2f} x 100 = ${net_credit_actual*100:.0f} per contract")

    # 6. Build trade record
    trade = {
        "id": f"IC-{date.today().isoformat()}-{len(load_trades())+1:03d}",
        "strategy": "iron_condor",
        "status": "open",
        "entered": date.today().isoformat(),
        "expiry": expiry.isoformat(),
        "dte_entry": (expiry - date.today()).days,
        "underlying": "SPY",
        "spy_price_entry": S,
        "vix_entry": vix,
        "qty": args.qty,
        "legs": {
            "long_put":   {"strike": long_put_strike,   "ticker": lp_ticker, "entry_price": lp_actual},
            "short_put":  {"strike": short_put_strike,  "ticker": sp_ticker, "entry_price": sp_actual},
            "short_call": {"strike": short_call_strike, "ticker": sc_ticker, "entry_price": sc_actual},
            "long_call":  {"strike": long_call_strike,  "ticker": lc_ticker, "entry_price": lc_actual},
        },
        "net_credit": net_credit_actual,
        "max_profit": net_credit_actual * 100 * args.qty,
        "max_loss": (args.wing - net_credit_actual) * 100 * args.qty,
        "target_profit": net_credit_actual * 0.5,
        "stop_loss_credit": net_credit_actual * 2.0,
        "pnl": 0.0,
        "exit_reason": None,
        "exited": None,
    }

    # 7. Save
    trades = load_trades()
    trades.append(trade)
    save_trades(trades)

    print(f"\n✓ Trade logged: {trade['id']}")
    print(f"  Max profit: ${trade['max_profit']:.0f}")
    print(f"  Max loss:   ${trade['max_loss']:.0f}")
    print(f"  Target:     ${trade['target_profit']*100:.0f} (50% of credit)")
    print(f"  Stop loss:  ${trade['stop_loss_credit']*100:.0f} (debit = 2x credit)")


if __name__ == "__main__":
    main()
