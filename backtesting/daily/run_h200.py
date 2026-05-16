"""
H200 — Graphical Matching Pairs Trading (Stock-Level)
======================================================
Source: arXiv:2403.07998 (Qureshi & Zaman, 2024)

Method:
  1. Monthly: build correlation graph over 30 large-cap stocks (12-month rolling)
  2. Maximum weighted matching (networkx): each stock in at most 1 pair
  3. Engle-Granger cointegration test (p < 0.05) — reject uncointeg. pairs
  4. Daily z-score of log(price_A / price_B), 60-day rolling mean/std
  5. Entry: |z| > 1.5 → long underperformer, short outperformer
     Exit:  |z| < 0.5
     Stop:  |z| > 3.0
  6. Dollar-neutral per pair; equal weight across active pairs

Universe: same 30 large-cap S&P 500 stocks as H181/H198
Data: daily 2010-2026
IS:  2013-01-01 to 2020-12-31
OOS: 2021-01-01 to 2026-04-30

Confirm criteria (market-neutral): OOS Sharpe > 0.5, OOS Cumul > 1.3x
"""

import warnings
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from statsmodels.tsa.stattools import coint
import networkx as nx

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","NVDA","AMZN","META","TSLA","GOOGL","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM",
    "UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST",
    "CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2010-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

CORR_WINDOW  = 252    # days for correlation lookback (12 months)
ZSCORE_LB    = 60     # rolling window for z-score
ENTRY_Z      = 1.5
EXIT_Z       = 0.5
STOP_Z       = 3.0
COINT_PVAL   = 0.05
COST_RT      = 0.001  # 0.10% round-trip per trade per leg


def fetch_daily(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(152, 201)]:
        for suffix in ["close", "ohlc"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_{suffix}_{DATA_START}_{DATA_END}.parquet"
            if cp.exists():
                df = pd.read_parquet(cp)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h200_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r: pd.Series) -> float:
    if len(r) < 12 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(252))


def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())


def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def get_matching(prices_window: pd.DataFrame) -> list[tuple]:
    """Maximum weighted matching on correlation graph."""
    log_ret = np.log(prices_window).diff().dropna()
    if len(log_ret) < 30:
        return []
    corr = log_ret.corr()
    tickers = corr.columns.tolist()
    n = len(tickers)

    G = nx.Graph()
    G.add_nodes_from(tickers)
    for i in range(n):
        for j in range(i + 1, n):
            w = corr.iloc[i, j]
            if np.isfinite(w) and w > 0:
                G.add_edge(tickers[i], tickers[j], weight=w)

    matching = nx.max_weight_matching(G, maxcardinality=False)
    return list(matching)


def test_coint(pa: pd.Series, pb: pd.Series) -> bool:
    """Engle-Granger cointegration test. Returns True if cointegrated (p < threshold)."""
    try:
        _, pval, _ = coint(pa, pb)
        return pval < COINT_PVAL
    except Exception:
        return False


def zscore_series(spread: pd.Series, lb: int) -> pd.Series:
    roll_mean = spread.rolling(lb).mean()
    roll_std  = spread.rolling(lb).std()
    return (spread - roll_mean) / roll_std.replace(0, np.nan)


