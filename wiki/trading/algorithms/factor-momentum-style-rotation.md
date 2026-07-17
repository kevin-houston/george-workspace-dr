---
created: 2026-06-06
updated: 2026-07-17
status: active
relevance: H255 (NOT CONFIRMED), H256 (NOT CONFIRMED), H026 (production sector rotation), H041a (production momentum), H395/H398A (CONFIRMED — IMOM factor momentum), H406 (design stub, factor momentum on alpha101)
see_also:
  - wiki/trading/algorithms/momentum-strategies.md
  - wiki/trading/algorithms/factor-models.md
  - wiki/trading/backtesting/design-principles.md
  - wiki/trading/algorithms/long-short-equity.md
---

# Factor Momentum & Style Rotation

Factor momentum extends the classical momentum anomaly from individual stocks to
entire investment *factors*: style portfolios such as value, quality, size, momentum,
and minimum-volatility that are constructed according to documented anomaly signals.
The central claim is that these factor returns themselves exhibit serial correlation —
recent factor winners keep winning, recent losers keep losing.

This page documents the academic theory, two full empirical tests (H255, H256), and
the structural failure modes discovered in each.

---

## 1. Academic Evidence — Gupta & Kelly (2019)

**Source:** "Factor Momentum Everywhere," Journal of Portfolio Management (2019).
Tarun Gupta and Bryan T. Kelly.

### What they found

The paper documents factor momentum in a large cross-section of **65 widely-studied
characteristic-based equity factors** (value, profitability, investment, quality, size,
and over 50 others) in international markets. Key results:

| Metric | Result |
|--------|--------|
| IS Sharpe ratio (factor timing portfolio) | **0.84 annualized** |
| Signal: time-series momentum on factor portfolios | 12-month lookback, monthly rebalance |
| Universe | 65 long-short equity factors |
| Breadth | International (US, Europe, Asia) |
| Factor momentum explains | Individual stock momentum + industry momentum |

### The mechanism

Factor momentum works because:

1. **Style regime persistence**: Growth, value, quality, and momentum regimes rotate
   slowly — months, not days. A factor in favor (e.g., growth ETFs during rate-cut
   cycles) tends to remain in favor for several months.

2. **Factor-specific alpha**: The paper separates factor momentum from stock-level
   momentum — they are distinct and each adds independent Sharpe.

3. **Breadth advantage**: Timing 65 factors provides more stable signal than timing
   individual stocks. Diversification reduces noise.

### Critical implementation detail

Gupta & Kelly use **long-short factor portfolios** — not long-only ETFs. The strategy
is long recent outperforming factors *and short* recent underperforming factors. The
short side captures half the alpha. Long-only ETF implementations cannot replicate this.

---

## 2. H255 — Factor ETF Momentum Rotation

**Date**: 2026-06-05  
**Status**: NOT CONFIRMED  
**Script**: `backtesting/daily/run_h255.py`

### Design

- Universe: 12 factor ETFs (MTUM, QUAL, VLUE, USMV, SIZE, IVW, IVE, IWM, IWD, IWF, SPY, BIL)
- Signal: 6-1 month momentum (skip 1-month reversal)
- Variants: Top-1 EW, Top-2 EW, Top-3 EW
- IS: 2014-2019, OOS: 2020-2025, TC: 10bp round-trip
- Confirm gate: OOS Sharpe > 1.0, Corr(best, SPY) < 0.70

### Results

| Variant | OOS Sharpe | OOS CAGR | Corr(SPY) |
|---------|-----------|---------|-----------|
| Top-1 (A) | 0.901 | 14.5% | 0.894 |
| Top-2 (B) | **0.883** | 11.2% | 0.894 |
| Top-3 (C) | 0.831 | 9.4% | 0.883 |
| SPY B&H | 1.015 | 15.8% | — |

Best variant (B-Top2): Sharpe=0.883 < gate 1.0. **FAIL**  
Corr=0.894 >> gate 0.70. **FAIL**

