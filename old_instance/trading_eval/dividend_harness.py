#!/usr/bin/env python3
"""
Round 27: Dividend Strategies
Tests 8 dividend-related strategy types using cached price data.
"""

import sys, json, warnings, pickle, os
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

try:
    import pandas as pd
    import yfinance as yf
    from scipy.stats import norm
    from scipy import stats as scipy_stats
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    'pandas', 'yfinance', 'scipy', 'numpy',
                    '--break-system-packages', '-q'], capture_output=True)
    import pandas as pd
    import yfinance as yf
    from scipy.stats import norm
    from scipy import stats as scipy_stats

CACHE_DIR = Path('/workspace/group/trading_eval/cache')
DIV_CACHE  = CACHE_DIR / 'dividends'
DIV_CACHE.mkdir(exist_ok=True)
ROUNDS_DIR = Path('/workspace/group/trading_eval/rounds')

START = pd.Timestamp('2015-01-01')
END   = pd.Timestamp('2025-12-31')
RF    = 0.045

# ── Helpers ───────────────────────────────────────────────────────────────────

def sharpe(arr):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    if len(arr) < 20: return np.nan
    excess = arr - RF/252
    return float(excess.mean() / excess.std() * np.sqrt(252)) if excess.std() else np.nan

def max_dd(arr):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    if not len(arr): return np.nan
    cum = np.cumprod(1 + arr)
    return float(((cum - np.maximum.accumulate(cum)) / np.maximum.accumulate(cum)).min())

def cagr(arr):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    if len(arr) < 20: return np.nan
    return float(np.prod(1 + arr) ** (252 / len(arr)) - 1)

def win_rate(arr):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    return float((arr > 0).mean()) if len(arr) else np.nan

def tstat(arr):
    arr = np.asarray(arr, float); arr = arr[~np.isnan(arr)]
    if len(arr) < 5: return np.nan, 1.0
    t, p = scipy_stats.ttest_1samp(arr, 0)
    return float(t), float(p)

def bs_call(S, K, T, sigma, r=RF):
    if T <= 0 or sigma <= 0: return max(S-K, 0)
    d1 = (np.log(S/K) + (r + .5*sigma**2)*T) / (sigma*np.sqrt(T))
    return float(S * norm.cdf(d1) - K * np.exp(-r*T) * norm.cdf(d1 - sigma*np.sqrt(T)))

def strip_tz(idx):
    """Remove timezone from DatetimeIndex."""
    if hasattr(idx, 'tz') and idx.tz is not None:
        return idx.tz_localize(None)
    return idx

# ── Load price cache (Series from _15yr.pkl) ─────────────────────────────────

def load_prices():
    prices = {}
    for f in CACHE_DIR.glob('*_15yr.pkl'):
        ticker = f.stem.replace('_15yr', '')
        if ticker.startswith('ohlcv_'):
            continue
        try:
            s = pickle.load(open(f, 'rb'))
            if isinstance(s, pd.DataFrame):
                s = s['Close'].squeeze()
            s.index = strip_tz(s.index)
            s = s.loc[START:END].dropna()
            if len(s) > 100:
                prices[ticker] = s
        except:
            pass
    return prices

# ── Load / fetch dividends ────────────────────────────────────────────────────

def load_dividends(tickers):
    divs = {}
    for ticker in tickers:
        cache_file = DIV_CACHE / f'{ticker}.pkl'
        if cache_file.exists():
            try:
                s = pickle.load(open(cache_file, 'rb'))
                s.index = strip_tz(s.index)
                divs[ticker] = s
                continue
            except:
                pass
        try:
            s = yf.Ticker(ticker).dividends
            if s is not None and len(s) > 0:
                s.index = strip_tz(s.index)
                pickle.dump(s, open(cache_file, 'wb'))
                divs[ticker] = s
        except:
            pass
    return divs

# ── Strategy 1: Dividend Capture ─────────────────────────────────────────────

