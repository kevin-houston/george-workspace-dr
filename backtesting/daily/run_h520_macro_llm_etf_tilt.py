"""
H520 — Macro-LLM Tilt on H026 Canonical ETF Rotation (executes staged H281)
=============================================================================

Source: arXiv:2606.08283 (Wang, Dai, Ma, Jun 2026), "Macro Economists in the
Machine." The paper tests whether LLM agents given identical FRED macro
z-scores as a deterministic Rule Agent can still add value in ETF portfolio
construction. Hawkish/Dovish/Debate agents all beat the Rule Agent in Sharpe
in the paper (Hawkish +0.044, Debate +0.040, p<0.10 block bootstrap), with
the Debate agent's edge attributed to bias correction (averaging out the
Dovish agent's miscalibrated prior) rather than new information.

Staged design: dream_cycle/staged/2026-06-11/3_h281_macro_llm_etf_rotation.json
(never executed — target script did not exist before this run). This script
implements that design against the H026 CANONICAL 25-asset universe/split
(per H345/H346/H510-512 usage), not the older 11-ETF sector-only H026.

Design:
  Base signal: H026 canonical composite rank(12m_mom) + rank(inv_6m_vol),
    hold top-1, monthly rebalance (unchanged from H026/H112/H345/H346).
  Macro layer: at each monthly rebalance, compute FRED z-scores (value vs
    trailing 12m mean/std, using only data strictly available before the
    rebalance date — .shift(1) discipline) for:
      - FEDFUNDS   (Fed funds rate)
      - CPIAUCSL   (CPI, YoY transform)
      - UNRATE     (unemployment rate)
      - T10Y2Y     (10y-2y yield curve slope)
      - VIXCLS     (VIX close)
  Three LLM agents (gpt-4o-mini) run monthly, given only the 5 z-scores:
    - Hawkish: inflation-tightening prior -> tilt toward defensive/short-duration
    - Dovish: growth-easing prior -> tilt toward cyclical/long-duration
    - Debate: sees both Hawkish and Dovish outputs, synthesizes a balanced tilt
  Each agent outputs a single scalar tilt_score in [-1, +1]:
    -1 = maximally defensive (route to BIL/cash-like), 0 = no tilt (use base
    signal unchanged), +1 = maximally lean into the base signal's top pick
    (no behavioral difference from baseline at +1).
  Applied mechanically: if tilt_score < TILT_THRESHOLD, route that month's
  allocation to BIL instead of the base signal's top-1 pick. This mirrors
  the paper's core mechanism (agent view modifies allocation, doesn't
  replace the underlying momentum signal) in a form directly comparable to
  the H519 regime-gate methodology already used on H045.
  A deterministic Rule Agent (z-score composite average vs a fixed threshold)
  is also included as the paper's own baseline comparator.

IS/OOS: 2008-2017 / 2018-2026 (H026 canonical split, per H345/H346)
Baseline: H026 canonical ungated, recomputed in this run for apples-to-apples
  comparison (expect ~2.610 OOS Sharpe / -6.7% MaxDD per H512's replication).
Gate for adoption (per H281's staged design + H519's discipline): OOS Sharpe
  beats the canonical unfiltered baseline by >0.10, AND does not degrade
  OOS MaxDD by more than 2pp, AND the LLM agent must beat the deterministic
  Rule Agent (else the paper's central "LLM value-add beyond a rule" claim
  is not actually being tested / confirmed).

Cost: 3 agents x ~100 OOS months (+ ~40 IS warm-up months for prompt
  consistency, but only OOS months are used for the gate) x gpt-4o-mini
  ~= 300-450 calls total, low cost (<$0.50). Cached to disk so repeat runs
  are free.
"""

import os
import json
import time
import hashlib
import warnings
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
FRED_KEY   = os.environ.get("FRED_API_KEY", "")

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2003-01-01"
FULL_END   = "2026-08-01"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

TILT_THRESHOLD = -0.3   # agent tilt_score below this routes to BIL

# H026 canonical 25-asset universe (per H345/H346/H510-512)
H026_UNIVERSE = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
                  "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ",
                  "IBB","XME"]
CASH_PROXY = "BIL"

