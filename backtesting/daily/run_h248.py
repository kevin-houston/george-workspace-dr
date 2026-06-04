"""
H248 — Betting Against Bad Beta (BABB)
=======================================
Source: arXiv:2409.00416 (Herculano, August 2024)
  'Betting Against (Bad) Beta'
  Double-sort on total beta AND bad beta (downside component).
  Bad beta = coskewness/downside beta, computed on down-market days.

H192-D baseline: Sector-neutral BAB, OOS Sharpe=1.367
BABB refinement: Remove stocks with high downside beta even if low total beta.

Bad beta definition:
  bad_beta_i = cov(R_i, R_m | R_m < 0) / var(R_m | R_m < 0)
  = realized beta during SPY down-days only

Total beta: OLS slope on trailing 12-month daily returns vs SPY

Portfolio construction (BABB):
  - Bottom tertile total beta AND bottom tertile bad beta → LONG leg
  - Top tertile total beta AND top tertile bad beta → SHORT leg
  - Long-only variant: just long the BABB-long leg (equal-weight, top-30)

IS: 2013-2020  OOS: 2021-2026
Universe: H241 195-stock large-cap universe
Confirm: OOS Sharpe >= 1.5
Key diagnostic: Corr(BABB, H228) OOS -- if < 0.3 -> production addition candidate
"""

import warnings; warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2012-01-01"   # warmup (need 12m for beta)
FULL_END   = "2026-05-30"
IS_START   = "2013-01-01"
IS_END     = "2020-12-31"
OOS_START  = "2021-01-01"
OOS_END    = "2026-05-31"

# Use H241 195-stock universe
UNIVERSE = [
    # Information Technology (30)
    "AAPL","MSFT","NVDA","AVGO","AMD","QCOM","ORCL","CRM","ADBE","INTC",
    "TXN","ACN","IBM","AMAT","LRCX","MU","NOW","INTU","ADI","NXPI",
    "MCHP","KLAC","CDNS","SNPS","FTNT","GLW","HPE","KEYS","ZBRA","JNPR",
    # Consumer Discretionary (20)
    "AMZN","TSLA","HD","MCD","NKE","SBUX","LOW","TJX","F","GM",
    "CMG","BKNG","ROST","DRI","DHI","LEN","PHM","NVR","TOL","EXPE",
    # Financials (25)
    "JPM","BAC","WFC","GS","MS","C","BLK","AXP","CB","PGR",
    "MET","PRU","TRV","ICE","CME","SCHW","USB","PNC","TFC","SPGI",
    "MCO","COF","DFS","AIG","MMC",
    # Healthcare (25)
    "UNH","LLY","JNJ","ABBV","MRK","PFE","TMO","ABT","AMGN","GILD",
    "MDT","BMY","ISRG","CVS","CI","HUM","ELV","REGN","VRTX","ZBH",
    "BDX","BSX","EW","DXCM","HOLX",
    # Consumer Staples (15)
    "WMT","COST","PG","KO","PEP","PM","MO","MDLZ","CL","GIS",
    "K","CPB","HRL","SJM","CAG",
    # Energy (15)
    "XOM","CVX","COP","EOG","PSX","VLO","MPC","SLB","HAL",
    "OXY","HES","APA","DVN","FANG","KMI",
    # Industrials (20)
    "BA","HON","UNP","UPS","RTX","DE","CAT","ETN","EMR","ITW",
    "NSC","FDX","GE","LMT","NOC","MMM","CSX","CTAS","RSG","WM",
    # Utilities + Real Estate (10)
    "NEE","DUK","SO","D","EXC","AEP","PPL","XEL","SRE","PCG",
    # Real Estate REITs (10)
    "PLD","AMT","CCI","EQIX","O","DLR","EQR","AVB","EXR","SPG",
    # Materials (10)
    "LIN","SHW","APD","ECL","NEM","FCX","NUE","CF","ALB","MOS",
    # Other / Media (10)
    "NFLX","DIS","CMCSA","CHTR","T","VZ","TMUS","FOXA","IPG","OMC",
    # Consumer other (5)
    "BKNG","EA","TTWO","NKE","LDOS",  # BKNG/NKE already above, dedup below
]

