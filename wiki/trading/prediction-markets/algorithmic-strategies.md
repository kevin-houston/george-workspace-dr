---
updated: 2026-05-13
---

# Algorithmic Strategies for Prediction Markets

## Strategy overview

| Strategy | Difficulty | Annualized edge | Platforms | Notes |
|----------|-----------|-----------------|-----------|-------|
| Cross-market arbitrage | Hard | 0.5–2% | Kalshi + Polymarket | Window collapsed to 2.7s avg; requires automation |
| Cross-derivative arbitrage | Hard | 1–3% | Kalshi + CME | Options pricing expertise required |
| **Event modeling / nowcasting** | Medium | **3–8%** | Kalshi, IBKR | **Best risk-adjusted opportunity; Sharpe ~1.2** |
| Perpetual funding rate arb | Medium | 2–6% | Kalshi Timeless | New (April 2026); funding rate mechanics |
| NLP / sentiment | Medium | 2–5% | Polymarket | LLM APIs commoditized; fine-tuning differentiates |
| Market microstructure | Hard | 0.2–1% | Kalshi | Micro-edges eaten by fees |

---

## 1. Cross-market arbitrage (Kalshi ↔ Polymarket)

Buy YES on one platform, sell NO on the other when they disagree.

- Average spread historically: **~8 probability points** (CPI contracts specifically)
- $40M in realized profits extracted across platforms in 12 months (2025 IMDEA study)
- Opportunity window: **12.3 seconds (2024) → 2.7 seconds (2026)** — now requires sub-second automated execution
- Friction: Kalshi per-contract fee + Polymarket 2% taker fee + latency

**Implementation skeleton**:

```python
import asyncio
import aiohttp

KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"
POLY_BASE   = "https://clob.polymarket.com"

async def get_kalshi_price(session, market_id, api_key):
    headers = {"Authorization": f"Bearer {api_key}"}
    r = await session.get(f"{KALSHI_BASE}/markets/{market_id}", headers=headers)
    data = await r.json()
    return data["market"]["yes_ask"], data["market"]["no_ask"]

async def get_poly_price(session, condition_id):
    r = await session.get(f"{POLY_BASE}/book", params={"token_id": condition_id})
    data = await r.json()
    best_ask = float(data["asks"][0]["price"]) if data["asks"] else None
    best_bid = float(data["bids"][0]["price"]) if data["bids"] else None
    return best_bid, best_ask   # bid=someone will pay this for YES

async def arb_scan(kalshi_market, poly_condition, kalshi_key, threshold=0.03):
    async with aiohttp.ClientSession() as session:
        k_yes_ask, k_no_ask = await get_kalshi_price(session, kalshi_market, kalshi_key)
        p_yes_bid, p_yes_ask = await get_poly_price(session, poly_condition)
        if k_yes_ask and p_yes_bid:
            spread = p_yes_bid - k_yes_ask   # buy Kalshi YES, sell Poly YES
            if spread > threshold:
                print(f"ARB: buy Kalshi YES @{k_yes_ask:.3f}, sell Poly YES @{p_yes_bid:.3f} → {spread:.3f}")
                return ("kalshi_yes", spread)
        # Check reverse direction
        if k_no_ask and p_yes_ask:
            spread_rev = (1 - p_yes_ask) - k_no_ask
            if spread_rev > threshold:
                print(f"ARB: buy Kalshi NO @{k_no_ask:.3f}, buy Poly NO @{1-p_yes_ask:.3f} → {spread_rev:.3f}")
                return ("kalshi_no", spread_rev)
        return None
```

**Realistic verdict**: Edge exists but increasingly institutional. Sub-second execution now required; above is a scanner, not a full trading loop.

---

## 2. Cross-derivative arbitrage (prediction markets vs. CME/options)

Exploit mispricing between Kalshi contracts and CME Fed funds futures or equity options.

**Example**: CME implies 68% rate cut probability; Kalshi prices at 72%. Sell Kalshi, delta-hedge via options.

- Historical edge (2015–2025): ~12% annualized on simple Kalshi/Eurodollar arb
- Viable spread threshold: **>2%** (rare in current markets post-institutional adoption)
- Requires: options pricing model, dual-market data feeds, cross-asset execution

**CME FedWatch probability extraction**:

```python
import requests
from scipy.stats import norm

def cme_fedwatch_prob(meeting_date="2026-06"):
    """Extract market-implied rate cut probability from CME Fedwatch API."""
    # CME Group publishes FedWatch data (unofficial endpoint; may change)
    url = "https://www.cmegroup.com/CmeWS/mvc/FedWatch/currentRates"
    r = requests.get(url, timeout=10)
    data = r.json()
    for m in data.get("meetings", []):
        if meeting_date in m.get("meetingDate", ""):
            return m["probabilities"]   # dict of {rate_target: prob}
    return None

def implied_cut_prob(probs):
    """Probability of at least one 25bp cut = 1 - prob(no cut)."""
    no_cut = probs.get("UNCH", 0.0)   # unchanged rate
    return 1.0 - no_cut
```

---

## 3. Event modeling / nowcasting ⭐ Priority strategy

Build probabilistic forecasts for economic events (CPI, Fed decisions, unemployment). Trade when your estimate diverges from market price.

### Quantitative benchmark

