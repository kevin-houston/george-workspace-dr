---
title: Cryptocurrency Trading Strategies — Systematic Approaches
added: 2026-06-16
updated: 2026-06-16
category: algorithms
sources: |
  Drogen, Hoffstein & Otte (2023) SSRN:4322637; AUT Working Paper (2024);
  Cambridge JFE (2024) TREND factor; Zarattini et al. SSRN:5209907;
  CEPR VoxEU crypto carry; unravel.finance cross-sectional alpha;
  MDPI halving event study (2025); ScienceDirect funding rate arbitrage
related: [regime-detection.md, commodity-trend-following.md, ibs-mean-reversion.md]
---

# Cryptocurrency Trading Strategies — Systematic Approaches

Crypto markets exhibit stronger and more persistent anomalies than equity markets — partly because retail dominates, partly because 24/7 trading allows weekend effects to persist, and partly because information diffusion is slower in less-covered assets. This page covers systematic strategies that have empirical backing, with focus on what's implementable using the existing Kraken paper account ($10k) and ccxt/CoinGecko stack.

---

## 1. Cross-Sectional Momentum

### Evidence

**Drogen, Hoffstein & Otte (2023, SSRN:4322637)**: Cross-sectional momentum is the dominant factor in crypto. The top-quintile vs. bottom-quintile spread earns economically large returns, especially with formation periods of 28–30 days.

**AUT Working Paper (2024)**: Among all tested specifications, the **28-day lookback / 5-day holding period** combo achieves **Sharpe 1.51** vs. 0.84 for the market portfolio — strongest of all momentum configurations tested. Cross-sectional consistently beats time-series momentum.

**Unravel Finance (2024)**: Long top-20% / short bottom-20% of Top-50 coins by market cap, daily rebalanced, with inverse-vol weighting → **Sharpe ~2.0–2.5** when blended with carry factor.

**Trend Factor (Cambridge JFE 2024)**: A TREND signal (combining multiple lookback horizons, analogous to the equity trend factor from Han et al.) achieves **Sharpe 0.5–2.0** depending on the specification, with monthly rebalancing. Strongest results with medium-term (1–3 month) lookbacks.

### Key Parameters

| Parameter | Best specification | Notes |
|-----------|-------------------|-------|
| Formation period | 28 days | Weekly rebalance → Sharpe 1.51 |
| Holding period | 5–7 days | Daily if needed |
| Universe size | Top 50 by market cap | Survivorship bias risk below top 30 |
| Ranking | Pure 28-day return | Don't skip-month in crypto (no reversal at 1-month) |
| Weight | Equal-weight or inv-vol | Inv-vol important: crypto vol dispersion is extreme |
| Longs only | Top quartile | Short leg requires perpetual futures (not Kraken spot) |

**Critical finding**: Unlike equities, **skip-month is unnecessary in crypto** — there is no 1-month reversal effect. 28-day momentum signal is used directly.

### Python Implementation

