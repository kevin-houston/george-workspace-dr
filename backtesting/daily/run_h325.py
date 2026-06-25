"""
H325 — AEGIS Sortino-Optimized Cross-Sectional Momentum
========================================================
Source: arXiv:2604.09060 (2026) — "Taming the Black Swan: A Momentum-Gated
Hierarchical Optimisation Framework for Asymmetric Alpha Generation"

Three-stage pipeline over H198 universe:
  Stage 1: Volatility-adjusted momentum score = 6m-1m return / 63d realized vol
  Stage 2: Minimax-correlation filter (greedy, max pairwise corr ≤ 0.60)
  Stage 3: SLSQP Sortino ratio maximization (mean/downside_std, 12m rolling IS)

Universe: Same 30 large-cap S&P 500 stocks as H198
IS: 2013-2020 | OOS: 2021-2026
Gate: OOS Sharpe > H198 1.174 AND MaxDD improvement > 5pp AND Corr(SPY) < 0.70
"""
import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from scipy.optimize import minimize

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

TOP_CANDIDATES = 12   # pre-filter by vol-adj momentum before correlation filter
FINAL_K        = 6    # stocks after minimax-corr filter (= top quintile)
MAX_CORR       = 0.60 # minimax pairwise correlation threshold
MIN_W          = 0.05 # min weight per stock
MAX_W          = 0.30 # max weight per stock
TC_BPS         = 5    # one-way transaction cost
VOL_WINDOW     = 63   # days for realized vol
OPT_WINDOW     = 12   # months of history for Sortino optimization
H198_SHARPE    = 1.174
H198_MAXDD     = -0.227  # approximate from H198 OOS results


def fetch_prices() -> pd.DataFrame:
    print("Fetching price data…")
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)["Close"]
    raw = raw.dropna(how="all")
    print(f"  Downloaded {raw.shape[0]} daily rows x {raw.shape[1]} tickers")
    return raw


def monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.resample("ME").last().pct_change().dropna(how="all")


def compute_vol_adj_score(prices: pd.DataFrame, date: pd.Timestamp) -> pd.Series:
    """Vol-adjusted 6m-1m momentum score at month-end `date`."""
    # 6m-1m = return from 7 months ago to 1 month ago (skip last month)
    try:
        t_minus_1m = prices.index[prices.index <= date - pd.DateOffset(months=1)][-1]
        t_minus_7m = prices.index[prices.index <= date - pd.DateOffset(months=7)][-1]
    except IndexError:
        return pd.Series(dtype=float)

    mom = prices.loc[t_minus_7m:t_minus_1m].iloc[-1] / prices.loc[t_minus_7m:t_minus_1m].iloc[0] - 1

    # 63-day realized vol ending 1 month ago
    daily_window = prices.loc[:t_minus_1m].iloc[-VOL_WINDOW:]
    if len(daily_window) < 20:
        return pd.Series(dtype=float)
    rvol = daily_window.pct_change().std() * np.sqrt(252)
    rvol = rvol.replace(0, np.nan)

    score = mom / rvol
    return score.dropna()


def minimax_corr_filter(candidates: list, daily_rets: pd.DataFrame, k: int, max_corr: float) -> list:
    """Greedy selection: pick k stocks with max pairwise correlation ≤ max_corr."""
    if len(candidates) <= k:
        return candidates

    corr_mat = daily_rets[candidates].corr()
    selected = [candidates[0]]  # always take top-scored stock first

    for ticker in candidates[1:]:
        if len(selected) >= k:
            break
        corrs = [abs(corr_mat.loc[ticker, s]) for s in selected if ticker in corr_mat.index and s in corr_mat.columns]
        if not corrs or max(corrs) <= max_corr:
            selected.append(ticker)

    # If still short of k, fill from remaining (relax constraint)
    if len(selected) < k:
        remaining = [t for t in candidates if t not in selected]
        selected.extend(remaining[:k - len(selected)])

    return selected[:k]


