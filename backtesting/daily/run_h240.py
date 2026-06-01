#!/usr/bin/env python3
"""
H240: PEAD Fine-Grained Decomposition — Guidance Quality as Third Filter

Source: arXiv:2602.23330 (Feb 2026) — fine-grained task decomposition improves
  LLM system performance. Applied to PEAD: add guidance quality as third filter.

H174 dual filter:
  (1) FinBERT score >= 0.18 (positive tone in 8-K)
  (2) EPS surprise >= 0.02 (quantitative beat)

H240 triple filter (adds):
  (3) Guidance: management raised or affirmed forward guidance

Source: Guidance raise is the strongest PEAD continuation predictor beyond day 0
  (Nguyen et al. 2022, Journal of Finance; also Lennox & Li 2012).

Implementation:
  - Extract guidance language from 8-K Item 2.02 text via keyword matching + GPT-4o-mini
  - Classify: RAISE (guidance upgraded), AFFIRM (reiterated/maintained), LOWER (cut/withdrawn)
  - Triple filter: score>=0.18 AND surprise>=0.02 AND guidance in {RAISE, AFFIRM}
  - Also test RAISE-only as the most restrictive filter

IS: 2019-2022, OOS: 2023-2025 (aligns with H232 framework)
Confirm: OOS WR > 83% OR MeanRet > 7.5% (H225 bar)
H174 baseline: WR=81.8%, MeanRet=6.89%, n=22
"""

import os
import json
import re
import numpy as np
import pandas as pd
from pathlib import Path
from openai import OpenAI

# H174 cache files
H163_CACHE_DIR = 'backtesting/daily'  # h163_8k_*.txt and h163_scored_results.csv

GUIDANCE_PROMPT = """
Analyze this earnings press release excerpt and classify the company's forward guidance.

Excerpt:
{text}

Classify guidance as ONE of:
- RAISE: company raised, increased, or upgraded its forward outlook/guidance
- AFFIRM: company affirmed, maintained, reaffirmed, or reiterated prior guidance
- LOWER: company lowered, reduced, withdrew guidance OR provided no guidance
- NONE: no forward-looking guidance statement found

Return ONLY valid JSON: {{"guidance": "RAISE"|"AFFIRM"|"LOWER"|"NONE",
  "evidence": "brief quote from text supporting classification"}}"""

# Keyword patterns for fast pre-filtering (before LLM call)
RAISE_KEYWORDS = [
    r'raises?\s+(?:its\s+)?(?:full.year|annual|quarterly|fiscal|outlook|guidance)',
    r'increases?\s+(?:its\s+)?(?:full.year|annual|quarterly|fiscal|outlook|guidance)',
    r'(?:raised|increased|updated|raised\s+guidance)',
    r'above\s+(?:prior|previous|its)\s+(?:guidance|outlook)',
    r'above\s+the\s+(?:high|top)\s+end\s+of',
    r'increases?\s+(?:its\s+)?(?:eps|revenue|earnings)\s+(?:guidance|outlook|forecast)',
]
AFFIRM_KEYWORDS = [
    r'reaffirms?\s+(?:its\s+)?(?:full.year|annual|quarterly|fiscal|outlook|guidance)',
    r'maintains?\s+(?:its\s+)?(?:full.year|annual|quarterly|fiscal|outlook|guidance)',
    r'reiterate[sd]?\s+(?:its\s+)?(?:full.year|annual|quarterly|fiscal|outlook|guidance)',
    r'on\s+track\s+to\s+(?:meet|achieve)',
    r'consistent\s+with\s+(?:prior|previous|our)\s+(?:guidance|outlook)',
]
LOWER_KEYWORDS = [
    r'lowers?\s+(?:its\s+)?(?:full.year|annual|quarterly|fiscal|outlook|guidance)',
    r'reduces?\s+(?:its\s+)?(?:full.year|annual|quarterly|fiscal|outlook|guidance)',
    r'withdraw[sn]?\s+(?:its\s+)?(?:full.year|annual|quarterly|fiscal|outlook|guidance)',
    r'below\s+(?:prior|previous|its)\s+(?:guidance|outlook)',
    r'below\s+the\s+(?:low|bottom)\s+end\s+of',
    r'not\s+(?:providing|reaffirming|reinstating)\s+(?:guidance|outlook)',
]


def classify_guidance_fast(text):
    """
    Fast keyword-based guidance classification.
    Returns ('RAISE'|'AFFIRM'|'LOWER'|'NONE', confidence)
    confidence: 'high' = clear keyword match, 'uncertain' = no clear match
    """
    text_lower = text.lower()
    for pattern in RAISE_KEYWORDS:
        if re.search(pattern, text_lower):
            return 'RAISE', 'high'
    for pattern in AFFIRM_KEYWORDS:
        if re.search(pattern, text_lower):
            return 'AFFIRM', 'high'
    for pattern in LOWER_KEYWORDS:
        if re.search(pattern, text_lower):
            return 'LOWER', 'high'
    return 'NONE', 'uncertain'


def classify_guidance_llm(client, text, max_chars=3000):
    """
    LLM-based guidance classification for uncertain cases.
    Uses first max_chars characters of 8-K text (guidance usually in first section).
    """
    excerpt = text[:max_chars]
    prompt = GUIDANCE_PROMPT.format(text=excerpt)
    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=100,
        )
        result = json.loads(response.choices[0].message.content)
        return result.get('guidance', 'NONE'), result.get('evidence', '')
    except Exception:
        return 'NONE', ''


