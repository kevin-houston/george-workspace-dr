#!/usr/bin/env python3
"""
H238: BlindTrade — Anonymization-First 4-Agent LLM Portfolio Construction

Source: arXiv:2603.17692 (Mar 2026) — 'Can Blindfolded LLMs Still Trade?'
  Anonymize ticker symbols before LLM portfolio construction to eliminate
  memorization bias. Achieved Sharpe 1.40±0.22 on 2025 YTD (20 seeds).

Design:
  1. Extract alpha101 factor values for each of 30 stocks at each rebalance date
  2. Anonymize tickers (replace with Stock_01..Stock_30 in random order each month)
  3. Feed anonymized factor table to 4 GPT-4o-mini agents with different personas
  4. Each agent returns top-6 picks from the anonymized universe
  5. Re-map picks back to real tickers; select stocks that appear in most agent picks
  6. Compare OOS performance vs H217 baseline (alpha101 LightGBM, Sharpe 1.559)

Universe: 30 large-cap S&P 500 (same as H217)
IS: 2013-2020, OOS: 2021-2026
Confirm gate: OOS Sharpe > 1.40
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
from openai import OpenAI
from sklearn.preprocessing import RankWarning
import warnings
warnings.filterwarnings('ignore', category=RankWarning)

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

AGENT_PERSONAS = [
    {
        "name": "momentum_analyst",
        "instruction": "You are a quantitative momentum analyst. Focus on stocks with strong positive momentum signals and high volume trends. Avoid stocks with weak or negative momentum."
    },
    {
        "name": "value_analyst",
        "instruction": "You are a quantitative value analyst. Focus on stocks with attractive reversal signals (currently oversold relative to peers). Avoid stocks that have run up significantly."
    },
    {
        "name": "risk_analyst",
        "instruction": "You are a risk-focused quantitative analyst. Select stocks with strong signals AND low volatility relative to peers. Prefer diversified factor exposure over single-factor concentration."
    },
    {
        "name": "composite_analyst",
        "instruction": "You are a composite factor analyst. Select the 6 stocks with the best overall factor profile: balance momentum, quality (volume consistency), and value signals."
    }
]


def compute_alpha101_features(monthly_closes, daily_closes, date):
    """
    Compute simplified alpha101 features for each stock at a given rebalance date.
    Returns a dict of {ticker: {feature_name: value}}.
    Features: mom_1m, mom_6m, mom_12m, reversal_adj, vol_20d, volume_trend.
    """
    features = {}
    prev_month = date - pd.offsets.MonthEnd(1)
    prev_6m = date - pd.offsets.MonthEnd(6)
    prev_12m = date - pd.offsets.MonthEnd(12)

    m_now = monthly_closes[monthly_closes.index <= date].iloc[-1]
    m_1m = monthly_closes[monthly_closes.index <= prev_month].iloc[-1] if len(monthly_closes[monthly_closes.index <= prev_month]) else None
    m_6m = monthly_closes[monthly_closes.index <= prev_6m].iloc[-1] if len(monthly_closes[monthly_closes.index <= prev_6m]) else None
    m_12m = monthly_closes[monthly_closes.index <= prev_12m].iloc[-1] if len(monthly_closes[monthly_closes.index <= prev_12m]) else None

    for ticker in UNIVERSE:
        try:
            ret_1m = (m_now[ticker] / m_1m[ticker] - 1) if m_1m is not None else np.nan
            ret_6m = (m_now[ticker] / m_6m[ticker] - 1) if m_6m is not None else np.nan
            ret_12m = (m_now[ticker] / m_12m[ticker] - 1) if m_12m is not None else np.nan

            # 20-day volatility from daily data
            daily = daily_closes[ticker].dropna()
            recent = daily[daily.index <= date].tail(20)
            vol_20d = recent.pct_change().dropna().std() * np.sqrt(252) if len(recent) > 5 else np.nan

            features[ticker] = {
                'mom_1m': round(ret_1m, 4) if not np.isnan(ret_1m) else None,
                'mom_6m_skip1m': round(ret_6m - ret_1m, 4) if not np.isnan(ret_6m) else None,
                'mom_12m_skip1m': round(ret_12m - ret_1m, 4) if not np.isnan(ret_12m) else None,
                'vol_20d_ann': round(vol_20d, 4) if not np.isnan(vol_20d) else None,
            }
        except Exception:
            features[ticker] = None

    # Cross-sectional rank normalization (0=worst, 1=best)
    for feat in ['mom_1m', 'mom_6m_skip1m', 'mom_12m_skip1m']:
        vals = {t: features[t][feat] for t in features if features[t] and features[t].get(feat) is not None}
        ranked = pd.Series(vals).rank(pct=True)
        for t in ranked.index:
            features[t][f'{feat}_rank'] = round(ranked[t], 3)

    # Reversal: bottom decile of 1m momentum (mean-reversion setup)
    for t in features:
        if features[t] and features[t].get('mom_1m_rank') is not None:
            features[t]['reversal_signal'] = round(1 - features[t]['mom_1m_rank'], 3)  # invert: high = more oversold

    return features


def anonymize_features(features):
    """
    Replace real ticker names with Stock_NN labels in random order.
    Returns: (anonymized_dict, deanonymization_map).
    """
    tickers = [t for t in features if features[t] is not None]
    np.random.shuffle(tickers)
    anon_map = {f'Stock_{i+1:02d}': t for i, t in enumerate(tickers)}
    deanon_map = {v: k for k, v in anon_map.items()}
    anon_features = {anon_label: features[real_ticker] for anon_label, real_ticker in anon_map.items()}
    return anon_features, anon_map


def format_factor_table(anon_features):
    """
    Format anonymized features as a readable table for the LLM.
    """
    lines = ["Stock | mom_1m_rank | mom_6m_rank | mom_12m_rank | reversal_signal | vol_20d"]
    lines.append("-" * 85)
    for anon_label, f in sorted(anon_features.items()):
        if f is None:
            continue
        lines.append(
            f"{anon_label:10s} | {f.get('mom_1m_rank', 'N/A'):10} | "
            f"{f.get('mom_6m_skip1m_rank', 'N/A'):10} | "
            f"{f.get('mom_12m_skip1m_rank', 'N/A'):11} | "
            f"{f.get('reversal_signal', 'N/A'):15} | "
            f"{f.get('vol_20d_ann', 'N/A')}"
        )
    return "\n".join(lines)


def query_agent(client, persona, factor_table, n_picks=6):
    """
    Query a single LLM agent for its top stock picks from the anonymized universe.
    Returns list of top N anonymized stock labels.
    """
    prompt = f"""{persona['instruction']}

