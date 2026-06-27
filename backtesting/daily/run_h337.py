"""
H337 — Quality-Momentum Dual Ranking on H198 Universe
======================================================
Source: Novy-Marx (2013) "The Other Side of Value: The Gross Profitability
        Premium" (JFE); Asness, Frazzini & Pedersen (2014) "Quality Minus Junk".
        Fama & French (1993, 2015) — quality factors complement momentum.

Hypothesis: stocks ranked highly by BOTH momentum (6-1m) AND quality
outperform stocks with only momentum signal.

Quality signal: computed from yfinance quarterly financial statements.
  - Gross Profitability (GP/A) = Gross Profit TTM / Total Assets (Novy-Marx 2013)
  - Return on Equity (ROE) = Net Income TTM / Avg Total Equity

Data note: yfinance quarterly financials go back ~4-5 years with coverage gaps.
3-month reporting lag applied (use Q ending at t-3 months).

Variants:
  A: momentum only (H198 baseline — sanity check)
  B: dual rank 0.5*mom + 0.5*gp_a (Novy-Marx gross profitability)
  C: dual rank 0.7*mom + 0.3*gp_a (momentum-dominant)
  D: dual rank 0.5*mom + 0.5*roe
  E: FILTER — top-1 momentum only if GP/A > cross-sectional median

Universe: H198 30-stock S&P 500 (survivorship bias caveat).
IS: 2013-2020 | OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 baseline)
"""
import warnings
warnings.filterwarnings("ignore")
import json, os, time, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

H198_SHARPE = 1.174
TC          = 0.001
TOP_K       = 1

# ── Price data ────────────────────────────────────────────────────────────────
print("Downloading price data…")
raw     = yf.download(UNIVERSE + ["SPY"], start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)['Close'].ffill()
monthly = raw.resample('ME').last()
ret_all = monthly.pct_change()
ret     = ret_all[UNIVERSE]
spy_r   = ret_all['SPY']

# ── 6-1m momentum signal ─────────────────────────────────────────────────────
mom6 = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(7) - 1

# ── Fetch quarterly quality data via yfinance ─────────────────────────────────
CACHE_FILE = RESULT_DIR / "h337_quality_cache.json"

def fetch_quality():
    if CACHE_FILE.exists():
        print("Using cached quality data…")
        return json.loads(CACHE_FILE.read_text())

    print(f"Fetching quarterly financials for {len(UNIVERSE)} tickers…")
    data = {}
    for i, ticker in enumerate(UNIVERSE):
        try:
            t = yf.Ticker(ticker)
            # Quarterly financials: columns are dates (quarter-end)
            qf  = t.quarterly_financials  # rows=items, cols=dates
            qbs = t.quarterly_balance_sheet
            records = []
            if qf is not None and not qf.empty and qbs is not None and not qbs.empty:
                # Align columns
                cols_f  = qf.columns.sort_values(ascending=True)
                cols_bs = qbs.columns.sort_values(ascending=True)
                for col in cols_f:
                    try:
                        # GP/A = Gross Profit (trailing 4Q) / Total Assets (latest Q)
                        # We compute TTM GP and TTM Revenue
                        idx_f = list(cols_f).index(col)
                        # Get up to 4 quarters ending at col
                        ttm_cols_f = cols_f[max(0, idx_f-3):idx_f+1]
                        gp_key  = 'Gross Profit'
                        ni_key  = 'Net Income'
                        rev_key = 'Total Revenue'
                        # Get values; handle missing
                        gp_ttm  = sum(float(qf.loc[gp_key, c]) for c in ttm_cols_f
                                      if gp_key in qf.index and c in qf.columns
                                      and not pd.isna(qf.loc[gp_key, c]))
                        ni_ttm  = sum(float(qf.loc[ni_key, c]) for c in ttm_cols_f
                                      if ni_key in qf.index and c in qf.columns
                                      and not pd.isna(qf.loc[ni_key, c]))
                        rev_ttm = sum(float(qf.loc[rev_key, c]) for c in ttm_cols_f
                                      if rev_key in qf.index and c in qf.columns
                                      and not pd.isna(qf.loc[rev_key, c]))
                        # Total Assets from balance sheet — nearest quarter
                        bs_prior = [c for c in cols_bs if c <= col]
                        ta = None
                        eq = None
                        if bs_prior:
                            last_bs = bs_prior[-1]
                            ta_key  = 'Total Assets'
                            eq_key  = 'Stockholders Equity'
                            if ta_key in qbs.index and not pd.isna(qbs.loc[ta_key, last_bs]):
                                ta = float(qbs.loc[ta_key, last_bs])
                            if eq_key in qbs.index and not pd.isna(qbs.loc[eq_key, last_bs]):
                                eq = float(qbs.loc[eq_key, last_bs])
                        gp_a  = gp_ttm / ta  if ta  and ta  > 0 else None
                        roe   = ni_ttm  / eq  if eq  and eq  > 0 else None
                        gp_m  = gp_ttm  / rev_ttm if rev_ttm and rev_ttm > 0 else None
                        records.append({
                            "date":  str(col.date()),
                            "gp_a":  gp_a,
                            "roe":   roe,
                            "gp_m":  gp_m,
                        })
                    except Exception:
                        continue
            data[ticker] = records
        except Exception as e:
            print(f"  {ticker}: {e}")
            data[ticker] = []
        if (i+1) % 10 == 0:
            print(f"  {i+1}/{len(UNIVERSE)} done")
        time.sleep(0.2)

    CACHE_FILE.write_text(json.dumps(data))
    print("Quality data cached.")
    return data

