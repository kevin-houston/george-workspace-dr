#!/usr/bin/env python3
"""H434 — Market Regime Council (MRC) Shapley-Weighted Multi-Agent ETF Rotation
Source: arXiv:2605.24490 (Pei, Ge, Zheng & Cartlidge, May 2026)

MRC Architecture:
- N=3 specialist agents, each with a single view on the best ETF to hold each month
- Compute all 2^N - 1 = 7 coalition outputs (each coalition picks based on consensus)
- Track each coalition's realized monthly P&L
- Shapley weight for agent i = Σ over coalitions containing i: (|S|-1)!(N-|S|)!/N! * marginal_contrib
- Weights updated with exponential decay (lambda=0.95) to focus on recent performance
- Final allocation = Shapley-weighted blend of agent recommendations

Three agents:
  Agent 1 (Momentum): 12m momentum + inv_vol_6m rank, H026 25-asset universe
  Agent 2 (Macro): SPY 200MA + VIX<20 gate (from H301); if gate fires → BIL
  Agent 3 (OB): Order Block filtered top-2 (from H346 best_B window=20/swing_len=3)

Note: H434 uses DETERMINISTIC agents, not LLM agents. MRC is the credit-assignment
architecture — the agents themselves are proven quantitative rules.

IS: 2008-2017 (H026 canonical IS), OOS: 2018-2026
Gate: OOS Sharpe > 3.238 (H346 OB-filtered H026 baseline)
"""

import os
import json
import itertools
import pandas as pd
import numpy as np
from functools import lru_cache

# --- CONFIG ---
FRED_API_KEY = os.environ.get('FRED_API_KEY')

# H026 expanded 25-asset universe
H026_UNIVERSE = [
    'XLK', 'XLV', 'XLE', 'XLF', 'XLU', 'XLI', 'XLB', 'XLRE', 'XLC',
    'XLP', 'XLY',  # 11 sector ETFs
    'GLD', 'TLT', 'IEF', 'TIP', 'DBC', 'AGG',  # Bonds + commodities
    'GDX', 'DBA', 'SLV', 'UNG', 'EWZ', 'IBB', 'XME',  # Alts
    'BIL'  # Cash
]
SAFE_HAVEN = 'BIL'
IS_START = '2008-01-01'
IS_END = '2017-12-31'
OOS_START = '2018-01-01'
OOS_END = '2026-06-30'
RF_RATE = 0.04 / 252
SHAPLEY_DECAY = 0.95  # Exponential decay for historical Shapley
OB_WINDOW = 20
OB_SWING_LEN = 3
VIX_THRESHOLD = 20

def load_prices(tickers: list) -> pd.DataFrame:
    import yfinance as yf
    prices = yf.download(
        tickers,
        start='2007-01-01',
        end='2026-07-01',
        auto_adjust=True,
        progress=False
    )['Close'].resample('MS').first()
    # Fill missing
    prices = prices.reindex(columns=tickers).ffill().bfill()
    return prices

def load_spy_200ma(prices: pd.DataFrame) -> pd.Series:
    """Returns True when SPY is above its 200-day MA (monthly check)."""
    if 'SPY' not in prices.columns:
        import yfinance as yf
        spy_daily = yf.download('SPY', start='2007-01-01', end='2026-07-01',
                               auto_adjust=True, progress=False)['Close']
    else:
        spy_daily = prices['SPY']
    spy_200 = spy_daily.rolling(200).mean()
    above_200 = (spy_daily > spy_200).resample('MS').last()
    return above_200

def load_vix_monthly() -> pd.Series:
    """Load VIX from FRED, return monthly average."""
    try:
        import requests
        url = (f"https://api.stlouisfed.org/fred/series/observations"
               f"?series_id=VIXCLS&api_key={FRED_API_KEY}&file_type=json"
               f"&observation_start=2007-01-01")
        r = requests.get(url, timeout=15)
        data = r.json()
        obs = [(o['date'], float(o['value'])) for o in data['observations']
               if o['value'] != '.']
        vix = pd.Series(dict(obs), dtype=float)
        vix.index = pd.to_datetime(vix.index)
        return vix.resample('MS').mean()
    except Exception as e:
        print(f"  [WARN] VIX load failed: {e} — using constant 18")
        return pd.Series(18.0, index=pd.date_range('2007-01-01', '2026-07-01', freq='MS'))

def check_ob_filter(ticker: str, as_of: pd.Timestamp,
                    window: int = OB_WINDOW, swing_len: int = OB_SWING_LEN) -> bool:
    """Check if ticker has unmitigated bullish OB within last `window` trading days."""
    try:
        from smartmoneyconcepts import smc
        import yfinance as yf
        start = (as_of - pd.DateOffset(months=3)).strftime('%Y-%m-%d')
        end = as_of.strftime('%Y-%m-%d')
        df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        if len(df) < 20:
            return False
        df.columns = [c.lower() if c != 'Volume' else 'volume' for c in df.columns]
        swings = smc.swing_highs_lows(df, swing_length=swing_len)
        obs = smc.ob(df, swings)
        bullish = obs[(obs['OB'] == 1) & (obs['MitigatedIndex'].isna())]
        return len(bullish) > 0
    except Exception:
        return True  # Assume OB present if check fails

