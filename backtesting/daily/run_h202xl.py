"""
H202-XL — XGBoost Cross-Sectional Momentum on 150-Stock Universe
=================================================================
Scales H202-C (XGBoost + bias mask on 30 stocks) to a 150-stock S&P 500
large-cap universe. Research question: does H202's ML signal improve
with more cross-sectional data?

H202-C on 30 stocks: OOS Sharpe 1.278 (CONFIRMED threshold: 1.474)
H202-C was NOT CONFIRMED on 30 stocks (Sharpe < threshold).
H202-XL hypothesis: larger universe exposes the ML signal to true cross-
sectional variation, improving both fit and OOS generalization.

Design:
  - Universe: ~150 S&P 500 large-cap stocks across all 11 GICS sectors
  - Features: mom_6_1, mom_12_1, mom_3_1, rev_1m, vol_12m, vol_1m,
              vol_change, mom_risk_adj (same as H202)
  - Model: XGBoost rank regressor, trained IS-only, predict forward return rank
  - Portfolio: Top-15 equal-weight (10% of universe, matching H202's 6/30)
  - Monthly rebalance, 5 bps TC each way
  - Walk-forward: retrain each year on expanding IS window
  - IS: 2013–2020   OOS: 2021–2026
  - Confirm: OOS Sharpe > 1.5 (meaningful improvement over H198 1.174)
"""

import warnings
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
import time

try:
    from xgboost import XGBRegressor
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("WARNING: xgboost not installed — run `pip install xgboost`")

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

DATA_START = "2010-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

TOP_N    = 15   # top 10% of ~150-stock universe
TC_BPS   = 5    # one-way slippage

# ~150 S&P 500 large-cap stocks across all 11 GICS sectors
# Organized by sector for readability and sector diagnostics
UNIVERSE_SECTORS = {
    # Information Technology (~25 stocks)
    "AAPL": "IT",  "MSFT": "IT",  "NVDA": "IT",  "AVGO": "IT",
    "AMD":  "IT",  "QCOM": "IT",  "INTC": "IT",  "IBM":  "IT",
    "ORCL": "IT",  "CRM":  "IT",  "ACN":  "IT",  "TXN":  "IT",
    "AMAT": "IT",  "MU":   "IT",  "NOW":  "IT",  "LRCX": "IT",
    "ADI":  "IT",  "CSCO": "IT",  "HPQ":  "IT",  "SNPS": "IT",
    "CDNS": "IT",  "KLAC": "IT",  "MRVL": "IT",  "FTNT": "IT",
    "PANW": "IT",

    # Communication Services (~12 stocks)
    "GOOGL": "CS", "META": "CS",  "NFLX": "CS",  "DIS":  "CS",
    "CMCSA": "CS", "VZ":   "CS",  "T":    "CS",  "TMUS": "CS",
    "EA":    "CS", "CHTR": "CS",  "LYV":  "CS",  "TTWO": "CS",

    # Consumer Discretionary (~14 stocks)
    "AMZN": "CD",  "TSLA": "CD",  "HD":   "CD",  "LOW":  "CD",
    "SBUX": "CD",  "MCD":  "CD",  "NKE":  "CD",  "CMG":  "CD",
    "TGT":  "CD",  "BKNG": "CD",  "ORLY": "CD",  "AZO":  "CD",
    "ROST": "CD",  "TJX":  "CD",

    # Consumer Staples (~12 stocks)
    "WMT":  "CS2", "COST": "CS2", "PG":   "CS2", "KO":   "CS2",
    "PEP":  "CS2", "MDLZ": "CS2", "MO":   "CS2", "PM":   "CS2",
    "STZ":  "CS2", "CL":   "CS2", "KMB":  "CS2", "GIS":  "CS2",

    # Financials (~18 stocks)
    "JPM":  "FIN", "BAC":  "FIN", "WFC":  "FIN", "GS":   "FIN",
    "MS":   "FIN", "C":    "FIN", "BLK":  "FIN", "AXP":  "FIN",
    "SCHW": "FIN", "USB":  "FIN", "PNC":  "FIN", "COF":  "FIN",
    "MCO":  "FIN", "CME":  "FIN", "ICE":  "FIN", "SPGI": "FIN",
    "CB":   "FIN", "PRU":  "FIN",

    # Health Care (~18 stocks)
    "UNH":  "HC",  "LLY":  "HC",  "JNJ":  "HC",  "PFE":  "HC",
    "MRK":  "HC",  "ABBV": "HC",  "AMGN": "HC",  "MDT":  "HC",
    "ABT":  "HC",  "BMY":  "HC",  "GILD": "HC",  "CVS":  "HC",
    "ISRG": "HC",  "TMO":  "HC",  "DHR":  "HC",  "REGN": "HC",
    "VRTX": "HC",  "BDX":  "HC",

    # Industrials (~16 stocks)
    "BA":   "IND", "CAT":  "IND", "GE":   "IND", "HON":  "IND",
    "RTX":  "IND", "LMT":  "IND", "NOC":  "IND", "DE":   "IND",
    "UPS":  "IND", "FDX":  "IND", "CSX":  "IND", "NSC":  "IND",
    "EMR":  "IND", "ITW":  "IND", "ETN":  "IND", "DOV":  "IND",

    # Energy (~9 stocks)
    "XOM":  "ENE", "CVX":  "ENE", "COP":  "ENE", "SLB":  "ENE",
    "PSX":  "ENE", "VLO":  "ENE", "EOG":  "ENE", "OXY":  "ENE",
    "MPC":  "ENE",

    # Materials (~8 stocks)
    "LIN":  "MAT", "APD":  "MAT", "NEM":  "MAT", "FCX":  "MAT",
    "DD":   "MAT", "PPG":  "MAT", "SHW":  "MAT", "ECL":  "MAT",

    # Real Estate (~5 stocks)
    "AMT":  "RE",  "CCI":  "RE",  "EQIX": "RE",  "PLD":  "RE",
    "PSA":  "RE",

    # Utilities (~5 stocks)
    "NEE":  "UTL", "DUK":  "UTL", "SO":   "UTL", "AEP":  "UTL",
    "EXC":  "UTL",
}

