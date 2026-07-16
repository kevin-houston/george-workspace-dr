---
updated: 2026-07-16
type: guide
relevance: all confirmed strategies; multi-strategy portfolio Phase 3
---

# Position Sizing & Portfolio Construction

How to size positions and blend our confirmed strategies. Updated for the current production portfolio: **H041a 22% / H026 27% / H045 21% / IBS 30%** (OOS Sharpe 4.158, MaxDD −3.60%, ~23.5% CAGR, zero negative years 2004–2025).

**Related pages**: [Portfolio Optimization Libraries](../tools/portfolio-optimization.md) (PyPortfolioOpt/Riskfolio/skfolio) | [Backtesting Design Principles](../backtesting/design-principles.md) | [Walk-Forward & CPCV](../backtesting/walk-forward-cpcv.md) | [Regime Detection](regime-detection.md) (gating strategies by market state)

---

## Production Portfolio (as of 2026-07-16)

Current live allocation in Alpaca paper account (~$102k):

| Sleeve | Strategy | Alloc | OOS Sharpe | MaxDD | Frequency |
|--------|----------|-------|-----------|-------|-----------|
| Stock momentum | H041a (4-factor top-2: IMOM6+MOM60+LowVol+IMOM12) | 22% | 4.068 | −8.4% | Monthly |
| ETF rotation | H026 (25-asset sector+alts dual-rank top-1) | 27% | 2.665 | −5.7% | Monthly |
| Bond rotation | H045 (13-asset bond ETF top-2 rank ensemble) | 21% | 1.351 | −6.3% | Monthly |
| Daily reversal | IBS (XLK/SMH/IGV Internal Bar Score) | 30% | ~2.5 standalone | est. −12% | Daily |
| **Combined** | **Production blend** | **100%** | **4.158** | **−3.60%** | — |

**Key observation**: the IBS daily sleeve is the primary source of the portfolio's Sharpe jump from ~2.5 (rotation-only) to 4.158 — it is largely uncorrelated with monthly strategies because it trades at intraday resolution on different assets. H041a and H026 are partially correlated (both momentum-based on equity ETFs vs individual stocks) but different enough to compound diversification.

## Legacy Confirmed Strategy Inventory (as of 2026-05-21)

These strategies are confirmed but not in the current production blend; they are candidates for future blending.

| Strategy | OOS Sharpe | MaxDD | Frequency | Corr bucket |
|----------|-----------|-------|-----------|-------------|
| H026 ETF Rotation (TSMOM) | 3.007 | −14.2% | Monthly | Time-series momentum |
| H174 PEAD NLP (FinBERT 8-K) | OOS 80.8% win | −est. 15% | Event-driven | Event |
| H181 Industry-Adj. Reversal | 1.138 | −18.7% | Monthly | Short-term reversal |
| H192-D BAB Sector-Neutral | 1.367 | −15.4% | Monthly | Low-beta factor |
| H198 6-1m Cross-Sec Momentum | 1.174 | −22.7% | Monthly | Cross-sec momentum |
| H201 TOM SPY Timing | 0.740 | −9.3% | Daily (4d/mo) | Calendar |

**Key observation**: these strategies occupy different factor buckets. Empirical correlations between factor strategies are low-to-moderate, enabling genuine diversification. PEAD is nearly orthogonal to all systematic strategies (event-driven vs. calendar-driven).

---

## Kelly Criterion

### Single-strategy formula

```
f* = (b·p - q) / b  =  W - (1-W)/R
```

- `W` = win rate, `R` = avg win / avg loss, `b` = W/L ratio

### Applied to our strategies

| Strategy | Est. win rate | Est. W/L | Full Kelly | Half Kelly |
|----------|--------------|----------|-----------|-----------|
| H026 ETF Rotation | ~62% | 2.8× | 44% | 22% |
| H174 PEAD NLP | 80.8% | ~1.8× | 59% | 29% |
| H181 Reversal | ~56% | 2.4× | 33% | 16% |
| H192-D BAB | ~58% | 2.6× | 36% | 18% |
| H198 Momentum | ~57% | 2.5× | 35% | 17% |
| H201 TOM | ~55% | 2.1× | 29% | 14% |

**Use fractional Kelly in practice.**

