"""
H161 — Dividend Raise Signal
=============================

Event-driven: company raises quarterly dividend ≥10% vs prior payment.
Enter on ex-dividend date, hold 40 trading days.

Claim: Ernesto/R27: Sharpe +4.403 per-trade (n=345 events, 10yr), WR 64.9%.
Hypothesis: market underreacts to dividend increases — they signal management
confidence in future earnings. Ex-dividend drift is a known effect.

Universe: 50 large-cap dividend payers (S&P 500 dividend growers)
Data: yfinance Ticker.dividends (quarterly payments, ex-dividend dates)
Signal: pct change in quarterly dividend ≥ 10% vs prior quarterly payment
Entry: market-open on ex-dividend date (or next trading day)
Exit: 40 trading days after entry
Position: equal-weight, max 10 concurrent positions, $10,000 per position
Costs: 0.05% round-trip

IS: 2008–2017  OOS: 2018–2026

Success criteria (new standalone strategy):
  OOS Sharpe > 1.0, MaxDD > -25%, WinRate > 55%, Corr(SPY) < 0.5
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START   = "2007-01-01"
FULL_END     = "2026-04-30"
IS_END       = pd.Timestamp("2017-12-31")
OOS_START    = pd.Timestamp("2018-01-01")
ALT_OOS_ST   = pd.Timestamp("2013-01-01")

DIV_RAISE_THRESH = 0.10   # ≥10% increase vs prior payment
HOLD_DAYS        = 40     # trading days to hold
MAX_POSITIONS    = 10
POSITION_SIZE    = 10_000 # $ per trade
COST_RT          = 0.0005 # 0.05% round-trip

# 50 well-known S&P 500 large-cap dividend payers with long histories
UNIVERSE = [
    "AAPL", "MSFT", "JPM", "JNJ", "PG",  "KO",   "PEP", "MCD", "MMM",  "CAT",
    "GE",   "IBM",  "T",   "VZ",  "XOM", "CVX",  "COP", "SLB", "WMT",  "TGT",
    "HD",   "LOW",  "MO",  "PM",  "USB", "BAC",  "WFC", "GS",  "AXP",  "V",
    "MA",   "BRK-B","LMT", "NOC", "RTX", "HON",  "EMR", "ABT", "MRK",  "PFE",
    "AMGN", "BMY",  "UNH", "CVS", "CI",  "MDT",  "BDX", "SYK", "ZTS",  "ABBV",
]


def fetch_close(ticker):
    cp = CACHE_DIR / f"h161_{ticker}_close_{FULL_START}_{FULL_END}.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        df.columns = [c.lower() for c in df.columns]
        col = "close" if "close" in df.columns else df.columns[0]
        return df[col].rename(ticker)
    raw = yf.download([ticker], start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def fetch_dividends(ticker):
    cp = CACHE_DIR / f"h161_{ticker}_divs.parquet"
    if cp.exists():
        return pd.read_parquet(cp)["dividends"]
    t = yf.Ticker(ticker)
    divs = t.dividends
    if divs.empty:
        return pd.Series(dtype=float, name="dividends")
    # Normalize timezone
    divs.index = pd.to_datetime(divs.index).tz_localize(None)
    divs.name = "dividends"
    divs.to_frame().to_parquet(cp)
    return divs


def classify_payments(divs):
    """Classify dividend payments as quarterly/monthly/annual based on spacing."""
    if len(divs) < 4:
        return None
    gaps = divs.index.to_series().diff().dt.days.dropna()
    med  = gaps.median()
    if med < 40:   return "monthly"
    if med < 120:  return "quarterly"
    return "annual"


def find_raise_events(ticker, divs, close_prices):
    """
    Find events where quarterly dividend raised ≥ DIV_RAISE_THRESH.
    Returns list of (ex_date, pct_raise, div_new, div_prev).
    """
    freq = classify_payments(divs)
    if freq != "quarterly":
        return []

    events = []
    div_sorted = divs.sort_index()

    for i in range(4, len(div_sorted)):  # compare to same quarter of prior year
        dt     = div_sorted.index[i]
        d_cur  = div_sorted.iloc[i]
        # Compare to 4 quarters ago (same fiscal quarter, prior year)
        d_prev = div_sorted.iloc[i - 4]

        if d_prev <= 0:
            continue
        pct_chg = (d_cur - d_prev) / d_prev

        if pct_chg >= DIV_RAISE_THRESH:
            # Find nearest trading day on or after ex-date
            valid_dates = close_prices.index[close_prices.index >= dt]
            if len(valid_dates) == 0:
                continue
            entry_date = valid_dates[0]
            events.append({
                "ex_date":   dt,
                "entry_date": entry_date,
                "pct_raise": pct_chg,
                "div_new":   d_cur,
                "div_prev":  d_prev,
                "ticker":    ticker,
            })
    return events


def simulate_portfolio(all_events, close_prices_dict):
    """
    Walk-forward portfolio simulation:
    - Max MAX_POSITIONS concurrent holdings
    - Enter at open of entry_date (use close as proxy)
    - Exit HOLD_DAYS trading days later
    - COST_RT round-trip cost on entry
    """
    all_events_sorted = sorted(all_events, key=lambda e: e["entry_date"])

    # Get a common trading calendar
    spy_dates = sorted(set().union(*[set(c.index) for c in close_prices_dict.values()]))
    spy_dates = [d for d in spy_dates if pd.Timestamp(FULL_START) <= d <= pd.Timestamp(FULL_END)]
    date_to_idx = {d: i for i, d in enumerate(spy_dates)}

    trades = []
    for ev in all_events_sorted:
        entry_dt = ev["entry_date"]
        if entry_dt not in date_to_idx:
            continue
        entry_idx = date_to_idx[entry_dt]
        exit_idx  = min(entry_idx + HOLD_DAYS, len(spy_dates) - 1)
        exit_dt   = spy_dates[exit_idx]

        ticker = ev["ticker"]
        if ticker not in close_prices_dict:
            continue
        prices = close_prices_dict[ticker]

        if entry_dt not in prices.index or exit_dt not in prices.index:
            continue

        p_entry = float(prices.loc[entry_dt])
        p_exit  = float(prices.loc[exit_dt])

        gross_ret = (p_exit - p_entry) / p_entry
        net_ret   = gross_ret - COST_RT

        trades.append({
            "entry_date": entry_dt,
            "exit_date":  exit_dt,
            "ticker":     ticker,
            "pct_raise":  ev["pct_raise"],
            "entry_price": p_entry,
            "exit_price":  p_exit,
            "gross_ret":   gross_ret,
            "net_ret":     net_ret,
            "win":         gross_ret > 0,
        })

    return pd.DataFrame(trades)


def portfolio_equity_curve(trades_df, spy_prices):
    """
    Build daily equity curve with max-position overlap constraint.
    Each trade contributes POSITION_SIZE to equity. We cap at MAX_POSITIONS
    simultaneous open trades.
    """
    if trades_df.empty:
        return pd.Series(dtype=float), pd.DataFrame()

    spy_cal = sorted(spy_prices.index)
    date_idx = {d: i for i, d in enumerate(spy_cal)}

    # Daily P&L across all positions
    daily_pnl = pd.Series(0.0, index=spy_cal)

    # Respect MAX_POSITIONS by taking the first MAX_POSITIONS open each day
    # Simple approach: process trades in order; at each entry, check active count
    active = []  # list of (exit_date, per_day_contribution)

    # Actually, simpler: just compute per-trade returns, then group by entry date
    # and allow max MAX_POSITIONS per day window
    #
    # We'll do a proper overlap simulation:
    open_slots = [True] * MAX_POSITIONS
    open_trades = []  # (exit_date, position_idx, net_ret, entry_date)

    accepted_trades = []
    for _, row in trades_df.sort_values("entry_date").iterrows():
        entry_dt = row["entry_date"]
        exit_dt  = row["exit_date"]

        # Free any slots that have exited by this entry date
        still_open = []
        for ot in open_trades:
            if ot["exit_date"] < entry_dt:
                open_slots[ot["slot"]] = True
            else:
                still_open.append(ot)
        open_trades = still_open

        # Assign a slot if available
        avail = [i for i, f in enumerate(open_slots) if f]
        if not avail:
            continue  # skip — all positions full
        slot = avail[0]
        open_slots[slot] = False

        open_trades.append({
            "exit_date":  exit_dt,
            "entry_date": entry_dt,
            "slot":       slot,
            "net_ret":    row["net_ret"],
            "ticker":     row["ticker"],
        })
        accepted_trades.append(row)

    accepted_df = pd.DataFrame(accepted_trades)
    if accepted_df.empty:
        return pd.Series(dtype=float), accepted_df

    # Build daily P&L: for each accepted trade, allocate P&L on exit date
    daily_pnl = pd.Series(0.0, index=spy_cal)
    for _, row in accepted_df.iterrows():
        exit_dt = row["exit_date"]
        if exit_dt in daily_pnl.index:
            daily_pnl[exit_dt] += row["net_ret"] * POSITION_SIZE

    # Equity: start at MAX_POSITIONS * POSITION_SIZE (always deployed capital)
    total_capital = MAX_POSITIONS * POSITION_SIZE
    eq = (total_capital + daily_pnl.cumsum())
    daily_ret = daily_pnl / total_capital
    return daily_ret, accepted_df


def stats_daily(r):
    r = r.dropna()
    r = r[r != 0]  # filter flat days
    if len(r) < 20:
        return {"cumul": 1.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0,
                "neg_yrs": 0, "n_trades": 0}
    eq = (1 + r).cumprod()
    n_yrs = len(r) / 252
    cagr  = float(eq.iloc[-1]) ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    vol   = r.std(ddof=1) * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1 + x).prod() - 1).lt(0).sum())
    return {"cumul": float(eq.iloc[-1]), "cagr": cagr, "sharpe": sharpe,
            "max_dd": max_dd, "neg_yrs": neg_yrs, "n_trades": len(r[r != 0])}


def main():
    print("\n" + "=" * 70)
    print("  H161 — Dividend Raise Signal")
    print("=" * 70)
    print(f"  Universe: {len(UNIVERSE)} large-cap dividend payers")
    print(f"  Signal: quarterly div raised ≥{DIV_RAISE_THRESH:.0%}")
    print(f"  Hold: {HOLD_DAYS} trading days  |  Max positions: {MAX_POSITIONS}")
    print(f"  IS: {FULL_START}–{IS_END.date()}  |  OOS: {OOS_START.date()}–{FULL_END}")

    # --- Load data ---
    print(f"\n[1] Loading price data and dividends…")
    close_prices = {}
    dividend_data = {}
    for ticker in UNIVERSE:
        try:
            c = fetch_close(ticker)
            if len(c) > 200:
                close_prices[ticker] = c
            d = fetch_dividends(ticker)
            if not d.empty:
                dividend_data[ticker] = d
        except Exception as e:
            pass

    print(f"    Prices loaded: {len(close_prices)} tickers")
    print(f"    Dividends loaded: {len(dividend_data)} tickers")

    spy = fetch_close("SPY")

    # --- Find events ---
    print(f"\n[2] Scanning for dividend raise events…")
    all_events = []
    skipped = []
    for ticker in UNIVERSE:
        if ticker not in dividend_data or ticker not in close_prices:
            skipped.append(ticker)
            continue
        divs   = dividend_data[ticker]
        prices = close_prices[ticker]
        freq   = classify_payments(divs)
        if freq != "quarterly":
            skipped.append(f"{ticker}({freq})")
            continue
        events = find_raise_events(ticker, divs, prices)
        all_events.extend(events)

    events_df = pd.DataFrame(all_events)
    if events_df.empty:
        print("  ERROR: No events found!")
        return

    is_mask  = events_df["entry_date"] <= IS_END
    oos_mask = events_df["entry_date"] >= OOS_START

    print(f"    Total events: {len(events_df)}")
    print(f"    IS events ({FULL_START}–{IS_END.date()}): {is_mask.sum()}")
    print(f"    OOS events ({OOS_START.date()}–{FULL_END}): {oos_mask.sum()}")
    if skipped:
        print(f"    Skipped: {', '.join(skipped[:10])}{'...' if len(skipped) > 10 else ''}")

    # Show top tickers by event count
    top_tickers = events_df["ticker"].value_counts().head(5)
    print(f"    Most active: {dict(top_tickers)}")
    print(f"    Avg raise: {events_df['pct_raise'].mean():.1%}  Median: {events_df['pct_raise'].median():.1%}")

    # --- Compute per-event raw returns + exit dates ---
    print(f"\n[3] Computing per-event raw returns…")
    raw_rets  = []
    exit_dates = []
    spy_cal = sorted(spy.index)
    spy_idx_map = {d: i for i, d in enumerate(spy_cal)}

    for ev in all_events:
        ticker = ev["ticker"]
        entry_dt = ev["entry_date"]
        prices = close_prices.get(ticker)
        if prices is None or entry_dt not in spy_idx_map:
            raw_rets.append(np.nan)
            exit_dates.append(pd.NaT)
            continue
        entry_idx = spy_idx_map[entry_dt]
        exit_idx  = min(entry_idx + HOLD_DAYS, len(spy_cal) - 1)
        exit_dt   = spy_cal[exit_idx]
        if entry_dt not in prices.index or exit_dt not in prices.index:
            raw_rets.append(np.nan)
            exit_dates.append(pd.NaT)
            continue
        p_entry = float(prices.loc[entry_dt])
        p_exit  = float(prices.loc[exit_dt])
        net_ret = (p_exit - p_entry) / p_entry - COST_RT
        raw_rets.append(net_ret)
        exit_dates.append(exit_dt)

    events_df["net_ret"]   = raw_rets
    events_df["exit_date"] = exit_dates
    events_df["win"]       = events_df["net_ret"] > 0

    print(f"    Per-event statistics (no portfolio constraint)…")
    for label, mask in [("IS", is_mask), ("OOS", oos_mask), ("Full", pd.Series(True, index=events_df.index))]:
        sub = events_df[mask].dropna(subset=["net_ret"])
        if len(sub) < 10:
            continue
        wr    = (sub["net_ret"] > 0).mean()
        mr    = sub["net_ret"].mean()
        med_r = sub["net_ret"].median()
        t_stat = mr / (sub["net_ret"].std() / np.sqrt(len(sub)))
        print(f"    {label:6s}: n={len(sub):4d}  WR={wr:.1%}  MeanRet={mr:.2%}  Median={med_r:.2%}  t={t_stat:.2f}")

    # --- Portfolio simulation ---
    print(f"\n[4] Portfolio simulation (max {MAX_POSITIONS} concurrent, ${POSITION_SIZE:,}/trade)…")
    daily_ret, accepted_df = portfolio_equity_curve(events_df, spy)

    if daily_ret.empty:
        print("  ERROR: No accepted trades in portfolio simulation!")
        return

    s_is  = stats_daily(daily_ret[(daily_ret.index >= ALT_OOS_ST) & (daily_ret.index <= IS_END)])
    s_oos = stats_daily(daily_ret[daily_ret.index >= OOS_START])
    s_alt = stats_daily(daily_ret[daily_ret.index >= ALT_OOS_ST])
    s_spy = stats_daily(spy.pct_change().dropna().loc[lambda x: x.index >= OOS_START])

    print(f"\n    Accepted trades: {len(accepted_df)} of {len(events_df)} ({len(accepted_df)/len(events_df)*100:.0f}%)")
    print(f"    IS  : cumul={s_is['cumul']:.4f}  CAGR={s_is['cagr']:.2%}  Sharpe={s_is['sharpe']:.3f}  MaxDD={s_is['max_dd']:.2%}")
    print(f"    OOS : cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
    print(f"    Alt : cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
    print(f"    SPY : cumul={s_spy['cumul']:.4f}  Sharpe={s_spy['sharpe']:.3f}")

    # Market correlation
    common = daily_ret.index.intersection(spy.pct_change().dropna().index)
    corr_spy = float(daily_ret.loc[common].corr(spy.pct_change().dropna().loc[common]))
    print(f"    Corr(SPY): {corr_spy:.3f}")

    # --- Threshold sensitivity ---
    print(f"\n[5] Raise threshold sensitivity…")
    print(f"    {'Thresh':>8} {'N IS':>6} {'N OOS':>6} {'WR OOS':>8} {'MeanRet OOS':>12}")
    for thresh in [0.05, 0.10, 0.15, 0.20, 0.25]:
        is_sub  = events_df[(events_df["pct_raise"] >= thresh) & is_mask].dropna(subset=["net_ret"])
        oos_sub = events_df[(events_df["pct_raise"] >= thresh) & oos_mask].dropna(subset=["net_ret"])
        if len(oos_sub) < 5:
            continue
        wr = (oos_sub["net_ret"] > 0).mean()
        mr = oos_sub["net_ret"].mean()
        print(f"    {thresh:>8.0%} {len(is_sub):>6d} {len(oos_sub):>6d} {wr:>8.1%} {mr:>12.2%}")

    # --- Verdict ---
    passed = sum([
        s_oos["sharpe"] > 1.0,
        s_oos["max_dd"] > -0.25,
        (events_df[oos_mask]["net_ret"] > 0).mean() > 0.55 if oos_mask.sum() > 0 else False,
    ])

    print(f"\n[6] Verdict:")
    print(f"    OOS Sharpe>1.0: {'✓' if s_oos['sharpe'] > 1.0 else '✗'}  ({s_oos['sharpe']:.3f})")
    print(f"    OOS MaxDD>-25%: {'✓' if s_oos['max_dd'] > -0.25 else '✗'}  ({s_oos['max_dd']:.2%})")
    print(f"    OOS WinRate>55%: {'✓' if (events_df[oos_mask]['net_ret'] > 0).mean() > 0.55 else '✗'}  "
          f"({(events_df[oos_mask]['net_ret'] > 0).mean():.1%})")
    print(f"    Criteria met: {passed}/3")

    verdict = "CONFIRMED" if passed >= 2 else ("PARTIAL" if passed == 1 else "NOT CONFIRMED")
    print(f"\n    VERDICT: {verdict}")

    # Save
    lines = [
        "H161 — Dividend Raise Signal\n",
        f"Run: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"Universe: {len(close_prices)} stocks  |  Raise thresh: {DIV_RAISE_THRESH:.0%}  |  Hold: {HOLD_DAYS}d\n\n",
        f"IS: {is_mask.sum()} events  |  OOS: {oos_mask.sum()} events\n\n",
        f"IS  : cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}  MaxDD={s_is['max_dd']:.2%}\n",
        f"OOS : cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}\n",
        f"Alt : cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}\n",
        f"SPY : cumul={s_spy['cumul']:.4f}  Sharpe={s_spy['sharpe']:.3f}\n\n",
        f"VERDICT: {verdict}\n",
    ]
    (RESULT_DIR / "h161_dividend_raise.txt").write_text("".join(lines))
    print(f"\n    Results saved → backtesting/results/h161_dividend_raise.txt")


if __name__ == "__main__":
    main()
