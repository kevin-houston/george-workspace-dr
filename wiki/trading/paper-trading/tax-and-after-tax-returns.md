---
title: Tax & After-Tax Return Modeling
added: 2026-06-05
category: paper-trading
---

# Tax & After-Tax Return Modeling

Kevin's explicit requirement: backtests must report **after-tax returns**. This page covers the mechanics — federal/state rates, wash sale rule, tax lot selection, and a practical after-tax Sharpe formula applicable to the production portfolio.

---

## Why It Matters

A strategy showing 15% pre-tax CAGR with monthly rebalancing and all short-term gains might deliver only 10–11% after federal + state taxes. For a strategy running in a taxable account, the Sharpe ratio comparison is misleading unless computed on after-tax cash flows.

---

## Tax Rate Reference (2026)

### Federal Capital Gains

| Holding Period | Rate (Single, income $200k–$250k) |
|----------------|-----------------------------------|
| Short-term (< 1 year) | Ordinary income rate → **22–32%** |
| Long-term (≥ 1 year) | **15%** for most retail investors |

For a full-time trader with $200k+ in trading income, effective short-term rate is typically **28–32%** federal.

### State Capital Gains (Illinois)

Illinois taxes all capital gains as ordinary income: flat **4.95%** on all gains regardless of holding period.

**Combined marginal rate (short-term, IL):** ~32% federal + 4.95% state + 3.8% NIIT (Net Investment Income Tax if AGI > $200k) = **≈ 40.75%** effective on short-term gains.

**Combined marginal rate (long-term, IL):** 15% + 4.95% + 3.8% = **≈ 23.75%** long-term.

> Note: NIIT (3.8% on net investment income above $200k AGI) applies to passive investment income including trading gains from non-active-trader accounts. Most algorithmic traders do NOT qualify as "trader in securities" under IRS Section 475 and pay NIIT.

---

## Short-Term vs Long-Term in Practice

Nearly all strategies in our pipeline generate **short-term gains**:
- H026 (sector ETF top-1): monthly rebalance → 100% STCG
- H041a (19-asset top-1): monthly → 100% STCG
- H045 (bonds top-2): monthly → 100% STCG
- IBS (daily mean reversion): daily → 100% STCG
- H174/PEAD (20-day hold): < 1 month → 100% STCG
- H181 (industry reversal): monthly → 100% STCG

Only strategies with multi-year hold periods (LTCG planning) are irrelevant to the current stack. **Plan all return modeling assuming short-term rates.**

---

## Wash Sale Rule

**Rule:** If you sell a security at a loss and buy the **substantially identical** security within 30 days before or after the sale, the loss is **disallowed** — it defers to your cost basis in the replacement position.

### Critical Implications for Algo Trading

1. **ETF rotation strategies (H026/H041a/H045):** Rotating from XLK → XLE in a loss period is fine. But if the model rotates back to XLK within 30 days after selling it at a loss, the loss is disallowed.

2. **Same-security entries:** PEAD/H174 strategy: if you sell a position at a loss and a new 8-K fires for the same stock within 30 days → buying it triggers wash sale. The paper trading system should flag this.

