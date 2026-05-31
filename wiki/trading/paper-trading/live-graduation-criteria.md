---
added: 2026-05-30
updated: 2026-05-30
category: paper-trading
---

# Live Trading Graduation Criteria & Performance Attribution

Reference guide for deciding when paper trading results are statistically sufficient to deploy real capital, and how to decompose the performance gap between simulation and live execution.

---

## The Core Problem

Paper trading always overstates live performance. The three sources of bias are systematic and cannot be eliminated:

| Bias Source | Direction | Magnitude |
|------------|-----------|-----------|
| Instant fills at mid-price | Optimistic | 0.05–0.15% per trade |
| No market impact | Optimistic | Grows with order size |
| No psychological friction | Optimistic | Behavioral, hard to quantify |

Options paper trading is worst: fill prices can deviate up to 20% from live executions because of wide bid-ask spreads that simulators ignore. Equity strategies (H026, H181, PEAD) are more reliable — Alpaca paper uses realistic NBBO pricing.

---

## Minimum Trade Count Before Graduation

Statistical significance requires sufficient sample size. Use this table as a floor, not a ceiling:

| Metric | Minimum | Preferred |
|--------|---------|-----------|
| Monthly-rebalance strategies (H026, H181) | 6 months / 6 rebalances | 12 months |
| Event-driven strategies (PEAD H174) | 20 qualifying events | 30+ events |
| Daily strategies (IBS) | 60 trading signals | 100+ signals |

**Why 20–30 events for PEAD?** With a confirmed backtest WR of 81.8% (H174), the standard error on a 20-trade sample is ~√(0.82×0.18/20) ≈ 8.6pp. You need the live WR to stay above 65% (i.e., within 2 SE of backtest) to confirm the signal is intact.

---

## Statistical Graduation Gates

### Gate 1: SPRT (Sequential Probability Ratio Test)

The SPRT is the gold standard for sequential strategy validation — it minimizes the number of trades needed to reach a decision with controlled error rates. Unlike fixed-sample tests, it is valid to "peek" at intermediate results.

**Setup for PEAD (H174 baseline WR = 81.8%):**

```python
import numpy as np

# Hypotheses:
# H0: true WR = p0 = 0.60  (strategy no longer works — null)
# H1: true WR = p1 = 0.80  (strategy working as expected)
alpha = 0.05   # false positive rate (declare working when it isn't)
beta  = 0.10   # false negative rate (miss that it's working)

A = (1 - beta) / alpha      # upper threshold = 18.0 → log(A) = 2.89
B = beta / (1 - alpha)      # lower threshold = 0.105 → log(B) = -2.25

def sprt_update(n_wins, n_trials, p0=0.60, p1=0.80, alpha=0.05, beta=0.10):
    log_A = np.log((1 - beta) / alpha)
    log_B = np.log(beta / (1 - alpha))
    llr = n_wins * np.log(p1/p0) + (n_trials - n_wins) * np.log((1-p1)/(1-p0))
    if llr >= log_A:
        return "CONFIRM — go live"
    elif llr <= log_B:
        return "REJECT — strategy broken"
    else:
        return f"CONTINUE — need more data (LLR={llr:.2f}, range [{log_B:.2f}, {log_A:.2f}])"
```

For H026/H181 (monthly Sharpe strategies), use a one-sided t-test on monthly returns vs the backtest OOS mean.

**Setup for monthly-return strategies:**

```python
from scipy import stats

def sharpe_graduation_check(live_monthly_returns, backtest_oos_mean, backtest_oos_std,
                             min_months=6, alpha=0.10):
    """
    One-sided t-test: is live Sharpe significantly below backtest OOS?
    If not rejected → proceed to live.
    """
    n = len(live_monthly_returns)
    if n < min_months:
        return f"WAIT — only {n} months, need {min_months}"
    live_mean = np.mean(live_monthly_returns)
    live_std  = np.std(live_monthly_returns, ddof=1)
    live_sharpe = live_mean / live_std * np.sqrt(12)
    # Test H0: live_mean < backtest_oos_mean * 0.5 (strategy significantly degraded)
    # This is a conservative check: tolerate up to 50% degradation
    threshold = backtest_oos_mean * 0.5
    t_stat, p_val = stats.ttest_1samp(live_monthly_returns, threshold, alternative='greater')
    return {
        "live_sharpe_ann": live_sharpe,
        "p_value": p_val,
        "decision": "PROCEED" if p_val < alpha else "WAIT",
        "months": n
    }
```

### Gate 2: Regime Coverage Check

Paper trading results are only valid if the test period includes at least one meaningful drawdown or VIX spike. A strategy only tested in a low-volatility bull market period is unvalidated.

**Minimum regime coverage requirements:**

