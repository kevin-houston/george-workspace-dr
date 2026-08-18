"""
H519 — SPY 200MA / VIX Macro Regime Gate on H045 Bond ETF Rotation
=====================================================================

Question: Does a simple external equity-market regime gate (SPY 200-day MA
and/or VIX threshold) improve H045's Treasury ETF momentum rotation?

This is a genuinely untested combination. Prior bond-universe regime-gate
attempts used bond-specific signals:
  - H314 (duration-factor / yield-curve gate) — NOT CONFIRMED, redundant
    with momentum's own duration handling
  - H315 (credit-regime gate via BAMLH0A0HYM2) — NOT CONFIRMED, insufficient
    FRED history (only from June 2023)

Neither tested the same simple SPY-200MA/VIX construction that worked for
H301 (sector ETF rotation, +27.4% OOS Sharpe) and H362 (low-vol ETF rotation,
29% MaxDD improvement). This hypothesis applies that exact construction to
H045 instead.

Counter-precedent (reason to expect failure): H053 found the same SPY 200MA
gate REJECTED on H041a because H041a's own momentum signal already rotates
into defensive assets ahead of drawdowns — an external equity gate was
redundant/harmful. H045's own write-up shows near-identical behavior: in
2022's rate shock, the rotation signal moved into SHY via its own 12m
momentum without any external gate ("TLT was almost never selected").
This makes H045 look more like the H041a case (endogenous regime-awareness
already present) than the H301/H362 case (rotation among similarly-behaved
risk assets with no defensive escape hatch) — but that's a hypothesis to
test, not assume.

Universe: SHY/IEI/IEF/TLT/TIP/HYG/LQD (identical to H045)
Signal:   rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50, monthly
          rebalance — IDENTICAL to H045, unchanged.
Gate (applied at each monthly rebalance, using prior trading day's close —
      no look-ahead):
  Variant A: SPY < 200-day MA  → route 100% to SHY (cash-like proxy)
  Variant B: VIX > 25          → route 100% to SHY
  Variant C: SPY < 200MA AND VIX > 25 (joint, both must fire) → SHY
  Variant D: SPY < 200MA OR  VIX > 25 (either fires)          → SHY

IS: 2007-2016  |  OOS: 2017-2026 (matches H045 exactly)
Benchmark: H045 ungated OOS Sharpe 1.351, MaxDD -6.28% (recomputed here,
           not reused stale, to guarantee an apples-to-apples comparison)

Gate for "worth adopting": beats H045 ungated on EITHER Sharpe by a
meaningful margin (>0.10) OR MaxDD by >2pp, without meaningfully hurting
the other dimension (degeneracy check: gated variant must still hold
risk assets >50% of OOS months, else it's just parking in cash).
"""

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from collections import defaultdict

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START   = "2002-01-01"
FULL_END     = "2026-04-27"
WINDOW_START = "2007-01-01"
IS_END       = "2016-12-31"
OOS_START    = "2017-01-01"

BOND_UNIVERSE = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
CASH_PROXY    = "SHY"
GATE_ASSETS   = ["SPY", "^VIX"]
TOP_N         = 2


def fetch_close(tickers, start, end, tag=""):
    import hashlib
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    cp = CACHE_DIR / f"h519_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def stats_from_monthly_returns(monthly_rets, label=""):
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 6:
        return {"error": "insufficient data", "label": label}
    equity = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd = float((equity / roll_max - 1).min())
    calmar = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "label": label, "cagr": round(float(cagr), 4), "sharpe": round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4), "calmar": round(float(calmar), 4),
        "ann_vol": round(float(vol), 4), "n_months": len(monthly_rets),
        "start": str(monthly_rets.index[0].date()), "end": str(monthly_rets.index[-1].date()),
    }


def to_monthly_returns(eq_daily):
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