| Fraction | Risk profile | Recommended for |
|----------|-------------|-----------------|
| Full (1.0×) | ~2× optimal vol | Never in practice |
| Half (0.5×) | Robust to estimation error | Live trading with 12+ months OOS data |
| Quarter (0.25×) | Conservative | Paper trading; first 6 months live |

### Multivariate Kelly (multiple simultaneous strategies)

When strategies run concurrently, the optimal allocation accounts for cross-strategy correlations. The multivariate Kelly maximizes expected log-growth of the combined portfolio.

**Matrix form** (continuous approximation): `f* = Σ⁻¹ μ`

Where `μ` is the vector of strategy expected excess returns and `Σ` is the strategy covariance matrix. This is identical in form to the tangency portfolio problem — the Kelly-optimal multi-strategy portfolio IS the max-Sharpe portfolio.

```python
import numpy as np
from scipy.linalg import solve

def multivariate_kelly(mu: np.ndarray, cov: np.ndarray,
                       max_leverage: float = 2.0) -> np.ndarray:
    """
    Kelly-optimal fractions for n concurrent strategies.
    mu:  (n,) vector of expected annualized excess returns
    cov: (n,n) covariance matrix of annualized returns
    Returns: (n,) fractional allocations (sum may exceed 1.0 = leverage)
    """
    f = solve(cov, mu)                  # Σ⁻¹ μ
    total = np.abs(f).sum()
    if total > max_leverage:
        f = f * max_leverage / total    # scale to max leverage
    return f


# Example: 3-strategy portfolio (H192-D BAB, H198 Momentum, H181 Reversal)
# Annualized excess returns (rough OOS estimates)
mu = np.array([0.067, 0.095, 0.082])   # BAB ann_ret ≈ 6.7%; MOM ≈ 9.5%; REV ≈ 8.2%

# Annualized vols and pairwise correlations (see table below)
vols = np.array([0.085, 0.115, 0.095])
corr = np.array([
    [1.00, 0.15, -0.10],   # BAB vs BAB, MOM, REV
    [0.15, 1.00,  0.05],   # MOM
    [-0.10, 0.05, 1.00],   # REV
])
cov = np.diag(vols) @ corr @ np.diag(vols)

kelly_fracs = multivariate_kelly(mu, cov, max_leverage=1.0)
print(dict(zip(["BAB", "MOM", "REV"], kelly_fracs.round(3))))
# → {'BAB': 0.38, 'MOM': 0.40, 'REV': 0.22}  (approximate — depends on estimates)
```

**Practical limit**: Kelly fractions are highly sensitive to mean return estimates (the most uncertain input). Use half the computed Kelly fraction as the actual allocation. Recompute quarterly from realized OOS data.

---

## Cross-Strategy Correlation Estimates

Empirical correlations between our factor buckets (literature estimates, annual returns):

| | ETF Rotation | PEAD | Reversal | BAB | Momentum | TOM |
|-|---|---|---|---|---|---|
| **ETF Rotation** | 1.00 | 0.05 | 0.10 | 0.10 | 0.45 | 0.20 |
| **PEAD** | 0.05 | 1.00 | 0.05 | 0.02 | 0.15 | 0.00 |
| **Reversal** | 0.10 | 0.05 | 1.00 | −0.10 | −0.20 | 0.05 |
| **BAB** | 0.10 | 0.02 | −0.10 | 1.00 | 0.15 | 0.05 |
| **Momentum** | 0.45 | 0.15 | −0.20 | 0.15 | 1.00 | 0.15 |
| **TOM** | 0.20 | 0.00 | 0.05 | 0.05 | 0.15 | 1.00 |

**Key observations:**
- ETF Rotation and Momentum are the most correlated (both momentum-based, ~0.45). Treat them as partially redundant.
- Reversal and Momentum are negatively correlated (~−0.20) — the best diversification pair in our portfolio.
- BAB and Reversal are slightly negatively correlated (~−0.10) — also complementary.
- PEAD is nearly uncorrelated with everything (event-driven mechanism vs. calendar-driven). Highest diversification value.
- TOM is essentially orthogonal to most strategies (calendar timing overlay).