```python
from pycoingecko import CoinGeckoAPI
import pandas as pd
import numpy as np

cg = CoinGeckoAPI()

def get_top_coins(n=50):
    """Get top N coins by market cap."""
    coins = cg.get_coins_markets(
        vs_currency="usd",
        order="market_cap_desc",
        per_page=n,
        page=1,
        sparkline=False
    )
    return [c["id"] for c in coins]


def fetch_ohlc(coin_id, days=90):
    """Fetch OHLC data for a coin. Free tier: up to 365 days."""
    # Returns [timestamp_ms, open, high, low, close]
    data = cg.get_coin_ohlc_by_id(id=coin_id, vs_currency="usd", days=days)
    df = pd.DataFrame(data, columns=["ts", "open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms")
    df = df.set_index("date").sort_index()
    return df["close"]


def cross_sectional_momentum_signal(prices: pd.DataFrame, lookback=28):
    """
    Compute cross-sectional momentum ranks.
    prices: DataFrame, columns = coin ids, rows = daily dates
    Returns DataFrame of z-scored ranks (long top quartile in practice)
    """
    mom = prices.pct_change(lookback)   # 28-day return (no skip-month)
    ranks = mom.rank(axis=1, pct=True)  # 0 to 1
    return ranks


def run_crypto_momentum_backtest(prices: pd.DataFrame, lookback=28, top_n=5,
                                  inv_vol=True, rebal_days=7):
    """
    Long-only crypto momentum: hold top_n coins by 28-day return.
    rebal_days: rebalance every N days (5 or 7 = weekly)
    """
    equity = 100_000.0
    series = []
    
    # Compute rolling returns and volatility
    mom = prices.pct_change(lookback)
    if inv_vol:
        vol = prices.pct_change().rolling(21).std()

    rebal_dates = prices.index[lookback::rebal_days]
    holdings = None
    weights = None

    for i, date in enumerate(prices.index[lookback:]):
        if date in rebal_dates or holdings is None:
            row = mom.loc[date].dropna()
            row = row[row > -0.99]  # exclude crashed coins
            if len(row) < top_n:
                continue
            top_coins = row.nlargest(top_n).index.tolist()
            if inv_vol:
                vols = vol.loc[date, top_coins].replace(0, np.nan).dropna()
                inv = 1.0 / vols
                weights = inv / inv.sum()
            else:
                weights = pd.Series(1.0 / top_n, index=top_coins)
            holdings = top_coins

        if holdings and i > 0:
            prev = prices.index[lookback + i - 1]
            rets = prices.loc[date, holdings] / prices.loc[prev, holdings] - 1
            port_ret = (rets * weights.reindex(holdings).fillna(0)).sum()
            equity *= (1 + port_ret)
        
        series.append((date, equity))

    return pd.Series({d: v for d, v in series})
```

---

## 2. Time-Series / Trend Following on BTC

### Evidence

**Grayscale Research**: BTC 50-day moving average strategy (long BTC when price > 50d MA, else cash) → Sharpe **1.9** vs buy-and-hold Sharpe 1.3 (2012–2023). Reduces max drawdown dramatically.

**Zarattini, Pagani & Barbon (SSRN:5209907, 2025)**: Ensemble of Donchian channel-based trend models on top-20 liquid coins → **Sharpe >1.5** with **10.8% annualized alpha vs BTC**. Optimal lookback: 30–100 days. Weekly rebalance.

**Quantified Strategies**: EMA crossover strategies (EMA20 vs EMA50) on BTC → annualized returns 126%, Sharpe 1.9 over 2012–2023. Key insight: staying out during bear markets dramatically improves risk-adjusted returns.

### BTC Trend Following — Key Specs

| Signal | Lookback | Sharpe | MaxDD | Notes |
|--------|----------|--------|-------|-------|
| 50d MA | — | 1.9 | ~−50% (2022) | Simple, classic |
| EMA crossover 20/50 | — | 1.9 | Similar | More reactive |
| Donchian channel (ensemble) | 30–100d | 1.5+ | Lower than B&H | Multi-coin |
| 28d momentum | 28 days | 1.51 | — | Best weekly rebalance |

### Python Implementation

```python
import yfinance as yf
import numpy as np
import pandas as pd

def btc_ma_strategy(lookback=50, ticker="BTC-USD"):
    """
    BTC/USD time-series momentum: long when price > lookback-day MA.
    Uses yfinance (free, daily data since ~2014).
    """
    prices = yf.download(ticker, start="2014-01-01", progress=False)["Close"].squeeze()
    ma = prices.rolling(lookback).mean()
    
    # Signal: 1 when in trend, 0 when in cash
    signal = (prices > ma).shift(1).fillna(0)
    
    rets = prices.pct_change()
    strat_rets = signal * rets
    
    equity = (1 + strat_rets).cumprod() * 100_000
    bah     = (1 + rets).cumprod() * 100_000
    
    n_years = (prices.index[-1] - prices.index[0]).days / 365.25
    sharpe_strat = strat_rets.mean() / strat_rets.std() * np.sqrt(252)
    sharpe_bah   = rets.mean() / rets.std() * np.sqrt(252)
    
    print(f"Strategy Sharpe: {sharpe_strat:.2f}  B&H Sharpe: {sharpe_bah:.2f}")
    print(f"Strategy CAGR: {(equity.iloc[-1]/100_000)**(1/n_years)-1:.1%}")
    print(f"% time invested: {signal.mean():.0%}")
    return equity, bah
```

