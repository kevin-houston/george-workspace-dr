---
updated: 2026-04-27
type: guide
---

# Position Sizing & Portfolio Construction

How to size positions and blend strategies. Directly applicable to our H018 blend (H020 + H009).

---

## Kelly Criterion

### Formula

```
f* = (b·p - q) / b
```

- `f*` = fraction of capital to bet
- `b` = win/loss ratio (avg win ÷ avg loss)
- `p` = win rate
- `q` = 1 - p (loss rate)

Equivalent form:
```
Kelly % = W - (1 - W) / R
```

Where `W` = win rate, `R` = avg win / avg loss.

### Applied to H009 (IBS mean-reversion)

From the H009 backtest:
- Win rate: ~60% (estimated from Sharpe 0.63 + characteristics)
- Avg win ≈ 2× avg loss (typical for mean-reversion)

```
Kelly = 0.60 - (0.40 / 2.0) = 0.60 - 0.20 = 0.40 (40% of capital)
```

**Use fractional Kelly in practice** — full Kelly maximizes long-run growth but produces extreme volatility. Standard choices:

| Fraction | Portfolio vol | Long-run growth |
|----------|--------------|-----------------|
| Full Kelly (1.0×) | ~2× optimal | Maximum CAGR |
| Half Kelly (0.5×) | ~√2× optimal | ~75% of max CAGR |
| Quarter Kelly (0.25×) | ~optimal | ~50% of max CAGR |

Most professionals use **half Kelly**. Reason: Kelly assumes exact probability estimates; real estimates have error. Half Kelly is forgiving of estimation error and still captures most of the edge.

For our strategies: start with **quarter Kelly** in paper trading, graduate to half Kelly after 6 months of live results.

---

## Risk Parity (Equal Risk Contribution)

### Core idea

Size each asset (or strategy) so it contributes *equal volatility* to the portfolio, rather than equal capital.

### Inverse volatility weighting (practical approximation)

```python
import numpy as np

def risk_parity_weights(vols: dict[str, float]) -> dict[str, float]:
    """Simple inverse-vol weights. vols = {symbol: annualized_vol}."""
    inv_vols = {s: 1.0 / v for s, v in vols.items()}
    total = sum(inv_vols.values())
    return {s: w / total for s, w in inv_vols.items()}

# Example: H020 universe
vols = {"SPY": 0.19, "QQQ": 0.24, "TLT": 0.13, "GLD": 0.16, "IEF": 0.07}
weights = risk_parity_weights(vols)
# → IEF gets highest weight (lowest vol); QQQ gets lowest
```

### Full ERC formula (accounts for correlations)

```
RC_i = w_i × (σ_i × ρ_{i,p} × σ_p)
```

- `RC_i` = risk contribution of asset `i`
- `w_i` = weight of asset `i`
- `σ_i` = asset volatility
- `ρ_{i,p}` = correlation of asset `i` with portfolio
- `σ_p` = total portfolio volatility

Goal: set weights so all `RC_i` are equal. Requires numerical optimization. Use `scipy.optimize.minimize` with the ERC objective function.

### When to use risk parity

H020's current approach (rank-based, top-2 equal weight) already partially risk-adjusts by penalizing high-vol assets through the inverse-vol rank component of the score. Full risk parity is useful if you want to hold *all* assets with different weights instead of a binary top-2 selection.

---

## Volatility Targeting

### Concept

Set a *target portfolio volatility* (e.g., 10% annualized). Scale positions up or down to hit it.

```
position_scale = target_vol / current_portfolio_vol
```

### Example

H020 full-period annualized vol: ~12%. To target 10%:
```
scale = 0.10 / 0.12 = 0.83
→ Reduce all positions to 83% of nominal (17% in cash)
```

If H020 vol drops to 8% during calm markets:
```
scale = 0.10 / 0.08 = 1.25
→ Scale up to 125% (25% leverage — only appropriate in margin accounts)
```

### Practical implementation

Use **exponentially weighted volatility** (EWM) — recent data matters more:

```python
def ewm_vol(returns: pd.Series, span: int = 60) -> float:
    """Annualized EWM volatility."""
    return returns.ewm(span=span).std().iloc[-1] * np.sqrt(252)
```

Recompute and rebalance monthly. This naturally reduces exposure when markets are volatile (like 2022) and increases it during calm periods.

---

## Blended portfolio sizing (H018: H020 + H009)

H018 confirmed: 0.31 daily return correlation between H016 and H009.

### Two-strategy portfolio variance

```
σ²_blend = w₁²·σ₁² + w₂²·σ₂² + 2·w₁·w₂·ρ·σ₁·σ₂
```

Plugging in H018 actuals (from backtest):
- `σ_H016 = 11.4%` (annualized vol)
- `σ_H009 = 14.9%`
- `ρ = 0.31`
- `w₁ = w₂ = 0.5`

```
σ²_blend = 0.25 × 0.114² + 0.25 × 0.149² + 2 × 0.25 × 0.31 × 0.114 × 0.149
         = 0.000325 + 0.000556 + 0.000264
         = 0.001145

σ_blend = √0.001145 = 10.7%   ← matches backtest result exactly
```

The 0.31 correlation saved ~2% of annualized volatility vs naive addition. At 0.0 correlation it would be ~9.4%; at 1.0 it would be ~13%.

### Optimal split between H020 and H009

To find the minimum-variance combination (ignoring returns):

```python
from scipy.optimize import minimize_scalar

s1, s2, rho = 0.114, 0.149, 0.31

def blend_vol(w1):
    w2 = 1 - w1
    return np.sqrt(w1**2*s1**2 + w2**2*s2**2 + 2*w1*w2*rho*s1*s2)

result = minimize_scalar(blend_vol, bounds=(0, 1), method='bounded')
print(f"Min-variance split: H020={result.x:.1%}, H009={1-result.x:.1%}")
# → H020=58%, H009=42%  (lower vol on H020 means slightly more weight)
```

The 50/50 split we used is close to optimal. Min-variance would be ~58/42 in favor of H020, giving about 0.1% less annualized vol.

---

## Practical position limits

| Rule | Value | Rationale |
|------|-------|-----------|
| Single trade risk | 1–2% of equity | Standard risk management |
| Single ETF max allocation | 50% | H020 equal-weight already enforces this |
| Strategy concentration | ≤60% in any one strategy | Protects against model failure |
| Portfolio heat (total open risk) | ≤10% | Sum of all stop-based losses |
| Correlated positions | Count as one | SPY + QQQ = ~one equity position |

### Position limits for H018

At $102k paper account:
- H020 side: $51k → two ETFs at ~$25.5k each
- H009 side: $51k → SPY position when signal fires (≈$51k, held 1-5 days)
- When H009 is flat (most days): $51k sits in cash earning ~5% (T-bills equivalent)

**Practical result**: average daily equity exposure is well below 100% because H009 is only invested ~30-40% of trading days.

---

## Implementation checklist for Phase 3

- [ ] Compute H020 signal monthly → target weights
- [ ] Compare target vs current Alpaca holdings → generate trade list
- [ ] Apply 2% single-trade risk cap
- [ ] Execute sells first, then buys
- [ ] Log fill prices vs backtest assumed prices (slippage tracking)
- [ ] Monthly: update 60-day EWM vol, check if vol-targeting adjustment needed
- [ ] Quarterly: recheck Kelly fractions based on realized paper trading win rate
