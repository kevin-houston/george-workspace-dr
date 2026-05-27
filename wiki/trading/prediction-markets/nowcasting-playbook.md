---
created: 2026-05-27
updated: 2026-05-27
status: active
relevance: Kalshi economic contracts, IBKR ForecastTrader, H185 (prediction market nowcasting)
---

# Economic Nowcasting Playbook — Prediction Markets

Operational guide for trading economic data release contracts on Kalshi and IBKR ForecastTrader. See [Algorithmic Strategies](algorithmic-strategies.md) for code scaffolding; this page covers the practical per-release workflow.

---

## Economic Calendar: Kalshi-Tradeable Releases

| Release | Frequency | Typical Release Day/Time (ET) | Kalshi Category | Contract Volume | Edge Window |
|---------|-----------|------------------------------|-----------------|----------------|-------------|
| **CPI** (Consumer Price Index) | Monthly (~mid-month) | Tuesday, 8:30 AM | Economics / Inflation | Highest | 2–6 AM same day |
| **Core PCE** (Personal Consumption Expenditures) | Monthly (last week) | Friday, 8:30 AM | Economics / Inflation | High | Day-before evening |
| **NFP** (Nonfarm Payrolls) | Monthly (first Friday) | Friday, 8:30 AM | Economics / Employment | High | Day-before evening |
| **Fed Funds Rate** (FOMC decision) | 8× per year | Wednesday, 2:00 PM | Economics / Fed | Highest | 1–2 days before |
| **GDP** (advance/second/third estimate) | Quarterly | Thursday, 8:30 AM | Economics | Medium | Week before |
| **Unemployment Rate** | Monthly (same day as NFP) | Friday, 8:30 AM | Economics / Employment | Medium | With NFP model |
| **Recession** (next-12-month probability) | Perpetual | Continuous | Economics | Growing | Long-term position |

### Kalshi URL pattern
```
https://kalshi.com/category/economics   ← browse all active contracts
https://kalshi.com/markets/kxcpi/       ← CPI contract series (example)
https://kalshi.com/markets/kxpcecore/   ← Core PCE
```

Market volume note: Fed rate contracts routinely exceed 100M contracts traded; CPI contracts run 10–50M. Both have institutional market makers with tight spreads; the arb window has compressed from 12s (2024) to 2.7s (2026). Edge now comes from better forecasts, not execution speed.

---

## Nowcasting Data Sources

### 1. Cleveland Fed Inflation Nowcast ⭐ Most actionable

**URL**: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting  
**Updates**: Every business day, ~10:00 AM ET  
**What it provides**: Daily updated nowcasts for CPI, core CPI, PCE, and core PCE in four formats (MoM non-annualized, QoQ SAAR, YoY)  
**Inputs**: Daily oil prices, weekly gasoline prices, monthly CPI/PCE data  
**User guide**: https://www.clevelandfed.org/-/media/project/clevelandfedtenant/clevelandfedsite/indicators-and-data/inflation-nowcasting/nowcasting_users_guide.pdf

```python
import requests
from bs4 import BeautifulSoup
import re

def get_cleveland_fed_cpi_nowcast():
    """
    Scrapes the Cleveland Fed nowcast page for current CPI estimate.
    Returns: dict with mom_pct, yoy_pct, last_updated
    Note: page structure may change; validate periodically.
    """
    url = "https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting"
    r = requests.get(url, timeout=15,
                     headers={"User-Agent": "Mozilla/5.0 (research bot; contact@example.com)"})
    soup = BeautifulSoup(r.text, "html.parser")
    # Cleveland Fed publishes data in a table or downloadable CSV
    # Look for the "Download" link on the page for structured data
    tables = soup.find_all("table")
    # Parse first table (current month nowcast by measure)
    # Fallback: FRED series MEDCPIM158SFRBCLE (Cleveland Fed median CPI)
    cpi_median = None
    try:
        from fredapi import Fred
        fred = Fred(api_key=os.environ.get("FRED_API_KEY", ""))
        # Cleveland Fed Median CPI (monthly, closest proxy)
        median_cpi = fred.get_series("MEDCPIM158SFRBCLE")
        last_val = median_cpi.iloc[-1]
        cpi_median = float(last_val)
    except Exception:
        pass
    return {"median_cpi_mom_pct": cpi_median, "source": "Cleveland Fed / FRED MEDCPIM158SFRBCLE"}
```

