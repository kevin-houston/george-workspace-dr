---
added: 2026-05-24
updated: 2026-07-13
category: strategy
status: active — H221 (Piotroski F-Score) queued; H337 NOT CONFIRMED (large-cap universe); H337b proposed (200-stock)
source: Asness/Frazzini/Pedersen (2019); Novy-Marx (2013); Piotroski (2000)
---

# Quality Factor (QMJ — Quality Minus Junk)

The quality anomaly: **high-quality companies deliver higher risk-adjusted returns than low-quality (junk) companies**, controlling for price. Contradicts efficient markets; attributed to investor neglect of slow-moving fundamental signals, institutional constraints, and lottery demand for speculative/junk stocks.

**Key papers:**
- Asness, Frazzini & Pedersen (2019) "Quality Minus Junk" — *Review of Accounting Studies*. QMJ factor, global evidence
- Novy-Marx (2013) "The Other Side of Value" — *JFE*. Gross profitability (GP/Assets) alone explains much of the value-quality premium
- Piotroski (2000) "Value Investing: The Use of Historical Financial Statement Information" — *JAR*. F-Score predicts returns among value stocks

**AQR public datasets:**
- Daily QMJ returns: https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Daily
- Monthly QMJ: https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Monthly
- Free download, US + international

---

## Theoretical Foundation

The quality factor exploits a structural mispricing: investors systematically underprice **boring, profitable, stable companies** while overpaying for **speculative, high-growth, cash-burning companies**. Multiple independent mechanisms:

1. **Leverage constraints** (Black 1972; Frazzini & Pedersen 2014): Investors who cannot lever up buy speculative high-beta stocks to boost returns → overprices junk
2. **Lottery demand** (Kumar 2009): Retail investors prefer low-price, high-volatility, positively-skewed stocks → overprices junk
3. **Institutional benchmarking**: Fund managers measured vs market-cap-weighted index cannot short junk without career risk → market cannot fully correct mispricing
4. **Analyst coverage bias**: Analysts write bullish reports on exciting growth stories → junk is over-covered/overhyped

**Key insight**: QMJ and BAB (Betting Against Beta, our H192-D) share the same theoretical foundation. Both are long "boring safe assets" and short "exciting speculative assets." The correlation between QMJ and BAB is ~0.5–0.6 — related but distinct.

---

## Three Quality Dimensions

### 1. Profitability

How much cash does the business generate per unit of assets/equity?

| Metric | Formula | Source |
|--------|---------|--------|
| Gross profitability (GP/A) | (Revenue − COGS) / Total Assets | Income + Balance sheet |
| Return on Equity (ROE) | Net Income / Book Equity | Same |
| Return on Assets (ROA) | Net Income / Total Assets | Same |
| Cash flow / Assets | Operating Cash Flow / Total Assets | Cash flow statement |
| Gross margin | (Revenue − COGS) / Revenue | Income statement |
| EBITDA margin | EBITDA / Revenue | Income statement |

**Novy-Marx finding**: GP/Assets alone has nearly the same explanatory power as the 5-factor Fama-French model. It's the single most powerful quality metric.

### 2. Growth / Safety

Is quality improving or deteriorating? Are the finances stable?

| Metric | Formula |
|--------|---------|
| Earnings stability | σ(ROE) or σ(Earnings) over trailing 5yr — lower is better |
| Leverage | Total Debt / Total Assets — lower is better |
| Payout ratio | Dividends / Earnings — sustainable but not excessive |
| Accruals | (Net Income − Operating Cash Flow) / Assets — lower accruals = higher quality earnings |
| Altman Z-score | Classic financial distress predictor (Z > 2.99 = safe zone) |

### 3. Piotroski F-Score (9-point checklist)

**Piotroski (2000)** scores each company 0–9 on binary (pass/fail) criteria:

**Profitability signals (4 points):**
- F1: ROA > 0 (positive this year)
- F2: Operating cash flow > 0
- F3: Change in ROA > 0 (improving)
- F4: Accruals = (Operating CF / Assets) − ROA > 0 (cash > accruals)

**Leverage / liquidity signals (3 points):**
- F5: Change in leverage < 0 (leverage decreasing)
- F6: Change in current ratio > 0 (liquidity improving)
- F7: No new shares issued this year (dilution test)

**Operating efficiency signals (2 points):**
- F8: Change in gross margin > 0
- F9: Change in asset turnover > 0

**Score interpretation:**
- 0–2: Junk (high distress risk, short candidates)
- 3–6: Average
- 7–9: Quality (long candidates)

Piotroski's original finding: **high F-Score value stocks return 7.5% more annually** than low F-Score value stocks. Using F-Score alone (without value) also generates alpha.

---

## Data Sources

### FMP API (`$FMP_API_KEY` available)

All required data is available via Financial Modeling Prep:

```python
import os, requests, pandas as pd

FMP_KEY = os.environ["FMP_API_KEY"]
BASE    = "https://financialmodelingprep.com/api/v3"

def get_income(ticker: str, limit: int = 5) -> list:
    """Annual income statements (last N years)."""
    r = requests.get(f"{BASE}/income-statement/{ticker}",
                     params={"apikey": FMP_KEY, "limit": limit})
    return r.json()

def get_balance(ticker: str, limit: int = 5) -> list:
    r = requests.get(f"{BASE}/balance-sheet-statement/{ticker}",
                     params={"apikey": FMP_KEY, "limit": limit})
    return r.json()

def get_cashflow(ticker: str, limit: int = 5) -> list:
    r = requests.get(f"{BASE}/cash-flow-statement/{ticker}",
                     params={"apikey": FMP_KEY, "limit": limit})
    return r.json()

def get_ratios_ttm(ticker: str) -> dict:
    """TTM financial ratios — grossProfitMarginTTM, returnOnEquityTTM, etc."""
    r = requests.get(f"{BASE}/ratios-ttm/{ticker}",
                     params={"apikey": FMP_KEY})
    data = r.json()
    return data[0] if data else {}
```

**Key FMP fields for quality signals:**

| FMP field | Quality metric |
|-----------|---------------|
| `grossProfit` / `totalAssets` | GP/Assets (Novy-Marx) |
| `netIncome` / `totalEquity` | ROE |
| `netIncome` / `totalAssets` | ROA |
| `operatingCashFlow` / `totalAssets` | CF/Assets |
| `totalDebt` / `totalAssets` | Leverage |
| `grossProfitRatio` | Gross margin |
| `currentRatio` | Liquidity |
| `commonStockIssued` | Dilution check (F7) |

**FMP free tier limits**: 250 API calls/day. For our 30-stock universe, that's 30 calls per statement type — easily within limits.

**FMP bulk endpoint** (more efficient for cross-sectional work):
```python
# Get all TTM ratios for S&P 500 in one call (paid tier)
# Free tier: per-ticker calls
r = requests.get(f"{BASE}/financial-ratios-ttm/AAPL", 
                 params={"apikey": FMP_KEY})
```

### AQR Dataset (direct download — no API needed)

AQR publishes the official QMJ factor returns (long quality, short junk):
```python
import pandas as pd

# Monthly US QMJ factor (R^QMJ column)
aqr_url = "https://www.aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors-Monthly"
# Download from AQR website → Excel file → parse "USA" sheet
# Columns: MKT, SMB, HML, QMJ, RF (excess returns, decimal)

# Can use as a factor to check correlation with our strategies
```

### Kenneth French Data Library

Gross profitability factor is also available from Ken French:
```python
import pandas_datareader.data as web

# OP (operating profitability) = Ken French's quality proxy
ff5 = web.DataReader("F-F_Research_Data_5_Factors_2x3", "famafrench")
# RMW = "Robust Minus Weak" profitability factor (most similar to QMJ)
```

