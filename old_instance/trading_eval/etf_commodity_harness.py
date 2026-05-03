#!/usr/bin/env python3
"""
ETF Sector Rotation & Commodity Futures Backtest Harness
Rounds: E1, E2, C1, C2
"""

import sys
sys.path.insert(0, '/tmp/eval_deps')

import os
import json
import pickle
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, date

warnings.filterwarnings('ignore')

CACHE_DIR = '/workspace/group/trading_eval/cache'
RESULTS_DIR = '/workspace/group/trading_eval/rounds'
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

START_DATE = '2015-01-01'
END_DATE = datetime.today().strftime('%Y-%m-%d')

SECTOR_ETFS = ['XLE', 'XLF', 'XLK', 'XLV', 'XLI', 'XLU', 'XLY', 'XLP', 'XLB', 'XLRE']
COMMODITIES = ['GC=F', 'CL=F', 'NG=F', 'HG=F', 'ZC=F', 'ZW=F', 'SI=F', 'GLD']
BENCHMARK = 'SPY'
AUX_TICKERS = ['^VIX', '^TNX', 'RINF', 'CL=F']

ALL_TICKERS = SECTOR_ETFS + COMMODITIES + [BENCHMARK] + ['^VIX', '^TNX', 'RINF']
# dedupe
ALL_TICKERS = list(dict.fromkeys(ALL_TICKERS))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

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
        # flatten multi-level columns if present
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


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------

def compute_metrics(daily_rets, name='strategy', n_trades=0):
    """Given a pd.Series of daily returns, compute performance metrics."""
    rets = daily_rets.dropna()
    if len(rets) < 20:
        return {
            'name': name, 'sharpe': np.nan, 'cagr': np.nan,
            'max_dd': np.nan, 'win_rate': np.nan, 'n_trades': n_trades
        }
    annual_factor = 252
    mean_r = rets.mean()
    std_r = rets.std()
    sharpe = (mean_r / std_r * np.sqrt(annual_factor)) if std_r > 0 else 0.0

    total_r = (1 + rets).prod()
    n_years = len(rets) / annual_factor
    cagr = total_r ** (1 / n_years) - 1 if n_years > 0 else 0.0

    cum = (1 + rets).cumprod()
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    max_dd = dd.min()

    win_rate = (rets > 0).mean()

    return {
        'name': name,
        'sharpe': round(float(sharpe), 4),
        'cagr': round(float(cagr), 4),
        'max_dd': round(float(max_dd), 4),
        'win_rate': round(float(win_rate), 4),
        'n_trades': int(n_trades)
    }


def apply_tcost(weights_df, daily_returns_df, tcost_bps):
    """
    weights_df: daily position weights (N securities)
    daily_returns_df: daily returns (same shape)
    tcost_bps: transaction cost per trade in basis points
    Returns: series of net daily portfolio returns
    """
    tcost = tcost_bps / 10000.0
    # portfolio gross return
    gross = (weights_df * daily_returns_df).sum(axis=1)
    # turnover-based cost
    weight_change = weights_df.diff().abs().sum(axis=1)
    cost = weight_change * tcost
    net = gross - cost
    return net


# ---------------------------------------------------------------------------
# Round E1: Sector ETF Momentum Rotation
# ---------------------------------------------------------------------------

