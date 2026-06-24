---
updated: 2026-06-24
focus: options strategy backtesting — methodology, libraries, data tiers, pitfalls
priority: high (H309 dispersion Phase 2, H266 iron condor, H329 skew-t options portfolio)
---

# Options Backtesting Methodology

Options backtesting is fundamentally harder than equity backtesting. This page covers the methodology differences, library ecosystem, practical data tiers, and common mistakes. Directly relevant to H309 (SPX dispersion), H266 (iron condor), and H329 (skew-t options portfolio).

**Related pages**: [Options Data Sources](../data-sources/options-data.md) | [Options Income Strategies](../algorithms/options-income-strategies.md) | [SPX Dispersion & Variance](../algorithms/spx-dispersion-variance.md) | [Transaction Cost Modeling](transaction-costs.md)

---

## Why Options Backtesting Is Different From Equity Backtesting

| Dimension | Equity | Options |
|-----------|--------|---------|
| Path dependency | None — only entry/exit prices matter | Critical — IV dynamics during hold period determine P&L |
| Instrument lifetime | Perpetual | Contract expires; requires roll management |
| P&L decomposition | Price change only | Δ + Γ/2·ΔS² + Θ·Δt + V·ΔIV (Greeks components) |
| Bid-ask spread | ~0.01–0.05% of price | 5–30% of premium — dominant cost for OTM options |
| Assignment risk | N/A | Short options: early assignment on deep ITM before dividends/expiry |
| Universe construction | Static constituents file | Dynamic: contracts added/expired daily; thousands of strikes |
| Slippage model | Square-root law | Separate models for bid-ask + market impact on options |

**Core problem**: equity backtesting can reconstruct full P&L from EOD prices. Options P&L requires knowing **IV at entry and exit**, not just underlying price. A long straddle can lose money even if the underlying moved — if IV collapsed more than price moved.

---

## Data Tiers

Choose tier based on strategy and budget:

### Tier 0 — Free (Synthetic Chains via BSM + VIX Proxy)

**Use when**: Exploring strategy logic before committing to paid data. Good for iron condors, strangles, simple CSPs.

**Method**: Use VIX ÷ √252 as daily ATM IV proxy, then construct a synthetic options surface using Black-Scholes:

```python
from scipy.stats import norm
import numpy as np

def bsm_price(S, K, T, r, sigma, option_type='call'):
    """Black-Scholes-Merton option price."""
    if T <= 0:
        return max(S - K, 0) if option_type == 'call' else max(K - S, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def bsm_greeks(S, K, T, r, sigma, option_type='call'):
    """Return dict of BSM Greeks."""
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    delta = norm.cdf(d1) if option_type == 'call' else norm.cdf(d1) - 1
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    theta = (- S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
             - r * K * np.exp(-r * T) * (norm.cdf(d2) if option_type == 'call' else norm.cdf(-d2))) / 365
    vega  = S * norm.pdf(d1) * np.sqrt(T) / 100  # per 1% IV move
    return {'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega}
```

**VIX → IV approximation**:
```python
import yfinance as yf

def get_vix_iv_proxy(start, end):
    """VIX / sqrt(252) ≈ daily ATM IV (annualized)."""
    vix = yf.download("^VIX", start=start, end=end, progress=False)["Close"]
    return vix / 100  # VIX is in %, convert to decimal for BSM
```

**Strike construction for condor/strangle**:
```python
def synthetic_condor_strikes(S, iv, dte, short_delta=0.16, long_delta=0.05):
    """Find strikes for iron condor using delta targets."""
    T = dte / 365
    results = {}
    for target_delta in [short_delta, long_delta]:
        # Invert BSM to find strike at target delta
        from scipy.optimize import brentq
        def objective(K):
            greeks = bsm_greeks(S, K, T, 0.05, iv, 'put')
            return abs(greeks['delta']) - target_delta
        K = brentq(objective, S * 0.5, S * 0.99)
        results[f'put_{target_delta:.0%}'] = K
        results[f'call_{target_delta:.0%}'] = 2 * S - K  # symmetric
    return results
```

**Limitations**: VIX proxy assumes flat IV surface (no skew). Real puts > calls (skew). Use this for feasibility testing only.

---

### Tier 1 — LEAN / QuantConnect (Free, 10 BT/day)

**Use when**: Want realistic options simulation without raw data costs.

QuantConnect provides minute-level options chains via their data library (2010+). The LEAN engine handles:
- Automatic contract selection by delta/DTE filters
- Roll logic at expiry
- Realistic fill simulation (bid/ask midpoint or market)
- Assignment/exercise events