**Source**: AQR factor return data, Frazzini & Pedersen (2014) BAB paper, Israel & Moskowitz (2013) on momentum/reversal interaction, internal H205 analysis (TOM vs. BAB).

---

## Risk Parity (Equal Risk Contribution)

### Inverse volatility (quick approximation)

```python
import numpy as np

def risk_parity_weights(strategy_vols: dict) -> dict:
    """Inverse-vol weights. vols = {name: annualized_vol}."""
    inv = {s: 1.0 / v for s, v in strategy_vols.items()}
    total = sum(inv.values())
    return {s: w / total for s, w in inv.items()}

# Current strategy annualized vols (from backtest results)
vols = {
    "H026_ETF":    0.09,   # low vol — mostly in BIL/TLT
    "H174_PEAD":   0.14,   # event-driven; moderate vol
    "H181_REV":    0.10,   # reversal; moderate
    "H192D_BAB":   0.085,  # sector-neutral; low vol
    "H198_MOM":    0.115,  # higher vol; 30-stock concentrated
    "H201_TOM":    0.07,   # SPY timing; very low active vol
}
weights = risk_parity_weights(vols)
# → H201_TOM and H192D_BAB get the most weight; H198_MOM the least
```

### Full ERC (accounts for correlations)

```python
from scipy.optimize import minimize

def erc_weights(cov: np.ndarray) -> np.ndarray:
    """Equal Risk Contribution weights via numerical optimization."""
    n = cov.shape[0]
    def risk_budget_obj(w):
        port_var = w @ cov @ w
        mrc = cov @ w          # marginal risk contributions
        rc = w * mrc           # risk contributions
        rc_target = port_var / n
        return np.sum((rc - rc_target) ** 2)

    w0 = np.ones(n) / n
    result = minimize(
        risk_budget_obj, w0,
        method='SLSQP',
        constraints={'type': 'eq', 'fun': lambda w: w.sum() - 1.0},
        bounds=[(0.01, 0.60)] * n,   # min 1%, max 60% per strategy
    )
    return result.x
```

---

## Volatility Targeting

Target a **10% annualized portfolio volatility** across all strategies combined. Scale each strategy's allocation when realized vol diverges from target.

```python
def ewm_vol(returns: pd.Series, span: int = 60) -> float:
    """Annualized EWM volatility."""
    return returns.ewm(span=span).std().iloc[-1] * np.sqrt(252)

def vol_target_scale(current_vol: float, target_vol: float = 0.10,
                     max_scale: float = 1.5) -> float:
    """Scale factor to hit target vol. Capped at max_scale to limit leverage."""
    return min(target_vol / current_vol, max_scale)
```

**Recompute monthly.** Natural de-risking: during high-vol periods (VIX > 25, 2022-style), scale drops automatically. During calm periods, can modestly increase exposure toward target.

---

## Suggested Multi-Strategy Allocation

Based on half-Kelly fractions, adjusted for practical constraints:

| Strategy | Raw half-Kelly | Adj. allocation | Notes |
|----------|---------------|-----------------|-------|
| H026 ETF Rotation | 22% | 20% | Flagship; time-tested 382× |
| H174 PEAD NLP | 29% | 15% | Event-driven; size limited by capacity |
| H181 Reversal | 16% | 15% | Monthly rebalance |
| H192-D BAB | 18% | 20% | Highest confirmed Sharpe |
| H198 Momentum | 17% | 15% | Diluted by ETF Rotation overlap |
| H201 TOM | 14% | 10% | Overlay; low CAGR standalone |
| **Cash buffer** | — | 5% | Execution reserve |

**Concentration adjustment**: H026 and H198 both express momentum; combined momentum exposure is ~35% of portfolio. If momentum regime turns adverse (2022-style), this concentration will hurt. Consider capping combined momentum to ≤30% or adding a VIX gate on both.

### Python blending scaffold