---

## Python: Piotroski F-Score

```python
import pandas as pd
import numpy as np

def piotroski_fscore(income: dict, balance: dict, cashflow: dict,
                     income_prev: dict, balance_prev: dict) -> dict:
    """
    Compute F-Score from two consecutive years of financials.
    income/balance/cashflow: current year dict from FMP
    income_prev/balance_prev: prior year dict from FMP
    Returns dict with each signal and total score.
    """
    total_assets = balance.get("totalAssets", 1) or 1
    total_assets_p = balance_prev.get("totalAssets", 1) or 1
    book_equity = balance.get("totalEquity", 1) or 1

    roa   = income.get("netIncome", 0) / total_assets
    roa_p = income_prev.get("netIncome", 0) / total_assets_p
    cf    = cashflow.get("operatingCashFlow", 0) / total_assets
    accruals = cf - roa

    leverage   = (balance.get("longTermDebt", 0) or 0) / total_assets
    leverage_p = (balance_prev.get("longTermDebt", 0) or 0) / total_assets_p
    cur_ratio   = balance.get("currentRatio", 0) or 0
    cur_ratio_p = balance_prev.get("currentRatio", 0) or 0

    shares_issued = (balance.get("commonStockIssued", 0) or 0)

    gross_margin   = (income.get("grossProfit", 0) or 0) / max(income.get("revenue", 1), 1)
    gross_margin_p = (income_prev.get("grossProfit", 0) or 0) / max(income_prev.get("revenue", 1), 1)
    asset_turn   = (income.get("revenue", 0) or 0) / total_assets
    asset_turn_p = (income_prev.get("revenue", 0) or 0) / total_assets_p

    signals = {
        "F1_roa_positive":     int(roa > 0),
        "F2_cf_positive":      int(cashflow.get("operatingCashFlow", 0) > 0),
        "F3_roa_improving":    int(roa > roa_p),
        "F4_accruals_low":     int(accruals > 0),
        "F5_leverage_down":    int(leverage < leverage_p),
        "F6_liquidity_up":     int(cur_ratio > cur_ratio_p),
        "F7_no_dilution":      int(shares_issued <= 0),
        "F8_margin_up":        int(gross_margin > gross_margin_p),
        "F9_asset_turn_up":    int(asset_turn > asset_turn_p),
    }
    signals["total"] = sum(signals.values())
    return signals
```

---

## Cross-Sectional Quality Strategy Design

### H221: Piotroski F-Score Cross-Sectional (proposed)

**Signal**: Annual Piotroski F-Score computed from FMP annual statements
**Universe**: Same 30 large-cap stocks as H198/H217 (annual rebalance)
**Portfolio**: Long top-6 by F-Score (score 7+), equal-weight
**IS**: 2010–2020, OOS: 2021–2026
**Confirm**: OOS Sharpe > 0.7

**Critical data timing note**: Annual reports file 60–90 days after fiscal year end. F-Score computed from fiscal year 2023 data is available ~March 2024. Portfolio rebalanced in April using prior-year financials → clean no-lookahead signal.

**Expected correlation with H192-D BAB**: ~0.4–0.6. BAB uses price (beta); F-Score uses fundamentals. Independent sources of quality alpha.

### H222: Gross Profitability (Novy-Marx) Cross-Sectional (proposed)

**Signal**: GP/Assets (gross profit / total assets) from FMP
**Portfolio**: Long top-6 by GP/Assets, monthly rebalance using most recent TTM data
**Expected Sharpe**: 0.6–0.9 (academic IC ~0.03–0.05)
**Note**: GP/Assets is the most robust single quality metric; Novy-Marx (2013) documented 0.53% monthly premium in the U.S.

---

## Relationship to Confirmed Strategies