### Root cause: no defensive escape

All 12 ETFs are **US large-cap equity**. IWF (Russell 1000 Growth) dominated with 36
holding months; IVW (S&P 500 Growth) had 33 months. During the 2022 rate shock:
- All factor ETFs declined simultaneously
- Rotation within the universe cannot escape systemic equity risk
- SPY B&H actually outperformed all variants

This is the **long-only implementation trap**: Gupta & Kelly's academic factor momentum
requires shorting the losing factors to capture the full effect. Long-only factor ETF
rotation captures only the relative difference across correlated instruments — not the
absolute factor timing premium.

---

## 3. H256 — Dual Momentum (Antonacci GEM)

**Date**: 2026-06-05  
**Status**: NOT CONFIRMED  
**Script**: `backtesting/daily/run_h256.py`

### Design

Three variants tested on 2015-2025 OOS:

| Variant | Description | Universe |
|---------|-------------|----------|
| GEM | Classic Global Equities Momentum (Antonacci 2012) | SPY, EFA, BIL |
| PACS | Extended: equity pool (SPY/EFA/IWM/QQQ) vs defensive (TLT/BIL/GLD) | 7 ETFs |
| GEM+Sector | GEM absolute gate + sector rotation | SPY/EFA/BIL + 11 sector ETFs |

Signal: 12-month absolute momentum gate; if equity positive, relative momentum selects best equity. If not, BIL (or defensive pool).

### Results

| Variant | OOS Sharpe | OOS CAGR | vs SPY Sharpe |
|---------|-----------|---------|---------------|
| GEM | 0.696 | 9.2% | 1.015 |
| PACS | 0.522 | 7.4% | 1.015 |
| GEM+Sector | 0.646 | 8.7% | 1.015 |
| SPY B&H | 1.015 | 15.8% | — |

All three variants underperform SPY by a wide margin. **NOT CONFIRMED**.

### Root cause: 2022 joint bond+equity crash

Antonacci validated GEM on data from 1974-2012. The 2015-2025 OOS window violated the
core structural assumption:

**1. Correlated bond+equity crash (2022)**:
- TLT: −26.1% (worst bond year in modern history)
- SPY: −18.2%
- The defensive exit triggered (12m equity momentum < 0) but BIL offered near-zero
  return while TLT destroyed capital

**2. Fast V-shape recoveries post-2015**:
- COVID crash (2020): −33% then full recovery in 5 months
- 12-month lookback signals "exit equities" after the crash — but the market recovered
  before the signal reversed, causing whipsaw losses

**3. Post-publication decay**:
- Pre-publication (1974-2012): 17.4% annual return, 0.95 Sharpe
- Post-publication (2014-2021): 5.9% annual return, ~0.45 Sharpe
- Alpha-decay from widespread adoption and structural regime change

### Look-ahead bias trap — CRITICAL

**H256 uncovered the most dangerous momentum implementation mistake:**

```python
# WRONG — look-ahead bias (unlagged)
r12 = monthly / monthly.shift(12) - 1

# CORRECT — properly lagged
r12_raw = monthly / monthly.shift(12) - 1
r12 = r12_raw.shift(1)  # signal at month t uses data through t-1
```

Without the `.shift(1)`, the signal uses the *same month's return* as the signal — the
backtest "knows" whether this month is good before deciding to be invested in it.

**Magnitude of the bias (GEM+Sector variant):**
- Unlagged (look-ahead): OOS Sharpe = 1.956
- Properly lagged: OOS Sharpe = 0.646
- **3× inflation from a single missing `.shift(1)`**

This is one of the highest-impact look-ahead traps in momentum strategies. Always lag
momentum signals by 1 period before using as trading signals.

---

## 4. Why Long-Only Factor ETF Momentum Fails

Both H255 and H256 share a fundamental structural limitation in long-only form:

| Problem | H255 (Factor ETF) | H256 (Dual Momentum) |
|---------|-------------------|---------------------|
| Universe too correlated | All ETFs = US equity, ρ=0.89 | SPY/EFA/BIL: equity dominates |
| No short side | Long-only can't short losers | Long-only can't extract negative factor premium |
| Crisis escape | Can go to BIL but sacrifices all upside | Works until bonds also crash (2022) |
| Lookback mismatch | 6-1m good for equities | 12m GEM misses fast recoveries |

The academic evidence for factor momentum (Gupta & Kelly) uses **net-zero long-short**
portfolios. A long-short factor portfolio has:
- Portfolio-level beta ≈ 0 (longs and shorts cancel)
- Pure factor timing alpha
- Maximum diversification benefit

Long-only ETF implementations capture only the relative cross-section within one risk
category, not the absolute factor premium.

---

## 5. What Might Actually Work — Extensions

### Multi-asset absolute momentum (not yet tested)

The Composite Dual Momentum (Antonacci) uses 4 separate modules each with
relative+absolute momentum:
1. US large-cap / International equity
2. High-yield credit / Aggregate bonds
3. REITs (equity / mortgage)
4. Gold / Treasuries

Within each module, select the best asset using relative momentum. If absolute momentum
is negative, park in T-bills. This produces a more diversified multi-asset rotation.

**Why this might avoid H256's failure**: If equity crashes while credit crashes too,
the REIT and commodities modules can still find positive absolute momentum. More escape
routes than GEM's binary equity/bonds split.

### Integrated momentum across factor categories

A meaningful improvement over H255: combine factor ETFs with **bonds + commodities**
to allow genuine cross-asset rotation:
- Equity factors: MTUM, QUAL, VLUE (or long-short mimics)
- Bonds: TLT, HYG, LQD
- Commodities: GLD, USO, DBC
- International: EFA, EEM, VEA