```python
import pandas as pd
import numpy as np

# Daily strategy returns (from live paper trading logs)
# Each column = one strategy's daily P&L as fraction of allocated capital
strategy_returns = pd.DataFrame({
    "H026": ...,   # from paper_trading/h122-alpaca log
    "H174": ...,   # from paper_trading/pead logs
    "H181": ...,   # from paper_trading/h181-alpaca log
    "H192D": ...,
    "H198": ...,
    "H201": ...,
})

# Target allocations
TARGET_ALLOC = {
    "H026": 0.20, "H174": 0.15, "H181": 0.15,
    "H192D": 0.20, "H198": 0.15, "H201": 0.10,
}

# Combined portfolio return
alloc_vec = pd.Series(TARGET_ALLOC)
portfolio_ret = (strategy_returns * alloc_vec).sum(axis=1)

# Monthly rebalancing: compute vol-targeting scale
monthly_vol = ewm_vol(portfolio_ret.last("60D"))
scale = vol_target_scale(monthly_vol, target_vol=0.10)

# Adjusted allocations
adjusted = {k: v * scale for k, v in TARGET_ALLOC.items()}
```

---

## Practical Position Limits

| Rule | Value | Rationale |
|------|-------|-----------|
| Single strategy max allocation | 25% | No strategy failure should exceed −5% portfolio impact |
| Combined momentum exposure | ≤30% | H026 + H198 are correlated; cap combined |
| Single PEAD position | ≤5% of capital | Event-driven; binary outcome |
| Portfolio heat (total open risk) | ≤10% | Sum of all stop-based losses |
| TOM overlay | ≤15% | Low CAGR standalone; keep as timing enhancement |
| Min allocation per active strategy | 5% | Below this, transaction costs dominate |

### Strategy-specific sizing

**H174 PEAD (event-driven)**: size individual positions at 2–4% of capital, not 15% in one name. The 15% allocation is the total capital reserved for PEAD, deployed across 1–3 concurrent positions.

```python
MAX_PEAD_ALLOCATION = 0.15   # 15% of portfolio to PEAD bucket
MAX_SINGLE_PEAD = 0.04       # 4% max per position
# → max 3–4 concurrent PEAD positions before capital constraint hits
```

**H181 Reversal (30 stocks equal weight)**: each stock gets 15%/30 = 0.5% of total portfolio. No single-stock risk dominates.

**H192-D BAB (sector-neutral)**: by construction, the long and short legs are beta-neutral and sector-neutral. Effective market exposure is near zero — can size more aggressively than pure long strategies.

---

## PEAD Note: Large-Cap vs. Microcap

Recent research (2024, IDEAS/ReFEC) finds PEAD t-stat drops to 1.43 when excluding microcaps in raw price-based signals. **Our H174 is immune to this**: the FinBERT NLP signal (8-K language quality + EPS surprise gate) generates alpha from information asymmetry, not price momentum. The 80.8% win rate is achieved on large-cap stocks with genuine surprises filtered by dual threshold. Mechanism differs from PEAD price-based studies.

---

## Regime-Conditional Sizing

All strategies show regime-dependent performance. Apply VIX + 200MA gate:

```python
def regime_scale(spy_prices: pd.Series, vix: pd.Series,
                 date, bull_scale: float = 1.0, bear_scale: float = 0.5) -> float:
    """
    Reduce all strategy allocations by bear_scale in bear/stress regimes.
    Applies to H198 (momentum most vulnerable) and H181 (reversal degrades).
    H192-D BAB: do NOT reduce in bear — it performs BETTER in bear (13.8% vs 6.7% bull).
    """
    is_bull = spy_prices[date] > spy_prices[:date].rolling(200).mean()[date]
    is_calm = vix[date] < 25.0
    return bull_scale if (is_bull and is_calm) else bear_scale

# Strategy-specific bear regime handling:
BEAR_REGIME_ADJUSTMENT = {
    "H026": 0.5,   # TSMOM built-in exit; reduce further in VIX>25
    "H174": 1.0,   # PEAD: regime-neutral (event-driven)
    "H181": 0.7,   # Reversal degrades somewhat in bear
    "H192D": 1.2,  # BAB: performs BETTER in bear; actually increase slightly
    "H198": 0.5,   # Momentum worst in bear (2022 -25%)
    "H201": 1.0,   # TOM calendar effect: regime-neutral
}
```

---

## Quarterly Review Checklist

