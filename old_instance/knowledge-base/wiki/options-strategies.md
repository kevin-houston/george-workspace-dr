# Options Strategies

*Options research spans two rounds: R25 (covered calls, cash-secured puts, earnings straddles, VIX strategies) and R28 (bull put spreads, iron condors, wheel strategy, VRP harvest, gamma scalping, VIX puts). The master finding is that IV rank is the non-optional filter for all premium-selling strategies. Best deployable results: bull put spreads on energy/defensive names (Sharpe +2.584 on XOM) and covered calls around ex-dividend dates (Sharpe +2.643). Worst: short VIX outright (Sharpe -4.975). See also: Squid Programs (VIX term structure dynamic allocation) — external whitepaper, Sharpe 1.27-1.31, potential R34+ candidate.*

---

## Round 25: Covered Calls and Baseline Options

Universe: Fortune 100 dividend stocks | Period: 2015-2025 | Black-Scholes simulation

### Results

| Strategy | Best Result | Avg Result | Notes |
|----------|-------------|------------|-------|
| Covered Calls | IBM: Sharpe +0.836 | +0.533 | Best on slow-moving dividend names |
| Cash-Secured Puts | N/A | +0.210 | Works but lower than CCs |
| Earnings Straddles | N/A | Inflated | Look-ahead bias; doesn't survive slippage |
| Protective Puts on PEAD | N/A | Collapses PEAD to 0.25 | Insurance cost overwhelms the signal edge |
| VIX Short Vol (XIV-style) | N/A | **-4.975** | Fatal: Feb 2018 and Mar 2020 destroyed all gains |

### Covered Call Rules
- Sell 30-day OTM calls on dividend stocks
- **Best universe**: IBM, MCD, KO, MO, T, VZ, PG (slow-moving, high-div)
- **Avoid**: NVDA, TSLA, high-growth names — missed recoveries compound to -0.130/yr vs BH
- IBM best at Sharpe +0.836, CAGR ~9.2%, Max DD -16.1%
- **Implementation note**: Black-Scholes with 20d realized vol as IV proxy; actual slippage would reduce by ~15-20%

### Critical Lesson: Never Protect PEAD with Puts
- Adding 2% protective puts to PEAD: Sharpe collapses 4.46 → 0.25
- The insurance cost overwhelms the drift premium entirely
- Alternative: size PEAD positions small (1-3% per position) instead of hedging

---

## Round 28: Options Deep Dive

Universe: 30 tickers + ^VIX | Period: 2020-2025 | 6 strategies
Methodology: IV = realized_vol × 1.03 (3% VRP modeled); IV rank = percentile of IV over trailing 252 days

### Results

| Strategy | Best | Avg | Win Rate | Notes |
|----------|------|-----|----------|-------|
| Bull Put Spread (IV rank>50%) | XOM: +2.584 | +0.744 | 85.7% (XOM) | Defined risk; best deployable |
| Bull Put Spread CVX | +2.470 | N/A | N/A | Energy sector |
| VIX Short Put | +0.846 | +0.846 | 88.6% | Structural floor strategy |
| Iron Condor (IV rank>50%) | N/A | +0.523 | 62.8% | Best on low-vol names |
| VRP Harvest (straddle, IV rank>40%) | QCOM: +1.651 | +0.499 | N/A | IV rank filter non-optional |
| Gamma Scalping | N/A | +0.413 | N/A | Real edge; transaction costs eliminate at retail |
| Wheel Strategy | N/A | +0.312 | N/A | -0.130/yr vs BH; skip on growth stocks |
| VRP Harvest (no filter) | N/A | **-0.086** | N/A | Negative without IV rank filter |
| Long VIX Call | N/A | N/A | 14.3% | Lottery ticket; hedge only |

### IV Rank Filter: The Master Key
**All premium-selling strategies improve dramatically when filtered by IV rank.**

- VRP Harvest without filter: Sharpe -0.086 (negative!)
- VRP Harvest with IV rank>40%: Sharpe +0.499 (positive)
- Iron condor: only enter when IV rank > 50%
- Bull put spreads: only enter when IV rank > 50%

The rule is simple: only sell options premium when options are expensive relative to their recent history.

### Bull Put Spreads: Best Deployable Options Strategy

- Sell OTM put, buy further OTM put (defined risk)
- Best names: XOM (+2.584), CVX (+2.470), GE (+2.305)
- Energy and value names work best; avoid high-beta (NVDA, TSLA — max-loss events spike)
- Advantage over naked puts: defined maximum loss makes position sizing tractable
- Average across 30 tickers: +0.744

### VIX Short Put: Structural Edge

