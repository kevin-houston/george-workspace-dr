"""
H054 — QQQ IBS Mean-Reversion: Standalone + Correlation to H037b
=================================================================

Hypothesis: IBS (Internal Bar Strength) mean-reversion works on QQQ for similar
reasons as SPY (H037b) — oversold bounces driven by market-wide risk appetite.
But QQQ is tech-heavy, so IBS signal may fire on different days (sector-specific
stress) vs SPY IBS (broad market stress).

If daily return correlation to H037b < 0.40, QQQ IBS adds genuine diversification.
If correlation ≥ 0.40 (like XLK at 0.65 in H048a), it's redundant.

H054a: QQQ IBS standalone (gap filter off — baseline)
H054b: QQQ IBS with gap < -0.5% filter (same as H037b improvement)
H054c: QQQ IBS with 1% gap filter (test if -1.0% is better for QQQ given higher vol)

Correlation tests:
  - Monthly return corr H054b vs H037b
  - Daily return corr (simultaneous trade days)
  - Blend analysis: 50/50 H037b + H054b — does Sharpe improve?

Confirm criteria:
  - Standalone H054b Sharpe > 0.80
  - Monthly correlation to H037b < 0.50
  - 50/50 blend Sharpe > max(H037b, H054b) standalone
Reject criteria:
  - H054b Sharpe < 0.60
  - Monthly correlation > 0.55
  - No blend benefit

Period: 2001-01-01 → 2026-04-27 (max QQQ history available)
IS/OOS: 2003-08 → 2017-12 / 2018-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h054_results.json
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

FULL_START   = "2000-01-01"
FULL_END     = "2026-04-27"
WINDOW_START = "2003-08-01"
IS_END       = "2017-12-31"
OOS_START    = "2018-01-01"

IBS_BUY       = 0.20
IBS_SELL      = 0.80
MAX_HOLD      = 5
GAP_FILTER_B  = -0.005   # -0.5% gap filter (H054b — matches H037b)
GAP_FILTER_C  = -0.010   # -1.0% gap filter (H054c — test tighter threshold for QQQ)


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker: str, start: str, end: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h054_{ticker}_ohlc_{start}_{end}.parquet"
    # reuse SPY OHLC caches for SPY
    if ticker == "SPY":
        for fname in [
            f"h031_spy_ohlc_{start}_{end}.parquet",
            f"h042_spy_ohlc_{start}_{end}.parquet",
            f"h050_spy_ohlc_{start}_{end}.parquet",
        ]:
            existing = CACHE_DIR / fname
            if existing.exists():
                df = pd.read_parquet(existing)
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs("SPY", axis=1, level=1)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    return df
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# IBS equity curve builder
# ─────────────────────────────────────────────────────────────────────────────

def ibs_equity_curve(ohlc: pd.DataFrame, gap_filter: float | None = None) -> tuple:
    """
    Build equity curve for IBS mean-reversion strategy.
    Returns (equity_curve_daily, trade_log).
    gap_filter: if not None, skip entry if today's gap < gap_filter (e.g. -0.005)
    """
    df = ohlc.copy()
    denom   = (df["high"] - df["low"]).replace(0, np.nan)
    ibs     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    gap     = (df["open"] - prev_cl) / prev_cl

    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []
    trades    = []
    entry_price = 0.0
    entry_date  = None

    for i in range(1, len(df)):
        date     = df.index[i]
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o        = float(df["open"].iloc[i])
        c        = float(df["close"].iloc[i])
        c_prev   = float(df["close"].iloc[i - 1])

        ret_oc = (c / o - 1)      if o > 0      else 0.0
        ret_cc = (c / c_prev - 1) if c_prev > 0 else 0.0

        if position == 0:
            buy_signal = prev_ibs < IBS_BUY
            if gap_filter is not None:
                buy_signal = buy_signal and (cur_gap >= gap_filter)
            if buy_signal:
                position    = 1
                days_held   = 1
                equity     *= (1 + ret_oc)
                entry_price = o
                entry_date  = date
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                trades.append({
                    "entry_date":  str(entry_date.date()),
                    "exit_date":   str(date.date()),
                    "days_held":   days_held,
                    "exit_reason": "ibs_sell" if cur_ibs > IBS_SELL else "max_hold",
                    "pnl_pct":     round((c / entry_price - 1) * 100, 4) if entry_price > 0 else 0,
                })
                position  = 0
                days_held = 0
        series.append((date, equity))

    if not series:
        return pd.Series(dtype=float), trades
    return (
        pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series])),
        trades,
    )


def to_monthly_returns(eq_daily):
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


def stats_from_monthly_returns(monthly_rets, label=""):
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 6:
        return {"error": "insufficient data", "n_months": len(monthly_rets), "label": label}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "label":        label,
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "calmar":       round(float(calmar),  4),
        "ann_vol":      round(float(vol),     4),
        "n_months":     len(monthly_rets),
    }


def trade_stats(trades: list) -> dict:
    if not trades:
        return {"n_trades": 0}
    n = len(trades)
    winners = [t for t in trades if t["pnl_pct"] > 0]
    win_rate = len(winners) / n
    avg_pnl  = np.mean([t["pnl_pct"] for t in trades])
    avg_hold = np.mean([t["days_held"] for t in trades])
    return {
        "n_trades":   n,
        "win_rate":   round(win_rate, 4),
        "avg_pnl_pct": round(avg_pnl,  4),
        "avg_hold_days": round(avg_hold, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H054 — QQQ IBS Mean-Reversion: Standalone + Correlation to H037b (SPY)")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching OHLC data …")
    spy_ohlc = fetch_ohlc("SPY", FULL_START, FULL_END)
    qqq_ohlc = fetch_ohlc("QQQ", FULL_START, FULL_END)
    print(f"   SPY: {spy_ohlc.index[0].date()} → {spy_ohlc.index[-1].date()} ({len(spy_ohlc)} days)")
    print(f"   QQQ: {qqq_ohlc.index[0].date()} → {qqq_ohlc.index[-1].date()} ({len(qqq_ohlc)} days)")

    # ── 2. Build equity curves ────────────────────────────────────────────────
    print("\n[2] Building IBS equity curves …")
    eq_spy_a, t_spy_a = ibs_equity_curve(spy_ohlc, gap_filter=None)       # H037 unfiltered
    eq_spy_b, t_spy_b = ibs_equity_curve(spy_ohlc, gap_filter=GAP_FILTER_B) # H037b
    eq_qqq_a, t_qqq_a = ibs_equity_curve(qqq_ohlc, gap_filter=None)       # H054a
    eq_qqq_b, t_qqq_b = ibs_equity_curve(qqq_ohlc, gap_filter=GAP_FILTER_B) # H054b
    eq_qqq_c, t_qqq_c = ibs_equity_curve(qqq_ohlc, gap_filter=GAP_FILTER_C) # H054c

    for name, eq, trades in [
        ("SPY IBS (no filter)",   eq_spy_a, t_spy_a),
        ("H037b SPY IBS (−0.5%)", eq_spy_b, t_spy_b),
        ("QQQ IBS (no filter)",   eq_qqq_a, t_qqq_a),
        ("H054b QQQ IBS (−0.5%)", eq_qqq_b, t_qqq_b),
        ("H054c QQQ IBS (−1.0%)", eq_qqq_c, t_qqq_c),
    ]:
        print(f"   {name}: {len(eq)} days, {len(trades)} trades")

    # ── 3. Monthly returns ────────────────────────────────────────────────────
    print("\n[3] Monthly returns and correlations …")
    r_spy_a = to_monthly_returns(eq_spy_a)
    r_spy_b = to_monthly_returns(eq_spy_b)
    r_qqq_a = to_monthly_returns(eq_qqq_a)
    r_qqq_b = to_monthly_returns(eq_qqq_b)
    r_qqq_c = to_monthly_returns(eq_qqq_c)

    window_ts = pd.Timestamp(WINDOW_START)
    common = (
        r_spy_b.index
        .intersection(r_qqq_b.index)
    )
    common = common[common >= window_ts]
    print(f"   Common window: {common[0].date()} → {common[-1].date()} ({len(common)} months)")

    r_sb = r_spy_b.loc[common]
    r_qa = r_qqq_a.loc[common]
    r_qb = r_qqq_b.loc[common]
    r_qc = r_qqq_c.loc[common]

    corr_qa_sb = float(r_qa.corr(r_sb))
    corr_qb_sb = float(r_qb.corr(r_sb))
    corr_qc_sb = float(r_qc.corr(r_sb))
    print(f"   Monthly corr H054a (QQQ no filter) vs H037b (SPY -0.5%): {corr_qa_sb:.4f}")
    print(f"   Monthly corr H054b (QQQ -0.5%)     vs H037b (SPY -0.5%): {corr_qb_sb:.4f}")
    print(f"   Monthly corr H054c (QQQ -1.0%)     vs H037b (SPY -0.5%): {corr_qc_sb:.4f}")
    print(f"   Reference: XLK IBS vs H037b = 0.65 (from H048a)")

    # ── 4. Standalone stats ───────────────────────────────────────────────────
    print("\n[4] Standalone statistics (full common window) …")
    s_spy_a = stats_from_monthly_returns(r_spy_a.loc[common], "SPY IBS (no filter)")
    s_spy_b = stats_from_monthly_returns(r_sb,  "H037b SPY IBS (-0.5%)")
    s_qqq_a = stats_from_monthly_returns(r_qa,  "H054a QQQ IBS (no filter)")
    s_qqq_b = stats_from_monthly_returns(r_qb,  "H054b QQQ IBS (-0.5%)")
    s_qqq_c = stats_from_monthly_returns(r_qc,  "H054c QQQ IBS (-1.0%)")

    print(f"\n   {'Strategy':<32}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Trades':>7}")
    print(f"   {'-'*78}")
    for s, trades in [
        (s_spy_a, t_spy_a), (s_spy_b, t_spy_b),
        (s_qqq_a, t_qqq_a), (s_qqq_b, t_qqq_b), (s_qqq_c, t_qqq_c),
    ]:
        if "error" in s:
            print(f"   {s.get('label','?'):<32}  ERROR")
        else:
            print(f"   {s['label']:<32}  {s['cagr']:>8.2%}  {s['sharpe']:>8.4f}  "
                  f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  {len(trades):>7}")

    # ── 5. Trade stats ────────────────────────────────────────────────────────
    print("\n[5] Trade statistics …")
    for name, trades in [("H037b SPY -0.5%", t_spy_b), ("H054b QQQ -0.5%", t_qqq_b), ("H054c QQQ -1.0%", t_qqq_c)]:
        ts = trade_stats(trades)
        print(f"   {name}: {ts['n_trades']} trades  win_rate {ts['win_rate']:.1%}  avg_pnl {ts['avg_pnl_pct']:.3f}%  avg_hold {ts['avg_hold_days']:.1f}d")

    # ── 6. Blend analysis (H037b + H054b) ────────────────────────────────────
    print("\n[6] Blend analysis: H037b + H054b …")
    for w_spy in [0.5, 0.6, 0.7]:
        w_qqq = 1.0 - w_spy
        r_blend = w_spy * r_sb + w_qqq * r_qb
        s_blend = stats_from_monthly_returns(r_blend)
        if "error" not in s_blend:
            print(f"   {w_spy:.0%} H037b / {w_qqq:.0%} H054b: Sharpe {s_blend['sharpe']:.4f}  CAGR {s_blend['cagr']:.2%}  MaxDD {s_blend['max_drawdown']:.2%}")

    # ── 7. IS / OOS split ────────────────────────────────────────────────────
    print("\n[7] IS / OOS split …")
    is_ts  = pd.Timestamp(IS_END)
    oos_ts = pd.Timestamp(OOS_START)
    is_idx  = common[(common >= window_ts) & (common <= is_ts)]
    oos_idx = common[common >= oos_ts]

    s_qb_is  = stats_from_monthly_returns(r_qb.loc[is_idx],  "H054b IS")
    s_qb_oos = stats_from_monthly_returns(r_qb.loc[oos_idx], "H054b OOS")
    s_sb_is  = stats_from_monthly_returns(r_sb.loc[is_idx],  "H037b IS")
    s_sb_oos = stats_from_monthly_returns(r_sb.loc[oos_idx], "H037b OOS")

    deg_qb = (s_qb_oos["sharpe"] - s_qb_is["sharpe"]) / s_qb_is["sharpe"] * 100
    deg_sb = (s_sb_oos["sharpe"] - s_sb_is["sharpe"]) / s_sb_is["sharpe"] * 100
    corr_oos = float(r_qb.loc[oos_idx].corr(r_sb.loc[oos_idx]))

    print(f"   H054b IS  Sharpe {s_qb_is['sharpe']:.4f}  OOS {s_qb_oos['sharpe']:.4f}  Degradation {deg_qb:+.1f}%")
    print(f"   H037b IS  Sharpe {s_sb_is['sharpe']:.4f}  OOS {s_sb_oos['sharpe']:.4f}  Degradation {deg_sb:+.1f}%")
    print(f"   OOS correlation H054b vs H037b: {corr_oos:.4f}")

    # ── 8. Verdict ────────────────────────────────────────────────────────────
    print("\n[8] Verdict …")
    standalone_ok = s_qqq_b["sharpe"] > 0.80 if "error" not in s_qqq_b else False
    corr_low      = corr_qb_sb < 0.50
    blend_ok      = False
    for w_spy in [0.5, 0.6, 0.7]:
        w_qqq = 1.0 - w_spy
        r_blend = w_spy * r_sb + w_qqq * r_qb
        s_blend = stats_from_monthly_returns(r_blend)
        if "error" not in s_blend and s_blend["sharpe"] > max(s_spy_b.get("sharpe",0), s_qqq_b.get("sharpe",0)):
            blend_ok = True
            break

    if standalone_ok and corr_low and blend_ok:
        verdict = "CONFIRMED — QQQ IBS adds diversification to H037b (SPY IBS)"
    elif standalone_ok and corr_low:
        verdict = "PARTIALLY CONFIRMED — Good standalone, low correlation but blend benefit marginal"
    elif standalone_ok and not corr_low:
        verdict = "REJECTED as diversifier — Good standalone but too correlated to H037b"
    else:
        verdict = "REJECTED — Insufficient standalone Sharpe or too correlated to H037b"

    print(f"   Standalone H054b Sharpe > 0.80: {standalone_ok} ({s_qqq_b.get('sharpe',0):.4f})")
    print(f"   Monthly corr < 0.50: {corr_low} ({corr_qb_sb:.4f})")
    print(f"   Blend benefit: {blend_ok}")
    print(f"\n   Verdict: {verdict}")

    # ── 9. Summary table ─────────────────────────────────────────────────────
    print(f"\n{'=' * 85}")
    print("  H054 — QQQ IBS SUMMARY")
    print(f"{'=' * 85}")
    print(f"  {'Strategy':<32}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'IS Sharpe':>10}  {'OOS Sharpe':>11}")
    print(f"  {'-'*84}")
    for label, s_full, s_is, s_oos in [
        ("H037b SPY IBS (-0.5%)", s_spy_b, s_sb_is, s_sb_oos),
        ("H054b QQQ IBS (-0.5%)", s_qqq_b, s_qb_is, s_qb_oos),
    ]:
        if "error" in s_full:
            print(f"  {label:<32}  ERROR")
        else:
            print(f"  {label:<32}  {s_full['cagr']:>8.2%}  {s_full['sharpe']:>8.4f}  "
                  f"{s_full['max_drawdown']:>8.2%}  {s_is['sharpe']:>10.4f}  {s_oos['sharpe']:>11.4f}")

    # ── 10. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy":    "H054 — QQQ IBS Mean-Reversion: Standalone + Correlation to H037b",
        "description": (
            "Tests QQQ IBS mean-reversion (same rules as H037b but on QQQ). "
            "Key question: is monthly correlation to H037b (SPY IBS) low enough for diversification?"
        ),
        "parameters": {
            "ibs_buy":   IBS_BUY,
            "ibs_sell":  IBS_SELL,
            "max_hold":  MAX_HOLD,
            "gap_filter_b": GAP_FILTER_B,
            "gap_filter_c": GAP_FILTER_C,
        },
        "standalone_stats": {
            "spy_ibs_unfiltered":  s_spy_a,
            "h037b_spy_ibs_0.5":   s_spy_b,
            "h054a_qqq_unfiltered": s_qqq_a,
            "h054b_qqq_0.5":       s_qqq_b,
            "h054c_qqq_1.0":       s_qqq_c,
        },
        "trade_stats": {
            "h037b": trade_stats(t_spy_b),
            "h054b": trade_stats(t_qqq_b),
            "h054c": trade_stats(t_qqq_c),
        },
        "correlations": {
            "h054a_vs_h037b_monthly": round(corr_qa_sb, 4),
            "h054b_vs_h037b_monthly": round(corr_qb_sb, 4),
            "h054c_vs_h037b_monthly": round(corr_qc_sb, 4),
            "h054b_vs_h037b_oos":     round(corr_oos, 4),
            "reference_xlk_vs_h037b": 0.65,
        },
        "IS_OOS": {
            "h037b": {"IS": s_sb_is, "OOS": s_sb_oos, "degradation_pct": round(deg_sb, 2)},
            "h054b": {"IS": s_qb_is, "OOS": s_qb_oos, "degradation_pct": round(deg_qb, 2)},
        },
        "verdict": {
            "summary":             verdict,
            "standalone_ok":       standalone_ok,
            "correlation_low":     corr_low,
            "blend_benefit":       blend_ok,
            "monthly_corr_h054b":  round(corr_qb_sb, 4),
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h054_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
