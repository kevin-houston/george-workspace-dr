"""
H290 — Lexical Density of EDGAR Filings
========================================

Hypothesis:
  SSRN 3921091 — stocks with higher lexical density (vocabulary diversity)
  in 10-K/10-Q filings outperform. Lexical density = unique words / total words
  (Type-Token Ratio, TTR). Higher TTR implies more substantive, precise disclosure.
  Paper reports Sharpe 0.688 with monthly rebalancing on broad S&P 500 universe.

  Design:
    - Universe: 50 S&P 500 large-cap stocks (same as H284)
    - Signal: Type-Token Ratio of most recent 10-K or 10-Q filing text
      (60-day availability lag before using a filing)
    - Secondary metric: Herdan's C = log(unique)/log(total) — length-normalized TTR
    - Rebalance: monthly; long top-10 by TTR, equal-weight
    - IS: 2019-2021, OOS: 2022-2025

  Filing source: SEC EDGAR via public REST API (no API key required).
  Text extraction: strip HTML, tokenize alphanumeric words, cap at 200K chars.

  Gate: OOS Sharpe ≥ 0.6, walkforward ratio ≥ 0.45

  NOTE: First run downloads ~1,400 EDGAR filings (~500MB). Subsequent runs use cache.
  Allow 60-90 minutes for initial download phase.

Academic basis:
  SSRN 3921091 — Lexical Density and Readability Indices in US Annual Reports
"""

import json
import math
import os
import re
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

EDGAR_UA      = os.environ.get("EDGAR_USER_AGENT", "GeorgeResearch research@example.com")
EDGAR_HEADERS = {"User-Agent": EDGAR_UA, "Accept-Encoding": "gzip, deflate"}

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_END = "2026-06-01"

IS_START  = "2019-01-01"
IS_END    = "2021-12-31"
OOS_START = "2022-01-01"

UNIVERSE = [
    "AAPL","MSFT","GOOGL","AMZN","META","INTC","CSCO","QCOM","TXN","ORCL",
    "JNJ","UNH","PFE","ABBV","MRK","LLY","BMY","AMGN","MDT","ABT",
    "HD","LOW","MCD","NKE","SBUX","TGT","CMG","YUM","DHI","PHM",
    "WMT","PG","KO","PEP","PM","MO","CL","GIS","SYY","CHD",
    "JPM","BAC","WFC","GS","MS","BLK","AXP","USB","PNC","TFC",
]

N_LONG          = 10
FILING_TYPES    = {"10-K", "10-Q"}
FILING_LAG_DAYS = 60       # Filing must be published 60+ days before use
MAX_TEXT_CHARS  = 200_000  # Cap raw text to limit memory / processing time
MIN_TEXT_CHARS  = 5_000    # Skip documents shorter than this


# ── EDGAR helpers ─────────────────────────────────────────────────────────────

def _sec_get(url, timeout=25):
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=timeout)
    time.sleep(0.12)
    return resp


def load_sec_cik_map():
    """Download SEC's canonical ticker→CIK mapping (one request total)."""
    cache = CACHE_DIR / "h290_sec_cik_map.json"
    if cache.exists():
        return json.loads(cache.read_text())
    resp = _sec_get("https://www.sec.gov/files/company_tickers.json")
    if resp.status_code != 200:
        return {}
    mapping = {v["ticker"]: str(v["cik_str"]).zfill(10)
               for v in resp.json().values()}
    cache.write_text(json.dumps(mapping))
    return mapping


