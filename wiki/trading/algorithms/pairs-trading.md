---
updated: 2026-06-21
type: strategy-guide
status: PAIRS FAMILY EXHAUSTED at statistical cointegration level (H152–H160 daily; H200 NOT CONFIRMED 2026-05-15); LLM SEMANTIC PAIRS new direction active (H316 queued; arXiv:2605.01954 + 2604.19476)
---

# ETF Pairs Trading (Statistical Arbitrage)

Mean-reversion strategy exploiting temporary deviations from a long-run equilibrium between two or more co-moving ETFs. The alpha source is cointegration — two price series that individually follow random walks but share a stationary spread.

**Related pages**: [Momentum Strategies](momentum-strategies.md) — opposite alpha source; low correlation to pairs | [Event-Driven Strategies](event-driven.md) — H160 factor-residualized pairs design | [Hypothesis Log](../backtesting/hypothesis-log.md) — H152–H160 ALL NOT CONFIRMED; family exhausted at daily frequency

**Academic foundation**: Engle & Granger (1987) — Error Correction Models; Gatev, Goetzmann & Rouwenhorst (2006) — classic pairs trading study on US stocks (60-day formation, 6-month trading window).

---

## Why ETFs (not stocks)

- Structural cointegration: ETF pairs in the same segment (GDX/SIL, XLE/OIH) are cointegrated by economic necessity — they track correlated underlying factors
- No overnight/fundamental jump risk that breaks stock pairs
- No borrowing cost or short-squeeze risk (ETFs are liquid and borrowable)
- Pairs persist for years; stock pairs break at earnings or M&A

**Risk**: sector composition drift. XLE/OIH partially diverged 2020-2024 after energy transition changed the sub-industry weights. Retest cointegration quarterly.

---

## Known Cointegrated ETF Pairs

| Pair | Economic link | Notes |
|------|--------------|-------|
| GDX / SIL | Gold miners / Silver miners | Share underlying metal prices, royalty economics |
| XLE / OIH | Energy broad / Oil services | Services sector depends on E&P capex |
| XLK / QQQ | Technology sector / Nasdaq-100 | QQQ is ~50% tech; cointegration tight but OHLCs differ |
| EWA / EWC | Australia / Canada iShares | Both commodity-exporting economies |
| TLT / IEF | 20yr+ Treasury / 7-10yr Treasury | Yield-curve spread play; same issuer |
| SPY / IVV | Two S&P 500 trackers | Near-arbitrage — spreads tiny, eaten by fees |
| XLF / KRE | Financials broad / Regional banks | KRE is a subset of XLF |
| GLD / IAU | Two gold ETFs | Same underlying, expense ratio arbitrage only |

**Most promising for backtesting**: GDX/SIL and XLE/OIH — large spreads (lower transaction cost hurdle), clear economic narrative, liquid options for hedging.

---

## Step 1: Test for Cointegration

### Engle-Granger (two-asset pairs)

```python
from statsmodels.tsa.stattools import coint
import yfinance as yf

# Load ETF prices
tickers = ["GDX", "SIL"]
prices = yf.download(tickers, start="2010-01-01", auto_adjust=True)["Close"]

stat, pvalue, critical_values = coint(prices["GDX"], prices["SIL"])
print(f"p-value: {pvalue:.4f}")   # p < 0.05 → cointegrated
# critical_values: [1%, 5%, 10%] thresholds for test stat
```

**Interpretation**: p < 0.05 rejects null of no cointegration. p < 0.01 is high confidence. Always test over the full available history, then re-test on sub-periods to check stability.

### Johansen Test (3+ assets or validation)

```python
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import numpy as np

data = prices[["GDX", "SIL"]].dropna().values
result = coint_johansen(data, det_order=0, k_ar_diff=1)
# result.lr1: trace statistics; result.cvt: critical values [90%, 95%, 99%]
print("Trace stat:", result.lr1)
print("Critical values (90/95/99%):", result.cvt)
```

Johansen avoids the two-step error accumulation of Engle-Granger and is required when testing 3+ asset groups.

---

## Step 2: Estimate the Hedge Ratio

The hedge ratio β tells you how many units of Y to hold per unit of X. Two approaches:

### Static OLS (simple but degrades)

```python
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

X = add_constant(prices["GDX"])
model = OLS(prices["SIL"], X).fit()
beta = model.params["GDX"]          # hedge ratio
spread = prices["SIL"] - beta * prices["GDX"] - model.params["const"]
```

**Problem**: OLS estimates a single β over the full sample. For pairs held over years, β drifts. TLT/IEI hedge ratio dropped from 1.38 to 0.9 over 2011–2016 (Chan, 2013).

### Rolling OLS (better, but noisy)

