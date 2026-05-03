# R30: Multi-Quarter SUE Elastic Net PEAD
**Date:** 2026-04-03
**Hypothesis:** 12-quarter SUE history improves PEAD Sharpe via elastic net vs single-quarter signal
**Paper:** Kaczmarek & Zaremba (Finance Research Letters, 2025)

## Universe & Data
- **Tickers with data:** 22 / 30
- **Available tickers:** AAPL, MSFT, GOOGL, AMZN, META, NVDA, JPM, JNJ, XOM, WMT, BAC, PG, UNH, HD, CVX, LLY, MRK, PFE, KO, PEP, TMO, COST
- **Missing (API limit):** ABBV, MCD, ACN, ABT, DHR, NEE, LIN, HON
- **Total observations:** 2,210 earnings events
- **Clean observations (all 12 lags available):** 2,210
- **Date range:** 1999-04-15 to 2026-02-25

## Results

| Model | Sharpe | Win Rate | N Signals | CAGR | MaxDD |
|-------|--------|----------|-----------|------|-------|
| Elastic Net (12-Q SUE) | 0.493 | 58.7% | 2041 | 64.4% | -86.7% |
| Baseline (1-Q SUE > 3%) | 0.640 | 59.9% | 1228 | 47.1% | -93.7% |

**Sharpe improvement (EN vs Baseline):** -23.0%

## Key Findings

- Walk-forward elastic net was trained on all earnings data prior to each quarter, then predicted the next quarter's return direction.
- The model uses 12 lags of SUE (standardized unexpected earnings %) plus derived features: 4-quarter mean SUE, std SUE, and trend slope.
- Entry signal: long for 20 trading days starting the next trading day after the earnings report.
- No leverage applied; equal weight per signal.
- **Elastic Net Sharpe:** 0.493 vs **Baseline Sharpe:** 0.640

### Diagnostic: Why EN Sharpe is Lower

The elastic net predicted long (positive return) for 2,041 out of 2,072 total signals (~98.5%) — near-universal long bias. This indicates the model learned the general positive equity drift embedded in the training data rather than purely the earnings surprise signal. Key implications:

- **Per-trade info ratio:** Baseline 0.181 vs EN 0.139. EN is diluting signal quality by adding many marginal trades (76/yr vs 45/yr for baseline).
- **Annualized Sharpe by trade frequency:** When accounting for the higher EN trade count (more independent bets), the frequency-adjusted Sharpes are nearly equal (~1.21 vs ~1.22), suggesting both models capture similar information per unit of risk.
- **CAGR comparison:** EN CAGR 64.4% vs baseline 47.1% — EN wins on absolute returns by virtue of more trades and compounding, but with worse risk-adjusted returns per bet.
- **Baseline selectivity advantage:** The SUE > 3% filter selects only the strongest surprises, yielding 1.0% mean return vs 0.756% for EN, explaining the higher per-trade Sharpe.

## Comparison to Kaczmarek & Zaremba (2025)

The paper reports that using 12 quarters of SUE history in a regularized regression roughly **doubles the Sharpe ratio** vs single-quarter SUE PEAD, primarily because:
1. Older earnings surprises remain unpriced — markets underreact to sustained earnings momentum
2. Elastic net selects informative lags and discards noise via L1 regularization
3. The effect is particularly strong for large-cap stocks (consistent with our universe)

Our backtest shows a Sharpe improvement of -23.0% on a raw basis. However, when accounting for EN's higher trade frequency (~76 vs ~45 trades/year), both models yield nearly identical frequency-adjusted Sharpes (~1.21). The paper's claimed Sharpe doubling is likely not replicated in this run.

**Caveats and likely sources of divergence from paper:**
- Only 22 tickers with both earnings and price data (vs 30 target; API daily limit hit at 23 fetches)
- Missing tickers: ABBV, MCD, ACN, ABT, DHR, NEE, LIN, HON
- `surprisePercentage` (raw %) used as SUE proxy instead of true analyst-consensus-normalized SUE — this affects signal quality
- Paper likely used long-short strategy (EN positive → long, EN negative → short), not long-only; this would double the effective Sharpe
- Paper may use cross-sectional normalization across stocks each quarter rather than time-series per stock
- Walk-forward minimum training set: 8 quarters
- 25 req/day API limit prevents full universe replication without premium plan

## Recommendation

**Do not add yet. Revisit with improvements.**

- The baseline SUE > 3% signal (Sharpe 0.640) remains the stronger long-only PEAD signal
- The EN adds more trades and higher CAGR (64.4%) but with lower per-bet quality
- If implementing as long-short (short when EN predicts negative), Sharpe could materially improve — this is the most likely source of the paper's doubling claim
- Next steps to validate: (1) obtain premium Alpha Vantage for full 30-ticker universe, (2) implement true analyst-consensus SUE normalization, (3) test long-short version, (4) cross-sectional signal construction (rank within quarter rather than absolute level)

The framework and walk-forward infrastructure is validated and ready for those extensions.
