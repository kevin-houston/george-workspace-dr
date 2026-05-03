"""
analysis_layer.py — NanoClaw Trading Eval Framework v1.0
=========================================================
Reads any .trades.jsonl file (or a directory of them) and computes rich
risk-adjusted metrics, regime-conditional analysis, and cross-strategy
portfolio statistics.

NEVER add new metrics to harnesses — add them here instead.
This file can be re-run at any time without touching harness code.

Usage:
    python analysis_layer.py                    # analyze all trade_logs/
    python analysis_layer.py my_strategy.jsonl  # single file
    python analysis_layer.py --regime-only      # just print regime calendar
"""

import sys
import os
import json
import argparse
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from collections import defaultdict

warnings.filterwarnings('ignore')

# Allow running standalone or as module
_here = Path(__file__).parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from base_harness import (
    fetch_data, get_close, build_regime_calendar, get_trade_regime,
    REGIME_CRISIS, REGIME_BEAR, REGIME_HIGH_VOL, REGIME_BULL,
    REGIME_LOW_VOL, REGIME_UNKNOWN, EVAL_DIR, TRADE_LOG_DIR
)

ANALYSIS_DIR = EVAL_DIR / 'analysis'
ANALYSIS_DIR.mkdir(exist_ok=True)

REGIMES_ORDERED = [REGIME_CRISIS, REGIME_BEAR, REGIME_HIGH_VOL,
                   REGIME_BULL, REGIME_LOW_VOL]

# ─────────────────────────────────────────────
# METRICS ENGINE
# ─────────────────────────────────────────────

def _arr(returns):
    return np.array([float(r) for r in returns], dtype=float)

def sharpe(returns, annualize=12):
    r = _arr(returns)
    if len(r) < 5 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(annualize))

def sortino(returns, annualize=12, mar=0.0):
    """Sortino ratio — penalizes only downside deviation."""
    r = _arr(returns)
    if len(r) < 5:
        return 0.0
    downside = r[r < mar] - mar
    dd_std = np.sqrt(np.mean(downside**2)) if len(downside) > 0 else 1e-9
    if dd_std == 0:
        return 0.0
    return float(((r.mean() - mar) / dd_std) * np.sqrt(annualize))

def equity_curve(returns):
    r = _arr(returns)
    eq = np.ones(len(r) + 1)
    for i, ret in enumerate(r):
        eq[i+1] = eq[i] * (1 + ret)
    return eq

def max_drawdown(returns):
    eq = equity_curve(returns)
    peak = np.maximum.accumulate(eq)
    dd   = (eq - peak) / np.where(peak > 0, peak, 1)
    return float(dd.min())

def calmar(returns, annualize=12):
    """CAGR / |max drawdown|."""
    r = _arr(returns)
    if len(r) < 5:
        return 0.0
    eq  = equity_curve(r)
    n_periods = len(r)
    years = n_periods / annualize
    cagr = (eq[-1] ** (1/years) - 1) if years > 0 and eq[-1] > 0 else 0.0
    mdd  = abs(max_drawdown(r))
    return float(cagr / mdd) if mdd > 1e-6 else 0.0

def skewness(returns):
    r = _arr(returns)
    if len(r) < 5 or r.std() == 0:
        return 0.0
    return float(pd.Series(r).skew())

def kurtosis(returns):
    r = _arr(returns)
    if len(r) < 5:
        return 0.0
    return float(pd.Series(r).kurtosis())   # excess kurtosis (normal = 0)

def win_rate(returns):
    r = _arr(returns)
    if len(r) == 0:
        return 0.0
    return float((r > 0).mean())

def profit_factor(returns):
    r = _arr(returns)
    gains  = r[r > 0].sum()
    losses = abs(r[r < 0].sum())
    return float(gains / losses) if losses > 1e-9 else float('inf')

def max_consec_losses(returns):
    r = _arr(returns)
    max_streak = 0
    streak     = 0
    for ret in r:
        if ret < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    return int(max_streak)

def kelly_fraction(returns):
    """
    Simplified Kelly: f = (p * b - q) / b
    where p = win rate, q = 1-p, b = avg win / avg loss
    Capped at 0.25 (25% of capital) to avoid Kelly overbetting.
    """
    r = _arr(returns)
    wins   = r[r > 0]
    losses = r[r < 0]
    if len(wins) == 0 or len(losses) == 0:
        return 0.0
    p   = len(wins) / len(r)
    q   = 1 - p
    b   = abs(wins.mean() / losses.mean()) if losses.mean() != 0 else 1
    f   = (p * b - q) / b if b > 0 else 0
    return float(min(max(f, 0.0), 0.25))

