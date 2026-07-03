---
updated: 2026-07-03
type: research-note
source: https://github.com/yli188/WorldQuant_alpha101_code
related: auto-alpha-discovery.md, factor-models.md, momentum-strategies.md
---

# WorldQuant 101 Formulaic Alphas — Confirmed Results & Signal Taxonomy

The 101 alphas from Kakushadze (2015) "101 Formulaic Alphas" are OHLCV + VWAP signals designed for
daily cross-sectional portfolios with a 0.6–6.4 day average holding period. This page tracks:
(1) our confirmed results from testing the WQ101 family, (2) which signals survive OOS in the
US market per new empirical research, and (3) OHLCV-only signals buildable without paid data.

---

## Confirmed Results — Our Own Backtests

| Hypothesis | Signal | IS Sharpe | OOS Sharpe | Result |
|-----------|--------|-----------|------------|--------|
| **H215** | alpha101: (close−open)/(high−low), cross-sectional rank | 1.283 | **1.321** | CONFIRMED |
| **H216** | alpha002 + alpha013 vol-price divergence blend | 0.862 | **0.823** | CONFIRMED-weak |
| **H217** | Median of OHLCV-only alpha101 signals (ensemble) | 1.421 | **1.559** | CONFIRMED — strongest |
| **H228** | H217 + H181 industry reversal blend (50/50) | 1.467 | **1.572** | CONFIRMED |

**Key insight from H217 vs H215:** the single alpha101 (close-within-range) OOS Sharpe is 1.321.
Taking the *median* of all buildable OHLCV-only signals lifts OOS to 1.559 — an ensemble gain of
+18% with no additional data cost. This is the signal to use.

**H228 blend:** adding H181 industry-adjusted short-term reversal (OOS 0.998) to H217 adds minimal
marginal Sharpe (1.572 vs 1.559) but reduces MaxDD and improves correlation profile.
Corr(H217, H181) ≈ −0.12 — nearly orthogonal.

---

## Data Requirements

| Data tier | Signals available | Path |
|-----------|------------------|------|
| EOD OHLCV (yfinance, Alpaca free) | ~40 signals | Available NOW |
| Daily VWAP (Polygon paid $29/mo) | ~60 additional | Unlock if OHLCV signals confirm |
| L2 order book (Polygon pro) | Microprice / AS models | Not needed for monthly rotation |

**Note**: VWAP unlock is worth considering — 60+ additional signals vs. a $29/mo data cost.
The OHLCV-only family has already confirmed (H215/H217), making the incremental bet on VWAP
signals well-motivated.

---

## OHLCV-Only Signal Taxonomy (40 buildable signals)

### Group A — Close-within-Range (Intraday Positioning)

These measure where price closed within the day's range, ranked cross-sectionally.

| Alpha | Formula | Interpretation | Confirmed |
|-------|---------|----------------|-----------|
| **alpha101** | `(close−open) / (0.001 + high−low)` | Internal Bar Score — daily close position; high = closed near top | **H215 OOS 1.321** |
| alpha033 | `rank(−1 × (1 − open/close))` | Short bullish bars (contrarian) | H217 component |
| alpha038 | `−rank(ts_rank(close, 10)) × rank(close/open)` | Trend × intraday confirmation | H217 component |
| alpha053 | `−delta((close−low−(high−close)) / (close−low), 9)` | Change in close-range position over 9d | H217 component |

**Production signal:** alpha101 is the single best OHLCV signal confirmed. For production, use
the H217 ensemble (median of all Group A+B signals) for higher Sharpe.

### Group B — Volume-Price Divergence

Signals where volume and price move in conflicting directions — predictive of reversal.

| Alpha | Formula | Interpretation | Confirmed |
|-------|---------|----------------|-----------|
| **alpha002** | `−rank(delta(log(volume), 2)) × rank((close−open)/open)` | Volume surge + no price move → reversal | H216 component |
| **alpha013** | `−rank(cov(rank(close), rank(volume), 5))` | Decouple of close-rank and vol-rank over 5d | H216 component |
| alpha043 | `ts_rank(volume/mean(volume,20), 20) × ts_rank(−delta(close,7), 8)` | Volume spike × 7d price reversal | H217 component |

**H216 note:** alpha002 + alpha013 blend OOS Sharpe 0.823 — confirms the signal exists but is
weaker than momentum-based signals. Useful as a diversifier, not a standalone.

### Group C — Momentum / Trend Continuation

| Alpha | Formula | Notes |
|-------|---------|-------|
| alpha019 | 250-day momentum | Covered by H198 (6-1m); independent lookback |
| alpha081 | 50-day volume × correlation momentum | Partial overlap with H212 vol-scaling |
| alpha028 | `scale(corr(adv20, low, 5), 7)` | Requires VWAP-adjacent volume avg — partially buildable |

---

## What the 101 Alphas Don't Cover

The WQ101 are pure price/volume signals. Our strongest confirmed strategies are *outside* this
family:

| Our strategy | Type | OOS Sharpe | Not in WQ101 |
|-------------|------|------------|--------------|
| H174 PEAD | Event/NLP | WR 81.8% | ✓ — earnings 8-K text |
| H192-D BAB | Low-beta L/S | 1.367 | ✓ — market beta factor |
| H234 Inside-bar | Pattern recognition | 1.770 | ✓ — multi-day patterns |
| H343/H346 OB filter | SMC institutional | +0.628 overlay | ✓ — order block detection |

This means the 101 alphas complement our core portfolio rather than competing with it. The
cross-sectional volume/price signals have low correlation with event-driven and SMC strategies.

