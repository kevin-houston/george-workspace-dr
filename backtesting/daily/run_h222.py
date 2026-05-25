"""
H222 — Quality Factor: Piotroski F-Score + Gross Profitability (Novy-Marx 2013)
================================================================================
Two quality signals from annual fundamentals via yfinance (FMP legacy blocked).

A. Piotroski F-Score (9-point binary checklist):
   Profitability (4): ROA>0, CFO>0, ΔROA>0, CFO>Accruals
   Leverage (3): ΔLeverage<0, ΔCurrentRatio>0, no dilution
   Efficiency (2): ΔGrossMargin>0, ΔAssetTurnover>0
   Long top-6 by F-Score, annual rebalance

B. Gross Profitability (Novy-Marx 2013):
   Signal = (Revenue - COGS) / Total Assets
   Long top-6 by GP/Assets, annual rebalance

Data: yfinance (5 years history) — NOTE: limited to FY2021-2025 ≈ 3 hold periods
Universe: same 30 large-cap stocks as H181/H198/H217
Available: 2023-2026 (IS: 2023-2024, OOS: 2025-2026)
Rebalance: April (90-day lag from Dec 31 fiscal year-end)
Confirm: OOS Sharpe > 0.7  (but flag BLOCKED if <6 OOS months)
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
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

DATA_START  = "2011-01-01"
DATA_END    = "2026-04-30"
IS_START    = pd.Timestamp("2023-04-01")   # adjusted for yfinance data availability
IS_END      = pd.Timestamp("2024-03-31")
OOS_START   = pd.Timestamp("2024-04-01")
OOS_END     = pd.Timestamp("2026-04-30")
REBALANCE_MONTH = 4
TOP_N       = 6
CONFIRM_THRESHOLD = 0.7


# ── yfinance fundamentals fetching ───────────────────────────────────────────

def _get_row(df: pd.DataFrame, *names) -> pd.Series:
    """Get a row from a transposed yfinance statement by trying multiple names."""
    for name in names:
        if name in df.index:
            return df.loc[name]
    return pd.Series(dtype=float)


def fetch_fundamentals_yf(ticker: str) -> pd.DataFrame:
    """Return annual fundamental data indexed by fiscal year (int)."""
    cp = CACHE_DIR / f"h222_yf_fundamentals_{ticker}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)

    try:
        t = yf.Ticker(ticker)
        inc = t.financials          # index=metrics, columns=dates
        bal = t.balance_sheet
        cf  = t.cashflow
    except Exception as e:
        print(f"  yfinance error {ticker}: {e}")
        return pd.DataFrame()

    if inc.empty or bal.empty or cf.empty:
        return pd.DataFrame()

    # Align on fiscal year end dates common to all three
    common_dates = inc.columns.intersection(bal.columns).intersection(cf.columns)
    if len(common_dates) == 0:
        return pd.DataFrame()

    rows = []
    for dt in sorted(common_dates):
        yr = dt.year

        net_income  = _get_row(inc, "Net Income", "Net Income From Continuing Operation Net Minority Interest").get(dt, np.nan)
        revenue     = _get_row(inc, "Total Revenue").get(dt, np.nan)
        gross_profit = _get_row(inc, "Gross Profit").get(dt, np.nan)
        cogs        = _get_row(inc, "Cost Of Revenue", "Reconciled Cost Of Revenue").get(dt, np.nan)

        total_assets = _get_row(bal, "Total Assets").get(dt, np.nan)
        cur_assets   = _get_row(bal, "Current Assets").get(dt, np.nan)
        cur_liab     = _get_row(bal, "Current Liabilities").get(dt, np.nan)
        ltd          = _get_row(bal, "Long Term Debt", "Long Term Debt And Capital Lease Obligation").get(dt, np.nan)
        shares       = _get_row(bal, "Share Issued", "Ordinary Shares Number").get(dt, np.nan)

        cfo          = _get_row(cf, "Operating Cash Flow").get(dt, np.nan)

        ta = total_assets if (pd.notna(total_assets) and total_assets != 0) else np.nan
        rev = revenue if (pd.notna(revenue) and revenue != 0) else np.nan
        cl = cur_liab if (pd.notna(cur_liab) and cur_liab != 0) else np.nan

        roa           = net_income / ta if pd.notna(ta) and pd.notna(net_income) else np.nan
        cfo_a         = cfo / ta if pd.notna(ta) and pd.notna(cfo) else np.nan
        leverage      = ltd / ta if pd.notna(ta) and pd.notna(ltd) else np.nan
        current_ratio = cur_assets / cl if pd.notna(cl) and pd.notna(cur_assets) else np.nan
        gross_margin  = gross_profit / rev if pd.notna(rev) and pd.notna(gross_profit) else np.nan
        asset_turnover = rev / ta if pd.notna(ta) and pd.notna(rev) else np.nan
        gp_assets      = (gross_profit) / ta if pd.notna(ta) and pd.notna(gross_profit) else np.nan

        rows.append({
            "year": yr, "roa": roa, "cfo": cfo, "cfo_a": cfo_a,
            "leverage": leverage, "current_ratio": current_ratio,
            "shares": shares, "gross_margin": gross_margin,
            "asset_turnover": asset_turnover, "gp_assets": gp_assets,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("year").sort_index()
    df.to_parquet(cp)
    return df


def piotroski_fscore(df: pd.DataFrame, yr: int) -> float:
    """Compute 9-point F-Score for fiscal year yr."""
    if yr not in df.index or (yr - 1) not in df.index:
        return np.nan

    cur = df.loc[yr]
    prv = df.loc[yr - 1]

    def s(v, d=0.0):
        return float(v) if pd.notna(v) else d

    f1 = 1 if s(cur.roa) > 0 else 0
    f2 = 1 if s(cur.cfo) > 0 else 0
    f3 = 1 if s(cur.roa) > s(prv.roa) else 0
    f4 = 1 if s(cur.cfo_a) > s(cur.roa) else 0           # CFO > accruals
    f5 = 1 if s(cur.leverage, 1) < s(prv.leverage, 1) else 0
    f6 = 1 if s(cur.current_ratio) > s(prv.current_ratio) else 0
    cur_sh, prv_sh = s(cur.shares), s(prv.shares, 1)
    f7 = 1 if (prv_sh == 0 or cur_sh <= prv_sh * 1.05) else 0
    f8 = 1 if s(cur.gross_margin) > s(prv.gross_margin) else 0
    f9 = 1 if s(cur.asset_turnover) > s(prv.asset_turnover) else 0

    return float(f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9)


# ── fetch fundamentals for all 30 stocks ─────────────────────────────────────
print("Fetching annual fundamentals via yfinance (cached)…")
fundamentals = {}
for tk in UNIVERSE:
    df_f = fetch_fundamentals_yf(tk)
    if df_f.empty:
        print(f"  ⚠ No data: {tk}")
    else:
        fundamentals[tk] = df_f
        print(f"  ✓ {tk}: FY{df_f.index.min()}–{df_f.index.max()}")

print(f"\nGot data for {len(fundamentals)}/{len(UNIVERSE)} stocks")


# ── build annual signal matrices ──────────────────────────────────────────────
# Rebalance in April of year Y uses FY(Y-1) data
# With yfinance 5-year history (FY2021-2025), rebalances 2023-2026 are feasible
# (FY2022+ have prior-year deltas from FY2021)

years_range = range(2022, 2027)
fscore_by_year = {}
gpa_by_year    = {}

for reb_year in years_range:
    fy = reb_year - 1
    f_row, gpa_row = {}, {}
    for tk, df_f in fundamentals.items():
        f_row[tk]   = piotroski_fscore(df_f, fy)
        gpa_row[tk] = df_f.loc[fy, "gp_assets"] if fy in df_f.index else np.nan
    fscore_by_year[reb_year] = f_row
    gpa_by_year[reb_year]    = gpa_row

fscore_df = pd.DataFrame(fscore_by_year).T
gpa_df    = pd.DataFrame(gpa_by_year).T

print("\nF-Score coverage by rebalance year:")
for yr in fscore_df.index:
    valid = fscore_df.loc[yr].dropna()
    mn = f"{valid.mean():.1f}" if len(valid) > 0 else "n/a"
    lo = f"{int(valid.min())}" if len(valid) > 0 else "n/a"
    hi = f"{int(valid.max())}" if len(valid) > 0 else "n/a"
    print(f"  {yr}: {len(valid)}/30 stocks with F-Score  "
          f"(mean={mn}, range {lo}-{hi})")


# ── load monthly returns ──────────────────────────────────────────────────────
print("\nLoading monthly price returns…")
monthly_close_cache = CACHE_DIR / "h222_monthly_close.parquet"
if monthly_close_cache.exists():
    monthly_close = pd.read_parquet(monthly_close_cache)
else:
    daily_close = {}
    for tk in UNIVERSE:
        cp = CACHE_DIR / f"h215_{tk}_daily_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            daily_close[tk] = pd.read_parquet(cp)["close"]
        else:
            raw = yf.download(tk, start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw = raw.xs(tk, axis=1, level=1)
            col = "close" if "close" in raw.columns else "Close"
            daily_close[tk] = raw[col]
    monthly_close = pd.DataFrame(daily_close).resample("ME").last()
    monthly_close.index = pd.to_datetime(monthly_close.index).tz_localize(None)
    monthly_close.to_parquet(monthly_close_cache)

monthly_ret = monthly_close.pct_change()


# ── build annual-rebalance portfolios ─────────────────────────────────────────
def build_annual_portfolio(signal_df: pd.DataFrame) -> pd.Series:
    port_rets = {}
    for yr in signal_df.index:
        sig = signal_df.loc[yr].dropna()
        if len(sig) < TOP_N:
            continue
        picks = sig.nlargest(TOP_N).index.tolist()

        start = pd.Timestamp(f"{yr}-{REBALANCE_MONTH:02d}-01")
        end   = pd.Timestamp(f"{yr+1}-{REBALANCE_MONTH:02d}-01") - pd.DateOffset(months=1)

        for dt, row in monthly_ret.loc[start:end].iterrows():
            valid = row[picks].dropna()
            if not valid.empty:
                port_rets[dt] = float(valid.mean())

    s = pd.Series(port_rets).sort_index()
    s.index = pd.to_datetime(s.index)
    return s


print("Building F-Score portfolio…")
fscore_rets = build_annual_portfolio(fscore_df)
print("Building GP/Assets portfolio…")
gpa_rets    = build_annual_portfolio(gpa_df)

print(f"  F-Score returns: {len(fscore_rets)} months "
      f"({fscore_rets.index.min().strftime('%Y-%m') if len(fscore_rets) else 'empty'} – "
      f"{fscore_rets.index.max().strftime('%Y-%m') if len(fscore_rets) else 'empty'})")
print(f"  GPA returns: {len(gpa_rets)} months")


# ── performance metrics ───────────────────────────────────────────────────────
def sharpe(rets: pd.Series, ann: int = 12) -> float:
    if len(rets) < 3 or rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * np.sqrt(ann))


def maxdd(rets: pd.Series) -> float:
    if rets.empty:
        return 0.0
    cum = (1 + rets).cumprod()
    roll_max = cum.cummax()
    return float(((cum - roll_max) / roll_max).min())


def neg_years(rets: pd.Series) -> int:
    if rets.empty:
        return 0
    r = rets.copy()
    r.index = pd.to_datetime(r.index)
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())


def eval_period(rets: pd.Series, start: pd.Timestamp, end: pd.Timestamp,
                label: str) -> dict:
    r = rets.loc[start:end].dropna()
    n = len(r)
    sh = sharpe(r)
    md = maxdd(r)
    ny = neg_years(r)
    cum = float((1 + r).prod() - 1) if n > 0 else 0.0
    print(f"  {label}: n={n}mo  Sharpe={sh:.3f}  MaxDD={md:.1%}  NegYrs={ny}  Cumul={cum:.1%}")
    return {"sharpe": round(sh,3), "maxdd": round(md,4), "neg_yrs": ny,
            "cumul": round(cum,3), "n_months": n}


# ── SPY benchmark ─────────────────────────────────────────────────────────────
spy_cp = CACHE_DIR / "h221_SPY_monthly.parquet"
if spy_cp.exists():
    spy_ret = pd.read_parquet(spy_cp)["ret"]
    spy_ret.index = pd.to_datetime(spy_ret.index).tz_localize(None)
else:
    spy_raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
    if isinstance(spy_raw.columns, pd.MultiIndex):
        spy_raw = spy_raw.xs("SPY", axis=1, level=1)
    col = "Close" if "Close" in spy_raw.columns else "close"
    spy_ret = spy_raw[col].resample("ME").last().pct_change()
    spy_ret.index = pd.to_datetime(spy_ret.index).tz_localize(None)
    pd.DataFrame({"ret": spy_ret}).to_parquet(spy_cp)

spy_oos_sh = sharpe(spy_ret.loc[OOS_START:OOS_END].dropna())


# ── Results ───────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("H222A — PIOTROSKI F-SCORE RESULTS")
print("="*60)
fa_is  = eval_period(fscore_rets, IS_START,  IS_END,  "IS ")
fa_oos = eval_period(fscore_rets, OOS_START, OOS_END, "OOS")
print(f"  SPY OOS Sharpe: {spy_oos_sh:.3f}")

print("\n" + "="*60)
print("H222B — GP/ASSETS (NOVY-MARX) RESULTS")
print("="*60)
gb_is  = eval_period(gpa_rets, IS_START,  IS_END,  "IS ")
gb_oos = eval_period(gpa_rets, OOS_START, OOS_END, "OOS")
print(f"  SPY OOS Sharpe: {spy_oos_sh:.3f}")

# ── Correlation with H192-D BAB ───────────────────────────────────────────────
bab_cp = CACHE_DIR / "h192_bab_rets.parquet"
corr_fscore_bab = None
if bab_cp.exists():
    bab_rets = pd.read_parquet(bab_cp).squeeze()
    bab_rets.index = pd.to_datetime(bab_rets.index).tz_localize(None)
    bab_oos = bab_rets.loc[OOS_START:OOS_END].dropna()
    fscore_oos_common = fscore_rets.loc[OOS_START:OOS_END].reindex(bab_oos.index).dropna()
    if len(fscore_oos_common) >= 6:
        corr_fscore_bab = float(fscore_oos_common.corr(bab_oos.reindex(fscore_oos_common.index)))
        print(f"\nCorr(H222A F-Score, H192-D BAB) OOS: {corr_fscore_bab:.3f}")
    else:
        print("\nInsufficient overlap with BAB for correlation")
else:
    print("\nH192-D BAB cache not found — skipping correlation")

# ── F-Score distribution ──────────────────────────────────────────────────────
print("\nF-Score distribution (all available rebalance years, 30 stocks):")
all_fscores = fscore_df.stack().dropna()
dist = all_fscores.value_counts().sort_index()
for score, cnt in dist.items():
    print(f"  Score {int(score)}: {cnt} stock-years")

# ── Top picks by GP/Assets ────────────────────────────────────────────────────
print("\nTop-6 by GP/Assets by rebalance year:")
for yr in gpa_df.index:
    top = gpa_df.loc[yr].dropna().nlargest(6)
    if not top.empty:
        print(f"  {yr}: {', '.join([f'{t}({v:.2f})' for t, v in top.items()])}")

# ── Data limitation assessment ────────────────────────────────────────────────
oos_months = fa_oos["n_months"]
data_blocked = oos_months < 12
if data_blocked:
    status_note = "DATA_BLOCKED — insufficient OOS history (yfinance only 5yr; need FY2010+ for IS/OOS)"
else:
    status_note = "sufficient"

fa_confirmed = (not data_blocked) and fa_oos["sharpe"] >= CONFIRM_THRESHOLD
gb_confirmed = (not data_blocked) and gb_oos["sharpe"] >= CONFIRM_THRESHOLD

print(f"\n{'='*60}")
print("STATUS:")
if data_blocked:
    print(f"  ⛔ DATA_BLOCKED: Only {oos_months} OOS months available")
    print(f"     yfinance gives FY2021-2025 only; quality factor needs 10+ year IS history")
    print(f"     To unblock: use SEC EDGAR XBRL (10-K filings) for FY2010+ history")
else:
    print(f"  H222A F-Score  : {'✅ CONFIRMED' if fa_confirmed else '❌ NOT CONFIRMED'} (OOS Sharpe {fa_oos['sharpe']:.3f})")
    print(f"  H222B GP/Assets: {'✅ CONFIRMED' if gb_confirmed else '❌ NOT CONFIRMED'} (OOS Sharpe {gb_oos['sharpe']:.3f})")
print(f"  Confirm threshold: {CONFIRM_THRESHOLD}")

results = {
    "hypothesis": "H222",
    "data_source": "yfinance (FY2021-2025 only; FMP legacy blocked)",
    "data_blocked": data_blocked,
    "data_blocked_reason": "yfinance provides 5yr history; quality factor requires FY2010+ for robust IS/OOS" if data_blocked else None,
    "sub_hypotheses": {
        "H222A_fscore": {"is": fa_is, "oos": fa_oos, "confirmed": fa_confirmed},
        "H222B_gpa":    {"is": gb_is, "oos": gb_oos, "confirmed": gb_confirmed},
    },
    "spy_oos_sharpe": round(spy_oos_sh, 3),
    "corr_fscore_bab": round(corr_fscore_bab, 3) if corr_fscore_bab is not None else None,
    "confirm_threshold": CONFIRM_THRESHOLD,
    "overall_confirmed": fa_confirmed or gb_confirmed,
    "unblock_path": "SEC EDGAR XBRL: financials/income-statement/AAPL.json for FY2010-2020; or Polygon fundamentals (paid tier)",
}

out = RESULT_DIR / "h222_results.json"
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved → {out}")
