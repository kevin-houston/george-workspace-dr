#!/usr/bin/env python3
"""
H474 — 8-Specialist LLM Pipeline (Fin-Analyst Architecture) as PEAD Pre-Filter
Source: arXiv:2607.12233 (Rashid et al., Jul 2026) — FinMMEval 2026 Task 3 winner

3-specialist MVP of Fin-Analyst applied to H174 PEAD:
  Specialist-1: 8-K press release (FinBERT, from H174)
  Specialist-2: Analyst revision signal (FMP upgrades/downgrades)
  Specialist-3: Earnings call KPI tone (FMP transcript + GPT-4o-mini)
  Meta-Agent: weighted composite → entry decision

Variants:
  Var A: 3-specialist with equal Meta-Agent weights
  Var B: 3-specialist with Meta-Agent dynamic reweighting by rolling Brier score
  Var C: 2-specialist (8-K FinBERT + analyst revision only — no transcript)
  Var D: H174 baseline (FinBERT only) — sanity check

Gate: OOS WR >= 0.818 AND n >= 15 AND MeanRet >= 6.89% (H174 parity)
IS: 2022-2023  OOS: 2024-2026
"""

import os
import sys
import json
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

VENV_SITE = "/workspace/agent/venv/lib/python3.11/site-packages"
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def specialist_finbert(score: float) -> float:
    """Return FinBERT score (pre-computed by H174 overnight pass)."""
    return float(score)


def specialist_analyst_revision(ticker: str, announcement_date: str) -> float:
    """
    Fraction of upgrades in 5-day window around announcement.
    Returns [0, 1]. 0.5 = neutral (no revisions found).
    """
    if not FMP_API_KEY:
        return 0.5
    date_obj = datetime.strptime(announcement_date, "%Y-%m-%d")
    date_from = (date_obj - timedelta(days=5)).strftime("%Y-%m-%d")
    date_to = (date_obj + timedelta(days=5)).strftime("%Y-%m-%d")
    url = (
        f"https://financialmodelingprep.com/stable/upgrades-downgrades"
        f"?symbol={ticker}&from={date_from}&to={date_to}&apikey={FMP_API_KEY}"
    )
    try:
        data = requests.get(url, timeout=10).json()
        if not isinstance(data, list):
            return 0.5
        ups = sum(1 for d in data if d.get("action", "").lower() in ("upgrade", "buy", "strong buy"))
        downs = sum(1 for d in data if d.get("action", "").lower() in ("downgrade", "sell", "strong sell"))
        total = ups + downs
        return ups / total if total > 0 else 0.5
    except Exception:
        return 0.5


def specialist_call_kpi(ticker: str, announcement_date: str) -> float:
    """
    KPI beat fraction from earnings transcript via FMP + GPT-4o-mini.
    Requires FMP Professional plan (H247 caveat). Returns 0.5 if unavailable.
    """
    if not FMP_API_KEY or not OPENAI_API_KEY:
        return 0.5
    year = announcement_date[:4]
    url = (
        f"https://financialmodelingprep.com/stable/earning-call-transcript"
        f"?symbol={ticker}&year={year}&apikey={FMP_API_KEY}"
    )
    try:
        data = requests.get(url, timeout=15).json()
        if not isinstance(data, list) or not data:
            return 0.5
        transcript = data[0].get("content", "")
        if len(transcript) < 100:
            return 0.5
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            "Count KPIs that beat vs missed expectations in this earnings call. "
            "Return JSON: {\"beat\": N, \"miss\": N}.\n\nTranscript (3000 chars):\n"
            + transcript[:3000]
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=50,
        )
        result = json.loads(resp.choices[0].message.content)
        beat, miss = result.get("beat", 0), result.get("miss", 0)
        return beat / (beat + miss) if (beat + miss) > 0 else 0.5
    except Exception:
        return 0.5


