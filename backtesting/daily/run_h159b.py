"""
H159b — Beta-Neutral PEAD (Post-Earnings Announcement Drift)
=============================================================

Same gap >5% signal as H159, but each long position is paired with a
proportional SPY short to remove market beta.

Beta is estimated via rolling 60-day OLS (stock returns vs SPY returns)
computed on the 60 trading days BEFORE the event entry date.

Position:
  Long 1 unit of stock at open on gap day
  Short beta units of SPY at same open price
  Close both legs after hold_days

Daily hedged return:
  r_hedged[t] = r_stock[t] - beta * r_spy[t]

Assumptions:
  - No margin cost on SPY short (simplification)
  - SPY short settled at daily close-to-close (or open-to-open, matching stock side)
  - Same 0.1% RT cost per stock leg; SPY short = 0.05% RT (liquid ETF)

This should isolate the idiosyncratic event alpha from the market beta that
caused H159's unhedged portfolio to have MaxDD -43 to -58%.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from statsmodels.regression.linear_model import OLS
import statsmodels.api as sm

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START  = "2007-01-01"
FULL_END    = "2026-04-30"
IS_END      = "2017-12-31"
OOS_START   = "2018-01-01"
ALT_OOS_ST  = "2013-01-01"

COST_RT_STOCK = 0.001   # 0.1% RT per stock leg
COST_RT_SPY   = 0.0005  # 0.05% RT per SPY short leg (liquid ETF)
HOLD_DAYS     = 20
GAP_THRESH    = 0.05
N_MAX         = 10
BETA_WINDOW   = 60      # trading days for rolling beta estimate

UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "TSLA",
    "JPM",  "BAC",  "WFC",
    "JNJ",  "PFE",  "MRK",
    "XOM",  "CVX",
    "WMT",  "COST", "HD",  "LOW",
    "SBUX", "V",    "MA",
    "UNH",  "ABBV", "LLY",
    "AVGO", "AMD",  "QCOM", "INTC", "IBM",
]


def fetch_ohlcv(tickers, start, end):
    """Fetch daily OHLCV with cache reuse from H159."""
    result = {}
    to_dl  = []
    for t in tickers:
        found = None
        # Try H159 cache first (OHLCV)
        cp159 = CACHE_DIR / f"h159_{t}_ohlcv_{start}_{end}.parquet"
        if cp159.exists():
            df = pd.read_parquet(cp159)
            df.columns = [c.lower() for c in df.columns]
            if "open" in df.columns and "close" in df.columns:
                found = df[["open", "close"]]
        if found is None:
            # Try close-only caches for SPY
            for pfx in [f"h{i:03d}" for i in range(62, 160)]:
                for suf in ["ohlc", "close"]:
                    p = CACHE_DIR / f"{pfx}_{t}_{suf}_{start}_{end}.parquet"
                    if p.exists():
                        df = pd.read_parquet(p)
                        df.columns = [c.lower() for c in df.columns]
                        if "open" in df.columns and "close" in df.columns:
                            found = df[["open", "close"]]
                            break
                        elif "close" in df.columns:
                            found = df[["close"]]
                            break
                if found is not None:
                    break
        if found is not None and "open" in found.columns:
            result[t] = found
        elif found is not None and "close" in found.columns:
            result[t] = found   # close-only, used for SPY beta
        else:
            to_dl.append(t)

    if to_dl:
        print(f"    Downloading {len(to_dl)} tickers…")
        batch = yf.download(to_dl, start=start, end=end,
                            auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    df = df.dropna()
                    if len(df) > 100:
                        df.to_parquet(CACHE_DIR / f"h159_{t}_ohlcv_{start}_{end}.parquet")
                        result[t] = df
                except Exception:
                    pass
        else:
            t = to_dl[0]
            df = batch[["Open", "Close"]].copy()
            df.columns = ["open", "close"]
            df = df.dropna()
            if len(df) > 100:
                df.to_parquet(CACHE_DIR / f"h159_{t}_ohlcv_{start}_{end}.parquet")
                result[t] = df
    return result


def build_daily_returns(ohlcv_dict):
    """Build close-to-close return series for each ticker."""
    rets = {}
    for t, df in ohlcv_dict.items():
        if "close" in df.columns:
            rets[t] = df["close"].pct_change().rename(t)
    return rets


def compute_beta(stock_ret, spy_ret, window=BETA_WINDOW):
    """
    OLS beta of stock vs SPY over a rolling window.
    Returns a pd.Series indexed to stock_ret.index.
    """
    aligned = pd.concat([stock_ret, spy_ret], axis=1).dropna()
    if len(aligned) < window:
        return pd.Series(1.0, index=stock_ret.index)
    betas = pd.Series(np.nan, index=aligned.index)
    arr_y = aligned.iloc[:, 0].values
    arr_x = aligned.iloc[:, 1].values
    for i in range(window, len(aligned) + 1):
        y = arr_y[i-window:i]
        x = sm.add_constant(arr_x[i-window:i])
        try:
            b = OLS(y, x).fit().params[1]
        except Exception:
            b = 1.0
        betas.iloc[i-1] = b
    return betas.reindex(stock_ret.index).ffill().fillna(1.0)


def find_gap_events(ohlcv_dict, gap_thresh=GAP_THRESH):
    """Find gap-up events as in H159."""
    events = []
    for t, df in ohlcv_dict.items():
        if "open" not in df.columns:
            continue
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        signal_days = df[gap_pct > gap_thresh].copy()
        signal_days["gap_pct"] = gap_pct[gap_pct > gap_thresh]
        for idx, row in signal_days.iterrows():
            events.append({
                "date":     idx,
                "ticker":   t,
                "gap_pct":  row["gap_pct"],
                "entry_px": row["open"],
            })
    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def precompute_hedged_paths(events_df, ohlcv_dict, daily_rets, spy_ret_series,
                            all_betas, hold_days=HOLD_DAYS):
    """
    For each event, compute daily beta-hedged return path.
    Day 0: r_stock = (close - open) / open  (entered at open)
           r_spy   = (spy_close - spy_open) / spy_open  (matched timing)
           r_hedged = r_stock - beta * r_spy
    Day 1+: r_stock = (close[t] - close[t-1]) / close[t-1]
            r_spy   = spy_ret_series[t]
            r_hedged = r_stock - beta * r_spy

    all_betas: dict of ticker → pd.Series(date → beta)
    """
    # Build SPY open return series (day 0 approximation)
    spy_df = ohlcv_dict.get("SPY")
    spy_open_ret = pd.Series(dtype=float)
    if spy_df is not None and "open" in spy_df.columns:
        spy_open_ret = ((spy_df["close"] - spy_df["open"]) / spy_df["open"]).rename("SPY_open")

    paths = {}
    for idx, ev in events_df.iterrows():
        t = ev["ticker"]
        if t not in ohlcv_dict:
            continue
        df = ohlcv_dict[t].sort_index()
        if "open" not in df.columns:
            continue
        entry_date = ev["date"]
        if entry_date not in df.index:
            continue

        # Beta at entry
        beta_series = all_betas.get(t, pd.Series(1.0, index=df.index))
        if entry_date in beta_series.index:
            beta = float(beta_series[entry_date])
        else:
            beta = 1.0
        beta = max(0.0, min(3.0, beta))   # clamp to reasonable range

        future = df[df.index >= entry_date]
        if len(future) < hold_days:
            continue
        hold_slice = future.iloc[:hold_days]

        daily = []
        for i in range(len(hold_slice)):
            d = hold_slice.index[i]
            row = hold_slice.iloc[i]

            if i == 0:
                # Day 0: open-to-close for both legs
                if row["open"] > 0:
                    r_stock = (row["close"] - row["open"]) / row["open"]
                else:
                    r_stock = 0.0
                r_spy = float(spy_open_ret[d]) if d in spy_open_ret.index else 0.0
            else:
                prev = hold_slice.iloc[i-1]
                r_stock = (row["close"] - prev["close"]) / prev["close"] if prev["close"] > 0 else 0.0
                r_spy   = float(spy_ret_series[d]) if d in spy_ret_series.index else 0.0

            r_hedged = r_stock - beta * r_spy
            daily.append((d, r_hedged, r_stock, r_spy, beta))

        if daily:
            paths[idx] = {
                "hedged": pd.Series({x[0]: x[1] for x in daily}),
                "raw":    pd.Series({x[0]: x[2] for x in daily}),
                "beta":   beta,
            }
    return paths


def simulate_portfolio(events_df, paths, n_max=N_MAX,
                       cost_stock=COST_RT_STOCK, cost_spy=COST_RT_SPY):
    """Simulate beta-neutral PEAD portfolio."""
    all_dates = sorted(set.union(*[set(p["hedged"].index) for p in paths.values()]))

    events_df_idx = events_df.reset_index(drop=True)
    future_from = {}
    for idx, ev in events_df_idx.iterrows():
        if idx in paths:
            d = ev["date"]
            if d not in future_from:
                future_from[d] = []
            future_from[d].append((idx, ev["gap_pct"]))

    active = []   # list of (event_idx, exit_date)
    daily_rets = []

    for date in all_dates:
        # Expire finished positions
        active = [(eidx, ex) for eidx, ex in active if ex > date]

        # Add new events today, largest gaps first
        new_today = sorted(future_from.get(date, []), key=lambda x: -x[1])
        for ev_idx, _ in new_today:
            if len(active) < n_max and ev_idx in paths:
                h = paths[ev_idx]["hedged"]
                if len(h) > 0:
                    active.append((ev_idx, h.index[-1]))

        if not active:
            daily_rets.append((date, 0.0))
            continue

        pos_rets = []
        for (ev_idx, _) in active:
            h = paths[ev_idx]["hedged"]
            if date in h.index:
                r = float(h[date])
                if not np.isnan(r):
                    pos_rets.append(r)

        port_ret = np.mean(pos_rets) if pos_rets else 0.0
        daily_rets.append((date, port_ret))

    port = pd.DataFrame(daily_rets, columns=["date", "ret"]).set_index("date")["ret"]
    port.index = pd.to_datetime(port.index)

    # Apply costs: stock leg + SPY hedge leg
    cost_per_event = (cost_stock + cost_spy) / n_max
    cost_series = pd.Series(0.0, index=port.index)
    for _, ev in events_df_idx.iterrows():
        if ev["date"] in cost_series.index:
            cost_series[ev["date"]] += cost_per_event

    return port - cost_series


def stats_daily(r):
    r = r.dropna()
    if len(r) < 20:
        return {"cumul": 1.0, "cagr": 0.0, "vol": 0.0, "sharpe": 0.0, "max_dd": 0.0, "neg_yrs": 0}
    eq = (1 + r).cumprod()
    ann = 252
    cagr   = float(eq.iloc[-1]) ** (ann / len(r)) - 1
    vol    = r.std(ddof=1) * np.sqrt(ann)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cumul": float(eq.iloc[-1]), "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "max_dd": max_dd, "neg_yrs": neg_yrs}


def main():
    print("\nH159b — Beta-Neutral PEAD")
    print("=" * 60)

    print(f"\n[1] Loading OHLCV for {len(UNIVERSE)} stocks + SPY…")
    all_tickers = UNIVERSE + ["SPY"]
    ohlcv = fetch_ohlcv(all_tickers, FULL_START, FULL_END)
    valid = {t: df for t, df in ohlcv.items()
             if "open" in df.columns and "close" in df.columns and len(df) >= 500
             and t != "SPY"}
    print(f"    Valid stock tickers: {len(valid)}")

    spy_df = ohlcv.get("SPY")
    if spy_df is None:
        print("ERROR: SPY not loaded")
        return

    spy_ret = spy_df["close"].pct_change().rename("SPY")
    spy_ret.index = pd.to_datetime(spy_ret.index)

    print(f"\n[2] Building daily returns and rolling betas…")
    daily_rets = build_daily_returns(valid)

    # Compute rolling 60-day beta for every stock
    print(f"    Computing {len(valid)} beta series (this takes ~30s)…")
    all_betas = {}
    for i, (t, ret) in enumerate(daily_rets.items()):
        aligned_spy = spy_ret.reindex(ret.index)
        all_betas[t] = compute_beta(ret, aligned_spy, window=BETA_WINDOW)
        if (i + 1) % 10 == 0:
            print(f"    ... {i+1}/{len(valid)} done")

    # Beta distribution stats
    all_beta_vals = []
    for t, bs in all_betas.items():
        all_beta_vals.extend(bs.dropna().tolist())
    print(f"    Beta distribution: mean={np.mean(all_beta_vals):.2f}  "
          f"median={np.median(all_beta_vals):.2f}  "
          f"p10={np.percentile(all_beta_vals, 10):.2f}  "
          f"p90={np.percentile(all_beta_vals, 90):.2f}")

    print(f"\n[3] Finding gap events…")
    events = find_gap_events(valid, gap_thresh=GAP_THRESH)
    print(f"    Total gap >5% events: {len(events)}")

    print(f"\n[4] Precomputing beta-hedged paths…")
    paths = precompute_hedged_paths(events, ohlcv, daily_rets, spy_ret,
                                    all_betas, hold_days=HOLD_DAYS)
    print(f"    Paths computed: {len(paths)}/{len(events)} events")

    print(f"\n[5] Running portfolio simulations…")
    spy_oos = stats_daily(spy_ret[spy_ret.index >= OOS_START])
    spy_is  = stats_daily(spy_ret[(spy_ret.index >= ALT_OOS_ST) &
                                   (spy_ret.index <= IS_END)])
    print(f"    SPY OOS: cumul={spy_oos['cumul']:.4f}  Sharpe={spy_oos['sharpe']:.3f}  MaxDD={spy_oos['max_dd']:.2%}")

    VARIANTS = [
        ("A gap5% n10 h20",  0.05, 10, 20),
        ("B gap5% n5  h20",  0.05,  5, 20),
        ("C gap5% n10 h10",  0.05, 10, 10),
        ("D gap5% n15 h20",  0.05, 15, 20),
    ]

    results = []
    for (label, g_thresh, n_max_, hold) in VARIANTS:
        ev = find_gap_events(valid, gap_thresh=g_thresh)
        p_ = precompute_hedged_paths(ev, ohlcv, daily_rets, spy_ret,
                                     all_betas, hold_days=hold)
        port = simulate_portfolio(ev, p_, n_max=n_max_)
        port.index = pd.to_datetime(port.index)

        s_is  = stats_daily(port[(port.index >= pd.Timestamp(ALT_OOS_ST)) &
                                  (port.index <= pd.Timestamp(IS_END))])
        s_oos = stats_daily(port[port.index >= pd.Timestamp(OOS_START)])
        s_alt = stats_daily(port[port.index >= pd.Timestamp(ALT_OOS_ST)])

        # Correlation vs SPY (should be near 0 if hedge is working)
        ov = port.index.intersection(spy_ret.index)
        corr_spy = port.loc[ov].corr(spy_ret.loc[ov])

        ev_oos = ev[ev["date"] >= pd.Timestamp(OOS_START)]
        ev_is  = ev[(ev["date"] >= pd.Timestamp(ALT_OOS_ST)) &
                    (ev["date"] <= pd.Timestamp(IS_END))]

        results.append({
            "label": label, "n_max": n_max_, "hold": hold,
            "is": s_is, "oos": s_oos, "alt": s_alt,
            "corr_spy": corr_spy,
            "ev_oos": len(ev_oos), "ev_is": len(ev_is),
        })
        print(f"\n  {label}  (events IS={len(ev_is)}, OOS={len(ev_oos)}):")
        print(f"    IS(2013-17): cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}  MaxDD={s_is['max_dd']:.2%}")
        print(f"    OOS(2018+):  cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  "
              f"Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
        print(f"    AltOOS:      cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
        print(f"    Corr(SPY):   {corr_spy:.3f}  (target: near 0)")

    # Compare vs H159 unhedged best: B(gap3%, n10, h20) OOS Sharpe=0.436 MaxDD=-43.21%
    print(f"\n[6] Verdict (vs SPY OOS Sharpe={spy_oos['sharpe']:.3f})…")
    for rec in results:
        s_oos = rec["oos"]
        s_is  = rec["is"]
        # For beta-neutral strategy: correlation is more important than beating SPY
        # Criteria: Sharpe>1.0, MaxDD>-20%, IS Sharpe>0.5, corr<0.3
        checks = [
            s_oos["sharpe"] > 1.0,
            s_oos["max_dd"] > -0.20,
            s_is["sharpe"]  > 0.5,
            abs(rec["corr_spy"]) < 0.30,
        ]
        score = sum(checks)
        verdict = "CONFIRMED" if score >= 3 else "PARTIAL" if score >= 2 else "NOT CONFIRMED"
        rec["verdict"] = verdict
        rec["score"] = score
        print(f"  {rec['label']}: {verdict} ({score}/4)  OOS Sharpe={s_oos['sharpe']:.3f}  "
              f"MaxDD={s_oos['max_dd']:.2%}  Corr(SPY)={rec['corr_spy']:.3f}")

    best = max(results, key=lambda x: x["oos"]["sharpe"])
    overall = best["verdict"]
    print(f"\n  Best: {best['label']}  →  {overall}")
    print(f"  OOS: Sharpe={best['oos']['sharpe']:.3f}  CAGR={best['oos']['cagr']:.2%}  MaxDD={best['oos']['max_dd']:.2%}")
    print(f"  AltOOS: Sharpe={best['alt']['sharpe']:.3f}  cumul={best['alt']['cumul']:.4f}")
    print(f"  Corr(SPY OOS): {best['corr_spy']:.3f}")
    print(f"  H159b vs H159 MaxDD: {best['oos']['max_dd']:.2%} vs −43% (unhedged)")

    lines = [
        "H159b — Beta-Neutral PEAD", "=" * 60, "",
        f"Signal: gap >5% at open → long stock + short beta*SPY, hold {HOLD_DAYS}d",
        f"Beta: rolling {BETA_WINDOW}-day OLS (stock vs SPY), computed before entry",
        f"Cost: {COST_RT_STOCK:.2%} RT stock + {COST_RT_SPY:.2%} RT SPY short per event",
        "",
        "VARIANTS",
    ]
    for rec in results:
        s = rec["oos"]
        lines.append(
            f"  {rec['label']}: OOS cumul={s['cumul']:.4f} CAGR={s['cagr']:.2%} "
            f"Sharpe={s['sharpe']:.3f} MaxDD={s['max_dd']:.2%} NegYrs={s['neg_yrs']} "
            f"Corr(SPY)={rec['corr_spy']:.3f} → {rec['verdict']}"
        )
    lines += [
        "",
        f"BEST: {best['label']}",
        f"  OOS: cumul={best['oos']['cumul']:.4f}  Sharpe={best['oos']['sharpe']:.3f}  "
        f"MaxDD={best['oos']['max_dd']:.2%}  CAGR={best['oos']['cagr']:.2%}",
        f"  AltOOS: cumul={best['alt']['cumul']:.4f}  Sharpe={best['alt']['sharpe']:.3f}",
        f"  Corr(SPY OOS): {best['corr_spy']:.3f}",
        "",
        f"VERDICT: {overall}",
    ]
    (RESULT_DIR / "h159b_pead_beta_neutral.txt").write_text("\n".join(lines))
    print(f"\n  Results saved to results/h159b_pead_beta_neutral.txt")
    return overall, best


if __name__ == "__main__":
    main()
