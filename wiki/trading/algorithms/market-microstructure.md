---
title: Market Microstructure & HFT Strategies
added: 2026-05-25
category: algorithms
source: Stanford MS&E 448 (2021) — Sasson, Ho, Samson
---

# Market Microstructure & HFT Strategies

## Source

"High Frequency Trading Strategies" — Stanford MS&E 448, 2021. Joachim Sasson, Wei Hong Ho, Finsam Samson.
File: `sources/stanford_msande448_2021_gr1.pdf`

Two strategies covered: **Microprice** (Stoikov 2017) and **Avellaneda-Stoikov optimal market making** (2008).

---

## 1. Microprice (Stoikov 2017)

**Core idea:** A fair-price estimator that improves on mid-price and weighted mid-price by incorporating both order book imbalance *and* spread.

**Construction:**

P_micro = Mt + Σ gk(It, St)

Where:
- Mt = current mid-price
- It = order book imbalance = Qb / (Qa + Qb) — ratio of best-bid volume to total top-of-book volume
- St = bid-ask spread
- g1 = expected next mid-price move given current (I, S) state
- Series converges in ~6 iterations (g6 is adequate in practice)

**Why it beats weighted mid-price:**
- Weighted mid (Wt = It×Pa + (1−It)×Pb) has no theoretical martingale justification
- Microprice = E[mid-price at infinite future | current order book state] — a genuine conditional expectation
- Modeled as Markov chain: state = (imbalance, spread); transition matrices Q, R estimated from tick data

**Implementation:**
1. Discretize imbalance into buckets; record spread categories (1-tick, 2-tick, etc.)
2. Symmetrize dataset (flip bid/ask sides)
3. Estimate Q (transient transitions), R1 (into absorbing = mid-moves), R2 (absorbing + new imbalance)
4. g1 = (I − Q)⁻¹ R1 k; iterate B = (I−Q)⁻¹R2; compute g6 = g1 + Bg1 + ... + B⁵g1

**Results on AAPL / CVX (2021):**
- Microprice lives between bid and ask (theoretically appropriate)
- More movement than mid-price → richer signal, but did NOT generate significant profit on its own as a directional predictor
- Stationary imbalance distribution: N-shaped at 1-tick spread (imbalance rarely extreme); liquid stocks show U-shaped at 2-tick spread (lopsided when wide)

---

## 2. Avellaneda-Stoikov (AS) Market Making Model

**Core idea:** Market maker quotes bid/ask around a *reservation price* that adjusts for inventory risk, rather than symmetric mid-price quoting.

**Key formulas:**

Reservation price: r = S − q·γ·σ²·(T − t)

Optimal spread: δa + δb = γ·σ²·(T−t) + (2/γ)·ln(1 + γ/k)

Where:
- q = current inventory (positive = long)
- γ = risk-aversion parameter
- σ = volatility
- k = order arrival decay rate (from Poisson model: λ(δ) = A·e^{−kδ})

**Intuition:** If you're long inventory, shift both quotes *lower* to attract sell orders and repel buy orders. The spread widens when risk aversion or volatility is high.

**Results:**
| γ | AS Profit | Control Profit | AS Inv Std | Control Inv Std |
|---|-----------|----------------|------------|-----------------|
| 0.1 | 65.3 | 68.9 | 2.99 | 8.49 |
| 0.5 | 49.0 | 60.0 | 2.10 | 6.75 |

AS reduces inventory standard deviation by **3–4x** vs symmetric quoting, at a cost of 5–20% lower profit depending on risk aversion.

**Limitations noted:**
- Treats volatility σ as constant (unrealistic intraday)
- Treats order arrival rate k as constant (liquidity varies through day)
- Only places 1-unit orders (optimal sizing not addressed)

---

## Applicability to Kevin's Strategies

**Verdict: Not directly actionable with current infrastructure.**

| Aspect | Assessment |
|--------|-----------|
| Microprice as signal | Could improve intraday execution quality (buy when micro > mid = order book skewed bullish). But requires **tick-level L2 order book data** (bid/ask + volume at each level, millisecond timestamps). Polygon free tier does not cover this. |
| AS market making | Not relevant — Kevin is a **directional price-taker**, not a market maker. |
| Data requirement | Both strategies need Level 2 order book data at sub-second granularity. Not available in current stack (Alpaca paper API, Polygon free). |
| Potential future use | If Polygon paid tier (L2) is added: microprice signal could be layered on PEAD intraday entries to improve execution timing by 1–5 cents/share. Worth ~H230+ range if L2 data is acquired. |

**Bottom line:** File under "interesting when we have L2 data." Not blocking any current hypothesis.

---

## Related Hypotheses

None active. Potential future: microprice-enhanced execution for PEAD intraday (H225+).

## Cross-References

- [Event-Driven Strategies](event-driven.md) — PEAD intraday scanner (H174) where microprice execution could apply
- [Deep RL for Trading](deep-rl-trading.md) — RL agents in HFT market making is an extension of AS
