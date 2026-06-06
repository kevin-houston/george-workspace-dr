"""
H258 — Text-to-Alpha: LLM Metric-Shift Detection in SEC 10-Q Filings
=====================================================================
Source: arXiv:2510.03195 — "From Text to Alpha: Can LLMs Track Evolving
        Signals in Corporate Disclosures?"
        H174 CONFIRMED (FinBERT score>=0.18 + EPS surprise>=0.02) — prerequisite

Hypothesis:
  Corporate 10-Q filings reveal "metric shifts" — management moving emphasis away from
  previously highlighted KPIs (e.g., from revenue to user growth). These shifts predict
  negative abnormal returns. An LLM extractor that identifies the top-5 metrics
  emphasized in current vs. prior-quarter filings, and scores the degree of semantic
  shift, provides independent alpha not captured by FinBERT sentiment (H174 signal).

Mechanism:
  1. For PEAD watchlist candidates (already gated by H174 score>=0.18 + surprise>=0.02),
     fetch current and 1-quarter-prior 10-Q from EDGAR CompanyFacts
  2. Use GPT-4o-mini to extract the top-5 most emphasized financial metrics from each
  3. Compute semantic shift score: 1 - (Jaccard similarity of metric sets)
  4. HIGH shift (>0.6) + negative sentiment direction = additional short signal
     LOW shift (<0.2) + positive sentiment = additional long signal
  5. Use as an overlay/filter on H174, not as a standalone signal

Independence check:
  Correlation of H258 shift signal vs H174 FinBERT score must be < 0.50 to confirm
  it adds independent information.

IS: 2019-01-01 to 2021-12-31
OOS: 2022-01-01 to 2025-12-31
Confirm gates:
  OOS Win Rate > 55% (vs H174 baseline 81.8%)
  OOS Mean Return > 2.0%
  Min OOS events: 20
  Independence: Corr(shift_signal, H174_score) < 0.50

NOTE: Requires OpenAI API key ($OPENAI_API_KEY — available in environment).
EDGAR 10-Q access via edgartools or direct EDGAR REST API.
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore")

RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

OPENAI_KEY    = os.environ.get("OPENAI_API_KEY", "")
EDGAR_AGENT   = os.environ.get("EDGAR_USER_AGENT", "george-agent@nanoclaw.ai")

IS_START  = "2019-01-01"
IS_END    = "2021-12-31"
OOS_START = "2022-01-01"
OOS_END   = "2025-12-31"


def install_deps():
    """Install edgartools and openai if not present."""
    import subprocess
    subprocess.run(
        ["python3", "-m", "pip", "install", "edgartools", "openai", "-q",
         "--break-system-packages"],
        capture_output=True
    )


def fetch_10q_text(ticker: str, cik: str, quarters_back: int = 0) -> str:
    """
    Fetch 10-Q filing text for a given ticker.
    quarters_back=0 → most recent; quarters_back=1 → 1 quarter prior.
    Uses EDGAR EDGAR submissions endpoint.
    Returns empty string on failure.
    """
    import requests
    headers = {"User-Agent": EDGAR_AGENT}
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        data = r.json()
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accessions = filings.get("accessionNumber", [])

        # Find 10-Q filings in order (most recent first)
        tenq_idxs = [i for i, f in enumerate(forms) if f == "10-Q"]
        if len(tenq_idxs) <= quarters_back:
            return ""

        idx = tenq_idxs[quarters_back]
        acc = accessions[idx].replace("-", "")
        cik_padded = cik.zfill(10)
        doc_url = f"https://www.sec.gov/Archives/edgar/{cik_padded}/{acc}/0001.txt"
        # Try primary document index
        idx_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-Q&dateb=&owner=include&count=5&search_text=&output=atom"
        return f"[10-Q accession: {acc}, date: {dates[idx]}]"  # stub — full text fetch in production
    except Exception as e:
        return f"[fetch error: {e}]"


def extract_metrics_llm(text: str, ticker: str) -> list:
    """
    Use GPT-4o-mini to extract top-5 financial metrics emphasized in the filing.
    Returns list of metric names.
    """
    if not OPENAI_KEY:
        print(f"  [WARN] OPENAI_API_KEY not set — using mock for {ticker}")
        return ["revenue", "gross_margin", "operating_income", "eps", "cash_flow"]

    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            messages=[
                {"role": "system", "content":
                    "Extract the top-5 financial metrics most emphasized in this SEC 10-Q text. "
                    "Return ONLY a JSON list of metric names, e.g. [\"revenue\", \"EBITDA\", ...]. "
                    "Focus on KPIs management chose to highlight, not just what appears most often."},
                {"role": "user", "content": f"10-Q text for {ticker}:\n\n{text[:4000]}"}
            ]
        )
        content = resp.choices[0].message.content.strip()
        return json.loads(content)
    except Exception as e:
        print(f"  [WARN] LLM extraction failed for {ticker}: {e}")
        return []


def compute_shift_score(metrics_current: list, metrics_prior: list) -> float:
    """
    Jaccard distance between metric sets.
    Score 0 = identical emphasis; Score 1 = completely different emphasis.
    """
    if not metrics_current or not metrics_prior:
        return 0.5  # unknown
    s_cur = set(m.lower() for m in metrics_current)
    s_pri = set(m.lower() for m in metrics_prior)
    intersection = len(s_cur & s_pri)
    union = len(s_cur | s_pri)
    jaccard_sim = intersection / union if union > 0 else 0.0
    return round(1.0 - jaccard_sim, 4)  # distance = shift


def run_backtest_on_pead_events(events_df: pd.DataFrame) -> dict:
    """
    Given a DataFrame of PEAD events with columns:
    [ticker, date, h174_score, eps_surprise, forward_return_20d,
     shift_score, shift_direction]

    Compute H258 overlay performance: trade only when shift_score confirms H174 direction.
    """
    # H174 baseline (all events passing H174 gate)
    baseline = events_df.copy()
    base_wr   = (baseline["forward_return_20d"] > 0).mean()
    base_mean = baseline["forward_return_20d"].mean()

    # H258 overlay: require SHIFT < 0.3 (metric consistency confirms direction)
    confirmed = events_df[events_df["shift_score"] < 0.3]
    wr_conf   = (confirmed["forward_return_20d"] > 0).mean() if len(confirmed) > 0 else 0.0
    mean_conf = confirmed["forward_return_20d"].mean() if len(confirmed) > 0 else 0.0

    corr_signal_score = events_df["shift_score"].corr(events_df["h174_score"])

    return {
        "n_baseline": len(baseline),
        "wr_baseline": round(float(base_wr), 4),
        "mean_baseline": round(float(base_mean), 4),
        "n_confirmed": len(confirmed),
        "wr_confirmed": round(float(wr_conf), 4),
        "mean_confirmed": round(float(mean_conf), 4),
        "corr_shift_finbert": round(float(corr_signal_score), 4),
    }


# ─────────────────────────────────────────────
# Main execution
# ─────────────────────────────────────────────
print("H258 — Text-to-Alpha: LLM Metric-Shift Detection")
print("=" * 60)
print("SCAFFOLD: Full implementation requires EDGAR 10-Q corpus.")
print("This script sets up the data pipeline and scoring framework.")
print("Run after loading EDGAR 10-Q text for PEAD watchlist candidates.")
print()
print("Pipeline steps:")
print("  1. Load H174 PEAD event log (historical confirmed events)")
print("  2. Fetch 10-Q text for each event (current + prior quarter)")
print("  3. Extract metrics via GPT-4o-mini")
print("  4. Compute shift scores")
print("  5. Run overlay backtest")
print()

# Demo with mock data to validate scoring logic
mock_events = pd.DataFrame({
    "ticker": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"] * 6,
    "date": pd.date_range("2022-01-01", periods=30, freq="ME"),
    "h174_score": np.random.uniform(0.2, 0.8, 30),
    "eps_surprise": np.random.uniform(0.02, 0.15, 30),
    "forward_return_20d": np.random.normal(0.035, 0.08, 30),
    "shift_score": np.random.uniform(0.0, 1.0, 30),
})

result = run_backtest_on_pead_events(mock_events)
print("Mock validation results (random data — not real signal):")
for k, v in result.items():
    print(f"  {k}: {v}")

print("\nConfirm gates:")
print("  OOS Win Rate > 55%")
print("  OOS Mean Return > 2.0%")
print("  Min OOS events: 20")
print("  Corr(shift_signal, H174_score) < 0.50")
print("\nStatus: SCAFFOLD — requires EDGAR 10-Q corpus and H174 event log.")

output = {
    "hypothesis": "H258",
    "title": "Text-to-Alpha: LLM Metric-Shift Detection in SEC 10-Q Filings",
    "status": "SCAFFOLD",
    "source": "arXiv:2510.03195",
    "prerequisite": "H174 CONFIRMED",
    "pipeline": [
        "EDGAR 10-Q text fetch (current + 1 quarter prior)",
        "GPT-4o-mini metric extraction",
        "Jaccard distance shift score",
        "Overlay on H174 PEAD event set",
    ],
    "confirm_gates": {
        "oos_win_rate": 0.55,
        "oos_mean_return": 0.02,
        "min_events": 20,
        "independence_corr": 0.50,
    },
    "mock_validation": result,
}
with open(RESULT_DIR / "h258_results.json", "w") as f:
    json.dump(output, f, indent=2)
print("\nScaffold saved → backtesting/results/h258_results.json")
