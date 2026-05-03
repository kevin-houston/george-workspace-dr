#!/usr/bin/env python3
"""
lev_etf_v2.py — Leveraged ETF Strategy Trade Logger (Framework v2)
====================================================================
Replays all leveraged ETF strategy variants from lev_etf_harness.py
and logs individual trades via TradeLogger.

Strategy variants (one logger each):
  lev_etf_short_both_sides         — short equal notional TQQQ+SQQQ / UPRO+SPXU
  lev_etf_short_lev_long_underlying — short TQQQ long QQQ (decay capture)
  lev_etf_vix_regime               — short both sides only when VIX < 20
  lev_etf_momentum                 — long UPRO/SPY when SPY > 50d MA, else IEF
  lev_etf_rebalancing_band         — short both sides with drift-triggered rebalance

round_num=1, category='leveraged_etf'

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/lev_etf_v2.py
"""

import sys
import os
from pathlib import Path

# ── sys.path setup ─────────────────────────────────────────────────────────────
FRAMEWORK_DIR = Path(__file__).parent
EVAL_DIR      = FRAMEWORK_DIR.parent
sys.path.insert(0, str(FRAMEWORK_DIR))
sys.path.insert(0, str(EVAL_DIR))

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

from base_harness import TradeLogger, fetch_data, get_close

# ── Configuration ──────────────────────────────────────────────────────────────
START_DATE = "2015-01-01"
END_DATE   = "2025-01-01"
BORROW_COST_ANNUAL = 0.01   # 1% annual borrow cost for leveraged ETF shorts

UNIVERSE = {
    "3x_bull": ["TQQQ", "UPRO", "TECL", "SOXL", "FAS"],
    "3x_bear": ["SQQQ", "SPXU"],
    "2x":      ["QLD", "SSO"],
    "underlying": ["QQQ", "SPY"],
    "vol":     ["VXX", "UVXY"],
    "other":   ["IEF"],
}
ALL_TICKERS = (
    UNIVERSE["3x_bull"] + UNIVERSE["3x_bear"] +
    UNIVERSE["2x"] + UNIVERSE["underlying"] +
    UNIVERSE["vol"] + UNIVERSE["other"] + ["^VIX"]
)

ROUND_NUM = 1

# ── Data Fetching ──────────────────────────────────────────────────────────────
def fetch_prices(tickers, start=START_DATE, end=END_DATE, retries=3):
    print(f"Fetching {len(tickers)} tickers from {start} to {end} ...")
    import time
    all_dfs = []
    batch_size = 5
    batches = [tickers[i:i+batch_size] for i in range(0, len(tickers), batch_size)]
    for batch in batches:
        for attempt in range(retries):
            try:
                raw = yf.download(batch, start=start, end=end, auto_adjust=True, progress=False)
                if isinstance(raw.columns, pd.MultiIndex):
                    sub = raw["Close"]
                elif "Close" in raw.columns:
                    sub = raw[["Close"]]
                    sub.columns = batch[:1]
                else:
                    sub = raw
                sub = sub.dropna(how="all")
                # Flatten MultiIndex column names
                if hasattr(sub.columns, 'tolist'):
                    sub.columns = [c if isinstance(c, str) else c[0] for c in sub.columns]
                all_dfs.append(sub)
                break
            except Exception as e:
                print(f"  Batch {batch} attempt {attempt+1} failed: {e}")
                time.sleep(2)
    if not all_dfs:
        raise RuntimeError("All data fetches failed")
    prices = pd.concat(all_dfs, axis=1)
    prices = prices.loc[:, ~prices.columns.duplicated()]
    prices.index = pd.to_datetime(prices.index)
    prices = prices.dropna(how="all")
    print(f"  Got {prices.shape[0]} rows, {prices.shape[1]} cols")
    print(f"  Columns: {list(prices.columns)}")
    return prices

def annual_borrow_cost_daily():
    return BORROW_COST_ANNUAL / 252

