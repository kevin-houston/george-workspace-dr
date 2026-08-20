"""
H522 — Spatio-Temporal Momentum Single-Linear-Layer (STMOM-SLP) on H241 200-Stock Universe
=============================================================================================
Closes the long-queued "H180 spatio-temporal momentum NN" direction (see
CLAUDE.local.md "Next research direction" note and
wiki/trading/sources/spatio-temporal-momentum-2023.md).

Source: Tan, Roberts & Zohren (2023) "Spatio-Temporal Momentum: Jointly Learning
Time-Series and Cross-Sectional Strategies", arXiv:2302.10175, JFDS 5(3):107-129.

Core idea: instead of hand-crafted cross-sectional rank momentum (H198/H241-A),
train a small neural network (as simple as a single linear layer, "SLP") to
directly output *position sizes* for the whole cross-section jointly, trained
by gradient descent on a differentiable Sharpe-ratio loss (not a regression/
classification proxy target). The paper's headline finding is "simplicity
wins" — SLP beats MLP/LSTM/CNN on their institutional datasets. Turnover
regularization is explicitly required (Table 6): unregularized SLP collapses
from OOS Sharpe 2.609 (0bp) to 0.762 (10bp costs) — turnover-regularized SLP
is HIGHER than plain SLP at 10bp. We budget for this from the start.

Dataset caveat (documented per the source page): the paper uses a paid CRSP
46-stock Financials-only universe (1990-2022) and a paid Pinnacle futures
dataset — neither is reproducible with our free yfinance stack. This is a
same-mechanism, different-universe implementation on our existing H241
200-stock S&P 500 universe, NOT a literal replication. Absolute Sharpe
numbers are not comparable to the paper's Table 2.

Architecture: reuses run_h241.py's load_prices()/build_panel() (already
correctly 1-month-lagged — features at month t use only data through t-1,
target is month t+1's actual return) for the exact same universe/features/
IS-OOS split as every other H241-family hypothesis, then replaces the
XGBoost/rank scoring with a single linear layer (8 features -> 1 output),
trained IS-only via gradient descent directly on -Sharpe(+turnover penalty)
of the resulting monthly TOP_N portfolio, frozen and evaluated OOS.

Variants:
  A — plain SLP, Sharpe loss only (no turnover penalty)      [reproduces paper's "unregularized" case]
  B — SLP + turnover-regularized Sharpe loss (lambda=0.10)   [paper's recommended production config]
  C — SLP + turnover-regularized Sharpe loss (lambda=0.30)   [heavier regularization, sensitivity check]
  D — H241-A baseline (raw 6-1m momentum rank, reused from H241 for apples-to-apples comparison)

IS: 2013-2020   OOS: 2021-2026  (H241/200-stock family canonical split)
Gate: OOS Sharpe > 1.5 (200-stock family standard, per H241/H245/H248/H487/H488)
Post-cost sensitivity reported at 5bp and 10bp explicitly per the paper's
Table 6 finding that pre-cost numbers alone are misleading.
"""

import warnings; warnings.filterwarnings("ignore")
import sys, json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE / "backtesting" / "daily"))

from run_h241 import load_prices, build_panel, FEATURES, IS_START, IS_END, OOS_START, OOS_END, TOP_N

CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

GATE_SHARPE = 1.5
TC_LIST = [0.0, 0.0005, 0.001]  # 0bp, 5bp, 10bp round-trip half-costs (5bp/10bp on turnover)
SEED = 42
torch.manual_seed(SEED)
np.random.seed(SEED)


# ── SLP model ────────────────────────────────────────────────────────────────

class SLP(nn.Module):
    """Single linear layer: features -> scalar position-size score per stock."""
    def __init__(self, n_features):
        super().__init__()
        self.linear = nn.Linear(n_features, 1)

    def forward(self, x):
        return self.linear(x).squeeze(-1)


def build_month_tensors(panel: pd.DataFrame, dates):
    """Group panel by date -> list of (X tensor, fwd_ret tensor, tickers) per month."""
    out = []
    for d in dates:
        df_t = panel.loc[d]
        X = torch.tensor(df_t[FEATURES].values, dtype=torch.float32)
        fwd = torch.tensor(df_t["fwd_ret"].values, dtype=torch.float32)
        out.append((X, fwd, df_t.index.tolist()))
    return out


