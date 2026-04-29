"""
H118 — Volatility-Targeted Weight Scaling
==========================================

H116 baseline: fixed weights H041a=22%, H026=27%, H045=21% (+ IBS 30%).
H118 hypothesis: dynamically scale each rotation sub-strategy's monthly
weight by (target_vol / realized_6m_vol). When a sub-strategy is more
volatile than usual, reduce its allocation; when calmer, increase it.

This is AQR-style vol targeting applied at the sub-strategy level.

Variants tested:
  A) Baseline H116 (fixed weights)
  B) Vol-target on all three rotation subs (clamp 0.5x–2x base)
  C) Risk parity: weight ∝ 1/vol (renorm to 70% total rotation allocation)
  D) Vol-target on H026 only (highest-vol sub)
  E) Vol-target on H041a+H026 only (IBS and H045 fixed)

H116 baseline: OOS 6.5635, AltOOS 14.9411, MaxDD -3.6%, NegYrs 0
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2003-01-01"
FULL_END   = "2026-04-27"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

IBS_CFGS = {
    "XLK": (0.15, 0.90, 7, -0.010),
    "SMH": (0.20, 0.75, 6, -0.005),
    "IGV": (0.30, 0.75, 5,  0.0025),
}
BASE_WEIGHTS = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
                "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}
ROTATION_TOTAL = BASE_WEIGHTS["h041a"] + BASE_WEIGHTS["h026"] + BASE_WEIGHTS["h045"]  # 0.70

_PREFIXES = [f"h{i:03d}" for i in range(62, 119)]


# ── Data helpers ──────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h118_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h118_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ── Strategy builders ─────────────────────────────────────────────────────────

def build_rotation(tickers, start, end, n_hold=1, tsmom_filter=False):
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    rows = []
    for i in range(12, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        mom_row = mom_12.iloc[i].dropna()
        valid = mom_row.index.intersection(vol_row.index)
        if tsmom_filter:
            valid = pd.Index([t for t in valid if mom_row[t] > 0])
            if len(valid) == 0:
                rows.append((monthly_px.index[i], 0.0))
                continue
        if len(valid) < n_hold:
            rows.append((monthly_px.index[i],
                         monthly_ret.iloc[i][list(valid)].mean() if len(valid) > 0 else 0.0))
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], float(monthly_ret.iloc[i][top_n].mean())))
    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom = (df["high"] - df["low"]).replace(0, np.nan)
    ibs = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g = (df["open"] - prev_cl) / prev_cl
    equity = INITIAL_EQUITY
    position = days_held = 0
    series = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o = float(df["open"].iloc[i]); c = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i-1])
        ret_oc = (c/o - 1) if o > 0 else 0.0
        ret_cc = (c/cp - 1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1; days_held = 1; equity *= (1 + ret_oc)
        else:
            days_held += 1; equity *= (1 + ret_cc)
            if cur_ibs > sell or days_held >= hold:
                position = 0; days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0, "cumul": 1.0}
    eq  = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    cagr = float(eq.iloc[-1]) ** (1/n_yr) - 1
    vol  = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r),
            "neg_years": neg_yrs, "cumul": round(float(eq.iloc[-1]), 4)}


def print_stats(r, label):
    oos = stats(r[OOS_START:])
    alt = stats(r[ALT_OOS_ST:])
    is_ = stats(r[IS_START:IS_END])
    print(f"  {label:<40} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


# ── Vol-targeted blending ─────────────────────────────────────────────────────

VOL_WINDOW = 6   # months of history to estimate sub-strategy vol
VOL_CLAMP  = (0.5, 2.0)  # clamp scalar to [0.5x, 2.0x] of base weight


def blend_fixed(sub_rets: dict[str, pd.Series]) -> pd.Series:
    """Standard fixed-weight blend (H116 baseline)."""
    df = pd.DataFrame(sub_rets).dropna(how="all")
    combined = pd.Series(0.0, index=df.index)
    for key, w in BASE_WEIGHTS.items():
        if key in df.columns:
            combined += df[key].reindex(combined.index).fillna(0) * w
    return combined.dropna()


def blend_vol_targeted(
    sub_rets: dict[str, pd.Series],
    vol_target_keys: list[str],
) -> pd.Series:
    """
    For keys in vol_target_keys, scale weight by (target_vol / realized_vol).
    target_vol is computed as the cross-sectional mean of long-run vols for
    the targeted sub-strategies (so baseline is preserved on average).
    IBS and non-targeted components keep fixed weights.
    """
    df = pd.DataFrame(sub_rets).dropna(how="all")

    # Compute long-run annualized vol for each targeted sub to set target
    long_vols = {}
    for key in vol_target_keys:
        if key in df.columns:
            long_vols[key] = float(df[key].std(ddof=1)) * np.sqrt(12)
    if not long_vols:
        return blend_fixed(sub_rets)
    target_vol = np.mean(list(long_vols.values()))

    combined = pd.Series(0.0, index=df.index)

    for i in range(len(df)):
        dt = df.index[i]
        row_weights = dict(BASE_WEIGHTS)  # start from base

        if i >= VOL_WINDOW:
            # Compute realized vol for each targeted key over past VOL_WINDOW months
            window_rets = {k: df[k].iloc[i-VOL_WINDOW:i] for k in vol_target_keys if k in df.columns}
            realized_vols = {k: float(v.std(ddof=1)) * np.sqrt(12)
                             for k, v in window_rets.items() if len(v) >= 3}

            # Compute raw scalars
            raw_scalars = {}
            for k, rv in realized_vols.items():
                if rv > 0:
                    scalar = target_vol / rv
                    scalar = np.clip(scalar, VOL_CLAMP[0], VOL_CLAMP[1])
                    raw_scalars[k] = scalar

            if raw_scalars:
                # Scale targeted weights
                old_total_targeted = sum(BASE_WEIGHTS[k] for k in raw_scalars)
                new_total_targeted = sum(BASE_WEIGHTS[k] * s for k, s in raw_scalars.items())
                # Renorm so total rotation weight stays at ROTATION_TOTAL
                # (shift slack goes to/from cash implicitly)
                for k, s in raw_scalars.items():
                    row_weights[k] = BASE_WEIGHTS[k] * s

                # Renormalize all rotation subs so they sum to ROTATION_TOTAL
                rot_keys  = ["h041a", "h026", "h045"]
                current_sum = sum(row_weights[k] for k in rot_keys)
                if current_sum > 0:
                    scale = ROTATION_TOTAL / current_sum
                    for k in rot_keys:
                        row_weights[k] *= scale

        # Apply weights to this month's returns
        month_ret = 0.0
        for key, w in row_weights.items():
            if key in df.columns:
                month_ret += float(df[key].iloc[i]) * w

        combined.iloc[i] = month_ret

    return combined.dropna()


def blend_risk_parity(sub_rets: dict[str, pd.Series]) -> pd.Series:
    """
    Risk-parity across the three rotation subs: weight ∝ 1/long-run vol.
    IBS keeps fixed weights. Total rotation allocation stays at ROTATION_TOTAL.
    """
    df = pd.DataFrame(sub_rets).dropna(how="all")
    rot_keys = ["h041a", "h026", "h045"]
    inv_vols = {}
    for k in rot_keys:
        if k in df.columns:
            v = float(df[k].std(ddof=1)) * np.sqrt(12)
            if v > 0:
                inv_vols[k] = 1.0 / v
    total_inv = sum(inv_vols.values())

    rp_weights = dict(BASE_WEIGHTS)
    for k, iv in inv_vols.items():
        rp_weights[k] = (iv / total_inv) * ROTATION_TOTAL

    combined = pd.Series(0.0, index=df.index)
    for key, w in rp_weights.items():
        if key in df.columns:
            combined += df[key].reindex(combined.index).fillna(0) * w
    return combined.dropna()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("H118 — Volatility-Targeted Weight Scaling")
    print("=" * 70)
    print(f"Base weights: H041a={BASE_WEIGHTS['h041a']*100:.0f}% "
          f"H026={BASE_WEIGHTS['h026']*100:.0f}% H045={BASE_WEIGHTS['h045']*100:.0f}%")
    print(f"Vol window: {VOL_WINDOW}m  Clamp: {VOL_CLAMP}")

    # IBS components
    print("\nPre-computing IBS components…")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))
        print(f"  IBS {sym} done")

    # Rotation sub-strategies (H116 production configuration)
    print("\nComputing rotation sub-strategies (H116 config)…")
    h041a = build_rotation(H041A_FULL,  FULL_START, FULL_END, n_hold=1, tsmom_filter=False)
    h026  = build_rotation(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=True)  # H116
    h045  = build_rotation(H045_PROD,   FULL_START, FULL_END, n_hold=2, tsmom_filter=False)

    all_rets = {"h041a": h041a, "h026": h026, "h045": h045, **ibs_rets}

    print("\n" + "=" * 70)
    print("Results (IS Sharpe/CAGR | OOS Sharpe/CAGR/Cumul | AltOOS Cumul | MaxDD | NegYrs)")
    print("=" * 70 + "\n")

    # A) Baseline H116
    baseline = blend_fixed(all_rets)
    b_oos, b_alt = print_stats(baseline, "A) H116 baseline (fixed weights)")
    b_sum = b_oos["cumul"] + b_alt["cumul"]

    # B) Vol-target all three rotation subs
    vt_all = blend_vol_targeted(all_rets, ["h041a", "h026", "h045"])
    vt_all_oos, vt_all_alt = print_stats(vt_all, "B) Vol-target all 3 rotation subs")

    # C) Risk parity across rotation subs
    rp = blend_risk_parity(all_rets)
    rp_oos, rp_alt = print_stats(rp, "C) Risk parity (rotation subs)")

    # D) Vol-target H026 only (highest vol sub)
    vt_h026 = blend_vol_targeted(all_rets, ["h026"])
    vt_h026_oos, vt_h026_alt = print_stats(vt_h026, "D) Vol-target H026 only")

    # E) Vol-target H041a + H026
    vt_eq = blend_vol_targeted(all_rets, ["h041a", "h026"])
    vt_eq_oos, vt_eq_alt = print_stats(vt_eq, "E) Vol-target H041a + H026")

    print("\n" + "─" * 70)
    candidates = {
        "B) Vol-target all 3":    (vt_all_oos,  vt_all_alt),
        "C) Risk parity":         (rp_oos,      rp_alt),
        "D) Vol-target H026 only":(vt_h026_oos, vt_h026_alt),
        "E) Vol-target H041a+H026":(vt_eq_oos,  vt_eq_alt),
    }
    best_label = max(candidates, key=lambda k: candidates[k][0]["cumul"] + candidates[k][1]["cumul"])
    best_oos, best_alt = candidates[best_label]
    delta_oos = best_oos["cumul"] - b_oos["cumul"]
    delta_alt = best_alt["cumul"] - b_alt["cumul"]

    print(f"\n  Best variant: {best_label}")
    print(f"    OOS Cumul:  {best_oos['cumul']:.4f}  (baseline {b_oos['cumul']:.4f},  Δ{delta_oos:+.4f})")
    print(f"    AltOOS:     {best_alt['cumul']:.4f}  (baseline {b_alt['cumul']:.4f},  Δ{delta_alt:+.4f})")
    print(f"    OOS Sharpe: {best_oos['sharpe']:.3f}  MaxDD: {best_oos['max_drawdown']*100:.1f}%  "
          f"NegYrs: {best_oos['neg_years']}")

    both_better = delta_oos > 0 and delta_alt > 0
    print(f"\n  Verdict: {'✅ CONFIRMED — both OOS windows improve' if both_better else '❌ NOT CONFIRMED — does not pass dual-window test'}")
    if not both_better:
        print(f"  Note: OOS Δ={delta_oos:+.4f}  AltOOS Δ={delta_alt:+.4f}  "
              f"(both must be positive to confirm)")


if __name__ == "__main__":
    main()
