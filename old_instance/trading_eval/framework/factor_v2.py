#!/usr/bin/env python3
"""
factor_v2.py — Factor Investing & Seasonal/Calendar Effects
NanoClaw Trading Eval Framework v2

Preserves exact strategy logic from factor_seasonal_harness.py.
Logs individual trades via TradeLogger instead of computing metrics.
"""

import sys
import os

# Ensure framework dir is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '/tmp/eval_deps')

import glob
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, date
from scipy import stats

warnings.filterwarnings('ignore')

from framework.base_harness import TradeLogger, fetch_data, get_close

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_DIR = '/workspace/group/trading_eval/cache'
START     = '2015-01-01'
END       = datetime.today().strftime('%Y-%m-%d')

UNIVERSE = [
    'AAPL','MSFT','GOOGL','META','AMZN','NVDA','TSLA',
    'JPM','BAC','GS','WFC',
    'XOM','CVX','COP','HAL',
    'LMT','RTX','NOC','GD',
    'WMT','COST','KO','PEP','PG',
    'JNJ','LLY','MRK','PFE','UNH',
    'CAT','DE','GE','UPS','BA','F','GM',
    'NKE','MO','BRK-B'
]

# US market holidays (approximate, fixed + observed)
HOLIDAYS = {
    # New Year's
    **{date(y, 1, 1): 'New Year' for y in range(2014, 2027)},
    # MLK (3rd Monday Jan)
    date(2015,1,19):'MLK', date(2016,1,18):'MLK', date(2017,1,16):'MLK',
    date(2018,1,15):'MLK', date(2019,1,21):'MLK', date(2020,1,20):'MLK',
    date(2021,1,18):'MLK', date(2022,1,17):'MLK', date(2023,1,16):'MLK',
    date(2024,1,15):'MLK', date(2025,1,20):'MLK', date(2026,1,19):'MLK',
    # Presidents Day (3rd Monday Feb)
    date(2015,2,16):'Presidents', date(2016,2,15):'Presidents',
    date(2017,2,20):'Presidents', date(2018,2,19):'Presidents',
    date(2019,2,18):'Presidents', date(2020,2,17):'Presidents',
    date(2021,2,15):'Presidents', date(2022,2,21):'Presidents',
    date(2023,2,20):'Presidents', date(2024,2,19):'Presidents',
    date(2025,2,17):'Presidents', date(2026,2,16):'Presidents',
    # Memorial Day (last Monday May)
    date(2015,5,25):'Memorial', date(2016,5,30):'Memorial',
    date(2017,5,29):'Memorial', date(2018,5,28):'Memorial',
    date(2019,5,27):'Memorial', date(2020,5,25):'Memorial',
    date(2021,5,31):'Memorial', date(2022,5,30):'Memorial',
    date(2023,5,29):'Memorial', date(2024,5,27):'Memorial',
    date(2025,5,26):'Memorial', date(2026,5,25):'Memorial',
    # Independence Day
    **{date(y, 7, 4): 'Independence' for y in range(2014, 2027)},
    # Labor Day (1st Monday Sep)
    date(2015,9,7):'Labor', date(2016,9,5):'Labor', date(2017,9,4):'Labor',
    date(2018,9,3):'Labor', date(2019,9,2):'Labor', date(2020,9,7):'Labor',
    date(2021,9,6):'Labor', date(2022,9,5):'Labor', date(2023,9,4):'Labor',
    date(2024,9,2):'Labor', date(2025,9,1):'Labor', date(2026,9,7):'Labor',
    # Thanksgiving (4th Thursday Nov)
    date(2015,11,26):'Thanksgiving', date(2016,11,24):'Thanksgiving',
    date(2017,11,23):'Thanksgiving', date(2018,11,22):'Thanksgiving',
    date(2019,11,28):'Thanksgiving', date(2020,11,26):'Thanksgiving',
    date(2021,11,25):'Thanksgiving', date(2022,11,24):'Thanksgiving',
    date(2023,11,23):'Thanksgiving', date(2024,11,28):'Thanksgiving',
    date(2025,11,27):'Thanksgiving', date(2026,11,26):'Thanksgiving',
    # Christmas
    **{date(y,12,25): 'Christmas' for y in range(2014, 2027)},
}