raw_quality = fetch_quality()

# ── Build monthly quality panels with 3-month reporting lag ──────────────────
all_dates = pd.date_range(start=DATA_START, end=DATA_END, freq='ME')

gpa_panel = pd.DataFrame(index=all_dates, columns=UNIVERSE, dtype=float)
roe_panel = pd.DataFrame(index=all_dates, columns=UNIVERSE, dtype=float)
gpm_panel = pd.DataFrame(index=all_dates, columns=UNIVERSE, dtype=float)

for ticker in UNIVERSE:
    records = raw_quality.get(ticker, [])
    if not records:
        continue
    ts_gpa, ts_roe, ts_gpm = {}, {}, {}
    for r in records:
        try:
            fy_end = pd.Timestamp(r["date"])
            avail  = fy_end + pd.DateOffset(days=90)  # 3-month lag
            if r["gp_a"] is not None: ts_gpa[avail] = r["gp_a"]
            if r["roe"]  is not None: ts_roe[avail]  = r["roe"]
            if r["gp_m"] is not None: ts_gpm[avail] = r["gp_m"]
        except Exception:
            continue
    for name, ts_dict, panel in [
        ("gpa", ts_gpa, gpa_panel),
        ("roe", ts_roe, roe_panel),
        ("gpm", ts_gpm, gpm_panel),
    ]:
        if not ts_dict: continue
        s = pd.Series(ts_dict).sort_index().dropna()
        if s.empty: continue
        for dt in all_dates:
            prior = s[s.index <= dt]
            if len(prior) > 0:
                panel.loc[dt, ticker] = float(prior.iloc[-1])

gpa_panel = gpa_panel.astype(float)
roe_panel = roe_panel.astype(float)
gpm_panel = gpm_panel.astype(float)

def coverage(panel):
    sub = panel[(panel.index >= IS_START)]
    return (~sub.isna()).mean().mean()

print(f"\nQuality data coverage (IS+OOS):")
print(f"  GP/A:       {coverage(gpa_panel):.1%}")
print(f"  ROE:        {coverage(roe_panel):.1%}")
print(f"  GP Margin:  {coverage(gpm_panel):.1%}")

# ── Helper functions ──────────────────────────────────────────────────────────
def sharpe(s):
    if len(s) < 6 or s.std() < 1e-10: return 0.0
    return float(s.mean() / s.std() * np.sqrt(12))

