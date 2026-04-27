"""
H021 — VIX-Conditional Short Put Spread on SPY

Rules:
  - On the first trading day of each month, check VIX close.
  - If VIX > 20: sell put spread expiring ~30 DTE
      Short put: strike = SPY_close * 0.95  (5% OTM)
      Long  put: strike = SPY_close * 0.90  (10% OTM)
      Spread width = short_strike - long_strike ≈ 5% of SPY
  - If VIX ≤ 20: stay flat that month.
  - Exit: hold to expiry (use SPY close ~30 calendar days later).
  - Position size: allocate to risk max 2% of equity per spread.
      i.e. num_spreads = floor(equity * 0.02 / max_loss_per_spread)
      max_loss_per_spread = spread_width - net_premium_received

Pricing: Black-Scholes-Merton.
  - IV = VIX / 100  (30-day annualized IV for SPY)
  - T  = 30 / 365
  - r  = 0 (simplification; negligible on short tenor)

P&L at expiry:
  - SPY > short_strike  → full premium kept
  - SPY < long_strike   → max loss (spread_width - premium)
  - SPY between strikes → partial loss = short_strike - SPY_expiry - premium
    (long put offsets below long_strike, so net = -(short_strike - SPY_expiry) + premium)
    i.e. P&L = premium - (short_strike - SPY_expiry)

Data: yfinance SPY + ^VIX, 2004-01-01 onward.
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

START         = "2004-01-01"
END           = "2026-04-01"
INITIAL_EQUITY = 100_000.0
VIX_THRESHOLD  = 20.0
OTM_SHORT      = 0.05     # 5% OTM for short put
OTM_LONG       = 0.10     # 10% OTM for long put
RISK_PCT       = 0.02     # max 2% of equity per spread
TENOR_DAYS     = 30       # calendar days to expiry
T_YEARS        = TENOR_DAYS / 365.0
RISK_FREE      = 0.0      # simplified

CACHE_DIR  = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────

def _cache_path(tickers, start, end):
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h021_{h}.parquet"


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


def spread_premium(S: float, short_K: float, long_K: float,
                   T: float, r: float, sigma: float) -> float:
    """Net premium received for selling put spread (short_K > long_K)."""
    short_put = bsm_put(S, short_K, T, r, sigma)
    long_put  = bsm_put(S, long_K,  T, r, sigma)
    return short_put - long_put   # net credit received


# ─────────────────────────────────────────────
# Backtest core
# ─────────────────────────────────────────────

def run_backtest(spy_closes: pd.Series, vix_closes: pd.Series) -> dict:
    """
    Returns a dict with:
      equity_curve: pd.Series (monthly, indexed by entry date)
      trades: list of trade dicts
    """
    # Align series on common trading dates
    df = pd.DataFrame({"spy": spy_closes, "vix": vix_closes}).dropna()

    # Identify first trading day of each month
    df["ym"] = df.index.to_period("M")
    month_starts = df.groupby("ym").apply(lambda g: g.index[0])

    equity      = INITIAL_EQUITY
    equity_pts  = []   # (date, equity) after each month-end
    trades      = []

    # Track equity at start of full period
    equity_pts.append((df.index[0], equity))

    for entry_date in month_starts:
        spy_entry = df.loc[entry_date, "spy"]
        vix_entry = df.loc[entry_date, "vix"]

        # Find expiry date: first trading day ≥ entry_date + 30 calendar days
        expiry_min = entry_date + pd.Timedelta(days=TENOR_DAYS)
        future_dates = df.index[df.index >= expiry_min]
        if len(future_dates) == 0:
            break   # no expiry possible (end of data)
        expiry_date = future_dates[0]
        spy_expiry  = df.loc[expiry_date, "spy"]

        if vix_entry > VIX_THRESHOLD:
            # Strike computation
            short_K = spy_entry * (1 - OTM_SHORT)   # 5% OTM
            long_K  = spy_entry * (1 - OTM_LONG)    # 10% OTM
            spread_width = short_K - long_K          # ≈ 5% of SPY

            # IV from VIX
            sigma = vix_entry / 100.0

            # BSM net premium per spread (in $ per share)
            net_premium = spread_premium(spy_entry, short_K, long_K, T_YEARS, RISK_FREE, sigma)

            # Max loss per spread (in $ per share * 100 shares/contract)
            max_loss_per_share  = spread_width - net_premium
            max_loss_per_contract = max_loss_per_share * 100.0

            # Position sizing: risk 2% of equity
            if max_loss_per_contract <= 0:
                # Premium >= spread width (very rare, free trade) → cap at 1 contract
                num_contracts = 1
            else:
                num_contracts = max(1, int(equity * RISK_PCT / max_loss_per_contract))

            total_premium_received = net_premium * 100 * num_contracts

            # P&L at expiry
            if spy_expiry > short_K:
                # Above short strike → full profit
                pnl = total_premium_received
                outcome = "full_profit"
            elif spy_expiry < long_K:
                # Below long strike → max loss
                pnl = -(max_loss_per_share * 100 * num_contracts)
                outcome = "max_loss"
            else:
                # Between strikes → partial loss
                # Short put ITM, long put OTM
                # Net P&L = premium - (short_K - spy_expiry) per share * contracts
                pnl = (net_premium - (short_K - spy_expiry)) * 100 * num_contracts
                outcome = "partial_loss"

            equity += pnl

            trades.append({
                "entry_date":   str(entry_date.date()),
                "expiry_date":  str(expiry_date.date()),
                "spy_entry":    round(float(spy_entry), 4),
                "vix_entry":    round(float(vix_entry), 4),
                "short_K":      round(float(short_K), 4),
                "long_K":       round(float(long_K), 4),
                "spread_width": round(float(spread_width), 4),
                "sigma":        round(float(sigma), 4),
                "net_premium":  round(float(net_premium), 4),
                "max_loss_per_share": round(float(max_loss_per_share), 4),
                "num_contracts": int(num_contracts),
                "total_premium": round(float(total_premium_received), 2),
                "spy_expiry":   round(float(spy_expiry), 4),
                "pnl":          round(float(pnl), 2),
                "outcome":      outcome,
                "equity_after": round(float(equity), 2),
                "active":       True,
            })
        else:
            # VIX ≤ 20: flat, equity unchanged
            trades.append({
                "entry_date":  str(entry_date.date()),
                "vix_entry":   round(float(vix_entry), 4),
                "active":      False,
                "outcome":     "flat",
                "pnl":         0.0,
                "equity_after": round(float(equity), 2),
            })

        equity_pts.append((expiry_date if trades[-1]["active"] else entry_date, equity))

    eq_series = pd.Series(
        [v for _, v in equity_pts],
        index=[d for d, _ in equity_pts]
    ).sort_index()
    # Deduplicate index (keep last)
    eq_series = eq_series[~eq_series.index.duplicated(keep="last")]

    return {"equity_curve": eq_series, "trades": trades}


# ─────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series, label: str = "") -> dict:
    eq = eq.dropna().sort_index()
    if len(eq) < 4:
        return {"error": "insufficient data"}

    rets = eq.pct_change().dropna()
    n_months = len(rets)
    years    = n_months / 12.0

    total_return = (eq.iloc[-1] / eq.iloc[0]) - 1
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    monthly_mean = rets.mean()
    monthly_std  = rets.std()
    sharpe = (monthly_mean / monthly_std * sqrt(12)) if monthly_std > 0 else 0.0

    # Max drawdown
    running_max = eq.cummax()
    dd = (eq - running_max) / running_max
    max_dd = float(dd.min())

    return {
        "label":         label,
        "n_months":      n_months,
        "total_return":  round(float(total_return), 4),
        "cagr":          round(float(cagr), 4),
        "sharpe":        round(float(sharpe), 4),
        "max_drawdown":  round(float(max_dd), 4),
        "monthly_mean":  round(float(monthly_mean), 4),
        "monthly_std":   round(float(monthly_std), 4),
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("H021 — VIX-Conditional Short Put Spread on SPY")
    print("=" * 55)

    # ── Fetch data ──────────────────────────────────────
    print("Fetching SPY and ^VIX …")
    raw = fetch_data(["SPY", "^VIX"], START, END)
    spy_closes = raw["SPY"].dropna()
    vix_closes = raw["^VIX"].dropna()

    # ── Run backtest ─────────────────────────────────────
    print("Running backtest …")
    result     = run_backtest(spy_closes, vix_closes)
    equity     = result["equity_curve"]
    trades     = result["trades"]

    # ── Aggregate stats ──────────────────────────────────
    active_trades  = [t for t in trades if t["active"]]
    flat_trades    = [t for t in trades if not t["active"]]
    total_months   = len(trades)
    active_months  = len(active_trades)
    flat_months    = len(flat_trades)
    pct_active     = active_months / total_months if total_months > 0 else 0

    win_trades     = [t for t in active_trades if t["outcome"] == "full_profit"]
    loss_trades    = [t for t in active_trades if t["outcome"] == "max_loss"]
    partial_trades = [t for t in active_trades if t["outcome"] == "partial_loss"]
    win_rate       = len(win_trades) / active_months if active_months > 0 else 0

    avg_pnl_active = np.mean([t["pnl"] for t in active_trades]) if active_trades else 0
    avg_monthly_ret_all = np.mean([t["pnl"] / (t["equity_after"] - t["pnl"]) for t in trades]) if trades else 0

    full_stats = calc_stats(equity, label="H021 Full Period")

    # ── VIX regime comparison ────────────────────────────
    # Build monthly return series split by regime
    vix_high_rets = []
    vix_low_rets  = []
    for t in trades:
        eq_before = t["equity_after"] - t["pnl"]
        if eq_before <= 0:
            continue
        monthly_ret = t["pnl"] / eq_before
        if t["active"]:
            vix_high_rets.append(monthly_ret)
        else:
            vix_low_rets.append(monthly_ret)  # always 0 when flat

    vix_high_mean = np.mean(vix_high_rets) if vix_high_rets else 0
    vix_low_mean  = np.mean(vix_low_rets)  if vix_low_rets  else 0

    # ── Print summary ─────────────────────────────────────
    print()
    print(f"Period:              {trades[0]['entry_date']} → {trades[-1]['entry_date']}")
    print(f"Total months:        {total_months}")
    print(f"Active months (VIX>20): {active_months}  ({pct_active:.1%})")
    print(f"Flat months (VIX≤20):   {flat_months}  ({1-pct_active:.1%})")
    print()
    print(f"Win trades (full profit): {len(win_trades)}")
    print(f"Partial-loss trades:      {len(partial_trades)}")
    print(f"Max-loss trades:          {len(loss_trades)}")
    print(f"Win rate (active months): {win_rate:.1%}")
    print()
    print(f"Avg P&L per active trade: ${avg_pnl_active:,.0f}")
    print(f"Avg monthly return (active months): {vix_high_mean:.2%}")
    print()
    print(f"CAGR:         {full_stats['cagr']:.2%}")
    print(f"Sharpe:       {full_stats['sharpe']:.2f}")
    print(f"Max Drawdown: {full_stats['max_drawdown']:.2%}")
    print(f"Total Return: {full_stats['total_return']:.2%}")
    print()

    # ── Build results dict ────────────────────────────────
    results = {
        "strategy":      "H021",
        "description":   "VIX-Conditional Short Put Spread on SPY",
        "period":        {"start": START, "end": END},
        "parameters": {
            "vix_threshold":    VIX_THRESHOLD,
            "otm_short":        OTM_SHORT,
            "otm_long":         OTM_LONG,
            "tenor_days":       TENOR_DAYS,
            "risk_pct_per_spread": RISK_PCT,
            "initial_equity":   INITIAL_EQUITY,
        },
        "stats":         full_stats,
        "activity": {
            "total_months":    total_months,
            "active_months":   active_months,
            "flat_months":     flat_months,
            "pct_months_active": round(pct_active, 4),
        },
        "outcomes": {
            "full_profit":   len(win_trades),
            "partial_loss":  len(partial_trades),
            "max_loss":      len(loss_trades),
            "win_rate":      round(win_rate, 4),
        },
        "regime_comparison": {
            "vix_gt_20_avg_monthly_return": round(float(vix_high_mean), 4),
            "vix_le_20_avg_monthly_return": round(float(vix_low_mean), 4),
            "edge_vs_flat":                 round(float(vix_high_mean - vix_low_mean), 4),
        },
        "avg_pnl_per_active_trade": round(float(avg_pnl_active), 2),
        "final_equity":  round(float(equity.iloc[-1]), 2),
        "trades":        trades,
    }

    out_path = RESULTS_DIR / "h021_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved → {out_path}")

    return results


if __name__ == "__main__":
    main()
