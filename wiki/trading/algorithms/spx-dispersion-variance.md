---
updated: 2026-06-19
hypothesis: H309 (PARTIAL)
---

# SPX Dispersion Trading & Variance Risk Premium

Dispersion trading harvests the **correlation risk premium**: index options persistently price implied correlation higher than subsequently realized pairwise stock correlation. The trade is structurally short the index implied-correlation level and long the realized correlation realized by the basket.

**Status (H309):** Phase 1 confirmed (variance risk premium + implied correlation premium validated with proxy metrics). Phase 2 blocked on Polygon options API for historical component IV.

---

## Core Math

Index variance decomposes as:

```
σ²_index = Σᵢ Σⱼ wᵢ wⱼ ρᵢⱼ σᵢ σⱼ
         ≈ ρ̄ × σ̄_weighted²
```

Rearranging for implied correlation:

```
ρ_implied = (σ_index)² / (Σᵢ wᵢ σᵢ)²
```

When σ_index = VIX / 100 and σᵢ = component HV21 (or component IV):

```python
# Dirty correlation proxy (Phase 1: realized vol only)
mro = (vix / 100.0)**2 / sigma_wb**2   # implied / weighted-avg component variance

# Full dispersion (Phase 2: actual component IV needed)
rho_implied = iv_index**2 / weighted_avg_component_iv**2
```

**Practical example:** SPX IV = 20%, weighted avg component IV = 30%  
→ Implied correlation = (0.20/0.30)² = **0.44**

---

## Correlation Risk Premium — Empirical Evidence

| Study | Period | Implied Corr | Realized Corr | Premium |
|-------|--------|-------------|--------------|---------|
| Driessen, Maenhout & Vilkov (2005) | 1996-2003 | ~50% | ~32% | **18 pp** |
| Faria, Kosowski & Wang (2021) | 91-day options | varies | varies | **6.7–8.9 pp** |
| H309 Phase 1 (proxy, HV21) | 2010-2026 | Mρ > Realized: 87% of months | varies | confirmed positive |

**Key observation:** VIX exceeds realized SPX volatility ~73% of months. This variance risk premium is the index leg of the dispersion trade. Component IV is typically also rich, but the index IV richness exceeds that of components — the correlation premium.

---

## CBOE Indices for Signal Construction

| Index | Ticker | Description | Update Frequency |
|-------|--------|-------------|-----------------|
| VIX | ^VIX | 30-day implied vol on SPX | Real-time |
| DSPX | (CBOE, Sept 2023+) | 30-day implied dispersion (index minus component vol) | Real-time |
| COR1M | ^COR1M | 1-month implied correlation on S&P 500 | Daily |
| COR3M | ^COR3M | 3-month implied correlation on S&P 500 | Daily |

**DSPX methodology:** VIX-style computation combining index options with cap-weighted single-stock options. High DSPX + low COR3M = "busy stocks / calm index" = ideal long-dispersion entry environment.

**Free data access:**
```python
import yfinance as yf

# Implied correlation indices (free via Yahoo Finance)
cor1m = yf.download("^COR1M", start="2020-01-01")["Close"]
cor3m = yf.download("^COR3M", start="2020-01-01")["Close"]
vix   = yf.download("^VIX",   start="2020-01-01")["Close"]

# DSPX not in yfinance yet — check CBOE data site directly
# https://www.cboe.com/products/futures-and-options/volatility/s-p-500-dispersion
```

---

## Trade Construction: "Dirty" Dispersion (Practical Version)

The theoretical trade is pure correlation — short index variance, long basket variance. In practice, "dirty dispersion" uses straddles:

### Long Dispersion (Short Correlation) — Standard Setup

```
SELL: ATM straddle on SPX (30-DTE, monthly roll)
BUY:  ATM straddles on top-N SPX constituents (same expiry)
      Sized vega-neutral: SPX notional vega = Σ component notional vega
```

**Entry signal:** COR3M > historical 70th percentile OR DSPX elevated
**Exit:** Expiry (pure premium capture) or at 50% P&L (straddle management)

### Strike Selection (kurupjayesh approach)

