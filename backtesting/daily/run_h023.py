"""
H023 — VIX-Conditional Short Put Spread on SPY (5% risk budget variants)

Baseline: H021 uses 2% risk per trade.
H023:  Same rules, but risk 5% of equity per spread (max loss = 5% equity).
H023b: Same as H023, but exit at 50% profit (close when spread has decayed
       to 50% of initial premium received — standard short-premium management).

Rules (all variants):
  - On the first trading day of each month, check VIX close.
  - If VIX > 20: sell put spread expiring ~30 DTE
      Short put: strike = SPY_close * 0.95  (5% OTM)
      Long  put: strike = SPY_close * 0.90  (10% OTM)
      Spread width = short_strike - long_strike ≈ 5% of SPY
  - If VIX ≤ 20: stay flat that month.
  - BSM pricing with IV = VIX / 100, T = 30/365, r = 0.

H023:
  - Exit: hold to expiry.
  - Position size: risk 5% of equity per spread.

H023b:
  - Exit: whichever comes first —
      a) Spread's daily BSM value ≤ 0.50 × initial_premium → 50% profit exit
      b) Expiry date reached → settle per final SPY price
  - Position size: risk 5% of equity per spread.

P&L at expiry (when no early exit):
  - SPY > short_strike  → full premium kept
  - SPY < long_strike   → max loss (spread_width - premium)
  - SPY between strikes → partial loss = premium - (short_K - SPY_expiry)

Data: yfinance SPY + ^VIX, 2004-01-01 through 2026-04-25.
"""

import json
import sys
import hashlib
from pathlib import Path
from math import log, sqrt, exp

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

START          = "2004-01-01"
END            = "2026-04-25"
INITIAL_EQUITY = 100_000.0
VIX_THRESHOLD  = 20.0
OTM_SHORT      = 0.05     # 5% OTM for short put
OTM_LONG       = 0.10     # 10% OTM for long put
TENOR_DAYS     = 30       # calendar days to expiry
T_YEARS        = TENOR_DAYS / 365.0
RISK_FREE      = 0.0      # simplified

RISK_PCT_H021  = 0.02     # H021 baseline
RISK_PCT_H023  = 0.05     # H023 / H023b

PROFIT_EXIT_PCT = 0.50    # H023b: exit at 50% of initial premium

CACHE_DIR   = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────

def _cache_path(tickers, start, end):
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h023_{h}.parquet"


