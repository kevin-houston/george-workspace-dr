---
title: Herding, Momentum, and Reversal — Network Information Diffusion Theory
description: Agent-based network model explaining the momentum-to-reversal transition through local herding and delayed information diffusion; implications for momentum age/streak signals
tags: momentum, reversal, herding, network-theory, agent-based, behavioral-finance, h198, h181, momentum-streak
added: 2026-07-30
category: Trading / Concepts
---

# Herding, Momentum, and Reversal — Network Information Diffusion Theory

## The Central Puzzle

Classical finance cannot explain why:
1. Momentum (3-12 month horizon) and reversal (1-3 month and 3-5 year horizon) **coexist** in
   the same securities
2. The **transition** between momentum and reversal is relatively predictable
3. Both effects **strengthen** when investor attention is clustered geographically or sectorally

A network-based herding model provides a unified explanation.

---

## Source Paper

**arXiv:2607.27063** (Jul 2026) — "Herding, Momentum, and Reversal in China's A-Share Market:
An Agent-Based Network Model with Information Diffusion"

### Model Architecture

Investors are placed on a network (von Neumann / Moore lattice; Erdős-Rényi; Watts-Strogatz
for robustness). Each investor:

1. Forms a **heterogeneous Gaussian belief** about next-period price: μ_i ~ N(v, σ²_belief)
2. Chooses **buy / sell / inactive** based on their belief vs current price
3. **Updates action probability** by copying neighboring investors who were "right" recently
   (local herding / imitation)
4. Receives **delayed information** about fundamental value v with a lag τ_i drawn from a
   distribution of information delays

### Information Diffusion Mechanism

The key insight is **two distinct time scales**:

- **Short run (1-9 months)**: local herding creates positive autocorrelation. Early-informed
  investors buy → neighboring investors imitate without having the information → price rises
  above fundamental, creating further buying pressure
- **Long run (9-24 months)**: information eventually diffuses to all nodes in the network.
  Once all investors are informed, the "late-arrival" effect kicks in — late-informed investors
  realize the stock is now overpriced relative to their (delayed) fundamental signal → sell
  pressure → reversal

### Mathematical Structure

The aggregate price dynamics satisfy approximately:

```
P(t) = P_0 + α·E[fundamental] + β·ρ^{(t)} - γ·ρ^{(t-τ_network)}
```

Where:
- ρ^{(t)} = density of "herding-in" investors at time t
- τ_network = characteristic network diameter × information propagation speed
- α, β, γ > 0 are structural parameters

**Momentum phase**: when t < τ_network, ρ^{(t)} > ρ^{(t-τ_network)} → price rises (trend-following)
**Reversal phase**: when t > τ_network, ρ^{(t)} < ρ^{(t-τ_network)} → price falls (mean-reversion)

### Calibration Results (China A-Shares)

- **Momentum phase duration**: 3-9 months (consistent with 6-1m skip-month momentum window)
- **Reversal onset**: 9-18 months after initial information shock
- **Network topology effect**: Small-world networks (Watts-Strogatz) generate more pronounced
  momentum AND sharper reversals than random graphs (Erdős-Rényi) — due to clustering
- **Herding intensity effect**: higher herding parameter → longer momentum, stronger reversal

---

## US Market Adaptation

China A-shares have higher retail participation and herding intensity than US large-cap equities.
Expected differences for H198 30-stock NASDAQ universe:

| Property | China A-Shares | US Large-Cap NASDAQ |
|-----------|---------------|---------------------|
| Retail participation | ~75% | ~20-30% |
| Network diameter | Larger (fragmented) | Smaller (institutional) |
| Momentum duration | 3-9 months | 3-12 months (J&T 1993) |
| Reversal onset | 9-18 months | 12-36 months (DeBondt/Thaler) |
| Herding intensity | High | Moderate |

**Key implication for H198**: The 6-1m skip-month signal already avoids the 1-month
reversal (noise), but does NOT account for whether a stock is in early-momentum phase vs
late-momentum (approaching reversal threshold).

---

## Momentum Streak Signal

The network model suggests a **momentum streak** signal: count the number of consecutive months
a stock has ranked in the top quintile of cross-sectional momentum. 

- **Short streak (1-3 months)**: likely early-herding phase → continuation expected
- **Medium streak (3-6 months)**: momentum is maturing → normal continuation with some risk
- **Long streak (6+ months)**: approaching network saturation → reversal risk elevated

### Empirical Evidence for Streak Effects

1. **Grinblatt & Moskowitz (2004)**: "Predicting Stock Price Movements from Past Returns: The Role
   of Consistency and Tax-Loss Selling." Shows that stocks with more consistent positive returns
   (higher streak-like metrics) have stronger future momentum.

2. **Sagi & Seasholes (2007)**: "Stock Returns Following Profit Warnings." Momentum
   performance deteriorates sharply for stocks with already-embedded large price moves.

3. **The "exhausted winner" pattern**: Practitioners observe that stocks which have been momentum
   winners for 4+ quarters begin to underperform their sector — consistent with herding saturation.

---

## Connection to Existing Confirmed Strategies

### H198 (6-1m Momentum, OOS Sharpe 1.174)

The H198 signal does not differentiate between:
- A stock that entered the top-6 one month ago (fresh momentum signal)
- A stock that has been in the top-6 for 12 consecutive months (mature momentum)

