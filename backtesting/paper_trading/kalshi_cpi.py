#!/usr/bin/env python3
"""
Kalshi CPI Nowcasting Strategy
================================
Builds a 1-month-ahead CPI forecast using FRED data + ARIMA, then trades
Kalshi CPI event contracts when our model diverges from market pricing by
more than THRESHOLD_EDGE (default 3pp).

Credentials required (set as environment variables):
    KALSHI_API_KEY_ID      — from Kalshi dashboard → API Keys
    KALSHI_PRIVATE_KEY_PEM — RSA-PSS private key PEM contents
                             (or set KALSHI_PRIVATE_KEY_PATH to the .pem file path)
    FRED_API_KEY           — from fred.stlouisfed.org/docs/api/api_key.html

Usage:
    python3 kalshi_cpi.py                  # full run (places real orders if edge > threshold)
    python3 kalshi_cpi.py --dry-run        # print signal + orders, no submission
    python3 kalshi_cpi.py --status         # show current positions + open orders
    python3 kalshi_cpi.py --backfill-check # validate FRED data freshness
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

from kalshi_client import KalshiAuthenticatedClient
KALSHI_SDK_AVAILABLE = True

LOG_FILE = Path(__file__).parent / "kalshi_cpi_trades.json"

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_URL       = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE_URL  = "https://demo-api.kalshi.co/trade-api/v2"

BANKROLL       = 5_000    # USD allocated to this strategy (conservative start)
THRESHOLD_EDGE = 0.03     # min edge (3pp) to place a trade
MIN_CONTRACTS  = 5        # don't trade less than 5 contracts
MAX_CONTRACTS  = 500      # cap per single trade
KELLY_FRACTION = 0.25     # quarter-Kelly for safety

CPI_SERIES_TICKER = "KXINFL"  # Kalshi CPI event series

# ARIMA parameters (validated on 2015-2026 CPI data)
ARIMA_ORDER    = (2, 0, 1)
ARIMA_WINDOW   = 36       # months of history for model fitting
PCE_BLEND      = 0.30     # weight on PCE nowcast vs ARIMA (0 = ARIMA only)


# ── Credentials ───────────────────────────────────────────────────────────────

def load_credentials() -> tuple[str, str]:
    """Load Kalshi API key and private key PEM. Raises on missing."""
    key_id = os.environ.get("KALSHI_API_KEY_ID") or os.environ.get("KALSHI_API_KEY", "")
    if not key_id:
        raise EnvironmentError(
            "KALSHI_API_KEY_ID (or KALSHI_API_KEY) not set.\n"
            "  1. Create a Kalshi account at https://kalshi.com\n"
            "  2. Go to Account & Security → API Keys\n"
            "  3. Generate a new RSA key pair (2048-bit)\n"
            "  4. Save the private key immediately — it cannot be retrieved later\n"
            "  5. Set env vars: KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PEM"
        )

    pem = os.environ.get("KALSHI_PRIVATE_KEY_PEM", "")
    if not pem:
        pem_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
        if pem_path and Path(pem_path).exists():
            pem = Path(pem_path).read_text()
        else:
            raise EnvironmentError(
                "KALSHI_PRIVATE_KEY_PEM (or KALSHI_PRIVATE_KEY_PATH) not set.\n"
                "Set to the RSA private key PEM string from Kalshi dashboard."
            )
    return key_id, pem


# ── FRED data + forecasting ───────────────────────────────────────────────────

def get_cpi_data(fred: Fred) -> dict:
    """Pull CPI and PCE series. Returns dict of series."""
    cpi  = fred.get_series("CPIAUCSL")   # Headline CPI all-urban consumers
    pce  = fred.get_series("PCEPI")      # PCE price index
    return {"cpi": cpi, "pce": pce}


def build_arima_forecast(cpi: pd.Series) -> tuple[float, float]:
    """
    Fit ARIMA(2,0,1) on last ARIMA_WINDOW months of CPI MoM changes.
    Returns (forecast_mean, forecast_std_error).
    """
    mom = cpi.pct_change().dropna() * 100  # % MoM
    if len(mom) < ARIMA_WINDOW + 5:
        raise ValueError(f"Insufficient CPI history: {len(mom)} months")

    series = mom.iloc[-ARIMA_WINDOW:]
    model  = ARIMA(series, order=ARIMA_ORDER)
    fit    = model.fit()
    fc     = fit.get_forecast(steps=1)
    mean   = float(fc.predicted_mean.iloc[0])
    se     = float(fc.se_mean.iloc[0])
    return mean, se


def build_ensemble_forecast(data: dict) -> tuple[float, float]:
    """
    Blend ARIMA CPI forecast (70%) with PCE lagged nowcast (30%).
    Returns (ensemble_mean, forecast_se).
    """
    arima_mean, arima_se = build_arima_forecast(data["cpi"])

    # PCE as correlated nowcast signal (last available MoM change)
    pce_mom = float(data["pce"].pct_change().dropna().iloc[-1] * 100)

    ensemble_mean = (1 - PCE_BLEND) * arima_mean + PCE_BLEND * pce_mom
    return ensemble_mean, arima_se


def forecast_to_probability(ensemble_mean: float, se: float,
                            threshold: float) -> float:
    """
    P(CPI MoM >= threshold) using normal CDF with ensemble forecast.
    threshold: Kalshi contract threshold (e.g., 0.3 for "CPI >= 0.3% MoM").
    """
    return float(1 - norm.cdf(threshold, loc=ensemble_mean, scale=se))


# ── Kalshi market helpers ──────────────────────────────────────────────────────

def find_cpi_market(target_threshold: float | None = None) -> dict | None:
    """
    Find the open CPI Kalshi market closest to our model's threshold.
    If target_threshold is None, return the highest-volume open market.
    """
    resp = requests.get(f"{BASE_URL}/markets", params={
        "status": "open",
        "series_ticker": CPI_SERIES_TICKER,
        "limit": 100,
    }, timeout=10)
    resp.raise_for_status()
    markets = resp.json().get("markets", [])

    if not markets:
        return None

    if target_threshold is None:
        # Pick highest volume
        return max(markets, key=lambda m: m.get("volume", 0))

    # Pick contract whose threshold is closest to our model threshold
    best = None
    best_dist = float("inf")
    for m in markets:
        ticker = m.get("ticker", "")
        # Extract threshold from ticker, e.g., "KXINFL-26MAY-B0.3" → 0.3
        try:
            parts = ticker.split("-B")
            if len(parts) == 2:
                thresh = float(parts[1])
                dist = abs(thresh - target_threshold)
                if dist < best_dist:
                    best_dist = dist
                    best = m
        except (ValueError, IndexError):
            continue

    return best


def get_market_price(market: dict) -> float:
    """Return YES mid-price as decimal probability."""
    bid = market.get("yes_bid", 0) or 0
    ask = market.get("yes_ask", 100) or 100
    return ((bid + ask) / 2) / 100.0


# ── Kelly sizing ──────────────────────────────────────────────────────────────

def kelly_contracts(p_model: float, p_market: float,
                    bankroll: float) -> tuple[int, float]:
    """
    Quarter-Kelly sizing.
    p_model  — our forecast probability (of YES outcome)
    p_market — Kalshi YES mid-price as decimal
    Returns (n_contracts, total_cost_usd).
    """
    if p_market <= 0 or p_market >= 1:
        return 0, 0.0

    side = "yes" if p_model > p_market else "no"
    p = p_model if side == "yes" else (1 - p_model)
    q = p_market if side == "yes" else (1 - p_market)

    if q <= 0 or q >= 1:
        return 0, 0.0

    M = 1.0 / q         # payout multiplier per dollar risked
    f = (p * M - (1 - p)) / (M - 1)
    f = max(0.0, f * KELLY_FRACTION)

    cost_per_contract = q  # price of the side we're buying
    usd_to_risk = bankroll * f
    n_contracts = int(usd_to_risk / cost_per_contract)
    n_contracts = max(0, min(n_contracts, MAX_CONTRACTS))

    return n_contracts, round(n_contracts * cost_per_contract, 2)


def fee_estimate(n_contracts: int, price: float, maker: bool = False) -> float:
    """Kalshi fee formula: 0.07 * C * P * (1-P) for takers."""
    rate = 0.0175 if maker else 0.07
    return round(rate * n_contracts * price * (1 - price), 4)


# ── Order execution ───────────────────────────────────────────────────────────

def get_client(demo: bool = False):
    key_id, pem = load_credentials()
    base = DEMO_BASE_URL if demo else BASE_URL
    return KalshiAuthenticatedClient(
        access_key_id=key_id,
        private_key_pem=pem,
        base_url=base,
    )


def get_portfolio_status(client) -> dict:
    """Return current balance and positions."""
    try:
        bal = client.get_balance()
        positions = client.get_positions()
        return {
            "balance_cents": bal.get("balance", 0),
            "positions": positions.get("market_positions", []),
        }
    except Exception as e:
        return {"error": str(e)}


def place_order(client, market: dict, side: str, n_contracts: int,
                price_cents: int, dry_run: bool) -> dict:
    """Submit a limit IOC order on Kalshi."""
    ticker = market["ticker"]
    tag = "[DRY RUN] " if dry_run else ""
    print(f"  {tag}ORDER: {n_contracts}x {ticker} {side.upper()} @ {price_cents}¢  "
          f"(${n_contracts * price_cents / 100:.2f})")

    if dry_run:
        return {"dry_run": True, "ticker": ticker, "side": side,
                "count": n_contracts, "price_cents": price_cents}

    try:
        order = client.create_order(
            ticker=ticker,
            action="buy",
            side=side,
            count=n_contracts,
            yes_price=price_cents if side == "yes" else (100 - price_cents),
            time_in_force="ioc",
        )
        print(f"  ✓ order_id={order.get('order', {}).get('order_id', '?')}  "
              f"filled={order.get('order', {}).get('filled_count', 0)}")
        return order
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return {"error": str(e)}


def log_trade(entry: dict):
    log = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("--status",         action="store_true")
    parser.add_argument("--backfill-check", action="store_true")
    parser.add_argument("--demo",           action="store_true",
                        help="Use Kalshi demo environment")
    parser.add_argument("--bankroll",       type=float, default=BANKROLL)
    args = parser.parse_args()

    print(f"\nKalshi CPI Nowcasting — {date.today()}")
    print(f"Mode: {'DEMO' if args.demo else 'LIVE'}  "
          f"{'[DRY RUN]' if args.dry_run else ''}")

    # ── Status-only mode ──
    if args.status:
        if not KALSHI_SDK_AVAILABLE:
            print("kalshi-py not installed. pip install kalshi-py")
            return
        try:
            client = get_client(demo=args.demo)
            status = get_portfolio_status(client)
            if "error" in status:
                print(f"Error: {status['error']}")
                return
            bal_usd = status["balance_cents"] / 100
            print(f"\nKalshi balance: ${bal_usd:,.2f}")
            positions = status["positions"]
            if positions:
                print(f"\nOpen positions ({len(positions)}):")
                for p in positions:
                    print(f"  {p.get('ticker','?'):<30} {p.get('position',0):>6} contracts")
            else:
                print("No open positions.")
        except EnvironmentError as e:
            print(f"\n⚠ Credentials not set:\n{e}")
        return

    # ── FRED data + forecast ──
    fred_key = os.environ.get("FRED_API_KEY", "")
    if not fred_key:
        print("FRED_API_KEY not set.")
        sys.exit(1)

    print("\nPulling FRED data…")
    fred = Fred(api_key=fred_key)
    data = get_cpi_data(fred)
    cpi_latest_date = data["cpi"].index[-1]
    print(f"  CPI latest: {cpi_latest_date.strftime('%Y-%m')}  "
          f"({data['cpi'].iloc[-1]:.3f})")

    if args.backfill_check:
        lag = (pd.Timestamp.now() - cpi_latest_date).days
        print(f"  Data lag: {lag} days")
        if lag > 45:
            print("  ⚠ Data may be stale — CPI releases ~2 weeks after month end")
        return

    print("\nBuilding ensemble forecast…")
    try:
        ensemble_mean, forecast_se = build_ensemble_forecast(data)
    except Exception as e:
        print(f"  ✗ Forecast failed: {e}")
        sys.exit(1)
    print(f"  Ensemble mean:    {ensemble_mean:>+.3f}% MoM")
    print(f"  Forecast std err: {forecast_se:.3f}%")

    # ── Find Kalshi market ──
    print("\nFinding Kalshi CPI market…")
    try:
        market = find_cpi_market(target_threshold=round(ensemble_mean, 1))
    except Exception as e:
        print(f"  ✗ Market lookup failed: {e}")
        market = None

    if market is None:
        print("  No open CPI market found.")
        sys.exit(0)

    # Extract threshold from ticker
    ticker = market.get("ticker", "")
    try:
        threshold = float(ticker.split("-B")[1])
    except (IndexError, ValueError):
        threshold = 0.3  # fallback

    print(f"  Market: {ticker}")
    print(f"  Threshold: {threshold}% MoM")

    # Convert to probability
    p_model  = forecast_to_probability(ensemble_mean, forecast_se, threshold)
    p_market = get_market_price(market)

    print(f"\nSignal:")
    print(f"  Model prob P(CPI >= {threshold}%): {p_model:.3f}")
    print(f"  Kalshi mid price:                  {p_market:.3f}")
    edge = abs(p_model - p_market)
    side = "yes" if p_model > p_market else "no"
    print(f"  Edge: {edge:.3f}  Direction: {side.upper()}")

    if edge < THRESHOLD_EDGE:
        print(f"\n  ⊘ Edge {edge:.3f} < threshold {THRESHOLD_EDGE:.3f} — no trade.")
        sys.exit(0)

    # ── Position sizing ──
    n_contracts, trade_cost = kelly_contracts(p_model, p_market, args.bankroll)
    if n_contracts < MIN_CONTRACTS:
        print(f"\n  ⊘ Too few contracts ({n_contracts} < {MIN_CONTRACTS}) — no trade.")
        sys.exit(0)

    price_for_side = p_market if side == "yes" else (1 - p_market)
    fee = fee_estimate(n_contracts, price_for_side, maker=False)
    net_edge = edge - (fee / n_contracts if n_contracts > 0 else 0)
    price_cents = int(price_for_side * 100)

    print(f"\nTrade plan:")
    print(f"  {n_contracts} contracts {side.upper()} @ {price_cents}¢")
    print(f"  Total cost: ${trade_cost:.2f}")
    print(f"  Taker fee est: ${fee:.2f}  Net edge: {net_edge:.3f}")

    if net_edge < 0.005:
        print("  ⊘ Net edge after fees < 0.5% — no trade.")
        sys.exit(0)

    # ── Execute ──
    if not KALSHI_SDK_AVAILABLE:
        print("\nkalshi-py SDK required. Install with: pip install kalshi-py")
        sys.exit(1)

    try:
        client = get_client(demo=args.demo)
    except EnvironmentError as e:
        print(f"\n⚠ Cannot connect to Kalshi:\n{e}")
        sys.exit(1)

    result = place_order(client, market, side, n_contracts, price_cents, args.dry_run)

    if not args.dry_run and "error" not in result:
        log_trade({
            "date":           date.today().isoformat(),
            "ticker":         ticker,
            "threshold":      threshold,
            "p_model":        round(p_model, 4),
            "p_market":       round(p_market, 4),
            "edge":           round(edge, 4),
            "side":           side,
            "n_contracts":    n_contracts,
            "price_cents":    price_cents,
            "trade_cost_usd": trade_cost,
            "fee_est":        fee,
            "net_edge":       round(net_edge, 4),
            "submitted_at":   datetime.now().isoformat(),
        })
        print(f"\n✓ Logged to {LOG_FILE.name}")


if __name__ == "__main__":
    main()
