---
updated: 2026-06-02
status: active
sources:
  - Jegadeesh & Titman (1993) JF — "Returns to Buying Winners and Selling Losers"
  - Asness, Moskowitz & Pedersen (2013) JF — "Value and Momentum Everywhere"
  - Frazzini & Pedersen (2014) JFE — "Betting Against Beta"
  - Jacobs & Levy (2007) FAJ — "Enhanced Active Equity Strategies: Relaxing the Long-Only Constraint"
  - Grinold & Kahn (2019) — Active Portfolio Management, 3rd ed.
  - Avellaneda & Lee (2010) QF — "Statistical Arbitrage in the US Equities Market"
  - AQR Capital — "Craftsmanship Alpha: An Application to Style Investing" (2015)
---

# Long/Short Equity Portfolio Construction

Reference for building dollar-neutral and extended long/short portfolios from cross-sectional factor signals. Directly enables H243 (long/short variant of H241 cross-sectional momentum).

**Key finding motivating this page:** H241 established 200-stock universe momentum has genuine stock-selection alpha (Corr(SPY)=-0.276 OOS, 0 negative years) but can't breach OOS Sharpe 1.5 long-only. H242 confirmed the negative correlation is real (persists sector-neutral at -0.199). Going long/short should unlock the bottom-quintile short-side alpha currently left on the table.

---

## 1. Portfolio Types

### 1.1 Dollar-Neutral (Market-Neutral)

Equal notional long and short. Net exposure ≈ 0, gross exposure = 200%.

```
Long 100% notional → top quintile (20% of universe)
Short 100% notional → bottom quintile (20% of universe)
```

- **Pros:** Removes market beta; return is pure alpha
- **Cons:** Requires borrowable securities; borrow costs drag returns
- **Expected Sharpe lift:** ~1.5–2.5× vs long-only equivalent (Grinold-Kahn)

### 1.2 130/30

Long 130%, short 30%. Net 100% long exposure. More accessible for many fund mandates.

```
Long 130% notional → top ~45% of universe (weighted toward top)
Short 30% notional → bottom ~15% of universe
```

- **Pros:** Net long means participates in market rallies; requires less borrowing
- **Cons:** Beta not hedged; drawdowns similar to long-only in crashes
- **Sharpe lift:** ~0.3–0.6 Sharpe improvement vs long-only (empirical, Jacobs & Levy)

### 1.3 Beta-Hedged (Not Dollar-Neutral)

Use SPY/ES futures to hedge systematic beta while remaining notionally long:

```python
portfolio_beta = 0.85  # measured from regression
hedge_ratio = portfolio_beta  # short SPY for this fraction of AUM
```

- Simpler than full L/S; captures stock-selection without full hedge cost
- Relevant for H241 which has Corr(SPY) < 0 — beta hedge adds very little

---

## 2. Expected Performance: Long-Only vs Long/Short

From AQR research on US equity factors (2000–2020):

| Strategy | Long-Only Sharpe | L/S Dollar-Neutral Sharpe | Lift |
|----------|-----------------|--------------------------|------|
| 12-1m momentum | 0.50–0.80 | 0.90–1.20 | ~1.5× |
| Value (HML) | 0.30–0.50 | 0.70–1.00 | ~1.8× |
| Quality (QMJ) | 0.60–0.80 | 1.00–1.30 | ~1.4× |
| BAB (beta) | 0.70–1.00 | 1.10–1.60 | ~1.5× |
| Reversal | 0.40–0.60 | 0.80–1.10 | ~1.7× |

For our 200-stock universe (H241):
- H241 long-only OOS Sharpe = 1.222 (Variant A, equal-weight)
- **Expected L/S target: 1.5–2.0 Sharpe** (before borrow costs)
- After borrow costs (~50bps/yr for large-cap): **1.4–1.9 Sharpe**

The fundamental reason: long-only captures only the upside of the cross-sectional signal. L/S earns the spread between the top and bottom quantiles, approximately doubling signal-to-noise.

---

## 3. Short Selling Costs

### 3.1 Borrow Rate by Universe

| Universe | Typical Borrow Rate | Notes |
|----------|---------------------|-------|
| S&P 500 top-100 (mega-cap) | 10–50 bps/yr | Very liquid, easy borrow |
| S&P 500 (full) | 25–75 bps/yr | Occasional hard-to-borrow names |
| Mid-cap (S&P 400) | 50–150 bps/yr | Sporadically hard-to-borrow |
| Small-cap (Russell 2000) | 100–500+ bps/yr | Many hard-to-borrow names |
| Highly shorted stocks | 5–50%/yr | Short squeeze risk is real |

For H243 (200 large-cap S&P 500 stocks): **model borrow at 0.50–0.75%/yr on short notional**.

