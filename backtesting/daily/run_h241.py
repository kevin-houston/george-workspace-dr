"""
H241 — XGBoost Cross-Sectional Momentum on 200-Stock Universe (H202-XL)
========================================================================
Root cause of H202 NOT CONFIRMED: 30 stocks → ~2,879 IS samples, too small for
XGBoost to learn a robust cross-sectional function.

H241 fix: ~200 large-cap stocks → ~19,200 IS samples (7× more).
At this scale, XGBoost can meaningfully differentiate signal vs simple rank.

Source: arXiv:2507.07107 (Du, May 2026) — ML Enhanced Cross-Sectional Portfolio Optimization
Universe: ~200 current S&P 500 large-cap stocks (survivorship-biased, consistent with H202)
Variants:
  A — simple 6-1m rank (baseline)
  B — bias-masked 6-1m rank (|1m|≤25%, vol_change≤2.5)
  C — XGBoost on 8 features, trained IS-only, frozen in OOS
Portfolio: top-20 equal-weight (5% per position), monthly rebalance
TC: 0.10% round-trip
IS: 2013–2020   OOS: 2021–2026
Confirm: OOS Sharpe > 1.5
Secondary: any variant > H202-C OOS Sharpe 1.278 beats 30-stock XGBoost
"""

import warnings; warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from xgboost import XGBRegressor

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# ~200 large-cap S&P 500 stocks across all 11 GICS sectors
UNIVERSE = [
    # Information Technology (30)
    "AAPL","MSFT","NVDA","AVGO","AMD","QCOM","ORCL","CRM","ADBE","INTC",
    "TXN","ACN","IBM","AMAT","LRCX","MU","NOW","INTU","ADI","NXPI",
    "MCHP","KLAC","CDNS","SNPS","FTNT","GLW","HPE","KEYS","ZBRA","JNPR",
    # Consumer Discretionary (20)
    "AMZN","TSLA","HD","MCD","NKE","SBUX","LOW","TJX","F","GM",
    "CMG","BKNG","ROST","DRI","DHI","LEN","PHM","NVR","TOL","EXPE",
    # Financials (25)
    "JPM","BAC","WFC","GS","MS","C","BLK","AXP","CB","PGR",
    "MET","PRU","TRV","ICE","CME","SCHW","USB","PNC","TFC","SPGI",
    "MCO","COF","DFS","AIG","MMC",
    # Healthcare (25)
    "UNH","LLY","JNJ","ABBV","MRK","PFE","TMO","ABT","AMGN","GILD",
    "MDT","BMY","ISRG","CVS","CI","HUM","ELV","REGN","VRTX","ZBH",
    "BDX","BSX","EW","DXCM","HOLX",
    # Consumer Staples (15)
    "WMT","COST","PG","KO","PEP","PM","MO","MDLZ","CL","GIS",
    "K","CPB","HRL","SJM","CAG",
    # Energy (15)
    "XOM","CVX","COP","EOG","PSX","VLO","MPC","SLB","HAL",
    "OXY","HES","APA","DVN","FANG","KMI",
    # Industrials (20)
    "HON","UPS","RTX","LMT","CAT","GE","NOC","BA","DE","EMR",
    "ETN","ITW","CTAS","WM","RSG","CSX","NSC","UNP","FDX","MMM",
    # Materials (10)
    "LIN","APD","SHW","ECL","NEM","FCX","NUE","ALB","CF","MOS",
    # Real Estate (10)
    "PLD","AMT","EQIX","CCI","SPG","O","DLR","EXR","AVB","EQR",
    # Utilities (10)
    "NEE","DUK","SO","D","AEP","EXC","PCG","SRE","XEL","PPL",
    # Communication Services (15)
    "GOOGL","META","NFLX","DIS","CMCSA","VZ","T","TMUS","CHTR","FOXA",
    "EA","TTWO","OMC","IPG","LDOS",
]
# Deduplicate while preserving order
seen = set()
UNIVERSE = [t for t in UNIVERSE if not (t in seen or seen.add(t))]

DATA_START = "2010-01-01"
DATA_END   = "2026-05-31"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-05-31")
TOP_N      = 20   # 5% per position (vs H202's 6-stock 1/6 weight)
TC         = 0.001  # 0.10% round-trip

FEATURES = ['mom_6_1','mom_12_1','mom_3_1','rev_1m',
            'vol_12m','vol_1m','vol_change','mom_risk_adj']

# ── helpers ─────────────────────────────────────────────────────────────────

def sharpe(r: pd.Series) -> float:
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0

def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())

def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_yrs(r: pd.Series) -> int:
    ann = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())

# ── data ────────────────────────────────────────────────────────────────────

