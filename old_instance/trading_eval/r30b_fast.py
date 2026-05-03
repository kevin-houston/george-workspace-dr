"""
R30b: Multi-Quarter SUE Elastic Net PEAD — Long-Short Version (Optimized)
Walk-forward by QUARTER rather than observation to reduce model fits from ~500 to ~40.
"""

import json
import pickle
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import ElasticNetCV
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings('ignore')

TICKERS = ['AAPL','MSFT','GOOGL','AMZN','META','NVDA','JPM','JNJ','XOM',
           'WMT','BAC','PG','UNH','HD','CVX','LLY','MRK','PFE','KO','PEP','TMO','COST']

CACHE_DIR = Path('/workspace/group/trading_eval/cache')

# ─── Data Loaders ───────────────────────────────────────────────────────────

def load_earnings(ticker):
    path = CACHE_DIR / 'earnings' / f'{ticker}_earnings.json'
    if not path.exists():
        return []
    d = json.loads(path.read_text())
    quarters = d.get('quarterlyEarnings', [])
    records = []
    for q in quarters:
        try:
            records.append({
                'ticker': ticker,
                'fiscalDate': q['fiscalDateEnding'],
                'reportedDate': pd.to_datetime(q['reportedDate']),
                'sue': float(q['surprisePercentage'])
            })
        except (KeyError, ValueError):
            continue
    return sorted(records, key=lambda x: x['reportedDate'])

def load_prices(ticker):
    path = CACHE_DIR / f'{ticker}_15yr.pkl'
    if not path.exists():
        return None
    prices = pickle.load(open(path, 'rb')).squeeze()
    if hasattr(prices.index, 'tz') and prices.index.tz is not None:
        prices = prices.tz_localize(None)
    return prices

def get_forward_return(prices, start_date, n_days=20):
    future = prices[prices.index >= start_date]
    if len(future) < n_days + 1:
        return np.nan
    return (future.iloc[n_days] / future.iloc[0]) - 1

# ─── Feature Engineering ────────────────────────────────────────────────────

def build_features(earnings_records, prices):
    rows = []
    for i in range(len(earnings_records)):
        rec = earnings_records[i]
        if i < 4:
            continue
        history = [earnings_records[j]['sue'] for j in range(max(0, i-12), i)]
        if len(history) < 4:
            continue
        # Pad to 12
        while len(history) < 12:
            history = [0.0] + history
        sue_q1_12 = history[-12:]
        mean_sue_4q = np.mean(history[-4:])
        std_sue_4q = np.std(history[-4:]) if len(history) >= 4 else 0.0
        y4 = history[-4:]
        x4 = np.arange(4)
        trend_sue = np.polyfit(x4, y4, 1)[0]

        fwd_ret = get_forward_return(prices, rec['reportedDate'])
        if np.isnan(fwd_ret):
            continue
        row = {
            'ticker': rec['ticker'],
            'reportedDate': rec['reportedDate'],
            'sue_current': rec['sue'],
        }
        for k, v in enumerate(sue_q1_12):
            row[f'sue_q{k+1}'] = v
        row['mean_sue_4q'] = mean_sue_4q
        row['std_sue_4q'] = std_sue_4q
        row['trend_sue'] = trend_sue
        row['fwd_ret'] = fwd_ret
        rows.append(row)
    return rows

FEATURE_COLS = [f'sue_q{i}' for i in range(1,13)] + ['mean_sue_4q','std_sue_4q','trend_sue']

# ─── Walk-Forward by Calendar Quarter ────────────────────────────────────────

