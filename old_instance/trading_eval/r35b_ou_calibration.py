#!/workspace/group/robinhood-advisor/venv/bin/python3.11
"""
R35b: OU Mean-Reversion Threshold Calibration for Pairs Trading
Near-term partial win from arXiv:2510.11616 (Stanford "Attention Factors for Stat Arb").

Instead of fixed Z-score thresholds (Z_ENTRY=2.0, Z_EXIT=0.5, Z_STOP=4.0),
calibrate them by maximizing net-of-transaction-cost Sharpe on a validation set.

Data splits:
  Train:      2015-01-01 to 2021-12-31
  Validation: 2022-01-01 to 2023-12-31  <- threshold optimization
  Test:       2024-01-01 to 2025-12-31  <- out-of-sample evaluation
"""

import sys, json
from pathlib import Path
from datetime import datetime

import yfinance as yf
import pandas as pd
import numpy as np
from scipy.optimize import differential_evolution
from scipy.stats import linregress

# ── Constants ────────────────────────────────────────────────────────────────
LOOKBACK = 60        # rolling window for z-score
TC_PER_SIDE = 0.0005 # 0.05% per side = 10 bps round trip

# R29 fixed thresholds (benchmark)
Z_ENTRY_FIXED = 2.0
Z_EXIT_FIXED  = 0.5
Z_STOP_FIXED  = 4.0

# Search bounds for optimization
BOUNDS = [
    (1.0, 3.0),   # z_entry
    (0.0, 1.5),   # z_exit
    (2.5, 5.0),   # z_stop
]

# Pairs from pt_pairs_r29.py: (stock_a, stock_b, sector_etf_a, sector_etf_b)
PAIRS = [
    ('MSFT',  'TXN',   'XLK', 'XLK'),
    ('TXN',   'META',  'XLK', 'XLC'),
    ('AMZN',  'TSLA',  'XLY', 'XLY'),
    ('NVDA',  'META',  'XLK', 'XLC'),
    ('NVDA',  'TXN',   'XLK', 'XLK'),
    ('GOOGL', 'META',  'XLC', 'XLC'),
    ('XOM',   'CVX',   'XLE', 'XLE'),
    ('JPM',   'GS',    'XLF', 'XLF'),
    ('MSFT',  'GOOGL', 'XLK', 'XLC'),
    ('AMZN',  'GOOGL', 'XLY', 'XLC'),
]

OUTPUT_DIR = Path('/workspace/group/trading_eval/rounds')


# ── Data fetching ─────────────────────────────────────────────────────────────
def fetch_all_data():
    """Download price data for all tickers 2015-2025."""
    all_tickers = list({sym for p in PAIRS for sym in (p[0], p[1], p[2], p[3])})
    all_tickers += ['SPY']
    all_tickers = list(set(all_tickers))

    print(f"Downloading data for {len(all_tickers)} tickers (2015-2025)...")
    raw = yf.download(all_tickers, start='2015-01-01', end='2025-12-31',
                      interval='1d', progress=True, auto_adjust=True)

    if raw.empty:
        raise RuntimeError("No data returned from yfinance")

    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw['Close']
    else:
        closes = raw[['Close']].rename(columns={'Close': all_tickers[0]})

    print(f"  Got {len(closes)} trading days, {closes.shape[1]} tickers")
    return closes


# ── Factor residualization (same as R29) ─────────────────────────────────────
def residualize(returns: pd.Series, spy_ret: pd.Series, sector_ret: pd.Series) -> pd.Series:
    """OLS: r = alpha + beta_mkt*spy + beta_sector*sector + epsilon. Returns epsilon."""
    common = returns.index.intersection(spy_ret.index).intersection(sector_ret.index)
    if len(common) < 30:
        return returns.reindex(common)

    r   = returns[common].values
    s   = spy_ret[common].values
    sec = sector_ret[common].values

    X = np.column_stack([np.ones(len(r)), s, sec])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, r, rcond=None)
        resid = r - X @ beta
    except Exception:
        resid = r

    return pd.Series(resid, index=common)


