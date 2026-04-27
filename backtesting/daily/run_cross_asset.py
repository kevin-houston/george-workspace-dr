"""
Cross-asset robustness validation for H016 (Momentum+Carry) and H006 (Dual Momentum).

Principle: if the edge is real, it should survive universe substitution.
If it only works on the original SPY/TLT/GLD trio — likely overfit.

H016 universes tested:
  A (original)  : SPY, TLT, GLD  → SHY
  B (equity rot): SPY, QQQ, IWM  → SHY
  C (global)    : SPY, EFA, EEM  → SHY
  D (macro alt) : QQQ, TLT, GLD  → SHY
  E (bonds+gold): IEF, TLT, GLD  → SHY
  F (all-macro) : SPY, TLT, GLD, IEF, QQQ  → SHY  (top 2 from 5)

H006 universes tested:
  A (original)  : US sectors (XLK … XLU) vs SPY, safe=BIL
  B (global)    : VTI, EFA, EEM, VWO vs QQQ, safe=BIL
  C (factors)   : VUG, VTV, VBR, VBK vs SPY, safe=BIL
  D (sectors v2): Replace BIL with IEF (intermediate bonds) as safe haven
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

START = "2007-01-01"
END   = "2026-04-01"
INITIAL_EQUITY = 100_000.0

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# Data layer
# ─────────────────────────────────────────────

def _cache_path(tickers: list[str], start: str, end: str) -> Path:
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    import hashlib
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"xasset_{h}.parquet"


def fetch_prices(tickers: list[str], start: str = START, end: str = END) -> pd.DataFrame:
    cp = _cache_path(tickers, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series) -> dict:
    if len(eq) < 10:
        return {"error": "insufficient data"}
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1 if n_years > 0 else 0
    vol  = rets.std() * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    dd = (eq / roll_max - 1)
    max_dd = dd.min()
    calmar = abs(cagr / max_dd) if max_dd < 0 else 0
    return {
        "cagr":         round(cagr, 4),
        "sharpe":       round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "calmar":       round(calmar, 4),
        "n_years":      round(n_years, 1),
    }


# ─────────────────────────────────────────────
# H016 engine
# ─────────────────────────────────────────────

def run_h016_universe(
    label: str,
    assets: list[str],
    cash_etf: str,
    start: str = START,
    end: str   = END,
    top_n: int = 2,
) -> dict:
    all_syms = sorted(set(assets + [cash_etf]))
    prices   = fetch_prices(all_syms, start, end)

    # Drop any ticker that has <2 years of data
    available = [s for s in assets if s in prices.columns and prices[s].dropna().shape[0] > 500]
    if len(available) < top_n + 1:
        return {"error": f"only {len(available)} assets available — need ≥{top_n+1}"}

    asset_px  = prices[available].dropna(how="all")
    cash_px   = prices[cash_etf] if cash_etf in prices.columns else None

    monthly_px   = asset_px.resample("ME").last()
    monthly_rets = asset_px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6_monthly = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12        = monthly_px / monthly_px.shift(12) - 1

    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6_monthly.iloc[i].dropna()

        valid = mom_row.index.intersection(vol_row.index)
        if len(valid) < top_n + 1:
            continue

        mom_rank = mom_row[valid].rank()
        inv_vol  = vol_row[valid].rank(ascending=False)
        combined = (mom_rank + inv_vol)
        top      = list(combined.nlargest(top_n).index)
        rest     = [s for s in valid if s not in top]

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub       = prices[all_syms].loc[sub_start:month_end].dropna(how="all")
        if len(sub) < 2:
            continue

        cash_weight = len(rest) / len(valid)

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                if sym in sub.columns:
                    p0, p1 = float(sub[sym].iloc[j - 1]), float(sub[sym].iloc[j])
                    if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                        port_ret += (p1 / p0 - 1) / top_n
            if cash_weight > 0 and cash_px is not None:
                p0 = float(cash_px.loc[sub.index[j - 1]] if sub.index[j-1] in cash_px.index else np.nan)
                p1 = float(cash_px.loc[sub.index[j]] if sub.index[j] in cash_px.index else np.nan)
                if not np.isnan(p0) and not np.isnan(p1) and p0 > 0:
                    port_ret += cash_weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if len(series) < 50:
        return {"error": "too few data points"}

    eq = pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))
    return calc_stats(eq)


# ─────────────────────────────────────────────
# H006 engine (dual momentum)
# ─────────────────────────────────────────────

def run_h006_universe(
    label: str,
    risky_assets: list[str],
    benchmark_asset: str,
    safe_asset: str,
    start: str = START,
    end:   str = END,
    top_n: int = 3,
    lookback: int = 12,
) -> dict:
    all_syms = sorted(set(risky_assets + [benchmark_asset, safe_asset]))
    prices   = fetch_prices(all_syms, start, end)

    available = [s for s in risky_assets if s in prices.columns and prices[s].dropna().shape[0] > 500]
    if len(available) < top_n:
        return {"error": f"only {len(available)} risky assets available — need ≥{top_n}"}

    closes = prices.copy()
    equity = INITIAL_EQUITY
    series = []

    # Monthly rebalance
    monthly_end_dates = closes.resample("ME").last().index

    for i in range(lookback, len(monthly_end_dates)):
        month_end = monthly_end_dates[i]
        lb_start  = monthly_end_dates[i - lookback]

        # Absolute momentum: is benchmark above its own return?
        if benchmark_asset not in closes.columns:
            continue
        bm_now  = closes[benchmark_asset].asof(month_end)
        bm_then = closes[benchmark_asset].asof(lb_start)
        abs_mom_positive = (bm_now > bm_then)

        # Cross-sectional momentum: rank risky assets by lookback return
        rets = {}
        for s in available:
            if s not in closes.columns:
                continue
            p_now  = closes[s].asof(month_end)
            p_then = closes[s].asof(lb_start)
            if p_now > 0 and p_then > 0:
                rets[s] = p_now / p_then - 1

        if len(rets) < top_n:
            continue

        ranked = sorted(rets.items(), key=lambda x: -x[1])
        winners = [s for s, _ in ranked[:top_n] if rets[s] > 0]  # positive momentum required

        # Apply weights for the following month
        if not abs_mom_positive or not winners:
            # All to safe haven
            chosen = {safe_asset: 1.0}
        else:
            chosen = {s: 1.0 / len(winners) for s in winners}

        sub_start = month_end + pd.Timedelta(days=1)
        sub_end   = monthly_end_dates[i + 1] if i + 1 < len(monthly_end_dates) else pd.Timestamp(end)
        sub = closes.loc[sub_start:sub_end].dropna(how="all")
        if len(sub) < 2:
            continue

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym, w in chosen.items():
                if sym in sub.columns:
                    p0, p1 = float(sub[sym].iloc[j-1]), float(sub[sym].iloc[j])
                    if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                        port_ret += w * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if len(series) < 50:
        return {"error": "too few data points"}

    eq = pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))
    return calc_stats(eq)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

H016_UNIVERSES = [
    ("A — original (SPY/TLT/GLD)",        ["SPY", "TLT", "GLD"],           "SHY",  2),
    ("B — equity rotation (SPY/QQQ/IWM)", ["SPY", "QQQ", "IWM"],           "SHY",  2),
    ("C — global equity (SPY/EFA/EEM)",   ["SPY", "EFA", "EEM"],           "SHY",  2),
    ("D — macro alt (QQQ/TLT/GLD)",       ["QQQ", "TLT", "GLD"],           "SHY",  2),
    ("E — bonds+gold (IEF/TLT/GLD)",      ["IEF", "TLT", "GLD"],           "SHY",  2),
    ("F — 5-asset macro top-2",           ["SPY", "QQQ", "TLT", "GLD", "IEF"], "SHY",  2),
]

H006_UNIVERSES = [
    ("A — original (US sectors / BIL)",
     ["XLK","XLF","XLV","XLE","XLY","XLP","XLI","XLU","XLB"], "SPY", "BIL"),
    ("B — global ETFs (VTI/EFA/EEM/VWO / BIL)",
     ["VTI","EFA","EEM","VWO"], "VTI", "BIL"),
    ("C — factor ETFs (VUG/VTV/VBR/VBK / BIL)",
     ["VUG","VTV","VBR","VBK"], "SPY", "BIL"),
    ("D — US sectors / IEF safe haven",
     ["XLK","XLF","XLV","XLE","XLY","XLP","XLI","XLU","XLB"], "SPY", "IEF"),
]

SPY_BENCHMARK = {
    "A — original (SPY/TLT/GLD)": "SPY",
    "B — equity rotation (SPY/QQQ/IWM)": "SPY",
}


def print_table(label: str, rows: list[tuple[str, dict]]):
    print(f"\n{'═'*82}")
    print(f"  {label}")
    print(f"{'═'*82}")
    print(f"  {'Universe':<42} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} {'Yrs':>5}")
    print(f"  {'─'*42} {'─'*7} {'─'*7} {'─'*8} {'─'*7} {'─'*5}")
    for name, m in rows:
        if "error" in m:
            print(f"  {name:<42}  ERROR: {m['error']}")
        else:
            flag = " ✓" if m["sharpe"] > 0.5 and m["cagr"] > 0.08 else ("  " if m["sharpe"] > 0.3 else " ✗")
            print(f"  {name:<42} {m['cagr']:>7.2%} {m['sharpe']:>7.3f} {m['max_drawdown']:>8.2%} {m['calmar']:>7.3f} {m['n_years']:>5.1f}{flag}")
    print(f"{'═'*82}")
    print("  ✓ = CAGR>8% + Sharpe>0.5  ✗ = Sharpe<0.3  (blank = mid-range)")


def main():
    print("Cross-Asset Robustness Validation")
    print("Principle: a real edge generalizes — overfit edges don't.\n")

    # ── H016 ──
    print("\n[H016] Momentum+Carry Blend — testing signal across 6 universes")
    h016_rows = []
    h016_results = {}
    for name, assets, cash, top_n in H016_UNIVERSES:
        print(f"  Running {name} …", end=" ", flush=True)
        m = run_h016_universe(name, assets, cash, top_n=top_n)
        h016_rows.append((name, m))
        h016_results[name] = m
        status = f"CAGR {m.get('cagr', 'ERR'):.2%}  Sharpe {m.get('sharpe', 'ERR'):.3f}" if "error" not in m else f"ERROR: {m['error']}"
        print(status)

    print_table("H016 — Momentum+Carry across universes", h016_rows)

    # ── H006 ──
    print("\n[H006] Dual Momentum — testing signal across 4 universes")
    h006_rows = []
    h006_results = {}
    for name, risky, bm, safe in H006_UNIVERSES:
        print(f"  Running {name} …", end=" ", flush=True)
        m = run_h006_universe(name, risky, bm, safe)
        h006_rows.append((name, m))
        h006_results[name] = m
        status = f"CAGR {m.get('cagr', 'ERR'):.2%}  Sharpe {m.get('sharpe', 'ERR'):.3f}" if "error" not in m else f"ERROR: {m['error']}"
        print(status)

    print_table("H006 — Dual Momentum across universes", h006_rows)

    # ── Verdict ──
    h016_pass = sum(1 for _, m in h016_rows if "error" not in m and m["sharpe"] > 0.4)
    h006_pass = sum(1 for _, m in h006_rows if "error" not in m and m["sharpe"] > 0.4)
    h016_total = sum(1 for _, m in h016_rows if "error" not in m)
    h006_total = sum(1 for _, m in h006_rows if "error" not in m)

    print(f"\n{'─'*82}")
    print(f"  VERDICT")
    print(f"  H016: {h016_pass}/{h016_total} universes pass (Sharpe > 0.4)")
    print(f"  H006: {h006_pass}/{h006_total} universes pass (Sharpe > 0.4)")
    if h016_pass >= h016_total * 0.6:
        print("  H016 → GENERALIZES  (majority of universes produce positive edge)")
    else:
        print("  H016 → OVERFIT WARNING  (edge does not survive universe substitution)")
    if h006_pass >= h006_total * 0.6:
        print("  H006 → GENERALIZES")
    else:
        print("  H006 → OVERFIT WARNING")
    print(f"{'─'*82}")

    # Save results
    out = {
        "h016": {name: m for name, m in h016_rows},
        "h006": {name: m for name, m in h006_rows},
        "verdict": {
            "h016_pass_rate": f"{h016_pass}/{h016_total}",
            "h006_pass_rate": f"{h006_pass}/{h006_total}",
        }
    }
    out_path = Path(__file__).parent / "cross_asset_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")

    return out


if __name__ == "__main__":
    main()