```python
window = 252  # 1 year
rolling_beta = prices["SIL"].rolling(window).apply(
    lambda y: np.polyfit(prices["GDX"].loc[y.index], y, 1)[0], raw=False)
spread_rolling = prices["SIL"] - rolling_beta * prices["GDX"]
```

### Kalman Filter (best for dynamic pairs)

Treats β as a hidden state that evolves as a random walk. Updates continuously; most stationary spreads in practice.

```python
from pykalman import KalmanFilter
import numpy as np

# Observation matrix: [GDX, 1] (slope + intercept)
obs_mat = np.vstack([prices["GDX"].values, np.ones(len(prices))]).T[:, np.newaxis, :]

kf = KalmanFilter(
    n_dim_obs=1,
    n_dim_state=2,
    initial_state_mean=[1.0, 0.0],
    initial_state_covariance=np.eye(2),
    transition_matrices=np.eye(2),          # β follows random walk
    observation_matrices=obs_mat,
    observation_covariance=1.0,
    transition_covariance=0.01 * np.eye(2), # how fast β can change
)
state_means, _ = kf.filter(prices["SIL"].values[:, np.newaxis])
beta_kf = state_means[:, 0]
intercept_kf = state_means[:, 1]
spread_kf = prices["SIL"].values - beta_kf * prices["GDX"].values - intercept_kf
```

Use Kalman when holding > 6 months. For short-term (< 3 month rolling tests), rolling OLS is sufficient.

---

## Step 3: Calculate the Z-Score

```python
import pandas as pd

spread = pd.Series(spread_kf, index=prices.index).dropna()

lookback = 60  # trading days (~3 months)
z_score = (spread - spread.rolling(lookback).mean()) / spread.rolling(lookback).std()
```

**Critical**: use rolling statistics computed *only from past data*. Never use full-sample mean/std (look-ahead bias).

---

## Step 4: Generate Signals

Standard thresholds (Gatev et al. 2006, Chan 2013):

| Action | Z-score condition | Direction |
|--------|------------------|-----------|
| Enter long spread | z < −2.0 | Long Y (SIL), Short X (GDX) |
| Enter short spread | z > +2.0 | Short Y, Long X |
| Exit | \|z\| < 0.5 | Close both legs |
| Stop-loss | \|z\| > 4.0 | Regime break — exit and pause |

```python
long_entry   = z_score < -2.0
short_entry  = z_score > +2.0
exit_signal  = z_score.abs() < 0.5
stop_loss    = z_score.abs() > 4.0
```

**Optimized thresholds** (from parameter search): entry ~1.4–1.5σ reduces whipsaw; exit ~0.3–0.5σ locks profits earlier. Test on OOS data.

---

## Step 5: Measure Half-Life of Mean Reversion

Half-life tells you how quickly the spread reverts. Short half-life (< 20 days) = fast mean-reversion strategy; long half-life (> 60 days) = slower, monthly-rebalance appropriate.

```python
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
import numpy as np

spread_lag  = spread.shift(1).dropna()
spread_diff = spread.diff().dropna()
aligned = pd.concat([spread_diff, spread_lag], axis=1).dropna()
aligned.columns = ["diff", "lag"]

model = OLS(aligned["diff"], add_constant(aligned["lag"])).fit()
theta = model.params["lag"]           # mean-reversion coefficient (should be negative)
half_life = np.log(2) / (-theta)      # days to 50% reversion

print(f"Half-life: {half_life:.1f} trading days")
```

**Rule of thumb**: set lookback window = 2–4× half-life.

---

## Backtesting Methodology

### Walk-Forward (mandatory)

```python
TRAIN_MONTHS = 12   # estimate β and z-score params
TEST_MONTHS  = 3    # trade on OOS signals

results = []
for start in pd.date_range("2010-01", "2025-01", freq="3MS"):
    train_end  = start + pd.DateOffset(months=TRAIN_MONTHS)
    test_end   = train_end + pd.DateOffset(months=TEST_MONTHS)
    train = prices[start:train_end]
    test  = prices[train_end:test_end]
    # fit β on train, generate signals on test
    beta = fit_ols(train)
    signals = generate_signals(test, beta)
    results.append(backtest(test, signals))
```

Never fit β or the z-score window on the data you're trading. This is the most common error in pairs backtests.

### Transaction costs

ETF pairs are relatively cheap to trade but:
- Two-sided round trip: 2× commission + 2× half-spread
- For IB: ~$0.005/share × 2 legs × 4 trades (entry + exit) = ~$0.04/share
- Rule of thumb: require >0.5% spread width to cover costs

---

## Common Failure Modes

### 1. Cointegration breakdown

Signs: z-score drifts to extreme values without reverting; ADF p-value on spread rises > 0.1 in rolling re-test.

**Response**: close positions, pause until rolling cointegration test confirms reinstatement. Re-test monthly.

### 2. Look-ahead bias in hedge ratio

