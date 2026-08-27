---
title: Survivorship Bias & Universe Construction
added: 2026-06-03
category: backtesting
---

# Survivorship Bias & Universe Construction

Survivorship bias is the most common source of inflated backtested Sharpe ratios in systematic trading. It occurs when you test a strategy on the *current* members of an index rather than the *historical* members — unconsciously excluding every company that was delisted, went bankrupt, or was removed from the index during your test period.

## How Much Does It Matter?

- **arXiv:2603.19380** (Ranse 2025, NIFTY Smallcap 250, 2016–2025): survivor-only backtests inflate annual returns by **4.94pp** and Sharpe ratios by **0.097** (≈9% relative).
- **arXiv:0810.1922** (Daniel, Sornette & Wohrmann 2008, S&P 500, 1926–2006): look-ahead benchmark bias reaches **8% per annum** in large-cap US backtests.
- **Shumway (1997)** *Journal of Finance* 52(1) 327–340: delisting returns are **large and systematically negative** for bankruptcy/distress events. Responsible for **≈40% of reported momentum profits** in US data — include delistings and the momentum premium shrinks substantially.

For our universe (large-cap S&P 500 stocks, 2013–present) the bias is moderate: large caps rarely go bankrupt mid-index. But additions/removals at quarterly rebalance dates still introduce bias if you use the current list to build IS history.

## Types of Bias

| Type | Description | Impact Direction |
|------|-------------|-----------------|
| **Survivorship bias** | Using current index members retroactively; missing removed stocks | Inflates returns |
| **Look-ahead bias** | Using index membership known only in the future (e.g., 2026 S&P list for 2015 backtest) | Inflates returns |
| **Delisting bias** | Missing the final negative return when a stock is delisted/bankrupt | Inflates returns for L/S; deflates for long-only |
| **IPO inclusion bias** | Including IPO stocks before they had a 12-month track record | Inflates short-term momentum |
| **Selection bias** | Choosing the universe from a characteristic known in advance (e.g., "most liquid 200 today") | Inflates returns |

## Our Current Exposure (H241–H246)

The H241 cache uses **current** S&P 500 large-cap names downloaded via yfinance. This introduces:

1. **Mild survivorship bias**: stocks added to the S&P 500 since 2013 (e.g., META, NVDA as top weights) are present for their full history even if they weren't in the index. Conversely, companies removed from the index (GE demoted in weight, DXC, etc.) may be absent.
2. **No delisting bias**: all 195 names are currently active — no delistings in the cache.
3. **Practical impact estimate**: for large-cap monthly momentum, bias is **< 0.1 Sharpe** on OOS results (Shumway effect is concentrated in small-caps and stocks near bankruptcy; large-cap S&P 500 names rarely delist mid-index).

For strategy development and hypothesis filtering (not final publication), the current approach is acceptable. For production certification or academic claims, use point-in-time data.

## Data Solutions

### Free Options

**GitHub: fja05680/sp500** ★854  
`https://github.com/fja05680/sp500`

Best free source. File: `S&P 500 Historical Components & Changes.csv`. Point-in-time snapshots from 1996. Reliable from 2001 onward. Shows exact addition/removal dates.

```python
import pandas as pd

# Load historical constituents
sp500 = pd.read_csv('S&P 500 Historical Components & Changes.csv', index_col=0)
# Column per date, True/False for each ticker

def get_universe(date: str) -> list[str]:
    '''Returns S&P 500 constituents on a given date (YYYY-MM-DD).'''
    col = sp500.columns[sp500.columns <= date].max()
    return sp500.index[sp500[col]].tolist()
```

**Limitation**: doesn't include price data for delistings — only tells you *which* stocks should be in the universe.

---

**Wikipedia API (2010–present)**

Scrape Wikipedia revision history for historical S&P 500 membership. Teddy Koker's approach (teddykoker.com/2019/05/creating-a-survivorship-bias-free-sp-500-dataset-with-python):

```python
import requests, pandas as pd

def get_sp500_at_date(date: str) -> list[str]:
    '''Approximate S&P 500 membership as of date via Wikipedia revision history.'''
    url = 'https://en.wikipedia.org/w/api.php'
    params = {
        'action': 'query',
        'prop': 'revisions',
        'titles': 'List_of_S%26P_500_companies',
        'rvprop': 'ids|timestamp|content',
        'rvstart': date + 'T00:00:00Z',
        'rvlimit': 1,
        'format': 'json',
    }
    r = requests.get(url, params=params).json()
    # parse wikitext for ticker symbols
    # ...
    pass  # full implementation: teddykoker/survivorship-free-spy on GitHub
```