3. **"Substantially identical" = same ticker.** Different-sector ETFs (XLK vs XLV) are not substantially identical. SPY and VOO/IVV **might** be (IRS hasn't ruled definitively). QQQ and XLK are different enough.

4. **Tax-loss harvesting automation:** In a live account, wash sale tracking requires per-lot accounting. The broker (Alpaca → Apex Clearing) tracks this automatically per lot, but the algo system should avoid re-entering a position at a loss within 30 days.

---

## Tax Lot Selection Strategy

When selling a partial position, the choice of which lots to sell affects tax liability:

| Method | Description | When to use |
|--------|-------------|-------------|
| **HIFO** (Highest In, First Out) | Sells highest-cost lots first → minimizes gain | Default for tax-efficiency when profitable |
| **FIFO** (First In, First Out) | Sells oldest lots first → may convert STCG→LTCG | Use when oldest lots are at 1-year mark |
| **LIFO** | Sells newest lots first → preserves oldest lots | Rarely optimal |
| **Specific ID** | Choose exact lots | Maximum flexibility; requires tracking |

**Recommendation:** Use **HIFO** for all rotation strategies to minimize realized gains. Alpaca supports specific lot identification via the `legs[].cost_basis` field in orders. The IRS requires you to identify lots *at time of sale*, not retroactively.

---

## After-Tax Return Calculation

### Simple After-Tax Return (Monthly Strategy)

```python
def after_tax_monthly_return(monthly_ret: float,
                              tax_rate_stcg: float = 0.4075,
                              tax_rate_ltcg: float = 0.2375,
                              holding_period_years: float = 1/12) -> float:
    """
    Approximate after-tax monthly return.
    Assumes gains are realized each month (worst case for short-term).
    
    Parameters
    ----------
    monthly_ret : float — pre-tax return (e.g. 0.015 = 1.5%)
    tax_rate_stcg : float — combined STCG rate (federal + state + NIIT)
    tax_rate_ltcg : float — combined LTCG rate
    holding_period_years : float — average hold duration
    """
    if monthly_ret <= 0:
        return monthly_ret  # losses carry forward; no immediate tax benefit in simple model
    
    # All monthly rebalancing strategies → STCG
    rate = tax_rate_stcg if holding_period_years < 1 else tax_rate_ltcg
    return monthly_ret * (1 - rate)
```

### After-Tax Sharpe Ratio

```python
import numpy as np
import pandas as pd

def after_tax_sharpe(monthly_returns: pd.Series,
                     tax_rate: float = 0.40,
                     rf_monthly: float = 0.0043) -> dict:
    """
    Compute after-tax Sharpe ratio for a monthly return series.
    
    Key simplifications:
      - Gains taxed monthly (conservative — realistically deferred to year-end)
      - Losses generate a tax shield (partial offset)
      - Risk-free rate not tax-adjusted (T-bills also taxed as ordinary income)
    """
    # After-tax returns: gains taxed, losses get partial credit
    def apply_tax(r):
        if r > 0:
            return r * (1 - tax_rate)
        else:
            # Loss deduction reduces future tax liability
            return r * (1 - tax_rate * 0.5)  # conservative: assume 50% loss utilization
    
    at_returns = monthly_returns.apply(apply_tax)
    
    # Annualized after-tax metrics
    ann_ret = (1 + at_returns.mean()) ** 12 - 1
    ann_vol = at_returns.std() * np.sqrt(12)
    rf_annual = (1 + rf_monthly) ** 12 - 1
    sharpe_at = (ann_ret - rf_annual) / ann_vol if ann_vol > 0 else 0
    
    # Comparison
    ann_ret_pre = (1 + monthly_returns.mean()) ** 12 - 1
    sharpe_pre = (ann_ret_pre - rf_annual) / (monthly_returns.std() * np.sqrt(12))
    
    return {
        "pre_tax_cagr":     round(ann_ret_pre, 4),
        "after_tax_cagr":   round(ann_ret, 4),
        "pre_tax_sharpe":   round(sharpe_pre, 4),
        "after_tax_sharpe": round(sharpe_at, 4),
        "tax_drag_cagr_pp": round((ann_ret_pre - ann_ret) * 100, 2),
    }
```

### Expected Tax Drag (Production Portfolio Estimate)

Approximate annual tax impact on current production portfolio (monthly rebalancing, IL taxable account):

| Metric | Pre-Tax | After-Tax | Drag |
|--------|---------|-----------|------|
| CAGR (~23.5%) | 23.5% | ~14.1% | −9.4pp |
| Sharpe (4.16) | 4.16 | ~2.7 | −1.46 |

**Key insight:** The after-tax CAGR is roughly `pre_tax_CAGR × (1 - 0.40)` for a pure STCG strategy. The Sharpe ratio drops less dramatically because volatility is also reduced (gains and losses are both scaled by the tax factor).

> Caveat: actual tax drag depends on loss carry-forwards, tax-loss harvesting, and the year-end realization pattern. The 40% effective rate is a conservative upper bound; actual may be 30–35% with good tax-lot management.

---

## Tax-Efficient Structure Options

### Option 1: Trade in a Tax-Deferred Account (IRA/401k)

- No capital gains tax on rebalancing within the account
- All withdrawals taxed as ordinary income (Traditional IRA) or tax-free (Roth)
- **Best case:** Roth IRA — zero tax on gains if held to retirement
- **Limitation:** Contribution limits ($7,000/year in 2026); no short-selling

### Option 2: Trader in Securities Status (Section 475 MTM Election)

- IRS allows active traders to elect **mark-to-market** accounting (Section 475(f))
- All positions valued at year-end at market price; gains/losses treated as ordinary income
- **Advantage:** Losses are fully deductible against ordinary income (no $3k cap on capital loss)
- **Disadvantage:** No LTCG treatment — all income ordinary
- **Qualification:** ≥4 trades/day, ≥ 4 days/week, ≥ $3k average daily trading volume
- **Deadline:** Must elect by April 15 of the tax year

For a low-turnover monthly rotation strategy, MTM election is likely **not beneficial** — you lose LTCG rates without enough loss deductions to compensate.

### Option 3: Qualified Opportunity Zone Fund (QOZ)

- Defer capital gains by investing in a QOZ fund within 180 days
- 10-year hold → any gains on the QOZ investment itself are tax-free
- Viable for large lump-sum gains; not relevant to ongoing monthly trading income

### Option 4: Tax-Loss Harvesting

- Systematically harvest losing positions in December to offset gains
- Replace with correlated-but-not-identical ETF (e.g., sell XLK → buy QQQ if not substantially identical, hold 31 days, rotate back)
- Target: offset 15–30% of annual realized gains with harvested losses
- **Risk:** wash sale if replacement is substantially identical

---

## Practical Implications for Backtests

When reporting backtest results to Kevin, include an after-tax column:

```
H026 OOS (2018–2025):
  Pre-tax Sharpe:   1.50
  After-tax Sharpe: ~0.97  (at 40% STCG effective rate)
  Pre-tax CAGR:     ~18%
  After-tax CAGR:   ~10.8%
```

This is the correct comparison for decision-making. A strategy with 1.5 pre-tax Sharpe and monthly rebalancing may be worse after-tax than a strategy with 1.2 Sharpe and annual rebalancing (LTCG eligible).

### Modeling Taxes in run_h***.py

Add an `after_tax_stats()` function to each backtest script:

```python
TAX_RATE_STCG = 0.40  # conservative IL + federal + NIIT
TAX_RATE_LTCG = 0.24  # IL + federal LTCG

def after_tax_stats(monthly_returns, holding_months=1):
    rate = TAX_RATE_STCG if holding_months < 12 else TAX_RATE_LTCG
    at_returns = monthly_returns.apply(lambda r: r * (1 - rate) if r > 0 else r)
    ann_ret = (1 + at_returns.mean()) ** 12 - 1
    sharpe  = ann_ret / (at_returns.std() * np.sqrt(12))
    cumret  = (1 + at_returns).prod() - 1
    return {"after_tax_cagr": ann_ret, "after_tax_sharpe": sharpe, "after_tax_cumret": cumret}
```

---

## IRS Reporting

For live trading (Phase 4):
- **Form 8949**: Report every individual sale (realized gain/loss, holding period, cost basis)
- **Schedule D**: Summary of capital gains/losses from Form 8949
- **Form 4797**: Only if Section 475 MTM election applies
- Brokers (Alpaca → Apex Clearing) provide **1099-B** with per-lot realized gain/loss; cost basis reported to IRS

Alpaca's 1099-B uses **FIFO** by default. To use HIFO, you must specify lots at time of sale — not retroactively. Track this in the trading system from Day 1 of live operation.

---

## References

- IRS Publication 550: Investment Income and Expenses
- IRS Rev. Rul. 2023-2: Wash sale rule clarification for ETFs
- Arnott et al. (2018) "Tax-Managed Factor Strategies" — Financial Analysts Journal (after-tax factor alpha typically 40–60% of pre-tax for monthly-rebalanced strategies)
- Jeffrey & Arnott (1993) "Is Your Alpha Big Enough to Cover Its Taxes?" — Journal of Portfolio Management (seminal paper on tax drag)