def run_e1(prices):
    results = []
    etf_prices = prices[SECTOR_ETFS].dropna(how='all')
    spy = prices[BENCHMARK].dropna()
    rets = etf_prices.pct_change()
    spy_rets = spy.pct_change()

    # align
    common_idx = rets.index.intersection(spy_rets.index)
    rets = rets.loc[common_idx]
    spy_rets = spy_rets.loc[common_idx]
    etf_prices = etf_prices.loc[common_idx]
    spy = spy.loc[common_idx]

    # helper: build long-only rotation portfolio
    def rotation_long(signal_df, n_top, rebal_freq='W', name=''):
        # signal_df: daily signal values, higher = more preferred
        # resample to weekly for signal
        weekly_signal = signal_df.resample(rebal_freq).last()
        # build daily weights
        weights = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
        n_trades = 0
        prev_held = set()
        for i, (dt, row) in enumerate(weekly_signal.iterrows()):
            valid = row.dropna()
            if len(valid) < n_top:
                continue
            top_n = valid.nlargest(n_top).index.tolist()
            w = 1.0 / n_top
            # find dates in the next period
            next_dates = rets.index[rets.index >= dt]
            if i + 1 < len(weekly_signal):
                next_end = weekly_signal.index[i + 1]
                next_dates = next_dates[next_dates < next_end]
            for d in next_dates:
                if d in weights.index:
                    weights.loc[d, top_n] = w
            # count trades
            new_held = set(top_n)
            n_trades += len(new_held.symmetric_difference(prev_held))
            prev_held = new_held
        # shift 1 to avoid lookahead
        weights = weights.shift(1).fillna(0.0)
        net = apply_tcost(weights, rets, tcost_bps=1)
        return compute_metrics(net, name=name, n_trades=n_trades)

    # 1-month (20d) momentum
    mom_20 = etf_prices.pct_change(20)
    for n in [1, 2, 3]:
        r = rotation_long(mom_20, n, name=f'E1_mom20d_top{n}')
        results.append(r)

    # 3-month (60d) momentum
    mom_60 = etf_prices.pct_change(60)
    for n in [1, 2, 3]:
        r = rotation_long(mom_60, n, name=f'E1_mom60d_top{n}')
        results.append(r)

    # 12-1 month Jegadeesh-Titman (252-21 day)
    mom_jt = etf_prices.pct_change(252) - etf_prices.pct_change(21)
    weekly_signal = mom_jt.resample('W').last()
    weights_long = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    weights_short = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    n_trades_jt = 0
    prev_long = set(); prev_short = set()
    for i, (dt, row) in enumerate(weekly_signal.iterrows()):
        valid = row.dropna()
        if len(valid) < 6:
            continue
        top3 = valid.nlargest(3).index.tolist()
        bot3 = valid.nsmallest(3).index.tolist()
        next_dates = rets.index[rets.index >= dt]
        if i + 1 < len(weekly_signal):
            next_end = weekly_signal.index[i + 1]
            next_dates = next_dates[next_dates < next_end]
        for d in next_dates:
            if d in weights_long.index:
                weights_long.loc[d, top3] = 1/3
                weights_short.loc[d, bot3] = 1/3
        n_trades_jt += len(set(top3).symmetric_difference(prev_long)) + len(set(bot3).symmetric_difference(prev_short))
        prev_long = set(top3); prev_short = set(bot3)
    weights_long = weights_long.shift(1).fillna(0.0)
    weights_short = weights_short.shift(1).fillna(0.0)
    gross_ls = (weights_long * rets).sum(axis=1) - (weights_short * rets).sum(axis=1)
    turnover_ls = (weights_long.diff().abs().sum(axis=1) + weights_short.diff().abs().sum(axis=1))
    net_ls = gross_ls - turnover_ls * 0.0001
    results.append(compute_metrics(net_ls, name='E1_JT_L3S3', n_trades=n_trades_jt))

    # Relative strength vs SPY: long sectors outperforming SPY on 20d, short underperformers
    rel_strength = etf_prices.pct_change(20).subtract(spy.pct_change(20), axis=0)
    weekly_rs = rel_strength.resample('W').last()
    wl_rs = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    ws_rs = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    n_trades_rs = 0
    for i, (dt, row) in enumerate(weekly_rs.iterrows()):
        valid = row.dropna()
        longs = valid[valid > 0].index.tolist()
        shorts = valid[valid < 0].index.tolist()
        next_dates = rets.index[rets.index >= dt]
        if i + 1 < len(weekly_rs):
            next_end = weekly_rs.index[i + 1]
            next_dates = next_dates[next_dates < next_end]
        for d in next_dates:
            if d in wl_rs.index:
                if longs:
                    wl_rs.loc[d, longs] = 1.0 / len(longs)
                if shorts:
                    ws_rs.loc[d, shorts] = 1.0 / len(shorts)
        n_trades_rs += 1
    wl_rs = wl_rs.shift(1).fillna(0.0)
    ws_rs = ws_rs.shift(1).fillna(0.0)
    gross_rs = (wl_rs * rets).sum(axis=1) - (ws_rs * rets).sum(axis=1)
    net_rs = gross_rs - (wl_rs.diff().abs().sum(axis=1) + ws_rs.diff().abs().sum(axis=1)) * 0.0001
    results.append(compute_metrics(net_rs, name='E1_RelStr_LS', n_trades=n_trades_rs))

    # Defensive rotation: bear vs bull
    spy_50 = spy.rolling(50).mean()
    spy_200 = spy.rolling(200).mean()
    bear_mask = (spy_50 < spy_200)
    defensive = ['XLU', 'XLP', 'XLV']
    w_def = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    w_bull = pd.DataFrame(0.0, index=rets.index, columns=SECTOR_ETFS)
    n_trades_def = 0
    prev_regime = None
    for dt in rets.index:
        if dt not in bear_mask.index:
            continue
        is_bear = bear_mask.loc[dt]
        regime = 'bear' if is_bear else 'bull'
        if regime != prev_regime:
            n_trades_def += 1
            prev_regime = regime
        if is_bear:
            w_def.loc[dt, defensive] = 1/3
        else:
            # top 3 by 20d momentum
            if dt in mom_20.index:
                row = mom_20.loc[dt].dropna()
                if len(row) >= 3:
                    top3 = row.nlargest(3).index.tolist()
                    w_bull.loc[dt, top3] = 1/3
    # combine
    w_combined = w_def + w_bull
    w_combined = w_combined.shift(1).fillna(0.0)
    net_def = apply_tcost(w_combined, rets, tcost_bps=1)
    results.append(compute_metrics(net_def, name='E1_Defensive_Rotation', n_trades=n_trades_def))

    # Mean reversion rotation: long bottom 3 last month
    r_rev = rotation_long(-mom_20, 3, name='E1_MeanReversion_bot3')
    results.append(r_rev)

    return results