def get_filings_list(cik, ticker):
    """
    Return list of {date, form, accession, doc} dicts for all 10-K/10-Q
    filings since 2018 from the SEC submissions JSON.
    """
    cache = CACHE_DIR / f"h290_filings_{ticker}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = _sec_get(url)
    if resp.status_code != 200:
        return []

    data     = resp.json()
    recent   = data.get("filings", {}).get("recent", {})
    accs     = recent.get("accessionNumber", [])
    dates    = recent.get("filingDate", [])
    forms    = recent.get("form", [])
    docs     = recent.get("primaryDocument", [])

    result = []
    for acc, date_str, form, doc in zip(accs, dates, forms, docs):
        if form not in FILING_TYPES:
            continue
        if date_str < "2018-01-01":
            continue
        result.append({"accession": acc, "date": date_str,
                        "form": form, "doc": doc, "cik": cik})

    # Also pull from older-filings pages if available
    files_section = data.get("filings", {}).get("files", [])
    for file_entry in files_section:
        sub_url = "https://data.sec.gov/submissions/" + file_entry["name"]
        try:
            sub_resp = _sec_get(sub_url)
            if sub_resp.status_code != 200:
                continue
            sub = sub_resp.json()
            s_accs  = sub.get("accessionNumber", [])
            s_dates = sub.get("filingDate", [])
            s_forms = sub.get("form", [])
            s_docs  = sub.get("primaryDocument", [])
            for acc, date_str, form, doc in zip(s_accs, s_dates, s_forms, s_docs):
                if form not in FILING_TYPES:
                    continue
                if date_str < "2018-01-01":
                    continue
                result.append({"accession": acc, "date": date_str,
                                "form": form, "doc": doc, "cik": cik})
        except Exception:
            continue

    result.sort(key=lambda x: x["date"])
    cache.write_text(json.dumps(result))
    return result


def fetch_filing_text(filing, ticker):
    """Download and cache primary document text; strip HTML; cap at MAX_TEXT_CHARS."""
    acc_clean = filing["accession"].replace("-", "")
    cache = CACHE_DIR / f"h290_text_{ticker}_{acc_clean}.txt"
    if cache.exists():
        return cache.read_text(errors="ignore")

    cik_int = int(filing["cik"])
    doc     = filing["doc"]
    url     = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}"
    try:
        resp = _sec_get(url, timeout=40)
        if resp.status_code != 200:
            cache.write_text("")
            return ""
        raw = resp.text[:MAX_TEXT_CHARS * 4]  # read 4× in case HTML is dense
        # Strip HTML
        text = re.sub(r"<[^>]{0,500}>", " ", raw)
        text = re.sub(r"&[a-z]{2,6};", " ", text)  # HTML entities
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:MAX_TEXT_CHARS]
        cache.write_text(text, errors="ignore")
        return text
    except Exception:
        cache.write_text("")
        return ""


def compute_lexical_density(text):
    """
    Compute Type-Token Ratio (TTR) and Herdan's C for a document.
    Returns None if the document is too short to be meaningful.
    """
    if len(text) < MIN_TEXT_CHARS:
        return None

    tokens  = re.findall(r"\b[a-z]{2,}\b", text.lower())
    n_total = len(tokens)
    if n_total < 500:
        return None

    n_unique = len(set(tokens))
    ttr      = n_unique / n_total

    herdan_c = (math.log(n_unique) / math.log(n_total)
                if n_total > 1 and n_unique > 1 else None)

    return {
        "ttr":      round(ttr, 6),
        "herdan_c": round(herdan_c, 6) if herdan_c else None,
        "n_tokens": n_total,
        "n_unique": n_unique,
    }


# ── Price helpers ─────────────────────────────────────────────────────────────