def strat_capture(prices, divs, buy_before=1, hold_after=3):
    """
    NOTE: Using auto_adjust=True (adjusted) prices. The adjusted price already
    incorporates dividend reinvestment, so we do NOT add div_amount separately
    (that would double-count). This tests pure price momentum around ex-date.
    True dividend capture P&L requires unadjusted prices.
    """
    trades = []
    for ticker, closes in prices.items():
        d = divs.get(ticker)
        if d is None or len(d) == 0: continue
        idx_list = closes.index.tolist()
        d2i = {dt: i for i, dt in enumerate(idx_list)}
        for ex_date in d.index:
            if ex_date < START or ex_date > END: continue
            ex_i = next((d2i[dt] for dt in idx_list if dt >= ex_date), None)
            if ex_i is None: continue
            bi, si = ex_i - buy_before, ex_i + hold_after
            if bi < 0 or si >= len(idx_list): continue
            # Pure price return, no div double-count (adjusted prices)
            ret = (float(closes.iloc[si]) - float(closes.iloc[bi])) / float(closes.iloc[bi])
            trades.append(ret)
    if not trades: return {}
    arr = np.array(trades)
    t, p = tstat(arr)
    return dict(strategy=f'Div Capture buy-{buy_before}d sell+{hold_after}d',
                n_trades=len(trades), sharpe=sharpe(arr), win_rate=win_rate(arr),
                avg_ret_pct=float(arr.mean()*100), t_stat=t, p_value=p)

# ── Strategy 2: Ex-Div Drift ──────────────────────────────────────────────────

def strat_exdiv_drift(prices, divs, hold=10):
    trades = []
    for ticker, closes in prices.items():
        d = divs.get(ticker)
        if d is None or len(d) == 0: continue
        idx_list = closes.index.tolist()
        d2i = {dt: i for i, dt in enumerate(idx_list)}
        for ex_date in d.index:
            if ex_date < START or ex_date > END: continue
            ex_i = next((d2i[dt] for dt in idx_list if dt >= ex_date), None)
            if ex_i is None: continue
            si = ex_i + hold
            if si >= len(idx_list): continue
            ret = (float(closes.iloc[si]) - float(closes.iloc[ex_i])) / float(closes.iloc[ex_i])
            trades.append(ret)
    if not trades: return {}
    arr = np.array(trades)
    t, p = tstat(arr)
    return dict(strategy=f'Ex-Div Drift hold-{hold}d',
                n_trades=len(trades), sharpe=sharpe(arr), win_rate=win_rate(arr),
                avg_ret_pct=float(arr.mean()*100), t_stat=t, p_value=p)

# ── Strategy 3: Dogs of the Dow ───────────────────────────────────────────────

DOW30 = ['AAPL','AXP','BA','CAT','CRM','CSCO','CVX','DIS','DOW','GS',
         'HD','HON','IBM','INTC','JNJ','JPM','KO','MCD','MMM','MRK',
         'MSFT','NKE','PG','TRV','UNH','V','VZ','WBA','WMT','AMGN']

def strat_dogs(prices, divs, n_dogs=10):
    annual_rets = []
    for year in range(2015, 2026):
        start_dt = pd.Timestamp(f'{year}-01-02')
        end_dt   = pd.Timestamp(f'{year}-12-31')
        yields = {}
        for ticker in DOW30:
            if ticker not in prices or ticker not in divs: continue
            closes = prices[ticker]
            year_closes = closes.loc[start_dt:end_dt]
            if len(year_closes) < 50: continue
            p0 = float(year_closes.iloc[0])
            prior_divs = divs[ticker].loc[
                (divs[ticker].index >= start_dt - timedelta(days=365)) &
                (divs[ticker].index < start_dt)]
            ann_div = float(prior_divs.sum())
            if p0 > 0 and ann_div > 0:
                yields[ticker] = ann_div / p0
        if len(yields) < n_dogs: continue
        portfolio = [t for t, _ in sorted(yields.items(), key=lambda x: x[1], reverse=True)[:n_dogs]]
        rets = []
        for ticker in portfolio:
            year_closes = prices[ticker].loc[start_dt:end_dt]
            if len(year_closes) < 50: continue
            p0, p1 = float(year_closes.iloc[0]), float(year_closes.iloc[-1])
            div_income = float(divs[ticker].loc[start_dt:end_dt].sum()) if ticker in divs else 0
            rets.append((p1 + div_income - p0) / p0)
        if rets: annual_rets.append(np.mean(rets))
    if not annual_rets: return {}
    arr = np.array(annual_rets)
    std = arr.std()
    sh = (arr.mean() - RF) / std if std > 0 else np.nan
    t, p = scipy_stats.ttest_1samp(arr, RF)
    return dict(strategy=f'Dogs of the Dow top-{n_dogs}', n_years=len(annual_rets),
                annual_returns=[round(r,4) for r in annual_rets],
                mean_annual_return=float(arr.mean()), sharpe_annual=float(sh),
                best_year=float(arr.max()), worst_year=float(arr.min()),
                t_stat=float(t), p_value=float(p))