# ── Monthly resampling helper ──────────────────────────────────────────────────
def _month_ends(index):
    """Return end-of-month dates present in index."""
    return pd.Series(index=index, dtype=float).resample('ME').last().index

# ── Strategy 1: Short Both Sides (TQQQ + SQQQ) ───────────────────────────────
def run_short_both_sides(prices, logger):
    """
    Short equal dollar notional of TQQQ and SQQQ simultaneously.
    Monthly rebalance.  Logs each monthly period as a trade.
    """
    pairs = [("TQQQ", "SQQQ"), ("UPRO", "SPXU")]
    bc    = annual_borrow_cost_daily()
    n_logged = 0

    for bull, bear in pairs:
        if bull not in prices.columns or bear not in prices.columns:
            print(f"  Skipping {bull}/{bear}: data missing")
            continue

        df = prices[[bull, bear]].dropna()
        rb = df.pct_change()

        # Month-end rebalance dates
        me_dates = _month_ends(df.index)

        for i in range(len(me_dates) - 1):
            entry_dt = me_dates[i]
            exit_dt  = me_dates[i + 1]

            mask    = (rb.index > entry_dt) & (rb.index <= exit_dt)
            period  = rb.loc[mask]
            if period.empty:
                continue

            # Short both: daily P&L = -(return) - borrow
            pnl_bull = -period[bull] - bc
            pnl_bear = -period[bear] - bc
            pnl      = 0.5 * pnl_bull + 0.5 * pnl_bear
            cum_ret  = float((1 + pnl).prod() - 1)
            hold_d   = len(period)

            entry_p_bull = float(prices[bull].asof(entry_dt))
            exit_p_bull  = float(prices[bull].asof(exit_dt))
            entry_p_bear = float(prices[bear].asof(entry_dt))
            exit_p_bear  = float(prices[bear].asof(exit_dt))

            spy_ret = prices["SPY"].pct_change().reindex(period.index).dropna()
            if len(spy_ret) >= 2:
                common = pnl.index.intersection(spy_ret.index)
                spy_corr_val = float(pnl.loc[common].corr(spy_ret.loc[common])) if len(common) > 2 else float('nan')
            else:
                spy_corr_val = float('nan')

            logger.log(
                ticker        = f'{bull}/{bear}',
                entry_date    = entry_dt,
                exit_date     = exit_dt,
                return_pct    = cum_ret,
                hold_days     = hold_d,
                direction     = 'short_both',
                entry_price   = entry_p_bull,
                exit_price    = exit_p_bull,
                params        = {
                    'strategy':          'short_both_sides',
                    'bull':              bull,
                    'bear':              bear,
                    'borrow_cost_annual': BORROW_COST_ANNUAL,
                    'rebalance':         'monthly',
                },
                notes         = (
                    f"short {bull}+{bear}; "
                    f"entry_p_{bear}={entry_p_bear:.2f}; "
                    f"exit_p_{bear}={exit_p_bear:.2f}"
                ),
                bull          = bull,
                bear          = bear,
                entry_price_bear = entry_p_bear,
                exit_price_bear  = exit_p_bear,
                spy_corr      = spy_corr_val,
            )
            n_logged += 1

    print(f"  short_both_sides: {n_logged} trades logged")

