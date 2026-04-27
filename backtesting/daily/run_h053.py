"""
H053 — SPY 200-Day MA Regime Filter on H041a
=============================================

Hypothesis: When SPY is below its 200-day moving average, the macro environment
is hostile to equity momentum. In those months, H041a should shift from equity
top-picks to holding IEF (intermediate Treasury) — the "flight to safety" that
H041a's momentum signal would eventually trigger anyway, but faster.

Implementation:
  Normal (SPY > 200MA): H041a runs as usual — rank-select top-2 from 7 assets
  Risk-off (SPY < 200MA): Hold IEF 100% regardless of rank signal

Hypothesis: Regime filter reduces drawdown and improves Sharpe vs unfiltered H041a.
Confirm criteria:
  - Filtered Sharpe > unfiltered Sharpe
  - Filtered MaxDD > unfiltered MaxDD (less negative, i.e. shallower)
  - OOS Sharpe (2018+) competitive with H041a OOS

Reject criteria:
  - Filtered Sharpe < unfiltered Sharpe AND MaxDD is not better
  - Filter triggers so frequently it just becomes a duration hold

Asset universe:
  H041a: SPY, QQQ, TLT, GLD, IEF, EFA, EEM (top-2, monthly)
  Regime: SPY 200-day MA (monthly, last business day)

Period: 2001-01-01 → 2026-04-27 (full H041a history)
IS/OOS: 2003-08 → 2017-12 (IS) / 2018-01 → 2026-04 (OOS)

Outputs:
  /workspace/agent/backtesting/results/h053_results.json
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

H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
TOP_N        = 2
RISK_OFF_HOLD = "IEF"   # hold this in risk-off months
MA_WINDOW    = 200       # days for moving average regime detection


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    # reuse H042/H043 cache
    for prefix_tag in ["h042_all", "h043_"]:
        test_key = "_".join(sorted(tickers)) + f"_{prefix_tag}_{start}_{end}"
        test_h   = hashlib.md5(test_key.encode()).hexdigest()[:12]
        for prefix in ["h042", "h043", "h052"]:
            cp = CACHE_DIR / f"{prefix}_{test_h}.parquet"
            if cp.exists():
                return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h053_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────────────────────────────────────
# Strategy builders
# ─────────────────────────────────────────────────────────────────────────────

def compute_spy_regime(prices_daily: pd.DataFrame) -> pd.Series:
    """
    Return monthly series: True = risk-on (SPY > 200MA), False = risk-off.
    Uses last trading day of each month.
    """
    spy = prices_daily["SPY"].dropna()
    ma  = spy.rolling(MA_WINDOW).mean()
    # Monthly: last day of each month
    spy_monthly = spy.resample("ME").last()
    ma_monthly  = ma.resample("ME").last()
    regime = (spy_monthly > ma_monthly)
    return regime


def h041a_unfiltered_equity_curve(prices: pd.DataFrame) -> pd.Series:
    """Standard H041a: rank-select top-2 monthly, no regime filter."""
    available = [a for a in H041A_ASSETS if a in prices.columns]
    if len(available) < TOP_N:
        return pd.Series(dtype=float)
    px = prices[available].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N
    equity = INITIAL_EQUITY
    series = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = sum(
                weight * (float(sub[sym].iloc[j]) / float(sub[sym].iloc[j-1]) - 1)
                for sym in top
                if float(sub[sym].iloc[j-1]) > 0 and not np.isnan(sub[sym].iloc[j-1]) and not np.isnan(sub[sym].iloc[j])
            )
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def h053_filtered_equity_curve(prices: pd.DataFrame, regime: pd.Series) -> tuple:
    """
    H053: H041a with SPY 200MA regime filter.
    In risk-off months (SPY < 200MA), hold IEF instead of top-2.
    Returns (equity_curve, monthly_mode_log).
    """
    available = [a for a in H041A_ASSETS if a in prices.columns]
    if len(available) < TOP_N or RISK_OFF_HOLD not in prices.columns:
        return pd.Series(dtype=float), []
    px = prices[available].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N
    equity   = INITIAL_EQUITY
    series   = []
    mode_log = []  # (month, "risk_on"/"risk_off", holdings)

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        # get regime for this month (use prior month's close to avoid lookahead)
        signal_month = monthly_px.index[i - 1]
        is_risk_on = bool(regime.get(signal_month, True))  # default risk-on if no signal

        if is_risk_on:
            mom_row = mom_12.iloc[i].dropna()
            vol_row = vol_6.iloc[i].dropna()
            valid   = mom_row.index.intersection(vol_row.index)
            if len(valid) < TOP_N:
                continue
            score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
            top   = list(score.nlargest(TOP_N).index)
            mode  = "risk_on"
        else:
            top  = [RISK_OFF_HOLD]
            mode = "risk_off"

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[list(set(top))].loc[sub_start:month_end] if set(top).issubset(set(available)) else None
        if sub is None or len(sub) < 2:
            # fallback: use IEF returns from full prices
            ief_sub = prices[RISK_OFF_HOLD].loc[sub_start:month_end]
            if len(ief_sub) < 2:
                continue
            for j in range(1, len(ief_sub)):
                p0, p1 = float(ief_sub.iloc[j-1]), float(ief_sub.iloc[j])
                equity *= (1 + (p1/p0 - 1)) if p0 > 0 else 1.0
                series.append((ief_sub.index[j], equity))
            mode_log.append((str(month_end.date()), mode, top))
            continue

        w = 1.0 / len(top)
        for j in range(1, len(sub)):
            port_ret = sum(
                w * (float(sub[sym].iloc[j]) / float(sub[sym].iloc[j-1]) - 1)
                for sym in top
                if float(sub[sym].iloc[j-1]) > 0 and not np.isnan(sub[sym].iloc[j-1]) and not np.isnan(sub[sym].iloc[j])
            )
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))
        mode_log.append((str(month_end.date()), mode, top))

    if not series:
        return pd.Series(dtype=float), mode_log
    return (
        pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series])),
        mode_log,
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


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H053 — SPY 200-Day MA Regime Filter on H041a")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = list(set(H041A_ASSETS))
    prices = fetch_close(all_tickers, FULL_START, FULL_END, tag="h042_all")
    print(f"   Tickers: {sorted(prices.columns.tolist())}")
    print(f"   Period:  {prices.index[0].date()} → {prices.index[-1].date()} ({len(prices)} days)")

    # ── 2. Compute regime signal ──────────────────────────────────────────────
    print("\n[2] Computing SPY 200-day MA regime …")
    regime = compute_spy_regime(prices)
    risk_off_months = (~regime).sum()
    risk_on_months  = regime.sum()
    print(f"   Total months: {len(regime)}  |  Risk-on: {risk_on_months}  |  Risk-off: {risk_off_months} ({risk_off_months/len(regime)*100:.1f}%)")

    # Check coverage in our backtesting window
    window_regime = regime[(regime.index >= pd.Timestamp(WINDOW_START))]
    risk_off_window = (~window_regime).sum()
    print(f"   Backtest window risk-off months: {risk_off_window} of {len(window_regime)} ({risk_off_window/len(window_regime)*100:.1f}%)")
    # List risk-off months for reference
    risk_off_dates = [str(d.date()) for d in window_regime[~window_regime].index[:20]]
    print(f"   First 20 risk-off months: {risk_off_dates}")

    # ── 3. Build equity curves ────────────────────────────────────────────────
    print("\n[3] Building equity curves …")
    eq_unfiltered = h041a_unfiltered_equity_curve(prices)
    eq_filtered, mode_log = h053_filtered_equity_curve(prices, regime)

    print(f"   H041a unfiltered: {eq_unfiltered.index[0].date()} → {eq_unfiltered.index[-1].date()} ({len(eq_unfiltered)} days)")
    print(f"   H053  filtered  : {eq_filtered.index[0].date()} → {eq_filtered.index[-1].date()} ({len(eq_filtered)} days)")

    # ── 4. Monthly returns ────────────────────────────────────────────────────
    r_unfiltered = to_monthly_returns(eq_unfiltered)
    r_filtered   = to_monthly_returns(eq_filtered)

    window_ts = pd.Timestamp(WINDOW_START)
    common = r_unfiltered.index.intersection(r_filtered.index)
    common = common[common >= window_ts]

    r_uf = r_unfiltered.loc[common]
    r_f  = r_filtered.loc[common]

    print(f"\n   Common window: {common[0].date()} → {common[-1].date()} ({len(common)} months)")

    # ── 5. Full-period stats ──────────────────────────────────────────────────
    print("\n[4] Full-period statistics …")
    s_uf   = stats_from_monthly_returns(r_uf, "H041a unfiltered")
    s_f    = stats_from_monthly_returns(r_f,  "H053 200MA filtered")
    print(f"   H041a unfiltered: CAGR {s_uf['cagr']:.2%}  Sharpe {s_uf['sharpe']:.4f}  MaxDD {s_uf['max_drawdown']:.2%}")
    print(f"   H053  filtered  : CAGR {s_f['cagr']:.2%}  Sharpe {s_f['sharpe']:.4f}  MaxDD {s_f['max_drawdown']:.2%}")

    sharpe_delta = s_f['sharpe'] - s_uf['sharpe']
    maxdd_delta  = s_f['max_drawdown'] - s_uf['max_drawdown']
    print(f"   Delta Sharpe: {sharpe_delta:+.4f}  Delta MaxDD: {maxdd_delta:+.4f} (positive MaxDD delta = shallower drawdown)")

    # ── 6. IS / OOS split ────────────────────────────────────────────────────
    print("\n[5] IS / OOS split …")
    is_ts  = pd.Timestamp(IS_END)
    oos_ts = pd.Timestamp(OOS_START)

    is_idx  = common[(common >= window_ts) & (common <= is_ts)]
    oos_idx = common[common >= oos_ts]

    s_uf_is  = stats_from_monthly_returns(r_uf.loc[is_idx],  "H041a IS")
    s_f_is   = stats_from_monthly_returns(r_f.loc[is_idx],   "H053 IS")
    s_uf_oos = stats_from_monthly_returns(r_uf.loc[oos_idx], "H041a OOS")
    s_f_oos  = stats_from_monthly_returns(r_f.loc[oos_idx],  "H053 OOS")

    print(f"   IS  (2003-2017): H041a Sharpe {s_uf_is['sharpe']:.4f}  H053 {s_f_is['sharpe']:.4f}  Delta {s_f_is['sharpe']-s_uf_is['sharpe']:+.4f}")
    print(f"   OOS (2018-2026): H041a Sharpe {s_uf_oos['sharpe']:.4f}  H053 {s_f_oos['sharpe']:.4f}  Delta {s_f_oos['sharpe']-s_uf_oos['sharpe']:+.4f}")

    # ── 7. Regime breakdown ───────────────────────────────────────────────────
    print("\n[6] Regime breakdown …")
    # Monthly returns in risk-on vs risk-off months
    regime_window = regime[(regime.index >= window_ts) & (regime.index <= common[-1])]
    risk_on_idx  = [d for d in common if regime.get(d, True)]
    risk_off_idx = [d for d in common if not regime.get(d, True)]

    r_h041a_risk_on  = r_uf.loc[[d for d in risk_on_idx  if d in r_uf.index]]
    r_h041a_risk_off = r_uf.loc[[d for d in risk_off_idx if d in r_uf.index]]

    if len(r_h041a_risk_on) > 0:
        on_mean  = float(r_h041a_risk_on.mean())  * 12
        off_mean = float(r_h041a_risk_off.mean()) * 12 if len(r_h041a_risk_off) > 0 else 0
        print(f"   H041a annualized return — risk-on months: {on_mean:.2%}  risk-off months: {off_mean:.2%}")
        print(f"   Risk-off months: {len(risk_off_idx)} of {len(common)} ({len(risk_off_idx)/len(common)*100:.1f}%)")
        print(f"   IEF held in risk-off → dragged H041a up/down in those months: {off_mean - r_h041a_risk_off.mean()*12 if len(r_h041a_risk_off) > 0 else 0:.2%}")

    # ── 8. Correlation check ──────────────────────────────────────────────────
    corr = float(r_uf.corr(r_f))
    print(f"\n   H041a vs H053 monthly return correlation: {corr:.4f}")

    # ── 9. Verdict ────────────────────────────────────────────────────────────
    print("\n[7] Verdict …")
    sharpe_improves = s_f['sharpe'] > s_uf['sharpe']
    maxdd_improves  = s_f['max_drawdown'] > s_uf['max_drawdown']
    oos_competes    = s_f_oos['sharpe'] > s_uf_oos['sharpe'] - 0.05

    if sharpe_improves and maxdd_improves:
        verdict = "CONFIRMED — 200MA filter improves both Sharpe and MaxDD"
    elif sharpe_improves:
        verdict = "PARTIALLY CONFIRMED — Sharpe improved but MaxDD not improved"
    elif maxdd_improves and abs(sharpe_delta) < 0.05:
        verdict = "PARTIALLY CONFIRMED — MaxDD improved, Sharpe neutral (acceptable trade-off)"
    else:
        verdict = "REJECTED — 200MA filter does not improve H041a risk-adjusted returns"

    if oos_competes:
        oos_note = f"OOS competitive (H053={s_f_oos['sharpe']:.4f} vs H041a={s_uf_oos['sharpe']:.4f})"
    else:
        oos_note = f"OOS degraded (H053={s_f_oos['sharpe']:.4f} vs H041a={s_uf_oos['sharpe']:.4f})"

    print(f"   Sharpe improves: {sharpe_improves}  ({sharpe_delta:+.4f})")
    print(f"   MaxDD improves:  {maxdd_improves}  ({maxdd_delta:+.4f})")
    print(f"   OOS: {oos_note}")
    print(f"\n   Verdict: {verdict}")

    # ── 10. Summary table ─────────────────────────────────────────────────────
    print(f"\n{'=' * 92}")
    print("  H053 — SPY 200MA REGIME FILTER ON H041a — SUMMARY")
    print(f"{'=' * 92}")
    print(f"  {'Scenario':<40}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'Calmar':>8}  {'Months':>7}")
    print(f"  {'-'*90}")
    for label, s, nm in [
        ("H041a  unfiltered  — full period",  s_uf,     len(common)),
        ("H053   filtered    — full period",  s_f,      len(common)),
        ("H041a  unfiltered  — IS (2003-17)", s_uf_is,  len(is_idx)),
        ("H053   filtered    — IS (2003-17)", s_f_is,   len(is_idx)),
        ("H041a  unfiltered  — OOS (2018+)",  s_uf_oos, len(oos_idx)),
        ("H053   filtered    — OOS (2018+)",  s_f_oos,  len(oos_idx)),
    ]:
        if "error" in s:
            print(f"  {label:<40}  {'ERROR':>8}")
        else:
            print(f"  {label:<40}  {s['cagr']:>8.2%}  {s['sharpe']:>8.4f}  {s['max_drawdown']:>8.2%}  {s['calmar']:>8.3f}  {nm:>7}")

    # ── 11. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy":    "H053 — SPY 200-Day MA Regime Filter on H041a",
        "description": (
            "Tests whether applying a SPY 200-day MA filter to H041a improves "
            "risk-adjusted returns. In risk-off months (SPY < 200MA), hold IEF "
            "instead of the momentum top-2."
        ),
        "parameters": {
            "ma_window":    MA_WINDOW,
            "risk_off_hold": RISK_OFF_HOLD,
            "assets":       H041A_ASSETS,
            "top_n":        TOP_N,
        },
        "regime_stats": {
            "total_months_window":    len(window_regime),
            "risk_off_months_window": int(risk_off_window),
            "risk_off_pct":           round(risk_off_window / len(window_regime) * 100, 1),
        },
        "full_period_stats": {
            "h041a_unfiltered":  s_uf,
            "h053_filtered":     s_f,
            "sharpe_delta":      round(sharpe_delta, 4),
            "maxdd_delta":       round(maxdd_delta,  4),
        },
        "IS_OOS_stats": {
            "IS":  {"h041a": s_uf_is,  "h053": s_f_is},
            "OOS": {"h041a": s_uf_oos, "h053": s_f_oos},
        },
        "correlation_unfiltered_vs_filtered": round(corr, 4),
        "verdict": {
            "summary":         verdict,
            "oos_note":        oos_note,
            "sharpe_improves": sharpe_improves,
            "maxdd_improves":  maxdd_improves,
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h053_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
