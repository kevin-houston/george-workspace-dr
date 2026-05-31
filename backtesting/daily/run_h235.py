"""
H235 — RF Classifier as IBS Signal Confirmation Filter (XLK / SMH / IGV)
=========================================================================
Source: Jevtic, Délèze & Osterrieder (2022) ZHAW bachelor thesis —
"AI for Trading Strategies: A Practical Application on Brent Crude Oil"
RF top model (Sharpe 1.15, PF 5.77); MACD 44% feature importance.

Hypothesis: H112's IBS mean-reversion signals on XLK, SMH, and IGV generate
false positives when the ETF is in a sustained downtrend. Adding an RF
classifier trained on TA features (MACD, RSI, Stochastic, ROC) as a
confirmation gate — entry only when IBS triggers AND RF predicts "up"
(prob ≥ 0.55) — will improve win rate and Sharpe vs pure IBS baseline.

Design:
- Universe: XLK (20% weight), SMH (8%), IGV (2%)
- IBS signal: same parameters as H112 production
  XLK: buy<0.15, sell>0.90, hold=7, gap=-0.010
  SMH: buy<0.20, sell>0.75, hold=6, gap=-0.005
  IGV: buy<0.30, sell>0.75, hold=5, gap=0.0025
- RF features: MACD(12/26/9), RSI(14), Stoch %K/%D(14/3), ROC(10)
- IS: 2013-2020 (train RF on IBS trade outcomes)
- OOS: 2021-2026 (frozen RF applied to live IBS signals)
- Confirm: OOS Sharpe > H112 IBS baseline
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2003-01-01"
FULL_END   = "2026-04-27"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-27")

INITIAL_EQUITY = 100_000.0

# H112 IBS parameters (production values)
ETF_PARAMS = {
    "XLK": {"buy": 0.15, "sell": 0.90, "hold": 7, "gap": -0.010, "weight": 0.20},
    "SMH": {"buy": 0.20, "sell": 0.75, "hold": 6, "gap": -0.005, "weight": 0.08},
    "IGV": {"buy": 0.30, "sell": 0.75, "hold": 5, "gap":  0.0025,"weight": 0.02},
}
IBS_TOTAL_WEIGHT = 0.30

RF_PROB_THRESHOLD = 0.55   # RF must predict P(up) >= this to allow entry
RF_PARAMS = {
    "n_estimators": 200,
    "max_depth":    5,
    "random_state": 42,
    "n_jobs":       -1,
}


# ── Data loading ──────────────────────────────────────────────────────────────

def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    """Load daily OHLCV, checking existing caches first."""
    _prefixes = [f"h{i:03d}" for i in range(62, 235)]
    for prefix in _prefixes:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{FULL_START}_{FULL_END}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h235_{ticker}_ohlcv_{FULL_START}_{FULL_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).normalize()
    df.to_parquet(cp)
    return df


# ── IBS signal + equity curve (with trade log) ───────────────────────────────

def ibs_equity_and_trades(df: pd.DataFrame, buy: float, sell: float,
                           hold: int, gap: float) -> tuple:
    """
    Runs H112-style IBS strategy.
    Returns:
        equity_series: pd.Series of daily equity values
        trades: list of dicts with {date, entry_price, exit_price, return_oc, label}
    """
    denom   = (df["high"] - df["low"]).replace(0, np.nan)
    ibs     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g       = (df["open"] - prev_cl) / prev_cl

    equity   = INITIAL_EQUITY
    position = 0
    days_held = 0
    equity_series = []
    trades = []
    trade_entry_idx = None

    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o  = float(df["open"].iloc[i])
        c  = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i - 1])
        dt = df.index[i]

        ret_oc = (c / o - 1) if o > 0 else 0.0
        ret_cc = (c / cp - 1) if cp > 0 else 0.0

        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1
                days_held = 1
                trade_entry_idx = i
                equity *= (1 + ret_oc)
                # Record the trade event (will update label on exit)
        else:
            days_held += 1
            equity *= (1 + ret_cc)
            if cur_ibs > sell or days_held >= hold:
                # Trade exit
                if trade_entry_idx is not None:
                    entry_dt = df.index[trade_entry_idx]
                    # Compute total trade return from entry open to exit close
                    entry_o = float(df["open"].iloc[trade_entry_idx])
                    exit_c  = float(df["close"].iloc[i])
                    trade_ret = (exit_c / entry_o - 1) if entry_o > 0 else 0.0
                    trades.append({
                        "entry_date": entry_dt,
                        "exit_date":  dt,
                        "entry_idx":  trade_entry_idx,
                        "trade_ret":  trade_ret,
                        "label":      1 if trade_ret > 0 else 0,
                    })
                position = 0
                days_held = 0
                trade_entry_idx = None

        equity_series.append((dt, equity))

    eq_series = pd.Series(
        [v for _, v in equity_series],
        index=pd.DatetimeIndex([d for d, _ in equity_series])
    )
    return eq_series, trades


# ── TA features at a given point in time ─────────────────────────────────────

def compute_ta_features_at(df: pd.DataFrame, idx: int, lookback: int = 60) -> dict:
    """
    Compute TA features using data up to (not including) idx.
    Uses last `lookback` bars of history.
    """
    start = max(0, idx - lookback)
    sub   = df.iloc[start:idx]
    if len(sub) < 30:
        return None

    c   = sub["close"]
    h   = sub["high"]
    lo  = sub["low"]

    # MACD (12/26/9)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line   = float((ema12 - ema26).iloc[-1])
    signal_line = float((ema12 - ema26).ewm(span=9, adjust=False).mean().iloc[-1])
    macd_hist   = macd_line - signal_line

    # RSI (14)
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = float((100 - 100 / (1 + rs)).iloc[-1]) / 100.0  # [0,1]

    # Stochastic %K/%D (14/3)
    low14  = lo.rolling(14).min()
    high14 = h.rolling(14).max()
    denom  = (high14 - low14).replace(0, np.nan)
    stoch_k = float(((c - low14) / denom).iloc[-1])
    stoch_d = float(((c - low14) / denom).rolling(3).mean().iloc[-1])

    # ROC (10)
    roc = float(c.pct_change(10).iloc[-1]) if len(c) >= 11 else np.nan

    feats = {
        "macd_line":   macd_line,
        "signal_line": signal_line,
        "macd_hist":   macd_hist,
        "rsi":         rsi if not np.isnan(rsi) else 0.5,
        "stoch_k":     stoch_k if not np.isnan(stoch_k) else 0.5,
        "stoch_d":     stoch_d if not np.isnan(stoch_d) else 0.5,
        "roc":         roc if not np.isnan(roc) else 0.0,
    }
    return feats


FEATURE_COLS = ["macd_line", "signal_line", "macd_hist", "rsi", "stoch_k", "stoch_d", "roc"]


# ── Backtest with RF gate ─────────────────────────────────────────────────────

def run_rf_gated_ibs(df: pd.DataFrame, buy: float, sell: float, hold: int,
                     gap: float, rf_model, is_period: bool = False) -> tuple:
    """
    Run IBS strategy with RF gate.
    is_period: if True, always enter (no RF gate — for IS equity curve baseline).
    Returns equity series and trade list.
    """
    denom   = (df["high"] - df["low"]).replace(0, np.nan)
    ibs     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g       = (df["open"] - prev_cl) / prev_cl

    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    trade_entry_idx = None
    equity_series = []
    trades = []
    rf_accepted = 0
    rf_rejected = 0

    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o  = float(df["open"].iloc[i])
        c  = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i - 1])
        dt = df.index[i]

        ret_oc = (c / o - 1) if o > 0 else 0.0
        ret_cc = (c / cp - 1) if cp > 0 else 0.0

        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                # IBS triggered — now check RF gate
                allow_entry = True
                if rf_model is not None and not is_period:
                    feats = compute_ta_features_at(df, i)
                    if feats is not None:
                        X = np.array([[feats[col] for col in FEATURE_COLS]])
                        prob_up = rf_model.predict_proba(X)[0][1]
                        allow_entry = prob_up >= RF_PROB_THRESHOLD
                        if allow_entry:
                            rf_accepted += 1
                        else:
                            rf_rejected += 1

                if allow_entry:
                    position = 1
                    days_held = 1
                    trade_entry_idx = i
                    equity *= (1 + ret_oc)
        else:
            days_held += 1
            equity *= (1 + ret_cc)
            if cur_ibs > sell or days_held >= hold:
                if trade_entry_idx is not None:
                    entry_o = float(df["open"].iloc[trade_entry_idx])
                    exit_c  = float(df["close"].iloc[i])
                    trade_ret = (exit_c / entry_o - 1) if entry_o > 0 else 0.0
                    trades.append({
                        "entry_date": df.index[trade_entry_idx],
                        "exit_date":  dt,
                        "trade_ret":  trade_ret,
                        "label":      1 if trade_ret > 0 else 0,
                    })
                position = 0
                days_held = 0
                trade_entry_idx = None

        equity_series.append((dt, equity))

    eq = pd.Series(
        [v for _, v in equity_series],
        index=pd.DatetimeIndex([d for d, _ in equity_series])
    )
    return eq, trades, rf_accepted, rf_rejected


# ── Metrics ──────────────────────────────────────────────────────────────────

def to_monthly(eq: pd.Series) -> pd.Series:
    return eq.resample("ME").last().ffill().pct_change().dropna()


def stats_monthly(r: pd.Series, label: str = "") -> dict:
    r = r.dropna()
    if len(r) < 6:
        return {"label": label, "n": 0, "sharpe": 0.0, "cagr": 0.0, "maxdd": 0.0}
    eq   = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1 if n_yr > 0 else 0.0
    vol  = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    maxdd  = float((eq / eq.expanding().max() - 1).min())
    neg_yr = int(sum(r.resample("YE").apply(lambda x: (1 + x).prod() - 1) < 0))
    return {
        "label":   label,
        "n":       len(r),
        "sharpe":  round(sharpe, 3),
        "cagr":    round(cagr, 4),
        "maxdd":   round(maxdd, 4),
        "neg_yrs": neg_yr,
    }


def trade_stats(trades: list) -> dict:
    if not trades:
        return {"n_trades": 0, "win_rate": 0.0}
    n = len(trades)
    wins = sum(1 for t in trades if t["label"] == 1)
    returns = [t["trade_ret"] for t in trades]
    return {
        "n_trades":    n,
        "win_rate":    round(wins / n, 4) if n > 0 else 0.0,
        "mean_ret":    round(float(np.mean(returns)), 4),
        "median_ret":  round(float(np.median(returns)), 4),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("H235 — RF Classifier as IBS Signal Confirmation Filter")
    print("=" * 60)

    # ── Step 1: Load data ────────────────────────────────────────────────────
    print("\nStep 1: Loading OHLCV data…")
    ohlcv = {}
    for ticker in ETF_PARAMS:
        ohlcv[ticker] = fetch_ohlcv(ticker)
        print(f"  {ticker}: {len(ohlcv[ticker])} rows")

    # ── Step 2: Run pure IBS on IS to get trade labels for RF training ───────
    print("\nStep 2: Generating IS IBS trades for RF training…")

    is_feature_rows = []
    is_trade_labels = []

    for ticker, params in ETF_PARAMS.items():
        df = ohlcv[ticker]
        df_is = df[(df.index >= IS_START) & (df.index <= IS_END)]
        _, trades = ibs_equity_and_trades(
            df_is, params["buy"], params["sell"], params["hold"], params["gap"]
        )
        print(f"  {ticker}: {len(trades)} IS trades")

        # For each trade, compute TA features at signal time (entry_idx within IS df)
        df_is_reset = df_is.reset_index(drop=False)
        for trade in trades:
            entry_idx = trade["entry_idx"]
            feats = compute_ta_features_at(df_is, entry_idx)
            if feats is None:
                continue
            row = [feats[col] for col in FEATURE_COLS]
            if any(np.isnan(v) for v in row):
                continue
            is_feature_rows.append(row)
            is_trade_labels.append(trade["label"])

    X_train = np.array(is_feature_rows)
    y_train = np.array(is_trade_labels)
    print(f"\n  IS training samples: {len(X_train)} (class balance: {y_train.mean():.2%} wins)")

    # ── Step 3: Train RF classifier ─────────────────────────────────────────
    print("\nStep 3: Training RF classifier…")
    rf = RandomForestClassifier(**RF_PARAMS)
    rf.fit(X_train, y_train)

    # IS accuracy and classification report
    y_pred_is = rf.predict(X_train)
    is_acc = (y_pred_is == y_train).mean()
    print(f"  IS accuracy: {is_acc:.2%}")
    print(f"  IS classification report:")
    print(classification_report(y_train, y_pred_is, target_names=["down", "up"], zero_division=0))

    # Feature importance
    fi = dict(zip(FEATURE_COLS, rf.feature_importances_.tolist()))
    fi_sorted = sorted(fi.items(), key=lambda x: x[1], reverse=True)
    print("  Feature importance (RF):")
    for fname, fval in fi_sorted:
        print(f"    {fname:<15} {fval:.3f}")

    # ── Step 4: Run full backtests (IS + OOS) ────────────────────────────────
    print("\nStep 4: Running backtests…")

    # We run on the full date range, then slice IS/OOS
    results = {}
    for ticker, params in ETF_PARAMS.items():
        df = ohlcv[ticker]
        w  = params["weight"] / IBS_TOTAL_WEIGHT  # normalized weight within IBS sleeve

        # Pure IBS (no RF gate) — full period
        eq_pure, trades_pure, _, _ = run_rf_gated_ibs(
            df, params["buy"], params["sell"], params["hold"], params["gap"],
            rf_model=None
        )

        # RF-gated IBS — OOS only (RF is frozen after IS training)
        # For IS period, run without gate to maintain IS equity curve
        df_is  = df[df.index <= IS_END]
        df_oos = df[df.index >= OOS_START]

        eq_is_pure, trades_is_pure, _, _ = run_rf_gated_ibs(
            df_is, params["buy"], params["sell"], params["hold"], params["gap"],
            rf_model=None
        )
        eq_oos_rf, trades_oos_rf, rf_acc, rf_rej = run_rf_gated_ibs(
            df_oos, params["buy"], params["sell"], params["hold"], params["gap"],
            rf_model=rf
        )
        eq_oos_pure, trades_oos_pure, _, _ = run_rf_gated_ibs(
            df_oos, params["buy"], params["sell"], params["hold"], params["gap"],
            rf_model=None
        )

        print(f"\n  {ticker}:")
        print(f"    IS trades (pure): {len(trades_is_pure)} | OOS trades pure: {len(trades_oos_pure)} | OOS RF-gated: {len(trades_oos_rf)}")
        print(f"    RF accepted: {rf_acc}, rejected: {rf_rej}")

        results[ticker] = {
            "eq_pure":      eq_pure,
            "eq_is_pure":   eq_is_pure,
            "eq_oos_pure":  eq_oos_pure,
            "eq_oos_rf":    eq_oos_rf,
            "trades_is":    trades_is_pure,
            "trades_oos_pure": trades_oos_pure,
            "trades_oos_rf":   trades_oos_rf,
            "rf_acc":       rf_acc,
            "rf_rej":       rf_rej,
            "weight":       w,
        }

    # ── Step 5: Blend ETF curves into portfolio ───────────────────────────────
    print("\nStep 5: Computing portfolio-level statistics…")

    def blend_equity_curves(eq_dict: dict, weights: dict) -> pd.Series:
        """Combine monthly returns from multiple ETF equity curves."""
        monthly_rets = {}
        for t, eq in eq_dict.items():
            mr = to_monthly(eq)
            monthly_rets[t] = mr
        idx = monthly_rets[list(monthly_rets.keys())[0]].index
        for mr in monthly_rets.values():
            idx = idx.intersection(mr.index)
        idx = idx.sort_values()
        port = sum(w * monthly_rets[t].reindex(idx, fill_value=0.0)
                   for t, w in weights.items())
        return port

    weights = {t: p["weight"] / IBS_TOTAL_WEIGHT for t, p in ETF_PARAMS.items()}

    # IS pure baseline
    eq_is_pure_dict = {t: results[t]["eq_is_pure"] for t in ETF_PARAMS}
    port_is_pure = blend_equity_curves(eq_is_pure_dict, weights)

    # OOS pure baseline
    eq_oos_pure_dict = {t: results[t]["eq_oos_pure"] for t in ETF_PARAMS}
    port_oos_pure = blend_equity_curves(eq_oos_pure_dict, weights)

    # OOS RF-gated
    eq_oos_rf_dict = {t: results[t]["eq_oos_rf"] for t in ETF_PARAMS}
    port_oos_rf = blend_equity_curves(eq_oos_rf_dict, weights)

    # Full pure IBS (IS+OOS combined)
    eq_full_pure_dict = {t: results[t]["eq_pure"] for t in ETF_PARAMS}
    port_full_pure = blend_equity_curves(eq_full_pure_dict, weights)
    port_full_is   = port_full_pure[(port_full_pure.index >= IS_START) & (port_full_pure.index <= IS_END)]
    port_full_oos  = port_full_pure[port_full_pure.index >= OOS_START]

    # ── Step 6: Results table ────────────────────────────────────────────────
    print("\n" + "=" * 75)
    print(f"{'Strategy':<35} {'IS Sharpe':>10} {'OOS Sharpe':>10} {'OOS MaxDD':>10} {'NegYrs':>7}")
    print("-" * 75)

    s_is_pure   = stats_monthly(port_is_pure,    "IBS Pure IS")
    s_oos_pure  = stats_monthly(port_oos_pure,   "IBS Pure OOS")
    s_oos_rf    = stats_monthly(port_oos_rf,     "IBS RF-gated OOS")
    s_full_is   = stats_monthly(port_full_is,    "IBS Full IS")
    s_full_oos  = stats_monthly(port_full_oos,   "IBS Full OOS")

    for label, is_s, oos_s in [
        ("H235 RF-gated IBS",   s_is_pure,  s_oos_rf),
        ("H235 Pure IBS baseline", s_is_pure, s_oos_pure),
        ("H235 Full-period pure IBS", s_full_is, s_full_oos),
    ]:
        print(f"{label:<35} {is_s.get('sharpe',0):>10.3f} {oos_s.get('sharpe',0):>10.3f} "
              f"{oos_s.get('maxdd',0):>10.1%} {oos_s.get('neg_yrs',0):>7d}")

    # Per-ETF trade stats
    print("\n  Per-ETF OOS trade stats:")
    print(f"  {'ETF':<6} {'Pure n':>8} {'Pure WR':>10} {'RF n':>8} {'RF WR':>10} {'RF acc%':>10}")
    for ticker in ETF_PARAMS:
        tp = trade_stats(results[ticker]["trades_oos_pure"])
        tr = trade_stats(results[ticker]["trades_oos_rf"])
        acc = results[ticker]["rf_acc"]
        rej = results[ticker]["rf_rej"]
        total = acc + rej
        acc_pct = acc / total if total > 0 else 0
        print(f"  {ticker:<6} {tp['n_trades']:>8} {tp['win_rate']:>10.1%} "
              f"{tr['n_trades']:>8} {tr['win_rate']:>10.1%} {acc_pct:>10.1%}")

    # Confirm
    h235_oos_sharpe   = s_oos_rf.get("sharpe", 0)
    baseline_sharpe   = s_oos_pure.get("sharpe", 0)
    confirmed = h235_oos_sharpe > baseline_sharpe

    print(f"\n=== Verdict ===")
    print(f"H235 RF-gated OOS Sharpe: {h235_oos_sharpe:.3f}")
    print(f"H235 Pure IBS OOS Sharpe: {baseline_sharpe:.3f}")
    print(f"Improvement: {h235_oos_sharpe - baseline_sharpe:+.3f}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'} (threshold: RF-gated > pure IBS baseline)")

    out = {
        "hypothesis":          "H235",
        "confirmed":           confirmed,
        "rf_gated_is":         s_is_pure,
        "rf_gated_oos":        s_oos_rf,
        "pure_ibs_oos":        s_oos_pure,
        "full_period_ibs_is":  s_full_is,
        "full_period_ibs_oos": s_full_oos,
        "baseline_sharpe":     baseline_sharpe,
        "feature_importance":  fi_sorted,
        "rf_accuracy_is":      round(float(is_acc), 4),
        "rf_prob_threshold":   RF_PROB_THRESHOLD,
        "per_etf": {
            t: {
                "oos_pure_trades":  trade_stats(results[t]["trades_oos_pure"]),
                "oos_rf_trades":    trade_stats(results[t]["trades_oos_rf"]),
                "rf_accepted":      results[t]["rf_acc"],
                "rf_rejected":      results[t]["rf_rej"],
            }
            for t in ETF_PARAMS
        },
    }

    out_path = RESULT_DIR / "h235_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {out_path}")
    return out


if __name__ == "__main__":
    main()
