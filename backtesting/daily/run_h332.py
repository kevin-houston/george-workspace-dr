"""
H332 — QuantaAlpha: Evolutionary Alpha Mining on H198 Universe
==============================================================
Source: arXiv:2602.07085 — "QuantaAlpha: Trajectory-Level Optimization for
Evolutionary Alpha Mining with Large Language Models" (2026)

Simplified version: no LLM in the loop.
Population of 20 alpha expressions (parameter variants of momentum/vol signals).
Evolutionary search over 5 generations on IS, single OOS run.

Universe: H198 30-stock S&P 500 universe
IS: 2013-2020 | OOS: 2021-2026
Gate: OOS Sharpe > H198 1.174 AND IC > 0.05
"""
import warnings
warnings.filterwarnings("ignore")
import json, copy, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path
from scipy.stats import spearmanr

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
N_GENERATIONS = 5
POP_SIZE      = 20
TOP_K         = 1
TC            = 0.001  # 10bps one-way

rng = np.random.default_rng(42)

# ── Data ──────────────────────────────────────────────────────────────────────
print("Downloading price data…")
prices = yf.download(UNIVERSE + ["SPY"], start=DATA_START, end=DATA_END,
                     auto_adjust=True, progress=False)['Close']
prices = prices.ffill()
monthly = prices.resample('ME').last()
ret_all = monthly.pct_change()
ret = ret_all[UNIVERSE]
spy_ret = ret_all['SPY']

# ── Signal functions ──────────────────────────────────────────────────────────
def compute_signal(monthly_px, gene):
    n_long  = gene['n_long']
    n_skip  = gene['n_skip']
    vol_adj = gene.get('vol_adj', False)
    reverse = gene.get('reverse', False)

    sig = monthly_px.shift(n_skip) / monthly_px.shift(n_skip + n_long) - 1

    if vol_adj:
        vol = monthly_px.pct_change().rolling(12).std()
        sig = sig / (vol + 1e-8)

    if gene.get('blend') is not None:
        sig2 = compute_signal(monthly_px, gene['blend'])
        w = gene.get('blend_weight', 0.5)
        sig = (1 - w) * sig + w * sig2

    return -sig if reverse else sig

# ── Backtest ──────────────────────────────────────────────────────────────────
def backtest(signal_df, ret_df, start, end):
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior = signal_df.index[signal_df.index < dt]
        if len(prior) == 0:
            continue
        sig = signal_df.loc[prior[-1]][UNIVERSE].dropna()
        if len(sig) < TOP_K:
            continue
        holdings = set(sig.nlargest(TOP_K).index)
        turnover  = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
        r = ret_df.loc[dt, list(holdings)].mean() - turnover * TC * 2
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

def sharpe(s):
    if len(s) < 6 or s.std() < 1e-10:
        return 0.0
    return float(s.mean() / s.std() * np.sqrt(12))

def mean_ic(signal_df, ret_df, start, end):
    ics = []
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior = signal_df.index[signal_df.index < dt]
        if len(prior) == 0: continue
        s = signal_df.loc[prior[-1]][UNIVERSE].dropna()
        r = ret_df.loc[dt].dropna()
        common = s.index.intersection(r.index)
        if len(common) < 5: continue
        ic, _ = spearmanr(s[common].rank(), r[common].rank())
        if not np.isnan(ic): ics.append(ic)
    return float(np.mean(ics)) if ics else 0.0

# ── Initial population ────────────────────────────────────────────────────────
def seed_population():
    pop = []
    for n_long in [3, 6, 9, 12]:
        for n_skip in [0, 1, 2]:
            pop.append({'n_long': n_long, 'n_skip': n_skip, 'vol_adj': False})
    for n_long in [6, 12]:
        pop.append({'n_long': n_long, 'n_skip': 1, 'vol_adj': True})
    # Blends of momentum windows
    pop.append({'n_long': 6, 'n_skip': 1, 'vol_adj': False,
                'blend': {'n_long': 12, 'n_skip': 1, 'vol_adj': False}, 'blend_weight': 0.5})
    pop.append({'n_long': 6, 'n_skip': 1, 'vol_adj': True,
                'blend': {'n_long': 3,  'n_skip': 0, 'vol_adj': False}, 'blend_weight': 0.3})
    # Short-term reversal as diversifier
    pop.append({'n_long': 1, 'n_skip': 0, 'vol_adj': False, 'reverse': True})
    return pop[:POP_SIZE]

def mutate(gene):
    g = copy.deepcopy(gene)
    m = int(rng.integers(0, 6))
    if m == 0:
        g['n_long'] = int(rng.choice([3, 6, 9, 12]))
    elif m == 1:
        g['n_skip'] = int(rng.integers(0, 3))
    elif m == 2:
        g['vol_adj'] = not g.get('vol_adj', False)
    elif m == 3:
        if g.get('blend') is None:
            g['blend'] = {'n_long': int(rng.choice([3, 6, 12])), 'n_skip': 1, 'vol_adj': False}
            g['blend_weight'] = float(rng.uniform(0.2, 0.8))
        else:
            g.pop('blend', None); g.pop('blend_weight', None)
    elif m == 4 and g.get('blend') is not None:
        g['blend_weight'] = float(rng.uniform(0.2, 0.8))
    elif m == 5:
        g['n_long'] = max(1, g['n_long'] + int(rng.integers(-2, 3)))
    return g

