---
title: AI-Driven Alpha Factor Discovery
added: 2026-07-01
category: algorithms
related: factor-models.md, momentum-strategies.md, multi-agent-llm-trading.md
hypotheses: H347, H349, H288, H352
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