def fetch_data(tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = _cache_path(tickers, start, end)
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
# BSM pricing (European puts)
# ─────────────────────────────────────────────

def bsm_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes-Merton put price."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(K - S, 0.0)
    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    price = K * exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return max(price, 0.0)


def spread_value(S: float, short_K: float, long_K: float,
                 T: float, r: float, sigma: float) -> float:
    """
    Current BSM value of the put spread the *buyer* holds
    (short_K put - long_K put, from buyer's perspective).
    For the *seller* (us): profit = initial_premium - spread_value.
    """
    short_put = bsm_put(S, short_K, T, r, sigma)
    long_put  = bsm_put(S, long_K,  T, r, sigma)
    return short_put - long_put   # ≥ 0


# ─────────────────────────────────────────────
# Backtest core — single variant
# ─────────────────────────────────────────────

def run_backtest(df: pd.DataFrame, risk_pct: float, early_exit_50pct: bool) -> dict:
    """
    df: DataFrame with columns 'spy', 'vix', indexed by trading date.
    risk_pct: max fraction of equity to risk per spread.
    early_exit_50pct: if True, exit when spread value ≤ 50% of initial premium.

    Returns dict with equity_curve (pd.Series) and trades (list).
    """
    # Identify first trading day of each month
    df = df.copy()
    df["ym"] = df.index.to_period("M")
    month_starts = df.groupby("ym").apply(lambda g: g.index[0])

    equity     = INITIAL_EQUITY
    equity_pts = [(df.index[0], equity)]
    trades     = []

    for entry_date in month_starts:
        spy_entry = df.loc[entry_date, "spy"]
        vix_entry = df.loc[entry_date, "vix"]

        # Find expiry: first trading day ≥ entry_date + 30 calendar days
        expiry_min   = entry_date + pd.Timedelta(days=TENOR_DAYS)
        future_dates = df.index[df.index >= expiry_min]
        if len(future_dates) == 0:
            break
        expiry_date = future_dates[0]
        spy_expiry  = df.loc[expiry_date, "spy"]

        if vix_entry <= VIX_THRESHOLD:
            # VIX ≤ 20: flat
            trades.append({
                "entry_date":   str(entry_date.date()),
                "vix_entry":    round(float(vix_entry), 4),
                "active":       False,
                "outcome":      "flat",
                "pnl":          0.0,
                "equity_after": round(float(equity), 2),
            })
            equity_pts.append((entry_date, equity))
            continue

        # ── Active trade ────────────────────────────────────────
        short_K      = spy_entry * (1 - OTM_SHORT)
        long_K       = spy_entry * (1 - OTM_LONG)
        spread_width = short_K - long_K

        sigma         = vix_entry / 100.0
        net_premium   = spread_value(spy_entry, short_K, long_K, T_YEARS, RISK_FREE, sigma)

        max_loss_per_share    = spread_width - net_premium
        max_loss_per_contract = max_loss_per_share * 100.0

        if max_loss_per_contract <= 0:
            num_contracts = 1
        else:
            num_contracts = max(1, int(equity * risk_pct / max_loss_per_contract))

        total_premium_received = net_premium * 100 * num_contracts

        # ── Early-exit scan (H023b only) ─────────────────────────
        exit_date   = expiry_date
        early_exit  = False
        exit_spread_val = None

        if early_exit_50pct and net_premium > 0:
            target_val = PROFIT_EXIT_PCT * net_premium  # exit when spread ≤ this
            # Scan each trading day from entry+1 through expiry
            holding_dates = df.index[(df.index > entry_date) & (df.index <= expiry_date)]
            for d in holding_dates:
                spy_d = df.loc[d, "spy"]
                vix_d = df.loc[d, "vix"]
                t_rem = max((expiry_date - d).days / 365.0, 0.0)
                sigma_d = vix_d / 100.0
                sv = spread_value(spy_d, short_K, long_K, t_rem, RISK_FREE, sigma_d)
                if sv <= target_val:
                    exit_date       = d
                    exit_spread_val = sv
                    early_exit      = True
                    break

        # ── P&L calculation ─────────────────────────────────────
        if early_exit:
            # Bought back spread at exit_spread_val (per share)
            pnl     = (net_premium - exit_spread_val) * 100 * num_contracts
            outcome = "50pct_profit_exit"
            spy_at_exit = float(df.loc[exit_date, "spy"])
        else:
            # Settle at expiry
            spy_at_exit = float(spy_expiry)
            if spy_expiry > short_K:
                pnl     = total_premium_received
                outcome = "full_profit"
            elif spy_expiry < long_K:
                pnl     = -(max_loss_per_share * 100 * num_contracts)
                outcome = "max_loss"
            else:
                pnl     = (net_premium - (short_K - spy_expiry)) * 100 * num_contracts
                outcome = "partial_loss"

        equity += pnl

        trade_rec = {
            "entry_date":          str(entry_date.date()),
            "exit_date":           str(exit_date.date()),
            "expiry_date":         str(expiry_date.date()),
            "early_exit":          early_exit,
            "spy_entry":           round(float(spy_entry), 4),
            "vix_entry":           round(float(vix_entry), 4),
            "short_K":             round(float(short_K), 4),
            "long_K":              round(float(long_K), 4),
            "spread_width":        round(float(spread_width), 4),
            "sigma":               round(float(sigma), 4),
            "net_premium":         round(float(net_premium), 4),
            "max_loss_per_share":  round(float(max_loss_per_share), 4),
            "num_contracts":       int(num_contracts),
            "total_premium":       round(float(total_premium_received), 2),
            "spy_at_exit":         round(spy_at_exit, 4),
            "pnl":                 round(float(pnl), 2),
            "outcome":             outcome,
            "equity_after":        round(float(equity), 2),
            "active":              True,
        }
        if early_exit:
            trade_rec["exit_spread_val"] = round(float(exit_spread_val), 6)

        trades.append(trade_rec)
        equity_pts.append((exit_date, equity))

    eq_series = pd.Series(
        [v for _, v in equity_pts],
        index=[d for d, _ in equity_pts]
    ).sort_index()
    eq_series = eq_series[~eq_series.index.duplicated(keep="last")]

    return {"equity_curve": eq_series, "trades": trades}


# ─────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series, label: str = "") -> dict:
    eq = eq.dropna().sort_index()
    if len(eq) < 4:
        return {"error": "insufficient data"}

    rets   = eq.pct_change().dropna()
    n_pts  = len(rets)
    years  = n_pts / 12.0   # treat each equity point as ~monthly

    total_return = (eq.iloc[-1] / eq.iloc[0]) - 1
    cagr  = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    mean_ret = rets.mean()
    std_ret  = rets.std()
    sharpe   = (mean_ret / std_ret * sqrt(12)) if std_ret > 0 else 0.0

    running_max = eq.cummax()
    dd          = (eq - running_max) / running_max
    max_dd      = float(dd.min())

    return {
        "label":        label,
        "n_points":     n_pts,
        "total_return": round(float(total_return), 4),
        "cagr":         round(float(cagr), 4),
        "sharpe":       round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4),
        "monthly_mean": round(float(mean_ret), 4),
        "monthly_std":  round(float(std_ret), 4),
    }