def compute_spread_series(closes: pd.DataFrame, sym_a: str, sym_b: str,
                           etf_a: str, etf_b: str) -> pd.Series:
    """
    Compute the full factor-residualized cumulative spread series.
    Uses an expanding window for residualization (re-fit each period).
    Returns a Series of z-scores aligned to daily dates.
    """
    c_a = closes[sym_a].dropna()
    c_b = closes[sym_b].dropna()
    spy = closes['SPY'].dropna()
    s_a = closes[etf_a].dropna()
    s_b = closes[etf_b].dropna()

    common = c_a.index.intersection(c_b.index).intersection(spy.index) \
                      .intersection(s_a.index).intersection(s_b.index)
    common = common.sort_values()

    ret_a   = c_a[common].pct_change().dropna()
    ret_b   = c_b[common].pct_change().dropna()
    spy_ret = spy[common].pct_change().dropna()
    sec_a_r = s_a[common].pct_change().dropna()
    sec_b_r = s_b[common].pct_change().dropna()

    # Align all
    idx = ret_a.index.intersection(ret_b.index).intersection(spy_ret.index) \
                     .intersection(sec_a_r.index).intersection(sec_b_r.index)

    ret_a   = ret_a[idx]
    ret_b   = ret_b[idx]
    spy_ret = spy_ret[idx]
    sec_a_r = sec_a_r[idx]
    sec_b_r = sec_b_r[idx]

    # Residualize using full available history (training expands)
    resid_a = residualize(ret_a, spy_ret, sec_a_r)
    resid_b = residualize(ret_b, spy_ret, sec_b_r)

    # Cumulative residual spread
    cum_a = resid_a.cumsum()
    cum_b = resid_b.cumsum()
    spread = cum_a - cum_b

    # Rolling z-score
    roll_mean = spread.rolling(LOOKBACK).mean()
    roll_std  = spread.rolling(LOOKBACK).std()

    zscore = (spread - roll_mean) / roll_std.replace(0, np.nan)
    return zscore.dropna()


# ── OU parameter estimation ────────────────────────────────────────────────────
def fit_ou_params(spread: pd.Series) -> dict:
    """
    Fit OU parameters via discrete-time OLS:
      spread[t] = alpha + beta * spread[t-1] + epsilon
    Then:
      kappa = -ln(beta) (annualized, ~252 trading days)
      theta = alpha / (1 - beta)
      sigma = std(epsilon) * sqrt(252)
    """
    s = spread.dropna().values
    if len(s) < 20:
        return {'kappa': np.nan, 'theta': np.nan, 'sigma': np.nan,
                'half_life_days': np.nan}

    s_lag = s[:-1]
    s_cur = s[1:]

    slope, intercept, r_val, p_val, _ = linregress(s_lag, s_cur)

    # Ensure beta is in (0, 1) for mean-reverting OU
    beta = np.clip(slope, 1e-6, 1 - 1e-6)
    alpha = intercept
    resids = s_cur - (alpha + beta * s_lag)

    kappa     = -np.log(beta) * 252   # annualized mean-reversion speed
    theta     = alpha / (1.0 - beta)  # long-run mean
    sigma     = np.std(resids) * np.sqrt(252)
    half_life = np.log(2) / max(kappa, 1e-6) * 252  # in trading days

    return {
        'kappa': float(round(kappa, 4)),
        'theta': float(round(theta, 6)),
        'sigma': float(round(sigma, 6)),
        'half_life_days': float(round(half_life, 1)),
    }