From sparkco.ai CPI nowcast strategy (2015–2025 live track record):

| Metric | Value |
|--------|-------|
| Win rate | 62–68% |
| Annualized return | 11.8% |
| Sharpe ratio | **1.2** |
| Brier score | 0.15 (lower is better; perfect = 0, random = 0.25) |
| Avg calibration error | 12 pp |
| Cross-venue CPI spread | avg 8 pp (Kalshi vs. Polymarket) |

**Key finding**: Favorite-longshot bias exists on Kalshi CPI contracts — the market systematically overprices tail outcomes and underprices near-consensus outcomes. Models that avoid this bias gain ~3% annual edge over raw market prices.

### Data pipeline

```python
from fredapi import Fred
import pandas as pd
import requests

fred = Fred(api_key='...')

# CPI components — pulled monthly
cpi_all  = fred.get_series('CPIAUCSL')     # All-items CPI (seasonally adj)
cpi_core = fred.get_series('CPILFESL')     # Core CPI ex food/energy
cpi_shelter = fred.get_series('CUUR0000SAH')  # Shelter component (lagged 12mo)
cpi_used_cars = fred.get_series('CUSR0000SETA02')  # Used cars — volatile
pce_core = fred.get_series('PCEPILFE')     # PCE core (Fed's preferred)

# Leading indicators (released before CPI)
adp_employ = fred.get_series('ADPWNUSNERSA')  # ADP (2-3d before BLS)
jobless_claims = fred.get_series('ICSA')       # Weekly, best leading

# Atlanta Fed GDPNow (web-scraped — no official API)
def get_gdpnow():
    r = requests.get("https://www.atlantafed.org/cqer/research/gdpnow.aspx")
    # Parse current estimate from page (structure changes occasionally)
    return r.text
```

### Modeling approaches

**ARIMA/VAR (simple baseline)**:
```python
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.api import VAR
from scipy.stats import norm

# Univariate CPI ARIMA
model = ARIMA(cpi_all.pct_change(12).dropna(), order=(1,1,1)).fit()
forecast = model.get_forecast(steps=1)
mu  = forecast.predicted_mean.iloc[0]
std = forecast.conf_int(alpha=0.32).diff(axis=1).iloc[0, 1] / 2  # 1σ

# Probability CPI > X%
def prob_above(threshold, mu, std):
    return 1 - norm.cdf(threshold, loc=mu, scale=std)

# Probability CPI in [lo, hi]% band (Kalshi contract format)
def prob_band(lo, hi, mu, std):
    return norm.cdf(hi, loc=mu, scale=std) - norm.cdf(lo, loc=mu, scale=std)
```

**Bayesian ensemble (better calibration)**:
```python
import pymc as pm
import numpy as np

def bayesian_cpi_forecast(prior_mu, prior_sigma, observations, obs_sigmas):
    """
    Bayesian update: combine economist consensus prior with data signals.
    observations: list of floats (nowcast estimates from different models)
    obs_sigmas:   corresponding uncertainty estimates
    """
    with pm.Model() as model:
        true_cpi = pm.Normal('true_cpi', mu=prior_mu, sigma=prior_sigma)
        for obs, sigma in zip(observations, obs_sigmas):
            pm.Normal(f'obs_{obs:.3f}', mu=true_cpi, sigma=sigma, observed=obs)
        trace = pm.sample(4000, progressbar=False, return_inferencedata=True)
    posterior = trace.posterior['true_cpi'].values.flatten()
    return posterior

# Usage:
# prior: analyst consensus 3.1%, σ=0.3%
# signals: [ADP model: 3.2%, shelter lag model: 3.0%, VAR: 3.15%]
posterior = bayesian_cpi_forecast(
    prior_mu=3.1, prior_sigma=0.3,
    observations=[3.2, 3.0, 3.15],
    obs_sigmas=[0.2, 0.25, 0.15]
)
print(f"P(CPI > 3.2) = {(posterior > 3.2).mean():.3f}")
print(f"P(CPI in 3.0-3.3) = {((posterior >= 3.0) & (posterior < 3.3)).mean():.3f}")
```

### Calibration framework (Brier score + reliability)

Track your model's calibration to catch overconfidence before it becomes expensive:

```python
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def brier_score(probs, outcomes):
    """Lower is better. Perfect=0, random binary=0.25, always-wrong=1."""
    return np.mean((np.array(probs) - np.array(outcomes)) ** 2)

def reliability_diagram(probs, outcomes, n_bins=10):
    """
    Returns calibration error and plots reliability diagram.
    Perfect calibration: 70% confident events happen 70% of the time.
    """
    probs, outcomes = np.array(probs), np.array(outcomes)
    bins = np.linspace(0, 1, n_bins + 1)
    bin_centers, mean_pred, mean_obs, counts = [], [], [], []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() > 0:
            bin_centers.append((lo + hi) / 2)
            mean_pred.append(probs[mask].mean())
            mean_obs.append(outcomes[mask].mean())
            counts.append(mask.sum())
    ece = np.average(np.abs(np.array(mean_pred) - np.array(mean_obs)),
                     weights=counts)  # expected calibration error
    fig, ax = plt.subplots()
    ax.plot([0,1], [0,1], 'k--', label='Perfect')
    ax.scatter(mean_pred, mean_obs, s=[c*5 for c in counts], alpha=0.7)
    ax.set_xlabel("Predicted probability"); ax.set_ylabel("Actual frequency")
    ax.set_title(f"Reliability Diagram (ECE={ece:.3f})")
    return ece, fig

# Track predictions over time
history = pd.DataFrame({
    "date": [...],           # release date
    "p_above_3": [...],      # your model's P(CPI > 3%)
    "outcome": [...],        # 1 if CPI was above 3%, else 0
    "kalshi_price": [...],   # Kalshi price at trade entry
})
bs = brier_score(history["p_above_3"], history["outcome"])
ece, fig = reliability_diagram(history["p_above_3"], history["outcome"])
```