# ── Data Loading ──────────────────────────────────────────────────────────────
def load_symbol(sym):
    """Load price data from cache or yfinance."""
    cache_key = sym.replace('-', '_')
    pattern  = os.path.join(CACHE_DIR, f'ohlcv_{cache_key}_*.pkl')
    matches  = glob.glob(pattern)
    pattern2 = os.path.join(CACHE_DIR, f'{cache_key}_15yr.pkl')
    matches2 = glob.glob(pattern2)

    if matches:
        df = pd.read_pickle(matches[0])
    elif matches2:
        df = pd.read_pickle(matches2[0])
    else:
        try:
            import yfinance as yf
            ticker = yf.Ticker(sym)
            df = ticker.history(start=START, end=END, auto_adjust=True)
            if df.empty:
                return None
        except Exception as e:
            print(f"  Failed to download {sym}: {e}")
            return None

    df.columns = [c.lower() for c in df.columns]
    if 'adj close' in df.columns:
        df = df.rename(columns={'adj close': 'close'})

    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df[df.index >= START]
    df = df[['close']].dropna()
    return df


# ── Factor helpers ─────────────────────────────────────────────────────────────
def zscore_cs(series):
    """Cross-sectional z-score (demean, scale by std)."""
    m = series.mean()
    s = series.std()
    if s == 0 or np.isnan(s):
        return pd.Series(np.nan, index=series.index)
    return (series - m) / s


def combine_scores(score_dict_a, score_dict_b, weight_a=0.5, weight_b=0.5):
    """Combine two factor score dicts by equal-weighting z-scores."""
    combined = {}
    all_dates = set(score_dict_a.keys()) | set(score_dict_b.keys())
    for d in all_dates:
        a = score_dict_a.get(d, pd.Series(dtype=float))
        b = score_dict_b.get(d, pd.Series(dtype=float))
        idx = a.index.union(b.index)
        a = a.reindex(idx)
        b = b.reindex(idx)
        combined[d] = (a.fillna(0) * weight_a + b.fillna(0) * weight_b)
        valid = a.notna() & b.notna()
        combined[d] = combined[d][valid]
    return combined


def combine_all_scores(*score_dicts):
    all_dates = set()
    for d in score_dicts:
        all_dates |= set(d.keys())
    combined = {}
    for dt in all_dates:
        parts = [d.get(dt, pd.Series(dtype=float)) for d in score_dicts]
        idx = parts[0].index
        for p in parts[1:]:
            idx = idx.union(p.index)
        stacked = pd.DataFrame({i: p.reindex(idx) for i, p in enumerate(parts)})
        valid_mask = stacked.notna().sum(axis=1) >= 4
        combined[dt] = stacked[valid_mask].mean(axis=1, skipna=True)
    return combined