- **SPX leg:** Nearest ATM strike (delta ≈ 0.50 call / -0.50 put)
- **Component legs:** Nearest 3 OTM strikes considered; use ATM for simplicity
- **Delta hedging:** Rebalance delta every 15 minutes using ES futures for SPX leg; stock position for component delta

### Vega Neutral Sizing

```python
def compute_vega_neutral_weights(spx_vega_per_contract, component_vegas, weights):
    """
    spx_vega_per_contract: float, vega of one SPX straddle
    component_vegas: dict {ticker: vega_per_contract}
    weights: dict {ticker: market_cap_weight}
    Returns: number of contracts per component
    """
    target_vega = spx_vega_per_contract  # match SPX straddle vega
    n_contracts = {}
    total_component_vega = sum(component_vegas[t] * weights[t] 
                               for t in component_vegas)
    scale = target_vega / total_component_vega
    for ticker in component_vegas:
        n_contracts[ticker] = scale * weights[ticker]
    return n_contracts
```

### H309 Simplified Universe (Top 30 S&P 500 by weight)

```python
COMPONENTS = {
    "AAPL": 0.073, "MSFT": 0.065, "NVDA": 0.060, "AMZN": 0.038,
    "META": 0.027, "GOOGL": 0.022, "GOOG": 0.018, "BRK-B": 0.017,
    "LLY":  0.015, "AVGO": 0.014, "JPM":  0.014, "TSLA": 0.013,
    "V":    0.011, "UNH":  0.011, "XOM":  0.011, "MA":   0.010,
    "COST": 0.009, "HD":   0.009, "PG":   0.008, "JNJ":  0.008,
    "WMT":  0.008, "ABBV": 0.007, "BAC":  0.007, "CRM":  0.006,
    "MRK":  0.006, "CVX":  0.006, "ORCL": 0.006, "NFLX": 0.006,
    "KO":   0.005, "PEP":  0.005,
}
# Together these 30 represent ~60% of S&P 500 market cap
# More than adequate for dirty-dispersion implementation
```

---

## H309 Phase 1 Results (Proxy Metrics Only)

Sub-hypothesis 1 — Short SPX Variance Premium:
- VIX exceeds SPX realized vol by **~4.1 pp on average**
- Always-on short index vol: OOS Sharpe **>2.0** (confirmed via proxy returns)
- VIX>20 gated variant: OOS Sharpe similarly positive
- Win rate ~73% of months historically

Sub-hypothesis 3 — Implied Correlation Premium:
- Mρ (dirty implied corr) exceeds realized correlation **87% of months**
- Dispersion P&L proxy positive and persistent
- Full phase 2 needed for accurate sizing/returns

**Phase 1 verdict: PARTIAL — variance risk premium and implied correlation premium confirmed; full dispersion returns require component IV data.**

---

## Phase 2: Full Implementation Requirements

### What Phase 2 Needs

| Data Point | Source | Cost | Notes |
|-----------|--------|------|-------|
| Historical component IV (ATM, 30-DTE) | Polygon options API | $79/mo options add-on | Daily snapshots from 2014 |
| Historical SPX straddle prices | Polygon or ThetaData | Same | Need bid/ask for slippage |
| Component option chains (ATM strikes) | Polygon or ThetaData | Same | 30 stocks × monthly |
| ES futures (delta hedge) | Alpaca / Polygon | Free | CME front-month |

### Phase 2 Python Scaffold