class MetaAgent:
    def __init__(self, n_specialists: int = 3):
        self.weights = np.ones(n_specialists) / n_specialists
        self.history: list = []

    def score(self, signals: list) -> float:
        return float(np.dot(self.weights[:len(signals)], signals))

    def update(self, signals: list, outcome: float):
        """Update per-specialist Brier scores for dynamic reweighting (Var B)."""
        self.history.append({"signals": signals, "outcome": outcome})
        window = self.history[-20:]
        if len(window) < 5:
            return
        n = len(signals)
        brier = np.zeros(n)
        for h in window:
            for i, s in enumerate(h["signals"][:n]):
                brier[i] += (s - h["outcome"]) ** 2
        brier /= len(window)
        inv_b = 1.0 / (brier + 1e-6)
        self.weights[:n] = inv_b / inv_b.sum()

    def entry(self, signals: list, threshold: float = 0.18) -> bool:
        return self.score(signals) >= threshold


def load_h174_events() -> pd.DataFrame:
    """Load H174 event log from paper trading results."""
    paths = [
        "/workspace/agent/backtesting/paper_trading/pead_results.json",
        "/workspace/agent/backtesting/daily/h174_events.csv",
    ]
    for path in paths:
        if Path(path).exists():
            try:
                if path.endswith(".json"):
                    with open(path) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        return pd.DataFrame(data)
                elif path.endswith(".csv"):
                    return pd.read_csv(path, parse_dates=["date"])
            except Exception:
                pass
    print("  [H474] No H174 event log found. Run H174 backtest first to generate event data.")
    return pd.DataFrame(columns=["ticker", "date", "finbert_score", "surprise", "ret_20d"])


def run_backtest(variant: str) -> dict:
    print(f"\n=== H474 {variant} | Fin-Analyst 3-specialist PEAD ===")
    events = load_h174_events()
    if events.empty:
        return {}

    events["date"] = pd.to_datetime(events["date"])
    oos = events[events["date"] >= pd.Timestamp("2024-01-01")].copy()
    if oos.empty:
        print("  No OOS events (need events from 2024 onward).")
        return {}

    required = ["ticker", "date", "finbert_score", "ret_20d"]
    if any(c not in oos.columns for c in required):
        print(f"  Missing columns. Available: {oos.columns.tolist()}")
        return {}

    meta = MetaAgent()
    results_list = []

    for _, row in oos.iterrows():
        ticker = str(row["ticker"])
        date_str = row["date"].strftime("%Y-%m-%d")
        s1 = specialist_finbert(float(row.get("finbert_score", 0)))

        if variant in ("A", "B"):
            s2 = specialist_analyst_revision(ticker, date_str)
            s3 = specialist_call_kpi(ticker, date_str)
            signals = [s1, s2, s3]
        elif variant == "C":
            s2 = specialist_analyst_revision(ticker, date_str)
            signals = [s1, s2]
        else:  # Var D — FinBERT only (H174 baseline)
            signals = [s1]

        if not meta.entry(signals):
            continue

        ret = float(row.get("ret_20d", 0.0))
        results_list.append({"ticker": ticker, "date": date_str, "ret": ret})

        if variant == "B":
            meta.update(signals, 1.0 if ret > 0 else 0.0)

    if not results_list:
        print("  No qualifying events.")
        return {}

    df = pd.DataFrame(results_list)
    n = len(df)
    win_rate = (df["ret"] > 0).mean()
    mean_ret = df["ret"].mean()
    gate = win_rate >= 0.818 and n >= 15 and mean_ret >= 0.0689
    print(f"  n={n}  WR={win_rate:.3f}  MeanRet={mean_ret:.2%}  {'PASS' if gate else 'FAIL'}")
    return {"n": n, "win_rate": win_rate, "mean_ret": mean_ret, "gate": gate}


if __name__ == "__main__":
    results = {v: run_backtest(v) for v in ["A", "B", "C", "D"]}
    print("\n=== H474 Summary ===")
    for name, r in results.items():
        if r:
            print(f"  Var {name}: n={r['n']}  WR={r['win_rate']:.3f}  "
                  f"MeanRet={r['mean_ret']:.2%}  {'PASS' if r['gate'] else 'FAIL'}")
