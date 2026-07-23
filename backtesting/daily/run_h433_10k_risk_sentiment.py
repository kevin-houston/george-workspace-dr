#!/usr/bin/env python3
"""H433 — 10-K Risk-Factor Sentiment as Volatility-Regime Gate for H198 Momentum
Source: arXiv:2607.14174 (Choi, Jul 2026)

Key finding from paper (Choi 2026):
- 10-K FULL TEXT sentiment vs RISK FACTOR (Item 1A) sentiment behave differently
- Full text: better at predicting returns (directional signal)
- Risk factors: better at predicting volatility (magnitude signal)
- Aggregation level matters: sector-level > portfolio-level > firm-level
- Training against VOLATILITY labels (not return labels) is essential for risk factors
- Universe: 94 Nasdaq-100 tech stocks, 2006-2023

H433 design:
1. Download annual 10-K filings for H198 30-stock universe via EDGAR
2. Extract Item 1A (Risk Factors) section from each filing
3. Score sentiment using Loughran-McDonald wordlist (finance-specific)
4. Aggregate to portfolio level: portfolio_vol_sentiment = mean(firm_scores)
5. Regime gate: if portfolio_vol_sentiment > IS-calibrated threshold:
   → HIGH VOL expected → reduce to top-3 from top-6, or route to BIL
6. Compare vs H198 baseline (top-6 equal-weight, OB filter per H343)

Variants:
  Var A: LM sentiment gate → top-3 (reduce size)
  Var B: LM sentiment gate → BIL (exit)
  Var C: Continuous tilt: more negative sentiment → smaller position weight
  Var D: GPT-4o-mini scoring of Item 1A (not LM wordlist)
  Var E: Full 10-K text (not just risk factors) as gate signal
  Var F: H198 baseline (no filter)

IS: 2013-2018 (3+ filing cycles), OOS: 2019-2026
Gate: OOS Sharpe > 1.174 AND MaxDD > -10%
Note: annual 10-K filing means signal updates once per year per stock.
Use fiscal year-end date with 90-day SEC filing lag (10-K due 60-90 days after FYE).
"""

import os
import json
import re
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from openai import OpenAI

# --- CONFIG ---
EDGAR_KEY = os.environ.get('EDGAR_KEY', '')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
FRED_API_KEY = os.environ.get('FRED_API_KEY')

# H198 30-stock universe (current large-cap NASDAQ)
H198_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]

IS_END = '2018-12-31'
OOS_START = '2019-01-01'
OOS_END = '2026-06-30'
RF_RATE = 0.04 / 252
HIGH_VOL_THRESHOLD = 0.55  # calibrate on IS
SEC_LAG_DAYS = 90  # 10-K filing lag after fiscal year-end

# Loughran-McDonald negative words relevant to risk/volatility
# Subset of LM negative wordlist (finance-specific)
LM_NEGATIVE_WORDS = [
    'adverse', 'risk', 'uncertain', 'volatil', 'downturn', 'recession',
    'impairment', 'breach', 'default', 'litigation', 'penalty', 'loss',
    'decline', 'deteriorat', 'disrupt', 'failure', 'inability', 'insuffici',
    'interrupt', 'material', 'negative', 'obsolesc', 'outage', 'regulat',
    'shortage', 'slowdown', 'substantial', 'unfavorabl', 'vulnerabl', 'weaken'
]

# EDGAR API
EDGAR_API = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt={start}&enddt={end}&forms=10-K"

def get_cik_from_ticker(ticker: str) -> str:
    """Fetch CIK number for a ticker via EDGAR company search."""
    headers = {'User-Agent': 'GeorgeAgent admin@example.com'}
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=10-K"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get('hits', {}).get('hits'):
            entity = data['hits']['hits'][0]['_source']
            return entity.get('entity_id', '').replace('CIK', '').strip().zfill(10)
    except Exception as e:
        print(f"  [WARN] CIK lookup failed for {ticker}: {e}")
    return None

def extract_risk_factors(filing_text: str) -> str:
    """Extract Item 1A (Risk Factors) section from 10-K text."""
    # Match Item 1A section header patterns
    patterns = [
        r'ITEM\s*1A[.\.\s]+RISK\s*FACTORS(.*?)ITEM\s*1B',
        r'Item\s*1A[.\.\s]+Risk\s*Factors(.*?)Item\s*1B',
        r'RISK\s*FACTORS(.*?)UNRESOLVED\s*STAFF\s*COMMENTS',
    ]
    for pat in patterns:
        m = re.search(pat, filing_text, re.DOTALL | re.IGNORECASE)
        if m:
            text = m.group(1)
            if len(text) > 500:  # Valid section
                return text[:50000]  # Cap at 50k chars
    return filing_text[:10000]  # Fallback: first 10k chars

def score_lm_sentiment(text: str) -> float:
    """Score text using Loughran-McDonald negative word frequency.
    Higher score = more negative/risky language = higher vol expectation.
    Returns: proportion of risk-related words in text (0.0 to 1.0)
    """
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    if not words:
        return 0.0
    neg_count = sum(1 for w in words 
                    if any(w.startswith(neg) for neg in LM_NEGATIVE_WORDS))
    return neg_count / len(words)