# ── Strategy 4: Dividend Aristocrats Momentum ─────────────────────────────────

ARISTOCRATS = ['ABT','AFL','CAH','CAT','CL','COST','CVX','GD','HD','IBM',
               'ITW','JNJ','KMB','KO','LMT','LOW','MCD','MMM','MRK','NKE',
               'NOC','PEP','PG','RTX','SYY','TGT','UNH','UPS','WMT','XOM']

def strat_aristocrats_mom(prices, top_n=10):
    rebal_dates = pd.date_range(start=START, end=END, freq='QS')
    avail = [t for t in ARISTOCRATS if t in prices and len(prices[t]) > 130]
    if not avail: return {}
    combined = pd.DataFrame({t: prices[t] for t in avail}).ffill()
    port_rets = []
    for i, rdt in enumerate(rebal_dates):
        hist = combined.loc[:rdt]
        if len(hist) < 130: continue
        scores = {}
        for t in avail:
            s = hist[t].dropna()
            if len(s) < 126: continue
            scores[t] = (float(s.iloc[-1]) - float(s.iloc[-126])) / float(s.iloc[-126])
        if len(scores) < top_n: continue
        port = [t for t, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]]
        nxt = rebal_dates[i+1] if i+1 < len(rebal_dates) else pd.Timestamp(END)
        period = combined.loc[rdt:nxt]
        if len(period) < 2: continue
        rets = pd.concat([period[t].pct_change().dropna() for t in port if t in period], axis=1)
        if not rets.empty:
            port_rets.extend(rets.mean(axis=1).tolist())
    if not port_rets: return {}
    arr = np.array(port_rets)
    return dict(strategy=f'Aristocrats Momentum top-{top_n} quarterly',
                n_days=len(arr), sharpe=sharpe(arr), cagr=cagr(arr),
                max_dd=max_dd(arr), win_rate=win_rate(arr))

# ── Strategy 5: High Yield Screen ─────────────────────────────────────────────

def strat_high_yield(prices, divs, top_pct=0.25):
    avail = [t for t in prices if t in divs]
    if not avail: return {}
    combined = pd.DataFrame({t: prices[t] for t in avail}).ffill()
    rebal_dates = pd.date_range(start=START, end=END, freq='QS')
    port_rets = []
    for i, rdt in enumerate(rebal_dates):
        hist = combined.loc[:rdt]
        if len(hist) < 2: continue
        yields = {}
        for t in avail:
            prior = divs[t].loc[rdt - timedelta(days=365):rdt]
            ann_div = float(prior.sum())
            price = float(hist[t].dropna().iloc[-1]) if len(hist[t].dropna()) else 0
            if price > 0 and ann_div > 0:
                yields[t] = ann_div / price
        if len(yields) < 4: continue
        n_top = max(1, int(len(yields) * top_pct))
        port = [t for t, _ in sorted(yields.items(), key=lambda x: x[1], reverse=True)[:n_top]]
        nxt = rebal_dates[i+1] if i+1 < len(rebal_dates) else pd.Timestamp(END)
        period = combined.loc[rdt:nxt]
        if len(period) < 2: continue
        rets = pd.concat([period[t].pct_change().dropna() for t in port if t in period], axis=1)
        if not rets.empty:
            port_rets.extend(rets.mean(axis=1).tolist())
    if not port_rets: return {}
    arr = np.array(port_rets)
    return dict(strategy='High Yield Screen top-25% quarterly',
                n_days=len(arr), sharpe=sharpe(arr), cagr=cagr(arr),
                max_dd=max_dd(arr), win_rate=win_rate(arr))

# ── Strategy 6: Dividend Raise Signal ─────────────────────────────────────────

