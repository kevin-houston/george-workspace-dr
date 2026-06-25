"""
H328 — Student-t Emission HMM (H251 heavy-tail fix)
=====================================================
Source: arXiv:2606.23492 (2026) — "Continuous HMM with Heavy-Tail Emissions
for Equity Regime Detection"

H251 was CONFIRMED but degenerate: predicted low_vol 100% of OOS months.
Root cause: Gaussian thin tails absorb crisis returns into the low-vol state.
Fix: transform returns via r* = sign(r)*|r|^(1/nu) (nu=4 approximates Student-t)
before fitting GaussianHMM, so extreme returns compress less and preserve
state separation.

Also test Option B: direct scipy.stats.t fitting via custom EM (experimental).

Universe: SPY / TLT / GLD (same as H251)
IS: 2004-2017 | OOS: 2018-2026
Gate: OOS Sharpe > H251 0.941 AND no single state > 80% OOS months
"""
import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from hmmlearn import hmm

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

TICKERS    = ["SPY", "TLT", "GLD"]
DATA_START = "2003-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2004-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
N_STATES   = 3
NU         = 4       # Student-t df for power transform; r* = sign(r)|r|^(1/nu)
MIN_DUR    = 2       # smooth regime labels: min consecutive months in same state

# State-conditional allocations (same as H251)
ALLOC = {
    0: {"SPY": 0.80, "TLT": 0.10, "GLD": 0.10},  # low-vol / bull
    1: {"SPY": 0.50, "TLT": 0.30, "GLD": 0.20},  # neutral
    2: {"SPY": 0.20, "TLT": 0.50, "GLD": 0.30},  # high-vol / bear
}
TC_BPS = 10  # round-trip; regime changes touch 3 assets


def fetch_monthly_returns() -> pd.DataFrame:
    print("Fetching SPY/TLT/GLD prices…")
    raw = yf.download(TICKERS, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)["Close"]
    monthly = raw.resample("ME").last().pct_change().dropna()
    print(f"  {len(monthly)} monthly observations")
    return monthly


def power_transform(rets: pd.DataFrame, nu: int) -> np.ndarray:
    """Approximate Student-t tail compression: r* = sign(r)*|r|^(1/nu)."""
    r = rets.values
    return np.sign(r) * (np.abs(r) ** (1.0 / nu))


def smooth_regime_labels(labels: np.ndarray, min_dur: int) -> np.ndarray:
    """Force minimum consecutive months in same regime to reduce whipsaw."""
    smoothed = labels.copy()
    n = len(smoothed)
    i = 0
    while i < n:
        j = i + 1
        while j < n and smoothed[j] == smoothed[i]:
            j += 1
        run_len = j - i
        if run_len < min_dur and i > 0:
            smoothed[i:j] = smoothed[i - 1]
        i = j
    return smoothed


def fit_hmm_option_a(train_data: pd.DataFrame) -> hmm.GaussianHMM:
    """Option A: power-transform returns, then fit GaussianHMM."""
    X = power_transform(train_data, NU)
    model = hmm.GaussianHMM(n_components=N_STATES, covariance_type="full",
                             n_iter=200, random_state=42)
    model.fit(X)
    return model


def get_regime_labels(model: hmm.GaussianHMM, data: pd.DataFrame) -> np.ndarray:
    X = power_transform(data, NU)
    raw = model.predict(X)
    # relabel states by SPY mean return (ascending = bear to bull)
    state_spy_mean = {}
    for s in range(N_STATES):
        mask = raw == s
        if mask.sum() > 0:
            state_spy_mean[s] = data.loc[mask, "SPY"].mean()
        else:
            state_spy_mean[s] = 0.0
    # sort: state with highest SPY mean = 0 (bull), lowest = 2 (bear)
    sorted_states = sorted(state_spy_mean, key=state_spy_mean.get, reverse=True)
    remap = {orig: new for new, orig in enumerate(sorted_states)}
    relabeled = np.array([remap[s] for s in raw])
    return smooth_regime_labels(relabeled, MIN_DUR)