def maxdd(s):
    c = (1 + s).cumprod()
    return float(c.div(c.cummax()).sub(1).min())

def cagr(s):
    return float((1 + s).prod() ** (12 / max(len(s), 1)) - 1)

def neg_years(s):
    if not isinstance(s.index, pd.DatetimeIndex) or len(s) < 3: return 0
    try:
        return int(((1 + s).resample('YE').prod() - 1 < 0).sum())
    except Exception:
        return 0

# ── Backtest engines ──────────────────────────────────────────────────────────
def backtest_composite(w_mom, w_qual, qual_panel, ret_df, start, end):
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior_m = mom6.index[mom6.index < dt]
        prior_q = qual_panel.index[qual_panel.index < dt]
        if len(prior_m) == 0 or len(prior_q) == 0: continue
        m_sig  = mom6.loc[prior_m[-1]].dropna()
        q_sig  = qual_panel.loc[prior_q[-1]].dropna()
        common = m_sig.index.intersection(q_sig.index)
        if len(common) < TOP_K:
            # Fall back to pure momentum if quality data missing
            common = m_sig.index
            if len(common) < TOP_K: continue
            composite = m_sig[common].rank(pct=True)
        else:
            m_rank = m_sig[common].rank(pct=True)
            q_rank = q_sig[common].rank(pct=True)
            composite = w_mom * m_rank + w_qual * q_rank
        holdings = set(composite.nlargest(TOP_K).index)
        turnover = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
        r = ret_df.loc[dt, list(holdings)].mean() - turnover * TC * 2
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

def backtest_filter_qual(qual_panel, ret_df, start, end):
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior_m = mom6.index[mom6.index < dt]
        prior_q = qual_panel.index[qual_panel.index < dt]
        if len(prior_m) == 0 or len(prior_q) == 0: continue
        m_sig  = mom6.loc[prior_m[-1]].dropna()
        q_sig  = qual_panel.loc[prior_q[-1]].dropna()
        common = m_sig.index.intersection(q_sig.index)
        # Top-1 by momentum from full universe
        top_t  = m_sig.dropna().nlargest(TOP_K).index[0]
        if len(common) >= 2:
            median_q = q_sig[common].median()
            top_q    = q_sig.get(top_t, np.nan)
            if pd.notna(top_q) and top_q > median_q:
                enter = True
            else:
                enter = False
        else:
            enter = True  # no quality data → default to momentum
        if enter:
            holdings = {top_t}
            turnover = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
            r = ret_df.loc[dt, top_t] - turnover * TC * 2
        else:
            turnover = len(prev) / (2 * TOP_K) if prev else 0
            r = -turnover * TC * 2
            holdings = set()
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

def backtest_mom_only(ret_df, start, end):
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior = mom6.index[mom6.index < dt]
        if len(prior) == 0: continue
        sig = mom6.loc[prior[-1]].dropna()
        if len(sig) < TOP_K: continue
        holdings  = set(sig.nlargest(TOP_K).index)
        turnover  = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
        r = ret_df.loc[dt, list(holdings)].mean() - turnover * TC * 2
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

# ── Baseline ──────────────────────────────────────────────────────────────────
bl_oos  = backtest_mom_only(ret, OOS_START, OOS_END)
bl_sh   = sharpe(bl_oos)
spy_oos = spy_r[(spy_r.index >= OOS_START) & (spy_r.index <= OOS_END)]
print(f"\nH198 baseline OOS Sharpe: {bl_sh:.3f}")
print(f"SPY OOS Sharpe:           {sharpe(spy_oos):.3f}")

# ── Evaluate variants ─────────────────────────────────────────────────────────
print(f"\n{'Var':<22} {'IS_Sh':>7} {'OOS_Sh':>8} {'CAGR':>8} {'MaxDD':>7} "
      f"{'NegYr':>6} {'WF':>6} {'CorrBL':>7} {'CorrSPY':>8} {'Verdict'}")
print("-" * 95)

results_all = {}
best_sh, best_var = H198_SHARPE, None

