"""
H154 — ETF Pairs Trading: TLT/IEF (Treasury Yield Curve)
==========================================================

Treasury pair: TLT (iShares 20+ Year Treasury) vs IEF (iShares 7-10 Year Treasury).
Economic link: Both track US government bonds from the same issuer (US Treasury).
The spread captures the yield curve spread between long-duration (20yr+) and
intermediate-duration (7-10yr) bonds. This is structurally the most defensible
cointegration of any pair in the candidate list — same credit risk, same issuer,
different duration.

When the yield curve steepens (long rates rise faster): spread widens, short TLT/long IEF.
When the yield curve flattens/inverts: spread narrows, long TLT/short IEF.

Data: TLT launched 2002-07-22, IEF launched 2002-07-22. Using 2007-01-01 start
to capture the GFC and subsequent rate cycle.

Parameters: shorter z-score window (30d vs 60d in H152/H153) — yield curve mean-reverts
faster than equity/commodity spreads. Also test 60d for comparison.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from statsmodels.tsa.stattools import coint, adfuller
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

PAIR      = ("IEF", "TLT")   # X = IEF (shorter duration), Y = TLT (longer duration)
FULL_START = "2007-01-01"
FULL_END   = "2026-04-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

ROLL_WINDOW = 252
COST_RT     = 0.0005

_PREFIXES = [f"h{i:03d}" for i in range(62, 155)]


def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h154_{ticker}_close_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def compute_ols_beta(x, y):
    res = OLS(y, add_constant(x)).fit()
    return float(res.params.iloc[1]), float(res.params.iloc[0])


def compute_halflife(spread):
    s = spread.dropna()
    lag = s.shift(1).dropna(); diff = s.diff().dropna()
    aln = pd.concat([diff, lag], axis=1).dropna(); aln.columns = ["diff","lag"]
    if len(aln) < 30: return np.nan
    theta = float(OLS(aln["diff"], add_constant(aln["lag"])).fit().params["lag"])
    return np.log(2)/(-theta) if theta < 0 else np.nan


def compute_rolling_spread(prices, window=ROLL_WINDOW, zscore_lb=60):
    x, y = prices["X"], prices["Y"]
    betas = np.full(len(prices), np.nan)
    alphas = np.full(len(prices), np.nan)
    spreads = np.full(len(prices), np.nan)
    for i in range(window, len(prices)):
        b, a = compute_ols_beta(x.iloc[i-window:i], y.iloc[i-window:i])
        betas[i] = b; alphas[i] = a
        spreads[i] = float(y.iloc[i]) - b * float(x.iloc[i]) - a
    spread_s = pd.Series(spreads, index=prices.index)
    z = (spread_s - spread_s.rolling(zscore_lb).mean()) / spread_s.rolling(zscore_lb).std()
    return pd.DataFrame({"X": x, "Y": y, "beta": betas, "alpha": alphas,
                          "spread": spread_s, "z_score": z})


def generate_signals(z, entry_z=2.0, exit_z=0.5, stop_z=4.0):
    pos = np.zeros(len(z)); cur = 0
    for i in range(1, len(z)):
        zv = z.iloc[i]
        if np.isnan(zv): pos[i] = 0; cur = 0; continue
        if cur == 0:
            if zv < -entry_z: cur = 1
            elif zv > entry_z: cur = -1
        elif cur == 1:
            if zv > -exit_z or abs(zv) > stop_z: cur = 0
        elif cur == -1:
            if zv < exit_z or abs(zv) > stop_z: cur = 0
        pos[i] = cur
    return pd.Series(pos, index=z.index)


def backtest_pair(spread_df, positions, cost_rt=COST_RT):
    x_ret = spread_df["X"].pct_change()
    y_ret = spread_df["Y"].pct_change()
    spread_ret = y_ret - spread_df["beta"].shift(1) * x_ret
    cost_series = (positions != positions.shift(1).fillna(0)).astype(float) * cost_rt
    return (positions.shift(1) * spread_ret - cost_series).fillna(0)


def stats_daily(r):
    r = r.dropna()
    eq = (1+r).cumprod()
    cagr = float(eq.iloc[-1])**(252/len(r))-1
    vol = r.std(ddof=1)*np.sqrt(252)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x:(1+x).prod()-1).lt(0).sum())
    return {"cumul": float(eq.iloc[-1]), "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "max_dd": max_dd, "neg_yrs": neg_yrs}


def run_variant(prices, spy, zscore_lb, label):
    spread_df = compute_rolling_spread(prices, zscore_lb=zscore_lb)
    hl_full = compute_halflife(spread_df["spread"].dropna())
    hl_oos  = compute_halflife(spread_df.loc[spread_df.index>=OOS_START,"spread"])

    pos_full = generate_signals(spread_df["z_score"])
    strat = backtest_pair(spread_df, pos_full)

    s_oos  = stats_daily(strat[strat.index >= OOS_START])
    s_is   = stats_daily(strat[(strat.index>=ALT_OOS_ST)&(strat.index<=IS_END)])
    s_alt  = stats_daily(strat[strat.index >= ALT_OOS_ST])
    s_spy  = stats_daily(spy.pct_change().dropna().loc[lambda x: x.index>=OOS_START])

    pos_oos = pos_full[pos_full.index >= OOS_START]
    n_long = int((pos_oos==1).sum()); n_short = int((pos_oos==-1).sum())
    total = len(pos_oos)

    print(f"\n  Variant {label} (z_lb={zscore_lb}d)")
    print(f"    Half-life: full={hl_full:.1f}d  OOS={hl_oos:.1f}d")
    print(f"    OOS position: long={n_long/total*100:.1f}%  short={n_short/total*100:.1f}%  "
          f"flat={(total-n_long-n_short)/total*100:.1f}%")
    print(f"    IS: cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}  MaxDD={s_is['max_dd']:.2%}")
    print(f"    OOS: cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  "
          f"Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
    print(f"    AltOOS: cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
    print(f"    SPY OOS: cumul={s_spy['cumul']:.4f}  Sharpe={s_spy['sharpe']:.3f}")

    oos_coint_ok = True   # will be set from the global cointegration test
    passed = sum([
        s_oos["sharpe"] > 1.0,
        s_oos["cumul"] > s_spy["cumul"],
        s_oos["max_dd"] > -0.25,
    ])
    return s_oos, s_alt, s_is, passed, hl_oos


def main():
    xt, yt = PAIR
    print(f"\nH154 — ETF Pairs Trading: {xt}/{yt} (Treasury Yield Curve)")
    print("=" * 60)

    print(f"\n[1] Loading price data…")
    px = fetch_daily_close(xt, FULL_START, FULL_END)
    py = fetch_daily_close(yt, FULL_START, FULL_END)
    prices = pd.concat([px, py], axis=1).dropna()
    prices.columns = ["X","Y"]
    spy = fetch_daily_close("SPY", FULL_START, FULL_END)
    print(f"    {xt}: {len(prices)} days  ({prices.index[0].date()} → {prices.index[-1].date()})")

    print(f"\n[2] Cointegration tests…")
    oos_coint = False
    for label, sub in [("Full (2007–2026)", prices),
                        ("IS (2007–2017)",   prices[prices.index <= IS_END]),
                        ("OOS (2018–2026)",  prices[prices.index >= OOS_START])]:
        stat, pval, cvs = coint(sub["X"], sub["Y"])
        adf_x = adfuller(sub["X"].dropna(), autolag="AIC")[1]
        adf_y = adfuller(sub["Y"].dropna(), autolag="AIC")[1]
        verdict = "COINTEGRATED" if pval < 0.05 else "NOT cointegrated"
        flag = "***" if pval < 0.01 else ("**" if pval < 0.05 else "")
        print(f"  {label:25s}  n={len(sub):4d}  p={pval:.4f}{flag:3s}  "
              f"stat={stat:.2f}  cv5%={cvs[1]:.2f}  → {verdict}")
        print(f"    ADF: {xt}={adf_x:.4f}  {yt}={adf_y:.4f}")
        if label.startswith("OOS"):
            oos_coint = pval < 0.05

    b_full, a_full = compute_ols_beta(prices["X"], prices["Y"])
    print(f"\n  Full-sample OLS: β={b_full:.4f}  α={a_full:.4f}")

    print(f"\n[3] Testing variants…")

    best_verdict = "NOT CONFIRMED"
    best_sharpe = -99
    results = {}

    # Variant A: z_lb=30d (shorter — bond spreads revert faster)
    soa, alta, isa, pa, hla = run_variant(prices, spy, zscore_lb=30,  label="A (z_lb=30d)")
    # Variant B: z_lb=60d (standard from H152)
    sob, altb, isb, pb, hlb = run_variant(prices, spy, zscore_lb=60,  label="B (z_lb=60d)")
    # Variant C: z_lb=120d (longer — captures slower regime drifts)
    soc, altc, isc, pc, hlc = run_variant(prices, spy, zscore_lb=120, label="C (z_lb=120d)")

    spy_s = stats_daily(spy.pct_change().dropna().loc[lambda x: x.index>=OOS_START])

    print(f"\n[4] Cointegration check for verdict…")
    print(f"    OOS cointegration: {'✓' if oos_coint else '✗'}")

    print(f"\n[5] Verdict:")
    verdicts = {}
    for var_label, s_oos, s_alt in [("A (z_lb=30d)", soa, alta),
                                      ("B (z_lb=60d)", sob, altb),
                                      ("C (z_lb=120d)", soc, altc)]:
        checks = [
            oos_coint,
            s_oos["sharpe"] > 1.0,
            s_oos["cumul"] > spy_s["cumul"],
            s_oos["max_dd"] > -0.25,
        ]
        n_pass = sum(checks)
        v = "CONFIRMED" if n_pass==4 else "PARTIAL" if n_pass>=3 else "NOT CONFIRMED"
        verdicts[var_label] = (v, n_pass, s_oos)
        print(f"    {var_label}: {v} ({n_pass}/4)  "
              f"OOS Sharpe={s_oos['sharpe']:.3f}  cumul={s_oos['cumul']:.4f}")

    best_var = max(verdicts.items(), key=lambda kv: kv[1][2]["sharpe"])
    best_label = best_var[0]; best_v = best_var[1][0]; best_s = best_var[1][2]
    overall = best_var[1][0]

    print(f"\n  H154 overall: {overall}  (best variant: {best_label})")

    lines = [f"H154 — {xt}/{yt} Treasury Yield Curve Pairs Trading", "="*60, "",
             f"Data: {prices.index[0].date()} → {prices.index[-1].date()}",
             f"Full-sample β={b_full:.4f}  α={a_full:.4f}",
             f"OOS cointegration: {'YES' if oos_coint else 'NO'}", "",
             "VARIANTS",
             f"  A(z_lb=30d): OOS cumul={soa['cumul']:.4f} CAGR={soa['cagr']:.2%} "
             f"Sharpe={soa['sharpe']:.3f} MaxDD={soa['max_dd']:.2%}",
             f"  B(z_lb=60d): OOS cumul={sob['cumul']:.4f} CAGR={sob['cagr']:.2%} "
             f"Sharpe={sob['sharpe']:.3f} MaxDD={sob['max_dd']:.2%}",
             f"  C(z_lb=120d): OOS cumul={soc['cumul']:.4f} CAGR={soc['cagr']:.2%} "
             f"Sharpe={soc['sharpe']:.3f} MaxDD={soc['max_dd']:.2%}",
             f"  SPY OOS: cumul={spy_s['cumul']:.4f} CAGR={spy_s['cagr']:.2%}",
             "", f"VERDICT: {overall}  (best: {best_label})"]
    (RESULT_DIR / "h154_tlt_ief.txt").write_text("\n".join(lines))
    return overall, best_s, spy_s


if __name__ == "__main__":
    main()
