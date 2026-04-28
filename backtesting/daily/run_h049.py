"""
H049 — Formal IS/OOS Validation of H047 Four-Component Blend
=============================================================

H047 recommended blend: H041a 39.2% / H026 11.2% / H037b 19.6% / H045 30%
  → Full-period Sharpe 1.984, MaxDD -6.63% (2008-01 to 2026-04)

Concern: weights derived on 18-year window (limited by IEI). Is the blend overfit?

Validation design:
  IS  period: 2008-01 → 2017-12 (10 years)
  OOS period: 2018-01 → 2026-04 (8.3 years; includes 2022 rate shock)

Tests:
  1. IS-optimal weights (optimize on IS only via grid search)
  2. Apply IS-optimal weights → OOS Sharpe
  3. Apply operating weights (39.2/11.2/19.6/30) → OOS Sharpe
  4. OOS degradation % vs IS (compare to H042's 9.3%)
  5. 5-fold walk-forward on full 2008-2026 window
  6. 2022 isolation: what happened in Jan-Dec 2022?

Outputs:
  /workspace/agent/backtesting/results/h049_results.json
  /workspace/agent/backtesting/daily/run_h049.py  (this file)
"""

import json
import hashlib
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START    = "2000-01-01"
FULL_END      = "2026-04-27"

# IS / OOS split dates
IS_START  = "2008-01-01"
IS_END    = "2017-12-31"
OOS_START = "2018-01-01"
OOS_END   = "2026-04-27"

# Operating weights from H047 (grid best at H045=30%)
OP_W_H041A = 0.392
OP_W_H026  = 0.112
OP_W_H037B = 0.196
OP_W_H045  = 0.300

# Asset universes
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
SECTOR_ETFS  = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]
TREASURY_ETFS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]

TOP_N_H41A = 2
TOP_N_H26  = 3
TOP_N_H45  = 2

# H037b params
IBS_BUY      = 0.20
IBS_SELL     = 0.80
MAX_HOLD     = 5
GAP_FILTER_B = -0.005


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h049_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    cp = _cache_path(tickers, start, end, tag)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_spy_ohlc(start: str, end: str) -> pd.DataFrame:
    for fname in [
        f"h031_spy_ohlc_{start}_{end}.parquet",
        f"h042_spy_ohlc_{start}_{end}.parquet",
        f"h047_spy_ohlc_{start}_{end}.parquet",
    ]:
        cp = CACHE_DIR / fname
        if cp.exists():
            df = pd.read_parquet(cp)
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs("SPY", axis=1, level=1)
            cols = {c: c.lower() for c in df.columns}
            df = df.rename(columns=cols)
            if not all(c in df.columns for c in ["open", "high", "low", "close"]):
                df.columns = [c.lower() for c in df.columns]
            print(f"  Loaded SPY OHLC from cache ({len(df)} rows)")
            return df
    cp = CACHE_DIR / f"h049_spy_ohlc_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print("  Downloading SPY OHLC …")
    raw = yf.download(["SPY"], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs("SPY", axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Equity curve builders (identical logic to H047)
# ─────────────────────────────────────────────────────────────────────────────

def h041a_equity_curve(prices: pd.DataFrame) -> pd.Series:
    available = [a for a in H041A_ASSETS if a in prices.columns]
    if len(available) < TOP_N_H41A:
        return pd.Series(dtype=float)
    px = prices[available].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N_H41A
    equity = INITIAL_EQUITY
    series = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H41A:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N_H41A).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


def h026_equity_curve(prices: pd.DataFrame) -> pd.Series:
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N_H26
    equity = INITIAL_EQUITY
    series = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H26:
            continue
        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(TOP_N_H26).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top_hold].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top_hold:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


