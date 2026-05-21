---
updated: 2026-05-21
type: guide
relevance: all confirmed strategies; multi-strategy portfolio Phase 3
---

# Position Sizing & Portfolio Construction

How to size positions and blend our confirmed strategies. Updated for the current confirmed portfolio: H026, H174, H181, H192-D, H198, H201.

**Related pages**: [Portfolio Optimization Libraries](../tools/portfolio-optimization.md) (PyPortfolioOpt/Riskfolio/skfolio) | [Backtesting Design Principles](../backtesting/design-principles.md) | [Walk-Forward & CPCV](../backtesting/walk-forward-cpcv.md) | [Regime Detection](regime-detection.md) (gating strategies by market state)

---

## Confirmed Strategy Inventory (as of 2026-05-21)

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
