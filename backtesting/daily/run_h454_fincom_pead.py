#!/usr/bin/env python3
"""
H454 — FinCom Disagree-or-Commit Multi-Agent PEAD Signal

Source: Li, Zhang et al. (2026) arXiv:2606.00939
        'FinCom: A Multi-Agent Framework for Financial Deliberation
         with Disagree-or-Commit'

Hypothesis: Structured agent deliberation where each model must explicitly
critique or commit to peers' reasoning prevents groupthink and improves
PEAD signal quality beyond H174's single-model FinBERT score.

Variants:
  A: DoC 3-agent (FinBERT + EPS extractor + guidance extractor)
  B: DoC 2-agent (FinBERT + EPS, skip guidance when not parseable)
  C: H174 baseline (single FinBERT, score>=0.18, surprise>=0.02)
  D: Simple ensemble mean (no DoC, average 3 scores)
  E: DoC with veto (any agent below 0.10 blocks trade)

IS: 2019-2022, OOS: 2023-2026
Gate: OOS WR > 81.8% AND n >= 20 (H174 baseline: WR=81.8%, n=22)
"""

import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests
from transformers import pipeline

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

STRATEGY = 'H454'
EDGAR_BASE = 'https://efts.sec.gov/LATEST/search-index?q=%22Item+2.02%22&dateRange=custom'
FINBERT_MODEL = 'ProsusAI/finbert'
OPENAI_MODEL = 'gpt-4o-mini'
RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

IS_START = '2019-01-01'
IS_END   = '2022-12-31'
OOS_START = '2023-01-01'
OOS_END   = '2026-07-21'

H174_SCORE_GATE    = 0.18
H174_SURPRISE_GATE = 0.02
DOC_VETO_THRESHOLD = 0.10  # Var E: any agent below this blocks trade


def finbert_score(text: str, pipe) -> float:
    """Returns positive sentiment probability from FinBERT."""
    result = pipe(text[:512], truncation=True)[0]
    scores = {r['label']: r['score'] for r in result} if isinstance(result, list) else {result['label']: result['score']}
    return scores.get('positive', 0.0)


def eps_agent_score(text: str, client: Optional[object]) -> float:
    """
    EPS extraction agent: returns 0.0-1.0 probability of positive earnings surprise.
    Uses GPT-4o-mini for structured extraction.
    """
    if not client:
        return 0.5  # neutral when API unavailable
    prompt = (
        "You are an earnings analysis agent. Read this 8-K excerpt and assess "
        "whether the company's earnings BEAT expectations. "
        "Reply with ONLY a JSON: {\"beat\": true/false, \"confidence\": 0.0-1.0, "
        "\"eps_actual\": number_or_null, \"eps_estimate\": number_or_null}\n\n"
        f"8-K excerpt:\n{text[:1000]}"
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            response_format={'type': 'json_object'},
        )
        data = json.loads(resp.choices[0].message.content)
        if data.get('beat'):
            return min(0.5 + data.get('confidence', 0.5) * 0.5, 1.0)
        else:
            return max(0.5 - data.get('confidence', 0.5) * 0.5, 0.0)
    except Exception:
        return 0.5


def guidance_agent_score(text: str, client: Optional[object]) -> float:
    """
    Forward guidance extraction agent: positive guidance = high score.
    """
    if not client:
        return 0.5
    prompt = (
        "You are a forward guidance analyst. Read this 8-K excerpt and assess "
        "whether the company's forward guidance is POSITIVE (raised/beat). "
        "Reply with ONLY a JSON: {\"positive_guidance\": true/false, "
        "\"confidence\": 0.0-1.0}\n\n"
        f"8-K excerpt:\n{text[:1000]}"
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            response_format={'type': 'json_object'},
        )
        data = json.loads(resp.choices[0].message.content)
        if data.get('positive_guidance'):
            return min(0.5 + data.get('confidence', 0.5) * 0.5, 1.0)
        else:
            return max(0.5 - data.get('confidence', 0.5) * 0.5, 0.0)
    except Exception:
        return 0.5


def disagree_or_commit(scores: dict, text: str, client: Optional[object]) -> dict:
    """
    DoC round: agents receive all scores and must COMMIT or DISAGREE with reason.
    Returns final consensus score or None if unresolved disagreement.
    """
    if not client:
        return {'score': np.mean(list(scores.values())), 'resolved': True}

    agents_str = json.dumps({k: round(v, 3) for k, v in scores.items()})
    prompt = (
        f"Three financial analysis agents have scored this 8-K:\n{agents_str}\n\n"
        "Each agent must respond COMMIT or DISAGREE with a specific reason.\n"
        "A score gap >0.3 between agents typically signals disagreement.\n"
        "Reply with ONLY JSON: {\"finbert\": \"COMMIT\"|\"DISAGREE: reason\", "
        "\"eps\": \"COMMIT\"|\"DISAGREE: reason\", "
        "\"guidance\": \"COMMIT\"|\"DISAGREE: reason\", "
        "\"consensus\": 0.0-1.0}\n\n"
        f"8-K excerpt:\n{text[:500]}"
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            response_format={'type': 'json_object'},
        )
        data = json.loads(resp.choices[0].message.content)
        disagreements = [k for k, v in data.items()
                        if k in ('finbert', 'eps', 'guidance')
                        and isinstance(v, str) and v.startswith('DISAGREE')]
        if disagreements:
            return {'score': data.get('consensus', 0.5),
                    'resolved': False,
                    'disagreements': disagreements}
        return {'score': data.get('consensus', np.mean(list(scores.values()))),
                'resolved': True}
    except Exception:
        return {'score': np.mean(list(scores.values())), 'resolved': True}