# ---------------------------------------------------------------------------
# Round E2: Sector ETF Macro Overlay
# ---------------------------------------------------------------------------

def run_e2(prices):
    results = []
    etf_prices = prices[SECTOR_ETFS].dropna(how='all')
    rets = etf_prices.pct_change()

    # VIX signal
    if '^VIX' in prices.columns:
        vix = prices['^VIX'].dropna()
        # align
        common = rets.index.intersection(vix.index)
        rets_v = rets.loc[common]
        vix_v = vix.loc[common]

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
        net_vix = apply_tcost(w_vix, rets_v, tcost_bps=1)
        results.append(compute_metrics(net_vix, name='E2_VIX_Regime'))
    else:
        print("  [warn] ^VIX not available, skipping VIX strategy")

    # Oil momentum signal for energy
    if 'CL=F' in prices.columns:
        oil = prices['CL=F'].dropna()
        common2 = rets.index.intersection(oil.index)
        rets_o = rets.loc[common2]
        oil_o = oil.loc[common2]
        oil_mom = oil_o.pct_change(20)

        w_oil = pd.DataFrame(0.0, index=rets_o.index, columns=SECTOR_ETFS)
        for dt in rets_o.index:
            if dt not in oil_mom.index or pd.isna(oil_mom.loc[dt]):
                continue
            om = oil_mom.loc[dt]
            if om > 0.05:
                # overweight XLE
                w_oil.loc[dt, 'XLE'] = 0.5
                # fill rest equal weight in remaining
                others = [e for e in SECTOR_ETFS if e != 'XLE']
                w_oil.loc[dt, others] = 0.5 / len(others)
            elif om < -0.05:
                # underweight XLE, overweight XLU
                w_oil.loc[dt, 'XLU'] = 0.5
                others2 = [e for e in SECTOR_ETFS if e not in ['XLE', 'XLU']]
                w_oil.loc[dt, others2] = 0.5 / len(others2)
            else:
                w_oil.loc[dt, SECTOR_ETFS] = 0.1  # equal weight
        w_oil = w_oil.shift(1).fillna(0.0)
        net_oil = apply_tcost(w_oil, rets_o, tcost_bps=1)
        results.append(compute_metrics(net_oil, name='E2_Oil_Energy_Signal'))

    # TNX yield curve signal
    if '^TNX' in prices.columns:
        tnx = prices['^TNX'].dropna()
        common3 = rets.index.intersection(tnx.index)
        rets_t = rets.loc[common3]
        tnx_t = tnx.loc[common3]
        tnx_mom = tnx_t.pct_change(20)

        w_tnx = pd.DataFrame(0.0, index=rets_t.index, columns=SECTOR_ETFS)
        for dt in rets_t.index:
            if dt not in tnx_mom.index or pd.isna(tnx_mom.loc[dt]):
                continue
            tm = tnx_mom.loc[dt]
            if tm > 0:  # rising rates
                # long XLF, short XLRE
                w_tnx.loc[dt, 'XLF'] = 1.0
            else:  # falling rates
                # long XLU + XLRE, short XLF
                w_tnx.loc[dt, ['XLU', 'XLRE']] = 0.5
        w_tnx = w_tnx.shift(1).fillna(0.0)
        net_tnx = apply_tcost(w_tnx, rets_t, tcost_bps=1)
        results.append(compute_metrics(net_tnx, name='E2_TNX_YieldCurve_Long'))

        # Long-short version
        w_tnx_ls_long = pd.DataFrame(0.0, index=rets_t.index, columns=SECTOR_ETFS)
        w_tnx_ls_short = pd.DataFrame(0.0, index=rets_t.index, columns=SECTOR_ETFS)
        for dt in rets_t.index:
            if dt not in tnx_mom.index or pd.isna(tnx_mom.loc[dt]):
                continue
            tm = tnx_mom.loc[dt]
            if tm > 0:
                w_tnx_ls_long.loc[dt, 'XLF'] = 1.0
                w_tnx_ls_short.loc[dt, 'XLRE'] = 1.0
            else:
                w_tnx_ls_long.loc[dt, ['XLU', 'XLRE']] = 0.5
                w_tnx_ls_short.loc[dt, 'XLF'] = 1.0
        w_tnx_ls_long = w_tnx_ls_long.shift(1).fillna(0.0)
        w_tnx_ls_short = w_tnx_ls_short.shift(1).fillna(0.0)
        gross_tnx_ls = (w_tnx_ls_long * rets_t).sum(axis=1) - (w_tnx_ls_short * rets_t).sum(axis=1)
        net_tnx_ls = gross_tnx_ls - (w_tnx_ls_long.diff().abs().sum(axis=1) + w_tnx_ls_short.diff().abs().sum(axis=1)) * 0.0001
        results.append(compute_metrics(net_tnx_ls, name='E2_TNX_YieldCurve_LS'))

    return results