# ── Strategy 2: Short Leveraged + Long Underlying ────────────────────────────
def run_short_lev_long_underlying(prices, logger):
    """
    Short TQQQ, Long QQQ (equal notional) — pure decay capture.
    Logs monthly periods as trades.
    """
    pairs = [("TQQQ", "QQQ"), ("UPRO", "SPY")]
    bc    = annual_borrow_cost_daily()
    n_logged = 0

    for lev, und in pairs:
        if lev not in prices.columns or und not in prices.columns:
            continue

        df = prices[[lev, und]].dropna()
        rb = df.pct_change().dropna()

        me_dates = _month_ends(df.index)

        for i in range(len(me_dates) - 1):
            entry_dt = me_dates[i]
            exit_dt  = me_dates[i + 1]

            mask   = (rb.index > entry_dt) & (rb.index <= exit_dt)
            period = rb.loc[mask]
            if period.empty:
                continue

            # Short lev, long underlying — equal dollar
            pnl     = -period[lev] - bc + period[und]
            cum_ret = float((1 + pnl).prod() - 1)
            hold_d  = len(period)

            entry_p_lev = float(prices[lev].asof(entry_dt))
            exit_p_lev  = float(prices[lev].asof(exit_dt))
            entry_p_und = float(prices[und].asof(entry_dt))
            exit_p_und  = float(prices[und].asof(exit_dt))

            logger.log(
                ticker          = f'short_{lev}_long_{und}',
                entry_date      = entry_dt,
                exit_date       = exit_dt,
                return_pct      = cum_ret,
                hold_days       = hold_d,
                direction       = 'short_lev_long_underlying',
                entry_price     = entry_p_lev,
                exit_price      = exit_p_lev,
                params          = {
                    'strategy':          'short_lev_long_underlying',
                    'leveraged_etf':     lev,
                    'underlying':        und,
                    'borrow_cost_annual': BORROW_COST_ANNUAL,
                    'rebalance':         'monthly',
                },
                notes           = (
                    f"short {lev} / long {und}; "
                    f"entry_p_{und}={entry_p_und:.2f}; "
                    f"exit_p_{und}={exit_p_und:.2f}"
                ),
                leveraged_etf    = lev,
                underlying       = und,
                entry_price_und  = entry_p_und,
                exit_price_und   = exit_p_und,
            )
            n_logged += 1

    print(f"  short_lev_long_underlying: {n_logged} trades logged")

# ── Strategy 3: VIX Regime Filter ────────────────────────────────────────────
def run_vix_regime(prices, logger):
    """
    Short TQQQ+SQQQ only when VIX < 20.
    Close shorts when VIX > 25.
    Logs each continuous in-trade segment as one trade.
    """
    if "^VIX" not in prices.columns:
        print("  VIX data not available, skipping regime strategy")
        return

    pairs = [("TQQQ", "SQQQ")]
    bc    = annual_borrow_cost_daily()
    n_logged = 0

    for bull, bear in pairs:
        if bull not in prices.columns or bear not in prices.columns:
            continue

        df  = prices[[bull, bear, "^VIX"]].dropna()
        rb  = df[[bull, bear]].pct_change()
        vx  = df["^VIX"]

        # Build daily signal
        signal = pd.Series(0.0, index=df.index)
        in_trade = False
        for i, date in enumerate(df.index):
            v = vx.iloc[i]
            if not in_trade and v < 20:
                in_trade = True
            elif in_trade and v > 25:
                in_trade = False
            signal.iloc[i] = 1.0 if in_trade else 0.0

        # Identify contiguous in-trade segments
        sig_shifted = signal.shift(1).fillna(0)
        transitions = sig_shifted.diff().fillna(0)
        starts = df.index[transitions == 1].tolist()
        ends   = df.index[transitions == -1].tolist()

        # Handle case where signal never drops to 0 at end
        if len(starts) > len(ends):
            ends.append(df.index[-1])

        for entry_dt, exit_dt in zip(starts, ends):
            mask   = (rb.index >= entry_dt) & (rb.index < exit_dt)
            period = rb.loc[mask]
            if period.empty:
                continue

            base_pnl = -0.5 * period[bull] - bc - 0.5 * period[bear] - bc
            cum_ret  = float((1 + base_pnl).prod() - 1)
            hold_d   = len(period)

            entry_p_bull = float(prices[bull].asof(entry_dt))
            exit_p_bull  = float(prices[bull].asof(exit_dt))
            entry_p_bear = float(prices[bear].asof(entry_dt))
            exit_p_bear  = float(prices[bear].asof(exit_dt))
            vix_at_entry = float(vx.asof(entry_dt))
            vix_at_exit  = float(vx.asof(exit_dt))

            spy_ret = prices["SPY"].pct_change().reindex(period.index).dropna()
            common  = base_pnl.index.intersection(spy_ret.index)
            spy_corr_val = (float(base_pnl.loc[common].corr(spy_ret.loc[common]))
                            if len(common) > 2 else float('nan'))

            logger.log(
                ticker          = f'{bull}/{bear}',
                entry_date      = entry_dt,
                exit_date       = exit_dt,
                return_pct      = cum_ret,
                hold_days       = hold_d,
                direction       = 'short_both',
                entry_price     = entry_p_bull,
                exit_price      = exit_p_bull,
                params          = {
                    'strategy':          'vix_regime_short_both',
                    'bull':              bull,
                    'bear':              bear,
                    'vix_entry_thresh':  20,
                    'vix_exit_thresh':   25,
                    'borrow_cost_annual': BORROW_COST_ANNUAL,
                },
                notes           = (
                    f"vix_entry={vix_at_entry:.1f}; vix_exit={vix_at_exit:.1f}"
                ),
                bull             = bull,
                bear             = bear,
                entry_price_bear = entry_p_bear,
                exit_price_bear  = exit_p_bear,
                vix_at_entry     = vix_at_entry,
                vix_at_exit      = vix_at_exit,
                spy_corr         = spy_corr_val,
            )
            n_logged += 1

    print(f"  vix_regime: {n_logged} trades logged")

