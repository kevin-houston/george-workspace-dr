"""
H203 — Risk-Parity Multi-Strategy Blend (HRP)
==============================================
Hypothesis: HRP blend of three confirmed satellite strategies achieves
higher OOS Sharpe than any single strategy on the 30-stock universe.

Strategies blended:
  S1 — H198-style: 6-1m momentum, top-6, equal-weight   (OOS Sharpe 1.174)
  S2 — H191-C-style: hybrid low-vol (50% vol rank + 50% 12-1m rank), top-6  (OOS ~1.110)
  S3 — H201-style: TOM timing on SPY (last 2 + first 2 trading days), BIL otherwise  (OOS 0.740)

Method: Hierarchical Risk Parity (HRP)
  - Monthly rebalance of STRATEGY weights (not stock weights)
  - Covariance estimated on 24-month rolling window
  - Ledoit-Wolf shrinkage
  - Implementation: scipy-based HRP (no external dependency)

IS: 2016–2021 (first 24m for warm-up → effective IS 2018–2021)
OOS: 2022–2026
Baseline: H192-D BAB sector-neutral OOS Sharpe 1.367 (best single strategy)

Confirm: OOS Sharpe > 1.2 (realistic target; full 1.367 unlikely from blend of weaker strategies)
         AND MaxDD > -20%
Secondary: all 3 strategies receive positive weight in OOS

NOTE: H026 ETF rotation not included — it operates on a different universe
and capital bucket (production); this blend is for the satellite capital allocation.
"""

import warnings
warnings.filterwarnings("ignore")
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

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM",
    "UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST",
    "CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2010-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2016-01-01")   # 24m warm-up → effective 2018+
IS_END     = pd.Timestamp("2021-12-31")
OOS_START  = pd.Timestamp("2022-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

TOP_N   = 6
HRP_LOOKBACK = 24   # months for covariance estimation


def fetch_price(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 204)]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    for date_suffix in ["2011-01-01_2026-04-30", "2010-01-01_2026-04-30"]:
        cp = CACHE_DIR / f"h198_{ticker}_monthly_{date_suffix}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h203_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_spy_daily() -> pd.Series:
    cp = CACHE_DIR / "h203_SPY_daily_2010-01-01_2026-04-30.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("SPY", axis=1, level=1)
    s = raw["Close"]
    s.name = "SPY"
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r: pd.Series) -> float:
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0

def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())

def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def eval_period(rets: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "cumul": 1.0, "maxdd": 0.0, "neg_yrs": 0}
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "cagr":    round(float(r.mean() * 12), 4),
        "cumul":   round(cumul(r), 4),
        "maxdd":   round(maxdd(r), 3),
        "neg_yrs": int((ann < 0).sum()),
    }


# ─── Strategy S1: 6-1m momentum ─────────────────────────────────────────────

def strategy_s1(prices: pd.DataFrame) -> pd.Series:
    monthly_ret = prices.pct_change()
    port_rets = []
    months = prices.index[prices.index >= IS_START]
    for month_end in months:
        loc = prices.index.get_loc(month_end)
        if loc < 8:
            continue
        sig = prices.iloc[loc-1] / prices.iloc[loc-7] - 1
        sig = sig.dropna()
        if len(sig) < TOP_N:
            continue
        selected = sig.nlargest(TOP_N).index.tolist()
        ret = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


# ─── Strategy S2: hybrid low-vol (H191-C style) ─────────────────────────────

def strategy_s2(prices: pd.DataFrame) -> pd.Series:
    monthly_ret = prices.pct_change()
    port_rets = []
    months = prices.index[prices.index >= IS_START]
    for month_end in months:
        loc = prices.index.get_loc(month_end)
        if loc < 14:
            continue
        # vol signal: 12m realized volatility (lower = better)
        past_returns = monthly_ret.iloc[max(0, loc-12):loc]
        vol = past_returns.std() * np.sqrt(12)
        vol = vol.dropna()
        # momentum signal: 12-1m return
        if loc < 14:
            continue
        mom = prices.iloc[loc-1] / prices.iloc[loc-13] - 1
        mom = mom.dropna()
        # normalize both signals cross-sectionally to ranks
        common = vol.index.intersection(mom.index)
        if len(common) < TOP_N:
            continue
        vol_rank  = vol[common].rank(ascending=True, pct=True)   # low vol = high rank
        mom_rank  = mom[common].rank(ascending=True, pct=True)   # high mom = high rank
        # hybrid: 50% low-vol + 50% high-momentum (invert vol: low vol → high score)
        hybrid = 0.5 * (1 - vol_rank) + 0.5 * mom_rank          # high = good
        selected = hybrid.nlargest(TOP_N).index.tolist()
        ret = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