UNIVERSE = list(UNIVERSE_SECTORS.keys())
print(f"Universe size: {len(UNIVERSE)} stocks")


def fetch_price(ticker: str) -> pd.Series | None:
    # Try existing caches first
    for prefix in ["h198", "h202", "h192", "h181"]:
        for date_suf in [f"{DATA_START}_{DATA_END}",
                         "2011-01-01_2026-04-30",
                         "2010-01-01_2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{date_suf}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.index = pd.to_datetime(s.index).tz_localize(None)
                return s.rename(ticker)

    cp = CACHE_DIR / f"h202xl_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        s = pd.read_parquet(cp).squeeze()
        s.index = pd.to_datetime(s.index).tz_localize(None)
        return s.rename(ticker)

    try:
        raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        s = raw["Close"].resample("ME").last().rename(ticker)
        s.index = pd.to_datetime(s.index).tz_localize(None)
        pd.DataFrame(s).to_parquet(cp)
        return s
    except Exception as e:
        print(f"  Failed {ticker}: {e}")
        return None


def sharpe_monthly(r: pd.Series) -> float:
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0

def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())

def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_yrs(r: pd.Series) -> int:
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())

def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "cumul": 1.0, "maxdd": 0.0, "neg_yrs": 0}
    return {
        "n":        len(r),
        "sharpe":   round(sharpe_monthly(r), 3),
        "cumul":    round(cumul(r), 4),
        "cagr_pct": round(float(r.mean() * 12 * 100), 2),
        "maxdd":    round(maxdd(r), 3),
        "neg_yrs":  neg_yrs(r),
    }