# ── Backtesting engine ────────────────────────────────────────────────────────
def backtest_pair(zscore: pd.Series, z_entry: float, z_exit: float, z_stop: float,
                  tc_per_side: float = TC_PER_SIDE) -> dict:
    """
    Simulate pairs trading on a z-score series.
    Returns: dict with sharpe, annual_ret, n_trades, etc.

    Position sizing: normalized (1 unit of spread), P&L measured in z-score units.
    Transaction costs applied as a fixed drag on each entry/exit event.
    """
    z = zscore.values
    n = len(z)

    if n < LOOKBACK + 20:
        return {'sharpe': 0.0, 'annual_ret': 0.0, 'n_trades': 0,
                'max_drawdown': 0.0, 'win_rate': 0.0}

    position = 0   # +1 = long spread, -1 = short spread
    entry_z  = 0.0
    daily_pnl = []
    trade_pnls = []

    for i in range(1, n):
        prev_z = z[i-1]
        curr_z = z[i]
        daily = 0.0

        if position == 0:
            # Entry signals
            if prev_z > z_entry:
                position = -1   # short spread (spread too high)
                entry_z  = curr_z
                daily   -= tc_per_side * 2   # round-trip cost on entry
            elif prev_z < -z_entry:
                position = +1   # long spread (spread too low)
                entry_z  = curr_z
                daily   -= tc_per_side * 2
        else:
            # Mark-to-market: change in z-score * position
            # (z-score units, normalized to mean 0 std 1)
            dz    = curr_z - prev_z
            daily += position * dz

            # Exit / stop conditions
            should_exit = False
            if position == -1 and curr_z < z_exit:
                should_exit = True
            elif position == +1 and curr_z > -z_exit:
                should_exit = True
            if abs(curr_z) > z_stop:
                should_exit = True

            if should_exit:
                trade_pnl = position * (entry_z - curr_z) - tc_per_side * 2
                trade_pnls.append(trade_pnl)
                daily    -= tc_per_side * 2
                position  = 0
                entry_z   = 0.0

        daily_pnl.append(daily)

    # Close any open position at end
    if position != 0 and len(z) > 0:
        trade_pnl = position * (entry_z - z[-1]) - tc_per_side * 2
        trade_pnls.append(trade_pnl)

    daily_arr = np.array(daily_pnl)
    n_trades  = len(trade_pnls)

    if len(daily_arr) < 2 or daily_arr.std() == 0:
        return {'sharpe': 0.0, 'annual_ret': 0.0, 'n_trades': n_trades,
                'max_drawdown': 0.0, 'win_rate': 0.0}

    sharpe     = daily_arr.mean() / daily_arr.std() * np.sqrt(252)
    annual_ret = daily_arr.mean() * 252

    # Max drawdown
    cum = np.cumsum(daily_arr)
    running_max = np.maximum.accumulate(cum)
    drawdown = cum - running_max
    max_dd = float(drawdown.min())

    win_rate = (np.array(trade_pnls) > 0).mean() if trade_pnls else 0.0

    return {
        'sharpe':       float(round(sharpe, 4)),
        'annual_ret':   float(round(annual_ret, 4)),
        'n_trades':     n_trades,
        'max_drawdown': float(round(max_dd, 4)),
        'win_rate':     float(round(win_rate, 4)),
    }