# Deduplicate universe
seen = set()
UNIVERSE_CLEAN = []
for t in UNIVERSE:
    if t not in seen:
        seen.add(t)
        UNIVERSE_CLEAN.append(t)
UNIVERSE = UNIVERSE_CLEAN


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def load_daily_prices():
    """Load daily close prices. Use H241 monthly cache as fallback for universe."""
    cache_path = CACHE_DIR / f"h248_daily_closes_{FULL_START}_{FULL_END}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        print(f"    Loaded from cache: {df.shape}")
        return df

    print(f"    Downloading daily closes for {len(UNIVERSE)} tickers in batches...")
    batch_size = 50
    all_data   = []
    all_tickers = UNIVERSE + ["SPY"]
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i+batch_size]
        print(f"      Batch {i//batch_size+1}: {batch[0]}...{batch[-1]}")
        raw = yf.download(batch, start=FULL_START, end=FULL_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            closes = raw["Close"]
        else:
            closes = raw
        all_data.append(closes)

    df = pd.concat(all_data, axis=1)
    # Remove duplicate columns
    df = df.loc[:, ~df.columns.duplicated()]
    df = df.dropna(how="all")
    df.to_parquet(cache_path)
    print(f"    Downloaded and cached: {df.shape}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Beta computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_betas_monthly(daily_ret, spy_ret, lookback=252):
    """
    For each month-end, compute total beta and bad beta for all stocks.
    total_beta: OLS slope over trailing 'lookback' days vs SPY
    bad_beta:   OLS slope conditioned on SPY down-days (SPY_ret < 0)

    Returns:
        total_beta_m: DataFrame (month-end dates x tickers)
        bad_beta_m:   DataFrame (month-end dates x tickers)
    """
    # Get month-end dates in range
    month_ends = daily_ret.resample("ME").last().index
    month_ends = month_ends[month_ends >= pd.Timestamp(IS_START)]
    month_ends = month_ends[month_ends <= pd.Timestamp(OOS_END)]

    total_betas = {}
    bad_betas   = {}

    for me in month_ends:
        # Trailing lookback days up to month-end
        mask = (daily_ret.index <= me)
        window = daily_ret[mask].tail(lookback)
        spy_w  = spy_ret[mask].tail(lookback)

        if len(window) < 100:
            continue

        # Total beta: cov(R_i, R_SPY) / var(R_SPY)
        spy_var = spy_w.var()
        if spy_var < 1e-10:
            continue

        tb = {}
        bb = {}
        # Down-market days (SPY < 0)
        down_mask = spy_w < 0
        spy_down  = spy_w[down_mask]
        spy_down_var = spy_down.var()
        has_down = (spy_down_var > 1e-10) and (down_mask.sum() > 20)

        for ticker in window.columns:
            ri = window[ticker]
            valid = ri.notna() & spy_w.notna()
            if valid.sum() < 60:
                continue

            ri_v   = ri[valid]
            spy_v  = spy_w[valid]
            cov_ts = np.cov(ri_v, spy_v, ddof=1)
            beta_t = cov_ts[0, 1] / spy_var if cov_ts[1, 1] > 0 else np.nan
            tb[ticker] = beta_t

            # Bad beta: only on down-market days
            if has_down:
                down_d = down_mask & ri.notna()
                if down_d.sum() > 15:
                    ri_down   = ri[down_d]
                    spy_down2 = spy_w[down_d]
                    cov_dd    = np.cov(ri_down, spy_down2, ddof=1)
                    beta_b    = cov_dd[0, 1] / spy_down_var if cov_dd[1, 1] > 0 else np.nan
                    bb[ticker] = beta_b
                else:
                    bb[ticker] = beta_t  # fallback to total beta
            else:
                bb[ticker] = beta_t  # fallback

        total_betas[me] = tb
        bad_betas[me]   = bb

    total_beta_m = pd.DataFrame(total_betas).T
    bad_beta_m   = pd.DataFrame(bad_betas).T
    return total_beta_m, bad_beta_m


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio construction
# ─────────────────────────────────────────────────────────────────────────────

def build_babb_portfolio(total_beta_m, bad_beta_m, monthly_ret):
    """
    Monthly double-sort:
      BABB long:  stocks in bottom-tertile total beta AND bottom-tertile bad beta
      BABB short: stocks in top-tertile total beta AND top-tertile bad beta (skipped for long-only)

    Returns:
      port_long:  long-only portfolio monthly returns
      port_ls:    long-short dollar-neutral portfolio monthly returns
    """
    port_long  = []
    port_ls    = []

    dates = total_beta_m.index
    for i in range(len(dates)):
        dt = dates[i]
        # Return month is the NEXT month after signal
        ret_dates_after = monthly_ret.index[monthly_ret.index > dt]
        if len(ret_dates_after) == 0:
            continue
        ret_dt = ret_dates_after[0]

        tb = total_beta_m.loc[dt].dropna()
        bb = bad_beta_m.loc[dt].dropna()

        # Common valid tickers
        valid = tb.index.intersection(bb.index)
        if len(valid) < 30:
            continue

        tb_v = tb[valid]
        bb_v = bb[valid]

        # Tertile cutoffs
        n = len(valid)
        tertile = n // 3

        # Bottom tertile total beta (low beta, rank ascending)
        tb_rank     = tb_v.rank(ascending=True)
        bb_rank     = bb_v.rank(ascending=True)

        # BABB long: bottom tertile on BOTH
        long_mask   = (tb_rank <= tertile) & (bb_rank <= tertile)
        long_tickers = valid[long_mask].tolist()

        # BABB short: top tertile on BOTH
        short_mask   = (tb_rank > (n - tertile)) & (bb_rank > (n - tertile))
        short_tickers = valid[short_mask].tolist()

        # Get next-month returns
        if ret_dt not in monthly_ret.index:
            continue

        ret_row = monthly_ret.loc[ret_dt]

        # Long leg
        if long_tickers:
            long_rets = ret_row[long_tickers].dropna()
            long_ret  = long_rets.mean()
        else:
            long_ret  = 0.0

        # Short leg
        if short_tickers:
            short_rets = ret_row[short_tickers].dropna()
            short_ret  = short_rets.mean()
        else:
            short_ret  = 0.0

        # Long-only return
        port_long.append((ret_dt, float(long_ret)))

        # Long-short (dollar-neutral): long - short
        # Short leg: 0.75%/yr borrow cost = 0.0625%/month
        borrow_cost = 0.000625
        ls_ret = long_ret - short_ret - borrow_cost
        port_ls.append((ret_dt, float(ls_ret)))

    if not port_long:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    dates_lo, rets_lo = zip(*port_long)
    dates_ls, rets_ls = zip(*port_ls)
    r_long = pd.Series(rets_lo, index=pd.DatetimeIndex(dates_lo))
    r_ls   = pd.Series(rets_ls, index=pd.DatetimeIndex(dates_ls))
    return r_long, r_ls


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def calc_stats(returns, label=""):
    r = returns.dropna()
    if len(r) < 12:
        return {"label": label, "error": "insufficient data"}
    eq = (1 + r).cumprod()
    n_years = len(r) / 12
    cagr    = (eq.iloc[-1]) ** (1/n_years) - 1
    vol     = r.std() * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    max_dd   = (eq / roll_max - 1).min()
    neg_yrs  = (r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum()
    return {
        "label":    label,
        "n_months": len(r),
        "cagr":     round(float(cagr), 4),
        "sharpe":   round(float(sharpe), 4),
        "max_dd":   round(float(max_dd), 4),
        "ann_vol":  round(float(vol), 4),
        "neg_yrs":  int(neg_yrs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("H248 — Betting Against Bad Beta (BABB)")
    print("=" * 60)

    # ── 1. Load daily prices ──────────────────────────────────────────────────
    print("\n[1] Loading daily prices...")
    daily_closes = load_daily_prices()

    # Compute daily returns
    daily_ret = daily_closes.drop(columns=["SPY"], errors="ignore").pct_change()
    spy_ret   = daily_closes["SPY"].pct_change() if "SPY" in daily_closes.columns else None

    if spy_ret is None:
        print("  ERROR: SPY not in price data")
        return

    # Drop tickers with < 500 days of data
    valid_tickers = daily_ret.columns[daily_ret.notna().sum() >= 500].tolist()
    daily_ret = daily_ret[valid_tickers]
    print(f"    Valid tickers: {len(valid_tickers)}")

    # ── 2. Monthly returns ────────────────────────────────────────────────────
    print("\n[2] Computing monthly returns...")
    monthly_ret  = daily_closes[valid_tickers].resample("ME").last().pct_change()
    spy_monthly  = daily_closes["SPY"].resample("ME").last().pct_change()

    # ── 3. Compute betas ──────────────────────────────────────────────────────
    print("\n[3] Computing total and bad betas (rolling 252-day)...")
    total_beta_m, bad_beta_m = compute_betas_monthly(
        daily_ret, spy_ret, lookback=252
    )
    print(f"    Beta months computed: {len(total_beta_m)}")
    print(f"    Avg stocks with total beta: {total_beta_m.notna().sum(axis=1).mean():.0f}")
    print(f"    Avg stocks with bad beta: {bad_beta_m.notna().sum(axis=1).mean():.0f}")

    # Sample diagnostics
    if len(total_beta_m) > 0:
        recent = total_beta_m.iloc[-1].dropna()
        print(f"    Recent total beta: median={recent.median():.3f} "
              f"min={recent.min():.3f} max={recent.max():.3f}")
        recent_bb = bad_beta_m.iloc[-1].dropna()
        print(f"    Recent bad beta: median={recent_bb.median():.3f} "
              f"min={recent_bb.min():.3f} max={recent_bb.max():.3f}")

    # ── 4. Build BABB portfolios ──────────────────────────────────────────────
    print("\n[4] Building BABB portfolios...")
    r_long, r_ls = build_babb_portfolio(total_beta_m, bad_beta_m, monthly_ret)
    print(f"    Long-only: {len(r_long)} months")
    print(f"    Long-short: {len(r_ls)} months")

    # Baseline: standard BAB (lowest total beta only, long-only)
    bab_long = []
    bab_dates_all = total_beta_m.index
    for i in range(len(bab_dates_all)):
        dt = bab_dates_all[i]
        ret_dates_after = monthly_ret.index[monthly_ret.index > dt]
        if len(ret_dates_after) == 0:
            continue
        ret_dt = ret_dates_after[0]
        tb = total_beta_m.loc[dt].dropna()
        if len(tb) < 20:
            continue
        tertile = len(tb) // 3
        low_beta = tb.nsmallest(tertile).index.tolist()
        if ret_dt in monthly_ret.index:
            bab_ret = monthly_ret.loc[ret_dt, low_beta].dropna().mean()
            bab_long.append((ret_dt, float(bab_ret)))

    if bab_long:
        d_bab, r_bab = zip(*bab_long)
        r_bab = pd.Series(list(r_bab), index=pd.DatetimeIndex(list(d_bab)))
    else:
        r_bab = pd.Series(dtype=float)

    # ── 5. Statistics ─────────────────────────────────────────────────────────
    print("\n[5] Computing statistics...")
    is_mask  = r_long.index <= pd.Timestamp(IS_END)
    oos_mask = r_long.index >= pd.Timestamp(OOS_START)

    is_bab_mask  = r_bab.index <= pd.Timestamp(IS_END)
    oos_bab_mask = r_bab.index >= pd.Timestamp(OOS_START)
    is_ls_mask   = r_ls.index <= pd.Timestamp(IS_END)
    oos_ls_mask  = r_ls.index >= pd.Timestamp(OOS_START)

    stats_babb_long_is  = calc_stats(r_long[is_mask],   "BABB Long IS")
    stats_babb_long_oos = calc_stats(r_long[oos_mask],  "BABB Long OOS")
    stats_babb_ls_is    = calc_stats(r_ls[is_ls_mask],  "BABB L/S IS")
    stats_babb_ls_oos   = calc_stats(r_ls[oos_ls_mask], "BABB L/S OOS")
    stats_bab_is        = calc_stats(r_bab[is_bab_mask],  "BAB baseline IS")
    stats_bab_oos       = calc_stats(r_bab[oos_bab_mask], "BAB baseline OOS")

    # SPY stats
    spy_oos = spy_monthly[spy_monthly.index >= pd.Timestamp(OOS_START)]
    spy_oos = spy_oos[spy_oos.index <= pd.Timestamp(OOS_END)]
    stats_spy_oos = calc_stats(spy_oos, "SPY OOS")

    print(f"    BABB Long-only: IS={stats_babb_long_is.get('sharpe','N/A'):.3f}  "
          f"OOS={stats_babb_long_oos.get('sharpe','N/A'):.3f} (MaxDD={stats_babb_long_oos.get('max_dd','N/A'):.3f})")
    print(f"    BABB L/S:       IS={stats_babb_ls_is.get('sharpe','N/A'):.3f}  "
          f"OOS={stats_babb_ls_oos.get('sharpe','N/A'):.3f} (MaxDD={stats_babb_ls_oos.get('max_dd','N/A'):.3f})")
    print(f"    BAB baseline:   IS={stats_bab_is.get('sharpe','N/A'):.3f}  "
          f"OOS={stats_bab_oos.get('sharpe','N/A'):.3f}")
    print(f"    SPY OOS:        Sharpe={stats_spy_oos.get('sharpe','N/A'):.3f}")

    # Confirm gate
    babb_oos_sharpe = stats_babb_long_oos.get("sharpe", 0)
    confirmed = babb_oos_sharpe >= 1.5
    print(f"\n    OOS Sharpe: {babb_oos_sharpe:.3f}")
    print(f"    Confirm gate: >= 1.5")
    print(f"    Result: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # Correlation with H228 momentum strategy (approximate: use SPY monthly as proxy)
    if len(r_long) > 0 and len(spy_monthly) > 0:
        common_oos = r_long[oos_mask].index.intersection(
            spy_monthly[spy_monthly.index >= pd.Timestamp(OOS_START)].index
        )
        if len(common_oos) > 12:
            corr_spy = r_long[oos_mask].reindex(common_oos).corr(
                spy_monthly.reindex(common_oos)
            )
            print(f"    Corr(BABB, SPY) OOS: {corr_spy:.3f}")
        else:
            corr_spy = None
    else:
        corr_spy = None

    # ── 6. Beta distribution diagnostics ─────────────────────────────────────
    print("\n[6] Beta diagnostics...")
    all_tb = total_beta_m.stack().dropna()
    all_bb = bad_beta_m.stack().dropna()
    print(f"    Total beta distribution: "
          f"mean={all_tb.mean():.3f}, std={all_tb.std():.3f}, "
          f"p25={all_tb.quantile(0.25):.3f}, p75={all_tb.quantile(0.75):.3f}")
    print(f"    Bad beta distribution: "
          f"mean={all_bb.mean():.3f}, std={all_bb.std():.3f}, "
          f"p25={all_bb.quantile(0.25):.3f}, p75={all_bb.quantile(0.75):.3f}")

    # ── 7. Save results ───────────────────────────────────────────────────────
    print("\n[7] Saving results...")
    results = {
        "hypothesis":          "H248",
        "description":         "Betting Against Bad Beta (BABB)",
        "source":              "arXiv:2409.00416 (Herculano, August 2024)",
        "universe":            f"{len(valid_tickers)} stocks from H241",
        "confirmed":           confirmed,
        "confirm_gate":        "OOS Sharpe >= 1.5",
        "babb_long_is":        stats_babb_long_is,
        "babb_long_oos":       stats_babb_long_oos,
        "babb_ls_is":          stats_babb_ls_is,
        "babb_ls_oos":         stats_babb_ls_oos,
        "bab_baseline_is":     stats_bab_is,
        "bab_baseline_oos":    stats_bab_oos,
        "spy_oos":             stats_spy_oos,
        "corr_babb_spy_oos":   round(float(corr_spy), 4) if corr_spy is not None else None,
        "beta_stats": {
            "total_beta_mean": round(float(all_tb.mean()), 3),
            "total_beta_std":  round(float(all_tb.std()), 3),
            "bad_beta_mean":   round(float(all_bb.mean()), 3),
            "bad_beta_std":    round(float(all_bb.std()), 3),
        },
        "data_source": "yfinance daily (195-stock H241 universe)",
    }

    out_path = RESULT_DIR / "h248_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"    Saved → {out_path}")

    return results


if __name__ == "__main__":
    main()