---

## 3. Funding Rate Carry (Perpetual Futures)

### Mechanism

Perpetual futures exchanges (Binance, Bybit, Kraken) use **funding rates** to keep perp prices anchored to spot. When the market is bullish (perp > spot), longs pay shorts every 8 hours. This creates a carry trade:

- **Long spot BTC + short perp BTC = delta-neutral**
- Collect funding rate income without directional exposure
- Funding rate averages ~8% annualized, low volatility (~0.8% StdDev)

### Performance

| Period | Annualized Carry | Sharpe | Notes |
|--------|-----------------|--------|-------|
| 2020–2025 (full) | ~8% | **6.45** | Best period; bull market dominates |
| 2024 | ~4–5% | 4.06 | Compression as institutions enter |
| 2025 | Near-negative | Negative | ETF adoption reduced funding premium |

**Warning**: This is NOT a permanent edge. As institutional capital arbitrages the spread, funding rates compress. The Sharpe of 6.45 full-sample is misleading — recent performance (2025) has turned negative.

### Implementation Notes

```python
# Funding rate data sources
# Coinglass: https://www.coinglass.com (web, API paid tier)
# CryptoHopper API: provides systematic funding rate data
# Alternative: fetch from Kraken/Binance REST API directly

import ccxt

exchange = ccxt.kraken()

def get_funding_rate(symbol="BTC/USDT:USDT"):
    """Fetch current funding rate from Kraken perpetuals."""
    try:
        info = exchange.fetch_funding_rate(symbol)
        return {
            "funding_rate": info["fundingRate"],
            "funding_timestamp": info["fundingDatetime"],
            "next_funding": info["nextFundingDatetime"],
        }
    except Exception as e:
        return {"error": str(e)}

# Delta-neutral carry setup:
# 1. Buy $X BTC on spot
# 2. Short $X BTC perpetual futures
# 3. Collect funding 3× per day (every 8h on most exchanges)
# Kraken: fundingInterval 28800s (8h)
```

**Kraken paper account status**: Perpetual futures available on Kraken, but the Kraken CLI (`/home/node/.cargo/bin/kraken`) primarily wraps spot. Check `kraken futures list` for available perpetual products.

---

## 4. Calendar Anomalies in Crypto

### Monday / Weekend Effect

**Key findings** (multiple studies):

| Day | BTC avg daily return | Notes |
|-----|---------------------|-------|
| Monday | **+0.51%** | Highest; buy late Sunday → sell Monday |
| Tuesday | +0.17% | 2nd best |
| Wednesday | +0.04% | Roughly flat |
| Thursday–Friday | Variable | Lower on average |
| Saturday–Sunday | Lower / negative | Money moves out to equities Mon open |

- **Asymmetric spillover**: Negative weekend crypto returns predict Monday US equity declines; positive crypto weekends do NOT predict equity gains (loss aversion effect — ScienceDirect 2025)
- **Implementation**: Buy BTC Sunday evening (6 PM CT), sell Monday close → captures anomaly with low transaction cost (1 trade per week)

```python
def monday_effect_backtest(ticker="BTC-USD", start="2018-01-01"):
    prices = yf.download(ticker, start=start, progress=False)["Close"].squeeze()
    rets = prices.pct_change()
    
    day_returns = rets.groupby(rets.index.dayofweek).mean()
    # 0=Monday, 1=Tuesday, ..., 6=Sunday
    print("Average return by day of week:")
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for d, r in day_returns.items():
        print(f"  {days[d]}: {r*100:.3f}%")
    
    # Strategy: long only on Monday
    monday_only = rets[rets.index.dayofweek == 0]
    sharpe = monday_only.mean() / monday_only.std() * np.sqrt(52)
    print(f"\nMonday-only Sharpe: {sharpe:.2f}")
    return day_returns
```

### Halving Cycle Positioning

**Empirical pattern** across 4 halvings (2012, 2016, 2020, 2024):

| Halving → Peak | Lag | BTC return |
|----------------|-----|-----------|
| Nov 2012 → Nov 2013 | 12 months | +7,000% |
| Jul 2016 → Dec 2017 | 17.3 months | +291% |
| May 2020 → Nov 2021 | 18.0 months | +541% |
| Apr 2024 → Oct 2025 | 17.6 months | +100% |

