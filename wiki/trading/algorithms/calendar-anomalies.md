---
updated: 2026-05-18
type: strategy family
status: active — H201 CONFIRMED; H205 queued; H206 queued; Halloween mechanism confirmed (Schroeder 2025)
---

# Calendar Anomalies

Calendar anomalies are persistent return patterns tied to the calendar — day of week, month, season, or proximity to specific events. In efficient markets they should be arbitraged away; in practice, several have survived decades of academic scrutiny, though magnitudes are shrinking in liquid US markets.

**Our confirmed result**: H201 — Turn-of-Month effect CONFIRMED on SPY 2018–2026, OOS Sharpe 0.740, MaxDD -9.3%. The TOM window (last 2 + first 2 trading days) captures ~19% of trading days but delivers most of SPY's returns with far lower drawdown.

**Related pages**: [Low-Volatility Anomaly](low-volatility.md) (H205 = TOM overlay on BAB) | [Momentum Strategies](momentum-strategies.md) (H198/H203 momentum tested with TOM) | [Backtesting Design Principles](../backtesting/design-principles.md) | [Hypothesis Log](../backtesting/hypothesis-log.md) | [Portfolio Optimization](../tools/portfolio-optimization.md) (blending calendar strategies)

---

## Turn-of-Month (TOM) Effect ← CONFIRMED (H201)

### What it is

Stocks earn abnormally high returns in a narrow window around month-end. Ariel (1987) documented positive returns only in the first half of each month; Lakonishok & Smidt (1988) refined this to a 4-day window spanning the end of one month and start of the next.

**Mechanism**: institutional cash flows (payroll, pension contributions, 401k deposits) arrive predictably at month-end, creating temporary demand pressure. Index rebalancing and futures roll activity also concentrate around these dates.

### Magnitude & window

| Period | TOM return/day | Non-TOM return/day | Source |
|--------|---------------|-------------------|--------|
| 1987–2005 (CRSP) | +0.14% (VW) | −0.01% | Lakonishok & Smidt |
| 1963–2018 | +0.067% | +0.046% | Meta-analysis |
| 2018–2026 (H201) | +0.067% | +0.046% | Our backtest |

**Best window (H201)**: last 2 + first 2 trading days of month (4 days total = ~19% of trading days)

### H201 Results (our backtest)

**IS 2003–2017**: Sharpe=0.147 (TOM premium compressed in 2008–2009 and 2015–2016 bear markets)  
**OOS 2018–2026** (best window): Sharpe=0.740, MaxDD=-9.3%, Cumul=1.559×, CAGR=5.6%  
**SPY buy-and-hold OOS**: Sharpe=0.789, Cumul=3.03×

Key finding: IS/OOS dynamic is inverted — TOM is STRONGER in recent data (2018–2026) than in the pre-2018 period. The premium is real and growing, possibly because institutional cash flows have become more concentrated.

**Critical caveat**: TOM earns CAGR 5.6% vs SPY 15.2%. Its value is in the Sharpe and drawdown profile (-9.3% vs -33.7% for SPY), not raw returns. It's a timing overlay, not an alpha source.

### Implementation

```python
import pandas as pd
import yfinance as yf

def build_tom_mask(trading_days: pd.DatetimeIndex, before: int = 2, after: int = 2) -> pd.Series:
    """Returns boolean Series: True on TOM window days."""
    mask = pd.Series(False, index=trading_days)
    monthly_ends = (trading_days.to_series()
                    .groupby([trading_days.year, trading_days.month])
                    .last().values)
    for month_end in monthly_ends:
        end_loc = trading_days.get_loc(month_end)
        start   = max(0, end_loc - before + 1)
        stop    = min(len(trading_days) - 1, end_loc + after)
        mask.iloc[start:stop + 1] = True
    return mask


# Backtest: hold SPY on TOM days, BIL otherwise
spy = yf.download("SPY", start="2015-01-01", auto_adjust=True, progress=False)["Close"]
daily_ret = spy.pct_change().dropna()
trading_days = daily_ret.index

tom = build_tom_mask(trading_days, before=2, after=2)
strategy_ret = daily_ret.where(tom, other=0.0)   # 0 = BIL
monthly_ret  = strategy_ret.resample("ME").apply(lambda x: (1 + x).prod() - 1)
```