def walk_forward_quarter(df_all):
    """
    Train on all data before each calendar quarter, predict that quarter.
    Much faster than per-observation fitting.
    """
    df_all = df_all.sort_values('reportedDate').reset_index(drop=True)
    # Assign calendar quarter
    df_all['cal_quarter'] = df_all['reportedDate'].dt.to_period('Q')
    quarters = sorted(df_all['cal_quarter'].unique())

    predictions = []
    MIN_TRAIN = 30  # need at least 30 training observations

    for i, q in enumerate(quarters):
        train = df_all[df_all['cal_quarter'] < q]
        test = df_all[df_all['cal_quarter'] == q]

        if len(train) < MIN_TRAIN:
            continue
        if len(test) == 0:
            continue

        X_train = train[FEATURE_COLS].values
        y_train = train['fwd_ret'].values
        X_test = test[FEATURE_COLS].values

        scaler = StandardScaler()
        X_tr_scaled = scaler.fit_transform(X_train)
        X_te_scaled = scaler.transform(X_test)

        try:
            model = ElasticNetCV(
                l1_ratio=[0.1, 0.5, 0.7, 0.9, 0.95, 1.0],
                cv=5,
                max_iter=2000,
                random_state=42,
                n_jobs=-1
            )
            model.fit(X_tr_scaled, y_train)
            preds = model.predict(X_te_scaled)
        except Exception as e:
            print(f"  Quarter {q}: model failed ({e}), skipping")
            continue

        for j, (_, row) in enumerate(test.iterrows()):
            r = row.to_dict()
            r['predicted_return'] = preds[j]
            predictions.append(r)

        if i % 5 == 0:
            print(f"  Processed quarter {q} ({i+1}/{len(quarters)}), train_n={len(train)}, test_n={len(test)}")

    return pd.DataFrame(predictions)

# ─── Strategy Simulation ─────────────────────────────────────────────────────

def simulate_strategy(preds_df, threshold=0.0, long_short=True):
    trades = []
    for _, row in preds_df.iterrows():
        pred = row['predicted_return']
        if long_short:
            if pred > threshold:
                direction = 1
            elif pred < -threshold:
                direction = -1
            else:
                continue
        else:
            if pred > threshold:
                direction = 1
            else:
                continue
        trades.append({
            'ticker': row['ticker'],
            'date': row['reportedDate'],
            'direction': direction,
            'actual_return': row['fwd_ret'] * direction,
            'raw_return': row['fwd_ret'],
            'pred': pred,
        })
    return trades

def compute_metrics(trades, label=""):
    if not trades:
        return {'label': label, 'sharpe': np.nan, 'win_rate': np.nan,
                'n_long': 0, 'n_short': 0, 'cagr': np.nan, 'max_dd': np.nan,
                'info_ratio': np.nan, 'n_trades': 0, 'mean_ret': np.nan}

    df = pd.DataFrame(trades)
    df = df.sort_values('date').reset_index(drop=True)

    rets = df['actual_return'].values
    n = len(rets)
    n_long = int((df['direction'] == 1).sum())
    n_short = int((df['direction'] == -1).sum())
    win_rate = float((rets > 0).mean())
    mean_ret = float(rets.mean())
    std_ret = float(rets.std())

    date_range_days = (df['date'].max() - df['date'].min()).days
    if date_range_days < 1:
        trades_per_year = n
    else:
        trades_per_year = n / (date_range_days / 365.25)

    sharpe = float(mean_ret / std_ret * np.sqrt(trades_per_year)) if std_ret > 0 else np.nan
    info_ratio = float(mean_ret / std_ret) if std_ret > 0 else np.nan

    cum = np.cumprod(1 + rets)
    years = date_range_days / 365.25 if date_range_days > 1 else 1
    cagr = float(cum[-1] ** (1 / years) - 1)

    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    max_dd = float(dd.min())

    return {
        'label': label,
        'sharpe': round(sharpe, 4),
        'win_rate': round(win_rate, 4),
        'n_long': n_long,
        'n_short': n_short,
        'n_trades': n,
        'cagr': round(cagr, 4),
        'max_dd': round(max_dd, 4),
        'info_ratio': round(info_ratio, 4),
        'mean_ret': round(mean_ret, 4),
    }

# ─── Baseline ────────────────────────────────────────────────────────────────

def sue_baseline(all_rows, long_thresh=3.0, short_thresh=-3.0, long_short=False):
    trades = []
    for row in all_rows:
        sue = row['sue_current']
        if sue > long_thresh:
            direction = 1
        elif long_short and sue < short_thresh:
            direction = -1
        else:
            continue
        trades.append({
            'ticker': row['ticker'],
            'date': row['reportedDate'],
            'direction': direction,
            'actual_return': row['fwd_ret'] * direction,
            'raw_return': row['fwd_ret'],
        })
    return trades

# ─── Main ────────────────────────────────────────────────────────────────────