# ── Evolutionary search ───────────────────────────────────────────────────────
population = seed_population()
while len(population) < POP_SIZE:
    population.append(mutate(copy.deepcopy(rng.choice(population))))

best_gene, best_is_sh = None, -999.0

for gen in range(N_GENERATIONS):
    fits = []
    for gene in population:
        sig = compute_signal(monthly[UNIVERSE], gene)
        bt  = backtest(sig, ret, IS_START, IS_END)
        fits.append(sharpe(bt))

    ranked = sorted(zip(fits, population), key=lambda x: -x[0])
    top_sh, top_gene = ranked[0]
    if top_sh > best_is_sh:
        best_is_sh  = top_sh
        best_gene   = copy.deepcopy(top_gene)
    print(f"  Gen {gen+1}: best IS Sharpe={top_sh:.3f}  gene={top_gene}")

    survivors = [g for _, g in ranked[:5]]
    new_pop   = list(survivors)
    while len(new_pop) < POP_SIZE:
        new_pop.append(mutate(copy.deepcopy(rng.choice(survivors))))
    population = new_pop

print(f"\nBest evolved gene (IS Sharpe {best_is_sh:.3f}):\n  {best_gene}")

# ── Baseline (H198 6-1m) ──────────────────────────────────────────────────────
baseline_gene = {'n_long': 6, 'n_skip': 1, 'vol_adj': False}
bl_sig  = compute_signal(monthly[UNIVERSE], baseline_gene)
bl_oos  = backtest(bl_sig, ret, OOS_START, OOS_END)
bl_sh   = sharpe(bl_oos)
print(f"\nH198 baseline OOS Sharpe: {bl_sh:.3f}")

# ── OOS evaluation ────────────────────────────────────────────────────────────
best_sig     = compute_signal(monthly[UNIVERSE], best_gene)
best_is_ret  = backtest(best_sig, ret, IS_START, IS_END)
best_oos_ret = backtest(best_sig, ret, OOS_START, OOS_END)

best_is_sh_check = sharpe(best_is_ret)
best_oos_sh      = sharpe(best_oos_ret)
best_oos_maxdd   = float(
    (best_oos_ret + 1).cumprod().div(
        (best_oos_ret + 1).cumprod().cummax()
    ).sub(1).min())
best_oos_cagr  = float((1 + best_oos_ret).prod() ** (12 / max(len(best_oos_ret), 1)) - 1)
wf             = best_oos_sh / best_is_sh_check if best_is_sh_check > 0 else 0.0
oos_ic         = mean_ic(best_sig, ret, OOS_START, OOS_END)
neg_years      = int(((1 + best_oos_ret).resample('YE').prod() - 1 < 0).sum())

spy_oos = spy_ret[(spy_ret.index >= OOS_START) & (spy_ret.index <= OOS_END)]
corr_spy = float(best_oos_ret.corr(spy_oos.reindex(best_oos_ret.index)))

pass_gate = best_oos_sh > H198_SHARPE and oos_ic > 0.05
verdict   = "CONFIRMED" if pass_gate else "NOT CONFIRMED"

print(f"\n{'='*60}")
print(f"H332 Results:")
print(f"  IS Sharpe : {best_is_sh_check:.3f}  OOS Sharpe: {best_oos_sh:.3f}")
print(f"  OOS CAGR  : {best_oos_cagr:.1%}  MaxDD: {best_oos_maxdd:.1%}  NegYrs: {neg_years}")
print(f"  IC (OOS)  : {oos_ic:.3f}  WF ratio: {wf:.3f}")
print(f"  Corr(SPY) : {corr_spy:.3f}")
print(f"  Baseline OOS Sharpe: {bl_sh:.3f}  Gate: >{H198_SHARPE} AND IC>0.05")
print(f"  Verdict   : {verdict}")

results = {
    "hypothesis": "H332",
    "best_gene": str(best_gene),
    "is_stats":  {"sharpe": round(best_is_sh_check, 3), "cagr": round(best_oos_cagr, 3)},
    "oos_stats": {"sharpe": round(best_oos_sh, 3), "cagr": round(best_oos_cagr, 3),
                  "maxdd": round(best_oos_maxdd, 3), "neg_years": neg_years},
    "oos_ic": round(oos_ic, 3),
    "wf_ratio": round(wf, 3),
    "corr_spy_oos": round(corr_spy, 3),
    "baseline_oos_sharpe": round(bl_sh, 3),
    "verdict": verdict,
}
(RESULT_DIR / "h332_results.json").write_text(json.dumps(results, indent=2))
print(f"Saved → h332_results.json")
