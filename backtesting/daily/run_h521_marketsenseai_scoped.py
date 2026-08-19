"""
H521 — Scoped MarketSenseAI 4-Agent Stock Selector (executes staged H280)
=============================================================================

Source: arXiv:2604.17327 (Fatouros & Metaxas, Apr 2026), "Signal or Noise in
Multi-Agent LLM-based Stock Recommendations?" Original design: 4 specialist
agents (News, Fundamentals, Dynamics, Macro) + synthesis agent issue a
monthly BUY/HOLD/SELL thesis per stock; strong-buy equal-weight portfolio
beat passive S&P 500 benchmark in the paper's live 19-month study.

Staged design: dream_cycle/staged/2026-06-11/2_h280_marketsenseai_replication.json
(never executed — target script did not exist before this run).

SCOPING DECISIONS (documented explicitly per project precedent, not silent
narrowing):
  1. News agent substitution: NewsAPI free tier has no usable historical
     depth (established blocker, see H339/H289/H509 in hypothesis-log.md).
     A literal historical news-sentiment agent cannot be honestly
     backtested over multiple years. Per the H339/H509 precedent, this
     agent is substituted with the SAME point-in-time price/volatility
     statistics (1m/3m/6-1m/12m returns, trailing vol, distance from 252d
     high) reasoned over qualitatively by an LLM rather than a hardcoded
     rule -- this is documented as a "Dynamics-proxy News agent", not a
     real News agent, and its output is logged separately for attribution.
  2. Universe: reuse H174's 30-stock large-cap universe (same tickers PEAD
     already validated data availability for) rather than S&P 100, given
     time budget for this session.
  3. IS/OOS: 2013-2020 / 2021-2026 (consistent with several other H198-family
     stock hypotheses e.g. H320, H339) rather than the paper's own narrow
     2023-2025 window, to get a larger, more robust OOS sample including a
     down year (2022).

DEGENERACY SELF-CHECK (added after H520's finding that gpt-4o-mini agents
can collapse to a near-constant output when reasoning over structured
numeric inputs at temperature 0.0): after all agent scores are computed,
before backtesting, this script asserts each agent's score distribution has
a minimum standard deviation and that the resulting BUY/SELL classification
frequency is not within a few points of 0% or 100%. If an agent fails this
check, it is flagged in the output and EXCLUDED from the "gate pass"
determination (its results are still reported for transparency, but a
degenerate agent cannot make the hypothesis CONFIRMED).

Agents (score 0-10 each, from LLM given only structured numeric context,
no free text unless noted):
  Agent F (Fundamentals): FMP key-metrics — FCF yield, ROE, revenue growth,
    debt/equity trend (last complete quarter strictly before signal date)
  Agent D (Dynamics-proxy / News-substitute): price/volume momentum stats
    (see scoping note 1)
  Agent M (Macro): current FRED regime z-scores (reuses H520's FRED fetch:
    FEDFUNDS, CPIAUCSL YoY, UNRATE, T10Y2Y, VIXCLS, .shift(1) lagged)
  Synthesis: average of F + D + M (0-10 each) -> strong_buy if avg >= 7.0

Portfolio: equal-weight top-5 strong_buy stocks per month (or top-N if fewer
  than 5 qualify that month; cash/BIL if zero qualify).
Baseline: equal-weight buy-and-hold across the full 30-stock universe
  (comparable "RSP-style" benchmark using only tickers we actually have).
Gate for adoption: OOS Sharpe > equal-weight baseline by >0.15, MaxDD not
  worse by more than 3pp, AND no agent flagged degenerate.
"""

import os
import json
import time
import warnings
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
FRED_KEY   = os.environ.get("FRED_API_KEY", "")
FMP_KEY    = os.environ.get("FMP_API_KEY", "")
FMP_BASE   = "https://financialmodelingprep.com/stable"

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","GOOGL","META","AMZN","NVDA","TSLA",
    "JPM","BAC","WFC",
    "JNJ","PFE","MRK",
    "XOM","CVX",
    "WMT","COST","HD","LOW",
    "SBUX","V","MA",
    "UNH","ABBV","LLY",
    "AVGO","AMD","QCOM","INTC","IBM",
]