The network model predicts these two groups have different forward expectations. H477 (staged
2026-07-30) tests whether a streak-conditioned variant improves OOS Sharpe.

### H181 (Industry-Adjusted Reversal, OOS Sharpe 1.138)

H181 exploits 1-month reversal (buying last month's losers). The network model explains
WHY reversal is strongest at 1 month: it captures the noise/microstructure layer (fast mean
reversion) before the herding momentum builds at 2-9 months. H181 and H198 are designed to
be orthogonal precisely because they operate at different phases of the herding cycle.

### H376 (6-0m No-Skip Momentum, OOS Sharpe 3.120)

Including the most recent month in the momentum signal (no skip) might seem to benefit from
fresh information, but the network model suggests the 1-month autocorrelation at monthly
frequency is noise (bid-ask bounce / microstructure), not herding momentum. H376's
outperformance over H198 is not due to the 1-month price move being informative, but likely
because the 6m window on large-cap NASDAQ is sufficiently short that mature-momentum stocks
have not yet reached saturation.

---

## Herding Detection in Practice

Without individual investor position data (unavailable for most practitioners), herding can
be proxied via:

1. **Return autocorrelation of the sector**: high AC₁ (positive lag-1 correlation in a sector
   or stock) suggests active herding phase
2. **Volume-price correlation**: herding creates volume spikes on price moves (Blume, Easley,
   O'Hara 1994)  
3. **Breadth within momentum quintile**: when most stocks in the momentum quintile are trending
   together (high intra-quintile correlation), herding is likely widespread
4. **Short interest dynamics**: herding usually accompanies declining short interest as shorts
   cover → peak short cover = herding saturation signal

### Practical Implementation Note

For H477, the simplest proxy is the **momentum streak counter** (months consecutively ranked
top-6). This captures the key theoretical prediction (duration-based saturation) without
requiring investor-level data or complex herding detection algorithms.

---

## Strategy Design Implications

### Momentum Entry Timing

The herding model suggests **momentum is more reliable when newly established** than when
mature. Practical criteria for "fresh" momentum:

```python
# Streak counter: months consecutively in top-N
def compute_streak(ranks, top_n=6, total_stocks=30):
    """
    ranks: DataFrame of monthly momentum ranks (lower = better momentum)
    Returns: DataFrame of streak lengths per stock
    """
    in_top = (ranks <= top_n)
    streak = in_top.copy().astype(int)
    for t in range(1, len(ranks)):
        streak.iloc[t] = np.where(
            in_top.iloc[t],
            streak.iloc[t-1] + 1,
            0
        )
    return streak

# Exclude old-momentum stocks (streak >= 6 months)
def h477_select(momentum_ranks, streak, top_n=6, max_streak=5):
    eligible = streak <= max_streak
    eligible_ranks = momentum_ranks.where(eligible, other=np.inf)
    return eligible_ranks.nsmallest(top_n).index
```

### Reversal Entry Timing

The herding saturation model also informs H181 (reversal). The reversal effect should be
strongest for stocks that:
1. Were recent momentum winners (top-quintile 6-12 months ago)
2. Have recently dropped out of the momentum quintile (herding exhaustion)
3. Experience a sharp reversal of fund flows (detectable via price momentum sign flip)

This suggests a "fallen angel" sub-strategy within H181: among last month's losers, prefer
those that were recent momentum winners (herding exhaustion candidates) over structural
value stocks (which lose for different reasons).

---

## Cross-References

- [Momentum Strategies](../trading/algorithms/momentum-strategies.md) — H198, H376, H377 momentum family
- [Short-Term Reversal](../trading/algorithms/short-term-reversal.md) — H181 industry-adjusted reversal
- [Behavioral Finance Signals](../trading/algorithms/behavioral-finance-signals.md) — 52w high anchoring, disposition effect
- [Multi-Memory Factor Model](../trading/backtesting/multi-memory-factor-model-equity.md) — spectral frequency decomposition (persistent/momentum/reversal factors)
- [Signal Half-Life & Alpha Decay](../trading/backtesting/signal-halflife.md) — momentum decay timing
- H477 (staged 2026-07-30) — momentum streak backtest on H198

---

## References

- Anon. (2026). "Herding, Momentum, and Reversal in China's A-Share Market: An Agent-Based
  Network Model with Information Diffusion." arXiv:2607.27063.
- Grinblatt, M. & Moskowitz, T.J. (2004). "Predicting Stock Price Movements from Past Returns:
  The Role of Consistency and Tax-Loss Selling." *Journal of Financial Economics*, 71(3), 541-579.
- Jegadeesh, N. & Titman, S. (1993). "Returns to Buying Winners and Selling Losers: Implications
  for Stock Market Efficiency." *Journal of Finance*, 48(1), 65-91.
- DeBondt, W.F.M. & Thaler, R. (1985). "Does the Stock Market Overreact?" *Journal of Finance*,
  40(3), 793-805.
- Hong, H. & Stein, J.C. (1999). "A Unified Theory of Underreaction, Momentum Trading, and
  Overreaction in Asset Markets." *Journal of Finance*, 54(6), 2143-2184.
  (Original underreaction/overreaction model; network model is a structural microfoundation)
- Watts, D.J. & Strogatz, S.H. (1998). "Collective dynamics of 'small-world' networks."
  *Nature*, 393, 440-442. (Network topology referenced in paper)
