---
title: AI-Driven Alpha Factor Discovery
added: 2026-07-01
updated: 2026-07-08
category: algorithms
related: factor-models.md, momentum-strategies.md, multi-agent-llm-trading.md
hypotheses: H347, H349, H288, H352, H365, H380, H381, H382, H383, H384
---

# AI-Driven Alpha Factor Discovery

Automated alpha mining pipelines that use LLMs, evolutionary algorithms, and deep learning to discover novel quantitative factors. Relevant to queued hypotheses H347 (Attention Factors), H349 (QuantaAlpha), H288 (LLM-DSL Factor Discovery), and H352 (TreEvo).

---

## Taxonomy

Two independent axes define the design space:

| Automation | Interpretability |
|---|---|
| Fully automated neural (Attention Factors) → LLM + evolutionary (TreEvo, QuantaAlpha) → human-in-loop agentic (Hubble, Constrained DSL) | Attention map (moderate) ← symbolic formulas (high: TreEvo, DSL) → neural weights (low) |

**Key insight:** symbolic/DSL methods are more audit-friendly for production and avoid "black box" regulatory concerns; neural methods achieve higher raw Sharpe but require GPU infrastructure.

---

## Method 1 — Attention Factors (H347)

**Source:** arXiv:2510.11616 | Epstein, Wang, Choi & Pelger (Stanford) | Oct 2025 | Accepted ACM ICAIF 2025

### Algorithm

Conditional latent factors learned via attention over firm characteristic embeddings. One-step joint optimization of factor structure + trading policy.

- **Characteristic embedding:** X̃_t = X_t W^K (M×d reduction over 39 firm characteristics)
- **Factor weights:** ω^F_{t-1} = Softmax(Q X̃^T_t / √d), Q = learned query matrix
- **Time-series module:** LongConv (linear complexity via FFT) on factor residuals
- **39 characteristics:** past returns, value, investment, profitability, intangibles, trading frictions

### Results (US large-cap 500, 1998–2021)

| Metric | Value |
|--------|-------|
| OOS Sharpe (gross) | >4.0 |
| OOS Sharpe (net, 5bp) | 2.3 |
| Annualized return (net) | ~16% |
| Market correlation | ~0.0 (market-neutral by construction) |

**Key insight:** "Weak factors" (rank 10+) capture important local dependency patterns — do NOT restrict to top-K prematurely.

### Implementation Requirements

- Framework: PyTorch
- Data: CRSP daily returns + Compustat fundamentals (rank-normalized), 8-year rolling window
- Compute: GPU-intensive (paper: 5× NVIDIA RTX A6000); feasible on a single RTX 3090 with reduced universe
- No recurring API cost

### Fit for Our Universe

- **Excellent fit** on paper: tested on 500-stock US large-cap, exact overlap with H198 extension universe
- **Caveat:** academic data sources (CRSP/Compustat). Approximation path: 39 characteristics via yfinance + EDGAR XBRL (coverage ~80% for large-cap). Monthly rebalance compatible (model retrains annually, signals update monthly).

---

## Method 2 — QuantaAlpha: Trajectory-Level Evolutionary LLM Mining (H349)

**Source:** arXiv:2602.07085 | Han et al. (Tsinghua/Peking/CMU/HKUST) | Feb 2026 v3  
**GitHub:** https://github.com/QuantaAlpha/QuantaAlpha  
**Install:** `pip install quantalpha`

### Algorithm

Treats factor mining as a trajectory optimization problem. Each "trajectory" is a sequence of hypothesis → feature engineering → portfolio test decisions. Evolutionary operators work at the trajectory level (not just individual factors), enabling reuse of validated patterns.

**Evolutionary operators:**
- **Trajectory mutation:** identify suboptimal decision point → replace with alternative branch
- **Trajectory crossover:** graft high-reward segment from a different trajectory
- **Complexity penalty:** limits factor depth, penalizes correlation with existing factors (anti-crowding)

### Results

| Market | Metric | Value | Timeframe |
|--------|--------|-------|-----------|
| CSI 300 | IC | 0.1501 | In-sample |
| CSI 300 | ARR/MDD | 27.75% / 7.98% | – |
| S&P 500 transfer | Cumulative excess return | ~19.1% | 4-year |

### Cost & Complexity

- LLM API: ~$5–20 per factor discovery session (GPT-5 class model; `$OPENAI_API_KEY` available)
- Wall-clock: 2–4 hours per search round
- Caveat: 19.1% cumulative over 4 years = ~4.75% annualized excess return on S&P 500 transfer; competitive but not extraordinary

### Implementation Sketch

```python
pip install quantalpha

from quantalpha import AlphaEvolution

searcher = AlphaEvolution(
    api_key=os.environ["OPENAI_API_KEY"],
    universe="SPX500",          # or custom yfinance ticker list
    lookback_years=4,           # IS window
    rounds=3,                   # trajectory evolution rounds
    complexity_penalty=0.3      # anti-overfit control
)
factors = searcher.run()        # returns top-K factor expressions
```

