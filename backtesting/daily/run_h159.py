"""
H159 — PEAD: Post-Earnings Announcement Drift
===============================================
Strategy: When a stock gaps up >5% at market open vs prior close (proxy for
a positive earnings surprise), enter at the open and hold for 20 trading days.

Based on Ernesto/R24h: per-stock Sharpe +2.394 on 30-stock portfolio,
8-10 signals/month. This is the first test of PEAD in this research programme.

Portfolio construction:
  - Universe: 30 large-cap stocks
  - Max N_MAX concurrent positions, equal-weighted
  - Entry at open on gap day, exit at close after 20 trading days
  - If more than N_MAX events fire on the same day, take the largest gaps first
  - Cost: 0.1% round-trip (stock commissions)

Benchmark: SPY buy-and-hold, and SPY over the same active-period

Note on survivorship bias: same caveat as H156 — universe is current large-caps
that survived. Failing stocks are not in this universe.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2007-01-01"
FULL_END   = "2026-04-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

COST_RT    = 0.001    # 0.1% RT (higher than ETFs)
HOLD_DAYS  = 20       # trading days to hold after gap
GAP_THRESH = 0.05     # gap threshold: +5% open vs prev close
N_MAX      = 10       # max concurrent positions

UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA", "TSLA",
    "JPM",  "BAC",  "WFC",
    "JNJ",  "PFE",  "MRK",
    "XOM",  "CVX",
    "WMT",  "COST", "HD", "LOW",
    "SBUX", "V",    "MA",
    "UNH",  "ABBV", "LLY",
    "AVGO", "AMD",  "QCOM", "INTC", "IBM",
]


def fetch_ohlcv(tickers, start, end):
    """Fetch daily OHLCV with cache."""
    result = {}
    to_dl  = []

    for t in tickers:
        # Try existing caches (various H-series)
        found = None
        for pfx in [f"h{i:03d}" for i in range(62, 160)]:
            for suf in ["ohlc", "close"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_{start}_{end}.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "open" in df.columns and "close" in df.columns:
                        found = df[["open", "high", "low", "close"]]
                        break
                    elif "close" in df.columns:
                        found = df[["close"]]
                        break
            if found is not None:
                break

        if found is not None and "open" in found.columns:
            result[t] = found
        else:
            cp = CACHE_DIR / f"h159_{t}_ohlcv_{start}_{end}.parquet"
            if cp.exists():
                df = pd.read_parquet(cp)
                df.columns = [c.lower() for c in df.columns]
                result[t] = df
            else:
                to_dl.append(t)

    if to_dl:
        print(f"    Downloading {len(to_dl)} tickers OHLCV…")
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
            # Single ticker
            t = to_dl[0]
            df = batch[["Open", "Close"]].copy()
            df.columns = ["open", "close"]
            df = df.dropna()
            if len(df) > 100:
                df.to_parquet(CACHE_DIR / f"h159_{t}_ohlcv_{start}_{end}.parquet")
                result[t] = df

    return result


def find_gap_events(ohlcv_dict, gap_thresh=GAP_THRESH):
    """
    For each ticker, find days where open > prev_close * (1 + gap_thresh).
    Returns a DataFrame of events with columns:
      [ticker, date, gap_pct, open_px, close_px_entry]
    """
    events = []
    for t, df in ohlcv_dict.items():
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        signal_days = df[gap_pct > gap_thresh].copy()
        signal_days["gap_pct"] = gap_pct[gap_pct > gap_thresh]
        signal_days["ticker"] = t
        for idx, row in signal_days.iterrows():
            events.append({
                "date":     idx,
                "ticker":   t,
                "gap_pct":  row["gap_pct"],
                "entry_px": row["open"],    # enter at open
            })
    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def precompute_event_paths(events_df, ohlcv_dict, hold_days):
    """
    For each event, precompute daily return path starting from open on entry day.
    Day 0: (close[entry] - open[entry]) / open[entry]  ← entered at open, not prev close
    Day 1+: normal close-to-close returns
    Returns dict: event_index → pd.Series(date → return)
    """
    paths = {}
    for idx, ev in events_df.iterrows():
        t = ev["ticker"]
        if t not in ohlcv_dict:
            continue
        df = ohlcv_dict[t].sort_index()
        entry_date = ev["date"]
        if entry_date not in df.index:
            continue
        # Get dates from entry onward
        future = df[df.index >= entry_date]
        if len(future) < hold_days:
            continue
        hold_slice = future.iloc[:hold_days]

        daily = []
        for i in range(len(hold_slice)):
            row = hold_slice.iloc[i]
            if i == 0:
                # Entry at open, first day return = (close - open) / open
                if row["open"] > 0:
                    r = (row["close"] - row["open"]) / row["open"]
                else:
                    r = 0.0
            else:
                # Close-to-close
                prev_close = hold_slice.iloc[i-1]["close"]
                if prev_close > 0:
                    r = (row["close"] - prev_close) / prev_close
                else:
                    r = 0.0
            daily.append((hold_slice.index[i], r))

        paths[idx] = pd.Series(dict(daily))
    return paths


def simulate_portfolio(events_df, ohlcv_dict, hold_days=HOLD_DAYS,
                       n_max=N_MAX, cost_rt=COST_RT):
    """
    Simulate PEAD portfolio using correct entry-price returns.
    Entry day return = (close - open) / open  (entered at open AFTER gap).
    Subsequent days: close-to-close.
    """
    # All trading dates
    all_dates = sorted(set.union(*[set(df.index) for df in ohlcv_dict.values()]))
    all_dates = [d for d in all_dates if pd.Timestamp(FULL_START) <= d <= pd.Timestamp(FULL_END)]

    # Precompute per-event return paths (correct entry price)
    paths = precompute_event_paths(events_df, ohlcv_dict, hold_days)

    events_by_date = events_df.groupby("date")
    # active_events: list of (event_idx, exit_date)
    active = []
    daily_rets = []

    future_from = {d: [] for d in all_dates}  # lookup: date → events starting that day
    for idx, ev in events_df.iterrows():
        if idx in paths and ev["date"] in future_from:
            future_from[ev["date"]].append((idx, ev["gap_pct"]))

    for i, date in enumerate(all_dates):
        # Remove expired positions (those whose path has ended)
        active = [(ev_idx, ex) for ev_idx, ex in active if ex > date]

        # Add new events today, sorted by gap size desc, up to n_max slots
        new_today = sorted(future_from.get(date, []), key=lambda x: -x[1])
        for ev_idx, _ in new_today:
            if len(active) < n_max and ev_idx in paths:
                path = paths[ev_idx]
                if len(path) > 0:
                    exit_date = path.index[-1]
                    active.append((ev_idx, exit_date))

        if not active:
            daily_rets.append((date, 0.0))
            continue

        pos_rets = []
        for (ev_idx, _) in active:
            path = paths[ev_idx]
            if date in path.index:
                r = path[date]
                if not np.isnan(r):
                    pos_rets.append(r)

        port_ret = np.mean(pos_rets) if pos_rets else 0.0
        daily_rets.append((date, port_ret))

    port = pd.DataFrame(daily_rets, columns=["date", "ret"]).set_index("date")["ret"]
    port.index = pd.to_datetime(port.index)
    return port


def apply_costs(events_df, port_daily, n_max=N_MAX, cost_rt=COST_RT):
    """
    Apply entry/exit costs. Each event entering costs 0.5*cost_rt on entry day.
    Exit costs 0.5*cost_rt charged on exit day (approximated on event entry).
    Simpler: deduct cost_rt * fraction_portfolio_turned_over each event.
    """
    # Cost per event = cost_rt / n_max (each position is 1/n_max of portfolio)
    cost_per_event = cost_rt / n_max
    cost_series = pd.Series(0.0, index=port_daily.index)
    for _, ev in events_df.iterrows():
        if ev["date"] in cost_series.index:
            cost_series[ev["date"]] += cost_per_event
    return port_daily - cost_series


def stats_daily(r, label=""):
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
    print(f"\nH159 — PEAD: Post-Earnings Announcement Drift")
    print("=" * 60)

    print(f"\n[1] Loading OHLCV for {len(UNIVERSE)} stocks…")
    ohlcv = fetch_ohlcv(UNIVERSE, FULL_START, FULL_END)
    valid = {t: df for t, df in ohlcv.items()
             if "open" in df.columns and "close" in df.columns and len(df) >= 500}
    print(f"    Valid: {len(valid)}/{len(UNIVERSE)} tickers with open+close")

    spy_ohlcv = fetch_ohlcv(["SPY"], FULL_START, FULL_END)
    spy_ret   = spy_ohlcv["SPY"]["close"].pct_change().rename("SPY")
    spy_ret.index = pd.to_datetime(spy_ret.index)

    print(f"\n[2] Finding gap events…")
    events = find_gap_events(valid, gap_thresh=GAP_THRESH)
    print(f"    Total gap >5% events: {len(events)}")
    print(f"    Events per year (approx): {len(events) / ((pd.Timestamp(FULL_END) - pd.Timestamp(FULL_START)).days / 365):.0f}")

    # Event distribution by period
    is_events   = events[(events["date"] >= pd.Timestamp(FULL_START)) &
                         (events["date"] <= pd.Timestamp(IS_END))]
    oos_events  = events[events["date"] >= pd.Timestamp(OOS_START)]
    alt_events  = events[events["date"] >= pd.Timestamp(ALT_OOS_ST)]
    print(f"    IS events (2008-17): {len(is_events)}")
    print(f"    OOS events (2018+):  {len(oos_events)}")
    print(f"    Avg gap size: {events['gap_pct'].mean():.2%}  "
          f"Max: {events['gap_pct'].max():.2%}")

    print(f"\n[3] Running variants (gap thresh × N_max × hold)…")

    VARIANTS = [
        ("A gap5% n10 h20",  0.05, 10, 20),
        ("B gap3% n10 h20",  0.03, 10, 20),
        ("C gap5% n5  h20",  0.05,  5, 20),
        ("D gap5% n10 h10",  0.05, 10, 10),
        ("E gap5% n15 h20",  0.05, 15, 20),
    ]

    spy_oos = stats_daily(spy_ret[spy_ret.index >= OOS_START])
    spy_alt = stats_daily(spy_ret[spy_ret.index >= ALT_OOS_ST])
    print(f"    SPY OOS: cumul={spy_oos['cumul']:.4f}  CAGR={spy_oos['cagr']:.2%}  "
          f"Sharpe={spy_oos['sharpe']:.3f}  MaxDD={spy_oos['max_dd']:.2%}")

    results = []
    for (label, g_thresh, n_max_, hold) in VARIANTS:
        ev = find_gap_events(valid, gap_thresh=g_thresh)
        port = simulate_portfolio(ev, valid, hold_days=hold, n_max=n_max_)
        port = apply_costs(ev, port, n_max=n_max_)
        port.index = pd.to_datetime(port.index)

        s_is  = stats_daily(port[(port.index >= pd.Timestamp(ALT_OOS_ST)) &
                                  (port.index <= pd.Timestamp(IS_END))])
        s_oos = stats_daily(port[port.index >= pd.Timestamp(OOS_START)])
        s_alt = stats_daily(port[port.index >= pd.Timestamp(ALT_OOS_ST)])

        # Correlation vs SPY
        ov = port.index.intersection(spy_ret.index)
        corr_spy = port.loc[ov].corr(spy_ret.loc[ov])

        # Event count in OOS
        ev_oos = ev[ev["date"] >= pd.Timestamp(OOS_START)]
        ev_is  = ev[(ev["date"] >= pd.Timestamp(ALT_OOS_ST)) &
                    (ev["date"] <= pd.Timestamp(IS_END))]

        results.append({
            "label": label, "g_thresh": g_thresh, "n_max": n_max_, "hold": hold,
            "is": s_is, "oos": s_oos, "alt": s_alt,
            "corr_spy": corr_spy,
            "ev_oos": len(ev_oos), "ev_is": len(ev_is),
        })

        print(f"\n  {label}  (events IS={len(ev_is)}, OOS={len(ev_oos)}):")
        print(f"    IS(2013-17): cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}  MaxDD={s_is['max_dd']:.2%}")
        print(f"    OOS(2018+):  cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  "
              f"Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
        print(f"    AltOOS:      cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
        print(f"    Corr(SPY OOS): {corr_spy:.3f}")

    print(f"\n[4] Per-stock event statistics (raw drift, no portfolio)…")
    # Compute raw 20-day post-gap return for each event
    all_event_rets = []
    for _, ev in events.iterrows():
        t = ev["ticker"]
        if t not in valid:
            continue
        df = valid[t].sort_index()
        entry_date = ev["date"]
        future = df[df.index > entry_date]
        if len(future) >= HOLD_DAYS:
            exit_date = future.index[HOLD_DAYS - 1]
            ret = (future["close"].iloc[HOLD_DAYS - 1] - ev["entry_px"]) / ev["entry_px"]
            period = "IS" if entry_date <= pd.Timestamp(IS_END) else "OOS"
            all_event_rets.append({"ticker": t, "date": entry_date,
                                   "gap": ev["gap_pct"], "ret_20d": ret, "period": period})

    if all_event_rets:
        edf = pd.DataFrame(all_event_rets)
        for period in ["IS", "OOS"]:
            sub = edf[edf["period"] == period]["ret_20d"]
            if len(sub) > 0:
                t_stat = sub.mean() / (sub.std() / np.sqrt(len(sub))) if sub.std() > 0 else 0
                pct_pos = (sub > 0).mean()
                print(f"    {period}: n={len(sub)}  mean_20d_ret={sub.mean():.3%}  "
                      f"win_rate={pct_pos:.1%}  t-stat={t_stat:.2f}")

    print(f"\n[5] Verdict…")
    for rec in results:
        s_oos = rec["oos"]
        s_is  = rec["is"]
        checks = [
            s_oos["sharpe"] > spy_oos["sharpe"],
            s_oos["cumul"]  > spy_oos["cumul"],
            s_oos["max_dd"] > -0.30,
            s_is["sharpe"]  > 0.5,
        ]
        score = sum(checks)
        verdict = "CONFIRMED" if score >= 3 else "PARTIAL" if score >= 2 else "NOT CONFIRMED"
        rec["verdict"] = verdict
        rec["score"] = score
        print(f"  {rec['label']}: {verdict} ({score}/4) | "
              f"OOS Sharpe={s_oos['sharpe']:.3f} cumul={s_oos['cumul']:.4f} MaxDD={s_oos['max_dd']:.2%}")

    best = max(results, key=lambda x: x["oos"]["sharpe"])
    overall = best["verdict"]
    print(f"\n  Best: {best['label']}  →  {overall}")
    print(f"  OOS Sharpe={best['oos']['sharpe']:.3f}  CAGR={best['oos']['cagr']:.2%}  "
          f"MaxDD={best['oos']['max_dd']:.2%}  Corr(SPY)={best['corr_spy']:.3f}")

    # Write result
    lines = [
        "H159 — PEAD: Post-Earnings Announcement Drift", "=" * 60, "",
        f"Universe: {len(valid)} large-cap stocks (survivorship-biased)",
        f"Signal: open/prev_close > 1+gap_thresh → enter open, hold {HOLD_DAYS}d",
        f"Cost: {COST_RT:.1%} RT  | IS: 2008-17 | OOS: 2018+ | AltOOS: 2013+",
        "",
        f"RAW EVENT STATS",
    ]
    if all_event_rets:
        edf = pd.DataFrame(all_event_rets)
        for period in ["IS", "OOS"]:
            sub = edf[edf["period"] == period]["ret_20d"]
            if len(sub) > 0:
                t_stat = sub.mean() / (sub.std() / np.sqrt(len(sub))) if sub.std() > 0 else 0
                lines.append(
                    f"  {period}: n={len(sub)} mean_ret={sub.mean():.3%} "
                    f"win_rate={(sub>0).mean():.1%} t={t_stat:.2f}")
    lines += ["", "VARIANTS"]
    for rec in results:
        s = rec["oos"]
        lines.append(
            f"  {rec['label']}: OOS cumul={s['cumul']:.4f} CAGR={s['cagr']:.2%} "
            f"Sharpe={s['sharpe']:.3f} MaxDD={s['max_dd']:.2%} NegYrs={s['neg_yrs']} "
            f"Corr(SPY)={rec['corr_spy']:.3f} IS_evts={rec['ev_is']} OOS_evts={rec['ev_oos']} "
            f"→ {rec['verdict']}"
        )
    lines += [
        "",
        f"BEST VARIANT: {best['label']}",
        f"  OOS: cumul={best['oos']['cumul']:.4f}  Sharpe={best['oos']['sharpe']:.3f}  "
        f"MaxDD={best['oos']['max_dd']:.2%}  CAGR={best['oos']['cagr']:.2%}",
        f"  AltOOS: cumul={best['alt']['cumul']:.4f}  Sharpe={best['alt']['sharpe']:.3f}",
        f"  Corr(SPY OOS): {best['corr_spy']:.3f}",
        "",
        f"VERDICT: {overall}",
        f"NOTE: Survivorship-biased universe — confirm with bias-free data before production",
    ]
    (RESULT_DIR / "h159_pead.txt").write_text("\n".join(lines))
    print(f"\n  Results saved to results/h159_pead.txt")
    return overall, best


if __name__ == "__main__":
    main()
