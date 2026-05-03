"""
R30b: Multi-Quarter SUE Elastic Net PEAD — Long-Short Version
Tests whether the SHORT side of the elastic net signal adds alpha.
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
    """Get n-day return starting from start_date (finds next trading day)."""
    future = prices[prices.index >= start_date]
    if len(future) < n_days + 1:
        return np.nan
    return (future.iloc[n_days] / future.iloc[0]) - 1

# ─── Feature Engineering ────────────────────────────────────────────────────

def build_features(earnings_records, prices):
    """Build feature matrix for a single ticker."""
    rows = []
    for i in range(len(earnings_records)):
        rec = earnings_records[i]
        # Need at least 12 prior quarters for features
        if i < 12:
            continue
        history = [earnings_records[j]['sue'] for j in range(max(0, i-12), i)]
        if len(history) < 8:
            continue
        # Pad to 12 if needed
        while len(history) < 12:
            history = [0.0] + history
        sue_q1_12 = history[-12:]
        mean_sue_4q = np.mean(history[-4:])
        std_sue_4q = np.std(history[-4:]) if len(history) >= 4 else 0.0
        # Trend: slope of last 4
        y = history[-4:]
        x = np.arange(len(y))
        if std_sue_4q > 0:
            trend_sue = np.polyfit(x, y, 1)[0]
        else:
            trend_sue = 0.0
        # Forward return
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

# ─── Walk-Forward Backtest ───────────────────────────────────────────────────

FEATURE_COLS = [f'sue_q{i}' for i in range(1,13)] + ['mean_sue_4q','std_sue_4q','trend_sue']

def walk_forward_predictions(df_all):
    """Walk-forward elastic net: train on all prior obs, predict next."""
    df_all = df_all.sort_values('reportedDate').reset_index(drop=True)
    predictions = []

    for idx in range(len(df_all)):
        train = df_all.iloc[:idx]
        if len(train) < 8:
            continue
        X_train = train[FEATURE_COLS].values
        y_train = train['fwd_ret'].values
        # Fit model
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_train)
        try:
            model = ElasticNetCV(
                l1_ratio=[0.1, 0.5, 0.7, 0.9, 0.95, 1.0],
                cv=5,
                max_iter=2000,
                random_state=42
            )
            model.fit(X_scaled, y_train)
            X_pred = scaler.transform(df_all.iloc[idx:idx+1][FEATURE_COLS].values)
            pred = model.predict(X_pred)[0]
        except Exception:
            continue
        row = df_all.iloc[idx].copy()
        row['predicted_return'] = pred
        predictions.append(row)

    return pd.DataFrame(predictions)

# ─── Strategy Simulation ─────────────────────────────────────────────────────

def simulate_strategy(preds_df, threshold=0.0, long_short=True):
    """
    threshold: minimum |predicted_return| to take a position
    long_short: if True, short when pred < -threshold; if False, long-only
    Returns list of trade dicts.
    """
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
    n_long = (df['direction'] == 1).sum()
    n_short = (df['direction'] == -1).sum()
    win_rate = (rets > 0).mean()
    mean_ret = rets.mean()
    std_ret = rets.std()

    # Annualized metrics (assume ~4 signals/quarter per ticker, but use actual dates)
    # Estimate trades per year
    date_range_days = (df['date'].max() - df['date'].min()).days
    if date_range_days < 1:
        trades_per_year = n
    else:
        trades_per_year = n / (date_range_days / 365.25)

    sharpe = (mean_ret / std_ret * np.sqrt(trades_per_year)) if std_ret > 0 else np.nan
    info_ratio = mean_ret / std_ret if std_ret > 0 else np.nan

    # CAGR via compounding
    cum = np.cumprod(1 + rets)
    years = date_range_days / 365.25 if date_range_days > 1 else 1
    cagr = cum[-1] ** (1 / years) - 1

    # Max drawdown
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    max_dd = dd.min()

    return {
        'label': label,
        'sharpe': round(sharpe, 4),
        'win_rate': round(win_rate, 4),
        'n_long': int(n_long),
        'n_short': int(n_short),
        'n_trades': n,
        'cagr': round(cagr, 4),
        'max_dd': round(max_dd, 4),
        'info_ratio': round(info_ratio, 4),
        'mean_ret': round(mean_ret, 4),
    }

# ─── Baseline: Single-Quarter SUE ────────────────────────────────────────────

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

# Convert to DataFrame and run walk-forward
df_all = pd.DataFrame(all_rows)
df_all = df_all.sort_values('reportedDate').reset_index(drop=True)
print(f"Date range: {df_all['reportedDate'].min().date()} to {df_all['reportedDate'].max().date()}")

print("\nRunning walk-forward elastic net predictions...")
preds_df = walk_forward_predictions(df_all)
print(f"Predictions generated: {len(preds_df)}")

# Distribution of predicted returns
pred_std = preds_df['predicted_return'].std()
pred_mean = preds_df['predicted_return'].mean()
print(f"Predicted return stats: mean={pred_mean:.4f}, std={pred_std:.4f}")
print(f"  > 0: {(preds_df['predicted_return']>0).sum()}, < 0: {(preds_df['predicted_return']<0).sum()}")
print(f"  > 0.01: {(preds_df['predicted_return']>0.01).sum()}, < -0.01: {(preds_df['predicted_return']<-0.01).sum()}")
print(f"  > 0.02: {(preds_df['predicted_return']>0.02).sum()}, < -0.02: {(preds_df['predicted_return']<-0.02).sum()}")

# ─── Run 4 Variations ────────────────────────────────────────────────────────

print("\nRunning strategy variations...")

results = []

# Var 1: Long-only, threshold=0.0 (reproduce R30)
t1 = simulate_strategy(preds_df, threshold=0.0, long_short=False)
results.append(compute_metrics(t1, "ElasticNet Long-Only (t=0)"))

# Var 2: Long-short, threshold=0.0
t2 = simulate_strategy(preds_df, threshold=0.0, long_short=True)
results.append(compute_metrics(t2, "ElasticNet Long-Short (t=0)"))

# Var 3: Long-short, threshold=1%
t3 = simulate_strategy(preds_df, threshold=0.01, long_short=True)
results.append(compute_metrics(t3, "ElasticNet Long-Short (t=1%)"))

# Var 4: Long-short, threshold=2%
t4 = simulate_strategy(preds_df, threshold=0.02, long_short=True)
results.append(compute_metrics(t4, "ElasticNet Long-Short (t=2%)"))

# ─── Baselines ───────────────────────────────────────────────────────────────

print("Computing baselines...")

# B1: Buy and hold (use all ticker returns)
bh_trades = [{'date': r['reportedDate'], 'actual_return': r['fwd_ret'],
               'direction': 1, 'ticker': r['ticker']} for r in all_rows]
results.append(compute_metrics(bh_trades, "Buy-and-Hold (all obs)"))

# B2: Single-quarter SUE long-only (sue > 3%)
b2 = sue_baseline(all_rows, long_thresh=3.0, long_short=False)
results.append(compute_metrics(b2, "Single-Q SUE Long-Only (sue>3%)"))

# B3: Single-quarter SUE long-short
b3 = sue_baseline(all_rows, long_thresh=3.0, short_thresh=-3.0, long_short=True)
results.append(compute_metrics(b3, "Single-Q SUE Long-Short (sue>3%/<-3%)"))

# ─── Analyze Short Side Separately ───────────────────────────────────────────

print("\nAnalyzing long vs short legs separately...")

# Long leg only from long-short t=0
long_only_leg = [t for t in t2 if t['direction'] == 1]
short_only_leg = [t for t in t2 if t['direction'] == -1]

results.append(compute_metrics(long_only_leg, "EN Long-Short t=0: LONG LEG only"))
results.append(compute_metrics(short_only_leg, "EN Long-Short t=0: SHORT LEG only"))

# Long leg from t=1%
long_leg_1 = [t for t in t3 if t['direction'] == 1]
short_leg_1 = [t for t in t3 if t['direction'] == -1]
results.append(compute_metrics(long_leg_1, "EN Long-Short t=1%: LONG LEG only"))
results.append(compute_metrics(short_leg_1, "EN Long-Short t=1%: SHORT LEG only"))

# Print all results
print("\n" + "="*80)
print("RESULTS SUMMARY")
print("="*80)
for r in results:
    print(f"\n{r['label']}")
    print(f"  Sharpe: {r['sharpe']}  WinRate: {r['win_rate']}  CAGR: {r['cagr']}  MaxDD: {r['max_dd']}")
    print(f"  N_Long: {r['n_long']}  N_Short: {r['n_short']}  N_Total: {r['n_trades']}  MeanRet: {r['mean_ret']}  InfoRatio: {r['info_ratio']}")

# ─── Save Results ─────────────────────────────────────────────────────────────

rounds_dir = Path('/workspace/group/trading_eval/rounds')
rounds_dir.mkdir(exist_ok=True)

with open(rounds_dir / 'r30b_results.json', 'w') as f:
    json.dump({'results': results, 'n_obs': len(all_rows), 'n_preds': len(preds_df)}, f, indent=2)
print("\nSaved JSON to rounds/r30b_results.json")

# ─── Generate Report ──────────────────────────────────────────────────────────

def fmt_pct(v):
    return f"{v*100:.1f}%" if not np.isnan(v) else "N/A"

def fmt_f(v, d=3):
    return f"{v:.{d}f}" if not np.isnan(v) else "N/A"

report = f"""# R30b: Multi-Quarter SUE Elastic Net — Long-Short
**Date:** 2026-04-03
**Hypothesis:** Short side of elastic net signal explains Kaczmarek & Zaremba 2x improvement