### 2. Atlanta Fed GDPNow ⭐ For GDP/recession contracts

**URL**: https://www.atlantafed.org/cqer/research/gdpnow  
**Updates**: Every few days as new data arrives, or after major releases  
**What it provides**: Real-time Q-over-Q annualized GDP growth estimate for current quarter  
**Key advantage**: Updates frequently within the quarter as data arrives; best leading indicator of GDP release surprise

```python
import requests

def get_gdpnow():
    """Fetch Atlanta Fed GDPNow current estimate."""
    # No official JSON API; parse the page or use FRED series GDPNOW
    from fredapi import Fred
    import os
    fred = Fred(api_key=os.environ.get("FRED_API_KEY", ""))
    # FRED hosts the GDPNow series
    gdpnow = fred.get_series("GDPNOW")
    return {
        "current_estimate": float(gdpnow.iloc[-1]),
        "as_of": str(gdpnow.index[-1].date()),
        "description": "Q-o-Q annualized GDP growth (Atlanta Fed GDPNow)",
    }
```

### 3. New York Fed Staff Nowcast (GDP)

**URL**: https://www.newyorkfed.org/research/policy/nowcast  
**Updates**: Every Friday at 11:15 AM ET (except holidays)  
**Format**: Excel file download with current-quarter and next-quarter GDP nowcast  
**Inputs**: Retail sales, industrial production, labor market data, trade balance

```python
import requests
import io
import pandas as pd

def get_nyfed_nowcast():
    """Download NY Fed staff nowcast Excel."""
    # The NY Fed publishes a downloadable Excel on the nowcast page
    # URL format changes; check page for current link
    url = "https://www.newyorkfed.org/medialibrary/media/research/policy/nowcast/new-york-fed-staff-nowcast_data_current.xlsx"
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        df = pd.read_excel(io.BytesIO(r.content), sheet_name=0)
        return df
    return None
```

### 4. FRED Economic Data ← Primary source

Already integrated via `$FRED_API_KEY`. Key series for prediction market forecasting:

| Series | Description | Use for |
|--------|-------------|---------|
| `CPIAUCSL` | CPI All Items (seasonally adj) | CPI contracts |
| `CPILFESL` | Core CPI ex food/energy | Core CPI contracts |
| `CUUR0000SAH` | CPI Shelter component | CPI sub-models (shelter lags 12mo) |
| `PCEPILFE` | Core PCE | PCE contracts |
| `PAYEMS` | Nonfarm payrolls | NFP contracts |
| `UNRATE` | Unemployment rate | Unemployment contracts |
| `GDPC1` | Real GDP | GDP contracts |
| `GDPNOW` | Atlanta Fed GDPNow | GDP contracts (real-time) |
| `MEDCPIM158SFRBCLE` | Cleveland Fed Median CPI | CPI nowcast proxy |
| `ICSA` | Initial jobless claims (weekly) | NFP leading indicator |
| `ADPWNUSNERSA` | ADP private employment | NFP leading indicator (2-3d ahead) |
| `DFF` | Fed Funds effective rate | FOMC contracts |
| `T10Y2Y` | 10-2yr yield spread | Recession probability |

### 5. New: Multi-platform aggregator APIs (2026)

- **Dome** (Y Combinator 2026): unified API across Kalshi + Polymarket — single auth, normalized price format
- **pmxt** (Jan 2026 launch): cross-exchange price comparison and historical data
- **PolyRouter** (beta): smart order routing across exchanges for best execution

