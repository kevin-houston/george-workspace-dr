---
added: 2026-07-31
category: portfolio construction / factor tilts
url: https://arxiv.org/abs/2601.05428
---

# Dynamic Inclusion and Bounded Multi-Factor Tilts for Robust Portfolio Construction (2026)

**arXiv**: 2601.05428 (Jan 2026), HTML: https://arxiv.org/html/2601.05428v1

---

## What This Paper Is

A portfolio-construction framework paper (not a signal-discovery paper) that asks: how do you tilt an equal-weight portfolio toward multiple factors (momentum, value, quality) without letting concentration, turnover, or estimation error blow up the risk profile? It sits squarely between our H478 result (Golden Criterion — binary switch between top-1 and EW-top-3/5 based on eigenvalue dispersion, NOT CONFIRMED 2026-07-30) and the production H026/H198/H411 rotation strategies (hard top-1/top-2/top-3 picks, no smooth blending). This paper's mechanism is a **continuous, bounded** alternative to a binary switch — directly relevant follow-up territory for H478's failure mode.

No empirical Sharpe/CAGR/MaxDD numbers are published (the authors explicitly defer full backtests to future work — this is a "behavioral validation," not an alpha claim). The value here is the **mechanism**, not a performance claim to import wholesale.

---

## Dynamic Inclusion (Eligibility Gate)

Assets must clear two objective liquidity/history filters to enter the universe at each rebalance:

```
U_t = { i ∈ U : H_i(t) ≥ H_min,  ADV_bar_i(t; L_ADV) ≥ ADV_min }
```

- `H_i(t)` — available price history length for asset i at time t (must exceed `H_min`, e.g. enough bars to compute the momentum lookback)
- `ADV_bar_i(t; L_ADV)` — trailing average dollar volume over window `L_ADV`, must exceed `ADV_min`

