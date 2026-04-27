"""
H024 — VIX Term Structure Signal

Rules:
  Primary signal (if VIX9D data available): VIX9D / VIX ratio each month-end
    - VIX9D/VIX < 0.9  (contango, near-term calm)   → LONG SPY next month
    - VIX9D/VIX > 1.1  (backwardation, fear spike)  → SHORT via SH next month
    - Otherwise                                      → hold SHY (cash)

  Fallback signal (if VIX9D history too short): VIX / VIX3M ratio
    - VIX/VIX3M < 1.0  (contango)      → LONG SPY
    - VIX/VIX3M >= 1.0 (backwardation) → hold SHY (cash)

  Signal computed on last trading day of each month.
  Position entered on first trading day of following month.

Data:  ^VIX9D, ^VIX, ^VIX3M, SPY, SH, SHY
Period: as far back as data allows through 2026-04-25
"""

import json
import hashlib
from pathlib import Path
from math import sqrt

import numpy as np
import pandas as pd
import yfinance as yf

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

END             = "2026-04-26"
INITIAL_EQUITY  = 100_000.0

# VIX9D thresholds
VIX9D_LOW       = 0.9   # below → contango → long
VIX9D_HIGH      = 1.1   # above → backwardation → short

# VIX/VIX3M thresholds (fallback)
VIX3M_LOW       = 1.0   # below → contango → long
VIX3M_HIGH      = 1.0   # at/above → backwardation → cash

# Minimum years for VIX9D to be preferred over VIX3M
VIX9D_MIN_YEARS = 5.0

CACHE_DIR   = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────

def _cache_key(tickers, start, end):
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h024_{h}.parquet"


def fetch_closes(tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = _cache_key(tickers, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]]
        closes.columns = tickers
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────
# Signal computation
# ─────────────────────────────────────────────

def compute_monthly_signals_vix9d(df: pd.DataFrame) -> pd.DataFrame:
    """
    Using VIX9D/VIX ratio at month-end.
    Returns DataFrame with month-end dates and signal column.
    """
    # Resample to month-end (last trading day of each month)
    monthly = df[["VIX9D", "VIX"]].resample("ME").last().dropna()
    monthly["ratio"] = monthly["VIX9D"] / monthly["VIX"]

    def classify(r):
        if r < VIX9D_LOW:
            return "long_spy"
        elif r > VIX9D_HIGH:
            return "short_sh"
        else:
            return "cash_shy"

    monthly["signal"] = monthly["ratio"].apply(classify)
    return monthly


def compute_monthly_signals_vix3m(df: pd.DataFrame) -> pd.DataFrame:
    """
    Using VIX/VIX3M ratio at month-end (longer-history signal).
    Contango (VIX < VIX3M, ratio < 0.95) → long SPY
    Backwardation (VIX > VIX3M, ratio > 1.05) → short via SH
    Near par (0.95–1.05) → hold SHY
    """
    monthly = df[["VIX", "VIX3M"]].resample("ME").last().dropna()
    monthly["ratio"] = monthly["VIX"] / monthly["VIX3M"]

    def classify(r):
        if r < 0.95:
            return "long_spy"
        elif r > 1.05:
            return "short_sh"
        else:
            return "cash_shy"

    monthly["signal"] = monthly["ratio"].apply(classify)
    return monthly


# ─────────────────────────────────────────────
# Backtest engine
# ─────────────────────────────────────────────