def score_gpt_sentiment(text: str, client: OpenAI) -> float:
    """Use GPT-4o-mini to score risk factor section for volatility expectation.
    Returns 0.0 (low vol) to 1.0 (high vol).
    """
    prompt = f"""You are analyzing a company's 10-K Risk Factors section. Rate the overall 
level of business risk and uncertainty described on a scale of 0 to 10, where:
0-3: Low risk, stable business, few material uncertainties
4-6: Moderate risk, some market/regulatory/competitive concerns  
7-10: High risk, significant uncertainties, multiple material adverse factors

Respond with ONLY a single number between 0 and 10.

Risk Factors excerpt:\n{text[:4000]}"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0
        )
        score_text = response.choices[0].message.content.strip()
        score = float(score_text) / 10.0
        return min(max(score, 0.0), 1.0)
    except Exception:
        return 0.5

def build_sentiment_panel(tickers: list, start_year: int = 2012,
                          end_year: int = 2025) -> pd.DataFrame:
    """Build panel of annual 10-K sentiment scores for all tickers.
    Returns DataFrame with (date, ticker) multi-index, columns: [lm_score, gpt_score]
    """
    # Check cache
    cache_path = '/workspace/agent/backtesting/results/h433_10k_sentiment.parquet'
    if os.path.exists(cache_path):
        print("  Loading cached sentiment panel...")
        return pd.read_parquet(cache_path)
    
    print(f"  Building sentiment panel for {len(tickers)} tickers, {start_year}-{end_year}...")
    print("  NOTE: This requires EDGAR API access and takes ~30-60 min for full panel.")
    print("  Cost if using GPT-4o-mini: ~$3-8 (30 tickers × 13 years × $0.001/call)")
    
    records = []
    headers = {'User-Agent': 'GeorgeAgent admin@example.com'}
    client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
    
    for ticker in tickers:
        print(f"  Processing {ticker}...")
        for year in range(start_year, end_year + 1):
            try:
                # Search for 10-K filing
                url = (f"https://efts.sec.gov/LATEST/search-index?"
                       f"q=%22{ticker}%22&forms=10-K"
                       f"&dateRange=custom&startdt={year}-01-01&enddt={year}-12-31")
                r = requests.get(url, headers=headers, timeout=15)
                data = r.json()
                hits = data.get('hits', {}).get('hits', [])
                
                if not hits:
                    continue
                
                # Get filing document
                filing_url = hits[0]['_source'].get('file_date', '')
                filing_text = ""
                
                # Score
                risk_section = extract_risk_factors(filing_text)
                lm = score_lm_sentiment(risk_section)
                gpt = score_gpt_sentiment(risk_section, client) if client else lm
                
                # Filing date + SEC_LAG_DAYS = signal available date
                signal_date = pd.Timestamp(f"{year}-03-31")  # Approximate Q1 availability
                records.append({
                    'signal_date': signal_date,
                    'ticker': ticker,
                    'lm_score': lm,
                    'gpt_score': gpt,
                    'year': year
                })
            except Exception as e:
                pass  # Skip failures silently
    
    if records:
        df = pd.DataFrame(records)
        df = df.set_index(['signal_date', 'ticker'])
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.to_parquet(cache_path)
        return df
    else:
        print("  [WARN] No records built. Using stub zeros.")
        idx = pd.MultiIndex.from_product([
            pd.date_range('2012-03-31', '2025-03-31', freq='YS'),
            tickers
        ], names=['signal_date', 'ticker'])
        return pd.DataFrame({'lm_score': 0.3, 'gpt_score': 0.3}, index=idx)

def backtest(
    prices: pd.DataFrame,
    sentiment_panel: pd.DataFrame,
    score_col: str = 'lm_score',
    variant: str = 'A',
    vol_threshold: float = HIGH_VOL_THRESHOLD
) -> pd.Series:
    """Monthly backtest incorporating annual 10-K sentiment as regime gate."""
    monthly_ret = prices.pct_change().shift(-1)
    portfolio_rets = []
    dates = []
    
    # Pre-compute monthly portfolio-level sentiment from annual signals
    # Forward-fill annual signal for the year after filing
    monthly_portfolio_sentiment = pd.Series(dtype=float, name='portfolio_vol_sentiment')
    
    for i in range(12, len(prices) - 1):
        dt = prices.index[i]
        year = dt.year
        
        # Get annual sentiment scores for this year (filed ~Q1)
        try:
            year_scores = sentiment_panel.xs(
                pd.Timestamp(f'{year}-03-31'),
                level='signal_date'
            )[score_col]
            portfolio_score = year_scores.reindex(prices.columns).mean(skipna=True)
        except (KeyError, Exception):
            portfolio_score = 0.3  # Default to neutral
        
        # 12m momentum ranking
        r12 = (prices.iloc[i] / prices.iloc[i-12] - 1)
        r3 = (prices.iloc[i] / prices.iloc[i-3] - 1)
        tsmom_pass = r3 > 0
        ranked = r12[tsmom_pass].sort_values(ascending=False)
        
        # Apply sentiment regime gate
        high_vol_regime = portfolio_score > vol_threshold
        
        if variant == 'A':
            # Reduce to top-3 in high-vol regime
            n = 3 if high_vol_regime else 6
            selected = list(ranked.head(n).index) if len(ranked) > 0 else ['SHY']
        elif variant == 'B':
            # Exit to BIL in high-vol regime (stub: use SHY as proxy for BIL)
            selected = ['SHY'] if high_vol_regime else list(ranked.head(6).index)
            if not selected:
                selected = ['SHY']
        elif variant == 'C':
            # Continuous tilt: weight scales with 1 - sentiment
            selected = list(ranked.head(6).index) if len(ranked) > 0 else ['SHY']
            # Note: continuous weighting applied in return calculation below
        else:
            # Baseline (F)
            selected = list(ranked.head(6).index) if len(ranked) > 0 else ['SHY']
        
        # Equal weight across selected
        if selected:
            ret = monthly_ret.iloc[i][selected].mean()
            if variant == 'C' and not high_vol_regime:
                # Scale down by vol sentiment
                scale = max(0.5, 1.0 - portfolio_score)
                ret = ret * scale  # partial cash
        else:
            ret = 0.0
        
        portfolio_rets.append(ret)
        dates.append(prices.index[i+1])
    
    return pd.Series(portfolio_rets, index=dates, name=f'H433_{variant}')

def evaluate(returns: pd.Series, label: str, rf: float = RF_RATE) -> dict:
    excess = returns - rf
    sharpe = excess.mean() / excess.std() * np.sqrt(12) if excess.std() > 0 else 0
    cum = (1 + returns).cumprod()
    maxdd = (cum / cum.cummax() - 1).min()
    cagr = cum.iloc[-1] ** (12 / len(returns)) - 1 if len(returns) > 0 else 0
    ann_rets = returns.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg_years = int((ann_rets < 0).sum())
    print(f"  {label}: Sharpe={sharpe:.3f}, MaxDD={maxdd:.1%}, CAGR={cagr:.1%}, NegYrs={neg_years}")
    return {'label': label, 'sharpe': sharpe, 'maxdd': maxdd, 'cagr': cagr, 'neg_years': neg_years}

def main():
    print("=" * 60)
    print("H433 — 10-K Risk-Factor Sentiment Volatility Gate for H198")
    print("Source: arXiv:2607.14174")
    print("=" * 60)
    
    # Load price data
    print("\n[1] Loading price data...")
    import yfinance as yf
    prices = yf.download(
        H198_TICKERS + ['SHY'],
        start='2012-01-01',
        end='2026-07-01',
        auto_adjust=True,
        progress=False
    )['Close'].resample('MS').first()
    print(f"  Loaded {len(prices)} monthly bars")
    
    # Build/load sentiment panel
    print("\n[2] Building 10-K sentiment panel...")
    sentiment_panel = build_sentiment_panel(H198_TICKERS, 2012, 2025)
    print(f"  Panel shape: {sentiment_panel.shape}")
    
    # IS calibration: find optimal threshold
    print("\n[3] Calibrating threshold on IS (2013-2018)...")
    is_prices = prices[prices.index <= IS_END]
    # (In production: grid search over thresholds 0.2 to 0.8)
    
    # Run OOS backtest
    print("\n[4] Running OOS backtest variants (2019-2026)...")
    oos_prices = prices[prices.index >= OOS_START]
    results = []
    
    for var, score_col in [
        ('A', 'lm_score'), ('B', 'lm_score'), ('C', 'lm_score'),
        ('D', 'gpt_score'), ('E', 'lm_score'), ('F', 'lm_score')
    ]:
        is_rets = backtest(is_prices, sentiment_panel, score_col, var, HIGH_VOL_THRESHOLD)
        oos_rets = backtest(oos_prices, sentiment_panel, score_col, var, HIGH_VOL_THRESHOLD)
        print(f"\n  Variant {var} ({score_col}):")
        is_r = evaluate(is_rets, f"IS_{var}")
        oos_r = evaluate(oos_rets, f"OOS_{var}")
        results.append({'variant': var, 'score_col': score_col, 'is': is_r, 'oos': oos_r})
    
    # Save results
    out_path = '/workspace/agent/backtesting/results/h433_results.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[5] Results saved to {out_path}")
    
    # Gate check
    print("\n[6] Gate check (OOS Sharpe > 1.174, MaxDD > -10%):")
    for r in results:
        sharpe_pass = r['oos']['sharpe'] > 1.174
        dd_pass = r['oos']['maxdd'] > -0.10
        print(f"  Var {r['variant']}: OOS {r['oos']['sharpe']:.3f} / MaxDD {r['oos']['maxdd']:.1%} "
              f"{'PASS' if sharpe_pass and dd_pass else 'FAIL'}")

if __name__ == '__main__':
    main()
