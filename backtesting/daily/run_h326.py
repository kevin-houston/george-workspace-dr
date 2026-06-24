"""
H326 — Continuous Tanh-Gated H026/H041a/H045 Strategy Blend
=============================================================
Source: arXiv:2605.20636 (2026) "Continuous Timing Signals for
        Growth-Defensive Style Allocation"

Hypothesis:
  Replace H318's discrete regime switches with differentiable tanh/softplus
  scoring.  Four continuous signals blend H026/H041a/H045 weights smoothly
  between bear_w and bull_w, avoiding the sharp threshold discontinuities
  that caused H318's regime-switch variant D to clip just below the gate
  (Sharpe +0.08 vs static B, but MaxDD 0.1 pp worse).

  Four signals:
    rate_relief    = tanh(-delta_TNX_3m / 1.0)   # +1 rates falling, -1 rising
    equity_stress  = tanh(-SPY_drawdown / 0.10)  # +1 near highs, -1 down >10%
    vix_relief     = tanh((20 - VIX) / 5.0)      # +1 VIX<20, -1 VIX>30
    growth_crowding= tanh(-(SPY_12m - 0.15)/0.10) # penalise stretched equity

  Composite score = mean(signals), range [-1, +1]

  Allocation:
    bull_w = [H026=0.50, H041a=0.35, H045=0.15]
    base_w = [H026=0.40, H041a=0.30, H045=0.30]   (H318 static B)
    bear_w = [H026=0.20, H041a=0.15, H045=0.65]

    pos = max(score, 0)
    neg = max(-score, 0)
    w_i = bear_w_i * neg + base_w_i * (1-pos-neg) + bull_w_i * pos
    (linear interpolation from base toward bull or bear)

IS:  2010-01-01 – 2017-12-31
OOS: 2018-01-01 – 2026-06-20
Gate: OOS Sharpe > 2.501 (H318 static B) AND MaxDD ≥ -4.3%
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2008-01-01"
FULL_END   = "2026-06-20"
IS_START   = "2010-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

H026_ASSETS  = [
    "SPY","QQQ","IWM","EFA","EEM",
    "XLK","XLF","XLE","XLV","XLI","XLP","XLY","XLU","XLRE","XLC",
    "GLD","SLV","USO","UNG",
    "TLT","IEF","HYG","LQD","BIL","VNQ",
]
H041A_ASSETS = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM"]
H045_ASSETS  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD"]
H026_TOP_N   = 1
H041A_TOP_N  = 2
H045_TOP_N   = 2

ALL_TICKERS = sorted(set(H026_ASSETS + H041A_ASSETS + H045_ASSETS + ["^VIX","^TNX"]))

BULL_W = {"H026": 0.50, "H041a": 0.35, "H045": 0.15}
BASE_W = {"H026": 0.40, "H041a": 0.30, "H045": 0.30}
BEAR_W = {"H026": 0.20, "H041a": 0.15, "H045": 0.65}

STATIC_B_SHARPE = 2.501
STATIC_B_MDD    = -0.043   # -4.3%


# ── Data helpers ─────────────────────────────────────────────────────────────

def fetch_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = CACHE_DIR / "h318_prices_main.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        missing = [t for t in tickers if t not in df.columns and not t.startswith("^")]
        if not missing:
            print("  Loaded price cache (H318 shared)")
            return df
    strat_tickers = [t for t in tickers if not t.startswith("^")]
    print(f"  Downloading {len(strat_tickers)} strategy tickers …")
    raw = yf.download(strat_tickers, start=start, end=end,
                      auto_adjust=True, progress=False, threads=True)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_series(ticker: str, start: str, end: str) -> pd.Series:
    cp = CACHE_DIR / f"h326_{ticker.replace('^','')}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    s = raw["Close"].squeeze().rename(ticker)
    pd.DataFrame(s).to_parquet(cp)
    return s


# ── Strategy engine (same as H318) ───────────────────────────────────────────

def compute_strategy_returns(prices: pd.DataFrame, universe: list,
                              top_n: int) -> pd.Series:
    avail = [t for t in universe if t in prices.columns]
    px    = prices[avail].copy().ffill()
    mpx   = px.resample("ME").last()
    mret  = mpx / mpx.shift(1) - 1
    mom12 = mpx / mpx.shift(12) - 1
    vol6  = mret.rolling(6).std() * np.sqrt(12)

    port_rets, port_idx = [], []
    for i in range(13, len(mpx)):
        signal_row = mom12.iloc[i].dropna()
        vol_row    = vol6.iloc[i].dropna()
        valid = signal_row.index.intersection(vol_row.index)
        if len(valid) < top_n:
            port_rets.append(np.nan)
        else:
            score = signal_row[valid].rank() + vol_row[valid].rank(ascending=False)
            picks = list(score.nlargest(top_n).index)
            port_rets.append((mret.iloc[i][picks] / len(picks)).sum())
        port_idx.append(mpx.index[i])

    return pd.Series(port_rets, index=port_idx, name="strategy_ret").dropna()


# ── Continuous scoring signals ────────────────────────────────────────────────

def build_tanh_scores(prices: pd.DataFrame, vix: pd.Series,
                      tnx: pd.Series) -> pd.DataFrame:
    """
    Build monthly tanh composite score [-1, +1] aligned to month-end.
    All signals lagged 1 month (use prior month's data to avoid lookahead).
    """
    spy = prices["SPY"].dropna() if "SPY" in prices.columns else pd.Series(dtype=float)

    # Monthly resample (month-end)
    spy_m   = spy.resample("ME").last()
    vix_m   = vix.resample("ME").last()
    tnx_m   = tnx.resample("ME").last()

    # Signal 1: rate_relief = tanh(-delta_TNX_3m / 1.0)
    delta_tnx  = tnx_m.diff(3)           # 3-month change in 10Y yield
    rate_relief = np.tanh(-delta_tnx / 1.0)

    # Signal 2: equity_stress = tanh(-SPY_drawdown / 0.10)
    spy_peak     = spy_m.expanding().max()
    spy_dd       = (spy_m / spy_peak - 1)
    equity_stress = np.tanh(-spy_dd / 0.10)

    # Signal 3: vix_relief = tanh((20 - VIX) / 5.0)
    vix_relief = np.tanh((20 - vix_m) / 5.0)

    # Signal 4: growth_crowding = tanh(-(SPY_12m - 0.15) / 0.10)
    spy_12m      = spy_m / spy_m.shift(12) - 1
    growth_crowd = np.tanh(-(spy_12m - 0.15) / 0.10)

    df = pd.DataFrame({
        "rate_relief":     rate_relief,
        "equity_stress":   equity_stress,
        "vix_relief":      vix_relief,
        "growth_crowding": growth_crowd,
    })
    df["composite"] = df.mean(axis=1)

    # Lag 1 month (use prior month's signal to avoid lookahead)
    df = df.shift(1)
    return df


def tanh_weights(score: float) -> dict:
    """
    Linearly interpolate between base and bull (score>0) or bear (score<0).
    score in [-1, +1].
    """
    pos = max(score, 0.0)
    neg = max(-score, 0.0)
    neutral = 1.0 - pos - neg
    w = {}
    for k in ("H026", "H041a", "H045"):
        w[k] = BEAR_W[k] * neg + BASE_W[k] * neutral + BULL_W[k] * pos
    return w


# ── Backtest engine ───────────────────────────────────────────────────────────

def calc_stats(rets: pd.Series, label: str = "") -> dict:
    rets = rets.dropna()
    if len(rets) < 6:
        return {"error": "too few months"}
    eq = (1 + rets).cumprod()
    n  = len(rets) / 12
    cagr   = eq.iloc[-1] ** (1 / n) - 1
    vol    = rets.std() * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0
    mdd    = (eq / eq.expanding().max() - 1).min()
    neg_yr = sum(1 for _, g in rets.groupby(rets.index.year)
                 if (1 + g).prod() - 1 < 0)
    wf = 0.0
    return {
        "label": label, "cagr": round(float(cagr), 4),
        "sharpe": round(float(sharpe), 4), "max_dd": round(float(mdd), 4),
        "ann_vol": round(float(vol), 4), "neg_years": neg_yr,
        "n_months": len(rets), "wf_ratio": round(wf, 3),
    }


def blend_tanh(strats: dict, scores: pd.DataFrame,
               start: str, end: str) -> pd.Series:
    """Tanh-gated blend: compute weighted return each month."""
    idx = strats["H026"].loc[start:end].index
    rets = []
    for dt in idx:
        sc = scores["composite"].asof(dt)
        if pd.isna(sc):
            # No signal yet → fall back to static B
            sc = 0.0
        w = tanh_weights(float(sc))
        r = sum(w[k] * (strats[k].get(dt, np.nan) if isinstance(strats[k], pd.Series)
                        else strats[k].loc[dt] if dt in strats[k].index else np.nan)
                for k in w)
        rets.append(r)
    return pd.Series(rets, index=idx, name="H326_tanh").dropna()


def blend_static(strats: dict, start: str, end: str,
                 w: dict = None) -> pd.Series:
    """Static blend for comparison."""
    if w is None:
        w = BASE_W
    idx = strats["H026"].loc[start:end].index
    rets = [sum(w[k] * strats[k].loc[dt] for k in w if dt in strats[k].index)
            for dt in idx]
    return pd.Series(rets, index=idx, name="static").dropna()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("H326 — Continuous Tanh-Gated H026/H041a/H045 Blend")
    print("=" * 62)

    # ── Download data ─────────────────────────────────────────────
    prices = fetch_prices(ALL_TICKERS, FULL_START, FULL_END)
    vix    = fetch_series("^VIX", FULL_START, FULL_END)
    tnx    = fetch_series("^TNX", FULL_START, FULL_END)

    # ── Compute sub-strategy returns ──────────────────────────────
    print("\nComputing sub-strategy returns …")
    r026  = compute_strategy_returns(prices, H026_ASSETS,  H026_TOP_N)
    r041a = compute_strategy_returns(prices, H041A_ASSETS, H041A_TOP_N)
    r045  = compute_strategy_returns(prices, H045_ASSETS,  H045_TOP_N)
    strats = {"H026": r026, "H041a": r041a, "H045": r045}

    # ── Build tanh score series ───────────────────────────────────
    print("Building tanh composite score …")
    scores = build_tanh_scores(prices, vix, tnx)

    # ── Backtests ─────────────────────────────────────────────────
    print("\nRunning backtests …\n")

    # IS diagnostics (not for gate, just informational)
    is_tanh   = blend_tanh(strats, scores, IS_START, IS_END)
    is_static = blend_static(strats, IS_START, IS_END)

    # OOS
    oos_tanh   = blend_tanh(strats, scores, OOS_START, FULL_END)
    oos_static = blend_static(strats, OOS_START, FULL_END)

    is_stat  = calc_stats(is_tanh,   "IS tanh-gated")
    is_bs    = calc_stats(is_static, "IS static B")
    oos_stat = calc_stats(oos_tanh,  "OOS tanh-gated")
    oos_bs   = calc_stats(oos_static,"OOS static B")

    # WF ratio
    is_sh  = is_stat.get("sharpe",  0)
    oos_sh = oos_stat.get("sharpe", 0)
    wf = round(oos_sh / is_sh, 3) if is_sh > 0 else 0.0
    oos_stat["wf_ratio"] = wf

    # Year-by-year OOS
    yoy = {}
    for yr, g in oos_tanh.groupby(oos_tanh.index.year):
        yoy[str(yr)] = round(float((1 + g).prod() - 1), 4)

    # Score distribution diagnostics
    oos_scores = scores.loc[OOS_START:FULL_END, "composite"].dropna()
    bull_pct = float((oos_scores > 0.3).mean())
    bear_pct = float((oos_scores < -0.3).mean())

    # ── Print results ─────────────────────────────────────────────
    print(f"{'Metric':<20} {'IS tanh':>12} {'IS static':>12} {'OOS tanh':>12} {'OOS static':>12}")
    print("-" * 68)
    for key in ("sharpe", "cagr", "max_dd", "ann_vol", "neg_years"):
        v_it = is_stat.get(key, "—")
        v_is = is_bs.get(key, "—")
        v_ot = oos_stat.get(key, "—")
        v_os = oos_bs.get(key, "—")
        fmt = lambda v: f"{v:>12.4f}" if isinstance(v, float) else f"{v:>12}"
        print(f"{key:<20}{fmt(v_it)}{fmt(v_is)}{fmt(v_ot)}{fmt(v_os)}")
    print(f"{'wf_ratio':<20}{'':>12}{'':>12}{wf:>12.3f}")
    print()
    print("OOS year-by-year (tanh):")
    for yr, r in yoy.items():
        print(f"  {yr}: {r*100:+.1f}%")
    print()
    print("OOS score distribution:")
    print(f"  Bull (>0.3): {bull_pct*100:.0f}%  "
          f"Bear (<-0.3): {bear_pct*100:.0f}%  "
          f"Neutral: {(1-bull_pct-bear_pct)*100:.0f}%")

    # ── Gate check ────────────────────────────────────────────────
    oos_sharpe = oos_stat.get("sharpe", 0)
    oos_mdd    = oos_stat.get("max_dd", -999)
    gate_sharpe = oos_sharpe > STATIC_B_SHARPE
    gate_mdd    = oos_mdd   >= STATIC_B_MDD
    confirmed   = gate_sharpe and gate_mdd
    print(f"\nGate check:")
    print(f"  Sharpe > {STATIC_B_SHARPE} → {oos_sharpe:.4f}  {'✓ PASS' if gate_sharpe else '✗ FAIL'}")
    print(f"  MaxDD  ≥ {STATIC_B_MDD}  → {oos_mdd:.4f}  {'✓ PASS' if gate_mdd else '✗ FAIL'}")
    print(f"\n  → H326 {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # ── Save results ──────────────────────────────────────────────
    results = {
        "hypothesis": "H326",
        "title": "Continuous Tanh-Gated H026/H041a/H045 Blend",
        "source": "arXiv:2605.20636",
        "is":  is_stat,
        "oos": oos_stat,
        "oos_static_b": oos_bs,
        "oos_yoy": yoy,
        "score_distribution": {
            "bull_pct": round(bull_pct, 3),
            "bear_pct": round(bear_pct, 3),
            "neutral_pct": round(1 - bull_pct - bear_pct, 3),
        },
        "gate": {"sharpe_pass": gate_sharpe, "mdd_pass": gate_mdd,
                 "confirmed": confirmed},
    }
    out = RESULT_DIR / "h326_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved → {out}")


if __name__ == "__main__":
    main()