def build_features(prices: pd.DataFrame, t: int) -> pd.DataFrame:
    """Feature matrix at rebalance point t. All data strictly < month t."""
    monthly_ret = prices.pct_change()
    if t < 14:
        return pd.DataFrame()

    rows = {}
    for tkr in prices.columns:
        p = prices[tkr]
        r = monthly_ret[tkr]
        if pd.isna(p.iloc[t-1]) or pd.isna(p.iloc[t-13]):
            continue

        mom_6_1   = (p.iloc[t-1] / p.iloc[t-7]  - 1) if not pd.isna(p.iloc[t-7])  else np.nan
        mom_12_1  = (p.iloc[t-1] / p.iloc[t-13] - 1) if not pd.isna(p.iloc[t-13]) else np.nan
        mom_3_1   = (p.iloc[t-1] / p.iloc[t-4]  - 1) if t >= 5 and not pd.isna(p.iloc[t-4]) else np.nan
        rev_1m    = r.iloc[t-1] if not pd.isna(r.iloc[t-1]) else np.nan

        past_12   = r.iloc[max(0, t-13):t-1]
        vol_12m   = float(past_12.std() * np.sqrt(12)) if len(past_12) >= 6 else np.nan
        vol_1m    = abs(rev_1m) if not pd.isna(rev_1m) else np.nan
        vol_change = (vol_1m / vol_12m - 1) if (vol_12m and vol_12m > 0) else np.nan
        mom_risk_adj = (mom_6_1 / vol_12m) if (vol_12m and vol_12m > 0 and not pd.isna(mom_6_1)) else np.nan

        rows[tkr] = {
            "mom_6_1":      mom_6_1,
            "mom_12_1":     mom_12_1,
            "mom_3_1":      mom_3_1,
            "rev_1m":       rev_1m,
            "vol_12m":      vol_12m,
            "vol_1m":       vol_1m,
            "vol_change":   vol_change,
            "mom_risk_adj": mom_risk_adj,
        }

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).T


def bias_mask(feat: pd.DataFrame) -> pd.Index:
    if feat.empty:
        return pd.Index([])
    ok = feat.dropna(subset=["mom_6_1", "rev_1m", "vol_12m"])
    ok = ok[ok["rev_1m"].abs() <= 0.25]
    ok = ok[ok["vol_change"].fillna(0) <= 2.5]
    return ok.index


def backtest_simple(prices: pd.DataFrame, top_n: int) -> pd.Series:
    """Simple 6-1m rank baseline — H198 logic at 150-stock scale."""
    monthly_ret = prices.pct_change()
    port_rets = []
    months = prices.index[prices.index >= IS_START]

    for i, month in enumerate(months):
        t = prices.index.get_loc(month)
        if t < 14:
            port_rets.append(pd.Series({"date": month, "ret": 0.0}))
            continue

        feat = build_features(prices, t)
        if feat.empty or len(feat) < top_n:
            port_rets.append(pd.Series({"date": month, "ret": 0.0}))
            continue

        valid = bias_mask(feat)
        if len(valid) < top_n:
            valid = feat.index
        ranked = feat.loc[valid, "mom_6_1"].dropna().sort_values(ascending=False)
        picks = ranked.head(top_n).index

        next_rets = monthly_ret.loc[month, picks].dropna()
        if len(next_rets) == 0:
            port_rets.append(pd.Series({"date": month, "ret": 0.0}))
            continue
        port_rets.append(pd.Series({"date": month, "ret": float(next_rets.mean())}))

    df = pd.DataFrame(port_rets).set_index("date")["ret"]
    df.index = pd.to_datetime(df.index)
    return df - TC_BPS / 10_000


