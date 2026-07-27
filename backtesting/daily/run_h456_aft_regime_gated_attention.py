#!/usr/bin/env python3
"""
H456 — Adaptive Financial Transformer with Regime-Gated Attention for H198

Source: arXiv:2606.29347 (Sarkar, Jun 2026)
        "Adaptive Financial Transformer with Regime-Gated Attention for Stock Return Prediction"

Hypothesis: AFT groups 95 financial features into 11 semantic categories and uses a
Market Regime Encoder + Adaptive Gate Network to dynamically bias self-attention based
on latent market regimes. Paper also identifies and corrects sequence-alignment look-ahead
bugs common in transformer finance work. H456 ports AFT's regime-gated attention to the
H198 30-stock NASDAQ universe for cross-sectional ranking.

Variants:
  A: Full AFT — Market Regime Encoder + Adaptive Gate + 11-category feature groups, top-6
  B: AFT no regime encoder — plain transformer on feature groups, top-6 (ablation)
  C: AFT no adaptive gate — regime-encoded features but uniform attention, top-6
  D: Lightweight regime proxy — VIX+SPY 200MA state as regime input, momentum re-ranked, top-6
  E: H198 baseline 6-1m momentum top-6 (sanity check)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe >= 1.174 (H198 momentum baseline) AND MaxDD improvement
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY   = 'H456'
UNIVERSE   = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]
DATA_START  = '2012-01-01'
IS_START    = '2013-01-01'
IS_END      = '2020-12-31'
OOS_START   = '2021-01-01'
OOS_END     = '2026-07-25'
N_POSITIONS = 6

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 11 semantic feature categories (AFT design; mapped to OHLCV-derivable signals)
FEATURE_CATEGORIES = {
    'momentum_short':   ['ret_1m', 'ret_3m'],
    'momentum_long':    ['ret_6m', 'ret_12m'],
    'reversal':         ['ret_1w'],
    'volatility':       ['vol_20d', 'vol_60d'],
    'trend':            ['above_50d', 'above_200d'],
    'illusion_mom':     ['imom_6m'],
    'low_vol':          ['inv_vol_20d'],
    'price_level':      ['price_to_52wh'],
    'skewness':         ['skew_20d'],
    'drawdown':         ['max_dd_60d'],
    'regime_macro':     ['vix_level', 'spy_200ma'],
}


def download_data():
    print(f'Downloading {len(UNIVERSE)} stocks + VIX + SPY...')
    prices = yf.download(UNIVERSE, start=DATA_START, end=OOS_END,
                         auto_adjust=True, progress=False)['Close']
    prices = prices.dropna(how='all').ffill()
    vix = yf.download('^VIX', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close'].squeeze()
    spy = yf.download('SPY', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close'].squeeze()
    return prices, vix, spy


def build_features(prices: pd.DataFrame, vix: pd.Series, spy: pd.Series) -> dict:
    """Construct monthly feature panel for each stock (no look-ahead)."""
    daily_ret = prices.pct_change()
    monthly   = prices.resample('MS').first()
    feat = {}

    feat['ret_1m']      = monthly.pct_change().shift(1)
    feat['ret_3m']      = monthly.pct_change(3).shift(1)
    feat['ret_6m']      = monthly.pct_change(6).shift(1)
    feat['ret_12m']     = monthly.pct_change(12).shift(1)
    feat['ret_1w']      = prices.pct_change(5).resample('MS').last().shift(1)

    roll20 = daily_ret.rolling(20)
    roll60 = daily_ret.rolling(60)
    feat['vol_20d']     = roll20.std().resample('MS').last().shift(1) * np.sqrt(252)
    feat['vol_60d']     = roll60.std().resample('MS').last().shift(1) * np.sqrt(252)
    feat['skew_20d']    = roll20.skew().resample('MS').last().shift(1)

    feat['inv_vol_20d'] = 1.0 / feat['vol_20d'].replace(0, np.nan)

    # Price relative to 52-week high
    roll52w = prices.rolling(252)
    hi52    = roll52w.max().resample('MS').last().shift(1)
    feat['price_to_52wh'] = (monthly / hi52.reindex(monthly.index)).clip(0, 1)

    # Moving average flags (1=above, 0=below) — monthly close vs. 50d/200d MA
    ma50  = prices.rolling(50).mean().resample('MS').last().shift(1)
    ma200 = prices.rolling(200).mean().resample('MS').last().shift(1)
    feat['above_50d']  = (monthly > ma50.reindex(monthly.index)).astype(float)
    feat['above_200d'] = (monthly > ma200.reindex(monthly.index)).astype(float)

    # Max drawdown over 60 trading days
    rolling_max = prices.rolling(60).max()
    dd = (prices / rolling_max - 1)
    feat['max_dd_60d'] = dd.resample('MS').last().shift(1)

    # Illusion Momentum: compound - arithmetic (6m)
    def imom_6m(col):
        comp  = (1 + daily_ret[col]).rolling(126).apply(np.prod, raw=True) - 1
        arith = daily_ret[col].rolling(126).sum()
        return (comp - arith).resample('MS').last().shift(1)

    feat['imom_6m'] = pd.DataFrame({c: imom_6m(c) for c in prices.columns})

    # Macro regime features (cross-sectional; same value for all stocks at a date)
    vix_m  = vix.resample('MS').last().shift(1)
    spy200 = spy.rolling(200).mean()
    spyma  = (spy > spy200).astype(float).resample('MS').last().shift(1)
    feat['vix_level']   = pd.DataFrame({c: vix_m for c in prices.columns})
    feat['spy_200ma']   = pd.DataFrame({c: spyma for c in prices.columns})

    return feat


def compute_regime(vix_m: pd.Series, spy_ma: pd.Series) -> pd.Series:
    """
    Simple 3-state regime proxy (Calm/Turbulent/Crisis).
    Calm   = SPY above 200MA AND VIX < 20
    Crisis = VIX > 30
    Turbulent = otherwise
    Returns: 0=Calm, 1=Turbulent, 2=Crisis
    """
    regime = pd.Series(1, index=vix_m.index)  # default Turbulent
    regime[spy_ma.astype(bool) & (vix_m < 20)] = 0  # Calm
    regime[vix_m > 30] = 2                           # Crisis
    return regime


def aft_score(feat: dict, weights_by_regime: dict, regime: int,
              date: pd.Timestamp, use_adaptive_gate: bool = True,
              use_regime_encoder: bool = True) -> pd.Series:
    """
    Lightweight AFT scoring: weighted combination of feature categories.
    In the full AFT, this is learned; here we use IS-calibrated weights
    as a tractable proxy for the attention mechanism.

    weights_by_regime: {regime_int: {category: weight}} — IS-calibrated.
    """
    if use_regime_encoder and use_adaptive_gate:
        w = weights_by_regime.get(regime, weights_by_regime[1])
    elif not use_regime_encoder:
        w = weights_by_regime.get('uniform', {k: 1.0 for k in FEATURE_CATEGORIES})
    else:
        # regime encoder without gate — use regime but equal weights
        w = {k: 1.0 for k in FEATURE_CATEGORIES}

    scores = []
    for cat, feature_names in FEATURE_CATEGORIES.items():
        cat_score = []
        for fn in feature_names:
            if fn not in feat:
                continue
            row = feat[fn]
            if isinstance(row, pd.DataFrame):
                val = row.loc[date] if date in row.index else pd.Series(dtype=float)
            else:
                val = pd.Series(dtype=float)
            if val is not None and len(val) > 0:
                # Cross-sectional rank (0..1)
                ranked = val.rank(pct=True, na_option='keep')
                cat_score.append(ranked)
        if cat_score:
            cat_avg = pd.concat(cat_score, axis=1).mean(axis=1)
            scores.append(cat_avg * w.get(cat, 1.0))

    if not scores:
        return pd.Series(dtype=float)
    return pd.concat(scores, axis=1).mean(axis=1)


def calibrate_weights_is(feat: dict, fwd_ret: pd.DataFrame,
                         regime: pd.Series, is_dates) -> dict:
    """
    IS-calibrate per-regime feature category weights by IC with forward returns.
    Returns weights_by_regime dict.
    """
    weights = {}
    for r in [0, 1, 2]:
        r_dates = [d for d in is_dates if d in regime.index and regime.loc[d] == r]
        if len(r_dates) < 6:
            weights[r] = {k: 1.0 for k in FEATURE_CATEGORIES}
            continue
        cat_ics = {}
        for cat, feature_names in FEATURE_CATEGORIES.items():
            ics = []
            for fn in feature_names:
                if fn not in feat:
                    continue
                for dt in r_dates:
                    if dt not in fwd_ret.index:
                        continue
                    row_feat = feat[fn]
                    if isinstance(row_feat, pd.DataFrame) and dt in row_feat.index:
                        f_vals = row_feat.loc[dt].dropna()
                        r_vals = fwd_ret.loc[dt].reindex(f_vals.index).dropna()
                        common = f_vals.index.intersection(r_vals.index)
                        if len(common) >= 8:
                            ic = f_vals[common].corr(r_vals[common])
                            ics.append(ic if not np.isnan(ic) else 0.0)
            cat_ics[cat] = np.mean(ics) if ics else 0.0

        # Weight = max(0, IC) so negative-IC categories don't contribute
        raw = {k: max(0.0, v) for k, v in cat_ics.items()}
        total = sum(raw.values()) or 1.0
        weights[r] = {k: v / total for k, v in raw.items()}

    weights['uniform'] = {k: 1.0 / len(FEATURE_CATEGORIES) for k in FEATURE_CATEGORIES}
    return weights


def run_backtest(prices: pd.DataFrame, vix: pd.Series, spy: pd.Series) -> dict:
    feat    = build_features(prices, vix, spy)
    monthly = prices.resample('MS').first()
    fwd_ret = monthly.pct_change().shift(-1)

    vix_m  = vix.resample('MS').last().shift(1)
    spy200 = spy.rolling(200).mean()
    spy_ma = (spy > spy200).astype(float).resample('MS').last().shift(1)
    regime = compute_regime(vix_m, spy_ma)

    is_dates  = [d for d in fwd_ret.index if IS_START <= str(d.date()) <= IS_END]
    oos_dates = [d for d in fwd_ret.index if OOS_START <= str(d.date()) <= OOS_END]

    print('  Calibrating IS weights...')
    weights_by_regime = calibrate_weights_is(feat, fwd_ret, regime, is_dates)

    results = {}
    for var in ['A', 'B', 'C', 'D', 'E']:
        rets, dates = [], []
        use_regime  = var in ('A', 'C', 'D')
        use_gate    = var in ('A', 'B')

        for dt in oos_dates:
            if dt not in fwd_ret.index:
                continue
            ret_row = fwd_ret.loc[dt].dropna()
            if len(ret_row) < N_POSITIONS:
                continue

            if var == 'E':
                # Plain 6-1m momentum baseline
                if dt not in feat['ret_6m'].index:
                    continue
                sig = feat['ret_6m'].loc[dt].dropna()
                common = sig.index.intersection(ret_row.index)
                if len(common) < N_POSITIONS:
                    continue
                sel = sig[common].sort_values(ascending=False).head(N_POSITIONS).index
            elif var == 'D':
                # Lightweight regime proxy: re-rank momentum by regime strength
                if dt not in feat['ret_6m'].index:
                    continue
                sig = feat['ret_6m'].loc[dt].dropna()
                r   = int(regime.get(dt, 1))
                # In Calm: full momentum; Turbulent: blend with rev; Crisis: BIL
                if r == 2:
                    dates.append(dt)
                    rets.append(0.0)
                    continue
                common = sig.index.intersection(ret_row.index)
                if len(common) < N_POSITIONS:
                    continue
                if r == 1:
                    rev_sig = feat['ret_1m'].loc[dt].reindex(common)
                    combined = 0.7 * sig[common].rank(pct=True) + 0.3 * (-rev_sig).rank(pct=True)
                    sel = combined.sort_values(ascending=False).head(N_POSITIONS).index
                else:
                    sel = sig[common].sort_values(ascending=False).head(N_POSITIONS).index
            else:
                r = int(regime.get(dt, 1)) if use_regime else 1
                score = aft_score(feat, weights_by_regime, r, dt,
                                  use_adaptive_gate=use_gate,
                                  use_regime_encoder=use_regime)
                if score.empty:
                    continue
                common = score.index.intersection(ret_row.index)
                if len(common) < N_POSITIONS:
                    continue
                sel = score[common].sort_values(ascending=False).head(N_POSITIONS).index

            ret = ret_row.reindex(sel).mean()
            if not np.isnan(ret):
                rets.append(float(ret))
                dates.append(dt)

        results[var] = pd.Series(rets, index=dates, name=f'{STRATEGY}_{var}')
    return results


def evaluate(s: pd.Series, label: str) -> dict:
    r = s.dropna()
    if len(r) < 6:
        return {'sharpe': 0.0, 'cagr': 0.0, 'maxdd': 0.0, 'neg_years': 0}
    sharpe = r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else 0.0
    cum    = (1 + r).cumprod()
    n_yrs  = len(r) / 12
    cagr   = cum.iloc[-1] ** (1 / max(n_yrs, 1e-6)) - 1
    maxdd  = (cum / cum.cummax() - 1).min()
    ann    = r.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg    = int((ann < 0).sum())
    print(f'  {label:42s}  Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={maxdd:.1%}  NegYrs={neg}')
    return {'sharpe': round(sharpe, 3), 'cagr': round(cagr, 3),
            'maxdd': round(maxdd, 3), 'neg_years': neg}


def main():
    print(f'=== {STRATEGY} Adaptive Financial Transformer (Regime-Gated Attention) ===')
    print(f'IS: {IS_START}—{IS_END} | OOS: {OOS_START}—{OOS_END}')
    print(f'Gate: OOS Sharpe >= 1.174 (H198 baseline)')
    print()

    prices, vix, spy = download_data()
    results = run_backtest(prices, vix, spy)

    GATE = 1.174
    all_stats = {}

    # IS eval on full series for each var (refit for IS window)
    print('=== OOS Results ===')
    oos_stats = {}
    for v, s in results.items():
        mask = (s.index >= OOS_START) & (s.index <= OOS_END)
        oos_stats[v] = evaluate(s[mask], f'OOS Var{v}')

    print(f'\n=== Gate Check (OOS Sharpe >= {GATE}) ===')
    confirmed = []
    for v, st in oos_stats.items():
        status = 'PASS' if st['sharpe'] >= GATE else 'FAIL'
        print(f'  Var {v}: OOS Sharpe={st["sharpe"]:.3f} → {status}')
        if st['sharpe'] >= GATE:
            confirmed.append(v)

    if confirmed:
        print(f'\nCONFIRMED variants: {confirmed}')
    else:
        print('\nNOT CONFIRMED — all variants below gate')

    out = RESULTS_DIR / 'h456_results.json'
    payload = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat()[:10],
        'oos_stats': oos_stats,
        'confirmed_variants': confirmed,
    }
    out.write_text(json.dumps(payload, indent=2))
    print(f'\nResults saved to {out}')


if __name__ == '__main__':
    main()
