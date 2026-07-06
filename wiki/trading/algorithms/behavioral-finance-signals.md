---
added: 2026-06-14
updated: 2026-07-06
category: algorithms / behavioral
---

# Behavioral Finance Signals in Systematic Trading

Anomalies arising from investor psychology — anchoring, disposition effect, seasonal
preference — that generate predictable cross-sectional return patterns.

---

## 1. 52-Week High Anchoring (George & Hwang 2004)

**Source**: George, T. J. and Hwang, C.-Y. (2004). "The 52-Week High and Momentum
Investing." *Journal of Finance*, 59(5), 2145–2176.

### Mechanism
Investors use the 52-week high as a **reference anchor** when evaluating a stock's
fair value. When fundamentals would warrant a price beyond the anchor, investors
resist bidding beyond it, creating temporary underpricing near the high. When news
eventually forces a breakout, the release of the anchored constraint generates
continuation.

### Signal
```
R52 = P_t / max(P_{t−252}, ..., P_t)
```
- R52 ∈ (0, 1] — how close the current price is to the 52-week high
- Long stocks with **highest R52** (close to or at 52-week high)

### Key findings (original paper, 1963–2001)
- R52 explains more of the momentum profit than the prior 6m or 12m raw return
- Significance holds after controlling for Jegadeesh-Titman momentum
- Average monthly excess return: +0.65%/month (NYSE/AMEX/NASDAQ)
- Not explained by earnings seasonality or risk factors

### 2025 update: 52WH subsumes momentum in retail-heavy stocks

A 2024/2025 paper (extended sample through 2023) finds that **price momentum does NOT
significantly predict returns after controlling for 52-week high nearness** in stocks
with high retail ownership. Key findings:

- In mega-cap and retail-dominated stocks: 52WH factor fully absorbs momentum alpha
- In small/mid-cap institutional-dominant stocks: both 52WH and 12-1m momentum
  add independent alpha
- Practical implication: for S&P 500 / NASDAQ-100 universes, 52WH is the **better
  predictor** than raw prior-return momentum; momentum is a noisy proxy for anchoring

**Implementation**: Yan1015/Optimize-momentum-strategy-with-52-week-high (GitHub)
shows how to blend R52 proximity with price momentum for NASDAQ-100:
```python
import yfinance as yf
import pandas as pd

def r52_proximity(df_close, lookback=252):
    """R52 = current price / 52-week high. Higher = closer to high."""
    rolling_max = df_close.rolling(window=lookback).max()
    return df_close / rolling_max

# Usage:
# close = pd.DataFrame of daily closes for universe
# r52 = r52_proximity(close)  # shape: (T, N)
# monthly_r52 = r52.resample('ME').last()
# rank and long top decile by R52 each month
```

### H291 backtest result
- IS (2008–2017): Sharpe=1.031, CAGR=12.8%
- **OOS (2018–2025): Sharpe=0.764, CAGR=11.6%, MaxDD=-14.4%** — NOT CONFIRMED
- Root cause: 50-stock large-cap universe in 2018–2025 bull market → most stocks
  near 52-week highs simultaneously → collapsed cross-sectional dispersion
- See H336 NOT CONFIRMED (same finding in NASDAQ large-cap universe)

### When the signal is strongest
- Bear/recovery markets with high dispersion across stocks
- Small and mid-cap universes (more cross-sectional variation)
- When the market itself is below its own 52-week high (Li & Yu 2012 market-level version)
- **Combined with retail ownership filter** (2025 update): pure 52WH in retail-heavy stocks

---

## 2. Return Seasonality — Same Calendar Month (Heston & Sadka 2008)

**Source**: Heston, S. L. and Sadka, R. (2008). "Seasonality in the Cross-Section
of Stock Returns." *Journal of Financial Economics*, 87(2), 418–445.

### Mechanism
Stocks display persistent seasonality in returns tied to the calendar month:
- **Earnings seasonality**: firms in cyclical industries have structurally higher
  earnings in certain quarters every year