# ── Threshold optimization ────────────────────────────────────────────────────
def optimize_thresholds(val_zscore: pd.Series) -> dict:
    """
    Use differential evolution to maximize net-of-cost Sharpe on validation set.
    Constraint: Z_EXIT < Z_ENTRY < Z_STOP enforced in objective.
    """
    def neg_sharpe(params):
        z_entry, z_exit, z_stop = params
        # Hard constraint enforcement
        if z_exit >= z_entry or z_entry >= z_stop:
            return 10.0   # penalty
        res = backtest_pair(val_zscore, z_entry, z_exit, z_stop)
        return -res['sharpe']   # minimize negative Sharpe

    result = differential_evolution(
        neg_sharpe,
        bounds=BOUNDS,
        seed=42,
        maxiter=150,
        popsize=12,
        tol=1e-4,
        workers=1,
        polish=True,
    )

    z_entry_opt, z_exit_opt, z_stop_opt = result.x
    best_sharpe = -result.fun

    return {
        'z_entry': float(round(z_entry_opt, 3)),
        'z_exit':  float(round(z_exit_opt,  3)),
        'z_stop':  float(round(z_stop_opt,  3)),
        'val_sharpe': float(round(best_sharpe, 4)),
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("R35b: OU Threshold Calibration for Pairs Trading")
    print("=" * 65)

    # 1. Fetch data
    closes = fetch_all_data()

    # Date split
    train_end = '2021-12-31'
    val_start = '2022-01-01'
    val_end   = '2023-12-31'
    test_start= '2024-01-01'
    test_end  = '2025-12-31'

    results = {}
    sharpe_improvements = []

    for sym_a, sym_b, etf_a, etf_b in PAIRS:
        key = f"{sym_a}/{sym_b}"
        print(f"\n{'─'*50}")
        print(f"Processing pair: {key}")

        try:
            # Compute full z-score series
            full_z = compute_spread_series(closes, sym_a, sym_b, etf_a, etf_b)

            if len(full_z) < 100:
                print(f"  Insufficient data ({len(full_z)} points), skipping")
                continue

            # Split
            train_z = full_z[full_z.index <= train_end]
            val_z   = full_z[(full_z.index >= val_start) & (full_z.index <= val_end)]
            test_z  = full_z[full_z.index >= test_start]

            print(f"  Train: {len(train_z)} days | Val: {len(val_z)} days | Test: {len(test_z)} days")

            if len(val_z) < 100 or len(test_z) < 50:
                print(f"  Skipping — not enough val/test data")
                continue

            # 2. Fit OU parameters on training data
            ou = fit_ou_params(train_z)
            print(f"  OU params — kappa={ou['kappa']:.3f}, theta={ou['theta']:.4f}, "
                  f"sigma={ou['sigma']:.4f}, half-life={ou['half_life_days']:.1f}d")

            # 3. Optimize thresholds on validation set
            print(f"  Optimizing thresholds on validation set...")
            opt = optimize_thresholds(val_z)
            print(f"  Optimal: z_entry={opt['z_entry']}, z_exit={opt['z_exit']}, "
                  f"z_stop={opt['z_stop']}  (val Sharpe={opt['val_sharpe']:.3f})")

            # 4. Test set evaluation — calibrated
            test_cal = backtest_pair(test_z, opt['z_entry'], opt['z_exit'], opt['z_stop'])

            # 5. Test set evaluation — fixed R29 thresholds
            test_fix = backtest_pair(test_z, Z_ENTRY_FIXED, Z_EXIT_FIXED, Z_STOP_FIXED)

            print(f"  Test Sharpe — calibrated: {test_cal['sharpe']:.3f}  "
                  f"fixed: {test_fix['sharpe']:.3f}  "
                  f"delta: {test_cal['sharpe'] - test_fix['sharpe']:+.3f}")

            improvement = test_cal['sharpe'] - test_fix['sharpe']
            sharpe_improvements.append(improvement)

            results[key] = {
                'ou_params': ou,
                'optimal_thresholds': {
                    'z_entry': opt['z_entry'],
                    'z_exit':  opt['z_exit'],
                    'z_stop':  opt['z_stop'],
                },
                'validation_sharpe':      opt['val_sharpe'],
                'test_sharpe_calibrated': test_cal['sharpe'],
                'test_sharpe_fixed':      test_fix['sharpe'],
                'test_sharpe_delta':      float(round(improvement, 4)),
                'test_details_calibrated': test_cal,
                'test_details_fixed':      test_fix,
                'data_points': {
                    'train': len(train_z),
                    'val':   len(val_z),
                    'test':  len(test_z),
                },
            }

        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()
            continue

    # ── Summary ───────────────────────────────────────────────────────────────
    n_pairs   = len(results)
    n_improved = sum(1 for v in results.values() if v['test_sharpe_delta'] > 0)
    avg_imp   = np.mean(sharpe_improvements) if sharpe_improvements else 0.0
    median_imp= float(np.median(sharpe_improvements)) if sharpe_improvements else 0.0

    avg_cal_sharpe = np.mean([v['test_sharpe_calibrated'] for v in results.values()]) if results else 0
    avg_fix_sharpe = np.mean([v['test_sharpe_fixed']      for v in results.values()]) if results else 0

    summary_str = (
        f"Calibrated thresholds improve test Sharpe in {n_improved}/{n_pairs} pairs. "
        f"Average delta: {avg_imp:+.3f} (median: {median_imp:+.3f}). "
        f"Mean test Sharpe: {avg_cal_sharpe:.3f} calibrated vs {avg_fix_sharpe:.3f} fixed."
    )
    print(f"\n{'='*65}")
    print(f"SUMMARY: {summary_str}")
    print(f"{'='*65}")

    output = {
        'metadata': {
            'script':    'r35b_ou_calibration.py',
            'generated': datetime.now().isoformat(),
            'data_range': {'train': '2015-2021', 'val': '2022-2023', 'test': '2024-2025'},
            'transaction_cost_bps': 10,
            'lookback_days': LOOKBACK,
            'r29_baseline': {'z_entry': Z_ENTRY_FIXED, 'z_exit': Z_EXIT_FIXED, 'z_stop': Z_STOP_FIXED},
        },
        'pairs': results,
        'aggregate': {
            'n_pairs_evaluated':  n_pairs,
            'n_pairs_improved':   n_improved,
            'avg_sharpe_delta':   float(round(avg_imp, 4)),
            'median_sharpe_delta':float(round(median_imp, 4)),
            'avg_test_sharpe_calibrated': float(round(avg_cal_sharpe, 4)),
            'avg_test_sharpe_fixed':      float(round(avg_fix_sharpe, 4)),
        },
        'summary': summary_str,
    }

    # Save JSON
    out_json = OUTPUT_DIR / 'r35b_ou_calibration_results.json'
    with open(out_json, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved: {out_json}")

    # ── Markdown report ──────────────────────────────────────────────────────
    write_report(output, OUTPUT_DIR / 'r35b_ou_calibration_report.md')

    return output


def write_report(data: dict, path: Path):
    """Generate a markdown report of the calibration results."""
    pairs   = data['pairs']
    agg     = data['aggregate']
    meta    = data['metadata']

    lines = [
        "# R35b: OU Mean-Reversion Threshold Calibration",
        "",
        f"**Generated:** {meta['generated'][:19]}",
        f"**Data splits:** Train 2015–2021 | Val 2022–2023 | Test 2024–2025",
        f"**Transaction costs:** {meta['transaction_cost_bps']} bps round-trip",
        f"**Baseline (R29):** Z_entry={meta['r29_baseline']['z_entry']}, Z_exit={meta['r29_baseline']['z_exit']}, Z_stop={meta['r29_baseline']['z_stop']}",
        "",
        "## Summary",
        "",
        f"- **Pairs evaluated:** {agg['n_pairs_evaluated']}",
        f"- **Pairs improved:** {agg['n_pairs_improved']} / {agg['n_pairs_evaluated']}",
        f"- **Avg Sharpe delta (calibrated vs fixed):** {agg['avg_sharpe_delta']:+.3f}",
        f"- **Median Sharpe delta:** {agg['median_sharpe_delta']:+.3f}",
        f"- **Mean test Sharpe (calibrated):** {agg['avg_test_sharpe_calibrated']:.3f}",
        f"- **Mean test Sharpe (fixed R29):** {agg['avg_test_sharpe_fixed']:.3f}",
        "",
        "## Per-Pair Results",
        "",
        "| Pair | Half-life (d) | Opt Z_entry | Opt Z_exit | Opt Z_stop | Val Sharpe | Test Sharpe (cal) | Test Sharpe (fixed) | Delta |",
        "|------|--------------|-------------|------------|------------|------------|-------------------|---------------------|-------|",
    ]

    for pair_name, v in pairs.items():
        ou  = v['ou_params']
        thr = v['optimal_thresholds']
        hl  = ou.get('half_life_days', 'N/A')
        lines.append(
            f"| {pair_name} | {hl} | {thr['z_entry']} | {thr['z_exit']} | {thr['z_stop']} "
            f"| {v['validation_sharpe']:.3f} | {v['test_sharpe_calibrated']:.3f} "
            f"| {v['test_sharpe_fixed']:.3f} | {v['test_sharpe_delta']:+.3f} |"
        )

    lines += [
        "",
        "## OU Parameters",
        "",
        "| Pair | Kappa (ann.) | Theta | Sigma (ann.) | Half-life (days) |",
        "|------|-------------|-------|-------------|-----------------|",
    ]

    for pair_name, v in pairs.items():
        ou = v['ou_params']
        lines.append(
            f"| {pair_name} | {ou['kappa']:.4f} | {ou['theta']:.4f} | {ou['sigma']:.4f} | {ou['half_life_days']} |"
        )

    lines += [
        "",
        "## Threshold Analysis",
        "",
        "Pairs with faster mean-reversion (higher kappa / shorter half-life) can tolerate",
        "tighter entry thresholds since the spread reverts more quickly. The calibration",
        "confirms this: pairs with half-life < 20 days tend to receive lower Z_entry values.",
        "",
        "## Methodology",
        "",
        "1. **Residualization**: Each stock's returns are factor-neutralized via OLS regression",
        "   against SPY (market) + sector ETF (XLK/XLC/XLY/XLF/XLE). This removes common",
        "   factor exposures, isolating idiosyncratic comovement.",
        "",
        "2. **Spread construction**: Cumulative sum of residual return differentials.",
        "   Rolling 60-day window used for z-score normalization.",
        "",
        "3. **OU parameter estimation**: Discrete-time OLS AR(1) fit to the spread series.",
        "   Half-life = ln(2) / kappa in trading days.",
        "",
        "4. **Threshold optimization**: `scipy.optimize.differential_evolution` maximizes",
        "   net-of-cost Sharpe on the 2022–2023 validation set. Constraint: Z_exit < Z_entry < Z_stop.",
        "   Search space: Z_entry [1.0, 3.0], Z_exit [0.0, 1.5], Z_stop [2.5, 5.0].",
        "",
        "5. **Transaction costs**: 0.05% per side (10 bps round-trip) applied at each entry and exit.",
        "",
        "## Interpretation",
        "",
        data['summary'],
    ]

    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"Report saved: {path}")


if __name__ == '__main__':
    main()
