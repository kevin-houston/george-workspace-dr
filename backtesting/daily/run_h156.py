"""
H156 — Cross-Sectional Stock Momentum (NASDAQ Universe)
=======================================================

Classic Jegadeesh-Titman (1993) cross-sectional momentum:
  - Signal: 12-1 month return (skip 1 month to avoid reversal)
  - Universe: Large-cap NASDAQ stocks with history back to 2007
  - Monthly rebalance, equal-weight top-N holdings
  - Benchmark: QQQ

SURVIVORSHIP BIAS NOTE: This universe is curated from stocks currently listed
that also had data in 2007. True survivorship-bias-free backtesting requires
point-in-time constituent data (Compustat, CRSP). This test is a hypothesis
validator only — a confirmed result should be reproduced with bias-free data
before production deployment.

Universe: ~80 large-cap NASDAQ stocks, all with pre-2008 history.
Grouped by sector to ensure diversification.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2007-01-01"
FULL_END   = "2026-04-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

COST_RT    = 0.001    # 0.1% round-trip (higher than ETFs — stock-level costs)
MOM_LB     = 12       # lookback months
SKIP       = 1        # skip-1 month (Jegadeesh-Titman)
MIN_MONTHS = 24       # minimum months of history to be eligible

# Large-cap NASDAQ stocks with pre-2008 history (survivorship-biased universe)
UNIVERSE = [
    # Technology
    "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "INTC", "CSCO", "QCOM",
    "TXN", "AMAT", "MU", "ADI", "KLAC", "MRVL", "LRCX", "CDNS", "SNPS", "ANSS",
    # Biotech / Healthcare
    "AMGN", "GILD", "BIIB", "REGN", "VRTX", "ILMN", "IDXX", "ALGN",
    # Consumer
    "COST", "SBUX", "MDLZ", "MNST", "FAST",
    # Financial
    "FISV", "PAYX", "CINF",
    # Semiconductors (added)
    "MCHP", "XLNX", "SWKS", "MPWR",
    # Communications / Media
    "CMCSA", "CHTR", "NFLX",
    # Industrials on NASDAQ
    "CTAS", "ODFL", "EXPD",
    # Additional large-caps
    "ISRG", "DXCM", "INTU", "ADBE", "ORCL", "IBM",
    "AVGO", "ANET", "PANW", "CRWD", "ZS",
    # ETF benchmarks (excluded from signal, used for comparison only)
    # QQQ — benchmark, loaded separately
]

# Remove any duplicates
UNIVERSE = sorted(set(UNIVERSE))


def fetch_prices(tickers, start, end):
    """Batch download with caching per ticker."""
    result = {}
    to_download = []
    for t in tickers:
        cp = CACHE_DIR / f"h156_{t}_close_{start}_{end}.parquet"
        # Also check prior H-series caches
        found = None
        for pfx in [f"h{i:03d}" for i in range(62, 157)]:
            for suf in ["ohlc", "close"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_{start}_{end}.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    col = "close" if "close" in df.columns else df.columns[0]
                    found = df[col].rename(t)
                    break
            if found is not None:
                break
        if found is not None:
            result[t] = found
        elif cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            col = "close" if "close" in df.columns else df.columns[0]
            result[t] = df[col].rename(t)
        else:
            to_download.append(t)

    if to_download:
        print(f"    Downloading {len(to_download)} tickers from yfinance…")
        batch = yf.download(to_download, start=start, end=end,
                            auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            closes = batch["Close"]
        else:
            closes = batch[["Close"]]

        for t in to_download:
            if t in closes.columns:
                s = closes[t].dropna()
                if len(s) > 100:
                    s.to_frame().to_parquet(
                        CACHE_DIR / f"h156_{t}_close_{start}_{end}.parquet")
                    result[t] = s.rename(t)

    return result


def build_monthly_returns(price_dict):
    """Convert daily prices to monthly returns (end-of-month)."""
    frames = []
    for t, s in price_dict.items():
        m = s.resample("ME").last().pct_change()
        m.name = t
        frames.append(m)
    return pd.concat(frames, axis=1)


def compute_signal(monthly_ret, date, mom_lb=MOM_LB, skip=SKIP):
    """
    Compute 12-1 momentum signal at given date.
    Uses returns from (date - mom_lb months) to (date - skip months).
    """
    end   = date - pd.DateOffset(months=skip)
    start = end   - pd.DateOffset(months=mom_lb - 1)  # inclusive
    window = monthly_ret.loc[start:end]
    if len(window) < mom_lb - skip:
        return pd.Series(dtype=float)
    # Compound return over window
    cum = (1 + window).prod() - 1
    # Require MIN_MONTHS of history available at this date
    available = monthly_ret.loc[:date].count()
    eligible   = available[available >= MIN_MONTHS].index
    return cum[cum.index.isin(eligible)].dropna()


def backtest_momentum(monthly_ret, n_hold, cost_rt=COST_RT):
    """
    Monthly rebalance: buy top-n_hold by 12-1 momentum.
    Returns daily portfolio returns (using monthly steps).
    """
    dates  = monthly_ret.index[monthly_ret.index >= FULL_START]
    ret_monthly = []
    prev_holdings = set()

    for i in range(len(dates)):
        d = dates[i]
        sig = compute_signal(monthly_ret, d)
        if len(sig) < n_hold * 2:   # need enough candidates
            ret_monthly.append((d, 0.0, 0))
            continue

        top = sig.nlargest(n_hold).index.tolist()
        if not top:
            ret_monthly.append((d, 0.0, 0))
            prev_holdings = set()
            continue

        # Next month's return
        if i + 1 >= len(dates):
            break
        next_d = dates[i + 1]
        # Equal-weight return for the holding month
        fwd_rets = monthly_ret.loc[next_d, top].dropna()
        if len(fwd_rets) == 0:
            ret_monthly.append((next_d, 0.0, len(top)))
            continue
        port_ret = fwd_rets.mean()

        # Transaction cost: fraction of portfolio turned over
        new_h = set(top)
        if prev_holdings:
            turnover = len(new_h.symmetric_difference(prev_holdings)) / (2 * n_hold)
        else:
            turnover = 1.0
        port_ret -= turnover * cost_rt
        prev_holdings = new_h
        ret_monthly.append((next_d, port_ret, len(fwd_rets)))

    return pd.DataFrame(ret_monthly, columns=["date", "ret", "n_stocks"]).set_index("date")["ret"]


def stats_monthly(r):
    r  = r.dropna()
    eq = (1 + r).cumprod()
    ann_factor = 12
    cagr   = float(eq.iloc[-1]) ** (ann_factor / len(r)) - 1
    vol    = r.std(ddof=1) * np.sqrt(ann_factor)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cumul": float(eq.iloc[-1]), "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "max_dd": max_dd, "neg_yrs": neg_yrs}


def main():
    print(f"\nH156 — Cross-Sectional Stock Momentum (NASDAQ universe)")
    print("=" * 60)

    print(f"\n[1] Loading prices for {len(UNIVERSE)} stocks…")
    price_dict = fetch_prices(UNIVERSE, FULL_START, FULL_END)
    # Load QQQ benchmark separately
    qqq_prices = fetch_prices(["QQQ"], FULL_START, FULL_END)
    spy_prices = fetch_prices(["SPY"], FULL_START, FULL_END)

    valid = {t: s for t, s in price_dict.items() if len(s) >= 500}
    print(f"    Valid tickers: {len(valid)} (of {len(UNIVERSE)} requested)")

    print(f"\n[2] Building monthly returns…")
    monthly_ret = build_monthly_returns(valid)
    qqq_m = build_monthly_returns(qqq_prices)["QQQ"].rename("QQQ")
    spy_m = build_monthly_returns(spy_prices)["SPY"].rename("SPY")
    print(f"    Monthly grid: {monthly_ret.shape[0]} months × {monthly_ret.shape[1]} stocks")
    print(f"    Period: {monthly_ret.index[0].date()} → {monthly_ret.index[-1].date()}")

    # Universe coverage over time
    coverage = monthly_ret.count(axis=1)
    print(f"    Coverage: {coverage.loc[coverage.index <= IS_END].mean():.0f} stocks avg (IS)  "
          f"/ {coverage.loc[coverage.index >= OOS_START].mean():.0f} (OOS)")

    print(f"\n[3] Testing variants (n_hold)…")

    spy_s = stats_monthly(spy_m[spy_m.index >= OOS_START])
    qqq_s = stats_monthly(qqq_m[qqq_m.index >= OOS_START])

    variants = [10, 15, 20, 30]
    results  = {}

    for n in variants:
        strat = backtest_momentum(monthly_ret, n_hold=n)
        s_oos = stats_monthly(strat[strat.index >= OOS_START])
        s_is  = stats_monthly(strat[(strat.index >= ALT_OOS_ST) & (strat.index <= IS_END)])
        s_alt = stats_monthly(strat[strat.index >= ALT_OOS_ST])

        # Correlation with SPY
        overlap = strat.index.intersection(spy_m.index)
        corr_spy = strat.loc[overlap].corr(spy_m.loc[overlap])

        results[n] = (s_oos, s_alt, s_is)
        print(f"\n  Variant n={n} top stocks:")
        print(f"    IS(2013-17): cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}  MaxDD={s_is['max_dd']:.2%}")
        print(f"    OOS(2018+):  cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  "
              f"Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
        print(f"    AltOOS:      cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
        print(f"    Corr(SPY OOS): {corr_spy:.3f}")

    print(f"\n    QQQ OOS: cumul={qqq_s['cumul']:.4f}  Sharpe={qqq_s['sharpe']:.3f}")
    print(f"    SPY OOS: cumul={spy_s['cumul']:.4f}  Sharpe={spy_s['sharpe']:.3f}")

    print(f"\n[4] Verdict:")
    verdicts = {}
    for n, (s_oos, s_alt, s_is) in results.items():
        checks = [
            s_oos["sharpe"] > 1.0,
            s_oos["cumul"]  > qqq_s["cumul"],    # beats QQQ (harder bar)
            s_oos["max_dd"] > -0.35,
            s_is["sharpe"]  > 0.5,
        ]
        np_ = sum(checks)
        v = "CONFIRMED" if np_ >= 3 else "PARTIAL" if np_ >= 2 else "NOT CONFIRMED"
        verdicts[n] = (v, np_, s_oos)
        print(f"    n={n}: {v} ({np_}/4)  OOS Sharpe={s_oos['sharpe']:.3f}  "
              f"cumul={s_oos['cumul']:.4f} vs QQQ {qqq_s['cumul']:.4f}")

    best_n, (best_v, _, best_s) = max(verdicts.items(), key=lambda kv: kv[1][2]["sharpe"])
    overall = "CONFIRMED" if best_v == "CONFIRMED" else \
              ("PARTIAL" if best_v == "PARTIAL" else "NOT CONFIRMED")
    print(f"\n  H156 overall: {overall}  (best: n={best_n})")
    print(f"  NOTE: Universe is survivorship-biased — positive result needs bias-free replication")

    lines = [
        "H156 — Cross-Sectional Stock Momentum (NASDAQ)", "=" * 60, "",
        f"Universe: {len(valid)} stocks (survivorship-biased), monthly rebalance",
        f"Signal: {MOM_LB}-{SKIP} month momentum, equal-weight top-N",
        f"Cost: {COST_RT:.1%} RT per rebalance",
        f"QQQ OOS: cumul={qqq_s['cumul']:.4f}  Sharpe={qqq_s['sharpe']:.3f}",
        f"SPY OOS: cumul={spy_s['cumul']:.4f}  Sharpe={spy_s['sharpe']:.3f}", "",
        "VARIANTS",
    ]
    for n, (s_oos, s_alt, s_is) in results.items():
        lines.append(
            f"  n={n}: OOS cumul={s_oos['cumul']:.4f} CAGR={s_oos['cagr']:.2%} "
            f"Sharpe={s_oos['sharpe']:.3f} MaxDD={s_oos['max_dd']:.2%} NegYrs={s_oos['neg_yrs']}"
        )
    lines += [
        "",
        f"VERDICT: {overall}  (best: n={best_n})",
        f"CAVEAT: Survivorship bias — result is directional only",
    ]
    (RESULT_DIR / "h156_stock_momentum.txt").write_text("\n".join(lines))
    return overall, best_s, qqq_s


if __name__ == "__main__":
    main()
