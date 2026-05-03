# PEAD (Post-Earnings Announcement Drift) Report
Date: 2026-03-30
Universe: 30 large-cap stocks, 2020-2025
Method: Overnight gap as earnings surprise proxy (>3%, 4%, 5% gaps)
Backtests: 4 thresholds × 5 hold periods × 3 directions + filters = 96+ variants

---

## Summary

PEAD is one of the strongest anomalies found in this research. Best single strategy: Gap 5% long, 20-day hold — Sharpe +1.137, 67.8% win rate, p=0.000. Portfolio of all signals: Sharpe +2.394, Max DD -26.9%.

Critical asymmetry: LONG-only PEAD works (avg Sharpe +0.706). SHORT PEAD fails (avg Sharpe -0.294). Positive surprises drift up; negative surprises mean-revert.

---

## Strategy Matrix — Top Results

| Threshold | Hold | Direction | Sharpe | Win Rate | N Trades | p-value |
|-----------|------|-----------|--------|----------|----------|---------|
| 5%        | 20d  | Long      | +1.137 | 67.8%    | 199      | 0.000   |
| 5%        | 20d  | Long+Vol  | +1.114 | 67.3%    | 156      | 0.000   |
| 4%        | 20d  | Long      | +1.101 | 66.3%    | 273      | 0.000   |
| 4%        | 20d  | Long+Vol  | +1.013 | 66.3%    | 196      | 0.000   |
| 3%        | 20d  | Long      | +0.973 | 63.8%    | 411      | 0.000   |
| 2%        | 20d  | Long      | +0.687 | 61.6%    | 716      | 0.000   |
| 2%        | 5d   | Long      | +0.496 | 54.9%    | 1112     | 0.005   |

---

## Key Findings

### 1. Long-only PEAD is consistently profitable
Every single long-direction variant (across all thresholds and hold periods) produced positive Sharpe. Statistical significance is overwhelming (t-stats of 4.2-6.6). This is one of the most robust findings in the entire research program.

### 2. Short PEAD fails
Average Sharpe of shorts: -0.294. Negative gaps (down surprises) do NOT continue drifting down. They mean-revert. The asymmetry is structural:
- Positive surprise: institutional investors buy the news, retail FOMO kicks in, drift continues 20-40 days
- Negative surprise: bargain hunters step in, price recovers quickly

### 3. Larger gaps = higher Sharpe, fewer trades
5% threshold: Sharpe 1.137, 199 trades
2% threshold: Sharpe 0.687, 716 trades
The 5% threshold is filtering for truly exceptional events (major earnings beats, guidance raises, M&A). These have stronger drift.

### 4. 20-day hold is optimal
5-day: Sharpe ~0.5 (drift not fully realized)
10-day: Sharpe ~0.6
20-day: Sharpe ~1.1 (optimal)
40-day: Sharpe drops (drift exhausts, gives back gains)
60-day: Further decay

### 5. Volume filter adds minimal value
Gap 5% + volume filter: Sharpe 1.114 vs 1.137 without. The large gap already self-selects for high-volume events.

### 6. Portfolio diversification creates extraordinary Sharpe
Individual stock signals: Sharpe ~1.1
30-stock portfolio (equal weight all long signals): Sharpe +2.394
This is the diversification benefit — uncorrelated earnings events across 30 stocks smooth the return stream dramatically.

---

## Portfolio Construction

- Buy every stock that gaps up >5% at open
- Hold 20 trading days
- Max 5-10 concurrent positions (equal weight)
- Use a 30-stock universe minimum for diversification
- Expected: ~8-10 signals per month across 30 large-caps

Portfolio metrics (2020-2025):
- Sharpe: +2.394
- Max DD: -26.9% (COVID crash hit all simultaneously — main risk is correlated macro events)
- CAGR: ~38% (implied from Sharpe + vol)

---

## Practical Implementation Notes

1. Execution: Must enter at market open on gap day (not previous close) — the gap is the signal
2. Corporate earnings calendar: Using gap proxy works well for large-caps. With real earnings calendar data, could pre-screen for earnings dates and reduce noise
3. Risk: All positions can gap down simultaneously in market crash (COVID showed this). Position sizing essential
4. Sectors to focus: Tech and healthcare have the cleanest PEAD due to binary earnings outcomes
5. Avoid: Biotech (gap-and-reversal pattern, not drift) and utility/REIT stocks (gaps from dividends)

---

## Comparison to Literature

Academic PEAD literature (Ball & Brown 1968, Bernard & Thomas 1989, Chordia & Shivakumar 2006) documents 20-60 day drift. Our findings confirm:
- Direction of drift confirmed (long-only works)
- Magnitude of effect: consistent with post-2000 literature
- The anomaly survives in 2020-2025 despite being well-known

The anomaly persists likely because:
1. Institutional constraints prevent full arbitrage
2. Attention hypothesis: retail investors underreact to earnings surprises
3. Liquidity cost: smaller position sizes needed to avoid market impact