# ─── Strategy S3: TOM timing (H201 style) ───────────────────────────────────

def strategy_s3(spy_daily: pd.Series) -> pd.Series:
    """
    Hold SPY during TOM window (last 2 + first 2 trading days of month), BIL otherwise.
    Monthly return series.
    """
    BEFORE, AFTER = 2, 2
    spy_ret_d = spy_daily.pct_change().dropna()

    # build TOM mask on daily data
    trading_days = spy_ret_d.index
    tom_mask = pd.Series(False, index=trading_days)

    monthly_ends = trading_days.to_series().groupby(
        [trading_days.year, trading_days.month]).last().values

    for month_end in monthly_ends:
        end_loc = trading_days.get_loc(month_end)
        start_loc = max(0, end_loc - BEFORE + 1)
        after_loc  = min(len(trading_days) - 1, end_loc + AFTER)
        tom_mask.iloc[start_loc:after_loc + 1] = True

    # daily returns: SPY on TOM days, 0 (BIL) on non-TOM days
    strategy_daily = spy_ret_d.where(tom_mask, other=0.0)

    # aggregate to monthly
    monthly_ret = strategy_daily.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly_ret = monthly_ret[monthly_ret.index >= IS_START]
    return monthly_ret.sort_index()


# ─── HRP implementation ──────────────────────────────────────────────────────

def cov_ledoit_wolf(returns: np.ndarray) -> np.ndarray:
    """Simple analytical Ledoit-Wolf shrinkage (Oracle formula, Ledoit & Wolf 2004)."""
    T, N = returns.shape
    S = np.cov(returns.T, ddof=1)
    mu = np.trace(S) / N
    # shrinkage target: scaled identity
    F = mu * np.eye(N)
    # compute optimal rho
    X = returns - returns.mean(axis=0)
    rho_num = sum(
        np.sum((np.outer(X[t], X[t]) - S) ** 2)
        for t in range(T)
    ) / T
    rho_den = np.sum((S - F) ** 2)
    rho = min(1.0, rho_num / (T * rho_den)) if rho_den > 0 else 0.0
    return (1 - rho) * S + rho * F


def hrp_weights(cov: np.ndarray) -> np.ndarray:
    """
    Hierarchical Risk Parity weights (Lopez de Prado 2016).
    Returns array of weights summing to 1.0.
    """
    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])

    # correlation from covariance
    std = np.sqrt(np.diag(cov))
    std = np.where(std == 0, 1e-8, std)
    corr = cov / np.outer(std, std)
    corr = np.clip(corr, -1, 1)
    dist = np.sqrt((1 - corr) / 2)

    # quasi-diagonal reordering via single-linkage clustering
    from scipy.cluster.hierarchy import linkage, leaves_list
    from scipy.spatial.distance import squareform
    dist_condensed = squareform(dist, checks=False)
    link = linkage(dist_condensed, method="single")
    order = leaves_list(link)

    # recursive bisection
    weights = np.ones(n)
    items = list(order)

    def _bisect(items, weights):
        if len(items) <= 1:
            return
        mid = len(items) // 2
        left, right = items[:mid], items[mid:]

        def _cluster_var(idxs):
            sub_cov = cov[np.ix_(idxs, idxs)]
            inv_var = 1.0 / np.diag(sub_cov)
            inv_var /= inv_var.sum()
            return float(inv_var @ sub_cov @ inv_var)

        var_l = _cluster_var(left)
        var_r = _cluster_var(right)
        total = var_l + var_r
        alpha_l = 1 - var_l / total if total > 0 else 0.5
        for i in left:
            weights[i] *= alpha_l
        for i in right:
            weights[i] *= (1 - alpha_l)
        _bisect(left, weights)
        _bisect(right, weights)

    _bisect(items, weights)
    return weights / weights.sum()