You are selecting from a universe of {len(factor_table.split(chr(10)))-2} anonymized stocks.
All values are normalized ranks (0=worst, 1=best in universe).
reversal_signal is the oversold rank (1=most oversold).
vol_20d is annualized 20-day realized volatility.

Factor data for this month:
{factor_table}

Select the {n_picks} best stocks for the next month. Reply ONLY with a JSON array of exactly
{n_picks} stock labels, e.g.: ["Stock_03", "Stock_11", "Stock_07", "Stock_19", "Stock_24", "Stock_28"]
Do not include any explanation."""

    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=100,
    )
    content = response.choices[0].message.content
    try:
        picks = json.loads(content)
        if isinstance(picks, list):
            return picks[:n_picks]
        # Some models return {"picks": [...]}
        for v in picks.values():
            if isinstance(v, list):
                return v[:n_picks]
    except Exception:
        pass
    return []


def run_h238(start_is='2013-01-01', end_is='2020-12-31',
             start_oos='2021-01-01', end_oos='2026-05-31',
             n_long=6, use_llm=True):
    """
    H238: BlindTrade anonymization-first LLM portfolio.
    If use_llm=False, run a simple majority-vote factor composite as a non-LLM baseline.
    """
    print('H238: BlindTrade Anonymization-First LLM Portfolio')

    # Download data
    dl_start = (pd.Timestamp(start_is) - pd.Timedelta(days=400)).strftime('%Y-%m-%d')
    print(f'Downloading daily data from {dl_start} to {end_oos}...')
    raw = yf.download(UNIVERSE, start=dl_start, end=end_oos, auto_adjust=True, progress=False)
    daily_closes = raw['Close'].dropna(how='all')
    monthly_closes = daily_closes.resample('ME').last()

    client = OpenAI() if use_llm else None

    portfolio_returns = []
    dates = []
    agent_agreement = []

    for i in range(1, len(monthly_closes) - 1):
        rebalance_date = monthly_closes.index[i]
        if rebalance_date < pd.Timestamp(start_is):
            continue

        # Compute alpha101 features
        features = compute_alpha101_features(monthly_closes, daily_closes, rebalance_date)

        if use_llm and client:
            # Anonymize and query agents
            anon_features, anon_map = anonymize_features(features)
            factor_table = format_factor_table(anon_features)

            all_picks_anon = []
            for persona in AGENT_PERSONAS:
                picks = query_agent(client, persona, factor_table, n_picks=n_long)
                all_picks_anon.extend(picks)

            # Vote counting: de-anonymize and pick most-voted stocks
            vote_counts = {}
            for anon_label in all_picks_anon:
                real_ticker = anon_map.get(anon_label)
                if real_ticker:
                    vote_counts[real_ticker] = vote_counts.get(real_ticker, 0) + 1

            selected = sorted(vote_counts, key=vote_counts.get, reverse=True)[:n_long]
            if len(selected) < n_long:
                # Fallback: fill with highest-momentum stocks
                fallback = sorted([t for t in features if features[t] and features[t].get('mom_12m_skip1m_rank')],
                                   key=lambda t: features[t]['mom_12m_skip1m_rank'], reverse=True)
                selected = (selected + fallback)[:n_long]

            # Agreement score: if all 4 agents agree on the same N stocks
            unique_picks = set(vote_counts.keys())
            top_6_agreement = sum(1 for t in selected if vote_counts.get(t, 0) >= 2) / n_long
            agent_agreement.append(top_6_agreement)
        else:
            # Non-LLM baseline: composite rank (momentum + reversal blend)
            scores = {}
            for t in features:
                if features[t] and features[t].get('mom_12m_skip1m_rank') and features[t].get('mom_6m_skip1m_rank'):
                    scores[t] = 0.6 * features[t]['mom_12m_skip1m_rank'] + 0.4 * features[t]['mom_6m_skip1m_rank']
            selected = sorted(scores, key=scores.get, reverse=True)[:n_long]

        # Forward return
        fwd_ret = (monthly_closes.iloc[i+1][selected] / monthly_closes.iloc[i][selected] - 1)
        port_ret = fwd_ret.mean()
        portfolio_returns.append(port_ret)
        dates.append(rebalance_date)

    ret_series = pd.Series(portfolio_returns, index=pd.DatetimeIndex(dates))

    # Performance evaluation
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

    if agent_agreement:
        results['avg_agent_agreement'] = round(np.mean(agent_agreement), 3)

    # SPY benchmark
    spy = yf.download('SPY', start=start_oos, end=end_oos, auto_adjust=True, progress=False)
    spy_m = spy['Close'].resample('ME').last().pct_change().dropna()
    spy_m = spy_m[spy_m.index >= start_oos]
    results['SPY_OOS_sharpe'] = round(float(spy_m.mean() / spy_m.std(ddof=1) * np.sqrt(12)), 3)

    out_path = 'backtesting/results/h238_blindtrade_llm.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f'Results: {json.dumps(results, indent=2)}')
    print(f'Saved to {out_path}')
    print(f'Confirm gate: OOS Sharpe > 1.40 (BlindTrade benchmark)')
    print(f'H217 reference OOS Sharpe: 1.559 (alpha101 LightGBM)')
    return results


if __name__ == '__main__':
    run_h238(use_llm=True)