def load_h174_results():
    """
    Load the H174 cached 8-K texts and scored results.
    Returns: scored_df (ticker, date, finbert_score, eps_surprise, h174_pass)
    """
    results_path = Path('backtesting/results/h174_results.json')
    if not results_path.exists():
        raise FileNotFoundError('H174 results not found. Run run_h174.py first.')
    with open(results_path) as f:
        h174 = json.load(f)
    # Load event list from H163 cache
    cache_files = sorted(Path(H163_CACHE_DIR).glob('h163_8k_*.txt'))
    events = []
    for f in cache_files:
        parts = f.stem.split('_')  # h163_8k_{ticker}_{date}
        if len(parts) >= 4:
            ticker = parts[2]
            date_str = parts[3]
            events.append({'ticker': ticker, 'date': date_str, 'file': str(f)})
    return events, h174


def run_h240(start_is='2019-01-01', end_is='2022-12-31',
             start_oos='2023-01-01', end_oos='2025-12-31',
             use_llm_fallback=True):
    """
    H240: Add guidance quality as third PEAD filter.
    Variants:
    A: H174 baseline (FinBERT >= 0.18 AND surprise >= 0.02)
    B: Triple filter (A + guidance in {RAISE, AFFIRM})
    C: Strictest (A + guidance == RAISE only)
    """
    print('H240: PEAD Fine-Grained Guidance Filter')

    # Load H174 event data
    try:
        events, h174_data = load_h174_results()
    except FileNotFoundError as e:
        print(f'ERROR: {e}')
        print('Run run_h174.py first to generate the cached 8-K results.')
        return None

    client = OpenAI() if use_llm_fallback else None

    # Score guidance for each event
    guidance_results = []
    for event in events:
        ticker = event['ticker']
        date_str = event['date']
        try:
            with open(event['file']) as f:
                text = f.read()
        except Exception:
            continue

        # Fast keyword classification
        guidance, confidence = classify_guidance_fast(text)

        # LLM fallback for uncertain cases
        if confidence == 'uncertain' and use_llm_fallback and client:
            guidance, evidence = classify_guidance_llm(client, text)

        guidance_results.append({
            'ticker': ticker,
            'date': date_str,
            'guidance': guidance,
        })

    guidance_df = pd.DataFrame(guidance_results)
    guidance_df['date'] = pd.to_datetime(guidance_df['date'])

    print(f'\nGuidance distribution:')
    print(guidance_df['guidance'].value_counts())
    print(f'RAISE rate: {(guidance_df["guidance"]=="RAISE").mean():.1%}')
    print(f'AFFIRM rate: {(guidance_df["guidance"]=="AFFIRM").mean():.1%}')

    # Load H174 event returns (forward returns from pead_overnight results)
    # Using the H163 OOS framework with forward returns
    # (events file should contain ticker, date, finbert_score, surprise, forward_ret)
    scored_path = Path('backtesting/results/h174_event_returns.json')
    if not scored_path.exists():
        print('H174 event returns file not found. Generating from run_h174.py output...')
        return None

    with open(scored_path) as f:
        event_returns = json.load(f)

    er_df = pd.DataFrame(event_returns)
    er_df['date'] = pd.to_datetime(er_df['date'])

    # Merge guidance with event returns
    merged = er_df.merge(guidance_df, on=['ticker', 'date'], how='left')
    merged['guidance'] = merged['guidance'].fillna('NONE')

    # Filter to IS and OOS periods
    is_mask = (merged['date'] >= start_is) & (merged['date'] <= end_is)
    oos_mask = (merged['date'] >= start_oos) & (merged['date'] <= end_oos)

    results = {}
    for period_name, mask in [('IS', is_mask), ('OOS', oos_mask)]:
        for variant, filter_cond in [
            ('A_baseline', (merged['finbert_score'] >= 0.18) & (merged['eps_surprise'] >= 0.02)),
            ('B_triple', (merged['finbert_score'] >= 0.18) & (merged['eps_surprise'] >= 0.02)
                         & (merged['guidance'].isin(['RAISE', 'AFFIRM']))),
            ('C_raise_only', (merged['finbert_score'] >= 0.18) & (merged['eps_surprise'] >= 0.02)
                             & (merged['guidance'] == 'RAISE')),
        ]:
            subset = merged[mask & filter_cond]
            n = len(subset)
            if n < 5:
                results[f'{variant}_{period_name}'] = {'n': n, 'insufficient': True}
                continue
            wr = (subset['forward_ret'] > 0).mean()
            mean_ret = subset['forward_ret'].mean()
            results[f'{variant}_{period_name}'] = {
                'n': n,
                'wr': round(wr, 3),
                'mean_ret': round(mean_ret, 4),
            }

    print('\nResults:')
    for k, v in results.items():
        print(f'  {k}: {v}')

    # Save
    out_path = 'backtesting/results/h240_pead_guidance.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'\nSaved to {out_path}')
    print(f'H174 baseline (OOS): WR=81.8%, MeanRet=6.89%, n=22')
    print(f'Confirm gate: OOS WR > 83% OR MeanRet > 7.5%')
    return results


if __name__ == '__main__':
    run_h240()