### Peak edge window

Models outperform market consensus in the **3–6 hours before official data release** — when your nowcast has diverged from stale market prices but market hasn't repriced yet. BLS releases CPI at 8:30 AM ET; optimal trading window is 2:00–6:00 AM ET.

**Important**: Kalshi closes CPI contracts ~30 minutes before the release. Build the trade before this window.

### Kalshi full trading lifecycle

```python
import time
import hashlib
import base64
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"

class KalshiClient:
    def __init__(self, key_id, private_key_pem):
        self.key_id = key_id
        self.private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )

    def _sign(self, method, path, timestamp):
        msg = f"{timestamp}{method}{path}".encode()
        sig = self.private_key.sign(msg, padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode()

    def _headers(self, method, path):
        ts = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY":       self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": self._sign(method, path, ts),
            "Content-Type": "application/json",
        }

    def get_market(self, market_id):
        path = f"/trade-api/v2/markets/{market_id}"
        r = httpx.get(KALSHI_BASE + f"/markets/{market_id}",
                      headers=self._headers("GET", path))
        return r.json()["market"]

    def get_orderbook(self, market_id):
        path = f"/trade-api/v2/markets/{market_id}/orderbook"
        r = httpx.get(KALSHI_BASE + f"/markets/{market_id}/orderbook",
                      headers=self._headers("GET", path))
        return r.json()

    def place_order(self, market_id, side, price_cents, count, action="buy"):
        """
        side:   'yes' | 'no'
        price_cents: 1–99 (contract price × 100)
        count:  number of contracts (each costs price_cents / 100 dollars)
        action: 'buy' | 'sell'
        """
        path = "/trade-api/v2/portfolio/orders"
        body = {
            "ticker":  market_id,
            "action":  action,
            "side":    side,
            "type":    "limit",
            "yes_price": price_cents if side == "yes" else 100 - price_cents,
            "count":   count,
        }
        r = httpx.post(KALSHI_BASE + "/portfolio/orders",
                       headers=self._headers("POST", path), json=body)
        return r.json()

    def cancel_order(self, order_id):
        path = f"/trade-api/v2/portfolio/orders/{order_id}"
        r = httpx.delete(KALSHI_BASE + f"/portfolio/orders/{order_id}",
                         headers=self._headers("DELETE", path))
        return r.json()

    def get_positions(self):
        path = "/trade-api/v2/portfolio/positions"
        r = httpx.get(KALSHI_BASE + "/portfolio/positions",
                      headers=self._headers("GET", path))
        return r.json().get("market_positions", [])

    def get_balance(self):
        path = "/trade-api/v2/portfolio/balance"
        r = httpx.get(KALSHI_BASE + "/portfolio/balance",
                      headers=self._headers("GET", path))
        return r.json()["balance"] / 100  # returns cents; convert to dollars
```

**Trade execution logic**:

```python
def execute_cpi_trade(client, market_id, my_prob, kelly_fraction=0.25,
                      max_position_pct=0.05, min_edge=0.03):
    """
    Execute a Kalshi CPI trade when model diverges from market.
    Returns order id or None if no trade taken.
    """
    market = client.get_market(market_id)
    yes_ask = market["yes_ask"] / 100   # convert to probability
    no_ask  = market["no_ask"]  / 100
    # Market price for YES (what we'd pay to buy YES)
    mkt_yes = yes_ask

    edge_yes = my_prob - mkt_yes
    edge_no  = (1 - my_prob) - no_ask

    direction, edge, price_cents = None, 0, 0
    if edge_yes > min_edge:
        direction, edge, price_cents = "yes", edge_yes, market["yes_ask"]
    elif edge_no > min_edge:
        direction, edge, price_cents = "no", edge_no, market["no_ask"]
    else:
        print(f"No edge: model={my_prob:.3f}, mkt={mkt_yes:.3f}")
        return None

    # Kelly sizing: f* = edge / (payout - 1) simplified for binary
    payout = 1.0 / (price_cents / 100)
    kelly_f = (my_prob * payout - (1 - my_prob)) / (payout - 1)
    f = kelly_f * kelly_fraction   # fractional Kelly

    balance = client.get_balance()
    max_spend = balance * max_position_pct
    kelly_spend = f * balance
    spend = min(kelly_spend, max_spend)
    count = max(1, int(spend / (price_cents / 100)))

    print(f"Trade: {direction} @ {price_cents}¢ × {count} contracts  "
          f"(edge={edge:.3f}, Kelly={kelly_f:.3f}, f={f:.3f}, spend=${spend:.0f})")

    order = client.place_order(market_id, direction, price_cents, count)
    return order.get("order", {}).get("order_id")
```