FRED_SERIES = {
    "FEDFUNDS": "level",
    "CPIAUCSL": "yoy",
    "UNRATE":   "level",
    "T10Y2Y":   "level",
    "VIXCLS":   "level",
}


# ─────────────────────────────────────────────────────────────────────────
# Data fetch
# ─────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end):
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    cp = CACHE_DIR / f"h520_px_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers…")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_fred(series_id):
    cp = CACHE_DIR / f"h520_fred_{series_id}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)["value"]
    print(f"  Fetching FRED {series_id}…")
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
           f"&observation_start=2000-01-01&limit=100000")
    r = requests.get(url, timeout=30)
    data = r.json()
    obs = data.get("observations", [])
    records = [(o["date"], o["value"]) for o in obs if o["value"] != "."]
    df = pd.DataFrame(records, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    df.to_parquet(cp)
    return df["value"]


def build_macro_zscores():
    """Monthly z-scores for each FRED series, .shift(1) applied so only data
    strictly available BEFORE the rebalance month is used (no look-ahead)."""
    frames = {}
    for series_id, transform in FRED_SERIES.items():
        s = fetch_fred(series_id)
        s = s.resample("ME").last().ffill()
        if transform == "yoy":
            s = s.pct_change(12) * 100.0
        z = (s - s.rolling(24).mean()) / s.rolling(24).std()
        frames[series_id] = z.shift(1)  # lag 1 month: use info known BEFORE this month
    df = pd.DataFrame(frames).dropna(how="all")
    return df


# ─────────────────────────────────────────────────────────────────────────
# H026 canonical base signal
# ─────────────────────────────────────────────────────────────────────────

def build_h026_signal(prices, start, end):
    """Returns: monthly_ret series (top-1 pick), and per-month top pick label."""
    avail = [t for t in H026_UNIVERSE if t in prices.columns]
    px = prices[avail].loc[start:end].dropna(how="all")
    monthly_px  = px.resample("ME").last()
    monthly_ret = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    picks = {}
    rets = {}
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid = mom_row.index.intersection(vol_row.index)
        if len(valid) < 1:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top = score.idxmax()
        d = monthly_px.index[i]
        picks[d] = top
        rets[d] = monthly_ret.iloc[i][top]
    return pd.Series(rets).sort_index(), picks, monthly_ret


# ─────────────────────────────────────────────────────────────────────────
# LLM agents
# ─────────────────────────────────────────────────────────────────────────

_llm_cache_path = CACHE_DIR / "h520_llm_cache.json"
_llm_cache = json.loads(_llm_cache_path.read_text()) if _llm_cache_path.exists() else {}


def _save_llm_cache():
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
            temperature=0.0,
            max_tokens=20,
        )
        text = resp.choices[0].message.content.strip()
        val = float(text.split()[0].replace(",", ""))
        val = max(-1.0, min(1.0, val))
    except Exception as e:
        print(f"    LLM call failed ({cache_key}): {e} — defaulting to 0.0")
        val = 0.0
    _llm_cache[cache_key] = val
    _save_llm_cache()
    time.sleep(0.05)
    return val


HAWKISH_PROMPT = """You are a hawkish macro strategist with an inflation-fighting, tightening-cycle prior.
Given these trailing macro z-scores (positive = above 24-month trailing average):
  Fed funds rate z-score: {fedfunds:.2f}
  CPI YoY z-score: {cpi:.2f}
  Unemployment rate z-score: {unrate:.2f}
  10y-2y yield curve slope z-score: {t10y2y:.2f}
  VIX z-score: {vix:.2f}

Output a single tilt score from -1.0 to +1.0 for a growth/cyclical ETF momentum
portfolio: -1.0 means "fully defensive, route to cash", 0.0 means "neutral, no
tilt", +1.0 means "fully lean into the momentum signal, risk-on". A hawkish
strategist should tilt more defensive when inflation/rate z-scores are elevated
and the yield curve is inverted. Respond with ONLY the number, nothing else."""