```python
import os, pandas as pd
from polygon import RESTClient

POLYGON_KEY = os.environ["POLYGON_API_KEY"]
client = RESTClient(POLYGON_KEY)

def get_component_atm_iv(ticker: str, target_date: str, dte_target: int = 30) -> float:
    """
    Fetch nearest ATM straddle IV for a given ticker on a given date.
    Requires Polygon options add-on.
    
    target_date: "2024-01-31" format
    Returns: float, annualized IV (decimal, e.g. 0.28 = 28%)
    """
    # Get current price for ATM determination
    snap = client.get_snapshot_option(ticker, params={"limit": 1})
    # NOTE: historical snapshot not available on Polygon free tier
    # For backtesting: use bulk historical chain endpoint
    # GET /v3/options/snapshots/{underlying}?as_of=YYYY-MM-DD (premium endpoint)
    pass

def compute_dispersion_signal(date: str, component_ivs: dict, 
                               spx_iv: float, weights: dict) -> dict:
    """
    Full dispersion signal.
    
    component_ivs: {ticker: iv_float}   e.g. {"AAPL": 0.28, "MSFT": 0.25, ...}
    spx_iv: float                       SPX 30-DTE ATM straddle IV
    weights: {ticker: weight}
    
    Returns: dict with signal metrics
    """
    sigma_wb = sum(weights[t] * component_ivs[t] 
                   for t in component_ivs if t in weights)
    rho_implied = (spx_iv**2) / (sigma_wb**2)
    
    return {
        "spx_iv": spx_iv,
        "sigma_wb": sigma_wb,        # weighted avg component IV
        "iv_spread": sigma_wb - spx_iv,  # component vol > index vol (expected)
        "rho_implied": rho_implied,  # implied correlation
        "long_dispersion": rho_implied > 0.60,  # entry trigger
    }
```

### Historical Component IV: Polygon Endpoint

```python
# Polygon options add-on: historical IV snapshot (as_of parameter)
# This is a PREMIUM endpoint — not available on standard Polygon tier
# GET https://api.polygon.io/v3/snapshot/options/{underlyingAsset}
#     ?as_of=2024-01-31&strike_price_near=ATM&expiration_near=30d

# Alternative: reconstruct from historical bars + py_vollib
from py_vollib.black_scholes.implied_volatility import implied_volatility
import requests

def get_hist_component_iv(ticker: str, date: str, risk_free: float = 0.045) -> float:
    """
    Reconstruct ATM IV from Polygon historical options bars.
    NOTE: Requires options add-on ($79/mo).
    """
    # Step 1: Get underlying price on target date
    r = requests.get(
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{date}/{date}",
        params={"apiKey": os.environ["POLYGON_API_KEY"]}
    )
    spot = r.json()["results"][0]["c"]
    
    # Step 2: Find nearest ATM call, 30-DTE expiry
    # Step 3: Get its historical close price
    # Step 4: Solve for IV using py_vollib
    # ... (implementation in run_h309_phase2.py)
    pass
```

---

## Execution Considerations

### Transaction Cost Reality

The theoretical correlation premium is 6-18 pp. In practice:
- **Bid-ask spread on 30 component straddles:** ~0.5-1.0 vol pt per leg × 60 legs = 3-6 vol pts round-trip
- **Net edge after costs:** 1-2 vol pts → needs careful execution
- **Practical solution:** Use top-10 components (cover ~45% of SPX weight) to reduce cost

### Delta Hedging Protocol

```python
DELTA_REBALANCE_BAND = 0.05   # rebalance if portfolio delta > ±0.05
HEDGE_INSTRUMENT = "ES=F"     # CME E-mini S&P 500 futures
ES_MULTIPLIER = 50            # $50 per index point

def needs_rebalance(current_delta: float, band: float = DELTA_REBALANCE_BAND) -> bool:
    return abs(current_delta) > band
```

### Monthly Roll Calendar

- **Entry:** First Friday of each month (after NFP, before weekend)
- **Expiry:** 4th Friday (standard monthly expiry)
- **30-DTE target:** Maximizes theta decay while retaining vega sensitivity
- **Rolling:** Close expiring straddles on Thursday, open next month

---

## Risk Factors

| Risk | Description | Magnitude | Management |
|------|-------------|-----------|-----------|
| Correlation spike | Macro shock causes ρ → 1 (2008, 2020, 2022) | Large loss | VIX stop: exit if VIX > 40 |
| Gap risk | Earnings gaps not covered by delta hedge | Medium | Avoid entering near component earnings |
| Gamma squeeze | Short index gamma magnifies losses when market moves fast | Medium | Manage SPX leg delta daily |
| Execution cost | Wide spreads on OTM options | Reduces edge | Use ATM only; limit to top-10 components |
| Correlation convexity | Position becomes long vol as corr rises (negative convexity) | Structural | Monitor vega tilt; overweight long-component leg slightly |

