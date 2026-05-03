# Backtesting Methodology

Research and lessons on backtesting rigor, robustness testing, and avoiding overfitting.

---

## Population-Level MA Filter Validation (@onlybreakouts, April 2026)

**Source**: https://x.com/onlybreakouts/status/2043752640522162215  
**Tool**: BreakoutOS (proprietary, launching April 2026)  
**Added**: 2026-04-13

### Methodology

Tested MA filters on a Nasdaq 60-min breakout strategy across ~1 million iterations:
- Base strategy: entry at prev_day_low + 0.8×ATR(40), exit EOD
- Test matrix: 1,000 strategy siblings × 1,000 market conditions
- This "population-level" approach exposes overfitting that single-curve backtests miss

### Results

| Filter | Population Result | Notes |
|--------|------------------|-------|
| Single EMA close filter | **FAILED** — collapses at population level | Looks good individually; adapts to noise, not signal |
| SMA close filter | **83% viability, +50% avg trade** | Period-insensitive (20–200 all work equally) |
| Dual EMA crossover (fast 10-20, slow 70-90, fast below slow at entry) | **Strongest across all metrics** | Broad flat optimization landscape = genuine structural edge |

### Key Lesson

**Flat optimization landscape = genuine edge.** When a filter works across a wide range of parameters (SMA 20–200 all perform similarly), it signals a structural effect, not a curve-fit. When performance peaks sharply at one parameter value and degrades quickly on either side, it's overfitting.

Single EMA appeared to add value on individual strategy curves — the population test revealed it was adapting to per-curve noise. SMA and dual EMA crossover survived because they capture something real in price structure.

### Relevance to Kevin's Research

- **R28/R29 robustness check**: The backtests use fixed parameter sets. A mini population test — shifting entry thresholds ±20%, varying hold periods, using universe subsets — would distinguish genuine edge from parameter fit before live deployment.
- **R33 and future strategies**: Before committing to a signal, test it across parameter neighborhoods. If the edge only exists at one precise value, treat it as fragile.
- **PEAD quality threshold (40)**: Worth checking: does the Sharpe degrade sharply if threshold = 35 or 45? Flat landscape would validate the filter; a sharp peak would suggest overfitting.
