#!/usr/bin/env python3
"""
etf_v2.py — ETF Sector Rotation & Commodity Futures Backtest
NanoClaw Trading Eval Framework v2

Preserves exact strategy logic from etf_commodity_harness.py.
Logs individual trades via TradeLogger instead of computing metrics.
"""

import sys
import os

# Ensure framework dir is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '/tmp/eval_deps')

import pickle
import warnings
import numpy as np
import pandas as pd
from datetime import datetime

warnings.filterwarnings('ignore')

from framework.base_harness import TradeLogger, fetch_data, get_close

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_DIR  = '/workspace/group/trading_eval/cache'
START_DATE = '2015-01-01'
END_DATE   = datetime.today().strftime('%Y-%m-%d')

SECTOR_ETFS = ['XLE', 'XLF', 'XLK', 'XLV', 'XLI', 'XLU', 'XLY', 'XLP', 'XLB', 'XLRE']
COMMODITIES = ['GC=F', 'CL=F', 'NG=F', 'HG=F', 'ZC=F', 'ZW=F', 'SI=F', 'GLD']
BENCHMARK   = 'SPY'
AUX_TICKERS = ['^VIX', '^TNX', 'RINF', 'CL=F']

ALL_TICKERS = SECTOR_ETFS + COMMODITIES + [BENCHMARK] + ['^VIX', '^TNX', 'RINF']
ALL_TICKERS = list(dict.fromkeys(ALL_TICKERS))


# ── Data loading ──────────────────────────────────────────────────────────────
def cache_path(ticker):
    safe = ticker.replace('=', '_').replace('^', '_').replace('/', '_')
    return os.path.join(CACHE_DIR, f'etf_comm_{safe}.pkl')


def fetch_ticker(ticker):
    import yfinance as yf
    cp = cache_path(ticker)
    if os.path.exists(cp):
        with open(cp, 'rb') as f:
            df = pickle.load(f)
        print(f"  [cache] {ticker}: {len(df)} rows")
        return df
    print(f"  [download] {ticker}...")
    try:
        df = yf.download(ticker, start=START_DATE, end=END_DATE,
                         auto_adjust=True, progress=False)
        if df.empty:
            print(f"  [warn] {ticker} returned empty")
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        with open(cp, 'wb') as f:
            pickle.dump(df, f)
        print(f"  [ok] {ticker}: {len(df)} rows")
        return df
    except Exception as e:
        print(f"  [error] {ticker}: {e}")
        return pd.DataFrame()


def load_close_prices(tickers):
    frames = {}
    for t in tickers:
        df = fetch_ticker(t)
        if not df.empty and 'Close' in df.columns:
            s = df['Close'].copy()
            s.index = pd.to_datetime(s.index).tz_localize(None)
            frames[t] = s
    if not frames:
        return pd.DataFrame()
    price_df = pd.DataFrame(frames)
    price_df.index = pd.to_datetime(price_df.index).tz_localize(None)
    price_df = price_df.sort_index()
    return price_df


# ── Transaction cost helper ────────────────────────────────────────────────────
def apply_tcost(weights_df, daily_returns_df, tcost_bps):
    tcost = tcost_bps / 10000.0
    gross = (weights_df * daily_returns_df).sum(axis=1)
    weight_change = weights_df.diff().abs().sum(axis=1)
    cost = weight_change * tcost
    return gross - cost