def backtest_xgb(prices: pd.DataFrame, top_n: int) -> pd.Series:
    """Walk-forward XGBoost rank regressor."""
    if not HAS_XGB:
        return pd.Series(dtype=float)

    monthly_ret = prices.pct_change()
    port_rets = []
    months = prices.index[prices.index >= IS_START]

    FEAT_COLS = ["mom_6_1","mom_12_1","mom_3_1","rev_1m","vol_12m","vol_1m",
                 "vol_change","mom_risk_adj"]

    model = None
    last_train_year = None

    for month in months:
        t = prices.index.get_loc(month)
        if t < 14:
            port_rets.append(pd.Series({"date": month, "ret": 0.0}))
            continue

        cur_year = month.year

        # Retrain annually (expanding IS window through IS_END)
        if (last_train_year is None or cur_year != last_train_year) and month <= IS_END:
            train_months = prices.index[(prices.index >= IS_START) & (prices.index < month)]
            X_train, y_train = [], []
            for tm in train_months:
                ti = prices.index.get_loc(tm)
                if ti < 14:
                    continue
                f = build_features(prices, ti)
                if f.empty or len(f) < top_n + 2:
                    continue
                valid = bias_mask(f)
                if len(valid) < top_n + 2:
                    valid = f.index
                fv = f.loc[valid, FEAT_COLS].dropna()
                if len(fv) < top_n + 2:
                    continue
                # Forward 1-month return as target
                fwd = monthly_ret.loc[tm, fv.index].dropna()
                common_idx = fv.index.intersection(fwd.index)
                if len(common_idx) < top_n + 2:
                    continue
                fwd_rank = fwd.loc[common_idx].rank(pct=True)
                X_train.append(fv.loc[common_idx])
                y_train.append(fwd_rank)

            if X_train:
                X = pd.concat(X_train).fillna(0)
                y = pd.concat(y_train)
                model = XGBRegressor(
                    n_estimators=200, max_depth=3,
                    learning_rate=0.05, subsample=0.8,
                    colsample_bytree=0.8, random_state=42,
                    verbosity=0,
                )
                model.fit(X, y)
                last_train_year = cur_year

        # If no model yet (before enough IS data), fall back to simple sort
        feat = build_features(prices, t)
        if feat.empty or len(feat) < top_n:
            port_rets.append(pd.Series({"date": month, "ret": 0.0}))
            continue

        valid = bias_mask(feat)
        if len(valid) < top_n:
            valid = feat.index
        fv = feat.loc[valid, FEAT_COLS].dropna()

        if model is None or len(fv) < top_n:
            ranked = fv["mom_6_1"].sort_values(ascending=False)
            picks = ranked.head(top_n).index
        else:
            pred = model.predict(fv.fillna(0))
            score_s = pd.Series(pred, index=fv.index)
            picks = score_s.nlargest(top_n).index

        next_rets = monthly_ret.loc[month, picks].dropna()
        if len(next_rets) == 0:
            port_rets.append(pd.Series({"date": month, "ret": 0.0}))
            continue
        port_rets.append(pd.Series({"date": month, "ret": float(next_rets.mean())}))

    df = pd.DataFrame(port_rets).set_index("date")["ret"]
    df.index = pd.to_datetime(df.index)
    return df - TC_BPS / 10_000


