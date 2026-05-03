# Options Strategies Research Report — Round 25

**Run Date:** 2026-03-31
**Universe:** 10 Fortune 100 dividend stocks (XOM, CVX, JNJ, PFE, KO, T, VZ, IBM, MO, PG) + 30-stock PEAD universe
**Period:** 2020-01-01 to 2025-12-31 (5 years)
**Method:** Black-Scholes simulated premiums with 20-day realized volatility, r=4.5%

---

## Executive Summary

Options writing strategies (covered calls, cash-secured puts) deliver modest positive Sharpe ratios (0.21–0.53) but generally do NOT improve risk-adjusted returns versus buy-and-hold. The best individual strategy is **covered_call_IBM** (Sharpe 0.836), and the best stock for writing options is IBM. Earnings straddles show high simulated Sharpe but are inflated by the gap-event methodology. Protective puts **severely destroy** PEAD edge (Sharpe drops from 4.46 to 0.25). VIX short-vol via VXX is deeply unprofitable due to structural VXX decay overwhelming the synthetic premium.

---

## Strategy 1: Covered Call Writing

| Ticker | Sharpe | vs Buy-Hold (ann.) | Premium/yr | Max DD | Win Rate |
|--------|--------|-------------------|------------|--------|----------|
| IBM    | 0.836  | -10.9%            | 20.8%      | -19.0% | 69.0%    |
| KO     | 0.707  | +1.2%             | 12.5%      | -18.1% | 67.6%    |
| MO     | 0.707  | +1.3%             | 17.1%      | -18.8% | 62.0%    |
| XOM    | 0.706  | -2.6%             | 27.7%      | -42.5% | 74.7%    |
| PG     | 0.622  | +2.4%             | 12.7%      | -10.8% | 59.2%    |
| JNJ    | 0.569  | -0.9%             | 12.0%      | -18.7% | 60.6%    |
| CVX    | 0.537  | -2.5%             | 26.3%      | -34.6% | 73.2%    |
| T      | 0.525  | +3.9%             | 20.0%      | -27.3% | 67.6%    |
| VZ     | 0.219  | +3.6%             | 14.9%      | -27.7% | 57.8%    |
| PFE    | -0.103 | -1.3%             | 21.9%      | -38.3% | 46.5%    |

**Average:** Sharpe 0.533, vs Buy-Hold -0.58%/yr, premium income 18.6%/yr, avg max DD -25.6%

**Key insights:**
- Covered calls improve on buy-hold only for slow-moving, high-dividend names (KO, MO, T, VZ, PG)
- High-premium stocks (XOM, CVX at ~25-28%/yr) have large energy-sector drawdowns that overwhelm income
- IBM's cap on upside was extreme (-10.9% vs BH) — IBM ripped 268% over the period
- 3% OTM calls are frequently exercised (70%+ win rates on energy) due to high volatility
- PFE is the worst case: stock declined structurally, no amount of premium overcame losses

**Does covered call writing improve risk-adjusted returns vs buy-and-hold?**
Mixed. Sharpe ratios of 0.5–0.84 are reasonable, but vs buy-and-hold the improvement is marginal. Only 5 of 10 stocks show positive vs-BH alpha (T, VZ, KO, MO, PG — all low-vol, slow-growth names). High-growth and energy names underperform buy-hold when sold via covered calls.

---

## Strategy 2: Cash-Secured Put (CSP)

| Ticker | Sharpe | vs Cash (ann.) | Premium/yr | Max DD | Win Rate |
|--------|--------|----------------|------------|--------|----------|
| IBM    | 0.449  | +0.8%          | 31.2%      | -17.3% | 71.8%    |
| XOM    | 0.418  | +1.4%          | 38.4%      | -40.7% | 76.1%    |
| PG     | 0.352  | -1.6%          | 22.4%      | -11.9% | 71.8%    |
| CVX    | 0.311  | -0.5%          | 36.9%      | -32.6% | 80.3%    |
| MO     | 0.296  | -1.5%          | 27.2%      | -18.4% | 71.8%    |
| KO     | 0.256  | -2.3%          | 22.1%      | -17.1% | 70.4%    |
| T      | 0.207  | -2.7%          | 30.4%      | -28.0% | 69.0%    |
| JNJ    | 0.182  | -3.3%          | 21.6%      | -23.7% | 70.4%    |
| VZ     | -0.097 | -6.4%          | 24.9%      | -29.8% | 64.8%    |
| PFE    | -0.270 | -8.4%          | 32.5%      | -34.1% | 52.1%    |