---

## 4. Perpetual funding rate strategy (Kalshi Timeless)

Kalshi Timeless launched April 27, 2026: the first CFTC-regulated perpetual prediction market contracts. Structure mirrors crypto perpetual futures.

### How funding works

- **Contract**: "Will BTC be above $X at 8 PM ET?" — no expiration
- **Funding rate**: Paid every 8 hours. When perp price > fair value, longs pay shorts. When perp < fair value, shorts pay longs.
- **Equilibrium**: Funding rate pushes perp price toward fair value (spot probability estimate)
- **Rate magnitude**: 0.01–0.15% per 8-hour period depending on deviation size
- **CFTC-regulated**: CFTC DCM; contracts settled in USD; margin-based

### Funding rate arbitrage

When the perp price diverges significantly from spot (calculated from options/CME), collect the funding rate:

```python
import httpx
import time

TIMELESS_BASE = "https://trading-api.kalshi.com/trade-api/v2/timeless"   # hypothetical

def get_timeless_price(client, series_id):
    """Get current perp price and next funding rate."""
    r = httpx.get(f"{TIMELESS_BASE}/{series_id}",
                  headers=client._headers("GET", f"/trade-api/v2/timeless/{series_id}"))
    data = r.json()
    return {
        "price": data["yes_bid"] / 100,         # current perp implied prob
        "funding_rate": data["funding_rate"],    # next 8h funding (+ = longs pay)
        "fair_value": data["fair_value"],        # exchange's estimate of fair value
        "next_funding": data["next_funding_ts"],
    }

def funding_arb_signal(timeless_price, spot_prob, funding_rate,
                       threshold=0.03, min_funding=0.005):
    """
    Returns: ('long_collect', 'short_collect', None)
    long_collect: perp undervalued vs spot → buy perp, collect positive funding (shorts pay)
    short_collect: perp overvalued → sell perp, collect positive funding (longs pay)
    """
    deviation = timeless_price - spot_prob
    if deviation > threshold and funding_rate > min_funding:
        return "short_collect"   # perp expensive; longs will pay funding → sell perp
    elif deviation < -threshold and funding_rate < -min_funding:
        return "long_collect"    # perp cheap; shorts will pay funding → buy perp
    return None
```

### Risks

- **Gap risk**: Perp can gap against you if the underlying event probability shifts sharply overnight
- **Liquidation**: Margin-based; leverage amplifies losses
- **Funding rate changes**: Rate adjusts each 8-hour window; a profitable setup can reverse
- **Low liquidity (new product)**: Bid-ask spreads are wide initially; factor 0.5–1% into edge calc

---

## 5. NLP / Sentiment signals

Extract signals from Fed communications, news flow, social media.

**Models**:
- FinBERT: pre-trained BERT on financial text; strong on "hawkish/dovish" classification
- GPT-4: few-shot prompting, comparable to FinBERT with domain prompts
- OpenAI API is available (`$OPENAI_API_KEY` in env) — use for inference

```python
from openai import OpenAI

client = OpenAI()   # reads OPENAI_API_KEY from env

FOMC_PROMPT = """
Classify the following Fed statement excerpt as:
- HAWKISH (rate hike bias, inflation concern dominant)
- NEUTRAL (balanced, data-dependent)
- DOVISH (rate cut bias, employment/growth concern dominant)

Give your answer as JSON: {"stance": "...", "confidence": 0.0-1.0, "key_phrases": [...]}

Text: {text}
"""

def classify_fomc_statement(text):
    response = client.chat.completions.create(
        model="gpt-4o-mini",   # fast, cheap; sufficient for this task
        messages=[{"role": "user", "content": FOMC_PROMPT.format(text=text)}],
        response_format={"type": "json_object"},
        max_tokens=200,
    )
    import json
    return json.loads(response.choices[0].message.content)

# Win rate boost: +2–4% when sentiment strongly aligned with trade direction
# Best signal: Fed speeches 24-48 hours before rate decision markets close
```

**Data sources with keys available**:
- `$NEWSAPI_KEY` — real-time news feed
- EDGAR + `$EDGAR_KEY` — SEC filings, earnings releases
- FRED speeches/minutes — free

---

## 6. Kelly Criterion for position sizing

**Formula** (binary outcomes):
```
f* = (p × M - (1 - p)) / (M - 1)
```

Where:
- `p` = your estimated probability
- `M` = payout odds = `1 / contract_price`

**Example**: Market at $0.65 (65%), your estimate 70%:
```
M = 1 / 0.65 ≈ 1.538
f* = (0.70 × 1.538 - 0.30) / (1.538 - 1) = 0.077 / 0.538 ≈ 14.3%
```

**Practical rule**: Use **quarter-Kelly to half-Kelly** (0.25–0.5 × f*) to account for model uncertainty. Most prediction market losses come from incorrect position sizing, not bad trade direction.