- **Tax-loss harvesting bounce**: stocks sold in December for tax purposes tend
  to rebound in January every year
- **Institutional window dressing**: fund managers buy winners at quarter-end
  predictably, creating calendar-driven demand
- **Analyst coverage cycles**: upgrades/downgrades cluster by fiscal calendar

### Signal
```
R_seasonal(i, month M, year Y) = return of stock i in month M of year Y−1
```
Long stocks with highest prior-year same-month return in the current month.

### Key findings (paper)
- 0.40%/month alpha at 1-year lag, significant at 1% after FF-3 adjustment
- Persists for up to **20 annual lags** (pattern decays slowly)
- Holds in international markets (Germany, Japan, France, UK)
- Keloharju et al. (2016): explains ~30% of annual stock return variation

### H292 backtest result
- IS (2008–2017): Sharpe=0.688, CAGR=11.6%
- **OOS (2018–2025): Sharpe=0.970, CAGR=18.2%, MaxDD=-19.1%** — CONFIRMED (survivorship bias caveat)
- WF ratio=1.411 (OOS > IS — suspicious; survivorship bias likely inflating both)
- Corr(SPY) OOS = 0.838 — moderate-high market correlation

### Monthly breakdown (OOS 2018–2025, 50-stock large-cap universe)

| Month | Mean Return | Win Rate | Assessment |
|-------|-------------|----------|------------|
| Jan   | +2.69%      | 89%      | Strong — tax bounce |
| Feb   | −0.64%      | 44%      | Weak |
| Mar   | −1.20%      | 44%      | Weak |
| Apr   | +2.37%      | 67%      | Moderate |
| May   | +1.09%      | 67%      | Moderate |
| Jun   | +2.70%      | 62%      | Good |
| Jul   | **+5.10%**  | **100%** | Strongest — pre-earnings |
| Aug   | +1.95%      | 62%      | Moderate |
| Sep   | −1.54%      | 50%      | Weak — September effect |
| Oct   | +0.08%      | 38%      | Weak |
| Nov   | **+5.13%**  | **88%**  | Strongest — pre-holiday rally |
| Dec   | +1.21%      | 62%      | Moderate |

July and November are the standout months — consistent with Q2 earnings preview
positioning (July) and pre-holiday consumer/retail positioning (November).

### Caveats and 2026 status
1. Survivorship bias: fixed 50-stock universe from 2026 inflates all results
2. WF > 1 (OOS > IS) suggests OOS period happened to be favorable, not skill
3. Only 8-9 observations per calendar month in OOS — small sample
4. **No new arXiv papers 2025–2026 updating Heston-Sadka** — seasonal anomaly may be
   decaying as crowding increases; flag for re-evaluation if H292 is ever promoted to production

### Practical use
The **July and November seasonal signals** are actionable as **tactical overlays**:
- In July and November, increase equity weight or add to existing positions in
  stocks that did well in the same month last year
- Do NOT use as a standalone monthly rotation — the weak months erode annual Sharpe

---

## 3. Disposition Effect and Capital Gains Overhang (CGO)

**Source**: Frazzini (2006). "The Disposition Effect and Underreaction to News."
*Journal of Finance*, 61(4), 2017–2046. Also: Grinblatt & Han (2005), SSRN.

### Mechanism
The **disposition effect** (Shefrin & Statman 1985): investors tend to sell winners
too early and hold losers too long. This creates:
- Prolonged underreaction to good news for stocks trading below purchase price
- Prolonged underreaction to bad news for stocks trading above purchase price
- Both cases create **momentum**: positive or negative news is incorporated slowly

### Signal: Capital Gains Overhang (CGO)
CGO = proxy for the aggregate unrealized gain/loss of investors currently holding the stock.

```python
def compute_cgo(close, volume, lookback=260):
    """
    CGO proxy using volume-weighted reference price.
    Negative CGO → investors are underwater → disposition creates
    underreaction to good news → stronger positive momentum.
    """
    # Volume-weighted average "purchase price" over lookback days
    vwap = (close * volume).rolling(lookback).sum() / volume.rolling(lookback).sum()
    cgo = (close - vwap) / close
    return cgo
```