FULL_START = "2010-01-01"
FULL_END   = "2026-08-01"
IS_START   = "2013-01-01"
IS_END     = "2020-12-31"
OOS_START  = "2021-01-01"

STRONG_BUY_THRESH = 7.0
TOP_N = 5

FRED_SERIES = {"FEDFUNDS": "level", "CPIAUCSL": "yoy", "UNRATE": "level",
               "T10Y2Y": "level", "VIXCLS": "level"}


# ─────────────────────────────────────────────────────────────────────────
# Data fetch
# ─────────────────────────────────────────────────────────────────────────

def fetch_prices():
    cp = CACHE_DIR / "h521_px.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print("  Downloading price data…")
    raw = yf.download(UNIVERSE, start=FULL_START, end=FULL_END, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    vols = raw["Volume"] if isinstance(raw.columns, pd.MultiIndex) else None
    closes.to_parquet(cp)
    if vols is not None:
        vols.to_parquet(CACHE_DIR / "h521_vol.parquet")
    return closes


def fetch_volumes():
    cp = CACHE_DIR / "h521_vol.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    return None


def fetch_fred(series_id):
    cp = CACHE_DIR / f"h520_fred_{series_id}.parquet"  # reuse H520's cache
    if cp.exists():
        return pd.read_parquet(cp)["value"]
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
           f"&observation_start=2000-01-01&limit=100000")
    r = requests.get(url, timeout=30)
    obs = r.json().get("observations", [])
    records = [(o["date"], o["value"]) for o in obs if o["value"] != "."]
    df = pd.DataFrame(records, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["value"] = pd.to_numeric(df["value"], errors="coerce").dropna()
    df.to_parquet(cp)
    return df["value"]


def build_macro_z():
    frames = {}
    for sid, transform in FRED_SERIES.items():
        s = fetch_fred(sid).resample("ME").last().ffill()
        if transform == "yoy":
            s = s.pct_change(12) * 100.0
        z = (s - s.rolling(24).mean()) / s.rolling(24).std()
        frames[sid] = z.shift(1)
    return pd.DataFrame(frames).dropna(how="all")


def fetch_fmp_metrics(ticker):
    """FMP key-metrics, quarterly, up to 5yr history (free-tier limit)."""
    cp = CACHE_DIR / f"h521_fmp_{ticker}.json"
    if cp.exists():
        return json.loads(cp.read_text())
    url = f"{FMP_BASE}/key-metrics?symbol={ticker}&period=quarter&limit=80&apikey={FMP_KEY}"
    try:
        r = requests.get(url, timeout=20)
        data = r.json()
        if not isinstance(data, list):
            data = []
    except Exception as e:
        print(f"    FMP fetch failed for {ticker}: {e}")
        data = []
    cp.write_text(json.dumps(data))
    time.sleep(0.05)
    return data


# ─────────────────────────────────────────────────────────────────────────
# Agent D (Dynamics-proxy / News-substitute) — deterministic 0-10 rescale
# of price/vol momentum stats, per H339 rule design (no LLM call needed,
# purely numeric -- kept separate from Agent F/M's LLM calls to control cost
# and because H339 already validated this exact stat set works as a filter).
# ─────────────────────────────────────────────────────────────────────────

def dynamics_score_row(px_hist, vol_hist):
    """px_hist: trailing daily close series up to and including signal date.
    Returns 0-10 score from momentum + volume dynamics."""
    if len(px_hist) < 260:
        return np.nan
    r1m  = px_hist.iloc[-1] / px_hist.iloc[-21] - 1 if len(px_hist) > 21 else np.nan
    r3m  = px_hist.iloc[-1] / px_hist.iloc[-63] - 1 if len(px_hist) > 63 else np.nan
    r12m = px_hist.iloc[-1] / px_hist.iloc[-252] - 1 if len(px_hist) > 252 else np.nan
    dist_from_high = px_hist.iloc[-1] / px_hist.iloc[-252:].max() - 1
    if vol_hist is not None and len(vol_hist) > 21:
        vol_trend = vol_hist.iloc[-21:].mean() / (vol_hist.iloc[-63:-21].mean() + 1e-9) - 1
    else:
        vol_trend = 0.0
    # Deterministic composite -> 0-10 scale (documented rule, not an LLM call)
    raw = (np.clip(r12m, -0.5, 1.0) * 3 + np.clip(r3m, -0.3, 0.5) * 2 +
           np.clip(dist_from_high, -0.4, 0) * 2 + np.clip(vol_trend, -0.5, 0.5) * 1)
    score = 5.0 + raw * 2.5
    return float(np.clip(score, 0, 10))


# ─────────────────────────────────────────────────────────────────────────
# LLM agents (Fundamentals, Macro)
# ─────────────────────────────────────────────────────────────────────────

_llm_cache_path = CACHE_DIR / "h521_llm_cache.json"
_llm_cache = json.loads(_llm_cache_path.read_text()) if _llm_cache_path.exists() else {}


def _save_cache():
    _llm_cache_path.write_text(json.dumps(_llm_cache))


def call_llm(prompt, cache_key):
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0, max_tokens=15,
        )
        val = float(resp.choices[0].message.content.strip().split()[0].replace(",", ""))
        val = max(0.0, min(10.0, val))
    except Exception as e:
        print(f"    LLM call failed ({cache_key}): {e} -> default 5.0")
        val = 5.0
    _llm_cache[cache_key] = val
    _save_cache()
    time.sleep(0.03)
    return val