---

## Method 3 — Constrained LLM-DSL Factor Discovery (H288)

**Source:** arXiv:2604.26747 | Huang et al. (HKUST) | Apr 2026

### Algorithm

Sequential hypothesis search with strict reproducibility protocol: LLM proposes factors in a restricted point-in-time DSL (no lookahead, no arbitrary code) → deterministic engine evaluates → LLM interprets results → iterate. Ridge regression combines surviving factors.

### DSL Grammar (for equity adaptation)

```
Base inputs: open, high, low, close, volume, VWAP, log_ret,
             rel_vol, realized_vol, price_to_MA, high_low_range
Cross-sectional: percentile_rank(X), z_score(X)
Time-series:     lag(X, n), rolling_mean(X, n), rolling_std(X, n),
                 diff(X, n), pct_change(X, n)
Nonlinear:       log(X), abs(X), clip(X, lo, hi)
Combination:     weighted_sum([f1, f2, ...], [w1, w2, ...])
Forbidden:       forward-looking lookups, arbitrary Python
```

### Results (crypto original; equity adaptation needed)

| Metric | Value |
|--------|-------|
| Pure OOS Sharpe (crypto L/S) | 1.55 |
| Annualized return | 44.55% |
| OOS window | 2024–2026 |
| Transaction cost | 5bp one-way |

**Equity adaptation:** redesign DSL grammar for US large-cap equity characteristics; retrain IS on 2020–2022; test OOS 2023+. Expected OOS Sharpe lower (~0.8–1.2) given more crowded equity alpha.

### Cost & Complexity

- LLM API: ~$10–30 per session (5 rounds × 3–5 queries)
- Wall-clock: 4–8 hours
- Key strength: audit trail of all failed hypotheses; no overfitting from arbitrary code generation

---

## Method 4 — TreEvo: Tree-Structured Thought Evolution (H352 candidate)

**Source:** arXiv:2508.16334 | Ren et al. | Aug 2025 (v2 May 2026)

### Algorithm

Represents each factor as a hierarchical **tree-structured thought** rather than flat text. Evolutionary operators (crossover, mutation-R/I/F, pruning) act on tree nodes. Eliminates LLM positional bias present in flat-prompt factor evolution.

**Example tree:**
```
Root: Momentum Strength
├─ Extreme Intraday Moves
│  ├─ Large Upward Moves (Potential Overreactions)
│  └─ Large Downward Moves
├─ Prior Day Price Direction
├─ Volume Anomalies
│  ├─ Spikes in Intraday Volume
│  └─ Volume vs. 5-Day Average
└─ Combine into Unified Factor
```

**Mutation variants:**
- Mutation-R (p=0.4): full tree replacement (diversity)
- Mutation-I (p=0.4): internal node replacement (local refinement)
- Mutation-F (p=0.2): leaf parameter tuning (fine-tuning)
- Pruning: remove redundant sub-trees

### Results (US SPX, tested alongside CSI300/500/NDX)

| Market | IC | RankIC | vs. Best Baseline |
|--------|----|--------|-------------------|
| CSI 300 | 0.0308 | 0.0349 | +1.99% vs EoH |
| SPX | 0.0317 | 0.0355 | +10% vs EoH |
| NDX | 0.0285 | 0.0316 | +12.2% vs ReEvo |

**Efficiency:** 200 evaluations (vs. 40k–50k for genetic programming baselines). Wall-clock: **20 minutes** per session.

**Ablation finding:** tree-structure contribution (+23.98% IC gain) > operator design (+10.19% IC gain). The hierarchical representation is the key innovation.

### Cost & Complexity

- LLM API: ~$3–10 per session (200 evaluations, batched)
- Wall-clock: **20 min** — best fit for nightly automated discovery
- Compatible LLMs: Qwen3-Max, DeepSeek V3, Gemini 3, GPT-5.1

### Implementation Sketch

```python
# TreEvo is not yet packaged; implement from arXiv:2508.16334
# Core loop:

def treevo_session(universe, is_data, llm_client, n_generations=5, pop_size=10):
    population = [generate_initial_tree(llm_client) for _ in range(pop_size)]
    for gen in range(n_generations):
        scored = [(tree, evaluate_ic(tree, is_data)) for tree in population]
        scored.sort(key=lambda x: x[1], reverse=True)
        elite = scored[:pop_size//2]
        new_pop = []
        for parent1, parent2 in zip(elite[::2], elite[1::2]):
            child = crossover_trees(parent1[0], parent2[0], llm_client)
            child = mutate_tree(child, llm_client, p_R=0.4, p_I=0.4, p_F=0.2)
            new_pop.append(child)
        population = [t for t, _ in elite] + new_pop
    return population[0]  # best tree-factor
```