def spy_correlation(trade_records, spy_monthly):
    """
    Pearson correlation between strategy monthly returns and SPY monthly returns.
    Matches by entry month.
    """
    if spy_monthly is None or len(spy_monthly) == 0:
        return None
    strat_by_month = defaultdict(list)
    for rec in trade_records:
        try:
            month = pd.Timestamp(rec['entry_date']).to_period('M').to_timestamp()
            strat_by_month[month].append(float(rec['return_pct']))
        except Exception:
            pass
    months     = sorted(strat_by_month.keys())
    strat_rets = []
    spy_rets   = []
    for m in months:
        if m in spy_monthly.index:
            strat_rets.append(np.mean(strat_by_month[m]))
            spy_rets.append(float(spy_monthly.loc[m]))
    if len(strat_rets) < 5:
        return None
    s = pd.Series(strat_rets)
    sp = pd.Series(spy_rets)
    return float(s.corr(sp))

# ─────────────────────────────────────────────
# REGIME-CONDITIONAL ANALYSIS
# ─────────────────────────────────────────────

def regime_stats(trade_records, calendar, annualize=12):
    """
    For each macro regime, compute: Sharpe, Sortino, n_trades, win_rate, avg_return.
    Returns dict of {regime: metrics_dict}.
    """
    by_regime = defaultdict(list)
    for rec in trade_records:
        regime = get_trade_regime(rec['entry_date'], calendar)
        by_regime[regime].append(float(rec['return_pct']))

    result = {}
    for regime in REGIMES_ORDERED + [REGIME_UNKNOWN]:
        rets = by_regime.get(regime, [])
        if len(rets) < 3:
            result[regime] = {
                'n_trades': len(rets),
                'sharpe':   None,
                'sortino':  None,
                'win_rate': None,
                'avg_return': None,
                'note':     'insufficient data'
            }
        else:
            result[regime] = {
                'n_trades':   len(rets),
                'sharpe':     round(sharpe(rets, annualize=annualize), 4),
                'sortino':    round(sortino(rets, annualize=annualize), 4),
                'win_rate':   round(win_rate(rets), 4),
                'avg_return': round(float(np.mean(rets)), 4),
                'max_dd':     round(max_drawdown(rets), 4),
            }
    return result

# ─────────────────────────────────────────────
# FULL STRATEGY ANALYSIS
# ─────────────────────────────────────────────

def analyze_strategy(records: list, calendar: pd.DataFrame,
                     spy_monthly: pd.Series, annualize: int = 12) -> dict:
    """
    Full risk-adjusted analysis for a list of trade records from one strategy.
    """
    if not records:
        return {'error': 'no records'}

    rets   = [float(r['return_pct']) for r in records]
    eq     = equity_curve(rets)
    years  = len(rets) / annualize
    cagr   = float(eq[-1] ** (1/years) - 1) if years > 0 and eq[-1] > 0 else 0.0

    strategy  = records[0].get('strategy', 'unknown')
    category  = records[0].get('category', '')
    round_num = records[0].get('round', None)
    tickers   = sorted(set(r.get('ticker', '') for r in records))
    dates     = sorted(r['entry_date'] for r in records if 'entry_date' in r)

    core = {
        # identity
        'strategy':         strategy,
        'category':         category,
        'round':            round_num,
        'tickers':          tickers,
        'n_trades':         len(records),
        'date_range':       f"{dates[0]} – {dates[-1]}" if dates else 'unknown',
        # performance
        'total_return':     round(float(eq[-1] - 1), 4),
        'cagr':             round(cagr, 4),
        # risk-adjusted ratios
        'sharpe':           round(sharpe(rets, annualize), 4),
        'sortino':          round(sortino(rets, annualize), 4),
        'calmar':           round(calmar(rets, annualize), 4),
        # distribution
        'skewness':         round(skewness(rets), 4),
        'kurtosis':         round(kurtosis(rets), 4),  # excess; normal = 0
        # risk
        'max_drawdown':     round(max_drawdown(rets), 4),
        'max_consec_losses': max_consec_losses(rets),
        # trade stats
        'win_rate':         round(win_rate(rets), 4),
        'profit_factor':    round(profit_factor(rets), 4),
        'avg_return':       round(float(np.mean(rets)), 4),
        'avg_win':          round(float(np.mean([r for r in rets if r > 0])), 4) if any(r > 0 for r in rets) else 0,
        'avg_loss':         round(float(np.mean([r for r in rets if r < 0])), 4) if any(r < 0 for r in rets) else 0,
        # sizing
        'kelly_fraction':   round(kelly_fraction(rets), 4),
        # correlation
        'spy_correlation':  (lambda v: round(v, 4) if v is not None else None)(spy_correlation(records, spy_monthly)),
        # regime breakdown
        'regime_stats':     regime_stats(records, calendar, annualize),
        # flags
        'negative_skew_flag':  skewness(rets) < -0.5,
        'high_kurtosis_flag':  kurtosis(rets) > 3.0,   # fat tails
        'spy_correlated_flag': (spy_correlation(records, spy_monthly) or 0) > 0.6,
    }

    # Risk summary sentence
    flags = []
    if core['negative_skew_flag']:
        flags.append('negative skew (hidden tail risk)')
    if core['high_kurtosis_flag']:
        flags.append('fat tails (kurtosis > 3)')
    if core['spy_correlated_flag']:
        flags.append('high SPY correlation (not market-neutral)')
    core['risk_flags'] = flags if flags else ['none identified']

    return core