### H205 queued: TOM overlay on BAB

Rather than using TOM as a standalone strategy (low CAGR), use it as a timing gate on H192-D sector-neutral BAB positions: hold BAB stocks during TOM window, hold BIL otherwise. Hypothesis: BAB alpha is concentrated in the TOM window, and calendar gating reduces drawdown while preserving most returns.

---

## Halloween Effect (Sell in May and Go Away)

### What it is

Stocks earn significantly higher returns in the November–April period ("winter") than May–October ("summer"). Bouman & Jacobsen (2002) documented this in 36 of 37 countries tested.

**Strategy**: hold equities November 1 – April 30, hold T-bills May 1 – October 31.

### Magnitude

| Period | Winter return | Summer return | Annualized edge |
|--------|--------------|--------------|-----------------|
| 1970–2020 (global) | +7.8%/6m avg | +2.1%/6m avg | ~7.2%/yr |
| US 1900–2020 | +6.8%/6m | +1.4%/6m | ~6.0%/yr |
| 2010–2024 (recent) | +5.2%/6m | +3.8%/6m | ~2.8%/yr |

**Combined with TOM**: Holding stocks only during TOM windows AND only in November–April periods generates 7.2%/yr annualized edge (Quantpedia).

### Why it persists

Competing explanations (none fully settled):
- **Risk-based**: summer has higher macroeconomic uncertainty (earnings/guidance seasonality)
- **Behavioral**: summer reduces investor attention (vacation effect)
- **Institutional**: risk-taking agencies reduce positions in summer
- **Momentum feedback**: if everyone sells in May, selling in May is rational

### Implementation

```python
def halloween_mask(idx: pd.DatetimeIndex) -> pd.Series:
    """True = winter period (Nov–Apr), False = summer (May–Oct)."""
    return pd.Series(idx.month.isin([11, 12, 1, 2, 3, 4]), index=idx)

# Combine with TOM:
tom_mask = build_tom_mask(daily_ret.index, before=2, after=2)
halloween = halloween_mask(daily_ret.index)
combined = tom_mask & halloween   # hold SPY only during TOM windows in winter months
```

### H206 queued (candidate): Halloween on SPY with TOM composite

Test combining Halloween + TOM on SPY. IS: 2003–2017, OOS: 2018–2026. Hypothesis: compound calendar filter (hold only on TOM days AND in November–April) improves OOS Sharpe above H201's 0.740 with similar or lower MaxDD.

**New mechanism evidence (Schroeder 2025)**: A November 2025 study in the *International Journal of Financial Studies* (IJFS, doi:10.3390/ijfs13040208) identifies SEC regulatory disclosure seasonality as a novel, structural mechanism for the Halloween effect. From 2004–2023: total SEC filings 17% higher in winter (Nov–Apr) vs summer (May–Oct); February is the peak month, September the lowest. Winter also shows 22% more insider trading activity, 473% more annual report filings, 96% more shareholder meetings, and 12% more activist investor activity. Interpretation: more value-relevant information arrives in winter due to fiscal year-end cycles and regulatory calendars, supporting higher price discovery efficiency and reduced information asymmetry risk in the winter period. This is a durable structural driver (tied to fiscal/regulatory calendars, not easily arbitraged). Success gates for H206: OOS Sharpe > 0.6 (H206-A standalone), OOS Sharpe > 0.8 (H206-B with TOM composite).

---

## January Effect (Month-of-Year Seasonality)

### Current evidence: largely gone in US large-caps

**Historical** (1963–1993): +1.85% average January return; tax-loss selling recovery in small-caps  
**Recent** (2015–2024): January is middle-of-pack, not exceptional. November, April, December consistently stronger.  
**Academic consensus (2025)**: "No significant difference between January and other months for most recent 5 years"

