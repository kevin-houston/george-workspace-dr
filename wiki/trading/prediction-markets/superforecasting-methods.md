---
created: 2026-06-11
updated: 2026-06-11
category: prediction-markets
relevance: H185 (PolySwarm/Kalshi nowcasting), calibration framework, LLM forecasting pipeline
---

# Superforecasting Methods

The theoretical and practical foundation for prediction market trading. Covers Philip Tetlock's Good Judgment Project methodology, reference class forecasting, calibration training, LLM forecasting benchmarks, and domain-specific market biases.

---

## Why Superforecasting Matters for Prediction Market Trading

The **Good Judgment Project** (Philip Tetlock, Barbara Mellers, U. Penn) won a US intelligence community forecasting tournament by a wide margin — superforecasters outperformed professional intelligence analysts with classified access by ~30%, and outperformed standard prediction markets on the same questions.

For trading purposes: the edge is **calibration + updating speed**. Markets are often anchored on stale information or systematically biased by domain (see Domain Biases below). A well-calibrated model that updates faster than the market earns the spread.

---

## Core Methodology

### The Outside View First (Reference Class Forecasting)

Before considering any case-specific factors, ask: **"What is the base rate for this class of events?"**

Developed by Kahneman & Tversky. Three steps:
1. Identify a **reference class** — a set of comparable past cases (e.g., "all prior CPI releases where ADP was within 1σ of consensus")
2. Compile the outcome **distribution** across the reference class
3. **Anchor** on that distribution, then adjust for case-specific factors

**Common mistake**: jumping directly to the inside view ("this time the shelter component is lagging more than usual") without anchoring on base rates. Inside view alone produces systematic overconfidence.

**Market application**:
```python
def base_rate_anchor(event_type, historical_df, threshold_col, outcome_col):
    """
    Start with historical base rate before adding case-specific signals.
    
    historical_df: past events with relevant features
    threshold_col: e.g., "did_cpi_beat_estimate"
    outcome_col:   binary outcome variable
    
    Returns: base_rate + confidence interval
    """
    import numpy as np
    from scipy import stats
    
    outcomes = historical_df[outcome_col].values
    n = len(outcomes)
    base_rate = outcomes.mean()
    
    # Wilson confidence interval for proportions
    z = 1.96  # 95% CI
    lower = (base_rate + z**2/(2*n) - z*np.sqrt(base_rate*(1-base_rate)/n + z**2/(4*n**2))) / (1 + z**2/n)
    upper = (base_rate + z**2/(2*n) + z*np.sqrt(base_rate*(1-base_rate)/n + z**2/(4*n**2))) / (1 + z**2/n)
    
    print(f"Base rate: {base_rate:.3f}  [95% CI: {lower:.3f}–{upper:.3f}]  n={n}")
    return base_rate, (lower, upper)
```

### Tetlock's Ten Commandments of Superforecasting

1. **Triage** — focus effort on rewarding (near-term, resolvable, well-defined) questions
2. **Unpack** — decompose questions to expose hidden assumptions; Fermi-ize
3. **Outside view first** — consider the broader reference class before the specific case
4. **Inside view next** — adjust the base rate for genuinely distinctive case features
5. **Update frequently** — revise in small increments proportional to evidence weight
6. **Find merit in opposition** — actively seek out evidence that challenges your current estimate
7. **Probabilistic granularity** — think in precise percentages, not vague qualifiers ("likely" ≠ a number)
8. **Prudent decisiveness** — avoid both overconfidence and indecision; be wrong and correctable
9. **Learn from feedback** — use Brier scores; track calibration curves, not just win rates
10. **Embrace iterative improvement** — forecasting is a skill; deliberate practice improves it

### The CHAMP Checklist (Cognitive Debiasing)

**C**alibration — Am I overconfident? What's the base rate?
**H**umility — What don't I know? What could make me wrong?
**A**ccuracy — What's my track record on similar questions?
**M**ultiple perspectives — What does the opposing view say?
**P**robability — Have I translated my uncertainty into a precise number?