print("Loading data...")
all_rows = []
for ticker in TICKERS:
    earnings = load_earnings(ticker)
    prices = load_prices(ticker)
    if not earnings or prices is None:
        print(f"  {ticker}: missing data, skipping")
        continue
    rows = build_features(earnings, prices)
    all_rows.extend(rows)
    print(f"  {ticker}: {len(rows)} observations")

print(f"\nTotal observations: {len(all_rows)}")

df_all = pd.DataFrame(all_rows)
df_all = df_all.sort_values('reportedDate').reset_index(drop=True)
print(f"Date range: {df_all['reportedDate'].min().date()} to {df_all['reportedDate'].max().date()}")

print("\nRunning walk-forward elastic net (by calendar quarter)...")
preds_df = walk_forward_quarter(df_all)
print(f"Predictions generated: {len(preds_df)}")

pred_std = float(preds_df['predicted_return'].std())
pred_mean = float(preds_df['predicted_return'].mean())
print(f"Predicted return stats: mean={pred_mean:.4f}, std={pred_std:.4f}")
print(f"  > 0: {(preds_df['predicted_return']>0).sum()}, < 0: {(preds_df['predicted_return']<0).sum()}")
print(f"  > 0.01: {(preds_df['predicted_return']>0.01).sum()}, < -0.01: {(preds_df['predicted_return']<-0.01).sum()}")
print(f"  > 0.02: {(preds_df['predicted_return']>0.02).sum()}, < -0.02: {(preds_df['predicted_return']<-0.02).sum()}")

# ─── Strategy Variations ─────────────────────────────────────────────────────

print("\nRunning strategy variations...")

results = []

t1 = simulate_strategy(preds_df, threshold=0.0, long_short=False)
results.append(compute_metrics(t1, "ElasticNet Long-Only (t=0)"))

t2 = simulate_strategy(preds_df, threshold=0.0, long_short=True)
results.append(compute_metrics(t2, "ElasticNet Long-Short (t=0)"))

t3 = simulate_strategy(preds_df, threshold=0.01, long_short=True)
results.append(compute_metrics(t3, "ElasticNet Long-Short (t=1%)"))

t4 = simulate_strategy(preds_df, threshold=0.02, long_short=True)
results.append(compute_metrics(t4, "ElasticNet Long-Short (t=2%)"))

# Baselines
bh_trades = [{'date': r['reportedDate'], 'actual_return': r['fwd_ret'],
               'direction': 1, 'ticker': r['ticker']} for r in all_rows]
results.append(compute_metrics(bh_trades, "Buy-and-Hold (all obs)"))
b2 = sue_baseline(all_rows, long_thresh=3.0, long_short=False)
results.append(compute_metrics(b2, "Single-Q SUE Long-Only (sue>3%)"))
b3 = sue_baseline(all_rows, long_thresh=3.0, short_thresh=-3.0, long_short=True)
results.append(compute_metrics(b3, "Single-Q SUE Long-Short (sue>3%/<-3%)"))

# Leg analysis
long_leg_0 = [t for t in t2 if t['direction'] == 1]
short_leg_0 = [t for t in t2 if t['direction'] == -1]
results.append(compute_metrics(long_leg_0, "EN t=0: LONG LEG only"))
results.append(compute_metrics(short_leg_0, "EN t=0: SHORT LEG only"))

long_leg_1 = [t for t in t3 if t['direction'] == 1]
short_leg_1 = [t for t in t3 if t['direction'] == -1]
results.append(compute_metrics(long_leg_1, "EN t=1%: LONG LEG only"))
results.append(compute_metrics(short_leg_1, "EN t=1%: SHORT LEG only"))

# Print
print("\n" + "="*80)
for r in results:
    print(f"\n{r['label']}")
    print(f"  Sharpe={r['sharpe']}  WinRate={r['win_rate']}  CAGR={r['cagr']}  MaxDD={r['max_dd']}")
    print(f"  NLong={r['n_long']}  NShort={r['n_short']}  NTotal={r['n_trades']}  MeanRet={r['mean_ret']}  IR={r['info_ratio']}")

# ─── Save ─────────────────────────────────────────────────────────────────────

rounds_dir = Path('/workspace/group/trading_eval/rounds')
rounds_dir.mkdir(exist_ok=True)