# ---------------------------------------------------------------------------
# Round C1: Commodity Momentum
# ---------------------------------------------------------------------------

def run_c1(prices):
    results = []
    comm_tickers = [c for c in COMMODITIES if c in prices.columns]
    comm_prices = prices[comm_tickers].dropna(how='all')
    comm_rets = comm_prices.pct_change()

    # Raw momentum - long only
    for period in [20, 60, 120]:
        mom = comm_prices.pct_change(period)
        weights = pd.DataFrame(0.0, index=comm_rets.index, columns=comm_tickers)
        for dt in comm_rets.index:
            if dt not in mom.index:
                continue
            row = mom.loc[dt]
            longs = row[row > 0].index.tolist()
            if longs:
                weights.loc[dt, longs] = 1.0 / len(longs)
        weights = weights.shift(1).fillna(0.0)
        net = apply_tcost(weights, comm_rets, tcost_bps=3)
        results.append(compute_metrics(net, name=f'C1_Mom{period}d_LongOnly'))

    # SMA crossover strategies
    for fast, slow in [(10, 50), (20, 100)]:
        weights_sma = pd.DataFrame(0.0, index=comm_rets.index, columns=comm_tickers)
        for t in comm_tickers:
            if t not in comm_prices.columns:
                continue
            p = comm_prices[t].dropna()
            sma_fast = p.rolling(fast).mean()
            sma_slow = p.rolling(slow).mean()
            long_signal = (sma_fast > sma_slow).astype(float)
            long_signal = long_signal.reindex(comm_rets.index, fill_value=0)
            weights_sma[t] = long_signal
        # normalize
        row_sums = weights_sma.sum(axis=1)
        weights_sma = weights_sma.div(row_sums.replace(0, np.nan), axis=0).fillna(0.0)
        weights_sma = weights_sma.shift(1).fillna(0.0)
        net_sma = apply_tcost(weights_sma, comm_rets, tcost_bps=3)
        results.append(compute_metrics(net_sma, name=f'C1_SMA_{fast}_{slow}_crossover'))

    # Trend filter: only long when price > 200d SMA
    sma200 = comm_prices.rolling(200).mean()
    trend_signal = (comm_prices > sma200).astype(float)
    trend_weights = trend_signal.copy()
    row_sums2 = trend_weights.sum(axis=1)
    trend_weights = trend_weights.div(row_sums2.replace(0, np.nan), axis=0).fillna(0.0)
    trend_weights = trend_weights.shift(1).fillna(0.0)
    net_trend = apply_tcost(trend_weights, comm_rets, tcost_bps=3)
    results.append(compute_metrics(net_trend, name='C1_TrendFilter_200SMA'))

    # Gold/Oil ratio spread
    if 'GC=F' in prices.columns and 'CL=F' in prices.columns:
        gold = prices['GC=F'].dropna()
        oil = prices['CL=F'].dropna()
        common_go = gold.index.intersection(oil.index)
        gold_go = gold.loc[common_go]
        oil_go = oil.loc[common_go]
        ratio = gold_go / oil_go
        ratio_zscore = (ratio - ratio.rolling(60).mean()) / ratio.rolling(60).std()

        go_rets = comm_rets.reindex(common_go)
        w_go = pd.DataFrame(0.0, index=common_go, columns=comm_tickers)
        for dt in common_go:
            if dt not in ratio_zscore.index or pd.isna(ratio_zscore.loc[dt]):
                continue
            z = ratio_zscore.loc[dt]
            if z > 1.0:   # ratio high = oil cheap vs gold -> long oil
                if 'CL=F' in comm_tickers:
                    w_go.loc[dt, 'CL=F'] = 1.0
            elif z < -1.0:  # ratio low = gold cheap vs oil -> long gold
                if 'GC=F' in comm_tickers:
                    w_go.loc[dt, 'GC=F'] = 1.0
                elif 'GLD' in comm_tickers:
                    w_go.loc[dt, 'GLD'] = 1.0
        w_go = w_go.shift(1).fillna(0.0)
        net_go = apply_tcost(w_go, go_rets, tcost_bps=3)
        results.append(compute_metrics(net_go, name='C1_GoldOil_RatioSpread'))

    # Inflation basket: equal weight GC=F + CL=F + HG=F using RINF as proxy
    inflation_basket = [t for t in ['GC=F', 'CL=F', 'HG=F'] if t in prices.columns]
    if inflation_basket and 'RINF' in prices.columns:
        rinf = prices['RINF'].dropna()
        rinf_ret = rinf.pct_change(20)
        basket_prices = comm_prices[[t for t in inflation_basket if t in comm_prices.columns]]
        basket_rets = basket_prices.pct_change()
        common_inf = basket_rets.index.intersection(rinf.index)
        basket_rets_inf = basket_rets.loc[common_inf]
        rinf_inf = rinf.loc[common_inf]
        # proxy: RINF positive momentum = inflation
        w_inf = pd.DataFrame(0.0, index=common_inf, columns=basket_rets_inf.columns)
        for dt in common_inf:
            if dt not in rinf_ret.index or pd.isna(rinf_ret.loc[dt]):
                continue
            if rinf_ret.loc[dt] > 0:
                n_b = len(basket_rets_inf.columns)
                w_inf.loc[dt, :] = 1.0 / n_b
        w_inf = w_inf.shift(1).fillna(0.0)
        net_inf = apply_tcost(w_inf, basket_rets_inf, tcost_bps=3)
        results.append(compute_metrics(net_inf, name='C1_InflationBasket_RINF'))
    elif inflation_basket:
        # fallback: always long inflation basket
        basket_prices = comm_prices[[t for t in inflation_basket if t in comm_prices.columns]]
        basket_rets = basket_prices.pct_change()
        w_inf_eq = pd.DataFrame(1.0 / len(inflation_basket), index=basket_rets.index, columns=basket_rets.columns)
        w_inf_eq = w_inf_eq.shift(1).fillna(0.0)
        net_inf_eq = apply_tcost(w_inf_eq, basket_rets, tcost_bps=3)
        results.append(compute_metrics(net_inf_eq, name='C1_InflationBasket_EqWt'))

    return results