# ── Generic portfolio trade logger ────────────────────────────────────────────
def log_portfolio_trades(weights, rets, prices, logger, strategy_name,
                         direction_map=None):
    """
    Walk through a weights DataFrame and log one trade record per
    (ticker, contiguous-holding-block).

    weights     : DataFrame, daily position weights (may be 0)
    rets        : DataFrame, daily returns (same columns)
    prices      : DataFrame, close prices (same columns)
    logger      : TradeLogger instance
    strategy_name: string label for params
    direction_map: optional dict {ticker: 'long'|'short'} override
    """
    for ticker in weights.columns:
        w_series = weights[ticker]
        in_trade   = False
        block_start = None
        block_w    = None
        block_dates = []

        dates_list = w_series.index.tolist()

        def flush_block(block_dates, block_w):
            if not block_dates:
                return
            entry_date = block_dates[0]
            exit_date  = block_dates[-1]
            hold_days  = len(block_dates)

            # cumulative return of the weighted position over the block
            if ticker in rets.columns:
                r_series   = rets[ticker].reindex(block_dates).fillna(0)
                block_ret  = float((r_series * block_w).sum())
            else:
                block_ret  = 0.0

            ep = float(prices.loc[entry_date, ticker]) if (ticker in prices.columns and entry_date in prices.index) else None
            xp = float(prices.loc[exit_date,  ticker]) if (ticker in prices.columns and exit_date  in prices.index) else None

            if direction_map and ticker in direction_map:
                direction = direction_map[ticker]
            else:
                direction = 'long' if block_w >= 0 else 'short'

            logger.log(
                ticker      = ticker,
                entry_date  = entry_date,
                exit_date   = exit_date,
                return_pct  = block_ret,
                hold_days   = hold_days,
                direction   = direction,
                entry_price = ep,
                exit_price  = xp,
                params      = {'strategy': strategy_name, 'weight': round(block_w, 4)},
                notes       = strategy_name,
            )

        for dt in dates_list:
            w = w_series.loc[dt]
            if w != 0.0 and not in_trade:
                in_trade    = True
                block_w     = w
                block_dates = [dt]
            elif w != 0.0 and in_trade:
                block_dates.append(dt)
            elif w == 0.0 and in_trade:
                flush_block(block_dates, block_w)
                in_trade    = False
                block_dates = []
                block_w     = None

        if in_trade and block_dates:
            flush_block(block_dates, block_w)


def log_ls_trades(weights_long, weights_short, rets, prices, logger, strategy_name):
    """Log long-leg and short-leg trades separately for L/S strategies."""
    log_portfolio_trades(weights_long,  rets, prices, logger, strategy_name,
                         direction_map={t: 'long'  for t in weights_long.columns})
    # For short legs, invert return sign
    neg_weights = -weights_short
    log_portfolio_trades(weights_short, rets, prices, logger, strategy_name + '_short',
                         direction_map={t: 'short' for t in weights_short.columns})