with open(rounds_dir / 'r30b_results.json', 'w') as f:
    json.dump({'results': results, 'n_obs': len(all_rows), 'n_preds': len(preds_df),
               'pred_mean': pred_mean, 'pred_std': pred_std}, f, indent=2, default=str)
print("\nSaved JSON.")

# ─── Report ───────────────────────────────────────────────────────────────────

def fmt_pct(v):
    return f"{v*100:.1f}%" if v == v else "N/A"  # nan check

def fmt_f(v, d=3):
    return f"{v:.{d}f}" if v == v else "N/A"

lo0 = next(r for r in results if r['label'] == "ElasticNet Long-Only (t=0)")
ls0 = next(r for r in results if r['label'] == "ElasticNet Long-Short (t=0)")
ls1 = next(r for r in results if r['label'] == "ElasticNet Long-Short (t=1%)")
ls2 = next(r for r in results if r['label'] == "ElasticNet Long-Short (t=2%)")
long_leg = next(r for r in results if r['label'] == "EN t=0: LONG LEG only")
short_leg = next(r for r in results if r['label'] == "EN t=0: SHORT LEG only")

valid_sharpes = [r['sharpe'] for r in results[:4] if r['sharpe'] == r['sharpe']]
best_sharpe = max(valid_sharpes) if valid_sharpes else float('nan')
best_model = next(r for r in results[:4] if r['sharpe'] == best_sharpe)

sharpe_diff = ls0['sharpe'] - lo0['sharpe']
short_adds = short_leg['sharpe'] == short_leg['sharpe'] and short_leg['sharpe'] > 0

report = f"""# R30b: Multi-Quarter SUE Elastic Net — Long-Short
**Date:** 2026-04-03
**Hypothesis:** Short side of elastic net signal explains Kaczmarek & Zaremba 2x improvement

---

## Setup
- Tickers: {len(TICKERS)} large-cap US stocks
- Total quarterly observations: {len(all_rows)}
- Walk-forward predictions: {len(preds_df)} (by calendar quarter, min 30 training obs)
- Prediction distribution: mean={pred_mean:.4f}, std={pred_std:.4f}
- Longs (pred>0): {(preds_df['predicted_return']>0).sum()}, Shorts (pred<0): {(preds_df['predicted_return']<0).sum()}

---

## Results Table

| Model | Sharpe | Win Rate | N Long | N Short | CAGR | MaxDD | Info Ratio |
|-------|--------|----------|--------|---------|------|-------|------------|
| {lo0['label']} | {fmt_f(lo0['sharpe'])} | {fmt_pct(lo0['win_rate'])} | {lo0['n_long']} | {lo0['n_short']} | {fmt_pct(lo0['cagr'])} | {fmt_pct(lo0['max_dd'])} | {fmt_f(lo0['info_ratio'])} |
| {ls0['label']} | {fmt_f(ls0['sharpe'])} | {fmt_pct(ls0['win_rate'])} | {ls0['n_long']} | {ls0['n_short']} | {fmt_pct(ls0['cagr'])} | {fmt_pct(ls0['max_dd'])} | {fmt_f(ls0['info_ratio'])} |
| {ls1['label']} | {fmt_f(ls1['sharpe'])} | {fmt_pct(ls1['win_rate'])} | {ls1['n_long']} | {ls1['n_short']} | {fmt_pct(ls1['cagr'])} | {fmt_pct(ls1['max_dd'])} | {fmt_f(ls1['info_ratio'])} |
| {ls2['label']} | {fmt_f(ls2['sharpe'])} | {fmt_pct(ls2['win_rate'])} | {ls2['n_long']} | {ls2['n_short']} | {fmt_pct(ls2['cagr'])} | {fmt_pct(ls2['max_dd'])} | {fmt_f(ls2['info_ratio'])} |

### Baselines

| Model | Sharpe | Win Rate | N Long | N Short | CAGR | MaxDD |
|-------|--------|----------|--------|---------|------|-------|
"""
for r in results[4:7]:
    report += f"| {r['label']} | {fmt_f(r['sharpe'])} | {fmt_pct(r['win_rate'])} | {r['n_long']} | {r['n_short']} | {fmt_pct(r['cagr'])} | {fmt_pct(r['max_dd'])} |\n"