Annual borrow drag on a dollar-neutral portfolio:
```python
# 100% short notional, 0.60% annual borrow rate
borrow_drag_annual = 1.0 * 0.0060  # = 0.60% per year
borrow_drag_monthly = borrow_drag_annual / 12  # = 0.05% per month
```

### 3.2 Hard-to-Borrow Risk

Some bottom-quintile stocks (the ones you want to short most) may be hard to borrow. Mitigations:
1. **Universe filter**: Only short stocks with >$2B market cap and >$5M ADV
2. **Short interest cap**: Skip stocks with >20% short interest (squeeze risk)
3. **Fallback**: Replace HTB names with next-best available short candidate

### 3.3 ETB vs HTB

In practice, prime brokers classify stocks daily as:
- **ETB (Easy-to-Borrow)**: Available at standard rate (<0.25%)
- **HTB (Hard-to-Borrow)**: Premium rate (>0.25%), sometimes unavailable
- **SBR (Short-Borrow Rate)**: Actual annualized cost, updated daily

For backtesting, use a conservative 0.75%/yr uniform assumption for S&P 500 large-cap shorts. Do not apply premium to HTB names (too hard to model historically).

---

## 4. Python Implementation

### 4.1 Dollar-Neutral Portfolio Construction

```python
import numpy as np
import pandas as pd

def build_long_short_portfolio(
    signal: pd.Series,      # cross-sectional signal for all stocks at date t
    n_long: int = 40,       # top-40 (top quintile of 200)
    n_short: int = 40,      # bottom-40
    vol_scale: bool = False,
    vol_series: pd.Series = None,
) -> pd.Series:
    """
    Build dollar-neutral long/short weights from a cross-sectional signal.
    Returns weight series: positive = long, negative = short.
    Sum of positive weights = 1.0, sum of negative weights = -1.0.
    """
    ranked = signal.rank(ascending=False)
    n = len(signal)
    
    long_names  = ranked[ranked <= n_long].index
    short_names = ranked[ranked > n - n_short].index
    
    weights = pd.Series(0.0, index=signal.index)
    
    if vol_scale and vol_series is not None:
        # Inverse-volatility weighting within each leg
        long_vols  = 1.0 / vol_series.loc[long_names].replace(0, np.nan).fillna(0.20)
        short_vols = 1.0 / vol_series.loc[short_names].replace(0, np.nan).fillna(0.20)
        weights.loc[long_names]  =  long_vols  / long_vols.sum()
        weights.loc[short_names] = -short_vols / short_vols.sum()
    else:
        # Equal weight within each leg
        weights.loc[long_names]  =  1.0 / n_long
        weights.loc[short_names] = -1.0 / n_short
    
    return weights

def compute_ls_returns(
    panel: pd.DataFrame,
    signal_col: str = 'mom_6_1',
    fwd_ret_col: str = 'fwd_ret',
    n_long: int = 40,
    n_short: int = 40,
    tc: float = 0.001,
    borrow_rate_annual: float = 0.0075,
) -> pd.Series:
    """
    Run a long/short backtest on a panel DataFrame.
    panel: MultiIndex (date, ticker) with signal_col and fwd_ret_col columns.
    """
    borrow_monthly = borrow_rate_annual / 12
    dates = panel.index.get_level_values('date').unique().sort_values()
    port_rets = []
    prev_weights = pd.Series(dtype=float)
    
    for date in dates:
        df = panel.loc[date]
        signal = df[signal_col].dropna()
        
        if len(signal) < n_long + n_short:
            port_rets.append(0.0)
            continue
        
        weights = build_long_short_portfolio(signal, n_long=n_long, n_short=n_short)
        
        # Transaction costs on turnover
        if len(prev_weights) > 0:
            weight_change = weights.reindex(prev_weights.index, fill_value=0) - prev_weights
            turnover = weight_change.abs().sum() / 2
        else:
            turnover = 1.0
        tc_drag = turnover * tc
        
        # Borrow cost on short leg
        short_notional = weights[weights < 0].abs().sum()
        borrow_drag = short_notional * borrow_monthly
        
        # Portfolio return
        fwd = df[fwd_ret_col].reindex(weights.index)
        port_ret = (weights * fwd).sum() - tc_drag - borrow_drag
        port_rets.append(port_ret)
        prev_weights = weights
    
    return pd.Series(port_rets, index=pd.to_datetime(dates))
```

### 4.2 Sector-Neutral Long/Short

Combine H242's sector-neutralization with L/S:

```python
def sector_neutral_ls_portfolio(
    panel_at_date: pd.DataFrame,
    signal_col: str = 'mom_6_1',
    sector_col: str = 'sector',
    tops_per_sector: int = 2,
    bottoms_per_sector: int = 2,
) -> pd.Series:
    """
    Within each sector: long top-N, short bottom-N.
    Produces a sector-neutral dollar-neutral portfolio.
    """
    weights = pd.Series(0.0, index=panel_at_date.index)
    n_sectors = panel_at_date[sector_col].nunique()
    
    for sector, grp in panel_at_date.groupby(sector_col):
        ranked = grp[signal_col].rank(ascending=False)
        n = len(grp)
        
        if n >= tops_per_sector + bottoms_per_sector:
            longs  = ranked[ranked <= tops_per_sector].index
            shorts = ranked[ranked > n - bottoms_per_sector].index
        else:
            continue  # skip tiny sectors
        
        sector_weight = 1.0 / n_sectors
        weights.loc[longs]  =  sector_weight / tops_per_sector
        weights.loc[shorts] = -sector_weight / bottoms_per_sector
    
    return weights
```

### 4.3 Beta Measurement and Hedging

```python
import statsmodels.api as sm

def compute_rolling_beta(strategy_returns: pd.Series,
                         spy_returns: pd.Series,
                         window: int = 36) -> pd.Series:
    """Rolling beta over window months."""
    betas = []
    for i in range(window, len(strategy_returns)):
        y = strategy_returns.iloc[i-window:i]
        x = sm.add_constant(spy_returns.iloc[i-window:i])
        model = sm.OLS(y, x).fit()
        betas.append(model.params.iloc[1])
    return pd.Series(betas, index=strategy_returns.index[window:])

# For H241 (Corr=-0.276), beta is very low/negative → beta hedge adds minimal value
# But if we extend to a broader factor model, beta hedge stabilizes returns
```

---

## 5. Performance Diagnostics

### 5.1 Long vs Short Leg Attribution

Decompose performance between long and short legs:

```python
def leg_attribution(panel, weights_series):
    """
    Decompose L/S portfolio into long-leg and short-leg returns.
    Returns DataFrame: date × [long_leg, short_leg, ls_spread, market_ret]
    """
    results = []
    for date, weights in weights_series.items():
        long_w  = weights[weights > 0]
        short_w = weights[weights < 0]
        fwd = panel.loc[date, 'fwd_ret']
        
        long_ret  = (long_w  * fwd.reindex(long_w.index)).sum()
        short_ret = (short_w * fwd.reindex(short_w.index)).sum()  # negative weight × negative contribution
        
        results.append({
            'long_leg': long_ret,
            'short_leg': -short_ret,  # flip sign: profit = bought-low-sold-high
            'ls_spread': long_ret - short_ret,
        })
    return pd.DataFrame(results, index=pd.to_datetime(list(weights_series.keys())))
```

Key diagnostic: if the short leg loses money in a bull market (short leg earns when bottom-quintile stocks underperform), that's expected. If the short leg loses money in bear markets too, the signal is weak on the short side.

### 5.2 IC and Long/Short Spread

```python
from scipy.stats import spearmanr

def rolling_ic(panel, signal_col='mom_6_1', fwd_col='fwd_ret', window=12):
    """
    Rolling 12-month Information Coefficient (Spearman rank correlation).
    IC > 0.03 is meaningful for monthly signals.
    """
    dates = panel.index.get_level_values('date').unique().sort_values()
    ics = []
    for i in range(window, len(dates)):
        period = dates[i-window:i]
        sub = panel.loc[period]
        ic, _ = spearmanr(sub[signal_col].dropna(), sub[fwd_col].dropna())
        ics.append({'date': dates[i], 'ic': ic})
    df = pd.DataFrame(ics).set_index('date')
    df['ic_ir'] = df['ic'].rolling(12).mean() / df['ic'].rolling(12).std()
    return df

# IC > 0 → long-side alpha; IC < 0 → signal inverted (would flip long/short)
```

---

## 6. H243 Design — Long/Short Cross-Sectional Momentum

**Hypothesis:** H241-A (200-stock EW momentum, OOS Sharpe 1.222 long-only) leaves the short-side alpha on the table. A dollar-neutral long/short portfolio on the same signal should break the 1.5 Sharpe threshold.