# ── Strategy 4: Momentum on Leveraged ETFs ───────────────────────────────────
def run_momentum_lev(prices, logger):
    """
    When SPY > 50d MA: long UPRO.
    When SPY < 50d MA: long IEF.
    Also logs the base_momentum (SPY vs IEF) variant.
    Logs each continuous same-signal segment as one trade.
    """
    if "SPY" not in prices.columns or "UPRO" not in prices.columns:
        return

    spy  = prices["SPY"]
    upro = prices["UPRO"] if "UPRO" in prices.columns else None
    ief  = prices["IEF"]  if "IEF"  in prices.columns else None

    ma50  = spy.rolling(50).mean()
    above = (spy > ma50).shift(1)  # signal from prior day

    variants = []
    if upro is not None and ief is not None:
        variants.append(("lev_momentum_UPRO_IEF", upro, ief))
    if ief is not None:
        variants.append(("base_momentum_SPY_IEF", spy, ief))

    n_logged = 0
    for name, risky, safe in variants:
        risky_r = risky.pct_change()
        safe_r  = safe.pct_change() if safe is not None else pd.Series(0.0, index=risky.index)

        common = risky_r.index.intersection(safe_r.index).intersection(above.index)
        sig    = above.reindex(common).fillna(False)

        # Find contiguous segments by signal value
        seg_start   = None
        seg_signal  = None
        prev_sig    = None
        segments    = []

        for date in common:
            cur_sig = bool(sig.loc[date])
            if prev_sig is None:
                seg_start  = date
                seg_signal = cur_sig
            elif cur_sig != prev_sig:
                segments.append((seg_start, date, seg_signal))
                seg_start  = date
                seg_signal = cur_sig
            prev_sig = cur_sig

        if seg_start is not None and prev_sig is not None:
            segments.append((seg_start, common[-1], seg_signal))

        for entry_dt, exit_dt, in_risky in segments:
            mask   = (common >= entry_dt) & (common < exit_dt)
            period = common[mask]
            if len(period) == 0:
                continue

            chosen_r = risky_r.reindex(period) if in_risky else safe_r.reindex(period)
            pnl      = chosen_r.dropna()
            if len(pnl) == 0:
                continue

            cum_ret  = float((1 + pnl).prod() - 1)
            hold_d   = len(pnl)
            chosen   = (risky.name if hasattr(risky, 'name') and risky.name else
                        ('UPRO' if 'UPRO' in name else 'SPY')) if in_risky else 'IEF'

            entry_price = float(risky.asof(entry_dt) if in_risky else
                                 (safe.asof(entry_dt) if safe is not None else float('nan')))
            exit_price  = float(risky.asof(exit_dt) if in_risky else
                                 (safe.asof(exit_dt) if safe is not None else float('nan')))

            spy_ma_at_entry = float(ma50.asof(entry_dt))
            spy_at_entry    = float(spy.asof(entry_dt))

            logger.log(
                ticker          = chosen,
                entry_date      = entry_dt,
                exit_date       = exit_dt,
                return_pct      = cum_ret,
                hold_days       = hold_d,
                direction       = 'long',
                entry_price     = entry_price,
                exit_price      = exit_price,
                params          = {
                    'strategy':    name,
                    'signal':      'SPY vs 50d MA',
                    'risky_asset': 'UPRO' if 'UPRO' in name else 'SPY',
                    'safe_asset':  'IEF',
                },
                notes           = (
                    f"in_risky={in_risky}; chosen={chosen}; "
                    f"spy={spy_at_entry:.2f}; spy_ma50={spy_ma_at_entry:.2f}"
                ),
                variant_name     = name,
                in_risky         = bool(in_risky),
                spy_at_entry     = spy_at_entry,
                spy_ma50_at_entry = spy_ma_at_entry,
            )
            n_logged += 1

    print(f"  momentum_lev: {n_logged} trades logged")

