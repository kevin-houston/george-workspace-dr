---
updated: 2026-04-24
---

# Backtesting Design Principles

These constraints must be baked into the backtesting framework from the start, not bolted on later.

---

## 1. Macroeconomic regime awareness

Strategies that work in a bull market often fail in a bear market or stagflation. Backtests must be evaluated across regimes, not just in aggregate.

### Regimes to model

| Regime | Key indicators | Asset behavior |
|--------|---------------|----------------|
| Expansion | Rising GDP, low unemployment, earnings growth | Growth/tech outperform |
| Peak | High inflation, Fed tightening, yield curve flat | Rotate to value, commodities |
| Contraction/Recession | Falling GDP, rising unemployment, credit spreads widen | Defensives, cash, short duration |
| Recovery | Stimulus, loose monetary policy, credit easing | Cyclicals, small caps outperform |

### Data sources for macro context

- **FRED (Federal Reserve)**: GDP, CPI, unemployment, Fed funds rate, yield curve — free via `fredapi` (`pip install fredapi`)
- **EDGAR**: Earnings season context, sector financials
- **VIX**: Market fear/volatility regime proxy (available free from CBOE/Alpaca/Polygon)
- **Yield curve**: 2yr/10yr spread — key recession signal

### Implementation approach

- Tag each backtest period with the prevailing regime
- Report strategy performance broken out by regime (not just overall Sharpe)
- Flag strategies that only work in one regime as fragile
- Consider regime-conditional position sizing or strategy switching

---

## 2. Tax burden

High gross returns can become mediocre after-tax returns, especially for high-turnover strategies. All performance metrics should be presented on an **after-tax basis**.

### Key rules (US, 2026)

| Holding period | Tax treatment | Rate (approx, single filer) |
|---------------|--------------|---------------------------|
| < 1 year | Short-term capital gains | Ordinary income rate (up to 37%) |
| ≥ 1 year | Long-term capital gains | 0%, 15%, or 20% |
| Options (equity) | Short-term unless exercised into long-term position | Same as STCG |
| Index options (1256 contracts) | 60% long-term / 40% short-term (60/40 rule) | Blended ~26.8% max |

### Wash sale rule

Selling a security at a loss and buying it back within 30 days (before or after) disallows the loss for tax purposes. High-frequency tax-loss harvesting strategies must track this.

### Practical impact

- A momentum strategy with weekly rebalancing: all gains are STCG — subtract ~37% from gross returns
- A buy-and-hold strategy: LTCG rates apply — 15-20% for most investors
- **Rule of thumb**: high-turnover strategies need ~1.5–2x the gross return of low-turnover strategies to net the same after-tax income

### Implementation approach

- Track holding period for every position in the backtester
- Apply appropriate tax rates to realized gains/losses
- Model wash sale disallowance for loss-harvesting positions
- Report: gross return, estimated tax drag, net after-tax return
- When comparing strategies, rank by **after-tax Sharpe ratio**, not gross Sharpe

### Kevin's tax situation

- Need to understand marginal rate to apply correct STCG rate
- Options strategy tax treatment depends on contract type (equity vs index)
- TODO: confirm Kevin's approximate tax bracket so we apply the right rates

---

## 3. Other real-world costs to model

- **Slippage**: assume 0.05–0.1% per trade for liquid large-caps; more for small-caps
- **Commission**: Alpaca is commission-free, but note payment for order flow (PFOF) means fills may not be at best price
- **Bid-ask spread**: especially important for options, where spreads can be 1–5% of premium
- **Margin costs**: if using leverage, apply current margin interest (~5–8% annually)
- **Dividends**: include in total return calculations

---

## 4. Performance metrics to report (after-tax)

- After-tax net return (annualized)
- After-tax Sharpe ratio
- Max drawdown
- Win rate and avg win/loss ratio
- Performance by macro regime
- Tax drag (gross minus net return)
- Calmar ratio (return / max drawdown)