**Trend**: Returns are diminishing each cycle as market matures and institutional capital dampens the supply shock. The 2024 cycle returned only 100% vs historical 300–7000%.

**MDPI 2025**: Synthetic control analysis confirms statistically significant positive returns 3 months post-halving (p < 0.05), but effect shrinks each cycle.

**Simple positioning signal**: Long BTC from month 6–18 post-halving, avoid months 1–5 (volatility but no confirmed trend) and months 18+ (peak zone, fade).

```python
HALVING_DATES = {
    "H1": "2012-11-28",
    "H2": "2016-07-09", 
    "H3": "2020-05-11",
    "H4": "2024-04-20",
}

def halving_cycle_position(today: pd.Timestamp, max_lag_months=18) -> dict:
    """Return which cycle phase we're in and whether to be long BTC."""
    for name, date_str in sorted(HALVING_DATES.items(), reverse=True):
        halvdate = pd.Timestamp(date_str)
        months_since = (today - halvdate).days / 30.44
        if 0 <= months_since <= max_lag_months:
            phase = "accumulation" if months_since < 6 else "bull"
            return {"cycle": name, "months_since": round(months_since, 1),
                    "phase": phase, "long_btc": months_since > 6}
    return {"phase": "post_peak", "long_btc": False}
```

---

## 5. Universe Construction for Cross-Sectional Strategies

**The survivorship bias problem** in crypto is severe. Coins that were in the top 50 in 2018 include many that are now worthless (BitConnect, etc.). Mitigation:

1. **Market cap filter at entry**: Only include coins that are top-50 *at the time of the signal*. Use rolling market cap, not current cap.
2. **Liquidity filter**: Exclude coins with 30-day average daily volume < $10M. Illiquid coins have large spreads that destroy returns.
3. **Age filter**: Exclude coins younger than 90 days. New coins spike on launch, creating false momentum.
4. **CoinGecko data quality**: Free API provides daily OHLC back to 2013 for major coins, 2017+ for most altcoins.

```python
def build_crypto_universe(n_top=30, min_volume_usd=10_000_000):
    """
    Build a point-in-time safe universe of top crypto assets.
    n_top: max universe size
    min_volume_usd: minimum daily volume filter
    """
    cg = CoinGeckoAPI()
    coins = cg.get_coins_markets(
        vs_currency="usd",
        order="market_cap_desc",
        per_page=n_top * 2,   # fetch extra to filter
        page=1,
        sparkline=False
    )
    
    universe = []
    for c in coins:
        if c.get("total_volume", 0) >= min_volume_usd:
            universe.append({
                "id":         c["id"],
                "symbol":     c["symbol"].upper(),
                "market_cap": c["market_cap"],
                "volume_24h": c["total_volume"],
                "price":      c["current_price"],
            })
        if len(universe) >= n_top:
            break
    
    # Exclude stablecoins and wrapped tokens
    EXCLUDE = {"usdt", "usdc", "busd", "dai", "wbtc", "steth", "usds"}
    universe = [c for c in universe if c["symbol"].lower() not in EXCLUDE]
    
    return universe
```

---

## 6. Production Notes — Kraken Paper Account Integration

### Kraken CLI Asset Codes

| Coin | Kraken code | Symbol in yfinance |
|------|------------|-------------------|
| Bitcoin | XBT | BTC-USD |
| Ethereum | ETH | ETH-USD |
| Solana | SOL | SOL-USD |
| Cardano | ADA | ADA-USD |

**Note**: Kraken uses `XBT` for Bitcoin (not `BTC`) in API calls. The ccxt wrapper handles this automatically.

```python
import ccxt

kraken = ccxt.kraken({
    "apiKey":    os.environ["KRAKEN_API_KEY"],    # if available
    "secret":    os.environ["KRAKEN_API_SECRET"],
    "enableRateLimit": True,
})

# Paper trading: use sandbox if available, or start with tiny sizes ($10–50)
def get_kraken_balance():
    """Fetch current paper account balances."""
    return kraken.fetch_balance()

def place_market_buy(symbol="BTC/USD", amount_usd=1000):
    """Market buy $X of crypto."""
    ticker = kraken.fetch_ticker(symbol)
    qty = amount_usd / ticker["last"]
    order = kraken.create_order(symbol, "market", "buy", qty)
    return order
```

