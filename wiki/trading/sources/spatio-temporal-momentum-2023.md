---
created: 2026-08-03
updated: 2026-08-03
type: source_summary
authors: Wee Ling Tan, Stephen Roberts, Stefan Zohren (Oxford-Man Institute of Quantitative Finance)
published: Feb 2023 (arXiv), Journal of Financial Data Science 5(3):107-129, Summer 2023
source: arXiv:2302.10175
url: https://arxiv.org/abs/2302.10175
---

# Spatio-Temporal Momentum: Jointly Learning Time-Series and Cross-Sectional Strategies — Tan, Roberts & Zohren 2023

**Authors:** Wee Ling Tan, Stephen Roberts, Stefan Zohren (Oxford-Man Institute)
**Venue:** arXiv:2302.10175, published in *The Journal of Financial Data Science* 5(3):107-129 (Summer 2023)

This is the paper behind the "H180 spatio-temporal momentum NN" idea logged in CLAUDE.local.md as a queued next research direction alongside H181 (industry-adjusted reversal). Reading the full text confirms it is directly actionable, with a published results table, an open-source reference implementation from the same lab, and an explicit finding (simpler beats complex) that meaningfully de-risks a first attempt.

---

## Core Idea

Classical momentum comes in two flavors that are normally modeled separately:

- **Time-series momentum (TSMOM)** — trade an asset against its own trailing sign/return, independent of other assets (Moskowitz, Ooi, Pedersen 2012)
- **Cross-sectional momentum (CSMOM/XSMOM)** — rank assets against each other, long winners short losers (Jegadeesh & Titman 1993) — our production H198/H241/H411 family

**Spatio-temporal momentum (STMOM)** treats momentum features as a single tensor with both a temporal axis (each asset's own history) and a spatial/cross-sectional axis (all assets at time t), and trains one small neural network — as simple as a single fully-connected layer (SLP) — to output position sizes for the whole universe jointly, directly optimizing the **annualized Sharpe ratio** as the loss function rather than a regression/classification proxy.

```python
# Sharpe-ratio loss (Eq. 8-9 in the paper), the core training objective —
# not a classification/regression loss, so the network learns whatever
# signal shape maximizes risk-adjusted return, not price direction accuracy.
def sharpe_loss(returns):  # returns: (T,) tensor of daily position*asset returns for one instrument
    n = returns.shape[0]
    mean_term = returns.sum() * (252 ** 0.5)
    var_term = (n * (returns ** 2).sum() - returns.sum() ** 2)
    return -mean_term / var_term  # negative because optimizers minimize
```

Inputs are the same volatility-normalized return features used in classical Deep Momentum Networks (DMN, Lim, Zohren & Roberts 2019) — daily returns normalized by rolling volatility at k ∈ {1, 20, 63, 126, 252} trading days (daily/monthly/quarterly/semiannual/annual), plus MACD signals at short/long timescale pairs (8/24, 16/48, 32/96). Four architectures are compared for the spatio-temporal function: SLP (single linear layer + shrinkage penalty), MLP, LSTM, CNN.

---

## Key Result: Simplicity Wins, and by a Lot

The paper's headline finding directly contradicts the intuitive expectation that more model capacity should help:

> "we observe a deterioration in performance of the STMOM strategy with an increased level of model complexity" — SLP beats MLP, LSTM, and CNN on both datasets.

**Table 2 — US Equities, vol-scaled to 15% annualized target (out-of-sample, 1995-2022, no transaction costs):**

| Strategy | E[Return] | Vol | MaxDD | **Sharpe** | Sortino | Calmar |
|---|---|---|---|---|---|---|
| Long Only | 13.1% | 15.5% | -34.4% | 0.841 | 1.197 | 0.380 |
| TSMOM | 5.6% | 15.7% | -47.0% | 0.358 | 0.501 | 0.119 |
| MACD | 3.8% | 15.7% | -52.4% | 0.245 | 0.343 | 0.073 |
| CSMOM (decile L/S) | -10.1% | 15.4% | -96.4% | **-0.655** | -0.880 | -0.105 |
| DMN (reference, non-spatial) | 48.7% | 16.7% | -26.0% | 2.920 | 4.647 | 1.887 |
| **STMOM-SLP** | 42.3% | 16.2% | -30.1% | **2.609** | 4.161 | 1.428 |
| STMOM-MLP | 17.5% | 16.9% | -41.0% | 1.040 | 1.590 | 0.439 |
| STMOM-CNN | 3.5% | 20.0% | -66.5% | 0.192 | 0.314 | 0.079 |
| STMOM-LSTM | 17.8% | 18.2% | -54.4% | 1.015 | 1.422 | 0.405 |

Two things jump out for our pipeline:

1. **Raw classical CSMOM (decile long/short) is a *losing* strategy in this dataset** (Sharpe -0.655) — consistent with what we've independently found: naive cross-sectional long/short (H243, H271) underperforms long-only momentum (H198/H241) on similarly-sized universes. The paper's ML methods fix this by learning position *sizes*, not just rank direction.
2. **The simplest model (SLP, a single linear layer with a shrinkage/turnover penalty) is competitive with the much more expensive DMN** (2.609 vs 2.920 Sharpe) and clearly beats every deeper architecture (MLP 1.040, LSTM 1.015, CNN 0.192). The authors attribute this to STMOM's smaller effective training-sample count (t samples vs DMN's t×N samples) making complex architectures overfit.

