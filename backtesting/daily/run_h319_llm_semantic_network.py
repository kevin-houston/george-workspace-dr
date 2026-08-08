"""
H319 — LLM-Augmented Cross-Stock Semantic Network (scoped implementation)
============================================================================
Source: Huang, Fan, Hu, Ye arXiv:2604.19476 (April 2026). Two-stage framework:
build a sparse economic-link graph from 10-K text, classify each candidate
edge's TYPE via LLM, and route asymmetric links (CUSTOMER_SUPPLIER) to
lead-lag momentum trades and symmetric links (COMPETITOR/COMMON_INPUT) to
mean-reversion pairs trades.

SCOPING NOTE vs the original stub design (backtesting/daily/run_h319.py,
logged as a STUB "not yet run" with 100-stock universe + text-embedding-3-small
full embedding pipeline, ~500 candidate pairs, $5-15 estimated cost): this run
narrows scope to make the hypothesis tractable in a single nightly session
while still testing the paper's actual mechanism (LLM edge-type
classification driving DIFFERENT downstream strategies per type). Changes
from the original stub:
  - Universe: the existing 30-stock H198/H174 universe (already has cached
    price history, well-understood, avoids a fresh 100-stock data pull).
  - Candidate pair generation: replaced the embedding-similarity stage with
    a sector/industry pre-filter (yfinance sector+industry metadata) — pairs
    within the same industry, or in adjacent supply-chain sectors, are
    proposed as candidates. This is a substitute for Stage 1 (embeddings
    narrow ~100^2 pairs to top-10 each; here 30 stocks' industry clustering
    narrows C(30,2)=435 pairs to ~60 candidates directly, at zero LLM/embed
    cost). Documented explicitly as a scope-narrowing, not hidden.
  - Stage 2 (LLM edge classification) is implemented as designed: GPT-4o-mini
    classifies each candidate pair from 10-K Item 1 business-description
    text into CUSTOMER_SUPPLIER (+ direction) / COMPETITOR / COMMON_INPUT /
    NONE.
  - Signals: asymmetric (CUSTOMER_SUPPLIER) -> weekly lead-lag momentum;
    symmetric (COMPETITOR/COMMON_INPUT) -> weekly z-score mean-reversion.
    Same mechanism as the original design.

IS: 2015-01-01 to 2020-12-31 | OOS: 2021-01-01 to 2026-06-20
Gate: OOS Sharpe > 1.0 AND Corr(SPY) < 0.40 AND WF ratio in [0.5, 4.0]
      (unchanged from original H319 stub spec)
"""
import warnings
warnings.filterwarnings("ignore")

import json, os, re, time, itertools
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from openai import OpenAI

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

TENK_CACHE  = CACHE_DIR / "h319_10k_business_desc.json"
EDGE_CACHE  = CACHE_DIR / "h319_edge_classifications.json"

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

DATA_START = "2013-01-01"
DATA_END   = "2026-06-20"
IS_START   = pd.Timestamp("2015-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-20")

MODEL          = "gpt-4o-mini"
EMBED_UNUSED   = None  # embeddings not used in scoped version (see module docstring)
TC             = 0.0005  # per-leg weekly transaction cost estimate
GATE_SHARPE    = 1.0
GATE_CORR_SPY  = 0.40
GATE_WF_LO, GATE_WF_HI = 0.5, 4.0

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ── Stage 0: sector/industry metadata (candidate pre-filter) ──────────────────

def get_sector_industry():
    cache_path = CACHE_DIR / "h319_sector_industry.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    out = {}
    for t in UNIVERSE:
        try:
            info = yf.Ticker(t).info
            out[t] = {"sector": info.get("sector"), "industry": info.get("industry")}
        except Exception:
            out[t] = {"sector": None, "industry": None}
    cache_path.write_text(json.dumps(out, indent=2))
    return out


# Adjacent-sector supply-chain heuristic: sectors likely to have
# customer/supplier or common-input relationships even when industry differs.
ADJACENT_SECTOR_PAIRS = {
    frozenset(["Technology", "Communication Services"]),   # chipmakers <-> platforms
    frozenset(["Technology", "Consumer Cyclical"]),         # semis <-> Tesla/Amazon hardware
    frozenset(["Healthcare", "Healthcare"]),
}

def generate_candidate_pairs(sector_info):
    """Same-industry (competitor/common-input candidates) OR same/adjacent
    sector (potential customer-supplier candidates). This replaces the
    embedding-similarity stage from the original design."""
    candidates = []
    for a, b in itertools.combinations(UNIVERSE, 2):
        sa, ia = sector_info[a]["sector"], sector_info[a]["industry"]
        sb, ib = sector_info[b]["sector"], sector_info[b]["industry"]
        if ia and ib and ia == ib:
            candidates.append((a, b, "same_industry"))
        elif sa and sb and (sa == sb or frozenset([sa, sb]) in ADJACENT_SECTOR_PAIRS):
            candidates.append((a, b, "adjacent_sector"))
    return candidates