# ── Round E1: Sector ETF Momentum Rotation ────────────────────────────────────
def run_e1(prices, loggers):
    etf_prices = prices[SECTOR_ETFS].dropna(how='all')
    spy        = prices[BENCHMARK].dropna()
    rets       = etf_prices.pct_change()
    spy_rets   = spy.pct_change()

    common_idx = rets.index.intersection(spy_rets.index)
    rets       = rets.loc[common_idx]
    spy_rets   = spy_rets.loc[common_idx]
    etf_prices = etf_prices.loc[common_idx]
    spy        = spy.loc[common_idx]

    def rotation_long_weights(signal_df, n_top, rebal_freq='W'):
        weekly_signal = signal_df.resample(rebal_freq).last()
        weights = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
        prev_held = set()
        for i, (dt, row) in enumerate(weekly_signal.iterrows()):
            valid = row.dropna()
            if len(valid) < n_top:
                continue
            top_n      = valid.nlargest(n_top).index.tolist()
            w          = 1.0 / n_top
            next_dates = rets.index[rets.index >= dt]
            if i + 1 < len(weekly_signal):
                next_end   = weekly_signal.index[i + 1]
                next_dates = next_dates[next_dates < next_end]
            for d in next_dates:
                if d in weights.index:
                    weights.loc[d, top_n] = w
            prev_held = set(top_n)
        return weights.shift(1).fillna(0.0)

    # 1-month (20d) momentum
    mom_20 = etf_prices.pct_change(20)
    for n in [1, 2, 3]:
        name = f'E1_mom20d_top{n}'
        w    = rotation_long_weights(mom_20, n)
        log_portfolio_trades(w, rets, etf_prices, loggers[name], name)

    # 3-month (60d) momentum
    mom_60 = etf_prices.pct_change(60)
    for n in [1, 2, 3]:
        name = f'E1_mom60d_top{n}'
        w    = rotation_long_weights(mom_60, n)
        log_portfolio_trades(w, rets, etf_prices, loggers[name], name)

    # 12-1 month Jegadeesh-Titman long-short
    mom_jt = etf_prices.pct_change(252) - etf_prices.pct_change(21)
    weekly_signal = mom_jt.resample('W').last()
    weights_long  = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    weights_short = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    prev_long = set(); prev_short = set()
    for i, (dt, row) in enumerate(weekly_signal.iterrows()):
        valid = row.dropna()
        if len(valid) < 6:
            continue
        top3 = valid.nlargest(3).index.tolist()
        bot3 = valid.nsmallest(3).index.tolist()
        next_dates = rets.index[rets.index >= dt]
        if i + 1 < len(weekly_signal):
            next_end   = weekly_signal.index[i + 1]
            next_dates = next_dates[next_dates < next_end]
        for d in next_dates:
            if d in weights_long.index:
                weights_long.loc[d, top3]  = 1/3
                weights_short.loc[d, bot3] = 1/3
        prev_long = set(top3); prev_short = set(bot3)
    weights_long  = weights_long.shift(1).fillna(0.0)
    weights_short = weights_short.shift(1).fillna(0.0)
    log_ls_trades(weights_long, weights_short, rets, etf_prices,
                  loggers['E1_JT_L3S3'], 'E1_JT_L3S3')

    # Relative strength vs SPY
    rel_strength = etf_prices.pct_change(20).subtract(spy.pct_change(20), axis=0)
    weekly_rs    = rel_strength.resample('W').last()
    wl_rs = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    ws_rs = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    for i, (dt, row) in enumerate(weekly_rs.iterrows()):
        valid  = row.dropna()
        longs  = valid[valid > 0].index.tolist()
        shorts = valid[valid < 0].index.tolist()
        next_dates = rets.index[rets.index >= dt]
        if i + 1 < len(weekly_rs):
            next_end   = weekly_rs.index[i + 1]
            next_dates = next_dates[next_dates < next_end]
        for d in next_dates:
            if d in wl_rs.index:
                if longs:
                    wl_rs.loc[d, longs]  = 1.0 / len(longs)
                if shorts:
                    ws_rs.loc[d, shorts] = 1.0 / len(shorts)
    wl_rs = wl_rs.shift(1).fillna(0.0)
    ws_rs = ws_rs.shift(1).fillna(0.0)
    log_ls_trades(wl_rs, ws_rs, rets, etf_prices,
                  loggers['E1_RelStr_LS'], 'E1_RelStr_LS')

    # Defensive rotation: bear vs bull
    spy_50  = spy.rolling(50).mean()
    spy_200 = spy.rolling(200).mean()
    bear_mask = (spy_50 < spy_200)
    defensive = ['XLU', 'XLP', 'XLV']
    w_def  = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    w_bull = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    prev_regime = None
    for dt in rets.index:
        if dt not in bear_mask.index:
            continue
        is_bear = bear_mask.loc[dt]
        if is_bear:
            w_def.loc[dt, defensive] = 1/3
        else:
            if dt in mom_20.index:
                row = mom_20.loc[dt].dropna()
                if len(row) >= 3:
                    top3 = row.nlargest(3).index.tolist()
                    w_bull.loc[dt, top3] = 1/3
    w_combined = (w_def + w_bull).shift(1).fillna(0.0)
    log_portfolio_trades(w_combined, rets, etf_prices,
                         loggers['E1_Defensive_Rotation'], 'E1_Defensive_Rotation')

    # Mean reversion rotation: long bottom 3 last month
    w_rev = rotation_long_weights(-mom_20, 3)
    log_portfolio_trades(w_rev, rets, etf_prices,
                         loggers['E1_MeanReversion_bot3'], 'E1_MeanReversion_bot3')


