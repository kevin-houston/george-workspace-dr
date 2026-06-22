---
title: Time-Series Foundation Models for Trading
created: 2026-06-21
updated: 2026-06-21
category: algorithms
status: research — not yet backtested as standalone signal
---

# Time-Series Foundation Models for Trading

Foundation models pre-trained on massive time-series corpora — analogous to LLMs for text. Zero-shot or few-shot inference without task-specific training. The relevant question for this project: can they contribute Sharpe alpha beyond classical momentum/mean-reversion signals?

**Financial verdict (FinTSB 2026 benchmark):** ~15–25% improvement in directional accuracy over ARIMA; 50–70% directional accuracy in backtests on clean data; real-world Sharpe ~30–40% lower than backtest after transaction costs. Best use-case: **feature engineering, regime detection, tactical rebalancing** — not standalone directional trading signals.

---

## Primary Models

### Chronos-2 (Amazon, 2024–2025)

- **Paper:** arXiv:2403.07815 (original Chronos), arXiv:2510.15821 (Chronos-2 multivariate)
- **GitHub:** https://github.com/amazon-science/chronos-forecasting
- **Install:** `pip install chronos-forecasting`
- **License:** Apache 2.0

**Key specs:**
- Model family: Chronos-Bolt-tiny (9M) → Chronos-T5-large (710M)
- Chronos-Bolt variant: **250× faster inference** via distillation — same accuracy, practical for live use
- Zero-shot multivariate + covariate support (Chronos-2)
- **#1 on GIFT-Eval** among all pretrained models (June 2026)
- AutoGluon integration for ensemble forecasting

**Minimal inference code:**
```python
from chronos import Chronos2Pipeline
import pandas as pd
import torch

pipeline = Chronos2Pipeline.from_pretrained(
    "amazon/chronos-2-bolt-small",  # use -bolt for speed
    device_map="cuda",
    torch_dtype=torch.bfloat16,
)

# context_df: DataFrame with time column + target columns
# future_df: DataFrame with covariate columns for forecast horizon
pred_df = pipeline.predict_df(
    context_df,
    future_df=future_df,
    prediction_length=21,  # 21 trading days = 1 month
    quantile_levels=[0.1, 0.5, 0.9],
)
# pred_df has columns: mean, q10, q50, q90
```

**Trading integration pattern:**
- Monthly rebalance: use `prediction_length=21` on daily price series
- Covariate inputs: VIX, SPY daily return, yield curve slope (T10Y3M)
- Output: q50 (direction), q10/q90 spread (uncertainty → position sizing)
- Look-ahead guard: context window must end on last close **before** signal date

---

### TimesFM 2.5 (Google, 2025)

- **Paper:** arXiv:2310.10688 (TimesFM), updated to 2.5 mid-2025
- **GitHub:** https://github.com/google-research/timesfm
- **Install:** `pip install timesfm[torch]` (or `timesfm[jax]` for TPU)
- **License:** Apache 2.0

**Key specs:**
- **200M parameters**, trained on 100B+ time-series observations
- **16,384-token context window** (8× expansion from TimesFM 2.0)
- Optional **30M probabilistic quantile head** for risk-aware forecasts
- Available on BigQuery ML (GA) and Vertex AI Model Garden
- Benchmark: outperforms PatchTST, N-HiTS on M4/ETT/ECL datasets

**Minimal inference code:**
```python
import timesfm

model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
    "google/timesfm-2.5-200m-pytorch",
    backend="torch",
)

# input_series: list of 1D numpy arrays (one per stock)
point_forecast, quantile_forecast = model.forecast(
    horizon=12,          # 12 months ahead
    inputs=input_series,
)
# quantile_forecast shape: [n_series, horizon, n_quantiles]
```

**Strengths over Chronos:** Long context window makes it better for multi-year regime analysis. Quantile head gives calibrated confidence intervals useful for position sizing.

---

### Moirai (Salesforce, 2024)

- **Paper:** arXiv:2403.12773 (ICML 2024 Oral)
- **GitHub:** https://github.com/SalesforceAIResearch/uni2ts
- **Install:** `pip install uni2ts`
- **License:** Apache 2.0

**Key specs:**
- Architecture: **masked encoder** (vs Chronos decoder — better for multi-step)
- **Any-variate** design: handles variable number of channels natively
- Trained on **LOTSA** (Large-scale Open Time Series Archive): 27B+ observations
- Model sizes: Moirai-2.0-R-small → Moirai-1.1-R-large (900M params)
- **Moirai-MoE** variant (mixture-of-experts, late 2025) for lower inference cost

**Minimal inference code:**
```python
from uni2ts.model.moirai import MoiraiForecast, MoiraiModule

model = MoiraiForecast(
    module=MoiraiModule.from_pretrained("Salesforce/moirai-2.0-R-small"),
    prediction_length=20,
    context_length=200,  # 200 trading days context
    target_dim=5,        # 5 stocks simultaneously
    feat_dynamic_real_dim=2,  # covariates: VIX + yield
    num_samples=100,     # Monte Carlo samples for intervals
)

# dataset: GluonTS ListDataset format
forecast_it, ts_it = make_evaluation_predictions(model, dataset)
```

**Why Moirai for multi-stock:** The any-variate architecture handles the full stock universe in one forward pass rather than one model call per stock. Captures cross-stock correlations implicitly.

---

## Benchmark Models (Reference Only)

### PatchTST (2022)

