---
updated: 2026-05-05
type: strategy-guide
status: active — H159b NOT CONFIRMED; H161/H162 PARTIAL CONFIRMED; H163 running
---

# Event-Driven Trading Strategies

Systematic exploitation of price drifts triggered by discrete corporate events: earnings releases, dividend announcements, guidance changes, index additions. The edge comes from persistent *under-reaction* — prices adjust slowly, not instantly.

**Related pages**: [Options Income Strategies](options-income-strategies.md) — H162 covered-call ex-div | [Hypothesis Log](../backtesting/hypothesis-log.md) | [Momentum Strategies](momentum-strategies.md)

---

## Why Events Create Edge

Markets are not perfectly efficient around events because:
1. **Investor inattention**: many participants don't monitor every earnings release
2. **Uncertainty about persistence**: earnings beats may be one-off; market waits for confirmation
3. **Limits to arbitrage**: event positions are idiosyncratic, cannot be easily hedged by fast capital

Classic academic anchor: Ball & Brown (1968) showed prices drift for weeks after earnings. Still replicable 50+ years later (though smaller and faster-decaying).

---

## Strategy 1: Post-Earnings Announcement Drift (PEAD)

### Academic Foundation

**Jegadeesh-Titman** (earnings version), **Bernard & Thomas (1989)**: stocks in the top earnings surprise decile (SUE Q5) outperform bottom decile (SUE Q1) by 5–8% over the following 60 days.

Recent evidence:
- Long Q5/Short Q1 hedge portfolio: 5.1% risk-adjusted return over 3 months (~20% annualized) — *Quantpedia (2024)*
- ML with elastic-net over multi-quarter SUE history nearly doubles Sharpe vs simple SUE ranking
- FinBERT on earnings call transcripts achieves 57–58% accuracy for post-announcement direction

### Signal Construction

**SUE (Standardized Unexpected Earnings)**:
```
SUE = (actual_EPS - expected_EPS) / std_dev(surprise_series)
```
Expected EPS = seasonal random walk with drift (prior 8 quarters), OR analyst consensus estimate.

**EAR (Earnings Announcement Return)**:
Abnormal return in 3-day window `[-1, +1]` around announcement, adjusted for market factor.

**Combined signal** (strongest in practice):
- Long: top decile by BOTH SUE and EAR
- Short: bottom decile by BOTH
- 12.5% annual abnormal return in backtests (Bernard & Thomas)

**Gap entry variant** (H159 implementation):
- Trigger: open/prev_close gap ≥ +5% on earnings day
- Enter at market open, hold N days
- Avoids needing analyst EPS estimates (observable from price action alone)

H159 OOS findings (2018–2026):
- Raw event effect: n=374, mean 20-day return = +4.39%, win rate 63.9%, t-stat = 5.64 → **confirmed effect**
- Unhedged portfolio: MaxDD −43 to −58%, Sharpe 0.06–0.44 → **fails as standalone** (market beta kills it in 2020, 2022 crashes)

### Why Unhedged PEAD Fails

Long-only PEAD holds ~30 simultaneous positions at all times, all long equity, all correlated with SPY. In a bear market all 30 positions crash together. The event alpha is real but drowned by beta.

### Beta-Neutral PEAD: H159b — NOT CONFIRMED

Pair each PEAD long with a proportional SPY short:
```
position_spy_short = rolling_60d_beta(stock, SPY) × position_size
```

**H159b OOS results** (best of 4 variants — gap>5%, n=15, hold=20d):
- OOS Sharpe = 0.382, MaxDD = −48.68%, NegYrs = 3
- Beta hedge achieved Corr(SPY) = −0.05 to −0.11 (was 0.59–0.67) ✓
- MaxDD still −48–54% — far above −20% threshold ✗

**Why it still fails**: beta hedging removes market correlation but cannot hedge idiosyncratic risk. Gap-up stocks collapse 50%+ for company-specific reasons unrelated to SPY. The IS/OOS gap (IS Sharpe 1.6 → OOS 0.38) confirms PEAD structural decay post-2018: HFT/algos arbitrage the drift faster than 30-stock equal-weight can exploit.

