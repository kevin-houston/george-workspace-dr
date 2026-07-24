#!/usr/bin/env python3
"""H437 — Optimal Market Making in Prediction Markets (Kalshi).

Source: arXiv:2607.17991 (Feil & Nendel, Jul 2026)
'Optimal Market Making in Prediction Markets'

Framework:
  - Market price p_t = Phi(X_t) where X_t is latent belief diffusion,
    Phi = logistic function mapping belief to [0,1] probability.
  - Market maker chooses bid/ask spreads to maximize expected terminal wealth
    while controlling: (1) mark-to-market inventory risk; (2) binary settlement
    risk of remaining contracts at resolution.
  - HJB solution: optimal bid spread = f(inventory, belief, time-to-resolution)
    with wider spreads when inventory is extreme or near resolution date.
  - Key result: HJB strategy substantially improves downside protection vs myopic
    strategy (which maximizes instantaneous expected mark-to-market profit).

H437 Design:
  - Target: Kalshi CPI and NFP binary contracts
  - Implement latent belief tracker using historical Kalshi prices (EMA)
  - HJB solver: finite-difference on transformed PDE (belief space)
  - Quoting: call Kalshi REST API to post limit orders at computed bid/ask
  - Risk limits: max inventory = 50 contracts per event, max delta = $200

Variants:
  A: Full HJB optimal controller (belief diffusion calibrated IS from Kalshi history)
  B: Myopic controller (maximize instantaneous expected spread, no inventory penalty)
  C: Fixed spread market maker (constant 2-tick spread, no intelligence)
  D: No market making (paper only — track only, do not submit orders)

Note: Requires Kalshi API credentials (RSA-PSS auth, configured in OneCLI vault).
Paper trading only until 30-day gate evaluation passes.
"""

import os
import json
import time
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple

# ── Kalshi API configuration ──────────────────────────────────────────────────
# Credentials injected by OneCLI proxy; see wiki/trading/prediction-markets/kalshi.md
KALSHI_BASE_URL = 'https://trading-api.kalshi.com/trade-api/v2'

# Target event series (CPI + NFP binary contracts)
TARGET_SERIES = ['CPI', 'NFP']  # Kalshi series IDs

# ── HJB solver parameters ─────────────────────────────────────────────────────
GRID_BELIEF = 200     # belief grid points (0, 1)
GRID_INV    = 101     # inventory grid (-50 to +50)
DT          = 1 / (252 * 6.5 * 60)  # 1-minute time step
RISK_AVERSION = 0.01  # gamma: inventory risk aversion
BETA        = 0.5     # belief diffusion mean-reversion speed
SIGMA_X     = 0.02    # belief diffusion volatility
A_PARAM     = 5.0     # intensity model: arrival rate = A * exp(-k * spread)
K_PARAM     = 50.0


def logistic(x: float) -> float:
    """Belief-to-probability mapping."""
    return 1 / (1 + math.exp(-x))


def optimal_spread_hjb(inventory: float,
                       belief: float,
                       time_remaining: float,
                       grid_solution: Optional[np.ndarray] = None) -> Tuple[float, float]:
    """Compute optimal bid/ask spread from HJB solution.

    Args:
        inventory: current net contract position (negative = short)
        belief: current latent belief value (logistic maps to probability)
        time_remaining: fraction of time to contract resolution [0, 1]
        grid_solution: precomputed HJB value function grid (if None: use approximation)

    Returns:
        (bid_spread, ask_spread) in probability points [0, 1]
    """
    prob = logistic(belief)
    inv_norm = inventory / 50.0  # normalize to [-1, 1]

    if grid_solution is not None:
        # Interpolate from precomputed HJB grid
        # TODO: implement 2D interpolation on (belief, inventory) grid
        pass

    # Approximation: asymmetric spread based on inventory + settlement risk
    # Base spread widens near resolution (settlement risk) and with |inventory|
    base_spread = 0.02 + 0.03 * time_remaining
    inventory_skew = 0.01 * inv_norm  # lean against inventory
    settlement_risk = 0.05 * (1 - time_remaining) ** 2  # spike near expiry

    bid_spread = base_spread + inventory_skew + settlement_risk
    ask_spread = base_spread - inventory_skew + settlement_risk

    # Minimum spread = 1 tick (0.01)
    bid_spread = max(0.01, bid_spread)
    ask_spread = max(0.01, ask_spread)

    return bid_spread, ask_spread


def get_kalshi_market_price(series_id: str,
                             session=None) -> Optional[float]:
    """Fetch current mid-price from Kalshi REST API.

    Returns probability as float [0, 1], or None on error.
    """
    try:
        import requests
        url = f'{KALSHI_BASE_URL}/markets/?series_ticker={series_id}&status=open'
        resp = session.get(url) if session else requests.get(url)
        if resp.status_code == 200:
            markets = resp.json().get('markets', [])
            if markets:
                m = markets[0]
                yes_bid = m.get('yes_bid', 0) / 100.0
                yes_ask = m.get('yes_ask', 1) / 100.0
                return (yes_bid + yes_ask) / 2
    except Exception as e:
        print(f'  Kalshi API error: {e}')
    return None