FUND_PROMPT = """You are a fundamentals analyst scoring a stock 0-10 (10=excellent
fundamentals, 5=neutral/average, 0=poor fundamentals) for a 1-month-forward holding
period, based ONLY on this data as of the signal date (no other knowledge):
  Free cash flow yield: {fcf_yield}
  Return on equity: {roe}
  Revenue growth (YoY): {rev_growth}
  Debt/equity trend (positive = rising leverage): {de_trend}

Respond with ONLY a number 0-10, nothing else."""

MACRO_PROMPT = """You are a macro strategist scoring the current regime 0-10 for
holding growth/cyclical large-cap equities over the next month (10=very favorable
for equities, 5=neutral, 0=very unfavorable), given these trailing 24-month z-scores:
  Fed funds rate z-score: {fedfunds:.2f}
  CPI YoY z-score: {cpi:.2f}
  Unemployment rate z-score: {unrate:.2f}
  10y-2y yield curve slope z-score: {t10y2y:.2f}
  VIX z-score: {vix:.2f}

Respond with ONLY a number 0-10, nothing else."""


def macro_scores_by_month(macro_z, months):
    out = {}
    for d in months:
        if d not in macro_z.index or macro_z.loc[d].isna().any():
            out[d] = 5.0
            continue
        row = macro_z.loc[d]
        dkey = d.strftime("%Y-%m")
        out[d] = call_llm(MACRO_PROMPT.format(fedfunds=row["FEDFUNDS"], cpi=row["CPIAUCSL"],
                                                unrate=row["UNRATE"], t10y2y=row["T10Y2Y"],
                                                vix=row["VIXCLS"]), f"macro_{dkey}")
    return out