### Bayesian Updating

When new information arrives, update proportionally — not by over-reacting (anchoring) or under-reacting (conservatism bias):

```python
def bayesian_update(prior: float, likelihood_ratio: float) -> float:
    """
    Update a probability given new evidence.
    
    prior: current probability estimate (0–1)
    likelihood_ratio: P(evidence | YES) / P(evidence | NO)
                      >1 means evidence favors YES; <1 favors NO
    
    Example: Prior CPI-beat = 55%. ADP came in hot (+1.8σ above consensus).
    Historical LR for this signal: P(ADP hot | CPI beats) / P(ADP hot | CPI misses) = 2.3
    """
    prior_odds = prior / (1 - prior)
    posterior_odds = prior_odds * likelihood_ratio
    posterior = posterior_odds / (1 + posterior_odds)
    return posterior

# Example: CPI beat probability
p0 = 0.55                             # base rate: CPI beats consensus 55% of the time
lr_adp_hot = 2.3                      # ADP was hot → LR = 2.3
lr_shelter_lag = 0.85                 # shelter lag suggests slight miss → LR = 0.85

p1 = bayesian_update(p0, lr_adp_hot)     # → 0.738
p2 = bayesian_update(p1, lr_shelter_lag) # → 0.706
print(f"Final estimate: {p2:.3f}")        # 70.6% CPI beats
```

**Practical guidance**: Make sure the market has NOT already priced in the signal you're updating on. The edge is in signals the market hasn't incorporated yet.

---

## Calibration Training

### Brier Score (Primary Metric)

The Brier score measures how close your probabilistic predictions were to outcomes:

```
BS = (1/N) × Σ(p_i - o_i)²
```

Where `p_i` is your probability and `o_i` is 1 (occurred) or 0 (did not occur).

| Calibration Level | Brier Score |
|-------------------|-------------|
| Perfect | 0.000 |
| Human superforecasters | 0.150–0.180 |
| Frontier LLMs (2026) | 0.227–0.255 |
| Market consensus | 0.185–0.220 |
| Random / coin flip | 0.250 |
| Always wrong | 1.000 |

**Target for H185 pipeline**: Brier score ≤ 0.18 on economic data questions.

### Expected Calibration Error (ECE)

ECE measures whether your 70% predictions come true 70% of the time. Groups predictions into bins and measures accuracy deviation per bin:

```python
import numpy as np

def expected_calibration_error(probs, outcomes, n_bins=10):
    """
    Lower ECE = better calibrated.
    Human superforecasters: ECE 0.03–0.05
    Best frontier LLMs (KalshiBench 2025): ECE ~0.120 (Claude Opus 4.5)
    """
    probs, outcomes = np.array(probs), np.array(outcomes)
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        bin_prob = probs[mask].mean()
        bin_acc  = outcomes[mask].mean()
        bin_weight = mask.sum() / len(probs)
        ece += bin_weight * abs(bin_prob - bin_acc)
    
    return ece

# Track your model over time
def calibration_report(history_df):
    """history_df must have 'p_yes' and 'outcome' columns."""
    bs = np.mean((history_df['p_yes'] - history_df['outcome'])**2)
    ece = expected_calibration_error(history_df['p_yes'], history_df['outcome'])
    
    # Brier Skill Score vs naive 50% baseline
    bs_naive = np.mean((0.5 - history_df['outcome'])**2)
    bss = 1 - bs / bs_naive  # positive = beats random; 0 = no better than coin flip
    
    print(f"Brier Score: {bs:.4f}  (target ≤ 0.180)")
    print(f"ECE:         {ece:.4f}  (target ≤ 0.050)")
    print(f"BSS vs 50%:  {bss:.4f}  (target > 0)")
    return {"brier": bs, "ece": ece, "bss": bss}
```

### Calibration Practice Resources