def sortino_neg(weights, returns_matrix):
    """Negative Sortino ratio (for minimization)."""
    port_ret = returns_matrix @ weights
    mean_ret = port_ret.mean()
    downside = port_ret[port_ret < 0]
    if len(downside) < 2:
        return -mean_ret * 100  # fallback: maximize mean
    downside_std = np.sqrt((downside ** 2).mean())
    if downside_std < 1e-8:
        return -mean_ret * 100
    return -(mean_ret / downside_std)


def optimize_weights(selected: list, monthly_ret: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    """SLSQP Sortino optimization on OPT_WINDOW months ending at as_of."""
    window_start = as_of - pd.DateOffset(months=OPT_WINDOW)
    hist = monthly_ret.loc[window_start:as_of, selected].dropna()

    if len(hist) < 6 or len(selected) == 0:
        # fallback: equal weight
        ew = 1.0 / len(selected)
        return {t: ew for t in selected}

    n = len(selected)
    x0 = np.ones(n) / n
    bounds = [(MIN_W, MAX_W)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    try:
        res = minimize(sortino_neg, x0, args=(hist.values,),
                       method="SLSQP", bounds=bounds, constraints=constraints,
                       options={"ftol": 1e-9, "maxiter": 500})
        if res.success and abs(res.x.sum() - 1.0) < 0.01:
            return {t: float(w) for t, w in zip(selected, res.x)}
    except Exception:
        pass

    # fallback: equal weight
    return {t: 1.0 / n for t in selected}


def run_backtest(prices: pd.DataFrame, monthly_ret: pd.DataFrame,
                 spy_monthly: pd.Series) -> pd.DataFrame:
    rebalance_dates = monthly_ret.loc[IS_START:OOS_END].index
    results = []
    prev_port = {}

    for i, date in enumerate(rebalance_dates):
        # need at least 7 months of history for score
        if date < IS_START + pd.DateOffset(months=8):
            continue

        # Stage 1: vol-adjusted momentum score
        score = compute_vol_adj_score(prices, date)
        if len(score) < TOP_CANDIDATES:
            continue

        # Filter to universe tickers available in monthly_ret
        score = score[[t for t in score.index if t in monthly_ret.columns]]
        top_candidates = score.nlargest(TOP_CANDIDATES).index.tolist()

        # Stage 2: minimax-correlation filter
        daily_rets = prices[top_candidates].pct_change().dropna()
        selected = minimax_corr_filter(top_candidates, daily_rets, FINAL_K, MAX_CORR)

        # Stage 3: SLSQP Sortino optimization
        weights = optimize_weights(selected, monthly_ret, date)

        # compute next-month return
        if i + 1 >= len(rebalance_dates):
            continue
        next_date = rebalance_dates[i + 1]

        # next month individual returns
        next_rets = monthly_ret.loc[next_date, list(weights.keys())]
        port_ret = sum(weights.get(t, 0) * next_rets.get(t, 0) for t in weights)

        # transaction cost: estimate turnover
        turnover = 0.0
        for t in set(list(weights.keys()) + list(prev_port.keys())):
            new_w = weights.get(t, 0.0)
            old_w = prev_port.get(t, 0.0)
            turnover += abs(new_w - old_w)
        tc = (turnover / 2) * TC_BPS / 10000

        prev_port = weights.copy()

        results.append({
            "date": next_date,
            "gross_return": port_ret,
            "net_return": port_ret - tc,
            "holdings": list(weights.keys()),
        })

    df = pd.DataFrame(results).set_index("date")
    return df


def compute_stats(rets: pd.Series, label: str) -> dict:
    cum = (1 + rets).cumprod()
    n_years = len(rets) / 12
    cagr = cum.iloc[-1] ** (1 / n_years) - 1 if n_years > 0 else 0
    sharpe = (rets.mean() / rets.std()) * np.sqrt(12) if rets.std() > 0 else 0
    roll_max = cum.cummax()
    drawdowns = (cum - roll_max) / roll_max
    maxdd = drawdowns.min()
    neg_years = (rets.resample("YE").apply(lambda x: (1 + x).prod() - 1) < 0).sum()
    print(f"\n  {label}:")
    print(f"    Sharpe:   {sharpe:.3f}")
    print(f"    CAGR:     {cagr:.1%}")
    print(f"    MaxDD:    {maxdd:.1%}")
    print(f"    Neg yrs:  {neg_years}")
    return {"sharpe": round(sharpe, 4), "cagr": round(cagr, 4),
            "maxdd": round(maxdd, 4), "neg_years": int(neg_years)}


if __name__ == "__main__":
    print("=" * 60)
    print("H325 — AEGIS Sortino Momentum Optimizer")
    print("=" * 60)

    prices = fetch_prices()
    monthly_ret = monthly_returns(prices)

    spy_prices = yf.download("SPY", start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)["Close"]
    spy_monthly = spy_prices.resample("ME").last().pct_change().dropna()

    print("\nRunning backtest (vol-adj momentum + corr filter + Sortino opt)…")
    bt = run_backtest(prices, monthly_ret, spy_monthly)

    is_rets  = bt.loc[IS_START:IS_END, "net_return"]
    oos_rets = bt.loc[OOS_START:OOS_END, "net_return"]

    print("\n--- IN-SAMPLE (2013–2020) ---")
    is_stats = compute_stats(is_rets, "H325 IS")

    print("\n--- OUT-OF-SAMPLE (2021–2026) ---")
    oos_stats = compute_stats(oos_rets, "H325 OOS")

    # Correlation with SPY OOS
    spy_oos = spy_monthly.loc[OOS_START:OOS_END].squeeze()
    spy_oos.index = spy_oos.index.to_period("M").to_timestamp("M")
    oos_aligned = oos_rets.copy()
    oos_aligned.index = oos_aligned.index.to_period("M").to_timestamp("M")
    common = oos_aligned.index.intersection(spy_oos.index)
    if len(common) > 10:
        a = oos_aligned.loc[common].values.astype(float)
        b = spy_oos.loc[common].values.astype(float)
        corr_spy = float(np.corrcoef(a, b)[0, 1])
    else:
        corr_spy = float("nan")
    print(f"\n  Corr(SPY) OOS: {corr_spy:.3f}")

    # Walk-forward ratio
    wf = oos_stats["sharpe"] / is_stats["sharpe"] if is_stats["sharpe"] > 0 else float("nan")
    print(f"  WF ratio: {wf:.3f}")

    # Gate check
    gate_sharpe = oos_stats["sharpe"] > H198_SHARPE
    gate_maxdd  = (oos_stats["maxdd"] - H198_MAXDD) > 0.05  # 5pp improvement
    gate_corr   = corr_spy < 0.70

    print(f"\n--- GATE CHECK ---")
    print(f"  OOS Sharpe > {H198_SHARPE}: {oos_stats['sharpe']:.3f} → {'✓' if gate_sharpe else '✗'}")
    print(f"  MaxDD improvement > 5pp:    {oos_stats['maxdd']:.1%} vs {H198_MAXDD:.1%} → {'✓' if gate_maxdd else '✗'}")
    print(f"  Corr(SPY) < 0.70:           {corr_spy:.3f} → {'✓' if gate_corr else '✗'}")

    verdict = "CONFIRMED" if (gate_sharpe and gate_maxdd and gate_corr) else "NOT CONFIRMED"
    print(f"\n  VERDICT: {verdict}")

    # Save results
    out = {
        "hypothesis": "H325",
        "description": "AEGIS Sortino-Optimized Cross-Sectional Momentum",
        "is_stats": is_stats,
        "oos_stats": oos_stats,
        "corr_spy_oos": round(corr_spy, 4),
        "wf_ratio": round(wf, 4),
        "gates": {"sharpe": bool(gate_sharpe), "maxdd": bool(gate_maxdd), "corr": bool(gate_corr)},
        "verdict": verdict,
    }
    out_path = RESULT_DIR / "h325_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Results saved → {out_path}")