**Rolling beta calculation** (statsmodels):
```python
from statsmodels.regression.rolling import RollingOLS
import pandas as pd, numpy as np

def rolling_beta(stock_ret, spy_ret, window=60):
    df = pd.DataFrame({'y': stock_ret, 'x': spy_ret}).dropna()
    model = RollingOLS(df['y'], sm.add_constant(df['x']), window=window)
    result = model.fit()
    return result.params['x']  # beta series
```

**Remaining PEAD improvement paths**:
- H163 — FinBERT NLP filter (raise win rate above 64% via transcript sentiment; currently running)
- H164 — ElasticNet 8-quarter SUE history: NOT CONFIRMED (data blocker: FMP v3 deprecated, only 4yr history via yfinance; model collapses to near-zero coefficients)
- H168 — Speaker-weighted FinBERT (analyst Q&A weighted 49%, CFO 30%): QUEUED after H163

### Data Sources for PEAD

| Source | What you get | Cost | Python |
|--------|-------------|------|--------|
| **yfinance** | Earnings dates (approx), EPS actual | Free | `yf.Ticker('AAPL').earnings_dates` |
| **Finnhub** | Earnings calendar, EPS estimate + actual | Free 60 req/min | `GET /calendar/earnings?from=&to=` |
| **FMP** (Financial Modeling Prep) | Historical EPS surprises, SUE-ready data | Free 250 req/day | `GET /v3/earnings-surprises/{symbol}` |
| **Alpaca** | `GET /v1beta1/screener/stocks/most-actives` + corporate events | Free | alpaca-py |
| **EDGAR** | 10-Q/10-K actual EPS | Free | `python-edgar`, direct SEC XBRL API |

```python
# Finnhub earnings calendar
import requests, os
API_KEY = os.getenv("FINNHUB_API_KEY")  # use $NEWSAPI_KEY fallback for non-Finnhub

resp = requests.get(
    "https://finnhub.io/api/v1/calendar/earnings",
    params={"from": "2024-01-01", "to": "2024-03-31", "token": API_KEY}
)
events = resp.json()["earningsCalendar"]
# Fields: date, symbol, epsEstimate, epsActual, revenueEstimate, revenueActual
```

```python
# yfinance — get next earnings date and historical surprises
import yfinance as yf
t = yf.Ticker("AAPL")
print(t.earnings_dates.head(8))          # historical announcement dates
print(t.earnings_history)               # actual vs estimate history
```

---

## Strategy 2: Dividend Announcement Drift

### Academic Foundation

- **DRAD (Dividend Raise Announcement Drift)**: Firms announcing dividend increases of ≥10% show +1.39% AAR on announcement day (Warsaw 2024 study across 395 events, 2015–2024)
- Post-announcement: price holds and drifts slightly further positive for ~20 days
- Dividend decreases show persistent negative drift (−2.97% by day +16) — asymmetric
- Signal is stronger for first-ever dividend / unexpected large raises

**H161 result (PARTIAL CONFIRMED)**: Enter at close of announcement day, hold 40 days. OOS (2018–2026): n=499, WR=59.1%, MeanRet=1.97%, t=4.10 (p<0.0001). Portfolio OOS Sharpe=4.298, MaxDD=−18.06%, Corr(SPY)=0.001. Criteria: 3/3. Key caveat: Sharpe inflated by exit-day P&L model (true Sharpe ~1–2); IS (2007–2017) fails due to GFC. Signal fires frequently for dividend aristocrats (≈6.6 raises/stock/year).

### Signal Construction

```python
# Detect dividend increases ≥10%
import yfinance as yf, pandas as pd

def get_dividend_raises(ticker, min_pct=0.10):
    t = yf.Ticker(ticker)
    divs = t.dividends
    if len(divs) < 2:
        return pd.Series(dtype=float)
    pct_change = divs.pct_change()
    raises = pct_change[pct_change >= min_pct]
    return raises
```