# ── Factor backtest with trade logging ───────────────────────────────────────
def factor_backtest_log(factor_scores_monthly, factor_name, close, returns,
                        loaded_syms, logger, round_num):
    """
    Run long-short quintile backtest and log per-trade records.
    One record per (stock, rebalance_period, direction) tuple.
    """
    all_dates = returns.index
    monthly_dates = sorted(factor_scores_monthly.keys())

    for i, rebal_date in enumerate(monthly_dates):
        scores = factor_scores_monthly[rebal_date].dropna()
        if len(scores) < 20:
            continue

        n_q = max(1, len(scores) // 5)
        long_stocks  = scores.nlargest(n_q).index.tolist()
        short_stocks = scores.nsmallest(n_q).index.tolist()

        if i + 1 < len(monthly_dates):
            next_rebal = monthly_dates[i + 1]
        else:
            next_rebal = all_dates[-1]

        mask = (all_dates > rebal_date) & (all_dates <= next_rebal)
        window_dates = all_dates[mask]

        if len(window_dates) == 0:
            continue

        entry_date = rebal_date
        exit_date  = window_dates[-1]
        hold_days  = len(window_dates)

        for sym in long_stocks:
            if sym not in close.columns:
                continue
            try:
                ep = close.loc[entry_date, sym] if entry_date in close.index else np.nan
                xp = close.loc[exit_date, sym]  if exit_date  in close.index else np.nan
                stock_ret = returns.loc[window_dates, sym].sum() if sym in returns.columns else np.nan
            except Exception:
                ep, xp, stock_ret = np.nan, np.nan, np.nan

            logger.log(
                ticker      = sym,
                entry_date  = entry_date,
                exit_date   = exit_date,
                return_pct  = float(stock_ret) if not np.isnan(stock_ret) else 0.0,
                hold_days   = hold_days,
                direction   = 'long',
                entry_price = float(ep) if not np.isnan(ep) else None,
                exit_price  = float(xp) if not np.isnan(xp) else None,
                params      = {'factor': factor_name, 'quintile': 'top', 'n_q': n_q},
                notes       = f'round_F{round_num} factor long leg',
            )

        for sym in short_stocks:
            if sym not in close.columns:
                continue
            try:
                ep = close.loc[entry_date, sym] if entry_date in close.index else np.nan
                xp = close.loc[exit_date, sym]  if exit_date  in close.index else np.nan
                stock_ret = returns.loc[window_dates, sym].sum() if sym in returns.columns else np.nan
            except Exception:
                ep, xp, stock_ret = np.nan, np.nan, np.nan

            logger.log(
                ticker      = sym,
                entry_date  = entry_date,
                exit_date   = exit_date,
                return_pct  = float(-stock_ret) if not np.isnan(stock_ret) else 0.0,
                hold_days   = hold_days,
                direction   = 'short',
                entry_price = float(ep) if not np.isnan(ep) else None,
                exit_price  = float(xp) if not np.isnan(xp) else None,
                params      = {'factor': factor_name, 'quintile': 'bottom', 'n_q': n_q},
                notes       = f'round_F{round_num} factor short leg',
            )


# ── Seasonal backtest with trade logging ─────────────────────────────────────
def seasonal_backtest_log(signal_series, asset_ret, spy_close, strategy_name,
                          logger):
    """
    Log each contiguous in-signal block as one trade on SPY.
    signal_series: pd.Series of 0/1 indexed by date.
    asset_ret: pd.Series of daily returns for SPY.
    spy_close: pd.Series of SPY close prices.
    """
    common_idx = signal_series.index.intersection(asset_ret.index)
    sig = signal_series.reindex(common_idx).fillna(0)
    ret = asset_ret.reindex(common_idx).fillna(0)

    # Identify contiguous blocks where signal == 1
    in_trade   = False
    block_start = None
    block_dates = []

    dates_list = sig.index.tolist()

    def flush_block(block_dates):
        if not block_dates:
            return
        entry_date = block_dates[0]
        exit_date  = block_dates[-1]
        hold_days  = len(block_dates)
        block_ret  = ret.loc[block_dates].sum()

        ep = float(spy_close.loc[entry_date]) if entry_date in spy_close.index else None
        xp = float(spy_close.loc[exit_date])  if exit_date  in spy_close.index else None

        logger.log(
            ticker      = 'SPY',
            entry_date  = entry_date,
            exit_date   = exit_date,
            return_pct  = float(block_ret),
            hold_days   = hold_days,
            direction   = 'long',
            entry_price = ep,
            exit_price  = xp,
            params      = {'strategy': strategy_name},
            notes       = f'seasonal window: {strategy_name}',
        )

    for dt in dates_list:
        s = sig.loc[dt]
        if s > 0 and not in_trade:
            in_trade    = True
            block_dates = [dt]
        elif s > 0 and in_trade:
            block_dates.append(dt)
        elif s == 0 and in_trade:
            flush_block(block_dates)
            in_trade    = False
            block_dates = []

    # flush last open block
    if in_trade and block_dates:
        flush_block(block_dates)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("FACTOR & SEASONAL BACKTEST HARNESS v2 (TradeLogger)")
    print("=" * 70)

    # ── Load All Data ──────────────────────────────────────────────────────────
    print("\nLoading price data...")
    price_data = {}
    for sym in UNIVERSE + ['SPY']:
        df = load_symbol(sym)
        if df is not None and len(df) > 252:
            price_data[sym] = df['close']
            print(f"  {sym}: {len(df)} days loaded")
        else:
            print(f"  {sym}: SKIPPED (insufficient data)")

    loaded_syms = [s for s in UNIVERSE if s in price_data]
    print(f"\nLoaded {len(loaded_syms)} universe stocks + SPY")

    close   = pd.DataFrame({s: price_data[s] for s in loaded_syms}).dropna(how='all')
    close   = close[close.index >= START]
    returns = close.pct_change()

    spy_close = price_data.get('SPY')
    if spy_close is None:
        print("ERROR: SPY not loaded. Attempting download...")
        spy_df = load_symbol('SPY')
        if spy_df is not None:
            spy_close = spy_df['close']
            price_data['SPY'] = spy_close

    spy_ret = spy_close.pct_change() if spy_close is not None else None
    print(f"SPY: {len(spy_close) if spy_close is not None else 0} days")

    # ── Monthly rebalance dates ────────────────────────────────────────────────
    monthly_rebal_dates = []
    for period, group in returns.groupby([returns.index.year, returns.index.month]):
        monthly_rebal_dates.append(group.index[0])
    monthly_rebal_dates = sorted(set(monthly_rebal_dates))
    print(f"Monthly rebalance dates: {len(monthly_rebal_dates)} months")

    # ── ROUND F1: Single Factor Strategies ────────────────────────────────────
    print("\n" + "=" * 70)
    print("ROUND F1: CROSS-SECTIONAL FACTOR STRATEGIES")
    print("=" * 70)

    # Factor 1: Price Momentum 12-1
    print("\nComputing Factor 1: Momentum 12-1...")
    mom_12_1_scores = {}
    for rebal_date in monthly_rebal_dates:
        idx = close.index.get_indexer([rebal_date], method='nearest')[0]
        if idx < 252:
            continue
        try:
            past   = close.iloc[max(0, idx-252)]
            recent = close.iloc[max(0, idx-21)]
            scores = (recent / past - 1).dropna()
            mom_12_1_scores[rebal_date] = zscore_cs(scores)
        except Exception:
            pass

    logger_mom121 = TradeLogger(round_num=1, strategy='Momentum_12_1', category='factor')
    factor_backtest_log(mom_12_1_scores, 'Momentum_12_1', close, returns,
                        loaded_syms, logger_mom121, round_num=1)
    logger_mom121.save()

    # Factor 2: Momentum 6-1
    print("Computing Factor 2: Momentum 6-1...")
    mom_6_1_scores = {}
    for rebal_date in monthly_rebal_dates:
        idx = close.index.get_indexer([rebal_date], method='nearest')[0]
        if idx < 126:
            continue
        try:
            past   = close.iloc[max(0, idx-126)]
            recent = close.iloc[max(0, idx-21)]
            scores = (recent / past - 1).dropna()
            mom_6_1_scores[rebal_date] = zscore_cs(scores)
        except Exception:
            pass

    logger_mom61 = TradeLogger(round_num=1, strategy='Momentum_6_1', category='factor')
    factor_backtest_log(mom_6_1_scores, 'Momentum_6_1', close, returns,
                        loaded_syms, logger_mom61, round_num=1)
    logger_mom61.save()

    # Factor 3: Short-term Reversal
    print("Computing Factor 3: Short-term Reversal...")
    reversal_scores = {}
    for rebal_date in monthly_rebal_dates:
        idx = close.index.get_indexer([rebal_date], method='nearest')[0]
        if idx < 21:
            continue
        try:
            past    = close.iloc[max(0, idx-21)]
            current = close.iloc[idx]
            scores  = (current / past - 1).dropna()
            reversal_scores[rebal_date] = zscore_cs(-scores)
        except Exception:
            pass

    logger_rev = TradeLogger(round_num=1, strategy='Short_Term_Reversal', category='factor')
    factor_backtest_log(reversal_scores, 'Short_Term_Reversal', close, returns,
                        loaded_syms, logger_rev, round_num=1)
    logger_rev.save()

    # Factor 4: Low Volatility
    print("Computing Factor 4: Low Volatility...")
    lowvol_scores = {}
    for rebal_date in monthly_rebal_dates:
        idx = close.index.get_indexer([rebal_date], method='nearest')[0]
        if idx < 60:
            continue
        window = returns.iloc[max(0, idx-60):idx]
        vol    = window.std()
        lowvol_scores[rebal_date] = zscore_cs(-vol)

    logger_lowvol = TradeLogger(round_num=1, strategy='Low_Volatility', category='factor')
    factor_backtest_log(lowvol_scores, 'Low_Volatility', close, returns,
                        loaded_syms, logger_lowvol, round_num=1)
    logger_lowvol.save()

    # Factor 5: 52-week High Ratio
    print("Computing Factor 5: 52-week High Ratio...")
    wk52_scores = {}
    for rebal_date in monthly_rebal_dates:
        idx = close.index.get_indexer([rebal_date], method='nearest')[0]
        if idx < 252:
            continue
        window_high = close.iloc[max(0, idx-252):idx].max()
        current     = close.iloc[idx]
        ratio       = current / window_high
        wk52_scores[rebal_date] = zscore_cs(ratio.dropna())

    logger_wk52 = TradeLogger(round_num=1, strategy='52wk_High_Ratio', category='factor')
    factor_backtest_log(wk52_scores, '52wk_High_Ratio', close, returns,
                        loaded_syms, logger_wk52, round_num=1)
    logger_wk52.save()

    # Factor 6: Trend Strength
    print("Computing Factor 6: Trend Strength...")
    trend_scores = {}
    for rebal_date in monthly_rebal_dates:
        idx = close.index.get_indexer([rebal_date], method='nearest')[0]
        if idx < 60:
            continue
        window     = close.iloc[max(0, idx-60):idx]
        trend_vals = {}
        for sym in window.columns:
            col = window[sym].dropna()
            if len(col) < 20:
                continue
            x = np.arange(len(col))
            try:
                slope, intercept, r, p, se = stats.linregress(x, col.values)
                if se > 0:
                    trend_vals[sym] = slope / se
            except Exception:
                pass
        if trend_vals:
            series = pd.Series(trend_vals)
            trend_scores[rebal_date] = zscore_cs(series)

    logger_trend = TradeLogger(round_num=1, strategy='Trend_Strength', category='factor')
    factor_backtest_log(trend_scores, 'Trend_Strength', close, returns,
                        loaded_syms, logger_trend, round_num=1)
    logger_trend.save()

    # ── ROUND F2: Factor Combinations ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ROUND F2: FACTOR COMBINATIONS")
    print("=" * 70)

    # Factor 7: Momentum + Low Vol combo
    print("\nComputing Factor 7: Momentum + Low Vol combo...")
    combo_mom_vol = combine_scores(mom_12_1_scores, lowvol_scores)
    logger_combo_mv = TradeLogger(round_num=2, strategy='Combo_Mom_LowVol', category='factor')
    factor_backtest_log(combo_mom_vol, 'Combo_Mom_LowVol', close, returns,
                        loaded_syms, logger_combo_mv, round_num=2)
    logger_combo_mv.save()

    # Factor 8: Momentum + 52wk High combo
    print("Computing Factor 8: Momentum + 52wk High combo...")
    combo_mom_52 = combine_scores(mom_12_1_scores, wk52_scores)
    logger_combo_m52 = TradeLogger(round_num=2, strategy='Combo_Mom_52wkHigh', category='factor')
    factor_backtest_log(combo_mom_52, 'Combo_Mom_52wkHigh', close, returns,
                        loaded_syms, logger_combo_m52, round_num=2)
    logger_combo_m52.save()

    # Factor 9: All factors equal weight
    print("Computing Factor 9: All factors equal weight...")
    all_factor_scores = combine_all_scores(
        mom_12_1_scores, mom_6_1_scores, reversal_scores,
        lowvol_scores, wk52_scores, trend_scores
    )
    logger_multifactor = TradeLogger(round_num=2, strategy='Multi_Factor_EW', category='factor')
    factor_backtest_log(all_factor_scores, 'Multi_Factor_EW', close, returns,
                        loaded_syms, logger_multifactor, round_num=2)
    logger_multifactor.save()

    # ── ROUND S1: Seasonal / Calendar Effects ─────────────────────────────────
    print("\n" + "=" * 70)
    print("ROUND S1: SEASONAL / CALENDAR EFFECTS")
    print("=" * 70)

    if spy_ret is None or spy_close is None:
        print("ERROR: SPY data unavailable, skipping seasonal strategies.")
        return

    spy_dates      = spy_ret.index
    spy_dates_list = sorted(spy_dates.tolist())

    print("\nComputing Seasonal Strategies on SPY...")

    # S1: January Effect
    signal = pd.Series(0.0, index=spy_dates)
    for dt in spy_dates:
        d = dt.date()
        if d.month == 1 or (d.month == 12 and d.day >= 28):
            signal[dt] = 1.0
    logger_jan = TradeLogger(round_num=1, strategy='January_Effect', category='seasonal')
    seasonal_backtest_log(signal, spy_ret, spy_close, 'January_Effect', logger_jan)
    logger_jan.save()

    # S2: Turn of Month
    signal = pd.Series(0.0, index=spy_dates)
    for i, dt in enumerate(spy_dates_list):
        d     = dt.date()
        month = d.month
        days_in_month_after  = [dd for dd in spy_dates_list[i:i+5] if dd.date().month == month]
        days_next_month_before = [dd for dd in spy_dates_list[i:i+5] if dd.date().month != month]

        if len(days_in_month_after) <= 1:
            signal[dt] = 1.0
        elif i > 0:
            prev_month = spy_dates_list[i-1].date().month
            if prev_month != month:
                start_of_month = [dd for dd in spy_dates_list[max(0,i-5):i+1]
                                  if dd.date().month == month]
                if len(start_of_month) <= 3:
                    signal[dt] = 1.0

    logger_tom = TradeLogger(round_num=1, strategy='Turn_of_Month', category='seasonal')
    seasonal_backtest_log(signal, spy_ret, spy_close, 'Turn_of_Month', logger_tom)
    logger_tom.save()

    # S3: Pre-Holiday Effect
    holiday_set = set(HOLIDAYS.keys())
    signal = pd.Series(0.0, index=spy_dates)
    for i, dt in enumerate(spy_dates_list):
        future = spy_dates_list[i+1:i+4]
        in_pre = False
        for fut in future:
            d_fut = fut.date()
            for hol in holiday_set:
                if abs((d_fut - hol).days) <= 2:
                    in_pre = True
                    break
        if in_pre:
            signal[dt] = 1.0

    logger_prehol = TradeLogger(round_num=1, strategy='Pre_Holiday', category='seasonal')
    seasonal_backtest_log(signal, spy_ret, spy_close, 'Pre_Holiday', logger_prehol)
    logger_prehol.save()

    # S4: Monday Effect
    signal = pd.Series(0.0, index=spy_dates)
    for dt in spy_dates:
        if dt.weekday() == 0:
            signal[dt] = 1.0

    logger_mon = TradeLogger(round_num=1, strategy='Monday_Effect', category='seasonal')
    seasonal_backtest_log(signal, spy_ret, spy_close, 'Monday_Effect', logger_mon)
    logger_mon.save()

    # S5: End of Quarter
    quarter_ends = []
    for period, group in spy_ret.groupby([spy_ret.index.year, spy_ret.index.quarter]):
        quarter_ends.append(group.index[-1])
    quarter_ends = set(quarter_ends)

    signal = pd.Series(0.0, index=spy_dates)
    for i, dt in enumerate(spy_dates_list):
        future_3 = spy_dates_list[i:i+6]
        near_qend = any(d in quarter_ends for d in future_3[:4])
        past_2    = spy_dates_list[max(0,i-3):i+1]
        past_qend = any(d in quarter_ends for d in past_2)
        if near_qend or past_qend:
            signal[dt] = 1.0

    logger_eoq = TradeLogger(round_num=1, strategy='End_of_Quarter', category='seasonal')
    seasonal_backtest_log(signal, spy_ret, spy_close, 'End_of_Quarter', logger_eoq)
    logger_eoq.save()

    # S6: Santa Claus Rally (Dec 20 to Jan 3)
    signal = pd.Series(0.0, index=spy_dates)
    for dt in spy_dates:
        d = dt.date()
        if (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 3):
            signal[dt] = 1.0

    logger_santa = TradeLogger(round_num=1, strategy='Santa_Claus_Rally', category='seasonal')
    seasonal_backtest_log(signal, spy_ret, spy_close, 'Santa_Claus_Rally', logger_santa)
    logger_santa.save()

    # S7: Sell in May / Halloween Strategy (Long Oct-Apr)
    signal = pd.Series(0.0, index=spy_dates)
    for dt in spy_dates:
        d = dt.date()
        if d.month in [10, 11, 12, 1, 2, 3, 4]:
            signal[dt] = 1.0
        elif d.month == 5 and d.day == 1:
            signal[dt] = 0.0

    logger_sim = TradeLogger(round_num=1, strategy='Sell_in_May_Halloween', category='seasonal')
    seasonal_backtest_log(signal, spy_ret, spy_close, 'Sell_in_May_Halloween', logger_sim)
    logger_sim.save()

    print("\nDone. All trade logs saved.")


if __name__ == '__main__':
    main()