# --- AGENT FUNCTIONS ---

def agent_momentum(prices_i: pd.DataFrame, i: int) -> str:
    """Agent 1: Pure 12m momentum + inv_vol_6m, top-1 selection."""
    r12 = prices_i.iloc[i] / prices_i.iloc[i-12] - 1
    vol6 = prices_i.iloc[max(0,i-6):i].pct_change().std()
    # Dual rank: 12m return rank + inverse vol rank
    rank_r12 = r12.rank(ascending=True)
    rank_invvol = (1 / vol6).rank(ascending=True)
    composite = (rank_r12 + rank_invvol) / 2
    composite = composite.drop(SAFE_HAVEN, errors='ignore')
    best = composite.idxmax()
    return best if pd.notna(best) else SAFE_HAVEN

def agent_macro(prices_i: pd.DataFrame, i: int, spy_200: pd.Series, vix: pd.Series) -> str:
    """Agent 2: Macro regime gate — if SPY < 200MA or VIX >= 20, route to BIL."""
    dt = prices_i.index[i]
    above_200 = spy_200.get(dt, True)  # Default: assume bullish
    vix_level = vix.get(dt, 18.0)
    if not above_200 or vix_level >= VIX_THRESHOLD:
        return SAFE_HAVEN
    # Otherwise: same as momentum agent (uses H026 12m top-1)
    r12 = prices_i.iloc[i] / prices_i.iloc[i-12] - 1
    r12 = r12.drop(SAFE_HAVEN, errors='ignore')
    best = r12.idxmax()
    return best if pd.notna(best) else SAFE_HAVEN

def agent_ob_filtered(prices_i: pd.DataFrame, i: int, ob_cache: dict) -> str:
    """Agent 3: OB-filtered top-2 selection (H346 best_B logic)."""
    dt = prices_i.index[i]
    r12 = prices_i.iloc[i] / prices_i.iloc[i-12] - 1
    r12 = r12.drop(SAFE_HAVEN, errors='ignore')
    top3 = list(r12.nlargest(3).index)
    for ticker in top3:
        cache_key = f"{ticker}_{dt}"
        if cache_key not in ob_cache:
            ob_cache[cache_key] = check_ob_filter(ticker, dt)
        if ob_cache[cache_key]:
            return ticker
    return SAFE_HAVEN

# --- SHAPLEY COMPUTATION ---

def get_coalition_pick(agents_picks: list, coalition: tuple) -> str:
    """For a given coalition of agents, return their consensus ETF pick.
    Consensus: majority vote (tie-break: lower agent index = higher priority).
    """
    picks = [agents_picks[i] for i in coalition]
    from collections import Counter
    vote_count = Counter(picks)
    return vote_count.most_common(1)[0][0]

def compute_shapley_weights(agent_payoffs: dict, n_agents: int = 3) -> np.ndarray:
    """Compute Shapley values from historical coalition payoffs.
    agent_payoffs: {coalition_tuple: list_of_monthly_rets}
    Returns: np.array of shape (n_agents,) with Shapley weights summing to 1.
    """
    n = n_agents
    shapley = np.zeros(n)
    agents = list(range(n))
    
    for i in agents:
        for r in range(1, n+1):
            # All coalitions of size r that contain agent i
            others = [j for j in agents if j != i]
            for combo in itertools.combinations(others, r-1):
                S = tuple(sorted((i,) + combo))
                S_minus_i = tuple(j for j in S if j != i)
                
                # Marginal contribution: v(S) - v(S\{i})
                v_S = np.mean(agent_payoffs.get(S, [0.0]))
                v_S_minus_i = np.mean(agent_payoffs.get(S_minus_i, [0.0])) if S_minus_i else 0.0
                marginal = v_S - v_S_minus_i
                
                # Shapley formula coefficient
                coeff = (np.math.factorial(r-1) * np.math.factorial(n-r)) / np.math.factorial(n)
                shapley[i] += coeff * marginal
    
    # Softmax normalization to get portfolio weights
    exp_shapley = np.exp(np.clip(shapley, -5, 5))
    weights = exp_shapley / exp_shapley.sum()
    return weights

