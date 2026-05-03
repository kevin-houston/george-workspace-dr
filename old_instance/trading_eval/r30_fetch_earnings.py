"""
R30: Fetch earnings data from Alpha Vantage for PEAD universe.
Caches to /workspace/group/trading_eval/cache/earnings/{ticker}_earnings.json
Resume-safe: skips if cache exists.
Rate limit: 5 req/min → sleep 12s between calls.
"""

import requests
import json
import time
import os

API_KEY = "FSFO6925L9TF21C4"
CACHE_DIR = "/workspace/group/trading_eval/cache/earnings"
os.makedirs(CACHE_DIR, exist_ok=True)

UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "JPM", "JNJ", "XOM", "WMT",
    "BAC", "PG", "UNH", "HD", "CVX", "LLY", "MRK", "ABBV", "PFE", "KO",
    "PEP", "TMO", "COST", "MCD", "ACN", "ABT", "DHR", "NEE", "LIN", "HON"
]

fetched = 0
skipped = 0
failed = []

for ticker in UNIVERSE:
    cache_path = os.path.join(CACHE_DIR, f"{ticker}_earnings.json")
    if os.path.exists(cache_path):
        print(f"[SKIP] {ticker} — cache exists")
        skipped += 1
        continue

    url = f"https://www.alphavantage.co/query?function=EARNINGS&symbol={ticker}&apikey={API_KEY}"
    print(f"[FETCH] {ticker}...", end=" ", flush=True)

    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()

        # Check for API limit hit
        if "Note" in data or "Information" in data:
            msg = data.get("Note", data.get("Information", ""))
            print(f"RATE LIMITED: {msg}")
            failed.append(ticker)
            print(f"\nDaily limit hit after {fetched} fetches. Remaining: {UNIVERSE[UNIVERSE.index(ticker):]}")
            break

        if "quarterlyEarnings" not in data:
            print(f"No quarterly earnings in response. Keys: {list(data.keys())}")
            failed.append(ticker)
        else:
            with open(cache_path, "w") as f:
                json.dump(data, f)
            n = len(data.get("quarterlyEarnings", []))
            print(f"OK ({n} quarters)")
            fetched += 1
    except Exception as e:
        print(f"ERROR: {e}")
        failed.append(ticker)

    # Rate limit: 5 req/min
    if fetched < len(UNIVERSE):
        time.sleep(12)

print(f"\n=== Done: {fetched} fetched, {skipped} skipped, {len(failed)} failed ===")
if failed:
    print(f"Failed/missing: {failed}")