**Template for iron condor in LEAN** (Python algorithm):

```python
from AlgorithmImports import *

class IronCondorAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2025, 1, 1)
        self.SetCash(100000)
        
        self.spy = self.AddEquity("SPY", Resolution.Daily).Symbol
        self.option = self.AddOption("SPY", Resolution.Daily)
        self.option.SetFilter(-5, 5, 30, 60)  # delta filter, DTE filter
        
    def OnData(self, data):
        if not data.OptionChains.ContainsKey(self.option.Symbol): return
        chain = data.OptionChains[self.option.Symbol]
        
        # Select contracts: short 16-delta, long 5-delta
        puts  = [x for x in chain if x.Right == OptionRight.Put]
        calls = [x for x in chain if x.Right == OptionRight.Call]
        # ... (filter by delta, DTE, enter condor)
```

See `wiki/trading/tools/lean-quantconnect.md` for full LEAN setup.

---

### Tier 2 — ThetaData ($80/mo Standard)

**Use when**: Need historical chains for systematic backtesting, willing to compute own Greeks.

Provides tick-level historical data from 2005. You fetch raw bid/ask for each contract and compute IV/Greeks yourself using py_vollib:

```bash
pip install py_vollib
```

```python
from py_vollib.black_scholes.implied_volatility import implied_volatility
from py_vollib.black_scholes import black_scholes
from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega

# Compute IV from market price
iv = implied_volatility(
    price=option_price,
    S=underlying_price,
    K=strike,
    t=time_to_expiry,  # in years
    r=risk_free_rate,
    flag='p'  # 'c' for call, 'p' for put
)

# Compute Greeks using computed IV
d = delta('p', S, K, t, r, iv)  # put delta
g = gamma('p', S, K, t, r, iv)
th = theta('p', S, K, t, r, iv) / 365  # per day
v = vega('p', S, K, t, r, iv) / 100    # per 1% IV move
```

**py_vollib** (github.com/vollib/py_vollib, 413 stars, maintained 2026): lightweight BSM + LN Bachelier pricing. `pip install py_vollib`. Handles European options only (BSM) and binary options.

---

### Tier 3 — ORATS ($99/mo Trial)

**Use when**: Need pre-computed IV surface with skew, historical Greeks, 25 years of data.

ORATS provides 98 pre-computed indicators including:
- IV at specific deltas (IV5, IV10, IV25, IV50, IV75, IV90, IV95)
- Put/call IV skew
- VRP (IV − realized vol)
- Earnings-adjusted IVs
- 2007 to present

**Best for**: Strategy research with proper skew modeling (iron condor wings, earnings straddles).

---

## P&L Attribution — Greeks Decomposition

For any options position, total P&L decomposes as:

```
ΔP&L ≈ Δ·ΔS + ½·Γ·ΔS² + Θ·Δt + V·ΔIV
```

Where:
- **Delta P&L**: directional exposure to underlying movement
- **Gamma P&L**: benefit from large moves (long gamma) or cost (short gamma)
- **Theta P&L**: time decay — positive for short options (income)
- **Vega P&L**: sensitivity to IV changes — critical for earnings plays

For an iron condor (short strangle + protective wings):
- Target: positive Theta (collect premium) + negative Vega (benefit from IV crush)
- Risk: negative Gamma (hurt by large moves)
- Entry filter: IV Rank > 30% ensures you sell when Vega exposure is richly priced

**Python P&L attribution**:

```python
def options_pnl_attribution(position, entry, exit_state):
    """Decompose options P&L into Greeks components."""
    delta_pnl = position['delta'] * (exit_state['S'] - entry['S'])
    gamma_pnl = 0.5 * position['gamma'] * (exit_state['S'] - entry['S'])**2
    theta_pnl = position['theta'] * (exit_state['t'] - entry['t'])  # in days
    vega_pnl  = position['vega'] * (exit_state['iv'] - entry['iv']) * 100  # IV in %
    total_pnl = exit_state['price'] - entry['price']
    residual  = total_pnl - delta_pnl - gamma_pnl - theta_pnl - vega_pnl
    return {
        'delta': delta_pnl, 'gamma': gamma_pnl,
        'theta': theta_pnl, 'vega': vega_pnl,
        'residual': residual, 'total': total_pnl
    }
```

---

## VRP Signal — Free Synthetic Implementation

The variance risk premium (IV > RV ~85% of time) can be estimated without paid data:

```python
import yfinance as yf
import numpy as np

def vrp_signal(ticker='SPY', lookback=21):
    """VRP = VIX² - realized_var (annualized). Positive = sell volatility."""
    spy = yf.download(ticker, period='3mo', interval='1d', progress=False)['Close']
    vix = yf.download('^VIX', period='3mo', interval='1d', progress=False)['Close']
    
    # 21-day realized variance (annualized)
    returns = spy.pct_change().dropna()
    rv = returns.rolling(lookback).std() * np.sqrt(252)
    
    # VIX as implied vol proxy (divide by 100 for decimal)
    iv = vix / 100
    
    # VRP = IV² - RV² (variance form)
    vrp = iv**2 - rv**2
    return vrp  # positive = premium available; enter short-vol position
```

---

## Common Mistakes

| Mistake | Impact | Fix |
|---------|--------|-----|
| Assuming static IV | Understates losses in bearish moves (vol spikes) | Model IV dynamics; use VIX as IV proxy at minimum |
| Using last price instead of mid | Inflates P&L — options spread is 5-30% of premium | Use (bid+ask)/2 for simulation |
| Ignoring bid-ask as transaction cost | Iron condors on SPX: $0.50-$2.00 round-trip per leg | Budget $1-2/leg per spread; 4 legs = $4-8 cost per condor |
| Early exercise on short calls | Short calls on dividend payers get assigned | Screen for ex-dividend dates; add assignment probability |
| Confusing IV Rank with IV Percentile | IV Rank = (current-52wk low)/(52wk high-low); IV %ile = % of days IV was lower | IV %ile is more stable; use IV Rank for entry, %ile for hold |
| Backtesting only liquid underlyings | SPX/SPY condors look great; small-cap options have 20-40% spreads | Restrict to high-OI contracts (OI > 500); test spread cost impact |
| Not accounting for assignment on expiry | Near-the-money options at expiry: binary assignment event | Close all positions by 21 DTE as tastytrade rule |
| One-scenario backtest (no regime test) | 2017 low-vol regime sells great; 2020/2022 erases gains | Require regime coverage: test through at least one vol spike event |

---

## Strategy-Specific Guidance

### Iron Condor (H266 design)
- Use Tier 0 (synthetic) for parameter tuning (delta width, DTE entry, management rules)
- Validate with LEAN (Tier 1) for realistic fills
- Entry: 45 DTE, short 16Δ, long 5Δ
- Management: close at 50% profit; close/roll at 2× original credit; exit at 21 DTE
- IV Rank filter: > 30%

### SPX Dispersion (H309 Phase 2)
- Requires actual IV surface data — Tier 2 (ThetaData) or Tier 3 (ORATS)
- Compute implied correlation: ρ_implied = (IV_index² - Σᵢwᵢ²·IVᵢ²) / (2·Σᵢ<ⱼ wᵢwⱼ)
- VRP signal: short index variance (sell SPX straddle) + long component variance (buy XLK/sector straddles)
- Hedge ratio: vega-neutral — match total vega across index and component legs

### Options Portfolio Under Fat Tails (H329 design, arXiv:2606.17032)
- Use skew-elliptical t-distribution for underlying returns instead of normal
- Provides analytical weights for Sharpe and VaR ratio maximization
- Especially relevant for tail-hedging and iron condor sizing under crash regimes
- See staged proposal H329

---

## Library Quick Reference

| Library | Stars | Install | Purpose |
|---------|-------|---------|---------|
| py_vollib | 413 | `pip install py_vollib` | BSM pricing + Greeks + IV solver |
| QuantLib-SWIG | — | `pip install QuantLib` | Full derivatives library (American options, term structure) |
| mibian | ~200 | `pip install mibian` | Lightweight BSM, fast for scanning |
| vectorbt | 3.3k | `pip install vectorbt` | Equity + some options; pro version has full options module |
| LEAN (QuantConnect) | 9k+ | Docker / local | Production-grade options backtesting with data |
| py_vollib_vectorized | — | `pip install py_vollib_vectorized` | Vectorized BSM for batch pricing (much faster than py_vollib loops) |

---

## Production Checklist

Before deploying any options strategy to paper trading:

- [ ] Regime coverage: tested through VIX > 40 episode (2020 COVID or 2022)
- [ ] Spread cost model: all P&L calculated using (bid+ask)/2; transaction cost = full spread
- [ ] IV dynamics: P&L not calculated with static IV at entry
- [ ] Roll management: explicit logic for contracts approaching expiry
- [ ] Assignment handling: screening for ex-dividend dates if short calls
- [ ] Greeks monitoring: verify theta/vega balance; not just delta-focused P&L
- [ ] Position size: total short premium exposure ≤ 30% of portfolio net liquidation