def eval_variant(tag, is_ret, oos_ret):
    global best_sh, best_var
    if len(oos_ret) < 3:
        print(f"  {tag:<22}  SKIP — insufficient data ({len(oos_ret)} months)")
        results_all[f'variant_{tag}'] = {'skip': True, 'reason': 'insufficient_data', 'pass_gate': False}
        return
    is_sh  = sharpe(is_ret)
    oos_sh = sharpe(oos_ret)
    o_cagr = cagr(oos_ret)
    o_mdd  = maxdd(oos_ret)
    o_neg  = neg_years(oos_ret)
    wf     = oos_sh / is_sh if is_sh > 0 else 0.0
    corr_bl  = float(oos_ret.corr(bl_oos.reindex(oos_ret.index)))
    corr_spy = float(oos_ret.corr(spy_oos.reindex(oos_ret.index)))
    passes = oos_sh > H198_SHARPE
    if oos_sh > best_sh: best_sh = oos_sh; best_var = tag
    print(f"  {tag:<22} {is_sh:>7.3f} {oos_sh:>8.3f} {o_cagr:>8.1%} {o_mdd:>7.1%} "
          f"{o_neg:>6d} {wf:>6.3f} {corr_bl:>7.3f} {corr_spy:>8.3f}  {'PASS' if passes else 'fail'}")
    results_all[f'variant_{tag}'] = {
        'is_sharpe': round(is_sh,3), 'oos_sharpe': round(oos_sh,3),
        'oos_cagr': round(o_cagr,3), 'oos_maxdd': round(o_mdd,3),
        'neg_years': o_neg, 'wf_ratio': round(wf,3),
        'corr_baseline': round(corr_bl,3), 'corr_spy': round(corr_spy,3),
        'pass_gate': passes,
    }

eval_variant('A (mom only)',
             backtest_mom_only(ret, IS_START, IS_END),
             bl_oos)

eval_variant('B (0.5mom+0.5gp_a)',
             backtest_composite(0.5, 0.5, gpa_panel, ret, IS_START, IS_END),
             backtest_composite(0.5, 0.5, gpa_panel, ret, OOS_START, OOS_END))

eval_variant('C (0.7mom+0.3gp_a)',
             backtest_composite(0.7, 0.3, gpa_panel, ret, IS_START, IS_END),
             backtest_composite(0.7, 0.3, gpa_panel, ret, OOS_START, OOS_END))

eval_variant('D (0.5mom+0.5roe)',
             backtest_composite(0.5, 0.5, roe_panel, ret, IS_START, IS_END),
             backtest_composite(0.5, 0.5, roe_panel, ret, OOS_START, OOS_END))

eval_variant('E (mom + gp/a filter)',
             backtest_filter_qual(gpa_panel, ret, IS_START, IS_END),
             backtest_filter_qual(gpa_panel, ret, OOS_START, OOS_END))

any_pass = any(v.get('pass_gate', False) for v in results_all.values())
verdict  = "CONFIRMED" if any_pass else "NOT CONFIRMED"
print(f"\nH198 gate: >{H198_SHARPE}  Baseline OOS Sharpe: {bl_sh:.3f}")
print(f"Verdict: {verdict} (best variant {best_var}, OOS Sharpe {best_sh:.3f})")

results = {
    "hypothesis": "H337",
    "description": "Quality-Momentum Dual Ranking (GP/A and ROE from yfinance) on H198 Universe",
    "baseline_oos_sharpe": round(bl_sh, 3),
    "h198_gate": H198_SHARPE,
    "quality_coverage": {
        "gp_a": round(coverage(gpa_panel), 3),
        "roe":  round(coverage(roe_panel), 3),
        "gp_m": round(coverage(gpm_panel), 3),
    },
    "variants": results_all,
    "best_variant": best_var,
    "best_oos_sharpe": round(best_sh, 3),
    "verdict": verdict,
}
(RESULT_DIR / "h337_results.json").write_text(json.dumps(results, indent=2))
print(f"Saved → h337_results.json")