---

## Setup
- Tickers: {len(TICKERS)} large-cap US stocks
- Total quarterly observations: {len(all_rows)}
- Walk-forward predictions generated: {len(preds_df)}
- Prediction distribution: mean={pred_mean:.4f}, std={pred_std:.4f}
- Longs (pred>0): {(preds_df['predicted_return']>0).sum()}, Shorts (pred<0): {(preds_df['predicted_return']<0).sum()}

---

## Results Table

| Model | Sharpe | Win Rate | N Long | N Short | CAGR | MaxDD | Info Ratio |
|-------|--------|----------|--------|---------|------|-------|------------|
"""

# Main strategies
for r in results[:4]:
    report += f"| {r['label']} | {fmt_f(r['sharpe'])} | {fmt_pct(r['win_rate'])} | {r['n_long']} | {r['n_short']} | {fmt_pct(r['cagr'])} | {fmt_pct(r['max_dd'])} | {fmt_f(r['info_ratio'])} |\n"

report += "\n### Baselines\n\n"
report += "| Model | Sharpe | Win Rate | N Long | N Short | CAGR | MaxDD | Info Ratio |\n"
report += "|-------|--------|----------|--------|---------|------|-------|------------|\n"
for r in results[4:7]:
    report += f"| {r['label']} | {fmt_f(r['sharpe'])} | {fmt_pct(r['win_rate'])} | {r['n_long']} | {r['n_short']} | {fmt_pct(r['cagr'])} | {fmt_pct(r['max_dd'])} | {fmt_f(r['info_ratio'])} |\n"

report += "\n---\n\n## Does the Short Side Add Alpha?\n\n"
report += "### Leg-Separated Analysis (Long-Short t=0)\n\n"
report += "| Leg | Sharpe | Win Rate | N Trades | CAGR | MaxDD |\n"
report += "|-----|--------|----------|----------|------|-------|\n"
for r in results[7:11]:
    report += f"| {r['label'].split(': ')[-1]} | {fmt_f(r['sharpe'])} | {fmt_pct(r['win_rate'])} | {r['n_trades']} | {fmt_pct(r['cagr'])} | {fmt_pct(r['max_dd'])} |\n"

# Compute analysis
ls0 = next(r for r in results if r['label'] == "ElasticNet Long-Short (t=0)")
lo0 = next(r for r in results if r['label'] == "ElasticNet Long-Only (t=0)")
long_leg = next(r for r in results if "LONG LEG only" in r['label'] and "t=0" in r['label'])
short_leg = next(r for r in results if "SHORT LEG only" in r['label'] and "t=0" in r['label'])

sharpe_diff = ls0['sharpe'] - lo0['sharpe'] if not (np.isnan(ls0['sharpe']) or np.isnan(lo0['sharpe'])) else np.nan
short_adds = not np.isnan(short_leg['sharpe']) and short_leg['sharpe'] > 0

report += f"""
**Long-Only Sharpe:** {fmt_f(lo0['sharpe'])}
**Long-Short Sharpe:** {fmt_f(ls0['sharpe'])}
**Sharpe improvement from adding shorts:** {fmt_f(sharpe_diff)} ({'+' if sharpe_diff > 0 else ''}{sharpe_diff*100:.1f} basis points of Sharpe)