def trade_summary(trades: list, label: str) -> dict:
    active  = [t for t in trades if t["active"]]
    flat    = [t for t in trades if not t["active"]]
    total   = len(trades)

    wins    = [t for t in active if t["outcome"] in ("full_profit", "50pct_profit_exit")]
    partials= [t for t in active if t["outcome"] == "partial_loss"]
    losses  = [t for t in active if t["outcome"] == "max_loss"]

    win_rate   = len(wins) / len(active) if active else 0
    avg_pnl    = float(np.mean([t["pnl"] for t in active])) if active else 0

    pnl_list   = [t["pnl"] for t in active]
    avg_win    = float(np.mean([t["pnl"] for t in wins])) if wins else 0
    avg_loss   = float(np.mean([t["pnl"] for t in (partials + losses)])) if (partials + losses) else 0

    early_exits = [t for t in active if t.get("early_exit", False)]
    pct_active  = len(active) / total if total else 0

    return {
        "label":         label,
        "total_months":  total,
        "active_months": len(active),
        "flat_months":   len(flat),
        "pct_active":    round(pct_active, 4),
        "outcomes": {
            "full_profit_or_early_exit": len(wins),
            "partial_loss":              len(partials),
            "max_loss":                  len(losses),
            "early_exits_50pct":         len(early_exits),
        },
        "win_rate":      round(win_rate, 4),
        "avg_pnl_active_trade":  round(avg_pnl, 2),
        "avg_win":       round(avg_win, 2),
        "avg_loss":      round(avg_loss, 2),
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("H023 — VIX-Conditional Short Put Spread (5% risk budget variants)")
    print("=" * 65)

    # ── Fetch data ──────────────────────────────────────────────
    print(f"Fetching SPY and ^VIX ({START} → {END}) …")
    raw        = fetch_data(["SPY", "^VIX"], START, END)
    spy_closes = raw["SPY"].dropna()
    vix_closes = raw["^VIX"].dropna()

    df = pd.DataFrame({"spy": spy_closes, "vix": vix_closes}).dropna()
    print(f"  {len(df)} trading days loaded.")

    # ── H021 baseline (2% risk, hold to expiry) ──────────────────
    print("\n[1/3] Running H021 baseline (2% risk, hold to expiry) …")
    r_h021   = run_backtest(df, RISK_PCT_H021, early_exit_50pct=False)
    s_h021   = calc_stats(r_h021["equity_curve"], label="H021 (2% risk, hold-to-expiry)")
    ts_h021  = trade_summary(r_h021["trades"], "H021")

    # ── H023 (5% risk, hold to expiry) ──────────────────────────
    print("[2/3] Running H023 (5% risk, hold to expiry) …")
    r_h023   = run_backtest(df, RISK_PCT_H023, early_exit_50pct=False)
    s_h023   = calc_stats(r_h023["equity_curve"], label="H023 (5% risk, hold-to-expiry)")
    ts_h023  = trade_summary(r_h023["trades"], "H023")

    # ── H023b (5% risk, 50% profit exit) ────────────────────────
    print("[3/3] Running H023b (5% risk, 50%-profit exit) …")
    r_h023b  = run_backtest(df, RISK_PCT_H023, early_exit_50pct=True)
    s_h023b  = calc_stats(r_h023b["equity_curve"], label="H023b (5% risk, 50%-profit exit)")
    ts_h023b = trade_summary(r_h023b["trades"], "H023b")

    # ── Print comparison table ───────────────────────────────────
    print()
    print("=" * 65)
    print(f"{'Metric':<32} {'H021 (2%)':>10} {'H023 (5%)':>10} {'H023b (5%+50%)':>14}")
    print("-" * 65)
    for key, label in [
        ("cagr",         "CAGR"),
        ("sharpe",       "Sharpe"),
        ("max_drawdown", "Max Drawdown"),
        ("total_return", "Total Return"),
    ]:
        v21  = s_h021[key]
        v23  = s_h023[key]
        v23b = s_h023b[key]
        fmt  = ".2%" if key != "sharpe" else ".2f"
        print(f"  {label:<30} {format(v21, fmt):>10} {format(v23, fmt):>10} {format(v23b, fmt):>14}")

    print("-" * 65)
    for key, label in [
        ("win_rate",              "Win Rate (active months)"),
        ("pct_active",            "% Months Active (VIX>20)"),
        ("avg_pnl_active_trade",  "Avg P&L per Active Trade"),
    ]:
        v21  = ts_h021[key]
        v23  = ts_h023[key]
        v23b = ts_h023b[key]
        if key == "avg_pnl_active_trade":
            fmt_str = lambda v: f"${v:,.0f}"
        else:
            fmt_str = lambda v: f"{v:.1%}"
        print(f"  {label:<30} {fmt_str(v21):>10} {fmt_str(v23):>10} {fmt_str(v23b):>14}")

    print()
    print(f"  Final equity (H021):  ${r_h021['equity_curve'].iloc[-1]:>12,.2f}")
    print(f"  Final equity (H023):  ${r_h023['equity_curve'].iloc[-1]:>12,.2f}")
    print(f"  Final equity (H023b): ${r_h023b['equity_curve'].iloc[-1]:>12,.2f}")

    early_e = ts_h023b["outcomes"]["early_exits_50pct"]
    active  = ts_h023b["active_months"]
    print(f"\n  H023b early exits: {early_e}/{active} active trades ({early_e/active:.1%})")

    # ── Save results ─────────────────────────────────────────────
    results = {
        "generated":   str(pd.Timestamp.now().date()),
        "period":      {"start": START, "end": END},
        "parameters": {
            "vix_threshold":      VIX_THRESHOLD,
            "otm_short":          OTM_SHORT,
            "otm_long":           OTM_LONG,
            "tenor_days":         TENOR_DAYS,
            "profit_exit_pct":    PROFIT_EXIT_PCT,
            "initial_equity":     INITIAL_EQUITY,
        },
        "variants": {
            "H021": {
                "risk_pct":      RISK_PCT_H021,
                "early_exit":    False,
                "stats":         s_h021,
                "trade_summary": ts_h021,
                "final_equity":  round(float(r_h021["equity_curve"].iloc[-1]), 2),
                "trades":        r_h021["trades"],
            },
            "H023": {
                "risk_pct":      RISK_PCT_H023,
                "early_exit":    False,
                "stats":         s_h023,
                "trade_summary": ts_h023,
                "final_equity":  round(float(r_h023["equity_curve"].iloc[-1]), 2),
                "trades":        r_h023["trades"],
            },
            "H023b": {
                "risk_pct":      RISK_PCT_H023,
                "early_exit":    True,
                "early_exit_threshold": PROFIT_EXIT_PCT,
                "stats":         s_h023b,
                "trade_summary": ts_h023b,
                "final_equity":  round(float(r_h023b["equity_curve"].iloc[-1]), 2),
                "trades":        r_h023b["trades"],
            },
        },
    }

    out_path = RESULTS_DIR / "h023_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved → {out_path}")

    return results


if __name__ == "__main__":
    main()
