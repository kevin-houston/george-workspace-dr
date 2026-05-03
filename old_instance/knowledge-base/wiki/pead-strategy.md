# PEAD Strategy (Post-Earnings Announcement Drift)

*Post-Earnings Announcement Drift (PEAD) is Kevin's single highest-performing standalone strategy category, with the 30-stock portfolio achieving Sharpe +2.394 and ~38% CAGR. It exploits the documented academic phenomenon that stocks gapping up significantly on earnings continue to drift upward for 20+ days as institutional investors accumulate after confirming the fundamental quality of the beat.*

---

## The Signal

- **Entry**: Buy any stock that gaps up >5% at market open on an earnings day
- **Universe**: 30 large-cap Fortune 100 stocks, 2020-2025
- **Hold period**: 20 days optimal (drift exhausts after ~40 days)
- **Position sizing**: 10 concurrent positions max, equal weight
- **Long-only**: The short side does NOT work — negative surprise gaps mean-revert, not drift down

---

## Results Summary

| Strategy Variant | Sharpe | Win Rate | Notes |
|------------------|--------|----------|-------|
| PEAD Portfolio (30-stock) | +2.394 | N/A | Best portfolio Sharpe in corpus |
| PEAD gap5% 20d (single signal) | +1.137 | 67.8% | p=0.000 |
| Baseline (all signals) | +0.771 | 51% | R26 subset, 80 events |

- **Max DD**: -26.9% (correlated crash risk — all positions hit simultaneously in COVID-style events)
- **Annualized CAGR**: ~38% at portfolio level

---

## Key Asymmetry

- Long-only avg Sharpe: +0.706
- Short avg Sharpe: -0.294
- **Positive surprise gaps drift UP; negative surprise gaps mean-REVERT** (not drift down)
- Never short PEAD signals — the mechanism does not apply in reverse

---

## Why PEAD Works

Dividend raise signal and PEAD share the same underlying mechanism: institutional investors cannot fully absorb a fundamental positive surprise at the initial announcement. Continued drift reflects:
1. Large institutions slowly accumulating (cannot fill in one session)
2. Analysts upgrading with a delay (earnings call → model update → rating change = days)
3. Retail FOMO following institutional buying

---

## Live Paper Trading Status

- **Status**: In preparation — paper trading pilot planned as Round 29 (now deferred to post-R28)
- **Implementation**: Buy stock gapping >5% on earnings at open, hold 20 days, 10 concurrent positions max
- **Infrastructure**: Robinhood portfolio; live market data access required (runs on MX Linux host, not container)

---

## LLM Filtering Results (R26) ⚠️ Do Not Filter

Round 26 tested IndicatorAgent (LLM-based technical scoring) as a signal filter:
- Baseline PEAD (all signals): Sharpe 0.771
- LLM-confirmed signals: Sharpe 0.716 — WORSE
- LLM-rejected signals: Sharpe 0.904 — BETTER THAN BOTH

**The LLM penalizes exactly the setup that works.** PEAD fires when RSI is elevated (60-75+) and price is extended above moving averages — conditions the IndicatorAgent correctly identifies as "overbought." But institutions chasing an earnings beat don't care about chart aesthetics. The "ugly" setup IS the signal.

See [[llm-signal-research]] for full R26 analysis.

---

## R30: Multi-Quarter SUE Elastic Net (Completed 2026-04-03)

Tested Kaczmarek & Zaremba (2025) methodology: elastic net on 12 quarters of SUE history.

- **Elastic Net (12-Q SUE)**: Sharpe 0.493
- **Single-Quarter SUE baseline**: Sharpe 0.640
- **Paper's 2x improvement did NOT replicate** on 22 large-caps

Why it failed: The model learned general equity drift (long 98.5% of signals), not earnings signal. When frequency-adjusted, both models produce ~Sharpe 1.21-1.22 annualized. The paper likely used 500+ stocks including mid-caps where persistent negative drift exists.

**Verdict**: Single-Q SUE (Sharpe 1.40) still beats 12-Q elastic net (Sharpe 1.25). Complexity not justified at this universe size. Real fix: expand to 100-200 stocks including mid-caps.

---

## Upcoming Enhancements

### Round 28 (Queued): TradingAgents Multi-Agent Overlay
- **Hypothesis**: Fundamental/news LLM filter HELPS PEAD (unlike indicator filter which hurt)
- **Architecture**: EarningsQualityAgent + NewsAgent + RegimeGuard
- **Key distinction**: Asking "is this an organic earnings beat?" vs. "is the chart overbought?"
- **Amendment**: Use mini-RAG corpus per event (8-K + headlines + guidance) — bare LLM calls fail (R26 lesson)
- **Success criteria**: Filtered Sharpe > 2.394

### Round 31 (Queued): Text-Based PEAD
- **Source**: PEAD.txt methodology (JFQA 2022, Meursault et al.)
- **Signal**: FinBERT on earnings call transcripts → text surprise metric
- **Expected alpha**: 3.9 bps/day vs 2.6 bps/day (50% stronger than numeric SUE)
- **Critical advantage**: Text signal PERSISTS in recent years when numeric PEAD has decayed to ~0
- **Key insight**: Q&A section carries more signal than prepared remarks; weight Q&A 1.5x

---

## Related Topics

- [[llm-signal-research]] — R26 findings, why LLM hurts PEAD
- [[trading-strategies-leaderboard]] — Full leaderboard context
- [[research-agenda]] — R28, R31 design specs
- [[ml-for-trading]] — ML overlay potential

## Sources
- Master Trading Report: raw/master_trading_report_2026-04-05.md
- Memory Snapshot (R27, R30 results): raw/MEMORY_snapshot_2026-04-05.md