**Short leg Sharpe (isolated):** {fmt_f(short_leg['sharpe'])}
**Short leg win rate:** {fmt_pct(short_leg['win_rate'])}
**Short leg mean return:** {fmt_pct(short_leg['mean_ret'])} per trade

**Conclusion:** {"The short side DOES add meaningful alpha — shorting elastic-net-predicted losers generates positive risk-adjusted returns." if short_adds else "The short side does NOT add meaningful alpha — shorting elastic-net-predicted losers does not reliably generate positive returns in this sample."}

---

## Comparison to Paper (Kaczmarek & Zaremba 2025)

| Metric | R30 (Long-Only) | R30b Best | Paper (Reported) |
|--------|-----------------|-----------|------------------|
| Sharpe | {fmt_f(lo0['sharpe'])} | {fmt_f(max(r['sharpe'] for r in results[:4] if not np.isnan(r['sharpe'])))} | ~1.0 (estimated) |
| Strategy | Long-only EN | Long-short EN | Multi-factor PEAD |

### Gap Analysis
"""

best_sharpe = max(r['sharpe'] for r in results[:4] if not np.isnan(r['sharpe']))
report += f"""The paper's cited 2x improvement over single-factor baselines was hypothesized to come from the short leg.

- Long-only baseline (R30): Sharpe {fmt_f(lo0['sharpe'])}
- Best long-short variant: Sharpe {fmt_f(best_sharpe)}
- Long-only SUE baseline: Sharpe {fmt_f(next(r for r in results if "Single-Q" in r['label'] and "Long-Only" in r['label'])['sharpe'])}
- Long-short SUE baseline: Sharpe {fmt_f(next(r for r in results if "Single-Q" in r['label'] and "Long-Short" in r['label'])['sharpe'])}

