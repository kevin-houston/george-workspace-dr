---
title: DeePM — Regime-Robust Deep Learning for Macro Portfolio Management
added: 2026-07-07
updated: 2026-07-09
category: algorithms
url: https://arxiv.org/abs/2601.05975
code: https://github.com/kieranjwood/deepm
---

# DeePM: Regime-Robust Deep Learning for Systematic Macro Portfolio Management

**Paper**: arXiv:2601.05975 | Wood, Roberts, Zohren (Oxford ML, Jan 2026)  
**GitHub**: github.com/kieranjwood/deepm (MIT license, Python ≥ 3.10, CUDA GPU recommended)  
**Related**: arXiv:2603.01820 (same group, DL benchmark on futures); arXiv:2607.00475 (concurrent E2E parametric policy comparison)

---

## Summary

DeePM (Deep Portfolio Manager) is a structured deep-learning macro portfolio manager trained end-to-end to maximize a robust, risk-adjusted utility on 50 diversified futures contracts (2010–2025). Three architectural innovations make it regime-resilient where classical CTA trend-following has collapsed post-2016.

---

## Performance Benchmarks (2010–2025, Net of Costs)

| Method | Net Sharpe | Notes |
|--------|-----------|-------|
| Passive Equal Risk | ~0.50 | Diversified equal risk-weight baseline |
| TSMOM (classical trend) | ~0.45 | Standard time-series momentum |
| Momentum Transformer | ~0.66 | Prior SOTA; same Oxford group |
| **DeePM (GAT)** | **~0.93** | **~2× TSMOM; ~50% above MT** |

- **Max Drawdown**: ~21% lower than best baseline (Macro Graph Prior ablation contributes this)
- **Information Ratio** vs passive: 0.44
- **Average holding period**: 7.1 days
- **Turnover**: Low (cost-aware training with γ=0.5 penalizes excessive turnover)
- **Regime coverage**: Positive returns through 2010s "CTA Winter" AND post-2020 inflation regime — both periods that killed classical trend followers

Note: Net Sharpe of 0.93 on 50 futures is in a different return universe from the ETF strategies (H026 OOS 1.200+). The absolute level isn't comparable; the relative improvement vs baselines is the signal.

---

## Three Architectural Innovations

### 1. Directed Delay (Causal Sieve)

Solves the "ragged filtration" problem — different macro data series (GDP, CPI, equity prices, commodity term structures) arrive asynchronously. The Causal Sieve enforces **strict t−1 lag** on all cross-sectional context before feeding into the temporal attention layer, prioritizing causal impulse-response patterns over data freshness.

- **Why it works**: Sacrificing freshness for causality prevents look-ahead contamination from asynchronous feeds
- **Ablation**: Cascading filtration (maximize freshness) vs Directed Delay — Directed Delay wins out-of-sample
- **Applicability**: Less critical for synchronous equity markets (same closing time) but critical for multi-asset portfolios with macro data lags

### 2. Macroeconomic Graph Prior (GAT Layer)

Regularizes cross-asset dependence using an **ex-ante deterministic economic graph** rather than learned correlations:

- **Edges**: Based on economic first-principles (commodity → inflation → rates; FX → equities; energy → industrials)
- **Mechanism**: Graph Attention Network (GAT) with anisotropic learnable weights
  ```
  α_{ij,t} = Softmax_j((Q h_{i,t})^T (K h_{j,t}) / √d + ln(A_{ij}))
  ```
  where A_{ij} is the fixed graph adjacency matrix encoding economic links
- **Key ablation**: GAT with economic prior **reduces Max Drawdown by 21%** vs isotropic GCN or no graph
- **Why**: Prevents overfitting to spurious cross-asset correlations in the noisy financial learning problem

### 3. Distributionally Robust Objective (SoftMin EVaR)

Replaces standard Sharpe maximization with a **smooth worst-window adversarial penalty**:

```
ℒ(θ) = −SR_pool(ℛ) − λ · SoftMin_τ({SR_b})
```

Where:
- `SR_pool` = pooled Sharpe over the full training window
- `SR_b` = Sharpe of each non-overlapping time block (e.g., quarterly)
- `λ` = weight on the adversarial term (tunable)
- `τ` = SoftMin temperature (lower τ → harder minimax; higher τ → risk-neutral)

The SoftMin penalty serves as a differentiable proxy for **Entropic Value-at-Risk (EVaR)** — optimizing for worst-case regime performance rather than average performance.

**Critical finding**: The SoftMin adversarial penalty is identified as the **single largest driver** of cross-regime stability. Without it, the model performs well in calm periods but collapses in regime shifts (2016 CTA Winter, 2022 inflation shock, 2020 COVID).

---

## Full Architecture Stack

| Layer | Component | Specification |
|-------|-----------|---------------|
| Input embedding | V-VSN | Vectorized Variable Selection Network; FiLM-based feature gating with learnable softmax weights; selects most predictive feature subset per asset |
| Temporal | LSTM | Single-layer recurrent encoder initialized with asset embedding projection |
| Temporal | Causal MHA | Multi-head attention with ResSwiGLU adapter; Post-Norm + ReZero gating (α_cross ≈ 0 at init) |
| Cross-sectional | Directed Delay | Strictly lag cross-sectional context to t−1 (Causal Sieve) |
| Graph | GAT | Graph Attention Network with anisotropic weights + economic prior adjacency ln(A_{ij}) bias |
| Output | Position signals | Volatility-targeted portfolio weights w_{i,t} |

**Key design choices**:
- ReZero initialization (α≈0) makes the model functionally shallow at init → stable training
- Post-Norm layernorm throughout
- Asset-specific static embeddings e_i ∈ ℝ^d plus transaction cost context c_i fed into every forward pass

---

## Feature Engineering (Input Features)

Constructed exclusively from **daily closing prices** (no alternative data, no macro series):

| Feature | Formula | Horizons |
|---------|---------|---------|
| Vol-normalized returns | R_{i,t}^(h) = (P_{i,t}/P_{i,t-h} − 1) / (σ̂_{i,t} √h + ε) | h ∈ {1, 21, 63, 252} days |
| MACD trend | MACD_{S,L} = (EWM_S − EWM_L) / σ̂_{i,t} | 3 scales: (8,24), (16,48), (32,96) |
| Z-score mean reversion | log-price Z-score over rolling window | ℓ ∈ {21, 252} days |
| Clipping | ±5 × 1.48 × MAD_t on 252-day rolling median | Prevents gradient explosions from outlier returns |
| Ex-ante vol | 63-day EWMA (σ̂_{i,t}) | Used for all normalization and notional sizing |

**Parsimony variants** (ablation):
- **Raw Momentum**: Lagged returns + Z-scores only (no overlapping momentum windows)
- **Signal-Based**: 1-day return + MACD + Z-scores — avoids redundant overlapping windows, reduces overfitting in high-capacity architectures

---

## Transaction Cost Model

```
cost_i ≈ C_struct,i × λ_i
```

- **Structural floor**: ~0.5–1 bp for liquid electronic markets (tick-size quantization)
- **Liquidity scalar λ_i**: Asset-specific multiplier (1.0 for S&P 500 futures; higher for illiquid markets)
- **Training penalty**: `γ/N_t ∑_i m_{i,t} c_i |w_{i,t} − w_{i,t-1}|`
- **Optimal γ**: 0.5 (intermediate) beats γ=1.0 (full cost). Rationale: individual models benefit from looser regularization; ensembling handles actual cost control.

---

## Training Details

- **Optimizer**: AdamW with rolling-window training
- **Burn-in period**: L₀ = 21 days (LSTM warm-up before loss contribution)
- **Gradient computation**: Exact two-pass microbatching to compute global Sharpe statistics across non-separable Sharpe objectives (Appendix C.3 describes the algorithm)
- **Ensemble**: Train multiple seeds, select top K by validation Sharpe, average weights
- **GPU**: RTX 4090 used for experiments

