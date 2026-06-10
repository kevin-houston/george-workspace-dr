# Nightly Research Session Summary — 2026-06-09

## Hypotheses Tested: H270–H273

### Overview

4 hypotheses tested across 3 strategy families: Low-Volatility Anomaly, ETF Pairs Trading, NASDAQ Stock Momentum, and a Vol-Targeting overlay. 3 of 4 confirmed (2 with important caveats).

---

## H270 — CONFIRMED: Low-Volatility Anomaly (Momentum+Low-Vol Dual Ranking)

**Result:** OOS Sharpe=1.290, CAGR=14.5%, MaxDD=-8.7%, NegYrs=0

**Key finding:** Pure low-vol ETF rotation (USMV/SPLV/XLU) FAILS in rate-hike environments (2022 MaxDD=-19% even for "low vol" ETFs). But combining momentum rank + inverse vol rank across a 9-asset universe (adding sector ETFs for diversification) produces a genuine satellite signal.

**Signal:** Top-1 asset by `(12m momentum rank) + (inverse 12m vol rank)` from {USMV, SPLV, XLU, SPHD, XLK, XLF, XLE, XLV, BIL}. The key insight: in 2022, XLE (energy) had both strong momentum AND relatively lower vol vs growth stocks — the dual-rank correctly rotated there.

**Corr(Production)=0.512** — moderate correlation, some diversification value.

**Verdict:** Viable satellite at 5-10% allocation. No production changes yet — needs forward test.

---

## H271 — NOT CONFIRMED: ETF Pairs Trading

**Result:** Best OOS Sharpe=0.131 (XLK/SOXX). All 5 pairs failed.

**Key finding:** Only XLF/KRE passed the IS cointegration test, but still failed OOS (-0.080 Sharpe). The ETF creation/redemption arbitrage mechanism prevents pairs trading from working. This replicates H246's finding.

**Conclusion:** ETF pairs trading family CLOSED. IS cointegration is not predictive of OOS profitability for ETFs.

---

## H272 — CONFIRMED (with severe survivorship bias caveat)

**Result:** Variant C (12-0 momentum, Top-5): OOS Sharpe=2.509, CAGR=84.8%, NegYrs=0

**⚠️ CRITICAL CAVEAT:** The 25-stock fixed universe includes NVDA (+3684% in 2018-2025). The results are dominated by one stock with known 2025 survivorship. NOT FOR PRODUCTION.

**Genuine finding:** Among the valid structural insights:
- 12-0 momentum (include most recent month) beats 12-1 on NASDAQ stocks: suggests short-term reversal is weaker for high-growth tech than for value stocks.
- Even Variants A/B (12-1 Top-5/Top-10) show OOS Sharpe 1.16-1.23 vs QQQ 0.995 — some genuine signal exists, but the magnitude is inflated by survivorship.

**Next step:** H272b — rebuild with true historical NASDAQ-100 constituent lists. Alternatively, test on QQQ sub-sectors using known start dates.

---

## H273 — CONFIRMED: Vol-Targeted Production Portfolio Overlay

**Result:** At vol_target=12%, lookback=3mo: OOS Sharpe=4.200 (baseline 4.010, +0.190 improvement). All years positive. CAGR 22.7% → 35.1%.

**Key finding:** Vol-targeting works UPWARD for this portfolio — because the production portfolio has near-zero negative years and consistently low realized vol, the overlay mostly scales UP leverage (avg ~1.3x), amplifying already-positive returns. The vol signal does protect in 2022 (+23.9% vol-targeted vs +15.5% baseline).

**Optimal params:** vol_target=12%, lookback=3mo, max_leverage=1.5x.

**Implementation challenge:** Requires ~1.3x average leverage. At current margin rates (~5.5%), annual drag ~1.5%. Net improvement ~+0.10 Sharpe after leverage cost — still positive but reduced.

**Verdict:** CONFIRMED. Worth paper-trading with margin simulation before live deployment. No production changes yet.

---

## Session Statistics

| Metric | Value |
|--------|-------|
| Hypotheses tested | 4 (H270-H273) |
| Confirmed | 3 (H270, H272*, H273) |
| Not confirmed | 1 (H271) |
| New strategy families opened | 1 (Low-vol anomaly via dual rank) |
| Families closed | 1 (ETF pairs trading) |
| Scripts written | 4 |
| Data downloads | ~20 new tickers cached |

*H272 confirmed with severe survivorship bias — results not actionable without clean historical constituent data.

---

## Production Portfolio Status

**Unchanged.** H041a 22% / H026 27% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%.

No hypotheses from this session were added to production:
- H270: Needs 6-month forward test first (low-vol satellite candidate)
- H273: Needs leverage cost analysis and paper-trade validation

## Next Research Directions

1. **H272b** — Rebuild NASDAQ momentum with clean historical constituent data (Polygon or CRSP)
2. **H270b** — Longer IS period test (back to 2003) using XLU as USMV/SPLV proxy; test different lookbacks (6m, 3m)
3. **H260** (QUEUED) — PEAD Revival with 12-Quarter ML Features (LightGBM)
4. **H258** (QUEUED) — Text-to-Alpha LLM 10-Q shift detection overlay on H174
