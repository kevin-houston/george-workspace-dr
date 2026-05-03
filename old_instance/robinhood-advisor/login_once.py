#!/usr/bin/env python3
"""
One-time Robinhood login to cache the session token.
Run this once from the host; the token is saved persistently so the
daily scheduled job never needs to prompt for MFA again.

Usage:
    groups/telegram_main/robinhood-advisor/venv/bin/python \
        groups/telegram_main/robinhood-advisor/login_once.py
"""

import sys
from pathlib import Path

# Add advisor dir to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import os
import robin_stocks.robinhood as rh

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

username = os.getenv("ROBINHOOD_USERNAME")
password = os.getenv("ROBINHOOD_PASSWORD")

if not username or not password:
    print("ERROR: ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD must be set in .env")
    sys.exit(1)

print(f"Logging in as {username}...")
print("If prompted for MFA code, enter the 6-digit code from your authenticator app.\n")

try:
    login = rh.login(username, password, pickle_path=str(DATA_DIR))
    print("\n✅ Login successful! Session token cached at:")
    print(f"   {DATA_DIR}/robinhood.pickle")
    print("\nThe daily portfolio analysis job will now use this token automatically.")
    print("You won't need to log in again unless the token expires (~24h by default).")

    # Quick sanity check
    holdings = rh.account.build_holdings()
    print(f"\nCurrent holdings ({len(holdings)} positions):")
    for sym, data in sorted(holdings.items()):
        qty = float(data['quantity'])
        price = float(data['price'])
        equity = float(data['equity'])
        pct = float(data['percent_change'])
        print(f"  {sym:<6} {qty:>8.2f} shares  ${price:>8.2f}  equity=${equity:>8.2f}  {pct:+.1f}%")

    rh.logout()

except Exception as e:
    print(f"\n❌ Login failed: {e}")
    sys.exit(1)
