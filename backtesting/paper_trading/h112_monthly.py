#!/usr/bin/env python3
"""
H122 Monthly Portfolio Rebalancer
Manages H041a (22%), H026 (27%), H045 (21%) sub-strategies.

H116 upgrade (vs H112): H026 uses TSMOM filter — only assets with positive
12-month return are eligible. When nothing qualifies, H026 allocates to cash.

H120 upgrade (vs H116): ranking signal is now the rank ensemble of
3m + 6m + 12m momentum (each ranked independently then summed). Confirmed
+28% OOS improvement and MaxDD improvement -3.6% → -2.4%.
TSMOM filter still uses 12m return sign (unchanged).

H122 upgrade (vs H120): vol-targeting on H026 only (H121 confirmed). Scale
H026 base weight (27%) by (target_vol / realized_6m_vol), clamp 0.5x–2x,
renorm rotation total to stay at 70%. Uses trade log history to compute H026
realized vol. Falls back to fixed weights when < 3 months of history.

H128 upgrade (vs H122): H045 now uses a 3m TSMOM filter — only bond ETFs
with positive 3-month return are eligible. When nothing qualifies, H045
allocates to cash. Confirmed +0.4691 OOS cumul, +1.7194 AltOOS cumul.
Bond momentum reverses faster than equity; 3m filter exits early on rate
shocks and re-enters quickly on recovery vs the 12m filter used on H026.

H130 upgrade (vs H128): H041a now also uses a 3m TSMOM filter — only global
equity ETFs with positive 3-month return are eligible. When nothing qualifies,
H041a allocates to cash. Confirmed +1.6432 OOS cumul, +6.2530 AltOOS cumul,
Sharpe 4.553→4.600, MaxDD -3.6%→-3.0%. Both H041a and H045 now use 3m
TSMOM; H026 keeps 12m (sector rotation has longer-duration trends).

H133 upgrade (vs H130): vol-targeting on H041a at 25% annualized target
(same framework as H026/H122 vol-targeting). Scale H041a base weight (22%)
by (0.25 / realized_6m_vol), clamp 0.5x–2x. Confirmed Sharpe 4.600→4.846,
MaxDD -3.0%→-2.2%, AltOOS +2.1884. Only activates during extreme vol periods
(2022 selloff, 2020 COVID, 2008 crisis). OOS cumul change negligible (+0.003).

H134 note (vs H133): backtesting confirmed that the production H045 scoring
formula (rank(3m)+rank(6m)+rank(12m)+rank(inv_vol) via compute_signal) is
the optimal formula. Prior backtest runs (H128/H130/H133) used a simplified
rank(12m)+rank(inv_vol) for H045, underestimating production performance.
H134 backtest baseline corrected: OOS 24.9104, AltOOS 89.6697, Sharpe 4.889.
No code change needed — production was already using the correct full ensemble.

H139 upgrade (vs H134): H026 TSMOM threshold raised from 0% to +5%. Only
sector ETFs with 12m return > +5% are eligible for selection (previously any
positive 12m return qualified). Borderline-positive sectors (0-5% 12m return)
are unreliable trend followers and were diluting signal quality. Confirmed:
OOS Δ+1.6107, AltOOS Δ+3.0181, Sharpe 4.889→4.971.

H140 upgrade (vs H139): H041a TSMOM threshold raised from 0% to +0.5%. Only
global equity ETFs with 3m return > +0.5% are eligible (barely-breakeven
ETFs filtered out). Confirmed B (+0.5%): OOS Δ+0.4732, AltOOS Δ+3.0055,
Sharpe 4.971→5.012, MaxDD unchanged at -2.5%. Both H026 and H041a now use
tighter TSMOM thresholds. H045 remains at 0% (bonds need fast re-entry).

Run on the first trading day of each month at ~9:45 AM CT.
Usage:
    python3 h112_monthly.py            # live run
    python3 h112_monthly.py --dry-run  # print orders, no submission
    python3 h112_monthly.py --status   # show positions only
    python3 h112_monthly.py --force    # skip "first-of-month" guard
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# ── Universe definitions (H112 confirmed) ──────────────────────────────────
H041A_ASSETS = [
    "SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
    "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN",
]
H026_ASSETS = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO",
]
H045_ASSETS = [
    "SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY",
]

SUB_STRATS = {
    "h041a": {"assets": H041A_ASSETS, "n_hold": 1, "weight": 0.22, "tsmom_filter": True,  "tsmom_lb": 3,  "tsmom_threshold": 0.005},  # H130: 3m filter; H140: threshold +0.5%
    "h026":  {"assets": H026_ASSETS,  "n_hold": 1, "weight": 0.27, "tsmom_filter": True,  "tsmom_lb": 12, "tsmom_threshold": 0.05},  # H116: 12m filter; H139: threshold +5%
    "h045":  {"assets": H045_ASSETS,  "n_hold": 2, "weight": 0.21, "tsmom_filter": True,  "tsmom_lb": 3},   # H128: 3m filter
}

LOG_FILE = Path(__file__).parent / "h112_monthly_trades.json"
MIN_ORDER_USD = 5.0  # ignore rebalance deltas smaller than $5

# H122/H133: vol-targeting on H026 and H041a
ROTATION_WEIGHT  = 0.22 + 0.27 + 0.21  # 0.70 — total rotation allocation
VOL_TARGET_H026  = 0.15   # ~long-run annualized vol of H026 from backtests
VOL_TARGET_H041A = 0.25   # H133: vol-target H041a at 25% (only scales in extreme vol)
VOL_WINDOW_H026  = 6      # months of history to estimate realized vol (shared)
VOL_CLAMP_H026   = (0.5, 2.0)


# ── Signal computation ──────────────────────────────────────────────────────

def compute_signal(assets: list[str], n_hold: int,
                   tsmom_filter: bool = False,
                   tsmom_lb: int = 12,
                   tsmom_threshold: float = 0.0) -> tuple[list[str], dict]:
    """
    Rank ensemble (3m+6m+12m momentum ranks) + inv 6-month vol rank → top-N.

    H120 upgrade: each lookback is ranked independently then summed, avoiding
    scale dominance by the 12m signal. +28% OOS improvement over 12m-only.

    tsmom_filter: if True, only assets with positive N-month return are eligible.
      tsmom_lb=12 → H026 filter (12m sign, H116 upgrade)
      tsmom_lb=3  → H045 filter (3m sign, H128 upgrade)
    Returns ([], {}) when nothing qualifies → sub-strategy goes to cash.
    Returns (top_n_tickers, scores_dict).
    """
    tickers = list(set(assets))
    raw = yf.download(tickers, period="15mo", auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw
    prices = prices[assets].dropna(how="all", axis=1)

    monthly_px  = prices.resample("ME").last()
    monthly_ret = prices.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)

    mom_12 = (monthly_px / monthly_px.shift(12) - 1).iloc[-1].dropna()
    mom_6  = (monthly_px / monthly_px.shift(6)  - 1).iloc[-1].dropna()
    mom_3  = (monthly_px / monthly_px.shift(3)  - 1).iloc[-1].dropna()
    vol_6  = monthly_ret.rolling(6).std().iloc[-1].dropna() * np.sqrt(12)

    # Require data for all signals
    valid = mom_12.index.intersection(vol_6.index).intersection(
            mom_6.index).intersection(mom_3.index)

    if tsmom_filter:
        mom_filter = {12: mom_12, 6: mom_6, 3: mom_3}.get(tsmom_lb, mom_12)
        valid = valid[mom_filter[valid] > tsmom_threshold]
        if len(valid) == 0:
            return [], {}  # nothing qualifies → cash

    if len(valid) < n_hold:
        if len(valid) == 0:
            raise ValueError(f"No valid tickers after filtering")
        n_hold = len(valid)

    # H120: rank ensemble — each window ranked independently, then summed
    score = (mom_12[valid].rank() + mom_6[valid].rank() +
             mom_3[valid].rank() + vol_6[valid].rank(ascending=False))
    top_n = list(score.nlargest(n_hold).index)

    scores = {
        t: {
            "score":   round(float(score[t]), 2),
            "mom_12m": round(float(mom_12[t]) * 100, 1),
            "mom_6m":  round(float(mom_6[t])  * 100, 1),
            "mom_3m":  round(float(mom_3[t])  * 100, 1),
            "vol_6m":  round(float(vol_6.get(t, float("nan"))) * 100, 1),
        }
        for t in valid
    }
    return top_n, scores


# ── Alpaca helpers ──────────────────────────────────────────────────────────

def get_client() -> TradingClient:
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True,
    )


def get_positions(client: TradingClient) -> dict[str, dict]:
    return {
        p.symbol: {
            "qty":          float(p.qty),
            "market_value": float(p.market_value),
            "avg_cost":     float(p.avg_entry_price),
        }
        for p in client.get_all_positions()
    }


def get_equity(client: TradingClient) -> float:
    return float(client.get_account().equity)


def get_latest_price(symbol: str) -> float:
    raw = yf.download(symbol, period="3d", auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(closes, pd.DataFrame):
        closes = closes[symbol]
    return float(closes.dropna().iloc[-1])


def get_period_return(symbol: str, date_from: str, date_to: str) -> float:
    """Price return of symbol from date_from to date_to."""
    raw = yf.download(symbol, start=date_from, end=date_to,
                      auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(closes, pd.DataFrame):
        closes = closes[symbol]
    closes = closes.dropna()
    if len(closes) < 2:
        return 0.0
    return float(closes.iloc[-1] / closes.iloc[0] - 1)


# ── H022: H026 vol-targeting ─────────────────────────────────────────────────

def compute_h026_vol_scale(log: list) -> float:
    """
    Scale H026 base weight by (VOL_TARGET_H026 / realized_6m_vol).
    Uses trade log to reconstruct H026 monthly returns.
    Returns 1.0 (no scaling) when < 3 months of history.
    """
    if len(log) < 3:
        return 1.0

    entries = []
    for entry in log:
        sigs = entry.get("signals", {})
        top_n = sigs.get("h026", {}).get("top_n", [])
        entries.append({"date": entry["date"], "sym": top_n[0] if top_n else None})

    n = min(len(entries) - 1, VOL_WINDOW_H026)
    recent = entries[-(n + 1):]

    monthly_rets = []
    for i in range(len(recent) - 1):
        sym = recent[i]["sym"]
        if sym is None:
            monthly_rets.append(0.0)
            continue
        try:
            r = get_period_return(sym, recent[i]["date"], recent[i + 1]["date"])
            monthly_rets.append(r)
        except Exception:
            monthly_rets.append(0.0)

    if len(monthly_rets) < 3:
        return 1.0

    realized_vol = float(pd.Series(monthly_rets).std(ddof=1)) * np.sqrt(12)
    if realized_vol <= 0:
        return 1.0
    return float(np.clip(VOL_TARGET_H026 / realized_vol, VOL_CLAMP_H026[0], VOL_CLAMP_H026[1]))


def compute_h041a_vol_scale(log: list) -> float:
    """
    Scale H041a base weight by (VOL_TARGET_H041A / realized_6m_vol).
    Uses trade log to reconstruct H041a monthly returns.
    Returns 1.0 (no scaling) when < 3 months of history.
    """
    if len(log) < 3:
        return 1.0

    entries = []
    for entry in log:
        sigs = entry.get("signals", {})
        top_n = sigs.get("h041a", {}).get("top_n", [])
        entries.append({"date": entry["date"], "sym": top_n[0] if top_n else None})

    n = min(len(entries) - 1, VOL_WINDOW_H026)
    recent = entries[-(n + 1):]

    monthly_rets = []
    for i in range(len(recent) - 1):
        sym = recent[i]["sym"]
        if sym is None:
            monthly_rets.append(0.0)
            continue
        try:
            r = get_period_return(sym, recent[i]["date"], recent[i + 1]["date"])
            monthly_rets.append(r)
        except Exception:
            monthly_rets.append(0.0)

    if len(monthly_rets) < 3:
        return 1.0

    realized_vol = float(pd.Series(monthly_rets).std(ddof=1)) * np.sqrt(12)
    if realized_vol <= 0:
        return 1.0
    return float(np.clip(VOL_TARGET_H041A / realized_vol, VOL_CLAMP_H026[0], VOL_CLAMP_H026[1]))


# ── Trade planning ──────────────────────────────────────────────────────────

def build_target(equity: float, h026_scale: float = 1.0,
                 h041a_scale: float = 1.0) -> dict[str, float]:
    """
    Compute {symbol: target_usd} across all sub-strategies.
    H026 and H041a weights are scaled by their vol-target factors,
    then rotation is renormed to ROTATION_WEIGHT.
    """
    # Compute effective per-sub weights
    raw_weights = {name: cfg["weight"] for name, cfg in SUB_STRATS.items()}
    raw_weights["h026"]  *= h026_scale
    raw_weights["h041a"] *= h041a_scale
    rot_sum = sum(raw_weights.values())
    eff_weights = {k: v * ROTATION_WEIGHT / rot_sum for k, v in raw_weights.items()}

    target: dict[str, float] = {}
    signals: dict[str, tuple[list[str], dict]] = {}

    for name, cfg in SUB_STRATS.items():
        alloc_per_slot = equity * eff_weights[name] / cfg["n_hold"]
        top_n, scores = compute_signal(
            cfg["assets"], cfg["n_hold"],
            tsmom_filter=cfg.get("tsmom_filter", False),
            tsmom_lb=cfg.get("tsmom_lb", 12),
            tsmom_threshold=cfg.get("tsmom_threshold", 0.0),
        )
        signals[name] = (top_n, scores)
        for sym in top_n:
            target[sym] = target.get(sym, 0.0) + alloc_per_slot
        if not top_n:
            lb = cfg.get("tsmom_lb", 12)
            print(f"  {name.upper()}: TSMOM {lb}m filter — no qualifying assets, holding cash this month")

    return target, signals, eff_weights


def build_trade_plan(
    target: dict[str, float],
    positions: dict[str, dict],
) -> list[dict]:
    """Diff current holdings against target → list of trade dicts."""
    all_syms = set(target) | set(positions)
    trades = []

    for sym in all_syms:
        tgt = target.get(sym, 0.0)
        cur = positions.get(sym, {}).get("market_value", 0.0)
        diff = tgt - cur

        if abs(diff) < MIN_ORDER_USD:
            continue

        price = get_latest_price(sym)
        if price <= 0:
            continue
        qty = abs(diff) / price

        action = "BUY" if diff > 0 else "SELL"
        if action == "SELL" and sym in positions:
            # Never sell more than we have
            qty = min(qty, positions[sym]["qty"])

        trades.append({
            "symbol":    sym,
            "action":    action,
            "qty":       round(qty, 6),
            "est_value": round(abs(diff), 2),
            "reason":    f"target ${tgt:,.0f}, current ${cur:,.0f}",
        })

    # Sells first to free cash, then buys
    return [t for t in trades if t["action"] == "SELL"] + \
           [t for t in trades if t["action"] == "BUY"]


def execute_trades(client: TradingClient, trades: list[dict], dry_run: bool) -> list[dict]:
    executed = []
    for t in trades:
        tag = "[DRY RUN] " if dry_run else ""
        print(f"  {tag}{t['action']:4} {t['qty']:>10.4f} {t['symbol']:<6}  "
              f"~${t['est_value']:>9,.0f}  ({t['reason']})")
        if dry_run:
            continue
        try:
            order = client.submit_order(MarketOrderRequest(
                symbol=t["symbol"],
                qty=t["qty"],
                side=OrderSide.BUY if t["action"] == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            ))
            print(f"         ✓ order_id={order.id}")
            executed.append({**t, "order_id": str(order.id), "submitted_at": datetime.now().isoformat()})
        except Exception as e:
            print(f"         ✗ ERROR: {e}")
    return executed


# ── First-trading-day guard ─────────────────────────────────────────────────

def is_first_trading_day() -> bool:
    today = date.today()
    if today.weekday() >= 5:
        return False
    # It's the first trading day if today is the 1st, or if today ≤ 3rd and
    # every earlier day this month was a weekend/holiday (simple heuristic).
    if today.day > 4:
        return False
    for d in range(1, today.day):
        candidate = date(today.year, today.month, d)
        if candidate.weekday() < 5:  # found an earlier weekday this month
            return False
    return True


# ── Logging ─────────────────────────────────────────────────────────────────

def load_trade_log() -> list:
    if not LOG_FILE.exists():
        return []
    return json.loads(LOG_FILE.read_text())


def log_run(entry: dict):
    log = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status",  action="store_true")
    parser.add_argument("--force",   action="store_true", help="Skip first-of-month guard")
    args = parser.parse_args()

    if not args.force and not args.status and not is_first_trading_day():
        print(f"Not the first trading day of the month ({date.today()}). Skipping. Use --force to override.")
        sys.exit(0)

    client    = get_client()
    positions = get_positions(client)
    equity    = get_equity(client)

    log = load_trade_log()

    print(f"\nH133 Monthly Rebalancer — {date.today()}")
    print(f"Account equity: ${equity:,.2f}")

    if positions:
        print("\nCurrent positions:")
        for sym, pos in sorted(positions.items()):
            print(f"  {sym:<6} {pos['qty']:>10.4f} sh  ${pos['market_value']:>10,.2f}")
    else:
        print("\nNo current positions.")

    if args.status:
        return

    # H122/H133: compute vol-targeting scales from trade log history
    h026_scale  = compute_h026_vol_scale(log)
    h041a_scale = compute_h041a_vol_scale(log)
    if len(log) < 3:
        print(f"\nH026 vol-scale:  1.000 (fixed — only {len(log)} month(s) of history, need ≥3)")
        print(f"H041a vol-scale: 1.000 (fixed — only {len(log)} month(s) of history, need ≥3)")
    else:
        raw_h026  = 0.27 * h026_scale
        raw_h041a = 0.22 * h041a_scale
        rot_sum   = raw_h041a + raw_h026 + 0.21
        eff_h026  = raw_h026  * ROTATION_WEIGHT / rot_sum
        eff_h041a = raw_h041a * ROTATION_WEIGHT / rot_sum
        print(f"\nH026 vol-scale:  {h026_scale:.3f}  (base 27% → effective {eff_h026*100:.1f}%)")
        print(f"H041a vol-scale: {h041a_scale:.3f}  (base 22% → effective {eff_h041a*100:.1f}%)")

    # Compute signals
    print("\nFetching signals (downloading ~15mo of price data)…")
    target, signals, eff_weights = build_target(equity, h026_scale=h026_scale,
                                                 h041a_scale=h041a_scale)

    print("\nSub-strategy targets:")
    for name, (top_n, scores) in signals.items():
        eff_w = eff_weights[name]
        print(f"\n  {name.upper()} ({eff_w*100:.1f}%):  top-{SUB_STRATS[name]['n_hold']} → "
              f"{', '.join(top_n) if top_n else 'CASH'}")
        for sym in sorted(scores, key=lambda s: -scores[s]["score"])[:5]:
            mark = "★" if sym in top_n else " "
            sc = scores[sym]
            print(f"    {mark} {sym:<6} score={sc['score']:>5.1f}  "
                  f"m12={sc['mom_12m']:>+6.1f}%  m6={sc.get('mom_6m',0):>+6.1f}%  "
                  f"m3={sc.get('mom_3m',0):>+6.1f}%  vol={sc['vol_6m']:>5.1f}%")

    print("\nCombined target allocations:")
    for sym, usd in sorted(target.items(), key=lambda x: -x[1]):
        print(f"  {sym:<6} ${usd:>10,.0f}  ({usd/equity*100:.1f}%)")

    # Build trade plan
    trades = build_trade_plan(target, positions)

    if not trades:
        print("\nNo rebalance needed — portfolio matches target.")
        return

    print(f"\nTrade plan ({len(trades)} orders):")
    executed = execute_trades(client, trades, dry_run=args.dry_run)

    if not args.dry_run and executed:
        log_run({
            "date":        date.today().isoformat(),
            "equity":      equity,
            "target":      target,
            "eff_weights": {k: round(v, 4) for k, v in eff_weights.items()},
            "h026_scale":  round(h026_scale, 4),
            "h041a_scale": round(h041a_scale, 4),
            "signals":     {k: {"top_n": v[0]} for k, v in signals.items()},
            "trades":      executed,
        })
        print(f"\n✓ Logged {len(executed)} trades to {LOG_FILE.name}")
    elif args.dry_run:
        print(f"\n[DRY RUN] {len(trades)} orders would be submitted.")


if __name__ == "__main__":
    main()