# ── Stage 1: 10-K Item 1 business description (cached) ────────────────────────

_edgar_identity_set = False

def get_business_desc(ticker):
    if TENK_CACHE.exists():
        cache = json.loads(TENK_CACHE.read_text())
    else:
        cache = {}
    if ticker in cache and cache[ticker]:
        return cache[ticker]

    global _edgar_identity_set
    try:
        from edgar import Company, set_identity
        if not _edgar_identity_set:
            set_identity("George george@nanoclaw.test")
            _edgar_identity_set = True
        company = Company(ticker)
        filings = company.get_filings(form="10-K")
        if filings is None or len(filings) == 0:
            cache[ticker] = None
            TENK_CACHE.write_text(json.dumps(cache, indent=2))
            return None
        doc = filings[0].obj()
        biz = doc.business if isinstance(doc.business, str) else str(doc.business)
        biz = biz[:6000]
        cache[ticker] = biz
        TENK_CACHE.write_text(json.dumps(cache, indent=2))
        return biz
    except Exception as e:
        print(f"    10-K fetch error {ticker}: {e}")
        cache[ticker] = None
        TENK_CACHE.write_text(json.dumps(cache, indent=2))
        return None


# ── Stage 2: LLM edge classification (cached) ──────────────────────────────────

EDGE_PROMPT = """You are analyzing whether two public companies have a meaningful direct \
economic relationship, based on their SEC 10-K business descriptions.

Company A ({ta}): {desc_a}

Company B ({tb}): {desc_b}

Classify the relationship between A and B into exactly ONE of:
- CUSTOMER_SUPPLIER_A_SUPPLIES_B: A is plausibly a direct supplier/input-provider to B
- CUSTOMER_SUPPLIER_B_SUPPLIES_A: B is plausibly a direct supplier/input-provider to A
- COMPETITOR: A and B compete directly for the same customers in the same market
- COMMON_INPUT: A and B are not competitors or supplier/customer, but both depend heavily on a common upstream input/driver (e.g. same commodity, same macro factor, same platform ecosystem) such that their fortunes move together for a shared external reason
- NONE: no meaningful direct economic link beyond being large companies

Respond with ONLY the category name, nothing else."""

VALID_EDGES = {
    "CUSTOMER_SUPPLIER_A_SUPPLIES_B", "CUSTOMER_SUPPLIER_B_SUPPLIES_A",
    "COMPETITOR", "COMMON_INPUT", "NONE",
}

def classify_edge(ta, tb, desc_a, desc_b, cache):
    key = f"{ta}|{tb}"
    if key in cache:
        return cache[key]
    if not desc_a or not desc_b:
        cache[key] = "NONE"
        return "NONE"
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": EDGE_PROMPT.format(
                ta=ta, desc_a=desc_a[:2500], tb=tb, desc_b=desc_b[:2500])}],
            temperature=0,
            max_tokens=16,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"[A-Z_]+", raw)
        label = m.group() if m else "NONE"
        if label not in VALID_EDGES:
            label = "NONE"
    except Exception as e:
        print(f"    LLM edge error {ta}-{tb}: {e}")
        label = "NONE"
    cache[key] = label
    return label


# ── Price data + signals ────────────────────────────────────────────────────────

def sharpe(s, periods_per_year=52):
    if len(s) < 10 or s.std() < 1e-10:
        return 0.0
    return float(s.mean() / s.std() * np.sqrt(periods_per_year))

def maxdd(s):
    c = (1 + s).cumprod()
    return float(c.div(c.cummax()).sub(1).min())


