"""
H153 — ETF Pairs Trading: XLE/OIH
===================================

Energy sector pair: XLE (SPDR Energy Select Sector, broad E&P) vs OIH (VanEck Oil Services ETF).
Economic link: oil services companies (OIH) depend on exploration/production capex from companies
in XLE — when XLE outperforms, E&P capex rises, lifting oil services.

CAVEAT documented in pairs-trading.md: OIH composition changed 2020-2022 (SLB/HAL lost weight,
newer names added). Testing whether the relationship held through this disruption.

Data note: Current OIH (VanEck relaunched) starts 2011-12-20.

Method: Same as H152 — rolling OLS hedge ratio (252d window), z-score (60d), entry ±2σ, exit ±0.5σ.
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

PAIR      = ("XLE", "OIH")
FULL_START = "2012-01-01"   # OIH relaunched Dec 2011; start 2012 for clean year
FULL_END   = "2026-04-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

ROLL_WINDOW = 252
ZSCORE_LB   = 60
ENTRY_Z     = 2.0
EXIT_Z      = 0.5
STOP_Z      = 4.0
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
    cp = CACHE_DIR / f"h153_{ticker}_close_{start}_{end}.parquet"
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


def compute_rolling_spread(prices, window=ROLL_WINDOW, zscore_lb=ZSCORE_LB):
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


def generate_signals(z, entry_z=ENTRY_Z, exit_z=EXIT_Z, stop_z=STOP_Z):
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


def main():
    xt, yt = PAIR
    print(f"\nH153 — ETF Pairs Trading: {xt}/{yt}")
    print("=" * 60)

    print(f"\n[1] Loading price data…")
    px = fetch_daily_close(xt, FULL_START, FULL_END)
    py = fetch_daily_close(yt, FULL_START, FULL_END)
    prices = pd.concat([px, py], axis=1).dropna()
    prices.columns = ["X","Y"]
    spy = fetch_daily_close("SPY", FULL_START, FULL_END)
    print(f"    {xt}: {len(prices)} days  ({prices.index[0].date()} → {prices.index[-1].date()})")

    print(f"\n[2] Cointegration tests…")
    for label, sub in [("Full (2012–2026)", prices),
                        ("IS (2012–2017)",   prices[prices.index <= IS_END]),
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

    print(f"\n[3] Rolling OLS spread (window={ROLL_WINDOW}d, z_lb={ZSCORE_LB}d)…")
    spread_df = compute_rolling_spread(prices)
    hl_is  = compute_halflife(spread_df.loc[spread_df.index<=IS_END,"spread"])
    hl_oos = compute_halflife(spread_df.loc[spread_df.index>=OOS_START,"spread"])
    b_full,_ = compute_ols_beta(prices["X"], prices["Y"])
    print(f"    Full-sample β={b_full:.4f}  |  Half-life IS={hl_is:.1f}d  OOS={hl_oos:.1f}d")

    print(f"\n[4] Generating signals…")
    pos_full = generate_signals(spread_df["z_score"])
    pos_oos  = pos_full[pos_full.index >= OOS_START]
    n_long = int((pos_oos==1).sum()); n_short = int((pos_oos==-1).sum())
    total  = len(pos_oos); trades = int((pos_oos.diff().abs()>0).sum())
    print(f"    OOS: long={n_long}d ({n_long/total*100:.1f}%)  "
          f"short={n_short}d ({n_short/total*100:.1f}%)  flat={total-n_long-n_short}d  "
          f"{trades} direction changes")

    print(f"\n[5] Backtesting…")
    strat_full = backtest_pair(spread_df, pos_full)
    s_oos  = stats_daily(strat_full[strat_full.index >= OOS_START])
    s_is   = stats_daily(strat_full[(strat_full.index>="2013-01-01")&(strat_full.index<=IS_END)])
    s_alt  = stats_daily(strat_full[strat_full.index >= ALT_OOS_ST])
    spy_ret = spy.pct_change().dropna()
    s_spy  = stats_daily(spy_ret[spy_ret.index >= OOS_START])

    print(f"\n  {'':30s}  {'IS (2013-17)':>13s}  {'OOS (2018+)':>13s}  {'AltOOS (2013+)':>14s}")
    for k,label in [("cumul","Cumul"),("cagr","CAGR"),("sharpe","Sharpe"),
                    ("max_dd","MaxDD"),("neg_yrs","NegYrs")]:
        vi, vo, va = s_is[k], s_oos[k], s_alt[k]
        fmt = ".4f" if k=="cumul" else ".3f" if k=="sharpe" else ".2%" if k in ("cagr","vol","max_dd") else "d"
        print(f"  {label:30s}  {vi:>13{fmt}}  {vo:>13{fmt}}  {va:>14{fmt}}")
    print(f"\n  SPY OOS: cumul={s_spy['cumul']:.4f}  CAGR={s_spy['cagr']:.2%}  Sharpe={s_spy['sharpe']:.3f}")

    print(f"\n[6] Verdict:")
    checks = [
        (oos_coint,              "OOS cointegration p < 5%"),
        (s_oos["sharpe"] > 1.0,  f"OOS Sharpe > 1.0 (got {s_oos['sharpe']:.3f})"),
        (s_oos["cumul"] > s_spy["cumul"], f"OOS cumul > SPY ({s_oos['cumul']:.4f} vs {s_spy['cumul']:.4f})"),
        (s_oos["max_dd"] > -0.25, f"OOS MaxDD > -25% (got {s_oos['max_dd']:.2%})"),
    ]
    passed = sum(1 for c,_ in checks if c)
    for ok, label in checks:
        print(f"    {'✓' if ok else '✗'} {label}")
    verdict = "CONFIRMED" if passed==4 else "PARTIAL" if passed>=3 else "NOT CONFIRMED"
    print(f"\n  H153: {verdict} ({passed}/4 criteria)")

    lines = [f"H153 — {xt}/{yt} ETF Pairs Trading", "="*60, "",
             f"Full-sample β={b_full:.4f}", f"Half-life IS={hl_is:.1f}d OOS={hl_oos:.1f}d", "",
             "PERFORMANCE", f"  IS(2013-17): cumul={s_is['cumul']:.4f} CAGR={s_is['cagr']:.2%} "
             f"Sharpe={s_is['sharpe']:.3f} MaxDD={s_is['max_dd']:.2%} NegYrs={s_is['neg_yrs']}",
             f"  OOS(2018+): cumul={s_oos['cumul']:.4f} CAGR={s_oos['cagr']:.2%} "
             f"Sharpe={s_oos['sharpe']:.3f} MaxDD={s_oos['max_dd']:.2%} NegYrs={s_oos['neg_yrs']}",
             f"  AltOOS: cumul={s_alt['cumul']:.4f} Sharpe={s_alt['sharpe']:.3f}",
             f"  SPY OOS: cumul={s_spy['cumul']:.4f} CAGR={s_spy['cagr']:.2%}",
             "", f"VERDICT: {verdict} ({passed}/4)"]
    (RESULT_DIR / "h153_xle_oih.txt").write_text("\n".join(lines))
    return verdict, s_oos, s_spy


if __name__ == "__main__":
    main()