Fitting β on the full sample and then "backtesting" produces falsely smooth P&L. Always fit on train window only.

### 3. Overcrowded pairs

SPY/IVV and GLD/IAU are near-arbitrage relationships. The spread is so tight that any transaction costs eliminate edge. Only trade pairs where the spread justifies costs.

### 4. 2020 Energy sector break (XLE/OIH)

OIH composition shifted from diversified oil services to tech-heavy (SLB, HAL lost weight; newer names added). XLE/OIH spread widened permanently 2020-2022 before partially normalizing. **Lesson**: sector ETF composition changes — re-test cointegration after any major reconstitution.

---

## Python Library Stack

| Library | Purpose | Install |
|---------|---------|---------|
| `statsmodels` | Cointegration tests (Engle-Granger, Johansen), ADF test | `pip install statsmodels` |
| `pykalman` | Kalman filter for dynamic hedge ratio | `pip install pykalman` |
| `pandas` | Rolling z-score, resampling | standard |
| `scikit-learn` | Rolling OLS alternative, feature engineering | standard |
| `arch` | GARCH volatility for dynamic position sizing | `pip install arch` |
| `hurst` | Hurst exponent (measures mean-reversion strength) | `pip install hurst` |

### Alternative: Hudson & Thames ArbitrageLab

Academic-grade pairs trading library:
- GitHub: https://github.com/hudson-and-thames/arbitragelab
- Covers: distance approach, cointegration, Copula-based pairs, OU model fitting
- License: BSL 1.1 (non-commercial free; commercial ~$3k/year)
- Overkill for ETF pairs but useful for stock-universe stat arb

---

## Correlation with H026 Momentum Strategy

H150 (Low-Vol Anomaly) showed that sector strategies can have OOS corr ~0.18 with H026. Pairs trading is structurally different — it's market-neutral (long one ETF, short another), so correlation with a long-only momentum strategy should be near zero or even negative.

Target: monthly return correlation with H026 < 0.30. If a pairs strategy confirms (H152+), it could provide genuine diversification — the blending case is much stronger than low-vol vs H026.

---

## Backtest Results Summary (H152–H160)

All pairs trading hypotheses reached NOT CONFIRMED. The family is exhausted at daily frequency.

| H# | Strategy | Verdict | OOS Sharpe | Key Finding |
|----|----------|---------|-----------|-------------|
| H152 | GDX/SIL OLS | NOT CONFIRMED | — | No cointegration |
| H153 | XLE/OIH OLS | NOT CONFIRMED | — | No cointegration |
| H154 | TLT/IEF static OLS | NOT CONFIRMED | 0.514 | Mean-reverting but not cointegrated; best of family |
| H155 | TLT/IEF Kalman | NOT CONFIRMED | 0.118 | Kalman explains away the spread (half-life collapses to <2d) |
| H160 | Factor-residualized stock pairs | NOT CONFIRMED | 0.127–0.226 | Residualization improves cointegration stat but not trading PnL; OOS cointegration breaks all pairs |

**H166 (GRU/LSTM spread forecasting)**: FLAGGED — ML on broken signal unlikely to help; blocked pending H160 resolution. Deprioritized.

**H169 (LLM pair selection)**: BLOCKED — H200 NOT CONFIRMED confirms the pair selection hypothesis fails at the cointegration level, not the selection level. LLM/ML pair selection cannot fix absent cointegration.

**Recent literature note (ACM 2026, DOI 10.1145/3800000.3800094)**: Hybrid framework combining cointegration selection with ensemble ML for entry/exit signal generation claims to "substantially outperform traditional statistical approaches." Key caveat: this improves SIGNAL QUALITY on already-cointegrated pairs — it doesn't solve the fundamental problem that US large-cap equities are not cointegrated at daily frequency in 2018–2026. Relevant only if a sub-universe with genuine cointegration is found (e.g., sector-specific pairs on 60-min bars).

**Bottom line (ETF pairs)**: ETF pairs and stock pairs at daily frequency do not exhibit sufficient OOS cointegration in the 2018–2026 period for systematic trading. HFT arbitrage has compressed mean-reversion windows below the 5-day minimum required for cost-effective daily-close execution.

**However**: the graphical matching approach (H200) addresses the selection problem, not the cointegration problem. If the underlying cointegration has genuinely degraded, H200 will also fail. If the prior family's failure was partly due to poor pair selection (concentrating in overfit clusters), H200 may succeed.

See [Hypothesis Log](../backtesting/hypothesis-log.md) for detailed results per hypothesis.

---

## H200: Graphical Matching Pairs Trading (Stock-Level)

**Source**: arXiv:2403.07998 (Qureshi & Zaman, 2024). **Status**: NOT CONFIRMED (2026-05-15) — 0/15 pairs passed Engle-Granger cointegration test (p < 0.05). Root cause: cointegration in US large-cap equities at daily frequency has structurally degraded. The selection algorithm works (maximum weighted matching finds the most-correlated pairs) but no pairs are actually cointegrated in the 2018–2026 OOS window. Confirms H160 root cause: the problem is cointegration breakdown, not pair selection quality.