| Strategy | Signal type | Quality overlap | Our result |
|----------|-------------|-----------------|-----------|
| H192-D BAB | Market beta (price-based) | Moderate — both favor "boring" companies | OOS Sharpe **1.367** |
| H181 Short-term reversal | 1-week price return | Low | OOS Sharpe **1.138** |
| H217 Alpha101 | Intraday close position | Low | OOS Sharpe **1.559** |
| H198 Momentum | 6m price return | Negative — momentum long high-growth | OOS Sharpe **1.174** |
| QMJ/F-Score (proposed) | Fundamental profitability | — | *untested* |

**Key question for H221**: Does F-Score add independent alpha beyond H192-D BAB? If correlation < 0.5 (fundamentals vs price-based beta), a blend could improve the portfolio.

**Expected blend value**: Fundamental quality (annual rebalance) + BAB (monthly rebalance) should be complementary: BAB captures the pricing anomaly; F-Score captures the fundamental quality anomaly. Together: ~0.6–0.8 correlation, potentially pushing combined Sharpe from 1.367 to ~1.4–1.5.

---

## Academic Performance Summary

| Strategy | Period | OOS Sharpe | Notes |
|----------|--------|------------|-------|
| QMJ (AQR) | 1957–2012, global | ~0.8–1.1 | Long-short, gross |
| Piotroski F-Score (long-high) | 1976–1996 | ~0.6–0.9 | Value stocks only |
| Gross Profitability (Novy-Marx) | 1963–2010 | ~0.6–0.9 | All stocks |
| F-Score on S&P 500 | 2010–2024 | ~0.5–0.8 | Large-cap only; weaker |

**Large-cap caveat**: Quality anomaly is weakest in large-caps (better-covered, less mispricing). Our 30-stock mega-cap universe may show weaker quality effect than academic studies using 1000+ stocks. This is the same degradation seen in H213 (IVOL anomaly) and H219 (low-vol ETF).

---

## Next Steps

1. **Run H221** (Piotroski F-Score on 30-stock universe): ~2hr coding, uses FMP API
2. **Run H222** (GP/Assets Novy-Marx): simpler than F-Score, same data pipeline
3. **Correlation check**: H221 vs H192-D BAB — key for portfolio addition decision
4. **If confirmed**: consider QMJ-BAB blend as a single "quality" allocation replacing H192-D

