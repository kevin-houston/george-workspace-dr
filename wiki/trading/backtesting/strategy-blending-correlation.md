---
title: Strategy Blending & Correlation Management
created: 2026-06-23
updated: 2026-06-23
category: backtesting
---

# Strategy Blending & Correlation Management

How to combine confirmed strategies into a production portfolio — and how to decide whether a new confirmed strategy adds enough diversification to justify adding it.

---

## The Core Problem

Two strategies can both have OOS Sharpe > 1.5, yet blending them can produce a *worse* combined Sharpe than either alone if they are highly correlated. Conversely, a strategy with Sharpe 0.9 can dramatically improve a portfolio if it is uncorrelated with existing strategies.

**Decision rule:** A new strategy adds value if:

> `Sharpe_blend > Sharpe_best_existing`  AND  `MaxDD_blend < MaxDD_worst_existing`

---

## Production Portfolio Correlation Matrix (OOS 2018–2026)

From confirmed hypotheses, monthly return correlations OOS:

| | H026 | H041a | H045 | H198/mom | IBS | SPY |
|---|---|---|---|---|---|---|
| **H026** (sector rotation) | 1.00 | 0.71 | 0.22 | 0.58 | 0.21 | 0.62 |
| **H041a** (multi-asset) | 0.71 | 1.00 | 0.35 | 0.53 | 0.18 | 0.71 |
| **H045** (bond rotation) | 0.22 | 0.35 | 1.00 | 0.12 | 0.04 | 0.19 |
| **H198** (stock momentum) | 0.58 | 0.53 | 0.12 | 1.00 | 0.15 | 0.73 |
| **IBS** (XLK/SMH/IGV) | 0.21 | 0.18 | 0.04 | 0.15 | 1.00 | 0.29 |
| **SPY** | 0.62 | 0.71 | 0.19 | 0.73 | 0.29 | 1.00 |

**Notes:**
- H026/H041a correlation 0.71: both are momentum-driven, but H041a uses multi-asset (TLT/GLD refuge) while H026 is equity-only → moderate diversification
- H045 is the key diversifier: Corr(H026)=0.22, Corr(H041a)=0.35 — bond momentum runs on completely different signals
- IBS (internal bar strength) is also highly uncorrelated: daily mean-reversion orthogonal to monthly momentum signals
- H198 stock momentum too correlated with SPY (0.73) to add as standalone blend

---

## Production Blend Performance (OOS 2018–2026, monthly)

| Blend | Sharpe | CAGR | MaxDD | NegYrs | Corr(SPY) |
|-------|--------|------|-------|--------|-----------|
| H026 alone | 2.520 | 26.2% | -5.8% | 0 | 0.62 |
| H041a alone | 1.869 | 18.2% | -13.8% | 1 | 0.71 |
| H045 alone | 1.285 | 4.5% | -6.7% | 1 | 0.19 |
| H026+H041a+H045 equal (33/33/33) | 2.442 | — | -4.6% | 0 | 0.60 |
| H026+H041a+H045 opt (40/30/30) | 2.501 | — | -4.3% | 0 | 0.60 |
| Production (incl. IBS daily) | **4.158** | ~23.5% | -3.6% | 0 | 0.48 |

**Key insight from H318:** The IBS daily sleeve (XLK 20% / SMH 8% / IGV 2%) is responsible for most of the jump from 2.5 → 4.16 Sharpe. IBS runs on daily data and has Corr(H026)=0.21 — the orthogonality is the source of diversification, not any clever weighting of the three monthly strategies.

---

## Blending Rules

### Rule 1: Correlation gate for new strategy admission

Before adding a strategy to the production blend:
1. Compute Corr(new, H026) and Corr(new, H041a) on OOS returns
2. If both correlations > 0.70: reject — the strategy is a duplicate
3. If at least one correlation < 0.50: strong candidate for blend
4. Test: Sharpe of blend with new strategy vs without, holding weights proportional to IC

```python
import pandas as pd
import numpy as np

def marginal_sharpe(rets_dict: dict, new_name: str, new_rets: pd.Series,
                    new_weight: float = 0.10) -> dict:
    """Compute portfolio Sharpe before and after adding new strategy."""
    base_w = {k: (1 - new_weight) / len(rets_dict) for k in rets_dict}
    aligned = pd.DataFrame(rets_dict | {new_name: new_rets}).dropna()

    def sharpe(r: pd.Series) -> float:
        return r.mean() / r.std() * np.sqrt(12)

    base_port = sum(aligned[k] * base_w[k] for k in base_w)
    blend_port = base_port * (1 - new_weight) + aligned[new_name] * new_weight

    return {
        "base_sharpe":    round(sharpe(base_port), 3),
        "blend_sharpe":   round(sharpe(blend_port), 3),
        "corr_with_base": round(aligned[new_name].corr(base_port), 3),
        "new_weight":     new_weight,
    }
```

### Rule 2: Minimum independent alpha

A strategy with Corr > 0.70 to any existing strategy must achieve standalone Sharpe ≥ **1.5× the correlated strategy** to justify inclusion. Otherwise the capital is better deployed into the existing strategy.

Example: H313 (sector-neutral momentum) has Corr(H198)=0.906. To justify inclusion alongside H198, it would need OOS Sharpe ≥ 1.174 × 1.5 = 1.76. H313 achieved 0.97 → rejected.

### Rule 3: MaxDD scaling

New strategy allocation is capped at:

```
max_weight = target_MaxDD_reduction / strategy_MaxDD
```

For a portfolio targeting MaxDD ≤ -5% overall, a strategy with MaxDD -15% gets at most 33% weight. This prevents a single strategy's drawdown from blowing the portfolio limit.

---

## IC-Weighted Blending

