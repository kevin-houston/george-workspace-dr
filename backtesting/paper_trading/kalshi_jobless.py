#!/usr/bin/env python3
"""
Kalshi Initial Jobless Claims Strategy
=======================================
Builds a 1-week-ahead initial claims forecast using FRED data + AR(2),
then trades Kalshi KXJOBLESSCLAIMS contracts when our model diverges from
market pricing by more than THRESHOLD_EDGE (default 3pp).

Released every Thursday at 8:30 AM ET. Markets open the prior week.
Run before close of betting (typically Thursday pre-open or Wednesday evening).

Credentials required (set as environment variables):
    KALSHI_API_KEY_ID      — from Kalshi dashboard → API Keys
    KALSHI_PRIVATE_KEY_PEM — RSA-PSS private key PEM contents
    FRED_API_KEY           — from fred.stlouisfed.org/docs/api/api_key.html

Usage:
    python3 kalshi_jobless.py                  # full run
    python3 kalshi_jobless.py --dry-run        # signal + orders, no submission
    python3 kalshi_jobless.py --status         # show open Kalshi markets
    python3 kalshi_jobless.py --backfill-check # validate FRED data freshness
"""

import argparse
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from fredapi import Fred
from scipy.stats import norm
from statsmodels.tsa.arima.model import ARIMA

try:
    from kalshi_py import KalshiAuthenticatedClient
    KALSHI_SDK_AVAILABLE = True
except ImportError:
    KALSHI_SDK_AVAILABLE = False

LOG_FILE = Path(__file__).parent / "kalshi_jobless_trades.json"

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_URL       = "https://api.elections.kalshi.com/trade-api/v2"

BANKROLL       = 5_000    # USD allocated to this strategy
THRESHOLD_EDGE = 0.03     # min edge (3pp) to place a trade
MIN_CONTRACTS  = 5
MAX_CONTRACTS  = 500
KELLY_FRACTION = 0.25     # quarter-Kelly

SERIES_TICKER  = "KXJOBLESSCLAIMS"

# Model params — AR(2) on weekly ICSA in thousands
AR_ORDER       = (2, 0, 0)   # AR(2) on level; claims are I(0) in practice
AR_WINDOW      = 52          # 1 year of weekly data for fitting
MA4_BLEND      = 0.25        # blend 25% toward 4-week MA as anchor


# ── Credentials ───────────────────────────────────────────────────────────────

def load_credentials() -> tuple[str, str]:
    key_id = os.environ.get("KALSHI_API_KEY_ID") or os.environ.get("KALSHI_API_KEY", "")
    if not key_id:
        raise EnvironmentError(
            "KALSHI_API_KEY_ID (or KALSHI_API_KEY) not set.\n"
            "  1. Go to kalshi.com → Account & Security → API Keys\n"
            "  2. Generate RSA key pair (2048-bit), save private key immediately\n"
            "  3. export KALSHI_API_KEY_ID=<your-key-id>\n"
            "  4. export KALSHI_PRIVATE_KEY_PEM='<pem-contents>'"
        )
    pem = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
    if not pem:
        pem_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
        if pem_path and Path(pem_path).exists():
            pem = Path(pem_path).read_text()
        else:
            raise EnvironmentError("KALSHI_PRIVATE_KEY_PEM not set.")
    return key_id, pem


# ── FRED data + forecasting ───────────────────────────────────────────────────

def get_claims_data(fred: Fred) -> dict:
    """Pull initial claims and 4-week MA from FRED. Units: thousands."""
    icsa   = fred.get_series("ICSA")    # Initial claims SA, thousands
    ic4w   = fred.get_series("IC4WSA")  # 4-week MA SA, thousands
    return {"icsa": icsa, "ic4w": ic4w}


def build_ar_forecast(icsa: pd.Series) -> tuple[float, float]:
    """
    Fit AR(2) on last AR_WINDOW weeks of initial claims (level, thousands).
    Returns (forecast_mean_thousands, forecast_std_error_thousands).
    """
    series = icsa.dropna()
    if len(series) < AR_WINDOW + 5:
        raise ValueError(f"Insufficient claims history: {len(series)} weeks")

    recent = series.iloc[-AR_WINDOW:]
    model  = ARIMA(recent, order=AR_ORDER)
    fit    = model.fit()
    fc     = fit.get_forecast(steps=1)
    mean   = float(fc.predicted_mean.iloc[0])
    se     = float(fc.se_mean.iloc[0])
    return mean, se


def build_ensemble_forecast(data: dict) -> tuple[float, float]:
    """
    Blend AR(2) forecast with 4-week MA (simple trend anchor).
    Returns (forecast_mean_thousands, forecast_se_thousands).
    """
    ar_mean, ar_se = build_ar_forecast(data["icsa"])

    # 4-week MA as anchor — captures recent trend level
    ma4_mean = float(data["ic4w"].dropna().iloc[-1])

    ensemble_mean = (1 - MA4_BLEND) * ar_mean + MA4_BLEND * ma4_mean
    return ensemble_mean, ar_se