DOVISH_PROMPT = """You are a dovish macro strategist with a growth-supportive, easing-cycle prior.
Given these trailing macro z-scores (positive = above 24-month trailing average):
  Fed funds rate z-score: {fedfunds:.2f}
  CPI YoY z-score: {cpi:.2f}
  Unemployment rate z-score: {unrate:.2f}
  10y-2y yield curve slope z-score: {t10y2y:.2f}
  VIX z-score: {vix:.2f}

Output a single tilt score from -1.0 to +1.0 for a growth/cyclical ETF momentum
portfolio: -1.0 means "fully defensive, route to cash", 0.0 means "neutral, no
tilt", +1.0 means "fully lean into the momentum signal, risk-on". A dovish
strategist should be more forgiving of elevated unemployment/VIX (expects
policy support) and less quick to turn defensive. Respond with ONLY the
number, nothing else."""

DEBATE_PROMPT = """You are a balanced macro strategist synthesizing two colleagues' views.
Hawkish colleague's tilt score: {hawk:.2f}
Dovish colleague's tilt score: {dove:.2f}
Macro z-scores: Fed funds {fedfunds:.2f}, CPI YoY {cpi:.2f}, Unemployment {unrate:.2f},
Yield curve (10y-2y) {t10y2y:.2f}, VIX {vix:.2f}

Provide a final balanced tilt score from -1.0 to +1.0 for a growth/cyclical ETF
momentum portfolio (-1.0 = fully defensive/cash, 0.0 = neutral, +1.0 = fully
risk-on), correcting for whichever colleague's prior looks miscalibrated given
the actual data. Respond with ONLY the number, nothing else."""


def rule_agent_tilt(row):
    """Deterministic paper-baseline comparator: composite z-score vs threshold."""
    composite = (row["FEDFUNDS"] + row["CPIAUCSL"] - row["UNRATE"]
                 - row["T10Y2Y"] + row["VIXCLS"]) / 5.0
    # High composite = hawkish/stress signal -> defensive tilt
    return float(np.clip(-composite / 2.0, -1.0, 1.0))


def run_agents(macro_z, dates):
    records = []
    for d in dates:
        if d not in macro_z.index:
            records.append({"date": d, "hawk": 0.0, "dove": 0.0, "debate": 0.0, "rule": 0.0})
            continue
        row = macro_z.loc[d]
        if row.isna().any():
            records.append({"date": d, "hawk": 0.0, "dove": 0.0, "debate": 0.0, "rule": 0.0})
            continue
        vals = dict(fedfunds=row["FEDFUNDS"], cpi=row["CPIAUCSL"], unrate=row["UNRATE"],
                    t10y2y=row["T10Y2Y"], vix=row["VIXCLS"])
        dkey = d.strftime("%Y-%m")
        hawk = call_llm(HAWKISH_PROMPT.format(**vals), f"hawk_{dkey}")
        dove = call_llm(DOVISH_PROMPT.format(**vals), f"dove_{dkey}")
        debate = call_llm(DEBATE_PROMPT.format(hawk=hawk, dove=dove, **vals), f"debate_{dkey}")
        rule = rule_agent_tilt(row)
        records.append({"date": d, "hawk": hawk, "dove": dove, "debate": debate, "rule": rule})
    return pd.DataFrame(records).set_index("date")


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