# ─────────────────────────────────────────────
# CROSS-STRATEGY PORTFOLIO ANALYSIS
# ─────────────────────────────────────────────

def cross_strategy_analysis(all_analyses: dict) -> dict:
    """
    Build monthly return series per strategy, compute correlation matrix
    and naive max-Sharpe weights.
    """
    # Reconstruct monthly return series per strategy
    monthly_series = {}
    for name, analysis in all_analyses.items():
        if 'regime_stats' not in analysis:
            continue
        # We can only reconstruct from records directly — need raw records
        # This is called with raw records in the full pipeline below

    # Placeholder — full implementation in next iteration once we have
    # multiple strategies' trade logs to work with
    return {'note': 'cross-strategy analysis requires multiple trade log files'}

# ─────────────────────────────────────────────
# REPORT FORMATTING
# ─────────────────────────────────────────────

def format_report(analysis: dict) -> str:
    """Format a single strategy analysis as human-readable text."""
    s    = analysis
    name = s.get('strategy', 'unknown')
    sep  = '─' * 60

    regime_lines = []
    for regime, stats in s.get('regime_stats', {}).items():
        if stats.get('n_trades', 0) < 3:
            regime_lines.append(f"  {regime:<16} n={stats['n_trades']} (insufficient data)")
        else:
            regime_lines.append(
                f"  {regime:<16} n={stats['n_trades']:>3}  "
                f"Sharpe={stats['sharpe']:>+7.3f}  "
                f"Sortino={stats['sortino']:>+7.3f}  "
                f"WR={stats['win_rate']:.1%}  "
                f"AvgRet={stats['avg_return']:>+.3f}"
            )

    flags = '\n'.join(f"  ⚠ {f}" for f in s.get('risk_flags', ['none']))

    lines = [
        sep,
        f"Strategy:    {name}  (R{s.get('round', '?')} · {s.get('category', '')})",
        f"Instruments: {', '.join(s.get('tickers', [])[:8])}{'...' if len(s.get('tickers',[])) > 8 else ''}",
        f"Period:      {s.get('date_range', 'unknown')}  ({s.get('n_trades', 0)} trades)",
        sep,
        "PERFORMANCE",
        f"  CAGR:           {s.get('cagr', 0):>+8.2%}",
        f"  Total Return:   {s.get('total_return', 0):>+8.2%}",
        "",
        "RISK-ADJUSTED RATIOS",
        f"  Sharpe:         {s.get('sharpe', 0):>+8.3f}",
        f"  Sortino:        {s.get('sortino', 0):>+8.3f}",
        f"  Calmar:         {s.get('calmar', 0):>+8.3f}",
        "",
        "RISK",
        f"  Max Drawdown:   {s.get('max_drawdown', 0):>8.2%}",
        f"  Max Consec Loss:{s.get('max_consec_losses', 0):>8}",
        f"  Skewness:       {s.get('skewness', 0):>+8.3f}  {'← negative skew ⚠' if s.get('negative_skew_flag') else ''}",
        f"  Kurtosis:       {s.get('kurtosis', 0):>+8.3f}  {'← fat tails ⚠' if s.get('high_kurtosis_flag') else ''}",
        f"  SPY Correlation:{str(round(s.get('spy_correlation') or 0, 3)):>8}  {'← correlated ⚠' if s.get('spy_correlated_flag') else ''}",
        "",
        "TRADE STATS",
        f"  Win Rate:       {s.get('win_rate', 0):>8.1%}",
        f"  Profit Factor:  {s.get('profit_factor', 0):>8.3f}",
        f"  Avg Win:        {s.get('avg_win', 0):>+8.3%}",
        f"  Avg Loss:       {s.get('avg_loss', 0):>+8.3%}",
        f"  Kelly Fraction: {s.get('kelly_fraction', 0):>8.1%}",
        "",
        "REGIME-CONDITIONAL PERFORMANCE",
    ] + regime_lines + [
        "",
        "RISK FLAGS",
        flags,
        sep,
    ]
    return '\n'.join(lines)

# ─────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────