---

## Method 5 — Hubble: AST Sandbox + Dual-Channel RAG (wiki reference)

**Source:** arXiv:2604.09601 | Shi et al. | Mar 2026

### Algorithm

Production-focused pipeline combining:
- **AST sandbox:** validates all LLM-proposed factors before execution (no crashes, no lookahead)
- **Dual-channel RAG:** retrieves successful factor templates AND negative examples (failed factors + reasons)
- **Family-aware selection:** penalizes redundancy within factor families; separate per-family robustness reporting

### Results (US 500-stock, OOS Jun 2025 – Mar 2026)

- Range factors: **positive OOS** (Rank IC significant)
- Volatility factors: **positive OOS** (Pearson IC material)
- Trend factors: **decayed OOS** (best IS, worst OOS — key regime signal)
- Crash rate: **0%** (AST sandbox)

**Key insight:** family-aware tracking identifies which factor types are decaying — e.g., trend factors become crowded while range/volatility factors remain robust.

### Cost

- LLM API: ~$25–50 per session (3 rounds, 104 candidates)
- Wall-clock: 3–6 hours

---

## Comparison Summary

| Method | OOS Sharpe (Equity) | Wall-Clock | API Cost | GPU? | Fit |
|--------|--------------------|-----------|---------|----- |----|
| Attention Factors (H347) | 2.3 net (500-cap) | Hours | None | ✓ Required | Excellent |
| TreEvo (H352) | 0.0317 IC on SPX | **20 min** | $3–10/run | ✗ | Excellent |
| QuantaAlpha (H349) | ~4.75% ann. excess | 2–4h | $5–20/run | ✗ | Good |
| Hubble | Positive OOS range/vol | 3–6h | $25–50/run | ✗ | Excellent |
| Constrained DSL (H288) | 1.55 Sharpe (crypto) | 4–8h | $10–30/run | ✗ | Moderate |

---

## Implementation Roadmap

| Phase | Action | Cost | Priority |
|-------|--------|------|----------|
| 1 (immediate) | Run H349 (QuantaAlpha pip install) | $15 | High — `pip install quantalpha` ready |
| 2 (next) | Implement TreEvo loop (H352) — 20 min per run | $5 | High — fast iteration |
| 3 | H288 DSL equity adaptation | $20 | Medium — requires DSL grammar redesign |
| 4 | H347 Attention Factors | GPU cost | Low — needs GPU infra |

---

## Survivorship Bias Caveats

- **Attention Factors:** 500-stock universe from CRSP — includes delisted stocks; our 30-stock yfinance universe has survivorship bias (see survivorship-bias.md)
- **QuantaAlpha:** S&P 500 transfer tested; 19.1% cumulative ≈ 4.75% annualized — includes favorable 2022–2026 period; beware post-paper decay
- **TreEvo:** 200 evaluations is a small sample; paper averages 5 seeds; single-seed runs have high variance
- **Hubble:** 3-month OOS window (2025-06–2026-03) is very recent but also very tight

---

## Cross-References

- H347 (Attention Factors) → PyTorch attention model on H198 30-stock, IS 2000–2015
- H349 (QuantaAlpha) → `pip install quantalpha`, OpenAI API, H198 universe
- H288 (LLM-DSL) → equity DSL adaptation of arXiv:2604.26747, IS 2020–2022
- H352 (TreEvo) → implement arXiv:2508.16334 loop, 20 min per session, $3–10 cost
- H380 (Cross-Market Alpha191) → 17/168 Alpha191 signals survive LASSO on S&P500 (arXiv:2601.06499, Jan 2026); augment H198 with microstructure/volume signals
- H381 (AlphaLogics) → market-logic-driven 3-agent mining, S&P500 validated (arXiv:2603.20247, Mar 2026); initialize from hypothesis-log.md
- H382 (FactorEngine) → program-level dual-mode LLM+BayesHPO, knowledge-infused bootstrap (arXiv:2603.16365, Mar 2026); ingest wiki as experience KB
- [LLM Alpha Mining Systems 2026](../../ai-industry/llm-alpha-mining-systems-2026.md) — ecosystem overview, regime-adaptive methods, AlphaLogics/FactorEngine/Alpha191 transfer
- [Factor Models](factor-models.md) — academic factor foundations (FF5, q-factor)
- [Multi-Agent LLM Trading](multi-agent-llm-trading.md) — broader LLM trading agent landscape
- [Machine Learning for Trading](../tools/ml-for-trading.md) — FinAgent, Alpha-GPT, LLM ideation gap

---

## Method 6 — FactorMiner: Self-Evolving Agent with Experience Memory (H365 candidate)

**Source:** arXiv:2602.14670 | Wang et al. (Tsinghua/Peng Cheng Lab) | Feb 16, 2026  