- **Paper:** arXiv:2211.14730 (ICLR 2023)
- Patch-based transformer, channel-independent
- **21% MSE reduction** vs prior SOTA on long-term forecasting benchmarks
- Not a foundation model (trained per-dataset), but useful baseline
- `pip install PatchTST` (unofficial packages); official code at https://github.com/yuqinie98/PatchTST

---

## Emerging Models (2025–2026)

| Model | Paper | Highlight |
|-------|-------|-----------|
| **Timer-XL** | arXiv:2501.02505 (ICLR 2025) | Long-context autoregressive; github.com/thuml/Large-Time-Series-Model |
| **TS-RAG** | arXiv:2503.07649 (NeurIPS 2025) | Retrieval-augmented TS; **+6.51% over existing TSFMs** by retrieving similar historical patterns |
| **MOMENT** | arXiv:2402.03885 | `pip install momentfm`; MIT; strong on anomaly detection use case |
| **IBM FlowState** | June 2026 | **#2 GIFT-Eval** (behind Chronos-2); flow-based generative model |
| **Reverso** | arXiv:2602.17634 | **100× parameter reduction** vs full TSFMs; distillation-based |
| **FinCast** | arXiv:2508.19609 (Aug 2025) | Financial-specific training data; first TS foundation model tuned for equities |

**TS-RAG** is most promising for trading: retrieves similar past market conditions as context before forecasting — analogous to RAG for LLMs. Directly addresses the distribution shift problem in financial data.

---

## Financial Benchmark

**FinTSB** (arXiv:2502.18834, Feb 2026) is the first financial-domain TS benchmark:

- **50–70% directional accuracy** on clean historical data
- **15–25% improvement** over ARIMA/GARCH baselines
- **~30–40% Sharpe reduction** from backtest to live (transaction costs, slippage, distribution shift)
- Models trained on broad TS corpora underperform models fine-tuned on financial data
- **Best performers:** FinCast (financial fine-tuned) > Chronos-2 > TimesFM 2.5 > Moirai-large

Key insight: zero-shot TSFMs are better at **ranking** stocks than predicting absolute returns — cross-sectional momentum signal is a natural fit.

---

## Integration Patterns for This Project

### Pattern 1: TSFM as return feature for LightGBM

Use TSFM to generate 1-month forward return estimates → feed as input feature to existing crash-filter (H320) or factor models (H217).

```python
# Monthly signal generation — safe from look-ahead
def tsfm_return_feature(prices_df, as_of_date, model):
    """Returns TSFM-predicted next-month return for each stock."""
    context = prices_df[prices_df.index < as_of_date].tail(200)
    forecasts = model.predict(context, horizon=21)  # 21 trading days
    next_month_return = (forecasts['median'].iloc[-1] / context.iloc[-1]) - 1
    return next_month_return  # Series indexed by ticker
```

### Pattern 2: TSFM regime detector (H318 candidate)

Replace or augment the VIX/SPY-200MA binary gate with a continuous regime signal from TSFM volatility forecast.

```python
def tsfm_regime_signal(spy_prices, vix_series, model):
    """Continuous regime score from TSFM uncertainty spread."""
    q10, q90 = model.forecast_quantiles(spy_prices, horizon=21)
    uncertainty = (q90 - q10).mean()  # Avg forecast range
    # High uncertainty → reduce exposure
    return 1.0 - min(1.0, uncertainty / SPY_HIST_UNCERTAINTY_95TH)
```

### Pattern 3: Cross-sectional ranking for momentum augmentation

TSFMs are better at ranking than absolute prediction. Apply to H198 (6-1m momentum) universe as a second-pass filter.

---

## Architecture Decision Guide

| Use Case | Recommended Model | Reason |
|----------|-------------------|--------|
| Cloud-first / AWS integration | Chronos-2 Bolt | AutoGluon, SageMaker native; fastest inference |
| Multi-asset simultaneous | Moirai | Any-variate native; one pass for full universe |
| Risk management / intervals | TimesFM 2.5 | Calibrated quantile head |
| Low-memory / edge | Reverso | 100× parameter reduction |
| Financial domain first | FinCast | Tuned on equity data |
| Retrieve similar patterns | TS-RAG | Best for distribution shift environments |

**Practical recommendation for this project:** Start with **Chronos-2 Bolt** (fastest, best benchmarks, simplest install). Use as feature engineering input to LightGBM rather than standalone signal. Target: contribute to H318 (meta-agent ETF rotation) or augment H320 (crash filter).

---

## Hypothesis Queue

- **H318** (meta-agent ETF rotation selector) — TSFM return estimates as one input to the dynamic weight adjuster
- **H320+** — TSFM volatility forecast as additional feature in LightGBM crash filter (current features: 6 macro/technical; TSFM adds a forward-looking view)
- **Unnamed** — FinCast evaluation: does financial-domain fine-tuning produce cross-sectional alpha vs raw momentum? Gate: OOS Sharpe > H198 baseline 1.174 AND Corr(H198) < 0.8

---

## Cross-References

- [Multi-Agent LLM Trading](multi-agent-llm-trading.md) — LLMs for qualitative signal generation; complementary to TSFM quantitative signals
- [awesome-quant-ai](../tools/awesome-quant-ai.md) — lists PatchTST, Chronos, TimesFM, Moirai in the foundation model taxonomy
- [LightGBM Crash Filter H320](../../backtesting/daily/run_h320.py) — current crash filter; TSFM features could extend it
- [Factor Models & Cross-Sectional Alpha](factor-models.md) — TSFM cross-sectional ranking as alpha signal
- [Regime Detection](regime-detection.md) — TSFM uncertainty spread as continuous regime indicator
