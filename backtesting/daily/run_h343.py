"""
H343 — FVG Filter on H198 6-1m Momentum
========================================
Apply smart-money-concepts Fair Value Gap detection as a confirmation
filter on the H198 cross-sectional momentum universe (30 large-caps).

Base strategy: H198 6-1m momentum (confirmed OOS Sharpe 1.174)
Filter: at month-end, among top-ranked momentum stocks, only enter
those with an unmitigated bullish FVG on daily bars within the last N days.

Universe: same 30 stocks as H198
Signal: 6-1m momentum rank → FVG confirmation filter
Portfolio: top-6 (or best available) filtered, equal-weight, monthly rebalance
IS: 2013-2020  OOS: 2021-2026  Gate: OOS Sharpe > 1.174 (H198 baseline)

Variants tested:
  A  FVG strict  — only include if unmitigated bullish FVG in last 30d
  B  FVG lenient — prefer FVG stocks but fill slots from unfiltered if <3 pass
  C  OB strict   — only include if unmitigated bullish Order Block in last 30d
  D  OB lenient  — like B but for Order Blocks
  E  Baseline    — pure 6-1m H198 (no filter) for comparison
"""

import os, warnings
os.environ["SMC_CREDIT"] = "0"   # suppress banner
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from smartmoneyconcepts import smc as SMC

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM",
    "UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST",
    "CVX","XOM",
    "BA","CAT","IBM",
]

DATA_START  = "2011-01-01"
DATA_END    = "2026-04-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-04-30")
LOOKBACK    = 6     # 6-1m momentum (H198 best variant)
TOP_N       = 6
FVG_WINDOW  = 30    # trading days to look back for FVG/OB
MIN_FILTER  = 3     # minimum tickers after filter (lenient variants)


# ── Data loading ─────────────────────────────────────────────────────────────

def load_monthly(ticker: str) -> pd.Series:
    """Monthly close, cached."""
    cp = CACHE_DIR / f"h343_{ticker}_monthly.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    # reuse h198 cache if present
    for prefix in ["h198", "h199", "h320"]:
        old = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if old.exists():
            s = pd.read_parquet(old).squeeze()
            s.name = ticker
            pd.DataFrame(s).to_parquet(cp)
            return s
    print(f"  Downloading monthly {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def load_daily(ticker: str) -> pd.DataFrame:
    """Daily OHLCV, cached."""
    cp = CACHE_DIR / f"h343_{ticker}_daily.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading daily {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]
    df.to_parquet(cp)
    return df


# ── FVG / OB detection ───────────────────────────────────────────────────────

def has_bullish_fvg(daily_df: pd.DataFrame, as_of: pd.Timestamp, window: int) -> bool:
    """
    Returns True if there is at least one unmitigated bullish FVG
    in the `window` trading days ending at (and including) `as_of`.
    Uses data strictly up to `as_of` — no look-ahead.
    """
    sub = daily_df[daily_df.index <= as_of].tail(window + 2)
    if len(sub) < 3:
        return False
    try:
        fvg = SMC.fvg(sub[["open","high","low","close","volume"]])
    except Exception:
        return False
    # Bullish FVG = FVG == 1 and MitigatedIndex is NaN (still open)
    bull = fvg[(fvg["FVG"] == 1) & (fvg["MitigatedIndex"].isna())]
    return len(bull) > 0


def has_bullish_ob(daily_df: pd.DataFrame, as_of: pd.Timestamp, window: int) -> bool:
    """
    Returns True if there is at least one unmitigated bullish Order Block
    in the `window` trading days ending at `as_of`.
    """
    sub = daily_df[daily_df.index <= as_of].tail(window + 10)
    if len(sub) < 10:
        return False
    try:
        ohlcv = sub[["open","high","low","close","volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=min(5, len(sub)//3))
        ob = SMC.ob(ohlcv, swings)
    except Exception:
        return False
    bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
    return len(bull) > 0


# ── Backtest engine ───────────────────────────────────────────────────────────

def run_backtest(monthly_px: pd.DataFrame, daily_data: dict, variant: str) -> pd.Series:
    """
    Monthly rebalance strategy. variant controls the filter logic.
    """
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    for i, month_end in enumerate(months):
        loc = monthly_ret.index.get_loc(month_end)
        if loc < LOOKBACK + 1:
            continue
        signal_start = loc - LOOKBACK - 1
        signal_end   = loc - 1
        if signal_start < 0:
            continue

        # 6-1m momentum signal
        sig = monthly_px.iloc[signal_end] / monthly_px.iloc[signal_start] - 1
        sig = sig.dropna()
        if len(sig) < TOP_N:
            continue
        ranked = sig.nlargest(TOP_N * 2).index.tolist()  # wider pool for filtering
        top_ranked = ranked[:TOP_N]

        if variant == "E":
            selected = top_ranked
        else:
            # Apply FVG or OB filter
            filtered = []
            for ticker in ranked:
                if ticker not in daily_data:
                    continue
                if variant in ("A", "B"):
                    passes = has_bullish_fvg(daily_data[ticker], month_end, FVG_WINDOW)
                else:  # C or D
                    passes = has_bullish_ob(daily_data[ticker], month_end, FVG_WINDOW)

                if passes:
                    filtered.append(ticker)
                if len(filtered) >= TOP_N:
                    break

            if variant in ("A", "C"):
                # Strict: only use filtered; if fewer than MIN_FILTER, skip month
                if len(filtered) < MIN_FILTER:
                    # Hold cash (0% return)
                    port_rets.append((month_end, 0.0))
                    continue
                selected = filtered[:TOP_N]
            else:
                # Lenient: fill remaining slots from unfiltered top-ranked
                combined = filtered.copy()
                for t in top_ranked:
                    if t not in combined:
                        combined.append(t)
                    if len(combined) >= TOP_N:
                        break
                selected = combined[:TOP_N]

        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret_this))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ── Metrics ──────────────────────────────────────────────────────────────────

def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0

def cumul(r):
    return float((1 + r).prod())

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_yrs(r):
    return int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0))

