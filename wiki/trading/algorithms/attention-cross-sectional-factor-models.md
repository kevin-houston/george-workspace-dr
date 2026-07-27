---
title: Attention Mechanisms and Vector Quantization for Cross-Sectional Factor Models
added: 2026-07-27
category: trading/algorithms
---

# Attention Mechanisms and Vector Quantization for Cross-Sectional Factor Models

Cross-sectional stock ranking — sorting stocks by predicted relative return and taking the top-N — is the core operation in H198, H395, H398, and all equity rotation strategies. Traditional approaches weight features uniformly or via IS-calibrated IC. Two 2026 papers introduce richer inductive biases: **regime-gated attention** (AFT, arXiv:2606.29347) and **vector-quantized discrete latent factors** (PRISM-VQ, arXiv:2605.13407).

---

## Adaptive Financial Transformer (AFT)

**Paper:** Sarkar (2026), arXiv:2606.29347  
**Hypothesis:** H456

### Architecture

AFT groups 95 engineered financial features into 11 semantic categories:

| Category | Features |
|---|---|
| momentum_short | 1m, 3m returns |
| momentum_long | 6m, 12m returns |
| reversal | 1-week return |
| volatility | 20d, 60d realized vol |
| trend | 50d MA, 200d MA cross flags |
| illusion_mom | IMOM6 (compound–arithmetic gap) |
| low_vol | inverse realized vol |
| price_level | proximity to 52-week high |
| skewness | 20d return skewness |
| drawdown | 60d max drawdown |
| regime_macro | VIX level, SPY 200MA flag |

Three components compose AFT:
1. **Market Regime Encoder** — encodes the cross-sectional feature distribution at each date into a latent regime embedding.
2. **Adaptive Gate Network** — takes the regime embedding and outputs per-category attention weights.
3. **Adaptive Financial Context Module** — biases self-attention across stocks using semantic category weights, so in a Crisis regime the model upweights volatility/drawdown categories and downweights momentum_long.

### Look-Ahead Correction

The paper explicitly identifies and corrects two sequence-alignment errors common in prior transformer finance work:
- Using same-period returns as both input features and targets (inadvertent target leakage).
- Rolling standardization computed on the full time series rather than expanding-window.

This is the same discipline as the `shift(1)` convention enforced throughout our hypothesis pipeline.

### H456 Tractable Proxy

The full AFT requires PyTorch training (~2-3h on a standard GPU). The H456 stub implements a tractable proxy:
- IS-calibrate per-category IC weights across three detected regimes (Calm/Turbulent/Crisis).
- At each OOS date, look up regime via VIX + SPY 200MA, retrieve calibrated weights, compute weighted rank average.
- Ablations test which component (regime encoder vs. adaptive gate) drives the lift.

---

## PRISM-VQ: Vector-Quantized Discrete Latent Factors

**Paper:** Kim & Song (IJCAI 2026), arXiv:2605.13407  
**Code:** github.com/finxlab/PRISM-VQ  
**Hypothesis:** H457

### Core Idea

Standard factor models assume factor loadings are fixed or continuously varying. PRISM-VQ introduces **discrete** regime-like states via vector quantization:

1. **Expert Prior Factors** — confirmed signals from the hypothesis library (IMOM6, MOM60, LowVol, IMOM12 from H398).
2. **VQ Codebook** — a set of K discrete codes learned on IS cross-sectional structure. Each stock at each date is assigned to its nearest code via L2 distance in feature space. The VQ bottleneck suppresses noise by forcing stock embeddings through a finite vocabulary of market archetypes.
3. **Mixture-of-Experts (MoE)** — each VQ code activates a different expert module with its own factor loadings. Stocks assigned to the same code share loading parameters; stocks in different codes use different loading vectors.

### Why VQ Works

The vector quantization information bottleneck is the key innovation. Raw continuous factor features contain substantial noise at each date (especially for 30-stock concentrated universes). VQ forces the model to route each stock to one of K discrete "market states," discarding fine-grained feature variation that is unlikely to generalize OOS. Prior work (STORM, arXiv:2412.09468) used continuous variational autoencoders — VQ is more robust because the discrete codes create a hard information bottleneck.

### S&P 500 Validation

The paper tests PRISM-VQ on both CSI 300 and S&P 500, making it directly applicable without cross-market transfer risk. Results on S&P 500 show consistent IC improvement over strong ML baselines including LightGBM and plain transformer rankers.

### H457 Design Note

With a 30-stock universe (H198), K=8 codes may produce unstable assignments (3-4 stocks per code). If VQ assignment variance is high, consider:
- Reducing K to 4.
- Using soft VQ (weighted combination of top-3 nearest codes).
- Expanding to H041a 60-stock universe (H417 Var C OOS 5.855 universe).

---

## Relationship to Existing Work

| Concept | Earlier Work | New Contribution |
|---|---|---|
| Regime-conditional weighting | H165 (VIX gate), H249 (4-state SPY×VIX) | AFT learns regime from cross-sectional feature distribution, not exogenous VIX |
| Discrete regime states | H429 (Wasserstein HMM), H458 (MS-GARCH) | PRISM-VQ learns regime from return cross-section, not univariate portfolio return stream |
| Factor loadings | H395 (equal-weight IMOM+MOM+LowVol) | MoE per-regime loadings outperform fixed equal-weight IS calibration |
| Attention for factor selection | H347 (Attention Factors stat-arb) | AFT adapts attention across time (not just across assets) |

### Practical Tradeoffs

- **AFT** is interpretable (explicit feature categories + regime assignments) but requires IS calibration per regime. Performance may degrade if regimes shift structurally (e.g., 2024 AI thematic rally created a new "NVDA bull" regime not in IS).
- **PRISM-VQ** is less interpretable (VQ codes are learned) but the discrete bottleneck is theoretically motivated. Code at K=8 is sensitive to IS sample size; 8 years × 12 months × 30 stocks = 2,880 observations, which supports K≤8 comfortably.
- Both approaches are most valuable when the stock universe has genuine heterogeneity. On a concentrated large-cap universe (H198), uniform IL-momentum still competes — hence the stretch gate against H398 (OOS 4.068) for H457.

---

## Cross-References

- [Factor Models & Cross-Sectional Alpha](factor-models.md) — Fama-French, Fama-MacBeth, IC/ICIR
- [Time-Series Foundation Models](ts-foundation-models.md) — Chronos-2, TimesFM, Moirai (orthogonal: time-series vs. cross-sectional)
- [AI-Driven Alpha Factor Discovery](auto-alpha-discovery.md) — FactorEngine, AlphaLogics, EFS
- [Regime Detection](regime-detection.md) — HMM, SJM, Wasserstein state matching
- [Hypothesis Log](hypothesis-log.md) — H456 (AFT), H457 (PRISM-VQ) STAGED 2026-07-27