**Key idea**: Build a correlation graph over stocks. Apply maximum weighted matching — each stock can appear in at most one pair simultaneously. This prevents the concentration problem where highly-correlated clusters (e.g., all tech stocks) produce many overlapping pairs with correlated exposures.

### Method

1. Build correlation graph: nodes = stocks, edge weights = pairwise 12-month rolling return correlation
2. **Maximum weighted matching**: select pairs to maximize total correlation weight with the constraint that no stock appears in multiple pairs
3. For each matched pair: Engle-Granger cointegration test (p < 0.05). Reject non-cointegrated pairs.
4. Spread: z-score of log price ratio, 100-period rolling window
5. Entry: |z| > 1.5σ. Exit: |z| < 0.5σ. Stop-loss: |z| > 3.0σ
6. Monthly pair reassignment (re-run matching + cointegration)

### Academic results (S&P 500, 2017–2023)

| Strategy | Sharpe | Notes |
|----------|--------|-------|
| Graphical matching pairs | **1.23** | No asset in > 1 pair simultaneously |
| Random pair selection | 0.48 | Baseline without matching |
| Market (SPY BH) | 0.59 | |

### Distinction from H152–H160

H152–H160 tested ETF pairs with manually selected pairs and no constraint on overlap. H200 differs:
1. **Universe**: individual large-cap stocks (not ETFs); 30-stock pilot → 200+ if confirmed
2. **Selection**: maximum weighted matching on correlation graph — automated, no human curation
3. **Scale**: N=15 active pairs from 30-stock universe
4. **Confirm criteria**: OOS Sharpe > 0.5, Cumul > 1.3×, Corr-SPY < 0.4

### Universe

Same 30-stock S&P 500 universe as H181/H198 for initial validation. If confirmed, expand to the S&P 500 top-200 by market cap for sufficient pair candidates.

## LLM-Based Pair Selection — Active Research Direction (2025–2026)

Statistical cointegration is dead at daily frequency for US large-caps (H152–H200, 2018–2026). The new direction is **semantic pairs** — selecting pairs based on fundamental economic relatedness assessed by LLMs rather than statistical price tests. Structural business relationships persist through market regimes even when price cointegration breaks.

Three complementary 2026 papers define this landscape:

---

### Paper 1: Moira — Hierarchical RL with LLM Policies (arXiv:2605.01954)

**Full title**: "Moira: Language-driven Hierarchical Reinforcement Learning for Pair Trading"  
**Submitted**: May 3, 2026  
**URL**: https://arxiv.org/abs/2605.01954

**Core innovation**: Replaces statistical pair selection AND statistical signal generation with LLM-driven policies at both levels.

**Two-level architecture:**
- **High-level policy (LLM)**: selects which pair to trade from the candidate universe. Parameterized by LLM — evaluates semantic relatedness of companies (same supply chain, competing products, shared regulatory risk) to form a pair
- **Low-level policy (LLM)**: manages position sizing and exit timing. Receives spread z-score and company context, outputs position

Both policies updated via **textual feedback** (trajectory-level and episode-level rewards converted to natural language guidance) — not gradient backprop. This allows the policies to reason over why a trade worked or failed.

**Results (from paper HTML)**:
- Performance improves sharply from K=4+ trajectory update steps — annualized return and Sharpe increase substantially while max drawdown decreases
- "Semantic selection only" variant (no RL) already achieves positive returns and improved risk-adjusted performance vs traditional baselines
- Full Moira (semantic selection + RL exit) substantially outperforms the selection-only variant

**Key caveat**: Paper presents results on a single market period (2024-2025 real data). No out-of-sample walkforward across 2018-2023 bear/rate-hike regimes. Monitor for v2 with extended backtest.

**H316 design relevance**: H316 uses Moira's semantic pair selection idea but replaces the RL execution layer with our standard z-score threshold entry/exit (which is already validated). This isolates the novel contribution — LLM semantic pair identification.

---

### Paper 2: Cross-Stock Predictability via LLM-Augmented Semantic Networks (arXiv:2604.19476)

**Full title**: "Cross-Stock Predictability via LLM-Augmented Semantic Networks"  
**Authors**: Yikuan Huang, Zheqi Fan, Kaiqi Hu, Yifan Ye  
**Submitted**: April 21, 2026  
**URL**: https://arxiv.org/abs/2604.19476

**Core innovation**: Two-stage framework for building economically meaningful stock networks:
1. **Stage 1 — Sparse candidate graph**: build initial edges from 10-K filing embeddings (similar business descriptions → candidate link)
2. **Stage 2 — LLM edge classification**: LLM assesses each candidate edge — does it reflect a genuine economic relationship (customer/supplier, competitive, regulatory) or spurious text similarity?