# ── Round E2: Sector ETF Macro Overlay ────────────────────────────────────────
def run_e2(prices, loggers):
    etf_prices = prices[SECTOR_ETFS].dropna(how='all')
    rets       = etf_prices.pct_change()

    # VIX signal
    if '^VIX' in prices.columns:
        vix    = prices['^VIX'].dropna()
        common = rets.index.intersection(vix.index)
        rets_v = rets.loc[common]
        vix_v  = vix.loc[common]

        w_vix = pd.DataFrame(0.0, index=rets_v.index, columns=SECTOR_ETFS)
        for dt in rets_v.index:
            if dt not in vix_v.index:
                continue
            v = vix_v.loc[dt]
            if v < 20:
                w_vix.loc[dt, ['XLK', 'XLY']] = 0.5
            elif v <= 30:
                w_vix.loc[dt, ['XLV', 'XLP']] = 0.5
            else:
                w_vix.loc[dt, ['XLU', 'XLP']] = 0.5
        w_vix = w_vix.shift(1).fillna(0.0)
        log_portfolio_trades(w_vix, rets_v, etf_prices,
                             loggers['E2_VIX_Regime'], 'E2_VIX_Regime')
    else:
        print("  [warn] ^VIX not available, skipping VIX strategy")

    # Oil momentum signal for energy
    if 'CL=F' in prices.columns:
        oil     = prices['CL=F'].dropna()
        common2 = rets.index.intersection(oil.index)
        rets_o  = rets.loc[common2]
        oil_o   = oil.loc[common2]
        oil_mom = oil_o.pct_change(20)

        w_oil = pd.DataFrame(0.0, index=rets_o.index, columns=SECTOR_ETFS)
        for dt in rets_o.index:
            if dt not in oil_mom.index or pd.isna(oil_mom.loc[dt]):
                continue
            om = oil_mom.loc[dt]
            if om > 0.05:
                w_oil.loc[dt, 'XLE'] = 0.5
                others = [e for e in SECTOR_ETFS if e != 'XLE']
                w_oil.loc[dt, others] = 0.5 / len(others)
            elif om < -0.05:
                w_oil.loc[dt, 'XLU'] = 0.5
                others2 = [e for e in SECTOR_ETFS if e not in ['XLE', 'XLU']]
                w_oil.loc[dt, others2] = 0.5 / len(others2)
            else:
                w_oil.loc[dt, SECTOR_ETFS] = 0.1
        w_oil = w_oil.shift(1).fillna(0.0)
        log_portfolio_trades(w_oil, rets_o, etf_prices,
                             loggers['E2_Oil_Energy_Signal'], 'E2_Oil_Energy_Signal')

    # TNX yield curve signal
    if '^TNX' in prices.columns:
        tnx     = prices['^TNX'].dropna()
        common3 = rets.index.intersection(tnx.index)
        rets_t  = rets.loc[common3]
        tnx_t   = tnx.loc[common3]
        tnx_mom = tnx_t.pct_change(20)

        w_tnx = pd.DataFrame(0.0, index=rets_t.index, columns=SECTOR_ETFS)
        for dt in rets_t.index:
            if dt not in tnx_mom.index or pd.isna(tnx_mom.loc[dt]):
                continue
            tm = tnx_mom.loc[dt]
            if tm > 0:
                w_tnx.loc[dt, 'XLF'] = 1.0
            else:
                w_tnx.loc[dt, ['XLU', 'XLRE']] = 0.5
        w_tnx = w_tnx.shift(1).fillna(0.0)
        log_portfolio_trades(w_tnx, rets_t, etf_prices,
                             loggers['E2_TNX_YieldCurve_Long'], 'E2_TNX_YieldCurve_Long')

        # Long-short version
        w_tnx_ls_long  = pd.DataFrame(0.0, index=rets_t.index, columns=SECTOR_ETFS)
        w_tnx_ls_short = pd.DataFrame(0.0, index=rets_t.index, columns=SECTOR_ETFS)
        for dt in rets_t.index:
            if dt not in tnx_mom.index or pd.isna(tnx_mom.loc[dt]):
                continue
            tm = tnx_mom.loc[dt]
            if tm > 0:
                w_tnx_ls_long.loc[dt, 'XLF']   = 1.0
                w_tnx_ls_short.loc[dt, 'XLRE']  = 1.0
            else:
                w_tnx_ls_long.loc[dt, ['XLU', 'XLRE']] = 0.5
                w_tnx_ls_short.loc[dt, 'XLF']           = 1.0
        w_tnx_ls_long  = w_tnx_ls_long.shift(1).fillna(0.0)
        w_tnx_ls_short = w_tnx_ls_short.shift(1).fillna(0.0)
        log_ls_trades(w_tnx_ls_long, w_tnx_ls_short, rets_t, etf_prices,
                      loggers['E2_TNX_YieldCurve_LS'], 'E2_TNX_YieldCurve_LS')