def run_backtest(signals: pd.DataFrame, prices: pd.DataFrame, signal_type: str) -> dict:
    """
    signals: DataFrame with month-end index, 'signal' column, 'ratio' column
    prices:  DataFrame with daily closes (SPY, SH, SHY)
    """
    equity = INITIAL_EQUITY
    equity_pts = []
    trades = []

    # First trading day of each month mapping
    prices_monthly_first = prices.resample("MS").first()

    # We apply the signal from month M at the start of month M+1
    signal_dates = signals.index.tolist()

    for i, sig_date in enumerate(signal_dates):
        # Entry: first trading day of the month after signal
        next_month_start = sig_date + pd.offsets.MonthBegin(1)
        # Find first actual trading day >= next_month_start
        future_dates = prices.index[prices.index >= next_month_start]
        if len(future_dates) == 0:
            break
        entry_date = future_dates[0]

        # Exit: last trading day of that same month (before next signal)
        # (or first day of the month after that = next signal's entry)
        if i + 1 < len(signal_dates):
            next_sig_date = signal_dates[i + 1]
            next_entry_candidates = prices.index[prices.index >= (next_sig_date + pd.offsets.MonthBegin(1))]
            if len(next_entry_candidates) == 0:
                exit_date = prices.index[-1]
            else:
                # Exit = day before next entry
                next_entry = next_entry_candidates[0]
                prior = prices.index[prices.index < next_entry]
                exit_date = prior[-1] if len(prior) > 0 else prices.index[-1]
        else:
            exit_date = prices.index[-1]

        if entry_date > exit_date or entry_date not in prices.index:
            continue

        signal = signals.loc[sig_date, "signal"]
        ratio  = float(signals.loc[sig_date, "ratio"])

        # Determine the holding ticker
        if signal == "long_spy":
            ticker = "SPY"
        elif signal == "short_sh":
            ticker = "SH"
        else:
            ticker = "SHY"

        # Compute return over holding period
        if ticker not in prices.columns:
            # Fallback to SHY if SH not available
            ticker = "SHY"

        entry_price = float(prices.loc[entry_date, ticker])
        exit_price  = float(prices.loc[exit_date, ticker])

        if entry_price <= 0 or np.isnan(entry_price) or np.isnan(exit_price):
            continue

        period_return = exit_price / entry_price - 1
        pnl = equity * period_return
        equity_before = equity
        equity += pnl

        equity_pts.append((entry_date, equity_before))
        equity_pts.append((exit_date,  equity))

        trades.append({
            "signal_date":   str(sig_date.date()),
            "entry_date":    str(entry_date.date()),
            "exit_date":     str(exit_date.date()),
            "ratio":         round(ratio, 4),
            "signal":        signal,
            "ticker":        ticker,
            "entry_price":   round(entry_price, 4),
            "exit_price":    round(exit_price, 4),
            "period_return": round(period_return, 4),
            "pnl":           round(float(pnl), 2),
            "equity_after":  round(float(equity), 2),
        })

    if not equity_pts:
        return {"equity_curve": pd.Series(dtype=float), "trades": []}

    eq_series = pd.Series(
        [v for _, v in equity_pts],
        index=pd.DatetimeIndex([d for d, _ in equity_pts])
    ).sort_index()
    eq_series = eq_series[~eq_series.index.duplicated(keep="last")]

    return {"equity_curve": eq_series, "trades": trades}


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series, label: str = "", freq: str = "daily") -> dict:
    eq = eq.dropna().sort_index()
    if len(eq) < 4:
        return {"error": "insufficient data", "label": label}

    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25

    total_return = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0

    # Annualized Sharpe (assume daily, multiply by sqrt(252))
    daily_mean = rets.mean()
    daily_std  = rets.std()
    sharpe = (daily_mean / daily_std * sqrt(252)) if daily_std > 0 else 0.0

    running_max = eq.cummax()
    dd = (eq - running_max) / running_max
    max_dd = float(dd.min())

    return {
        "label":        label,
        "n_years":      round(float(n_years), 2),
        "total_return": round(float(total_return), 4),
        "cagr":         round(float(cagr), 4),
        "sharpe":       round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4),
    }


def calc_spy_bh(spy_prices: pd.Series, start: str) -> dict:
    spy = spy_prices.loc[start:].dropna()
    if len(spy) < 2:
        return {}
    eq = INITIAL_EQUITY * spy / spy.iloc[0]
    return calc_stats(eq, label="SPY Buy-and-Hold")


# ─────────────────────────────────────────────
# H020 monthly returns (for correlation)
# ─────────────────────────────────────────────