- Stocks with **negative CGO** (trading below volume-weighted avg cost) → disposition
  creates underreaction to positive news → stronger momentum going forward
- Stocks with **positive CGO** (trading above avg cost) → winners being sold → dampens upside
- Use CGO as a **momentum modifier**: within momentum portfolios, tilt toward negative CGO

### GitHub reference
**js-park/Disposition-effect-from-Aggregate-trading-data** — replication code for
CGO calculation from CRSP volume/price data; also computes cross-sectional CGO regressions.

### 2025 update: corporate transparency and CGO strength
A 2025 paper (cross-listed stocks study) finds that **corporate transparency reduces the
disposition effect by ~35%**. Higher analyst coverage, more frequent disclosure, and lower
information asymmetry attenuate CGO predictive power. Implications:

- CGO strongest in: small-caps with low analyst coverage, opaque earnings (irregular filers)
- CGO weakest in: mega-caps, high-coverage stocks, post-Reg FD environment
- In S&P 500 universe: CGO effect is significantly weaker than in Frazzini's original study

### Interaction with H174 PEAD
CGO is relevant to PEAD: stocks reporting earnings while sitting at deeply negative CGO
(below avg cost) may generate stronger post-announcement drift because:
1. Disposition prevents selling despite good news
2. Under-reaction is deeper → announcement jump is larger

**H344 (Order Block timing for H174 PEAD entries)** indirectly captures some CGO effect —
OB zones often coincide with prior high-volume accumulation zones (high-CGO from prior buyers).

---

## 4. Lottery Stock Premium — MAX Factor

**Source**: Kumar (2009); Bali, Cakici, & Whitelaw (2011) "Maxing Out: Stocks as Lotteries
and the Cross-Section of Expected Returns." *Journal of Financial Economics*, 99(2), 427–446.

### Mechanism
Retail investors overweight **lottery-like stocks** (high MAX — maximum daily return
in the prior month, low price, high idiosyncratic volatility). This causes:
- Overvaluation of lottery stocks → future underperformance
- Avoidance of boring/stable stocks → their underpricing → future outperformance

### Signal: MAX factor
```python
def compute_max(daily_returns, lookback=21):
    """MAX = max daily return over prior month. Higher MAX = more lottery-like."""
    return daily_returns.rolling(lookback).max()
```
- Short high-MAX stocks (overvalued lottery plays)
- Long low-MAX stocks (boring, stable, under-loved)

### Unconditional finding (Bali et al. 2011)
Long-short MAX factor: −0.55%/month alpha (short leg drives returns)
Long-only anti-MAX (low MAX stocks): modest positive, absorbs value premium

### 2025 update: MAX × Momentum interaction — high alpha in the intersection

A 2025 Tandfonline paper (extended 1963–2023 sample) identifies an unexpected alpha pocket:
**high-MAX stocks within high-momentum portfolios generate +2.5%/month** — substantially
above both the unconditional MAX effect and the unconditional momentum effect.

**Mechanism**: High-MAX stocks are volatile, lottery-like, and attract retail attention.
When these same stocks are in the top momentum decile, they experience:
1. Momentum continuation amplified by retail herding and attention-driven buying
2. Recency bias: recent extreme up-day is salient → overweight by retail → more buying
3. Short-seller resistance: high volatility makes shorting expensive → longs persist longer

**Practical implication**: The traditional "avoid high MAX in momentum" rule is WRONG in
aggregate — it depends on the momentum position:

| Position | Expected Return | Mechanism |
|----------|----------------|-----------|
| High MAX, High Momentum | +2.5%/month | Retail amplification of trend |
| High MAX, Low Momentum | −1.0%/month | Lottery overpricing reverts |
| Low MAX, High Momentum | +0.9%/month | Classic momentum |
| Low MAX, Low Momentum | ~0% | No signal |