def backtest_pairs(prices: pd.DataFrame) -> pd.Series:
    """
    Full daily pairs backtest.
    Returns daily P&L series (as fraction of notional capital).
    """
    all_dates = prices.index
    monthly_ends = prices.resample("ME").last().index

    # Track state per pair: (A, B, position: +1 long A/-1 long B, entry_z)
    active_pairs: dict[tuple, dict] = {}
    daily_pnl = {}

    # Pre-compute log prices
    log_px = np.log(prices)

    current_pairs: list[tuple] = []
    pair_coint: dict[tuple, bool] = {}

    for i, date in enumerate(all_dates):
        if date < IS_START:
            continue

        # Monthly reassignment: on first trading day of each month
        if i > 0 and (date.month != all_dates[i - 1].month or date == all_dates[0]):
            window_start = date - pd.Timedelta(days=CORR_WINDOW + 30)
            px_window = prices[(prices.index >= window_start) & (prices.index < date)]
            if len(px_window) < CORR_WINDOW // 2:
                pass
            else:
                new_pairs = get_matching(px_window)
                # Test cointegration for each matched pair
                cointed = []
                for pa_name, pb_name in new_pairs:
                    pa = px_window[pa_name].dropna()
                    pb = px_window[pb_name].dropna()
                    common = pa.index.intersection(pb.index)
                    if len(common) < 60:
                        continue
                    if test_coint(pa.loc[common], pb.loc[common]):
                        cointed.append((pa_name, pb_name))

                # Close any pairs that are no longer active
                pairs_set = set(map(frozenset, cointed))
                to_close = [k for k in active_pairs
                            if frozenset(k) not in pairs_set]
                for k in to_close:
                    del active_pairs[k]

                current_pairs = cointed
                pair_coint = {(a, b): True for a, b in cointed}

        if not current_pairs:
            daily_pnl[date] = 0.0
            continue

        # Compute z-scores and signals
        day_pnl = 0.0
        n_active = len(current_pairs)

        for (pa_name, pb_name) in current_pairs:
            if pa_name not in prices.columns or pb_name not in prices.columns:
                continue

            # Use rolling z-score on log spread
            lookback_start = date - pd.Timedelta(days=ZSCORE_LB + 30)
            spread_window = log_px[pa_name][(log_px.index >= lookback_start) &
                                            (log_px.index <= date)] - \
                            log_px[pb_name][(log_px.index >= lookback_start) &
                                            (log_px.index <= date)]
            if len(spread_window) < ZSCORE_LB:
                continue

            z = (spread_window.iloc[-1] - spread_window.iloc[-ZSCORE_LB:].mean()) / \
                (spread_window.iloc[-ZSCORE_LB:].std() + 1e-10)

            key = (pa_name, pb_name)
            pos = active_pairs.get(key, {}).get("position", 0)

            # Daily return contribution (from previous day's position)
            if pos != 0 and i > 0 and date in all_dates and date > all_dates[0]:
                prev_date = all_dates[i - 1]
                if prev_date in prices.index:
                    ret_a = prices.loc[date, pa_name] / prices.loc[prev_date, pa_name] - 1
                    ret_b = prices.loc[date, pb_name] / prices.loc[prev_date, pb_name] - 1
                    if pos == 1:    # long A, short B
                        pair_ret = (ret_a - ret_b) / 2
                    else:           # long B, short A
                        pair_ret = (ret_b - ret_a) / 2
                    day_pnl += pair_ret / n_active

            # Signal decisions
            new_pos = pos
            cost = 0.0
            if pos == 0:
                if z > ENTRY_Z:      # spread too wide, short spread (short A, long B)
                    new_pos = -1
                    cost = COST_RT / n_active
                elif z < -ENTRY_Z:   # spread too narrow, long spread (long A, short B)
                    new_pos = 1
                    cost = COST_RT / n_active
            elif pos == 1:
                if abs(z) < EXIT_Z or z > STOP_Z:
                    new_pos = 0
                    cost = COST_RT / n_active
            elif pos == -1:
                if abs(z) < EXIT_Z or z < -STOP_Z:
                    new_pos = 0
                    cost = COST_RT / n_active

            day_pnl -= cost
            if key not in active_pairs:
                active_pairs[key] = {}
            active_pairs[key]["position"] = new_pos

        daily_pnl[date] = day_pnl

    s = pd.Series(daily_pnl)
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