- **Strategy**: Sell puts on VIX below a certain strike (e.g., 20% OTM put on VIX)
- **Sharpe**: +0.846, Win Rate: 88.6%
- **Why it works**: VIX has a structural floor at ~9-10 (market makers need minimum hedging cost). A 20% OTM put strike is almost never breached.
- **Caveat**: This is an options simulation; actual execution on VIX options has specific rules (cash-settled, European-style)

### Wheel Strategy: Disappointing

- Sharpe +0.312 avg, but **underperforms buy-and-hold on 27 of 30 names**
- Avg gap vs BH: -0.130/yr
- Why: Wheel caps upside via covered calls on growth names that recover sharply
- Works on: PG, KO (slow/defensive names)
- Fails on: Anything with episodic large moves

---

## R32 (Queued): Index Put-Writing with VIX-Kelly Hybrid Sizing

Inspired by arXiv:2508.16598 (Aug 2025):
- **Strategy**: Systematic SPX/SPY put-writing at far OTM (delta 0.10-0.15), short-dated (0-14 DTE)
- **Sizing**: VIX-Kelly hybrid = Kelly fraction × (20/VIX). Best Sharpe AND lowest drawdown.
- **Why VIX-Kelly hybrid wins**: Kelly alone maximizes return; VIX-scaling alone reduces drawdown; hybrid achieves both
- **Cap**: 2x base size maximum to avoid ruin
- **Complementary to R25**: R25 covered calls = individual stocks; R32 put-writing = index-level VRP. Different risk sources, can run in parallel.
- **Implementation**: Only needs yfinance + FRED; can run now

---

## External Research: VIX Spikes as Opportunity Markers

**Source**: "Volatility, The VIX, and Opportunity" — Joshua Lawson, CIO, Mu Hat Capital Management  
**URL**: https://muhat.com/blog/volatility-the-vix-and-opportunity  
**Date**: March 30, 2026 (re: current Mar 2026 VIX spike, peak 35.3)

### Key Thesis

VIX spike episodes (monthly VIX high > 30) historically mark favorable *entry* points, not warning signs. The article presents forward returns for Hound Dog Partners (an opportunistic L/S equity strategy) after each VIX spike since 2020:

| Episode | Peak VIX | Next 3M | Next 6M |
|---------|----------|---------|---------|
| Apr–Jul 2020 | 60.6 | +18.4% | +115.2% |
| Sep 2020–Mar 2021 | 41.2 | +1.5% | +9.5% |
| Dec 2021–Jun 2022 | 38.9 | +14.1% | +15.5% |
| Sep 2022–Oct 2022 | 34.9 | +31.3% | +60.9% |
| Mar 2023 | 30.8 | +48.3% | +68.4% |
| Aug 2024 | 65.7 | +71.0% | +67.9% |
| Apr 2025 | 60.1 | +43.2% | +77.0% |
| **Mar 2026** | **35.3** | ? | ? |

- **Average (7 resolved episodes)**: +32.5% next 3M, +59.2% next 6M
- Positive in **all 7** observable cases
- Note: performance is hypothetical/model-based for Hound Dog Partners (2%/20% fee structure), not audited

### Applicability to Our Research

- **Contradicts our VIX kill switch** (R28/R29/R33 pause at VIX > 25): Lawson's data shows VIX spikes are when *opportunistic* strategies perform best — but the strategies differ fundamentally (L/S equity vs. LLM-signal momentum)
- **Consistent with our LLM kill switch research** (arXiv:2604.10996): LLM features specifically collapse during macro shocks — separate issue from whether the market itself is a buying opportunity
- **Potential signal**: VIX > 30 may be a regime where *mean reversion* and *pairs trading* (R29) thrive while *momentum/LLM signals* (R28/R33) should pause — regime-dependent strategy rotation
- **Not yet tested**: Whether our backtest strategies show the same post-spike positive skew as an opportunistic L/S fund

---

## General Options Lessons

1. **IV rank is non-optional** for all premium selling
2. **Covered calls best on dividend names**: KO, MO, T, VZ, PG — not on growth
3. **Never short VIX outright**: Feb 2018 and Mar 2020 are permanent fixtures in the tail risk history
4. **Protective puts are too expensive**: Position sizing small beats insurance hedging on high-Sharpe strategies like PEAD
5. **Gamma scalping at retail scale**: Edge is real but transaction costs erase it

---

## Related Topics

- [[dividend-strategies]] — CC around ex-div (Sharpe +2.643)
- [[pead-strategy]] — Why protective puts destroy PEAD
- [[trading-strategies-leaderboard]] — Full options results
- [[research-agenda]] — R32 put-writing design spec

## Sources
- Master Trading Report (R25, R28 sections): raw/master_trading_report_2026-04-05.md
- Memory Snapshot (R25 heuristics, R32 design): raw/MEMORY_snapshot_2026-04-05.md
- Heuristics Snapshot (options lessons): raw/heuristics_snapshot_2026-04-05.md