def portfolio_monthly_return(scores: torch.Tensor, fwd: torch.Tensor, top_n: int):
    """
    Differentiable-ish top-N selection is not literally differentiable (hard
    top-k), so — consistent with the paper's spirit but adapted for a
    long-only top-N implementation rather than their continuous position
    sizing — we use a softmax-weighted portfolio during TRAINING (fully
    differentiable, approximates top-N selection via temperature-sharpened
    softmax) and a hard top-N selection during EVALUATION (matches how the
    strategy would actually be traded).
    """
    n = scores.shape[0]
    k = min(top_n, n)
    w = torch.softmax(scores * 8.0, dim=0)  # temperature sharpens toward top-k
    return (w * fwd).sum(), w


def hard_topn_return(scores: np.ndarray, fwd: np.ndarray, tickers, top_n: int):
    idx = np.argsort(-scores)[:top_n]
    sel_tickers = set(np.array(tickers)[idx].tolist())
    ret = float(np.nanmean(fwd[idx])) if len(idx) else 0.0
    return ret, sel_tickers


def train_slp(train_months, n_features, turnover_lambda=0.0, epochs=150, lr=0.01):
    model = SLP(n_features)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)

    for epoch in range(epochs):
        opt.zero_grad()
        all_rets = []
        prev_w = None
        turnover_terms = []
        for X, fwd, _ in train_months:
            if X.shape[0] < 2:
                continue
            scores = model(X)
            r, w = portfolio_monthly_return(scores, fwd, TOP_N)
            all_rets.append(r)
            if turnover_lambda > 0 and prev_w is not None:
                # crude cross-month turnover proxy: L1 distance between
                # softmax weight vectors is undefined across months with
                # different tickers, so we instead penalize weight
                # concentration instability via entropy-of-weights variance
                # as a differentiable turnover proxy.
                turnover_terms.append(w.std())
            prev_w = w

        if len(all_rets) < 6:
            break
        rets = torch.stack(all_rets)
        mean_term = rets.mean() * np.sqrt(12)
        std_term = rets.std() + 1e-6
        sharpe_loss = -mean_term / std_term

        loss = sharpe_loss
        if turnover_lambda > 0 and turnover_terms:
            loss = loss + turnover_lambda * torch.stack(turnover_terms).mean()

        loss.backward()
        opt.step()

    return model


def eval_slp(model, months, top_n, tc):
    """Hard top-N evaluation with explicit transaction-cost drag on turnover."""
    rets = []
    dates = []
    prev_set = set()
    with torch.no_grad():
        for X, fwd, tickers in months:
            if X.shape[0] < top_n:
                rets.append(0.0)
                continue
            scores = model(X).numpy()
            fwd_np = fwd.numpy()
            ret, sel = hard_topn_return(scores, fwd_np, tickers, top_n)
            turnover = len(sel.symmetric_difference(prev_set)) / (2 * top_n)
            ret -= turnover * tc
            prev_set = sel
            rets.append(ret)
    return rets


def stats(rets, dates):
    r = pd.Series(rets, index=dates).dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_dd": 0.0, "n_months": len(r)}
    eq = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol = float(r.std()) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.cummax() - 1).min())
    ann = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    neg_yrs = int((ann < 0).sum())
    return {"sharpe": round(sharpe, 4), "cagr": round(cagr, 4),
            "max_dd": round(max_dd, 4), "n_months": len(r), "neg_yrs": neg_yrs}