### Algorithm

FactorMiner addresses a specific scaling failure in alpha mining: as the factor library grows, naive LLM generation produces increasingly redundant signals. The fix is **structured Experience Memory** that distills prior search trials into actionable constraints.

**Ralph Loop paradigm:**
1. **Retrieve** — query Experience Memory for relevant successful patterns and failed experiments
2. **Generate** — LLM proposes new factors guided by memory priors
3. **Evaluate** — deterministic IC/factor testing pipeline assesses generated factors
4. **Distill** — results (both successes and failures) update Experience Memory

**Memory structures:**
- **Success patterns**: factor templates that produced IC > threshold, stored with context (market regime, universe size, lookback)
- **Failure constraints**: factors that failed with reasons (overcrowding, data snooping, regime-dependent)
- **Modular Skill Architecture**: encapsulates systematic evaluation as reusable tools

### Key distinction from QuantaAlpha and TreEvo

| Feature | QuantaAlpha | TreEvo | FactorMiner |
|---------|-------------|--------|-------------|
| Structure | Trajectory evolution | Tree structure | Experience Memory |
| Anti-redundancy | Complexity penalty | Pruning | Memory-guided exclusion |
| Session cost | $5-20 | $3-10 | ~$5-15 |
| Wall-clock | 2-4h | 20min | 1-3h |

### Fit for Our Universe
- Tested across multiple assets and markets; "competitive performance with diverse library of high-quality factors"
- Memory mechanism specifically addresses the H349/H352 limitation: generating varied factors after the first session is hard without explicit failure tracking
- No GPU required; OpenAI API compatible

---

## Evaluation Tool — AlphaEval: Backtest-Free Alpha Screening (KDD 2026)

**Source:** arXiv:2508.13174 | KDD 2026 | GitHub: https://github.com/LeoDingggg/AlphaEval  

### What It Solves

For all alpha mining sessions (H288/H349/H352/H365), the bottleneck is sequential backtesting: each candidate factor requires running a full return attribution before you know if it's worth keeping. AlphaEval replaces this with a parallelizable, backtest-free screening pass.

### Five Evaluation Dimensions

| Dimension | What it measures |
|-----------|------------------|
| Predictive power | IC/RankIC on holdout period |
| Stability | IC volatility across rolling windows |
| Robustness | Performance under market perturbations (synthetic stress) |
| Financial logic | LLM-judged alignment with known factor premia |
| Diversity | Pairwise factor correlation within candidate set |

### Usage Pattern

```python
# Install
# pip install (see github.com/LeoDingggg/AlphaEval for current install)

# In any alpha mining session (H288/H349/H352):
# 1. Generate N candidate factors (e.g., 20 TreEvo outputs)
# 2. Run AlphaEval screening — parallel, ~5x faster than sequential backtest
# 3. Keep top-K by composite score
# 4. Run full backtests only on survivors

# Example workflow
from alphaeval import AlphaEvaluator

evaluator = AlphaEvaluator(
    universe='SPX500',        # or yfinance ticker list
    is_window=('2015', '2022'),
    oos_window=('2022', '2025'),
    dimensions=['ic', 'stability', 'diversity']  # skip 'logic' for speed
)

results = evaluator.evaluate(candidate_factors)  # list of factor expressions
top_k = results.rank('composite').head(5)
```

### Integration with Current Pipeline
- Run AlphaEval screening after each TreEvo/QuantaAlpha session before committing to full backtests
- Use diversity dimension to enforce low inter-factor correlation (natural anti-crowding)
- Financial logic dimension can replace manual review for obvious failures

---

## Updated Comparison Summary (including FactorMiner)

| Method | OOS Sharpe (Equity) | Wall-Clock | API Cost | GPU? | Fit |
|--------|--------------------|-----------|---------|----- |----|
| Attention Factors (H347) | 2.3 net (500-cap) | Hours | None | Required | Excellent |
| TreEvo (H352) | 0.0317 IC on SPX | **20 min** | $3–10/run | No | Excellent |
| QuantaAlpha (H349) | ~4.75% ann. excess | 2–4h | $5–20/run | No | Good |
| **FactorMiner (H365)** | Competitive (multi-market) | 1–3h | $5–15/run | No | **Excellent (scaling)** |
| Hubble | Positive OOS range/vol | 3–6h | $25–50/run | No | Excellent |
| Constrained DSL (H288) | 1.55 Sharpe (crypto) | 4–8h | $10–30/run | No | Moderate |

**AlphaEval** sits across all methods as a pre-screening layer: run after any session, before committing to full backtests.

---

## Method 7 — Cross-Market Alpha Transfer: Alpha191 → S&P 500 (H380)

