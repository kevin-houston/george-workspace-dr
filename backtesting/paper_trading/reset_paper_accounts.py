#!/usr/bin/env python3
"""
Reset paper trading to per-strategy $5k architecture.

Closes all open Alpaca positions (market sell), then
resets strategy_accounts.json so every strategy starts fresh at $5k.

Usage:
    python3 reset_paper_accounts.py --dry-run   # preview only
    python3 reset_paper_accounts.py             # execute
"""

import argparse
import json
import os
import shutil
from datetime import datetime, date
from pathlib import Path

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _ra
_orig = _ra.HTTPAdapter.send
def _no_verify(self, r, **kw): kw["verify"] = False; return _orig(self, r, **kw)
_ra.HTTPAdapter.send = _no_verify

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, ClosePositionRequest
from alpaca.trading.enums import OrderSide, TimeInForce

PT_DIR = Path(__file__).parent
ACCOUNTS_FILE = PT_DIR / "strategy_accounts.json"

LEGACY_LOGS = [
    "h112_monthly_trades.json",
    "h112_ibs_trades.json",
    "pead_positions.json",
    "pead_closed.json",
    "pead_watchlist.json",
    "trades.json",
]


def get_client() -> TradingClient:
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    args = parser.parse_args()

    client = get_client()
    account = client.get_account()
    equity = float(account.equity)
    print(f"\nAlpaca paper account equity: ${equity:,.2f}")

    # ── 1. List and close all open positions ──────────────────────────────────
    positions = client.get_all_positions()
    print(f"\nOpen positions to close: {len(positions)}")
    for p in positions:
        print(f"  {p.symbol:<8} qty={float(p.qty):>10.4f}  mkt=${float(p.market_value):>10,.2f}")

    if not args.dry_run and positions:
        print("\nClosing all positions…")
        for p in positions:
            try:
                client.close_position(p.symbol)
                print(f"  ✓ closed {p.symbol}")
            except Exception as e:
                print(f"  ✗ {p.symbol}: {e}")
    elif args.dry_run and positions:
        print("\n[DRY RUN] would close all positions above")

    # ── 2. Archive legacy logs ────────────────────────────────────────────────
    archive_dir = PT_DIR / "archive" / f"reset_{date.today().isoformat()}"
    archived = []
    for fname in LEGACY_LOGS:
        fpath = PT_DIR / fname
        if fpath.exists():
            archived.append(fname)
    print(f"\nLegacy logs to archive: {archived}")

    if not args.dry_run and archived:
        archive_dir.mkdir(parents=True, exist_ok=True)
        for fname in archived:
            shutil.move(str(PT_DIR / fname), str(archive_dir / fname))
            print(f"  archived → archive/reset_{date.today().isoformat()}/{fname}")

    # ── 3. Reset strategy_accounts.json ───────────────────────────────────────
    print(f"\nResetting strategy_accounts.json…")
    if not args.dry_run:
        data = json.loads(ACCOUNTS_FILE.read_text())
        reset_time = datetime.now().isoformat()
        for sid, strat in data["strategies"].items():
            strat["cash"] = strat["start_equity"]
            strat["open_positions"] = {}
            strat["closed_trades"] = []
            strat["equity_history"] = []
            print(f"  ✓ {sid}: reset to ${strat['start_equity']:.0f}")
        data["initialized"] = date.today().isoformat()
        data["updated"] = reset_time
        ACCOUNTS_FILE.write_text(json.dumps(data, indent=2, default=str))
    else:
        data = json.loads(ACCOUNTS_FILE.read_text())
        for sid in data["strategies"]:
            print(f"  [DRY RUN] would reset {sid} to ${data['strategies'][sid]['start_equity']:.0f}")

    if args.dry_run:
        print("\n[DRY RUN] complete — no changes made. Run without --dry-run to execute.")
    else:
        print(f"\n✓ Reset complete. Each strategy starts at ${data['start_equity_per_strategy']:.0f}.")
        print("  Next scheduled runs will allocate fresh positions.")


if __name__ == "__main__":
    main()
