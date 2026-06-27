"""
H338 — Multi-Asset Trend + Carry: Combined Bond+Equity ETF Universe
====================================================================
Source: Koijen, Moskowitz, Pedersen & Vrugt (2018) "Carry" (JFE);
        Asness, Moskowitz & Pedersen (2013) "Value and Momentum Everywhere".
        Task specification: combine 12m momentum signal with carry signal
        (yield/dividend yield for bonds/equity ETFs).

Motivation: H045 (bond rotation, OOS Sharpe 1.351) and H026 (equity rotation)
work independently. A combined universe with BOTH bonds and equity ETFs, ranked
by a blended momentum+carry signal, might capture cross-asset rotation alpha
that neither standalone achieves.

Carry signal: trailing 12-month dividend yield (TTM dividends / price), lagged 1m.
Momentum signal: 12-month price momentum, lagged 1m (price[t-1]/price[t-13]-1).
The carry acts as a tiebreaker when momentum signals are similar.

Universe (17 ETFs):
  Bonds: SHY, IEI, IEF, TLT, TIP, HYG, LQD  (H045 bond universe)
  Equity/Alternatives: XLK, XLV, XLE, XLF, XLU, GLD, DBC, EEM, QQQ, SPY
  (subset of H026 equity universe — diversified across sectors)
  Cash escape: BIL

Variants:
  A: momentum only (12m), top-2 from combined universe
  B: carry only (TTM yield), top-2 from combined universe
  C: 0.7 momentum + 0.3 carry, top-2  (momentum-dominant)
  D: 0.5 momentum + 0.5 carry, top-2  (equal blend)
  E: 0.7 momentum + 0.3 carry, top-3  (wider selection)
  F: 0.5 momentum + 0.5 carry, top-2 + absolute momentum filter
     (asset only eligible if its 12m return > 0, else BIL replaces)

IS: 2008-2017 | OOS: 2018-2026
Gate: OOS Sharpe > 1.351 (H045 baseline benchmark)
TC: 10bps one-way
"""
import warnings
warnings.filterwarnings("ignore")
import json, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

BOND_ETFS   = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
EQUITY_ETFS = ["XLK", "XLV", "XLE", "XLF", "XLU", "GLD", "DBC", "EEM", "QQQ", "SPY"]
UNIVERSE    = BOND_ETFS + EQUITY_ETFS
CASH        = "BIL"

DATA_START = "2005-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2008-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

H045_SHARPE = 1.351
AGG_SHARPE_BH = 0.298   # reference
TC          = 0.001
TOP_K_BASE  = 2

# ── Data ──────────────────────────────────────────────────────────────────────
print("Downloading ETF price data…")
all_tickers = UNIVERSE + [CASH]
adj_close = yf.download(all_tickers, start=DATA_START, end=DATA_END,
                        auto_adjust=True, progress=False)['Close'].ffill()

monthly_adj = adj_close.resample('ME').last()
ret_all     = monthly_adj.pct_change()
ret         = ret_all[UNIVERSE]
bil_r       = ret_all[CASH]

# ── Carry signal: TTM dividend yield via individual Ticker.dividends ──────────
print("Fetching dividend history for carry signal…")
divs_all = {}
for tk in UNIVERSE:
    try:
        t = yf.Ticker(tk)
        d = t.dividends  # DatetimeIndex Series of dividend payments
        if d is not None and len(d) > 0:
            # Convert to UTC-naive
            if hasattr(d.index, 'tz') and d.index.tz is not None:
                d.index = d.index.tz_convert(None)
            divs_all[tk] = d
        else:
            divs_all[tk] = pd.Series(dtype=float)
    except Exception:
        divs_all[tk] = pd.Series(dtype=float)

# Reindex all dividend series to daily, sum to monthly
daily_idx = pd.date_range(start=DATA_START, end=DATA_END, freq='D')
divs_df   = pd.DataFrame(0.0, index=daily_idx, columns=UNIVERSE)
for tk, s in divs_all.items():
    if len(s) > 0:
        valid = s[s.index.isin(daily_idx)]
        divs_df.loc[valid.index, tk] = valid.values

divs_monthly = divs_df.resample('ME').sum()
ttm_divs     = divs_monthly.rolling(12).sum()   # TTM dividend sum

# Carry = TTM div / adj close price at that month-end (lagged 1m)
carry_raw = ttm_divs / monthly_adj[UNIVERSE]
carry     = carry_raw.shift(1)  # lagged 1 month to avoid look-ahead

n_with_divs = sum(1 for tk in UNIVERSE if (ttm_divs[tk] > 0).any())
print(f"  Tickers with dividend history: {n_with_divs}/{len(UNIVERSE)}")

# ── Momentum signal: 12m price return, lagged 1m ─────────────────────────────
mom12 = monthly_adj[UNIVERSE].shift(1) / monthly_adj[UNIVERSE].shift(13) - 1

# ── Helper functions ──────────────────────────────────────────────────────────
def sharpe(s):
    if len(s) < 6 or s.std() < 1e-10: return 0.0
    return float(s.mean() / s.std() * np.sqrt(12))

def maxdd(s):
    c = (1 + s).cumprod()
    return float(c.div(c.cummax()).sub(1).min())

def cagr(s):
    return float((1 + s).prod() ** (12 / max(len(s), 1)) - 1)