# ── Round C1: Commodity Momentum ──────────────────────────────────────────────
def run_c1(prices, loggers):
    comm_tickers = [c for c in COMMODITIES if c in prices.columns]
    comm_prices  = prices[comm_tickers].dropna(how='all')
    comm_rets    = comm_prices.pct_change()

    # Raw momentum - long only
    for period in [20, 60, 120]:
        mom     = comm_prices.pct_change(period)
        weights = pd.DataFrame(0.0, index=comm_rets.index, columns=comm_tickers)
        for dt in comm_rets.index:
            if dt not in mom.index:
                continue
            row   = mom.loc[dt]
            longs = row[row > 0].index.tolist()
            if longs:
                weights.loc[dt, longs] = 1.0 / len(longs)
        weights = weights.shift(1).fillna(0.0)
        name    = f'C1_Mom{period}d_LongOnly'
        log_portfolio_trades(weights, comm_rets, comm_prices, loggers[name], name)

    # SMA crossover strategies
    for fast, slow in [(10, 50), (20, 100)]:
        weights_sma = pd.DataFrame(0.0, index=comm_rets.index, columns=comm_tickers)
        for t in comm_tickers:
            if t not in comm_prices.columns:
                continue
            p        = comm_prices[t].dropna()
            sma_fast = p.rolling(fast).mean()
            sma_slow = p.rolling(slow).mean()
            long_sig = (sma_fast > sma_slow).astype(float)
            long_sig = long_sig.reindex(comm_rets.index, fill_value=0)
            weights_sma[t] = long_sig
        row_sums    = weights_sma.sum(axis=1)
        weights_sma = weights_sma.div(row_sums.replace(0, np.nan), axis=0).fillna(0.0)
        weights_sma = weights_sma.shift(1).fillna(0.0)
        name        = f'C1_SMA_{fast}_{slow}_crossover'
        log_portfolio_trades(weights_sma, comm_rets, comm_prices, loggers[name], name)

    # Trend filter: only long when price > 200d SMA
    sma200        = comm_prices.rolling(200).mean()
    trend_signal  = (comm_prices > sma200).astype(float)
    trend_weights = trend_signal.copy()
    row_sums2     = trend_weights.sum(axis=1)
    trend_weights = trend_weights.div(row_sums2.replace(0, np.nan), axis=0).fillna(0.0)
    trend_weights = trend_weights.shift(1).fillna(0.0)
    log_portfolio_trades(trend_weights, comm_rets, comm_prices,
                         loggers['C1_TrendFilter_200SMA'], 'C1_TrendFilter_200SMA')

    # Gold/Oil ratio spread
    if 'GC=F' in prices.columns and 'CL=F' in prices.columns:
        gold      = prices['GC=F'].dropna()
        oil       = prices['CL=F'].dropna()
        common_go = gold.index.intersection(oil.index)
        gold_go   = gold.loc[common_go]
        oil_go    = oil.loc[common_go]
        ratio     = gold_go / oil_go
        ratio_zscore = (ratio - ratio.rolling(60).mean()) / ratio.rolling(60).std()

        go_rets = comm_rets.reindex(common_go)
        w_go    = pd.DataFrame(0.0, index=common_go, columns=comm_tickers)
        for dt in common_go:
            if dt not in ratio_zscore.index or pd.isna(ratio_zscore.loc[dt]):
                continue
            z = ratio_zscore.loc[dt]
            if z > 1.0:
                if 'CL=F' in comm_tickers:
                    w_go.loc[dt, 'CL=F'] = 1.0
            elif z < -1.0:
                if 'GC=F' in comm_tickers:
                    w_go.loc[dt, 'GC=F'] = 1.0
                elif 'GLD' in comm_tickers:
                    w_go.loc[dt, 'GLD'] = 1.0
        w_go = w_go.shift(1).fillna(0.0)
        log_portfolio_trades(w_go, go_rets, comm_prices,
                             loggers['C1_GoldOil_RatioSpread'], 'C1_GoldOil_RatioSpread')

    # Inflation basket
    inflation_basket = [t for t in ['GC=F', 'CL=F', 'HG=F'] if t in prices.columns]
    if inflation_basket and 'RINF' in prices.columns:
        rinf          = prices['RINF'].dropna()
        rinf_ret      = rinf.pct_change(20)
        basket_prices = comm_prices[[t for t in inflation_basket if t in comm_prices.columns]]
        basket_rets   = basket_prices.pct_change()
        common_inf    = basket_rets.index.intersection(rinf.index)
        basket_rets_inf = basket_rets.loc[common_inf]
        w_inf = pd.DataFrame(0.0, index=common_inf, columns=basket_rets_inf.columns)
        for dt in common_inf:
            if dt not in rinf_ret.index or pd.isna(rinf_ret.loc[dt]):
                continue
            if rinf_ret.loc[dt] > 0:
                n_b = len(basket_rets_inf.columns)
                w_inf.loc[dt, :] = 1.0 / n_b
        w_inf = w_inf.shift(1).fillna(0.0)
        log_portfolio_trades(w_inf, basket_rets_inf, comm_prices,
                             loggers['C1_InflationBasket_RINF'], 'C1_InflationBasket_RINF')
    elif inflation_basket:
        basket_prices  = comm_prices[[t for t in inflation_basket if t in comm_prices.columns]]
        basket_rets    = basket_prices.pct_change()
        w_inf_eq       = pd.DataFrame(1.0 / len(inflation_basket),
                                      index=basket_rets.index, columns=basket_rets.columns)
        w_inf_eq       = w_inf_eq.shift(1).fillna(0.0)
        log_portfolio_trades(w_inf_eq, basket_rets, comm_prices,
                             loggers['C1_InflationBasket_EqWt'], 'C1_InflationBasket_EqWt')