# ── Strategy 5: Rebalancing Band (TQQQ + SQQQ) ───────────────────────────────
def run_rebalancing_band(prices, logger, band=0.20):
    """
    Hold TQQQ + SQQQ (short both) in equal dollar weights.
    Rebalance only when one side drifts > 20% from equal weight.
    Logs each inter-rebalance segment as a trade.
    """
    pairs = [("TQQQ", "SQQQ")]
    bc    = annual_borrow_cost_daily()
    n_logged = 0

    for bull, bear in pairs:
        if bull not in prices.columns or bear not in prices.columns:
            continue

        df = prices[[bull, bear]].dropna()
        rb = df.pct_change().fillna(0)

        w_bull = -0.5
        w_bear = -0.5

        seg_start = df.index[0]
        seg_pnl   = []

        for i in range(1, len(df)):
            r_bull = rb[bull].iloc[i]
            r_bear = rb[bear].iloc[i]
            date   = df.index[i]

            # P&L this day
            p = w_bull * r_bull + w_bear * r_bear - bc * (abs(w_bull) + abs(w_bear))
            seg_pnl.append((date, p))

            # Update weights (mark to market)
            w_bull *= (1 + r_bull)
            w_bear *= (1 + r_bear)

            # Check drift
            total    = abs(w_bull) + abs(w_bear)
            rebal    = False
            if total > 0:
                frac_bull = abs(w_bull) / total
                if abs(frac_bull - 0.5) > band:
                    rebal = True

            if rebal and len(seg_pnl) > 0:
                # Close current segment
                seg_dates = [d for d, _ in seg_pnl]
                seg_rets  = pd.Series([r for _, r in seg_pnl], index=seg_dates)
                cum_ret   = float((1 + seg_rets).prod() - 1)
                hold_d    = len(seg_rets)

                entry_p_bull = float(prices[bull].asof(seg_start))
                exit_p_bull  = float(prices[bull].iloc[i])
                entry_p_bear = float(prices[bear].asof(seg_start))
                exit_p_bear  = float(prices[bear].iloc[i])

                logger.log(
                    ticker          = f'{bull}/{bear}',
                    entry_date      = seg_start,
                    exit_date       = date,
                    return_pct      = cum_ret,
                    hold_days       = hold_d,
                    direction       = 'short_both',
                    entry_price     = entry_p_bull,
                    exit_price      = exit_p_bull,
                    params          = {
                        'strategy':          'rebalancing_band',
                        'bull':              bull,
                        'bear':              bear,
                        'band':              band,
                        'borrow_cost_annual': BORROW_COST_ANNUAL,
                    },
                    notes           = (
                        f"rebalanced due to drift; "
                        f"entry_p_{bear}={entry_p_bear:.2f}; "
                        f"exit_p_{bear}={exit_p_bear:.2f}"
                    ),
                    bull             = bull,
                    bear             = bear,
                    entry_price_bear = entry_p_bear,
                    exit_price_bear  = exit_p_bear,
                    rebal_trigger    = 'drift',
                    band             = band,
                )
                n_logged += 1

                # Reset segment
                w_bull    = -total / 2
                w_bear    = -total / 2
                seg_start = date
                seg_pnl   = []

        # Log final open segment if any
        if len(seg_pnl) > 0:
            seg_dates = [d for d, _ in seg_pnl]
            seg_rets  = pd.Series([r for _, r in seg_pnl], index=seg_dates)
            cum_ret   = float((1 + seg_rets).prod() - 1)
            hold_d    = len(seg_rets)

            entry_p_bull = float(prices[bull].asof(seg_start))
            exit_p_bull  = float(prices[bull].iloc[-1])
            entry_p_bear = float(prices[bear].asof(seg_start))
            exit_p_bear  = float(prices[bear].iloc[-1])

            logger.log(
                ticker          = f'{bull}/{bear}',
                entry_date      = seg_start,
                exit_date       = df.index[-1],
                return_pct      = cum_ret,
                hold_days       = hold_d,
                direction       = 'short_both',
                entry_price     = entry_p_bull,
                exit_price      = exit_p_bull,
                params          = {
                    'strategy':          'rebalancing_band',
                    'bull':              bull,
                    'bear':              bear,
                    'band':              band,
                    'borrow_cost_annual': BORROW_COST_ANNUAL,
                },
                notes           = "final open segment (end of data)",
                bull             = bull,
                bear             = bear,
                entry_price_bear = entry_p_bear,
                exit_price_bear  = exit_p_bear,
                rebal_trigger    = 'end_of_data',
                band             = band,
            )
            n_logged += 1

    print(f"  rebalancing_band: {n_logged} trades logged")

