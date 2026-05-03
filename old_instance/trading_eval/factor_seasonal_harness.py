"""
Factor Investing & Seasonal/Calendar Effects Backtest Harness
Karpathy-style autoresearch loop
"""

import sys
sys.path.insert(0, '/tmp/eval_deps')

import os
import json
import glob
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, date
from scipy import stats

warnings.filterwarnings('ignore')

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_DIR  = '/workspace/group/trading_eval/cache'
ROUNDS_DIR = '/workspace/group/trading_eval/rounds'
START      = '2015-01-01'
END        = datetime.today().strftime('%Y-%m-%d')

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
    # MLK (3rd Monday Jan) - approximations
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

os.makedirs(ROUNDS_DIR, exist_ok=True)

# ── Data Loading ──────────────────────────────────────────────────────────────
def load_symbol(sym):
    """Load price data from cache or yfinance."""
    cache_key = sym.replace('-', '_')
    pattern = os.path.join(CACHE_DIR, f'ohlcv_{cache_key}_*.pkl')
    matches = glob.glob(pattern)
    # Also check the 15yr naming convention used in this cache
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

    # Standardize column names
    df.columns = [c.lower() for c in df.columns]
    if 'adj close' in df.columns:
        df = df.rename(columns={'adj close': 'close'})

    # Strip timezone
    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df[df.index >= START]
    df = df[['close']].dropna()
    return df


print("=" * 70)
print("FACTOR & SEASONAL BACKTEST HARNESS")
print("=" * 70)

# ── Load All Data ─────────────────────────────────────────────────────────────
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

# Build aligned close price matrix
close = pd.DataFrame({s: price_data[s] for s in loaded_syms}).dropna(how='all')
close = close[close.index >= START]
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

# ── Backtest Metrics ──────────────────────────────────────────────────────────
def compute_metrics(ret_series, cost_per_trade=0.0005, n_trades=None):
    """Compute Sharpe, CAGR, MaxDD, WinRate from a daily return series."""
    ret = ret_series.dropna()
    if len(ret) < 50:
        return dict(sharpe=np.nan, cagr=np.nan, max_dd=np.nan, win_rate=np.nan, n_trades=0)

    # Apply costs
    if n_trades is not None and n_trades > 0:
        total_cost = cost_per_trade * n_trades
        daily_cost = total_cost / len(ret)
        ret = ret - daily_cost

    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0

    # CAGR
    cum = (1 + ret).cumprod()
    n_years = len(ret) / 252
    cagr = cum.iloc[-1] ** (1 / n_years) - 1 if n_years > 0 else 0.0

    # Max Drawdown
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    max_dd = dd.min()

    win_rate = (ret > 0).mean()

    return dict(
        sharpe=round(sharpe, 3),
        cagr=round(cagr * 100, 2),
        max_dd=round(max_dd * 100, 2),
        win_rate=round(win_rate * 100, 2),
        n_trades=n_trades or len(ret)
    )


# ── ROUND F1: Factor Signals ──────────────────────────────────────────────────
print("\n" + "=" * 70)
print("ROUND F1: CROSS-SECTIONAL FACTOR STRATEGIES")
print("=" * 70)

def zscore_cs(series):
    """Cross-sectional z-score (demean, scale by std)."""
    m = series.mean()
    s = series.std()
    if s == 0 or np.isnan(s):
        return pd.Series(np.nan, index=series.index)
    return (series - m) / s