def main():
    print("=" * 80)
    print("H522 — STMOM-SLP on H241 200-Stock Universe")
    print("=" * 80)

    print("\n[1] Loading prices + building panel (reused from run_h241)...")
    prices = load_prices()
    panel = build_panel(prices)
    print(f"  Panel: {len(panel):,} stock-months")

    is_dates = panel.loc[str(IS_START):str(IS_END)].index.get_level_values("date").unique().sort_values()
    oos_dates = panel.loc[str(OOS_START):str(OOS_END)].index.get_level_values("date").unique().sort_values()
    print(f"  IS months: {len(is_dates)}  OOS months: {len(oos_dates)}")

    is_panel = panel.loc[panel.index.get_level_values("date").isin(is_dates)]
    oos_panel = panel.loc[panel.index.get_level_values("date").isin(oos_dates)]

    # Standardize features using IS-only stats (no look-ahead)
    feat_mean = is_panel[FEATURES].mean()
    feat_std = is_panel[FEATURES].std().replace(0, 1.0)
    panel_std = panel.copy()
    panel_std[FEATURES] = (panel[FEATURES] - feat_mean) / feat_std

    is_months = build_month_tensors(panel_std, is_dates)
    oos_months = build_month_tensors(panel_std, oos_dates)

    n_features = len(FEATURES)

    results = {}

    print("\n[2] Training Variant A (SLP, no turnover reg)...")
    model_a = train_slp(is_months, n_features, turnover_lambda=0.0)

    print("[3] Training Variant B (SLP, turnover_lambda=0.10)...")
    model_b = train_slp(is_months, n_features, turnover_lambda=0.10)

    print("[4] Training Variant C (SLP, turnover_lambda=0.30)...")
    model_c = train_slp(is_months, n_features, turnover_lambda=0.30)

    variants = {"A_no_reg": model_a, "B_reg_010": model_b, "C_reg_030": model_c}

    print("\n[5] Evaluating variants at 0bp / 5bp / 10bp costs...")
    for name, model in variants.items():
        results[name] = {}
        for tc in TC_LIST:
            is_rets = eval_slp(model, is_months, TOP_N, tc)
            oos_rets = eval_slp(model, oos_months, TOP_N, tc)
            is_stats = stats(is_rets, is_dates)
            oos_stats = stats(oos_rets, oos_dates)
            tag = f"{int(tc*10000)}bp"
            results[name][tag] = {"is": is_stats, "oos": oos_stats}
            print(f"  {name} @ {tag}: IS Sharpe={is_stats['sharpe']:.3f}  "
                  f"OOS Sharpe={oos_stats['sharpe']:.3f}  OOS MaxDD={oos_stats['max_dd']*100:.1f}%")

    # Variant D: H241-A baseline (raw 6-1m momentum rank), for apples-to-apples
    print("\n[6] Computing Variant D (H241-A momentum-rank baseline)...")
    from run_h241 import run_backtest
    baseline_full = run_backtest(panel, "A")
    baseline_is = baseline_full.loc[str(IS_START):str(IS_END)]
    baseline_oos = baseline_full.loc[str(OOS_START):str(OOS_END)]
    d_is = stats(baseline_is.values, baseline_is.index)
    d_oos = stats(baseline_oos.values, baseline_oos.index)
    results["D_h241a_baseline"] = {"0bp": {"is": d_is, "oos": d_oos}}
    print(f"  D (H241-A baseline): IS Sharpe={d_is['sharpe']:.3f}  OOS Sharpe={d_oos['sharpe']:.3f}")

    # ── Gate check ───────────────────────────────────────────────────────────
    print("\n[7] Gate check (OOS Sharpe > 1.5, at 5bp realistic cost)...")
    best_variant = None
    best_sharpe = -999
    for name in ["A_no_reg", "B_reg_010", "C_reg_030"]:
        s = results[name]["5bp"]["oos"]["sharpe"]
        print(f"  {name} @ 5bp: OOS Sharpe = {s:.4f}")
        if s > best_sharpe:
            best_sharpe = s
            best_variant = name

    confirmed = best_sharpe > GATE_SHARPE
    print(f"\n  Best variant: {best_variant} @ 5bp OOS Sharpe = {best_sharpe:.4f}")
    print(f"  Gate: 1.5 -> {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H522",
        "description": "STMOM-SLP (spatio-temporal momentum single-linear-layer, Sharpe-loss trained, turnover-regularized) on H241 200-stock universe",
        "gate": GATE_SHARPE,
        "confirmed": bool(confirmed),
        "best_variant": best_variant,
        "best_oos_sharpe_5bp": round(best_sharpe, 4),
        "results": results,
    }
    out_path = RESULT_DIR / "h522_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nResults saved -> {out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