def eval_period(r, start, end):
    r = r[(r.index >= start) & (r.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0, "cagr": 0, "maxdd": 0, "neg_yrs": 0}
    return {
        "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr": round(float(r.mean() * 12), 3),
        "maxdd": round(maxdd(r), 3),
        "neg_yrs": neg_yrs(r),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("H343 — FVG / Order Block Filter on H198 6-1m Momentum")
    print("=" * 58)

    # Load monthly prices
    print("\nLoading monthly data…")
    px_list = []
    for t in UNIVERSE:
        try:
            px_list.append(load_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(px_list).T.sort_index()

    # Load daily data (for FVG/OB detection)
    print("Loading daily data for FVG/OB detection…")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = load_daily(t)
        except Exception as e:
            print(f"  WARN {t} daily: {e}")

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h343_SPY_monthly.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_cp)
    spy_ret = spy_px.pct_change().dropna()

    VARIANTS = {
        "A": "FVG strict (cash if <3 pass)",
        "B": "FVG lenient (fill from unfiltered)",
        "C": "OB strict (cash if <3 pass)",
        "D": "OB lenient (fill from unfiltered)",
        "E": "Baseline 6-1m (no filter)",
    }

    results = {}
    print(f"\n{'Var':<4} {'Description':<35} {'IS Sharpe':>10} {'OOS Sharpe':>10} {'OOS MaxDD':>10} {'NegYrs':>7}")
    print("-" * 80)

    for vcode, vname in VARIANTS.items():
        print(f"  Running variant {vcode}…", end=" ", flush=True)
        rets = run_backtest(monthly_px, daily_data, vcode)
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        results[vcode] = {"name": vname, "is": is_, "oos": oos_}
        print(f"\r{vcode:<4} {vname:<35} {is_['sharpe']:>10.3f} {oos_['sharpe']:>10.3f} "
              f"{oos_['maxdd']:>10.1%} {oos_['neg_yrs']:>7d}")

    # SPY row
    spy_is  = eval_period(spy_ret, IS_START, IS_END)
    spy_oos = eval_period(spy_ret, OOS_START, OOS_END)
    print(f"{'SPY':<4} {'Buy-and-hold benchmark':<35} {spy_is['sharpe']:>10.3f} {spy_oos['sharpe']:>10.3f} "
          f"{spy_oos['maxdd']:>10.1%} {spy_oos['neg_yrs']:>7d}")

    # Verdict
    baseline_oos = results["E"]["oos"]["sharpe"]
    gate = 1.174  # H198 confirmed gate
    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {gate} (H198 6-1m baseline = {baseline_oos:.3f})")
    for vcode in ["A","B","C","D"]:
        oos_sharpe = results[vcode]["oos"]["sharpe"]
        beats = oos_sharpe > gate
        improves = oos_sharpe > baseline_oos
        print(f"  Variant {vcode} ({results[vcode]['name']}): OOS {oos_sharpe:.3f} "
              f"{'> GATE ✓' if beats else '< gate ✗'}  "
              f"{'IMPROVES vs baseline' if improves else 'does not improve vs baseline'}")

    # Save
    out = {
        "hypothesis": "H343",
        "description": "FVG / Order Block filter on H198 6-1m momentum",
        "gate": gate,
        "variants": results,
        "spy_is": spy_is,
        "spy_oos": spy_oos,
    }
    outpath = RESULT_DIR / "h343_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