**Source:** arXiv:2601.06499 | Du, Walter & Ulrich (KIT) | January 2026  
**GitHub:** No official repo — Alpha191 library publicly documented; implementation via OHLCV data only  
**Data requirement:** Daily OHLCV (yfinance sufficient — no fundamentals needed)

### Background

The **Alpha191 library** was originally developed for China's A-share market: 191 short-term price-volume signals targeting intraday momentum, reversal, and microstructure patterns in a retail-dominated, high-frequency environment. The signals use only OHLCV data and are computed at daily frequency.

**Hypothesis:** these signals should partially transfer to US large-cap markets because the underlying microstructure phenomena (short-term liquidity dynamics, volume imbalances, intraday price pressure) are universal, even if the magnitudes differ.

### Methodology

Double-Selection LASSO — two-stage variable selection that identifies Alpha191 factors with **incremental** explanatory power over and above the established US factor zoo:

```python
# Stage 1: standard LASSO on Alpha191 factors alone
# Stage 2: partial-out US fundamental factors (151 control variables)
# Keep factors significant at 5% in both stages

from sklearn.linear_model import LassoCV
import numpy as np

def double_selection_lasso(X_alpha191, X_controls, y_returns, cv=5):
    """
    X_alpha191: (n_months x 191) matrix of Alpha191 factor values
    X_controls: (n_months x 151) established US factor values
    y_returns:  (n_months,) next-month cross-sectional returns
    Returns: mask of surviving Alpha191 factor indices
    """
    # Stage 1: factor selection
    lasso1 = LassoCV(cv=cv).fit(X_alpha191, y_returns)
    selected_1 = np.abs(lasso1.coef_) > 0

    # Stage 2: incremental selection controlling for established factors
    X_residual = X_alpha191[:, selected_1] - X_controls @ np.linalg.lstsq(
        X_controls, X_alpha191[:, selected_1], rcond=None)[0]
    lasso2 = LassoCV(cv=cv).fit(np.hstack([X_controls, X_residual]), y_returns)
    n_controls = X_controls.shape[1]
    selected_2 = np.abs(lasso2.coef_[n_controls:]) > 0

    surviving_indices = np.where(selected_1)[0][selected_2]
    return surviving_indices
```

### Key Results

| Finding | Detail |
|---------|--------|
| Total Alpha191 factors | 191 (23 excluded: unstable time series on US data) |
| Factors tested on S&P 500 | 168 |
| **Survivors after double-LASSO** | **17 (at 5% significance)** |
| Period tested | 2002–2022, US S&P 500 large-cap |
| Surviving factor domains | Volume & Flow; Mean Reversion; Trend & Momentum; Volatility & Risk; Liquidity & VWAP; Price Action |

**Critical finding:** the 17 surviving signals are primarily **microstructure-based** (volume-flow, liquidity, VWAP deviations) — NOT the obvious momentum/reversal signals. These are orthogonal to our current H198 6-1m price momentum.

### Fit for H198 Universe

The H198 30-stock large-cap universe (AAPL, MSFT, NVDA, etc.) has daily OHLCV data available via Polygon.io (`$POLYGON_API_KEY`) at no additional cost. The 17 surviving signals are computable from OHLCV alone. Implementation path:

```python
# Alpha191 signal construction example (general pattern)
# All 191 signals use daily OHLCV; Alpha191 numbering convention: alpha_NNN

def alpha_001(close, volume, n=5):
    """Mean-reversion: rank(-1 * sum(rank(delta(log(volume), 1)) * rank((close/shift(close,1)-1)), n))"""
    log_vol_change = np.log(volume).diff(1).rank(pct=True)
    return_rank = (close / close.shift(1) - 1).rank(pct=True)
    combined = (log_vol_change * return_rank).rolling(n).sum()
    return -combined.rank(pct=True)

# For H380: implement the 17 survivors from Du et al. appendix
# Use as composite signal on top of H198 6-1m momentum ranking
```

**Gate**: OOS Sharpe > 1.174 (H198 baseline). IS: 2013–2020, OOS: 2021–2026.

---

## Method 8 — AlphaLogics: Market Logic as the Interpretability Layer (H381)

**Source:** arXiv:2603.20247 | Weng, Zhang, Wang & Xia | March 2026  
**Cost:** ~$15–40 per discovery session (OpenAI API, `$OPENAI_API_KEY` available)  
**Wall-clock:** 2–4 hours per session

### Algorithm

AlphaLogics introduces the **market logic** abstraction layer — an explicit, human-readable causal hypothesis (e.g., "momentum persists because of investor underreaction to gradual information diffusion") that constrains and guides factor code generation.

**Three-agent architecture:**

| Agent | Role |
|-------|------|
| Market Logic Mining Agent | Reverse-engineers market logics from existing confirmed factors (e.g., from hypothesis-log.md: "6-0m no-skip works on large-cap tech because J-T reversal convention is inapplicable in high-persistence regimes") |
| Factor Generation Agent | Uses market logics to propose new factor code; runs backtest-feedback loop; rejects factors that contradict their stated logic |
| Logic Refinement Agent | Updates logic library based on factor outcomes; prunes logics whose generated factors consistently fail |