Gaps pre-2010; incomplete during rapid rebalance events.

### Paid Options

| Solution | Cost | Delisted Stocks | Point-in-Time | Python | Best For |
|----------|------|:-:|:-:|:-:|---------|
| **fja05680/sp500 + yfinance** | Free | ❌ | ✅ (2001+) | ⭐⭐⭐⭐⭐ | Strategy ideation, IS/OOS R&D |
| **Norgate Platinum** | ~$800–1,500/yr | ✅ | ✅ (1990+) | ⭐⭐⭐⭐ | Production-grade backtests |
| **Sharadar (Nasdaq Data Link)** | Custom quote | ✅ | ⚠️ (partial) | ⭐⭐⭐⭐⭐ | Fundamentals + prices integrated |
| **WRDS CRSP** | ~$10k+/yr | ✅ | ✅ (1926+) | ⭐⭐⭐ | Academic / institutional publication |

**Norgate Data** (`norgatedata.com`) is the practical choice for serious Python backtesting at a reasonable price:
```python
import norgatedata

# Historical S&P 500 constituents at a date
tickers = norgatedata.index_constituent_timeseries(
    'S&P 500', 
    start_date='2013-01-01',
    end_date='2026-06-01'
)
# Returns a DataFrame: date × ticker, True/False membership

# Delisted stock prices included in full database
```

### Handling Delistings in yfinance Backtests

When a stock is delisted, yfinance simply stops returning data. The correct approach:

```python
import yfinance as yf
import numpy as np

DELISTING_RETURN = -0.30  # assume -30% return for involuntary delistings
                           # Shumway (1997) median delisting return

def safe_monthly_return(ticker: str, date: pd.Timestamp) -> float:
    '''Returns monthly return; substitutes DELISTING_RETURN if data ends.'''
    try:
        data = yf.download(ticker, start=date, end=date + pd.DateOffset(months=1),
                           auto_adjust=True, progress=False)['Close']
        if len(data) == 0:
            return DELISTING_RETURN  # stock was delisted during this month
        return float(data.iloc[-1] / data.iloc[0] - 1)
    except Exception:
        return DELISTING_RETURN
```

For large-cap S&P 500 stocks (our universe), involuntary delistings are rare. Voluntary removals (M&A, index rebalancing) tend to produce positive returns at delisting — safe to treat as 0 or the last available return.

## Practical Build: Survivorship-Bias-Reduced Universe

For H241-style backtests using the fja05680 CSV:

```python
import pandas as pd
import yfinance as yf
from pathlib import Path

SP500_HIST = Path('data/sp500_historical_components.csv')

def build_pit_universe(formation_date: str, n_stocks: int = 200) -> list[str]:
    '''
    Build a point-in-time universe from historical S&P 500 membership.
    formation_date: 'YYYY-MM-DD' — use constituents as of this date.
    '''
    sp500 = pd.read_csv(SP500_HIST, index_col=0)
    col = sp500.columns[sp500.columns <= formation_date].max()
    all_members = sp500.index[sp500[col]].tolist()
    
    # Filter to those with price data at formation_date
    available = []
    for tkr in all_members:
        try:
            price = yf.download(tkr, start=formation_date, 
                                end=pd.Timestamp(formation_date) + pd.DateOffset(days=5),
                                progress=False, auto_adjust=True)
            if len(price) > 0:
                available.append(tkr)
        except Exception:
            pass
    
    return available[:n_stocks]

# For a rolling backtest, rebuild universe at each rebalance date
# This eliminates look-ahead bias from index membership
```

## Bias Checklist for Every H-Number Backtest

Before claiming a result is "not confirmed" or "confirmed":

- [ ] **Universe selected at formation date**, not today's composition
- [ ] **No future data used in signal construction** (features use t-1 price, not t price)
- [ ] **Forward return uses t+1 monthly return**, entered at end of month t
- [ ] **Transaction costs applied** (we use 0.10% per side)
- [ ] **IS and OOS are strictly non-overlapping** (no leakage)
- [ ] **Momentum signals use 6-1 skip**: skip the most recent month to avoid microstructure reversal
- [ ] **ML training only uses IS data** — XGBoost fit on IS, applied frozen to OOS