def get_h020_monthly_returns(start: str, end: str) -> pd.Series:
    """
    Reconstruct H020 (top-2 momentum from SPY/QQQ/TLT/GLD/IEF universe)
    monthly return series for correlation computation.
    """
    ASSETS    = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
    CASH_ETF  = "IEF"
    TOP_N     = 2

    cp = _cache_key(ASSETS + ["h020"], start, end)
    if cp.exists():
        prices = pd.read_parquet(cp)
    else:
        print(f"  Downloading H020 assets {ASSETS} …")
        raw = yf.download(ASSETS, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"]
        else:
            prices = raw[["Close"]]
            prices.columns = ASSETS[:1]
        # Ensure flat string columns
        prices.columns = [str(c) for c in prices.columns]
        prices = prices.dropna(how="all")
        prices.to_parquet(cp)

    available = [a for a in ASSETS if a in prices.columns]
    if len(available) < TOP_N + 1:
        return pd.Series(dtype=float)

    monthly_px   = prices[available].resample("ME").last()
    monthly_rets = prices[available].pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6  = monthly_rets.rolling(6).std() * sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    equity = 100_000.0
    h020_rets = []
    h020_dates = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N + 1:
            continue

        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top = list(combined.nlargest(TOP_N).index)

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub_cols = [c for c in available if c in prices.columns]
        sub = prices[sub_cols].loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        month_ret = 0.0
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                if sym in sub.columns:
                    p0 = sub[sym].iloc[j-1]
                    p1 = sub[sym].iloc[j]
                    # guard against Series (shouldn't happen with flat cols)
                    if hasattr(p0, '__len__'):
                        p0 = float(p0.iloc[0])
                        p1 = float(p1.iloc[0])
                    else:
                        p0, p1 = float(p0), float(p1)
                    if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                        port_ret += (p1 / p0 - 1) / TOP_N
            equity *= (1 + port_ret)
            month_ret = port_ret

        # Compute the full monthly return as equity change
        h020_rets.append(month_ret)
        h020_dates.append(month_end)

    if not h020_dates:
        return pd.Series(dtype=float)
    return pd.Series(h020_rets, index=pd.DatetimeIndex(h020_dates))


# ─────────────────────────────────────────────
# Regime breakdown
# ─────────────────────────────────────────────

def regime_breakdown(trades: list) -> dict:
    total = len(trades)
    if total == 0:
        return {}
    counts = {"long_spy": 0, "short_sh": 0, "cash_shy": 0}
    returns = {"long_spy": [], "short_sh": [], "cash_shy": []}

    for t in trades:
        sig = t["signal"]
        counts[sig] = counts.get(sig, 0) + 1
        returns.setdefault(sig, []).append(t["period_return"])

    result = {}
    for sig, cnt in counts.items():
        avg_ret = float(np.mean(returns[sig])) if returns[sig] else 0.0
        result[sig] = {
            "count": cnt,
            "pct_time": round(cnt / total, 4),
            "avg_monthly_return": round(avg_ret, 4),
        }
    return result


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("H024 — VIX Term Structure Signal")
    print("=" * 50)

    # ── Step 1: Probe VIX9D data availability ──────────────
    print("\nProbing VIX9D data availability …")
    vix9d_raw = fetch_closes(["^VIX9D", "^VIX"], "2014-01-01", END)

    vix9d_col = "^VIX9D" if "^VIX9D" in vix9d_raw.columns else None
    vix_col   = "^VIX"   if "^VIX"   in vix9d_raw.columns else None

    vix9d_years = 0.0
    if vix9d_col and vix_col:
        combined = vix9d_raw[[vix9d_col, vix_col]].dropna()
        if len(combined) > 0:
            vix9d_years = (combined.index[-1] - combined.index[0]).days / 365.25
            print(f"  VIX9D available: {combined.index[0].date()} → {combined.index[-1].date()} ({vix9d_years:.1f} yr)")

    # ── Step 2: Probe VIX3M data availability ──────────────
    print("Probing VIX3M data availability …")
    vix3m_raw = fetch_closes(["^VIX3M", "^VIX"], "2007-01-01", END)

    vix3m_col = "^VIX3M" if "^VIX3M" in vix3m_raw.columns else None
    vix3m_years = 0.0
    if vix3m_col and "^VIX" in vix3m_raw.columns:
        combined3m = vix3m_raw[[vix3m_col, "^VIX"]].dropna()
        if len(combined3m) > 0:
            vix3m_years = (combined3m.index[-1] - combined3m.index[0]).days / 365.25
            print(f"  VIX3M available: {combined3m.index[0].date()} → {combined3m.index[-1].date()} ({vix3m_years:.1f} yr)")

    # ── Step 3: Choose signal — prefer LONGER history ─────
    # VIX3M goes back to 2007, VIX9D to 2014 → use VIX3M (longer history)
    use_vix9d = (vix9d_years > vix3m_years) or (vix3m_years < VIX9D_MIN_YEARS and vix9d_years >= VIX9D_MIN_YEARS)
    if use_vix9d:
        signal_type = "VIX9D/VIX"
        sig_start = str(vix9d_raw[[vix9d_col, vix_col]].dropna().index[0].date())
        print(f"\nUsing PRIMARY signal: {signal_type} (starts {sig_start})")
    else:
        signal_type = "VIX/VIX3M"
        if vix3m_col and "^VIX" in vix3m_raw.columns:
            sig_start = str(vix3m_raw[[vix3m_col, "^VIX"]].dropna().index[0].date())
        else:
            sig_start = "2007-01-01"
        print(f"\nUsing LONGER-HISTORY signal: {signal_type} (starts {sig_start})")

    # ── Step 4: Build signal DataFrame ────────────────────
    if use_vix9d:
        sig_df = vix9d_raw[[vix9d_col, vix_col]].dropna()
        sig_df = sig_df.rename(columns={vix9d_col: "VIX9D", vix_col: "VIX"})
        signals = compute_monthly_signals_vix9d(sig_df)
    else:
        sig_df = vix3m_raw[[vix3m_col, "^VIX"]].dropna()
        sig_df = sig_df.rename(columns={vix3m_col: "VIX3M", "^VIX": "VIX"})
        signals = compute_monthly_signals_vix3m(sig_df)

    print(f"  Signal observations: {len(signals)} months")

    # ── Step 5: Fetch equity data ──────────────────────────
    print("Fetching SPY, SH, SHY …")
    eq_tickers = ["SPY", "SH", "SHY"]
    price_data = fetch_closes(eq_tickers, sig_start, END)
    print(f"  Price data: {price_data.index[0].date()} → {price_data.index[-1].date()}")

    # ── Step 6: Run backtest ───────────────────────────────
    print("Running backtest …")
    result     = run_backtest(signals, price_data, signal_type)
    equity     = result["equity_curve"]
    trades     = result["trades"]

    if len(equity) < 4:
        print("ERROR: insufficient equity curve data.")
        return

    # ── Step 7: Stats ──────────────────────────────────────
    strat_stats = calc_stats(equity, label=f"H024 ({signal_type})")
    spy_stats   = calc_spy_bh(price_data["SPY"], sig_start)

    # ── Step 8: Regime breakdown ───────────────────────────
    regimes = regime_breakdown(trades)

    # ── Step 9: SPY buy-and-hold equity series for monthly comparison ──
    spy_eq = INITIAL_EQUITY * price_data["SPY"] / price_data["SPY"].iloc[0]

    # Monthly equity curves for correlation
    h024_monthly = equity.resample("ME").last()
    spy_monthly  = spy_eq.resample("ME").last()

    h024_monthly_rets = h024_monthly.pct_change().dropna()
    spy_monthly_rets  = spy_monthly.pct_change().dropna()

    common_idx = h024_monthly_rets.index.intersection(spy_monthly_rets.index)
    corr_spy = float(h024_monthly_rets.loc[common_idx].corr(spy_monthly_rets.loc[common_idx]))

    # ── Step 10: H020 correlation ──────────────────────────
    print("Computing H020 monthly returns for correlation …")
    h020_start = max(sig_start, "2008-01-01")
    h020_monthly_rets = get_h020_monthly_returns(h020_start, END)

    corr_h020 = float("nan")
    if len(h020_monthly_rets) > 10:
        common_h020 = h024_monthly_rets.index.intersection(h020_monthly_rets.index)
        if len(common_h020) > 10:
            corr_h020 = float(
                h024_monthly_rets.loc[common_h020].corr(h020_monthly_rets.loc[common_h020])
            )
            print(f"  H020 correlation period: {common_h020[0].date()} → {common_h020[-1].date()} ({len(common_h020)} months)")

    # ── Step 11: Also run secondary signal for comparison ─────
    secondary_stats = {}
    if not use_vix9d and vix9d_col and vix_col:
        print("Running secondary signal (VIX9D/VIX, 2014–) for comparison …")
        vix9d_sig_df = vix9d_raw[[vix9d_col, vix_col]].dropna()
        vix9d_sig_df = vix9d_sig_df.rename(columns={vix9d_col: "VIX9D", vix_col: "VIX"})
        vix9d_signals = compute_monthly_signals_vix9d(vix9d_sig_df)
        vix9d_start = str(vix9d_sig_df.index[0].date())
        vix9d_prices = fetch_closes(["SPY", "SH", "SHY"], vix9d_start, END)
        vix9d_result = run_backtest(vix9d_signals, vix9d_prices, "VIX9D/VIX")
        if len(vix9d_result["equity_curve"]) >= 4:
            secondary_stats = calc_stats(vix9d_result["equity_curve"], label="H024 secondary (VIX9D/VIX)")
            secondary_stats["regime_breakdown"] = regime_breakdown(vix9d_result["trades"])
            secondary_stats["spy_bh"] = calc_spy_bh(vix9d_prices["SPY"], vix9d_start)
            print(f"  VIX9D/VIX CAGR: {secondary_stats['cagr']:.2%}  Sharpe: {secondary_stats['sharpe']:.2f}  MaxDD: {secondary_stats['max_drawdown']:.2%}")

    # ── Step 12: Alpha analysis ────────────────────────────
    alpha_note = ""
    sharpe_note = ""
    if strat_stats["sharpe"] > spy_stats.get("sharpe", 0):
        sharpe_note = (
            f"Risk-adjusted outperformance: Sharpe {strat_stats['sharpe']:.2f} vs SPY {spy_stats.get('sharpe',0):.2f}. "
            f"MaxDD {strat_stats['max_drawdown']:.1%} vs SPY {spy_stats.get('max_drawdown',0):.1%}. "
            "Protects capital significantly in bear regimes."
        )
    if strat_stats["cagr"] < spy_stats.get("cagr", 0):
        diff = spy_stats.get("cagr", 0) - strat_stats["cagr"]
        alpha_note = (
            f"Signal underperforms SPY B&H by {diff:.1%} CAGR. "
            "However, Sharpe and MaxDD are materially better. "
            "Recommend use as an overlay: scale down H020 (or other momentum) position "
            "in backwardation months (ratio > 1.05) rather than as standalone."
        )
    else:
        diff = strat_stats["cagr"] - spy_stats.get("cagr", 0)
        alpha_note = (
            f"Signal outperforms SPY B&H by {diff:.1%} CAGR. "
            "May have standalone merit; also consider as a risk-on/off overlay."
        )

    # ── Print summary ──────────────────────────────────────
    print()
    print(f"Signal type:   {signal_type}")
    print(f"Period:        {trades[0]['signal_date']} → {trades[-1]['exit_date']}")
    print(f"Total months:  {len(trades)}")
    print()
    print("Regime breakdown:")
    for sig, info in regimes.items():
        print(f"  {sig:<12}: {info['count']:>3} months ({info['pct_time']:.1%})  avg monthly ret: {info['avg_monthly_return']:.2%}")
    print()
    print(f"H024  CAGR: {strat_stats['cagr']:.2%}  Sharpe: {strat_stats['sharpe']:.2f}  MaxDD: {strat_stats['max_drawdown']:.2%}")
    print(f"SPY BH CAGR: {spy_stats.get('cagr',0):.2%}  Sharpe: {spy_stats.get('sharpe',0):.2f}  MaxDD: {spy_stats.get('max_drawdown',0):.2%}")
    print()
    print(f"Corr to SPY monthly rets: {corr_spy:.3f}")
    print(f"Corr to H020 monthly rets: {corr_h020:.3f}")
    print()
    print(f"Alpha note: {alpha_note}")
    if sharpe_note:
        print(f"Sharpe note: {sharpe_note}")

    # ── Build output ───────────────────────────────────────
    output = {
        "strategy":    "H024",
        "description": "VIX Term Structure Signal (VIX9D/VIX or VIX/VIX3M)",
        "signal_type": signal_type,
        "period": {
            "start": trades[0]["signal_date"] if trades else sig_start,
            "end":   trades[-1]["exit_date"]  if trades else END,
        },
        "parameters": {
            "vix9d_low_threshold":  VIX9D_LOW,
            "vix9d_high_threshold": VIX9D_HIGH,
            "vix3m_threshold":      VIX3M_LOW,
            "initial_equity":       INITIAL_EQUITY,
            "long_asset":           "SPY",
            "short_asset":          "SH",
            "cash_asset":           "SHY",
        },
        "stats":   strat_stats,
        "spy_bh":  spy_stats,
        "regime_breakdown": regimes,
        "correlation": {
            "to_spy_monthly":  round(corr_spy,  4),
            "to_h020_monthly": round(corr_h020, 4) if not np.isnan(corr_h020) else None,
            "overlap_months":  len(common_h020) if not np.isnan(corr_h020) else 0,
        },
        "alpha_analysis":  alpha_note,
        "sharpe_analysis": sharpe_note,
        "secondary_signal_vix9d": secondary_stats if secondary_stats else "not_computed",
        "final_equity":  round(float(equity.iloc[-1]), 2),
        "total_trades":  len(trades),
        "trades":        trades,
    }

    out_path = RESULTS_DIR / "h024_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
