'''
H247 — Speaker-Weighted FinBERT on Earnings Call Transcripts
============================================================
Source: arXiv:2604.13260 (Sidhu, Fan & Pishgar, April 2026)
  'Which Voices Move Markets? Speaker Identity and Cross-Section of Post-Earnings Returns'
  6.5M sentences from 16,428 S&P 500 earnings call transcripts.
  Speaker weights: CFO=30%, Analyst=49%, Executive=16%, Other=5%
  Monthly L/S alpha 2.03% (t=6.49), unexplained by FF5.

H174 baseline: OOS WR=81.8%, MeanRet=6.89%, n=22
  Signal: FinBERT score >= 0.18 AND EPS surprise >= 0.02
  Source: 8-K full text from EDGAR

H247 extends H174 by adding earnings call transcript scoring with speaker weights.
Data source: FMP earnings call transcripts API (via $FMP_API_KEY)
  Endpoint: https://financialmodelingprep.com/api/v3/earning_call_transcript/{ticker}?quarter={Q}&year={YYYY}

Speaker role inference from transcript structure:
  - Lines following Operator: or ending with ":" (name + title) -> identify role
  - Prepared remarks section -> executives (CEO/CFO/COO/President)
  - Q&A section:
    - First speaker per turn -> analyst (usually)
    - Company response -> executive
  - CFO: search for "CFO", "Chief Financial Officer", "Finance" in speaker label

Fusion:
  speaker_score = sum(weight_i * finbert_i for each sentence_i) / sum(weights)
  combined_score = 0.6 * 8k_score + 0.4 * speaker_score  (blend with H174 8-K signal)

Confirm: OOS WR > 81.8% OR OOS MeanRet > 6.89% on same universe as H174 (n >= 15 events)

NOTE: H168 previously failed on HuggingFace transcript dataset (coverage=26.5%).
FMP transcript API has much better coverage (most large-cap S&P 500 earnings calls).
Test coverage first before running full backtest.
'''

# TODO: Implement H247
# Step 1: For each event in H174 OOS universe (ticker + earnings date):
#   - Call FMP transcript API for that quarter's call
#   - Parse into sentence/speaker pairs
#   - Infer speaker role from label
#   - Score each sentence with FinBERT (ProsusAI/finbert, already cached in H174 pipeline)
# Step 2: Compute speaker-weighted FinBERT score per event
# Step 3: Blend with H174 8-K score (0.6/0.4 weights)
# Step 4: Apply same threshold: combined_score >= 0.18 AND surprise >= 0.02
# Step 5: Measure OOS WR and MeanRet vs H174 baseline

# Key dependency: FMP transcript API coverage check
import os, requests
def check_transcript_coverage(tickers, years=[2021,2022,2023,2024,2025]):
    api_key = os.environ.get('FMP_API_KEY', '')
    found = 0
    for ticker in tickers[:10]:  # sample check
        url = f'https://financialmodelingprep.com/api/v3/earning_call_transcript/{ticker}?year={years[0]}&quarter=1&apikey={api_key}'
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and r.json():
            found += 1
    print(f'Coverage sample: {found}/10 tickers have transcripts for {years[0]} Q1')

print('H247 scaffold — implementation needed (see design comments)')
print('Key dependency: FMP earnings call transcript API coverage')
print('Baseline to beat: H174 OOS WR=81.8%, MeanRet=6.89%, n=22')
print('Run check_transcript_coverage() first to validate data availability')