---

## Ablation Summary

| Component Removed | Impact on Out-of-Sample |
|------------------|------------------------|
| Directed Delay → Cascading filtration | Worse OOS (freshness < causality) |
| GAT → GCN (isotropic Laplacian) | +21% Max Drawdown |
| SoftMin penalty → standard Sharpe | Collapse during regime shifts; this is the **primary driver** |
| End-to-end → two-stage (signal-then-allocate) | ~2× gross Sharpe reduction |
| Full cost penalty (γ=1.0) vs γ=0.5 | ~50% worse net out-of-sample when ensembled |

---

## Installation & Quick Start

```bash
# Recommended: uv
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -e .

# Or pip
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Full pipeline: train + backtest + metrics
bash scripts/reproduce.sh

# Quick smoke test (reduced settings)
bash scripts/smoke_test.sh

# Train the main GAT model
python -m deepm.training -r "deepm-gat" -a DeePM

# Backtest with diagnostics
python -m deepm.backtest --name "bt-deepm-gat" --diagnostics
```

**Key dependencies**: PyTorch, PyTorch Geometric (PyG) for GAT, W&B for experiment tracking, Pandas/Parquet

**Data format**: Wide-format parquet with daily closing prices for 50 futures (equities, rates, energy, metals, agriculture, livestock, FX), 1990–2025

---

## Adaptation Path for ETF/Equity Universe (H318 / H249 Extension)

The core architecture maps from 50 futures to any multi-asset universe with modifications:

| Aspect | Futures (as-is) | ETF/Equity Adaptation |
|--------|----------------|----------------------|
| Graph topology | Inflation/rates/commodity triangle | Sector homophily + earnings correlation edges; GICS hierarchy |
| Directed Delay | Critical (async macro data) | Relaxed (synchronous equity closing prices) |
| Transaction costs | Tick-size based (0.5–1 bp) | Spread + market impact; adjust λ_i per ETF liquidity |
| Feature set | OHLCV only | Same closing-price features + optional order flow |
| Asset embedding dim | Calibrated for N=50 | Scale with universe size; keep O(N) graph edges |
| Lookback L | Set by MACD/return horizons | Extend for mean-reversion in equities; 63–252 day range |
| Burn-in L₀ | 21 days | Extend if using intraday features |
| Universe size | 50 futures (tractable) | 200–500 stocks → ensure GPU memory (batch the cross-sectional attention) |

**Practical minimum for ETF universe adaptation (H318 path)**:
1. Build GICS-based graph prior for H026's 25-asset universe
2. Use signal-based features (MACD + Z-scores) as parsimony variant
3. Replace SoftMin penalty with same formula — this is the key innovation, not futures-specific
4. Run smoke_test.sh to verify architecture adapts to N=25

---

## Concurrent Work: End-to-End Parametric Policies (arXiv:2607.00475)

Pollok & Robik (2026) independently confirm end-to-end E2E policy learning on 16 liquid CME futures:
- Differentiable Sharpe loss (same principle as DeePM)
- **Transformer > LSTM** at lower turnover; LSTM faster to train but overtrades
- After transaction costs, Transformer matches or exceeds equal-weight; LSTM underperforms
- Validates DeePM's architecture choice (attention > recurrence) and cost-aware training

---

## Relevance to Production Pipeline

| Hypothesis | Connection |
|-----------|------------|
| H249 (regime-conditional weights) | SoftMin EVaR objective directly targets the same problem (worst-window Sharpe) |
| H318 (meta-agent ETF rotation) | Macro Graph Prior models cross-ETF dependence structurally |
| H251 (HMM portfolio) | DeePM outperforms explicit HMM-based regime detection — implicit regime learning via graph |
| H273 (vol-targeted overlay) | EVaR robust objective generalizes H273's vol-targeting — same risk-aware logic |
| H370 (LambdaRankIC / deep ranking) | Same end-to-end philosophy; DeePM trains on Sharpe, LambdaRankIC on IC rank loss |
| H198 momentum family | Features (MACD, vol-normalized returns) directly transfer to H198's signal construction |

