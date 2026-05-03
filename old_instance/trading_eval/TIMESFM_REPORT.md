# TimesFM vs Random Forest Baseline — XOM Benchmark Report

**Date:** 2026-04-03
**Model:** Google TimesFM 1.0-200M (PyTorch backend)
**Baseline:** Random Forest walk-forward, XOM, Sharpe +1.744

---

## Installation Outcome

**Status: Success (with minor issues)**

- `pip install timesfm` installed successfully with warnings about PATH
- Required `pip install torch --index-url https://download.pytorch.org/whl/cpu` separately (timesfm does not auto-install torch)
- The HuggingFace repo `google/timesfm-1.0-200m` contains only JAX checkpoints; the PyTorch weights live in the separate repo `google/timesfm-1.0-200m-pytorch` — the install guide does not make this obvious
- Model checkpoint (`torch_model.ckpt`): **777 MB**, downloaded in ~60s
- `context_len` in `TimesFmHparams` must be a multiple of the model's internal patch size (32); `252` caused a shape error, so context was adjusted to `256` (nearest valid value)
- Total setup time (pip install + download): ~3 min on first run; subsequent runs load from cache in ~5.5s

---

## Walk-Forward Backtest Results

| Metric | TimesFM | RF Baseline | Buy-and-Hold |
|---|---|---|---|
| **Sharpe Ratio** | **0.449** | **1.744** | 0.457 |
| Annualized Return | 9.0% | — | — |
| Annualized Vol | 19.9% | — | — |
| Signal Rate | 45.2% | — | — |
| Win Rate (long windows) | 55.3% | — | — |
| Windows Tested | 168 | ~168 | — |

**Difference vs RF baseline: -1.295 Sharpe points**

### Parameters

- Context length: 256 trading days (≈1 year, adjusted from 252 for patch-size compatibility)
- Test window: 21 days (matches ML harness)
- Forecast horizon: 5 days
- Signal threshold: 0.5% predicted gain → go long; otherwise cash
- Data: XOM adjusted close, 2011-03-01 to 2026-03-26 (3,791 days)

---

## Key Finding

TimesFM (Sharpe **0.449**) is statistically indistinguishable from buy-and-hold XOM (Sharpe **0.457**). The model's 5-day-ahead log-price forecasts carry no exploitable directional edge at the 0.5% threshold tested. The signal fires 45% of the time and wins on those windows 55% of the time — barely above coin-flip — while the long-only exposure closely replicates the index.

The RF baseline at **1.744** benefits from a full feature engineering pipeline (RSI, momentum, volume, MACD, market regime features) and a classification framing (up/down) rather than raw price-level regression. TimesFM is a zero-shot time-series forecaster not trained on stock price discrimination — it forecasts levels, not directional probability.

---

## Runtime and Memory

| Stage | Time |
|---|---|
| Model load (from cache) | 5.5s |
| 168 inference calls (1 per window) | 190s (~1.1s/window) |
| Total backtest | ~3.5 min |

- Peak RAM during inference: ~2.5–3 GB (model weights ~777 MB + runtime overhead)
- CPU: 4 cores (Intel i5-4278U @ 2.60GHz); inference ran single-threaded
- 7.6 GB total RAM available; no OOM issues

---

## Issues Encountered

1. **Wrong HF repo**: `google/timesfm-1.0-200m` has only JAX weights; PyTorch requires `google/timesfm-1.0-200m-pytorch`. TimesFM's code silently fetches from the wrong repo first, then errors at checkpoint load.
2. **context_len must be multiple of 32**: The model uses patch_len=32 internally. Feeding 252-point context with `context_len=252` raises a shape error. Must use 256 (or another multiple of 32).
3. **No GPU**: CPU inference is ~1.1s/window, acceptable for a 168-window backtest but would be slow at scale.
4. **No auth token**: HuggingFace rate-limit warnings; download still succeeded but could fail under heavy load.

---

## Recommendation

**Not recommended for inclusion in the harness in its current form.**

TimesFM produces no meaningful alpha over buy-and-hold on XOM (Sharpe 0.449 vs 0.457 B&H). The gap vs the RF baseline (-1.295) is large enough to be disqualifying for this use case.

Potential follow-up experiments that might improve results:
- **Use quantile forecasts**: TimesFM outputs prediction intervals; an uncertainty-adjusted sizing scheme (e.g., only trade when the lower quantile also predicts a gain) might filter noise
- **Longer forecast horizon**: The 5-day horizon may be too noisy; testing 21-day horizon (matching the rebalance window) could improve signal stability
- **Fine-tuning**: TimesFM supports fine-tuning on domain-specific data; a fine-tuned version on energy sector price series might outperform zero-shot
- **TimesFM 2.0 (500M)**: The newer `google/timesfm-2.0-500m-pytorch` model may have better zero-shot financial forecasting capability
- **Multi-asset ensemble**: Combine TimesFM forecasts across correlated tickers (e.g., XOM + CVX + COP) as cross-sectional signals

For now, the Random Forest baseline at +1.744 Sharpe remains the benchmark to beat.
