#!/usr/bin/env python3
"""
H239: LLM Frozen-Snapshot Sector-Neutral Score as Monthly Alpha Factor

Source: arXiv:2604.21433 (Apr 2026) — 'ChatGPT as a Time Capsule'
  Frozen GPT snapshots encode fundamental information predictive of
  12-month revenue growth and analyst revisions (t-stat=6.02).
  Signal is DISTINCT from tone-based PEAD (H174/H225/H226).

Design:
  1. Each month, query GPT-4o for a fundamental outlook score per stock
  2. Sector-neutralize scores (subtract sector mean) to remove sector beta
  3. Hold top-6 stocks by sector-neutral score, monthly rebalance
  4. IS: 2021-2024 (matches paper's snapshot window), OOS: 2025-2026
  5. Blend test: LLM score + H217 alpha101 score (IC test between them)

Universe: 30 large-cap S&P 500 (same as H217)
Confirm gate: OOS Sharpe > 0.8 (supplementary factor threshold)
Secondary: IC(LLM_score, alpha101_rank) < 0.3 to confirm orthogonality
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import time
from openai import OpenAI

UNIVERSE = [
    'AAPL','MSFT','NVDA','AVGO','QCOM','AMD','IBM',
    'V','MA','BAC','WFC','JPM',
    'UNH','LLY','PFE','JNJ','ABBV',
    'AMZN','TSLA','HD','SBUX','LOW',
    'WMT','COST',
    'GOOGL','META',
    'CVX','XOM',
    'BA','CAT'
]

SECTORS = {
    'AAPL': 'IT', 'MSFT': 'IT', 'NVDA': 'IT', 'AVGO': 'IT',
    'QCOM': 'IT', 'AMD': 'IT', 'IBM': 'IT',
    'V': 'FIN', 'MA': 'FIN', 'BAC': 'FIN', 'WFC': 'FIN', 'JPM': 'FIN',
    'UNH': 'HC', 'LLY': 'HC', 'PFE': 'HC', 'JNJ': 'HC', 'ABBV': 'HC',
    'AMZN': 'CD', 'TSLA': 'CD', 'HD': 'CD', 'SBUX': 'CD', 'LOW': 'CD',
    'WMT': 'CS', 'COST': 'CS',
    'GOOGL': 'COMM', 'META': 'COMM',
    'CVX': 'ENE', 'XOM': 'ENE',
    'BA': 'IND', 'CAT': 'IND'
}

SCORING_PROMPT = """
You are a fundamental equity analyst providing a forward-looking assessment.
Score the following stock on its fundamental outlook for the NEXT 12 MONTHS.

Company: {company_name} (ticker: {ticker})
Sector: {sector}

Score the stock from -3 to +3 on each dimension:
  revenue_growth_outlook: expected revenue growth relative to sector peers
  earnings_quality: sustainability and quality of earnings
  competitive_position: business moat and market share trajectory
  management_execution: operational track record and guidance credibility

