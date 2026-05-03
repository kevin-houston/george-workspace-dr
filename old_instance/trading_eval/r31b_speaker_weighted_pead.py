#!/usr/bin/env python3
"""
R31b — Speaker-Weighted FinBERT Text PEAD
Upgrade of R31 text PEAD (r31_text_pead.py) implementing speaker-role weighting
following arXiv:2604.13260 ('Which Voices Move Markets?' Sidhu, Fan, Pishkar).

Core change vs R31: instead of averaging all FinBERT sentence scores equally,
weight by speaker role using IC-derived weights:
  Analyst:   0.488  (dominant signal — asks the hard questions)
  CFO:       0.295  (finance-specific authority)
  Executive: 0.159  (other executives)
  Other:     0.058  (operators, misc — minimal signal)

Expected improvement: OOS IC from ~0.115 to ~0.142 (+24%). Per-trade Sharpe
expected to improve from R31 baseline 1.322 → ~1.6-2.0+.

Inputs:
  - EDGAR earnings call transcripts (8-K exhibits or SeekingAlpha HTML)
  - Speaker labels parsed from transcript XML/VTT/HTML tags
  - yfinance OHLCV for S&P 500 tickers (same universe as R31)

Pipeline:
  1. Load earnings call transcripts (same corpus as R31)
  2. Parse speaker labels (CFO/CEO/Analyst/Other) using heuristics on name/title
  3. Run FinBERT sentence-level scoring: S_i = P(positive)_i - P(negative)_i
  4. Aggregate with speaker weights:
       weighted_score = sum(S_i * w_role_i) / sum(w_role_i for all i)
  5. Construct text surprise: weighted_score - trailing_12Q_weighted_avg_score
  6. Long signal: text_surprise > 0 AND price gap > 2% (PEAD entry condition)
  7. 3-day confirmation window (from R31 best variant)
  8. RegimeGuard: VIX > 25 → skip LLM-dependent layers (VIX>30 for PEAD trades)
  9. Hold 20 days, equal-weight portfolio

Reference:
  arXiv:2604.13260 — 16,428 S&P 500 calls, 2015-2025, 6.5M sentences
  OOS Spearman IC: 0.142 | Monthly FF5 alpha: 2.03% (t=6.49)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from datetime import datetime, timedelta
import re
import json
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# SPEAKER WEIGHTS (from arXiv:2604.13260, IC-derived, frozen)
# ============================================================
SPEAKER_WEIGHTS = {
    'analyst':   0.488,  # sell-side analysts in Q&A
    'cfo':       0.295,  # CFO prepared remarks + Q&A
    'executive': 0.159,  # CEO, President, COO, CTO, MD
    'other':     0.058,  # operators, other participants
}

def classify_speaker_role(speaker_name: str, speaker_title: str = '') -> str:
    """
    Classify speaker into one of four roles based on name/title.
    Speaker labels in EDGAR transcripts typically include name + affiliation.
    """
    combined = f"{speaker_name} {speaker_title}".lower()
    # CFO first (most specific)
    if any(t in combined for t in ['cfo', 'chief financial', 'finance officer']):
        return 'cfo'
    # Analysts: typically identified by sell-side firm affiliation
    # In SeekingAlpha/EDGAR format, analysts have 'Analyst' in title or 'Research' firm
    if any(t in combined for t in ['analyst', 'research', 'securities', 'capital markets',
                                    'bank', 'equity', 'llc', 'lp', 'partners', 'advisors']):
        return 'analyst'
    # Executive roles
    if any(t in combined for t in ['ceo', 'president', 'chairman', 'chief executive',
                                    'chief operating', 'coo', 'cto', 'chief technology',
                                    'managing director', 'vice president', 'svp', 'evp']):
        return 'executive'
    return 'other'


def compute_speaker_weighted_sentiment(
    sentences_with_roles: list,  # List of (sentence_text, role_str, finbert_score)
    weights: dict = SPEAKER_WEIGHTS
) -> float:
    """
    Aggregate per-sentence FinBERT scores (S_i = P_pos - P_neg) weighted by speaker role.
    
    Args:
        sentences_with_roles: list of (sentence, role, score) tuples
        weights: dict mapping role -> weight
    
    Returns:
        Weighted aggregate sentiment score in [-1, +1]
    """
    if not sentences_with_roles:
        return 0.0
    
    weighted_sum = 0.0
    weight_total = 0.0
    
    for sentence, role, score in sentences_with_roles:
        w = weights.get(role, weights['other'])
        weighted_sum += score * w
        weight_total += w
    
    if weight_total == 0:
        return 0.0
    
    return weighted_sum / weight_total


def parse_transcript_speakers(transcript_text: str) -> list:
    """
    Parse earnings call transcript into (speaker, text) blocks.
    Handles common formats from EDGAR 8-K exhibits and SeekingAlpha HTML.
    
    Returns:
        List of (speaker_name, speaker_lines) tuples
    """
    segments = []
    current_speaker = 'unknown'
    current_lines = []
    
    # Common transcript speaker patterns:
    # 'John Smith - CFO: ...' or 'Analyst from Goldman Sachs: ...'
    speaker_pattern = re.compile(
        r'^([A-Z][a-zA-Z\s,\.\-]+(?:CEO|CFO|COO|CTO|President|VP|SVP|EVP|Analyst|Operator|[A-Z]{2,6})?)'  
        r'(?:\s*[-–:]|\s*\n)',  
        re.MULTILINE
    )
    
    lines = transcript_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = speaker_pattern.match(line)
        if m:
            if current_lines:
                segments.append((current_speaker, ' '.join(current_lines)))
            current_speaker = m.group(1).strip()
            remainder = line[m.end():].strip().lstrip(':').strip()
            current_lines = [remainder] if remainder else []
        else:
            current_lines.append(line)
    
    if current_lines:
        segments.append((current_speaker, ' '.join(current_lines)))
    
    return segments


def get_finbert_scores(sentences: list, finbert_pipe) -> list:
    """
    Run FinBERT on list of sentence strings.
    Returns list of (pos - neg) scores in [-1, +1].
    FinBERT chunks at 512 tokens — long sentences are split.
    """
    scores = []
    for sentence in sentences:
        # Split long sentences at 512 token boundary (approx 400 chars)
        chunks = [sentence[i:i+400] for i in range(0, len(sentence), 400)]
        chunk_scores = []
        for chunk in chunks:
            if len(chunk.strip()) < 10:
                continue
            result = finbert_pipe(chunk, truncation=True, max_length=512)
            r = result[0] if isinstance(result, list) else result
            # result is list of {label, score} dicts
            pos = next((x['score'] for x in r if x['label'] == 'positive'), 0)
            neg = next((x['score'] for x in r if x['label'] == 'negative'), 0)
            chunk_scores.append(pos - neg)
        if chunk_scores:
            scores.append(np.mean(chunk_scores))
        else:
            scores.append(0.0)
    return scores


class SpeakerWeightedPEAD:
    """
    R31b: Text PEAD with speaker-weighted FinBERT aggregation.
    Inherits R31 3-day confirmation window and RegimeGuard.
    """
    
    def __init__(self, tickers: list, start_date: str, end_date: str):
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.results = []
        
        # Load FinBERT
        print('Loading FinBERT...')
        self.finbert = pipeline(
            'text-classification',
            model='ProsusAI/finbert',
            return_all_scores=True,
            device=-1  # CPU
        )
        print('FinBERT loaded.')
    
    def compute_transcript_signal(self, transcript_text: str) -> dict:
        """
        Compute speaker-weighted sentiment from a single transcript.
        Returns dict with overall score + per-role breakdowns.
        """
        segments = parse_transcript_speakers(transcript_text)
        all_scored = []
        
        for speaker_name, text_block in segments:
            role = classify_speaker_role(speaker_name)
            # Sentence-level split (simple; more sophisticated would use NLTK sent_tokenize)
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text_block) if len(s.strip()) > 20]
            if not sentences:
                continue
            sent_scores = get_finbert_scores(sentences, self.finbert)
            for sent, score in zip(sentences, sent_scores):
                all_scored.append((sent, role, score))
        
        weighted_score = compute_speaker_weighted_sentiment(all_scored)
        
        # Per-role breakdown for diagnostics
        role_scores = {}
        for role in SPEAKER_WEIGHTS:
            role_sents = [(s, sc) for (s, r, sc) in all_scored if r == role]
            role_scores[role] = np.mean([sc for _, sc in role_sents]) if role_sents else 0.0
        
        return {
            'weighted_score': weighted_score,
            'role_scores': role_scores,
            'n_sentences': len(all_scored),
            'n_analyst_sentences': sum(1 for _, r, _ in all_scored if r == 'analyst'),
        }
    
    def run_backtest(self):
        """
        Full backtest loop. For each ticker, find earnings events,
        compute speaker-weighted text signal, apply 3-day confirmation,
        and trade with 20-day hold.
        
        NOTE: This requires actual transcript data. For R31b testing,
        use the same EPS surprise % proxy as R31 but with speaker weighting
        applied when transcripts are available.
        """
        # TODO: Implement transcript fetching from EDGAR API
        # For now, scaffold the backtest structure
        print('R31b Speaker-Weighted PEAD Backtest')
        print('=' * 60)
        print(f'Universe: {len(self.tickers)} tickers')
        print(f'Period: {self.start_date} to {self.end_date}')
        print(f'Speaker weights: {SPEAKER_WEIGHTS}')
        print()
        print('Implementation note: requires EDGAR 8-K transcript access.')
        print('Speaker-weighting formula from arXiv:2604.13260.')
        print('Expected IC improvement: 0.115 -> 0.142 (+24%)')
        print('Expected Sharpe improvement: 1.322 -> ~1.6-2.0')
        return self.results


if __name__ == '__main__':
    # S&P 500 large-cap subset (same as R31)
    TICKERS = [
        'AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'TSLA', 'BRK-B',
        'UNH', 'JNJ', 'JPM', 'V', 'XOM', 'PG', 'MA', 'HD', 'CVX', 'MRK',
        'ABBV', 'PEP', 'KO', 'AVGO', 'COST', 'MCD', 'TMO', 'ACN', 'CSCO',
        'DHR', 'ABT', 'TXN'
    ]
    
    backtest = SpeakerWeightedPEAD(
        tickers=TICKERS,
        start_date='2020-01-01',
        end_date='2025-12-31'
    )
    results = backtest.run_backtest()
    print(f'\nR31b scaffold complete. Requires EDGAR transcript integration to run fully.')
    print('Key formula: weighted_score = sum(S_i * w_role_i) / sum(w_role_i)')
    print('where S_i = P(positive) - P(negative) from FinBERT, w_role_i from SPEAKER_WEIGHTS')
