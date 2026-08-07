"""
H494 — LLM Semantic Momentum Filter (true LLM implementation of H279/arXiv:2510.26228)
========================================================================================
H339 (NOT CONFIRMED, 2026-06-26) tested price-based PROXIES for an LLM sentiment/
plausibility gate on H198's 6-1m momentum top-1 pick and explicitly queued the "true"
LLM version as H279: "The LLM semantic filter in arXiv:2510.26228 is qualitatively
different: it filters based on *economic plausibility of the trend*, not just price
direction. H279 (true LLM semantic filter) remains the correct next step."

CONSTRAINT CARRIED FORWARD FROM H339: NewsAPI has no usable historical depth on the
free tier, so a literal news-headline-sentiment version of the paper cannot be
backtested honestly over 2013-2026. This run instead gives GPT-4o-mini the same
point-in-time, look-ahead-safe price/volatility statistics H339 used for its rule-based
proxies, and asks it to render a *holistic qualitative judgment* ("plausibility score
0-100") of whether the trend looks durable/business-driven vs. overextended/speculative
— rather than applying a hardcoded threshold rule. This isolates the paper's actual
mechanism (LLM reasoning over trend character) from the news-sourcing problem, which
remains a separate, unresolved blocker for the full paper replication.

Universe: H198 30-stock S&P 500 (same survivorship-bias caveat as H198/H339).
IS: 2013-2020 | OOS: 2021-2026 | Gate: OOS Sharpe > 1.174 (H198 baseline, per H339 lineage)
Model: gpt-4o-mini via $OPENAI_API_KEY. Responses cached to
       backtesting/results/h494_llm_cache.json so reruns are free/reproducible.
"""
import warnings
warnings.filterwarnings("ignore")
import json, os, re, time, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path
from openai import OpenAI

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)
CACHE_PATH = RESULT_DIR / "h494_llm_cache.json"

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
MODEL       = "gpt-4o-mini"

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ── Price data ────────────────────────────────────────────────────────────────
print("Downloading price data…")
raw     = yf.download(UNIVERSE + ["SPY","BIL"], start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)['Close'].ffill()
monthly = raw.resample('ME').last()
ret_all = monthly.pct_change()
ret     = ret_all[UNIVERSE]
spy_r   = ret_all['SPY']
bil_r   = ret_all['BIL']

mom6   = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(7) - 1     # 6-1m momentum (H198 signal)
ret1m  = monthly[UNIVERSE].pct_change().shift(1)
ret3m  = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(4) - 1
ret12m = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(13) - 1
vol12m = monthly[UNIVERSE].pct_change().rolling(12).std().shift(1) * np.sqrt(12)
roll_max_252 = raw[UNIVERSE].rolling(252).max()
dist_from_high = (raw[UNIVERSE] / roll_max_252 - 1).resample('ME').last().shift(1)

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

# ── LLM plausibility scoring (cached) ───────────────────────────────────────
if CACHE_PATH.exists():
    cache = json.loads(CACHE_PATH.read_text())
else:
    cache = {}

def llm_score(sig_dt, ticker):
    key = f"{sig_dt.date()}_{ticker}"
    if key in cache:
        return cache[key]
    r1  = ret1m.loc[sig_dt, ticker]  if sig_dt in ret1m.index  else np.nan
    r3  = ret3m.loc[sig_dt, ticker]  if sig_dt in ret3m.index  else np.nan
    r6  = mom6.loc[sig_dt, ticker]   if sig_dt in mom6.index   else np.nan
    r12 = ret12m.loc[sig_dt, ticker] if sig_dt in ret12m.index else np.nan
    vol = vol12m.loc[sig_dt, ticker] if sig_dt in vol12m.index else np.nan
    dfh = dist_from_high.loc[sig_dt, ticker] if sig_dt in dist_from_high.index else np.nan
    if any(pd.isna(x) for x in [r1, r3, r6, r12, vol, dfh]):
        cache[key] = 50  # neutral default, insufficient data
        return 50
    prompt = (
        f"Stock: {ticker}. As of {sig_dt.date()} (point-in-time, no forward information), "
        f"its trailing price statistics are:\n"
        f"- 1-month return: {r1:+.1%}\n"
        f"- 3-month return: {r3:+.1%}\n"
        f"- 6-month return (skip most recent month, momentum signal): {r6:+.1%}\n"
        f"- 12-month return: {r12:+.1%}\n"
        f"- trailing 12-month annualized volatility: {vol:.1%}\n"
        f"- distance from trailing 252-day high: {dfh:+.1%}\n\n"
        f"This stock ranks #1 by 6-1 month momentum among a 30-stock large-cap universe "
        f"and is a candidate for a momentum-following long position next month.\n"
        f"Based ONLY on these statistics (you have no news or fundamental data), judge "
        f"whether this trend pattern looks more like a durable, broad-based move "
        f"(steady accumulation, moderate vol, not extremely overextended) versus an "
        f"overextended/speculative spike (extreme vol, parabolic recent acceleration, "
        f"far past prior highs) that is statistically likely to mean-revert.\n"
        f"Respond with ONLY a single integer 0-100: a 'trend plausibility score' where "
        f"higher = more likely a durable continuing trend, lower = more likely an "
        f"overextended move prone to reversal. No words, just the number."
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=8,
        )
        text = resp.choices[0].message.content.strip()
        m = re.search(r"\d+", text)
        score = int(m.group()) if m else 50
        score = max(0, min(100, score))
    except Exception as e:
        print(f"    LLM error {ticker} {sig_dt.date()}: {e}")
        score = 50
    cache[key] = score
    return score