**Setup:**
- **Universe:** Same 195-stock large-cap S&P 500 as H241
- **Signal:** 6-1m momentum (same as H241-A Variant A — best long-only performer)
- **Long leg:** Top-40 stocks by 6-1m momentum (top quintile, ~20%)
- **Short leg:** Bottom-40 stocks by 6-1m momentum (bottom quintile, ~20%)
- **Weighting:** Equal-weight within each leg; test vol-scaled variant
- **TC:** 0.10% per side on turnover (same as H241)
- **Borrow cost:** 0.75%/yr on short notional (~0.0625%/month)
- **IS:** 2013–2020 | **OOS:** 2021–2026
- **Confirm gate:** OOS Sharpe ≥ 1.5 (vs H241-A's 1.222 long-only)

**Variants to test:**
1. **H243-A:** Top/bottom quintile, equal-weight, dollar-neutral
2. **H243-B:** Top/bottom quintile, vol-scaled, dollar-neutral
3. **H243-C:** Top/bottom decile (fewer stocks, stronger signal), equal-weight
4. **H243-D:** Sector-neutral long/short (top-2 long / bottom-2 short per sector)

**Key diagnostic:** If H243-A OOS Sharpe < 1.5, check whether the long leg or short leg is underperforming. If short leg generates near-zero returns, the bottom-quintile stocks are not truly inferior (momentum signal weak on downside).

**Script:** `backtesting/daily/run_h243.py`

---

## 7. Risk Considerations for L/S

### 7.1 Short Squeeze Risk

When many investors short the same stocks, a squeeze can cause violent short-covering rallies:
- GME (Jan 2021), AMC, BBBY examples
- **Mitigation:** Cap position size (2–3% per stock in short leg), avoid stocks with >15% short interest

### 7.2 Momentum Crash Risk

Long/short momentum portfolios are subject to momentum crashes — the worst being 2009 (momentum factor returned -83% in 3 months as beaten-down stocks recovered violently):
- **Mitigation:** Volatility-scaled positions (reduce exposure when market vol is high)
- Or: Regime gate (exit short-side momentum in VIX > 30 environments)
- Reference: Daniel & Moskowitz (2016) — "Momentum Crashes"

### 7.3 Factor Crowding

As more funds run the same momentum signals, alpha decays:
- MTUM ETF AUM > $10B by 2025 — mechanical momentum is crowded
- **Mitigation:** Use proprietary signal modifications (H215 alpha101 factors, H217 median-aggregation) that differ from raw 12-1m momentum
- See: factor-models.md → "Factor Crowding Risk" (arXiv:2512.11913)

### 7.4 Capital Efficiency

Dollar-neutral requires 2× capital to run the same notional (50% tied up as margin for shorts). In practice:
- Most prime brokers allow 4:1 leverage for institutional L/S equity
- For paper trading: Alpaca's margin account supports 2:1 leverage; pattern day trader rules apply for frequent rebalancing
- Monthly rebalancing avoids PDT restrictions

---

## 8. Backtesting L/S: Common Mistakes

| Mistake | Effect | Fix |
|---------|--------|-----|
| Forgetting borrow costs | Overstate returns ~0.6–1%/yr | Add 0.0625%/month on short notional |
| Using same TC for both legs | Understate costs if short leg has higher spread | Use 2× TC for small/illiquid shorts; large-cap: same |
| Survivorship bias in short leg | Bottom quintile has more delisted stocks | Use H241's h241_monthly_prices.parquet which handles delistings via yfinance |
| Look-ahead in signal | Signal uses prices not known at formation date | Always use prices.shift(1) as formation price |
| Assuming HTB = 0 | Short leg may be partially unavailable | Apply universe filter: skip stocks with short interest >15% |

---

## 9. Key Papers

| Paper | Finding | Link to Pipeline |
|-------|---------|-----------------|
| Jegadeesh & Titman (1993) | 12-1m momentum: ~1%/month L/S spread | Foundation of H198, H241 |
| Asness, Moskowitz & Pedersen (2013) | Value+momentum L/S outperforms globally; negative correlation between strategies suggests diversification | Multi-factor blend design |
| Daniel & Moskowitz (2016) JFE | Momentum crashes cluster in high-vol, bear-market rebounds | Risk management for H243 |
| Frazzini & Pedersen (2014) | BAB: low-beta stocks outperform on L/S basis 1.12 Sharpe vs 0.56 L/O | H192-D foundation |
| Jacobs & Levy (2007) FAJ | 130/30 adds ~0.4 Sharpe vs pure long-only; full L/S adds ~0.8 | Benchmark for H243 confirm gate |
| Novy-Marx & Velikov (2016) RFS | TC erodes many L/S anomalies; 6-1m momentum survives with 0.10% TC | Validates H241/H243 TC assumption |

---

## 10. Related Pages

- [Factor Models & Cross-Sectional Alpha](factor-models.md) — factor construction, alphalens, Fama-MacBeth
- [Momentum Strategies](momentum-strategies.md) — H198/H241 time-series and cross-sectional momentum
- [Low-Volatility Anomaly](low-volatility.md) — H192-D BAB as L/S baseline
- [Portfolio Optimization](../tools/portfolio-optimization.md) — HRP, risk parity for multi-factor L/S
- [Transaction Cost Modeling](../backtesting/transaction-costs.md) — borrow cost integration
- [Regime Detection](regime-detection.md) — momentum crash avoidance regime gate