| Resource | Type | Notes |
|----------|------|-------|
| [Metaculus](https://www.metaculus.com/) | Live forecasting platform | Tracks Brier scores vs community; great training |
| [Good Judgment Open](https://www.gjopen.com/) | Tournament forecasting | Based on GJP; open to public |
| [Calibration training](https://calibration.city/) | Trivia-based | Targets over/under confidence correction |
| [Prediction Book](https://predictionbook.com/) | Personal tracker | Lightweight Brier-score diary |

**Recommended routine**: Make 5–10 forecasts per week on Metaculus in economic domains. Review calibration monthly. Target ECE < 0.07 before deploying real capital on H185.

---

## LLM Forecasting Benchmarks (2025–2026)

Understanding where LLMs are and aren't useful as components in a prediction market pipeline.

### Performance Hierarchy (2026 state of the art)

```
Frontier LLMs > Human crowd  but  Expert superforecasters > Frontier LLMs
```

Key benchmarks:

| Study | Models Tested | Metric | LLM vs Human |
|-------|--------------|--------|---------------|
| Metaculus eval (arXiv:2507.04562, Jul 2026) | Frontier models | Brier score | Beats general crowd; worse than expert group |
| KalshiBench (arXiv:2512.16030, Dec 2025) | 5 frontier models | ECE | Best ECE 0.120 (Claude Opus 4.5); most underperform base rates |
| PolyBench (arXiv:2604.14199, Apr 2026) | 8 models, 2,400 Polymarket Q | Accuracy | Near-random on general questions; +6% on economic data with FRED context |
| Prediction Arena (arXiv:2604.07355, Mar 2026) | 6 models, real capital | PnL | All models lost money on Kalshi (weather-dominated); −1.1% on Polymarket |

### Where LLMs Add Value (and Where They Don't)

**Strong domains** (LLMs beat market or add to pipeline):
- Economic data release questions (CPI, NFP, FOMC) **with** structured FRED data — +6% accuracy vs market
- Elections **with** structured polling data aggregation
- Synthesizing analyst consensus vs. alternative signals

**Weak domains** (LLMs at or below random):
- Weather/climate outcomes
- Sports (without statistics)
- Geopolitics (without direct intelligence)
- Long-horizon questions (>3 months)

**Key insight from prompt engineering study (arXiv:2506.01578, Jun 2026)**:
- "Small prompt modifications rarely boost forecasting accuracy beyond a minimal baseline"
- Encouraging Bayesian reasoning in prompts **backfires** — it harms performance
- References to base rates yield slight benefits
- Conclusion: use LLMs as **structured signal aggregators** over numerical inputs, not as knowledge bases

### LLM Calibration Problems

From KalshiBench: systematic overconfidence across all tested models.
- When expressing 90%+ confidence → 20–30% error rates
- Enhanced reasoning variants (GPT-5.2-XHigh) showed **worse** calibration (ECE 0.395) despite similar accuracy
- "Scaling and enhanced reasoning do not automatically confer calibration benefits"

**Practical implication**: Use LLM probability estimates as **inputs to a calibration layer** rather than as direct trading signals. Apply isotonic regression or Platt scaling to post-hoc calibrate.

```python
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.isotonic import IsotonicRegression
import numpy as np

class LLMCalibrationLayer:
    """
    Post-hoc calibration layer for LLM probability outputs.
    Train on historical (llm_prob, outcome) pairs, then use to 
    calibrate future LLM estimates before trading.
    """
    def __init__(self):
        self.ir = IsotonicRegression(out_of_bounds='clip')
        self.trained = False
    
    def fit(self, llm_probs: np.ndarray, outcomes: np.ndarray):
        """
        llm_probs: array of LLM probability estimates (0–1)
        outcomes:  array of binary outcomes (0/1)
        """
        self.ir.fit(llm_probs, outcomes)
        self.trained = True
        
    def calibrate(self, llm_prob: float) -> float:
        if not self.trained:
            return llm_prob  # uncalibrated passthrough
        return float(self.ir.predict([llm_prob])[0])
    
    def ece(self, llm_probs, outcomes):
        calibrated = self.ir.predict(llm_probs)
        return expected_calibration_error(calibrated, outcomes)

# Usage: train on ~50+ historical observations before relying on calibration
layer = LLMCalibrationLayer()
layer.fit(historical_llm_probs, historical_outcomes)
trading_prob = layer.calibrate(raw_llm_estimate)
```

---

## Domain-Specific Market Biases (Actionable)

Source: arXiv:2602.19520 (Feb 2026) — 292M trades, 327K contracts on Kalshi + Polymarket.

The four components explaining 87.3% of calibration variance:
1. Universal horizon effect
2. Domain-specific biases
3. Domain × horizon interactions
4. Trade-size scale effect

### Domain Biases Table

| Domain | Bias Direction | Magnitude | Trading Implication |
|--------|---------------|-----------|---------------------|
| **Political markets** | Underconfidence | Large (price compresses toward 50%) | Bid the favorite — true probability higher than price suggests |
| **Weather** | Overconfidence at short horizons | Moderate | Fade extreme weather contracts in the last 1–2 hours |
| **Sports** | Well-calibrated | Small | Minimal structural edge; hard to beat |
| **Economics** | Mostly well-calibrated | Small | Edge comes from model quality, not market bias |

**Political market mechanics**: Prices cluster at 50% due to bilateral partisan betting canceling out. Large trades amplify this effect on Kalshi (0.53 effect size) but NOT on Polymarket (0.11) — suggesting Kalshi political contracts may be more systematically mispriced.

**Practical workflow for political contracts on Kalshi**:
```python
def political_bias_adjustment(raw_market_price: float, 
                               horizon_days: int, 
                               is_large_trade_dominated: bool = True) -> float:
    """
    Adjust Kalshi political market prices for systematic underconfidence.
    
    Prices near 50% are systematically too close to 50% — push away from center.
    Magnitude scales with dominance of large partisan bets.
    
    Raw price: 0.45 → your true probability estimate: ~0.52
    Raw price: 0.60 → your true probability estimate: ~0.63
    Raw price: 0.50 → no adjustment (symmetric)
    """
    if raw_market_price == 0.5:
        return 0.5
    
    # Bias correction: push away from 0.5
    # Conservative estimate: ~5-8 pp compression at 20+ day horizon
    compression = 0.06 if is_large_trade_dominated else 0.03
    compression *= min(horizon_days / 30, 1.0)  # scales with horizon
    
    if raw_market_price > 0.5:
        return min(0.99, raw_market_price + compression)
    else:
        return max(0.01, raw_market_price - compression)
```

---

## Fermi Estimation Framework for Economic Questions

Break complex event questions into knowable sub-components:

### CPI Beat Decomposition Example

**Question**: "Will headline CPI exceed 3.2% YoY?"

```
1. Base rate: CPI exceeds analyst consensus 48% of the time (last 36 months)
   → Start: P(beat) = 0.48

2. Shelter component (lagged 12-18 months by design):
   - Current OER: 5.4% → OER forecast in CPI print: 4.8%
   - OER drag factor: -0.15 base rate adjustment
   → Update: P(beat) = 0.48 × (1 - 0.15) = 0.41 [LR ≈ 0.85]

3. Used cars (Cleveland Fed auction data):
   - Manheim Index +3.2% MoM → suggests upward revision
   - Historical: when Manheim >2% MoM, CPI used cars prints hot 68% of time
   → Update: P(beat) = Bayesian update(0.41, LR=2.0) ≈ 0.58

4. Energy (already known from EIA weekly data):
   - Gasoline -1.8% MoM → CPI energy drag ~-0.08pp
   - Roughly neutral given already priced in
   → Minimal update: P(beat) = 0.58

5. ADP / broader employment (released 2 days before BLS):
   - ADP +172k vs consensus +145k → labor market tight → service inflation sticky
   - Historical LR: hot ADP → CPI beat: 1.6×
   → Update: P(beat) = Bayesian update(0.58, LR=1.6) ≈ 0.69

Final estimate: P(CPI > 3.2%) ≈ 69%
Market price (Kalshi): 62%
Edge: +7pp → trade threshold met (min_edge = 0.05)
```

---

## Superforecaster Profile Applied to Algorithmic Pipeline

What separates a superforecaster from an average predictor, translated to system design:

| Superforecaster Trait | System Implementation |
|-----------------------|-----------------------|
| Seeks diverse information | Multi-source ensemble: FRED + ADP + Manheim + nowcast |
| Updates frequently in small increments | Daily model runs; don't wait for release day |
| Uses precise probabilities | Output calibrated percentages, not "likely/unlikely" |
| Tracks calibration rigorously | Brier score + ECE dashboard per strategy |
| Acknowledges uncertainty honestly | Kelly fraction scales with calibration confidence |
| Learns from mistakes | Rolling 30-trade calibration window; automatic detuning |

---

## Integration with H185 / Prediction Market Pipeline

**Recommended workflow** (combines nowcasting data + calibration methodology):

1. **Base rate anchor**: pull historical release outcomes from FRED → compute P(beat consensus) by release type
2. **Signal stack**: add ADP, Manheim, shelter lag, Cleveland Fed nowcast → Bayesian update
3. **LLM overlay**: if using LLM synthesis, apply calibration layer trained on ≥50 historical observations
4. **Domain bias check**: political contracts → apply underconfidence correction; economic → trust model
5. **Kelly position size**: quarter-Kelly based on |P_model − P_market|
6. **Track**: Brier score, ECE, and rolling win rate per question category

**Performance targets** (H185 pipeline gates):
| Metric | Gate | Source Benchmark |
|--------|------|------------------|
| Brier score | ≤ 0.180 | Human superforecasters |
| ECE | ≤ 0.050 | GJP forecaster average |
| Win rate at ≥5pp edge | ≥ 58% | sparkco.ai CPI track record |
| Sharpe (annualized) | > 0.8 | sparkco.ai CPI track record |
| Min trades before live | 30 | Statistical reliability gate |

---

## Key References

| Paper / Resource | Key Finding |
|-----------------|------------|
| Tetlock, *Superforecasting* (2015) | Foundational methodology; Ten Commandments; GJP tournament results |
| arXiv:2602.19520 (Feb 2026) | 292M trades: political markets underconfident; sports best-calibrated; domain × horizon table |
| arXiv:2512.16030 (Dec 2025, KalshiBench) | Best LLM ECE = 0.120; most LLMs worse than base rates on 300 Kalshi questions |
| arXiv:2604.14199 (Apr 2026, PolyBench) | LLMs near-random on general questions; +6% only on economic data with FRED context |
| arXiv:2507.04562 (Jul 2026) | Frontier LLMs > human crowd on Metaculus; still < expert forecasters |
| arXiv:2506.01578 (Jun 2026) | Prompt engineering for forecasting: minimal gains; Bayesian reasoning prompts backfire |
| arXiv:2510.15205 (Oct 2025) | Black-Scholes analog for prediction markets: belief-volatility surface, variance swaps |
| arXiv:2604.20421 (Apr 2026) | Polymarket dataset: 770K markets, 943M fills, 2M resolution events, Oct 2020–Mar 2026 |

## See Also

- [Algorithmic Strategies](algorithmic-strategies.md) — trading code scaffolding, Kelly sizing, execution
- [Nowcasting Playbook](nowcasting-playbook.md) — per-release operational workflow
- [AI Model Benchmarks](ai-model-benchmarks.md) — Prediction Arena live capital results
- [Kalshi](kalshi.md) — API reference, RSA auth, order placement