# ── Main Execution ─────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Leveraged ETF Strategy Harness v2 — Trade Logger")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 60)

    # Fetch all price data
    prices = fetch_prices(ALL_TICKERS)

    if "^VIX" in prices.columns:
        print(f"  VIX data available: {prices['^VIX'].dropna().shape[0]} rows")

    # One TradeLogger per strategy
    loggers = {
        'short_both_sides':          TradeLogger(round_num=ROUND_NUM, strategy='lev_etf_short_both_sides',          category='leveraged_etf'),
        'short_lev_long_underlying': TradeLogger(round_num=ROUND_NUM, strategy='lev_etf_short_lev_long_underlying', category='leveraged_etf'),
        'vix_regime':                TradeLogger(round_num=ROUND_NUM, strategy='lev_etf_vix_regime',                category='leveraged_etf'),
        'momentum':                  TradeLogger(round_num=ROUND_NUM, strategy='lev_etf_momentum',                  category='leveraged_etf'),
        'rebalancing_band':          TradeLogger(round_num=ROUND_NUM, strategy='lev_etf_rebalancing_band',          category='leveraged_etf'),
    }

    print("\n--- Strategy 1: Short Both Sides ---")
    try:
        run_short_both_sides(prices, loggers['short_both_sides'])
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- Strategy 2: Short Lev + Long Underlying ---")
    try:
        run_short_lev_long_underlying(prices, loggers['short_lev_long_underlying'])
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- Strategy 3: VIX Regime Filter ---")
    try:
        run_vix_regime(prices, loggers['vix_regime'])
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- Strategy 4: Momentum on Leveraged ETFs ---")
    try:
        run_momentum_lev(prices, loggers['momentum'])
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n--- Strategy 5: Rebalancing Band ---")
    try:
        run_rebalancing_band(prices, loggers['rebalancing_band'])
    except Exception as e:
        print(f"  ERROR: {e}")

    # Save all trade logs
    print("\nSaving trade logs...")
    for key, logger in loggers.items():
        logger.save()

    print("\nDone.")
    for key, logger in loggers.items():
        print(f"  {key}: {len(logger)} trades")

if __name__ == '__main__':
    main()