**Key distinction from all other methods:** the only system that explicitly models *why* a factor should work. Factor proposals without causal rationale are rejected before backtesting — reducing the multiple-testing burden.

### Implementation Sketch

```python
# AlphaLogics not yet packaged; implement from arXiv:2603.20247

import openai

class MarketLogicLibrary:
    def __init__(self, hypothesis_log_path: str):
        """Initialize from our confirmed hypothesis results."""
        self.logics = self._extract_from_log(hypothesis_log_path)

    def _extract_from_log(self, path):
        # Parse CONFIRMED entries from hypothesis-log.md
        # Extract: (hypothesis_number, signal, rationale, oos_sharpe)
        # e.g., ("H198", "6-1m momentum", "cross-sectional persistence", 1.174)
        pass

    def retrieve_relevant(self, candidate_signal: str, top_k=3):
        """Semantic search for relevant prior market logics."""
        pass


class AlphaLogicsSession:
    def __init__(self, logic_library: MarketLogicLibrary, universe: list):
        self.library = logic_library
        self.universe = universe

    def generate_and_test(self, n_rounds=3):
        for _ in range(n_rounds):
            logic = self._mining_agent_propose()
            factor_code = self._generation_agent_code(logic)
            ic = self._backtest(factor_code)
            self._refinement_agent_update(logic, factor_code, ic)

    def _mining_agent_propose(self):
        logics = self.library.retrieve_relevant("momentum augmentation")
        prompt = f"Given prior logics: {logics}\nPropose a new market logic for undiscovered alpha."
        return openai.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}]
        ).choices[0].message.content
```

### Our Fit

AlphaLogics' market logic concept maps directly onto our hypothesis format — each H### entry has a `**Hypothesis**` and `**Source**` rationale. Initialization from `hypothesis-log.md` (380+ experiments) gives the mining agent a rich prior of which causal mechanisms work (6-0m > 6-1m: "tech momentum persists through current month") and which fail (MAX×momentum: "adversarial in divergent months").

**Expected output:** 3–5 new candidate factor expressions per session, validated on S&P 500, with explicit economic rationale for each.

---

## Method 9 — FactorEngine: Program-Level Dual-Mode Factor Mining (H382)

**Source:** arXiv:2603.16365 | Lin et al. (Tsinghua lineage, 10 authors) | March 2026  
**Cost:** ~$20–50 per session (LLM proposing code fragments; evaluation runs locally)  
**Wall-clock:** 2–6 hours

### Three Orthogonal Separations

FactorEngine resolves a fundamental design error in prior auto-alpha systems: conflating structural exploration with numerical optimization.

| Concern | FactorEngine's solution | Prior approach |
|---------|------------------------|----------------|
| Logic revision | LLM proposes code structure changes | LLM changes everything |
| Parameter tuning | Bayesian HPO (BoTorch/Ax) | LLM proposes numbers |
| API vs local computation | LLM: code fragments only; all eval local | LLM runs everything |

This separation dramatically reduces API costs (LLM only generates code *structure*; BoTorch finds optimal parameters locally) and improves reproducibility (deterministic parameter search given a code structure).

### Knowledge-Infused Bootstrapping

The key module that makes FactorEngine uniquely suited to our situation:

```python
# FactorEngine bootstrapping pipeline (from arXiv:2603.16365)

class KnowledgeInfusedBootstrap:
    """
    Transforms unstructured research (wiki pages, hypothesis log)
    into executable factor programs.
    """
    def __init__(self, knowledge_sources: list[str]):
        """
        knowledge_sources: list of file paths or text strings
        e.g., ['hypothesis-log.md', 'momentum-strategies.md', 'factor-models.md']
        """
        self.sources = knowledge_sources

    def bootstrap(self) -> list[str]:
        """
        Three-agent pipeline:
        1. Extraction agent: parses financial concepts from knowledge sources
        2. Verification agent: checks logical consistency + data availability
        3. Code generation agent: writes executable factor programs

        Returns: list of verified, executable factor programs
        """
        extracted = self._extraction_agent()     # financial logic units
        verified  = self._verification_agent(extracted)   # feasibility check
        code      = self._codegen_agent(verified)  # Python factor programs
        return code

    def _extraction_agent(self):
        # For hypothesis-log.md: extract (signal_type, lookback, direction)
        # e.g., "6-0m momentum → pct_change(6), ascending rank"
        pass
```

**For our use case:** feed `hypothesis-log.md` as the primary knowledge source. The bootstrap agent extracts the 380+ prior factor experiments — including failure reasons (e.g., "H313 NOT CONFIRMED: sector-neutral removes cross-sectional dispersion on homogeneous large-cap universe") — to avoid re-exploring dead ends.