**Portfolio Kelly across multiple simultaneous positions**:
```python
import numpy as np
from scipy.optimize import minimize

def portfolio_kelly(probs, prices, corr_matrix=None):
    """
    Maximize log-growth across n simultaneous positions.
    probs: model probability of YES for each contract
    prices: Kalshi ask price for YES (0-1 scale)
    corr_matrix: n×n correlation of outcomes (None → assume independent)
    """
    n = len(probs)
    payoffs = np.array([1/p - 1 for p in prices])   # net payout if YES wins

    if corr_matrix is None:
        # Independent: simple sum of individual Kelly bets
        f_star = []
        for p, price in zip(probs, prices):
            M = 1 / price
            f = (p * M - (1 - p)) / (M - 1)
            f_star.append(max(0, f))
        return np.array(f_star)

    # Correlated: numerical optimization
    def neg_log_growth(f):
        # Expected log growth over scenarios
        f = np.clip(f, 0, 1)
        # Monte Carlo scenarios
        rng = np.random.default_rng(42)
        n_sim = 10000
        z = rng.multivariate_normal(np.zeros(n), corr_matrix, size=n_sim)
        outcomes = (z > 0).astype(float)   # binary outcomes
        scenario_returns = (outcomes * payoffs - (1 - outcomes)) @ f
        log_growth = np.log(1 + scenario_returns)
        return -log_growth.mean()

    res = minimize(neg_log_growth, x0=np.ones(n) * 0.05,
                   bounds=[(0, 0.25)] * n, method='L-BFGS-B')
    return res.x
```

---

## IBKR ForecastTrader

IBKR provides access to CME-listed ForecastTrader event contracts via the standard IBKR TWS API. Contracts are treated as binary options: buy YES (price in $0–$100 range), collect $100 at expiry if event occurs.

**Available markets**: CPI, unemployment rate, Fed funds rate, S&P 500 index level, Bitcoin range, EUR/USD range.

**Commission**: Free (spread-based); contracts priced $1–$99.

### Python access via `ib_insync`

```python
from ib_insync import IB, Contract, Order, util

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)   # TWS paper trading port

# ForecastTrader contracts are "Forecast" secType
def find_forecast_contract(symbol, expiry, exchange="IBKRFCST"):
    """
    symbol:  e.g. "CPIFC" (CPI ForecastTrader), "USIC" (unemployment),
             "FEDTC" (Fed target rate), "SPX5C" (S&P 500 level)
    expiry:  YYYYMM format, e.g. "202606"
    """
    c = Contract()
    c.secType  = "BINARY"       # or "FOP" depending on contract type
    c.symbol   = symbol
    c.exchange = exchange
    c.currency = "USD"
    c.lastTradeDateOrContractMonth = expiry
    details = ib.reqContractDetails(c)
    if details:
        return details[0].contract
    return None

# Get market data for a ForecastTrader contract
def get_forecast_price(ib, contract):
    ib.reqMktData(contract, "", False, False)
    ib.sleep(1)
    ticker = ib.ticker(contract)
    return {
        "bid":  ticker.bid,
        "ask":  ticker.ask,
        "last": ticker.last,
        "mid":  (ticker.bid + ticker.ask) / 2 if ticker.bid and ticker.ask else None,
    }

# Place a limit order
def buy_forecast(ib, contract, limit_price, quantity=10):
    """
    limit_price: 1–99 (dollars per contract; contract pays $100 at expiry)
    quantity: number of contracts
    """
    order = Order()
    order.action    = "BUY"
    order.orderType = "LMT"
    order.lmtPrice  = limit_price
    order.totalQuantity = quantity
    trade = ib.placeOrder(contract, order)
    ib.sleep(1)
    return trade

# Example: buy CPI contract if model says 60% probability but IBKR shows 55%
cpi_contract = find_forecast_contract("CPIFC", "202606")
price_info   = get_forecast_price(ib, cpi_contract)
print(f"IBKR ForecastTrader CPI: bid={price_info['bid']}, ask={price_info['ask']}")
# if mid < model_prob × 100: buy
```

**Notes**:
- ForecastTrader contracts settle at $100 (YES) or $0 (NO); priced in dollars, not probability units
- IBKR API access requires TWS or IB Gateway running locally; paper trading on port 7497, live on 7496
- `ib_insync` is unofficial but well-maintained (`pip install ib_insync`)
- Liquidity significantly lower than Kalshi; use limit orders only

---

## Recommended starting strategy

**Event nowcasting on Kalshi economic contracts**:
1. Pull FRED data (CPI components, unemployment) via `fredapi`
2. Build ARIMA baseline model; layer in Atlanta Fed GDPNow and ADP data
3. Add FinBERT sentiment on Fed minutes/speeches (OpenAI API for inference)
4. When model diverges >3% from Kalshi price: trade at quarter-Kelly sizing
5. Track: win rate, calibration error (Brier score), after-fee P&L

Target metrics (per sparkco.ai benchmark):
- Brier score < 0.18 (beats market calibration at ~0.20)
- Win rate ≥ 58% on trades with >5% model-market divergence
- Sharpe > 0.8 after 30+ trades

This avoids the speed requirement of arbitrage while giving a durable, data-driven edge.

---

## Open-source frameworks

| Tool | GitHub | Notes |
|------|--------|-------|
| OctoBot Prediction Market | Drakkar-Software/OctoBot-Prediction-Market | Copy trading + arbitrage (beta); good for learning |
| prediction-market-arbitrage-bot | realfishsam/prediction-market-arbitrage-bot | Educational arb bot; not production-optimized |
| py-clob-client | Polymarket/py-clob-client | Official Polymarket Python client |
| kalshi-python | Kalshi-Co/kalshi-python | Official Kalshi Python SDK; covers REST API fully |
| ib_insync | erdewit/ib_insync | Unofficial IBKR async Python wrapper (widely used) |