**Average:** Sharpe 0.210, vs cash -2.44%/yr, premium income 28.7%/yr, avg max DD -25.4%

**Key insights:**
- ATM puts collect substantially more premium than OTM calls (28.7% vs 18.6%/yr) due to being struck at-the-money
- Win rates are high (70-80%) but assignments on big drops severely hurt returns
- Only IBM and XOM beat cash-secured alternatives after accounting for assignment losses
- CSP is worse than covered calls on a Sharpe basis (0.21 vs 0.53) — assignment losses on ATM puts exceed capped-gain losses on covered calls
- The high-premium stocks (XOM, CVX) have high win rates but catastrophic drawdowns during energy crises

---

## Strategy 3: Earnings Straddle (Gap Events as Proxy)

| Entry Timing | Avg Sharpe | Win Rate | Avg Return/Trade |
|--------------|-----------|----------|-----------------|
| 5 days before | 6.02 | 62.2% | +1.83%          |
| 2 days before | 3.79 | 62.9% | +0.89%          |
| 1 day before  | 3.89 | 68.4% | +0.55%          |

**Optimal entry: 5 days before the gap event**

**Important methodological caveat:** These Sharpe ratios (3–6) appear very high and should be interpreted with caution. The gap-event proxy introduces look-ahead bias — we identify "earnings-like" gap events post-hoc using daily closing prices. In live trading, you cannot reliably predict a >3% overnight gap 5 days in advance. True earnings straddle Sharpes are typically 0.3–0.5 in live conditions.

**What the numbers do tell us (bias-adjusted interpretation):**
- When a major move is about to occur (gap >3%), buying a straddle 5 days before is profitable ~62% of the time
- Earlier entry (5d) beats later entry because implied vol tends to rise into the event, making premiums more expensive the closer you are to the event
- The 1d-before high win rate (68.4%) with lower avg return (0.55%) reflects gamma risk — premiums are maximal but so is the straddle cost
- In realistic conditions, IV crush on non-events would reduce actual win rates significantly

---

## Strategy 4: Protective Put Overlay on PEAD

**Core question: Does the put cost destroy more edge than it protects?**

**Answer: Yes, decisively.**

| Metric | PEAD Raw | PEAD + Protective Put |
|--------|---------|----------------------|
| Avg Sharpe | 4.463 | 0.251 |
| Sharpe Impact | — | -4.211 |
| Avg Put Cost | — | 3.57%/trade |
| Destroys Edge | — | YES |

**Selected stock detail:**

| Ticker | Sharpe Raw | Sharpe Protected | Put Cost | Notes |
|--------|-----------|-----------------|----------|-------|
| MSFT   | 13.88     | 5.86            | 4.07%    | Strong trend, put rarely needed |
| JNJ    | 13.36     | 12.80           | 3.05%    | Low vol, put barely affects |
| TSLA   | 4.54      | 4.97            | 4.67%    | High vol means put actually helps max DD |
| AMZN   | 3.61      | 2.30            | 2.27%    | Moderate degradation |
| UNH    | 5.00      | 2.33            | 4.44%    | Significant degradation |
| JPM    | -0.17     | -5.64           | 4.35%    | Put cost on bad trades doubles loss |
| AAPL   | 2.11      | -1.27           | 2.99%    | Put cost turns edge negative |

**Analysis:**
- The 5% OTM put at 20-day expiry costs ~3.6% on average, which typically exceeds the PEAD edge per trade (~3-5% avg return)
- In the best case (TSLA), protective puts slightly improve Sharpe by reducing catastrophic drawdowns
- In most cases, the put premium simply eats the alpha — you spend insurance on trades that were already profitable
- The PEAD edge (gap > 5%, hold 20d) has a high win rate (~68%) meaning protection is only needed ~32% of the time, but you pay for it 100% of the time
- **Conclusion:** Do not add protective puts to PEAD trades. The edge is in the positive-momentum continuation, and 3.57%/trade insurance destroys the risk-adjusted profile entirely.

---

## Strategy 5: VIX-Based Short Vol (VXX Proxy)

| Metric | Value |
|--------|-------|
| N trades | 126 |
| Sharpe | -4.98 |
| Win rate | 68.3% |
| Avg return/trade | -3.34% |
| Max drawdown | -99.6% |
| Annualized premium collected | 10.5% |