def h037b_equity_curve(ohlc: pd.DataFrame) -> pd.Series:
    df = ohlc.copy()
    denom   = (df["high"] - df["low"]).replace(0, np.nan)
    ibs     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    gap     = (df["open"] - prev_cl) / prev_cl
    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []
    for i in range(1, len(df)):
        date     = df.index[i]
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o        = float(df["open"].iloc[i])
        c        = float(df["close"].iloc[i])
        c_prev   = float(df["close"].iloc[i - 1])
        ret_oc = (c / o - 1)      if o > 0     else 0.0
        ret_cc = (c / c_prev - 1) if c_prev > 0 else 0.0
        if position == 0:
            if prev_ibs < IBS_BUY and cur_gap >= GAP_FILTER_B:
                position  = 1
                days_held = 1
                equity   *= (1 + ret_oc)
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                position  = 0
                days_held = 0
        series.append((date, equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


def h045_equity_curve(prices: pd.DataFrame) -> pd.Series:
    available = [t for t in TREASURY_ETFS if t in prices.columns]
    if len(available) < TOP_N_H45:
        return pd.Series(dtype=float)
    px = prices[available].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N_H45
    equity = INITIAL_EQUITY
    series = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H45:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N_H45).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Statistics helpers
# ─────────────────────────────────────────────────────────────────────────────

def portfolio_stats(monthly_rets: np.ndarray, n_years: float = None) -> dict:
    if n_years is None:
        n_years = len(monthly_rets) / 12.0
    if n_years < 0.5 or len(monthly_rets) < 6:
        return {"error": "insufficient data", "n_months": len(monthly_rets)}
    cagr   = float(np.prod(1 + monthly_rets) ** (1 / n_years) - 1)
    vol    = float(np.std(monthly_rets, ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    eq     = np.cumprod(1 + monthly_rets)
    roll_mx = np.maximum.accumulate(eq)
    max_dd  = float(np.min(eq / roll_mx - 1))
    calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "cagr":         round(cagr,   4),
        "sharpe":       round(sharpe,  4),
        "max_drawdown": round(max_dd,  4),
        "calmar":       round(calmar,  4),
        "ann_vol":      round(vol,     4),
        "n_months":     len(monthly_rets),
        "n_years":      round(n_years, 2),
    }


def blend_returns(r1, r2, r3, r4, w1, w2, w3, w4, idx) -> np.ndarray:
    a1 = r1.loc[idx].values
    a2 = r2.loc[idx].values
    a3 = r3.loc[idx].values
    a4 = r4.loc[idx].values
    return w1 * a1 + w2 * a2 + w3 * a3 + w4 * a4


def sharpe_from_returns(monthly_rets: np.ndarray) -> float:
    if len(monthly_rets) < 6:
        return -np.inf
    n_years = len(monthly_rets) / 12.0
    cagr   = float(np.prod(1 + monthly_rets) ** (1 / n_years) - 1)
    vol    = float(np.std(monthly_rets, ddof=1)) * np.sqrt(12)
    return cagr / vol if vol > 0 else 0.0


def optimize_4way(r1, r2, r3, r4, idx, n_steps: int = 41) -> dict:
    """
    Grid search over 4-way weight simplex. Returns max-Sharpe weights.
    """
    a1 = r1.loc[idx].values
    a2 = r2.loc[idx].values
    a3 = r3.loc[idx].values
    a4 = r4.loc[idx].values
    n_years = len(a1) / 12.0

    best_sharpe = -np.inf
    best_w = (0.392, 0.112, 0.196, 0.30)
    axis = np.linspace(0, 1, n_steps)

    for w1 in axis:
        for w2 in axis:
            if w1 + w2 > 1:
                continue
            for w3 in axis:
                w4 = 1.0 - w1 - w2 - w3
                if w4 < 0:
                    continue
                rb = w1 * a1 + w2 * a2 + w3 * a3 + w4 * a4
                s  = sharpe_from_returns(rb)
                if s > best_sharpe:
                    best_sharpe = s
                    best_w = (float(w1), float(w2), float(w3), float(w4))

    w1, w2, w3, w4 = best_w
    rb = w1 * a1 + w2 * a2 + w3 * a3 + w4 * a4
    stats = portfolio_stats(rb, n_years)
    stats.update({
        "w_h041a": round(w1, 4),
        "w_h026":  round(w2, 4),
        "w_h037b": round(w3, 4),
        "w_h045":  round(w4, 4),
    })
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# 2022 analysis helper
# ─────────────────────────────────────────────────────────────────────────────

def year_stats(r1, r2, r3, r4, w1, w2, w3, w4, common_idx, year: int) -> dict:
    """Return calendar year stats for the blend and each component."""
    yr_idx = common_idx[(common_idx.year == year)]
    if len(yr_idx) < 2:
        return {}
    rb = blend_returns(r1, r2, r3, r4, w1, w2, w3, w4, yr_idx)
    result = {
        "blend":  round(float(np.prod(1 + rb) - 1), 4),
        "h041a":  round(float(np.prod(1 + r1.loc[yr_idx].values) - 1), 4),
        "h026":   round(float(np.prod(1 + r2.loc[yr_idx].values) - 1), 4),
        "h037b":  round(float(np.prod(1 + r3.loc[yr_idx].values) - 1), 4),
        "h045":   round(float(np.prod(1 + r4.loc[yr_idx].values) - 1), 4),
        "n_months": len(yr_idx),
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward
# ─────────────────────────────────────────────────────────────────────────────

def walk_forward_5fold(r1, r2, r3, r4, common_idx, n_folds=5, n_steps=31) -> dict:
    """
    5-fold expanding walk-forward on the full common_idx.
    Each fold: train on first k months, test on next segment.
    """
    n = len(common_idx)
    # Minimum 48 months train
    fold_size = n // (n_folds + 1)
    min_train = max(48, fold_size)

    folds = []
    for fold in range(n_folds):
        train_end_pos = min_train + fold * fold_size
        test_start_pos = train_end_pos
        test_end_pos = min(test_start_pos + fold_size, n)
        if test_start_pos >= n or test_end_pos <= test_start_pos:
            continue

        train_idx = common_idx[:train_end_pos]
        test_idx  = common_idx[test_start_pos:test_end_pos]

        # optimize on train
        is_opt = optimize_4way(r1, r2, r3, r4, train_idx, n_steps=n_steps)
        w1, w2, w3, w4 = is_opt["w_h041a"], is_opt["w_h026"], is_opt["w_h037b"], is_opt["w_h045"]

        # eval on train (for degradation calc)
        rb_train = blend_returns(r1, r2, r3, r4, w1, w2, w3, w4, train_idx)
        is_stats = portfolio_stats(rb_train)

        # eval on test
        rb_test = blend_returns(r1, r2, r3, r4, w1, w2, w3, w4, test_idx)
        oos_stats = portfolio_stats(rb_test)

        # also eval operating weights on test
        rb_test_op = blend_returns(r1, r2, r3, r4,
                                   OP_W_H041A, OP_W_H026, OP_W_H037B, OP_W_H045,
                                   test_idx)
        oos_op_stats = portfolio_stats(rb_test_op)

        degradation = (oos_stats["sharpe"] - is_stats["sharpe"]) / abs(is_stats["sharpe"]) * 100 if is_stats.get("sharpe") else None

        folds.append({
            "fold": fold + 1,
            "train_start": str(train_idx[0].date()),
            "train_end":   str(train_idx[-1].date()),
            "test_start":  str(test_idx[0].date()),
            "test_end":    str(test_idx[-1].date()),
            "is_optimal_weights": {
                "w_h041a": w1, "w_h026": w2, "w_h037b": w3, "w_h045": w4
            },
            "is_sharpe":         is_stats.get("sharpe"),
            "oos_sharpe_is_w":   oos_stats.get("sharpe"),
            "oos_sharpe_op_w":   oos_op_stats.get("sharpe"),
            "oos_cagr_is_w":     oos_stats.get("cagr"),
            "oos_maxdd_is_w":    oos_stats.get("max_drawdown"),
            "degradation_pct":   round(degradation, 2) if degradation is not None else None,
            "n_train":   len(train_idx),
            "n_test":    len(test_idx),
        })
        print(f"  Fold {fold+1}: train {train_idx[0].date()}–{train_idx[-1].date()} "
              f"({len(train_idx)}m) | test {test_idx[0].date()}–{test_idx[-1].date()} "
              f"({len(test_idx)}m)")
        print(f"    IS-opt: H041a={w1:.1%} H026={w2:.1%} H037b={w3:.1%} H045={w4:.1%}")
        print(f"    IS Sharpe={is_stats.get('sharpe','?'):.3f}  "
              f"OOS Sharpe(IS-w)={oos_stats.get('sharpe','?'):.3f}  "
              f"OOS Sharpe(op-w)={oos_op_stats.get('sharpe','?'):.3f}  "
              f"Degradation={degradation:.1f}%" if degradation else "")

    oos_sharpes = [f["oos_sharpe_is_w"] for f in folds if f["oos_sharpe_is_w"] is not None]
    oos_op_sharpes = [f["oos_sharpe_op_w"] for f in folds if f["oos_sharpe_op_w"] is not None]
    degradations = [f["degradation_pct"] for f in folds if f["degradation_pct"] is not None]

    return {
        "folds": folds,
        "avg_oos_sharpe_is_weights":  round(float(np.mean(oos_sharpes)), 4) if oos_sharpes else None,
        "std_oos_sharpe_is_weights":  round(float(np.std(oos_sharpes,  ddof=1)), 4) if len(oos_sharpes) > 1 else None,
        "avg_oos_sharpe_op_weights":  round(float(np.mean(oos_op_sharpes)), 4) if oos_op_sharpes else None,
        "std_oos_sharpe_op_weights":  round(float(np.std(oos_op_sharpes, ddof=1)), 4) if len(oos_op_sharpes) > 1 else None,
        "avg_degradation_pct":        round(float(np.mean(degradations)), 2) if degradations else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H049 — IS/OOS Validation of H047 Four-Component Blend")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    equity_tickers   = list(set(H041A_ASSETS + SECTOR_ETFS))
    treasury_tickers = TREASURY_ETFS

    prices_eq  = fetch_close(equity_tickers,   FULL_START, FULL_END, tag="h047_equity")
    prices_tr  = fetch_close(treasury_tickers, FULL_START, FULL_END, tag="h047_treasury")
    spy_ohlc   = fetch_spy_ohlc(FULL_START, FULL_END)

    # ── 2. Build full equity curves ──────────────────────────────────────────
    print("\n[2] Building equity curves over full history …")
    eq_h041a = h041a_equity_curve(prices_eq)
    eq_h026  = h026_equity_curve(prices_eq)
    eq_h037b = h037b_equity_curve(spy_ohlc)
    eq_h045  = h045_equity_curve(prices_tr)

    for name, eq in [("H041a", eq_h041a), ("H026", eq_h026),
                     ("H037b", eq_h037b), ("H045", eq_h045)]:
        if eq.empty:
            print(f"ERROR: {name} equity curve is empty. Aborting.")
            return {}
        print(f"   {name}: {eq.index[0].date()} → {eq.index[-1].date()} ({len(eq)} days)")

    # ── 3. Monthly returns (full history) ────────────────────────────────────
    print("\n[3] Converting to monthly returns …")
    r_h041a_all = to_monthly_returns(eq_h041a)
    r_h026_all  = to_monthly_returns(eq_h026)
    r_h037b_all = to_monthly_returns(eq_h037b)
    r_h045_all  = to_monthly_returns(eq_h045)

    # Common 4-way window (2008 onward due to IEI)
    common_all = (
        r_h041a_all.index
        .intersection(r_h026_all.index)
        .intersection(r_h037b_all.index)
        .intersection(r_h045_all.index)
    )
    window_ts = pd.Timestamp("2008-01-01")
    common_all = common_all[common_all >= window_ts]

    r_h041a = r_h041a_all.loc[common_all]
    r_h026  = r_h026_all.loc[common_all]
    r_h037b = r_h037b_all.loc[common_all]
    r_h045  = r_h045_all.loc[common_all]

    print(f"   Full common window: {common_all[0].date()} → {common_all[-1].date()} "
          f"({len(common_all)} months, {len(common_all)/12:.1f} yrs)")

    # ── 4. IS / OOS split indices ─────────────────────────────────────────────
    is_idx  = common_all[(common_all >= pd.Timestamp(IS_START))  & (common_all <= pd.Timestamp(IS_END))]
    oos_idx = common_all[(common_all >= pd.Timestamp(OOS_START)) & (common_all <= pd.Timestamp(OOS_END))]

    print(f"   IS  window: {is_idx[0].date()} → {is_idx[-1].date()} ({len(is_idx)} months)")
    print(f"   OOS window: {oos_idx[0].date()} → {oos_idx[-1].date()} ({len(oos_idx)} months)")

    # ── 5. Full-period stats (operating weights) ─────────────────────────────
    print("\n[4] Full-period stats at operating weights (39.2/11.2/19.6/30) …")
    rb_full_op = blend_returns(r_h041a, r_h026, r_h037b, r_h045,
                               OP_W_H041A, OP_W_H026, OP_W_H037B, OP_W_H045,
                               common_all)
    full_op_stats = portfolio_stats(rb_full_op)
    print(f"   Full-period (op weights): CAGR={full_op_stats['cagr']:.2%}  "
          f"Sharpe={full_op_stats['sharpe']:.4f}  MaxDD={full_op_stats['max_drawdown']:.2%}")

    # ── 6. IS optimization ────────────────────────────────────────────────────
    print(f"\n[5] Optimizing weights on IS period ({IS_START} → {IS_END}) with 41-step grid …")
    is_opt = optimize_4way(r_h041a, r_h026, r_h037b, r_h045, is_idx, n_steps=41)
    w_is1, w_is2, w_is3, w_is4 = is_opt["w_h041a"], is_opt["w_h026"], is_opt["w_h037b"], is_opt["w_h045"]

    print(f"   IS-optimal: H041a={w_is1:.1%}  H026={w_is2:.1%}  "
          f"H037b={w_is3:.1%}  H045={w_is4:.1%}")
    print(f"   IS Sharpe={is_opt['sharpe']:.4f}  CAGR={is_opt['cagr']:.2%}  "
          f"MaxDD={is_opt['max_drawdown']:.2%}")

    # IS stats at operating weights too
    rb_is_op = blend_returns(r_h041a, r_h026, r_h037b, r_h045,
                             OP_W_H041A, OP_W_H026, OP_W_H037B, OP_W_H045, is_idx)
    is_op_stats = portfolio_stats(rb_is_op)
    print(f"   IS (op weights 39.2/11.2/19.6/30): Sharpe={is_op_stats['sharpe']:.4f}  "
          f"CAGR={is_op_stats['cagr']:.2%}  MaxDD={is_op_stats['max_drawdown']:.2%}")

    # ── 7. OOS evaluation ─────────────────────────────────────────────────────
    print(f"\n[6] Evaluating OOS period ({OOS_START} → {OOS_END}) …")

    # OOS with IS-optimal weights
    rb_oos_isw = blend_returns(r_h041a, r_h026, r_h037b, r_h045,
                               w_is1, w_is2, w_is3, w_is4, oos_idx)
    oos_isw_stats = portfolio_stats(rb_oos_isw)
    print(f"   OOS (IS-optimal weights): Sharpe={oos_isw_stats['sharpe']:.4f}  "
          f"CAGR={oos_isw_stats['cagr']:.2%}  MaxDD={oos_isw_stats['max_drawdown']:.2%}")

    # OOS with operating weights
    rb_oos_op = blend_returns(r_h041a, r_h026, r_h037b, r_h045,
                              OP_W_H041A, OP_W_H026, OP_W_H037B, OP_W_H045, oos_idx)
    oos_op_stats = portfolio_stats(rb_oos_op)
    print(f"   OOS (op weights 39.2/11.2/19.6/30): Sharpe={oos_op_stats['sharpe']:.4f}  "
          f"CAGR={oos_op_stats['cagr']:.2%}  MaxDD={oos_op_stats['max_drawdown']:.2%}")

    # ── 8. Degradation calculations ───────────────────────────────────────────
    # IS-optimal IS Sharpe → IS-optimal OOS Sharpe
    is_sharpe_isw  = is_opt["sharpe"]
    oos_sharpe_isw = oos_isw_stats["sharpe"]
    deg_isw = (oos_sharpe_isw - is_sharpe_isw) / abs(is_sharpe_isw) * 100

    # Operating weights IS Sharpe → Operating weights OOS Sharpe
    is_sharpe_op   = is_op_stats["sharpe"]
    oos_sharpe_op  = oos_op_stats["sharpe"]
    deg_op = (oos_sharpe_op - is_sharpe_op) / abs(is_sharpe_op) * 100

    print(f"\n   Degradation (IS-opt wts):  IS={is_sharpe_isw:.4f} → OOS={oos_sharpe_isw:.4f}  "
          f"= {deg_isw:+.1f}%  (H042 ref: -22.4%)")
    print(f"   Degradation (op wts):      IS={is_sharpe_op:.4f} → OOS={oos_sharpe_op:.4f}  "
          f"= {deg_op:+.1f}%  (H042 ref: -9.3%)")

    # ── 9. 2022 isolation ─────────────────────────────────────────────────────
    print("\n[7] 2022 isolation (rate shock stress test) …")

    # Operating weights 2022
    yr2022_op = year_stats(r_h041a, r_h026, r_h037b, r_h045,
                           OP_W_H041A, OP_W_H026, OP_W_H037B, OP_W_H045,
                           common_all, 2022)
    print(f"   2022 (op weights): blend={yr2022_op.get('blend','?'):.2%}  "
          f"H041a={yr2022_op.get('h041a','?'):.2%}  "
          f"H026={yr2022_op.get('h026','?'):.2%}  "
          f"H037b={yr2022_op.get('h037b','?'):.2%}  "
          f"H045={yr2022_op.get('h045','?'):.2%}")

    # Also 2020 (COVID crash) for comparison
    yr2020_op = year_stats(r_h041a, r_h026, r_h037b, r_h045,
                           OP_W_H041A, OP_W_H026, OP_W_H037B, OP_W_H045,
                           common_all, 2020)
    print(f"   2020 (op weights): blend={yr2020_op.get('blend','?'):.2%}  "
          f"H041a={yr2020_op.get('h041a','?'):.2%}  "
          f"H045={yr2020_op.get('h045','?'):.2%}")

    # 2022 with OOS IS-optimal weights
    yr2022_isw = year_stats(r_h041a, r_h026, r_h037b, r_h045,
                            w_is1, w_is2, w_is3, w_is4,
                            common_all, 2022)
    print(f"   2022 (IS-opt wts): blend={yr2022_isw.get('blend','?'):.2%}")

    # H045 component 2022 — check if SHY/IEI dominated
    # Fetch H045 monthly selections for 2022 to understand what the rotation chose
    print(f"\n   H045 rotation — what did it hold in 2022?")
    px_tr = prices_tr.copy()
    monthly_tr = px_tr[TREASURY_ETFS].resample("ME").last()
    monthly_tr_ret = px_tr[TREASURY_ETFS].pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6_tr  = monthly_tr_ret.rolling(6).std() * np.sqrt(12)
    mom_12_tr = monthly_tr / monthly_tr.shift(12) - 1

    h045_holdings_2022 = {}
    for i in range(12, len(monthly_tr)):
        dt = monthly_tr.index[i]
        if dt.year not in (2021, 2022):
            continue
        mom_row = mom_12_tr.iloc[i].dropna()
        vol_row = vol_6_tr.iloc[i].dropna()
        valid = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H45:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top2 = list(score.nlargest(TOP_N_H45).index)
        h045_holdings_2022[str(dt.date())] = top2
        print(f"     {dt.strftime('%Y-%m')}: {top2}")

    # ── 10. 5-fold walk-forward ───────────────────────────────────────────────
    print("\n[8] Running 5-fold walk-forward (31-step grid per fold) …")
    wf_results = walk_forward_5fold(r_h041a, r_h026, r_h037b, r_h045, common_all,
                                    n_folds=5, n_steps=31)

    print(f"\n   Walk-forward summary:")
    print(f"   Avg OOS Sharpe (IS-optimal wts): {wf_results['avg_oos_sharpe_is_weights']:.4f}  "
          f"± {wf_results['std_oos_sharpe_is_weights']:.4f}")
    print(f"   Avg OOS Sharpe (op wts):          {wf_results['avg_oos_sharpe_op_weights']:.4f}  "
          f"± {wf_results['std_oos_sharpe_op_weights']:.4f}")
    print(f"   Avg degradation:                  {wf_results['avg_degradation_pct']:+.1f}%")

    # ── 11. Individual component IS/OOS stats ────────────────────────────────
    print("\n[9] Component IS/OOS stats …")
    comp_is_oos = {}
    for name, r in [("h041a", r_h041a), ("h026", r_h026), ("h037b", r_h037b), ("h045", r_h045)]:
        is_s  = portfolio_stats(r.loc[is_idx].values)
        oos_s = portfolio_stats(r.loc[oos_idx].values)
        deg   = (oos_s["sharpe"] - is_s["sharpe"]) / abs(is_s["sharpe"]) * 100
        comp_is_oos[name] = {"is": is_s, "oos": oos_s, "degradation_pct": round(deg, 2)}
        print(f"   {name}: IS Sharpe={is_s['sharpe']:.3f} → OOS Sharpe={oos_s['sharpe']:.3f}  "
              f"deg={deg:+.1f}%")

    # ── 12. Verdict ───────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  H049 VERDICT")
    print("=" * 80)

    # Compare to H042 benchmarks
    h042_oos_deg_op   = -9.3   # operating weights degradation
    h042_oos_deg_isw  = -22.4  # IS-optimal weights degradation

    if deg_op > -5:
        verdict_op = "ROBUST — operating-weight OOS degradation better than H042's -9.3%"
    elif deg_op > -15:
        verdict_op = "ACCEPTABLE — operating-weight OOS degradation within benchmark range"
    elif deg_op > -25:
        verdict_op = "MODERATE OVERFIT — degradation worse than H042 but still investable"
    else:
        verdict_op = "OVERFIT WARNING — operating-weight degradation exceeds -25%; review weights"

    if deg_isw > -25:
        verdict_isw = "ROBUST — IS-optimal-weight OOS degradation better than H042's -22.4%"
    elif deg_isw > -35:
        verdict_isw = "ACCEPTABLE — IS-optimal-weight OOS degradation within expected range"
    else:
        verdict_isw = "MODERATE OVERFIT — IS-optimal degradation exceeds -35%"

    # 2022 verdict
    blend_2022 = yr2022_op.get('blend', 0)
    h045_2022  = yr2022_op.get('h045', 0)
    if blend_2022 > -0.05:
        verdict_2022 = f"H049 blend weathered 2022 (total return {blend_2022:.1%}). H045 selected {h045_2022:.1%}. Tail protection confirmed."
    elif blend_2022 > -0.15:
        verdict_2022 = f"H049 blend took moderate 2022 loss ({blend_2022:.1%}). H045 helped but H041a equity exposure was dominant."
    else:
        verdict_2022 = f"H049 blend suffered significant 2022 loss ({blend_2022:.1%}). H041a equity exposure overwhelmed H045 defensive positioning."

    print(f"\n  Operating weights OOS degradation : {deg_op:+.1f}%  → {verdict_op}")
    print(f"  IS-optimal weights OOS degradation: {deg_isw:+.1f}%  → {verdict_isw}")
    print(f"\n  2022 stress: {verdict_2022}")
    print(f"\n  Walk-forward avg OOS Sharpe: {wf_results['avg_oos_sharpe_is_weights']:.4f} ± {wf_results['std_oos_sharpe_is_weights']:.4f}")

    # ── 13. Save results ──────────────────────────────────────────────────────
    output = {
        "strategy": "H049 — IS/OOS Validation of H047 Four-Component Blend",
        "description": (
            "Formal IS/OOS validation of H047 blend (H041a 39.2% / H026 11.2% / H037b 19.6% / H045 30%). "
            "IS: 2008-2017 (10y), OOS: 2018-2026 (8.3y). Also: 5-fold walk-forward and 2022 stress analysis."
        ),
        "components": {
            "h041a": "7-asset macro rotation (SPY/QQQ/TLT/GLD/IEF/EFA/EEM), top-2 rank",
            "h026":  "11-sector ETF top-3 momentum",
            "h037b": "IBS mean-reversion SPY gap-filtered",
            "h045":  "7-ETF Treasury rotation (SHY/IEI/IEF/TLT/TIP/HYG/LQD), top-2 rank",
        },
        "operating_weights": {
            "w_h041a": OP_W_H041A,
            "w_h026":  OP_W_H026,
            "w_h037b": OP_W_H037B,
            "w_h045":  OP_W_H045,
            "source": "H047 grid best (H045=30%): Sharpe 1.984, MaxDD -6.63%",
        },
        "periods": {
            "full":  {"start": str(common_all[0].date()), "end": str(common_all[-1].date()), "n_months": len(common_all)},
            "is":    {"start": str(is_idx[0].date()),     "end": str(is_idx[-1].date()),     "n_months": len(is_idx)},
            "oos":   {"start": str(oos_idx[0].date()),    "end": str(oos_idx[-1].date()),     "n_months": len(oos_idx)},
        },
        "full_period_stats": {
            "operating_weights": full_op_stats,
        },
        "is_optimization": {
            "is_optimal_weights": {
                "w_h041a": w_is1, "w_h026": w_is2, "w_h037b": w_is3, "w_h045": w_is4
            },
            "is_stats_is_optimal_weights":  is_opt,
            "is_stats_operating_weights":   is_op_stats,
        },
        "oos_evaluation": {
            "oos_stats_is_optimal_weights":  oos_isw_stats,
            "oos_stats_operating_weights":   oos_op_stats,
        },
        "degradation": {
            "is_optimal_weights": {
                "is_sharpe":           round(is_sharpe_isw, 4),
                "oos_sharpe":          round(oos_sharpe_isw, 4),
                "degradation_pct":     round(deg_isw, 2),
                "h042_reference_pct":  -22.4,
            },
            "operating_weights": {
                "is_sharpe":           round(is_sharpe_op, 4),
                "oos_sharpe":          round(oos_sharpe_op, 4),
                "degradation_pct":     round(deg_op, 2),
                "h042_reference_pct":  -9.3,
            },
        },
        "component_is_oos": comp_is_oos,
        "stress_tests": {
            "year_2022_operating_weights": yr2022_op,
            "year_2022_is_optimal_weights": yr2022_isw,
            "year_2020_operating_weights": yr2020_op,
            "h045_monthly_holdings_2021_2022": h045_holdings_2022,
            "verdict_2022": verdict_2022,
        },
        "walk_forward_5fold": wf_results,
        "verdicts": {
            "operating_weights": verdict_op,
            "is_optimal_weights": verdict_isw,
            "overall": (
                f"H049 OOS degradation (op weights): {deg_op:+.1f}% vs H042 benchmark -9.3%. "
                f"Walk-forward avg OOS Sharpe: {wf_results['avg_oos_sharpe_is_weights']:.4f}. "
                f"2022 blend return: {blend_2022:.1%}."
            ),
        },
        "h042_oos_benchmarks": {
            "is_optimal_weights_degradation": -22.4,
            "operating_weights_degradation":  -9.3,
            "oos_sharpe_operating_weights":   1.768,
            "note": "From H043 IS/OOS validation run",
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h049_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
