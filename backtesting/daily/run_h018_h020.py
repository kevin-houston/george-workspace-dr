"""
H018 — H016 + H009 blended portfolio (50/50 macro rotation + daily mean-reversion)
H019 — H016 proper IS/OOS split (2007–2018 in-sample, 2019–2026 OOS)
H020 — H016 Universe F (SPY/QQQ/TLT/GLD/IEF top-2) with IS/OOS split

All use the same data pipeline and stats engine.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

INITIAL_EQUITY = 100_000.0
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

IS_START  = "2007-01-01"
IS_END    = "2018-12-31"
OOS_START = "2019-01-01"
OOS_END   = "2026-04-01"
FULL_START = "2007-01-01"


# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────

def _cache_path(tickers, start, end, kind="daily"):
    import hashlib
    key = "_".join(sorted(tickers)) + f"_{kind}_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h18_20_{h}.parquet"


def fetch_close(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    cp = _cache_path(tickers, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    cp = _cache_path(tickers, start, end, kind="ohlc")
    if cp.exists():
        df = pd.read_parquet(cp)
        return {t: df.xs(t, level="ticker") for t in df.index.get_level_values("ticker").unique()}
    print(f"  Downloading OHLC {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    frames = {}
    for t in tickers:
        try:
            frames[t] = raw.xs(t, axis=1, level=1)[["Open","High","Low","Close"]].rename(
                columns=str.lower)
        except Exception:
            pass
    combined = pd.concat(frames, names=["ticker"])
    combined.to_parquet(cp)
    return frames


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series) -> dict:
    if len(eq) < 10:
        return {"error": "insufficient data"}
    eq = eq.dropna()
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr   = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol    = rets.std() * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    max_dd   = (eq / roll_max - 1).min()
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0
    win_rate = (rets > 0).mean()
    return {
        "cagr":         round(float(cagr),    4),
        "sharpe":       round(float(sharpe),   4),
        "max_drawdown": round(float(max_dd),   4),
        "calmar":       round(float(calmar),   4),
        "ann_vol":      round(float(vol),      4),
        "win_rate":     round(float(win_rate), 4),
        "n_years":      round(float(n_years),  1),
    }


# ─────────────────────────────────────────────
# H016 core engine — returns daily equity series
# ─────────────────────────────────────────────

def h016_equity_curve(
    prices: pd.DataFrame,
    assets: list[str],
    cash_etf: str,
    start: str,
    end: str,
    top_n: int = 2,
) -> pd.Series:
    """
    Returns daily equity curve for the momentum+carry strategy
    over [start, end] using pre-fetched prices DataFrame.
    """
    available = [a for a in assets if a in prices.columns]
    if len(available) < top_n + 1:
        return pd.Series(dtype=float)

    px = prices[available + [cash_etf]].loc[start:end].dropna(how="all")

    monthly_px   = px[available].resample("ME").last()
    monthly_rets = px[available].pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1

    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < top_n + 1:
            continue

        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top = list(combined.nlargest(top_n).index)
        rest = [s for s in valid if s not in top]
        cash_wt = len(rest) / len(valid)

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px.loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0, p1 = float(sub[sym].iloc[j-1]), float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += (p1 / p0 - 1) / top_n
            if cash_wt > 0 and cash_etf in sub.columns:
                p0 = float(sub[cash_etf].iloc[j-1])
                p1 = float(sub[cash_etf].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += cash_wt * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


# ─────────────────────────────────────────────
# H009 core engine — returns daily equity series
# ─────────────────────────────────────────────

def h009_equity_curve(
    ohlc: pd.DataFrame,  # DataFrame with columns: open, high, low, close
    start: str,
    end: str,
    buy_thresh: float = 0.2,
    sell_thresh: float = 0.8,
    max_hold: int = 5,
) -> pd.Series:
    df = ohlc.loc[start:end].copy()
    ibs = ((df["close"] - df["low"]) /
           (df["high"] - df["low"])).replace([np.inf, -np.inf], np.nan).fillna(0.5)

    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []

    for i in range(1, len(ibs)):
        c_prev = float(df["close"].iloc[i-1])
        c_curr = float(df["close"].iloc[i])
        ret    = c_curr / c_prev - 1 if c_prev > 0 else 0

        if position == 1:
            equity   *= (1 + ret)
            days_held += 1
            if float(ibs.iloc[i]) > sell_thresh or days_held >= max_hold:
                position = days_held = 0
        else:
            if float(ibs.iloc[i-1]) < buy_thresh:
                position  = 1
                days_held = 1
                equity   *= (1 + ret)

        series.append((df.index[i], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


# ─────────────────────────────────────────────
# H018 — Blended portfolio
# ─────────────────────────────────────────────

def run_h018():
    print("\n" + "═"*72)
    print("H018 — H016+H009 Blended Portfolio (50% macro rotation + 50% IBS)")
    print("═"*72)

    START, END = "2007-01-01", OOS_END

    # H016 data
    H16_ASSETS = ["SPY", "TLT", "GLD"]
    all_close = fetch_close(H16_ASSETS + ["SHY"], START, END)

    # H009 data (needs OHLC)
    spy_ohlc = fetch_ohlc(["SPY"], START, END).get("SPY")
    if spy_ohlc is None:
        print("  ERROR: could not fetch SPY OHLC")
        return {}

    # Generate equity curves
    print("  Building H016 equity curve …")
    eq16 = h016_equity_curve(all_close, H16_ASSETS, "SHY", START, END)

    print("  Building H009 (SPY IBS) equity curve …")
    eq09 = h009_equity_curve(spy_ohlc, START, END)

    if eq16.empty or eq09.empty:
        print("  ERROR: one or both curves empty")
        return {}

    # Normalize both to 1.0 at their shared start
    common_start = max(eq16.index[0], eq09.index[0])
    common_end   = min(eq16.index[-1], eq09.index[-1])

    eq16 = eq16.loc[common_start:common_end]
    eq09 = eq09.loc[common_start:common_end]

    # Forward-fill H016 (monthly signal applied daily) to align daily index
    all_dates = eq09.index  # H009 has a value every trading day
    eq16_daily = eq16.reindex(all_dates).ffill()
    eq09_daily = eq09.reindex(all_dates).ffill()

    # Compute daily returns, blend 50/50, reconstruct equity
    r16 = eq16_daily.pct_change().fillna(0)
    r09 = eq09_daily.pct_change().fillna(0)
    r_blend = 0.5 * r16 + 0.5 * r09

    eq_blend = INITIAL_EQUITY * (1 + r_blend).cumprod()

    # Benchmarks
    spy_close = all_close["SPY"].loc[common_start:common_end].reindex(all_dates).ffill()
    eq_spy    = INITIAL_EQUITY * (spy_close / spy_close.iloc[0])

    m_blend = calc_stats(eq_blend)
    m16     = calc_stats(eq16_daily / eq16_daily.iloc[0] * INITIAL_EQUITY)
    m09     = calc_stats(eq09_daily / eq09_daily.iloc[0] * INITIAL_EQUITY)
    m_spy   = calc_stats(eq_spy)

    # Correlation between strategies
    corr = r16.corr(r09)

    print(f"\n  Strategy              CAGR   Sharpe   MaxDD   Calmar  AnnVol")
    print(f"  {'─'*62}")
    for name, m in [("H016 (standalone)", m16), ("H009 (standalone)", m09),
                    ("H018 Blend 50/50", m_blend), ("SPY B&H", m_spy)]:
        if "error" in m:
            continue
        print(f"  {name:<22} {m['cagr']:>6.2%}  {m['sharpe']:>6.3f}  "
              f"{m['max_drawdown']:>7.2%}  {m['calmar']:>6.3f}  {m['ann_vol']:>6.2%}")

    print(f"\n  Daily return correlation (H016 vs H009): {corr:.3f}")
    print(f"  Period: {common_start.date()} → {common_end.date()} ({m_blend.get('n_years','?')} yrs)")

    result = {
        "blend_50_50": m_blend,
        "h016_standalone": m16,
        "h009_standalone": m09,
        "spy_bh": m_spy,
        "daily_correlation": round(float(corr), 4),
        "period": f"{common_start.date()} → {common_end.date()}",
    }
    return result


# ─────────────────────────────────────────────
# H019 — H016 IS/OOS split
# ─────────────────────────────────────────────

def run_h019():
    print("\n" + "═"*72)
    print("H019 — H016 Proper IS/OOS Split (IS: 2007–2018  OOS: 2019–2026)")
    print("═"*72)

    H16_ASSETS = ["SPY", "TLT", "GLD"]
    all_close = fetch_close(H16_ASSETS + ["SHY"], FULL_START, OOS_END)

    results = {}
    for label, start, end in [
        ("in_sample",     FULL_START, IS_END),
        ("out_of_sample", OOS_START,  OOS_END),
        ("full_period",   FULL_START, OOS_END),
    ]:
        print(f"\n  ── {label.upper().replace('_',' ')} ({start} → {end}) ──")
        eq16 = h016_equity_curve(all_close, H16_ASSETS, "SHY", start, end)
        spy  = all_close["SPY"].loc[start:end]

        if eq16.empty:
            print("    No data")
            results[label] = {"error": "no data"}
            continue

        eq_spy = INITIAL_EQUITY * (spy / spy.iloc[0])
        m16    = calc_stats(eq16)
        m_spy  = calc_stats(eq_spy.reindex(eq16.index).ffill())

        results[label] = {"h016": m16, "spy_bh": m_spy}
        print(f"    H016:   CAGR {m16['cagr']:>6.2%}  Sharpe {m16['sharpe']:.3f}  MaxDD {m16['max_drawdown']:.2%}")
        print(f"    SPY BH: CAGR {m_spy['cagr']:>6.2%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.2%}")

    print(f"\n  IS/OOS degradation (Sharpe):")
    is_s  = results.get("in_sample",     {}).get("h016", {}).get("sharpe", "n/a")
    oos_s = results.get("out_of_sample", {}).get("h016", {}).get("sharpe", "n/a")
    print(f"    IS  Sharpe: {is_s}")
    print(f"    OOS Sharpe: {oos_s}")
    if isinstance(is_s, float) and isinstance(oos_s, float):
        deg = (is_s - oos_s) / is_s * 100 if is_s > 0 else 0
        print(f"    Degradation: {deg:.1f}%  {'(acceptable <50%)' if deg < 50 else '(OVERFIT WARNING >50%)'}")

    return results


# ─────────────────────────────────────────────
# H020 — H016 Universe F (5-asset) IS/OOS
# ─────────────────────────────────────────────

def run_h020():
    print("\n" + "═"*72)
    print("H020 — H016 Universe F (SPY/QQQ/TLT/GLD/IEF top-2) IS/OOS Split")
    print("═"*72)

    H20_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
    all_close = fetch_close(H20_ASSETS + ["SHY"], FULL_START, OOS_END)

    results = {}
    for label, start, end in [
        ("in_sample",     FULL_START, IS_END),
        ("out_of_sample", OOS_START,  OOS_END),
        ("full_period",   FULL_START, OOS_END),
    ]:
        print(f"\n  ── {label.upper().replace('_',' ')} ({start} → {end}) ──")
        eq20 = h016_equity_curve(all_close, H20_ASSETS, "SHY", start, end, top_n=2)
        spy  = all_close["SPY"].loc[start:end]

        if eq20.empty:
            print("    No data")
            results[label] = {"error": "no data"}
            continue

        eq_spy = INITIAL_EQUITY * (spy / spy.iloc[0])
        m20    = calc_stats(eq20)
        m_spy  = calc_stats(eq_spy.reindex(eq20.index).ffill())

        results[label] = {"h020": m20, "spy_bh": m_spy}
        print(f"    H020:   CAGR {m20['cagr']:>6.2%}  Sharpe {m20['sharpe']:.3f}  MaxDD {m20['max_drawdown']:.2%}")
        print(f"    SPY BH: CAGR {m_spy['cagr']:>6.2%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.2%}")

    # Compare H019 original vs H020 expanded universe (full period)
    H16_ASSETS = ["SPY", "TLT", "GLD"]
    close16 = fetch_close(H16_ASSETS + ["SHY"], FULL_START, OOS_END)
    eq16_full = h016_equity_curve(close16, H16_ASSETS, "SHY", FULL_START, OOS_END)
    eq20_full = h016_equity_curve(all_close, H20_ASSETS, "SHY", FULL_START, OOS_END)

    print(f"\n  Full period comparison (H019 original vs H020 5-asset):")
    for name, eq in [("H019 3-asset (SPY/TLT/GLD)", eq16_full), ("H020 5-asset (+ QQQ/IEF)", eq20_full)]:
        m = calc_stats(eq)
        if "error" not in m:
            print(f"    {name:<35} CAGR {m['cagr']:>6.2%}  Sharpe {m['sharpe']:.3f}  MaxDD {m['max_drawdown']:.2%}")

    is_s  = results.get("in_sample",     {}).get("h020", {}).get("sharpe", "n/a")
    oos_s = results.get("out_of_sample", {}).get("h020", {}).get("sharpe", "n/a")
    print(f"\n  IS/OOS degradation (Sharpe):")
    print(f"    IS  Sharpe: {is_s}")
    print(f"    OOS Sharpe: {oos_s}")
    if isinstance(is_s, float) and isinstance(oos_s, float):
        deg = (is_s - oos_s) / is_s * 100 if is_s > 0 else 0
        print(f"    Degradation: {deg:.1f}%  {'(acceptable <50%)' if deg < 50 else '(OVERFIT WARNING >50%)'}")

    return results


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("Running H018, H019, H020\n")

    r18 = run_h018()
    r19 = run_h019()
    r20 = run_h020()

    out = {"h018": r18, "h019": r19, "h020": r20}
    out_path = Path(__file__).parent / "h018_h020_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))

    print(f"\n{'═'*72}")
    print("  SUMMARY")
    print(f"{'═'*72}")

    if r18 and "error" not in r18.get("blend_50_50", {}):
        m = r18["blend_50_50"]
        print(f"  H018 Blend:     CAGR {m['cagr']:.2%}  Sharpe {m['sharpe']:.3f}  MaxDD {m['max_drawdown']:.2%}  (corr={r18.get('daily_correlation','?')})")
    if r19:
        m_oos = r19.get("out_of_sample", {}).get("h016", {})
        if "error" not in m_oos:
            print(f"  H019 OOS:       CAGR {m_oos['cagr']:.2%}  Sharpe {m_oos['sharpe']:.3f}  MaxDD {m_oos['max_drawdown']:.2%}")
    if r20:
        m_oos = r20.get("out_of_sample", {}).get("h020", {})
        if "error" not in m_oos:
            print(f"  H020 OOS:       CAGR {m_oos['cagr']:.2%}  Sharpe {m_oos['sharpe']:.3f}  MaxDD {m_oos['max_drawdown']:.2%}")

    print(f"\n  Results → {out_path}")
    return out


if __name__ == "__main__":
    main()
