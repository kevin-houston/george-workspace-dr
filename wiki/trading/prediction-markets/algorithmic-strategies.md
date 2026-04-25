---
updated: 2026-04-25
---

# Algorithmic Strategies for Prediction Markets

## Strategy overview

| Strategy | Difficulty | Annualized edge | Platforms | Notes |
|----------|-----------|-----------------|-----------|-------|
| Cross-market arbitrage | Hard | 0.5–2% | Kalshi + Polymarket | Window collapsed to 2.7s avg; requires automation |
| Cross-derivative arbitrage | Hard | 1–3% | Kalshi + CME | Options pricing expertise required |
| **Event modeling / nowcasting** | Medium | **3–8%** | Kalshi | **Best risk-adjusted opportunity** |
| NLP / sentiment | Medium | 2–5% | Polymarket | LLM APIs commoditized; fine-tuning differentiates |
| Market microstructure | Hard | 0.2–1% | Kalshi | Micro-edges eaten by fees |

---

## 1. Cross-market arbitrage (Kalshi ↔ Polymarket)

Buy YES on one platform, sell NO on the other when they disagree.

- Average spread historically: ~8% probability points
- $40M in realized profits extracted across platforms in 12 months (2025 IMDEA study)
- Opportunity window: **12.3 seconds (2024) → 2.7 seconds (2026)** — now requires sub-second automated execution
- Friction: Kalshi per-contract fee + Polymarket 2% taker fee + latency

**Realistic verdict**: Edge exists but increasingly institutional. Fast algo execution required.

---

## 2. Cross-derivative arbitrage (prediction markets vs. CME/options)

Exploit mispricing between Kalshi contracts and CME Fed funds futures or equity options.

**Example**: CME implies 68% rate cut probability; Kalshi prices at 72%. Sell Kalshi, delta-hedge via options.

- Historical edge (2015–2025): ~12% annualized on simple Kalshi/Eurodollar arb
- Viable spread threshold: **>2%** (rare in current markets post-institutional adoption)
- Requires: options pricing model, dual-market data feeds, cross-asset execution

---

## 3. Event modeling / nowcasting ⭐ Priority strategy

Build probabilistic forecasts for economic events (CPI, Fed decisions, unemployment). Trade when your estimate diverges from market price.

### Data pipeline

```python
from fredapi import Fred
import requests

# Official: FRED, BLS, Atlanta Fed GDPNow
fred = Fred(api_key='...')
cpi = fred.get_series('CPIAUCSL')
fed_funds = fred.get_series('DFF')

# Atlanta Fed GDPNow (free daily nowcast)
gdpnow = requests.get('https://www.atlantafed.org/...').json()

# ADP Employment (free, monthly, 2-3 days before BLS)
# Combine with jobless claims, PMI for composite nowcast
```

### Modeling approaches

**ARIMA/VAR (simple baseline)**:
```python
from statsmodels.tsa.arima.model import ARIMA
from scipy.stats import norm

model = ARIMA(cpi_history, order=(1,1,1)).fit()
forecast = model.get_forecast(steps=1)
prob_above_3 = 1 - norm.cdf(3.0, loc=forecast.predicted_mean[0],
                              scale=forecast.se_mean[0])
```

**Bayesian ensemble (better calibration)**:
```python
import pymc as pm

with pm.Model() as model:
    true_cpi = pm.Normal('true_cpi', mu=3.2, sigma=0.5)  # Prior: economist consensus
    # Update with market-implied probability, nowcast data, etc.
    trace = pm.sample(10000)
    prob = (trace.posterior['true_cpi'] > 3.0).mean().item()
```

### Peak edge window

Models outperform market consensus in the **3–6 hours before official data release** — when your nowcast has diverged from stale market prices but market hasn't repriced yet.

### Realistic performance

- Nowcast models reduce forecast error 20–40% vs. simple historical averages
- Win rate boost: 2–5% over market consensus
- After fees: 3–8% annualized edge for well-calibrated models

---

## 4. NLP / Sentiment signals

Extract signals from Fed communications, news flow, social media.

**Models**:
- FinBERT: pre-trained BERT on financial text; strong on "hawkish/dovish" classification
- GPT-4: few-shot prompting, comparable to FinBERT with domain prompts
- OpenAI API is available (`$OPENAI_API_KEY` in env) — use for inference

**Win rate boost**: +2–4% when sentiment strongly aligned with trade direction
**Latency**: LLM inference 500ms–2s; faster signal extraction wins

**Data sources with keys available**:
- `$NEWSAPI_KEY` — real-time news feed
- EDGAR + `$EDGAR_KEY` — SEC filings, earnings releases
- FRED speeches/minutes — free

---

## 5. Kelly Criterion for position sizing

**Formula** (binary outcomes):
```
f* = (p × M - (1 - p)) / (M - 1)
```

Where:
- `p` = your estimated probability
- `M` = payout odds = `1 / contract_price`

**Example**: Market at $0.65 (65%), your estimate 70%:
```
M = 1 / 0.65 ≈ 1.538
f* = (0.70 × 1.538 - 0.30) / (1.538 - 1) = 0.077 / 0.538 ≈ 14.3%
```

**Practical rule**: Use **quarter-Kelly to half-Kelly** (0.25–0.5 × f*) to account for model uncertainty. Most prediction market losses come from incorrect position sizing, not bad trade direction.

---

## Recommended starting strategy

**Event nowcasting on Kalshi economic contracts**:
1. Pull FRED data (CPI components, unemployment) via `fredapi`
2. Build ARIMA baseline model; layer in Atlanta Fed GDPNow and ADP data
3. Add FinBERT sentiment on Fed minutes/speeches (OpenAI API for inference)
4. When model diverges >3% from Kalshi price: trade at quarter-Kelly sizing
5. Track: win rate, calibration error (Brier score), after-fee P&L

This avoids the speed requirement of arbitrage while giving a durable, data-driven edge.

---

## Open-source frameworks

| Tool | GitHub | Notes |
|------|--------|-------|
| OctoBot Prediction Market | Drakkar-Software/OctoBot-Prediction-Market | Copy trading + arbitrage (beta); good for learning |
| prediction-market-arbitrage-bot | realfishsam/prediction-market-arbitrage-bot | Educational arb bot; not production-optimized |
| py-clob-client | Polymarket/py-clob-client | Official Polymarket Python client |

**Recommendation**: Build custom on top of Kalshi REST API. Open-source tools are educational but lack production reliability.