def strat_div_raise(prices, divs, hold=20, min_raise=0.05):
    trades = []
    for ticker, closes in prices.items():
        d = divs.get(ticker)
        if d is None or len(d) < 3: continue
        idx_list = closes.index.tolist()
        d2i = {dt: i for i, dt in enumerate(idx_list)}
        amounts = d.values
        dates = d.index.tolist()
        for i in range(1, len(dates)):
            prev, cur = amounts[i-1], amounts[i]
            if prev <= 0: continue
            chg = (cur - prev) / prev
            if chg < min_raise: continue
            ev_date = dates[i]
            if ev_date < START or ev_date > END: continue
            ei = next((d2i[dt] for dt in idx_list if dt >= ev_date), None)
            if ei is None: continue
            xi = ei + hold
            if xi >= len(idx_list): continue
            ret = (float(closes.iloc[xi]) - float(closes.iloc[ei])) / float(closes.iloc[ei])
            trades.append({'ret': ret, 'chg': chg, 'ticker': ticker})
    if not trades: return {}
    arr = np.array([t['ret'] for t in trades])
    t_s, p_v = tstat(arr)
    return dict(strategy=f'Div Raise >={int(min_raise*100)}% hold-{hold}d',
                n_trades=len(trades), sharpe=sharpe(arr), win_rate=win_rate(arr),
                avg_ret_pct=float(arr.mean()*100), median_ret_pct=float(np.median(arr)*100),
                avg_raise_pct=float(np.mean([t['chg'] for t in trades])*100),
                t_stat=t_s, p_value=p_v)

# ── Strategy 7: Dividend Cut Signal (short) ───────────────────────────────────

def strat_div_cut(prices, divs, hold=20, min_cut=0.10):
    trades = []
    for ticker, closes in prices.items():
        d = divs.get(ticker)
        if d is None or len(d) < 3: continue
        idx_list = closes.index.tolist()
        d2i = {dt: i for i, dt in enumerate(idx_list)}
        amounts = d.values
        dates = d.index.tolist()
        for i in range(1, len(dates)):
            prev, cur = amounts[i-1], amounts[i]
            if prev <= 0: continue
            chg = (cur - prev) / prev
            if chg > -min_cut: continue
            ev_date = dates[i]
            if ev_date < START or ev_date > END: continue
            ei = next((d2i[dt] for dt in idx_list if dt >= ev_date), None)
            if ei is None: continue
            xi = ei + hold
            if xi >= len(idx_list): continue
            # Short: profit = -(price change)
            ret = -(float(closes.iloc[xi]) - float(closes.iloc[ei])) / float(closes.iloc[ei])
            trades.append({'ret': ret, 'chg': chg, 'ticker': ticker})
    if not trades: return {}
    arr = np.array([t['ret'] for t in trades])
    t_s, p_v = tstat(arr)
    return dict(strategy=f'Div Cut Short >={int(min_cut*100)}% hold-{hold}d',
                n_trades=len(trades), sharpe=sharpe(arr), win_rate=win_rate(arr),
                avg_ret_pct=float(arr.mean()*100), t_stat=t_s, p_value=p_v)

# ── Strategy 8: Dividend Initiation ───────────────────────────────────────────

def strat_div_initiation(prices, divs, hold=60, lookback_yrs=3):
    trades = []
    for ticker, closes in prices.items():
        d = divs.get(ticker)
        if d is None or len(d) == 0: continue
        idx_list = closes.index.tolist()
        d2i = {dt: i for i, dt in enumerate(idx_list)}
        for ev_date in d.index:
            if ev_date < START or ev_date > END: continue
            lb_start = ev_date - timedelta(days=lookback_yrs*365)
            prior = d.loc[(d.index >= lb_start) & (d.index < ev_date)]
            if len(prior) > 0: continue  # Not an initiation
            ei = next((d2i[dt] for dt in idx_list if dt >= ev_date), None)
            if ei is None: continue
            xi = ei + hold
            if xi >= len(idx_list): continue
            ret = (float(closes.iloc[xi]) - float(closes.iloc[ei])) / float(closes.iloc[ei])
            trades.append({'ret': ret, 'ticker': ticker, 'date': str(ev_date.date())})
    if not trades:
        return dict(strategy='Div Initiation (hold 60d)', n_trades=0,
                    note='No true initiations in Fortune 100 universe (all established dividend payers)')
    arr = np.array([t['ret'] for t in trades])
    t_s, p_v = tstat(arr)
    return dict(strategy=f'Div Initiation hold-{hold}d', n_trades=len(trades),
                sharpe=sharpe(arr), win_rate=win_rate(arr),
                avg_ret_pct=float(arr.mean()*100), t_stat=t_s, p_value=p_v,
                events=trades[:10])

# ── Strategy 9: Covered Calls Around Ex-Div ───────────────────────────────────