def load_trade_log(path: str) -> list:
    """Load a .trades.jsonl file. Returns list of record dicts."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records

def run_analysis(paths: list, start: str = '2020-01-01',
                 end: str = '2025-12-31', verbose: bool = True) -> dict:
    """
    Main entry point. Analyzes one or more .trades.jsonl files.
    Returns dict of {strategy_name: analysis_dict}.
    """
    print("=" * 60)
    print("ANALYSIS LAYER v1.0 — NanoClaw Trading Eval Framework")
    print("=" * 60)

    # Build regime calendar
    print("\n[1/3] Building regime calendar (SPY + ^VIX)...")
    calendar = build_regime_calendar(start, end)
    if len(calendar) == 0:
        print("  ⚠ Could not build regime calendar — SPY/VIX data unavailable")
        calendar = pd.DataFrame()

    # SPY monthly returns for correlation
    spy_monthly = None
    if len(calendar) > 0 and 'spy_ret_1m' in calendar.columns:
        spy_monthly = calendar['spy_ret_1m']

    # Print regime summary
    if len(calendar) > 0:
        regime_counts = calendar['regime'].value_counts()
        print(f"  Period: {calendar.index[0].strftime('%Y-%m')} – "
              f"{calendar.index[-1].strftime('%Y-%m')} ({len(calendar)} months)")
        for regime, count in regime_counts.items():
            pct = count / len(calendar)
            print(f"  {regime:<16} {count:>3} months ({pct:.0%})")

    # Analyze each file
    print(f"\n[2/3] Analyzing {len(paths)} trade log file(s)...")
    all_analyses = {}

    for path in paths:
        records = load_trade_log(path)
        if not records:
            print(f"  [skip] {path} — empty file")
            continue

        # Group by strategy name (a file may contain multiple strategies)
        by_strategy = defaultdict(list)
        for rec in records:
            by_strategy[rec.get('strategy', 'unknown')].append(rec)

        for strategy_name, strat_records in by_strategy.items():
            print(f"  Analyzing {strategy_name} ({len(strat_records)} trades)...")
            analysis = analyze_strategy(strat_records, calendar, spy_monthly)
            all_analyses[strategy_name] = analysis

    # Output
    print(f"\n[3/3] Writing reports...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')

    for strategy_name, analysis in all_analyses.items():
        # JSON
        json_path = ANALYSIS_DIR / f"{strategy_name}_{timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(analysis, f, indent=2, default=str)

        # Text report
        if verbose:
            print()
            print(format_report(analysis))

    # Summary table
    print("\n" + "=" * 60)
    print(f"{'Strategy':<30} {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} "
          f"{'MaxDD':>7} {'WR':>6} {'Skew':>6} {'SPYcorr':>8}")
    print("-" * 60)
    for name, a in sorted(all_analyses.items(),
                          key=lambda x: x[1].get('sharpe', 0), reverse=True):
        corr = a.get('spy_correlation')
        corr_str = f"{corr:>+7.3f}" if corr is not None else "    N/A"
        flags = '⚠' if a.get('risk_flags') != ['none identified'] else ' '
        print(f"  {flags}{name:<28} "
              f"{a.get('sharpe', 0):>+7.3f} "
              f"{a.get('sortino', 0):>+8.3f} "
              f"{a.get('calmar', 0):>+7.3f} "
              f"{a.get('max_drawdown', 0):>7.2%} "
              f"{a.get('win_rate', 0):>6.1%} "
              f"{a.get('skewness', 0):>+6.2f} "
              f"{corr_str}")
    print()

    # Save combined JSON
    combined_path = ANALYSIS_DIR / f"combined_{timestamp}.json"
    with open(combined_path, 'w') as f:
        json.dump({'run_date': timestamp,
                   'regime_calendar_months': len(calendar),
                   'strategies': all_analyses}, f, indent=2, default=str)
    print(f"Combined analysis → {combined_path}")

    return all_analyses


# ─────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='NanoClaw Analysis Layer — compute rich metrics from trade logs')
    parser.add_argument('files', nargs='*',
                        help='Specific .trades.jsonl files to analyze '
                             '(default: all files in trade_logs/)')
    parser.add_argument('--start', default='2020-01-01',
                        help='Regime calendar start date')
    parser.add_argument('--end', default='2025-12-31',
                        help='Regime calendar end date')
    parser.add_argument('--regime-only', action='store_true',
                        help='Only print regime calendar, no strategy analysis')
    args = parser.parse_args()

    if args.regime_only:
        cal = build_regime_calendar(args.start, args.end)
        print(cal.to_string())
        sys.exit(0)

    if args.files:
        paths = args.files
    else:
        paths = sorted(str(p) for p in TRADE_LOG_DIR.glob('*.trades.jsonl'))
        if not paths:
            print(f"No .trades.jsonl files found in {TRADE_LOG_DIR}")
            print("Run a v2 harness first to generate trade logs.")
            sys.exit(0)

    run_analysis(paths, start=args.start, end=args.end)