def fetch_monthly_returns(ticker):
    cache = CACHE_DIR / f"h290_monthly_{ticker}.parquet"
    if cache.exists():
        return pd.read_parquet(cache).squeeze().rename(ticker)

    raw = yf.download(ticker, start="2018-01-01", end=FULL_END,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    monthly = close.resample("ME").last().pct_change().rename(ticker)
    monthly.to_frame().to_parquet(cache)
    return monthly


def stats(r):
    r = r.dropna()
    if len(r) < 4:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0}
    eq    = (1 + r).cumprod()
    n_yr  = len(r) / 12
    cagr  = float(eq.iloc[-1]) ** (1 / n_yr) - 1 if n_yr > 0 else 0.0
    vol   = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    annual = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    neg_years = int((annual < 0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
            "n_months": len(r), "neg_years": neg_years}


def corr_series(r1, r2):
    idx = r1.dropna().index.intersection(r2.dropna().index)
    if len(idx) < 6:
        return float("nan")
    return round(float(r1.reindex(idx).corr(r2.reindex(idx))), 4)


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print("H290 — Lexical Density of EDGAR Filings (SSRN 3921091)")
print("=" * 80)

# ── Step 1: CIK resolution ────────────────────────────────────────────────────
print("\n[1] Loading SEC ticker → CIK mapping …")
sec_cik_map = load_sec_cik_map()
print(f"  Loaded {len(sec_cik_map):,} ticker-CIK entries from SEC")

cik_map = {}
for t in UNIVERSE:
    cik = sec_cik_map.get(t)
    if cik:
        cik_map[t] = cik
    else:
        print(f"  {t}: CIK not found — excluded")

print(f"  Resolved: {len(cik_map)}/{len(UNIVERSE)} tickers")

# ── Step 2: Filing lists ──────────────────────────────────────────────────────
print("\n[2] Fetching 10-K/10-Q filing metadata (since 2018) …")
filings_by_ticker = {}
for t, cik in cik_map.items():
    filings = get_filings_list(cik, t)
    if filings:
        filings_by_ticker[t] = filings
        print(f"  {t}: {len(filings)} filings  ({filings[0]['date']} – {filings[-1]['date']})")
    else:
        print(f"  {t}: no filings found")

# ── Step 3: Compute lexical density for each filing ───────────────────────────
print("\n[3] Computing TTR lexical density for each filing …")
print("  (Downloading EDGAR documents — cached after first run)")

ld_series = {}  # ticker → [(date_str, ttr)]
for t, filings in filings_by_ticker.items():
    ticker_ld = []
    n_total = len(filings)
    for i, filing in enumerate(filings):
        text    = fetch_filing_text(filing, t)
        metrics = compute_lexical_density(text)
        if metrics:
            ticker_ld.append((filing["date"], metrics["ttr"]))

    if ticker_ld:
        ld_series[t] = ticker_ld
        latest = ticker_ld[-1]
        print(f"  {t}: {len(ticker_ld)}/{n_total} scored; latest {latest[0]} TTR={latest[1]:.4f}")
    else:
        print(f"  {t}: no scorable filings ({n_total} attempted)")

print(f"\n  Tickers with LD data: {len(ld_series)}")

# Convert to pd.Series for efficient lookups
ld_lookup = {}
for t, ld_list in ld_series.items():
    idx  = pd.to_datetime([x[0] for x in ld_list])
    vals = [x[1] for x in ld_list]
    ld_lookup[t] = pd.Series(vals, index=idx).sort_index()

# ── Step 4: Monthly returns ───────────────────────────────────────────────────
print("\n[4] Loading monthly return series …")
monthly_returns = {}
for t in list(ld_lookup.keys()) + ["SPY"]:
    s = fetch_monthly_returns(t)
    if len(s.dropna()) > 20:
        monthly_returns[t] = s

spy_monthly = monthly_returns.get("SPY", pd.Series(dtype=float))

# ── Step 5: Monthly-rebalance backtest ───────────────────────────────────────
print("\n[5] Building monthly-rebalance lexical-density portfolio …")
port_returns = {}
date_range   = pd.date_range(start=IS_START, end=FULL_END, freq="ME")

for rebalance_date in date_range:
    signal_cutoff = rebalance_date - pd.Timedelta(days=FILING_LAG_DAYS)

    scores = {}
    for t, ttr_series in ld_lookup.items():
        valid = ttr_series[ttr_series.index <= signal_cutoff]
        if len(valid) == 0:
            continue
        scores[t] = float(valid.iloc[-1])

    if len(scores) < N_LONG:
        continue

    ranked = pd.Series(scores).sort_values(ascending=False)
    top    = list(ranked.head(N_LONG).index)

    # Collect next month's return for each holding
    next_month  = rebalance_date + pd.DateOffset(months=1)
    cohort_rets = []
    for t in top:
        if t in monthly_returns:
            r    = monthly_returns[t]
            mask = (r.index.year == next_month.year) & (r.index.month == next_month.month)
            if mask.any():
                cohort_rets.append(float(r[mask].iloc[0]))

    if cohort_rets:
        port_returns[next_month] = np.mean(cohort_rets)

if not port_returns:
    print("\nERROR: No portfolio returns generated.")
    import sys; sys.exit(1)

# ── Step 6: Performance metrics ───────────────────────────────────────────────
port_series = pd.Series(port_returns).sort_index()

IS_mask  = (port_series.index >= IS_START)  & (port_series.index <= IS_END)
OOS_mask = port_series.index >= OOS_START

is_ret  = port_series[IS_mask]
oos_ret = port_series[OOS_mask]

is_stats  = stats(is_ret)
oos_stats = stats(oos_ret)

spy_is  = stats(spy_monthly[(spy_monthly.index >= IS_START) & (spy_monthly.index <= IS_END)])
spy_oos = stats(spy_monthly[spy_monthly.index >= OOS_START])

corr_spy = corr_series(oos_ret, spy_monthly.reindex(oos_ret.index))
wf_ratio = oos_stats["sharpe"] / is_stats["sharpe"] if is_stats["sharpe"] > 0 else 0.0

print(f"\n{'=' * 60}")
print("RESULTS — H290 Lexical Density of EDGAR Filings")
print(f"{'=' * 60}")
print(f"\nIS  (2019-2021): Sharpe={is_stats['sharpe']:.4f}  CAGR={is_stats['cagr']*100:.1f}%"
      f"  MaxDD={is_stats['max_drawdown']*100:.1f}%  NegYrs={is_stats['neg_years']}")
print(f"OOS (2022-2025): Sharpe={oos_stats['sharpe']:.4f}  CAGR={oos_stats['cagr']*100:.1f}%"
      f"  MaxDD={oos_stats['max_drawdown']*100:.1f}%  NegYrs={oos_stats['neg_years']}")
print(f"\nSPY IS:  Sharpe={spy_is['sharpe']:.4f}  OOS: Sharpe={spy_oos['sharpe']:.4f}")
print(f"Walkforward ratio: {wf_ratio:.3f}")
print(f"Corr(H290, SPY) OOS: {corr_spy:.3f}")
print(f"\nPaper benchmark (SSRN 3921091) Sharpe: 0.688 (S&P 500, monthly rebalance)")

gate1 = oos_stats["sharpe"] >= 0.6
gate2 = wf_ratio >= 0.45

print(f"\nGate 1 — OOS Sharpe >= 0.6:        {'PASS' if gate1 else 'FAIL'} ({oos_stats['sharpe']:.4f})")
print(f"Gate 2 — Walkforward ratio >= 0.45: {'PASS' if gate2 else 'FAIL'} ({wf_ratio:.3f})")

verdict = "CONFIRMED" if (gate1 and gate2) else "NOT CONFIRMED"
print(f"\nVERDICT: {verdict}")
print("⚠️  Survivorship bias: universe selected with 2026 knowledge.")
print("⚠️  Small universe (50 stocks) vs paper's S&P 500 (~500 stocks).")
print("⚠️  TTR signal: higher = more diverse vocabulary in filing.")
print("⚠️  200K char text cap may underrepresent full 10-K content.")

results = {
    "hypothesis": "H290",
    "description": "Lexical Density of EDGAR Filings (SSRN 3921091)",
    "signal": "Type-Token Ratio (unique words / total words) of 10-K/10-Q",
    "rebalance": "monthly",
    "filing_lag_days": FILING_LAG_DAYS,
    "text_cap_chars": MAX_TEXT_CHARS,
    "academic_sharpe": 0.688,
    "is_period":  "2019-2021",
    "oos_period": "2022-2025",
    "is_stats":  is_stats,
    "oos_stats": oos_stats,
    "spy_is":    spy_is,
    "spy_oos":   spy_oos,
    "walkforward_ratio": round(wf_ratio, 4),
    "corr_spy_oos": corr_spy,
    "verdict": verdict,
    "survivorship_bias": True,
    "n_tickers_with_ld_data": len(ld_lookup),
}
out_path = RESULT_DIR / "h290_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")