def main():
    print("=" * 65)
    print("H202-XL — XGBoost Cross-Sectional Momentum (150-stock)")
    print("=" * 65)

    # ─── Data download ──────────────────────────────────────────────
    print("\nLoading price data…")
    price_dict = {}
    failed = []
    for i, tkr in enumerate(UNIVERSE):
        s = fetch_price(tkr)
        if s is None or s.empty:
            failed.append(tkr)
        else:
            price_dict[tkr] = s
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(UNIVERSE)} loaded ({len(failed)} failed)…")
        if i > 0 and (i + 1) % 5 == 0:
            time.sleep(0.3)   # gentle rate limiting

    print(f"Loaded: {len(price_dict)} / {len(UNIVERSE)}  |  Failed: {len(failed)}")
    if failed:
        print(f"  Failed tickers: {failed}")

    if len(price_dict) < 50:
        print("Too few stocks loaded — aborting.")
        return

    prices = pd.DataFrame(price_dict)
    prices = prices.sort_index()
    prices = prices[prices.index >= pd.Timestamp(DATA_START)]
    prices = prices[prices.index <= pd.Timestamp(DATA_END)]

    # Drop tickers with >50% missing
    ok_cols = [c for c in prices.columns if prices[c].notna().mean() > 0.5]
    prices = prices[ok_cols]
    print(f"Effective universe (>50% data coverage): {len(ok_cols)} stocks")

    # SPY benchmark
    spy_s = fetch_price("SPY")
    if spy_s is None:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        spy_s = raw["Close"].resample("ME").last().rename("SPY")
        spy_s.index = pd.to_datetime(spy_s.index).tz_localize(None)
    spy_ret = spy_s.pct_change().dropna()

    # ─── Variant A: Simple 6-1m rank ────────────────────────────────
    print("\nRunning Variant A: simple 6-1m rank (150-stock baseline)…")
    ret_A = backtest_simple(prices, TOP_N)

    # ─── Variant B: XGBoost ─────────────────────────────────────────
    if HAS_XGB:
        print("Running Variant B: XGBoost walk-forward…")
        ret_B = backtest_xgb(prices, TOP_N)
    else:
        ret_B = pd.Series(dtype=float)

    # ─── Results ────────────────────────────────────────────────────
    spy_is  = eval_period(spy_ret, IS_START, IS_END)
    spy_oos = eval_period(spy_ret, OOS_START, OOS_END)

    A_is  = eval_period(ret_A, IS_START, IS_END)
    A_oos = eval_period(ret_A, OOS_START, OOS_END)

    B_is  = eval_period(ret_B, IS_START, IS_END) if not ret_B.empty else {}
    B_oos = eval_period(ret_B, OOS_START, OOS_END) if not ret_B.empty else {}

    confirmed_A = A_oos.get("sharpe", 0) > 1.5
    confirmed_B = B_oos.get("sharpe", 0) > 1.5
    overall = confirmed_A or confirmed_B

    print(f"\n{'Strategy':<35} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>11} {'OOS Cumul':>10} {'MaxDD':>8}")
    print("-" * 90)

    def pr(name, is_d, oos_d):
        print(f"{name:<35} {is_d.get('sharpe',0):>10.3f} {is_d.get('cumul',1):>10.4f} "
              f"{oos_d.get('sharpe',0):>11.3f} {oos_d.get('cumul',1):>10.4f} "
              f"{oos_d.get('maxdd',0):>8.1%}")

    pr("SPY buy-and-hold",         spy_is, spy_oos)
    pr(f"A: 6-1m rank top-{TOP_N}",   A_is,   A_oos)
    if not ret_B.empty:
        pr(f"B: XGBoost top-{TOP_N}",   B_is,   B_oos)

    print(f"\nH198 reference (30-stock 6-1m): OOS Sharpe 1.174")
    print(f"H202-C reference (30-stock XGB): OOS Sharpe 1.278")
    print(f"\nConfirm threshold: OOS Sharpe > 1.5")
    print(f"Variant A confirmed: {confirmed_A}")
    print(f"Variant B confirmed: {confirmed_B}")
    print(f"H202-XL overall:     {'CONFIRMED' if overall else 'NOT CONFIRMED'}")

    # Save
    result = {
        "hypothesis":   "H202-XL",
        "description":  "XGBoost cross-sectional momentum on 150-stock universe",
        "universe_size": len(ok_cols),
        "top_n":         TOP_N,
        "confirm_threshold": 1.5,
        "verdict_A":    "CONFIRMED" if confirmed_A else "NOT CONFIRMED",
        "verdict_B":    "CONFIRMED" if confirmed_B else "NOT CONFIRMED",
        "verdict":      "CONFIRMED" if overall else "NOT CONFIRMED",
        "ref_h198_oos_sharpe": 1.174,
        "ref_h202c_oos_sharpe": 1.278,
        "spy_is":   spy_is,  "spy_oos":  spy_oos,
        "A_is":     A_is,    "A_oos":    A_oos,
        "B_is":     B_is,    "B_oos":    B_oos,
    }

    out = RESULT_DIR / "h202xl_results.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
