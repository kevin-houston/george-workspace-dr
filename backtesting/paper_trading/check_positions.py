#!/usr/bin/env python3
"""
Check open paper positions and compute current BSM P&L.

Usage:
    python check_positions.py [--close ID --reason REASON]

Prints a table of all open iron condors with:
  - DTE remaining
  - Current SPY vs entry SPY
  - Current BSM value of the spread
  - P&L vs entry credit
  - Status (on-track / at-target / stop-hit)
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from massive_client import get_spy_price
from bsm import bsm

TRADES_FILE = Path(__file__).parent / "trades.json"
RISK_FREE = 0.044


def load_trades():
    if not TRADES_FILE.exists():
        return []
    return json.loads(TRADES_FILE.read_text())


def save_trades(trades):
    TRADES_FILE.write_text(json.dumps(trades, indent=2, default=str))


def condor_value(S, legs, T, r, sigma):
    """Current BSM value of the iron condor (cost to close)."""
    lp = bsm(S, legs["long_put"]["strike"], T, r, sigma, "P")
    sp = bsm(S, legs["short_put"]["strike"], T, r, sigma, "P")
    sc = bsm(S, legs["short_call"]["strike"], T, r, sigma, "C")
    lc = bsm(S, legs["long_call"]["strike"], T, r, sigma, "C")
    return sp - lp + sc - lc  # net credit value (positive = still have credit)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--close", type=str, default=None, help="Trade ID to close")
    parser.add_argument("--reason", type=str, default="manual", help="Close reason")
    args = parser.parse_args()

    trades = load_trades()
    open_trades = [t for t in trades if t["status"] == "open"]

    if not open_trades:
        print("No open positions.")
        return

    print("Fetching SPY price...")
    S = get_spy_price()
    if S is None:
        print("Could not get SPY price. Using last known.")
        S = open_trades[0]["spy_price_entry"]
    print(f"SPY: ${S:.2f}\n")

    today = date.today()
    header = f"{'ID':<25} {'EXP':<12} {'DTE':>4} {'SPY_e':>7} {'CREDIT':>8} {'CURR_VAL':>10} {'P&L':>8} {'P&L%':>6} STATUS"
    print(header)
    print("-" * len(header))

    changed = False
    for t in trades:
        if t["status"] != "open":
            continue

        expiry = date.fromisoformat(t["expiry"])
        dte = (expiry - today).days
        T = max(dte / 365.0, 0.001)
        sigma = t.get("vix_entry", 20.0) / 100.0

        curr_val = condor_value(S, t["legs"], T, RISK_FREE, sigma)
        pnl_per_contract = curr_val - t["net_credit"]  # negative = loss (we received less)
        # Actually: we received net_credit at entry. Current cost to close = -curr_val (debit).
        # P&L = credit_received - cost_to_close = net_credit - (-curr_val)...
        # Wait: curr_val is the current net value of the spread.
        # At entry: we received net_credit (positive). Current value curr_val.
        # P&L = net_credit - cost_to_close
        # cost_to_close = -curr_val when curr_val is positive (still a credit spread)
        # Hmm, let me think again.
        # We SOLD the condor for net_credit. Current mark = curr_val (what we'd receive if we closed now).
        # If curr_val < net_credit: spread has decayed, we profit (buy back cheaper).
        # P&L = net_credit - curr_val (when positive, we've made money)
        # Wait no: curr_val here is computed as sp - lp + sc - lc = net credit value.
        # At entry: net_credit = sp_entry - lp_entry + sc_entry - lc_entry.
        # At exit: cost_to_close = sp_curr - lp_curr + sc_curr - lc_curr = curr_val.
        # P&L per contract = net_credit - curr_val (positive = profit).
        pnl_per_contract = t["net_credit"] - curr_val
        pnl_total = pnl_per_contract * 100 * t["qty"]
        pnl_pct = pnl_per_contract / t["net_credit"] * 100 if t["net_credit"] > 0 else 0

        # Status check
        if curr_val >= t["stop_loss_credit"]:  # cost to close >= 2x credit
            status = "STOP-HIT"
        elif pnl_pct >= 50:
            status = "AT-TARGET"
        elif dte <= 21:
            status = "DTE-EXIT"
        elif dte <= 0:
            status = "EXPIRED"
        else:
            status = "open"

        if args.close and t["id"] == args.close:
            status = f"CLOSED:{args.reason}"

        if status not in ("open",) and t["status"] == "open":
            t["status"] = "closed"
            t["exit_reason"] = status
            t["exited"] = today.isoformat()
            t["pnl"] = round(pnl_total, 2)
            changed = True

        print(f"{t['id']:<25} {t['expiry']:<12} {dte:>4} "
              f"${t['spy_price_entry']:>6.1f} "
              f"${t['net_credit']:>7.2f} "
              f"${curr_val:>9.2f} "
              f"${pnl_total:>7.0f} "
              f"{pnl_pct:>5.1f}% "
              f"{status}")

    if changed:
        save_trades(trades)
        print("\nPositions updated in trades.json")


if __name__ == "__main__":
    main()