**Proposal (H373, not yet staged)**: Within the H198 30-stock momentum universe, add a
MAX-score tilt to increase weight on top-momentum stocks with high MAX. Hypothesis:
MAX selects the stocks where retail herding is amplifying the momentum signal.

### Practical screening
```python
def momentum_max_screen(monthly_close, daily_returns, mom_pct=0.8, max_pct=0.6):
    """
    Selects stocks that are in top 20% momentum AND top 40% MAX.
    These are the 2.5%/month alpha pocket.
    """
    mom_12 = monthly_close.pct_change(12)
    max_factor = daily_returns.resample('ME').apply(lambda x: x.max())
    
    mom_rank = mom_12.rank(pct=True, axis=1)
    max_rank = max_factor.rank(pct=True, axis=1)
    
    # Both must be above threshold
    signal = (mom_rank >= mom_pct) & (max_rank >= max_pct)
    return signal
```

---

## 5. LLM Sentiment as Behavioral Signal (2025–2026)

### Why behavioral finance now intersects with LLMs

Traditional behavioral signals (disposition effect, anchoring) are priced from
trade-volume/price data. LLMs open a parallel lane: **directly measuring investor
sentiment from text** (earnings call tone, news, SEC filings) at scale.

The key insight from 2025 research: LLM sentiment alphas exhibit the same behavioral
patterns — momentum, underreaction, disposition — that price-based behavioral signals
detect. They are complementary signals from different data streams.

### FinGPT — Open-Source Financial LLM Backbone

**GitHub**: AI4Finance-Foundation/FinGPT (10,000+ stars)
**Install**: `pip install fingpt`

FinGPT is the primary open-source framework for sentiment-based behavioral signals:
- Fine-tuned Llama / Mistral on financial text (news, earnings calls, SEC filings)
- Sentiment classification: strongly positive / positive / neutral / negative / strongly negative
- Supports streaming inference via HuggingFace Transformers
- Produces per-document sentiment scores that can be aggregated to monthly signals

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# FinGPT sentiment (Llama-based, ~7B params — needs GPU or quantized)
MODEL = "FinGPT/fingpt-sentiment_llama2-13b_lora"

tokenizer = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForSequenceClassification.from_pretrained(MODEL)

def sentiment_score(text: str) -> float:
    """Returns scalar sentiment in [-1, 1]. Positive = bullish."""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1).squeeze()
    # Map [SPos, Pos, Neutral, Neg, SNeg] → scalar
    weights = torch.tensor([1.0, 0.5, 0.0, -0.5, -1.0])
    return (probs * weights).sum().item()