def run_backtest(monthly: pd.DataFrame) -> pd.Series:
    is_data  = monthly.loc[IS_START:IS_END]
    oos_data = monthly.loc[OOS_START:OOS_END]

    # Fit on IS data only
    model = fit_hmm_option_a(is_data)

    # For OOS: rolling re-fit on all data up to each month (expanding window)
    port_rets = []
    prev_alloc = None

    # Full history for expanding window
    all_data = monthly.loc[IS_START:OOS_END]
    oos_idx  = oos_data.index

    for i, date in enumerate(oos_idx):
        # Predict regime using all data up to (not including) this month
        hist = all_data.loc[:date].iloc[:-1]  # exclude current month
        if len(hist) < 24:
            continue

        # Re-fit every 6 months to avoid constant refitting cost
        if i % 6 == 0:
            model = fit_hmm_option_a(hist)

        labels = get_regime_labels(model, hist)
        current_regime = int(labels[-1])
        alloc = ALLOC[current_regime]

        # This month's portfolio return
        month_ret = oos_data.loc[date]
        port_ret = sum(alloc[t] * month_ret[t] for t in TICKERS)

        # Transaction cost on weight changes
        tc = 0.0
        if prev_alloc is not None:
            turnover = sum(abs(alloc.get(t, 0) - prev_alloc.get(t, 0)) for t in TICKERS)
            tc = (turnover / 2) * TC_BPS / 10000

        port_rets.append({"date": date, "return": port_ret - tc, "regime": current_regime})
        prev_alloc = alloc

    df = pd.DataFrame(port_rets).set_index("date")
    return df


def compute_stats(rets: pd.Series, label: str) -> dict:
    cum = (1 + rets).cumprod()
    n_years = len(rets) / 12
    cagr = cum.iloc[-1] ** (1 / n_years) - 1 if n_years > 0 else 0
    sharpe = (rets.mean() / rets.std()) * np.sqrt(12) if rets.std() > 0 else 0
    roll_max = cum.cummax()
    drawdowns = (cum - roll_max) / roll_max
    maxdd = drawdowns.min()
    neg_years = (rets.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum()
    print(f"\n  {label}:")
    print(f"    Sharpe: {sharpe:.3f}")
    print(f"    CAGR:   {cagr:.1%}")
    print(f"    MaxDD:  {maxdd:.1%}")
    print(f"    Neg yr: {neg_years}")
    return {"sharpe": round(sharpe, 4), "cagr": round(cagr, 4),
            "maxdd": round(maxdd, 4), "neg_years": int(neg_years)}


if __name__ == "__main__":
    print("=" * 60)
    print("H328 — Student-t Emission HMM (H251 fix)")
    print("=" * 60)

    monthly = fetch_monthly_returns()

    print("\nFitting HMM with power-transform (Option A)…")
    bt = run_backtest(monthly)

    oos_rets    = bt["return"]
    oos_regimes = bt["regime"]

    print("\n--- OUT-OF-SAMPLE (2018–2026) ---")
    oos_stats = compute_stats(oos_rets, "H328 OOS")

    # Regime distribution
    regime_counts = oos_regimes.value_counts().sort_index()
    total = len(oos_regimes)
    print(f"\n  Regime distribution (OOS):")
    regime_names = {0: "bull/low-vol", 1: "neutral", 2: "bear/high-vol"}
    for s, cnt in regime_counts.items():
        pct = cnt / total * 100
        print(f"    State {s} ({regime_names.get(s,'?')}): {cnt}mo ({pct:.0f}%)")

    max_state_pct = regime_counts.max() / total
    degenerate = bool(max_state_pct > 0.80)
    print(f"  Max single-state %: {max_state_pct:.0%} → {'DEGENERATE ✗' if degenerate else 'OK ✓'}")

    # Correlation with H026 proxy (SPY)
    spy_monthly = monthly["SPY"].loc[OOS_START:OOS_END]
    common = oos_rets.index.intersection(spy_monthly.index)
    if len(common) > 10:
        corr_h026 = float(np.corrcoef(oos_rets.loc[common].values,
                                       spy_monthly.loc[common].values)[0, 1])
    else:
        corr_h026 = float("nan")
    print(f"  Corr(SPY) OOS: {corr_h026:.3f}  (H251 was ~0.71)")

    # Gate check
    H251_SHARPE = 0.941
    gate_sharpe  = oos_stats["sharpe"] > H251_SHARPE
    gate_nodegen = not degenerate

    print(f"\n--- GATE CHECK ---")
    print(f"  OOS Sharpe > {H251_SHARPE}: {oos_stats['sharpe']:.3f} → {'✓' if gate_sharpe else '✗'}")
    print(f"  No single state > 80%:      {max_state_pct:.0%} → {'✓' if gate_nodegen else '✗'}")

    verdict = "CONFIRMED" if (gate_sharpe and gate_nodegen) else "NOT CONFIRMED"
    print(f"\n  VERDICT: {verdict}")

    out = {
        "hypothesis": "H328",
        "description": "Student-t Emission HMM (H251 heavy-tail fix, Option A)",
        "oos_stats": oos_stats,
        "regime_distribution": {str(k): int(v) for k, v in regime_counts.items()},
        "max_state_pct": round(float(max_state_pct), 4),
        "degenerate": degenerate,
        "corr_spy_oos": round(corr_h026, 4),
        "gates": {"sharpe": bool(gate_sharpe), "no_degeneracy": bool(gate_nodegen)},
        "verdict": verdict,
    }
    out_path = RESULT_DIR / "h328_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Results saved → {out_path}")
