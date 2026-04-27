"""Minimal Massive.com API client using the free-tier endpoints."""

import os
import requests
from datetime import date, timedelta

BASE = "https://api.massive.com"
KEY = os.environ["MASSIVE_KEY"]
HEADERS = {"Authorization": f"Bearer {KEY}"}


def get_spy_price() -> float | None:
    """Return the most recent available SPY close price (delayed)."""
    today = date.today()
    for days_back in range(7):
        d = today - timedelta(days=days_back)
        end = d.isoformat()
        start = (d - timedelta(days=1)).isoformat()
        r = requests.get(
            f"{BASE}/v2/aggs/ticker/SPY/range/1/day/{start}/{end}",
            headers=HEADERS, timeout=10
        )
        data = r.json()
        if data.get("resultsCount", 0) > 0:
            return data["results"][-1]["c"]
    return None


def find_option_ticker(underlying: str, expiry: date, right: str, strike: float) -> str | None:
    """Return the OCC ticker for the given contract, or None if not found."""
    strike_int = int(round(strike * 1000))
    ticker = f"O:{underlying}{expiry.strftime('%y%m%d')}{right[0].upper()}{strike_int:08d}"
    # Verify it exists in the reference
    r = requests.get(
        f"{BASE}/v3/reference/options/contracts",
        params={
            "underlying_ticker": underlying,
            "expiration_date": expiry.isoformat(),
            "contract_type": "call" if right.upper() == "C" else "put",
            "strike_price": strike,
            "limit": 1,
        },
        headers=HEADERS, timeout=10
    )
    results = r.json().get("results", [])
    return results[0]["ticker"] if results else ticker  # fall back to constructed


def find_nearest_contracts(underlying: str, expiry: date, right: str,
                           target_strike: float, n: int = 3) -> list[dict]:
    """Return n contracts nearest to target_strike for given expiry/right."""
    r = requests.get(
        f"{BASE}/v3/reference/options/contracts",
        params={
            "underlying_ticker": underlying,
            "expiration_date": expiry.isoformat(),
            "contract_type": "call" if right.upper() == "C" else "put",
            "strike_price.gte": target_strike - 20,
            "strike_price.lte": target_strike + 20,
            "limit": 50,
            "sort": "strike_price",
        },
        headers=HEADERS, timeout=10
    )
    results = r.json().get("results", [])
    # Sort by distance from target
    results.sort(key=lambda x: abs(x["strike_price"] - target_strike))
    return results[:n]


def get_option_last_price(ticker: str) -> float | None:
    """Return last close price for an options contract, or None."""
    today = date.today()
    for days_back in range(5):
        d = today - timedelta(days=days_back)
        start = (d - timedelta(days=1)).isoformat()
        end = d.isoformat()
        r = requests.get(
            f"{BASE}/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
            headers=HEADERS, timeout=10
        )
        data = r.json()
        if data.get("resultsCount", 0) > 0:
            return data["results"][-1]["c"]
    return None