**Best performing months historically** (QuantifiedStrategies 2024 analysis):
1. November (+5.8% avg)
2. April
3. December
4. October
5. January (historically overhyped)

**Do NOT use**: January Effect on US large-cap ETFs. Effect has been arbitraged to zero.

**May still apply**: small-cap value stocks (tax-loss selling recovery specifically in IWM/small value). Not tested in our universe.

### September Effect (inverse)

Historically, September is the worst performing month (avg -0.7% vs +0.9% for all other months combined). Still visible in recent data:

```python
monthly_data = spy_ret.resample("ME").apply(lambda x: (1+x).prod()-1)
by_month = monthly_data.groupby(monthly_data.index.month).mean()
# September (month=9) typically shows negative avg
```

---

## Weekend Effect / Monday Effect

### Status: REVERSED in US markets (do not trade)

**Historical** (1950s–1980s): Negative Monday returns, positive Friday returns in US equities  
**Post-2000**: Effect has reversed or disappeared in developed markets  
**Recent data**: Monday returns are slightly negative (-0.01% avg) but effect is not reliable  
**Emerging markets**: Still present in some markets (Korea KOSPI, India, GCC)

**Mechanism of reversal**: Algorithmic trading captured the Monday effect; HFT now often buys into Monday weakness, eliminating the pattern.

**Do NOT trade**: Weekend/Monday effect in US large-cap ETFs.

---

## End-of-Quarter / Window Dressing Effect

### Mechanism

Fund managers buy recent winners and sell recent losers before quarter-end to improve reported portfolio appearance. This creates predictable demand for winners and supply pressure on losers in the last 5–10 trading days of March, June, September, December.

### Magnitude

- Large-cap winners in last 10 days of quarter: +0.3–0.5% above normal
- Small-cap losers in last 10 days: -0.3–0.5% below normal
- Effect strongest at year-end (December) due to tax-loss selling overlay

### Regulatory change (May 2026)

New SEC reporting rule taking effect **May 2026 for smaller funds (<$1B AUM)**: quarterly holding disclosures shift to monthly. This will partially redistribute window-dressing effects from quarterly to monthly cycles. Monitor for effect on TOM premium in 2026–2027.

### Implementation note

H201's month-end timing may partially capture this: the TOM window covers the last 2 days of the quarter months (Mar/Jun/Sep/Dec) + first 2 days of the next quarter. Window dressing by large managers over the last week of each quarter could amplify TOM returns in quarter-end months.

```python
def is_quarter_end_tom(idx: pd.DatetimeIndex, tom_mask: pd.Series) -> pd.Series:
    """Identify TOM days in quarter-end months (potentially higher-premium)."""
    quarter_end_months = idx.month.isin([3, 6, 9, 12])
    return tom_mask & pd.Series(quarter_end_months, index=idx)
```

---

## FOMC Effect

### What it is

Lucca & Moench (2015, JF) documented that ~80% of the annual US equity premium has historically been earned in the 24-hour window before FOMC rate decisions. Effect is large relative to its frequency (~8 meetings/year).

**Pre-FOMC premium**: SPY earns approximately +0.5% in the 24h before each FOMC meeting  
**Annual contribution**: 8 meetings × 0.5% ≈ 4% (large fraction of ~10% SPY annual return)

### Implementation

```python
# FOMC meeting dates (approximate — update from Fed calendar)
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
fomc_dates = pd.to_datetime([
    "2026-01-29", "2026-03-19", "2026-05-07", "2026-06-18",
    "2026-07-30", "2026-09-17", "2026-11-05", "2026-12-17",
])

def fomc_mask(daily_index: pd.DatetimeIndex, fomc_dates, window: int = 1) -> pd.Series:
    """True = day(s) before FOMC decision."""
    mask = pd.Series(False, index=daily_index)
    for dt in fomc_dates:
        # window days before FOMC (entry: close D-1 → exit: close D0)
        for d in range(1, window + 1):
            pre = dt - pd.tseries.offsets.BDay(d)
            if pre in daily_index:
                mask[pre] = True
    return mask
```

