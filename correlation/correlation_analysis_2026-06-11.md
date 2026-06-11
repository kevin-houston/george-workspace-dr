# Cross-System Correlation Analysis
Date: 2026-06-11 | Analysts: George + Ernesto

## Data Coverage

| Side | Strategies with closed trades | Total strategies |
|------|-------------------------------|-----------------|
| Ernesto (R-series) | 2 (R29_Pairs, R29_LLM) | 15 |
| George (H-series) | 0* | 5 |

*George's production strategies (H041a/H026/H045) are monthly ETF rotation — no live paper trades in the Alpaca account are cleanly attributable (account was polluted with legacy positions). PEAD paper trading has been scanning but no qualifying entries (score ≥ 0.18 AND surprise ≥ 0.02 not triggered during this period).

**Conclusion: Cross-system matrix is premature.** Only 2 of 20 strategies have sufficient closed-trade data.

---

## What We Can Say Now

### R29_Pairs vs R29_LLM (Ernesto-side only)

- R29_LLM correlation with R29_Pairs: **-0.259**
- 10 trade days for R29_Pairs, 2 for R29_LLM
- Interpretation: **Decorrelated — running both is justified.** The LLM filter selects a subset of pairs trades but doesn't fire on the same days. Negative correlation suggests LLM tends to catch different opportunities.
- Caveat: n=2 for R29_LLM is statistically thin. Treat as preliminary.

### George H-series internal correlation (expected)

H041a and H026 are both top-1 ETF momentum strategies — different universes (19 vs 25 assets) but the same mechanism. Backtest correlation not yet computed from paper data. **Prior: high correlation (~0.7-0.9).** This is the biggest structural overlap on the George side. Should be confirmed once clean paper data is available.

---

## Why the Matrix Is Sparse

1. Most strategies launched June 2026 — only 2 weeks of history
2. Low signal frequency: most strategies fire 0-2 trades/month in paper mode
3. George's Alpaca account contains legacy positions that contaminate P&L attribution
4. PEAD entry threshold (score ≥ 0.18 AND surprise ≥ 0.02) is intentionally high — not every earnings cycle produces candidates

---

## Recommendation

**Re-run this analysis in 60 days (target: ~2026-08-10).** By then:
- R29_Pairs should have ~20-25 trades (enough for stable correlation)
- R43_Regime and R41_Sentiment should have at least a few exits
- George's Alpaca account will be reset and PEAD will have a clean series
- H041a/H026 monthly rotation will have 2-3 more data points

**One actionable insight now:** R29_Pairs and R29_LLM appear decorrelated (-0.26). Running both is justified on current data.

**One structural flag now:** H041a + H026 are likely correlated (same mechanism, overlapping universe). Combined allocation should be treated as a single position for portfolio sizing purposes until backtest correlation is confirmed.

---

## Next Steps

1. Reset Alpaca paper account (Kevin action) → clean George P&L baseline from reset date
2. Re-run analysis 2026-08-10
3. Add SPY daily returns as benchmark column in next run (Ernesto's Q2 from action items)