report += f"""
---

## Does the Short Side Add Alpha?

### Leg-Separated Analysis

| Leg | Sharpe | Win Rate | N Trades | CAGR | MaxDD | Mean Ret/Trade |
|-----|--------|----------|----------|------|-------|----------------|
"""
for r in results[7:11]:
    report += f"| {r['label']} | {fmt_f(r['sharpe'])} | {fmt_pct(r['win_rate'])} | {r['n_trades']} | {fmt_pct(r['cagr'])} | {fmt_pct(r['max_dd'])} | {fmt_pct(r['mean_ret'])} |\n"

report += f"""
**Long-Only Sharpe (R30 baseline):** {fmt_f(lo0['sharpe'])}
**Long-Short Sharpe (t=0):** {fmt_f(ls0['sharpe'])}
**Delta:** {'+' if sharpe_diff > 0 else ''}{sharpe_diff:.3f} ({'+' if sharpe_diff > 0 else ''}{sharpe_diff/abs(lo0['sharpe'])*100:.1f}% relative)

**Short leg isolated Sharpe:** {fmt_f(short_leg['sharpe'])}
**Short leg win rate:** {fmt_pct(short_leg['win_rate'])}
**Short leg mean return per trade:** {fmt_pct(short_leg['mean_ret'])}

**Verdict:** {"YES — the short side adds meaningful alpha." if short_adds else "NO — the short side does not add meaningful alpha."}

---

## Comparison to Paper

| | R30 (Long-Only) | R30b Best ({best_model['label']}) | Paper (K&Z 2025) |
|-|-----------------|----------------------------------|------------------|
| Sharpe | {fmt_f(lo0['sharpe'])} | {fmt_f(best_sharpe)} | ~1.0+ |
| Strategy | Long-only EN PEAD | Long-short EN PEAD | Multi-factor PEAD |
| Universe | 22 large-caps | 22 large-caps | ~500 stocks |

### Gap Analysis

- Long-only (R30): {fmt_f(lo0['sharpe'])}
- Best long-short: {fmt_f(best_sharpe)} ({'+' if best_sharpe > lo0['sharpe'] else ''}{best_sharpe - lo0['sharpe']:.3f} delta)
- The short side {"partially bridges" if best_sharpe > lo0['sharpe'] + 0.05 else "does not meaningfully bridge"} the gap with K&Z 2025.

### Remaining Gap Explanations
1. **Universe size** (most likely): 22 large-caps vs 500+ stocks. Large-caps are efficiently priced — less PEAD alpha
2. **Sector dispersion**: With 500 stocks across all caps, short leg picks weak micro/small-cap post-EPS drifters
3. **Feature richness**: Paper may include analyst revision features, volume, or sector-normalized SUE
4. **Holding period optimization**: Paper may use dynamic exits rather than fixed 20-day windows

---

## Recommendation

"""

if best_sharpe > lo0['sharpe'] + 0.10:
    report += f"""**Proceed with long-short framework.** Adding shorts improves Sharpe from {fmt_f(lo0['sharpe'])} to {fmt_f(best_sharpe)}.

Priority next step: **R31 — Expand to 100+ stock universe.** The main bottleneck is universe size. PEAD is a cross-sectional effect; with 22 names we can't diversify adequately. A 100–200 stock universe spanning mid and small-caps should dramatically improve the Sharpe.

Secondary: Test sector-neutralization of short leg to reduce systematic beta in shorts.
"""
else:
    report += f"""**The short side is a marginal improvement only.** Sharpe moves {'+' if sharpe_diff > 0 else ''}{sharpe_diff:.3f} ({'+' if sharpe_diff > 0 else ''}{sharpe_diff/abs(lo0['sharpe'])*100 if lo0['sharpe'] != 0 else 0:.1f}% relative) from adding shorts.

**Root cause:** 22 large-cap stocks is too small and too efficient a universe for PEAD. The elastic net doesn't have enough cross-sectional variation to identify reliable short candidates.

**Priority R31:** Expand to 100–200 stocks spanning mid-caps. PEAD alpha is strongest in smaller, less-covered stocks. This is likely the single biggest lever for matching K&Z 2025.
"""

report += "\n---\n*Generated by Andy (R30b), 2026-04-03*\n"

report_path = Path('/workspace/group/trading_eval/R30B_SUE_LONGSHORT_REPORT.md')
report_path.write_text(report)
print(f"\nReport saved to {report_path}")
print("DONE")