def eval_period(rets: pd.Series, label: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    r = r.dropna()
    if len(r) < 20:
        return {"label": label, "n": 0}
    ann_r = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {
        "label":   label,
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "cagr":    round(float(r.mean() * 252), 3),
        "cumul":   round(cumul(r), 4),
        "maxdd":   round(maxdd(r), 3),
        "neg_yrs": int((ann_r < 0).sum()),
    }


def main():
    print("H200 — Graphical Matching Pairs Trading")
    print("Loading price data…")

    prices_list = []
    for t in UNIVERSE:
        try:
            s = fetch_daily(t)
            s = s.loc[DATA_START:DATA_END]
            if len(s) > 500:
                prices_list.append(s)
        except Exception as e:
            print(f"  WARN: {t} — {e}")

    prices = pd.concat(prices_list, axis=1).sort_index()
    prices = prices.ffill().dropna(how="any")
    print(f"  {prices.shape[1]} tickers, {len(prices)} trading days")

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h200_SPY_close_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"]
        pd.DataFrame(spy_px).to_parquet(spy_cp)
    spy_ret = spy_px.pct_change().dropna()

    print("\nRunning backtest (daily, with monthly pair reassignment)…")
    daily_rets = backtest_pairs(prices)

    # --- Diagnostic: how many unique pairs were traded? ---
    # (check via first month's matching)
    px_sample = prices.loc[IS_START:IS_START + pd.Timedelta(days=365)]
    sample_pairs = get_matching(px_sample)
    print(f"\nSample matching (IS first year): {len(sample_pairs)} pairs")
    coint_count = 0
    for pa, pb in sample_pairs:
        pa_s = prices[pa].loc[IS_START:IS_START + pd.Timedelta(days=365)]
        pb_s = prices[pb].loc[IS_START:IS_START + pd.Timedelta(days=365)]
        if test_coint(pa_s, pb_s):
            coint_count += 1
            print(f"  ✓ {pa}/{pb} — cointegrated")
        else:
            print(f"  ✗ {pa}/{pb} — NOT cointegrated")
    print(f"  Cointegrated: {coint_count}/{len(sample_pairs)} pairs")

    # Eval
    is_res  = eval_period(daily_rets, "IS  2013-2020", IS_START, IS_END)
    oos_res = eval_period(daily_rets, "OOS 2021-2026", OOS_START, OOS_END)

    spy_is  = eval_period(spy_ret, "SPY IS",  IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY OOS", OOS_START, OOS_END)

    # Monthly conversion for correlation
    monthly_strat = daily_rets.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly_spy   = spy_ret.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    common = monthly_strat.index.intersection(monthly_spy.index)
    oos_mask = (common >= OOS_START) & (common <= OOS_END)
    corr_spy = float(monthly_strat.loc[common[oos_mask]].corr(
                     monthly_spy.loc[common[oos_mask]]))

    print("\n=== H200 Results ===")
    header = f"{'Period':<18} {'Sharpe':>8} {'CAGR%':>8} {'Cumul':>8} {'MaxDD':>8} {'NegYrs':>7}"
    print(header)
    print("─" * 62)
    for res in [is_res, oos_res, spy_is, spy_oos]:
        if res["n"] == 0:
            print(f"  {res['label']:<16} — insufficient data")
            continue
        print(f"  {res['label']:<16} {res['sharpe']:>8.3f} {res['cagr']*100:>7.1f}% "
              f"{res['cumul']:>8.4f} {res['maxdd']*100:>7.1f}% {res['neg_yrs']:>7}")

    oos_sharpe = oos_res.get("sharpe", 0)
    oos_cumul  = oos_res.get("cumul", 0)
    confirmed  = oos_sharpe > 0.5 and oos_cumul > 1.3

    print(f"\n  Corr(H200, SPY) OOS = {corr_spy:.3f}")
    print(f"\n  OOS Sharpe = {oos_sharpe:.3f}  (need > 0.5)")
    print(f"  OOS Cumul  = {oos_cumul:.4f}× (need > 1.3×)")
    verdict = "CONFIRMED" if confirmed else "NOT CONFIRMED"
    print(f"\n  VERDICT: {verdict}")

    # Save results
    results = {
        "hypothesis": "H200",
        "description": "Graphical Matching Pairs Trading (stock-level)",
        "source": "arXiv:2403.07998",
        "is":  is_res,
        "oos": oos_res,
        "spy_oos": spy_oos,
        "corr_spy_oos": round(corr_spy, 4),
        "confirmed": confirmed,
        "sample_pairs_coint_rate": round(coint_count / max(len(sample_pairs), 1), 3),
    }
    out = RESULT_DIR / "h200_graphical_pairs.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved → {out}")
    return results


if __name__ == "__main__":
    main()
