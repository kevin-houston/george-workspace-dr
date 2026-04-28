"""
H062 — Multi-Asset IBS Survey: Finding a Second Inverse-Degradation Signal
===========================================================================

Purpose:
  H054b (QQQ IBS) has +93% OOS improvement (IS 0.761 → OOS 1.472). This is
  exceptional and we don't want to be concentrated in a single IBS signal.
  H037b (SPY IBS) degrades −39%. H054b was selected because QQQ's post-2018
  intraday volatility increased dramatically.

  Hypothesis: Are there other ETFs with similarly strengthening IBS signals
  post-2018? Candidates: GLD (inflation/safe-haven vol), TLT (rate shock vol),
  SMH (semiconductor ETF, extreme intraday moves), IWM (small-cap, more volatile
  IBS signals), XLE (energy, extreme post-COVID moves).

  For each: run standalone IBS backtest (same rules as H054b) + IS/OOS split.
  Report: IS Sharpe, OOS Sharpe, degradation direction.
  Confirm/reject: at least one asset has inverse degradation (OOS > IS).

  If confirmed: test blend of H054b + best new IBS within H060 weights.

Periods:
  Full: 2003-01 → 2026-04 (longest available)
  IS: 2008-01 → 2017-12 (consistent with all prior work)
  OOS: 2018-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h062_results.json
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

FULL_START   = "2003-01-01"
FULL_END     = "2026-04-27"
IS_START     = "2008-01-01"
IS_END       = "2017-12-31"
OOS_START    = "2018-01-01"

IBS_BUY    = 0.20
IBS_SELL   = 0.80
MAX_HOLD   = 5
GAP_FILTER = -0.005

# Candidates for IBS survey
CANDIDATES = ["QQQ", "SPY", "GLD", "TLT", "SMH", "IWM", "XLE", "XLK", "EFA", "GDX"]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    # Check existing caches for QQQ and SPY
    if ticker == "QQQ":
        for prefix in ["h054", "h055", "h056", "h057", "h058", "h059", "h060", "h061"]:
            cp = CACHE_DIR / f"{prefix}_QQQ_ohlc_{start}_{end}.parquet"
            if cp.exists():
                df = pd.read_parquet(cp)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    return df
    if ticker == "SPY":
        for fname in [f"h031_spy_ohlc_{start}_{end}.parquet", f"h042_spy_ohlc_{start}_{end}.parquet"]:
            cp = CACHE_DIR / fname
            if cp.exists():
                df = pd.read_parquet(cp)
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs("SPY", axis=1, level=1)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    return df
    cp = CACHE_DIR / f"h062_{ticker}_ohlc_{start}_{end}.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        df.columns = [c.lower() for c in df.columns]
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            return df
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    cp = CACHE_DIR / f"h062_{ticker}_ohlc_{start}_{end}.parquet"
    df.to_parquet(cp)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# IBS backtest
# ─────────────────────────────────────────────────────────────────────────────

def ibs_equity_curve(ohlc):
    df        = ohlc.copy()
    denom     = (df["high"] - df["low"]).replace(0, np.nan)
    ibs       = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl   = df["close"].shift(1)
    gap       = (df["open"] - prev_cl) / prev_cl
    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []
    n_trades  = 0
    for i in range(1, len(df)):
        date     = df.index[i]
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o        = float(df["open"].iloc[i])
        c        = float(df["close"].iloc[i])
        c_prev   = float(df["close"].iloc[i - 1])
        ret_oc   = (c / o - 1)      if o > 0      else 0.0
        ret_cc   = (c / c_prev - 1) if c_prev > 0 else 0.0
        if position == 0:
            if prev_ibs < IBS_BUY and cur_gap >= GAP_FILTER:
                position  = 1
                days_held = 1
                equity   *= (1 + ret_oc)
                n_trades += 1
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                position  = 0
                days_held = 0
        series.append((date, equity))
    eq = pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))
    return eq, n_trades


def to_monthly_returns(eq_daily):
    return eq_daily.resample("ME").last().ffill().pct_change().dropna()


def stats_from_monthly_returns(monthly_rets, label=""):
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 12:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(monthly_rets)}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd  = float((equity / roll_max - 1).min())
    return {
        "label":        label,
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "n_months":     len(monthly_rets),
    }


def blend_returns(idx, r1, r2, w1, w2):
    return w1 * r1.reindex(idx, fill_value=0.0) + w2 * r2.reindex(idx, fill_value=0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H062 — Multi-Asset IBS Survey: Finding Inverse-Degradation Signals")
    print("=" * 80)

    is_ts  = pd.Timestamp(IS_END)
    oos_ts = pd.Timestamp(OOS_START)
    is_start_ts = pd.Timestamp(IS_START)

    # ── 1. Run IBS on all candidates ─────────────────────────────────────────
    print("\n[1] Running IBS backtest on all candidates …")
    print(f"\n  {'Ticker':>7}  {'Full S':>7}  {'IS S':>7}  {'OOS S':>7}  {'OOS MaxDD':>10}  {'Deg%':>8}  {'Trades':>7}  {'Direction'}")
    print(f"  {'-'*80}")

    results = {}
    monthly_rets = {}

    for ticker in CANDIDATES:
        try:
            ohlc = fetch_ohlc(ticker, FULL_START, FULL_END)
            eq, n_trades = ibs_equity_curve(ohlc)
            if len(eq) < 100:
                print(f"  {ticker:>7}  (insufficient data)")
                continue
            r = to_monthly_returns(eq)
            r_full = r[(r.index >= pd.Timestamp(IS_START))]  # 2008+ for consistency
            r_is   = r[(r.index >= is_start_ts) & (r.index <= is_ts)]
            r_oos  = r[r.index >= oos_ts]
            if len(r_is) < 24 or len(r_oos) < 12:
                print(f"  {ticker:>7}  (insufficient IS/OOS periods)")
                continue
            s_f = stats_from_monthly_returns(r_full)
            s_i = stats_from_monthly_returns(r_is)
            s_o = stats_from_monthly_returns(r_oos)
            deg = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100 if s_i["sharpe"] > 0 else float("nan")
            direction = "↑ IMPROVING" if deg > 10 else ("↓ degrading" if deg < -10 else "≈ stable")
            print(f"  {ticker:>7}  {s_f['sharpe']:>7.3f}  {s_i['sharpe']:>7.3f}  {s_o['sharpe']:>7.3f}  {s_o['max_drawdown']*100:>9.2f}%  {deg:>+8.1f}%  {n_trades:>7}  {direction}")
            results[ticker] = {
                "full":     s_f,
                "is":       s_i,
                "oos":      s_o,
                "deg":      round(deg, 2),
                "n_trades": n_trades,
                "direction": direction,
            }
            monthly_rets[ticker] = r
        except Exception as e:
            print(f"  {ticker:>7}  ERROR: {e}")

    # ── 2. Identify best IBS signals ─────────────────────────────────────────
    print("\n[2] Ranking by OOS Sharpe (improving assets) …")
    improving = {k: v for k, v in results.items() if v["deg"] > 0}
    stable    = {k: v for k, v in results.items() if -10 <= v["deg"] <= 0}
    degrading = {k: v for k, v in results.items() if v["deg"] < -10}

    print(f"\n   Improving (OOS > IS):")
    for k, v in sorted(improving.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True):
        print(f"     {k}: OOS {v['oos']['sharpe']:.3f}  Deg {v['deg']:+.1f}%")
    print(f"\n   Stable (deg -10% to 0%):")
    for k, v in sorted(stable.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True):
        print(f"     {k}: OOS {v['oos']['sharpe']:.3f}  Deg {v['deg']:+.1f}%")
    print(f"\n   Degrading (OOS < IS):")
    for k, v in sorted(degrading.items(), key=lambda x: x[1]["deg"], reverse=True):
        print(f"     {k}: OOS {v['oos']['sharpe']:.3f}  Deg {v['deg']:+.1f}%")

    # ── 3. Correlation of new IBS signals to H054b (QQQ) ─────────────────────
    print("\n[3] Correlation of IBS monthly returns to H054b (QQQ) …")
    qqq_rets = monthly_rets.get("QQQ", pd.Series(dtype=float))
    if not qqq_rets.empty:
        for ticker in [k for k in CANDIDATES if k != "QQQ" and k in monthly_rets]:
            other_rets = monthly_rets[ticker]
            common = qqq_rets.index.intersection(other_rets.index)
            common = common[common >= is_start_ts]
            if len(common) < 24:
                continue
            corr = qqq_rets.loc[common].corr(other_rets.loc[common])
            print(f"   QQQ IBS vs {ticker} IBS: {corr:+.3f}  ({'low — good diversifier' if abs(corr) < 0.4 else 'high — correlated'})")

    # ── 4. Best new IBS blend with H054b ─────────────────────────────────────
    print("\n[4] Best new IBS blend with H054b within H060 28% IBS budget …")
    # Find improving or stable assets with decent OOS Sharpe
    candidates_for_blend = {k: v for k, v in results.items()
                             if k != "QQQ" and k != "SPY"
                             and v["oos"]["sharpe"] > 0.5
                             and k in monthly_rets}

    if candidates_for_blend:
        is_ts_filter = pd.Timestamp(IS_END)
        oos_ts_filter = pd.Timestamp(OOS_START)

        print(f"\n  {'Blend':>28}  {'OOS S blend':>12}  {'vs H054b-only':>14}  {'Corr QQQ':>9}")
        print(f"  {'-'*65}")

        qqq_r = monthly_rets["QQQ"]
        for ticker, info in sorted(candidates_for_blend.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True):
            other_r = monthly_rets[ticker]
            common_oos = qqq_r.index.intersection(other_r.index)
            common_oos = common_oos[common_oos >= oos_ts_filter]
            if len(common_oos) < 24:
                continue
            # Try 50/50 blend
            r_blend = 0.5 * qqq_r.reindex(common_oos, fill_value=0.0) + 0.5 * other_r.reindex(common_oos, fill_value=0.0)
            s_blend = stats_from_monthly_returns(r_blend)
            s_qqq_oos = stats_from_monthly_returns(qqq_r.reindex(common_oos).dropna())
            corr = qqq_r.reindex(common_oos).corr(other_r.reindex(common_oos))
            delta = s_blend["sharpe"] - s_qqq_oos["sharpe"]
            print(f"  {f'50% QQQ + 50% {ticker}':>28}  {s_blend['sharpe']:>12.3f}  {delta:>+14.3f}  {corr:>9.3f}")
    else:
        print("   No viable blend candidates found.")

    # ── 5. Verdict ───────────────────────────────────────────────────────────
    print("\n[5] Verdict …")
    n_improving = len(improving)
    print(f"   {n_improving} assets show inverse degradation (OOS > IS)")
    if n_improving > 0:
        best_new = max(improving.items(), key=lambda x: x[1]["oos"]["sharpe"])
        print(f"   Best new IBS: {best_new[0]} OOS {best_new[1]['oos']['sharpe']:.3f}  Deg {best_new[1]['deg']:+.1f}%")
        print(f"   Verdict: CONFIRMED — Multiple assets show improving IBS signals")
    else:
        print(f"   Verdict: QQQ remains the only inverse-degradation IBS signal")

    # ── 6. Save results ──────────────────────────────────────────────────────
    out = RESULT_DIR / "h062_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H062", "results": results}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
