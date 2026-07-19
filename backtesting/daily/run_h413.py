"""
H413 — BAB × Lagged Realized Volatility Regime Gate
======================================================
Source: Barroso, Detzel & Maio (2025). 'The Volatility Puzzle of the Beta Anomaly.'
  Journal of Financial Economics, Vol. 165. SSRN 3882108.

Key finding: BAB Sharpe ratios rise AFTER low-volatility months. After high-vol months,
institutional investors shift from high-beta to low-beta, crowding the BAB trade and
depleting forward alpha. Gate: hold BAB only when last month's realized SPY vol was
below the rolling median → route to BIL (cash proxy) otherwise.

Base: H192-D sector-neutral BAB on H198 30-stock NASDAQ large-cap universe.
Gate threshold: OOS Sharpe > 1.5 (vs H192-D baseline OOS ~1.367)

Variants:
  A: vol_gate_21d  — trailing 21d SPY vol (annualized) < expanding median
  B: vol_gate_63d  — trailing 63d SPY vol (annualized) < expanding median
  C: vol_gate_21d + SPY > 200d MA (both conditions)
  D: vol_21d_pct < 40th percentile (stricter than median gate)

IS: 2013-2020  OOS: 2021-2026  Universe: H198 30-stock NASDAQ large-cap
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

UNIVERSE_SECTORS = {
    "AAPL": "IT",   "MSFT": "IT",   "NVDA": "IT",   "AVGO": "IT",
    "QCOM": "IT",   "AMD":  "IT",   "IBM":  "IT",
    "AMZN": "CD",   "TSLA": "CD",   "HD":   "CD",   "SBUX": "CD",   "LOW":  "CD",
    "GOOGL":"CS",   "META": "CS",
    "V":    "FIN",  "MA":   "FIN",  "BAC":  "FIN",  "WFC":  "FIN",  "JPM":  "FIN",
    "UNH":  "HC",   "LLY":  "HC",   "PFE":  "HC",   "JNJ":  "HC",   "ABBV": "HC",
    "WMT":  "STAP", "COST": "STAP",
    "CVX":  "EN",   "XOM":  "EN",
    "BA":   "IND",  "CAT":  "IND",
}
UNIVERSE = list(UNIVERSE_SECTORS.keys())
SPY      = "SPY"
BIL_RATE = 0.0005  # ≈ 0.06% monthly for BIL (cash proxy)

DATA_START  = "2011-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 1.5
N_LONG      = 6


def load_daily() -> tuple[pd.DataFrame, pd.Series]:
    cache = CACHE_DIR / f"h413_daily_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        print("  Downloading daily prices…")
        raw = yf.download(UNIVERSE + [SPY], start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        df.to_parquet(cache)
    spy_px = df[SPY].copy()
    stock_px = df[[t for t in UNIVERSE if t in df.columns]].copy()
    return stock_px, spy_px


def rolling_beta(stock_rets: pd.Series, spy_rets: pd.Series, window: int = 252) -> float:
    x = spy_rets.tail(window).values
    y = stock_rets.tail(window).values
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < window // 3:
        return np.nan
    xm, ym = x[mask].mean(), y[mask].mean()
    cov = np.mean((x[mask] - xm) * (y[mask] - ym))
    var = np.mean((x[mask] - xm) ** 2)
    return cov / var if var > 1e-10 else np.nan


def compute_bab_d_monthly(stock_px: pd.DataFrame, spy_px: pd.Series) -> pd.Series:
    """H192-D sector-neutral BAB: rank beta within sector, long bottom-6."""
    monthly_px  = stock_px.resample("ME").last()
    daily_rets  = stock_px.pct_change()
    spy_daily   = spy_px.pct_change()
    month_ends  = monthly_px.index

    rets, dates = [], []
    for i, hold_date in enumerate(month_ends[1:], 1):
        rebal_date = month_ends[i - 1]

        hist_rets  = daily_rets[daily_rets.index <= rebal_date]
        spy_hist   = spy_daily[spy_daily.index <= rebal_date]
        if len(hist_rets) < 130:
            continue

        spy_ser = spy_hist.tail(252)
        betas = {t: rolling_beta(hist_rets[t], spy_ser, 252)
                 for t in stock_px.columns if t in hist_rets.columns}
        betas = {t: b for t, b in betas.items() if pd.notna(b)}

        if len(betas) < N_LONG * 2:
            continue

        beta_s = pd.Series(betas)
        sectors = pd.Series(UNIVERSE_SECTORS)
        common = beta_s.index.intersection(sectors.index)
        df_tmp = pd.DataFrame({"beta": beta_s[common], "sector": sectors[common]})
        df_tmp["rank"] = df_tmp.groupby("sector")["beta"].rank(ascending=True)
        signal = df_tmp["rank"]

        long_tickers = signal.nsmallest(N_LONG).index.tolist()
        month_rets = []
        for t in long_tickers:
            p1 = monthly_px.iloc[i - 1].get(t, np.nan)
            p2 = monthly_px.iloc[i].get(t, np.nan)
            if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                month_rets.append((p2 - p1) / p1)
        if month_rets:
            rets.append(np.mean(month_rets))
            dates.append(hold_date)

    return pd.Series(rets, index=dates, name="bab_d")


def compute_vol_gate(spy_px: pd.Series) -> pd.DataFrame:
    """Compute lagged vol gates for each variant (monthly, lag=1 month)."""
    spy_ret = spy_px.pct_change()

    # Trailing annualized realized vol
    vol_21d = spy_ret.rolling(21).std() * np.sqrt(252)
    vol_63d = spy_ret.rolling(63).std() * np.sqrt(252)

    # Sample at month-end
    vol_21_m = vol_21d.resample("ME").last()
    vol_63_m = vol_63d.resample("ME").last()

    # SPY 200d MA flag at month-end
    ma200    = spy_px.rolling(200).mean()
    spy_abv  = (spy_px > ma200).resample("ME").last().astype(float)

    gates = pd.DataFrame(index=vol_21_m.index)
    gates["vol21"] = vol_21_m
    gates["vol63"] = vol_63_m
    gates["spy_abv_200"] = spy_abv.reindex(gates.index, method="ffill")

    # Expanding median (computed on vol known up to each month)
    # Shift by 1: gate[t] uses vol[t-1] to avoid look-ahead
    vol21_lagged = gates["vol21"].shift(1)
    vol63_lagged = gates["vol63"].shift(1)

    # Expanding median up to (but not including) current month
    exp_med_21 = vol21_lagged.expanding().median()
    exp_med_63 = vol63_lagged.expanding().median()
    exp_pct40_21 = vol21_lagged.expanding().quantile(0.40)

    gates["gate_A"] = (vol21_lagged < exp_med_21).astype(float)
    gates["gate_B"] = (vol63_lagged < exp_med_63).astype(float)
    gates["gate_C"] = ((vol21_lagged < exp_med_21) & (gates["spy_abv_200"].shift(1) > 0)).astype(float)
    gates["gate_D"] = (vol21_lagged < exp_pct40_21).astype(float)

    return gates


def sharpe(r):
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_years(r):
    return int((r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum())

def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0, "cash_pct": 0.0, "n": 0}
    return {
        "sharpe": round(sharpe(r), 3),
        "maxdd": round(maxdd(r), 3),
        "cagr": round(float(r.mean() * 12), 3),
        "neg_yrs": neg_years(r),
        "n": len(r),
    }


def apply_gate(bab_rets: pd.Series, gate: pd.Series, gate_col: str) -> tuple[pd.Series, float]:
    """Apply gate: hold BAB when gate=1, else BIL (BIL_RATE)."""
    gate_aligned = gate[gate_col].reindex(bab_rets.index, method="ffill")
    gated = np.where(gate_aligned.fillna(0) > 0.5, bab_rets.values, BIL_RATE)
    cash_pct = float((gate_aligned.fillna(0) < 0.5).mean())
    return pd.Series(gated, index=bab_rets.index), cash_pct


def main():
    print("H413 — BAB × Lagged Realized Volatility Regime Gate")
    print("=" * 70)
    print(f"Source: Barroso, Detzel & Maio (2025) JFE Vol. 165")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (vs H192-D baseline ~1.367)")

    print("\nLoading daily prices…")
    stock_px, spy_px = load_daily()
    print(f"  {stock_px.shape[1]} stocks, {len(stock_px)} daily obs")

    print("Computing H192-D sector-neutral BAB monthly returns…")
    bab_rets = compute_bab_d_monthly(stock_px, spy_px)
    bab_rets = bab_rets[bab_rets.index >= IS_START]
    print(f"  {len(bab_rets)} monthly BAB return observations")

    bab_baseline_is  = eval_period(bab_rets, IS_START, IS_END)
    bab_baseline_oos = eval_period(bab_rets, OOS_START, OOS_END)
    print(f"  Baseline (no gate): IS Sharpe={bab_baseline_is['sharpe']:.3f}  "
          f"OOS Sharpe={bab_baseline_oos['sharpe']:.3f}  "
          f"OOS MaxDD={bab_baseline_oos['maxdd']:.1%}")

    print("\nComputing vol gates…")
    gates = compute_vol_gate(spy_px)
    gates = gates.reindex(bab_rets.index, method="ffill")
    for col in ["gate_A", "gate_B", "gate_C", "gate_D"]:
        pct = gates[col].fillna(0).mean()
        print(f"  {col}: {pct:.1%} of months pass gate (gate=1)")

    variant_specs = [
        ("A", "gate_A", "21d vol < expanding median (lagged)"),
        ("B", "gate_B", "63d vol < expanding median (lagged)"),
        ("C", "gate_C", "21d vol < median AND SPY > 200d MA"),
        ("D", "gate_D", "21d vol < 40th pct (stricter threshold)"),
    ]

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'MaxDD':>8} {'CAGR%':>7} {'NegY':>5} {'Cash%':>7}  Desc")
    print("-" * 105)

    results = {}
    confirmed = []

    for v, gate_col, desc in variant_specs:
        gated_rets, cash_pct = apply_gate(bab_rets, gates, gate_col)
        vi = eval_period(gated_rets, IS_START, IS_END)
        vo = eval_period(gated_rets, OOS_START, OOS_END)
        oos_cash = float((gates[gate_col].reindex(
            gated_rets[(gated_rets.index >= OOS_START) & (gated_rets.index <= OOS_END)].index,
            method="ffill").fillna(0) < 0.5).mean())
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓" if beat else ""
        print(f"Var {v}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>8.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d} {oos_cash:>7.1%}  {desc}{flag}")
        results[f"var_{v}"] = {
            "is": vi, "oos": vo, "oos_cash_pct": round(oos_cash, 3),
            "desc": desc, "beats_gate": beat
        }
        if beat:
            confirmed.append(v)

    # Baseline (no gate) for reference
    print(f"Base   {bab_baseline_is['sharpe']:>7.3f} {bab_baseline_oos['sharpe']:>8.3f} "
          f"{bab_baseline_oos['maxdd']:>8.1%} "
          f"{bab_baseline_oos['cagr']*100:>6.1f}% {bab_baseline_oos['neg_yrs']:>5d}   0.0%"
          "  H192-D no gate [reference]")

    # OOS annual for best variant
    if confirmed:
        best_v = max(confirmed, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        gated_best, _ = apply_gate(bab_rets, gates, f"gate_{best_v}")
        print(f"\n=== Var {best_v} OOS annual returns ===")
        oos_series = gated_best[(gated_best.index >= OOS_START) & (gated_best.index <= OOS_END)]
        ann = oos_series.resample("YE").apply(lambda x: (1+x).prod()-1)
        for yr, ret in ann.items():
            print(f"  {yr.year}: {ret:+.1%}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    if confirmed:
        best_c = max(confirmed, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        print(f"CONFIRMED — variants: {', '.join(confirmed)}")
        print(f"Champion: Var {best_c}  OOS {results[f'var_{best_c}']['oos']['sharpe']:.3f}")
    else:
        best_v = max(results, key=lambda v: results[v]["oos"]["sharpe"])
        print(f"NOT CONFIRMED — best {best_v}  OOS {results[best_v]['oos']['sharpe']:.3f}")

    out = {
        "hypothesis": "H413",
        "gate": GATE_SHARPE,
        "baseline_oos_sharpe": bab_baseline_oos["sharpe"],
        "confirmed": bool(confirmed),
        "confirmed_variants": confirmed,
        "results": results,
    }
    op = RESULT_DIR / "h413_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
