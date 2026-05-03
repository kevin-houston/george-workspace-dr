# ML for Trading

*Machine learning approaches have been applied to Kevin's trading research in two forms: supervised classification models (Random Forest, XGBoost, GBM, ensemble — Rounds covering 20 large-caps, walk-forward validation) and foundation model benchmarking (Google TimesFM zero-shot). The headline finding is that Random Forest on XOM achieves Sharpe +1.744, making it the best individual ML result, but ML beats buy-and-hold on only 25-35% of stocks. TimesFM zero-shot ≈ buy-and-hold with no meaningful alpha.*

---

## Supervised ML: Walk-Forward Classification

**Setup**: 20 large-cap stocks | 252-day train / 21-day test windows | 5 models: RF, XGBoost, GBM, Logistic, Ensemble

### Results by Model

| Model | Avg Sharpe | Notes |
|-------|------------|-------|
| Ensemble (all models avg) | +0.527 | Best model-level result |
| Random Forest | +0.518 | Best single-model |
| XGBoost | +0.497 | |
| GBM | +0.448 | |
| Logistic Regression | +0.297 | Captures 60% of XGBoost's edge |

**Best individual result**: Random Forest on XOM, Sharpe +1.744, Win Rate 61.1%

### Stock-Level Performance

- ML beats buy-and-hold on only **25-35% of stocks** — 2020-2025 bull market is a high bar
- **Best sectors for ML**: Energy (XOM) and consumer staples (WMT, PG) — stable, mean-reverting
- **Worst**: Tech stocks — too noisy, NVDA/TSLA episodic moves break walk-forward models

### Top Features by Importance

1. vol_20d (20-day realized volatility)
2. close/SMA60 (price relative to 60-day moving average)
3. RSI_14 (14-day RSI)
4. close/SMA200 (price relative to 200-day moving average)
5. ret_20d (20-day return)

**Key insight**: Logistic regression captures 60% of XGBoost's edge → features matter more than model complexity. The feature engineering is the alpha; the model is secondary.

---

## TimesFM Zero-Shot Benchmark

**Setup**: Google TimesFM 1.0-200M (PyTorch) | XOM walk-forward | 168 windows | 2011-2026

### Results

| Approach | Sharpe |
|----------|--------|
| TimesFM (zero-shot) | 0.449 |
| Buy-and-Hold | 0.457 |
| Random Forest baseline | **1.744** |

**Verdict**: Zero-shot TimesFM ≈ buy-and-hold. No meaningful alpha.

**Why RF dominates**: RF uses feature-engineered classification (RSI, momentum, MACD); TimesFM does raw price regression. The features carry the signal, not the model architecture.

**Future potential**: TimesFM 2.5 (16k context) or fine-tuning on sector data may help; quantile filtering worth exploring. But zero-shot foundation models are not competitive with feature-engineered classical ML on this task.

Full report: /workspace/group/trading_eval/TIMESFM_REPORT.md

---

## Deep Learning Benchmark (ModernTCN Wins)

Source: arXiv:2603.16886 (March 2026) — 918 experiments across 9 architectures

| Architecture | Finding |
|-------------|---------|
| ModernTCN (CNN-based) | Wins on price-level forecasting |
| Transformers | Weaker than CNN for time-series |
| LSTMs | Weaker than CNN |
| **ALL models** | Directional accuracy ~50% |

**Critical insight**: No DL architecture reliably predicts direction. Directional accuracy hovers at ~50% across all 918 experiments.

**Lesson**: DL suits price-level forecasting (useful for position sizing, stop placement) but NOT for directional signals (entry/exit timing). Combine with classical signals for hybrid systems.

---

## Best Use Cases for ML in Kevin's System

Based on all research:

1. **Timing overlay on other strategies**: Use RF as an entry confirmation on pairs (enter only when RF says favorable; pairs provides direction)
2. **Position sizing**: DL price-level forecasting → size positions based on predicted vol, not directional signal
3. **Feature importance as research guide**: vol_20d and SMA ratios dominate → any strategy should incorporate these
4. **Sector selection**: RF works on energy/consumer staples → use ML signals for these sectors only

**Avoid**:
- ML as primary directional signal on tech stocks
- DL for binary entry/exit decisions
- Ensemble models without feature engineering (features > model choice)

---

## Research Assets

- `/workspace/group/trading_eval/harness.py` — 146 strategies
- `/workspace/group/trading_eval/rounds/` — rounds 1-19 JSON results
- TimesFM report: `/workspace/group/trading_eval/TIMESFM_REPORT.md`

---

## Related Topics

- [[llm-signal-research]] — LLM as an alternative "ML" for signal generation
- [[trading-strategies-leaderboard]] — ML results in context
- [[research-agenda]] — Future ML/DL experiments (SAE-FiRE for R31)

## Sources
- Master Trading Report (ML section): raw/master_trading_report_2026-04-05.md
- Memory Snapshot (TimesFM, ModernTCN benchmark): raw/MEMORY_snapshot_2026-04-05.md