**Analysis:**
VXX short-vol was deeply unprofitable over 2020-2025. Despite a 68.3% win rate:
- VXX experiences structural decay (contango roll costs) AND episodic catastrophic spikes
- When VXX rises after a "spike subsiding" signal, the move can be +20-50% (COVID re-waves, rate shock episodes)
- The 0.5% simulated premium (conservative) is insufficient vs. the magnitude of adverse moves
- Even with a 68% win rate, the 32% of losing trades involved losses of -10% to -50% on the position
- This matches real-world experience: short vol products (SVXY, XIV) famously blew up in February 2018

**The VXX mean-reversion hypothesis fails here:** the signal (VXX -5% in a day) fires too often and too early, often preceding further VIX spikes rather than sustained reversions.

---

## Cross-Strategy Comparison

| Strategy | Best Sharpe | Avg Sharpe | Premium/yr | Practical Grade |
|----------|------------|-----------|------------|-----------------|
| Covered Call | 0.836 (IBM) | 0.533 | 18.6% | B+ |
| Cash-Secured Put | 0.449 (IBM) | 0.210 | 28.7% | C+ |
| Earnings Straddle | 6.02* (proxy) | 6.02* | N/A (buyer) | A* (inflated) |
| Protective Put / PEAD | N/A | 0.251 | -3.57% (cost) | D |
| VIX Short Vol (VXX) | — | -4.98 | 10.5% | F |

*Straddle Sharpes are significantly inflated by look-ahead bias in gap-event identification

**Winner by Sharpe:** Covered calls, specifically IBM at 0.836

**Best premium income:** Cash-secured puts at 28.7%/yr, but most of this is "illusory" — the assigned positions create offsetting losses

**Compared to other strategies in this eval program:**
- PEAD long (Sharpe 1.14) still dominates all options strategies
- Options writing roughly matches macro trend-following (Sharpe ~0.5–0.7)
- Options writing significantly underperforms ML-enhanced strategies (Sharpe 1.5+)
- Premium income (18-29%/yr) looks large but comes with full equity risk exposure on assignment

---

## Does Options Writing Improve Risk-Adjusted Returns vs Buy-and-Hold?

**Covered calls:** Marginal improvement for low-volatility, slow-growth names. For high-growth or high-dividend names in secular uptrends, covered calls cap upside and underperform buy-hold.

**Cash-secured puts:** Generally inferior to covered calls AND to buy-and-hold on a Sharpe basis. High assignment risk during drawdowns.

**Overall conclusion:** Options writing provides income (18-29%/yr notional) but this comes at the cost of capped upside and full downside exposure. For the Fortune 100 universe tested, covered calls are a modest improvement on Sharpe only for range-bound or slowly trending stocks.

---

## Practical Notes

**Margin account required:**
- Cash-secured puts: NO margin required (cash secures the put)
- Covered calls: NO margin required (covered by long stock)
- Naked short calls/puts: YES, requires margin (not tested here)
- VXX short-vol structures: YES, requires margin

**Assignment risk:**
- Cash-secured puts face assignment if stock drops below strike — you acquire shares at K regardless of market price
- Covered calls face assignment if stock rises above strike — shares are called away at K (you miss upside)
- Assignment is most costly during trend reversals and gap-down events

**Options-specific risks not modeled:**
- Bid-ask spread on monthly options (typically 0.1-0.3% of premium)
- Early assignment risk on in-the-money options near ex-dividend dates
- Liquidity risk on low-volume names (T, VZ options can be illiquid)
- Volatility regime changes affecting Black-Scholes accuracy

**Best practical strategy from this eval:**
Covered calls on IBM, KO, MO, and PG — low-volatility names with sufficient premium (12-21%/yr) and limited upside capture loss. Avoid CSPs on trending stocks (IBM, XOM) and all VXX-based strategies.

---

## Key Finding

*Covered calls (avg Sharpe 0.533, best IBM at 0.836) modestly improve on buy-and-hold for range-bound dividend stocks, but cannot match PEAD long momentum (Sharpe 1.14). Protective puts completely destroy PEAD edge (Sharpe 4.46 → 0.25, put cost ~3.6%/trade). VIX short-vol via VXX is structurally unprofitable despite 68% win rate — rare large spikes dominate. The 20-28%/yr simulated premium income from options writing is the most attractive feature, but only 2-3 of 10 names actually generate alpha after assignment/cap losses.*
