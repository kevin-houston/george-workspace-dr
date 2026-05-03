# Dividend Strategies

*Dividend strategies (Round 27) produced the highest single-strategy Sharpe in Kevin's entire research corpus: Div Raise >=10%, hold 40 days achieves Sharpe +4.403. The key insight is that dividend raises are fundamentally similar to PEAD — they are quality/commitment signals that trigger institutional accumulation, producing multi-week post-announcement drift. The research covered 88 tickers, 10 years, ~12,000+ events.*

---

## Results Summary

| Strategy | Sharpe | Win Rate | n | Notes |
|----------|--------|----------|---|-------|
| Div Raise >=10% hold-40d | **+4.403** | 64.9% | 345 | Highest in corpus, p=0.000 |
| Div Raise >=5% hold-40d | +3.400 | N/A | N/A | More signals, slightly weaker |
| CC around Ex-Div 10d | +2.643 | N/A | N/A | Sell calls pre-ex-div; 3x better than generic CCs |
| Div Capture buy-3d sell+5d | +1.578 | N/A | N/A | Pre-ex-div institutional accumulation |
| Ex-Div Drift hold-20d | +1.511 | N/A | N/A | Post-ex-div continuation |
| Dogs of the Dow top-10 | +1.203* | N/A | N/A | *Annual Sharpe, p=0.003; mean return 15.3% |

---

## Dividend Raise Signal: Why It Works

The mechanism is identical to [[pead-strategy]]:
1. **Dividend raise = fundamental commitment signal** — management signals confidence in future earnings
2. **We enter on ex-date, not announcement date** — captures the POST-announcement institutional drift
3. **Larger raises produce stronger drift**: >=10% raise is a stronger commitment than >=5%
4. **40-day hold** is optimal — same drift duration as PEAD
5. **Win rate 64.9%, p=0.000** — statistically ironclad
6. **Implementation note**: Actual announcement-date entry would capture more drift and produce even higher Sharpe (we enter at ex-date, which lags the announcement by 2-6 weeks)

---

## Covered Calls Around Ex-Dividend (CC Ex-Div)

- **Strategy**: Sell calls 2% OTM, 10 days before ex-date
- **Sharpe**: +2.643 — approximately 3x better than generic monthly covered calls (R25: +0.836)
- **Why it outperforms**: IV spikes predictably before ex-dates as market makers price in the dividend uncertainty; selling calls captures the IV crush
- **Best on**: Slow-moving dividend names (KO, MO, T, VZ, PG) — same universe as regular covered calls

---

## Dividend Capture

- **Strategy**: Buy 3 days before ex-date, sell 5 days after
- **Sharpe**: +1.578
- **Mechanism**: Institutional accumulation begins several days before ex-date (to own the dividend); selling pressure clears within 5 days post-ex
- **Risk**: Individual events can go wrong if market corrects near ex-date; diversify across multiple names

---

## Ex-Dividend Drift

- **Strategy**: Buy on ex-date, hold 20 days
- **Sharpe**: +1.511
- **Mechanism**: Similar to PEAD — post-ex-div continuation as income-seeking investors continue to accumulate; stock re-rates slightly upward after dividend confirmation

---

## Dogs of the Dow

- **Strategy**: Buy the 10 highest-yield DJIA stocks at year-start; hold 1 year
- **Sharpe**: +1.203 (annual)
- **Mean return**: 15.3%
- **p-value**: 0.003 — statistically significant
- **Still works in 2015-2025** — classical value-yield strategy has not decayed

---

## What Doesn't Work

| Strategy | Sharpe | Notes |
|----------|--------|-------|
| Dividend Cut Short | -2.937 | Cuts = restructuring signal in bull markets → bounce |
| High Yield Screen | +0.448 (with -45% Max DD) | Value traps; risk-adjusted terrible |
| Dividend Initiation | Insufficient events | Fortune 100 universe: all established payers |

**Critical**: Never short dividend cuts in a secular bull market. The restructuring announcement precedes fundamental improvement; the bounce is the signal, not the cut.

---

## Implementation Notes

- **Universe**: Fortune 100 dividend-paying stocks (88 tickers in R27)
- **Data requirements**: Dividend history, ex-dates, announcement dates (Yahoo Finance has all of this)
- **Covered call around ex-div**: Requires options chain access (Robinhood supports this)
- **Live implementation**: Robinhood can handle all these strategies; ex-date data is freely available

---

## Related Topics

- [[pead-strategy]] — Same mechanism, earnings context
- [[options-strategies]] — Covered calls detail
- [[trading-strategies-leaderboard]] — Full leaderboard context
- [[portfolio-allocation]] — Where dividend strategies fit

## Sources
- Master Trading Report (R27 section): raw/master_trading_report_2026-04-05.md
- Memory Snapshot (R27 findings): raw/MEMORY_snapshot_2026-04-05.md