**Recommendation**: Build custom on top of Kalshi REST API (official SDK). Open-source bots are educational but lack production reliability.

---

## Multi-Agent Swarm Aggregation (PolySwarm Architecture)

**Source**: arXiv:2604.03888 (April 2026). "PolySwarm: A Multi-Agent Large Language Model Framework for Prediction Market Trading and Latency Arbitrage."

### Architecture

1. **Swarm**: N diverse LLM personas (paper uses 50) evaluate each binary market concurrently. Diversity is structural — different priors, information access patterns, analytical styles.
2. **Aggregation**: Confidence-weighted Bayesian combination:
   - Each agent outputs P(yes) + confidence score
   - Swarm consensus = weighted median of agent P(yes) estimates
   - Final probability = Bayesian blend of swarm consensus + market-implied probability
   - Weight on market: inversely proportional to swarm divergence (high disagreement → trust market more)
3. **Position sizing**: Quarter-Kelly based on |P_swarm − P_market| edge
4. **Inefficiency detection**: KL and Jensen-Shannon divergence between swarm distribution and market distribution — high divergence flags potential mispricing

### H185 Implementation Plan

Pre-requisite: Kalshi historical resolved markets data (download via Kalshi REST API `/markets?status=settled`). Current blocker: need to pull and cache ~6 months of resolved market data to backtest swarm accuracy.

```python
# Minimal PolySwarm for Kalshi
PERSONAS = [
    {"role": "macro economist", "bias": "data-driven, skeptical of consensus"},
    {"role": "political analyst", "bias": "tracks polling and historical base rates"},
    {"role": "statistician", "bias": "focuses on base rates and reference class"},
    # ... N total
]

def swarm_estimate(market_title: str, resolution_date: str, current_price: float) -> float:
    estimates = [ask_persona(p, market_title, resolution_date) for p in PERSONAS]
    weights = [e['confidence'] for e in estimates]
    p_swarm = np.average([e['p_yes'] for e in estimates], weights=weights)
    # Bayesian blend: weight on market increases with swarm agreement
    agreement = 1 - np.std([e['p_yes'] for e in estimates])
    p_final = agreement * p_swarm + (1 - agreement) * current_price
    return p_final
```

**Evaluation metrics**: Brier score, log-loss, calibration curve vs human superforecasters.


---

## LLM Forecasting Capability: PolyBench Reality Check

**Source**: arXiv:2604.14199 (Apr 2026). "PolyBench: Evaluating Large Language Model Forecasting on Polymarket Binary Prediction Markets."

**Bottom line**: LLMs are near-random on binary prediction market questions without structured numerical context. This is a calibration anchor for any LLM-based prediction market strategy.

### Benchmark Results (8 models, 2,400 resolved Polymarket questions)

| Model | Accuracy | Brier Score | vs. Market Implied |
|-------|----------|-------------|-------------------|
| GPT-4o | 51.3% | 0.248 | −0.4% |
| Claude 3.5 Sonnet | 52.1% | 0.244 | +0.4% |
| Gemini 1.5 Pro | 50.8% | 0.251 | −0.9% |
| Llama 3.1 70B | 49.7% | 0.255 | −2.0% |
| Market consensus (baseline) | 52.0% | 0.243 | 0% |

**Key finding**: No model systematically beats market consensus. The market itself is a better forecaster than LLMs on the full question distribution.

### Where LLMs Add Value (Narrow)

The paper finds meaningful edge in only 2 sub-categories:
1. **Economic data release questions** (e.g., "Will CPI exceed 3.2% in June?") — LLMs with access to FRED data and trend context achieve 58% accuracy (+6% vs. market) on 30-day horizon questions
2. **Elections with structured polling data** — LLMs aggregating poll numbers outperform market by ~4%

For general geopolitical/sports/entertainment questions: random.

### Implication for H185 (PolySwarm/Kalshi Strategy)

The H185 nowcasting approach (FRED + Fed model + LLM aggregation for CPI/FOMC questions) aligns with the one narrow category where LLMs add value. The strategy should:
- Restrict to economic data release questions (not general events)
- Provide structured numerical context (FRED trends, consensus forecasts) — not rely on LLM priors alone
- Use LLM primarily as aggregator/reasoner over quantitative inputs, not as a knowledge base

Raw "ask the LLM" approaches without structured inputs show zero edge per PolyBench.

---

## H185 Phase 2 Design: PolySwarm Swarm Consensus Upgrade

**Source**: arXiv:2604.03888 (Barot & Borkhatariya, Apr 2026)
**Status**: PROPOSED — extends H185 CPI nowcasting single-model to multi-agent swarm

### Problem
Current H185 design: single LLM call with structured CPI data → single probability estimate → Kalshi trade. PolyBench confirms single-model estimates are near-random without structured data. Even with structured data, a single model point estimate has high variance.

### PolySwarm-inspired upgrade