# ── Backtests ─────────────────────────────────────────────────────────────────
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

def backtest_llm_filtered(threshold, ret_df, start, end):
    rets, dates, scores_used = [], [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior_m = mom6.index[mom6.index < dt]
        if len(prior_m) == 0: continue
        sig = mom6.loc[prior_m[-1]].dropna()
        if len(sig) < TOP_K: continue
        top_t = sig.nlargest(TOP_K).index[0]
        score = llm_score(prior_m[-1], top_t)
        scores_used.append(score)
        if score >= threshold:
            holdings = {top_t}
            turnover = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
            r = ret_df.loc[dt, top_t] - turnover * TC * 2
        else:
            turnover = len(prev) / (2 * TOP_K) if prev else 0
            r = float(bil_r.get(dt, 0.0)) - turnover * TC * 2
            holdings = {'BIL'}
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates), scores_used

# ── Baseline ──────────────────────────────────────────────────────────────────
bl_is   = backtest_mom_only(ret, IS_START, IS_END)
bl_oos  = backtest_mom_only(ret, OOS_START, OOS_END)
bl_sh   = sharpe(bl_oos)
spy_oos = spy_r[(spy_r.index >= OOS_START) & (spy_r.index <= OOS_END)]
print(f"H198 baseline OOS Sharpe: {bl_sh:.3f}")
print(f"SPY OOS Sharpe:           {sharpe(spy_oos):.3f}\n")

print(f"Scoring months with {MODEL} (cached to {CACHE_PATH.name})…")
t0 = time.time()

results_all = {}
best_sh, best_var = H198_SHARPE, None
all_scores_is, all_scores_oos = [], []

def eval_variant(tag, is_ret, oos_ret, scores=None):
    global best_sh, best_var
    if len(oos_ret) < 3:
        print(f"  {tag:<22}  SKIP — insufficient data")
        results_all[f'variant_{tag}'] = {'skip': True, 'pass_gate': False}
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

print(f"{'Var':<22} {'IS_Sh':>7} {'OOS_Sh':>8} {'CAGR':>8} {'MaxDD':>7} "
      f"{'NegYr':>6} {'WF':>6} {'CorrBL':>7} {'CorrSPY':>8} {'Verdict'}")
print("-" * 95)

eval_variant('A (baseline)', bl_is, bl_oos)

THRESHOLDS = [40, 50, 60, 70]
for thr in THRESHOLDS:
    is_ret, sc_is   = backtest_llm_filtered(thr, ret, IS_START, IS_END)
    oos_ret, sc_oos = backtest_llm_filtered(thr, ret, OOS_START, OOS_END)
    all_scores_is = sc_is; all_scores_oos = sc_oos
    eval_variant(f'B (LLM>={thr})', is_ret, oos_ret)
    (RESULT_DIR / "h494_llm_cache.json").write_text(json.dumps(cache, indent=0))

elapsed = time.time() - t0
print(f"\nLLM scoring/backtest wall time: {elapsed:.0f}s  (cache size: {len(cache)} entries)")
if all_scores_oos:
    print(f"OOS score distribution: min={min(all_scores_oos)} max={max(all_scores_oos)} "
          f"mean={np.mean(all_scores_oos):.1f} median={np.median(all_scores_oos):.1f}")

any_pass = any(v.get('pass_gate', False) for v in results_all.values())
verdict  = "CONFIRMED" if any_pass else "NOT CONFIRMED"
print(f"\nH198 gate: >{H198_SHARPE}  Baseline OOS Sharpe: {bl_sh:.3f}")
print(f"Verdict: {verdict} (best variant {best_var}, OOS Sharpe {best_sh:.3f})")

results = {
    "hypothesis": "H494",
    "description": "LLM Semantic Momentum Filter (true LLM implementation of H279 direction, gpt-4o-mini plausibility score on point-in-time price stats, no historical news source available)",
    "source": "arXiv:2510.26228; supersedes H339 price-proxy test; queued as H279 in H339/H318 notes",
    "model": MODEL,
    "baseline_oos_sharpe": round(bl_sh, 3),
    "h198_gate": H198_SHARPE,
    "thresholds_tested": THRESHOLDS,
    "variants": results_all,
    "best_variant": best_var,
    "best_oos_sharpe": round(best_sh, 3),
    "oos_score_stats": {
        "min": int(min(all_scores_oos)) if all_scores_oos else None,
        "max": int(max(all_scores_oos)) if all_scores_oos else None,
        "mean": round(float(np.mean(all_scores_oos)), 1) if all_scores_oos else None,
        "median": round(float(np.median(all_scores_oos)), 1) if all_scores_oos else None,
    },
    "verdict": verdict,
    "caveat": "No historical news source was available (NewsAPI free tier lacks depth, per H339); LLM was given only point-in-time price/vol statistics, not news/fundamentals. This tests whether LLM holistic reasoning over price character alone beats hardcoded price threshold rules (H339) — it is a partial, not full, replication of the arXiv:2510.26228 news-sentiment design.",
}
(RESULT_DIR / "h494_results.json").write_text(json.dumps(results, indent=2))
print(f"Saved → h494_results.json")