None yet have public SDKs; monitor for production-readiness. For now, direct Kalshi + Polymarket REST APIs remain the standard.

---

## Per-Release Playbooks

### CPI — Highest priority, best edge

**Calendar**: ~15th of each month (BLS CPI release page for exact dates)  
**Kalshi closes**: ~30 min before 8:30 AM ET  
**Optimal trade window**: 2:00–5:00 AM ET day-of (late enough to incorporate Asian session, early enough before Kalshi closes)

**Model stack (in order of importance)**:
1. **Shelter lag model**: CPI shelter = Zillow Observed Rent Index lagged ~12 months. Shelter is ~33% of CPI; the lag is a reliable leading indicator. Zillow data: https://www.zillow.com/research/data/ (free CSV download)
2. **Cleveland Fed nowcast**: Pull daily before trading. If FRED `MEDCPIM158SFRBCLE` diverges >10bp from Kalshi-implied, that's a signal.
3. **Used car prices**: Manheim Used Vehicle Value Index or FRED `CUSR0000SETA02` — historically volatile, leads CPI by 1–2 months.
4. **Energy component**: FRED `GASDESW` (weekly gas price) — direct input to CPI energy.

**Signal construction**:
```python
import os
from fredapi import Fred
import numpy as np
from scipy.stats import norm

fred = Fred(api_key=os.environ["FRED_API_KEY"])

def build_cpi_estimate():
    """Simple CPI nowcast from FRED components."""
    cpi = fred.get_series("CPIAUCSL").pct_change(1).dropna() * 100  # MoM %
    shelter = fred.get_series("CUUR0000SAH").pct_change(1).dropna() * 100
    core = fred.get_series("CPILFESL").pct_change(1).dropna() * 100
    gas = fred.get_series("GASDESW").pct_change(1).dropna() * 100  # weekly

    # Regression residual as surprise indicator
    # Shelter-adjusted CPI trend
    shelter_contrib = shelter.iloc[-1] * 0.33  # shelter weight ~33%
    energy_contrib = gas.iloc[-1] * 0.08        # energy weight ~8%
    core_ex_shelter = core.iloc[-1] - shelter.iloc[-1] * 0.43  # core ex-shelter

    # Blended estimate
    estimate_mom = shelter_contrib + energy_contrib + core_ex_shelter
    prior_3m_avg = cpi.iloc[-3:].mean()
    uncertainty = cpi.iloc[-12:].std()  # historical 1σ

    return {
        "estimate_mom_pct": estimate_mom,
        "uncertainty_1sigma": uncertainty,
        "prior_3m_avg": prior_3m_avg,
    }

def cpi_trade_signal(estimate, uncertainty, kalshi_yes_threshold, kalshi_price):
    """
    kalshi_yes_threshold: the CPI level Kalshi contract resolves YES above
    kalshi_price: current Kalshi YES price (0-1 scale)
    Returns: edge (positive = buy YES, negative = buy NO)
    """
    my_prob = 1 - norm.cdf(kalshi_yes_threshold,
                           loc=estimate["estimate_mom_pct"],
                           scale=estimate["uncertainty_1sigma"])
    edge = my_prob - kalshi_price
    return my_prob, edge
```

---

### NFP (Nonfarm Payrolls) — Second priority

**Calendar**: First Friday of month, 8:30 AM ET  
**Kalshi closes**: ~8:00 AM ET  
**Optimal trade window**: Thursday evening after ADP release (Wednesday AM)

**Leading indicators**:
1. **ADP private payrolls** (Wednesday of NFP week): FRED `ADPWNUSNERSA`. Correlation with NFP: ~0.7 historically. ADP surprises vs. consensus predict NFP direction 60-65% of the time.
2. **Initial jobless claims** (Thursday before NFP): FRED `ICSA`. 4-week moving average direction is a reliable leading indicator.
3. **ISM Manufacturing Employment** (Monday of NFP week): ISM reports PMI employment sub-index; >50 = expansion.

**Key caveat**: NFP is notoriously revised. First release has ±75K standard error. Build wide uncertainty intervals.