**Primary obstacle**: Requires PyTorch + PyG + GPU. Current backtesting pipeline is CPU-only numpy/pandas. DeePM is a Phase 4+ undertaking for live trading infrastructure, not a near-term backtest candidate. The **feature engineering table above** (MACD scales, Z-score windows) is immediately usable in any hypothesis.

---

## Related Papers

- arXiv:2601.05975 — DeePM (this paper)
- arXiv:2603.01820 — Same Oxford group; DL benchmark on 50 futures confirming rich temporal representations > linear models
- arXiv:2607.00475 — Pollok & Robik concurrent E2E parametric policy paper; independently confirms transformer advantage after costs
- arXiv:2507.15876 — CTA trend factor Bayesian short vs long horizon blend (complementary CTA research)
- arXiv:2112.08534 — Momentum Transformer (the baseline DeePM improves by ~50%)

---

## Cross-References

- [Deep RL for Trading](deep-rl-trading.md) — FinRL-X, LambdaRankIC, HMM+RL; DeePM is the systematic macro complement
- [Regime Detection](regime-detection.md) — SJM/HMM explicit detection vs DeePM's implicit graph-prior approach
- [Factor Models](factor-models.md) — MACD and Z-score features directly overlap with WQ101 alpha signal set
- [Multi-Agent LLM Trading](multi-agent-llm-trading.md) — Macroeconomic Graph Prior = structured alternative to LLM-based agent coordination

## H392 Candidate: Lightweight E2E Transformer for ETF Rotation

**Based on**: arXiv:2607.00475 (Pollok & Robik 2026) + DeePM architecture principles

**Design**: Replace H026's rank-1 momentum heuristic with a small Transformer trained end-to-end on differentiable Sharpe ratio loss.

**Minimal viable architecture for N=25 ETF universe**:
```python
import torch, torch.nn as nn

class ETFPolicyNet(nn.Module):
    def __init__(self, n_assets=25, n_features=8, d_model=32, n_heads=4, n_layers=2):
        super().__init__()
        self.embed = nn.Linear(n_features, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=64,
            dropout=0.1, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.out = nn.Linear(d_model, 1)

    def forward(self, x):  # x: (batch, n_assets, n_features)
        h = self.transformer(self.embed(x))  # (batch, n_assets, d_model)
        logits = self.out(h).squeeze(-1)     # (batch, n_assets)
        return torch.softmax(logits, dim=-1) # (batch, n_assets) — long-only weights

def sharpe_loss(returns):  # returns: (batch,) portfolio returns
    return -(returns.mean() / (returns.std() + 1e-6)) * torch.sqrt(torch.tensor(12.0))
```

**Features per asset** (8 features, monthly):
1. Vol-norm 1m return: R_{i,t}^{(1)} / σ_{i,t}
2. Vol-norm 3m return: R_{i,t}^{(3)} / σ_{i,t}
3. Vol-norm 6m return: R_{i,t}^{(6)} / σ_{i,t}
4. Vol-norm 12m return: R_{i,t}^{(12)} / σ_{i,t}
5. MACD (1m/3m): (EWM_1 - EWM_3) / σ
6. MACD (3m/12m): (EWM_3 - EWM_12) / σ
7. Z-score 6m rolling
8. Ex-ante vol (3m EWMA)

**IS/OOS split**: 2004–2017 IS (same as H026), 2018–2026 OOS
**Gate**: OOS Sharpe > 1.200 (H026 baseline) AND Max Drawdown < -3.60%
**Hypothesis number**: H392 (proposed, not yet run)
