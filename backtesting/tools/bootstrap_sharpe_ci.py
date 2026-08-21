"""
BCa bootstrap confidence interval for the Sharpe ratio.

Not a PyBroker dependency -- reimplements PyBroker's per-bar-resampled BCa
bootstrap methodology directly with numpy/scipy (both already in venv/), so it
can be dropped into any existing run_hNNN.py as a sanity check without
migrating the pipeline onto PyBroker's Strategy/StrategyConfig scaffolding.
See wiki/trading/tools/pybroker.md for the source methodology.

Usage as a library:
    from backtesting.tools.bootstrap_sharpe_ci import bootstrap_sharpe_ci
    ci = bootstrap_sharpe_ci(oos_monthly_returns, periods_per_year=12)
    print(f"OOS Sharpe {ci['point']} (95% CI [{ci['lo']}, {ci['hi']}], n={ci['n_periods']})")

Usage from the CLI, against a CSV of one return value per row (no header):
    python3 backtesting/tools/bootstrap_sharpe_ci.py path/to/returns.csv --periods-per-year 12
"""
import argparse

import numpy as np
from scipy.stats import norm


def _sharpe(returns, periods_per_year):
    r = np.asarray(returns, dtype=float)
    std = r.std(ddof=1)
    if std == 0:
        return 0.0
    return (r.mean() / std) * np.sqrt(periods_per_year)


def bootstrap_sharpe_ci(returns, n_boot=2000, periods_per_year=12, alpha=0.05, seed=None):
    """BCa bootstrap confidence interval for the Sharpe ratio.

    Resamples whole return periods (per-bar, matching PyBroker's approach --
    NOT per-trade, which understates uncertainty when trades cluster).
    Requires at least 8 return periods; below that the bootstrap distribution
    is too sparse to trust.
    """
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 8:
        raise ValueError(f"Need at least 8 return periods for a meaningful bootstrap, got {n}")

    rng = np.random.default_rng(seed)
    point = _sharpe(r, periods_per_year)

    boot = np.empty(n_boot)
    for i in range(n_boot):
        sample = r[rng.integers(0, n, size=n)]
        boot[i] = _sharpe(sample, periods_per_year)

    # Bias-correction z0
    z0 = norm.ppf(np.clip((boot < point).mean(), 1e-6, 1 - 1e-6))

    # Acceleration via jackknife
    jack = np.array([_sharpe(np.delete(r, i), periods_per_year) for i in range(n)])
    jack_mean = jack.mean()
    num = np.sum((jack_mean - jack) ** 3)
    den = 6.0 * (np.sum((jack_mean - jack) ** 2) ** 1.5)
    a = num / den if den != 0 else 0.0

    z_lo, z_hi = norm.ppf(alpha / 2), norm.ppf(1 - alpha / 2)
    lo_p = norm.cdf(z0 + (z0 + z_lo) / (1 - a * (z0 + z_lo)))
    hi_p = norm.cdf(z0 + (z0 + z_hi) / (1 - a * (z0 + z_hi)))

    lo = np.percentile(boot, 100 * np.clip(lo_p, 0, 1))
    hi = np.percentile(boot, 100 * np.clip(hi_p, 0, 1))

    return {
        "point": round(float(point), 3),
        "lo": round(float(lo), 3),
        "hi": round(float(hi), 3),
        "n_boot": n_boot,
        "n_periods": n,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BCa bootstrap CI for Sharpe ratio")
    parser.add_argument("returns_csv", help="CSV of period returns, one value per row, no header")
    parser.add_argument("--periods-per-year", type=int, default=12)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    returns = np.loadtxt(args.returns_csv, delimiter=",")
    result = bootstrap_sharpe_ci(
        returns, n_boot=args.n_boot, periods_per_year=args.periods_per_year, seed=args.seed
    )
    print(f"Sharpe point estimate: {result['point']}")
    print(
        f"95% BCa CI: [{result['lo']}, {result['hi']}]  "
        f"(n_boot={result['n_boot']}, n_periods={result['n_periods']})"
    )
