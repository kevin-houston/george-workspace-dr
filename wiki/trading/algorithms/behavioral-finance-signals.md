---
added: 2026-06-14
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

### Key findings (paper)
- R52 explains more of the momentum profit than the prior 6m or 12m raw return
- Significance holds after controlling for Jegadeesh-Titman momentum
- Average monthly excess return: +0.65%/month (1963–2001, NYSE/AMEX/NASDAQ)
- Not explained by earnings seasonality or risk factors

### H291 backtest result
- IS (2008–2017): Sharpe=1.031, CAGR=12.8%
- **OOS (2018–2025): Sharpe=0.764, CAGR=11.6%, MaxDD=-14.4%** — NOT CONFIRMED
- Corr(SPY) OOS = 0.731 — high market beta, limited diversification
- Root cause: in a 50-stock large-cap universe during 2018–2025 bull market, most
  stocks are near their 52-week highs simultaneously, collapsing cross-sectional
  dispersion. Signal works better in volatile markets with wider dispersion.

### When the signal is strongest
- Bear/recovery markets with high dispersion across stocks
- Small and mid-cap universes (more cross-sectional variation)
- When the market itself is below its own 52-week high (Li & Yu 2012 market-level version)

---

## 2. Return Seasonality — Same Calendar Month (Heston & Sadka 2008)

**Source**: Heston, S. L. and Sadka, R. (2008). "Seasonality in the Cross-Section
of Stock Returns." *Journal of Financial Economics*, 87(2), 418–445.

### Mechanism
Stocks display persistent seasonality in returns tied to the calendar month:
- **Earnings seasonality**: firms in cyclical industries (retail, construction,
  agriculture) have structurally higher earnings in certain quarters every year
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
- Consistent with rational risk pricing AND behavioral seasonality stories
- Keloharju et al. (2016): explains ~30% of annual stock return variation

### H292 backtest result
- IS (2008–2017): Sharpe=0.688, CAGR=11.6%
- **OOS (2018–2025): Sharpe=0.970, CAGR=18.2%, MaxDD=-19.1%** — CONFIRMED
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

### Caveats
1. Survivorship bias: fixed 50-stock universe from 2026 inflates all results
2. WF > 1 (OOS > IS) suggests OOS period happened to be favorable
3. Only 8-9 observations per calendar month in OOS — small sample
4. Corr(SPY) = 0.838 means limited diversification value vs. SPY-heavy production

### Practical use
The **July and November seasonal signals** are actionable as **tactical overlays**:
- In July and November, increase equity weight or add to existing positions in
  stocks that did well in the same month last year
- Do NOT use as a standalone monthly rotation — the weak months (Feb, Mar, Sep, Oct)
  erode the annual Sharpe

---

## 3. Disposition Effect and Price Momentum

**Source**: Frazzini (2006). "The Disposition Effect and Underreaction to News."
*Journal of Finance*, 61(4), 2017–2046.

### Mechanism
The **disposition effect** (Shefrin & Statman 1985): investors tend to sell winners
too early and hold losers too long. This creates:
- Prolonged underreaction to good news for stocks trading below purchase price
- Prolonged underreaction to bad news for stocks trading above purchase price
- Both cases create **momentum**: positive or negative news is incorporated slowly

### Signal
- Capital gains overhang (CGO): proxy = (P_t − P̄_avg_cost) / P_t
- Stocks with **negative CGO** (trading below average purchase price) react more
  slowly to positive news → stronger momentum
- Typically used as a modifier to standard momentum, not standalone

### Implementation note
CGO requires estimating average investor purchase price. Frazzini's proxy:
```python
CGO_t = (P_t − avg_weighted_price_60d) / P_t
# where avg_weighted_price = Σ(volume_t × price_t) / Σ(volume_t) over past 60 days
```
This is a rough proxy (true CGO needs holding period data not publicly available).

---

## 4. Lottery Stock Premium and Reversal

**Source**: Kumar (2009); Bali et al. (2011) "Maxing Out."

### Mechanism
Retail investors overweight **lottery-like stocks** (high MAX — maximum daily return
in the prior month, low price, high idiosyncratic volatility). This causes:
- Overvaluation of lottery stocks → future underperformance
- Avoidance of boring/stable stocks → their underpricing → future outperformance

### Signal: MAX factor
```
MAX_i = max(daily_return_i, over prior month)
```
- Short high-MAX stocks (overvalued lottery plays)
- Long low-MAX stocks (boring, stable, under-loved)

### Key finding
Long-short MAX factor: −0.55%/month alpha (shorts win more than longs)
Long-only anti-MAX (low MAX stocks): modest positive, absorbs value premium

---

## Cross-References

- [Momentum Strategies](momentum-strategies.md) — 6m/12m momentum; 52-wk high as momentum modifier
- [Short-Term Reversal](short-term-reversal.md) — H181 CONFIRMED industry-adjusted reversal
- [Calendar Anomalies](calendar-anomalies.md) — TOM, January effect, FOMC effect; H292 return seasonality connects here
- [Factor Models](factor-models.md) — disposition effect as factor loading
- [Low-Volatility Anomaly](low-volatility.md) — lottery premium is the mirror of low-vol outperformance