### Experience Knowledge Base

Unlike QuantaAlpha (trajectory evolution without explicit failure logging), FactorEngine maintains:

```python
class ExperienceKB:
    """Persistent trajectory-aware factor refinement database."""

    def add(self, factor_code: str, direction: str, params: dict,
            ic: float, regime: str, failure_reason: str = None):
        """
        direction: the code structure (e.g., "mean-reversion on VWAP deviation")
        params: Bayesian-optimized hyperparameters
        failure_reason: if IC < threshold, why it failed
        """
        pass

    def query_unexplored(self, current_direction: str) -> list[str]:
        """Return directions not yet tried near current_direction."""
        pass
```

This structure directly addresses the crowding problem in large hypothesis spaces: as we accumulate H380+ experiments, the KB prevents the LLM from re-proposing known-failed directions.

### Updated Comparison Table (all methods)

| Method | Signal Quality | Wall-Clock | API Cost | GPU? | Priority |
|--------|---------------|------------|----------|------|----------|
| TreEvo (H352) | IC 0.0317 SPX | **20 min** | $3–10 | No | **1** |
| Alpha191 transfer (H380) | 17/168 signals survive | Hours (backtest only) | **$0** | No | **2** |
| AlphaLogics (H381) | SPX validated | 2–4h | $15–40 | No | 3 |
| FactorEngine (H382) | Multi-market | 2–6h | $20–50 | No | 3 |
| QuantaAlpha (H349) | 4.75% ann. excess | 2–4h | $5–20 | No | 4 |
| FactorMiner (H365) | Competitive | 1–3h | $5–15 | No | 4 |
| Hubble | Positive OOS (range/vol) | 3–6h | $25–50 | No | 5 |
| Attention Factors (H347) | 2.3 net Sharpe (500-cap) | Hours | None | **Required** | 6 |

Alpha191 (H380) is uniquely cost-effective: zero API cost, uses only OHLCV data already in our Polygon.io subscription, and has published academic validation on the same S&P 500 universe.

---

## Regime-Adaptive Extensions (H383, H384)

Two 2026 papers extend the alpha mining paradigm to handle the non-stationarity problem:

### H383 — HMM + RL Regime-Based Allocation (arXiv:2605.27848)

3-state Gaussian HMM (BIC-selected: Low-Vol, Transitional, High-Vol) combined with an RL allocation policy on SPY/TLT/GLD. The RL policy learns discrete regime-dependent allocation weights, maintaining interpretability while adapting to regime transitions. See full design in staged proposal H383 and [Regime Detection](regime-detection.md). Requires: `hmmlearn`, `stable-baselines3`.

### H384 — ReCAP Continual Learning on H026 (arXiv:2606.00143)

Regime-Adaptive Continual Portfolio management: change-point detection → per-regime DRL policy → policy library → rapid fine-tuning when new regime detected. Avoids catastrophic forgetting of prior regime knowledge. Risk-level HIGH — requires PyTorch + ruptures + SB3 + careful OOS discipline (filtered not smoothed HMM probabilities). See full design in staged proposal H384.


## MadEvolve: Evolutionary LLM Strategy Optimization (arXiv:2605.23007)

**Source**: Kvasiuk, Li, Colegrove, Münchmeyer (May 2026) — 'MadEvolve: Evolutionary Optimization of Trading Systems with Large Language Models'
**Inspired by**: DeepMind's AlphaEvolve (2025)

**Architecture:**
- **Outer loop (LLM code generation)**: LLM generates or mutates candidate trading strategy code (Python)
- **Inner loop (automated evaluation)**: Backtester scores each candidate on Sharpe/profit metrics
- **Evolution**: High-scoring candidates retained; used as seeds for next LLM generation cycle
- **Multi-objective**: jointly evolves (a) feature set, (b) signal generation, (c) execution strategy

**Key results on Bitcoin trading:**
- Significant improvements on all subtasks: feature evolution, component optimization, joint evolution
- Outperforms standalone Claude Code (agentic search baseline) on most tasks
- P-hacking probability rigorously evaluated; results hold under Bonferroni correction

**Comparison to existing H-series approaches:**
| Approach | Mechanism | Status |
|----------|-----------|--------|
| H382 FactorEngine | BayesHPO + knowledge-infused bootstrap from hypothesis-log | PROPOSED |
| H365 QuantaAlpha | Evolutionary framework with crossover + multi-agent | PROPOSED |
| MadEvolve | AlphaEvolve-style LLM code mutation + backtester fitness | NEW |

**Production path for H198 universe:**
Seed MadEvolve with run_h386.py as the base strategy. LLM mutates: feature set (add/remove IMOM variants, window lengths, normalization), ranking logic, portfolio concentration. Backtester = H386 IS fitness. Estimated 50 candidates at $5-15 (haiku rates). Target: find a Var A+ that improves MaxDD further.