def forecast_to_probability(mean_k: float, se_k: float,
                            threshold: int) -> float:
    """
    P(claims >= threshold) using normal CDF.
    mean_k, se_k: forecast in thousands.
    threshold: Kalshi contract threshold (integer claims count, e.g. 200000).
    """
    threshold_k = threshold / 1000.0
    return float(1 - norm.cdf(threshold_k, loc=mean_k, scale=se_k))


# ── Kalshi market helpers ──────────────────────────────────────────────────────

def find_open_claims_events() -> list[dict]:
    """Return list of open KXJOBLESSCLAIMS events."""
    resp = requests.get(f"{BASE_URL}/events", params={
        "status": "open",
        "series_ticker": SERIES_TICKER,
        "limit": 5,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json().get("events", [])


def get_event_markets(event_ticker: str) -> list[dict]:
    """Return all markets within an event."""
    resp = requests.get(
        f"{BASE_URL}/events/{event_ticker}",
        params={"with_nested_markets": "true"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("event", {}).get("markets", [])


def parse_threshold(ticker: str) -> int | None:
    """Extract integer threshold from ticker like KXJOBLESSCLAIMS-26APR30-200000."""
    try:
        return int(ticker.split("-")[-1])
    except (ValueError, IndexError):
        return None


def get_market_price(market: dict) -> float:
    """Return YES mid-price as decimal probability."""
    bid = market.get("yes_bid", 0) or 0
    ask = market.get("yes_ask", 100) or 100
    return ((bid + ask) / 2) / 100.0


def find_best_market(markets: list[dict], p_yes_by_threshold: dict[int, float]) -> dict | None:
    """
    Among all markets, find the one with the largest |model_prob - market_prob|
    that exceeds THRESHOLD_EDGE.
    """
    best = None
    best_edge = 0.0
    for m in markets:
        thresh = parse_threshold(m.get("ticker", ""))
        if thresh is None or thresh not in p_yes_by_threshold:
            continue
        p_model  = p_yes_by_threshold[thresh]
        p_market = get_market_price(m)
        if p_market <= 0 or p_market >= 1:
            continue
        edge = abs(p_model - p_market)
        if edge > best_edge and edge >= THRESHOLD_EDGE:
            best_edge = edge
            best = {"market": m, "p_model": p_model, "p_market": p_market,
                    "edge": edge, "threshold": thresh}
    return best


# ── Kelly sizing ──────────────────────────────────────────────────────────────

def kelly_contracts(p_model: float, p_market: float,
                    bankroll: float) -> tuple[int, float]:
    """Quarter-Kelly contract sizing."""
    if p_market <= 0 or p_market >= 1:
        return 0, 0.0
    if p_model > p_market:
        side = "YES"
        M = (1 - p_market) / p_market   # odds received per dollar risked
        f_star = (p_model * M - (1 - p_model)) / (M - 1 + 1e-9)
        price  = p_market
    else:
        side = "NO"
        p_no_model  = 1 - p_model
        p_no_market = 1 - p_market
        M = p_market / (1 - p_market)
        f_star = (p_no_model * M - (1 - p_no_model)) / (M - 1 + 1e-9)
        price  = p_no_market

    f_star = max(0.0, min(f_star * KELLY_FRACTION, 0.50))
    cost_per = price  # cost per contract in dollars
    n = int((bankroll * f_star) / cost_per) if cost_per > 0 else 0
    n = max(MIN_CONTRACTS, min(n, MAX_CONTRACTS)) if n >= MIN_CONTRACTS else 0
    return n, side, round(n * cost_per, 2)


def fee_estimate(n: int, price: float, maker: bool = False) -> float:
    """Kalshi fee: 0.07 * C * P * (1-P) taker, 0.0175 maker."""
    rate = 0.0175 if maker else 0.07
    return round(rate * n * price * (1 - price), 2)


# ── Order placement ───────────────────────────────────────────────────────────

def place_order(client, market: dict, side: str, n: int,
                price_cents: int, dry_run: bool) -> dict | None:
    """Place IOC order via Kalshi authenticated client."""
    ticker = market["ticker"]
    tag = "[DRY RUN] " if dry_run else ""
    print(f"  {tag}ORDER: {side} {n} × {ticker} @ {price_cents}¢")
    if dry_run:
        return None
    try:
        order = client.create_order(
            ticker=ticker,
            side=side.lower(),
            count=n,
            type="limit",
            yes_price=price_cents if side == "YES" else (100 - price_cents),
            time_in_force="ioc",
        )
        print(f"    ✓ order_id={order.get('order', {}).get('order_id', '?')}")
        return order
    except Exception as e:
        print(f"    ✗ ERROR: {e}")
        return None


def load_log() -> list:
    if not LOG_FILE.exists():
        return []
    return json.loads(LOG_FILE.read_text())


def save_log(entry: dict):
    log = load_log()
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("--status",         action="store_true",
                        help="Show open markets and current prices")
    parser.add_argument("--backfill-check", action="store_true",
                        help="Show latest FRED data freshness")
    args = parser.parse_args()

    fred_key = os.environ.get("FRED_API_KEY", "")
    if not fred_key:
        print("ERROR: FRED_API_KEY not set.")
        sys.exit(1)
    fred = Fred(api_key=fred_key)

    print(f"\nKalshi Jobless Claims Strategy — {date.today()}")

    # FRED data
    print("\nFetching FRED data (ICSA + IC4WSA)…")
    data = get_claims_data(fred)
    latest_date = data["icsa"].dropna().index[-1].strftime("%Y-%m-%d")
    latest_val  = float(data["icsa"].dropna().iloc[-1])
    latest_ma4  = float(data["ic4w"].dropna().iloc[-1])
    print(f"  Latest ICSA ({latest_date}): {latest_val:.0f}K claims")
    print(f"  4-week MA:  {latest_ma4:.1f}K claims")

    if args.backfill_check:
        print(f"\nData freshness: ICSA last obs {latest_date}, value {latest_val:.0f}K")
        return

    # Forecast
    mean_k, se_k = build_ensemble_forecast(data)
    print(f"\nForecast: {mean_k*1000:.0f} ± {se_k*1000:.0f} claims  "
          f"({mean_k:.1f}K ± {se_k:.1f}K, 1σ)")

    # Find open markets
    print("\nSearching for open KXJOBLESSCLAIMS markets…")
    events = find_open_claims_events()
    if not events:
        print("  No open KXJOBLESSCLAIMS events found.")
        return

    # Process most recent event
    ev = events[0]
    ev_ticker = ev["event_ticker"]
    print(f"  Found: {ev_ticker}  ({ev.get('sub_title','')})")

    markets = get_event_markets(ev_ticker)
    print(f"  {len(markets)} markets — thresholds: "
          f"{', '.join(str(parse_threshold(m['ticker'])) for m in markets if parse_threshold(m['ticker']))}")

    # Compute model probability for each threshold
    thresholds = [parse_threshold(m["ticker"]) for m in markets]
    thresholds = [t for t in thresholds if t is not None]
    p_yes_by_threshold = {t: forecast_to_probability(mean_k, se_k, t) for t in thresholds}

    print(f"\n  {'Threshold':>12}  {'Model P(≥T)':>12}  {'Market':>8}  {'Edge':>8}")
    print(f"  {'─'*12}  {'─'*12}  {'─'*8}  {'─'*8}")
    for m in markets:
        t = parse_threshold(m["ticker"])
        if t is None:
            continue
        p_m = p_yes_by_threshold.get(t, float("nan"))
        p_k = get_market_price(m)
        edge = p_m - p_k if not np.isnan(p_m) else float("nan")
        flag = " ← EDGE" if abs(edge) >= THRESHOLD_EDGE else ""
        print(f"  {t:>12,}  {p_m:>12.1%}  {p_k:>8.1%}  {edge:>+8.1%}{flag}")

    if args.status:
        return

    # Find best market to trade
    best = find_best_market(markets, p_yes_by_threshold)
    if best is None:
        print(f"\nNo market meets edge threshold ({THRESHOLD_EDGE*100:.0f}pp). No trade.")
        return

    m     = best["market"]
    pm    = best["p_model"]
    pk    = best["p_market"]
    edge  = best["edge"]
    thresh = best["threshold"]
    side_flag = "YES" if pm > pk else "NO"
    price_decimal = pk if side_flag == "YES" else 1 - pk

    result = kelly_contracts(pm, pk, BANKROLL)
    n, side, cost = result if len(result) == 3 else (0, side_flag, 0.0)

    print(f"\nBest market: {m['ticker']}")
    print(f"  Threshold: {thresh:,}")
    print(f"  Model P(YES): {pm:.1%}   Market P(YES): {pk:.1%}   Edge: {edge:+.1%}")
    print(f"  Side: {side}   Contracts: {n}   Cost: ${cost:,.2f}")
    print(f"  Fee est: ${fee_estimate(n, price_decimal):,.2f} (taker IOC)")

    if n == 0:
        print("  Kelly sizing below minimum — no trade.")
        return

    # Authenticate and trade
    if not KALSHI_SDK_AVAILABLE:
        print("\nERROR: kalshi-py not installed. Run: pip install kalshi-py")
        sys.exit(1)

    try:
        key_id, pem = load_credentials()
    except EnvironmentError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    client = KalshiAuthenticatedClient(key_id, pem, BASE_URL)
    price_cents = round(price_decimal * 100)
    order_result = place_order(client, m, side, n, price_cents, args.dry_run)

    if not args.dry_run and order_result:
        save_log({
            "date":         date.today().isoformat(),
            "event":        ev_ticker,
            "market":       m["ticker"],
            "threshold":    thresh,
            "side":         side,
            "n_contracts":  n,
            "p_model":      round(pm, 4),
            "p_market":     round(pk, 4),
            "edge":         round(edge, 4),
            "forecast_k":   round(mean_k, 1),
            "se_k":         round(se_k, 1),
            "cost_usd":     cost,
            "order":        order_result,
        })
        print(f"\n✓ Trade logged to {LOG_FILE.name}")


if __name__ == "__main__":
    main()