Return ONLY valid JSON:
{{"revenue_growth_outlook": <int -3 to 3>,
  "earnings_quality": <int -3 to 3>,
  "competitive_position": <int -3 to 3>,
  "management_execution": <int -3 to 3>,
  "composite_score": <float, weighted average>
}}"""

TICKER_NAMES = {
    'AAPL': 'Apple Inc', 'MSFT': 'Microsoft Corp', 'NVDA': 'NVIDIA Corp',
    'AVGO': 'Broadcom Inc', 'QCOM': 'Qualcomm Inc', 'AMD': 'Advanced Micro Devices',
    'IBM': 'IBM Corp', 'V': 'Visa Inc', 'MA': 'Mastercard Inc',
    'BAC': 'Bank of America', 'WFC': 'Wells Fargo', 'JPM': 'JPMorgan Chase',
    'UNH': 'UnitedHealth Group', 'LLY': 'Eli Lilly', 'PFE': 'Pfizer Inc',
    'JNJ': 'Johnson & Johnson', 'ABBV': 'AbbVie Inc', 'AMZN': 'Amazon.com Inc',
    'TSLA': 'Tesla Inc', 'HD': 'Home Depot', 'SBUX': 'Starbucks Corp',
    'LOW': 'Lowes Companies', 'WMT': 'Walmart Inc', 'COST': 'Costco Wholesale',
    'GOOGL': 'Alphabet Inc', 'META': 'Meta Platforms', 'CVX': 'Chevron Corp',
    'XOM': 'ExxonMobil Corp', 'BA': 'Boeing Co', 'CAT': 'Caterpillar Inc'
}


def get_llm_scores(client, date_label):
    """
    Query GPT-4o for fundamental outlook scores for all 30 stocks.
    Caches results to avoid re-querying (expensive: ~30 calls per month).
    Returns dict: {ticker: composite_score}
    """
    cache_file = f'backtesting/results/h239_llm_cache_{date_label}.json'
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    scores = {}
    for ticker in UNIVERSE:
        prompt = SCORING_PROMPT.format(
            company_name=TICKER_NAMES.get(ticker, ticker),
            ticker=ticker,
            sector=SECTORS.get(ticker, 'Unknown')
        )
        try:
            response = client.chat.completions.create(
                model='gpt-4o',  # Full GPT-4o for better fundamental knowledge
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=150,
            )
            result = json.loads(response.choices[0].message.content)
            scores[ticker] = result.get('composite_score',
                np.mean([result.get('revenue_growth_outlook', 0),
                         result.get('earnings_quality', 0),
                         result.get('competitive_position', 0),
                         result.get('management_execution', 0)]))
        except Exception as e:
            print(f'Error scoring {ticker}: {e}')
            scores[ticker] = 0.0
        time.sleep(0.2)  # Rate limit: 150 RPM on gpt-4o

    # Cache the scores
    os.makedirs('backtesting/results', exist_ok=True)
    with open(cache_file, 'w') as f:
        json.dump(scores, f)

    return scores


def sector_neutralize(scores):
    """
    Subtract sector mean from each stock's score.
    Returns sector-neutral scores.
    """
    sector_means = {}
    for sector in set(SECTORS.values()):
        sector_tickers = [t for t in UNIVERSE if SECTORS.get(t) == sector and t in scores]
        if sector_tickers:
            sector_means[sector] = np.mean([scores[t] for t in sector_tickers])

    neutral = {}
    for ticker in scores:
        sector = SECTORS.get(ticker)
        sector_mean = sector_means.get(sector, 0)
        neutral[ticker] = scores[ticker] - sector_mean

    return neutral


def run_h239(start_is='2021-01-01', end_is='2024-12-31',
             start_oos='2025-01-01', end_oos='2026-05-31',
             n_long=6, llm_refresh_months=3):
    """
    H239: LLM Frozen Snapshot Factor.
    llm_refresh_months: how often to re-query LLM (default: quarterly to save API cost)
    """
    import os
    print('H239: LLM Frozen-Snapshot Sector-Neutral Factor')
    print(f'IS: {start_is} to {end_is}, OOS: {start_oos} to {end_oos}')
    print(f'LLM refresh: every {llm_refresh_months} months (~30 API calls per refresh)')

    client = OpenAI()

    # Download price data
    raw = yf.download(UNIVERSE, start='2020-01-01', end=end_oos, auto_adjust=True, progress=False)
    monthly_closes = raw['Close'].resample('ME').last()

    # Monthly rebalance loop
    portfolio_returns = []
    dates = []
    llm_score_cache = {}  # {YYYY-QN: {ticker: score}}
    current_scores = None

    for i in range(1, len(monthly_closes) - 1):
        rebalance_date = monthly_closes.index[i]
        if rebalance_date < pd.Timestamp(start_is):
            continue

        # Determine which LLM snapshot to use (quarterly refresh)
        quarter_label = f"{rebalance_date.year}-Q{(rebalance_date.month-1)//3 + 1}"
        if quarter_label not in llm_score_cache:
            print(f'  Querying LLM for {quarter_label}...')
            raw_scores = get_llm_scores(client, quarter_label)
            llm_score_cache[quarter_label] = sector_neutralize(raw_scores)
        current_scores = llm_score_cache[quarter_label]

        # Select top-N by sector-neutral LLM score
        valid = {t: s for t, s in current_scores.items() if t in monthly_closes.columns}
        selected = sorted(valid, key=valid.get, reverse=True)[:n_long]

        # Forward return
        fwd_ret = (monthly_closes.iloc[i+1][selected] / monthly_closes.iloc[i][selected] - 1)
        port_ret = fwd_ret.mean()
        portfolio_returns.append(port_ret)
        dates.append(rebalance_date)

    ret_series = pd.Series(portfolio_returns, index=pd.DatetimeIndex(dates))

    # Evaluate IS and OOS
    results = {}
    for period_name, start, end in [('IS', start_is, end_is), ('OOS', start_oos, end_oos)]:
        mask = (ret_series.index >= start) & (ret_series.index <= end)
        r = ret_series[mask]
        if len(r) < 2:
            continue
        ann_sharpe = r.mean() / r.std(ddof=1) * np.sqrt(12)
        cumul = (1 + r).prod()
        cagr = cumul ** (12 / len(r)) - 1
        max_dd = (r.cumsum() - r.cumsum().cummax()).min()
        results[period_name] = {
            'sharpe': round(ann_sharpe, 3),
            'cagr': round(cagr, 3),
            'maxdd': round(float(max_dd), 3),
            'n_months': len(r)
        }

    # SPY benchmark
    spy = yf.download('SPY', start=start_oos, end=end_oos, auto_adjust=True, progress=False)
    spy_m = spy['Close'].resample('ME').last().pct_change().dropna()
    spy_m = spy_m[spy_m.index >= start_oos]
    results['SPY_OOS_sharpe'] = round(float(spy_m.mean() / spy_m.std(ddof=1) * np.sqrt(12)), 3)

    out_path = 'backtesting/results/h239_llm_timecapsule.json'
    os.makedirs('backtesting/results', exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'Results: {json.dumps(results, indent=2)}')
    print(f'Confirm gate: OOS Sharpe > 0.8')
    print(f'H217 reference: OOS Sharpe 1.559')
    return results


if __name__ == '__main__':
    run_h239()
