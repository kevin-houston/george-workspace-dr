#!/usr/bin/env python3
"""
Karpathy-style autoresearch loop: Volatility, Inter-market Rotation, Fixed Income
Backtest harness for vol_intermarket strategies
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

# ── Cache helpers ─────────────────────────────────────────────────────────────
CACHE_DIR = '/workspace/group/trading_eval/cache'
os.makedirs(CACHE_DIR, exist_ok=True)
ROUNDS_DIR = '/workspace/group/trading_eval/rounds'
os.makedirs(ROUNDS_DIR, exist_ok=True)

def cache_path(ticker):
    safe = ticker.replace('^', 'IDX_')
    return os.path.join(CACHE_DIR, f'vol_{safe}.pkl')

def fetch_price(ticker, start='2015-01-01'):
    cp = cache_path(ticker)
    if os.path.exists(cp):
        try:
            df = pickle.load(open(cp, 'rb'))
            # refresh if stale (last date older than 5 days)
            if not df.empty and (pd.Timestamp.today() - df.index[-1]).days < 5:
                return df
        except Exception:
            pass
    try:
        import yfinance as yf
        raw = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if raw.empty:
            return pd.DataFrame()
        # Strip timezone
        raw.index = raw.index.tz_localize(None) if raw.index.tz is not None else raw.index
        # Flatten multi-level columns if present
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        closes = raw[['Close']].copy()
        closes.columns = [ticker]
        pickle.dump(closes, open(cp, 'wb'))
        return closes
    except Exception as e:
        print(f"  [WARN] Could not fetch {ticker}: {e}")
        return pd.DataFrame()

def build_price_matrix(tickers, start='2015-01-01'):
    frames = []
    for t in tickers:
        df = fetch_price(t, start)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1)
    out = out.sort_index()
    # Strip tz just in case
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    return out

# ── Backtest metrics ──────────────────────────────────────────────────────────

def calc_metrics(rets, spy_rets, costs_per_trade=0.0001, n_trades=0, label='Strategy'):
    """Compute Sharpe, CAGR, MaxDD, WinRate, N_Trades, SPY_Corr"""
    rets = rets.dropna()
    if len(rets) < 20:
        return dict(label=label, sharpe=0, cagr=0, max_dd=0, win_rate=0, n_trades=n_trades, spy_corr=0)

    # Cost drag spread over period
    total_cost = costs_per_trade * n_trades
    n_years = len(rets) / 252
    daily_cost_drag = total_cost / max(len(rets), 1)
    rets_net = rets - daily_cost_drag

    ann_ret = (1 + rets_net).prod() ** (252 / len(rets_net)) - 1
    ann_vol = rets_net.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    cum = (1 + rets_net).cumprod()
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    max_dd = dd.min()

    win_rate = (rets_net > 0).mean()

    # SPY correlation
    common = rets_net.index.intersection(spy_rets.index)
    if len(common) > 20:
        spy_corr = rets_net.loc[common].corr(spy_rets.loc[common])
    else:
        spy_corr = np.nan

    return dict(
        label=label,
        sharpe=round(float(sharpe), 3),
        cagr=round(float(ann_ret) * 100, 2),
        max_dd=round(float(max_dd) * 100, 2),
        win_rate=round(float(win_rate) * 100, 2),
        n_trades=n_trades,
        spy_corr=round(float(spy_corr) if not np.isnan(spy_corr) else 0, 3)
    )

# ─────────────────────────────────────────────────────────────────────────────
# ROUND V1 — VIX Term Structure Strategies
# ─────────────────────────────────────────────────────────────────────────────

def run_vix_strategies(prices):
    results = []
    spy_r = prices['SPY'].pct_change().shift(-1)  # next-day returns
    spy_rets = prices['SPY'].pct_change()

    if '^VIX' not in prices.columns:
        print("  [WARN] ^VIX not available, skipping VIX strategies")
        return results

    vix = prices['^VIX']

    # --- Strategy 1: VIX Mean Reversion ---
    # Long SPY when VIX > 30, exit when VIX < 22
    in_trade = False
    position = pd.Series(0.0, index=prices.index)
    n_trades = 0
    for i, dt in enumerate(prices.index):
        v = vix.iloc[i]
        if pd.isna(v):
            continue
        if not in_trade and v > 30:
            in_trade = True
            n_trades += 1
        elif in_trade and v < 22:
            in_trade = False
        position.iloc[i] = 1.0 if in_trade else 0.0

    pos_shift = position.shift(1).fillna(0)
    spy_daily = prices['SPY'].pct_change()
    rets = pos_shift * spy_daily
    results.append(calc_metrics(rets, spy_rets, 0.0001, n_trades, 'V1-VIX_MeanReversion'))

    # --- Strategy 2: VIX Momentum ---
    vix_5d = vix.diff(5)
    position2 = pd.Series(0.0, index=prices.index)
    position2[vix_5d > 3] = -1.0   # rising VIX = short SPY
    position2[vix_5d < -3] = 1.0   # falling VIX = long SPY
    pos2_shift = position2.shift(1).fillna(0)
    rets2 = pos2_shift * spy_daily
    n2 = int((position2.diff().abs() > 0).sum())
    results.append(calc_metrics(rets2, spy_rets, 0.0001, n2, 'V1-VIX_Momentum'))

    # --- Strategy 3: VIX Level Regime ---
    # VIX < 15: long UVXY; VIX 15-25: long SPY; VIX > 25: long GLD+TLT
    gld_r = prices.get('GLD', pd.Series(np.nan, index=prices.index)).pct_change()
    tlt_r = prices.get('TLT', pd.Series(np.nan, index=prices.index)).pct_change()
    uvxy_r = prices.get('UVXY', pd.Series(np.nan, index=prices.index)).pct_change()

    regime_rets = []
    n3 = 0
    prev_regime = None
    for i, dt in enumerate(prices.index[1:], 1):
        v = vix.iloc[i-1]  # signal from prev day
        if pd.isna(v):
            regime_rets.append(np.nan)
            continue
        if v < 15:
            r = uvxy_r.iloc[i] if not pd.isna(uvxy_r.iloc[i]) else 0
            regime = 'UVXY'
        elif v <= 25:
            r = spy_daily.iloc[i] if not pd.isna(spy_daily.iloc[i]) else 0
            regime = 'SPY'
        else:
            r_g = gld_r.iloc[i] if not pd.isna(gld_r.iloc[i]) else 0
            r_t = tlt_r.iloc[i] if not pd.isna(tlt_r.iloc[i]) else 0
            r = (r_g + r_t) / 2
            regime = 'GLD+TLT'
        if regime != prev_regime:
            n3 += 1
        prev_regime = regime
        regime_rets.append(r)

    rets3 = pd.Series(regime_rets, index=prices.index[1:])
    results.append(calc_metrics(rets3, spy_rets, 0.0002, n3, 'V1-VIX_LevelRegime'))

    # --- Strategy 4: VIX Contango Roll ---
    # Short vol (long SVXY) when VIX < 20; exit when VIX > 25
    svxy_r = prices.get('SVXY', pd.Series(np.nan, index=prices.index)).pct_change()
    in_contango = False
    pos4 = pd.Series(0.0, index=prices.index)
    n4 = 0
    for i, dt in enumerate(prices.index):
        v = vix.iloc[i]
        if pd.isna(v):
            continue
        if not in_contango and v < 20:
            in_contango = True
            n4 += 1
        elif in_contango and v > 25:
            in_contango = False
            n4 += 1
        pos4.iloc[i] = 1.0 if in_contango else 0.0

    pos4_shift = pos4.shift(1).fillna(0)
    rets4 = pos4_shift * svxy_r
    rets4 = rets4.where(~svxy_r.isna(), other=0)
    results.append(calc_metrics(rets4.dropna(), spy_rets, 0.0002, n4, 'V1-VIX_ContangoRoll'))

    # --- Strategy 5: VIX Spike-and-Recover ---
    # 3-day window after VIX closes >35 → long SPY
    spike_signal = vix > 35
    pos5 = pd.Series(0.0, index=prices.index)
    n5 = 0
    active_days = 0
    in_spike = False
    for i in range(len(prices.index)):
        if spike_signal.iloc[i]:
            active_days = 3
            if not in_spike:
                n5 += 1
                in_spike = True
        if active_days > 0:
            pos5.iloc[i] = 1.0
            active_days -= 1
        else:
            pos5.iloc[i] = 0.0
            in_spike = False

    pos5_shift = pos5.shift(1).fillna(0)
    rets5 = pos5_shift * spy_daily
    results.append(calc_metrics(rets5, spy_rets, 0.0001, n5, 'V1-VIX_SpikeRecover'))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# ROUND V2 — Inter-Market Rotation
# ─────────────────────────────────────────────────────────────────────────────

def run_intermarket_strategies(prices):
    results = []
    spy_rets = prices['SPY'].pct_change()
    spy_close = prices['SPY']

    def safe_r(ticker):
        if ticker in prices.columns:
            return prices[ticker].pct_change()
        return pd.Series(0.0, index=prices.index)

    def safe_c(ticker):
        if ticker in prices.columns:
            return prices[ticker]
        return pd.Series(np.nan, index=prices.index)

    # --- IM1: Equity/Bond Rotation ---
    sma50 = spy_close.rolling(50).mean()
    sma200 = spy_close.rolling(200).mean()
    tlt_r = safe_r('TLT')
    spy_r = safe_r('SPY')

    pos_im1 = (sma50 > sma200).astype(float)  # 1=SPY, 0=TLT
    rets_im1 = pos_im1.shift(1) * spy_r + (1 - pos_im1.shift(1)) * tlt_r
    n_im1 = int((pos_im1.diff().abs() > 0.5).sum())
    results.append(calc_metrics(rets_im1.dropna(), spy_rets, 0.0001, n_im1, 'IM1-Equity_Bond_Rotation'))

    # --- IM2: Risk Parity Lite (SPY, TLT, GLD) monthly rebalance ---
    assets_rp = ['SPY', 'TLT', 'GLD']
    avail_rp = [a for a in assets_rp if a in prices.columns]
    if len(avail_rp) >= 2:
        px_rp = prices[avail_rp].copy()
        returns_rp = px_rp.pct_change()
        target_vol = 0.10 / np.sqrt(252)
        # Rolling 21-day vol
        roll_vol = returns_rp.rolling(21).std()
        # weights = target_vol / rolling_vol, normalize
        raw_w = target_vol / roll_vol.replace(0, np.nan)
        w_sum = raw_w.sum(axis=1)
        weights_rp = raw_w.div(w_sum, axis=0).fillna(1/len(avail_rp))
        # Monthly rebalance: use end-of-month weights
        weights_monthly = weights_rp.resample('ME').last().reindex(weights_rp.index, method='ffill')
        rets_rp = (weights_monthly.shift(1) * returns_rp).sum(axis=1)
        n_rp = 12 * max(1, int(len(prices) / 252))  # approx monthly rebalances
        results.append(calc_metrics(rets_rp.dropna(), spy_rets, 0.0001, n_rp, 'IM2-RiskParity_Lite'))
    else:
        results.append(dict(label='IM2-RiskParity_Lite', sharpe=0, cagr=0, max_dd=0, win_rate=0, n_trades=0, spy_corr=0))

    # --- IM3: Momentum Rotation (top 2 of SPY/TLT/GLD/USO/UUP) ---
    assets_mom = ['SPY', 'TLT', 'GLD', 'USO', 'UUP']
    avail_mom = [a for a in assets_mom if a in prices.columns]
    if len(avail_mom) >= 2:
        px_mom = prices[avail_mom]
        ret60 = px_mom.pct_change(60)
        # Monthly ranking
        monthly_dates = px_mom.resample('ME').last().index
        pos_mom = pd.DataFrame(0.0, index=px_mom.index, columns=avail_mom)
        for i, dt in enumerate(px_mom.index):
            # find last month-end <= dt
            past = monthly_dates[monthly_dates <= dt]
            if len(past) == 0:
                continue
            last_me = past[-1]
            r = ret60.loc[last_me] if last_me in ret60.index else ret60.iloc[:ret60.index.get_loc(dt)+1].iloc[-1]
            ranked = r.dropna().nlargest(2).index.tolist()
            if ranked:
                pos_mom.loc[dt, ranked] = 1.0 / len(ranked)

        rets_mom_arr = (pos_mom.shift(1) * prices[avail_mom].pct_change()).sum(axis=1)
        n_mom = len(monthly_dates) * 2
        results.append(calc_metrics(rets_mom_arr.dropna(), spy_rets, 0.0001, n_mom, 'IM3-Momentum_Rotation'))
    else:
        results.append(dict(label='IM3-Momentum_Rotation', sharpe=0, cagr=0, max_dd=0, win_rate=0, n_trades=0, spy_corr=0))

    # --- IM4: Dual Momentum ---
    # Absolute: SPY if 12m return > 0, else TLT
    # Relative: compare SPY to IEF
    ief_r = safe_r('IEF')
    ret252_spy = spy_close.pct_change(252)
    ief_close = safe_c('IEF')
    ret252_ief = ief_close.pct_change(252)

    pos_dm = pd.Series(0.0, index=prices.index)  # 1=SPY, -1=TLT blend
    for i, dt in enumerate(prices.index):
        abs_mom = ret252_spy.iloc[i]
        rel_spy = ret252_spy.iloc[i]
        rel_ief = ret252_ief.iloc[i] if not pd.isna(ret252_ief.iloc[i]) else 0
        if pd.isna(abs_mom):
            continue
        if abs_mom > 0 and rel_spy > rel_ief:
            pos_dm.iloc[i] = 1.0  # SPY
        else:
            pos_dm.iloc[i] = -1.0  # TLT

    # 1 = SPY, -1 = TLT
    dm_spy_alloc = (pos_dm == 1).astype(float)
    dm_tlt_alloc = (pos_dm == -1).astype(float)
    rets_dm = dm_spy_alloc.shift(1) * spy_r + dm_tlt_alloc.shift(1) * tlt_r
    n_dm = int((pos_dm.diff().abs() > 0).sum())
    results.append(calc_metrics(rets_dm.dropna(), spy_rets, 0.0001, n_dm, 'IM4-DualMomentum'))

    # --- IM5: Dollar/Equity Inverse ---
    uup_close = safe_c('UUP')
    uup_mom20 = uup_close.pct_change(20)
    # Strong USD (positive UUP 20d) → reduce SPY, increase TLT
    pos_im5_spy = pd.Series(0.5, index=prices.index)
    pos_im5_tlt = pd.Series(0.5, index=prices.index)
    strong_usd = uup_mom20 > 0
    pos_im5_spy[strong_usd] = 0.25
    pos_im5_tlt[strong_usd] = 0.75
    pos_im5_spy[~strong_usd] = 0.75
    pos_im5_tlt[~strong_usd] = 0.25
    rets_im5 = pos_im5_spy.shift(1) * spy_r + pos_im5_tlt.shift(1) * tlt_r
    n_im5 = int((strong_usd.astype(int).diff().abs() > 0).sum())
    results.append(calc_metrics(rets_im5.dropna(), spy_rets, 0.0001, n_im5, 'IM5-Dollar_Equity_Inverse'))

    # --- IM6: Oil Shock Signal ---
    uso_r10 = safe_c('USO').pct_change(10)
    oil_shock = uso_r10 > 0.08
    shy_r = safe_r('SHY')
    gld_r = safe_r('GLD')
    # Oil shock: rotate to TLT+GLD+SHY equally; normal: hold SPY
    pos_im6_spy = (~oil_shock).astype(float)
    pos_im6_def = (oil_shock).astype(float) / 3
    rets_im6 = pos_im6_spy.shift(1) * spy_r + pos_im6_def.shift(1) * (tlt_r + gld_r + shy_r)
    n_im6 = int((oil_shock.astype(int).diff().abs() > 0).sum())
    results.append(calc_metrics(rets_im6.dropna(), spy_rets, 0.0001, n_im6, 'IM6-OilShock_Signal'))

    # --- IM7: Credit Spread Signal ---
    hyg_close = safe_c('HYG')
    ief_close2 = safe_c('IEF')
    hyg_ief_ratio = hyg_close / ief_close2
    hyg_ief_mom = hyg_ief_ratio.pct_change(20)
    tight_spreads = hyg_ief_mom > 0  # HYG outperforming = tight
    pos_im7_spy = tight_spreads.astype(float)
    pos_im7_tlt = (~tight_spreads).astype(float)
    rets_im7 = pos_im7_spy.shift(1) * spy_r + pos_im7_tlt.shift(1) * tlt_r
    n_im7 = int((tight_spreads.astype(int).diff().abs() > 0).sum())
    results.append(calc_metrics(rets_im7.dropna(), spy_rets, 0.0001, n_im7, 'IM7-CreditSpread_Signal'))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# ROUND FI1 — Fixed Income Strategies
# ─────────────────────────────────────────────────────────────────────────────

def run_fixed_income_strategies(prices):
    results = []
    spy_rets = prices['SPY'].pct_change()

    def safe_r(ticker):
        if ticker in prices.columns:
            return prices[ticker].pct_change()
        return pd.Series(0.0, index=prices.index)

    def safe_c(ticker):
        if ticker in prices.columns:
            return prices[ticker]
        return pd.Series(np.nan, index=prices.index)

    tlt_r = safe_r('TLT')
    ief_r = safe_r('IEF')
    shy_r = safe_r('SHY')
    hyg_r = safe_r('HYG')
    lqd_r = safe_r('LQD')
    tip_r = safe_r('TIP')
    emb_r = safe_r('EMB')

    # --- FI1: Duration Momentum (60d rank of TLT, IEF, SHY) ---
    dur_assets = ['TLT', 'IEF', 'SHY']
    avail_dur = [a for a in dur_assets if a in prices.columns]
    if len(avail_dur) >= 2:
        px_dur = prices[avail_dur]
        ret60_dur = px_dur.pct_change(60)
        pos_fi1 = pd.DataFrame(0.0, index=px_dur.index, columns=avail_dur)
        for i in range(1, len(px_dur)):
            r = ret60_dur.iloc[i].dropna()
            if r.empty:
                continue
            best = r.idxmax()
            pos_fi1.iloc[i][best] = 1.0
        rets_fi1 = (pos_fi1.shift(1) * prices[avail_dur].pct_change()).sum(axis=1)
        n_fi1 = int((pos_fi1.diff().abs().sum(axis=1) > 0).sum())
        results.append(calc_metrics(rets_fi1.dropna(), spy_rets, 0.0001, n_fi1, 'FI1-Duration_Momentum'))
    else:
        results.append(dict(label='FI1-Duration_Momentum', sharpe=0, cagr=0, max_dd=0, win_rate=0, n_trades=0, spy_corr=0))

    # --- FI2: Yield Curve Trade ---
    ief_mom = safe_c('IEF').pct_change(60)
    shy_mom = safe_c('SHY').pct_change(60)
    steepening = ief_mom > shy_mom  # long TLT
    pos_fi2 = pd.Series(0.0, index=prices.index)
    pos_fi2[steepening] = 1.0    # long TLT
    pos_fi2[~steepening] = -1.0  # short TLT → use SHY as proxy
    rets_fi2_long = pos_fi2.clip(lower=0).shift(1) * tlt_r
    rets_fi2_short = (-pos_fi2.clip(upper=0)).shift(1) * shy_r  # flattening: go to SHY
    rets_fi2 = rets_fi2_long + rets_fi2_short
    n_fi2 = int((steepening.astype(int).diff().abs() > 0).sum())
    results.append(calc_metrics(rets_fi2.dropna(), spy_rets, 0.0001, n_fi2, 'FI2-YieldCurve_Trade'))

    # --- FI3: Credit Rotation ---
    hyg_mom60 = safe_c('HYG').pct_change(60)
    lqd_mom60 = safe_c('LQD').pct_change(60)
    ief_mom60 = safe_c('IEF').pct_change(60)
    risk_on_credit = (hyg_mom60 > lqd_mom60) & (lqd_mom60 > ief_mom60)
    pos_fi3_hyg = risk_on_credit.astype(float)
    pos_fi3_ief = (~risk_on_credit).astype(float)
    rets_fi3 = pos_fi3_hyg.shift(1) * hyg_r + pos_fi3_ief.shift(1) * ief_r
    n_fi3 = int((risk_on_credit.astype(int).diff().abs() > 0).sum())
    results.append(calc_metrics(rets_fi3.dropna(), spy_rets, 0.0001, n_fi3, 'FI3-Credit_Rotation'))

    # --- FI4: Inflation Protection ---
    tip_mom60 = safe_c('TIP').pct_change(60)
    ief_m60 = safe_c('IEF').pct_change(60)
    inflation_rising = tip_mom60 > ief_m60
    pos_fi4_tip = inflation_rising.astype(float)
    pos_fi4_ief = (~inflation_rising).astype(float)
    rets_fi4 = pos_fi4_tip.shift(1) * tip_r + pos_fi4_ief.shift(1) * ief_r
    n_fi4 = int((inflation_rising.astype(int).diff().abs() > 0).sum())
    results.append(calc_metrics(rets_fi4.dropna(), spy_rets, 0.0001, n_fi4, 'FI4-Inflation_Protection'))

    # --- FI5: EM vs DM Bonds ---
    emb_mom60 = safe_c('EMB').pct_change(60)
    lqd_m60 = safe_c('LQD').pct_change(60)
    em_wins = emb_mom60 > lqd_m60
    pos_fi5_emb = em_wins.astype(float)
    pos_fi5_lqd = (~em_wins).astype(float)
    rets_fi5 = pos_fi5_emb.shift(1) * emb_r + pos_fi5_lqd.shift(1) * lqd_r
    n_fi5 = int((em_wins.astype(int).diff().abs() > 0).sum())
    results.append(calc_metrics(rets_fi5.dropna(), spy_rets, 0.0001, n_fi5, 'FI5-EM_vs_DM_Bonds'))

    # --- FI6: Total Return Bond Ladder ---
    ladder_assets = ['TLT', 'IEF', 'SHY']
    avail_ladder = [a for a in ladder_assets if a in prices.columns]
    if len(avail_ladder) >= 1:
        px_ladder = prices[avail_ladder]
        w = 1.0 / len(avail_ladder)
        rets_fi6 = (px_ladder.pct_change() * w).sum(axis=1)
        # Monthly rebalance implied
        n_fi6 = 12 * max(1, int(len(prices) / 252))
        results.append(calc_metrics(rets_fi6.dropna(), spy_rets, 0.0001, n_fi6, 'FI6-BondLadder_Baseline'))
    else:
        results.append(dict(label='FI6-BondLadder_Baseline', sharpe=0, cagr=0, max_dd=0, win_rate=0, n_trades=0, spy_corr=0))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def print_table(title, results, sort_by='sharpe', top_n=None):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")
    sorted_r = sorted(results, key=lambda x: x.get(sort_by, 0), reverse=True)
    if top_n:
        sorted_r = sorted_r[:top_n]
    hdr = f"{'Strategy':<35} {'Sharpe':>7} {'CAGR%':>7} {'MaxDD%':>7} {'Win%':>6} {'Trades':>7} {'SPY_Corr':>9}"
    print(hdr)
    print('-' * 72)
    for r in sorted_r:
        print(f"{r['label']:<35} {r['sharpe']:>7.3f} {r['cagr']:>7.2f} {r['max_dd']:>7.2f} "
              f"{r['win_rate']:>6.1f} {r['n_trades']:>7} {r['spy_corr']:>9.3f}")

def main():
    print("\n" + "="*72)
    print("  VOL / INTERMARKET / FIXED INCOME BACKTEST HARNESS")
    print("  Period: 2015-01-01 to present")
    print("="*72)

    # All tickers needed
    all_tickers = [
        '^VIX', 'UVXY', 'VXZ', 'SVXY', 'SPY',
        'TLT', 'GLD', 'SLV', 'USO', 'UUP', 'IEF', 'HYG', 'IWM',
        'SHY', 'LQD', 'TIP', 'EMB'
    ]

    print("\nFetching price data...")
    prices = build_price_matrix(all_tickers, start='2015-01-01')

    if prices.empty:
        print("ERROR: No price data fetched. Exiting.")
        return

    print(f"Price matrix shape: {prices.shape}")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"Tickers loaded: {list(prices.columns)}")

    # SPY baseline
    spy_rets = prices['SPY'].pct_change()
    spy_metrics = calc_metrics(spy_rets.dropna(), spy_rets, 0, 0, 'SPY_Benchmark')
    print(f"\nSPY Benchmark: Sharpe={spy_metrics['sharpe']:.3f}, CAGR={spy_metrics['cagr']:.2f}%, MaxDD={spy_metrics['max_dd']:.2f}%")

    # Run strategies
    print("\nRunning Round V1 — VIX Strategies...")
    vix_results = run_vix_strategies(prices)

    print("Running Round V2 — Inter-Market Rotation...")
    im_results = run_intermarket_strategies(prices)

    print("Running Round FI1 — Fixed Income...")
    fi_results = run_fixed_income_strategies(prices)

    # Print tables
    print_table("ROUND V1 — VIX Term Structure (Top 5 by Sharpe)", vix_results, sort_by='sharpe', top_n=5)
    print_table("ROUND V2 — Inter-Market Rotation (All 7)", im_results, sort_by='sharpe')
    print_table("ROUND FI1 — Fixed Income (All 6)", fi_results, sort_by='sharpe')

    # Best overall
    all_results = vix_results + im_results + fi_results
    champion = max(all_results, key=lambda x: x['sharpe'])

    print(f"\n{'='*72}")
    print(f"  CHAMPION (Best Sharpe Across All Categories)")
    print(f"{'='*72}")
    print(f"  Strategy : {champion['label']}")
    print(f"  Sharpe   : {champion['sharpe']:.3f}")
    print(f"  CAGR     : {champion['cagr']:.2f}%")
    print(f"  Max DD   : {champion['max_dd']:.2f}%")
    print(f"  Win Rate : {champion['win_rate']:.1f}%")
    print(f"  SPY Corr : {champion['spy_corr']:.3f}")

    # Most diversifying: lowest SPY corr with positive Sharpe
    pos_sharpe = [r for r in all_results if r['sharpe'] > 0]
    if pos_sharpe:
        most_div = min(pos_sharpe, key=lambda x: x['spy_corr'])
    else:
        most_div = min(all_results, key=lambda x: x['spy_corr'])

    print(f"\n{'='*72}")
    print(f"  MOST DIVERSIFYING (Lowest SPY Correlation, Positive Sharpe)")
    print(f"{'='*72}")
    print(f"  Strategy : {most_div['label']}")
    print(f"  Sharpe   : {most_div['sharpe']:.3f}")
    print(f"  CAGR     : {most_div['cagr']:.2f}%")
    print(f"  SPY Corr : {most_div['spy_corr']:.3f}")

    # All strategies sorted by SPY corr
    print(f"\n  Bottom 5 by SPY Correlation (most diversifying):")
    sorted_div = sorted(all_results, key=lambda x: x['spy_corr'])[:5]
    for r in sorted_div:
        print(f"    {r['label']:<35} corr={r['spy_corr']:>7.3f}  sharpe={r['sharpe']:>6.3f}")

    # Save results
    output = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "spy_benchmark": spy_metrics,
        "vix_results": sorted(vix_results, key=lambda x: x['sharpe'], reverse=True),
        "intermarket_results": sorted(im_results, key=lambda x: x['sharpe'], reverse=True),
        "fixed_income_results": sorted(fi_results, key=lambda x: x['sharpe'], reverse=True),
        "champion": champion,
        "most_diversifying": most_div
    }

    out_path = '/workspace/group/trading_eval/rounds/vol_intermarket_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n{'='*72}")
    print(f"  Results saved to: {out_path}")
    print(f"{'='*72}\n")


if __name__ == '__main__':
    main()
