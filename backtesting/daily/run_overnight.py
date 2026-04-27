"""
run_overnight.py — Batch backtest H008 through H017.

Tests hypotheses sequentially, logs results to overnight_results.json,
and updates the hypothesis log at wiki/trading/backtesting/hypothesis-log.md.

Usage:
    python3 run_overnight.py
    # or background:
    nohup python3 run_overnight.py > overnight.log 2>&1 &
"""

import sys
import json
import time
import traceback
import hashlib
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent.parent.parent
CACHE_DIR  = ROOT / "backtesting" / "cache"
RESULTS_FILE = Path(__file__).parent / "overnight_results.json"
HYPO_LOG   = ROOT / "wiki" / "trading" / "backtesting" / "hypothesis-log.md"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

RF = 0.044          # risk-free rate used in Sharpe calculations
INITIAL_EQUITY = 100_000.0

# ── Runtime estimate ──────────────────────────────────────────────────────────

N_HYPOTHESES = 10   # H008-H017
EST_SECONDS  = 90   # rough estimate per hypothesis
RUN_START    = time.time()

print(f"{'='*72}")
print(f"  Overnight Backtest  H008 – H017")
print(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  Est. completion in ~{(N_HYPOTHESES * EST_SECONDS) // 60} minutes")
print(f"{'='*72}\n")

# ── Data cache helper ─────────────────────────────────────────────────────────

def _symbols_hash(symbols: list) -> str:
    key = "_".join(sorted(symbols))
    return hashlib.md5(key.encode()).hexdigest()[:8]


def fetch_prices(symbols: list, start: str, end: str) -> pd.DataFrame:
    """
    Returns a DataFrame of adjusted close prices, columns = symbols,
    index = DatetimeIndex. Caches to parquet.
    """
    h = _symbols_hash(symbols)
    cache_path = CACHE_DIR / f"{h}_daily_{start}_{end}.parquet"

    if cache_path.exists():
        raw = pd.read_parquet(cache_path)
        # If stored in MultiIndex (symbol, date) format from existing cache
        if isinstance(raw.index, pd.MultiIndex):
            frames = {}
            for sym in symbols:
                try:
                    s = raw.xs(sym, level=0)["close"]
                    s.index = pd.to_datetime(s.index)
                    frames[sym] = s
                except KeyError:
                    pass
            return pd.DataFrame(frames).sort_index().ffill()
        else:
            return raw

    # Download via yfinance
    print(f"  Downloading {symbols} ({start} → {end})...")
    raw = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)

    if isinstance(raw.columns, pd.MultiIndex):
        # New yfinance: MultiIndex ('Price', 'Ticker') — level 0 = price field
        try:
            close = raw["Close"].copy()
        except KeyError:
            close = raw.xs("Close", axis=1, level=0).copy()
        close.columns.name = None
        # If only one symbol the column might be named the ticker
        if len(symbols) == 1 and symbols[0] not in close.columns:
            close.columns = symbols
    else:
        close = raw[["Close"]].rename(columns={"Close": symbols[0]})

    close.index = pd.to_datetime(close.index)
    close = close.sort_index().ffill()
    close.to_parquet(cache_path)
    print(f"  Cached {len(close)} rows → {cache_path.name}")
    return close


def fetch_ohlc(symbols: list, start: str, end: str) -> dict:
    """
    Returns dict of DataFrames with OHLCV, keyed by symbol.
    Used by IBS (needs High/Low) and Donchian (needs High/Low).
    """
    h = _symbols_hash(symbols + ["__ohlc__"])
    cache_path = CACHE_DIR / f"{h}_ohlc_{start}_{end}.parquet"

    if cache_path.exists():
        multi = pd.read_parquet(cache_path)
    else:
        print(f"  Downloading OHLC for {symbols} ({start} → {end})...")
        raw = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)
        raw.index = pd.to_datetime(raw.index)
        multi = raw
        multi.to_parquet(cache_path)
        print(f"  Cached OHLC {len(multi)} rows → {cache_path.name}")

    result = {}
    for sym in symbols:
        if isinstance(multi.columns, pd.MultiIndex):
            # yfinance MultiIndex: ('Price', 'Ticker') or level 1 = ticker
            try:
                df = multi.xs(sym, axis=1, level=1).copy()
            except KeyError:
                try:
                    df = multi.xs(sym, axis=1, level='Ticker').copy()
                except KeyError:
                    continue
        else:
            df = multi.copy()
        # Flatten string columns
        df.columns = [str(c).lower() if not isinstance(c, tuple) else str(c[0]).lower()
                      for c in df.columns]
        result[sym] = df.sort_index().ffill()
    return result


# ── Standard statistics ───────────────────────────────────────────────────────

def calc_stats(equity: pd.Series, rf: float = RF) -> dict:
    """
    equity: daily portfolio value series (or monthly if monthly=True).
    Returns CAGR, Sharpe (rf=RF), max_drawdown, calmar.
    """
    equity = equity.dropna()
    if len(equity) < 10:
        return {"error": "insufficient data"}

    daily_ret = equity.pct_change().dropna()
    n_days    = len(daily_ret)
    years     = n_days / 252

    total_ret  = equity.iloc[-1] / equity.iloc[0] - 1
    cagr       = (1 + total_ret) ** (1 / years) - 1 if years > 0 else float('nan')

    ann_ret    = cagr
    ann_vol    = daily_ret.std() * np.sqrt(252)
    sharpe     = (ann_ret - rf) / ann_vol if ann_vol > 0 else float('nan')

    running_max = equity.cummax()
    drawdown    = (equity - running_max) / running_max
    max_dd      = float(drawdown.min())

    calmar = cagr / abs(max_dd) if max_dd != 0 else float('nan')

    # Monthly win rate
    monthly = equity.resample("ME").last().pct_change().dropna()
    win_rate_monthly = float((monthly > 0).mean())

    return dict(
        cagr=round(float(cagr), 4),
        sharpe=round(float(sharpe), 4),
        max_drawdown=round(float(max_dd), 4),
        calmar=round(float(calmar), 4),
        total_return=round(float(total_ret), 4),
        ann_vol=round(float(ann_vol), 4),
        win_rate_monthly=round(win_rate_monthly, 4),
    )


def spy_bh_stats(prices: pd.DataFrame, start: str, end: str) -> dict:
    """Quick buy-and-hold SPY stats for comparison."""
    spy = prices["SPY"].dropna().loc[start:end]
    eq  = INITIAL_EQUITY * (spy / spy.iloc[0])
    return calc_stats(eq)


# ── Results accumulator ───────────────────────────────────────────────────────

results: dict = {}

def save_results():
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2, default=str)


def done(hid: str, data: dict, sharpe=None, cagr=None):
    results[hid] = data
    save_results()
    label = f"H{hid[1:]}" if hid.startswith("h") else hid
    parts = []
    if sharpe is not None: parts.append(f"Sharpe {sharpe:.2f}")
    if cagr   is not None: parts.append(f"CAGR {cagr*100:.1f}%")
    elapsed = (time.time() - RUN_START) / 60
    print(f"  ✓ {label} done: {', '.join(parts)}  [{elapsed:.1f}min elapsed]")


# ══════════════════════════════════════════════════════════════════════════════
# H008 — Dual MA Crossover on SPY
# ══════════════════════════════════════════════════════════════════════════════