```python
# H185 Phase 2 — Multi-persona CPI probability aggregation
import numpy as np
from scipy.stats import entropy

PERSONAS = [
    {"name": "Fed watcher", "focus": "FOMC signals, shelter lag, supercore trends"},
    {"name": "Contrarian", "focus": "upside surprise risks, revision history"},
    {"name": "Seasonality expert", "focus": "monthly seasonal adjustments, BLS methodology"},
    {"name": "Energy economist", "focus": "gasoline/energy component transmission lag"},
    {"name": "Housing analyst", "focus": "OER/rent convergence timing"},
    {"name": "Labor market", "focus": "wage growth pass-through to services CPI"},
    {"name": "Supply chain", "focus": "goods deflation vs services stickiness"},
    {"name": "Nowcast quant", "focus": "Cleveland Fed implied prob + NY Fed model"},
    {"name": "Base effects", "focus": "YoY base effect calendar"},
    {"name": "Historical", "focus": "CPI surprise distribution last 36 months"},
]

def aggregate_swarm(estimates, confidences, market_prob):
    """Confidence-weighted Bayesian combination vs market price."""
    weights = np.array(confidences) / np.array(confidences).sum()
    swarm_prob = np.average(estimates, weights=weights)
    # KL divergence as disagreement metric
    disagreement = entropy([swarm_prob, 1-swarm_prob], [market_prob, 1-market_prob])
    # Only trade if swarm diverges meaningfully from market
    edge = swarm_prob - market_prob
    return {"swarm_prob": swarm_prob, "edge": edge, "disagreement": disagreement}

def quarter_kelly(edge, odds, max_fraction=0.1):
    """Quarter-Kelly sizing (conservative)."""
    kelly = edge / odds  # simplified
    return min(kelly * 0.25, max_fraction)
```

### Implementation gates before live
1. Backtest on 24+ historical CPI releases using PredictionMarketBench Kalshi replay framework
2. Swarm must generate >55% directional accuracy on held-out releases
3. Paper trade at least 6 CPI cycles before real capital
4. Cost cap: abort if >$1.00/release in API costs

### Cost estimate (GPT-4o-mini, 10 personas)
- Tokens per persona: ~500 prompt + 200 output = 700 tokens
- 10 personas: 7,000 tokens per CPI release
- Cost: 7k × $0.000150/1k input + 2k × $0.000600/1k output ≈ $0.03/release
- Annual (12 CPI releases): ~$0.36 — effectively free


## Structural Volatility in Binary Prediction Markets (arXiv:2607.08199)

**Source**: Xi, Moallemi, Pai, Want (Jul 2026) — 'Volatility in Prediction Markets: A Structural Approach'
**Data**: Large Kalshi panel across multiple contract categories

**Model components:**

1. **Wright-Fisher deadline-resolution component**: Binary uncertainty must resolve to 0 or 1 by deadline. This forces variance to grow as contracts approach resolution — a structural necessity, not noise. Near resolution, ANY remaining uncertainty = concentrated volatility.

2. **Glosten-Milgrom order-flow component**: Informed traders create volatility proportional to their information advantage, reflected in bid-ask spreads and volume. Analogous to Kyle's λ in equity markets.

**Empirical results on Kalshi panel:**
- Structural model dominates plain ARCH/GARCH benchmarks
- Structural + residual GARCH hybrid gives best overall forecasts
- **Volatility is highest near p=0.50 and near resolution deadline**
- Category differences:
  - Economics contracts (CPI, NFP): smooth deadline-resolution dynamics — predictable volatility curve
  - Sports contracts: event-concentrated, jump-like — discrete news arrivals dominate

**Practical implications for H185 (Kalshi nowcasting pipeline):**

| Rule | Rationale |
|------|----------|
| Enter positions when contract price is away from 50/50 (e.g., >65% or <35%) | Lower volatility → tighter spreads → better fills |
| Avoid new entries within 24h of resolution | Volatility peaks near deadline → spread widens → fill quality degrades |
| Classify contract category before sizing | Economics contracts: use CPI/NFP model outputs directly. Sports: don't use structured data models |
| Use Wright-Fisher scaling for Kelly sizing | k_t = k_base × (p - 0.5)² / σ_WF(t) — scale down as vol rises near resolution |
| Monitor spread as vol proxy | When Glosten-Milgrom spread widens (informed trading active), reduce position until spread normalizes |

**Spread interpretation (from Glosten-Milgrom component):**
Wider spread near resolution = informed traders are active = position in the direction of order flow, not against it. This is the OPPOSITE of market-making — as a directional bettor, follow the spread-widening signal, not fade it.

---

## Semantic Polymarket Pair Arbitrage (arXiv:2512.02436, Dec 2025)

**Source**: "Semantic Trading: Agentic AI for Clustering and Trading of Prediction Markets" (Dec 2025)

**Strategy**: Two-stage LLM pipeline for Polymarket pair arbitrage via implicit logical relationships:
1. Embed all active contract descriptions using `text-embedding-3-small` (or similar)
2. Cluster contracts by cosine similarity; contracts with sim > 0.80 are same-outcome candidates
3. Within each same-outcome pair, identify price divergence (|price_A - price_B| > 5%)
4. Buy the cheaper leg (underpriced contract) with Kelly sizing; hold until convergence or resolution

**Performance (paper)**: 60–70% accuracy in predicting relational patterns; ~20% average returns over week-long horizons on resolved Polymarket contracts.