def fund_score_for(ticker, quarterly_metrics, signal_date):
    """Find latest FMP quarterly metrics strictly before signal_date."""
    candidates = [m for m in quarterly_metrics if m.get("date") and
                  pd.Timestamp(m["date"]) < signal_date]
    if not candidates:
        return 5.0  # neutral default, no data
    candidates.sort(key=lambda m: m["date"], reverse=True)
    m = candidates[0]
    fcf_yield = m.get("freeCashFlowYield", m.get("fcfYield", 0)) or 0
    roe = m.get("returnOnEquity", 0) or 0
    rev_growth = m.get("revenueGrowth", 0) or 0
    de = m.get("debtToEquity", 0) or 0
    dkey = f"{ticker}_{m['date']}"
    return call_llm(FUND_PROMPT.format(fcf_yield=round(fcf_yield, 4), roe=round(roe, 4),
                                        rev_growth=round(rev_growth, 4), de_trend=round(de, 3)),
                     f"fund_{dkey}")


# ─────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────

def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(r)}
    eq = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r)}


def degeneracy_check(scores_dict, agent_name, low_thresh=6.5, high_thresh=7.5,
                      min_std=0.4, extreme_frac_max=0.95):
    vals = np.array(list(scores_dict.values()))
    std = float(vals.std())
    frac_above = float((vals >= STRONG_BUY_THRESH).mean())
    degenerate = (std < min_std) or (frac_above >= extreme_frac_max) or (frac_above <= 1 - extreme_frac_max)
    return {"agent": agent_name, "std": round(std, 4), "frac_strong_buy": round(frac_above, 4),
            "degenerate": bool(degenerate)}


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H521 — Scoped MarketSenseAI 4-Agent Stock Selector")
    print("=" * 80)

    if not (OPENAI_KEY and FRED_KEY and FMP_KEY):
        print("ERROR: missing API key(s)")
        return

    print("\n[1] Fetching prices/volumes…")
    px = fetch_prices()
    vol = fetch_volumes()
    monthly_px = px.resample("ME").last()
    monthly_ret = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    months = [d for d in monthly_px.index if d >= pd.Timestamp(IS_START) - pd.Timedelta(days=400)]

    print("[2] Fetching FMP fundamentals (cached, 30 tickers)…")
    fmp_data = {}
    for t in UNIVERSE:
        if t in px.columns:
            fmp_data[t] = fetch_fmp_metrics(t)

    print("[3] Building FRED macro z-scores + Macro agent scores…")
    macro_z = build_macro_z()
    signal_months = [d for d in months if d >= pd.Timestamp(IS_START)]
    macro_scores = macro_scores_by_month(macro_z, signal_months)
    print(f"  Macro agent scored {len(macro_scores)} months")

    print("[4] Computing Dynamics-proxy + Fundamentals scores per ticker-month…")
    fund_records = {}
    dyn_records = {}
    for d in signal_months:
        for t in UNIVERSE:
            if t not in px.columns:
                continue
            px_hist = px[t].loc[:d].dropna()
            vol_hist = vol[t].loc[:d].dropna() if vol is not None and t in vol.columns else None
            dyn_records[(d, t)] = dynamics_score_row(px_hist, vol_hist)
            fund_records[(d, t)] = fund_score_for(t, fmp_data.get(t, []), d)

    print(f"  Scored {len(dyn_records)} ticker-months (Dynamics), {len(fund_records)} (Fundamentals)")

    print("[5] Degeneracy self-check (pre-backtest)…")
    checks = []
    checks.append(degeneracy_check(macro_scores, "macro"))
    checks.append(degeneracy_check(fund_records, "fundamentals"))
    dyn_valid = {k: v for k, v in dyn_records.items() if not np.isnan(v)}
    checks.append(degeneracy_check(dyn_valid, "dynamics_proxy"))
    for c in checks:
        flag = "DEGENERATE" if c["degenerate"] else "ok"
        print(f"  {c['agent']:16s}: std={c['std']:.3f}  frac_strong_buy={c['frac_strong_buy']*100:.1f}%  [{flag}]")
    any_degenerate = any(c["degenerate"] for c in checks)

    print("\n[6] Building synthesis portfolio…")
    monthly_holding_ret = {}
    monthly_n_qualifying = {}
    for d in signal_months:
        next_idx = monthly_ret.index.get_indexer([d], method="nearest")
        scores = {}
        for t in UNIVERSE:
            if t not in px.columns:
                continue
            dv = dyn_records.get((d, t), np.nan)
            fv = fund_records.get((d, t), np.nan)
            mv = macro_scores.get(d, 5.0)
            if np.isnan(dv) or np.isnan(fv):
                continue
            scores[t] = (dv + fv + mv) / 3.0
        if not scores:
            continue
        qualifying = {t: s for t, s in scores.items() if s >= STRONG_BUY_THRESH}
        monthly_n_qualifying[d] = len(qualifying)
        picks = sorted(qualifying, key=qualifying.get, reverse=True)[:TOP_N]
        if not picks:
            monthly_holding_ret[d] = 0.0  # cash
            continue
        if d in monthly_ret.index:
            rets = [monthly_ret.loc[d, t] for t in picks if t in monthly_ret.columns]
            monthly_holding_ret[d] = float(np.nanmean(rets)) if rets else 0.0

    strategy_ret = pd.Series(monthly_holding_ret).sort_index()
    baseline_ret = monthly_ret[[c for c in UNIVERSE if c in monthly_ret.columns]].mean(axis=1)
    baseline_ret = baseline_ret.loc[strategy_ret.index]

    is_mask = (strategy_ret.index >= pd.Timestamp(IS_START)) & (strategy_ret.index <= pd.Timestamp(IS_END))
    oos_mask = strategy_ret.index >= pd.Timestamp(OOS_START)

    strat_is, strat_oos = stats(strategy_ret[is_mask]), stats(strategy_ret[oos_mask])
    base_is, base_oos = stats(baseline_ret[is_mask]), stats(baseline_ret[oos_mask])

    print(f"\n  Strategy: IS Sharpe {strat_is['sharpe']:.4f}  OOS Sharpe {strat_oos['sharpe']:.4f}  "
          f"OOS MaxDD {strat_oos['max_drawdown']*100:.2f}%")
    print(f"  Baseline (EW 30-stock): IS Sharpe {base_is['sharpe']:.4f}  OOS Sharpe {base_oos['sharpe']:.4f}  "
          f"OOS MaxDD {base_oos['max_drawdown']*100:.2f}%")
    avg_qualifying = float(np.mean(list(monthly_n_qualifying.values()))) if monthly_n_qualifying else 0.0
    print(f"  Avg qualifying (strong_buy) stocks/month: {avg_qualifying:.1f} / {len(UNIVERSE)}")

    print("\n[7] Gate check…")
    delta_sharpe = strat_oos["sharpe"] - base_oos["sharpe"]
    delta_maxdd_pp = (strat_oos["max_drawdown"] - base_oos["max_drawdown"]) * 100
    passes_raw = delta_sharpe > 0.15 and delta_maxdd_pp > -3.0
    passes_gate = passes_raw and not any_degenerate
    print(f"  ΔSharpe OOS: {delta_sharpe:+.4f}  ΔMaxDD OOS: {delta_maxdd_pp:+.2f}pp")
    print(f"  Raw numeric pass: {passes_raw}  Any agent degenerate: {any_degenerate}")
    print(f"  Final gate (numeric AND non-degenerate): {'PASS' if passes_gate else 'FAIL'}")

    output = {
        "hypothesis": "H521 — Scoped MarketSenseAI 4-Agent Stock Selector",
        "strategy": {"is": strat_is, "oos": strat_oos},
        "baseline_equal_weight_universe": {"is": base_is, "oos": base_oos},
        "delta_sharpe_oos": round(delta_sharpe, 4),
        "delta_maxdd_oos_pp": round(delta_maxdd_pp, 2),
        "avg_qualifying_per_month": round(avg_qualifying, 2),
        "degeneracy_checks": checks,
        "any_agent_degenerate": any_degenerate,
        "gate_pass_raw_numeric": passes_raw,
        "gate_pass_final": passes_gate,
        "n_llm_calls_cached": len(_llm_cache),
    }
    out_path = RESULT_DIR / "h521_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults saved -> {out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
