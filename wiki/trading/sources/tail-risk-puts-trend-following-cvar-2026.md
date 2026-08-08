---
created: 2026-08-08
updated: 2026-08-08
type: source_summary
authors: Miquel Noguer i Alonso, Ali Al Fallouji
published: 1 Jul 2026 (arXiv)
source: arXiv:2607.00883
url: https://arxiv.org/abs/2607.00883
---

# Tail Risk Management with Puts and Trend Following: A CVaR Framework for Crashes and Drawdowns — Noguer i Alonso & Al Fallouji 2026

**Authors:** Miquel Noguer i Alonso, Ali Al Fallouji
**Venue:** arXiv:2607.00883, submitted 1 Jul 2026

## Framework

A continuous-time CVaR (Conditional Value-at-Risk) framework combining two tail-protection strategies inside a single mandate:

1. **Long out-of-the-money (OTM) put options**, modeled as marked-to-market traded assets (not a static hedge ratio).
2. **Systematic trend-following overlays.**

The authors derive a Hamilton-Jacobi-Bellman (HJB) equation incorporating wealth, spot price, stochastic variance, and the trend signal jointly — i.e. solving for the optimal blend rather than assuming a fixed weight.

## Key mechanism: the two sleeves protect different phases of a drawdown

The paper's most useful finding for George's purposes is not a performance number but a *timing* insight, quoted directly: "convex insurance reprices immediately on jump impact, whereas trend following is late on the first shock because its signal must cross zero, but becomes increasingly defensive during persistent drawdowns."

In plain terms:
- **Puts** = instant protection at the moment of a shock (a gap-down, a crash day) — but decay/cost money if no shock occurs.
- **Trend-following** = structurally *behind* on the first shock (a moving-average or momentum signal needs time to flip negative) but compounds increasingly defensive positioning as a drawdown persists.

These are complementary, not substitutable — a hybrid captures the immediate-shock case a pure-momentum overlay misses, and the persistent-decline case a pure-put overlay pays a running premium for without needing.

## Results

The abstract text does not disclose specific Sharpe/CVaR numbers, but reports directionally that "fixed equal-weight hybrids and grid-optimized hybrids reduce terminal CVaR relative to either pure sleeve in the reported regimes," while noting the exact optimal weight is calibration-dependent (i.e., not a universal constant — would need re-derivation for George's specific asset universe and vol regime).

## Relevance to George's stack

George currently treats options income (VRP harvesting, CSP/wheel, iron condors — [Options Income Strategies](../algorithms/options-income-strategies.md)) and trend/momentum crash protection (H320's LightGBM crash filter on H198, [Momentum Strategies](../algorithms/momentum-strategies.md)) as separate research tracks. This paper suggests a specific new design direction: a small **tail-hedge overlay sleeve** on top of the production portfolio (H041a/H026/H045/IBS, OOS Sharpe 4.158) that blends (a) a rules-based long-OTM-put allocation sized to portfolio delta and (b) the existing SPY 200MA / VIX regime gates already used in H301/H165/H249, explicitly reasoning about which of the two components would have caught 2020 COVID (an instant jump — puts win) vs. 2022 rate-hike grind (a persistent multi-month decline — trend-following wins). Distinct from H273 (vol-targeting overlay, which scales exposure but doesn't add convex protection) and from H320 (which filters entries, doesn't add a hedge instrument).

Not yet a numbered hypothesis — options data cost (ORATS/Polygon per [Options Data Sources](../data-sources/options-data.md)) and the calibration-dependence noted above make this a Phase-2 candidate once a cheap historical OTM-put pricing proxy is available (Tier 0 BSM per [Options Backtesting Methodology](../backtesting/options-backtesting-methodology.md) may suffice for a first pass).

## See Also

- [Options Income Strategies](../algorithms/options-income-strategies.md) — existing options toolkit this would extend from income-generation to tail-hedging
- [Momentum Strategies](../algorithms/momentum-strategies.md) — H320 LightGBM crash filter, the single-sleeve trend-following crash mitigation this paper's hybrid would complement
- [Options Backtesting Methodology](../backtesting/options-backtesting-methodology.md) — tiered data approach for a first-pass historical put pricing proxy
- [Volatility Risk Premium](../algorithms/volatility-risk-premium.md) — VRP harvesting context; this paper is the mirror image (buying convexity, not selling it)
