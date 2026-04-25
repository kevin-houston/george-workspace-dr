"""
ORB backtest engine.

Simulates trade-by-trade P&L for both exit modes:
  - hl_mode:  stop at range low (long) / range high (short); target = 10R
  - atr_mode: stop at entry ± (ATR14 × 0.05); close at 15:55 ET if not stopped

Position sizing: risk 1% of equity per trade, max 4× leverage.
Commission: $0.0035/share/side (as used in the reference article).
"""

import numpy as np
import pandas as pd
import pytz

ET = pytz.timezone("America/New_York")
COMMISSION_PER_SHARE = 0.0035
RISK_PER_TRADE = 0.01
MAX_LEVERAGE = 4.0
EOD_EXIT_TIME = pd.Timestamp("15:55").time()


def _compute_atr14(bars: pd.DataFrame, day: object) -> float:
    """14-day ATR from daily OHLC derived from 1-min bars, looking back from day."""
    daily = bars.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    daily = daily[daily.index.date < day]
    if len(daily) < 14:
        return float("nan")
    tr = pd.concat([
        daily["high"] - daily["low"],
        (daily["high"] - daily["close"].shift()).abs(),
        (daily["low"] - daily["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.tail(14).mean()


def simulate(
    signal_records: list,
    bars_utc: pd.DataFrame,
    mode: str = "hl",
    starting_equity: float = 25_000.0,
) -> pd.DataFrame:
    """
    signal_records: list of dicts from signals.generate_signals (includes session_bars).
    bars_utc: full 1-min bar DataFrame (UTC index) — used for ATR calculation.
    mode: 'hl' or 'atr'
    Returns per-trade DataFrame.
    """
    assert mode in ("hl", "atr"), "mode must be 'hl' or 'atr'"

    bars_et = bars_utc.copy()
    bars_et.index = bars_et.index.tz_convert(ET)

    equity = starting_equity
    trades = []

    for rec in signal_records:
        if rec["signal"] == 0:
            continue

        day = rec["date"]
        direction = rec["signal"]
        entry_price = rec["entry_price"]
        range_high = rec["range_high"]
        range_low = rec["range_low"]
        session = rec["session_bars"]

        # Determine stop distance
        if mode == "hl":
            if direction == 1:
                stop_price = range_low
            else:
                stop_price = range_high
            stop_distance = abs(entry_price - stop_price)
            target_distance = stop_distance * 10  # 10R
            target_price = entry_price + direction * target_distance
        else:  # atr
            atr14 = _compute_atr14(bars_et, day)
            if np.isnan(atr14) or atr14 <= 0:
                continue
            stop_distance = atr14 * 0.05
            stop_price = entry_price - direction * stop_distance
            target_price = None  # EOD exit

        if stop_distance <= 0:
            continue

        # Position sizing
        risk_dollars = equity * RISK_PER_TRADE
        shares = risk_dollars / stop_distance
        max_shares = (equity * MAX_LEVERAGE) / entry_price
        shares = min(shares, max_shares)
        shares = int(shares)
        if shares < 1:
            continue

        # Simulate bar-by-bar exit
        exit_price = None
        exit_reason = None
        post_entry = session[session.index > rec["bar6_time"]]

        for ts, bar in post_entry.iterrows():
            if ts.time() >= EOD_EXIT_TIME:
                exit_price = bar["open"]
                exit_reason = "eod"
                break

            if mode == "hl":
                if direction == 1:
                    if bar["low"] <= stop_price:
                        exit_price = stop_price
                        exit_reason = "stop"
                        break
                    if bar["high"] >= target_price:
                        exit_price = target_price
                        exit_reason = "target"
                        break
                else:
                    if bar["high"] >= stop_price:
                        exit_price = stop_price
                        exit_reason = "stop"
                        break
                    if bar["low"] <= target_price:
                        exit_price = target_price
                        exit_reason = "target"
                        break
            else:  # atr
                if direction == 1:
                    if bar["low"] <= stop_price:
                        exit_price = stop_price
                        exit_reason = "stop"
                        break
                else:
                    if bar["high"] >= stop_price:
                        exit_price = stop_price
                        exit_reason = "stop"
                        break

        if exit_price is None:
            # EOD — use last bar close
            if len(post_entry) > 0:
                exit_price = post_entry.iloc[-1]["close"]
                exit_reason = "eod"
            else:
                continue

        pnl_per_share = direction * (exit_price - entry_price)
        gross_pnl = pnl_per_share * shares
        commission = COMMISSION_PER_SHARE * shares * 2  # entry + exit
        net_pnl = gross_pnl - commission
        equity += net_pnl

        trades.append({
            "date": day,
            "direction": "long" if direction == 1 else "short",
            "entry": entry_price,
            "exit": exit_price,
            "stop": stop_price,
            "shares": shares,
            "gross_pnl": gross_pnl,
            "commission": commission,
            "net_pnl": net_pnl,
            "equity": equity,
            "exit_reason": exit_reason,
            "mode": mode,
        })

    return pd.DataFrame(trades)