def factor_backtest(factor_scores_monthly, factor_name, cost_per_rebal=0.0005):
    """
    Given a dict {date: pd.Series of scores per stock},
    run long-short quintile backtest.
    Returns daily return series and contribution dict.
    """
    all_dates = returns.index
    daily_pnl = pd.Series(0.0, index=all_dates)
    monthly_dates = sorted(factor_scores_monthly.keys())

    n_trades = 0
    stock_contributions = {s: 0.0 for s in loaded_syms}

    for i, rebal_date in enumerate(monthly_dates):
        scores = factor_scores_monthly[rebal_date].dropna()
        if len(scores) < 20:
            continue

        # Long top quintile, short bottom quintile
        n_q = max(1, len(scores) // 5)
        long_stocks  = scores.nlargest(n_q).index.tolist()
        short_stocks = scores.nsmallest(n_q).index.tolist()
        n_trades += 2  # one rebalance = 2 legs

        # Window: from this rebal date to next
        if i + 1 < len(monthly_dates):
            next_rebal = monthly_dates[i + 1]
        else:
            next_rebal = all_dates[-1]

        mask = (all_dates > rebal_date) & (all_dates <= next_rebal)
        window_dates = all_dates[mask]

        if len(window_dates) == 0:
            continue

        # Equal weight returns
        long_ret  = returns.loc[window_dates, long_stocks].mean(axis=1)
        short_ret = returns.loc[window_dates, short_stocks].mean(axis=1)
        ls_ret = (long_ret - short_ret) / 2
        daily_pnl.loc[window_dates] = ls_ret

        # Track contributions (cumulative)
        for s in long_stocks:
            if s in returns.columns:
                stock_contributions[s] += returns.loc[window_dates, s].sum()
        for s in short_stocks:
            if s in returns.columns:
                stock_contributions[s] -= returns.loc[window_dates, s].sum()

    # Apply costs
    cost_total = cost_per_rebal * n_trades
    cost_daily = cost_total / max(len(daily_pnl), 1)
    daily_pnl_net = daily_pnl - cost_daily

    metrics = compute_metrics(daily_pnl_net[daily_pnl_net != 0], n_trades=n_trades)
    metrics['factor'] = factor_name

    top_contributors = sorted(stock_contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
    metrics['top_contributors'] = [(s, round(v, 4)) for s, v in top_contributors]

    return metrics, daily_pnl_net


# Get first trading day of each month
monthly_rebal_dates = []
for period, group in returns.groupby([returns.index.year, returns.index.month]):
    monthly_rebal_dates.append(group.index[0])
monthly_rebal_dates = sorted(set(monthly_rebal_dates))

print(f"Monthly rebalance dates: {len(monthly_rebal_dates)} months")

# Pre-compute factor scores for each month
factor_results_list = []

# ── Factor 1: Price Momentum 12-1 ─────────────────────────────────────────────
print("\nComputing Factor 1: Momentum 12-1...")
mom_12_1_scores = {}
for rebal_date in monthly_rebal_dates:
    idx = close.index.get_indexer([rebal_date], method='nearest')[0]
    if idx < 252:
        continue
    try:
        past = close.iloc[max(0, idx-252)]
        recent = close.iloc[max(0, idx-21)]
        scores = (recent / past - 1).dropna()
        mom_12_1_scores[rebal_date] = zscore_cs(scores)
    except:
        pass

metrics, _ = factor_backtest(mom_12_1_scores, 'Momentum_12_1')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# ── Factor 2: Momentum 6-1 ────────────────────────────────────────────────────
print("Computing Factor 2: Momentum 6-1...")
mom_6_1_scores = {}
for rebal_date in monthly_rebal_dates:
    idx = close.index.get_indexer([rebal_date], method='nearest')[0]
    if idx < 126:
        continue
    try:
        past = close.iloc[max(0, idx-126)]
        recent = close.iloc[max(0, idx-21)]
        scores = (recent / past - 1).dropna()
        mom_6_1_scores[rebal_date] = zscore_cs(scores)
    except:
        pass

metrics, _ = factor_backtest(mom_6_1_scores, 'Momentum_6_1')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# ── Factor 3: Short-term Reversal ─────────────────────────────────────────────
print("Computing Factor 3: Short-term Reversal...")
reversal_scores = {}
for rebal_date in monthly_rebal_dates:
    idx = close.index.get_indexer([rebal_date], method='nearest')[0]
    if idx < 21:
        continue
    try:
        past = close.iloc[max(0, idx-21)]
        current = close.iloc[idx]
        scores = (current / past - 1).dropna()
        # Reversal: negate so long losers, short winners
        reversal_scores[rebal_date] = zscore_cs(-scores)
    except:
        pass

metrics, _ = factor_backtest(reversal_scores, 'Short_Term_Reversal')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# ── Factor 4: Low Volatility ──────────────────────────────────────────────────
print("Computing Factor 4: Low Volatility...")
lowvol_scores = {}
for rebal_date in monthly_rebal_dates:
    idx = close.index.get_indexer([rebal_date], method='nearest')[0]
    if idx < 60:
        continue
    window = returns.iloc[max(0, idx-60):idx]
    vol = window.std()
    # Low vol: negate so lowest vol gets highest score
    lowvol_scores[rebal_date] = zscore_cs(-vol)

metrics, _ = factor_backtest(lowvol_scores, 'Low_Volatility')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# ── Factor 5: 52-week High ────────────────────────────────────────────────────
print("Computing Factor 5: 52-week High Ratio...")
wk52_scores = {}
for rebal_date in monthly_rebal_dates:
    idx = close.index.get_indexer([rebal_date], method='nearest')[0]
    if idx < 252:
        continue
    window_high = close.iloc[max(0, idx-252):idx].max()
    current = close.iloc[idx]
    ratio = current / window_high
    wk52_scores[rebal_date] = zscore_cs(ratio.dropna())

metrics, _ = factor_backtest(wk52_scores, '52wk_High_Ratio')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# ── Factor 6: Trend Strength (linear regression slope / std_err) ──────────────
print("Computing Factor 6: Trend Strength...")
trend_scores = {}
for rebal_date in monthly_rebal_dates:
    idx = close.index.get_indexer([rebal_date], method='nearest')[0]
    if idx < 60:
        continue
    window = close.iloc[max(0, idx-60):idx]
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
        except:
            pass
    if trend_vals:
        series = pd.Series(trend_vals)
        trend_scores[rebal_date] = zscore_cs(series)

metrics, _ = factor_backtest(trend_scores, 'Trend_Strength')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# ── ROUND F2: Factor Combinations ────────────────────────────────────────────
print("\n" + "=" * 70)
print("ROUND F2: FACTOR COMBINATIONS")
print("=" * 70)

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
        # Only keep stocks with both scores valid
        valid = a.notna() & b.notna()
        combined[d] = combined[d][valid]
    return combined

# Factor 7: Momentum 12-1 + Low Vol
print("\nComputing Factor 7: Momentum + Low Vol combo...")
combo_mom_vol = combine_scores(mom_12_1_scores, lowvol_scores)
metrics, _ = factor_backtest(combo_mom_vol, 'Combo_Mom_LowVol')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# Factor 8: Momentum 12-1 + 52wk High
print("Computing Factor 8: Momentum + 52wk High combo...")
combo_mom_52 = combine_scores(mom_12_1_scores, wk52_scores)
metrics, _ = factor_backtest(combo_mom_52, 'Combo_Mom_52wkHigh')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# Factor 9: All factors equal weight
print("Computing Factor 9: All factors equal weight...")
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
        # Only keep rows with at least 4 out of 6 valid scores
        valid_mask = stacked.notna().sum(axis=1) >= 4
        combined[dt] = stacked[valid_mask].mean(axis=1, skipna=True)
    return combined

all_factor_scores = combine_all_scores(
    mom_12_1_scores, mom_6_1_scores, reversal_scores,
    lowvol_scores, wk52_scores, trend_scores
)
metrics, _ = factor_backtest(all_factor_scores, 'Multi_Factor_EW')
print(f"  Sharpe: {metrics['sharpe']}, CAGR: {metrics['cagr']}%")
factor_results_list.append(metrics)

# Sort by Sharpe
factor_results_list.sort(key=lambda x: x.get('sharpe', -999) if not np.isnan(x.get('sharpe', np.nan)) else -999, reverse=True)

print("\n--- FACTOR RESULTS TABLE (sorted by Sharpe) ---")
print(f"{'Factor':<25} {'Sharpe':>8} {'CAGR%':>8} {'MaxDD%':>8} {'WinRate%':>9}")
print("-" * 60)
for r in factor_results_list:
    print(f"{r['factor']:<25} {r['sharpe']:>8.3f} {r['cagr']:>8.2f} {r['max_dd']:>8.2f} {r['win_rate']:>9.2f}")

champion_factor = factor_results_list[0] if factor_results_list else {}
print(f"\nBest Factor: {champion_factor.get('factor')}")
print(f"  Sharpe: {champion_factor.get('sharpe')}, CAGR: {champion_factor.get('cagr')}%")
if 'top_contributors' in champion_factor:
    print(f"  Top Contributors: {champion_factor['top_contributors']}")


# ── ROUND S1: Seasonal / Calendar Effects ─────────────────────────────────────
print("\n" + "=" * 70)
print("ROUND S1: SEASONAL / CALENDAR EFFECTS")
print("=" * 70)

def seasonal_backtest(signal_series, asset_ret, cost_per_trade=0.0002):
    """
    signal_series: pd.Series of 0/1 indexed by date
    asset_ret: pd.Series of daily returns
    """
    common_idx = signal_series.index.intersection(asset_ret.index)
    sig = signal_series.reindex(common_idx).fillna(0)
    ret = asset_ret.reindex(common_idx).fillna(0)

    strategy_ret = sig * ret

    # Count trades (transitions 0->1)
    transitions = (sig.diff().abs() > 0).sum()
    n_trades = int(transitions)

    metrics = compute_metrics(strategy_ret, cost_per_trade=cost_per_trade, n_trades=n_trades)

    # t-test for statistical significance
    active_ret = strategy_ret[sig > 0]
    if len(active_ret) > 30:
        t_stat, p_val = stats.ttest_1samp(active_ret.dropna(), 0)
        metrics['t_stat'] = round(t_stat, 3)
        metrics['p_value'] = round(p_val, 4)
        metrics['is_significant'] = p_val < 0.05
    else:
        metrics['t_stat'] = np.nan
        metrics['p_value'] = np.nan
        metrics['is_significant'] = False

    return metrics


def build_signal(dates_index, in_window_func):
    """Build a 0/1 signal series for given trading dates."""
    signal = pd.Series(0.0, index=dates_index)
    for dt in dates_index:
        d = dt.date()
        if in_window_func(d, dates_index):
            signal[dt] = 1.0
    return signal


# Use SPY for all seasonal tests
spy_dates = spy_ret.index if spy_ret is not None else None

seasonal_results = []

print("\nComputing Seasonal Strategies on SPY...")

# ── S1: January Effect (Buy Dec 31, Sell Jan 31) ──────────────────────────────
def jan_effect(d, idx):
    return (d.month == 1) or (d.month == 12 and d.day >= 31)

if spy_dates is not None:
    signal = pd.Series(0.0, index=spy_dates)
    for dt in spy_dates:
        d = dt.date()
        if d.month == 1 or (d.month == 12 and d.day >= 28):
            signal[dt] = 1.0
    m = seasonal_backtest(signal, spy_ret)
    m['strategy'] = 'January_Effect'
    print(f"  January Effect: Sharpe={m['sharpe']}, p={m.get('p_value')}")
    seasonal_results.append(m)

# ── S2: Turn of Month (Buy last day of month, sell 3rd day next month) ─────────
if spy_dates is not None:
    signal = pd.Series(0.0, index=spy_dates)
    # Build month-end and month-start calendars
    spy_dates_list = sorted(spy_dates.tolist())

    for i, dt in enumerate(spy_dates_list):
        d = dt.date()
        # Check if this is one of the last 1 trading days of month
        # or one of first 3 trading days of next month
        month = d.month
        year = d.year
        # Days remaining in month
        days_in_month_after = [dd for dd in spy_dates_list[i:i+5] if dd.date().month == month]
        days_next_month_before = [dd for dd in spy_dates_list[i:i+5] if dd.date().month != month]

        if len(days_in_month_after) <= 1:  # last 1 trading day of month
            signal[dt] = 1.0
        elif i > 0:
            prev_month = spy_dates_list[i-1].date().month
            if prev_month != month:
                # Count how many trading days since month started
                start_of_month = [dd for dd in spy_dates_list[max(0,i-5):i+1]
                                  if dd.date().month == month]
                if len(start_of_month) <= 3:
                    signal[dt] = 1.0

    m = seasonal_backtest(signal, spy_ret)
    m['strategy'] = 'Turn_of_Month'
    print(f"  Turn of Month: Sharpe={m['sharpe']}, p={m.get('p_value')}")
    seasonal_results.append(m)

# ── S3: Pre-Holiday Effect ─────────────────────────────────────────────────────
if spy_dates is not None:
    holiday_set = set(HOLIDAYS.keys())
    signal = pd.Series(0.0, index=spy_dates)
    spy_dates_list = sorted(spy_dates.tolist())

    for i, dt in enumerate(spy_dates_list):
        # Look at next 3 trading days to see if a holiday is approaching
        future = spy_dates_list[i+1:i+4]
        in_pre = False
        for fut in future:
            d_fut = fut.date()
            # Check if d_fut is within 2 calendar days of a holiday
            for hol in holiday_set:
                if abs((d_fut - hol).days) <= 2:
                    in_pre = True
                    break
        if in_pre:
            signal[dt] = 1.0

    m = seasonal_backtest(signal, spy_ret)
    m['strategy'] = 'Pre_Holiday'
    print(f"  Pre-Holiday: Sharpe={m['sharpe']}, p={m.get('p_value')}")
    seasonal_results.append(m)

# ── S4: Monday Effect ─────────────────────────────────────────────────────────
if spy_dates is not None:
    # Monday = weekday 0
    signal = pd.Series(0.0, index=spy_dates)
    for dt in spy_dates:
        if dt.weekday() == 0:  # Monday
            signal[dt] = 1.0

    m = seasonal_backtest(signal, spy_ret)
    m['strategy'] = 'Monday_Effect'

    # Extra: compare Monday avg return vs non-Monday
    mon_ret = spy_ret[spy_dates[spy_dates.weekday == 0]].dropna() if spy_ret is not None else pd.Series()
    non_mon = spy_ret[spy_dates[spy_dates.weekday != 0]].dropna() if spy_ret is not None else pd.Series()
    if len(mon_ret) > 0 and len(non_mon) > 0:
        m['monday_avg_return'] = round(mon_ret.mean() * 100, 4)
        m['non_monday_avg_return'] = round(non_mon.mean() * 100, 4)

    print(f"  Monday Effect: Sharpe={m['sharpe']}, p={m.get('p_value')}")
    seasonal_results.append(m)

# ── S5: End of Quarter ────────────────────────────────────────────────────────
if spy_dates is not None:
    quarter_ends = []
    for period, group in spy_ret.groupby([spy_ret.index.year, spy_ret.index.quarter]):
        quarter_ends.append(group.index[-1])
    quarter_ends = set(quarter_ends)

    signal = pd.Series(0.0, index=spy_dates)
    spy_dates_list = sorted(spy_dates.tolist())

    for i, dt in enumerate(spy_dates_list):
        # 3 days before quarter end
        future_3 = spy_dates_list[i:i+6]
        near_qend = any(d in quarter_ends for d in future_3[:4])
        # 2 days after quarter end
        past_2 = spy_dates_list[max(0,i-3):i+1]
        past_qend = any(d in quarter_ends for d in past_2)
        if near_qend or past_qend:
            signal[dt] = 1.0

    m = seasonal_backtest(signal, spy_ret)
    m['strategy'] = 'End_of_Quarter'
    print(f"  End of Quarter: Sharpe={m['sharpe']}, p={m.get('p_value')}")
    seasonal_results.append(m)

# ── S6: Santa Claus Rally (Dec 20 to Jan 3) ───────────────────────────────────
if spy_dates is not None:
    signal = pd.Series(0.0, index=spy_dates)
    for dt in spy_dates:
        d = dt.date()
        if (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 3):
            signal[dt] = 1.0

    m = seasonal_backtest(signal, spy_ret)
    m['strategy'] = 'Santa_Claus_Rally'
    print(f"  Santa Claus Rally: Sharpe={m['sharpe']}, p={m.get('p_value')}")
    seasonal_results.append(m)

# ── S7: Sell in May (Halloween Strategy: Long Oct 31-Apr 30) ──────────────────
if spy_dates is not None:
    signal = pd.Series(0.0, index=spy_dates)
    for dt in spy_dates:
        d = dt.date()
        # In market Oct through Apr
        if d.month in [10, 11, 12, 1, 2, 3, 4]:
            signal[dt] = 1.0
        # Edge cases
        elif d.month == 5 and d.day == 1:
            signal[dt] = 0.0

    m = seasonal_backtest(signal, spy_ret)
    m['strategy'] = 'Sell_in_May_Halloween'
    print(f"  Sell in May: Sharpe={m['sharpe']}, p={m.get('p_value')}")
    seasonal_results.append(m)

# Sort seasonal by Sharpe
seasonal_results.sort(key=lambda x: x.get('sharpe', -999) if not np.isnan(x.get('sharpe', np.nan)) else -999, reverse=True)

print("\n--- SEASONAL RESULTS TABLE (sorted by Sharpe) ---")
print(f"{'Strategy':<28} {'Sharpe':>8} {'CAGR%':>8} {'MaxDD%':>8} {'p-value':>10} {'Sig':>5}")
print("-" * 72)
for r in seasonal_results:
    sig = 'YES' if r.get('is_significant') else 'no'
    pval = r.get('p_value', np.nan)
    pval_str = f"{pval:.4f}" if pval is not None and not np.isnan(pval) else "  n/a"
    print(f"{r['strategy']:<28} {r['sharpe']:>8.3f} {r['cagr']:>8.2f} {r['max_dd']:>8.2f} {pval_str:>10} {sig:>5}")

champion_seasonal = seasonal_results[0] if seasonal_results else {}
print(f"\nBest Seasonal: {champion_seasonal.get('strategy')}")
print(f"  Sharpe: {champion_seasonal.get('sharpe')}, CAGR: {champion_seasonal.get('cagr')}%")
print(f"  Statistically significant (p<0.05): {champion_seasonal.get('is_significant')}")

# ── Overall Winner ────────────────────────────────────────────────────────────
best_factor_sharpe   = champion_factor.get('sharpe', -999) if champion_factor else -999
best_seasonal_sharpe = champion_seasonal.get('sharpe', -999) if champion_seasonal else -999

if np.isnan(best_factor_sharpe):   best_factor_sharpe = -999
if np.isnan(best_seasonal_sharpe): best_seasonal_sharpe = -999

overall_winner = 'factor' if best_factor_sharpe >= best_seasonal_sharpe else 'seasonal'

print("\n" + "=" * 70)
print(f"OVERALL WINNER: {overall_winner.upper()}")
print(f"  Best Factor  : {champion_factor.get('factor')} | Sharpe={best_factor_sharpe:.3f}")
print(f"  Best Seasonal: {champion_seasonal.get('strategy')} | Sharpe={best_seasonal_sharpe:.3f}")
print("=" * 70)

# ── Save Results ──────────────────────────────────────────────────────────────
def clean_for_json(obj):
    """Recursively make object JSON-serializable."""
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    elif isinstance(obj, tuple):
        return [clean_for_json(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, float) and np.isnan(obj):
        return None
    else:
        return obj


results = {
    'timestamp': datetime.now().isoformat(),
    'factor_results': clean_for_json(factor_results_list),
    'seasonal_results': clean_for_json(seasonal_results),
    'champion_factor': clean_for_json(champion_factor),
    'champion_seasonal': clean_for_json(champion_seasonal),
    'factor_vs_seasonal_winner': overall_winner,
}

out_path = os.path.join(ROUNDS_DIR, 'factor_seasonal_results.json')
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\nResults saved to: {out_path}")
print("Done.")