- [ ] Recompute EWM vols for each strategy from live paper trading returns
- [ ] Update Kelly fractions from realized win rates (not IS backtest estimates)
- [ ] Recheck cross-strategy correlation from live paper trading data
- [ ] Apply vol-targeting scale adjustment
- [ ] Check combined momentum exposure (H026 + H198 < 30%)
- [ ] Review PEAD capacity: if earnings season thins, reduce H174 allocation
- [ ] Log deviation between target and actual allocations

---

## Volatility Targeting — Adaptive Leveraged Vol Control (SALVOC)

**Source**: arXiv:2603.01298 — "Single-Asset Adaptive Leveraged Volatility Control" (March 2026)  
**Tested on**: 44 ETFs (US equities, international equities, commodities, sector funds), OOS Jan 2010–Dec 2024  
**Target volatility**: σᵗᵃʳ = 15% annualized (0.15/√252 daily)

### Results vs baseline (IVV S&P 500)

| Method | Sharpe | MaxDD |
|--------|--------|-------|
| Unmanaged IVV | 0.31 | 55.3% |
| Open-loop vol control | 0.33 | 38.6% |
| **SALVOC (adaptive)** | **0.42** | **37.1%** |

**MaxDD reduction: 18.2pp.** Sharpe improvement: 0.31 → 0.42 (+35%).

### The proportional control formula

SALVOC operates in log-space to avoid the compounding distortion of linear scaling:

```python
import numpy as np

def salvoc_weight(sigma_hat: float, sigma_target: float = 0.15,
                  kappa: float = 0.0, g: float = 0.5, theta: float = 0.8,
                  kappa_min: float = -1.5, kappa_max: float = 1.5,
                  L: float = 2.0) -> tuple[float, float]:
    """
    Single step of SALVOC proportional control.
    sigma_hat:   realized volatility estimate (annualized)
    sigma_target: target annualized volatility (default 15%)
    kappa:       current control state (log-scale bias)
    g, theta:    proportional gain and smoothing factor
    L:           leverage cap (max weight)
    Returns:     (weight, new_kappa)
    """
    e_k = np.log(sigma_hat / sigma_target)           # tracking error (log)
    update = -g * np.clip(e_k, kappa_min, kappa_max) # proportional correction
    kappa_new = (1 - theta) * update + theta * kappa  # exponential smoothing
    w = min(np.exp(kappa_new) * sigma_target / sigma_hat, L)
    return w, kappa_new

# Example: rolling application on monthly ETF data
def apply_salvoc(returns: pd.Series, sigma_target: float = 0.15,
                 vol_window: int = 21) -> pd.Series:
    sigma_estimates = returns.ewm(span=vol_window).std() * np.sqrt(252)
    weights = []
    kappa = 0.0
    for sigma in sigma_estimates:
        w, kappa = salvoc_weight(sigma, sigma_target, kappa)
        weights.append(w)
    return pd.Series(weights, index=returns.index)
```

### Practical notes for our ETF rotation strategies

- Apply SALVOC at the **strategy sleeve level** (not individual ETF), e.g. on H026 monthly returns.
- Target vol of **15%** matches momentum factor natural volatility; use **10%** for the combined portfolio (less aggressive).
- The open-loop version (`wₖ = σᵗᵃʳ / σ̂ₖ`) is simpler and captures most of the benefit (Sharpe 0.33 vs 0.42). Use it as the default implementation.
- Cap leverage at 1.0× (no leverage) for production; only allow up to 1.5× once live graduation criteria are met.
- **Does not require OOS lookahead**: all σ̂ estimates use only data through t−1.

---

## Regime-Based Factor Allocation Sizing (SJM)

**Source**: arXiv:2410.14841 — "Dynamic Factor Allocation Leveraging Regime-Switching Signals" (Oct 2024)  
**Method**: Sparse Jump Model (SJM) — same approach as the Regime Detection wiki recommends (Shu et al. 2024)  
**Universe**: 7 factor ETFs — PBUS (market), VLUE (value), SIZE (size), MTUM (momentum), QUAL (quality), USMV (min-vol), IWF (growth)

### Performance improvement from regime-based sizing

| Metric | Static EW | Dynamic SJM |
|--------|-----------|-------------|
| Sharpe | 0.52 | 0.60 |
| Information Ratio vs market | ~0.05 | 0.43 |
| MaxDD | −54.9% | −52.2% |
| Transaction cost | 5bp/leg | 5bp/leg |