| Regime | Minimum exposure | Source |
|--------|-----------------|--------|
| VIX > 20 period | ≥ 1 month | Macro stress |
| Month with SPY return < −3% | ≥ 1 occurrence | Drawdown behavior |
| TSMOM filter fires (BIL month, for H026) | ≥ 1 month | Defensive behavior |

### Gate 3: Execution Quality Check

Before scaling to live, verify the paper fills match what live fills would be:

1. **Slippage estimate**: For large-cap ETFs and S&P 500 stocks, bid-ask spread is typically 0.01–0.03%. Market-impact on $10k–$50k positions is negligible.
2. **Fill time**: Alpaca paper fills are instantaneous at 9:45 AM CT entry; live orders may take 5–30 seconds. For monthly-rebalance strategies this is immaterial.
3. **Partial fill risk**: For stocks with >$5M ADV (all 30 universe stocks, all ETFs), fills at $10k–$100k are near-certain. No partial fill risk.

---

## Graduation Decision Table

| Strategy | Paper Period Needed | Key Check | Live Scale-Up Path |
|----------|-------------------|-----------|-------------------|
| H026 ETF rotation | 3 months | Sharpe > 1.0 paper | Start at 10–20% of capital; scale monthly |
| H181 reversal | 3 months | Paper WR% vs backtest OOS within 1 SE | Start at 10% of satellite allocation |
| PEAD H174 | 20 qualifying events | SPRT LLR > log(A)=2.89 | Start at $2k–$5k per event |
| IBS (XLK/SMH/IGV) | 60 signals | Paper Sharpe > 1.5 | Already in production parameters — start at 50% of target |

---

## Performance Attribution: Paper vs Live Divergence

Once live trading begins, maintain a running performance attribution table updated monthly:

```
Live Return   = Paper Return
              − Slippage drag     (est. 0.05-0.10%/trade × n_trades)
              − Market impact     (est. 0.01-0.05%/trade for our sizes)
              − Commission        ($0 at Alpaca)
              ± Execution timing  (entry time difference from paper 9:45 AM)
              ± Position sizing   (fractional share rounding)
              = Residual (unexplained)
```

**Residual > +0.5%/month**: Paper is understating live alpha — good sign, often from timing luck.
**Residual < −1.0%/month**: Hidden cost or signal degradation. Investigate before scaling.
**Residual between −1.0% and +0.5%**: Normal range, proceed with scaling plan.

### Slippage estimation for our strategies

| Strategy | Trade frequency | Est. slippage/trade | Annual drag |
|----------|----------------|--------------------|-----------:|
| H026 | 1 trade/month | 0.03% (ETF spread) | ~0.36% |
| H181 | 6 trades/month | 0.05% (large-cap spread) | ~3.6% |
| PEAD | 1–2 events/month | 0.10% (gap-up volatility) | ~1.2–2.4% |
| IBS | 3–6 trades/week | 0.03% (ETF spread) | ~4.7–9.4% |

IBS is the most drag-sensitive. At Alpaca's zero-commission structure the spreads are the only cost.

---

## Alpaca Paper → Live Migration Steps

1. **Paper account validation**: All strategies running in `/workspace/agent/backtesting/paper_trading/`
2. **Enable live account**: Flip `base_url = "https://api.alpaca.markets"` (remove `-paper` prefix)
3. **Start small**: 10–25% of target allocation for first 1–3 months
4. **Monitor fill quality**: Compare each live fill vs paper fill from same morning; log in trade log
5. **Scale up**: Increase 25% of target per month if residual within normal range

**Alpaca paper vs live endpoint:**
```python
# Paper
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"

# Live (requires $ALPACA_API_KEY + $ALPACA_SECRET set to live account credentials)
ALPACA_BASE_URL = "https://api.alpaca.markets"
```

---

## Current Paper Trading Status (as of 2026-05)

| Strategy | Paper Start | Months | Status | Notes |
|----------|------------|--------|--------|-------|
| H026 rotation | 2026-04-28 | ~1 | Pre-graduation | Need 2+ more months |
| H181 reversal | 2026-05-10 | <1 | Pre-graduation | Need 2+ more months |
| PEAD H174 | 2026-05-06 | <1 | Pre-graduation | Need 15+ more qualifying events |

No strategies have cleared all three gates yet. Earliest realistic live graduation: **Q3 2026** for H026 (longest-running). PEAD depends on earnings event flow — at ~2 qualifying events/month, 20-event SPRT gate clears around **October 2026**.

---

## References

- Wald, A. (1945). "Sequential Tests of Statistical Hypotheses." *Annals of Mathematical Statistics*.
- Alpaca Markets. "Paper Trading vs. Live Trading: A Data-Backed Guide." alpaca.markets/learn.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Chapter 11: Strategy Evaluation.
- wiki: [Design Principles](../backtesting/design-principles.md) — IS/OOS framework
- wiki: [Walk-Forward & CPCV](../backtesting/walk-forward-cpcv.md) — multiple testing framework
