"""
H152 — ETF Pairs Trading: GDX/SIL Cointegration + OLS Spread Backtest
======================================================================

First test of the ETF pairs trading strategy family (H152+).
Implements the methodology documented in wiki/trading/algorithms/pairs-trading.md.

Pair: GDX (VanEck Gold Miners) / SIL (Global X Silver Miners)
Economic link: Both track precious metal miners — share underlying metal prices,
  royalty economics, and cost-of-production dynamics. Not perfectly correlated
  because gold/silver ratio varies, but structurally cointegrated.

Test design:
  Data     : 2010-01-01 to 2026-04-30 (daily close prices)
  IS       : 2010-01-01 to 2017-12-31 (training / cointegration confirmation)
  OOS      : 2018-01-01 to 2026-04-30 (test period; aligned with H026 OOS)
  Method   : OLS hedge ratio on rolling 252-day window (walk-forward)
  Signals  : z-score of spread; entry ±2σ, exit ±0.5σ, stop ±4σ
  Costs    : 0.05% round-trip per trade (conservative for ETFs)

Success criteria (new strategy family):
  - OOS Sharpe > 1.0
  - OOS cumulative return > SPY in same period
  - MaxDD < 25%
  - Monthly return correlation with H026 < 0.5

If standalone criteria met → run H153 (XLE/OIH pair) and H154 (Kalman filter).

H026 context: production is 100% H026 with OOS 382x cumulative. A pairs strategy
must justify displacing part of H026's budget — correlation check is critical.
Market-neutral structure means near-zero correlation is expected by design.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from statsmodels.tsa.stattools import coint, adfuller
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2010-01-01"
FULL_END   = "2026-04-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

# GDX/SIL pair
PAIR = ("GDX", "SIL")    # X = GDX (base), Y = SIL (dependent in OLS: Y = β*X + α + ε)

# Backtest parameters
ROLL_WINDOW   = 252    # days for rolling OLS hedge ratio
ZSCORE_LB     = 60     # lookback for z-score mean/std
ENTRY_Z       = 2.0    # enter when |z| > ENTRY_Z
EXIT_Z        = 0.5    # exit when |z| < EXIT_Z
STOP_Z        = 4.0    # stop-loss when |z| > STOP_Z
COST_RT       = 0.0005  # 0.05% round-trip cost (one side = 0.025%)

H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]

_PREFIXES = [f"h{i:03d}" for i in range(62, 153)]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h152_{ticker}_close_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def load_pair(start=FULL_START, end=FULL_END):
    x_ticker, y_ticker = PAIR
    px = fetch_daily_close(x_ticker, start, end)
    py = fetch_daily_close(y_ticker, start, end)
    df = pd.concat([px, py], axis=1).dropna()
    df.columns = ["X", "Y"]
    return df


def load_spy(start=FULL_START, end=FULL_END):
    return fetch_daily_close("SPY", start, end)


def load_h026_monthly(start=FULL_START, end=FULL_END):
    """Load H026-like monthly returns for correlation check."""
    prices = {}
    for t in H026_ASSETS:
        try:
            prices[t] = fetch_daily_close(t, start, end)
        except Exception:
            pass
    daily_df   = pd.DataFrame(prices).sort_index()
    monthly_px = daily_df.resample("ME").last()
    monthly_rt = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    RANKING_ASSETS = [a for a in H026_ASSETS if a != "BIL"]
    TSMOM_THRESHOLD = 0.05

    rets = []
    for i in range(13, len(monthly_px)):
        vol_6  = monthly_rt.rolling(6).std().iloc[i] * np.sqrt(12)
        mom_12 = (monthly_px.iloc[i] / monthly_px.iloc[i-12] - 1)
        mom_6  = (monthly_px.iloc[i] / monthly_px.iloc[i-6]  - 1)
        mom_3  = (monthly_px.iloc[i] / monthly_px.iloc[i-3]  - 1)
        passing = [t for t in RANKING_ASSETS
                   if t in mom_12.index and not np.isnan(float(mom_12[t]))
                   and float(mom_12[t]) > TSMOM_THRESHOLD]
        if not passing:
            top = "BIL"
        else:
            score = (mom_12.reindex(passing).rank() +
                     mom_6.reindex(passing).rank()  +
                     mom_3.reindex(passing).rank()  +
                     vol_6.reindex(passing).rank(ascending=False))
            top = score.idxmax()
        rets.append(float(monthly_rt.iloc[i][top]))
    return pd.Series(rets, index=monthly_px.index[13:], name="H026")


# ─────────────────────────────────────────────────────────────────────────────
# Cointegration tests
# ─────────────────────────────────────────────────────────────────────────────

def test_cointegration(prices: pd.DataFrame, label=""):
    """Run Engle-Granger cointegration test and ADF on individual series."""
    x, y = prices["X"], prices["Y"]

    # ADF on individual series (should be non-stationary)
    adf_x = adfuller(x.dropna(), autolag="AIC")
    adf_y = adfuller(y.dropna(), autolag="AIC")

    # Engle-Granger cointegration
    stat, pvalue, critical_values = coint(x, y)

    return {
        "label":      label,
        "n_obs":      len(prices),
        "start":      prices.index[0].strftime("%Y-%m-%d"),
        "end":        prices.index[-1].strftime("%Y-%m-%d"),
        "coint_stat": float(stat),
        "coint_pval": float(pvalue),
        "coint_cv1":  float(critical_values[0]),  # 1%
        "coint_cv5":  float(critical_values[1]),  # 5%
        "coint_cv10": float(critical_values[2]),  # 10%
        "adf_pval_x": float(adf_x[1]),
        "adf_pval_y": float(adf_y[1]),
        "cointegrated_5pct": bool(pvalue < 0.05),
        "cointegrated_1pct": bool(pvalue < 0.01),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Hedge ratio and spread
# ─────────────────────────────────────────────────────────────────────────────

def compute_ols_beta(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """Estimate OLS hedge ratio β: Y = β*X + α + ε. Returns (β, α)."""
    X_mat = add_constant(x)
    res = OLS(y, X_mat).fit()
    return float(res.params.iloc[1]), float(res.params.iloc[0])


def compute_rolling_spread(prices: pd.DataFrame, window=ROLL_WINDOW,
                            zscore_lb=ZSCORE_LB) -> pd.DataFrame:
    """
    Walk-forward rolling OLS spread.
    At each day i, fit OLS on [i-window, i-1] (strictly past data).
    Spread = Y - β*X - α (using past-fit β and α).
    Z-score = (spread - rolling mean) / rolling std (rolling window of zscore_lb days).
    """
    x = prices["X"]
    y = prices["Y"]

    betas      = np.full(len(prices), np.nan)
    alphas     = np.full(len(prices), np.nan)
    spreads    = np.full(len(prices), np.nan)

    for i in range(window, len(prices)):
        x_train = x.iloc[i - window : i]
        y_train = y.iloc[i - window : i]
        b, a = compute_ols_beta(x_train, y_train)
        betas[i]   = b
        alphas[i]  = a
        spreads[i] = float(y.iloc[i]) - b * float(x.iloc[i]) - a

    spread_series = pd.Series(spreads, index=prices.index, name="spread")
    beta_series   = pd.Series(betas,   index=prices.index, name="beta")
    alpha_series  = pd.Series(alphas,  index=prices.index, name="alpha")

    spread_mean = spread_series.rolling(zscore_lb).mean()
    spread_std  = spread_series.rolling(zscore_lb).std()
    z_score     = (spread_series - spread_mean) / spread_std

    return pd.DataFrame({
        "X":       x,
        "Y":       y,
        "beta":    beta_series,
        "alpha":   alpha_series,
        "spread":  spread_series,
        "z_score": z_score.rename("z_score"),
    })


def compute_halflife(spread: pd.Series) -> float:
    """OU half-life from AR(1) on spread: half_life = ln(2) / (-θ)."""
    spread_clean = spread.dropna()
    spread_lag  = spread_clean.shift(1).dropna()
    spread_diff = spread_clean.diff().dropna()
    aligned = pd.concat([spread_diff, spread_lag], axis=1).dropna()
    aligned.columns = ["diff", "lag"]
    if len(aligned) < 30:
        return np.nan
    res = OLS(aligned["diff"], add_constant(aligned["lag"])).fit()
    theta = float(res.params["lag"])
    if theta >= 0:
        return np.nan
    return float(np.log(2) / (-theta))


# ─────────────────────────────────────────────────────────────────────────────
# Signal generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_signals(z: pd.Series,
                     entry_z=ENTRY_Z, exit_z=EXIT_Z, stop_z=STOP_Z) -> pd.Series:
    """
    Returns position series: +1 (long spread), -1 (short spread), 0 (flat).
    Long spread = long Y, short X (when z < -ENTRY_Z, spread is below mean).
    Short spread = short Y, long X (when z > +ENTRY_Z, spread is above mean).
    """
    pos = np.zeros(len(z))
    current = 0

    for i in range(1, len(z)):
        zval = z.iloc[i]
        if np.isnan(zval):
            pos[i] = 0
            current = 0
            continue

        if current == 0:
            # No position — check for entry
            if zval < -entry_z:
                current = 1    # long spread (z too low, expect reversion up)
            elif zval > entry_z:
                current = -1   # short spread (z too high, expect reversion down)
        elif current == 1:
            # Long spread — exit when z reverts near mean or hits stop
            if zval > -exit_z or abs(zval) > stop_z:
                current = 0
        elif current == -1:
            # Short spread — exit when z reverts near mean or hits stop
            if zval < exit_z or abs(zval) > stop_z:
                current = 0

        pos[i] = current

    return pd.Series(pos, index=z.index, name="position")


# ─────────────────────────────────────────────────────────────────────────────
# Backtest engine
# ─────────────────────────────────────────────────────────────────────────────

def backtest_pair(spread_df: pd.DataFrame, positions: pd.Series,
                  cost_rt=COST_RT) -> pd.Series:
    """
    Daily P&L from pairs position.

    Long spread (pos=+1): long Y, short X with hedge ratio β
      Daily P&L = ΔY - β * ΔX  (proportional to one unit of Y vs β units of X)
    Short spread (pos=-1): short Y, long X
      Daily P&L = -(ΔY - β * ΔX)

    Normalized by initial equity; expressed as daily returns.
    Position changes incur round-trip cost on the smaller leg.
    """
    x = spread_df["X"]
    y = spread_df["Y"]
    beta = spread_df["beta"]

    x_ret = x.pct_change()
    y_ret = y.pct_change()

    # Hedge ratio normalizes: one unit of Y, β units of X
    # spread_ret = return of long Y - return of (β * X) position
    spread_ret = y_ret - beta.shift(1) * x_ret

    pos_prev = positions.shift(1).fillna(0)
    trade_flag = (positions != pos_prev).astype(float)
    cost_series = trade_flag * cost_rt

    strategy_ret = positions.shift(1) * spread_ret - cost_series
    strategy_ret = strategy_ret.fillna(0)

    return strategy_ret.rename("strategy")


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def stats_daily(r: pd.Series) -> dict:
    r = r.dropna()
    eq   = (1 + r).cumprod()
    cagr = float(eq.iloc[-1]) ** (252 / len(r)) - 1
    vol  = r.std(ddof=1) * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0.0
    rolling_max = eq.expanding().max()
    drawdown    = (eq / rolling_max - 1)
    max_dd = float(drawdown.min())
    annual_ret = r.resample("YE").apply(lambda x: (1+x).prod()-1)
    neg_yrs = int(annual_ret.lt(0).sum())
    trades  = int((r != 0).sum())
    return {
        "cumul":    float(eq.iloc[-1]),
        "cagr":     cagr,
        "vol":      vol,
        "sharpe":   sharpe,
        "max_dd":   max_dd,
        "neg_yrs":  neg_yrs,
        "trades":   trades,
    }


def stats_monthly(r_daily: pd.Series) -> pd.Series:
    return r_daily.resample("ME").apply(lambda x: (1+x).prod()-1)


def correlation_vs(r1_monthly: pd.Series, r2_monthly: pd.Series,
                   start=None, end=None) -> float:
    if start:
        r1_monthly = r1_monthly[r1_monthly.index >= start]
        r2_monthly = r2_monthly[r2_monthly.index >= start]
    if end:
        r1_monthly = r1_monthly[r1_monthly.index <= end]
        r2_monthly = r2_monthly[r2_monthly.index <= end]
    aligned = pd.concat([r1_monthly, r2_monthly], axis=1).dropna()
    if len(aligned) < 12:
        return np.nan
    return float(aligned.corr().iloc[0, 1])


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    x_ticker, y_ticker = PAIR
    print(f"\nH152 — ETF Pairs Trading: {x_ticker}/{y_ticker}")
    print("=" * 60)

    # 1. Load data
    print("\n[1] Loading price data…")
    prices = load_pair()
    spy    = load_spy()
    print(f"    {x_ticker}: {len(prices)} days  ({prices.index[0].date()} → {prices.index[-1].date()})")
    print(f"    {y_ticker}: (same)")

    # 2. Cointegration tests
    print("\n[2] Cointegration tests (Engle-Granger)…")

    # Full period
    ct_full = test_cointegration(prices, label="Full (2010–2026)")
    # Sub-periods for stability check
    ct_is   = test_cointegration(prices[prices.index <= IS_END], label="IS (2010–2017)")
    ct_oos  = test_cointegration(prices[prices.index >= OOS_START], label="OOS (2018–2026)")

    for ct in [ct_full, ct_is, ct_oos]:
        verdict = "COINTEGRATED" if ct["cointegrated_5pct"] else "NOT cointegrated"
        pval_flag = "***" if ct["cointegrated_1pct"] else ("**" if ct["cointegrated_5pct"] else "")
        print(f"\n  {ct['label']:25s}  n={ct['n_obs']:4d}  "
              f"p={ct['coint_pval']:.4f}{pval_flag:3s}  "
              f"stat={ct['coint_stat']:.2f}  cv5%={ct['coint_cv5']:.2f}  "
              f"→ {verdict}")
        print(f"    ADF p-values:  {x_ticker}={ct['adf_pval_x']:.4f}  {y_ticker}={ct['adf_pval_y']:.4f}")

    if not ct_full["cointegrated_5pct"]:
        print("\n  ⚠ Full-period cointegration FAILS at 5%. Continuing for diagnostic purposes.")
    if not ct_oos["cointegrated_5pct"]:
        print("  ⚠ OOS cointegration FAILS — pair may have broken down. Results are informational only.")

    # 3. Full-sample OLS (for reference — NOT used in backtest)
    print(f"\n[3] Full-sample OLS hedge ratio (reference only, NOT used in backtest)…")
    b_full, a_full = compute_ols_beta(prices["X"], prices["Y"])
    spread_static = prices["Y"] - b_full * prices["X"] - a_full
    hl_static = compute_halflife(spread_static)
    print(f"    β = {b_full:.4f}  α = {a_full:.4f}")
    print(f"    Full-sample spread half-life: {hl_static:.1f} trading days")

    # 4. Walk-forward rolling spread (backtest-safe)
    print(f"\n[4] Computing rolling OLS spread (window={ROLL_WINDOW}d, z_lb={ZSCORE_LB}d)…")
    spread_df = compute_rolling_spread(prices)

    # Half-life on rolling spread (OOS section)
    oos_spread = spread_df.loc[spread_df.index >= OOS_START, "spread"]
    hl_oos = compute_halflife(oos_spread)
    is_spread  = spread_df.loc[spread_df.index <= IS_END, "spread"]
    hl_is  = compute_halflife(is_spread)
    print(f"    Half-life — IS: {hl_is:.1f}d  OOS: {hl_oos:.1f}d")
    print(f"    (Lookback recommendation: {ZSCORE_LB}d ≈ 2–4× half-life if HL ≈ 15–30d)")

    # 5. Signals
    print(f"\n[5] Generating signals (entry ±{ENTRY_Z}σ, exit ±{EXIT_Z}σ, stop ±{STOP_Z}σ)…")
    z_oos  = spread_df.loc[spread_df.index >= OOS_START, "z_score"]
    z_full = spread_df["z_score"]

    pos_oos  = generate_signals(z_oos)
    pos_full = generate_signals(z_full)

    n_long  = int((pos_oos == 1).sum())
    n_short = int((pos_oos == -1).sum())
    n_flat  = int((pos_oos == 0).sum())
    total   = len(pos_oos)
    trades  = int((pos_oos.diff().abs() > 0).sum())
    print(f"    OOS: long={n_long}d ({n_long/total*100:.1f}%)  short={n_short}d ({n_short/total*100:.1f}%)  flat={n_flat}d ({n_flat/total*100:.1f}%)")
    print(f"    OOS: {trades} direction changes (≈ {trades//2} round trips)")

    # 6. Backtest
    print(f"\n[6] Backtesting…")
    strat_full = backtest_pair(spread_df, pos_full)
    strat_oos  = strat_full[strat_full.index >= OOS_START]
    strat_is   = strat_full[(strat_full.index >= "2011-01-01") & (strat_full.index <= IS_END)]
    strat_alt  = strat_full[strat_full.index >= ALT_OOS_ST]

    # SPY returns for comparison
    spy_ret  = spy.pct_change().dropna()
    spy_oos  = spy_ret[spy_ret.index >= OOS_START]
    spy_is   = spy_ret[(spy_ret.index >= "2011-01-01") & (spy_ret.index <= IS_END)]
    spy_alt  = spy_ret[spy_ret.index >= ALT_OOS_ST]

    s_oos    = stats_daily(strat_oos)
    s_is     = stats_daily(strat_is)
    s_alt    = stats_daily(strat_alt)
    spy_s_oos = stats_daily(spy_oos)

    print(f"\n  Results summary:")
    print(f"  {'':32s}  {'IS (2011-17)':>14s}  {'OOS (2018+)':>14s}  {'AltOOS (2013+)':>14s}")
    print(f"  {'Cumulative return':32s}  {s_is['cumul']:>14.4f}  {s_oos['cumul']:>14.4f}  {s_alt['cumul']:>14.4f}")
    print(f"  {'CAGR':32s}  {s_is['cagr']:>14.2%}  {s_oos['cagr']:>14.2%}  {s_alt['cagr']:>14.2%}")
    print(f"  {'Annualized vol':32s}  {s_is['vol']:>14.2%}  {s_oos['vol']:>14.2%}  {s_alt['vol']:>14.2%}")
    print(f"  {'Sharpe':32s}  {s_is['sharpe']:>14.3f}  {s_oos['sharpe']:>14.3f}  {s_alt['sharpe']:>14.3f}")
    print(f"  {'Max drawdown':32s}  {s_is['max_dd']:>14.2%}  {s_oos['max_dd']:>14.2%}  {s_alt['max_dd']:>14.2%}")
    print(f"  {'Negative years':32s}  {s_is['neg_yrs']:>14d}  {s_oos['neg_yrs']:>14d}  {s_alt['neg_yrs']:>14d}")
    print(f"\n  SPY (OOS) for comparison:")
    print(f"  {'Cumulative return':32s}  {'':14s}  {spy_s_oos['cumul']:>14.4f}")
    print(f"  {'CAGR':32s}  {'':14s}  {spy_s_oos['cagr']:>14.2%}")
    print(f"  {'Sharpe':32s}  {'':14s}  {spy_s_oos['sharpe']:>14.3f}")

    # 7. Correlation with H026
    print(f"\n[7] Correlation with H026 momentum strategy…")
    print(f"    (Loading H026 monthly returns — takes ~30s)")
    try:
        h026_monthly = load_h026_monthly()
        strat_monthly_oos = stats_monthly(strat_oos)
        strat_monthly_alt = stats_monthly(strat_alt)
        corr_oos = correlation_vs(strat_monthly_oos, h026_monthly, start=OOS_START)
        corr_alt = correlation_vs(strat_monthly_alt, h026_monthly, start=ALT_OOS_ST)
        print(f"    OOS corr(H152, H026) = {corr_oos:+.3f}")
        print(f"    AltOOS corr          = {corr_alt:+.3f}")
        if abs(corr_oos) < 0.3:
            print(f"    ✓ Near-zero correlation — diversification potential confirmed")
        elif abs(corr_oos) < 0.5:
            print(f"    ~ Moderate correlation — diversification limited")
        else:
            print(f"    ✗ High correlation — pairs strategy not adding independent alpha")
    except Exception as e:
        print(f"    Could not compute H026 correlation: {e}")
        corr_oos = np.nan
        corr_alt = np.nan

    # 8. Verdict
    print(f"\n[8] Verdict:")
    oos_beats_spy = s_oos["cumul"] > spy_s_oos["cumul"]
    oos_sharpe_ok = s_oos["sharpe"] > 1.0
    oos_dd_ok     = s_oos["max_dd"] > -0.25
    oos_coint_ok  = ct_oos["cointegrated_5pct"]

    checks = [
        (oos_coint_ok,    "OOS cointegration p < 5%"),
        (oos_sharpe_ok,   f"OOS Sharpe > 1.0 (got {s_oos['sharpe']:.3f})"),
        (oos_beats_spy,   f"OOS cumul > SPY (got {s_oos['cumul']:.4f} vs SPY {spy_s_oos['cumul']:.4f})"),
        (oos_dd_ok,       f"OOS MaxDD > -25% (got {s_oos['max_dd']:.2%})"),
    ]

    passed = sum(1 for c, _ in checks if c)
    for ok, label in checks:
        print(f"    {'✓' if ok else '✗'} {label}")

    if passed == len(checks):
        verdict = "CONFIRMED"
        print(f"\n  H152: {verdict} — all criteria met. Proceed to H153 (XLE/OIH) and H154 (Kalman filter).")
    elif passed >= 3:
        verdict = "PARTIAL"
        print(f"\n  H152: {verdict} — {passed}/{len(checks)} criteria met. Some evidence; not deployment-ready.")
    else:
        verdict = "NOT CONFIRMED"
        print(f"\n  H152: {verdict} — {passed}/{len(checks)} criteria met.")
        if not oos_coint_ok:
            print("        Primary issue: cointegration breaks down in OOS period.")
            print("        Consider testing sub-periods or Kalman filter (H154) before giving up.")

    print(f"\n  Full results saved to {RESULT_DIR}/h152_gdx_sil.txt")

    # 9. Save results
    result_lines = [
        "H152 — GDX/SIL ETF Pairs Trading Backtest",
        "=" * 60,
        "",
        f"Pair: {x_ticker} (X) / {y_ticker} (Y)",
        f"Data: {prices.index[0].date()} → {prices.index[-1].date()}  ({len(prices)} trading days)",
        "",
        "COINTEGRATION",
        f"  Full period: p={ct_full['coint_pval']:.4f}  {'cointegrated' if ct_full['cointegrated_5pct'] else 'NOT cointegrated'}",
        f"  IS (2010-17): p={ct_is['coint_pval']:.4f}  {'cointegrated' if ct_is['cointegrated_5pct'] else 'NOT cointegrated'}",
        f"  OOS (2018+):  p={ct_oos['coint_pval']:.4f}  {'cointegrated' if ct_oos['cointegrated_5pct'] else 'NOT cointegrated'}",
        "",
        f"HEDGE RATIO (full-sample OLS, reference): β={b_full:.4f}  α={a_full:.4f}",
        f"HALF-LIFE: IS={hl_is:.1f}d  OOS={hl_oos:.1f}d",
        "",
        "BACKTEST PERFORMANCE",
        f"  {'':28s}  IS (2011-17)   OOS (2018+)   AltOOS (2013+)",
        f"  {'Cumul return':28s}  {s_is['cumul']:>12.4f}  {s_oos['cumul']:>12.4f}  {s_alt['cumul']:>12.4f}",
        f"  {'CAGR':28s}  {s_is['cagr']:>12.2%}  {s_oos['cagr']:>12.2%}  {s_alt['cagr']:>12.2%}",
        f"  {'Annualized vol':28s}  {s_is['vol']:>12.2%}  {s_oos['vol']:>12.2%}  {s_alt['vol']:>12.2%}",
        f"  {'Sharpe':28s}  {s_is['sharpe']:>12.3f}  {s_oos['sharpe']:>12.3f}  {s_alt['sharpe']:>12.3f}",
        f"  {'Max drawdown':28s}  {s_is['max_dd']:>12.2%}  {s_oos['max_dd']:>12.2%}  {s_alt['max_dd']:>12.2%}",
        f"  {'Negative years':28s}  {s_is['neg_yrs']:>12d}  {s_oos['neg_yrs']:>12d}  {s_alt['neg_yrs']:>12d}",
        "",
        f"SPY OOS: cumul={spy_s_oos['cumul']:.4f}  CAGR={spy_s_oos['cagr']:.2%}  Sharpe={spy_s_oos['sharpe']:.3f}",
        "",
        f"CORRELATION WITH H026",
        f"  OOS:    {corr_oos:+.3f}",
        f"  AltOOS: {corr_alt:+.3f}",
        "",
        f"VERDICT: {verdict}",
        f"Checks passed: {passed}/{len(checks)}",
    ]
    (RESULT_DIR / "h152_gdx_sil.txt").write_text("\n".join(result_lines))


if __name__ == "__main__":
    main()