**Equity index futures dataset (12 contracts, 2003-2020) shows an even larger STMOM edge**: SLP outperforms the DMN reference by "more than six times in risk-adjusted returns" after vol-scaling — the paper attributes this to futures being noisier/fewer in count, where the DMN's larger per-asset sample advantage matters less.

---

## Transaction Cost Sensitivity (Table 6, US Equities)

| Strategy | 0bp | 2bp | 5bp | 10bp |
|---|---|---|---|---|
| Long Only | 0.841 | 0.835 | 0.826 | 0.812 |
| TSMOM | 0.358 | 0.315 | 0.249 | 0.140 |
| DMN | 2.920 | 2.615 | 2.153 | 1.375 |
| DMN+turnover reg | 2.073 | 1.957 | 1.782 | 1.486 |
| **STMOM-SLP** | 2.609 | 2.243 | 1.691 | **0.762** |
| STMOM-SLP+turnover reg | 2.672 | — | — | higher than plain SLP at 10bp |

Without turnover regularization, SLP's edge nearly evaporates at realistic 10bp equity costs (2.609 → 0.762). **Turnover regularization is not optional** — it's the difference between a strategy that survives transaction costs and one that doesn't. Any implementation on our universe needs an explicit turnover penalty term in the loss, not just the base Sharpe loss shown above.

---

## Dataset Caveat — Not Directly Reproducible with Our Data Stack

- **US equities dataset is 46 stocks from the Financials sector only** (not S&P 500 broad-market), sourced from CRSP (Center for Research in Security Prices) — a **paid, institutional-only** data vendor, not available via yfinance/Alpaca/Polygon.
- Backtest period 1990-2022 (equities) / 2003-2020 (futures), expanding-window retrain every 5 years.
- Equity index futures dataset uses Pinnacle Data Corp CLC Database — also paid.
- **Implication:** the specific numbers above are not directly comparable to our H241 200-stock universe (broad S&P 500, yfinance-sourced) or H198 (30-stock mega-cap). A faithful replication would need either (a) our existing free-data universes with the STMOM architecture substituted for the DMN/rank-based approach we currently use, accepting the dataset won't match, or (b) sourcing a Financials-sector-specific universe as a closer analog.

---

## Reference Implementation — Not a Direct Fit, But a Useful Skeleton

No official code repo accompanies this specific paper, but the same lab (Zohren group, Oxford-Man Institute) released code for the closely related "Trading with the Momentum Transformer" paper (arXiv:2112.08534), which extends the same DMN/Sharpe-loss framework with attention:

- **Repo:** [kieranjwood/trading-momentum-transformer](https://github.com/kieranjwood/trading-momentum-transformer) — MIT license, 633 stars, 255 forks
- Implements DMN + LSTM + Transformer variants with the same Sharpe-ratio loss and changepoint-detection module (CPD improves Sharpe by ~1/3 over 1995-2020 per the companion paper)
- **Not a drop-in fit for our stack:** pipeline is hardcoded to 100 continuous futures contracts pulled from Nasdaq Data Link (Quandl), which requires a paid subscription for full history and would need substantial rework to run on an equal-weight stock universe instead of futures
- Minimally maintained (17 commits) — the same author's more recent [DeePM regime-robust portfolio](deepm-regime-portfolio.md) (already in our wiki, updated 2026-07-09) is the actively-maintained successor and a better starting skeleton if implementing this family in PyTorch

**Practical build path for our stack (no paid data, no futures):** replace CRSP/Quandl loaders with our existing `run_h241.py` `load_prices()`/`build_panel()` pipeline (yfinance, 200-stock S&P 500 universe, already cached), keep the SLP architecture (cheapest, best-performing per the paper) and the Sharpe-ratio loss with turnover regularization, and train/validate on the same IS 2013-2020 / OOS 2021-2026 split used across the H-series. This sidesteps the CRSP dependency entirely at the cost of not being a literal replication.

```python
# Sketch: turnover-regularized Sharpe loss (Eq. 14 pattern) — the missing
# piece needed to make raw sharpe_loss() above survive realistic tcosts,
# per the Table 6 finding that unregularized SLP collapses 2.609->0.762 at 10bp.
def sharpe_loss_with_turnover(returns, positions, tc_bp=5.0, turnover_lambda=0.1):
    base = sharpe_loss(returns)
    turnover = (positions[1:] - positions[:-1]).abs().mean()
    return base + turnover_lambda * turnover * (tc_bp / 1e4)
```

---

## Relevance to Our Pipeline

1. **Directly closes the H180 queue item** referenced in CLAUDE.local.md — this is the paper, not just a category description, so a concrete hypothesis can now be scoped: STMOM-SLP with turnover-regularized Sharpe loss on the H241 200-stock universe, IS/OOS split matched to our standard.
2. **The "simplicity wins" finding is a strong prior for scoping the first attempt cheaply** — start with a single linear layer, not an LSTM/Transformer, matching this wiki's repeated finding elsewhere (H337 quality factor, H278 vol-parity) that added model complexity underperforms simpler signals on our universe sizes.
3. **Turnover regularization is the load-bearing detail**, not the architecture — any implementation must budget for it explicitly or the strategy will look good pre-cost and collapse post-cost exactly as Table 6 shows.
4. **CRSP/Quandl paid-data dependency means this cannot be literally replicated** — plan for a same-mechanism, different-universe implementation on our existing free H241 data pipeline from the start, and document that divergence when the hypothesis is logged so a future reader doesn't expect the paper's exact Sharpe 2.6.

**Proposed next hypothesis (to stage in dream cycle scan or a future daily research session):** Sharpe-loss-trained single-linear-layer network jointly sized across the H241 200-stock universe (spatio-temporal features: multi-horizon vol-normalized returns + MACD), turnover-regularized, IS 2013-2020 / OOS 2021-2026, compared against H241-A momentum and H198 baselines. Gate: OOS Sharpe > 1.5 (200-stock family standard) with post-cost Sharpe reported at 5bp and 10bp explicitly (not just pre-cost) given this paper's demonstrated cost sensitivity.

---

## Cross-References

- [Momentum Strategies](../algorithms/momentum-strategies.md) — H198/H241/H411 production cross-sectional momentum family this would extend
- [Factor Momentum & Style Rotation](../algorithms/factor-momentum-style-rotation.md) — factor-momentum context, "next 2026" section
- [DeePM — Regime-Robust Deep Learning Portfolio](../algorithms/deepm-regime-portfolio.md) — actively-maintained successor codebase from the same lab
- [Deep RL for Trading](../algorithms/deep-rl-trading.md) — adjacent deep-learning-for-portfolios literature
- [Transaction Cost Modeling](../backtesting/transaction-costs.md) — turnover regularization context
- CLAUDE.local.md "Next research direction" note — H180 (spatio-temporal momentum NN) queue item this source resolves