def load_prices() -> pd.DataFrame:
    cache = CACHE_DIR / "h241_monthly_prices.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        missing = [t for t in UNIVERSE if t not in df.columns]
        if not missing:
            print(f"  Loaded from cache: {df.shape[1]} tickers")
            return df[UNIVERSE]
    print(f"  Downloading {len(UNIVERSE)} tickers (batch)…")
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False, threads=True)
    closes = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw
    monthly = closes.resample("ME").last()
    monthly.to_parquet(cache)
    available = [t for t in UNIVERSE if t in monthly.columns]
    print(f"  Saved: {len(available)}/{len(UNIVERSE)} tickers")
    return monthly[available]

# ── feature engineering ─────────────────────────────────────────────────────

def build_panel(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Returns a MultiIndex DataFrame (date × ticker) with features and fwd_ret.
    fwd_ret[t] = return in month t+1 (entered at end of month t, exit end of t+1).
    Features at month t use only data through month t-1 (strict 1-month lag).
    """
    ret = prices.pct_change()
    rows = []
    dates = prices.index

    for i in range(13, len(dates) - 1):
        date = dates[i]
        fwd_date = dates[i + 1]

        # Monthly returns with 1-month lag
        p_now = prices.iloc[i - 1]       # price at end of month t-1 (signal formation)
        r1m   = ret.iloc[i - 1]          # 1m return (month t-1)

        def safe_ret(a, b):
            return prices.iloc[b] / prices.iloc[a] - 1

        mom_3_1  = safe_ret(i - 4, i - 1)  # months t-4 to t-1 (3m skip 1m)
        mom_6_1  = safe_ret(i - 7, i - 1)  # months t-7 to t-1 (6m skip 1m)
        mom_12_1 = safe_ret(i - 13, i - 1) # months t-13 to t-1 (12m skip 1m)

        # vol: trailing 12m and 3m monthly return std (annualised)
        vol_12m = ret.iloc[i - 12:i].std() * np.sqrt(12)
        vol_3m  = ret.iloc[i - 3:i].std()  * np.sqrt(12)

        fwd_ret_series = ret.iloc[i + 1]   # actual next-month return (target)

        tickers = prices.columns[prices.iloc[i - 1].notna() & prices.iloc[i + 1].notna()]
        for t in tickers:
            vc  = vol_3m[t] / (vol_12m[t] + 1e-8)
            mra = mom_6_1[t] / (vol_12m[t] + 1e-8)
            rows.append({
                'date': date,
                'ticker': t,
                'fwd_ret': fwd_ret_series[t],
                'mom_6_1': mom_6_1[t],
                'mom_12_1': mom_12_1[t],
                'mom_3_1': mom_3_1[t],
                'rev_1m': r1m[t],
                'vol_12m': vol_12m[t],
                'vol_1m': vol_3m[t],
                'vol_change': vc,
                'mom_risk_adj': mra,
            })

    df = pd.DataFrame(rows)
    df = df.dropna(subset=FEATURES + ['fwd_ret'])
    return df.set_index(['date', 'ticker'])

# ── backtest ─────────────────────────────────────────────────────────────────

def run_backtest(panel: pd.DataFrame, variant: str, model=None) -> pd.Series:
    dates = panel.index.get_level_values('date').unique().sort_values()
    port_rets = []
    prev_set: set = set()

    for date in dates:
        df_t = panel.loc[date].copy()

        if variant == 'B':
            df_t = df_t[(df_t['rev_1m'].abs() <= 0.25) & (df_t['vol_change'] <= 2.5)]

        if variant == 'C' and model is not None:
            X = df_t[FEATURES].fillna(0)
            df_t = df_t.copy()
            df_t['score'] = model.predict(X)
        else:
            df_t['score'] = df_t['mom_6_1']

        if len(df_t) < TOP_N:
            port_rets.append(0.0)
            continue

        top = set(df_t.nlargest(TOP_N, 'score').index.tolist())
        turnover = len(top.symmetric_difference(prev_set)) / (2 * TOP_N)
        tc_drag = turnover * TC
        prev_set = top

        monthly_ret = df_t.loc[list(top), 'fwd_ret'].dropna().mean()
        port_rets.append(monthly_ret - tc_drag)

    s = pd.Series(port_rets, index=dates, name=variant)
    s.index = pd.to_datetime(s.index)
    return s

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("H241 — XGBoost Cross-Sectional Momentum (200-Stock Universe)")
    print("=" * 65)

    print("\nLoading prices…")
    prices = load_prices()
    print(f"  Prices: {prices.shape[1]} tickers × {len(prices)} months")

    print("\nBuilding feature panel…")
    panel = build_panel(prices)
    n_months = panel.index.get_level_values('date').nunique()
    print(f"  Panel: {len(panel):,} stock-months across {n_months} months")

    is_panel  = panel.loc[IS_START:IS_END]
    oos_panel = panel.loc[OOS_START:OOS_END]
    print(f"  IS: {len(is_panel):,} samples  OOS: {len(oos_panel):,} samples")

    # SPY benchmark
    spy_raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)['Close']
    if isinstance(spy_raw, pd.DataFrame):
        spy_raw = spy_raw.squeeze()
    spy_ret = spy_raw.resample("ME").last().pct_change().squeeze()
    spy_oos = spy_ret.loc[OOS_START:OOS_END].dropna()
    spy_is  = spy_ret.loc[IS_START:IS_END].dropna()

    # Train XGBoost on IS (cross-sectional percentile rank as target)
    print("\nTraining XGBoost on IS data…")
    X_is = is_panel[FEATURES].fillna(0)
    y_is = is_panel.groupby('date')['fwd_ret'].rank(pct=True)

    model = XGBRegressor(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42,
        n_jobs=-1, verbosity=0,
    )
    model.fit(X_is, y_is)
    print("  Model trained.")

    feat_imp = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False)
    print("\nFeature importances (XGBoost gain):")
    for f, imp in feat_imp.items():
        print(f"  {f:15s}: {imp:.4f}")

    results = {}
    print()
    for var in ['A', 'B', 'C']:
        label = {'A':'Simple 6-1m Rank','B':'Bias-Masked Rank','C':'XGBoost'}[var]
        m = model if var == 'C' else None
        all_ret = run_backtest(panel, var, m)
        is_ret  = all_ret.loc[IS_START:IS_END]
        oos_ret = all_ret.loc[OOS_START:OOS_END]

        aligned_spy = spy_oos.reindex(oos_ret.index).squeeze()
        corr_spy = float(oos_ret.corr(aligned_spy))

        ann_oos = oos_ret.groupby(oos_ret.index.year).apply(lambda x: (1+x).prod()-1)
        ann_str = " | ".join(f"{y}:{v*100:+.1f}%" for y, v in ann_oos.items())

        print(f"--- Variant {var}: {label} ---")
        print(f"  IS  Sharpe={sharpe(is_ret):.3f}  Cumul={cumul(is_ret):.3f}×  MaxDD={maxdd(is_ret)*100:.1f}%  NegYrs={neg_yrs(is_ret)}")
        print(f"  OOS Sharpe={sharpe(oos_ret):.3f}  Cumul={cumul(oos_ret):.3f}×  MaxDD={maxdd(oos_ret)*100:.1f}%  NegYrs={neg_yrs(oos_ret)}")
        print(f"  Corr(OOS,SPY)={corr_spy:.3f}")
        print(f"  Annual OOS: {ann_str}")
        print()

        results[f'variant_{var}'] = {
            'is_sharpe': round(sharpe(is_ret),3),
            'oos_sharpe': round(sharpe(oos_ret),3),
            'oos_cumul': round(cumul(oos_ret),3),
            'oos_maxdd': round(maxdd(oos_ret)*100,1),
            'oos_neg_yrs': neg_yrs(oos_ret),
            'corr_spy_oos': round(corr_spy,3),
        }

    print(f"--- SPY Benchmark ---")
    print(f"  OOS Sharpe={sharpe(spy_oos):.3f}  Cumul={cumul(spy_oos):.3f}×  MaxDD={maxdd(spy_oos)*100:.1f}%")
    results['spy_benchmark'] = {
        'oos_sharpe': round(sharpe(spy_oos),3),
        'oos_cumul': round(cumul(spy_oos),3),
        'oos_maxdd': round(maxdd(spy_oos)*100,1),
    }

    out_path = RESULT_DIR / 'h241_results.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out_path}")

    xgb_sharpe = results['variant_C']['oos_sharpe']
    base_sharpe = results['variant_A']['oos_sharpe']
    confirmed = xgb_sharpe >= 1.5
    beat_h202  = xgb_sharpe > 1.278
    print(f"\nCONFIRM CHECKS:")
    print(f"  XGBoost OOS Sharpe {xgb_sharpe:.3f} >= 1.5 → {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"  XGBoost vs H202-C (1.278): {'BEATS' if beat_h202 else 'DOES NOT BEAT'} (key universe-size test)")
    print(f"  XGBoost vs Baseline-A ({base_sharpe:.3f}): {'XGB ADDS VALUE' if xgb_sharpe > base_sharpe else 'XGB NO LIFT'}")


if __name__ == "__main__":
    main()