"""

if best_sharpe > lo0['sharpe']:
    report += f"Adding the short leg improves Sharpe from {fmt_f(lo0['sharpe'])} to {fmt_f(best_sharpe)}, a {fmt_f(best_sharpe/lo0['sharpe'] if lo0['sharpe']>0 else float('nan'), 2)}x improvement. "
    if best_sharpe < 0.8:
        report += "This partially explains the gap but still falls short of the paper's results, suggesting other factors (universe size, different features, or transaction cost assumptions) also contribute.\n"
    else:
        report += "This largely explains the performance gap with the paper.\n"
else:
    report += "The short leg does NOT explain the performance gap with the paper — Sharpe does not meaningfully improve.\n"

report += """
## Possible Remaining Gaps vs Paper
1. **Universe size**: Paper likely uses 500+ stocks; we have 22 large-caps (less dispersion = less alpha)
2. **Earnings quality features**: Paper may use more sophisticated SUE normalization
3. **Market cap weighting**: Large-caps like our sample tend to be efficiently priced
4. **Transaction costs**: Paper may report gross returns; realistic costs reduce Sharpe
5. **Rebalancing**: Paper may use continuous rebalancing vs our event-driven approach

---

## Recommendation

"""

if best_sharpe > lo0['sharpe'] + 0.1:
    report += f"""**Use Long-Short variant.** The short leg adds meaningful alpha (Sharpe improves from {fmt_f(lo0['sharpe'])} to {fmt_f(best_sharpe)}).

Next steps:
1. **R31**: Expand universe to 100+ stocks to test if more tickers improve the signal
2. **R32**: Add market-cap and sector neutralization to improve short leg reliability
3. **R33**: Test SUE normalization methods from the paper
"""
else:
    report += f"""**Short side does not rescue the strategy.** Sharpe improvement ({fmt_f(sharpe_diff)}) is minimal.

The primary gap vs the paper is likely:
- Universe size (22 vs 500+ stocks)
- Large-cap efficiency reduces PEAD alpha

Next steps:
1. **R31**: Expand to mid/small-cap universe where PEAD is stronger
2. **R32**: Test if normalization or sector adjustment helps
3. Consider whether this factor is viable for large-cap-only portfolios
"""

report += "\n---\n*Generated by Andy (R30b), 2026-04-03*\n"

report_path = Path('/workspace/group/trading_eval/R30B_SUE_LONGSHORT_REPORT.md')
report_path.write_text(report)
print(f"\nReport saved to {report_path}")
print("\nDONE")
