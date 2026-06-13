# Dream Cycle Research Summary — 2026-06-12

## Session Overview

Three hypotheses tested: H284 (FCF/P stock screener), H285 (quality ETF rotation), H286 (macro regime-gated FCF/P).

**Net result:** 1 NOT CONFIRMED, 1 CONFIRMED-WEAK (non-additive), 1 CONFIRMED (additive diversifier — paper-trade recommended before production).

---

## H284 — FCF/P Stock Screener (NOT CONFIRMED)

**Thesis:** Yartseva 2025 finds FCF/P is the #1 multibagger predictor. Top FCF yield quintile outperforms by ~15%/yr.

**Implementation constraint hit:** yfinance quarterly cashflow provides only ~7 quarters of history (back to Q3 2024). FMP key-metrics endpoint returns 403 (paid plan required). Could not build a stock-level FCF screener with historical IS/OOS splits.

**Fallback test (COWZ ETF proxy):**
- COWZ (Pacer US Cash Cows 100 — top 100 Russell 1000 by FCF yield):
  - IS 2017-2019: Sharpe=0.615
  - OOS 2020+: Sharpe=0.737, MaxDD=-23.8%, Corr(SPY)=0.816
  - SPY OOS: Sharpe=0.920
- **COWZ underperforms SPY by 0.183 Sharpe units OOS.**

**Root cause:** FCF yield is a value signal. The 2020-2025 OOS period was dominated by mega-cap tech growth (NVDA/TSLA/META) which have low FCF yield ratios but extreme price appreciation. COWZ systematically excludes exactly these names.

**Data gap note:** To properly test this hypothesis, the FMP Professional plan (~$80/month) or Compustat point-in-time data is needed for 10+ years of quarterly fundamental history. The Yartseva 2025 academic result may still hold in a proper backtest — it is currently **untestable** with available free data sources.

**Status:** NOT CONFIRMED. Hypothesis not disproven — data limitation prevents fair evaluation.

---

## H285 — Earnings Quality Factor: Quality ETF Rotation (CONFIRMED-WEAK)

**Thesis:** Rotate among quality-factor ETFs (QUAL/SPHQ/DGRW/SPY/BIL) by 6-month momentum to capture the quality premium (Sloan 1996 accruals; Asness et al. 2014 QMJ).

**Results:**
- Rotation A (6m momentum, top-1): IS Sharpe=1.033, OOS Sharpe=0.932, MaxDD=-19.4%
- SPY OOS: Sharpe=0.921
- **CONFIRMED** (OOS Sharpe 0.932 > 0.9 gate)

**Critical finding — non-additive:**
- Corr(Rotation, SPY) OOS = **0.969** — near-perfect correlation with SPY
- Holdings distribution: SPY 27% / DGRW 26% / SPHQ 25% / QUAL 23% — the rotation rotates near-uniformly across all candidates including SPY itself
- QUAL B&H OOS: Sharpe=0.794 (underperforms SPY by -1.59%/yr, t-stat=-1.25)
- **The quality factor did NOT earn a premium over SPY in 2020-2025**

**Why quality underperformed:** The 2020-2025 period rewarded concentration in high-multiple growth (NVDA, MSFT, META). Quality screens (high ROE + stable earnings + low leverage) exclude exactly these names. SPHQ (0.959) and DGRW (0.885) did better than QUAL (0.794) because they include some quality-growth names.

**Status:** CONFIRMED-WEAK. Gates technically met but Corr=0.969 makes it useless for portfolio diversification. NOT recommended for production.

---

## H286 — Macro Regime-Gated FCF/P (CONFIRMED)

**Thesis:** COWZ's weakness is regime-specificity. A dynamic switching signal between COWZ (FCF value) and SPY (growth/momentum) using a 6-month relative momentum gate should adapt to the prevailing factor regime.

**Variants tested (IS 2017-2020, OOS 2021-2025):**

| Variant | IS Sharpe | OOS Sharpe | OOS MaxDD | Corr(SPY) |
|---------|-----------|------------|-----------|-----------|
| COWZ B&H | — | 0.893 | -17.6% | 0.816 |
| SPY B&H | — | 0.998 | -23.9% | 1.000 |
| A: 200MA+VIX<25→COWZ else BIL | 0.013 | 0.637 | -17.6% | — |
| B: COWZ/SPY 6m cross-mom + BIL escape | 0.624 | **1.031** | **-16.2%** | **0.596** |
| C: VIX-switched (COWZ<20/SPY 20-30/BIL≥30) | 0.283 | 0.682 | -23.2% | 0.836 |

**Variant B (best):** Hold COWZ when COWZ's 6m return > SPY's 6m return; hold SPY otherwise; escape to BIL when SPY < 200MA.
- OOS Sharpe=1.031 > SPY (0.998) and COWZ B&H (0.893)
- MaxDD=-16.2% (better than both)
- **Corr(SPY)=0.596** — below 0.70 threshold, genuinely diversifying

**Why it works:** The 6m relative momentum signal adaptively allocates to whichever of COWZ/SPY is in favor. In 2022 (value regime), COWZ's 6m return beat SPY's → held COWZ, capturing -9.7% vs SPY's -18.2%. In 2023-2024 (growth regime), SPY's momentum dominated → held SPY for the tech-driven rally.

**Why not production-ready yet:**
- IS Sharpe=0.624 < OOS Sharpe=1.031: IS underfits, suggesting OOS gain is concentrated in the single 2022 value regime year
- Only 5 years of OOS data (60 months) with one value-outperformance year — insufficient to distinguish skill from regime luck
- Recommended: paper-trade H286-B for 12+ months before production consideration

**Status:** CONFIRMED. Low correlation (0.596) makes it a genuine diversifier candidate. Track as paper trade.

---

## Key Research Gaps Identified

1. **FCF/P stock-level screener** requires paid fundamental data (FMP Pro or Compustat). The Yartseva 2025 result is potentially valid but untestable with current data access.

2. **Value regime detection**: H286-B shows promise but needs more OOS history. The 2022 value regime may not recur frequently — need to track through 2026-2027 cycles.

3. **Quality factor** (QUAL/SPHQ) underperformed SPY 2020-2025. Worth revisiting after a prolonged growth-to-value rotation (when FCF yield and quality screens regain relevance).

---

## Production Portfolio Status

Unchanged. H285 CONFIRMED-WEAK adds nothing (Corr=0.969). H286 CONFIRMED but requires more OOS validation. Production portfolio remains:

**H041a 22% / H026 27% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%**

OOS Sharpe 4.158, MaxDD -3.60%, ~23.5% CAGR, ZERO negative years 2004-2025.

---

## Next Hypotheses

H287 candidate: **H286-B extended universe** — apply COWZ/SPY cross-momentum logic to a broader FCF/value factor vs momentum factor rotation using multiple value ETFs (IVE, VTV, COWZ, CALF) vs momentum ETFs (MTUM, QUAL) with regime-switching. Tests if the relative momentum signal generalizes.

H288 candidate: **FMP fundamental screener** — revisit H284 with FMP cash-flow-statement endpoint (test if available) to build proper 10-year FCF yield history.