For systematic scanning, use FMP's dividend calendar:
```python
# FMP dividend calendar — upcoming ex-dates
resp = requests.get(
    f"https://financialmodelingprep.com/api/v3/stock_dividend_calendar",
    params={"from": "2024-01-01", "to": "2024-01-31",
            "apikey": os.getenv("FMP_API_KEY")}
)
```

### Ex-Dividend Price Anomaly

Price typically drops by approximately the dividend amount on ex-date. Mean reversion / arbitrage opportunities:
- Day before ex-date: small positive bias (dividend capture buyers)
- Ex-date: mechanical drop, then recovery if yield-seekers re-enter
- **H162 implementation**: sell covered call 10 days before ex-date (collected premium + dividend — risk = early assignment)

**H162 result (PARTIAL CONFIRMED)**: Universe: 50 large-cap dividend payers, 3509 quarterly ex-date events. OOS: WR=68.3%, MeanRet=0.62%, t=6.47. Portfolio OOS Sharpe=2.015, MaxDD=−16.17%, Corr(SPY)=0.167. vs. JEPI ETF: 2.015 vs 1.047 Sharpe (1.9×). Key caveats: (1) call leg loses money OOS (MeanRet=−0.14%, t=−1.92) — no IV risk premium; (2) true driver is stock drift before ex-dates (stock-only OOS MeanRet=0.76%, covered call reduces to 0.62%); (3) BS+HV proxy only — real bid-ask on short-dated options eats 0.2–0.4%. Strategy is "stock drift with a premium cushion," not an options income play.

---

## Market-Neutral Portfolio Construction

### Core Principle

Event portfolios suffer from market beta. Fix: hedge each long with a proportional short.

**Three approaches** (increasing complexity):

| Method | Hedge | Complexity | Residual risk |
|--------|-------|------------|---------------|
| Market-neutral | Short SPY proportional to β | Low | Sector, idiosyncratic |
| Sector-neutral | Short sector ETF (e.g. XLK) | Medium | Idiosyncratic |
| Factor-neutral | Short SPY + sector + size | High | Pure event alpha |

### Rolling Beta Hedge (practical implementation)

```python
import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
import statsmodels.api as sm

def compute_rolling_beta(asset_ret, mkt_ret, window=60):
    """60-day rolling OLS beta. Returns series aligned to asset_ret.index."""
    betas = pd.Series(index=asset_ret.index, dtype=float)
    for i in range(window, len(asset_ret)):
        y = asset_ret.iloc[i-window:i].values
        x = sm.add_constant(mkt_ret.iloc[i-window:i].values)
        try:
            b = OLS(y, x).fit().params[1]
        except Exception:
            b = 1.0
        betas.iloc[i] = b
    return betas.fillna(1.0)

def beta_neutral_return(long_ret, spy_ret, beta_at_entry):
    """
    long_ret: series of daily returns for the long leg
    spy_ret: SPY daily returns over same period
    beta_at_entry: scalar beta computed just before trade entry
    Returns: market-neutral return series
    """
    hedged = long_ret - beta_at_entry * spy_ret
    return hedged
```

### Position Sizing in an Event Portfolio

- Cap individual positions at 5% of portfolio (max 20 simultaneous events)
- Scale by signal strength: `weight ∝ abs(SUE) / sum(abs(SUE))`
- Equal-weight is competitive in practice (low signal-to-noise)

---

## Implementation Checklist

### Pre-trade
- [ ] Confirm earnings/event date is NOT estimated — use actual filing timestamp
- [ ] Filter: exclude stocks with options expiry within 3 days (IV crush noise)
- [ ] Check liquidity: avg daily volume ≥ 500k shares
- [ ] Compute rolling 60-day beta vs SPY before event

### Entry
- [ ] Gap trades: enter at market open on event day
- [ ] SUE trades: enter at close of event day (2-day delay avoids gap noise)
- [ ] Record SPY price at entry for hedge ratio

### During hold
- [ ] Monitor for secondary events (guidance revision, index rebalance) that invalidate the drift thesis

### Exit
- [ ] Hard exit at N days (10, 20, or 40 depending on strategy variant)
- [ ] Softer: exit if position returns >2× expected α (early profit-taking)

---

## Common Pitfalls