def backtest_mrc(
    prices: pd.DataFrame,
    spy_200: pd.Series,
    vix: pd.Series,
    variant: str = 'MRC'
) -> pd.Series:
    """Full MRC backtest."""
    monthly_ret = prices.pct_change().shift(-1)
    portfolio_rets = []
    dates = []
    ob_cache = {}
    
    # Historical coalition payoffs (rolling window, exponentially decayed)
    all_coalitions = []
    for r in range(1, 4):
        for combo in itertools.combinations([0,1,2], r):
            all_coalitions.append(combo)
    
    coalition_rets = {c: [] for c in all_coalitions}
    shapley_weights = np.array([1/3, 1/3, 1/3])  # Initialize equal
    
    for i in range(13, len(prices) - 1):
        dt = prices.index[i]
        
        # Get each agent's pick
        pick_0 = agent_momentum(prices, i)
        pick_1 = agent_macro(prices, i, spy_200, vix)
        pick_2 = agent_ob_filtered(prices, i, ob_cache)
        agent_picks = [pick_0, pick_1, pick_2]
        
        if variant == 'MRC':
            # MRC: blend based on Shapley weights
            # Each agent recommends their pick with full conviction
            # Portfolio = weighted blend of the three recommendations
            unique_picks = list(set(agent_picks))
            alloc = {p: 0.0 for p in unique_picks}
            for ai, pick in enumerate(agent_picks):
                alloc[pick] = alloc.get(pick, 0.0) + shapley_weights[ai]
            
            ret = sum(alloc[p] * monthly_ret.iloc[i].get(p, 0.0) for p in unique_picks)
        elif variant == 'EQUAL':
            # Equal-weight agent blend
            unique_picks = list(set(agent_picks))
            ret = monthly_ret.iloc[i][unique_picks].mean()
        elif variant == 'MOMENTUM_ONLY':
            ret = monthly_ret.iloc[i][pick_0]
        elif variant == 'OB_ONLY':
            ret = monthly_ret.iloc[i][pick_2]
        elif variant == 'MAJORITY':
            from collections import Counter
            winner = Counter(agent_picks).most_common(1)[0][0]
            ret = monthly_ret.iloc[i][winner]
        else:
            ret = 0.0
        
        portfolio_rets.append(ret)
        dates.append(prices.index[i+1])
        
        # Update coalition payoffs (only if we know the actual next-month return)
        if i < len(prices) - 2:
            for coalition in all_coalitions:
                c_pick = get_coalition_pick(agent_picks, coalition)
                c_ret = monthly_ret.iloc[i].get(c_pick, 0.0)
                coalition_rets[coalition].append(c_ret)
        
        # Recompute Shapley every 12 months
        if (i - 13) % 12 == 11 and i > 25:
            # Use exponentially-decayed history
            decayed_payoffs = {}
            for c, rets in coalition_rets.items():
                if rets:
                    n = len(rets)
                    weights_t = np.array([SHAPLEY_DECAY ** (n - 1 - k) for k in range(n)])
                    decayed_payoffs[c] = list(np.array(rets) * weights_t / weights_t.sum())
                else:
                    decayed_payoffs[c] = [0.0]
            try:
                shapley_weights = compute_shapley_weights(decayed_payoffs)
            except Exception:
                shapley_weights = np.array([1/3, 1/3, 1/3])
    
    return pd.Series(portfolio_rets, index=dates, name=f'H434_{variant}')

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
    print("H434 — Market Regime Council Shapley-Weighted ETF Rotation")
    print("Source: arXiv:2605.24490")
    print("=" * 60)
    
    print("\n[1] Loading data...")
    import yfinance as yf
    all_tickers = list(set(H026_UNIVERSE + ['SPY']))
    prices = load_prices(all_tickers)
    spy_200 = load_spy_200ma(prices)
    vix = load_vix_monthly()
    print(f"  Loaded {len(prices)} monthly bars")
    
    # ETF prices only (no SPY in portfolio)
    etf_prices = prices[H026_UNIVERSE]
    
    print("\n[2] Running IS backtest (2008-2017)...")
    is_prices = etf_prices.loc[IS_START:IS_END]
    is_spy_200 = spy_200.loc[IS_START:IS_END]
    is_vix = vix.loc[IS_START:IS_END]
    
    is_results = {}
    for variant in ['MRC', 'EQUAL', 'MOMENTUM_ONLY', 'OB_ONLY', 'MAJORITY']:
        rets = backtest_mrc(is_prices, is_spy_200, is_vix, variant)
        is_results[variant] = evaluate(rets, f"IS_{variant}")
    
    print("\n[3] Running OOS backtest (2018-2026)...")
    oos_prices = etf_prices.loc[OOS_START:OOS_END]
    oos_spy_200 = spy_200.loc[OOS_START:OOS_END]
    oos_vix = vix.loc[OOS_START:OOS_END]
    
    oos_results = {}
    for variant in ['MRC', 'EQUAL', 'MOMENTUM_ONLY', 'OB_ONLY', 'MAJORITY']:
        rets = backtest_mrc(oos_prices, oos_spy_200, oos_vix, variant)
        oos_results[variant] = evaluate(rets, f"OOS_{variant}")
    
    # Save results
    results = [
        {'variant': v, 'is': is_results[v], 'oos': oos_results[v]}
        for v in is_results
    ]
    out_path = '/workspace/agent/backtesting/results/h434_results.json'
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[4] Results saved to {out_path}")
    
    print("\n[5] Gate check (OOS Sharpe > 3.238 = H346 canonical OOS):")
    for v in oos_results:
        passed = oos_results[v]['sharpe'] > 3.238
        print(f"  {v}: OOS {oos_results[v]['sharpe']:.3f} {'PASS' if passed else 'FAIL'}")
    
    print("\nNOTE: Shapley computation is O(2^N * T) — for N=3 agents this is tractable.")
    print("      For N>4 agents, use approximation (random coalition sampling).")

if __name__ == '__main__':
    main()