# ── Backtest engine ───────────────────────────────────────────────────────────
def backtest(w_mom, w_carry, top_k, use_abs_filter, ret_df, start, end):
    """
    General backtest: composite = w_mom*mom_rank + w_carry*carry_rank.
    If use_abs_filter: only include assets with 12m mom > 0 (else include BIL slots).
    """
    rets, dates = [], []
    prev = set()
    eval_dates = ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index
    for dt in eval_dates:
        prior_m = mom12.index[mom12.index < dt]
        prior_c = carry.index[carry.index < dt]
        if len(prior_m) == 0 or len(prior_c) == 0: continue

        sig_m  = mom12.loc[prior_m[-1]]
        sig_c  = carry.loc[prior_c[-1]]
        common = sig_m.dropna().index.intersection(sig_c.dropna().index)
        if len(common) < 2: continue

        if use_abs_filter:
            # Only eligible if 12m return > 0
            common = common[sig_m[common] > 0]

        if len(common) == 0:
            # All momentum negative → hold cash
            rets.append(bil_r.get(dt, 0.0))
            dates.append(dt)
            prev = {CASH}
            continue

        m_rank = sig_m[common].rank(pct=True)
        c_rank = sig_c[common].rank(pct=True)
        composite = w_mom * m_rank + w_carry * c_rank

        n_pick    = min(top_k, len(common))
        holdings  = set(composite.nlargest(n_pick).index)
        turnover  = len(holdings.symmetric_difference(prev)) / (2 * max(top_k, 1))
        r = ret_df.loc[dt, list(holdings)].mean() - turnover * TC * 2
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

# ── AGG B&H baseline ──────────────────────────────────────────────────────────
agg_oos  = ret_all['TIP'][(ret_all.index >= OOS_START) & (ret_all.index <= OOS_END)]
# Use blend proxy instead: avg of bond ETFs
bond_oos = ret[(ret.index >= OOS_START) & (ret.index <= OOS_END)][BOND_ETFS].mean(axis=1)
spy_oos  = ret_all['SPY'][(ret_all.index >= OOS_START) & (ret_all.index <= OOS_END)]
print(f"Bond EW OOS Sharpe: {sharpe(bond_oos):.3f}")
print(f"SPY B&H OOS Sharpe: {sharpe(spy_oos):.3f}")

# ── Evaluate variants ─────────────────────────────────────────────────────────
variant_configs = [
    ('A', 1.0, 0.0, TOP_K_BASE, False, 'Momentum only top-2'),
    ('B', 0.0, 1.0, TOP_K_BASE, False, 'Carry only top-2'),
    ('C', 0.7, 0.3, TOP_K_BASE, False, '0.7mom+0.3carry top-2'),
    ('D', 0.5, 0.5, TOP_K_BASE, False, '0.5mom+0.5carry top-2'),
    ('E', 0.7, 0.3, 3,          False, '0.7mom+0.3carry top-3'),
    ('F', 0.5, 0.5, TOP_K_BASE, True,  '0.5mom+0.5carry top-2+abs filter'),
]

print(f"\n{'Var':<4} {'Config':<28} {'IS_Sh':>7} {'OOS_Sh':>8} {'CAGR':>8} "
      f"{'MaxDD':>7} {'NegYr':>6} {'WF':>6} {'Verdict'}")
print("-" * 95)

results_all = {}
best_sh, best_var = H045_SHARPE, None

for tag, w_m, w_c, top_k, abs_f, desc in variant_configs:
    is_r  = backtest(w_m, w_c, top_k, abs_f, ret, IS_START, IS_END)
    oos_r = backtest(w_m, w_c, top_k, abs_f, ret, OOS_START, OOS_END)
    is_sh  = sharpe(is_r)
    oos_sh = sharpe(oos_r)
    o_cagr = cagr(oos_r)
    o_mdd  = maxdd(oos_r)
    o_neg  = int(((1 + oos_r).resample('YE').prod() - 1 < 0).sum())
    wf     = oos_sh / is_sh if is_sh > 0 else 0.0
    passes = oos_sh > H045_SHARPE
    if oos_sh > best_sh: best_sh = oos_sh; best_var = tag
    print(f"  {tag:<3} {desc:<28} {is_sh:>7.3f} {oos_sh:>8.3f} {o_cagr:>8.1%} "
          f"{o_mdd:>7.1%} {o_neg:>6d} {wf:>6.3f}  {'PASS' if passes else 'fail'}")
    results_all[f'variant_{tag}'] = {
        'description': desc, 'w_mom': w_m, 'w_carry': w_c,
        'top_k': top_k, 'abs_filter': abs_f,
        'is_sharpe': round(is_sh,3), 'oos_sharpe': round(oos_sh,3),
        'oos_cagr': round(o_cagr,3), 'oos_maxdd': round(o_mdd,3),
        'neg_years': o_neg, 'wf_ratio': round(wf,3),
        'pass_gate': passes,
    }

any_pass = any(v['pass_gate'] for v in results_all.values())
verdict  = "CONFIRMED" if any_pass else "NOT CONFIRMED"
print(f"\nH045 gate: >{H045_SHARPE}")
print(f"Verdict: {verdict} (best variant {best_var}, OOS Sharpe {best_sh:.3f})")

results = {
    "hypothesis": "H338",
    "description": "Multi-Asset Trend + Carry on Combined Bond+Equity Universe",
    "h045_gate": H045_SHARPE,
    "universe_size": len(UNIVERSE),
    "variants": results_all,
    "best_variant": best_var,
    "best_oos_sharpe": round(best_sh, 3),
    "verdict": verdict,
}
(RESULT_DIR / "h338_results.json").write_text(json.dumps(results, indent=2))
print(f"Saved → h338_results.json")