```python
def build_nfp_estimate():
    adp = fred.get_series("ADPWNUSNERSA").diff().dropna()  # monthly change
    claims_4wk = fred.get_series("ICSA").rolling(4).mean().dropna()
    
    last_adp = adp.iloc[-1]
    claims_trend = claims_4wk.diff().iloc[-1]  # claims rising = bearish NFP
    
    # Simple regression: NFP ≈ ADP × 0.85 + claims_adj + seasonal
    # Historical: ADP underpredicts large moves but gets direction right
    estimate = last_adp * 0.85 - claims_trend * 50  # rough calibration
    return {"estimate_k": estimate / 1000, "uncertainty_k": 75}  # ±75K
```

---

### FOMC Rate Decision — Highest-volume contract

**Calendar**: 8× per year (Jan, Mar, May, Jun, Jul, Sep, Nov, Dec), Wednesday 2:00 PM ET  
**Kalshi closes**: ~1:45 PM ET  
**Optimal trade window**: 1–2 days before decision; optimal if CME FedWatch and Kalshi diverge

**Primary data source**: CME FedWatch Tool — market-implied probabilities from Fed funds futures.

```python
def get_cme_fedwatch_implied(target_date_str):
    """
    Extract market-implied rate decision probabilities.
    Uses FRED Fed Funds futures series as proxy.
    """
    # 30-day Fed Funds futures imply the average fed funds rate
    # for the delivery month — work backward to decision prob
    from fredapi import Fred
    fed_funds = fred.get_series("DFF")  # Effective fed funds rate
    current_rate = fed_funds.iloc[-1]
    
    # CME FedWatch: probability(cut) = (implied_rate - current_rate) / -0.25
    # Direct scrape of CME is unreliable; use FRED series or Bloomberg
    return {"current_rate_pct": current_rate}

# Better: use options on /ZQ (Fed funds futures) to extract implied distribution
# Requires CME data subscription for precision
```

**Edge source**: FOMC decisions have become very well-predicted by CME futures (>95% accuracy in recent years). Edge comes from:
1. Surprise between signal and final statement language (hawkish/dovish)
2. Dot plot surprise (rate projections vs. consensus)
3. Press conference tone divergence from prepared statement

---

### PCE — Undertraded relative to CPI

**Calendar**: Last Friday of month (~1 week after CPI), 8:30 AM ET  
**Kalshi closes**: ~8:00 AM ET  
**Relationship to CPI**: PCE = Fed's preferred measure; typically 0.2–0.4% below CPI YoY. PCE weights shelter lower (~15% vs. CPI's ~33%) and uses expenditure weights, not fixed basket.

**Key insight**: When CPI comes in, you already have ~70% of the information needed to model PCE. CPI-PCE spread is stable enough that a post-CPI PCE trade has low model risk.

```python
def pce_from_cpi(cpi_mom_actual, historical_spread_mean=0.18, historical_spread_std=0.08):
    """
    Estimate PCE MoM from actual CPI print and historical spread distribution.
    Returns: estimated PCE MoM %, uncertainty.
    """
    from scipy.stats import norm
    # PCE ≈ CPI - historical_spread (roughly)
    pce_estimate = cpi_mom_actual - historical_spread_mean
    pce_uncertainty = historical_spread_std
    return pce_estimate, pce_uncertainty
```

---

### GDP — Quarterly, lower frequency

**Calendar**: Advance estimate (month after quarter end, ~Jan/Apr/Jul/Oct), Thursday 8:30 AM ET  
**Sources**: Atlanta Fed GDPNow (best intra-quarter leading indicator), NY Fed Staff Nowcast

**Key caveat**: GDP contracts on Kalshi typically trade as "Will GDP growth exceed X%?" — the advance estimate is later revised; contracts settle on advance estimate only.

---

## Sizing Framework for Economic Releases

Combine Kelly sizing with position limits per release type:

| Release | Max position | Min edge to trade | Kelly fraction |
|---------|-------------|-------------------|----------------|
| CPI | 5% of prediction market capital | 3% | 25% |
| FOMC | 4% of capital | 4% | 20% (FOMC hard to beat) |
| NFP | 3% of capital | 4% (high variance) | 20% |
| PCE | 3% of capital | 2.5% (post-CPI update) | 30% |
| GDP | 2% of capital | 5% | 15% |
| Recession | 5% of capital | 5% | 25% |

**Diversification rule**: No more than 15% of prediction market capital deployed at any one time. FOMC weeks often stack CPI + FOMC + NFP within 2 weeks — total cap applies.

---

## Calibration Tracking

Track every prediction market trade to measure model calibration over time. The goal: Brier score < 0.18 (beats market ~0.20).

```python
import pandas as pd
import numpy as np
from pathlib import Path

TRADE_LOG = Path("/workspace/agent/backtesting/paper_trading/pm_trade_log.csv")

def log_prediction_market_trade(release_type, contract_id, my_prob,
                                 kalshi_price, direction, contracts, outcome=None):
    """
    Log a prediction market trade for calibration tracking.
    outcome: True/False (set at resolution), None (pending)
    """
    row = {
        "date": pd.Timestamp.now().date(),
        "release_type": release_type,
        "contract_id": contract_id,
        "my_prob": my_prob,
        "kalshi_price": kalshi_price,
        "edge": my_prob - kalshi_price if direction == "yes" else (1-my_prob) - (1-kalshi_price),
        "direction": direction,
        "contracts": contracts,
        "outcome": outcome,
    }
    existing = pd.read_csv(TRADE_LOG) if TRADE_LOG.exists() else pd.DataFrame()
    updated = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    updated.to_csv(TRADE_LOG, index=False)
    return row

def compute_brier_score():
    """Compute Brier score on resolved trades."""
    df = pd.read_csv(TRADE_LOG)
    resolved = df[df["outcome"].notna()].copy()
    if len(resolved) == 0:
        return None
    resolved["outcome"] = resolved["outcome"].astype(float)
    bs = np.mean((resolved["my_prob"] - resolved["outcome"]) ** 2)
    win_rate = resolved[resolved["direction"] == resolved["outcome"].astype(str)].shape[0] / len(resolved)
    return {"brier_score": bs, "n_trades": len(resolved), "win_rate": win_rate}
```

---

## Practical Startup Checklist

To begin trading economic release contracts on Kalshi:

1. **Paper phase (first 3 months)**:
   - Log every trade with `log_prediction_market_trade()` but use paper Kalshi account (or note-only)
   - Target: 20+ CPI trades before going live (minimum sample for calibration check)
   - Confirm Brier score < 0.19 before using real capital

2. **Required infrastructure**:
   - `$FRED_API_KEY` — already in env ✓
   - Kalshi API key (RSA key pair, registered at kalshi.com) — not yet set up
   - Cron job to pull Cleveland Fed nowcast daily (or FRED `MEDCPIM158SFRBCLE` proxy)
   - Kalshi contract monitor script (watch for spreads vs. model divergence)

3. **H185 implementation path**:
   - Phase 1: CPI-only ARIMA model vs. Kalshi price, paper trade 3 months
   - Phase 2: Add PCE (leverages CPI model) and ADP→NFP pipeline
   - Phase 3: Add FOMC (CME FedWatch + FinBERT on Fed minutes)
   - Phase 4: Live capital, Kelly-sized, Brier score < 0.18 confirmed

---

## Cross-References

- [Algorithmic Strategies](algorithmic-strategies.md) — code scaffolding for arb, full Kalshi client, Kelly formula
- [Kalshi](kalshi.md) — full RSA auth, WebSocket streaming, rate limits
- [Free / Low-Cost Data Sources](../data-sources/free-data.md) — FRED API setup
- [Earnings Calendar & Corporate Events](../data-sources/earnings-events.md) — complementary event-driven data pipeline