def backtest_blend(s1: pd.Series, s2: pd.Series, s3: pd.Series) -> dict:
    """
    Roll HRP weights monthly using 24-month lookback.
    Returns dict with: blend returns series, monthly weights DataFrame.
    """
    # align all three series to common monthly index
    df = pd.concat([s1.rename("S1"), s2.rename("S2"), s3.rename("S3")], axis=1)
    df = df.dropna()

    blend_rets = []
    weight_log = []

    for i, month_end in enumerate(df.index):
        if i < HRP_LOOKBACK:
            # use equal-weight for warm-up period
            w = np.array([1/3, 1/3, 1/3])
        else:
            # 24-month rolling window of returns
            window = df.iloc[i - HRP_LOOKBACK:i].values  # (24, 3)
            try:
                cov = cov_ledoit_wolf(window)
                w = hrp_weights(cov)
            except Exception:
                w = np.array([1/3, 1/3, 1/3])

        ret_this_month = df.iloc[i].values  # [S1_ret, S2_ret, S3_ret]
        blend_ret = float(w @ ret_this_month)
        blend_rets.append((month_end, blend_ret))
        weight_log.append((month_end, w[0], w[1], w[2]))

    blend_s = pd.Series({d: r for d, r in blend_rets})
    blend_s.index = pd.DatetimeIndex(blend_s.index)

    weights_df = pd.DataFrame(weight_log, columns=["date", "w_S1", "w_S2", "w_S3"])
    weights_df = weights_df.set_index("date")

    return {"rets": blend_s, "weights": weights_df}