### Common Mistakes Table

| Mistake | Effect | How We Avoid It |
|---------|--------|-----------------|
| Use current S&P 500 list for 2013 backtest | +0.05–0.1 Sharpe inflation | fja05680 CSV or accept mild bias for large-caps |
| Include most-recent-month return in 6-1m signal | Reversal contamination | Always skip `ret_1m` from momentum signal |
| Apply ML model trained on IS+OOS data | Huge IS Sharpe, garbage OOS | H241-C showed IS=3.82, OOS=1.28 — XGBoost overfit |
| Test > 20 variants without correction | False discovery | Apply BH correction at α=0.05 (see `multiple-testing.md`) |
| Report IS Sharpe as the claim | Meaningless | Always report OOS first |
| Include both bearish and bullish delisting returns | Depends on strategy | For long-only large-cap: treat delist as 0 or last price |

## Relevance to H241–H246 Findings

H243's conclusion (short leg hurts) may be *partially* explained by survivorship bias. If the current-constituent universe excludes stocks that became value traps and were removed from the index, we're shorting a cleaner set of "loser stocks" than existed historically. The true losers (delisted, bankrupt) aren't even in the OOS universe to short. This means our H243 result is actually *optimistic* about the short leg — real L/S momentum would underperform our backtest even more due to the delistings we can't short.

For H245 (Low-Vol Anomaly), survivorship bias cuts the other way: the true low-volatility portfolio would include stocks that later went bankrupt (which often show misleadingly low volatility just before collapse). Our current result (OOS Sharpe 0.626) may be slightly *above* what the true survivorship-bias-free result would be.

## Related Wiki Pages

- `backtesting/multiple-testing.md` — how to correct for testing many universe variants
- `backtesting/transaction-costs.md` — cost calibration per strategy type
- `algorithms/long-short-equity.md` — borrow cost and short-leg considerations (H243)
- `data-sources/free-data.md` — yfinance, Polygon free tier limitations
- [Point-in-Time Constituent & Vintage Data Sources](../data-sources/point-in-time-constituents.md) — provider comparison table (fja05680 vs Norgate vs Sharadar vs CRSP) and decision framework for when free PIT data is/isn't sufficient; consolidates the data-sourcing side of this page's bias-mechanism coverage ← new 2026-08-06
- [backtest-bias (Tools)](../tools/backtest-bias.md) — automated survivorship/identity/universe checks (`check_survivorship`, `check_identity`, `check_universe`) that could quantify the qualitative "large caps rarely delist mid-index" argument made above instead of asserting it; v0.3 roadmap targets the same as-of-date look-ahead class as H509–H514 ← new 2026-08-27


---

## Tradability / Price Limit Contamination Bias

**Source:** Du, Y. (2025). "Machine Learning Enhanced Multi-Factor Quantitative Trading."
arXiv:2507.07107. Key finding: 18% IC inflation, +0.44 Sharpe from non-tradable price inclusion.

### Mechanism

In A-shares markets, stocks hitting price limits cannot be traded at the limit price. If
your factor calculation uses the limit price for signal construction and return computation,
you create a circular bias: the "trade" used for backtesting never occurred.

**US market analog:** During single-stock circuit breakers (>5% intraday move on small-caps),
the halt price is not necessarily executable. Similarly, after-hours earnings prints may
show a "closing price" that doesn't reflect next-day open execution.

### The Mask-First Pattern

```python
# Standard (biased) approach
returns = prices.pct_change()  # includes halted sessions
factors = compute_factors(prices)

# Mask-first approach
tradable = ~prices.isnull() & (volume > 0)  # exclude zero-volume (halted) days
returns = prices.pct_change().where(tradable)
factors = compute_factors(prices.where(tradable))
```

### Impact Estimate for US Strategies

- Large-cap ETF rotation (H026/H041a): **negligible** — ETFs never halt
- Stock-level momentum (H198, H217): **small** — large-cap rarely halts, ~0.1 Sharpe inflation
- Small-cap strategies: **material** — small-cap halts are common; estimate ~0.15-0.20 Sharpe inflation
- PEAD (H163/H174): **moderate** — post-earnings halts on surprise beats/misses affect execution