# ---------------------------------------------------------------------------
# Round C2: Commodity Mean Reversion + Seasonality
# ---------------------------------------------------------------------------

def run_c2(prices):
    results = []
    comm_tickers = [c for c in COMMODITIES if c in prices.columns]
    comm_prices = prices[comm_tickers].dropna(how='all')
    comm_rets = comm_prices.pct_change()

    # Z-score mean reversion
    window = 20
    thresh = 1.5
    comm_ma = comm_prices.rolling(window).mean()
    comm_std = comm_prices.rolling(window).std()
    zscore = (comm_prices - comm_ma) / comm_std.replace(0, np.nan)

    # Long when z < -1.5 (oversold), short when z > 1.5 (overbought) - long only version
    w_mr_long = (zscore < -thresh).astype(float)
    row_sums_mr = w_mr_long.sum(axis=1)
    w_mr_long = w_mr_long.div(row_sums_mr.replace(0, np.nan), axis=0).fillna(0.0)
    w_mr_long = w_mr_long.shift(1).fillna(0.0)
    net_mr = apply_tcost(w_mr_long, comm_rets, tcost_bps=3)
    results.append(compute_metrics(net_mr, name='C2_Zscore_MR_LongOversold'))

    # L/S version: long oversold, short overbought
    w_mr_l = (zscore < -thresh).astype(float)
    w_mr_s = (zscore > thresh).astype(float)
    row_l = w_mr_l.sum(axis=1); row_s = w_mr_s.sum(axis=1)
    w_mr_l = w_mr_l.div(row_l.replace(0, np.nan), axis=0).fillna(0.0)
    w_mr_s = w_mr_s.div(row_s.replace(0, np.nan), axis=0).fillna(0.0)
    w_mr_l = w_mr_l.shift(1).fillna(0.0)
    w_mr_s = w_mr_s.shift(1).fillna(0.0)
    gross_mr_ls = (w_mr_l * comm_rets).sum(axis=1) - (w_mr_s * comm_rets).sum(axis=1)
    net_mr_ls = gross_mr_ls - (w_mr_l.diff().abs().sum(axis=1) + w_mr_s.diff().abs().sum(axis=1)) * 0.0003
    results.append(compute_metrics(net_mr_ls, name='C2_Zscore_MR_LS'))

    # Seasonal strategy for Natural Gas (winter months: Oct-Mar)
    if 'NG=F' in prices.columns:
        ng = prices['NG=F'].dropna()
        ng_rets = ng.pct_change()
        w_ng = pd.Series(0.0, index=ng_rets.index)
        for dt in ng_rets.index:
            if dt.month in [10, 11, 12, 1, 2, 3]:
                w_ng.loc[dt] = 1.0
        w_ng = w_ng.shift(1).fillna(0.0)
        net_ng = ng_rets * w_ng - w_ng.diff().abs() * 0.0003
        results.append(compute_metrics(net_ng, name='C2_NatGas_WinterSeasonal'))

    # Monthly seasonal for each commodity
    for t in comm_tickers:
        if t not in comm_rets.columns:
            continue
        tr = comm_rets[t].dropna()
        # find best 6 months by historical mean return
        monthly_means = tr.groupby(tr.index.month).mean()
        best_months = monthly_means.nlargest(6).index.tolist()
        w_seasonal = pd.Series(0.0, index=tr.index)
        for dt in tr.index:
            if dt.month in best_months:
                w_seasonal.loc[dt] = 1.0
        w_seasonal = w_seasonal.shift(1).fillna(0.0)
        net_seasonal = tr * w_seasonal - w_seasonal.diff().abs() * 0.0003
        safe_name = t.replace('=', '').replace('^', '')
        results.append(compute_metrics(net_seasonal, name=f'C2_Seasonal_{safe_name}'))

    # Contango/backwardation proxy: front-month vs 12-month average
    for t in comm_tickers:
        if t not in comm_prices.columns:
            continue
        p = comm_prices[t].dropna()
        p_ma252 = p.rolling(252).mean()
        # When front-month < 12-month average: likely contango, reduce position
        # When front > avg: backwardation, go long
        in_backwardation = (p > p_ma252).astype(float)
        in_backwardation_r = in_backwardation.reindex(comm_rets.index, fill_value=0.0)
        in_backwardation_r = in_backwardation_r.shift(1).fillna(0.0)
        t_rets = comm_rets[t] if t in comm_rets.columns else pd.Series(dtype=float)
        if not t_rets.empty:
            net_ct = t_rets * in_backwardation_r - in_backwardation_r.diff().abs() * 0.0003
            safe_name = t.replace('=', '').replace('^', '')
            results.append(compute_metrics(net_ct, name=f'C2_BackwardationProxy_{safe_name}'))

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("ETF SECTOR ROTATION & COMMODITY FUTURES BACKTEST HARNESS")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 70)

    print("\n[1] Loading price data...")
    prices = load_close_prices(ALL_TICKERS)
    print(f"Loaded {prices.shape[1]} tickers, {prices.shape[0]} trading days")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"Available: {list(prices.columns)}")

    # Run rounds
    print("\n[2] Running Round E1: Sector ETF Momentum Rotation...")
    e1_results = run_e1(prices)
    print(f"  E1 strategies: {len(e1_results)}")

    print("\n[3] Running Round E2: Sector ETF Macro Overlay...")
    e2_results = run_e2(prices)
    print(f"  E2 strategies: {len(e2_results)}")

    print("\n[4] Running Round C1: Commodity Momentum...")
    c1_results = run_c1(prices)
    print(f"  C1 strategies: {len(c1_results)}")

    print("\n[5] Running Round C2: Commodity Mean Reversion...")
    c2_results = run_c2(prices)
    print(f"  C2 strategies: {len(c2_results)}")

    # Aggregate
    all_etf = e1_results + e2_results
    all_comm = c1_results + c2_results
    all_results = all_etf + all_comm

    # Sort by Sharpe
    def sort_key(r):
        s = r.get('sharpe', np.nan)
        return -s if not np.isnan(s) else 9999

    all_results_sorted = sorted(all_results, key=sort_key)
    etf_sorted = sorted(all_etf, key=sort_key)
    comm_sorted = sorted(all_comm, key=sort_key)

    # Print top 15 overall
    print("\n" + "=" * 70)
    print("TOP 15 STRATEGIES BY SHARPE RATIO (ALL)")
    print("=" * 70)
    print(f"{'Rank':<5} {'Strategy':<45} {'Sharpe':>7} {'CAGR':>7} {'MaxDD':>8} {'WinRate':>8} {'Trades':>7}")
    print("-" * 95)
    for i, r in enumerate(all_results_sorted[:15], 1):
        print(f"{i:<5} {r['name']:<45} {r['sharpe']:>7.3f} {r['cagr']:>7.1%} {r['max_dd']:>8.1%} {r['win_rate']:>8.1%} {r['n_trades']:>7}")

    # ETF summary
    print("\n" + "=" * 70)
    print("ETF STRATEGIES SUMMARY (sorted by Sharpe)")
    print("=" * 70)
    print(f"{'Rank':<5} {'Strategy':<45} {'Sharpe':>7} {'CAGR':>7} {'MaxDD':>8} {'WinRate':>8}")
    print("-" * 85)
    for i, r in enumerate(etf_sorted, 1):
        print(f"{i:<5} {r['name']:<45} {r['sharpe']:>7.3f} {r['cagr']:>7.1%} {r['max_dd']:>8.1%} {r['win_rate']:>8.1%}")

    # Commodity summary
    print("\n" + "=" * 70)
    print("COMMODITY STRATEGIES SUMMARY (sorted by Sharpe)")
    print("=" * 70)
    print(f"{'Rank':<5} {'Strategy':<45} {'Sharpe':>7} {'CAGR':>7} {'MaxDD':>8} {'WinRate':>8}")
    print("-" * 85)
    for i, r in enumerate(comm_sorted, 1):
        print(f"{i:<5} {r['name']:<45} {r['sharpe']:>7.3f} {r['cagr']:>7.1%} {r['max_dd']:>8.1%} {r['win_rate']:>8.1%}")

    # Champions
    champion_etf = etf_sorted[0] if etf_sorted else {}
    champion_comm = comm_sorted[0] if comm_sorted else {}

    print(f"\nCHAMPION ETF Strategy: {champion_etf.get('name')} | Sharpe={champion_etf.get('sharpe')} | CAGR={champion_etf.get('cagr'):.1%}")
    print(f"CHAMPION Commodity Strategy: {champion_comm.get('name')} | Sharpe={champion_comm.get('sharpe')} | CAGR={champion_comm.get('cagr'):.1%}")

    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'period': {'start': START_DATE, 'end': END_DATE},
        'n_etf_strategies': len(all_etf),
        'n_commodity_strategies': len(all_comm),
        'top15_overall': all_results_sorted[:15],
        'etf_top10': etf_sorted[:10],
        'commodity_top10': comm_sorted[:10],
        'champion_etf': champion_etf,
        'champion_commodity': champion_comm,
        'all_etf_results': all_etf,
        'all_commodity_results': all_comm
    }

    out_path = os.path.join(RESULTS_DIR, 'etf_commodity_results.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {out_path}")
    print("Done.")


if __name__ == '__main__':
    main()