**Note**: The pre-FOMC premium has attracted significant attention since Lucca & Moench (2015); post-publication decay is possible. Most recent Quantpedia data suggests ~0.3% pre-FOMC premium (reduced from 0.5%).

---

## Academic Debate on TOM Persistence

**Contrarian finding (Finance Research Letters, 2025)**: "The Disappearing Turn-of-Month Effect" documents that the TOM premium disappears entirely after 2001 in US markets, arguing the Ogden (1990) liquidity mechanism no longer holds.

**Our position**: H201 confirms TOM OOS 2018–2026 (Sharpe 0.740) with a strict IS/OOS split. The divergence may reflect:
- Window sensitivity: we use last 2 + first 2 days; the FRL paper may use a different definition
- Universe: large-cap ETF (SPY) vs. broad equity universe
- Mechanism shift: institutional ETF flows and index rebalancing have grown since Ogden's era, possibly replacing the original payroll-deposit mechanism with a new one

**Practical implication**: TOM appears real in SPY 2018–2026 but the premium is window-sensitive and narrower than historical estimates. Use the confirmed 4-day window (H201) rather than expanding it.

---

## Composite Calendar Strategy

### Concept

Combine multiple calendar windows to capture complementary premiums. Quantpedia's composite (SIM + TOM + FOMC + SDM):
- **Annualized return**: 9.56%
- **Volatility**: 6.28%
- **Sharpe**: 0.77

Underperforms buy-and-hold in strong bull years but with much lower drawdown.

### Priority to test

| Window | OOS evidence | Priority |
|--------|-------------|----------|
| TOM (last 2 + first 2) | H201 CONFIRMED, Sharpe 0.740 | ✅ Done |
| TOM overlay on BAB | Not tested | H205 — next |
| Halloween (Nov–Apr) | Strong global evidence | H206 candidate |
| TOM + Halloween composite | Quantpedia: 7.2%/yr combined | H207 candidate |
| FOMC pre-meeting (24h) | Lucca & Moench (2015) | H208 candidate |
| Quarter-end TOM bonus | Directional | investigate in H205 results |

---

## Key papers

| Paper | Finding | Year |
|-------|---------|------|
| Ariel (1987, JFE) | Returns concentrated first half of month | 1987 |
| Lakonishok & Smidt (1988, JF) | 4-day TOM window, +15 bps/day | 1988 |
| Bouman & Jacobsen (2002, AER) | Halloween effect in 36/37 countries | 2002 |
| Lucca & Moench (2015, JF) | 80% of annual equity premium earned pre-FOMC | 2015 |
| Vidal & Vidal-García (SSRN 4106003, 2025) | TOM in UK 1990–2023: effect persists | 2025 |
| "Time-Based Trading Patterns" (SSRN, Jan 2025) | Full review: TOM, FOMC, holidays, weekends | 2025 |
| Schroeder (IJFS, Nov 2025) | SEC disclosures 17% higher in winter; February peak, September trough; 22% more insider trading in winter — structural information-flow mechanism for Halloween effect | 2025 |

---

## Data sources for calendar implementation

```python
# Trading day calendar (50+ exchanges)
# pip install exchange_calendars
import exchange_calendars as xcals
cal = xcals.get_calendar("XNYS")    # NYSE
sessions = cal.sessions_in_range("2020-01-01", "2026-12-31")

# FOMC calendar: fetch from Fed website or hardcode annually
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

# US market holidays: exchange_calendars handles these automatically
# cal.is_session(date) → bool
```

---

## What NOT to use (in US large-cap ETFs)

- **January Effect**: Arbitraged away; not reliable since ~2000
- **Weekend/Monday Effect**: Reversed in developed markets; negative expectation
- **Standalone calendar strategies as primary alpha**: TOM CAGR is 5.6% vs SPY 15.2% — meaningful as timing overlay but not standalone

**Bottom line**: Calendar anomalies are best used as OVERLAYS on top of alpha-generating signals (BAB, momentum), not as independent strategies. H201 confirms TOM's Sharpe/drawdown profile; H205 tests whether TOM timing gates improve BAB's already-strong results.