def post_limit_order(series_id: str,
                     side: str,  # 'yes' or 'no'
                     price_prob: float,
                     count: int,
                     session=None) -> bool:
    """Post a limit order to Kalshi."""
    try:
        import requests
        price_cents = int(price_prob * 100)
        payload = {
            'ticker': series_id,
            'action': 'buy',
            'side': side,
            'count': count,
            'type': 'limit',
            'yes_price': price_cents if side == 'yes' else 100 - price_cents,
        }
        url = f'{KALSHI_BASE_URL}/portfolio/orders'
        resp = session.post(url, json=payload) if session else requests.post(url, json=payload)
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f'  Order error: {e}')
        return False


class InventoryTracker:
    """Tracks open inventory and P&L per event."""

    def __init__(self, max_inventory: int = 50):
        self.inventory: dict = {}  # series_id -> net contracts
        self.cost_basis: dict = {}  # series_id -> average cost
        self.pnl: list = []
        self.max_inventory = max_inventory

    def update(self, series_id: str, side: str, count: int, price: float):
        if series_id not in self.inventory:
            self.inventory[series_id] = 0
            self.cost_basis[series_id] = price
        delta = count if side == 'yes' else -count
        self.inventory[series_id] += delta

    def net_delta(self, series_id: str, current_price: float) -> float:
        """Current P&L estimate for open position."""
        inv = self.inventory.get(series_id, 0)
        cost = self.cost_basis.get(series_id, 0.5)
        return inv * (current_price - cost)

    def can_add(self, series_id: str, side: str, count: int) -> bool:
        curr = self.inventory.get(series_id, 0)
        delta = count if side == 'yes' else -count
        return abs(curr + delta) <= self.max_inventory


def run_variant_d_paper_only(series_ids: list):
    """Variant D: paper tracking only, no orders submitted."""
    print('Variant D — Paper only (no orders). Tracking Kalshi prices...')
    for series_id in series_ids:
        price = get_kalshi_market_price(series_id)
        if price is not None:
            bid_s, ask_s = optimal_spread_hjb(
                inventory=0,
                belief=math.log(price / (1 - price + 1e-8)),  # logit
                time_remaining=0.5  # placeholder
            )
            print(f'  {series_id}: mid={price:.3f}  '
                  f'HJB bid_spread={bid_s:.3f}  ask_spread={ask_s:.3f}  '
                  f'→ bid={max(0, price - bid_s):.3f}  ask={min(1, price + ask_s):.3f}')
        else:
            print(f'  {series_id}: price unavailable')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='H437 Optimal Prediction Market MM')
    parser.add_argument('--variant', choices=['A', 'B', 'C', 'D'], default='D')
    parser.add_argument('--dry-run', action='store_true', default=True)
    parser.add_argument('--duration-mins', type=int, default=30)
    args = parser.parse_args()

    print('H437 — Optimal Market Making in Prediction Markets (Kalshi)')
    print('=' * 60)
    print(f'Variant: {args.variant}  DryRun: {args.dry_run}')
    print(f'Target series: {TARGET_SERIES}')
    print()

    # Variant D always starts as paper mode
    if args.variant == 'D' or args.dry_run:
        run_variant_d_paper_only(TARGET_SERIES)
        return

    # Variants A/B/C: live quoting (requires Kalshi auth)
    try:
        import requests
        session = requests.Session()
        # OneCLI proxy injects RSA-PSS auth headers automatically
        session.headers.update({'Content-Type': 'application/json'})
    except ImportError:
        print('ERROR: requests not available')
        return

    tracker = InventoryTracker(max_inventory=50)
    start_time = datetime.utcnow()
    end_time = start_time + timedelta(minutes=args.duration_mins)

    print(f'Running until {end_time.strftime("%H:%M:%S")} UTC')
    log = []

    while datetime.utcnow() < end_time:
        for series_id in TARGET_SERIES:
            price = get_kalshi_market_price(series_id, session)
            if price is None:
                continue

            belief = math.log(max(1e-6, price) / max(1e-6, 1 - price))
            time_remaining = 0.5  # TODO: compute from contract expiry
            inventory = tracker.inventory.get(series_id, 0)

            if args.variant == 'A':
                bid_s, ask_s = optimal_spread_hjb(inventory, belief, time_remaining)
            elif args.variant == 'B':
                # Myopic: fixed spread ignoring inventory
                bid_s = ask_s = 0.02
            elif args.variant == 'C':
                # Fixed 2-tick spread
                bid_s = ask_s = 0.02

            bid_price = max(0.01, price - bid_s)
            ask_price = min(0.99, price + ask_s)

            print(f'  {series_id}: mid={price:.3f}  bid={bid_price:.3f}  ask={ask_price:.3f}  inv={inventory}')
            log.append({
                'time': datetime.utcnow().isoformat(),
                'series': series_id,
                'mid': price,
                'bid': bid_price,
                'ask': ask_price,
                'inventory': inventory
            })

            if not args.dry_run and tracker.can_add(series_id, 'yes', 1):
                # Post 1-contract bid (buy yes at bid_price)
                post_limit_order(series_id, 'yes', bid_price, 1, session)
                # Post 1-contract ask (buy no at 1-ask_price)
                post_limit_order(series_id, 'no', 1 - ask_price, 1, session)

        time.sleep(60)  # 1-minute quoting cycle

    # Save run log
    os.makedirs('prediction_markets', exist_ok=True)
    log_path = f'prediction_markets/h437_log_{datetime.utcnow().strftime("%Y%m%d_%H%M")}.json'
    with open(log_path, 'w') as f:
        json.dump(log, f, indent=2)
    print(f'\nRun complete. Log: {log_path}')


if __name__ == '__main__':
    main()
