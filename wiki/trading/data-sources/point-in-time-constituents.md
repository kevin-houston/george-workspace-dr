---
added: 2026-08-06
updated: 2026-08-06
category: data-sources
relevance: H158, H167, H181, H241-H246, H277
---

# Point-in-Time Constituent & Vintage Data Sources

Consolidated sourcing guide for **point-in-time (PIT) index membership and vintage fundamentals** — the data class needed to eliminate survivorship and look-ahead bias from universe construction. This page collects the provider options; for the bias mechanism itself, formulas, and impact estimates, see [Survivorship Bias & Universe Construction](../backtesting/survivorship-bias.md).

## Why This Page Exists

The need for point-in-time data has been flagged repeatedly across the hypothesis log without ever getting a single reference page of its own:

- **H158** (sector-neutral momentum) — DEFERRED: "Needs Russell 1000 point-in-time data (Compustat/CRSP) or at least a broader multi-sector ETF-based proxy."
- **H167** (ML-momentum, bias-corrected multi-factor) — BLOCKED: "requires point-in-time bias-free constituent data (Compustat/CRSP — not available)."
- **H277** (NASDAQ tech momentum) — CONFIRMED but flagged NOT FOR PRODUCTION: "results materially inflated... until rebuilt with historical NASDAQ constituent data (requires Compustat or Bloomberg point-in-time)."
- **H181** (industry-adjusted reversal, queued) will need point-in-time GICS/SIC sector assignments, not just point-in-time membership — see [Sector & Industry Classification](sector-classification.md) for the sector-assignment half of this problem.

Each of these treated PIT sourcing as a one-off blocker to solve inline. This page exists so the next hypothesis that hits the same wall starts from a comparison table instead of re-researching provider options from scratch.

## Two Distinct Data Needs

It's worth separating these, because free options cover one well and the other barely at all:

1. **Index membership over time** ("was ticker X in the S&P 500 on date Y?") — needed to build the *universe* at each historical rebalance/formation date.
2. **Vintage fundamentals** ("what did the 10-K say for FY2015, using only data available as of the 2015 filing date, not today's restated figures") — needed so factor construction (quality, value) doesn't leak later restatements or amendments backward.

Most free sources solve (1) reasonably well for large-cap US equities. Solving (2) well generally requires a paid vendor or SEC EDGAR's own `filed` timestamps (see [SEC EDGAR Fundamentals](edgar-fundamentals.md) — the `extract_annual()` dedup-by-`filed`-date logic there is already vintage-aware for XBRL facts, which is a meaningfully under-appreciated free win).

## Provider Comparison

| Source | Membership History | Fundamentals Vintage-Aware | Cost | Coverage | Status in George's Stack |
|--------|:-:|:-:|------|----------|--------------------------|
| **fja05680/sp500** (GitHub) | 1996+ (reliable 2001+) | ❌ (membership only) | Free | S&P 500 only | ✅ Documented in `survivorship-bias.md`, not yet wired into a production universe builder |
| **Wikipedia revision API** | ~2010+ | ❌ | Free | S&P 500 only, gaps pre-2010 | ✅ Documented, unused (incomplete during rapid rebalances) |
| **SEC EDGAR XBRL `filed` dedup** | N/A (not membership) | ✅ (2009+, via amendment `filed` date) | Free | All US filers | ✅ Already implemented in `edgar-fundamentals.md`'s `extract_annual()` |
| **SEC EDGAR SIC codes** | Point-in-time via `submissions/CIK{cik}.json` | N/A (sector, not fundamentals) | Free | All US filers | ✅ Documented in `sector-classification.md` |
| **Norgate Platinum** | 1990+, all US indices incl. delisted | ✅ | ~$800-1,500/yr | Broad US equity | ❌ Not subscribed |
| **Sharadar (Nasdaq Data Link)** | Partial PIT | ✅ (integrated with prices) | Custom quote | US equity | ❌ Not subscribed |
| **WRDS CRSP** | 1926+, gold standard | ✅ | ~$10k+/yr | Academic-grade | ❌ Not subscribed — institutional/academic pricing, out of scope |
| **Bloomberg PORT/Terminal** | Full PIT | ✅ | Enterprise | Universal | ❌ Not subscribed |

## Decision Framework: When Is Free Good Enough?

This mirrors the judgment call already made in `survivorship-bias.md` for the current H241-H246 large-cap universe, generalized:

- **Large-cap, low-turnover universe (S&P 500 top ~200 by market cap)**: fja05680 CSV + accept the residual bias. Large caps rarely delist mid-backtest; the paper-documented impact estimate is **<0.1 Sharpe** for this universe class (per `survivorship-bias.md`).
- **Small/mid-cap or high-turnover universe (NASDAQ 30-100 tech names, as in H277)**: free sources are **not sufficient**. H277 explicitly hit this wall — a hand-picked 30-stock NASDAQ/tech universe selected with 2026 foreknowledge of which names survived inflated OOS Sharpe from a legitimate-looking 1.22 down to what would likely be a materially worse honest number. This is the highest-value place to spend on Norgate or Sharadar if the strategy family (momentum, sector rotation) is to be taken past the research/ideation stage.
- **Sector-neutral or industry-adjusted signals (H158, H181)**: need PIT *sector* assignment, not just membership — combine EDGAR SIC point-in-time lookups (`sector-classification.md`) with a PIT membership list. Neither alone is sufficient; GICS reclassifications (e.g., a stock moving from Consumer Discretionary to Communication Services) can silently bias within-sector ranking if you apply today's GICS code retroactively.
- **ML-driven multi-factor strategies with large universes (H167-style)**: this is the case that most clearly justifies a paid subscription — bias-corrected factor construction across hundreds of names essentially requires Compustat/CRSP-grade data; free sources were the explicit blocker cited when H167 was flagged for Kevin review rather than queued.

## Practical Next Step (Not Yet Built)

None of H158, H167, or H277 have actually been unblocked yet — all three remain in DEFERRED/BLOCKED/NOT-FOR-PRODUCTION status specifically because this data gap was never closed. A concrete, low-cost next step that hasn't been tried: wire the existing `fja05680/sp500` CSV (already documented, unused in production) into a shared `build_pit_universe(formation_date)` utility importable by any hypothesis script, rather than each hypothesis re-implementing its own inline universe fetch. The function already exists in `survivorship-bias.md`'s "Practical Build" section — it just hasn't been promoted to a shared module under `backtesting/` that H158/H167/H277-style hypotheses could import directly. If free-tier PIT membership turns out to still be the binding constraint after that (as expected for H167's ML-multi-factor case), that's the trigger point to revisit a Norgate or Sharadar subscription with a concrete cost/benefit case in hand.

## Related Pages

- [Survivorship Bias & Universe Construction](../backtesting/survivorship-bias.md) — the bias mechanism, impact estimates, and the free-tier `build_pit_universe()` implementation this page's provider table supports
- [Sector & Industry Classification](sector-classification.md) — the PIT sector-assignment half of the H158/H181 problem
- [SEC EDGAR Fundamentals](edgar-fundamentals.md) — free vintage-aware fundamentals via XBRL `filed` timestamp dedup
- [Hypothesis Log](../backtesting/hypothesis-log.md) — H158 (DEFERRED), H167 (BLOCKED), H277 (CONFIRMED, NOT FOR PRODUCTION) all cite this exact data gap