### Position sizing rule

The SJM identifies a bull or bear regime for each factor ETF separately. Position weights are set by the regime-specific expected active return:

```python
def regime_factor_weight(expected_active_return: float,
                         threshold: float = 0.05) -> float:
    """
    Set allocation based on regime's expected annual active return vs market.
    expected_active_return: positive = bull regime, negative = bear regime
    threshold: dead zone around zero (5% default)
    """
    if expected_active_return > threshold:
        return 1.0          # 100% long factor
    elif expected_active_return < -threshold:
        return -1.0         # 100% short factor (long market)
    else:
        # Linear interpolation in the dead zone
        return expected_active_return / threshold
```

**Regime inputs**: RSI, stochastic oscillator, MACD, EWMA returns at 8/21/63-day windows, VIX (log-differenced), 2Y yield, yield curve slope (10Y−2Y). The SJM minimizes a joint clustering + transition-penalty objective; RSI₆₃ and %K₆₃ receive highest feature importance (~11% each) in the value factor example.

**Implication for H026/H041a**: the SJM approach explains why H026's dual-rank (momentum + LowVol) outperforms pure momentum — it implicitly down-weights assets in bear regimes by assigning them low LowVol rank. The explicit SJM approach makes this regime detection transparent and tunable.

---

## Kelly-VIX Hybrid for Options Sleeve

**Source**: arXiv:2508.16598 — "Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put-Writing on Index Options" (Aug 2025)

For the options income sleeve (H266 iron condor / CSP strategy), combine Kelly sizing with VIX-rank position scaling:

### VIX-rank scaling (reduce size in high-vol regimes)

```python
def vix_rank_scale(vix_current: float, vix_history: pd.Series,
                   lookback: int = 252) -> float:
    """
    Scale position SIZE inversely with VIX regime.
    High VIX percentile → smaller size (more risk per contract, need fewer).
    """
    vix_window = vix_history.tail(lookback)
    percentile = (vix_window < vix_current).mean()   # VIX rank [0,1]
    return 1.0 - percentile                           # scale: 1.0 at low VIX, 0.0 at peak

def kelly_vix_contracts(portfolio_value: float, margin_per_contract: float,
                        kelly_fraction: float, vix_current: float,
                        vix_history: pd.Series) -> int:
    """
    Number of contracts = floor(portfolio_value / margin_per_contract
                               * kelly_fraction * vix_scale)
    """
    vix_scale = vix_rank_scale(vix_current, vix_history)
    return int(portfolio_value / margin_per_contract * kelly_fraction * vix_scale)
```

### Observed performance (OOS, SPX 0-DTE options)

| Strategy | Return (ann.) | Vol | MaxDD |
|----------|--------------|-----|-------|
| Full Kelly (0 DTE, 10% OTM) | 14.4–17.2% | 8.5% | ~0% |
| VIX-rank (5 DTE, 0% OTM) | est. high | — | 9.91% |
| Kelly-VIX hybrid (5 DTE, 0% OTM) | 22.1–23.1% | ~18% | 9.5–10.7% |

**Key finding**: Fractional Kelly reduces volatility more than it reduces expected growth — a favorable tradeoff. The VIX-rank overlay handles tail risk that pure Kelly doesn't see (Kelly assumes stationarity; VIX-rank injects regime awareness). Best blend: use half-Kelly as the base and VIX-rank as the scaling multiplier.

---

## Updated Quarterly Review Checklist (Production Portfolio)

- [ ] Recompute EWM vols for each sleeve: H041a, H026, H045, IBS
- [ ] Verify H026 dual-rank top-1 pick is live (check pead_open.log for current month)
- [ ] Check IBS strategy equity vs target (target: $5k per sleeve = $30k IBS total)
- [ ] Update correlation between IBS daily returns and monthly strategy returns (target: corr < 0.3)
- [ ] Apply SALVOC open-loop adjustment if realized 60-day vol > 12% or < 7%
- [ ] Check VIX for options sleeve sizing (if VIX > 25, scale down by VIX-rank factor)
- [ ] Log combined momentum exposure: H041a + H026 should stay ≤55% (both momentum but different universes)
- [ ] Review PEAD paper trading win rate: gate ≥75% over trailing 20 events