def strat_cc_exdiv(prices, divs, days_before=5, otm_pct=0.02):
    trades = []
    for ticker, closes in prices.items():
        d = divs.get(ticker)
        if d is None or len(d) == 0: continue
        idx_list = closes.index.tolist()
        d2i = {dt: i for i, dt in enumerate(idx_list)}
        rets_series = closes.pct_change()
        vol20 = rets_series.rolling(20).std() * np.sqrt(252)
        for ex_date, div_amt in d.items():
            if ex_date < START or ex_date > END: continue
            ex_i = next((d2i[dt] for dt in idx_list if dt >= ex_date), None)
            if ex_i is None: continue
            sell_i = ex_i - days_before
            if sell_i < 20: continue
            S = float(closes.iloc[sell_i])
            sigma = float(vol20.iloc[sell_i])
            if np.isnan(sigma) or sigma <= 0: continue
            K = S * (1 + otm_pct)
            T = days_before / 252
            premium = bs_call(S, K, T, sigma)
            prem_pct = premium / S
            S_ex = float(closes.iloc[ex_i])
            # Adjusted prices: stock_ret already incorporates dividend reinvestment
            # Do NOT add div_amount separately (double-count). Just price + premium.
            stock_ret = min((S_ex - S) / S, (K - S) / S)  # capped if called away
            total_ret = stock_ret + prem_pct
            trades.append({'ret': total_ret, 'prem_pct': prem_pct,
                           'div_pct': float(div_amt)/S, 'ticker': ticker})
    if not trades: return {}
    arr = np.array([t['ret'] for t in trades])
    t_s, p_v = tstat(arr)
    return dict(strategy=f'CC around Ex-Div {days_before}d before 2%OTM',
                n_trades=len(trades), sharpe=sharpe(arr), win_rate=win_rate(arr),
                avg_ret_pct=float(arr.mean()*100),
                avg_premium_pct=float(np.mean([t['prem_pct'] for t in trades])*100),
                avg_div_pct=float(np.mean([t['div_pct'] for t in trades])*100),
                t_stat=t_s, p_value=p_v)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ROUND 27: DIVIDEND STRATEGIES")
    print("=" * 60)

    print("\nLoading price cache...")
    prices = load_prices()
    print(f"  {len(prices)} tickers loaded from cache")

    print("Fetching dividends...")
    divs = load_dividends(list(prices.keys()))
    print(f"  {len(divs)} tickers with dividend data")

    results = {}

    # ── 1. Dividend Capture ──
    print("\n[1] Dividend Capture (12 variants)...")
    cap_all = []
    for bb in [1, 2, 3]:
        for ha in [1, 3, 5, 10]:
            r = strat_capture(prices, divs, bb, ha)
            if r:
                cap_all.append(r)
                print(f"    buy-{bb}d sell+{ha}d: Sharpe={r['sharpe']:.3f} "
                      f"WR={r['win_rate']:.1%} avg={r['avg_ret_pct']:.3f}% n={r['n_trades']}")
    results['capture_all'] = cap_all
    if cap_all:
        best = max(cap_all, key=lambda x: x.get('sharpe', -9))
        results['capture_best'] = best

    # ── 2. Ex-Div Drift ──
    print("\n[2] Ex-Div Drift (5 hold periods)...")
    drift_all = []
    for hold in [3, 5, 10, 15, 20]:
        r = strat_exdiv_drift(prices, divs, hold)
        if r:
            drift_all.append(r)
            print(f"    hold-{hold}d: Sharpe={r['sharpe']:.3f} "
                  f"WR={r['win_rate']:.1%} avg={r['avg_ret_pct']:.3f}%")
    results['drift_all'] = drift_all
    if drift_all:
        results['drift_best'] = max(drift_all, key=lambda x: x.get('sharpe', -9))

    # ── 3. Dogs of the Dow ──
    print("\n[3] Dogs of the Dow...")
    for n in [5, 10]:
        r = strat_dogs(prices, divs, n)
        if r:
            results[f'dogs_{n}'] = r
            print(f"    Dogs-{n}: Ann.Sharpe={r['sharpe_annual']:.3f} "
                  f"MeanRet={r['mean_annual_return']:.1%} p={r['p_value']:.3f}")

    # ── 4. Aristocrats Momentum ──
    print("\n[4] Dividend Aristocrats Momentum...")
    r = strat_aristocrats_mom(prices, top_n=10)
    if r:
        results['aristocrats_mom'] = r
        print(f"    Sharpe={r['sharpe']:.3f} CAGR={r['cagr']:.1%} MaxDD={r['max_dd']:.1%}")

    # ── 5. High Yield Screen ──
    print("\n[5] High Yield Screen (top 25% quarterly)...")
    r = strat_high_yield(prices, divs)
    if r:
        results['high_yield'] = r
        print(f"    Sharpe={r['sharpe']:.3f} CAGR={r['cagr']:.1%} MaxDD={r['max_dd']:.1%}")

    # ── 6. Dividend Raise Signal ──
    print("\n[6] Dividend Raise Signal...")
    raise_all = []
    for min_r in [0.03, 0.05, 0.10]:
        for hold in [10, 20, 40]:
            r = strat_div_raise(prices, divs, hold=hold, min_raise=min_r)
            if r:
                raise_all.append(r)
                print(f"    >={int(min_r*100)}% hold-{hold}d: "
                      f"Sharpe={r['sharpe']:.3f} WR={r['win_rate']:.1%} "
                      f"n={r['n_trades']} p={r['p_value']:.3f}")
    results['raise_all'] = raise_all
    if raise_all:
        results['raise_best'] = max(raise_all, key=lambda x: x.get('sharpe', -9))

    # ── 7. Dividend Cut Short ──
    print("\n[7] Dividend Cut Short Signal...")
    cut_all = []
    for min_c in [0.10, 0.25, 0.50]:
        r = strat_div_cut(prices, divs, hold=20, min_cut=min_c)
        if r and r.get('n_trades', 0) > 0:
            cut_all.append(r)
            print(f"    >={int(min_c*100)}% cut: "
                  f"Sharpe={r['sharpe']:.3f} WR={r['win_rate']:.1%} "
                  f"n={r['n_trades']} p={r['p_value']:.3f}")
    results['cut_all'] = cut_all
    if cut_all:
        results['cut_best'] = max(cut_all, key=lambda x: x.get('sharpe', -9))

    # ── 8. Dividend Initiation ──
    print("\n[8] Dividend Initiation Signal...")
    r = strat_div_initiation(prices, divs)
    results['initiation'] = r
    if r.get('n_trades', 0) > 0:
        print(f"    n={r['n_trades']} Sharpe={r.get('sharpe','N/A'):.3f}")
    else:
        print(f"    {r.get('note', 'No events')}")

    # ── 9. Covered Calls Around Ex-Div ──
    print("\n[9] Covered Calls Around Ex-Div...")
    cc_all = []
    for db in [3, 5, 10]:
        r = strat_cc_exdiv(prices, divs, days_before=db)
        if r:
            cc_all.append(r)
            print(f"    {db}d before: Sharpe={r['sharpe']:.3f} "
                  f"WR={r['win_rate']:.1%} avg={r['avg_ret_pct']:.3f}% "
                  f"prem={r['avg_premium_pct']:.3f}%")
    results['cc_exdiv_all'] = cc_all
    if cc_all:
        results['cc_exdiv_best'] = max(cc_all, key=lambda x: x.get('sharpe', -9))

    # ── Save ──
    out = ROUNDS_DIR / 'dividend_results.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved → {out}")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("LEADERBOARD — Dividend Strategies (best Sharpe per type)")
    print("=" * 60)
    summary = []
    for key, label in [
        ('capture_best', 'Div Capture (best window)'),
        ('drift_best', 'Ex-Div Drift (best hold)'),
        ('dogs_10', 'Dogs of Dow top-10'),
        ('dogs_5', 'Dogs of Dow top-5'),
        ('aristocrats_mom', 'Aristocrats Momentum'),
        ('high_yield', 'High Yield Screen'),
        ('raise_best', 'Div Raise Signal (best)'),
        ('cut_best', 'Div Cut Short (best)'),
        ('cc_exdiv_best', 'CC around Ex-Div'),
    ]:
        r = results.get(key, {})
        if not r: continue
        sh = r.get('sharpe', r.get('sharpe_annual', np.nan))
        if sh is None: sh = np.nan
        strat = r.get('strategy', label)
        summary.append((strat, float(sh) if sh is not None else np.nan))

    for name, sh in sorted(summary, key=lambda x: x[1] if not np.isnan(x[1]) else -99, reverse=True):
        print(f"  {name:<50} {sh:+.3f}")

    return results

if __name__ == '__main__':
    main()