For strategies with varying confidence levels (rolling performance), weight proportional to rolling Sharpe IC.

**When IC-weighting helps:** Strategies with **non-stationary** performance regimes (e.g., trend following works only in trending markets). If the strategies are momentum-adaptive (like H026/H041a/H045 — all momentum-based), they already handle their own regimes. IC weighting adds a second regime filter that is redundant. **(H318 finding)**

**When IC-weighting is appropriate:**
- Combining momentum + mean-reversion (genuinely opposing regimes)
- Combining equity + commodity strategies (different macro drivers)
- Strategy with clear out-of-sample alpha decay (rolling IC declining over time)

```python
def ic_weighted_blend(rets_dict: dict, window: int = 24) -> pd.Series:
    df = pd.DataFrame(rets_dict).dropna()
    port = pd.Series(np.nan, index=df.index)
    for i in range(window, len(df)):
        w_df = df.iloc[i-window:i]
        ics = {n: max(w_df[n].mean() / w_df[n].std(), 0.01) for n in w_df.columns}
        total = sum(ics.values())
        wts = {n: ics[n] / total for n in ics}
        port.iloc[i] = sum(df.iloc[i][n] * wts[n] for n in wts)
    return port.dropna()
```

**Caveat:** 24-month warmup means 2 OOS years produce NaN if OOS starts cold. Use rolling window that spans IS+OOS transition (≥ 48 months total) to avoid.

---

## Why Meta-Learning Failed for H026/H041a/H045 (H318 Lesson)

H318 tested 5 meta-learner variants to dynamically reweight the three strategies. None beat the static 40/30/30 blend meaningfully:

1. **H026 is already a regime-adaptive strategy.** Its top-1 momentum signal naturally rotates into BIL/TLT/GLD during bear markets. The strategy has internal regime detection baked in.
2. **H045 is the natural bear-market hedge.** During equity stress, bond momentum (H045) runs positive — this is already captured by the 30% static weight.
3. **Meta-learner overhead:** A regime switch that increases H045 weight to 70% in bear markets only improves by +0.08 Sharpe with no MaxDD benefit — the static 30% H045 weight is already adequate protection.

**Actionable rule:** For strategies that share the same underlying signal family (momentum), meta-learning is redundant. For strategies with fundamentally different mechanisms (momentum + mean-reversion + carry), meta-learning has more room to add value.

---

## Adding a New Strategy: Decision Flowchart

```
New strategy confirmed OOS Sharpe ≥ gate?
  └─ No → REJECT (don't blend in; insufficient standalone alpha)
  └─ Yes → compute Corr(new, each existing strategy)
            └─ All Corr > 0.70 → marginal Sharpe test
                                  └─ blend_Sharpe ≤ best_existing_Sharpe → REJECT
                                  └─ blend_Sharpe > best + 0.05 → ACCEPT at ≤ 15% weight
            └─ Any Corr < 0.50 → strong diversifier candidate
                                  └─ compute MaxDD-constrained optimal weight
                                  └─ target_weight = min(0.20, MaxDD_budget / strategy_MaxDD)
                                  └─ ACCEPT if blend improves Sharpe AND holds MaxDD gate
```

---

## Current Production Blend Rationale

| Strategy | Weight | Mechanism | Key Diversifier |
|----------|--------|-----------|-----------------|
| H026 (sector+alts rotation) | 27% | 12m momentum, 25-asset | Bull market engine |
| H041a (multi-asset top-2) | 22% | 12m momentum + vol, 7-asset | Equity/bond/gold switcher |
| H045 (bond rotation) | 21% | Bond momentum, 13-asset | Bear market / rate-cycle |
| XLK IBS | 20% | Daily mean-reversion | Orthogonal frequency |
| SMH IBS | 8% | Daily mean-reversion | Orthogonal frequency |
| IGV IBS | 2% | Daily mean-reversion | Orthogonal frequency |

The production portfolio's outperformance over the monthly-only blend (Sharpe 4.16 vs 2.50) comes almost entirely from the IBS daily sleeve being orthogonal (Corr ≈ 0.21) to the monthly rotation strategies. This is the #1 insight for future additions: **different time horizons create the most reliable diversification.**

---

## Next Addition Candidates

Based on correlation analysis:

| Candidate | OOS Sharpe | Corr(H026) | Corr(prod) | Decision |
|-----------|-----------|------------|------------|----------|
| H261b (commodity trend) | 0.922 | ~0.22 | ~0.25 | Weak standalone, strong diversifier — watch |
| H286 (COWZ value) | 1.031 | ~0.60 | ~0.55 | Medium Corr, moderate candidate at 5% |
| H309 (dispersion trading) | TBD Phase 2 | < 0.30 est. | < 0.30 est. | Very strong candidate if Phase 2 confirmed |
| H174 (PEAD NLP) | WR-based | ~0.20 est. | ~0.25 est. | Strong candidate, event-driven orthogonal |

**Production addition gate:** New strategy must improve blended Sharpe by ≥ 0.10 or reduce MaxDD by ≥ 1pp, while holding overall MaxDD ≤ -5%.

---

## Cross-References

- [Position Sizing & Portfolio Construction](../algorithms/position-sizing.md) — Kelly sizing per strategy
- [Hypothesis Log](hypothesis-log.md) — H318 (meta-agent NOT CONFIRMED), H320 (LightGBM partial)
- [Multiple Testing](multiple-testing.md) — PBO and deflated Sharpe for blends
- [Walk-Forward & CPCV](walk-forward-cpcv.md) — avoiding lookahead in blend optimization
- [ATLAS (atlas-gic)](../tools/atlas-gic.md) — Darwinian weight updates: ±5% increment alternative to full meta-learning