This is a simple, standard PIT-safe eligibility filter — nothing novel, but a clean pattern to copy directly into any future N00-stock universe expansion (e.g., H337b's proposed 200-stock quality universe, or any small/mid-cap extension of H198).

---

## Bounded Multi-Factor Tilt (the actual novel piece)

Instead of ranking and picking top-K (our current approach everywhere: H026, H198, H411, H445), this paper tilts *away from* an equal-weight baseline by a bounded multiplier per asset:

**1. Combine factors as a convex mixture of z-scores:**
```
z_i(t) = Σ_f  α_f · z_{i,f}(t),      α_f ≥ 0,  Σ_f α_f = 1
```
(Standard: momentum, value, quality each cross-sectionally standardized + winsorized before combining.)

**2. Convert to a bounded multiplicative adjustment:**
```
m_i(t) = clip(1 + λ · z_i(t),  m_min,  m_max)
```
`λ` controls tilt aggressiveness; `clip` hard-bounds the multiplier (e.g. `m_min=0.5, m_max=2.0`) so no single name can be up/down-weighted beyond a fixed band relative to its equal-weight share — this is what controls concentration and turnover, structurally, rather than via a post-hoc cap.

**3. Renormalize on top of the equal-weight base:**
```
w_i(t) = [ w_i^EW(t) · m_i(t) ] / Σ_j∈U_t  w_j^EW(t) · m_j(t)
```
where `w_i^EW(t) = 1/|U_t|`.

Net effect: when a factor signal is weak/noisy cross-sectionally (all z-scores near 0), `m_i(t) → 1` for everyone and the portfolio reverts smoothly to 1/N. When signal is strong, weights tilt toward high-z names but can never exceed the `[m_min, m_max]` band — no discrete regime switch, no cliff-edge turnover event.

**Factor formulas given:**
- Momentum: `s_MOM = P_{t-S} / P_{t-L_mom-S} - 1` (skip-period S, lookback L_mom — same functional form as our 12-1 momentum)
- Value: `s_VAL = BookEquity(q) / MktCap(t)`
- Quality: `s_QUAL = z(ROE) + z(GrossMargin) + z(-DebtToAssets)`

Optional (unused in the paper's own empirical section): factor weights `α_f` can be set via rolling Information Ratio (`IR_f = mean(IC_f)/std(IC_f)`, IC = Spearman rank correlation of z-score vs forward return) instead of fixed weights.

---

## Empirical Results (What's Actually Shown)

Qualitative only, on a large-cap global equity + gold/silver universe, semi-annual rebalance, vs. a cap-weighted benchmark:
- Top-5 concentration stays "materially below" cap-weighted
- "Improved drawdown convexity" vs cap-weighted (directional claim, no MaxDD numbers)
- Turnover "consistently below" naive equal-weight (the bounded tilt trades less than rebuilding EW from scratch every period)
- Explicitly: "does not dominate cap-weighted in all periods" — no claim of universal outperformance

**This is a construction-mechanism paper, not an alpha paper.** Treat it as a design pattern, not as evidence of a new confirmed edge.

---

## Practical Implications for Our Pipeline

**Direct connection to H478 (Golden Criterion, NOT CONFIRMED 2026-07-30):** H478 tried a *binary* switch (top-1 vs EW-top-3) gated on eigenvalue dispersion D. All 5 variants failed the gate, and Var D (always EW-top-5) was the best performer — suggesting the binary switch itself was adding noise, not the diversification concept. This paper's **bounded continuous tilt** is a natural next iteration: instead of switching discretely between top-1 and EW, use `m_i(t) = clip(1 + λ·momentum_z_i, m_min, m_max)` applied on top of EW across the full H026 (or H411/H198) universe every month. This avoids the cliff-edge concentration/diversification switch that likely hurt H478, while still tilting toward momentum leaders.

**Candidate next hypothesis (not yet staged as a full script — flagged for dream cycle):** Re-run H478's H026 universe with the bounded-tilt mechanism instead of the D-threshold binary switch: `w_i = EW_i · clip(1 + λ·mom_z_i, 0.3, 3.0)`, sweep `λ` on IS, gate at H346's OOS 2.610 (or the more realistic ~0.7-0.85 range the H478/H435-437 family has actually been landing in recently). Given H478's baseline (Var E, top-1) OOS was only 0.639 in this simplified script, the more informative comparison is bounded-tilt vs. the script's own EW-top-5 baseline (0.854) — if bounded-tilt beats 0.854 with lower MaxDD than -19.1%, that's a real signal even if it doesn't touch the aspirational 2.610 gate.

**Also relevant to H445/H411 (multi-factor 1/price × drift):** the `z_i(t) = Σ α_f z_f(t)` convex-combination pattern with IR-based `α_f` weighting is a more principled way to combine the value (1/price) and drift factors than a fixed rank-multiply, if IC calibration data is available.

---

## Cross-References

- [Golden Criterion Adaptive Equal-Weight (H478)](../backtesting/hypothesis-log.md) — binary D-threshold switch this paper's bounded tilt would replace
- [Factor Models & Cross-Sectional Alpha](../algorithms/factor-models.md) — IMOM/equal-weighting-optimal-for-orthogonal-signals theory this paper's "revert to 1/N when signal weak" mechanism directly implements
- [Position Sizing & Portfolio Construction](../algorithms/position-sizing.md) — production portfolio weighting table; bounded multiplier pattern is a candidate replacement for hard top-K selection in future variants
- [Quality Factor (QMJ)](../algorithms/quality-factor.md) — this paper's quality factor formula (ROE + GrossMargin − DebtToAssets z-score composite) is close to but not identical to our Piotroski/GP-Assets approach

## Citation

Author(s) unspecified in visible abstract/HTML (arXiv:2601.05428, Jan 2026). "Dynamic Inclusion and Bounded Multi-Factor Tilts for Robust Portfolio Construction."