**Key insight**: LLMs discover *implicit* same-outcome links that price history alone cannot identify. Examples:
- "Will the Fed cut rates in March?" and "Will the 2Y yield drop below 4% by April?" → same macro bet
- "Will NVIDIA beat Q3 earnings?" and "Will AI chip demand exceed 2024 levels?" → correlated resolution

This is fundamentally different from cointegration: semantic clustering identifies economic logic, not price history. H307 (ETF cointegration) confirmed pure price-based cointegration fails OOS; semantic linking may be more durable.

```python
import numpy as np
from openai import OpenAI

client = OpenAI()

def embed_contracts(titles: list[str]) -> np.ndarray:
    resp = client.embeddings.create(model="text-embedding-3-small", input=titles)
    return np.array([d.embedding for d in resp.data])

def find_same_outcome_pairs(titles: list[str], prices: list[float],
                            sim_threshold: float = 0.80,
                            price_gap: float = 0.05) -> list[dict]:
    """Find mispriced contract pairs via semantic similarity."""
    embs = embed_contracts(titles)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    normed = embs / norms
    sim_matrix = normed @ normed.T

    pairs = []
    n = len(titles)
    for i in range(n):
        for j in range(i + 1, n):
            sim = sim_matrix[i, j]
            if sim >= sim_threshold:
                gap = abs(prices[i] - prices[j])
                if gap >= price_gap:
                    cheaper = i if prices[i] < prices[j] else j
                    pairs.append({
                        'idx_cheap': cheaper,
                        'idx_exp': j if cheaper == i else i,
                        'sim': float(sim),
                        'price_gap': float(gap),
                        'title_cheap': titles[cheaper],
                        'title_exp': titles[j if cheaper == i else i],
                    })
    return sorted(pairs, key=lambda x: -x['price_gap'])
```

**Implementation path for H463** (design note — not yet a backtest):
1. Pull active Polymarket contracts via [CLOB API](https://clob.polymarket.com) (`py-clob-client`)
2. Embed contract descriptions using `text-embedding-3-small` (~$0.01 per nightly batch)
3. Identify same-outcome pairs: cosine sim > 0.80
4. Filter to pairs where |price_A - price_B| > 5%
5. Buy cheaper leg with Kelly sizing; track resolution outcomes

**Cost**: ~$5–10/month OpenAI embedding API for nightly batch of ~500 active contracts.

**Key risks to validate:**
- Different resolution dates: a same-outcome pair with different deadlines may not converge
- Liquidity mismatch: buying the cheaper leg may require crossing a wide spread
- False same-outcome: "Will Tech outperform?" and "Will NVIDIA beat?" are similar but not identical
- Requires ≥ 30 resolved contracts with WR ≥ 65% in paper trading before real capital

**Cross-references**: [Polymarket](polymarket.md) | [LLM Semantic Networks arXiv:2604.19476] | [H307 ETF cointegration failure] | oracle3 Wang Transform (below)

---

## oracle3 — Wang Transform Prediction Market Agent (2026)

**Repo**: [YichengYang-Ethan/oracle3](https://github.com/YichengYang-Ethan/oracle3) — Apache 2.0, 633 tests  
**Paper**: Yang (2026), "Pricing Prediction Markets: Risk Premiums, Incomplete Markets, and a Decomposition Framework" — UIUC SSRN working paper  
**Markets**: Kalshi, Polymarket, Solana DFlow + Jito bundles  

### Pricing Model: Wang Transform

Prediction markets suffer systematic **favorite-longshot bias**: a true 50/50 contract typically trades near 0.57. The Wang Transform prices this distortion analytically:

```python
from scipy.stats import norm

def wang_transform_price(p_true: float, lam: float = 0.183) -> float:
    """
    Wang Transform: converts true probability → market price.
    lam (lambda) = 0.183 calibrated on 291,309 resolved contracts.
    A positive lam shifts weight toward tails (risk premium).
    """
    return norm.cdf(norm.ppf(p_true) - lam)

def wang_edge(market_price: float, estimated_p: float, lam: float = 0.183) -> float:
    """Edge = estimated_p minus Wang-adjusted fair price."""
    fair = wang_transform_price(estimated_p, lam)
    return estimated_p - fair   # positive = bet is mispriced in our favor
```

**Calibration**: λ̂ = 0.183 from hierarchical MLE on 291,309 contracts across 6 platforms. Contracts pricing a true 50% event at ~57¢ systematically lose for long-biased buyers — oracle3 shorts these.

### Architecture
- **Pricing engine**: Wang Transform (calibrated λ̂=0.183) + incomplete-markets decomposition
- **Arbitrage strategies**: 8 constraint-based strategies detecting multi-contract mispricings
- **Position sizing**: Kelly criterion on edge estimate with drawdown guard
- **Execution**: Kalshi CLOB, Polymarket CLOB, Solana DFlow atomic execution

### Relevance to H185 (CPI nowcasting)
Our H185 pipeline estimates p(CPI > X) from Cleveland Fed nowcast. The Wang Transform gives the fair Kalshi price for that probability estimate. If Kalshi prices the contract at p_market >> wang_transform_price(p_cleveland_fed), there is edge to short.

**Implementation path**: install oracle3 → plug in Cleveland Fed / NY Fed nowcast for `estimated_p` → Kelly size the bet → submit via Kalshi API (already wired in OneCLI).