def evaluate_event(text: str, surprise: float, variant: str,
                   finbert_pipe, openai_client) -> Optional[float]:
    """
    Returns composite score for a single 8-K event, or None if trade blocked.
    """
    fb_score = finbert_score(text, finbert_pipe)

    if variant == 'C':  # H174 baseline
        if fb_score >= H174_SCORE_GATE and surprise >= H174_SURPRISE_GATE:
            return fb_score
        return None

    eps_score = eps_agent_score(text, openai_client)

    if variant in ('A', 'D', 'E'):
        guidance_score = guidance_agent_score(text, openai_client)
        agent_scores = {'finbert': fb_score, 'eps': eps_score, 'guidance': guidance_score}
    else:  # Var B: 2-agent
        agent_scores = {'finbert': fb_score, 'eps': eps_score}

    if variant == 'D':  # simple mean
        score = np.mean(list(agent_scores.values()))
        return score if score >= H174_SCORE_GATE else None

    if variant == 'E':  # veto
        if any(v < DOC_VETO_THRESHOLD for v in agent_scores.values()):
            return None  # blocked by veto

    # DoC round for A, B, E
    doc_result = disagree_or_commit(agent_scores, text, openai_client)
    if not doc_result['resolved']:
        return None  # unresolved disagreement: skip trade
    score = doc_result['score']
    return score if score >= H174_SCORE_GATE else None


def main():
    print(f'=== {STRATEGY} FinCom Disagree-or-Commit PEAD ===')
    print(f'IS: {IS_START}-{IS_END} | OOS: {OOS_START}-{OOS_END}')
    print(f'Gate: OOS WR > 81.8% AND n >= 20 (H174 baseline)')
    print()

    # Load pre-scored H174 events (reuse EDGAR downloads from prior runs)
    h174_events_path = Path('/workspace/agent/backtesting/results/h174_events.json')
    if not h174_events_path.exists():
        print('ERROR: h174_events.json not found. Run H174 backtest first to generate event cache.')
        return

    with open(h174_events_path) as f:
        events = json.load(f)

    print(f'Loaded {len(events)} H174 events from cache')

    finbert_pipe = pipeline('text-classification', model=FINBERT_MODEL,
                            top_k=None, truncation=True)
    openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY')) if OPENAI_AVAILABLE else None
    if not openai_client:
        print('WARNING: OpenAI unavailable — EPS/guidance agents return neutral 0.5')

    results = {}
    for var in ['A', 'B', 'C', 'D', 'E']:
        trades = []
        for ev in events:
            text = ev.get('text', '')
            surprise = ev.get('surprise', 0.0)
            ret = ev.get('forward_20d_return', None)
            date = ev.get('date', '')
            if ret is None:
                continue
            score = evaluate_event(text, surprise, var, finbert_pipe, openai_client)
            if score is not None:
                trades.append({'date': date, 'return': ret, 'score': score})

        df = pd.DataFrame(trades)
        if len(df) == 0:
            results[var] = {'n': 0, 'wr': 0.0, 'mean_ret': 0.0}
            continue
        df['date'] = pd.to_datetime(df['date'])
        results[var] = df

    print('=== IS Results (2019-2022) ===')
    is_stats = {}
    for var, df in results.items():
        if isinstance(df, dict):
            print(f'  Var {var}: n=0')
            is_stats[var] = {'n': 0, 'wr': 0.0, 'mean_ret': 0.0}
            continue
        mask = (df['date'] >= IS_START) & (df['date'] <= IS_END)
        r = df[mask]
        wr = (r['return'] > 0).mean() if len(r) > 0 else 0.0
        mr = r['return'].mean() if len(r) > 0 else 0.0
        print(f'  Var {var}: n={len(r)}, WR={wr:.1%}, MeanRet={mr:.2%}')
        is_stats[var] = {'n': len(r), 'wr': round(wr, 3), 'mean_ret': round(mr, 4)}

    print()
    print('=== OOS Results (2023-2026) ===')
    oos_stats = {}
    for var, df in results.items():
        if isinstance(df, dict):
            print(f'  Var {var}: n=0')
            oos_stats[var] = {'n': 0, 'wr': 0.0, 'mean_ret': 0.0}
            continue
        mask = (df['date'] >= OOS_START) & (df['date'] <= OOS_END)
        r = df[mask]
        wr = (r['return'] > 0).mean() if len(r) > 0 else 0.0
        mr = r['return'].mean() if len(r) > 0 else 0.0
        print(f'  Var {var}: n={len(r)}, WR={wr:.1%}, MeanRet={mr:.2%}')
        oos_stats[var] = {'n': len(r), 'wr': round(wr, 3), 'mean_ret': round(mr, 4)}

    WR_GATE = 0.818
    N_GATE  = 20
    print(f'\n=== Gate Check (WR > {WR_GATE:.1%} AND n >= {N_GATE}) ===')
    confirmed = []
    for var in results:
        s = oos_stats[var]
        status = 'PASS' if s['wr'] > WR_GATE and s['n'] >= N_GATE else 'FAIL'
        print(f'  Var {var}: WR={s["wr"]:.1%} n={s["n"]} [{status}]')
        if status == 'PASS':
            confirmed.append(var)

    verdict = 'CONFIRMED' if confirmed else 'NOT CONFIRMED'
    print(f'\nVERDICT: {verdict}')
    if confirmed:
        print(f'Confirmed variants: {confirmed}')

    output = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'gate_wr': WR_GATE,
        'gate_n': N_GATE,
        'h174_baseline': {'wr': 0.818, 'n': 22, 'mean_ret': 0.0689},
        'verdict': verdict,
        'confirmed_variants': confirmed,
        'is_stats': is_stats,
        'oos_stats': oos_stats,
    }
    out_path = RESULTS_DIR / 'h454_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f'\nResults: {out_path}')


if __name__ == '__main__':
    main()