def h045_gated_equity_curve(prices, gate_signal, start, end, track_holdings=False):
    """
    Same rank(12m_mom)+rank(inv_6m_vol) top-2 50/50 monthly rotation as H045,
    but if gate_signal.loc[rebal_date] is True (risk-off), route 100% to SHY
    for that month instead of the top-2 picks.

    gate_signal: daily boolean Series, True = gate fires (go defensive).
                 Value used is as-of the prior trading day's close relative
                 to the rebalance decision date (no look-ahead).
    """
    available = [a for a in BOND_UNIVERSE if a in prices.columns]
    px = prices[available].loc[start:end].dropna(how="all")
    if px.empty:
        return pd.Series(dtype=float), []

    monthly_px = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6 = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / TOP_N
    equity = INITIAL_EQUITY
    series = []
    holdings_log = []
    gate_fire_count = 0
    total_months = 0

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N:
            continue

        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top = list(score.nlargest(TOP_N).index)

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px.loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        # Gate decision: use the LAST gate_signal value strictly before sub_start
        # (i.e. known as of the close before this holding period begins) — no look-ahead.
        prior_gate = gate_signal.loc[:sub_start - pd.Timedelta(days=1)]
        gated = bool(prior_gate.iloc[-1]) if len(prior_gate) > 0 else False

        total_months += 1
        if gated:
            gate_fire_count += 1
            holdings_this_month = [CASH_PROXY]
            month_weight = 1.0
        else:
            holdings_this_month = top
            month_weight = weight

        if track_holdings:
            holdings_log.append({
                "month": str(month_end.date()),
                "holdings": holdings_this_month,
                "gated": gated,
            })

        for j in range(1, len(sub)):
            port_ret = 0.0
            if gated:
                p0 = float(sub[CASH_PROXY].iloc[j - 1]) if CASH_PROXY in sub.columns else np.nan
                p1 = float(sub[CASH_PROXY].iloc[j]) if CASH_PROXY in sub.columns else np.nan
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret = p1 / p0 - 1
            else:
                for sym in holdings_this_month:
                    p0 = float(sub[sym].iloc[j - 1])
                    p1 = float(sub[sym].iloc[j])
                    if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                        port_ret += month_weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float), holdings_log

    eq_curve = pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))
    gate_frac = gate_fire_count / total_months if total_months > 0 else 0.0
    return eq_curve, holdings_log, gate_frac