---

## EFS: Evolutionary Factor Search (arXiv:2507.17211)

**Source**: Luo, Zhang, Liu (Jul 2025) — 'EFS: Evolutionary Factor Searching for Sparse Portfolio Optimization Using Large Language Models'

**Architecture:**
- LLM generates alpha factor code (Python expressions, like WorldQuant 101 alphas)
- Reformulates portfolio construction as top-m ranking task
- Evolutionary feedback loop: performance-based factor selection + LLM cross-mutation
- Ablation validates: prompt composition, factor diversity, LLM backend choice all matter

**Results (Fama-French + real markets):**
- Significantly outperforms statistical and optimization baselines
- Strongest edge: **larger universes** (100+ stocks) and **volatile conditions**
- US50, HSI45, CSI300 all validated

**Implication for H393+:** EFS-style LLM factor generation could directly produce candidates for the H198 30-stock universe at low cost. The evolutionary loop provides automatic overfitting control via train/test separation built into the fitness function.

**Proposed pipeline:**
1. Use H198 universe (30 large-cap NASDAQ stocks)
2. Seed with existing confirmed factors: IMOM6, MOM60, Amihud ILLIQ
3. LLM generates factor mutations (e.g., partial moments, skewness, downside volatility)
4. IS (2013-2020) fitness → retain top-10 factors
5. Combine top factors in H386-style composite, OOS test on 2021-2026
6. Hypothesis number: H394 (if a new composite clears gate)

---

## Autonomous Factor Investing via Agentic AI (arXiv:2603.14288, March 2026)

**'Beyond Prompting'** (allenh16.github.io/agentic-factor-investing/) — autonomous pipeline for systematic factor investing with three components:

1. **LLM hypothesis generation**: Agents propose factor hypotheses from financial literature and market reasoning (no manual coding).
2. **Rigorous multiple testing**: Applies BH FDR correction and Deflated Sharpe Ratio (DSR) from Harvey-Liu-Zhu — specifically designed to combat the 'factor zoo' overfitting problem that plagues automated search.
3. **OOS signal decay evaluation**: Tracks alpha decay rate post-publication/post-discovery as a quality gate.

**Relevance to our pipeline:**
- H382 (FactorEngine design) should adopt this three-phase structure: generate → test with FDR → evaluate OOS decay.
- Our dream cycle already generates hypotheses (Phase 1) and stages them (Phase 2). Missing: FDR correction across the H-series. With 475+ hypotheses tested, the expected false discovery rate at p<0.05 without correction is ~24 false positives.
- **Action**: Add BH FDR correction to the batch evaluation step when multiple variants of the same hypothesis are tested in the same session (e.g., H411-H418 all tested together = multiple testing family).
- **OOS decay gate**: Add signal_halflife check before promoting any hypothesis to production.

**Cross-ref**: [Multiple Testing & Statistical Significance](../backtesting/multiple-testing.md), [Signal Half-Life](../backtesting/signal-halflife.md), [AlphaCrafter](https://arxiv.org/abs/2605.05580)

---

## Autonomous Factor Investing via Agentic AI (arXiv:2603.14288, March 2026)

**'Beyond Prompting'** (allenh16.github.io/agentic-factor-investing/) — autonomous pipeline for systematic factor investing with three components:

1. **LLM hypothesis generation**: Agents propose factor hypotheses from financial literature and market reasoning (no manual coding).
2. **Rigorous multiple testing**: Applies BH FDR correction and Deflated Sharpe Ratio (DSR) from Harvey-Liu-Zhu — specifically designed to combat the 'factor zoo' overfitting problem that plagues automated search.
3. **OOS signal decay evaluation**: Tracks alpha decay rate post-publication/post-discovery as a quality gate.

**Relevance to our pipeline:**
- H382 (FactorEngine design) should adopt this three-phase structure: generate → test with FDR → evaluate OOS decay.
- Our dream cycle already generates hypotheses (Phase 1) and stages them (Phase 2). Missing: FDR correction across the H-series. With 475+ hypotheses tested, the expected false discovery rate at p<0.05 without correction is ~24 false positives.
- **Action**: Add BH FDR correction to the batch evaluation step when multiple variants of the same hypothesis are tested in the same session (e.g., H411-H418 all tested together = multiple testing family).
- **OOS decay gate**: Add signal_halflife check (wiki/trading/backtesting/signal-halflife.md) before promoting any hypothesis to production.

**Cross-ref**: [Multiple Testing & Statistical Significance](../backtesting/multiple-testing.md), [Signal Half-Life](../backtesting/signal-halflife.md), [AlphaCrafter](https://arxiv.org/abs/2605.05580) (similar multi-agent approach).