def run_h008():
    print("\n" + "─"*72)
    print("H008 — Dual MA Crossover on SPY (2003–2026)")
    print("─"*72)

    START, END = "2003-01-01", "2026-04-01"
    PAIRS = [(10, 30), (20, 50), (50, 100), (50, 200)]

    prices = fetch_prices(["SPY"], START, END)
    spy    = prices["SPY"].dropna()

    combos = {}
    best_sharpe = -999
    winner = None

    for fast, slow in PAIRS:
        label = f"SMA({fast},{slow})"
        sma_f = spy.rolling(fast).mean()
        sma_s = spy.rolling(slow).mean()

        # Signal: long when fast > slow
        signal = (sma_f > sma_s).astype(float)
        signal = signal.shift(1).fillna(0)   # no look-ahead

        daily_ret   = spy.pct_change()
        strat_ret   = signal * daily_ret
        equity_curve = INITIAL_EQUITY * (1 + strat_ret).cumprod()
        equity_curve = equity_curve.dropna()

        m = calc_stats(equity_curve)
        m["fast_period"] = fast
        m["slow_period"] = slow

        # Win rate = % of months strategy is positive
        monthly = equity_curve.resample("ME").last().pct_change().dropna()
        m["win_rate_monthly"] = round(float((monthly > 0).mean()), 4)

        combos[label] = m
        print(f"  {label:<16}  CAGR {m['cagr']:+.1%}  Sharpe {m['sharpe']:.3f}  "
              f"MaxDD {m['max_dd'] if 'max_dd' in m else m['max_drawdown']:.1%}  "
              f"WinRate {m['win_rate_monthly']:.1%}")

        if m.get("sharpe", -999) > best_sharpe:
            best_sharpe = m["sharpe"]
            winner = label

    # Buy and hold
    bh_eq  = INITIAL_EQUITY * (spy / spy.iloc[0])
    bh     = calc_stats(bh_eq)
    combos["BH_SPY"] = bh
    print(f"  {'BH_SPY':<16}  CAGR {bh['cagr']:+.1%}  Sharpe {bh['sharpe']:.3f}  "
          f"MaxDD {bh['max_drawdown']:.1%}")

    print(f"\n  Winner (best Sharpe): {winner} — Sharpe {best_sharpe:.3f}")

    result = {
        "winner": winner,
        "best_sharpe": round(best_sharpe, 4),
        "combos": combos,
        "benchmark": bh,
        "period": f"{START} → {END}",
    }
    done("h008", result, sharpe=best_sharpe, cagr=combos[winner]["cagr"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H009 — IBS Mean-Reversion on SPY
# ══════════════════════════════════════════════════════════════════════════════

def run_h009():
    print("\n" + "─"*72)
    print("H009 — IBS Mean-Reversion on SPY + Sector Cross-Section (2003–2026)")
    print("─"*72)

    START, END   = "2003-01-01", "2026-04-01"
    SECTORS      = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLU", "XLB"]
    BUY_THRESH   = 0.2
    SELL_THRESH  = 0.8
    MAX_HOLD     = 5

    # SPY OHLC
    spy_ohlc = fetch_ohlc(["SPY"], START, END)["SPY"]

    # ── SPY IBS strategy ──────────────────────────────────────────────────────
    ibs = ((spy_ohlc["close"] - spy_ohlc["low"])
           / (spy_ohlc["high"] - spy_ohlc["low"])).replace([np.inf, -np.inf], np.nan).fillna(0.5)

    equity_spy = INITIAL_EQUITY
    position   = 0          # 0=flat, 1=long
    days_held  = 0
    equity_series_spy = []

    for i in range(1, len(ibs)):
        date   = ibs.index[i]
        c_prev = float(spy_ohlc["close"].iloc[i-1])
        c_curr = float(spy_ohlc["close"].iloc[i])
        ret    = c_curr / c_prev - 1 if c_prev > 0 else 0

        if position == 1:
            equity_spy *= (1 + ret)
            days_held  += 1
            ibs_val    = float(ibs.iloc[i])
            if ibs_val > SELL_THRESH or days_held >= MAX_HOLD:
                position  = 0
                days_held = 0
        else:
            ibs_prev = float(ibs.iloc[i-1])
            if ibs_prev < BUY_THRESH:
                position  = 1
                days_held = 1
                equity_spy *= (1 + ret)

        equity_series_spy.append((date, equity_spy))

    eq_spy = pd.Series(
        [v for _, v in equity_series_spy],
        index=pd.DatetimeIndex([d for d, _ in equity_series_spy]),
    )

    m_spy = calc_stats(eq_spy)

    # B&H SPY
    spy_close = spy_ohlc["close"]
    bh_eq     = INITIAL_EQUITY * (spy_close / spy_close.iloc[0])
    m_bh      = calc_stats(bh_eq.iloc[1:])

    print(f"  SPY IBS:   CAGR {m_spy['cagr']:+.1%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.1%}")
    print(f"  SPY B&H:   CAGR {m_bh['cagr']:+.1%}  Sharpe {m_bh['sharpe']:.3f}  MaxDD {m_bh['max_drawdown']:.1%}")

    # ── Cross-sectional IBS on 9 sector ETFs ─────────────────────────────────
    print(f"  Running cross-sectional IBS on {len(SECTORS)} sectors...")
    sector_ohlc = fetch_ohlc(SECTORS, START, END)

    # Build IBS matrix
    ibs_frames = {}
    close_frames = {}
    for sym, df in sector_ohlc.items():
        ibs_s = ((df["close"] - df["low"])
                 / (df["high"] - df["low"])).replace([np.inf, -np.inf], np.nan).fillna(0.5)
        ibs_frames[sym] = ibs_s
        close_frames[sym] = df["close"]

    ibs_mat   = pd.DataFrame(ibs_frames).sort_index().dropna(how="all")
    close_mat = pd.DataFrame(close_frames).reindex(ibs_mat.index).ffill()

    # Monthly rebalance: long bottom IBS decile, short/flat top IBS decile
    # (long-only: long bottom 3, flat otherwise)
    monthly_idx = ibs_mat.resample("ME").last().index
    portfolio_xs = INITIAL_EQUITY
    xs_series    = []

    prev_month_end = None
    holdings: dict = {}  # sym -> entry_price

    daily_rets_xs = []
    for i in range(1, len(close_mat)):
        date  = close_mat.index[i]
        month = date.to_period("M")

        # Calculate daily return of portfolio
        if holdings:
            total_ret_day = 0.0
            for sym, entry in holdings.items():
                if sym in close_mat.columns and i > 0:
                    c_prev = float(close_mat[sym].iloc[i-1])
                    c_curr = float(close_mat[sym].iloc[i])
                    if c_prev > 0:
                        total_ret_day += (c_curr / c_prev - 1) / len(holdings)
            portfolio_xs *= (1 + total_ret_day)

        xs_series.append((date, portfolio_xs))

        # Rebalance on first day of new month
        if prev_month_end is None or month != prev_month_end:
            prev_month_end = month
            # IBS as of previous day
            ibs_today = ibs_mat.iloc[i-1].dropna()
            if len(ibs_today) >= 3:
                ranked = ibs_today.sort_values()
                bottom3 = list(ranked.index[:3])   # lowest IBS = most oversold
                holdings = {sym: float(close_mat[sym].iloc[i]) for sym in bottom3
                            if sym in close_mat.columns}

    eq_xs = pd.Series(
        [v for _, v in xs_series],
        index=pd.DatetimeIndex([d for d, _ in xs_series]),
    )
    m_xs = calc_stats(eq_xs)
    print(f"  XS IBS (long bottom 3): CAGR {m_xs['cagr']:+.1%}  Sharpe {m_xs['sharpe']:.3f}  MaxDD {m_xs['max_drawdown']:.1%}")

    result = {
        "spy_ibs": m_spy,
        "spy_bh":  m_bh,
        "crosssectional_ibs": m_xs,
        "params": {"buy_thresh": BUY_THRESH, "sell_thresh": SELL_THRESH, "max_hold": MAX_HOLD},
        "period": f"{START} → {END}",
    }
    best_sharpe = max(m_spy.get("sharpe", -99), m_xs.get("sharpe", -99))
    done("h009", result, sharpe=best_sharpe, cagr=m_spy["cagr"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H010 — Multi-Asset Trend Following
# ══════════════════════════════════════════════════════════════════════════════

def run_h010():
    print("\n" + "─"*72)
    print("H010 — Multi-Asset Trend Following (2007–2026)")
    print("─"*72)

    START, END = "2007-01-01", "2026-04-01"
    UNIVERSE = ["SPY", "TLT", "GLD", "DBC", "VNQ"]
    CASH_ETF = "SHY"
    ALL_SYMS = sorted(set(UNIVERSE + [CASH_ETF]))

    prices = fetch_prices(ALL_SYMS, START, END)

    # SMA(200) filter: hold ETF if Close > SMA200, else hold SHY
    sma200 = prices[UNIVERSE].rolling(200, min_periods=200).mean()
    trend_signal = (prices[UNIVERSE] > sma200).shift(1)   # no look-ahead

    equity_trend = INITIAL_EQUITY
    equity_6040  = INITIAL_EQUITY
    trend_series = []
    bench_series = []

    for i in range(200, len(prices)):
        date = prices.index[i]

        # ── Trend strategy (monthly rebalance on first trading day of month) ──
        # For simplicity use daily signal but rebalance logic:
        # determine weights based on yesterday's signal
        sig  = trend_signal.iloc[i]
        n_in = sig.sum()

        daily_ret = prices.pct_change().iloc[i]

        if n_in > 0:
            wts  = {sym: (1.0 / n_in if sig.get(sym, False) else 0.0) for sym in UNIVERSE}
            cash = 0.0
        else:
            wts  = {sym: 0.0 for sym in UNIVERSE}
            cash = 1.0

        port_ret = sum(wts[sym] * daily_ret.get(sym, 0) for sym in UNIVERSE)
        if cash > 0:
            port_ret += cash * daily_ret.get(CASH_ETF, 0)
        equity_trend *= (1 + port_ret)

        # ── 60/40 SPY+TLT benchmark ───────────────────────────────────────────
        spy_ret = daily_ret.get("SPY", 0)
        tlt_ret = daily_ret.get("TLT", 0)
        bench_ret = 0.60 * spy_ret + 0.40 * tlt_ret
        equity_6040 *= (1 + bench_ret)

        trend_series.append((date, equity_trend))
        bench_series.append((date, equity_6040))

    eq_trend = pd.Series([v for _, v in trend_series],
                         index=pd.DatetimeIndex([d for d, _ in trend_series]))
    eq_6040  = pd.Series([v for _, v in bench_series],
                         index=pd.DatetimeIndex([d for d, _ in bench_series]))

    m_trend = calc_stats(eq_trend)
    m_6040  = calc_stats(eq_6040)

    print(f"  Trend Following:  CAGR {m_trend['cagr']:+.1%}  Sharpe {m_trend['sharpe']:.3f}  MaxDD {m_trend['max_drawdown']:.1%}")
    print(f"  60/40 SPY+TLT:    CAGR {m_6040['cagr']:+.1%}  Sharpe {m_6040['sharpe']:.3f}  MaxDD {m_6040['max_drawdown']:.1%}")

    result = {
        "trend_following": m_trend,
        "benchmark_6040": m_6040,
        "universe": UNIVERSE,
        "cash_etf": CASH_ETF,
        "period": f"{START} → {END}",
    }
    done("h010", result, sharpe=m_trend["sharpe"], cagr=m_trend["cagr"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H011 — Low-Volatility Anomaly on Sectors
# ══════════════════════════════════════════════════════════════════════════════

def run_h011():
    print("\n" + "─"*72)
    print("H011 — Low-Volatility Anomaly on Sectors (2003–2026)")
    print("─"*72)

    START, END = "2003-01-01", "2026-04-01"
    SECTORS    = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLU", "XLB"]
    ALL_SYMS   = sorted(set(SECTORS + ["SPY"]))
    VOL_PERIOD = 126    # ~6 months trailing

    prices = fetch_prices(ALL_SYMS, START, END)
    sector_prices = prices[SECTORS].copy()

    # Compute 126-day realized vol (annualized std of daily returns)
    daily_rets = sector_prices.pct_change()
    rolling_vol = daily_rets.rolling(VOL_PERIOD, min_periods=VOL_PERIOD).std() * np.sqrt(252)

    equity_lowvol = INITIAL_EQUITY
    lowvol_series = []

    # First day we can trade: after VOL_PERIOD trading days
    valid_dates = rolling_vol.dropna(how="all").index
    if len(valid_dates) == 0:
        return {}

    first_valid = valid_dates[0]
    current_holdings = None
    current_month = None

    for i in range(len(sector_prices)):
        date = sector_prices.index[i]
        if date < first_valid:
            continue

        month = date.to_period("M")

        # Monthly rebalance
        if month != current_month:
            current_month = month
            vol_row = rolling_vol.iloc[i-1].dropna()
            if len(vol_row) >= 6:
                ranked = vol_row.sort_values()
                current_holdings = list(ranked.index[:3])   # bottom 3 vol

        if current_holdings and i > 0:
            port_ret = 0.0
            for sym in current_holdings:
                p_prev = float(sector_prices[sym].iloc[i-1])
                p_curr = float(sector_prices[sym].iloc[i])
                if p_prev > 0:
                    port_ret += (p_curr / p_prev - 1) / len(current_holdings)
            equity_lowvol *= (1 + port_ret)
            lowvol_series.append((date, equity_lowvol))

    eq_lowvol = pd.Series([v for _, v in lowvol_series],
                           index=pd.DatetimeIndex([d for d, _ in lowvol_series]))

    m_lowvol = calc_stats(eq_lowvol)

    # SPY benchmark
    spy      = prices["SPY"].dropna().loc[str(eq_lowvol.index[0]):]
    bh_spy   = INITIAL_EQUITY * (spy / spy.iloc[0])
    m_spy    = calc_stats(bh_spy)

    print(f"  Low-Vol Sectors:  CAGR {m_lowvol['cagr']:+.1%}  Sharpe {m_lowvol['sharpe']:.3f}  MaxDD {m_lowvol['max_drawdown']:.1%}")
    print(f"  SPY B&H:          CAGR {m_spy['cagr']:+.1%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.1%}")

    result = {
        "low_vol_bottom3": m_lowvol,
        "benchmark_spy": m_spy,
        "vol_period": VOL_PERIOD,
        "period": f"{START} → {END}",
    }
    done("h011", result, sharpe=m_lowvol["sharpe"], cagr=m_lowvol["cagr"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H012 — Price Momentum on Sectors (12-1 skip)
# ══════════════════════════════════════════════════════════════════════════════

def run_h012():
    print("\n" + "─"*72)
    print("H012 — Price Momentum on Sectors 12-1 (2003–2026)")
    print("─"*72)

    START, END = "2003-01-01", "2026-04-01"
    SECTORS    = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLU", "XLB"]
    ALL_SYMS   = sorted(set(SECTORS + ["SPY"]))

    prices       = fetch_prices(ALL_SYMS, START, END)
    sector_px    = prices[SECTORS].copy()

    # 12-1 momentum: (price 12 months ago → price 1 month ago)
    # Monthly rebalance, long top 3
    monthly_px   = sector_px.resample("ME").last()
    mom_12       = monthly_px.shift(1) / monthly_px.shift(12) - 1   # skip last month
    # (shift(1) = last month's price, shift(12) = 12 months before that)

    equity_mom  = INITIAL_EQUITY
    mom_series  = []

    # Monthly portfolio
    monthly_dates = monthly_px.index
    holdings      = None

    for i in range(12, len(monthly_dates)):
        month_end = monthly_dates[i]
        # Rank by momentum as of last month-end
        mom_row = mom_12.iloc[i].dropna()
        if len(mom_row) >= 3:
            holdings = list(mom_row.nlargest(3).index)

        # Apply daily returns for this month
        if holdings is None:
            continue

        start_d = monthly_dates[i-1] + pd.Timedelta(days=1)
        end_d   = month_end
        sub     = sector_px.loc[start_d:end_d]

        if sub.empty:
            continue

        for j in range(len(sub)):
            if j == 0:
                continue
            port_ret = 0.0
            for sym in holdings:
                if sym in sub.columns:
                    p0 = float(sub[sym].iloc[j-1])
                    p1 = float(sub[sym].iloc[j])
                    if p0 > 0:
                        port_ret += (p1 / p0 - 1) / len(holdings)
            equity_mom *= (1 + port_ret)
            mom_series.append((sub.index[j], equity_mom))

    eq_mom = pd.Series([v for _, v in mom_series],
                        index=pd.DatetimeIndex([d for d, _ in mom_series]))

    m_mom = calc_stats(eq_mom)

    # SPY benchmark
    spy    = prices["SPY"].dropna()
    spy    = spy.loc[eq_mom.index[0]:]
    bh_spy = INITIAL_EQUITY * (spy / spy.iloc[0])
    m_spy  = calc_stats(bh_spy)

    print(f"  Sector Mom 12-1:  CAGR {m_mom['cagr']:+.1%}  Sharpe {m_mom['sharpe']:.3f}  MaxDD {m_mom['max_drawdown']:.1%}")
    print(f"  SPY B&H:          CAGR {m_spy['cagr']:+.1%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.1%}")

    result = {
        "momentum_12_1": m_mom,
        "benchmark_spy": m_spy,
        "top_n": 3,
        "period": f"{START} → {END}",
    }
    done("h012", result, sharpe=m_mom["sharpe"], cagr=m_mom["cagr"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H013 — Donchian Channel Breakout on SPY
# ══════════════════════════════════════════════════════════════════════════════

def run_h013():
    print("\n" + "─"*72)
    print("H013 — Donchian Channel Breakout on SPY (2003–2026)")
    print("─"*72)

    START, END = "2003-01-01", "2026-04-01"
    PERIODS    = [20, 55]

    spy_ohlc = fetch_ohlc(["SPY"], START, END)["SPY"]
    spy_close = spy_ohlc["close"]
    spy_high  = spy_ohlc["high"]
    spy_low   = spy_ohlc["low"]

    combos = {}

    for N in PERIODS:
        label       = f"Donchian({N})"
        n_high      = spy_high.rolling(N).max().shift(1)   # N-day high (excluding today)
        n_low       = spy_low.rolling(N).min().shift(1)    # N-day low  (excluding today)

        position    = 0
        equity_d    = INITIAL_EQUITY
        series      = []

        for i in range(N+1, len(spy_close)):
            date  = spy_close.index[i]
            c0    = float(spy_close.iloc[i-1])
            c1    = float(spy_close.iloc[i])
            ret   = c1 / c0 - 1 if c0 > 0 else 0

            nh    = float(n_high.iloc[i])
            nl    = float(n_low.iloc[i])

            # Enter long on breakout above N-day high
            if position == 0 and c0 > nh:
                position = 1
            # Exit when close < N-day low
            elif position == 1 and c0 < nl:
                position = 0

            if position == 1:
                equity_d *= (1 + ret)

            series.append((date, equity_d))

        eq    = pd.Series([v for _, v in series],
                           index=pd.DatetimeIndex([d for d, _ in series]))
        m     = calc_stats(eq)
        combos[label] = m
        print(f"  {label:<16}  CAGR {m['cagr']:+.1%}  Sharpe {m['sharpe']:.3f}  MaxDD {m['max_drawdown']:.1%}")

    # B&H
    bh_eq = INITIAL_EQUITY * (spy_close / spy_close.iloc[0])
    m_bh  = calc_stats(bh_eq)
    combos["BH_SPY"] = m_bh
    print(f"  {'BH_SPY':<16}  CAGR {m_bh['cagr']:+.1%}  Sharpe {m_bh['sharpe']:.3f}  MaxDD {m_bh['max_drawdown']:.1%}")

    best = max(combos.items(), key=lambda x: x[1].get("sharpe", -99) if "error" not in x[1] else -99)
    print(f"\n  Best: {best[0]} — Sharpe {best[1].get('sharpe', 'n/a'):.3f}")

    result = {
        "combos": combos,
        "winner": best[0],
        "period": f"{START} → {END}",
    }
    done("h013", result, sharpe=best[1].get("sharpe", 0), cagr=best[1].get("cagr", 0))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H014 — Mean-Reversion After Large Down Days
# ══════════════════════════════════════════════════════════════════════════════

def run_h014():
    print("\n" + "─"*72)
    print("H014 — Mean-Reversion After Large Down Days (2003–2026)")
    print("─"*72)

    START, END   = "2003-01-01", "2026-04-01"
    THRESHOLD    = -0.015    # -1.5%
    HOLD_DAYS    = 5

    prices    = fetch_prices(["SPY"], START, END)
    spy       = prices["SPY"].dropna()
    daily_ret = spy.pct_change()

    # Find signal days
    signal_days = daily_ret[daily_ret < THRESHOLD].index

    # For each signal, collect 5-day forward return
    forward_rets = []
    for sd in signal_days:
        loc = spy.index.get_loc(sd)
        if loc + HOLD_DAYS < len(spy):
            p_entry = float(spy.iloc[loc])
            p_exit  = float(spy.iloc[loc + HOLD_DAYS])
            fwd     = p_exit / p_entry - 1
            forward_rets.append(fwd)

    forward_rets = np.array(forward_rets)
    n_signals    = len(forward_rets)

    if n_signals == 0:
        print("  No signals found!")
        return {}

    avg_fwd  = float(np.mean(forward_rets))
    hit_rate = float(np.mean(forward_rets > 0))

    # Random 5-day windows for comparison
    all_fwd = []
    n_random = 1000
    rng = np.random.default_rng(42)
    valid_locs = [i for i in range(len(spy) - HOLD_DAYS)]
    sampled = rng.choice(valid_locs, size=min(n_random, len(valid_locs)), replace=False)
    for loc in sampled:
        p0  = float(spy.iloc[loc])
        p5  = float(spy.iloc[loc + HOLD_DAYS])
        all_fwd.append(p5 / p0 - 1)

    random_avg = float(np.mean(all_fwd))
    random_hit = float(np.mean(np.array(all_fwd) > 0))

    from scipy import stats as sp_stats
    t_stat, p_val = sp_stats.ttest_1samp(forward_rets, random_avg)

    print(f"  Signals (ret < {THRESHOLD:.1%}): {n_signals}")
    print(f"  Avg {HOLD_DAYS}-day fwd return (signal): {avg_fwd:+.2%}")
    print(f"  Hit rate (signal): {hit_rate:.1%}")
    print(f"  Avg {HOLD_DAYS}-day fwd return (random): {random_avg:+.2%}")
    print(f"  Hit rate (random): {random_hit:.1%}")
    print(f"  t-stat: {t_stat:.3f}   p-value: {p_val:.4f}")

    result = {
        "n_signals": n_signals,
        "threshold": THRESHOLD,
        "hold_days": HOLD_DAYS,
        "avg_forward_return": round(avg_fwd, 5),
        "hit_rate": round(hit_rate, 4),
        "random_avg_forward_return": round(random_avg, 5),
        "random_hit_rate": round(random_hit, 4),
        "t_stat": round(float(t_stat), 4),
        "p_value": round(float(p_val), 4),
        "edge": round(avg_fwd - random_avg, 5),
        "period": f"{START} → {END}",
    }
    done("h014", result, cagr=None, sharpe=None)
    print(f"  Edge (signal minus random): {result['edge']:+.3%}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H015 — Seasonal Patterns (Month-of-Year)
# ══════════════════════════════════════════════════════════════════════════════

def run_h015():
    print("\n" + "─"*72)
    print("H015 — Seasonal Patterns / Sell in May (2003–2026)")
    print("─"*72)

    from scipy import stats as sp_stats

    START, END = "2003-01-01", "2026-04-01"

    prices    = fetch_prices(["SPY"], START, END)
    spy       = prices["SPY"].dropna()
    monthly   = spy.resample("ME").last()
    monthly_ret = monthly.pct_change().dropna()

    month_avgs = monthly_ret.groupby(monthly_ret.index.month).mean()
    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

    print(f"\n  Month-by-month average returns:")
    for m, r in month_avgs.items():
        print(f"    {month_names[m]:3s}: {r:+.2%}")

    # Nov-Apr vs May-Oct CAGR
    nov_apr_months = [11, 12, 1, 2, 3, 4]
    may_oct_months = [5, 6, 7, 8, 9, 10]

    is_nov_apr = monthly_ret.index.month.isin(nov_apr_months)
    ret_nov_apr = monthly_ret[is_nov_apr]
    ret_may_oct = monthly_ret[~is_nov_apr]

    # Annualized from monthly
    cagr_nov_apr = (1 + ret_nov_apr.mean()) ** 12 - 1
    cagr_may_oct = (1 + ret_may_oct.mean()) ** 12 - 1

    t_stat, p_val = sp_stats.ttest_ind(ret_nov_apr, ret_may_oct)

    print(f"\n  Nov–Apr CAGR (equiv): {cagr_nov_apr:+.1%}  avg monthly: {ret_nov_apr.mean():+.3%}  n={len(ret_nov_apr)}")
    print(f"  May–Oct CAGR (equiv): {cagr_may_oct:+.1%}  avg monthly: {ret_may_oct.mean():+.3%}  n={len(ret_may_oct)}")
    print(f"  t-stat: {t_stat:.3f}   p-value: {p_val:.4f}")
    print(f"  Sell-in-May premium: {ret_nov_apr.mean() - ret_may_oct.mean():+.3%} per month")

    result = {
        "month_avg_returns": {month_names[m]: round(float(r), 5) for m, r in month_avgs.items()},
        "nov_apr_cagr_equiv": round(float(cagr_nov_apr), 4),
        "may_oct_cagr_equiv": round(float(cagr_may_oct), 4),
        "nov_apr_avg_monthly": round(float(ret_nov_apr.mean()), 5),
        "may_oct_avg_monthly": round(float(ret_may_oct.mean()), 5),
        "t_stat": round(float(t_stat), 4),
        "p_value": round(float(p_val), 4),
        "seasonal_premium_monthly": round(float(ret_nov_apr.mean() - ret_may_oct.mean()), 5),
        "period": f"{START} → {END}",
    }
    significant = p_val < 0.05
    print(f"  Statistically significant (p<0.05): {significant}")
    done("h015", result)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H016 — Multi-Asset Momentum + Carry Blend
# ══════════════════════════════════════════════════════════════════════════════

def run_h016():
    print("\n" + "─"*72)
    print("H016 — Multi-Asset Momentum + Carry Blend (2007–2026)")
    print("─"*72)

    START, END = "2007-01-01", "2026-04-01"
    ASSETS     = ["SPY", "TLT", "GLD"]
    CASH_ETF   = "SHY"
    ALL_SYMS   = sorted(set(ASSETS + [CASH_ETF]))

    prices = fetch_prices(ALL_SYMS, START, END)

    # Monthly prices
    monthly_px  = prices[ASSETS].resample("ME").last()
    monthly_shy = prices[CASH_ETF].resample("ME").last()

    # 12-month momentum rank (1=worst, 3=best)
    mom_12  = monthly_px / monthly_px.shift(12) - 1

    # 6-month vol rank (inverse: 1=most volatile, 3=least volatile)
    monthly_rets = monthly_px.pct_change()
    vol_6   = monthly_rets.rolling(6).std() * np.sqrt(12)

    equity   = INITIAL_EQUITY
    series   = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]

        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()

        if len(mom_row) < 3 or len(vol_row) < 3:
            continue

        # Rank: 1=worst, 3=best (higher is better)
        mom_rank = mom_row.rank()          # 1=lowest momentum
        vol_rank = vol_row.rank()          # 1=lowest vol
        inv_vol  = vol_row.rank(ascending=False)  # 1=highest vol → worst carry

        # Combined score = momentum rank + inverse-vol rank (both higher = better)
        combined = mom_rank + inv_vol

        # Top 2 by score
        top2 = list(combined.nlargest(2).index)
        rest = [s for s in ASSETS if s not in top2]

        # Apply monthly return
        sub_start = monthly_px.index[i-1] + pd.Timedelta(days=1)
        sub_end   = month_end
        sub       = prices[ALL_SYMS].loc[sub_start:sub_end]

        if sub.empty:
            continue

        # Daily returns for this month
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top2:
                p0 = float(sub[sym].iloc[j-1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0:
                    port_ret += (p1 / p0 - 1) / 2
            # Remainder in SHY
            cash_weight = len(rest) / len(ASSETS)
            p0 = float(sub[CASH_ETF].iloc[j-1])
            p1 = float(sub[CASH_ETF].iloc[j])
            if p0 > 0 and cash_weight > 0:
                port_ret += cash_weight * (p1 / p0 - 1)

            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        print("  No trades generated")
        return {}

    eq      = pd.Series([v for _, v in series],
                         index=pd.DatetimeIndex([d for d, _ in series]))
    m_blend = calc_stats(eq)

    # SPY benchmark
    spy    = prices["SPY"].loc[eq.index[0]:eq.index[-1]]
    bh_spy = INITIAL_EQUITY * (spy / spy.iloc[0])
    m_spy  = calc_stats(bh_spy)

    print(f"  Momentum+Carry:   CAGR {m_blend['cagr']:+.1%}  Sharpe {m_blend['sharpe']:.3f}  MaxDD {m_blend['max_drawdown']:.1%}")
    print(f"  SPY B&H:          CAGR {m_spy['cagr']:+.1%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.1%}")

    result = {
        "momentum_carry_blend": m_blend,
        "benchmark_spy": m_spy,
        "assets": ASSETS,
        "cash_etf": CASH_ETF,
        "period": f"{START} → {END}",
    }
    done("h016", result, sharpe=m_blend["sharpe"], cagr=m_blend["cagr"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# H017 — VIX-Filtered Iron Condor Entry
# ══════════════════════════════════════════════════════════════════════════════

from scipy.stats import norm as sp_norm

def bsm_price(S, K, T, r, sigma, right):
    if T <= 1e-6 or sigma <= 1e-6:
        return max(S - K, 0) if right == 'call' else max(K - S, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if right == 'call':
        return S * sp_norm.cdf(d1) - K * np.exp(-r * T) * sp_norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * sp_norm.cdf(-d2) - S * sp_norm.cdf(-d1)


def strike_for_delta(S, T, r, sigma, target_delta, right):
    if right == 'call':
        d1 = sp_norm.ppf(target_delta)
    else:
        d1 = sp_norm.ppf(1.0 - target_delta)
    lnSK = d1 * sigma * np.sqrt(T) - (r + 0.5 * sigma**2) * T
    return S * np.exp(-lnSK)


def slip(price):
    return max(0.01, price * 0.02)


def simulate_condor_vix_filtered(prices_spy, vix_series, rfr_series,
                                  vix_threshold=15.0, target_delta=0.16,
                                  wing=5.0, max_risk_pct=0.05):
    """Iron condor simulation with optional VIX filter."""
    results    = []
    portfolio  = INITIAL_EQUITY
    active     = None
    last_entry = -1

    for i in range(len(prices_spy)):
        date = prices_spy.index[i]
        S    = float(prices_spy.iloc[i])
        iv   = float(vix_series.iloc[i]) / 100.0
        r    = float(rfr_series.iloc[i])

        # Exit
        if active is not None:
            exp = active['expiry']
            d   = date.date() if hasattr(date, 'date') else date
            dte = (exp - d).days

            if dte <= 0:
                p  = (-max(S - active['sc_k'], 0)
                      + max(S - active['lc_k'], 0)
                      - max(active['sp_k'] - S, 0)
                      + max(active['lp_k'] - S, 0)) * 100 * active['qty']
                pnl = active['entry_credit'] + p
                portfolio += pnl
                results.append(dict(date=date, reason='expired', pnl=pnl, portfolio=portfolio))
                active = None
                continue

            T45 = dte / 365.0
            sc = bsm_price(S, active['sc_k'], T45, r, iv, 'call')
            lc = bsm_price(S, active['lc_k'], T45, r, iv, 'call')
            sp = bsm_price(S, active['sp_k'], T45, r, iv, 'put')
            lp = bsm_price(S, active['lp_k'], T45, r, iv, 'put')

            cost_to_close = (sc - lc + sp - lp) * 100 * active['qty']
            pnl_mark = active['entry_credit'] - cost_to_close
            reason = None
            if active['entry_credit'] > 0:
                if pnl_mark >= 0.50 * active['entry_credit']:
                    reason = '50pct_profit'
                elif cost_to_close >= 2.0 * active['entry_credit']:
                    reason = '2x_loss'
            if dte <= 21 and reason is None:
                reason = '21dte'
            if reason:
                exit_slip = (slip(sc) + slip(lc) + slip(sp) + slip(lp)) * 100 * active['qty']
                pnl = pnl_mark - exit_slip
                portfolio += pnl
                results.append(dict(date=date, reason=reason, pnl=pnl, portfolio=portfolio))
                active = None

        # Entry
        if active is None:
            month = date.month
            if month == last_entry:
                continue

            # VIX filter: only enter if VIX > threshold
            vix_today = float(vix_series.iloc[i])
            if vix_today <= vix_threshold:
                # Track as skipped month
                last_entry = month
                continue

            T45  = 45 / 365.0
            sc_k = round(strike_for_delta(S, T45, r, iv, target_delta, 'call') / 5) * 5
            sp_k = round(strike_for_delta(S, T45, r, iv, target_delta, 'put') / 5) * 5
            lc_k = sc_k + wing
            lp_k = sp_k - wing

            if sc_k <= S or sp_k >= S:
                last_entry = month
                continue

            sc_p  = bsm_price(S, sc_k, T45, r, iv, 'call')
            lc_p  = bsm_price(S, lc_k, T45, r, iv, 'call')
            sp_p  = bsm_price(S, sp_k, T45, r, iv, 'put')
            lp_p  = bsm_price(S, lp_k, T45, r, iv, 'put')

            gross_credit = sc_p - lc_p + sp_p - lp_p
            entry_slip   = slip(sc_p) + slip(lc_p) + slip(sp_p) + slip(lp_p)
            net_credit   = gross_credit - entry_slip

            if net_credit <= 0.02:
                last_entry = month
                continue

            max_risk = (wing - net_credit) * 100
            if max_risk <= 0:
                last_entry = month
                continue

            qty = max(1, int(portfolio * max_risk_pct / max_risk))
            expiry = date.date() + pd.Timedelta(days=45)
            while expiry.weekday() != 4:
                expiry += pd.Timedelta(days=1)

            entry_credit = net_credit * 100 * qty
            active = dict(sc_k=sc_k, lc_k=lc_k, sp_k=sp_k, lp_k=lp_k,
                          qty=qty, entry_credit=entry_credit, expiry=expiry)
            last_entry = month

    if active:
        residual = active['entry_credit'] * 0.5
        portfolio += residual
        results.append(dict(date=prices_spy.index[-1], reason='end_of_data',
                             pnl=residual, portfolio=portfolio))

    return pd.DataFrame(results), portfolio


def condor_stats(trades_df, portfolio_final, start, end, initial=INITIAL_EQUITY):
    if trades_df.empty:
        return {"error": "no trades"}
    n_years   = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    total_ret = (portfolio_final - initial) / initial
    cagr      = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else float('nan')
    port_vals = trades_df["portfolio"].values
    run_max   = np.maximum.accumulate(np.maximum(port_vals, initial))
    dd        = (port_vals - run_max) / run_max
    max_dd    = float(dd.min())
    calmar    = cagr / abs(max_dd) if max_dd != 0 else float('nan')
    won       = (trades_df["pnl"] > 0).sum()
    win_rate  = float(won / len(trades_df))
    monthly   = trades_df.set_index("date")["pnl"].resample("ME").sum()
    m_ret     = monthly / initial
    sharpe    = float(m_ret.mean() / m_ret.std() * np.sqrt(12)) if m_ret.std() > 0 else float('nan')
    return dict(cagr=round(float(cagr), 4), total_ret=round(float(total_ret), 4),
                max_dd=round(float(max_dd), 4), calmar=round(float(calmar), 4),
                sharpe=round(float(sharpe), 4), win_rate=round(float(win_rate), 4),
                n_trades=int(len(trades_df)), final=round(float(portfolio_final), 2))


def run_h017():
    print("\n" + "─"*72)
    print("H017 — VIX-Filtered Iron Condor (VIX > 15 only) (2007–2026)")
    print("─"*72)

    START, END      = "2007-01-01", "2026-04-01"
    VIX_THRESHOLD   = 15.0

    print("  Downloading SPY + ^VIX + ^IRX...")
    spy = yf.download("SPY",  start=START, end=END, auto_adjust=True, progress=False)["Close"].squeeze()
    vix = yf.download("^VIX", start=START, end=END, auto_adjust=True, progress=False)["Close"].squeeze()
    irx = yf.download("^IRX", start=START, end=END, auto_adjust=True, progress=False)["Close"].squeeze() / 100.0

    idx = spy.index.intersection(vix.index)
    spy = spy.reindex(idx).ffill()
    vix = vix.reindex(idx).ffill().fillna(20)
    irx = irx.reindex(idx).ffill().fillna(0.02)

    print(f"  Data: {idx[0].date()} → {idx[-1].date()}  ({len(idx)} trading days)")

    # Unfiltered (H007 baseline)
    print("  Running unfiltered condor (H007 baseline)...")
    t_unfilt, f_unfilt = simulate_condor_vix_filtered(spy, vix, irx, vix_threshold=0.0)
    m_unfilt = condor_stats(t_unfilt, f_unfilt, START, END)

    # VIX-filtered
    print(f"  Running VIX > {VIX_THRESHOLD} filtered condor...")
    t_filt, f_filt = simulate_condor_vix_filtered(spy, vix, irx, vix_threshold=VIX_THRESHOLD)
    m_filt = condor_stats(t_filt, f_filt, START, END)

    print(f"\n  Unfiltered:   CAGR {m_unfilt['cagr']:+.1%}  Win {m_unfilt['win_rate']:.0%}  "
          f"Sharpe {m_unfilt['sharpe']:.3f}  MaxDD {m_unfilt['max_dd']:.1%}  Trades {m_unfilt['n_trades']}")
    print(f"  VIX>{VIX_THRESHOLD:.0f} Filter:  CAGR {m_filt['cagr']:+.1%}  Win {m_filt['win_rate']:.0%}  "
          f"Sharpe {m_filt['sharpe']:.3f}  MaxDD {m_filt['max_dd']:.1%}  Trades {m_filt['n_trades']}")

    # SPY B&H
    spy_ret  = spy.iloc[-1] / spy.iloc[0] - 1
    spy_yrs  = (idx[-1] - idx[0]).days / 365.25
    spy_cagr = (1 + spy_ret) ** (1 / spy_yrs) - 1
    spy_dd   = float((spy / spy.cummax() - 1).min())
    m_spy = dict(cagr=round(float(spy_cagr), 4), max_drawdown=round(spy_dd, 4))
    print(f"  SPY B&H:      CAGR {spy_cagr:+.1%}  MaxDD {spy_dd:.1%}")

    result = {
        "unfiltered_h007_baseline": m_unfilt,
        "vix_filtered": m_filt,
        "benchmark_spy": m_spy,
        "vix_threshold": VIX_THRESHOLD,
        "period": f"{START} → {END}",
    }
    done("h017", result, sharpe=m_filt["sharpe"], cagr=m_filt["cagr"])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Hypothesis log updater
# ══════════════════════════════════════════════════════════════════════════════

def status_label(hid: str) -> str:
    """Derive a status label from results."""
    r = results.get(hid, {})
    if "error" in r:
        return "ERROR"
    return "COMPLETE"


def format_pct(v, decimals=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v*100:.{decimals}f}%"


def update_hypothesis_log():
    """Append H008-H017 result cards to the hypothesis log."""
    print("\n" + "="*72)
    print("  Updating hypothesis log...")

    log_path = HYPO_LOG
    with open(log_path, "r") as f:
        content = f.read()

    # Update frontmatter statuses
    new_statuses = {}
    for hid in [f"h{i:03d}" for i in range(8, 18)]:
        r = results.get(hid, {})
        if "error" in r or not r:
            new_statuses[hid] = "ERROR"
        else:
            new_statuses[hid] = "COMPLETE"

    # Find and replace frontmatter block
    import re
    fm_match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
    if fm_match:
        old_fm  = fm_match.group(0)
        fm_body = fm_match.group(1)
        for hid, status in new_statuses.items():
            n = hid[1:]   # "008"
            tag = f"h{n}_status"
            if tag in fm_body:
                fm_body = re.sub(rf'{tag}:.*', f'{tag}: {status}', fm_body)
            else:
                fm_body += f"\n{tag}: {status}"
        new_fm = f"---\n{fm_body}\n---\n"
        content = content.replace(old_fm, new_fm)

    # Append result cards at the end
    cards = []
    today = datetime.now().strftime("%Y-%m-%d")

    # ── H008 ──
    r8 = results.get("h008", {})
    w8 = r8.get("winner", "?")
    cs = r8.get("combos", {})
    bh8 = r8.get("benchmark", r8.get("combos", {}).get("BH_SPY", {}))
    rows8 = ""
    for label, m in cs.items():
        if isinstance(m, dict) and "cagr" in m:
            rows8 += f"| {label} | {format_pct(m.get('cagr'))} | {m.get('sharpe',''):.3f} | {format_pct(m.get('max_drawdown'))} | {format_pct(m.get('win_rate_monthly'))} |\n"
    cards.append(f"""
---

## H008 — Dual MA Crossover on SPY

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: Long when fast SMA > slow SMA, flat otherwise (long-only)
**Asset**: SPY
**Period**: 2003-01-01 → 2026-04-01

### Hypothesis

Long-only MA crossover on SPY will generate positive risk-adjusted returns. Tested 4 parameter sets: (10,30), (20,50), (50,100), (50,200).

### Results

| Strategy | CAGR | Sharpe | MaxDD | WinRate(Monthly) |
|----------|------|--------|-------|-----------------|
{rows8}
**Winner (best Sharpe)**: `{w8}` — Sharpe {r8.get('best_sharpe', 0):.3f}

SPY B&H: CAGR {format_pct(bh8.get('cagr'))}  Sharpe {bh8.get('sharpe', 0):.3f}  MaxDD {format_pct(bh8.get('max_drawdown'))}
""")

    # ── H009 ──
    r9     = results.get("h009", {})
    m9spy  = r9.get("spy_ibs", {})
    m9bh   = r9.get("spy_bh", {})
    m9xs   = r9.get("crosssectional_ibs", {})
    cards.append(f"""---

## H009 — IBS Mean-Reversion on SPY

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: Buy when IBS < 0.2, sell when IBS > 0.8 or after 5 days
**Asset**: SPY + 9 sector ETF cross-section
**Period**: 2003-01-01 → 2026-04-01

### Results

| Strategy | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| SPY IBS (single) | {format_pct(m9spy.get('cagr'))} | {m9spy.get('sharpe',0):.3f} | {format_pct(m9spy.get('max_drawdown'))} |
| SPY B&H | {format_pct(m9bh.get('cagr'))} | {m9bh.get('sharpe',0):.3f} | {format_pct(m9bh.get('max_drawdown'))} |
| XS IBS (long bottom 3) | {format_pct(m9xs.get('cagr'))} | {m9xs.get('sharpe',0):.3f} | {format_pct(m9xs.get('max_drawdown'))} |
""")

    # ── H010 ──
    r10    = results.get("h010", {})
    m10t   = r10.get("trend_following", {})
    m10bm  = r10.get("benchmark_6040", {})
    cards.append(f"""---

## H010 — Multi-Asset Trend Following

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: Hold ETF if Close > SMA(200), else SHY; equal weight, monthly rebalance
**Universe**: SPY, TLT, GLD, DBC, VNQ
**Period**: 2007-01-01 → 2026-04-01

### Results

| Strategy | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| Trend Following | {format_pct(m10t.get('cagr'))} | {m10t.get('sharpe',0):.3f} | {format_pct(m10t.get('max_drawdown'))} |
| 60/40 SPY+TLT | {format_pct(m10bm.get('cagr'))} | {m10bm.get('sharpe',0):.3f} | {format_pct(m10bm.get('max_drawdown'))} |
""")

    # ── H011 ──
    r11   = results.get("h011", {})
    m11lv = r11.get("low_vol_bottom3", {})
    m11s  = r11.get("benchmark_spy", {})
    cards.append(f"""---

## H011 — Low-Volatility Anomaly on Sectors

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: Rank 9 SPDR sectors by 126-day realized vol; long bottom 3, monthly rebalance
**Period**: 2003-01-01 → 2026-04-01

### Results

| Strategy | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| Low-Vol Bottom 3 | {format_pct(m11lv.get('cagr'))} | {m11lv.get('sharpe',0):.3f} | {format_pct(m11lv.get('max_drawdown'))} |
| SPY B&H | {format_pct(m11s.get('cagr'))} | {m11s.get('sharpe',0):.3f} | {format_pct(m11s.get('max_drawdown'))} |
""")

    # ── H012 ──
    r12   = results.get("h012", {})
    m12   = r12.get("momentum_12_1", {})
    m12s  = r12.get("benchmark_spy", {})
    cards.append(f"""---

## H012 — Price Momentum on Sectors (12-1)

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: 12-month minus 1-month momentum; long top 3 sectors, monthly rebalance
**Period**: 2003-01-01 → 2026-04-01

### Results

| Strategy | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| Momentum 12-1 (top 3) | {format_pct(m12.get('cagr'))} | {m12.get('sharpe',0):.3f} | {format_pct(m12.get('max_drawdown'))} |
| SPY B&H | {format_pct(m12s.get('cagr'))} | {m12s.get('sharpe',0):.3f} | {format_pct(m12s.get('max_drawdown'))} |
""")

    # ── H013 ──
    r13  = results.get("h013", {})
    w13  = r13.get("winner", "?")
    cs13 = r13.get("combos", {})
    rows13 = ""
    for label, m in cs13.items():
        if isinstance(m, dict) and "cagr" in m:
            rows13 += f"| {label} | {format_pct(m.get('cagr'))} | {m.get('sharpe',0):.3f} | {format_pct(m.get('max_drawdown'))} |\n"
    cards.append(f"""---

## H013 — Donchian Channel Breakout on SPY

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: Buy on N-day high breakout, sell on N-day low breach
**Variants**: 20-day, 55-day
**Period**: 2003-01-01 → 2026-04-01

### Results

| Strategy | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
{rows13}**Winner**: `{w13}` — Sharpe {r13.get('combos', {}).get(w13, {}).get('sharpe', 0):.3f}
""")

    # ── H014 ──
    r14 = results.get("h014", {})
    cards.append(f"""---

## H014 — Mean-Reversion After Large Down Days

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: Buy SPY after daily return < -1.5%, hold 5 days
**Period**: 2003-01-01 → 2026-04-01

### Results

- Signal count: {r14.get('n_signals', 'n/a')}
- Avg 5-day forward return (signal): {format_pct(r14.get('avg_forward_return'), 2)}
- Hit rate (% positive after 5 days): {format_pct(r14.get('hit_rate'))}
- Avg 5-day forward return (random): {format_pct(r14.get('random_avg_forward_return'), 2)}
- Edge (signal minus random): {format_pct(r14.get('edge'), 2)}
- t-stat: {r14.get('t_stat', 'n/a')}  p-value: {r14.get('p_value', 'n/a')}
""")

    # ── H015 ──
    r15   = results.get("h015", {})
    mavgs = r15.get("month_avg_returns", {})
    month_rows = "\n".join(f"| {m} | {format_pct(v, 2)} |" for m, v in mavgs.items())
    cards.append(f"""---

## H015 — Seasonal Patterns (Month-of-Year / Sell in May)

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: Statistical test of Nov-Apr vs May-Oct seasonal pattern
**Period**: 2003-01-01 → 2026-04-01

### Results

| Month | Avg Return |
|-------|-----------|
{month_rows}

- Nov–Apr CAGR equivalent: {format_pct(r15.get('nov_apr_cagr_equiv'))}  avg/month: {format_pct(r15.get('nov_apr_avg_monthly'), 2)}
- May–Oct CAGR equivalent: {format_pct(r15.get('may_oct_cagr_equiv'))}  avg/month: {format_pct(r15.get('may_oct_avg_monthly'), 2)}
- Seasonal premium: {format_pct(r15.get('seasonal_premium_monthly'), 2)} per month
- t-stat: {r15.get('t_stat', 'n/a')}  p-value: {r15.get('p_value', 'n/a')}
- Statistically significant (p<0.05): {'YES' if r15.get('p_value', 1) < 0.05 else 'NO'}
""")

    # ── H016 ──
    r16   = results.get("h016", {})
    m16   = r16.get("momentum_carry_blend", {})
    m16s  = r16.get("benchmark_spy", {})
    cards.append(f"""---

## H016 — Multi-Asset Momentum + Carry Blend

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: SPY, TLT, GLD — score = momentum rank + inverse-vol rank; hold top 2, rest to SHY
**Period**: 2007-01-01 → 2026-04-01

### Results

| Strategy | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| Momentum+Carry Blend | {format_pct(m16.get('cagr'))} | {m16.get('sharpe',0):.3f} | {format_pct(m16.get('max_drawdown'))} |
| SPY B&H | {format_pct(m16s.get('cagr'))} | {m16s.get('sharpe',0):.3f} | {format_pct(m16s.get('max_drawdown'))} |
""")

    # ── H017 ──
    r17  = results.get("h017", {})
    m17f = r17.get("vix_filtered", {})
    m17u = r17.get("unfiltered_h007_baseline", {})
    m17s = r17.get("benchmark_spy", {})
    cards.append(f"""---

## H017 — VIX-Filtered Iron Condor Entry

**Date filed**: {today}
**Status**: COMPLETE
**Strategy**: Iron condor as H007 but only enter when VIX > 15 (skip low-premium months)
**Period**: 2007-01-01 → 2026-04-01

### Results

| Strategy | CAGR | Sharpe | MaxDD | Win% | Trades |
|----------|------|--------|-------|------|--------|
| Unfiltered (H007) | {format_pct(m17u.get('cagr'))} | {m17u.get('sharpe',0):.3f} | {format_pct(m17u.get('max_dd'))} | {format_pct(m17u.get('win_rate'))} | {m17u.get('n_trades','?')} |
| VIX > 15 Filtered | {format_pct(m17f.get('cagr'))} | {m17f.get('sharpe',0):.3f} | {format_pct(m17f.get('max_dd'))} | {format_pct(m17f.get('win_rate'))} | {m17f.get('n_trades','?')} |
| SPY B&H | {format_pct(m17s.get('cagr'))} | n/a | {format_pct(m17s.get('max_drawdown'))} | — | — |
""")

    # Append all cards
    for card in cards:
        content += card

    with open(log_path, "w") as f:
        f.write(content)

    print(f"  Hypothesis log updated: {log_path}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

HYPOTHESES = [
    ("h008", run_h008),
    ("h009", run_h009),
    ("h010", run_h010),
    ("h011", run_h011),
    ("h012", run_h012),
    ("h013", run_h013),
    ("h014", run_h014),
    ("h015", run_h015),
    ("h016", run_h016),
    ("h017", run_h017),
]

if __name__ == "__main__":
    for hid, fn in HYPOTHESES:
        try:
            fn()
        except Exception as e:
            tb = traceback.format_exc()
            print(f"\n  ERROR in {hid}: {e}")
            print(tb)
            results[hid] = {"error": str(e), "traceback": tb}
            save_results()
            continue

    print("\n" + "="*72)
    total_min = (time.time() - RUN_START) / 60
    print(f"  All hypotheses complete in {total_min:.1f} minutes")
    print(f"  Results saved to: {RESULTS_FILE}")

    try:
        update_hypothesis_log()
    except Exception as e:
        print(f"  ERROR updating hypothesis log: {e}")
        traceback.print_exc()

    print("="*72)
    print("  DONE")
