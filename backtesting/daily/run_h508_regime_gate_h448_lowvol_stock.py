#!/usr/bin/env python3
"""
H508 — Macro Regime Gate on H448 Stock-Level Low-Volatility Anomaly
=======================================================================
H448 (2026-07-25, NOT CONFIRMED) tested pure realized-vol low-vol selection
on the H198 30-stock large-cap NASDAQ universe. Best variant (B, 60d vol,
bottom-6) reached OOS Sharpe 1.028-1.045, just short of the 1.174 gate.
H507 (this session) just showed the SMC Order Block filter does NOT rescue
it — filtering hurts (best OB variant OOS 0.908, worse than the 1.028
unfiltered baseline).

H362 (2026-07-03, CONFIRMED) showed a DIFFERENT filter — a macro regime gate
(VIX<20 and/or SPY>200MA, route to cash otherwise) — took H354's marginal ETF
low-vol rotation from OOS 1.339 to OOS 1.819/2.173 (H364 stacked). That
mechanism (avoid the strategy entirely during high-vol/bear regimes, since
low-vol assets still correlate with SPY in a crash) has never been tested on
H448's STOCK-level low-vol signal — only on the ETF-level one. This is the
genuinely open angle: same regime-gate recipe, same low-vol-anomaly family,
different (stock vs ETF) selection universe.

LOOK-AHEAD BIAS DISCIPLINE (per H506 audit):
  - vol_rank signal is shifted 1 month exactly as H448/H507 (verified — see
    compute_vol_rank(), identical to H507's).
  - The regime gate (VIX, SPY 200MA) is evaluated using the PRIOR month-end's
    close, not the current month_end's close — same "prior month-end as-of"
    discipline as H507/H484-corrected. A month M gate decision must be
    knowable before month M's return is realized.

Method: at each month-end, if the gate condition (evaluated on prior
month-end data) is true, hold H448 Var B's bottom-6-by-60d-vol picks;
otherwise hold cash (BIL proxy, 0% return approximation, consistent with
H362's convention).

Universe: H198/H448 30-stock large-cap NASDAQ-heavy universe + SPY + ^VIX
IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 canonical baseline, same as H448/H507)
      AND MaxDD improvement >= 0.5pp vs H448 Var B OOS MaxDD (-24.0% log
      reference, -25.9% this session's baseline replication per H507)
"""

import warnings
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]

DATA_START = "2011-01-01"
DATA_END   = "2026-07-21"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-07-21")

GATE_SHARPE      = 1.174
H448_B_OOS_MAXDD = -0.259   # this session's H507 baseline replication of H448 Var B
VOL_WINDOW       = 60
TOP_N            = 6


def load_prices():
    cp = CACHE_DIR / f"h507_universe_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    df = df.dropna(how="all", axis=0)
    df.to_parquet(cp)
    return df


def load_spy():
    cp = CACHE_DIR / f"h508_SPY_close_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename("SPY")
    raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    close = raw["Close"] if "Close" in raw.columns else raw.squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.rename("SPY")
    close.to_frame().to_parquet(cp)
    return close


