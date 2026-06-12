# Research Session Summary — 2026-06-11

**Hypotheses tested:** H282, H283 (both NOT CONFIRMED)
**Session window:** Nightly autonomous research pass

---

## H282 — Dividend Growth ETF Rotation

**Signal:** YoY trailing-twelve-month dividend growth rate, monthly rotation across dividend ETF universe (DVY, VYM, SDY, VIG, BIL; extended: +SCHD, DGRO, NOBL).

**Results (core universe, best variant A1 — Top-1 by growth):**
- IS 2008–2019: Sharpe 0.556, CAGR 8.1%, MaxDD −26.9%
- OOS 2020–2025: Sharpe 0.782, CAGR 12.2%, MaxDD −17.1%, NegYrs 1, Corr(prod) 0.490

**Gate:** OOS Sharpe ≥ 1.0. **NOT CONFIRMED** (best OOS Sharpe 0.782).

**Root cause:** Dividend growth rate is a noisy signal on this universe — all six ETFs track overlapping large-cap dividend payers, so cross-sectional dispersion is low. The signal adds no consistent rotation edge over buy-and-hold VYM. Hybrid variants (50% growth rank + 50% 6m momentum) degraded rather than improved. Extended universe (SCHD/DGRO/NOBL) showed inflated IS (Sharpe 1.488 on only 48 months) that collapsed to 0.741 OOS — classic short-IS overfitting.

---

## H283 — Bond ETF Carry + Momentum Rotation (H045 Enhancement)

**Signal:** Linear blend of carry (TTM dividend yield) and 6-month price momentum across the 13-ETF H045 bond universe. Five alpha values tested (α = 1.0, 0.75, 0.50, 0.25, 0.0 blending momentum vs carry).

**Results (best variant: α = 1.0, pure 6m momentum):**
- IS 2008–2017: Sharpe 0.877, CAGR 7.2%, MaxDD −8.9%
- OOS 2018–2025: Sharpe 0.743, CAGR 4.9%, MaxDD −5.9%, NegYrs 3, Corr(prod) 0.371

**Gate:** OOS Sharpe > H045 recomputed baseline 1.351. **NOT CONFIRMED** (best OOS Sharpe 0.743).

**Root cause:** H045's confirmed 12-month lookback provides much stronger bond momentum than the 6-month window tested here. The 6m/12m discrepancy is the primary gap (this pass confirms H045's design choice is load-bearing). Pure carry (α = 0.0) was the worst performer (OOS Sharpe 0.393, MaxDD −25.9%), as yield-chasing allocated heavily to HY credit during 2022's rate shock. Blended variants sit between the two extremes with no synergy — carry actively degrades momentum for the bond universe.

---

## Key Takeaways

1. **Dividend growth as rotation signal is weak on near-duplicate universes** — works better on individual stocks with genuine payout dispersion (cf. H181 industry-adjusted reversal approach).
2. **H045's 12m lookback is not replaceable by 6m** — a clean empirical confirmation. Any H045 enhancement must preserve the 12m window.
3. **Carry adds no edge to H045's bond rotation** — yield-chasing on bond ETFs is a risk factor, not an alpha source, in rate-stress environments.
4. **Production portfolio stays unchanged:** H041a 22% / H026 27% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%.
5. **Next viable hypotheses:** H281 (macro-LLM ETF tilt, arXiv:2606.08283) once API costs are acceptable, or H181 (industry-adjusted short-term reversal) on the individual equity side.

---

## Commits

- `24b2284` — hypothesis: H282 Dividend Growth ETF Rotation (NOT CONFIRMED)
- `20bdfe6` — hypothesis: H283 Bond Carry+Momentum H045 enhancement (NOT CONFIRMED)
- `1e261c4` — hypothesis-log: add H282 H283 entries (both NOT CONFIRMED 2026-06-11)