A 20-30 asset universe with genuine cross-asset dispersion allows momentum to escape
correlated equity crashes. Signal window of 3-6 months (shorter than GEM's 12m) may
better capture fast regime shifts.

### Crisis alpha overlay

H165a (VIX gate, OOS Sharpe +0.429) is the cleanest solution: run H026 sector
rotation but gate out to BIL during high-stress periods (VIX ≥ 25). This avoids
momentum crash risk without requiring complex multi-asset rotation mechanics.

---

## 6. Signal Window vs. Market Speed — Key Tension

| Lookback | Captures | Misses |
|---------|---------|-------|
| 1 month | Fast reversals | Sustained trends |
| 3 month | Intermediate trends | V-shape bounces |
| 6 month | Style cycles | Post-publication fast recovery |
| 12 month | Long cycles, avoids reversal | 2020/2021 V-shape; 2022 joint crash |

H026 (25-asset sector rotation) uses 6-month momentum and produced OOS Sharpe 1.2+.
The 12-month lookback of GEM is structurally too slow for post-2020 market dynamics.

---

## 7. Production Strategy Connection

| Strategy | Momentum type | Window | OOS Sharpe |
|----------|--------------|--------|-----------|
| H026 (production) | Sector ETF rotation, long-only | 6m | ~1.2 |
| H041a (production) | 19-asset multi-ETF top-1 | 6m | — |
| H198 (confirmed) | Cross-sectional stock momentum | 6-1m | 1.174 |
| H255 (not confirmed) | Factor ETF long-only | 6-1m | 0.883 |
| H256 (not confirmed) | Absolute + relative, binary gate | 12m | 0.696 |

The production portfolio (H026/H041a) outperforms both failed hypotheses because:
1. Broader universe with genuine cross-sector dispersion
2. 6-month window better matched to post-2020 regime speed
3. No binary gate — always invested, avoids whipsaw from trigger/re-entry

---

## 8. Future Hypothesis Directions

| Hypothesis | Description | Key innovation vs H255/H256 |
|-----------|-------------|---------------------------|
| H257 (queued) | Multi-asset dual momentum with 20+ assets | Include commodities, credit, international; 3-6m signal |
| H258 (queued) | Cross-asset factor timing (long+short mimics via paired ETFs) | Capture short-side premium using inverse ETFs or long-short pairs |
| H406 (design stub) | Factor momentum on broad alpha101 universe (50+ signals) | True factor-level cross-section; not L/S, top-rank composite |

**Avoid**: pure long-only single-asset-class factor rotation. Only works on paper when
shorting the loser factors — requires either long/short construction or genuinely diverse
multi-asset universe.

---

## 9. The IMOM Discovery — Factor Momentum Applied to Individual Signals (2026)

The most significant evolution since H255/H256: applying the factor momentum concept **within** the stock universe rather than across factor ETFs. This sidesteps the long-only correlation trap by constructing IMOM signals directly from price paths.

### IMOM (Illusion Momentum Factor)

**Source**: Iwanaga & Hirose (2026), *Pacific-Basin Finance Journal* Vol. 96.

```
IMOM(N) = compound_return_N_months - arithmetic_sum_N_months
        = [Π(1 + r_t) - 1] - Σ(r_t)
```

IMOM measures **compounding quality**: high IMOM = sustained directional gains where compounding worked in the stock's favour. Low IMOM = volatile round-trip where compounding erased gains. Cross-sectional ranking on IMOM selects consistent compounders and rejects volatile names — this is factor momentum at the individual-signal level.

### Confirmed Results on H198 30-Stock Universe

| Composite | Key signals | OOS Sharpe | OOS MaxDD |
|-----------|------------|-----------|----------|
| H376 baseline | 6-0m no-skip MOM alone | 3.120 | −8.4% |
| H395 Var C | IMOM6 + MOM60 + LowVol (equal) | 3.962 | −8.6% |
| **H398 Var A** | IMOM6 + MOM60 + LowVol + IMOM12 (equal) | **4.068** | **−4.7%** |

Annual OOS returns for H398A (current champion): 2021 +124%, 2022 +60%, 2023 +138%, 2024 +130%, 2025 +103%, 2026 +35% (partial). Zero negative years.

### Why This Is Factor Momentum

Gupta & Kelly's factor momentum operates at the **style-portfolio level**: time-series momentum on factor returns. IMOM operates at the **signal level**: it captures quality of compounding in a stock's own return path — which is the same concept one level down. The JPM 2025 Cakici et al. paper (see Section 10) confirms these are the same mechanism.

### H376 6-0m No-Skip Baseline

Before adding IMOM, 2026 research discovered that **6-0m momentum (no skip-month) dramatically outperforms 6-1m** on the H198 30-stock universe (OOS 3.120 vs 1.174 for 6-1m). This contrasts with the academic convention of skipping the most recent month. The reason: large-cap NASDAQ tech names exhibit persistent short-term momentum with no 1-month reversal (same finding as H277 on tech). Including the most recent month *improves* the signal by 1.95 Sharpe points.

**Key contrast with H255**: Factor ETFs (all US equity) have ρ=0.89 — the signal dominance is the same across all ETFs. Individual stocks in the H198 universe have genuine cross-sectional dispersion, allowing the factor momentum logic to work.

---

## 10. JPM 2025 — Factor Momentum Is the Sole ML Alpha

**Source**: Cakici, Fieberg, Osorio, Poddig & Zaremba — "Picking Winners in Factorland: A Machine Learning Approach to Predicting Factor Returns" — *Journal of Portfolio Management*, April 2025.

**Coverage**: 242 factor characteristics; ML methods tested: random forest, XGBoost, LASSO, neural nets, and others.

### Key Finding

> Factor momentum is the **main driver** of cross-sectional variation in anomaly returns. Once factor momentum is controlled for, **no long-short ML portfolio generates significant alpha** from any other ML signal.

This is the most important independent validation of our H398A design. The Cakici et al. study searched 242 factors for ML-exploitable predictability and found:
1. ML can predict which factors will outperform next month.
2. The entire predictability is attributable to **factor-level time-series momentum**.
3. No other ML signal survives after controlling for factor momentum.

### Connection to H398A

Our IMOM6/IMOM12 signals are implicit factor momentum:
- IMOM6 = time-averaged 6-month compounding quality → momentum on the stock's own factor history
- MOM60 = pure directional 5-year momentum → classic time-series momentum
- Together they comprise the primary factor-momentum channels in the H198 universe

### Turnover Warning

ML factor rotation strategies require **37–66% factor replacement per month**. This is why explicit ML factor selection adds nothing after costs to our H398A composite: IMOM already captures the signal, and the additional turnover cancels any gross alpha improvement.

**H406 implication**: factor momentum on a *broad* 50+ alpha101 signal universe (where genuine cross-signal variation exists) may uncover predictability that our 4-signal composite cannot. Design stub: `backtesting/daily/run_h406.py`, gate OOS Sharpe > 4.068.

---

## 11. H406 Design — Factor Momentum on Alpha101 Broad Universe

**Status**: Design stub (2026-07-16). Implementation pending.

**Hypothesis**: Apply factor-level time-series momentum to the WorldQuant 101 alpha universe. For each of 50+ alpha101 signals, compute the signal's 6-month trailing IC (information coefficient) vs forward returns. Rotate the composite weight toward recently-outperforming alpha signals.

```python
HYPOTHESIS = "H406"
GATE_SHARPE = 4.068          # must beat H398A champion
IS_START    = "2013-01-01"
OOS_START   = "2021-01-01"
UNIVERSE    = "H198_30_stock" # same as H398A for direct comparison
```

**Key design decisions**:
- Signal IC lookback: 6 months (consistent with Gupta & Kelly's best window)
- Factor selection: top-N alpha101 signals by trailing IC, equal-weight
- Gate: strict OOS Sharpe > 4.068 AND MaxDD < 5%
- Dependency: requires run_h395.py alpha101 infrastructure

**Caveats**:
- Alpha101 signals have high IC correlation — factor momentum within a correlated universe may not generate enough signal diversity
- 37-66% monthly factor turnover cost applies here too (per Cakici et al. 2025)
- H217 confirmed median-aggregation of alpha101 already generates OOS Sharpe 1.559; H406 tests if *time-weighted* aggregation beats that

---

## References

- Gupta, T. & Kelly, B.T. (2019). "Factor Momentum Everywhere." *Journal of Portfolio Management*, 45(3), 58-71. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3300728)
- Antonacci, G. (2012). "Risk Premia Harvesting Through Dual Momentum." [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2042750)
- Geczy, C. & Samonov, M. (2015). "Two Centuries of Multi-Asset Momentum." [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2607730)
- Hoffstein, C. (2019). "Fragility Case Study: Dual Momentum GEM." Newfound Research.
- Shu, W. & Mulvey, J. (2024). "Dynamic Factor Allocation Leveraging Regime-Switching Signals." arXiv:2410.14841
- Cakici, N., Fieberg, C., Osorio, D., Poddig, T. & Zaremba, A. (2025). "Picking Winners in Factorland." *Journal of Portfolio Management*, April 2025.
- Iwanaga, Y. & Hirose, T. (2026). "Illusion Momentum." *Pacific-Basin Finance Journal* Vol. 96.
- H255 empirical test: `backtesting/results/h255_results.json` (2026-06-05)
- H256 empirical test: `backtesting/results/h256_results.json` (2026-06-05)
- H395/H398A: `backtesting/results/h395_results.json`, `backtesting/results/h398_results.json`
- See also: `algorithms/momentum-strategies.md`, `algorithms/factor-models.md` (Sections 10–14), `backtesting/design-principles.md`