**See also**: [Factor Models & Cross-Sectional Alpha](factor-models.md) — Fama-French RMW factor; [BAB Strategy](../backtesting/hypothesis-log.md#H192-D); [Momentum Strategies](momentum-strategies.md) — interaction with momentum on large-cap

---

## Confirmed Results on Our 30-Stock Universe

### H337 NOT CONFIRMED — Quality Tiebreaker on H198 (June 2026)

**Hypothesis**: Dual-rank by momentum + quality (GP/A or ROE) improves over pure momentum on the H198 30-stock large-cap universe.

**IS**: 2013–2020, **OOS**: 2021–2026. Gate: OOS Sharpe > 1.174 (H198 baseline).

| Variant | Signal | OOS Sharpe | vs baseline |
|---------|--------|-----------|------------|
| A | Pure momentum (reference) | 1.055 | −0.12 |
| B | 0.5 × MOM + 0.5 × GP/A | 0.802 | −0.37 |
| C | 0.7 × MOM + 0.3 × GP/A | 0.832 | −0.34 |
| D | 0.5 × MOM + 0.5 × ROE | 0.792 | −0.38 |
| E | MOM + GP/A median filter | 0.812 | −0.36 |

**All variants failed gate. Quality tiebreaker made every variant worse than pure momentum.**

**Root causes (three compounding problems):**

1. **Low data coverage**: yfinance quarterly fundamentals only reach back 4–5 years, covering only 6.7% of the IS period. In data-sparse periods the strategy falls back to pure momentum; in data-rich periods (mostly OOS) the quality tiebreaker misfires.

2. **Insufficient cross-sectional variation**: All 30 S&P 500 mega-caps are high-quality businesses. GP/A variation across AAPL, MSFT, NVDA, and SBUX is narrow — insufficient for meaningful ranking. The academic GP/A premium requires a broad universe (200–1000+ stocks) where industry laggards genuinely differ from leaders.

3. **Quality works against momentum on this universe**: Momentum selects recent outperformers (e.g., NVDA in AI-driven years). Quality signals may route away from these winners — fabless semiconductor companies score differently on GP/A than consumer staples — reducing rather than refining the signal.

**Script**: `backtesting/daily/run_h337.py`. **Results**: `backtesting/results/h337_results.json`.

---

### H337b — Proposed (200-Stock Universe)

The quality premium requires broad cross-sectional variation. Next step: re-run on S&P 500 (~500 stocks) or Russell 1000 where quality spread is real:

- **Small/mid-cap** companies show 5–10× variation in GP/A vs mega-cap peers
- **Cross-sector**: Financial services and industrials at the low end vs pure-software/pharma at the high end
- **Data source**: FMP API (fix SSL cert issue with OneCLI CA bundle) rather than yfinance for reliable fundamentals coverage

**Expected outcome**: Quality premium likely reappears with >100 stocks and sector-neutral ranking. Academic evidence (Novy-Marx 2013) documents 0.53%/month premium in full S&P 500 universe — that's the environment this hypothesis needs.

---

## Factor Performance Context: 2024–2026

Quality factor performance has been regime-dependent in recent years:

| Period | Quality (QMJ) | Momentum | Notes |
|--------|--------------|----------|-------|
| 2022 | Outperformed | Crashed (momentum crash) | Rate hike environment favored defensive quality |
| 2023 | Moderate | Recovered | Growth rebound hurt quality premium |
| 2024 | Underperformed | Outperformed strongly | Mega-cap AI growth stocks (junk by quality metrics but huge winners) |
| 2025 | "Awful year" (Oakmark 4Q25) | Dominated | High-beta speculative assets outperformed boring compounders |
| Q1 2026 | Partial recovery | Still leading | Quality factor rebounded ~4% after −17% drawdown since July 2025 |

**Mechanism (2024–2025 underperformance)**: Quality factor is long "boring compounders" (high ROE, low leverage, stable earnings). In the 2024–2025 AI bubble, the highest-returning stocks (NVDA, META, AMZN) were high-quality by some metrics but also high-vol, high-beta — the exact names that momentum picks but quality traditionally avoids. Both Momentum and Quality ETFs ended up loading similarly on the "Magnificent 7," reducing the quality factor's ability to differentiate.

**Key risk**: The quality anomaly is **weakest in large-caps** (better analyst coverage, less mispricing opportunity) and further suppressed in concentrated tech-heavy environments. Both conditions apply to our 30-stock universe, explaining H337's failure.

**AQR QMJ historical context** (1964–2023): QMJ annual premium 4.7%, σ 9.9%, Sharpe **0.47**. Correlation to market: −0.59. Correlation to momentum: **0.29** (low — genuinely independent alpha source at scale). Correlation to BAB: ~0.5–0.6.

---

## Next Steps (Updated July 2026)

1. **H337b — 200-stock universe** (highest priority): Re-run quality-momentum composite on S&P 500 or Russell 1000. Fix FMP API SSL via `SSL_CERT_FILE=/tmp/onecli-combined-ca.pem`. Confirm cross-sectional GP/A spread first before running full backtest.
2. **H221 — Piotroski F-Score standalone**: Run on current 30-stock universe as separate strategy (not tiebreaker). Even if cross-sectional variation is low, annual rebalance + F-Score could still identify deteriorating names to exclude.
3. **H222 — GP/Assets Novy-Marx**: Simpler than F-Score, same data pipeline. Run on 200-stock universe if H337b data prep works.
4. **Correlation check**: For any confirmed quality variant vs H192-D BAB — key for portfolio addition decision. Target: Corr < 0.50 for independent quality sleeve.
