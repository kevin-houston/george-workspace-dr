#!/usr/bin/env python3
"""
H426 — FinDPO DPO-Aligned LLM as H174 8-K Scorer

Source: arXiv:2507.18417 (Iacovides, Zhou & Mandic, Jul 2025)
FinDPO: DPO-aligned Llama-3-8B-Instruct for financial sentiment.
DPO avoids SFT memorization; produces continuous scores via
calibration layer on discrete {positive, neutral, negative} outputs.

Hypothesis: DPO alignment better generalizes to novel earnings
language than FinBERT SFT, improving H174 8-K scoring quality.
Drop-in scorer replacement: score >= 0.18 AND surprise >= 0.02 thresholds
retained; only the scorer changes.

Gate:
  OOS WR > 0.818 AND n >= 15 (H174 baseline)
  IS: 2020-2022, OOS: 2023-present

Caveats:
  - Llama-3-8B requires GPU or quantized CPU inference (~8B params)
  - DPO-aligned checkpoint not publicly released; must finetune from scratch
    using ProsusAI/FinSentiment or similar labeled financial news
  - Fallback plan: GPT-4o-mini zero-shot with explicit preference framing
    (compare positive vs negative completion logprobs) as FinDPO proxy
  - OPENAI_API_KEY available in env for GPT-4o-mini fallback
  - H174 pipeline unchanged: pead_overnight.py loads 8-K, passes to scorer,
    applies threshold gates. Only scorer module swapped.

Implementation plan:
  Phase 1 (zero-shot GPT-4o-mini DPO-style):
    - Prompt: 'Score the following earnings press release for positive
      post-earnings drift on a scale 0-1. Consider tone, guidance,
      beat/miss signals. Return a JSON {score: float, rationale: str}'
    - Compare: finbert_score vs gpt_score on historical H174 events
    - IS calibration: find score threshold that matches H174 n=22 events
  Phase 2 (if GPU available):
    - Finetune Llama-3-8B with DPO on labeled financial sentences
    - Convert discrete labels to continuous scores via softmax calibration
    - Deploy via llama.cpp quantized for CPU inference
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# === CONFIGURATION ===
STRATEGY = 'H426'
IS_START = '2020-01-01'
IS_END   = '2022-12-31'
OOS_START = '2023-01-01'
OOS_END   = None  # through present

# H174 baseline thresholds (retain unchanged)
SCORE_THRESHOLD = 0.18  # FinBERT score threshold
SURPRISE_THRESHOLD = 0.02  # EPS surprise threshold

# GPT-4o-mini fallback settings
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
GPT_MODEL = 'gpt-4o-mini'
GPT_MAX_TOKENS = 200

# Data paths
WORKSPACE = Path('/workspace/agent')
PEAD_DATA = WORKSPACE / 'backtesting' / 'daily'
RESULTS_DIR = WORKSPACE / 'backtesting' / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def score_8k_gpt(text: str, client) -> dict:
    """
    GPT-4o-mini DPO-style 8-K scorer.
    
    Uses explicit preference framing inspired by FinDPO:
    instead of binary classify, asks for continuous drift probability.
    """
    prompt = (
        "You are a financial analyst evaluating whether this earnings press release "
        "indicates positive post-earnings announcement drift (PEAD) over the next 20 trading days. "
        "Consider: EPS beat/miss signals, revenue guidance, tone of management commentary, "
        "forward-looking language. "
        "Return ONLY a JSON object with keys: "
        '{{"score": <float 0-1 where 1=strong positive drift expected>, '
        '"rationale": <one sentence>}}\n\n'
        f"PRESS RELEASE:\n{text[:3000]}"
    )
    
    try:
        import openai
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GPT_MAX_TOKENS,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return {
            'score': float(result.get('score', 0.0)),
            'rationale': result.get('rationale', ''),
            'model': GPT_MODEL
        }
    except Exception as e:
        print(f"  GPT scoring failed: {e}")
        return {'score': 0.0, 'rationale': str(e), 'model': 'error'}


def load_h174_events() -> pd.DataFrame:
    """
    Load historical H174 events from the confirmed 8-K pipeline.
    Returns DataFrame with columns: ticker, date, finbert_score, eps_surprise,
    entry_price, exit_price, return, label (1=win, 0=loss)
    
    STUB: In production, load from pead_overnight log files and
    backtesting/results/h174_results.json if it exists.
    """
    # Attempt to load from existing H174 results
    h174_path = RESULTS_DIR / 'h174_results.json'
    if h174_path.exists():
        with open(h174_path) as f:
            data = json.load(f)
        print(f"Loaded {len(data.get('events', []))} H174 events from results file")
        return pd.DataFrame(data.get('events', []))
    
    print("H174 results file not found. Run run_h174.py first to generate event history.")
    print("STUB: returning empty DataFrame for scaffold testing")
    return pd.DataFrame(columns=[
        'ticker', 'date', 'finbert_score', 'eps_surprise',
        'entry_price', 'exit_price', 'return_20d', 'win'
    ])


def run_comparison_backtest(events_df: pd.DataFrame) -> dict:
    """
    Compare FinBERT vs FinDPO (GPT-4o-mini proxy) scoring on historical events.
    
    For each H174 event:
    1. Re-score the 8-K text with GPT-4o-mini FinDPO-style prompt
    2. Apply same thresholds (score >= 0.18, surprise >= 0.02)
    3. Compare: which scorer captures more wins?
    
    Returns dict with IS/OOS metrics for both scorers.
    """
    if events_df.empty:
        print("No events to evaluate. Exiting.")
        return {}
    
    # Initialize OpenAI client if available
    gpt_client = None
    if OPENAI_API_KEY:
        try:
            import openai
            gpt_client = openai.OpenAI(api_key=OPENAI_API_KEY)
            print(f"OpenAI client initialized. Using {GPT_MODEL}.")
        except ImportError:
            print("openai package not installed. Install with: pip install openai")
    
    results = []
    for _, row in events_df.iterrows():
        event = dict(row)
        
        # Original FinBERT scoring (already in event data)
        finbert_pass = (
            event.get('finbert_score', 0) >= SCORE_THRESHOLD and
            event.get('eps_surprise', 0) >= SURPRISE_THRESHOLD
        )
        
        # FinDPO proxy scoring (GPT-4o-mini)
        gpt_score = 0.0
        if gpt_client and event.get('text'):
            scored = score_8k_gpt(event['text'], gpt_client)
            gpt_score = scored['score']
            time.sleep(0.5)  # Rate limit
        
        findpo_pass = (
            gpt_score >= SCORE_THRESHOLD and
            event.get('eps_surprise', 0) >= SURPRISE_THRESHOLD
        )
        
        results.append({
            **event,
            'gpt_score': gpt_score,
            'finbert_pass': finbert_pass,
            'findpo_pass': findpo_pass,
        })
    
    df = pd.DataFrame(results)
    
    # Split IS/OOS
    df['date'] = pd.to_datetime(df['date'])
    is_mask = (df['date'] >= IS_START) & (df['date'] <= IS_END)
    oos_mask = df['date'] >= OOS_START
    
    def calc_metrics(subset, scorer_col):
        sel = subset[subset[scorer_col]]
        if len(sel) == 0:
            return {'n': 0, 'wr': 0, 'mean_ret': 0}
        wins = sel['win'].sum() if 'win' in sel.columns else 0
        mean_ret = sel['return_20d'].mean() if 'return_20d' in sel.columns else 0
        return {
            'n': len(sel),
            'wr': wins / len(sel) if len(sel) > 0 else 0,
            'mean_ret': mean_ret
        }
    
    results_summary = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'is_period': f'{IS_START} to {IS_END}',
        'oos_period': f'{OOS_START} to present',
        'finbert_is': calc_metrics(df[is_mask], 'finbert_pass'),
        'finbert_oos': calc_metrics(df[oos_mask], 'finbert_pass'),
        'findpo_is': calc_metrics(df[is_mask], 'findpo_pass'),
        'findpo_oos': calc_metrics(df[oos_mask], 'findpo_pass'),
        'gate_oos_wr': 0.818,
        'gate_min_n': 15,
        'total_events': len(df)
    }
    
    # Determine confirmation status
    oos_metrics = results_summary['findpo_oos']
    confirmed = (
        oos_metrics['wr'] > 0.818 and
        oos_metrics['n'] >= 15
    )
    results_summary['confirmed'] = confirmed
    results_summary['verdict'] = 'CONFIRMED' if confirmed else 'NOT CONFIRMED'
    
    return results_summary


if __name__ == '__main__':
    print(f"=== {STRATEGY} FinDPO PEAD Scorer Comparison ===")
    print(f"Gate: OOS WR > 81.8%, n >= 15 (H174 baseline)")
    print()
    
    # Load historical H174 events
    events = load_h174_events()
    print(f"Total H174 events loaded: {len(events)}")
    
    if events.empty:
        print("\nSTUB RUN: No event data available.")
        print("Prerequisites:")
        print("  1. Run run_h174.py to populate backtesting/results/h174_results.json")
        print("  2. Ensure OPENAI_API_KEY is set in environment")
        print("  3. Or: provide path to 8-K text corpus with historical FinBERT scores")
        print("\nFallback path: use pead_overnight.log to reconstruct event history")
    else:
        results = run_comparison_backtest(events)
        
        # Save results
        out_path = RESULTS_DIR / 'h426_results.json'
        with open(out_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to {out_path}")
        
        print(f"\n=== {STRATEGY} RESULTS ===")
        print(f"FinBERT IS:  n={results['finbert_is']['n']}, WR={results['finbert_is']['wr']:.1%}, MeanRet={results['finbert_is']['mean_ret']:.2%}")
        print(f"FinBERT OOS: n={results['finbert_oos']['n']}, WR={results['finbert_oos']['wr']:.1%}, MeanRet={results['finbert_oos']['mean_ret']:.2%}")
        print(f"FinDPO IS:   n={results['findpo_is']['n']}, WR={results['findpo_is']['wr']:.1%}, MeanRet={results['findpo_is']['mean_ret']:.2%}")
        print(f"FinDPO OOS:  n={results['findpo_oos']['n']}, WR={results['findpo_oos']['wr']:.1%}, MeanRet={results['findpo_oos']['mean_ret']:.2%}")
        print(f"\nVerdict: {results['verdict']}")
        if results['confirmed']:
            print(">> FinDPO outperforms FinBERT baseline — deploy as H174 scorer upgrade")
        else:
            print(">> FinDPO does not beat H174 gate — retain FinBERT")