```

For lighter-weight inference: use FinBERT (ProsusAI/finbert) which is already
production-validated in H163/H174 (PEAD strategy, OOS WR=81.8%).

### Key 2025 papers

**arXiv:2508.04975** — Transformer + LLM combined alphas:
- Combines FinBERT sentiment on news + LLM-generated fundamental summaries
- Cross-sectional momentum alpha persists after LLM sentiment control → additive signals
- 12-month LLM alpha: +4.2%/year after transaction costs

**arXiv:2510.10526** — RL + LLM dynamic sentiment weighting:
- RL agent learns when to weight LLM sentiment vs. price-based momentum
- Regime-adaptive: weights LLM sentiment more in high-news months (earnings season)
- OOS Sharpe improvement: +0.3–0.5 vs. static equal-weighting

**arXiv:2604.18373** (Stanford/Oxford, 2026) — **AI agents exhibit the disposition effect**:
- Tested GPT-4o, Claude 3.5, Gemini 1.5 on simulated trading decisions
- All exhibit statistically significant disposition effect: sell winners, hold losers
- LLM-based trading strategies that use model outputs directly inherit this bias
- **Critical implication for H274 multi-agent PEAD**: if debate agents inherit
  disposition bias, the 3-agent system may systematically underweight positive news
  for stocks with recent gains (positive CGO). Mitigation: frame prompts with CGO context.

### Lookahead bias in LLM signals — LAP metric (arXiv:2512.23847)

**This is the most operationally important 2025 paper for LLM-based strategies**.

LLMs trained on historical financial data may "know" future stock returns embedded in
their training set (if training data includes post-event articles). The **LAP (Lookahead
Accuracy Penalty) metric** detects this contamination:

```
LAP = AUC(model on eval set) − AUC(time-restricted baseline)
```
If LAP > 0.05, the model likely has lookahead contamination.

**Practical implications**:
1. All LLM-based sentiment strategies (FinGPT, FinBERT, GPT-4o) should be tested
   with a strict cutoff: training data must not include post-announcement articles
2. H163/H174 (FinBERT on EDGAR 8-Ks) is likely safe — FinBERT was trained on
   news headlines, not post-earnings analysis articles; but verify
3. Any strategy using GPT-4o on earnings calls or news is at high lookahead risk
   unless the model was not trained past the eval period start date

---

## 6. Multi-Factor ML with Behavioral Signals (2025)

**Source**: arXiv:2507.07107 — "Behavioral and Technical Alpha Extraction via ML Ensemble"

### Overview

A 2025 paper constructs a **213-factor set** combining:
- WorldQuant Alpha101 (101 price/volume features)
- 50 behavioral factors: MAX, CGO, 52WH proximity, same-month seasonality, volume
  surprise, analyst revision momentum, options implied sentiment
- 62 technical features: RSI, MACD, Bollinger bands, ATR variants

An **ML ensemble** (LightGBM + XGBoost + Ridge) trained on this feature set outperforms:
- Equal-weight factor combination: +1.8% CAGR / +0.4 Sharpe
- Any single behavioral factor alone: +2.3-3.1% CAGR

Key findings relevant to our stack:
1. **MAX factor is top-5 most important** across all factor groups by SHAP value
2. **52WH proximity is top-10** but importance drops post-2020 (mega-cap dominance)
3. CGO is top-15 but collinear with price momentum in bull markets
4. **Behavioral factors collectively add more than technical factors** (Alpha101 alone
   is the weakest standalone cluster; behavioral cluster is strongest)
5. Same-calendar-month seasonality is top-20 by SHAP

### Implications for H198 / H343 variants

This finding validates the direction of H337 (quality-momentum) and H336 (52WH) —
both failed because of poor feature construction on large-cap universe, not because
behavioral factors are uninformative. The fix is:
- Broader universe (200+ stocks, not 30)
- Proper ML combination (not simple tiebreaker ranking)
- Include MAX as a primary feature, not just as a screen

**Proposal (H374, not yet staged)**: LightGBM on 50-factor behavioral set across 200-stock
S&P 500 universe. Start with Max(1m), CGO(60d), R52, SeasonalRet(1y) as core features;
validate against H320 (LightGBM crash filter, PARTIAL CONFIRMED, OOS 1.274–1.283).

---

## Cross-References

- [Momentum Strategies](momentum-strategies.md) — 6m/12m momentum; 52-wk high as momentum modifier; H198 stock momentum confirmed
- [Short-Term Reversal](short-term-reversal.md) — H181 CONFIRMED industry-adjusted reversal (0.53%/month globally)
- [Calendar Anomalies](calendar-anomalies.md) — TOM, January effect, FOMC effect; H292 return seasonality connects here
- [Factor Models](factor-models.md) — disposition effect as factor loading; CGO in cross-sectional framework
- [Low-Volatility Anomaly](low-volatility.md) — lottery premium is the mirror of low-vol outperformance
- [Event-Driven Strategies](event-driven.md) — H174 PEAD; CGO interaction with post-earnings drift
- [Multi-Agent LLM Trading](multi-agent-llm-trading.md) — AI disposition effect (arXiv:2604.18373); H274 multi-agent PEAD
- [AI-Driven Alpha Factor Discovery](auto-alpha-discovery.md) — 213-factor ML ensemble; H374 proposal