This filters out the "same industry, different business model" false positives that plague embedding-only approaches (e.g., McDonald's and a restaurant supply chain ETF both use "food" vocabulary but have different economic dynamics).

**Academic foundation**: Builds on Cohen & Frazzini (2008) customer-supplier momentum and Menzly & Ozbas (2010) industry linkage predictability. The LLM stage classifies edge *type* (asymmetric lead-lag vs symmetric common factor) which determines the trading direction:
- **Asymmetric link** (supplier leads customer): trade the lead-lag spread
- **Symmetric link** (common factor): trade the mean-reversion spread

**Relevance to H316/H319**: Provides a richer pair taxonomy than Moira's binary "related/not-related." Asymmetric links → lead-lag (momentum-like); symmetric links → mean-reversion (pairs-like). Could drive two sub-strategies from the same LLM edge classification step.

**Caution from a 2025 EMH test** ([Is All the Information in the Price? — Wang, Johnson, Hybinette & Balch 2025](../sources/llm-embeddings-vs-price-stock-clustering-2025.md), arXiv:2509.01590): clustering stocks by *news-headline* LLM embeddings alone loses to plain price-correlation K-means by ~15% RMSE on out-of-sample return prediction — text similarity is not a standalone substitute for price co-movement as a stock-grouping signal. This is consistent with, not contradictory to, 2604.19476's design: that paper uses price/text co-occurrence to build the *candidate* graph first and only uses the LLM to *filter* candidates (removing false positives), rather than clustering on embeddings alone. Any H316/H319 implementation should follow the filter-not-primary-signal pattern — use LLM text similarity to prune a price/cointegration-derived candidate list, not to generate candidates from scratch.

---

### Paper 3: LLM as Risk Manager — Semantic Filtering for Lead-Lag (arXiv:2602.07048)

**Full title**: "LLM as a Risk Manager: LLM Semantic Filtering for Lead-Lag Trading in Prediction Markets"  
**Submitted**: February 27, 2026  
**URL**: https://arxiv.org/abs/2602.07048

**Core innovation**: Hybrid two-stage causal screener:
1. **Statistical stage**: Granger causality identifies candidate leader-follower pairs from time-series
2. **LLM semantic stage**: LLM re-ranks candidates by assessing whether the proposed direction has a plausible economic transmission mechanism based on event descriptions

**Key insight**: Granger causality frequently produces spurious leads (noise-driven or coincidental). The LLM semantic filter eliminates statistically significant but economically nonsensical leads — acts as a "plausibility gate."

**Result**: Outperforms statistical-only baseline on Kalshi Economics markets (no Sharpe reported, but consistent PnL improvement).

**Applicability to equities**: The same two-stage pipeline — statistical screen → LLM plausibility filter — applies to stock pairs. Use rolling 12-month return Granger causality (or lead-lag correlation) to generate candidates, then LLM rates whether the transmission story makes economic sense (e.g., "AAPL leads SWKS because Apple designs chips that Skyworks manufactures" is plausible; "WMT leads GOOGL" is not).

---

### Python Implementation: LLM Pair Scoring

```python
from openai import OpenAI
import pandas as pd
import json

client = OpenAI()  # uses $OPENAI_API_KEY

PAIR_SCORING_PROMPT = """
You are assessing whether two companies form a viable pair for statistical arbitrage.
A viable pair has a STRUCTURAL economic link that persists through market cycles:
- Same supply chain (one is a major customer/supplier of the other)
- Direct competitive overlap (>50% of revenue from same product/market)  
- Same regulatory regime (both revenue-dominated by a single regulator or commodity)
- Shared key input (both depend on the same critical input: e.g. both aluminum-intensive)

Rate the pair on two dimensions:
1. LINK_STRENGTH (0-10): strength of fundamental economic link
2. LINK_TYPE: "CUSTOMER_SUPPLIER" | "COMPETITOR" | "COMMON_INPUT" | "REGULATORY" | "WEAK" | "NONE"

Company A: {ticker_a} — {desc_a}
Company B: {ticker_b} — {desc_b}

Respond with JSON only: {{"link_strength": X, "link_type": "...", "rationale": "one sentence"}}
"""

def score_pair(ticker_a: str, desc_a: str, ticker_b: str, desc_b: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # ~$0.15/1M input tokens — cheapest capable model
        messages=[{
            "role": "user",
            "content": PAIR_SCORING_PROMPT.format(
                ticker_a=ticker_a, desc_a=desc_a,
                ticker_b=ticker_b, desc_b=desc_b
            )
        }],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


def score_universe_pairs(universe: list[tuple[str, str]], min_strength: int = 6) -> pd.DataFrame:
    """
    Score all N*(N-1)/2 pairs in universe.
    universe: list of (ticker, description) tuples
    Returns DataFrame with eligible pairs (link_strength >= min_strength).
    """
    results = []
    for i, (ta, da) in enumerate(universe):
        for j, (tb, db) in enumerate(universe):
            if j <= i:
                continue
            score = score_pair(ta, da, tb, db)
            results.append({
                "ticker_a": ta, "ticker_b": tb,
                "link_strength": score["link_strength"],
                "link_type": score["link_type"],
                "rationale": score["rationale"],
            })
    df = pd.DataFrame(results)
    return df[df["link_strength"] >= min_strength].sort_values("link_strength", ascending=False)
```

### Embedding-based Pre-filter (Two-Stage Pipeline)

For large universes (S&P 500 = 124,750 pairs), scoring all pairs with a chat model is prohibitively slow. Use embedding similarity as a fast first-pass filter:

```python
import numpy as np

def get_embeddings(texts: list[str], model: str = "text-embedding-3-small") -> np.ndarray:
    response = client.embeddings.create(input=texts, model=model)
    return np.array([e.embedding for e in response.data])

def build_candidate_pairs(
    universe: list[tuple[str, str]],
    top_k: int = 10,  # top-k similar companies per stock
    min_cos_sim: float = 0.75,
) -> list[tuple[str, str]]:
    """
    Stage 1: embedding cosine similarity → candidate pairs
    Stage 2 (caller): score candidates with LLM
    """
    tickers = [t for t, _ in universe]
    descs = [d for _, d in universe]
    
    embeddings = get_embeddings(descs)  # (N, 1536) for text-embedding-3-small
    # Normalize to unit vectors
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings_norm = embeddings / norms
    # Cosine similarity matrix
    sim_matrix = embeddings_norm @ embeddings_norm.T
    
    candidates = []
    for i in range(len(tickers)):
        sims = sim_matrix[i].copy()
        sims[i] = -1  # exclude self
        top_j = np.argsort(sims)[::-1][:top_k]
        for j in top_j:
            if sims[j] >= min_cos_sim and j > i:  # avoid duplicates
                candidates.append((tickers[i], tickers[j]))
    return candidates
```

### Cost Model

| Universe | Pairs | Stage 1 (embeddings) | Stage 2 (LLM scoring) | Total |
|----------|-------|---------------------|----------------------|-------|
| 30 stocks | 435 | $0.000006 | $0.07 (gpt-4o-mini) | ~$0.07 |
| 100 stocks | 4,950 | $0.00007 | ~$0.74 | ~$0.74 |
| S&P 500 | 124,750 | $0.0018 | ~$19 → pre-filter to ~500 | ~$0.08 |

**Key**: text-embedding-3-small costs $0.02/1M tokens. A 100-word company description = ~150 tokens. 500 companies = ~$0.0015 total for embeddings. The LLM scoring step (gpt-4o-mini at ~$0.15/1M input tokens) dominates — pre-filter to top-10 similarity candidates per stock to reduce from 124,750 → ~2,500 candidate pairs before LLM scoring.

Monthly rescoring for a 100-stock universe: **<$1/month** at gpt-4o-mini rates.

### H316 Design (Moira-inspired, our universe)

**Hypothesis**: LLM semantic pair selection (GPT-4o-rated link_strength ≥ 6) on S&P 500 stocks produces OOS Sharpe > 1.0 using z-score entry/exit execution.

| Design choice | Value | Reason |
|---------------|-------|--------|
| Universe | Top 200 S&P 500 by market cap | Sufficient pair candidates, liquid enough for monthly rebalance |
| Selection | Two-stage: embedding pre-filter → GPT-4o-mini scoring | Reduces cost 50× vs scoring all pairs |
| Min link_strength | 6/10 | Below this, rationale becomes "they're both large-caps" |
| Pair limit | Top 15 pairs by link_strength | Controls concentration |
| Execution | Rolling 60d z-score, entry ±2σ, exit 0.5σ | Validated from H152 parameter search |
| Hedge ratio | Rolling 120d OLS | Kalman showed too-fast beta decay in our tests |
| Pair refresh | Monthly (after scoring) | Balances cost vs stale pairs |
| IS | 2015–2020 | Avoids early-period LLM data issues |
| OOS | 2021–2026 | Includes COVID recovery, AI boom, rate hike |
| Gate | OOS Sharpe > 1.0 AND Corr-SPY < 0.35 | Must be both profitable and diversifying |

**Critical validation step** (from BlindTrade arXiv:2603.17692):
Before running the full backtest, verify the LLM signal is genuine:
- Test: does anonymized-ticker LLM scoring produce alpha?
- Control: does random-shuffled link_strength produce ~0 alpha?
- If both pass: signal is genuine, not memorization of historical ticker performance

**Key structural advantage over H152–H160**: H152 selected pairs by IS correlation/cointegration. IS cointegration was ANTI-predictive of OOS (correlation reversal at structural breaks). Semantic relatedness is durable — AAPL's relationship to AVGO (Apple's chip supplier) doesn't break when yield curves invert. The LLM is selecting on business fundamentals, not price history.