**Look-ahead bias**: earnings announcement times (before/after market) matter. A "same-day" entry using closing price on announcement day has look-ahead if announcement came after close. Use `yf.Ticker().earnings_dates` — it includes time where available.

**Survivorship bias**: backtesting on stocks still listed today inflates returns. Use point-in-time constituent lists (Compustat, CRSP) for production-grade tests.

**Transaction costs**: PEAD requires frequent entry/exit of 20–30 positions. At 0.1% RT cost, high-frequency rebalancing (~monthly turnover of 100%) costs ~1.2% annually — manageable if net alpha is 4–6%.

**Earnings date uncertainty**: some providers return estimated dates (±3 days). This can cause entry on wrong day. Finnhub and FMP are more reliable than yfinance for event timestamps.

---

## Hypothesis Status Summary

| H# | Strategy | Status | OOS Sharpe | Key Finding |
|----|----------|--------|-----------|-------------|
| H159 | PEAD — gap entry, unhedged | PARTIAL | 0.44 | Effect real (t=5.64) but beta kills portfolio |
| H159b | PEAD — beta-neutral (rolling 60d OLS) | NOT CONFIRMED | 0.382 | Beta hedge works (Corr→0) but idiosyncratic risk still −49% DD |
| H161 | Dividend raise ≥10% → enter close, hold 40d | PARTIAL CONFIRMED | 4.298* | Strong OOS signal (t=4.10); *Sharpe inflated by exit-day model |
| H162 | Covered calls 10d before ex-div | PARTIAL CONFIRMED | 2.015* | Stock drift is true driver; call leg loses OOS; *exit-day Sharpe inflation |
| H163 | PEAD + FinBERT filter | BLOCKED | — | OOS EDGAR coverage=0; IS analysis in progress (run 3, ~140/203 scored) |
| H164 | PEAD + ElasticNet 8-quarter SUE | NOT CONFIRMED | — | FMP v3 deprecated; 4yr IS insufficient for model training |
| H168 | PEAD + speaker-weighted FinBERT (AV transcripts) | IN-PROGRESS | — | Transcript download ongoing (25/day AV limit); GAP=0.03, ~203 events |
| H171 | PEAD + GPT-4o-mini earnings sentiment (H168 variant) | QUEUED | — | $0.48 total cost; shares H168 transcript cache; queue after H168 |

---

## Further Reading

- Bernard & Thomas (1989) — "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?" *JAE*
- Jegadeesh & Titman (1993) — "Returns to Buying Winners and Selling Losers" *JF*
- Sloan (1996) — accruals anomaly (related: accrual-based earnings quality signal)
- Quantpedia: [Post-Earnings Announcement Effect](https://quantpedia.com/strategies/post-earnings-announcement-effect)
- CFA Institute (2025): "Can Generative AI Disrupt PEAD?"
- ACL 2025: "Enhancing PEAD Measurement with Large Language Models" (FinBERT achieves 57.6–58.3%)

---

## H165 Design Caution — LLM Market Timing (KDD 2026 Finding)

KDD 2026 paper (arXiv:2505.07078, Li et al.) ran FINSABER backtest across 20 years and 100+ symbols: LLM-based timing strategies **do NOT outperform passive benchmarks** in the long run. Failure modes: overly conservative in bull markets (underperforms passive), overly aggressive in bear markets (incurs heavy losses).

**Implication for H165 (TradingAgents):** Do NOT use TradingAgents as a standalone market timer generating direct buy/sell signals. Use only as a **regime gate** — an additional confirmation layer that blocks entries during macro bear regimes (e.g., when LLM + macro data agrees recession is likely, exit H026 to BIL faster than 12m TSMOM alone).

The paper recommends: 'focus on trend detection and regime-aware risk controls over mere scaling of framework complexity.' H026's TSMOM filter already provides trend detection; TradingAgents should augment it with macro regime awareness, not replace it.

**Benchmark before committing API costs**: test a simple VIX threshold (VIX > 30 → BIL) first. If VIX alone achieves the same regime protection as TradingAgents, the LLM layer adds complexity without benefit.