def load_vix():
    cp = CACHE_DIR / f"h508_VIX_close_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename("VIX")
    print("  Downloading ^VIX...")
    raw = yf.download("^VIX", start=DATA_START, end=DATA_END, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("^VIX", axis=1, level=1)
    close = raw["Close"] if "Close" in raw.columns else raw.squeeze()
    close = close.rename("VIX")
    close.to_frame().to_parquet(cp)
    return close


def compute_vol_rank(daily_px: pd.DataFrame) -> pd.DataFrame:
    daily_rets = daily_px.pct_change()
    vol60 = daily_rets.rolling(VOL_WINDOW).std() * np.sqrt(252)
    monthly_vol = vol60.resample("ME").last().shift(1)
    return monthly_vol


def sharpe(r):
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_years(r):
    return int((r.resample("YE").apply(lambda x: (1 + x).prod() - 1) < 0).sum())

def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {"n": len(r), "sharpe": round(sharpe(r), 3),
            "maxdd": round(maxdd(r), 3), "cagr": round(float(r.mean() * 12), 3),
            "neg_yrs": neg_years(r)}


def backtest(monthly_px, vol_rank, gate_fn, spy_monthly, vix_monthly):
    """gate_fn(prior_month_end) -> bool. If True, trade; else hold cash."""
    monthly_ret = monthly_px.pct_change()
    month_ends = list(vol_rank.index)
    port_rets = []
    for i, month_end in enumerate(month_ends):
        if month_end not in monthly_ret.index or i == 0:
            continue
        prior = month_ends[i - 1]
        scores = vol_rank.loc[month_end].dropna()
        if len(scores) < TOP_N:
            port_rets.append((month_end, 0.0))
            continue
        selected = scores.nsmallest(TOP_N).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        raw_ret = float(monthly_ret.iloc[loc][selected].mean())

        gate_ok = gate_fn(prior, spy_monthly, vix_monthly)
        port_rets.append((month_end, raw_ret if gate_ok else 0.0))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def gate_spy200ma(prior, spy_monthly, vix_monthly):
    if prior not in spy_monthly.index:
        return True
    row = spy_monthly.loc[prior]
    return bool(row["close"] > row["ma200"]) if pd.notna(row.get("ma200")) else True

def gate_vix20(prior, spy_monthly, vix_monthly):
    if prior not in vix_monthly.index or pd.isna(vix_monthly.loc[prior]):
        return True
    return bool(vix_monthly.loc[prior] < 20)

def gate_joint_and(prior, spy_monthly, vix_monthly):
    return gate_spy200ma(prior, spy_monthly, vix_monthly) and (
        vix_monthly.loc[prior] < 25 if prior in vix_monthly.index and pd.notna(vix_monthly.loc[prior]) else True)

def gate_either_or(prior, spy_monthly, vix_monthly):
    return gate_spy200ma(prior, spy_monthly, vix_monthly) or gate_vix20(prior, spy_monthly, vix_monthly)

def gate_none(prior, spy_monthly, vix_monthly):
    return True


def main():
    print("H508 — Macro Regime Gate on H448 Stock-Level Low-Volatility Anomaly")
    print("=" * 74)

    print("\nLoading prices...")
    daily_px = load_prices()
    spy_close = load_spy()
    vix_close = load_vix()
    print(f"  {daily_px.shape[1]} tickers, {len(daily_px)} daily obs")

    print("Computing 60d realized-vol ranks (shifted 1 month)...")
    vol_rank = compute_vol_rank(daily_px)
    monthly_px = daily_px.resample("ME").last()

    # SPY monthly close + 200d MA (computed on daily then resampled)
    spy_ma200 = spy_close.rolling(200).mean()
    spy_monthly = pd.DataFrame({
        "close": spy_close.resample("ME").last(),
        "ma200": spy_ma200.resample("ME").last(),
    })
    vix_monthly = vix_close.resample("ME").last()

    variants = {
        "A_SPY200MA":  gate_spy200ma,
        "B_VIXlt20":   gate_vix20,
        "C_JOINT_AND": gate_joint_and,
        "D_EITHER_OR": gate_either_or,
        "E_NOGATE":    gate_none,
    }

    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND MaxDD improvement >= 0.5pp vs {H448_B_OOS_MAXDD:.1%}")
    print(f"\n{'Variant':<14} {'IS Sh':>8} {'OOS Sh':>8} {'MaxDD':>8} {'MDDimp(pp)':>11} {'Cash%':>7} {'Beat?':>6}")
    print("-" * 70)

    results = {}
    for name, gate_fn in variants.items():
        rets = backtest(monthly_px, vol_rank, gate_fn, spy_monthly, vix_monthly)
        is_ = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        oos_rets = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        cash_pct = (oos_rets == 0).sum() / max(len(oos_rets), 1) * 100
        mdd_improvement_pp = (oos_["maxdd"] - H448_B_OOS_MAXDD) * 100
        beats_sharpe = oos_["sharpe"] > GATE_SHARPE
        beats_mdd = mdd_improvement_pp >= 0.5
        beats_both = beats_sharpe and beats_mdd
        print(f"{name:<14} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
              f"{oos_['maxdd']:>8.1%} {mdd_improvement_pp:>10.2f}pp {cash_pct:>6.1f}% "
              f"{'YES' if beats_both else 'no':>6}")
        results[name] = {
            "is": is_, "oos": oos_, "oos_cash_pct": round(cash_pct, 1),
            "mdd_improvement_pp": round(mdd_improvement_pp, 2),
            "beats_sharpe_gate": beats_sharpe, "beats_mdd_gate": beats_mdd,
            "beats_both_gates": beats_both,
        }

    n_pass = sum(v["beats_both_gates"] for v in results.values())
    best_name = max(results, key=lambda k: results[k]["oos"]["sharpe"])
    best = results[best_name]
    print(f"\n=== Summary ===")
    print(f"Baseline (E_NOGATE, H448 Var B replication): OOS Sharpe {results['E_NOGATE']['oos']['sharpe']:.3f}, "
          f"MaxDD {results['E_NOGATE']['oos']['maxdd']:.1%}")
    print(f"Variants passing BOTH gates: {n_pass}/{len(variants) - 1}")  # exclude baseline E from denominator
    print(f"Best OOS Sharpe: {best['oos']['sharpe']:.3f} ({best_name}), "
          f"MaxDD={best['oos']['maxdd']:.1%}, cash%={best['oos_cash_pct']:.1f}")

    if n_pass > 0:
        print(f"\nVERDICT: CONFIRMED — {n_pass} variant(s) beat both the Sharpe and MaxDD gates.")
    else:
        gated_only = {k: v for k, v in results.items() if k != "E_NOGATE"}
        best_gated_name = max(gated_only, key=lambda k: gated_only[k]["oos"]["sharpe"])
        best_gated = gated_only[best_gated_name]
        if best_gated["beats_sharpe_gate"]:
            print(f"\nVERDICT: PARTIAL CONFIRMED — {best_gated_name} beats Sharpe gate but MaxDD "
                  f"improvement insufficient ({best_gated['mdd_improvement_pp']:.2f}pp < 0.5pp).")
        else:
            print(f"\nVERDICT: NOT CONFIRMED — no gated variant beats OOS Sharpe {GATE_SHARPE} "
                  f"(best {best_gated_name} {best_gated['oos']['sharpe']:.3f}).")

    out = {
        "hypothesis": "H508",
        "description": "Macro regime gate (VIX/SPY-200MA) on H448 Var B stock-level low-vol (60d vol, bottom-6)",
        "gate_sharpe": GATE_SHARPE,
        "gate_mdd_improvement_pp": 0.5,
        "variants": results,
        "n_pass_both_gates": n_pass,
    }
    outpath = RESULT_DIR / "h508_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")
    return out


if __name__ == "__main__":
    main()