**Status**: QUEUED (H316). Implementation requires ~200 company descriptions (from 10-K Item 1) + OpenAI API calls. First run estimated at $5–10 for the full description pipeline.

### Valeyre Factor Decomposition for Residual Extraction (arXiv:2412.09394)

**Source**: Valeyre, S. and Aboura, S. (2024/2025). "LLMs for Time Series: an Application for Single Stocks and Statistical Arbitrage." arXiv:2412.09394, updated November 2025.

Key insight: LLM is used to identify the optimal factor loading specification that minimizes the residual's mean-reversion half-life in a pairs spread — not to predict returns directly.

Valeyre (2019) proved trading the factor-residual is mathematically optimal vs. raw L/S when:
- Factor loadings are time-varying (LLM updates them dynamically)
- Residual has shorter half-life than the raw spread

Complementary to Moira (HRL+LLM semantic pair selection):
- **Moira**: select which pairs to trade (semantic similarity via LLM embeddings)
- **Valeyre**: optimize HOW to extract the stationary residual (LLM-guided factor decomposition)

Practical implementation for H316: after Moira selects a pair, run a small LLM prompt with the pair's recent price series and known factor loadings (sector, beta) to select the factor decomposition that minimizes ADF test p-value on the residual. Cost: ~$0.01 per pair per month.