### What's Viable in $10k Kraken Paper Account

| Strategy | Min capital | Complexity | Suggested allocation |
|----------|------------|------------|---------------------|
| BTC MA (50d) | Any | Low | $5k (BTC only) |
| Cross-sectional momentum (top 5) | $2k+ | Medium | $5k (5 × $1k) |
| Monday effect | Any | Low | $2k overlay |
| Funding carry | $10k+ | High | Not on spot account |

**Recommended first hypothesis**: **BTC 50-day MA** (H302 candidate). Simple, academically documented (Sharpe ~1.9), implementable with Kraken spot. IS: 2014–2020, OOS: 2021–2026. If confirmed → add to production as 5% allocation.

---

## 7. Risk Management for Crypto Strategies

### Volatility

Crypto is 3–5× more volatile than equities. A 20% BTC drawdown in a week is routine. Risk rules:

| Rule | Value | Reasoning |
|------|-------|-----------|
| Max portfolio allocation | 5% of total portfolio | At 80% volatility, even 5% feels like 25% equity exposure |
| Position-level stop | −25% from entry | Avg BTC drawdown during corrections |
| VIX-based gate | Don't add when SPY VIX > 30 | Equity stress = crypto stress + amplification |
| Liquidity gate | Daily volume > 100× position size | Don't get trapped |

### Correlation with Equities

| Regime | BTC–SPY correlation | Notes |
|--------|---------------------|-------|
| Normal low-vol | 0.10–0.25 | Near-uncorrelated; diversification benefit |
| Market crash | 0.70–0.90 | "Risk-off" drives everything down together |
| 2022 bear | 0.68 | Fed hikes crushed both |
| 2024 post-ETF | 0.35 | Institutional adoption increased equity correlation |

**Implication**: Crypto doesn't diversify when you need it most. Treat it as high-beta equity in risk models, not as an alternative asset.

---

## 8. Proposed Hypotheses

### H302 — BTC 50d MA Timing (queued)
- Signal: Daily BTC-USD price vs 50d MA. Long BTC when above, cash when below.
- IS: 2014–2020, OOS: 2021–2026
- Gate: OOS Sharpe > 1.0; Sharpe vs BTC buy-and-hold > 0 (risk-adj improvement)
- Data: `yf.download("BTC-USD")`

### H303 — Cross-Sectional Crypto Momentum (queued)
- Signal: Monthly rebalance, rank top 30 coins by 28-day return, hold top 5 equal-weight
- IS: 2018–2021, OOS: 2022–2026
- Gate: OOS Sharpe > 1.2
- Data: pycoingecko or ccxt OHLC
- Caveat: requires survivorship-safe universe construction

---

## Cross-References

- [Crypto Data Sources](../data-sources/crypto-data-sources.md) — yfinance fragility, ccxt/CoinGecko migration path
- [Commodity Trend Following](commodity-trend-following.md) — similar CTA approach; H261b Corr(SPY)=0.218 lowest of any confirmed H
- [Regime Detection](regime-detection.md) — VIX/SPY overlay applicable to crypto positions
- [Market Timing Overlays](market-timing-overlays.md) — SPY 200MA overlay can gate crypto allocation
- [Calendar Anomalies](calendar-anomalies.md) — Monday effect analogue in equities
- [IBS Mean-Reversion](ibs-mean-reversion.md) — crypto equivalent would be intraday BTC IBS


Add section at bottom of crypto-trading-strategies.md: '## LLM as signal not allocator (PortBench 2026)\n\nPortBench benchmark (arXiv:2604.14199, 2026): 90% of LLMs fail to beat equal-weight portfolio allocation across asset classes including crypto. Key implication for crypto strategy design: use LLMs as filter/signal layer (e.g. regime detection, narrative sentiment) rather than as direct allocation agents. H318 (meta-agent ETF rotation selector) uses LLM as filter with fixed-weight allocation for this reason. Cross-reference: [Multi-Agent LLM Trading](multi-agent-llm-trading.md).'