def main():
    print("=" * 70)
    print("  H319 — LLM Semantic Network: Scoped Lead-Lag / Mean-Reversion Test")
    print("=" * 70)

    print("\n[1/6] Sector/industry metadata + candidate pair generation…")
    sector_info = get_sector_industry()
    candidates = generate_candidate_pairs(sector_info)
    print(f"  Universe: {len(UNIVERSE)} stocks, C(n,2)={len(list(itertools.combinations(UNIVERSE,2)))} total pairs")
    print(f"  Candidate pairs after sector/industry pre-filter: {len(candidates)}")

    print("\n[2/6] Fetching 10-K Item 1 business descriptions (cached)…")
    descs = {}
    for t in UNIVERSE:
        descs[t] = get_business_desc(t)
        time.sleep(0.1)
    n_have_desc = sum(1 for v in descs.values() if v)
    print(f"  Business descriptions available: {n_have_desc}/{len(UNIVERSE)}")

    print(f"\n[3/6] Classifying {len(candidates)} candidate edges via {MODEL} (cached)…")
    edge_cache = json.loads(EDGE_CACHE.read_text()) if EDGE_CACHE.exists() else {}
    t0 = time.time()
    edges = []
    for a, b, reason in candidates:
        label = classify_edge(a, b, descs.get(a), descs.get(b), edge_cache)
        edges.append({"a": a, "b": b, "prefilter_reason": reason, "edge_type": label})
    EDGE_CACHE.write_text(json.dumps(edge_cache, indent=0))
    print(f"  Classified in {time.time()-t0:.0f}s")

    edge_df = pd.DataFrame(edges)
    print("\n  Edge type distribution:")
    print(edge_df["edge_type"].value_counts().to_string())

    asym_edges = edge_df[edge_df["edge_type"].isin(
        ["CUSTOMER_SUPPLIER_A_SUPPLIES_B", "CUSTOMER_SUPPLIER_B_SUPPLIES_A"])]
    sym_edges = edge_df[edge_df["edge_type"].isin(["COMPETITOR", "COMMON_INPUT"])]
    print(f"\n  Asymmetric (lead-lag) candidate edges: {len(asym_edges)}")
    print(f"  Symmetric (mean-reversion) candidate edges: {len(sym_edges)}")

    print("\n[4/6] Downloading weekly price data…")
    all_tickers = UNIVERSE + ["SPY"]
    raw = yf.download(all_tickers, start=DATA_START, end=DATA_END,
                       auto_adjust=True, progress=False)["Close"].ffill()
    weekly = raw.resample("W-FRI").last()
    wret = weekly.pct_change()

    def slice_period(s, start, end):
        return s[(s.index >= start) & (s.index <= end)]

    spy_wret = wret["SPY"]

    # ── Asymmetric lead-lag strategy ──
    def backtest_leadlag(edges_df, start, end):
        """Each week: for each asymmetric edge, if supplier's return last week > 0,
        go long the customer this week (equal-weight across active signals)."""
        dates = wret[(wret.index >= start) & (wret.index <= end)].index
        rets = []
        for dt in dates:
            prior = wret.index[wret.index < dt]
            if len(prior) == 0:
                continue
            prev_dt = prior[-1]
            longs = []
            for _, e in edges_df.iterrows():
                if e["edge_type"] == "CUSTOMER_SUPPLIER_A_SUPPLIES_B":
                    supplier, customer = e["a"], e["b"]
                else:
                    supplier, customer = e["b"], e["a"]
                if supplier not in wret.columns or customer not in wret.columns:
                    continue
                supplier_prev_ret = wret.loc[prev_dt, supplier] if prev_dt in wret.index else np.nan
                if pd.notna(supplier_prev_ret) and supplier_prev_ret > 0:
                    longs.append(customer)
            if not longs:
                rets.append(0.0)
                continue
            r = wret.loc[dt, longs].mean() if dt in wret.index else 0.0
            r = r - TC * 2  # weekly rebalance cost estimate
            rets.append(float(r) if pd.notna(r) else 0.0)
        return pd.Series(rets, index=dates)

    # ── Symmetric mean-reversion strategy ──
    def backtest_meanrev(edges_df, start, end, entry_z=1.5, exit_z=0.3, window=20):
        dates = wret[(wret.index >= start) & (wret.index <= end)].index
        pair_positions = {}  # (a,b) -> +1 (long a/short b), -1, 0
        pnl_by_date = {d: [] for d in dates}
        for _, e in edges_df.iterrows():
            a, b = e["a"], e["b"]
            if a not in weekly.columns or b not in weekly.columns:
                continue
            log_spread = np.log(weekly[a]) - np.log(weekly[b])
            z = (log_spread - log_spread.rolling(window).mean()) / log_spread.rolling(window).std()
            pos = 0
            for i, dt in enumerate(weekly.index):
                if dt not in pnl_by_date:
                    continue
                zt = z.get(dt, np.nan)
                if pd.isna(zt):
                    continue
                if pos == 0:
                    if zt > entry_z:
                        pos = -1  # spread too high -> short a, long b
                    elif zt < -entry_z:
                        pos = 1   # spread too low -> long a, short b
                else:
                    if abs(zt) < exit_z:
                        pos = 0
                if pos != 0 and dt in wret.index:
                    ra = wret.loc[dt, a] if pd.notna(wret.loc[dt, a]) else 0.0
                    rb = wret.loc[dt, b] if pd.notna(wret.loc[dt, b]) else 0.0
                    pair_ret = pos * (ra - rb) / 2 - TC * 2
                    pnl_by_date[dt].append(pair_ret)
        rets = [np.mean(pnl_by_date[d]) if pnl_by_date[d] else 0.0 for d in dates]
        return pd.Series(rets, index=dates)

    print("\n[5/6] Backtesting IS/OOS…")
    ll_is  = backtest_leadlag(asym_edges, IS_START, IS_END)
    ll_oos = backtest_leadlag(asym_edges, OOS_START, OOS_END)
    mr_is  = backtest_meanrev(sym_edges, IS_START, IS_END)
    mr_oos = backtest_meanrev(sym_edges, OOS_START, OOS_END)

    combo_is  = (ll_is.fillna(0) + mr_is.fillna(0)) / 2
    combo_oos = (ll_oos.fillna(0) + mr_oos.fillna(0)) / 2

    spy_oos = slice_period(spy_wret, OOS_START, OOS_END)

    def eval_strat(tag, is_s, oos_s):
        is_sh, oos_sh = sharpe(is_s), sharpe(oos_s)
        oos_mdd = maxdd(oos_s)
        wf = oos_sh / is_sh if is_sh > 0 else 0.0
        corr_spy = float(oos_s.corr(spy_oos.reindex(oos_s.index)))
        passes = (oos_sh > GATE_SHARPE) and (abs(corr_spy) < GATE_CORR_SPY) and (GATE_WF_LO <= wf <= GATE_WF_HI)
        print(f"  {tag:<20} IS_Sh={is_sh:>7.3f}  OOS_Sh={oos_sh:>7.3f}  OOS_MaxDD={oos_mdd:>7.1%}  "
              f"WF={wf:>6.3f}  Corr(SPY)={corr_spy:>7.3f}  {'PASS' if passes else 'fail'}")
        return {
            "is_sharpe": round(is_sh, 3), "oos_sharpe": round(oos_sh, 3),
            "oos_maxdd": round(oos_mdd, 3), "wf_ratio": round(wf, 3),
            "corr_spy": round(corr_spy, 3), "pass_gate": passes,
        }

    print(f"\n{'Strategy':<20} {'IS Sh':>9} {'OOS Sh':>9} {'OOS MaxDD':>10} {'WF':>7} {'CorrSPY':>10}  Verdict")
    print("-" * 90)
    results_all = {}
    results_all["asymmetric_leadlag"] = eval_strat("Lead-lag (asym)", ll_is, ll_oos)
    results_all["symmetric_meanrev"]  = eval_strat("Mean-rev (sym)", mr_is, mr_oos)
    results_all["combined_50_50"]     = eval_strat("Combined 50/50", combo_is, combo_oos)

    print("\n[6/6] Saving results…")
    any_pass = any(v["pass_gate"] for v in results_all.values())
    verdict = "CONFIRMED" if any_pass else "NOT CONFIRMED"
    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND |Corr(SPY)| < {GATE_CORR_SPY} AND WF in [{GATE_WF_LO},{GATE_WF_HI}]")
    print(f"Verdict: {verdict}")

    results = {
        "hypothesis": "H319",
        "description": "LLM-augmented cross-stock semantic network (scoped: 30-stock H198 universe, sector/industry pre-filter replacing embedding stage, GPT-4o-mini edge-type classification from 10-K Item 1 text, asymmetric->lead-lag / symmetric->mean-reversion routing)",
        "source": "arXiv:2604.19476 (Huang, Fan, Hu, Ye, April 2026)",
        "model": MODEL,
        "universe": UNIVERSE,
        "n_candidate_pairs": len(candidates),
        "n_desc_available": n_have_desc,
        "edge_type_distribution": edge_df["edge_type"].value_counts().to_dict(),
        "n_asymmetric_edges": len(asym_edges),
        "n_symmetric_edges": len(sym_edges),
        "is_start": str(IS_START.date()), "is_end": str(IS_END.date()),
        "oos_start": str(OOS_START.date()), "oos_end": str(OOS_END.date()),
        "gate": f"OOS Sharpe > {GATE_SHARPE} AND |Corr(SPY)| < {GATE_CORR_SPY} AND WF in [{GATE_WF_LO},{GATE_WF_HI}]",
        "results": results_all,
        "verdict": verdict,
        "scoping_caveat": "Narrowed from original 100-stock/embedding-based stub to 30-stock H198 universe with sector/industry metadata pre-filter replacing the embedding-similarity candidate generation stage. LLM edge-type classification (Stage 2) implemented as originally designed.",
    }
    (RESULT_DIR / "h319_results.json").write_text(json.dumps(results, indent=2, default=str))
    print("Saved -> h319_results.json")


if __name__ == "__main__":
    main()