---

## Attention Factors for Statistical Arbitrage (arXiv:2510.11616, Oct 2025)

Epstein, Wang, Choi & Pelger (Stanford) develop a machine learning framework that replaces cointegration-based pair identification with **conditional latent factors learned from firm characteristic embeddings**.

**Core innovation**: Instead of testing for statistical cointegration (which is backward-looking and structurally unstable — the root cause of H307's failure), the system learns which stocks are *similar* from their fundamental and technical characteristics. Two stocks with similar characteristics that diverge in price are identified as mispricings rather than as 'cointegrated pairs.'

**Architecture:**
1. **Attention factor learning**: Firm characteristics (size, momentum, profitability, investment, etc.) are embedded and passed through a sequence model (attention mechanism) to produce conditional latent factors
2. **Mispricing detection**: Stocks are compared cross-sectionally within their learned factor groupings; deviation from the group constitutes the arbitrage signal
3. **Joint optimization**: Factor identification and arbitrage strategy formation are jointly optimized, with transaction costs included in training (not as an afterthought)

**Key Results (large-cap US equities, 24-year OOS period):**
- Gross OOS Sharpe ratio: **>4.0**
- Net-of-transaction-costs OOS Sharpe ratio: **2.3**
- Weaker individual factors meaningfully contribute when combined — no single dominant factor

**Why This Directly Addresses H307's Root Cause:**

| H307 failure mode | Attention Factors approach |
|-------------------|---------------------------|
| Cointegration tests: IS passes, OOS fails (structural breaks) | Characteristic similarity: learned from recent data, adapts as fundamentals change |
| Static pair identity (same pairs throughout) | Dynamic groupings: firm characteristics change → pair identity updates monthly |
| No economic grounding for why ETF pairs should cointegrate | Characteristic embedding = economic similarity (same sector, size, profitability regime) |

**H401 Candidate Design (attention-based pairs on H198):**
- Universe: H198 30 large-cap stocks
- Factor inputs: IMOM6, MOM60, LowVol, IMOM12 (existing confirmed signals) + fundamentals (PE, ROE, sector) from FMP
- Method: For each stock, find the K=2 most similar stocks by characteristic embedding; trade deviation from the group
- Expected: OOS Sharpe >1.174 (H198 baseline); Corr(SPY) lower than momentum (stat-arb is market-neutral)
- IS: 2013-2020; OOS: 2021-2026
- Cost: No LLM calls needed — pure ML with PyTorch; ~$0 to run

**Code**: No public implementation released. Requires: PyTorch for attention layers, sklearn for characteristic preprocessing, alphalens-reloaded for factor evaluation. See `factor-models.md` for cross-sectional factor construction code.

**Note**: This methodology is complementary to the semantic LLM approach (H316 Moira). Attention factors use *price/fundamental characteristics*; H316 uses *textual similarity*. The two could be combined: attention factors for initial pair grouping, LLM semantic filter for final pair confirmation.

---

## ML Correlation Forecasting for Pair/Basket Selection (arXiv:2601.04602)

Fanshawe, Masih, Cameron (Jan 2026) proposed a Temporal-Heterogeneous Graph Neural Network (TH-GNN) for S&P 500 equity correlation forecasting (OOS 2019-2024). The model combines:
- **Transformer temporal encoder** — captures non-stationary time dependencies in returns
- **Edge-aware graph attention network** — propagates cross-asset information using sector relationships
- **Features:** Daily returns, technical indicators, sector data, previous correlations, macroeconomic signals
- **Target:** Residual deviations from rolling historical baselines in Fisher-z space

**Key results:** Out-of-sample correlation forecasting error meaningfully reduced vs rolling-window baselines. Forward-looking correlations produce "adaptable and economically meaningful baskets, particularly during periods of market stress."

**Why this matters for pairs trading:**
H246/H307 both failed because IS cointegration was INVERSELY predictive of OOS co-movement (structural breaks SVB 2023, gold-silver decoupling). The TH-GNN replaces backward-looking cointegration with forward-looking ML correlation — specifically designed to handle structural breaks via the GNN's adaptive edge-weighting.

**Architecture blueprint for H401 (Attention Factors):** H401 proposed semantic embedding similarity to replace cointegration. TH-GNN offers a complementary quantitative path — sector graph structure + temporal encoder instead of semantic proximity alone.

**Implementation path:** PyTorch Geometric + rolling-window training on S&P 500 daily returns. Pairs selected by top-decile predicted correlation stability (low predicted rolling correlation variance = stable pair).

**See also**: H246 (NOT CONFIRMED, cointegration structural breaks), H307 (NOT CONFIRMED, Johansen cointegration ETF pairs), H401 (staged, Attention Factors stat-arb).

---

## Moira: Hierarchical RL + LLM for Pairs Trading (May 2026)

**Source**: arXiv:2605.01954 — "Moira: Language-driven Hierarchical Reinforcement Learning for Pair Trading" (May 3, 2026)

### Why This Matters for H316 (LLM Pairs STUB)

H307 showed that Johansen cointegration IS selection is anti-predictive of OOS performance — structural breaks destroy statistical relationships. Moira proposes an alternative: use LLMs for **semantic** pair selection based on business relationships, then RL for execution.

### Architecture

Two-level hierarchy:
1. **High level (LLM as pair selector)**: Selects which assets to pair using textual reasoning about business similarity, supply chain relationships, competitive dynamics. No gradient updates — uses "prompt updates" from trajectory-level feedback.
2. **Low level (RL executor)**: Learns entry/exit timing conditioned on the selected pair. Gets episode-level feedback for credit assignment.

**Key advantage over cointegration**: LLM selection is based on durable business logic (A and B compete for the same customers) rather than historical price correlation (which breaks post-regime-change). H307's root failure was that IS cointegration has no predictive power for OOS stability.

### Caveats
- No Sharpe numbers available in abstract; paper claims "consistent improvements over traditional and LLM-based baselines"
- Long-short execution requires margin; current paper account is long-only
- Requires OpenAI API for LLM pair-selection step

### Recommended Path for H316
- Replace Johansen cointegration step with LLM business-similarity scoring (Moira's high-level LLM)
- Use Moira's hierarchical structure: LLM selects pairs monthly, RL or rule-based logic handles daily entries
- Universe: H198 30-stock NASDAQ + 30 peers from same industry group (not ETFs — ETF universe too diversified for pair logic)
- See also H316 STUB, H307 NOT CONFIRMED (structural breaks), H401 (Attention Factors stat-arb)

---

## Attention Factors for Statistical Arbitrage (Oct 2025, OOS Sharpe 4.0/2.3 net)

**Source**: arXiv:2510.11616 — "Attention Factors for Statistical Arbitrage" — accepted at 6th ACM ICAIF (peer-reviewed)

### Method
- Learn **conditional latent factors** from firm characteristic embeddings using attention mechanisms
- Joint optimization of factor identification + arbitrage trading strategy
- Apply sequence models to residual portfolios to detect pricing signals
- Account for transaction costs explicitly in optimization objective

### Key Results
- **Gross OOS Sharpe: 4.0+** on large U.S. equities
- **Net OOS Sharpe: 2.3** after transaction cost modeling
- **Study horizon**: 24 years (longest empirical validation in class)

### Key Insight: Weak Factors Matter
> "Weak factors are important for arbitrage trading" — even modest predictors contribute to strategy profitability when properly attention-weighted.

This validates the OB filter philosophy (H345/H346): regime-conditional signal activation turns weak unconditional factors into strong conditional ones.

### Connection to Production Pipeline
- Net Sharpe 2.3 is below our H041a/H026/H045 composite (4.158) but well above most stat-arb benchmarks
- The firm characteristic embedding approach directly extends our alpha101 signals (H215/H217/H228)
- Attention weighting of weak factors = principled version of IC-weighted composite idea (H406)
- H411 concept: attention-weighted alpha101 signals on H198 universe (gate OOS Sharpe > 4.068)