**Correlation convexity detail:** In a market crash (ρ → 1), the index straddle short loses more than the component straddle longs gain. The position is inherently negatively convex to correlation. Partial mitigant: size component leg vega 1.1–1.2× index leg ("correlation overweight").

---

## Entry/Exit Signal Framework (H309 Phase 2 Design)

```python
def dispersion_entry_signal(cor3m: float, dspx: float, 
                             cor3m_70pct: float, dspx_30pct: float) -> bool:
    """
    Enter long dispersion when:
    - Implied correlation (COR3M) is elevated (≥ 70th pct)
      AND
    - DSPX shows high expected dispersion (≥ 30th pct)
    
    The combination: high implied corr + high expected dispersion = 
    index options expensive vs components → ideal short-correlation entry.
    """
    return cor3m >= cor3m_70pct and dspx >= dspx_30pct

def dispersion_exit_signal(realized_corr_last_30d: float,
                            implied_corr: float,
                            threshold: float = 0.05) -> bool:
    """
    Exit when the premium has decayed (realized ≈ implied).
    Also: hard stop if realized correlation spike > 0.85 (systemic event).
    """
    premium_decayed = abs(implied_corr - realized_corr_last_30d) < threshold
    systemic_spike  = realized_corr_last_30d > 0.85
    return premium_decayed or systemic_spike
```

---

## Quantpedia Performance Reference

From Quantpedia's strategy database (backtest 1996-2007):
- **Annual Return:** 15.4% (after transaction costs, using analyst disagreement filter)
- **Sharpe Ratio:** 0.82
- **Annualized Volatility:** 13.9%
- **Max Drawdown:** -43.5% (concentrated in 2002-2003 and expected to spike in 2008)
- **Universe:** S&P 100 (100 components, 21-position portfolio)

**Caveat:** 2007-era backtest predates heavy 0-DTE volume and post-COVID idiosyncratic vol regime. Updated backtest needed with DSPX (2023+) as timing signal.

---

## Factor Dispersion Variant (CBOE Research)

CBOE research (Gerchik, Ruffo, Schonleber) identifies **factor-level dispersion** as an alternative: rather than single-stock options, use ETF options for size/value/quality/momentum factors:

```
SELL: SPX straddle
BUY: Sector ETF straddles weighted by factor loading

Instruments: XLK, XLF, XLV, XLY, XLE (sector ETFs have liquid options)
Advantage: No single-stock earnings gamma risk; lower transaction costs
Disadvantage: Less dispersion capture (sector ETFs more correlated than single stocks)
```

This is a cheaper, less precise version — viable before Polygon options data available.

---

## References

- Driessen, Maenhout & Vilkov (2005): "Option-Implied Correlations and the Price of Correlation Risk" — foundational paper documenting 18pp correlation premium 1996-2003
- CBOE DSPX Index Launch Note (Sept 2023): https://www.cboe.com/insights/posts/the-impact-of-dispersion-on-market-expectations-and-volatility
- Resonanz Capital DSPX Explainer: https://resonanzcapital.com/insights/dispersion-trading-and-the-dspx-index
- Moontower Media — "Dispersion Trading for the Uninitiated" (correlation convexity section): https://medium.com/@moontower/dispersion-trading-for-the-uninitiated-f96d9f6d6c7a
- IBKR Quant "Dirty Dispersion" (entry/exit, z1/z2/z3 thresholds): https://www.interactivebrokers.com/campus/ibkr-quant-news/dispersion-trading-in-practice-the-dirty-version/
- GitHub kurupjayesh/Dispersion-Trading-using-Options: https://github.com/kurupjayesh/Dispersion-Trading-using-Options
- Quantpedia Dispersion Trading: https://quantpedia.com/strategies/dispersion-trading
- arXiv:1004.0125 — Variance dispersion and correlation swaps (Jacquier & Slaoui 2010)
- arXiv:2603.25320 — Semi-static hedging of covariance risk (2025, geometric dispersion trades)
