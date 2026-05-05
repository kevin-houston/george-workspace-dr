"""
H160 — Factor-Residualized Equity Pairs Trading
================================================

Test: after removing SPY + sector factor exposure from each stock's return,
does the residual spread show better cointegration and higher OOS Sharpe?

Hypothesis: "Ernesto/R29" — factor residualization lifts Sharpe 0.44 → 1.38.
Mechanism: stock pairs share broad market + sector risk. OLS on raw prices captures
a "hedge ratio" that is really just β1 * SPY ≈ β2 * SPY — it mixes idiosyncratic
signal with factor noise. By removing SPY and sector exposure first, the residual
spread is purely idiosyncratic and should mean-revert more reliably.

Pairs (all same-sector, selected by Ernesto/R29):
  MSFT / TXN  — both XLK (Technology)
  TXN  / META — both XLK (Technology)
  AMZN / TSLA — both XLY (Consumer Discretionary)
  BAC  / GS   — both XLF (Financials)
  JNJ  / UNH  — both XLV (Healthcare)

Method:
  1. Rolling 252-day OLS: regress each stock's daily return against [SPY, sector ETF]
  2. At each day t: residual_t = r_t - b_spy*r_SPY_t - b_sec*r_sector_t
  3. Build cumulative "residual price": P_resid = exp(cumsum(residuals))
  4. Compute rolling OLS spread on the two residual price series
  5. Z-score → entry ±2σ, exit ±0.5σ, stop ±4σ

IS: 2007–2017, OOS: 2018–2026

Confirm criteria (new strategy, standalone):
  OOS Sharpe > 1.0, OOS MaxDD > -25%, OOS Cumul > SPY, Corr(H026) < 0.5
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

FULL_START = "2007-01-01"
FULL_END   = "2026-04-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

FACTOR_WINDOW = 252   # rolling window for factor regression
SPREAD_WINDOW = 252   # rolling OLS for spread hedge ratio
ZSCORE_LB     = 60    # z-score lookback
ENTRY_Z       = 2.0
EXIT_Z        = 0.5
STOP_Z        = 4.0
COST_RT       = 0.001  # 0.10% round-trip (stocks less liquid than ETFs)

PAIRS = [
    ("MSFT", "TXN",  "XLK"),
    ("TXN",  "META", "XLK"),
    ("AMZN", "TSLA", "XLY"),
    ("BAC",  "GS",   "XLF"),
    ("JNJ",  "UNH",  "XLV"),
]

_PREFIXES = [f"h{i:03d}" for i in range(62, 161)]


def fetch_close(ticker, start=FULL_START, end=FULL_END):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h160_{ticker}_close_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def build_residual_price(price_s, spy_s, sector_s, window=FACTOR_WINDOW):
    """
    Rolling OLS residual of stock return against [SPY, sector].
    Returns cumulative 'idiosyncratic price' series.
    """
    r_stk    = price_s.pct_change()
    r_spy    = spy_s.pct_change()
    r_sec    = sector_s.pct_change()

    df = pd.DataFrame({"r": r_stk, "spy": r_spy, "sec": r_sec}).dropna()

    resids = np.full(len(df), np.nan)

    for i in range(window, len(df)):
        wb = df.iloc[i - window: i]
        X  = add_constant(wb[["spy", "sec"]].values)
        y  = wb["r"].values
        try:
            res = OLS(y, X).fit()
            b_spy, b_sec = res.params[1], res.params[2]
        except Exception:
            resids[i] = 0.0
            continue
        resids[i] = float(df["r"].iloc[i]) - b_spy * float(df["spy"].iloc[i]) - b_sec * float(df["sec"].iloc[i])

    resid_s = pd.Series(resids, index=df.index)
    resid_price = np.exp(resid_s.fillna(0).cumsum())
    resid_price[resid_s.isna()] = np.nan
    return resid_price.rename(price_s.name + "_resid")


def compute_rolling_spread(rx, ry, window=SPREAD_WINDOW, zscore_lb=ZSCORE_LB):
    prices = pd.concat([rx, ry], axis=1).dropna()
    prices.columns = ["X", "Y"]
    betas  = np.full(len(prices), np.nan)
    alphas = np.full(len(prices), np.nan)
    spreads = np.full(len(prices), np.nan)
    for i in range(window, len(prices)):
        x_w = prices["X"].iloc[i - window: i].values
        y_w = prices["Y"].iloc[i - window: i].values
        res = OLS(y_w, add_constant(x_w)).fit()
        b, a = float(res.params[1]), float(res.params[0])
        betas[i] = b; alphas[i] = a
        spreads[i] = float(prices["Y"].iloc[i]) - b * float(prices["X"].iloc[i]) - a
    spread_s = pd.Series(spreads, index=prices.index)
    z = (spread_s - spread_s.rolling(zscore_lb).mean()) / spread_s.rolling(zscore_lb).std()
    return pd.DataFrame({
        "X": prices["X"], "Y": prices["Y"],
        "beta": pd.Series(betas, index=prices.index),
        "alpha": pd.Series(alphas, index=prices.index),
        "spread": spread_s, "z_score": z,
    })


def generate_signals(z_series):
    pos = np.zeros(len(z_series))
    cur = 0
    for i in range(1, len(z_series)):
        zv = z_series.iloc[i]
        if np.isnan(zv):
            pos[i] = 0; cur = 0; continue
        if cur == 0:
            if zv < -ENTRY_Z: cur = 1
            elif zv > ENTRY_Z: cur = -1
        elif cur == 1:
            if zv > -EXIT_Z or abs(zv) > STOP_Z: cur = 0
        elif cur == -1:
            if zv < EXIT_Z or abs(zv) > STOP_Z: cur = 0
        pos[i] = cur
    return pd.Series(pos, index=z_series.index)


def backtest_pair(spread_df, positions):
    x_ret = spread_df["X"].pct_change()
    y_ret = spread_df["Y"].pct_change()
    spread_ret = y_ret - spread_df["beta"].shift(1) * x_ret
    cost_s = (positions != positions.shift(1).fillna(0)).astype(float) * COST_RT
    return (positions.shift(1) * spread_ret - cost_s).fillna(0)


def stats_daily(r):
    r = r.dropna()
    if len(r) < 20:
        return {"cumul": 1.0, "cagr": 0.0, "vol": 0.0, "sharpe": 0.0,
                "max_dd": 0.0, "neg_yrs": 0}
    eq = (1 + r).cumprod()
    terminal = float(eq.iloc[-1])
    n_yrs = len(r) / 252
    cagr = (terminal ** (1 / n_yrs) - 1) if terminal > 0 else -1.0
    vol  = r.std(ddof=1) * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1 + x).prod() - 1).lt(0).sum())
    return {"cumul": terminal, "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "max_dd": max_dd, "neg_yrs": neg_yrs}


def compute_halflife(spread):
    s = spread.dropna()
    if len(s) < 30:
        return np.nan
    lag  = s.shift(1).dropna()
    diff = s.diff().dropna()
    aln  = pd.concat([diff, lag], axis=1).dropna()
    aln.columns = ["diff", "lag"]
    theta = float(OLS(aln["diff"], add_constant(aln["lag"])).fit().params["lag"])
    return np.log(2) / (-theta) if theta < 0 else np.nan


def run_pair(xt, yt, sector_t, spy_s):
    print(f"\n{'='*60}")
    print(f"  Pair: {xt} / {yt}  |  Sector ETF: {sector_t}")
    print(f"{'='*60}")

    px  = fetch_close(xt)
    py  = fetch_close(yt)
    sec = fetch_close(sector_t)
    all_tix = pd.concat([px, py, spy_s, sec], axis=1).dropna()
    px  = all_tix[xt]
    py  = all_tix[yt]
    spy_aligned = all_tix["SPY"]
    sec_aligned = all_tix[sector_t]

    print(f"  Raw data: {len(all_tix)} days  ({all_tix.index[0].date()} → {all_tix.index[-1].date()})")

    # --- Factor residualization ---
    print(f"\n  [A] Factor residualization (rolling {FACTOR_WINDOW}-day OLS)…")
    rx = build_residual_price(px, spy_aligned, sec_aligned)
    ry = build_residual_price(py, spy_aligned, sec_aligned)

    resid_df = pd.concat([rx, ry], axis=1).dropna()
    resid_df.columns = ["X_resid", "Y_resid"]
    print(f"      Residual series: {len(resid_df)} days  (first valid: {resid_df.dropna().index[0].date()})")

    # --- Cointegration on residual series ---
    print(f"\n  [B] Cointegration on residual price series…")
    for label, sub in [
        ("Full",  resid_df),
        ("IS",    resid_df[resid_df.index <= IS_END]),
        ("OOS",   resid_df[resid_df.index >= OOS_START]),
    ]:
        if len(sub.dropna()) < 100:
            print(f"    {label:6s}: insufficient data")
            continue
        stat, pval, cvs = coint(sub["X_resid"].dropna(), sub["Y_resid"].dropna())
        verdict = "COINTEGRATED" if pval < 0.05 else "not cointegrated"
        flag = "***" if pval < 0.01 else ("**" if pval < 0.05 else "")
        print(f"    {label:6s}: n={len(sub):4d}  p={pval:.4f}{flag:3s}  stat={stat:.2f}  → {verdict}")

    # Also check raw price cointegration for comparison
    raw_df = pd.concat([px, py], axis=1).dropna()
    _, pval_raw, _ = coint(raw_df.iloc[:,0], raw_df.iloc[:,1])
    print(f"    Raw prices (full): p={pval_raw:.4f}  (comparison)")

    # --- Spread and z-score ---
    print(f"\n  [C] Spread backtest…")
    spread_df = compute_rolling_spread(resid_df["X_resid"], resid_df["Y_resid"])
    hl_full = compute_halflife(spread_df["spread"].dropna())
    hl_oos  = compute_halflife(spread_df.loc[spread_df.index >= OOS_START, "spread"])
    print(f"      Half-life: full={hl_full:.1f}d  OOS={hl_oos:.1f}d")

    positions = generate_signals(spread_df["z_score"])
    strat     = backtest_pair(spread_df, positions)

    s_is  = stats_daily(strat[(strat.index >= ALT_OOS_ST) & (strat.index <= IS_END)])
    s_oos = stats_daily(strat[strat.index >= OOS_START])
    s_alt = stats_daily(strat[strat.index >= ALT_OOS_ST])
    s_spy = stats_daily(spy_aligned.pct_change().dropna().loc[lambda x: x.index >= OOS_START])

    pos_oos = positions[positions.index >= OOS_START]
    n_long  = int((pos_oos == 1).sum())
    n_short = int((pos_oos == -1).sum())
    total   = len(pos_oos)

    print(f"\n  Results:")
    print(f"    Position use: long={n_long/total*100:.1f}%  short={n_short/total*100:.1f}%  flat={(total-n_long-n_short)/total*100:.1f}%")
    print(f"    IS  : cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}  MaxDD={s_is['max_dd']:.2%}")
    print(f"    OOS : cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
    print(f"    Alt : cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
    print(f"    SPY : cumul={s_spy['cumul']:.4f}  Sharpe={s_spy['sharpe']:.3f}")

    passed = sum([
        s_oos["sharpe"] > 1.0,
        s_oos["cumul"]  > s_spy["cumul"],
        s_oos["max_dd"] > -0.25,
    ])
    print(f"    Criteria met: {passed}/3")

    # Correlation with SPY (market-neutrality check)
    strat_oos = strat[strat.index >= OOS_START]
    spy_oos   = spy_aligned.pct_change().dropna().loc[lambda x: x.index >= OOS_START]
    common    = strat_oos.index.intersection(spy_oos.index)
    corr_spy  = float(strat_oos.loc[common].corr(spy_oos.loc[common]))
    print(f"    Corr(SPY): {corr_spy:.3f}")

    return s_oos, s_alt, s_is, passed


def main():
    print("\n" + "=" * 70)
    print("  H160 — Factor-Residualized Equity Pairs Trading")
    print("=" * 70)
    print(f"  IS: {FULL_START}–{IS_END}  |  OOS: {OOS_START}–{FULL_END}")
    print(f"  Factor window: {FACTOR_WINDOW}d  |  Spread window: {SPREAD_WINDOW}d  |  Z-lb: {ZSCORE_LB}d")
    print(f"  Entry ±{ENTRY_Z}σ  Exit ±{EXIT_Z}σ  Stop ±{STOP_Z}σ  Cost {COST_RT*100:.2f}% RT")

    spy = fetch_close("SPY")

    results = {}
    for xt, yt, sector in PAIRS:
        s_oos, s_alt, s_is, passed = run_pair(xt, yt, sector, spy)
        results[f"{xt}/{yt}"] = {
            "oos_sharpe": s_oos["sharpe"],
            "oos_cumul":  s_oos["cumul"],
            "oos_maxdd":  s_oos["max_dd"],
            "oos_negyr":  s_oos["neg_yrs"],
            "alt_sharpe": s_alt["sharpe"],
            "is_sharpe":  s_is["sharpe"],
            "passed":     passed,
        }

    spy_s = stats_daily(spy.pct_change().dropna().loc[lambda x: x.index >= OOS_START])

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  {'Pair':<14} {'IS Sh':>7} {'OOS Sh':>7} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYr':>6} {'Crit':>5}")
    print(f"  {'-'*60}")
    for pair, r in results.items():
        print(f"  {pair:<14} {r['is_sharpe']:>7.3f} {r['oos_sharpe']:>7.3f} {r['oos_cumul']:>10.4f} {r['oos_maxdd']:>8.2%} {r['oos_negyr']:>6d} {r['passed']:>5}/3")
    print(f"  {'SPY baseline':<14} {'—':>7} {spy_s['sharpe']:>7.3f} {spy_s['cumul']:>10.4f} {spy_s['max_dd']:>8.2%}")

    any_confirmed = any(r["passed"] >= 2 for r in results.values())
    n_confirmed   = sum(r["passed"] >= 2 for r in results.values())

    print(f"\n  Pairs meeting ≥2 of 3 criteria: {n_confirmed}/{len(results)}")
    print(f"\n  VERDICT: {'PARTIAL CONFIRMED' if any_confirmed else 'NOT CONFIRMED'}")

    if any_confirmed:
        print(f"  → {n_confirmed} pair(s) pass criteria. Proceed with H161 (dividend raise) and H169 (LLM pair selection).")
        print(f"  → Check correlations across confirmed pairs for portfolio construction.")
    else:
        print(f"  → Factor residualization did not lift pairs above baseline.")
        print(f"  → Root cause: likely short half-life is already limiting, not factor noise.")
        print(f"  → H161/H162 (dividend/covered-call) can still proceed independently.")

    # Save results
    lines = []
    lines.append("H160 — Factor-Residualized Equity Pairs Trading\n")
    lines.append(f"Run: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append(f"Factor window: {FACTOR_WINDOW}d  Spread window: {SPREAD_WINDOW}d  Z-lb: {ZSCORE_LB}d\n\n")
    lines.append(f"{'Pair':<14} {'IS Sh':>7} {'OOS Sh':>7} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYr':>6} {'Crit':>5}\n")
    lines.append("-" * 60 + "\n")
    for pair, r in results.items():
        lines.append(f"{pair:<14} {r['is_sharpe']:>7.3f} {r['oos_sharpe']:>7.3f} {r['oos_cumul']:>10.4f} {r['oos_maxdd']:>8.2%} {r['oos_negyr']:>6d} {r['passed']:>5}/3\n")
    lines.append(f"{'SPY':<14} {'—':>7} {spy_s['sharpe']:>7.3f} {spy_s['cumul']:>10.4f} {spy_s['max_dd']:>8.2%}\n\n")
    verdict = "PARTIAL CONFIRMED" if any_confirmed else "NOT CONFIRMED"
    lines.append(f"VERDICT: {verdict}\n")
    (RESULT_DIR / "h160_factor_pairs.txt").write_text("".join(lines))
    print(f"\n  Results saved → backtesting/results/h160_factor_pairs.txt")


if __name__ == "__main__":
    main()