# ── Round C2: Commodity Mean Reversion + Seasonality ─────────────────────────
def run_c2(prices, loggers):
    comm_tickers = [c for c in COMMODITIES if c in prices.columns]
    comm_prices  = prices[comm_tickers].dropna(how='all')
    comm_rets    = comm_prices.pct_change()

    window = 20
    thresh = 1.5
    comm_ma  = comm_prices.rolling(window).mean()
    comm_std = comm_prices.rolling(window).std()
    zscore   = (comm_prices - comm_ma) / comm_std.replace(0, np.nan)

    # Long-only mean reversion (long oversold)
    w_mr_long  = (zscore < -thresh).astype(float)
    row_sums_mr = w_mr_long.sum(axis=1)
    w_mr_long  = w_mr_long.div(row_sums_mr.replace(0, np.nan), axis=0).fillna(0.0)
    w_mr_long  = w_mr_long.shift(1).fillna(0.0)
    log_portfolio_trades(w_mr_long, comm_rets, comm_prices,
                         loggers['C2_Zscore_MR_LongOversold'], 'C2_Zscore_MR_LongOversold')

    # L/S mean reversion
    w_mr_l = (zscore < -thresh).astype(float)
    w_mr_s = (zscore > thresh).astype(float)
    row_l  = w_mr_l.sum(axis=1); row_s = w_mr_s.sum(axis=1)
    w_mr_l = w_mr_l.div(row_l.replace(0, np.nan), axis=0).fillna(0.0)
    w_mr_s = w_mr_s.div(row_s.replace(0, np.nan), axis=0).fillna(0.0)
    w_mr_l = w_mr_l.shift(1).fillna(0.0)
    w_mr_s = w_mr_s.shift(1).fillna(0.0)
    log_ls_trades(w_mr_l, w_mr_s, comm_rets, comm_prices,
                  loggers['C2_Zscore_MR_LS'], 'C2_Zscore_MR_LS')

    # Natural Gas winter seasonal
    if 'NG=F' in prices.columns:
        ng      = prices['NG=F'].dropna()
        ng_rets = ng.pct_change()
        w_ng    = pd.Series(0.0, index=ng_rets.index)
        for dt in ng_rets.index:
            if dt.month in [10, 11, 12, 1, 2, 3]:
                w_ng.loc[dt] = 1.0
        w_ng = w_ng.shift(1).fillna(0.0)
        # Log as a single-column DataFrame
        w_ng_df = pd.DataFrame({'NG=F': w_ng})
        ng_rets_df = pd.DataFrame({'NG=F': ng_rets})
        ng_prices_df = pd.DataFrame({'NG=F': ng})
        log_portfolio_trades(w_ng_df, ng_rets_df, ng_prices_df,
                             loggers['C2_NatGas_WinterSeasonal'], 'C2_NatGas_WinterSeasonal')

    # Monthly seasonal for each commodity
    for t in comm_tickers:
        if t not in comm_rets.columns:
            continue
        tr           = comm_rets[t].dropna()
        monthly_means = tr.groupby(tr.index.month).mean()
        best_months  = monthly_means.nlargest(6).index.tolist()
        w_seasonal   = pd.Series(0.0, index=tr.index)
        for dt in tr.index:
            if dt.month in best_months:
                w_seasonal.loc[dt] = 1.0
        w_seasonal = w_seasonal.shift(1).fillna(0.0)
        safe_name  = t.replace('=', '').replace('^', '')
        name       = f'C2_Seasonal_{safe_name}'
        w_df       = pd.DataFrame({t: w_seasonal})
        r_df       = pd.DataFrame({t: tr})
        p_df       = pd.DataFrame({t: comm_prices[t]}) if t in comm_prices.columns else pd.DataFrame({t: pd.Series(dtype=float)})
        log_portfolio_trades(w_df, r_df, p_df, loggers[name], name)

    # Contango/backwardation proxy
    for t in comm_tickers:
        if t not in comm_prices.columns:
            continue
        p             = comm_prices[t].dropna()
        p_ma252       = p.rolling(252).mean()
        in_backwardation = (p > p_ma252).astype(float)
        in_backwardation_r = in_backwardation.reindex(comm_rets.index, fill_value=0.0)
        in_backwardation_r = in_backwardation_r.shift(1).fillna(0.0)
        t_rets = comm_rets[t] if t in comm_rets.columns else pd.Series(dtype=float)
        if not t_rets.empty:
            safe_name = t.replace('=', '').replace('^', '')
            name      = f'C2_BackwardationProxy_{safe_name}'
            w_df      = pd.DataFrame({t: in_backwardation_r})
            r_df      = pd.DataFrame({t: t_rets})
            p_df      = pd.DataFrame({t: p})
            log_portfolio_trades(w_df, r_df, p_df, loggers[name], name)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("ETF SECTOR ROTATION & COMMODITY FUTURES BACKTEST HARNESS v2")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 70)

    print("\n[1] Loading price data...")
    prices = load_close_prices(ALL_TICKERS)
    print(f"Loaded {prices.shape[1]} tickers, {prices.shape[0]} trading days")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"Available: {list(prices.columns)}")

    comm_tickers = [c for c in COMMODITIES if c in prices.columns]

    # ── Build all loggers upfront ──────────────────────────────────────────────
    # E1 strategies (round_num=1, category='etf')
    e1_names = (
        [f'E1_mom20d_top{n}' for n in [1,2,3]] +
        [f'E1_mom60d_top{n}' for n in [1,2,3]] +
        ['E1_JT_L3S3', 'E1_JT_L3S3_short',
         'E1_RelStr_LS', 'E1_RelStr_LS_short',
         'E1_Defensive_Rotation', 'E1_MeanReversion_bot3']
    )
    # E2 strategies (round_num=2, category='etf')
    e2_names = [
        'E2_VIX_Regime', 'E2_Oil_Energy_Signal',
        'E2_TNX_YieldCurve_Long',
        'E2_TNX_YieldCurve_LS', 'E2_TNX_YieldCurve_LS_short',
    ]
    # C1 strategies (round_num=1, category='commodity')
    c1_names = (
        [f'C1_Mom{p}d_LongOnly' for p in [20, 60, 120]] +
        [f'C1_SMA_{f}_{s}_crossover' for f, s in [(10,50),(20,100)]] +
        ['C1_TrendFilter_200SMA', 'C1_GoldOil_RatioSpread',
         'C1_InflationBasket_RINF', 'C1_InflationBasket_EqWt']
    )
    # C2 strategies (round_num=2, category='commodity')
    c2_seasonal_names = [f'C2_Seasonal_{t.replace("=","").replace("^","")}' for t in comm_tickers]
    c2_backw_names    = [f'C2_BackwardationProxy_{t.replace("=","").replace("^","")}' for t in comm_tickers]
    c2_names = (
        ['C2_Zscore_MR_LongOversold',
         'C2_Zscore_MR_LS', 'C2_Zscore_MR_LS_short',
         'C2_NatGas_WinterSeasonal'] +
        c2_seasonal_names + c2_backw_names
    )

    loggers = {}
    for name in e1_names:
        loggers[name] = TradeLogger(round_num=1, strategy=name, category='etf')
    for name in e2_names:
        loggers[name] = TradeLogger(round_num=2, strategy=name, category='etf')
    for name in c1_names:
        loggers[name] = TradeLogger(round_num=1, strategy=name, category='commodity')
    for name in c2_names:
        loggers[name] = TradeLogger(round_num=2, strategy=name, category='commodity')

    # ── Run rounds ────────────────────────────────────────────────────────────
    print("\n[2] Running Round E1: Sector ETF Momentum Rotation...")
    run_e1(prices, loggers)

    print("\n[3] Running Round E2: Sector ETF Macro Overlay...")
    run_e2(prices, loggers)

    print("\n[4] Running Round C1: Commodity Momentum...")
    run_c1(prices, loggers)

    print("\n[5] Running Round C2: Commodity Mean Reversion + Seasonality...")
    run_c2(prices, loggers)

    # ── Save all loggers ──────────────────────────────────────────────────────
    print("\n[6] Saving all trade logs...")
    for name, logger in loggers.items():
        if len(logger) > 0:
            logger.save()
        else:
            print(f"  [skip] {name}: 0 trades (strategy may have been skipped)")

    print("\nDone. All trade logs saved.")


if __name__ == '__main__':
    main()