def main():
    print("\n" + "=" * 80)
    print("H519 — SPY 200MA / VIX Macro Regime Gate on H045 Bond Rotation")
    print("=" * 80)

    print("\n[1] Fetching price data …")
    bond_tickers = BOND_UNIVERSE
    prices = fetch_close(bond_tickers, FULL_START, FULL_END, tag="h519_bonds")
    gate_prices = fetch_close(GATE_ASSETS, FULL_START, FULL_END, tag="h519_gate")

    spy = gate_prices["SPY"].dropna()
    vix = gate_prices["^VIX"].dropna()
    spy_200ma = spy.rolling(200).mean()

    spy_below_200ma = (spy < spy_200ma).reindex(prices.index).ffill().fillna(False)
    vix_above_25 = (vix > 25).reindex(prices.index).ffill().fillna(False)
    vix_above_20 = (vix > 20).reindex(prices.index).ffill().fillna(False)

    gates = {
        "A_spy200ma":      spy_below_200ma,
        "B_vix25":         vix_above_25,
        "C_joint_and":     spy_below_200ma & vix_above_25,
        "D_either_or":     spy_below_200ma | vix_above_20,
    }

    # ── Baseline: H045 ungated, recomputed here for apples-to-apples ──────────
    print("\n[2] Recomputing H045 ungated baseline …")
    no_gate = pd.Series(False, index=prices.index)
    eq_base_full, _, _ = h045_gated_equity_curve(prices, no_gate, WINDOW_START, FULL_END, track_holdings=True)
    eq_base_is, _, _   = h045_gated_equity_curve(prices, no_gate, WINDOW_START, IS_END, track_holdings=False)
    eq_base_oos, _, _  = h045_gated_equity_curve(prices, no_gate, OOS_START, FULL_END, track_holdings=False)

    s_base_is  = stats_from_monthly_returns(to_monthly_returns(eq_base_is), "H045 baseline IS")
    s_base_oos = stats_from_monthly_returns(to_monthly_returns(eq_base_oos), "H045 baseline OOS")

    print(f"   Baseline IS:  Sharpe={s_base_is.get('sharpe')}  MaxDD={s_base_is.get('max_drawdown')}")
    print(f"   Baseline OOS: Sharpe={s_base_oos.get('sharpe')}  MaxDD={s_base_oos.get('max_drawdown')}")

    # ── Gated variants ──────────────────────────────────────────────────────
    print("\n[3] Running gated variants …")
    variant_results = {}
    for name, gate_signal in gates.items():
        eq_is, _, gf_is = h045_gated_equity_curve(prices, gate_signal, WINDOW_START, IS_END, track_holdings=False)
        eq_oos, holdings_oos, gf_oos = h045_gated_equity_curve(prices, gate_signal, OOS_START, FULL_END, track_holdings=True)

        s_is = stats_from_monthly_returns(to_monthly_returns(eq_is), f"{name} IS")
        s_oos = stats_from_monthly_returns(to_monthly_returns(eq_oos), f"{name} OOS")

        variant_results[name] = {
            "is": s_is, "oos": s_oos,
            "gate_fire_frac_is": round(gf_is, 4),
            "gate_fire_frac_oos": round(gf_oos, 4),
            "sharpe_delta_oos": round(s_oos.get("sharpe", 0) - s_base_oos.get("sharpe", 0), 4),
            "maxdd_delta_oos_pp": round((s_oos.get("max_drawdown", 0) - s_base_oos.get("max_drawdown", 0)) * 100, 2),
        }
        print(f"   {name}: OOS Sharpe={s_oos.get('sharpe')}  MaxDD={s_oos.get('max_drawdown')}  "
              f"gate_fired={gf_oos:.1%} of months  ΔSharpe={variant_results[name]['sharpe_delta_oos']:+.3f}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    best_variant = max(variant_results.items(), key=lambda kv: kv[1]["oos"].get("sharpe", -99))
    best_name, best_stats = best_variant
    sharpe_improved = best_stats["sharpe_delta_oos"] > 0.10
    maxdd_improved = best_stats["maxdd_delta_oos_pp"] > 2.0
    degenerate = best_stats["gate_fire_frac_oos"] > 0.95 or best_stats["gate_fire_frac_oos"] < 0.005

    if degenerate:
        verdict = "NOT CONFIRMED (degenerate — gate fires almost never or almost always)"
    elif sharpe_improved or maxdd_improved:
        if sharpe_improved and best_stats["sharpe_delta_oos"] > 0 and best_stats["maxdd_delta_oos_pp"] >= -1.0:
            verdict = "CONFIRMED"
        else:
            verdict = "PARTIAL"
    else:
        verdict = "NOT CONFIRMED"

    print(f"\n  Best variant: {best_name}  ΔSharpe={best_stats['sharpe_delta_oos']:+.3f}  "
          f"ΔMaxDD={best_stats['maxdd_delta_oos_pp']:+.2f}pp")
    print(f"  Verdict: {verdict}")

    output = {
        "strategy": "H519 — SPY 200MA / VIX Macro Regime Gate on H045 Bond Rotation",
        "universe": BOND_UNIVERSE,
        "gate_variants": list(gates.keys()),
        "baseline": {"is": s_base_is, "oos": s_base_oos},
        "variants": variant_results,
        "best_variant": best_name,
        "verdict": verdict,
        "run_date": "2026-08-17",
    }

    out_path = RESULT_DIR / "h519_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved -> {out_path}")
    return output


if __name__ == "__main__":
    main()