---

## External Validation — 2025/2026 Research

### Cross-Market Alpha: 17 Surviving US Signals (Jan 2026)

**Source:** "Cross-Market Alpha: Testing Short-Term Trading Factors in the U.S. Market via
Double-Selection LASSO" — Du, Walter, Ulrich; arXiv:2601.06499 (Jan 10, 2026, v2 May 2026)

Tests 191 short-term, trading-based signals on the US equity market using double-selection LASSO
to control for multiple testing. **17 distinct price-volume and microstructural signals** survive.

Key findings:
- Volume-price divergence signals are among the survivors
- Microstructural intraday positioning signals (close-within-range family) show cross-market
  persistence
- Many "locally discovered" alphas collapse when subjected to proper multiple-testing correction
- Result: the WQ101 OHLCV family is NOT redundant — it contains robust signals, but far fewer
  than the headline 101 implies

**Implication:** Our confirmed H215/H217 signals are likely within the 17 survivors given they
passed OOS validation on a separate US universe. Cross-listing our alpha formulas against the
full list of survivors is a future task when the full paper text is available.

### ML-Enhanced Multi-Factor Quantitative Trading (May 2026)

**Source:** arXiv:2507.07107

Uses curated Alpha101 formulas — specifically **momentum rank, volume-intraday correlation, and
open-volume divergence** — as input to a Transformer model.

- Transformer Sharpe: **2.4 in 2023-Q1** (US equity)
- Confirms that WQ101 OHLCV signals remain predictive even in recent 2023–2024 data
- The "volume-intraday correlation" is an approximation of alpha013 using daily data
- Key insight: cross-sectional ML (Transformer over raw alpha signals) outperforms single-signal
  strategies — supports H228-style blending

### AlphaMemo — Self-Evolving Memory for Alpha Mining (May 2026)

**Source:** arXiv:2606.20625 — Yu, Zheng et al.

Discovers new alphas by recording which *edits* to existing WQ101-style expressions succeed or
fail in specific factor contexts (AST-diff motifs). The confidence-gated residual memory prevents
rediscovering known losers.

Tested on CSI 500 and S&P 500 — confirms that structured search memory significantly improves
OOS performance vs. memoryless LLM alpha mining. Indirectly validates that the WQ101 formula
space still contains undiscovered profitable edits (not fully mined).

### AlphaLogics — Multi-Agent Market Logic Extraction (Mar 2026)

**Source:** arXiv:2603.20247 — Weng et al.

Three-stage loop: (1) extract market logic from historical alpha performance, (2) generate new
factors guided by logic + backtesting feedback, (3) refine logic library. Tested on CSI 500 +
S&P 500. Consistently improves predictive metrics over representative baselines.

**Implication for pipeline:** the "market logic" extracted from WQ101 failures is itself a useful
signal — knowing WHY alpha053 fails in certain regimes helps design better replacements.

---

## Overlap Summary

| Our confirmed strategy | Best mapping in WQ101 | Substitutable? |
|----------------------|----------------------|----------------|
| H198 6-1m momentum | alpha019 (250d momentum) | Partial — different window |
| H181 industry reversal | alpha017/alpha035 (5d reversal) | Partial — industry-neutral version is stronger |
| H215 alpha101 close-within-range | alpha101 | Exact match — confirmed |
| H217 OHLCV ensemble | All Group A+B signals | Superset — our best expression |

---

## Blocked Signals (Require VWAP)

~60 alphas require VWAP: alpha005, 011, 025, 041, 042, 057, 060–062, 064–066, 068, 071–075,
077–079, 083–086, 088, 092, 094–096, 098–099, and others.

**Unlock path:** Polygon.io paid tier ($29/mo) provides 1-minute intraday bars → daily VWAP
easily computed as `sum(close × volume) / sum(volume)` over minute bars. Given H217 OOS 1.559
already confirmed, the VWAP tier unlocks ~50% more signals and is worth evaluating.

---

## Recommended Next Steps

| Priority | Action | Effort | Expected gain |
|----------|--------|--------|--------------|
| ✅ Done | H215 alpha101, H216 vol-price div, H217 ensemble, H228 blend | — | OOS 1.559 confirmed |
| High | Cross-list our OHLCV alphas against Du et al. 17 survivors (full paper) | Low | Validation |
| High | Run AlphaMemo on H217 ensemble expressions (find profitable edits) | Med | +0.1–0.3 IC |
| Medium | Unlock VWAP tier ($29/mo Polygon) → test 60 additional signals | Low cost | New signal family |
| Medium | H349 QuantaAlpha evolutionary session on US 500-stock universe | $5–20 | Novel factors |
| Low | H352 TreEvo loop (20 min, $3–10) using H217 winners as seed expressions | Low | Factor refinement |

**For AI-driven alpha discovery methods (QuantaAlpha, TreEvo, Hubble, Constrained DSL):**
see [AI-Driven Alpha Factor Discovery](auto-alpha-discovery.md) — dedicated deep-dive page.

---

## Cross-References

- [AI-Driven Alpha Factor Discovery](auto-alpha-discovery.md) — H347/H349/H288/H352 AI mining
- [Momentum Strategies](momentum-strategies.md) — H198 6-1m baseline; H217 as momentum complement
- [Short-Term Reversal](short-term-reversal.md) — H181 CONFIRMED industry reversal
- [Factor Models](factor-models.md) — academic factor foundations; WQ101 as pure price-vol layer
- [Machine Learning for Trading](../tools/ml-for-trading.md) — Transformer over WQ101 signals
