#!/usr/bin/env python3
"""
Kalshi Nonfarm Payrolls Strategy
=================================
Builds a 1-month-ahead NFP forecast using FRED data (PAYEMS + ADP) + AR(3),
then trades Kalshi KXUSNFP contracts when our model diverges from market
pricing by more than THRESHOLD_EDGE (default 3pp).

Released first Friday of each month at 8:30 AM ET.
ADP Employment report releases Wednesday of NFP week — best to run AFTER ADP.

Credentials required (set as environment variables):
    KALSHI_API_KEY_ID      — from Kalshi dashboard → API Keys
    KALSHI_PRIVATE_KEY_PEM — RSA-PSS private key PEM contents
    FRED_API_KEY           — from fred.stlouisfed.org/docs/api/api_key.html

Usage:
    python3 kalshi_nfp.py                  # full run
    python3 kalshi_nfp.py --dry-run        # signal + orders, no submission
    python3 kalshi_nfp.py --status         # show open Kalshi markets
    python3 kalshi_nfp.py --backfill-check # validate FRED data freshness

Schedule:
    - Run after ADP release (Wednesday of NFP week, ~8:15 AM ET)
    - Or run Thursday evening with latest FRED data
    - Markets typically open 1–2 weeks before NFP Friday
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

LOG_FILE = Path(__file__).parent / "kalshi_nfp_trades.json"

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_URL       = "https://api.elections.kalshi.com/trade-api/v2"

BANKROLL       = 5_000    # USD allocated to this strategy
THRESHOLD_EDGE = 0.03     # min edge (3pp) to place a trade
MIN_CONTRACTS  = 5
MAX_CONTRACTS  = 500
KELLY_FRACTION = 0.25     # quarter-Kelly

SERIES_TICKER  = "KXUSNFP"

# Model params — AR(3) on monthly PAYEMS change (in thousands)
AR_ORDER       = (3, 0, 0)
AR_WINDOW      = 36       # 3 years of monthly data for fitting
ADP_BLEND      = 0.30     # weight on ADP nowcast when available


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

def get_nfp_data(fred: Fred) -> dict:
    """
    Pull nonfarm payrolls and ADP employment from FRED.
    PAYEMS: total nonfarm payrolls, SA, thousands of persons.
    ADPWNUSNERSA: ADP national employment, SA, thousands.
    """
    payems = fred.get_series("PAYEMS")        # BLS NFP, thousands
    try:
        adp = fred.get_series("ADPWNUSNERSA") # ADP employment, thousands
    except Exception:
        adp = None  # ADP can lag FRED publication — gracefully degrade
    return {"payems": payems, "adp": adp}


def build_ar_forecast(payems: pd.Series) -> tuple[float, float]:
    """
    Fit AR(3) on last AR_WINDOW months of NFP monthly changes (thousands).
    Returns (forecast_mean_thousands, forecast_std_error_thousands).
    """
    monthly_change = payems.diff().dropna()
    if len(monthly_change) < AR_WINDOW + 5:
        raise ValueError(f"Insufficient NFP history: {len(monthly_change)} months")

    recent = monthly_change.iloc[-AR_WINDOW:]
    model  = ARIMA(recent, order=AR_ORDER)
    fit    = model.fit()
    fc     = fit.get_forecast(steps=1)
    mean   = float(fc.predicted_mean.iloc[0])
    se     = float(fc.se_mean.iloc[0])
    return mean, se


def get_adp_nowcast(adp: pd.Series | None) -> float | None:
    """
    Return the latest ADP monthly change as a nowcast for NFP (thousands).
    ADP releases 2 days before NFP — use if available and fresh.
    """
    if adp is None or len(adp) < 2:
        return None
    adp_change = adp.diff().dropna()
    latest_date = adp_change.index[-1]
    # Only use ADP if it's recent (within 45 days — covers NFP week)
    days_old = (pd.Timestamp.today() - latest_date).days
    if days_old > 45:
        return None
    return float(adp_change.iloc[-1])


def build_ensemble_forecast(data: dict) -> tuple[float, float]:
    """
    Blend AR(3) forecast with ADP nowcast if available.
    Returns (forecast_mean_thousands, forecast_se_thousands).
    """
    ar_mean, ar_se = build_ar_forecast(data["payems"])
    adp_nowcast   = get_adp_nowcast(data["adp"])

    if adp_nowcast is not None:
        # ADP is a strong same-month signal — upweight when available
        ensemble_mean = (1 - ADP_BLEND) * ar_mean + ADP_BLEND * adp_nowcast
        print(f"  ADP nowcast available: {adp_nowcast:+.0f}K  "
              f"(blending {100*(1-ADP_BLEND):.0f}% AR + {100*ADP_BLEND:.0f}% ADP)")
    else:
        ensemble_mean = ar_mean
        print("  ADP nowcast not available — using AR(3) only")

    return ensemble_mean, ar_se


def forecast_to_probability(mean_k: float, se_k: float,
                            threshold: int, direction: str) -> float:
    """
    Convert forecast to market probability.

    Kalshi KXUSNFP markets are structured as:
      "NFP will be ABOVE X"  → P(NFP > threshold)
      "NFP will be BELOW X"  → P(NFP < threshold)

    direction: "above" or "below" (parsed from market title/description).
    Threshold is in raw payroll count (e.g. 200000); convert to thousands.
    """
    threshold_k = threshold / 1_000.0
    if direction == "above":
        return float(1 - norm.cdf(threshold_k, loc=mean_k, scale=se_k))
    else:  # below
        return float(norm.cdf(threshold_k, loc=mean_k, scale=se_k))


# ── Kalshi market helpers ──────────────────────────────────────────────────────

def find_open_nfp_events() -> list[dict]:
    """Return list of open KXUSNFP events."""
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


def parse_market_info(ticker: str) -> tuple[int | None, str]:
    """
    Extract threshold (raw payroll count) and direction from KXUSNFP ticker.
    Actual Kalshi format uses thousands: KXUSNFP-26MAY08-T240 means 240K.
    Negative thresholds split as [..., "T", "40"] since "-" is the delimiter.
    Returns (threshold_raw_count, direction).
    """
    parts = ticker.split("-")
    if len(parts) < 3:
        return None, "above"
    last = parts[-1]
    second_last = parts[-2]
    try:
        # Negative threshold: e.g. KXUSNFP-26MAY08-T-40 → parts=[..., "T", "40"]
        if second_last.endswith(("T", "B")) and last.isdigit():
            sign = -1
            prefix = second_last[-1]
            threshold_k = -int(last)
        else:
            sign = 1
            prefix = last[0] if last and last[0] in ("T", "B") else "T"
            threshold_k = int(last.lstrip("TB"))
        direction = "below" if prefix == "B" else "above"
        return threshold_k * 1_000, direction
    except (ValueError, IndexError):
        return None, "above"


def get_market_price(market: dict) -> float:
    """Return YES mid-price as decimal probability."""
    bid = market.get("yes_bid", 0) or 0
    ask = market.get("yes_ask", 100) or 100
    return ((bid + ask) / 2) / 100.0


def find_best_market(markets: list[dict],
                     p_yes_by_ticker: dict[str, float]) -> dict | None:
    """
    Among all markets, find the one with the largest |model_prob - market_prob|
    that exceeds THRESHOLD_EDGE.
    """
    best = None
    best_edge = 0.0
    for m in markets:
        ticker = m.get("ticker", "")
        if ticker not in p_yes_by_ticker:
            continue
        p_model  = p_yes_by_ticker[ticker]
        p_market = get_market_price(m)
        if p_market <= 0 or p_market >= 1:
            continue
        edge = abs(p_model - p_market)
        if edge > best_edge and edge >= THRESHOLD_EDGE:
            best_edge = edge
            thresh, direction = parse_market_info(ticker)
            best = {
                "market": m, "p_model": p_model, "p_market": p_market,
                "edge": edge, "threshold": thresh, "direction": direction,
            }
    return best


# ── Kelly sizing ──────────────────────────────────────────────────────────────

def kelly_contracts(p_model: float, p_market: float,
                    bankroll: float) -> tuple[int, str, float]:
    """Quarter-Kelly contract sizing."""
    if p_market <= 0 or p_market >= 1:
        return 0, "YES", 0.0
    if p_model > p_market:
        side = "YES"
        M = (1 - p_market) / p_market
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
    n = int((bankroll * f_star) / price) if price > 0 else 0
    n = max(MIN_CONTRACTS, min(n, MAX_CONTRACTS)) if n >= MIN_CONTRACTS else 0
    return n, side, round(n * price, 2)


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

    print(f"\nKalshi NFP Strategy — {date.today()}")

    # FRED data
    print("\nFetching FRED data (PAYEMS + ADP)…")
    data = get_nfp_data(fred)
    payems   = data["payems"].dropna()
    latest_date  = payems.index[-1].strftime("%Y-%m-%d")
    latest_level = float(payems.iloc[-1])
    monthly_chg  = float(payems.diff().dropna().iloc[-1])
    print(f"  Latest PAYEMS ({latest_date}): {latest_level/1000:.1f}M workers  "
          f"(last change: {monthly_chg:+.0f}K)")

    if data["adp"] is not None:
        adp_latest  = data["adp"].dropna()
        adp_date    = adp_latest.index[-1].strftime("%Y-%m-%d")
        adp_chg     = float(adp_latest.diff().dropna().iloc[-1])
        print(f"  Latest ADP ({adp_date}): {adp_chg:+.0f}K")
    else:
        print("  ADP data unavailable")

    if args.backfill_check:
        print(f"\nData freshness: PAYEMS last obs {latest_date}, "
              f"change {monthly_chg:+.0f}K")
        return

    # Forecast
    mean_k, se_k = build_ensemble_forecast(data)
    print(f"\nForecast: {mean_k:+.0f}K ± {se_k:.0f}K (1σ)")
    print(f"  (range: {mean_k - se_k:+.0f}K to {mean_k + se_k:+.0f}K)")

    # Find open markets
    print("\nSearching for open KXUSNFP markets…")
    events = find_open_nfp_events()
    if not events:
        print("  No open KXUSNFP events found.")
        return

    ev = events[0]
    ev_ticker = ev["event_ticker"]
    print(f"  Found: {ev_ticker}  ({ev.get('sub_title', '')})")

    markets = get_event_markets(ev_ticker)
    print(f"  {len(markets)} markets")

    # Compute model probabilities for each market
    p_yes_by_ticker: dict[str, float] = {}
    for m in markets:
        ticker = m.get("ticker", "")
        thresh, direction = parse_market_info(ticker)
        if thresh is None:
            continue
        p_yes_by_ticker[ticker] = forecast_to_probability(
            mean_k, se_k, thresh, direction
        )

    print(f"\n  {'Market':<35}  {'Model':>7}  {'Market':>8}  {'Edge':>8}")
    print(f"  {'─'*35}  {'─'*7}  {'─'*8}  {'─'*8}")
    for m in markets:
        ticker = m.get("ticker", "")
        if ticker not in p_yes_by_ticker:
            continue
        p_m = p_yes_by_ticker[ticker]
        p_k = get_market_price(m)
        edge = p_m - p_k
        flag = " ← EDGE" if abs(edge) >= THRESHOLD_EDGE else ""
        label = ticker.split("-")[-1]
        print(f"  {ticker:<35}  {p_m:>7.1%}  {p_k:>8.1%}  {edge:>+8.1%}{flag}")

    if args.status:
        return

    # Find best market
    best = find_best_market(markets, p_yes_by_ticker)
    if best is None:
        print(f"\nNo market meets edge threshold ({THRESHOLD_EDGE*100:.0f}pp). No trade.")
        return

    m      = best["market"]
    pm     = best["p_model"]
    pk     = best["p_market"]
    edge   = best["edge"]
    thresh = best["threshold"]
    direc  = best["direction"]

    n, side, cost = kelly_contracts(pm, pk, BANKROLL)
    price_decimal = pk if side == "YES" else 1 - pk

    print(f"\nBest market: {m['ticker']}")
    print(f"  Threshold: {thresh:,}  ({direc.upper()})")
    print(f"  Model P(YES): {pm:.1%}   Market P(YES): {pk:.1%}   Edge: {edge:+.1%}")
    print(f"  Side: {side}   Contracts: {n}   Cost: ${cost:,.2f}")
    print(f"  Fee est: ${fee_estimate(n, price_decimal):,.2f} (taker IOC)")

    if n == 0:
        print("  Kelly sizing below minimum — no trade.")
        return

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
            "direction":    direc,
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
