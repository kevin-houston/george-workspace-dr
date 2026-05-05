"""
H162 — Covered Calls Around Ex-Dividend Date
=============================================

Hypothesis: Selling 2% OTM calls 10 trading days before ex-dividend date
outperforms static covered calls (JEPI-like).

Based on Ernesto/R25: Sharpe +2.643, 3× better than static covered calls.

Economic rationale:
  1. Dividend-capture buying can lift price before ex-date
  2. On ex-date, stock drops ≈ dividend amount, pushing below strike
  3. Short call tends to expire worthless → keep full premium
  4. IV may be elevated pre-ex-date (selling overpriced vol)

Universe: 50 large-cap dividend payers (same as H161)
Signal:   Every quarterly ex-dividend date fires an event
Entry:    10 trading days BEFORE ex-date — sell 2% OTM call + long stock
Exit:     ON ex-dividend date — close entire position
P&L:      stock_return + call_premium_collected − call_intrinsic_at_exit
Options:  Black-Scholes priced with 20-day historical vol as IV proxy

IS: 2008–2017  OOS: 2018–2026

Success criteria:
  OOS Sharpe > 1.0, MaxDD > -25%, WinRate > 55%
  covered-call returns > stock-only returns for same events
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from scipy.stats import norm

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START    = "2007-01-01"
FULL_END      = "2026-04-30"
IS_END        = pd.Timestamp("2017-12-31")
OOS_START     = pd.Timestamp("2018-01-01")
ALT_OOS_ST    = pd.Timestamp("2013-01-01")

OTM_STRIKE    = 0.02    # baseline: 2% OTM call
HOLD_DAYS     = 10      # trading days before ex-date to enter (baseline)
MAX_POSITIONS = 10
POSITION_SIZE = 10_000  # $ per position
COST_RT       = 0.0005  # round-trip transaction cost (stock leg only)
RISK_FREE     = 0.05    # annualized risk-free rate
HV_WINDOW     = 20      # days for historical vol
MIN_HV        = 0.05    # floor for IV (5% annualized)

UNIVERSE = [
    "AAPL", "MSFT", "JPM", "JNJ", "PG",  "KO",   "PEP", "MCD", "MMM",  "CAT",
    "GE",   "IBM",  "T",   "VZ",  "XOM", "CVX",  "COP", "SLB", "WMT",  "TGT",
    "HD",   "LOW",  "MO",  "PM",  "USB", "BAC",  "WFC", "GS",  "AXP",  "V",
    "MA",   "BRK-B","LMT", "NOC", "RTX", "HON",  "EMR", "ABT", "MRK",  "PFE",
    "AMGN", "BMY",  "UNH", "CVS", "CI",  "MDT",  "BDX", "SYK", "ZTS",  "ABBV",
]


# ---------------------------------------------------------------------------
# Black-Scholes
# ---------------------------------------------------------------------------

def bs_call(S, K, T, r, sigma):
    """European call price via Black-Scholes."""
    S, K, T, r, sigma = float(S), float(K), float(T), float(r), float(sigma)
    if T < 1e-6 or sigma < 1e-6:
        return max(0.0, S - K)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def fetch_close(ticker):
    cp = CACHE_DIR / f"h162_{ticker}_close.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        df.columns = [c.lower() for c in df.columns]
        col = "close" if "close" in df.columns else df.columns[0]
        return df[col].rename(ticker)
    raw = yf.download([ticker], start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close = close.rename(ticker)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close.to_frame().to_parquet(cp)
    return close


def fetch_dividends(ticker):
    cp = CACHE_DIR / f"h162_{ticker}_divs.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    try:
        t = yf.Ticker(ticker)
        divs = t.dividends
        if divs.empty:
            return pd.Series(dtype=float, name=ticker)
        divs.index = pd.to_datetime(divs.index).tz_localize(None)
        divs = divs[(divs.index >= FULL_START) & (divs.index <= FULL_END)]
        divs.to_frame().to_parquet(cp)
        return divs
    except Exception:
        return pd.Series(dtype=float, name=ticker)


# ---------------------------------------------------------------------------
# Quarterly dividend classification
# ---------------------------------------------------------------------------

def classify_quarterly(div_series):
    """
    Return filtered series of quarterly dividend payments.
    Removes duplicates within 10 days, keeps years with 3-6 payments.
    """
    if len(div_series) < 3:
        return pd.Series(dtype=float)
    s = div_series.sort_index()
    # Deduplicate within 10-day windows
    keep = [s.index[0]]
    for dt in s.index[1:]:
        if (dt - keep[-1]).days >= 10:
            keep.append(dt)
    s = s.loc[keep]
    # Keep only years with 3-6 payments (quarterly, not monthly or annual)
    yr = s.index.year
    annual_cnt = pd.Series(yr).value_counts()
    valid_yrs = set(annual_cnt[annual_cnt.between(3, 6)].index)
    return s[pd.Series(yr, index=s.index).isin(valid_yrs)]


# ---------------------------------------------------------------------------
# Historical volatility
# ---------------------------------------------------------------------------

def rolling_hv(close_series, window=HV_WINDOW):
    """Annualized historical volatility: rolling std of log returns × sqrt(252)."""
    log_ret = np.log(close_series / close_series.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252)


# ---------------------------------------------------------------------------
# Event builder
# ---------------------------------------------------------------------------

def build_events(ticker, close_s, hv_s, div_s, spy_cal, spy_idx_map):
    """Build covered-call events for one ticker."""
    q_divs = classify_quarterly(div_s)
    if q_divs.empty:
        return []

    events = []
    for ex_date in q_divs.index:
        ex_date = pd.Timestamp(ex_date)

        # Snap ex_date to nearest available SPY trading day
        if ex_date not in spy_idx_map:
            candidates = [d for d in spy_cal if d >= ex_date]
            if not candidates:
                continue
            ex_snap = candidates[0]
        else:
            ex_snap = ex_date

        ex_idx = spy_idx_map.get(ex_snap)
        if ex_idx is None or ex_idx < HOLD_DAYS + HV_WINDOW + 5:
            continue

        entry_idx = ex_idx - HOLD_DAYS
        entry_date = spy_cal[entry_idx]

        # Price availability
        if entry_date not in close_s.index or ex_snap not in close_s.index:
            continue

        S_entry = float(close_s.loc[entry_date])
        S_exit  = float(close_s.loc[ex_snap])
        if S_entry <= 0 or S_exit <= 0 or np.isnan(S_entry) or np.isnan(S_exit):
            continue

        # Historical vol at entry
        if entry_date not in hv_s.index:
            continue
        hv = float(hv_s.loc[entry_date])
        if np.isnan(hv) or hv <= 0:
            hv = MIN_HV
        hv = max(hv, MIN_HV)

        # Black-Scholes
        K = S_entry * (1.0 + OTM_STRIKE)
        T = HOLD_DAYS / 252.0
        call_premium = bs_call(S_entry, K, T, RISK_FREE, hv)
        call_payoff  = max(0.0, S_exit - K)

        stock_ret   = (S_exit - S_entry) / S_entry - COST_RT
        call_ret    = (call_premium - call_payoff) / S_entry
        cc_ret      = stock_ret + call_ret

        events.append({
            "ticker":      ticker,
            "entry_date":  entry_date,
            "exit_date":   ex_snap,
            "S_entry":     S_entry,
            "S_exit":      S_exit,
            "K":           K,
            "hv":          hv,
            "T":           T,
            "call_premium": call_premium,
            "call_payoff":  call_payoff,
            "div_pct":      q_divs.loc[ex_date] / S_entry if ex_date in q_divs.index else np.nan,
            "stock_ret":    stock_ret,
            "call_ret":     call_ret,
            "cc_ret":       cc_ret,
            "win":          cc_ret > 0,
        })

    return events


# ---------------------------------------------------------------------------
# Portfolio equity curve  (exit-day P&L model, consistent with H161)
# ---------------------------------------------------------------------------

def portfolio_equity_curve(events_df, spy_prices, ret_col="cc_ret"):
    if events_df.empty:
        return pd.Series(dtype=float), pd.DataFrame()

    spy_cal = sorted(spy_prices.index)

    open_slots  = [True] * MAX_POSITIONS
    open_trades = []
    accepted    = []

    for _, row in events_df.sort_values("entry_date").iterrows():
        entry_dt = pd.Timestamp(row["entry_date"])
        exit_dt  = pd.Timestamp(row["exit_date"])

        # Free expired slots
        still_open = []
        for ot in open_trades:
            if ot["exit_date"] < entry_dt:
                open_slots[ot["slot"]] = True
            else:
                still_open.append(ot)
        open_trades = still_open

        avail = [i for i, f in enumerate(open_slots) if f]
        if not avail:
            continue
        slot = avail[0]
        open_slots[slot] = False
        open_trades.append({"exit_date": exit_dt, "slot": slot})
        accepted.append(row)

    if not accepted:
        return pd.Series(dtype=float), pd.DataFrame()

    accepted_df = pd.DataFrame(accepted)
    daily_pnl   = pd.Series(0.0, index=spy_cal)

    for _, row in accepted_df.iterrows():
        exit_dt = pd.Timestamp(row["exit_date"])
        if exit_dt in daily_pnl.index:
            daily_pnl[exit_dt] += row[ret_col] * POSITION_SIZE

    total_capital = MAX_POSITIONS * POSITION_SIZE
    daily_ret = daily_pnl / total_capital
    return daily_ret, accepted_df


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def per_event_stats(df, label, ret_col="cc_ret"):
    sub = df.dropna(subset=[ret_col])
    if len(sub) < 5:
        print(f"    {label}: insufficient data (n={len(sub)})")
        return
    n  = len(sub)
    wr = (sub[ret_col] > 0).mean()
    mu = sub[ret_col].mean()
    se = sub[ret_col].std() / np.sqrt(n)
    t  = mu / se if se > 0 else 0
    prem_pct = (sub["call_premium"] / sub["S_entry"]).mean()
    print(f"    {label}: n={n}  WR={wr:.1%}  MeanRet={mu:.2%}"
          f"  Median={sub[ret_col].median():.2%}  t={t:.2f}"
          f"  AvgPremium={prem_pct:.3%}")


def stats_daily(r):
    r = r.dropna()
    if len(r) < 20:
        return {"cumul": 1.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0, "neg_yrs": 0}
    eq = (1 + r).cumprod()
    terminal = float(eq.iloc[-1])
    n_yrs = len(r) / 252
    cagr = (terminal ** (1 / n_yrs) - 1) if terminal > 0 else -1.0
    vol  = float(r.std() * np.sqrt(252))
    sharpe = (cagr / vol) if vol > 0 else 0.0
    rolling_max = eq.cummax()
    dd = (eq - rolling_max) / rolling_max
    max_dd = float(dd.min())
    neg_yrs = sum(1 for yr, grp in r.resample("YE") if (1 + grp).prod() < 1.0)
    return {"cumul": terminal, "cagr": cagr, "sharpe": sharpe,
            "max_dd": max_dd, "neg_yrs": neg_yrs}


# ---------------------------------------------------------------------------
# SPY reference
# ---------------------------------------------------------------------------

def fetch_spy():
    cp = CACHE_DIR / "h162_SPY_close.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        df.columns = [c.lower() for c in df.columns]
        col = "close" if "close" in df.columns else df.columns[0]
        return df[col].rename("SPY")
    raw = yf.download(["SPY"], start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    close = raw.xs("SPY", axis=1, level=1)["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
    close = close.rename("SPY")
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close.to_frame().to_parquet(cp)
    return close


# ---------------------------------------------------------------------------
# Sensitivity sweep
# ---------------------------------------------------------------------------

def sweep_params(all_events_df):
    """Per-event stats across (OTM, HoldDays) grid — no re-running BS."""
    print("\n[6] Parameter sensitivity (per-event, not portfolio)…")
    print(f"  {'OTM':>6}  {'HoldDays':>9}  {'N_OOS':>6}  {'WR_OOS':>7}  {'Ret_OOS':>8}  {'AvgPrem':>8}")
    for otm in [0.00, 0.01, 0.02, 0.03]:
        for hd in [5, 10, 15]:
            # Recompute returns with this OTM and hold period
            # (hold period changes timing but we don't re-fetch prices, so
            #  use the already-loaded events as a proxy by rescaling T only)
            T   = hd / 252.0
            sub = all_events_df.copy()
            sub["K2"]   = sub["S_entry"] * (1.0 + otm)
            # Re-price call at new strike
            sub["cp2"]  = sub.apply(
                lambda r: bs_call(r["S_entry"], r["K2"], T, RISK_FREE,
                                  max(float(r["hv"]), MIN_HV)), axis=1)
            # Payoff re-uses existing S_exit (conservative approximation
            # — actual S_exit would differ for hd≠10, but we only have
            # prices for the baseline HOLD_DAYS exit date)
            sub["py2"]  = (sub["S_exit"] - sub["K2"]).clip(lower=0)
            sub["ret2"] = sub["stock_ret"] + (sub["cp2"] - sub["py2"]) / sub["S_entry"]

            oos = sub[sub["exit_date"] >= OOS_START]
            if oos.empty:
                continue
            n   = len(oos)
            wr  = (oos["ret2"] > 0).mean()
            mu  = oos["ret2"].mean()
            ap  = (oos["cp2"] / oos["S_entry"]).mean()
            print(f"  {otm:>5.0%}  {hd:>9d}  {n:>6d}  {wr:>7.1%}  {mu:>8.2%}  {ap:>8.3%}")


# ---------------------------------------------------------------------------
# JEPI comparison
# ---------------------------------------------------------------------------

def jepi_comparison(spy_prices):
    """Load JEPI (launched May 2020) and compare to SPY."""
    print("\n[7] JEPI comparison (2020-05-20 → 2026-04-30)…")
    try:
        cp = CACHE_DIR / "h162_JEPI_close.parquet"
        if cp.exists():
            df  = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            jepi = df["close" if "close" in df.columns else df.columns[0]].rename("JEPI")
        else:
            raw  = yf.download(["JEPI"], start="2020-05-01", end=FULL_END,
                                auto_adjust=True, progress=False)
            jepi = (raw.xs("JEPI", axis=1, level=1)["Close"]
                    if isinstance(raw.columns, pd.MultiIndex) else raw["Close"])
            jepi = jepi.rename("JEPI")
            jepi.index = pd.to_datetime(jepi.index).tz_localize(None)
            jepi.to_frame().to_parquet(cp)

        start = jepi.index[0]
        spy_sub  = spy_prices[spy_prices.index >= start]
        jepi_sub = jepi[jepi.index >= start]

        spy_r  = spy_sub.pct_change().dropna()
        jepi_r = jepi_sub.pct_change().dropna()
        spy_s  = stats_daily(spy_r)
        jepi_s = stats_daily(jepi_r)

        print(f"    JEPI ({start.date()} → 2026-04-30):")
        print(f"      CAGR={jepi_s['cagr']:.1%}  Sharpe={jepi_s['sharpe']:.3f}"
              f"  MaxDD={jepi_s['max_dd']:.2%}  cumul={jepi_s['cumul']:.4f}x")
        print(f"    SPY (same window):")
        print(f"      CAGR={spy_s['cagr']:.1%}  Sharpe={spy_s['sharpe']:.3f}"
              f"  MaxDD={spy_s['max_dd']:.2%}  cumul={spy_s['cumul']:.4f}x")
    except Exception as e:
        print(f"    JEPI load failed: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    lines = []
    def out(s=""):
        print(s)
        lines.append(s)

    out()
    out("=" * 70)
    out("  H162 — Covered Calls Around Ex-Dividend Date")
    out("=" * 70)
    out(f"  Universe: {len(UNIVERSE)} large-cap dividend payers")
    out(f"  Signal:   sell {OTM_STRIKE:.0%} OTM call {HOLD_DAYS}d before ex-date")
    out(f"  Hold:     {HOLD_DAYS} trading days  |  Max positions: {MAX_POSITIONS}")
    out(f"  IS: 2008-01-01–2017-12-31  |  OOS: 2018-01-01–2026-04-30")
    out()

    # [1] Load data
    out("[1] Loading price data and dividends…")
    spy = fetch_spy()
    spy_cal     = sorted(spy.index)
    spy_idx_map = {d: i for i, d in enumerate(spy_cal)}

    close_dict = {}
    hv_dict    = {}
    div_dict   = {}

    for ticker in UNIVERSE:
        close_s = fetch_close(ticker)
        if close_s.empty or len(close_s) < 100:
            out(f"    Skipping {ticker}: insufficient price data")
            continue
        close_dict[ticker] = close_s
        hv_dict[ticker]    = rolling_hv(close_s)
        div_s = fetch_dividends(ticker)
        div_dict[ticker] = div_s

    out(f"    Prices loaded: {len(close_dict)} tickers")

    # [2] Build all events
    out("[2] Building covered-call events…")
    all_events = []
    skipped    = []
    for ticker in list(close_dict.keys()):
        evs = build_events(ticker, close_dict[ticker], hv_dict[ticker],
                           div_dict.get(ticker, pd.Series(dtype=float)),
                           spy_cal, spy_idx_map)
        if not evs:
            skipped.append(ticker)
        all_events.extend(evs)

    out(f"    Total events: {len(all_events)}")
    if not all_events:
        out("    BLOCKED: no events generated")
        return

    df = pd.DataFrame(all_events)
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["exit_date"]  = pd.to_datetime(df["exit_date"])

    is_df  = df[df["exit_date"] <= IS_END]
    oos_df = df[df["exit_date"] >= OOS_START]

    out(f"    IS events:  {len(is_df)}")
    out(f"    OOS events: {len(oos_df)}")
    if skipped:
        out(f"    Skipped (no dividends): {skipped}")

    avg_prem = (df["call_premium"] / df["S_entry"]).mean()
    avg_hv   = df["hv"].mean()
    out(f"    Avg call premium: {avg_prem:.3%} of stock price")
    out(f"    Avg historical vol used: {avg_hv:.1%}")

    # [3] Per-event statistics
    out("[3] Per-event statistics…")
    out("    COVERED CALL returns:")
    per_event_stats(is_df,  "IS   ", "cc_ret")
    per_event_stats(oos_df, "OOS  ", "cc_ret")
    per_event_stats(df,     "Full ", "cc_ret")
    out("    STOCK-ONLY returns (same events):")
    per_event_stats(is_df,  "IS   ", "stock_ret")
    per_event_stats(oos_df, "OOS  ", "stock_ret")
    out("    CALL-LEG-ONLY P&L (premium vs payoff):")
    per_event_stats(is_df,  "IS   ", "call_ret")
    per_event_stats(oos_df, "OOS  ", "call_ret")

    # [4] Portfolio simulation
    out("[4] Portfolio simulation (max 10 concurrent, $10,000/trade)…")

    spy_ret = spy.pct_change().dropna()
    spy_ret_is  = spy_ret[(spy_ret.index > pd.Timestamp("2008-01-01")) & (spy_ret.index <= IS_END)]
    spy_ret_oos = spy_ret[spy_ret.index >= OOS_START]
    spy_ret_alt = spy_ret[spy_ret.index >= ALT_OOS_ST]

    cc_ret,  cc_acc  = portfolio_equity_curve(df, spy)
    stk_ret, stk_acc = portfolio_equity_curve(df, spy, ret_col="stock_ret")

    cc_ret_is   = cc_ret[(cc_ret.index > pd.Timestamp("2008-01-01")) & (cc_ret.index <= IS_END)]
    cc_ret_oos  = cc_ret[cc_ret.index >= OOS_START]
    cc_ret_alt  = cc_ret[cc_ret.index >= ALT_OOS_ST]
    stk_ret_oos = stk_ret[stk_ret.index >= OOS_START]

    cc_is   = stats_daily(cc_ret_is)
    cc_oos  = stats_daily(cc_ret_oos)
    cc_alt  = stats_daily(cc_ret_alt)
    stk_oos = stats_daily(stk_ret_oos)
    spy_is  = stats_daily(spy_ret_is)
    spy_oos = stats_daily(spy_ret_oos)
    spy_alt = stats_daily(spy_ret_alt)

    corr_spy = float(cc_ret_oos.corr(spy_ret_oos.reindex(cc_ret_oos.index, fill_value=0)))

    n_acc = len(cc_acc) if not cc_acc.empty else 0
    n_tot = len(df)
    out(f"\n    Accepted trades: {n_acc} of {n_tot} ({n_acc/n_tot:.0%})")
    out(f"    IS  : cumul={cc_is['cumul']:.4f}  CAGR={cc_is['cagr']:.2%}"
        f"  Sharpe={cc_is['sharpe']:.3f}  MaxDD={cc_is['max_dd']:.2%}")
    out(f"    OOS : cumul={cc_oos['cumul']:.4f}  CAGR={cc_oos['cagr']:.2%}"
        f"  Sharpe={cc_oos['sharpe']:.3f}  MaxDD={cc_oos['max_dd']:.2%}"
        f"  NegYrs={cc_oos['neg_yrs']}")
    out(f"    Alt : cumul={cc_alt['cumul']:.4f}  Sharpe={cc_alt['sharpe']:.3f}")
    out(f"    SPY : cumul={spy_oos['cumul']:.4f}  Sharpe={spy_oos['sharpe']:.3f}")
    out(f"    Corr(SPY): {corr_spy:.3f}")
    out()
    out(f"    Stock-only (OOS): cumul={stk_oos['cumul']:.4f}"
        f"  Sharpe={stk_oos['sharpe']:.3f}  MaxDD={stk_oos['max_dd']:.2%}")
    out(f"    Covered-call lift vs stock-only OOS: "
        f"Δcumul={cc_oos['cumul']-stk_oos['cumul']:+.4f}  "
        f"ΔSharpe={cc_oos['sharpe']-stk_oos['sharpe']:+.3f}")

    # [5] Call premium analysis
    out("[5] Call premium vs realised move…")
    oos = oos_df.copy()
    oos["prem_pct"] = oos["call_premium"] / oos["S_entry"]
    oos["move_pct"] = (oos["S_exit"] - oos["S_entry"]).abs() / oos["S_entry"]
    oos["call_itm"] = (oos["S_exit"] > oos["K"]).mean() if not oos.empty else 0
    itm_rate = (oos["S_exit"] > oos["K"]).mean()
    avg_prem_oos = oos["prem_pct"].mean()
    avg_move_oos = oos["move_pct"].mean()
    out(f"    OOS avg premium collected:  {avg_prem_oos:.3%} of stock")
    out(f"    OOS avg abs stock move:     {avg_move_oos:.3%}")
    out(f"    OOS call finished ITM rate: {itm_rate:.1%}  (call expired worthless: {1-itm_rate:.1%})")
    out(f"    OOS avg call ret:           {oos['call_ret'].mean():.3%}")
    out(f"    OOS avg stock ret:          {oos['stock_ret'].mean():.3%}")

    # [6] Sensitivity sweep
    sweep_params(df)

    # [7] JEPI comparison
    jepi_comparison(spy)

    # [8] Verdict
    out("\n[8] Verdict:")
    criteria = [
        ("OOS Sharpe>1.0", cc_oos["sharpe"] > 1.0, f"{cc_oos['sharpe']:.3f}"),
        ("OOS MaxDD>-25%", cc_oos["max_dd"] > -0.25, f"{cc_oos['max_dd']:.2%}"),
        ("OOS WinRate>55%", True, "see per-event stats"),  # updated below
    ]
    oos_wr = (oos_df["cc_ret"] > 0).mean() if not oos_df.empty else 0
    criteria[2] = ("OOS WinRate>55%", oos_wr > 0.55, f"{oos_wr:.1%}")

    met = sum(c[1] for c in criteria)
    for name, passed, val in criteria:
        mark = "✓" if passed else "✗"
        out(f"    {name}: {mark}  ({val})")
    out(f"    Criteria met: {met}/3")
    out()

    if met == 3:
        verdict = "CONFIRMED"
    elif met >= 2:
        verdict = "PARTIAL CONFIRMED"
    else:
        verdict = "NOT CONFIRMED"

    out(f"    VERDICT: {verdict}")

    # Save results
    result_path = RESULT_DIR / "h162_covered_calls_exdiv.txt"
    with open(result_path, "w") as f:
        f.write("\n".join(lines))
    out()
    out(f"    Results saved → {result_path}")


if __name__ == "__main__":
    main()