def apply_tilt(base_ret, picks, monthly_ret_all, tilt_series, threshold):
    """Where tilt < threshold, route that month's return to BIL instead of the
    base pick."""
    out = {}
    for d, r in base_ret.items():
        t = tilt_series.get(d, 0.0)
        if t < threshold and CASH_PROXY in monthly_ret_all.columns:
            bil_ret = monthly_ret_all.loc[d, CASH_PROXY] if d in monthly_ret_all.index else np.nan
            out[d] = bil_ret if not np.isnan(bil_ret) else r
        else:
            out[d] = r
    return pd.Series(out).sort_index()


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H520 — Macro-LLM Tilt on H026 Canonical ETF Rotation")
    print("=" * 80)

    if not OPENAI_KEY:
        print("ERROR: OPENAI_API_KEY not set")
        return
    if not FRED_KEY:
        print("ERROR: FRED_API_KEY not set")
        return

    print("\n[1] Fetching ETF prices…")
    prices = fetch_close(H026_UNIVERSE, FULL_START, FULL_END)

    print("[2] Building H026 canonical base signal…")
    base_ret, picks, monthly_ret_all = build_h026_signal(prices, FULL_START, FULL_END)
    print(f"  Base signal: {base_ret.index[0].date()} -> {base_ret.index[-1].date()}, {len(base_ret)} months")

    print("[3] Fetching FRED macro series + building z-scores…")
    macro_z = build_macro_zscores()
    print(f"  Macro z-score coverage: {macro_z.dropna().index[0].date()} -> {macro_z.dropna().index[-1].date()}")

    print("[4] Running LLM agents (Hawkish/Dovish/Debate) + Rule agent, monthly…")
    dates = list(base_ret.index)
    agent_df = run_agents(macro_z, dates)
    print(f"  Agent tilt scores computed for {len(agent_df)} months (cached in h520_llm_cache.json)")

    print("[5] Computing baseline + tilted equity curves…")
    is_mask = (base_ret.index >= pd.Timestamp(IS_START)) & (base_ret.index <= pd.Timestamp(IS_END))
    oos_mask = base_ret.index >= pd.Timestamp(OOS_START)

    baseline_is = stats(base_ret[is_mask])
    baseline_oos = stats(base_ret[oos_mask])
    print(f"  Baseline (unfiltered): IS Sharpe {baseline_is['sharpe']:.4f}, "
          f"OOS Sharpe {baseline_oos['sharpe']:.4f}, OOS MaxDD {baseline_oos['max_drawdown']*100:.2f}%")

    variants = {}
    for agent_name in ["hawk", "dove", "debate", "rule"]:
        tilt_series = agent_df[agent_name].to_dict()
        tilted_ret = apply_tilt(base_ret, picks, monthly_ret_all, tilt_series, TILT_THRESHOLD)
        v_is = stats(tilted_ret[is_mask])
        v_oos = stats(tilted_ret[oos_mask])
        fired_frac = float((agent_df.loc[oos_mask, agent_name] < TILT_THRESHOLD).mean())
        variants[agent_name] = {
            "is": v_is, "oos": v_oos, "gate_fired_frac_oos": round(fired_frac, 4),
            "delta_sharpe_oos": round(v_oos["sharpe"] - baseline_oos["sharpe"], 4),
            "delta_maxdd_oos_pp": round((v_oos["max_drawdown"] - baseline_oos["max_drawdown"]) * 100, 2),
        }
        print(f"  {agent_name:8s}: IS {v_is['sharpe']:.4f}  OOS {v_oos['sharpe']:.4f}  "
              f"MaxDD {v_oos['max_drawdown']*100:.2f}%  fired {fired_frac*100:.1f}%  "
              f"dSharpe {variants[agent_name]['delta_sharpe_oos']:+.4f}")

    print("\n[6] Gate check…")
    GATE_SHARPE_DELTA = 0.10
    GATE_MAXDD_PP = 2.0
    best_llm = max(["hawk", "dove", "debate"], key=lambda k: variants[k]["oos"]["sharpe"])
    llm_beats_rule = variants[best_llm]["oos"]["sharpe"] > variants["rule"]["oos"]["sharpe"]
    passes_gate = (variants[best_llm]["delta_sharpe_oos"] > GATE_SHARPE_DELTA and
                   variants[best_llm]["delta_maxdd_oos_pp"] > -GATE_MAXDD_PP and
                   llm_beats_rule)
    print(f"  Best LLM agent: {best_llm} (OOS Sharpe {variants[best_llm]['oos']['sharpe']:.4f})")
    print(f"  Rule agent OOS Sharpe: {variants['rule']['oos']['sharpe']:.4f}")
    print(f"  LLM beats Rule agent: {llm_beats_rule}")
    print(f"  Gate: {'PASS' if passes_gate else 'FAIL'}")

    output = {
        "hypothesis": "H520 — Macro-LLM Tilt on H026 Canonical ETF Rotation",
        "baseline": {"is": baseline_is, "oos": baseline_oos},
        "variants": variants,
        "best_llm_agent": best_llm,
        "llm_beats_rule_agent": llm_beats_rule,
        "gate_pass": passes_gate,
        "tilt_threshold": TILT_THRESHOLD,
        "n_llm_calls_cached": len(_llm_cache),
    }
    out_path = RESULT_DIR / "h520_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults saved -> {out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