def main():
    print("H203 — Risk-Parity Multi-Strategy Blend (HRP)")
    print("=" * 55)

    # ── Load data ─────────────────────────────────────────────────────────────
    print("Loading price data…")
    price_list = []
    for t in UNIVERSE:
        try:
            price_list.append(fetch_price(t))
        except Exception as e:
            print(f"  WARN: {t} failed — {e}")
    prices = pd.DataFrame(price_list).T.sort_index()
    prices = prices.loc[DATA_START:]
    print(f"  {len(prices.columns)} tickers, {len(prices)} monthly bars")

    print("Loading SPY daily…")
    spy_daily = fetch_spy_daily()
    spy_monthly_ret = spy_daily.pct_change().dropna().resample("ME").apply(
        lambda x: (1 + x).prod() - 1)

    # ── Generate strategy return series ──────────────────────────────────────
    print("Building strategy return series…")
    s1 = strategy_s1(prices)
    s2 = strategy_s2(prices)
    s3 = strategy_s3(spy_daily)
    print(f"  S1 (6-1m momentum): {len(s1)} months")
    print(f"  S2 (hybrid low-vol): {len(s2)} months")
    print(f"  S3 (TOM): {len(s3)} months")

    # ── Standalone performance ────────────────────────────────────────────────
    print("\n=== Standalone strategies (OOS 2022-2026) ===")
    spy_oos  = eval_period(spy_monthly_ret, OOS_START, OOS_END)
    standalone = {}
    for key, rets, label in [
        ("S1", s1, "6-1m Momentum"),
        ("S2", s2, "Hybrid Low-Vol"),
        ("S3", s3, "TOM (SPY timing)"),
    ]:
        is_r  = eval_period(rets, IS_START, IS_END)
        oos_r = eval_period(rets, OOS_START, OOS_END)
        standalone[key] = {"label": label, "is": is_r, "oos": oos_r}
        print(f"  {key} {label:<20}: IS Sharpe {is_r['sharpe']:.3f} | "
              f"OOS Sharpe {oos_r['sharpe']:.3f} Cumul {oos_r['cumul']:.4f} MaxDD {oos_r['maxdd']:.1%}")
    print(f"  SPY benchmark:                  IS Sharpe {eval_period(spy_monthly_ret, IS_START, IS_END)['sharpe']:.3f} | "
          f"OOS Sharpe {spy_oos['sharpe']:.3f} Cumul {spy_oos['cumul']:.4f}")

    # ── Correlation matrix (OOS) ──────────────────────────────────────────────
    df = pd.concat([s1.rename("S1"), s2.rename("S2"), s3.rename("S3")], axis=1)
    oos_df = df[(df.index >= OOS_START) & (df.index <= OOS_END)].dropna()
    if len(oos_df) > 0:
        print("\n=== Correlation matrix (OOS 2022-2026) ===")
        print(oos_df.corr().round(3).to_string())

    # ── HRP blend ─────────────────────────────────────────────────────────────
    print("\nRunning HRP blend…")
    blend_result = backtest_blend(s1, s2, s3)
    blend_rets = blend_result["rets"]
    weights_df = blend_result["weights"]

    blend_is  = eval_period(blend_rets, IS_START, IS_END)
    blend_oos = eval_period(blend_rets, OOS_START, OOS_END)

    print("\n=== HRP Blend vs standalone ===")
    header = f"{'Strategy':<30} {'IS Sharpe':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8}"
    print(header)
    print("-" * len(header))
    for key, r in standalone.items():
        print(f"  {r['label']:<28} {r['is']['sharpe']:>10.3f} {r['oos']['sharpe']:>10.3f} "
              f"{r['oos']['cumul']:>10.4f} {r['oos']['maxdd']:>8.1%}")
    print(f"  {'HRP Blend':<28} {blend_is['sharpe']:>10.3f} {blend_oos['sharpe']:>10.3f} "
          f"{blend_oos['cumul']:>10.4f} {blend_oos['maxdd']:>8.1%}")
    print(f"  {'SPY benchmark':<28} {'':>10} {spy_oos['sharpe']:>10.3f} "
          f"{spy_oos['cumul']:>10.4f} {spy_oos['maxdd']:>8.1%}")

    # ── Weight evolution ──────────────────────────────────────────────────────
    oos_weights = weights_df[(weights_df.index >= OOS_START) & (weights_df.index <= OOS_END)]
    if len(oos_weights) > 0:
        print("\n=== HRP weights (OOS average) ===")
        avg_w = oos_weights.mean()
        print(f"  Avg w(S1 Momentum):  {avg_w['w_S1']:.1%}")
        print(f"  Avg w(S2 Low-Vol):   {avg_w['w_S2']:.1%}")
        print(f"  Avg w(S3 TOM):       {avg_w['w_S3']:.1%}")

    # ── Also test equal-weight blend as comparison ────────────────────────────
    eq_df = pd.concat([s1.rename("S1"), s2.rename("S2"), s3.rename("S3")], axis=1).dropna()
    eq_blend = eq_df.mean(axis=1)
    eq_is  = eval_period(eq_blend, IS_START, IS_END)
    eq_oos = eval_period(eq_blend, OOS_START, OOS_END)
    print(f"  {'Equal-weight 1/3 blend':<28} {eq_is['sharpe']:>10.3f} {eq_oos['sharpe']:>10.3f} "
          f"{eq_oos['cumul']:>10.4f} {eq_oos['maxdd']:>8.1%}")

    # ── Verdict ───────────────────────────────────────────────────────────────
    h192d_sharpe = 1.367  # best single strategy (BAB sector-neutral, not included in blend)
    confirm_threshold = 1.2
    confirmed = blend_oos["sharpe"] > confirm_threshold and blend_oos["maxdd"] > -0.20

    print(f"\n=== Verdict ===")
    print(f"Confirm criteria: OOS Sharpe > {confirm_threshold} AND MaxDD > -20%")
    print(f"Blend OOS Sharpe: {blend_oos['sharpe']:.3f}, MaxDD: {blend_oos['maxdd']:.1%}")
    print(f"Result: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"Note: H192-D BAB (best single, not blended here) = {h192d_sharpe:.3f}")

    # ── Save ──────────────────────────────────────────────────────────────────
    oos_weights_avg = {}
    if len(oos_weights) > 0:
        avg = oos_weights.mean()
        oos_weights_avg = {"w_S1": round(float(avg["w_S1"]), 3),
                           "w_S2": round(float(avg["w_S2"]), 3),
                           "w_S3": round(float(avg["w_S3"]), 3)}

    out = {
        "hypothesis": "H203",
        "description": "HRP blend: S1=6-1m MOM, S2=Hybrid LowVol, S3=TOM",
        "strategies": {k: {"label": v["label"], "is": v["is"], "oos": v["oos"]}
                       for k, v in standalone.items()},
        "hrp_blend": {"is": blend_is, "oos": blend_oos,
                      "oos_avg_weights": oos_weights_avg},
        "equal_weight": {"is": eq_is, "oos": eq_oos},
        "spy_oos": spy_oos,
        "confirm_threshold": confirm_threshold,
        "confirmed": confirmed,
        "oos_corr": oos_df.corr().round(3).to_dict() if len(oos_df) > 0 else {},
    }
    outpath = RESULT_DIR / "h203_hrp_blend.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
