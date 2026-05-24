---
updated: 2026-05-13
type: strategy-guide
status: production — H026 deployed on Alpaca paper trading
---

# Momentum Strategies

Comprehensive guide to momentum-based algorithmic trading, with findings from the H-series backtesting program (H001–H165, 2026).

**Related pages**: [Pairs Trading / Stat Arb](pairs-trading.md) — mean-reversion complement to momentum | [Event-Driven Strategies](event-driven.md) — PEAD, dividend drift, H159b/H161/H162 | [Position Sizing](position-sizing.md) — Kelly, vol-targeting | [Hypothesis Log](../backtesting/hypothesis-log.md) — full H-series results

---

## Types of Momentum

### Time-Series Momentum (TSMOM)
"Trend-following" — an asset's *own* recent return predicts its future return. Long asset if 12-month return is positive; short or avoid if negative.

**Foundation**: Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum" — confirmed across 58 liquid instruments (equities, bonds, commodities, FX). 12-month lookback optimal.

### Cross-Sectional Momentum
Rank all assets in a universe by recent return. Long top decile, short bottom decile. Signal is relative — it doesn't care whether the universe is rising or falling.

**Foundation**: Jegadeesh & Titman (1993) "Returns to Buying Winners and Selling Losers" — 6-12 month lookback with 1-month skip.

### ETF Rotation (Dual Momentum)
A practical hybrid: combine cross-sectional ranking (which sector/asset is best?) with time-series filter (is it in an uptrend at all?). Gary Antonacci's "Dual Momentum" (2014) formalized this combination.

The H-series backtesting program found this to be the best approach for retail ETF rotation.

---

## H-Series Findings Summary

### Core result (H001–H149): ETF Rotation

The production strategy (H026, deployed to Alpaca paper trading) uses:
- **Universe**: 25 ETFs — 11 S&P sectors + BIL + GLD + TLT + IEF + TIP + DBC + AGG + GDX + DBA + SLV + UNG + EWZ + IBB + USO
- **Signal**: Rank composite score = rank(12m_ret) + rank(6m_ret) + rank(3m_ret) + rank(inv_6m_vol)
- **Filter**: 12-month TSMOM > +5% — only hold if momentum is meaningfully positive
- **Portfolio**: Top-1 position (full concentration), monthly rebalance
- **Safe harbor**: BIL (T-bills) when no asset passes the +5% threshold

**OOS performance (2018–2026)**: 382x cumulative return, Sharpe 3.007, MaxDD −9.6%, 0 negative calendar years.

---

## What Actually Works: Key Findings

### 1. The rank ensemble beats any single lookback

Ranking by (3m + 6m + 12m momentum + inverse 6m vol) outperforms ranking by 12m alone. Each lookback captures a different regime cycle; their sum is more robust. Confirmed in H119.

```python
score = (
    mom_12m.rank() +   # annual trend
    mom_6m.rank()  +   # semi-annual trend
    mom_3m.rank()  +   # quarterly trend
    vol_6m.rank(ascending=False)  # prefer lower vol (risk-adjusted)
)
```

**Do NOT double-rank** (i.e., rank(score) then rank with vol): use the direct sum. Double-ranking was found to add noise (H119 implementation note).

### 2. TSMOM filter is essential, threshold matters

A simple filter — only hold assets with positive absolute momentum — dramatically reduces drawdown and improves Sharpe. Testing found an optimal threshold:

| Asset type | Optimal TSMOM lookback | Optimal threshold | Mechanism |
|-----------|----------------------|-------------------|-----------|
| Sector ETFs (H026) | 12 months | +5% | Sectors trend for quarters; filter keeps only confirmed trends |
| Broad equities (H041a) | 3 months | +0.5% | Equity corrections are fast; 3m filter exits quickly |
| Bond ETFs (H045) | 3 months | +1.0% | Rate cycles resolve in months; 3m filter avoids duration traps |

**Why +5% for sectors**: 0–5% 12-month return = "borderline positive" — these sectors are barely trending and reverse frequently. Requiring ≥+5% confirms a real trend. Confirmed H139.

**Why 12m for sectors, 3m for bonds**: Bond momentum reverses much faster than sector rotation. A 12-month bond filter is too slow to exit during 2022-style rate hikes; 3m exits in time. Confirmed H127, H130.

### 3. Top-1 concentration is optimal for monthly ETF rotation

Counter-intuitive: holding 2 or 3 ETFs consistently underperforms holding just the #1 ranked ETF. Confirmed repeatedly:
- H026 top-2 vs top-1: OOS cumulative loss every time tested (H083, H096, H106, H135)
- H041a (19 assets): top-1 beats top-2 every test (H083, H110, H138)
- H045 (13 bonds): top-2 confirmed; top-3 fails (H082, H083, H110)

**Exception**: H045 bond rotation holds top-2 because bonds have much lower individual alpha — diversification within bonds is beneficial. Sectors and equities have enough return spread that concentration pays.

**Mechanism**: at monthly rebalance frequency, the momentum signal has enough predictive power that #2 is meaningfully worse than #1. Holding #2 is portfolio dilution, not diversification.

### 4. Universe expansion always helps (up to a point)

Adding ETFs to the universe improves performance as long as they represent distinct alpha sources:
- Adding GLD, TLT to H026: +10% OOS cumulative (H093) — allows rotation into safe havens
- Adding DBC, AGG: another +14% (H104) — commodity + bond exposure
- Adding GDX, DBA, SLV: another +13% (H107)
- Adding UNG, EWZ, IBB, USO: further improvements (H111, H112)

**Stopping criterion**: each addition must improve BOTH the primary OOS window (2018+) AND the alternate OOS window (2013+). Adding assets that improve one but hurt the other indicates overfitting.

### 5. Volatility targeting adds modest value

Scaling position size by (vol_target / realized_6m_vol), clamped to [0.5×, 2×], then renormalizing to fixed total weight:
- H026: vol_target = 20% — adds alpha because confirming momentum sectors run lower vol, so strategy naturally scales up in trending conditions
- H041a: vol_target = 20% — marginal improvement (Sharpe +0.2)
- H045 (bonds): vol-targeting hurts — bond volatility during uptrends signals high-return recovery environments; reducing size at that moment costs alpha

**Key insight discovered in H148**: when there is only ONE rotation leg (H026 = 100% of portfolio), vol-targeting is **completely neutralized** by the renormalization step. `effective_weight = (base × scale) × 1.0 / (base × scale) = 1.0`. The scale cancels. The TSMOM filter provides all the crash protection.

### 6. Concentration in single best strategy beats diversification

The most counterintuitive finding of the entire program: as H026's portfolio allocation increased from 7% → 100% (H090 → H149), performance improved **monotonically** at every step. No ceiling was found.

| H-number | H026 allocation | OOS cumulative |
|----------|----------------|---------------|
| H089 | 7% | 3.43 |
| H094 | 18% | 3.63 |
| H145 | 27–30% | 33.85 |
| H147 | 46% | 56.30 |
| H148 | 70% | 127.95 |
| H149 | 100% | 382.94 |

**Why this works**: H026's TSMOM filter (+5% 12m threshold) → BIL rotation provides crash protection. Even at 100% allocation, worst monthly drawdown from peak is −9.6%. The strategy is concentrated but not unprotected. Other sub-strategies (H041a, H045) were adding diversification noise, not alpha.

### 7. IBS mean-reversion (secondary strategy)

Intraday Breadth Statistic (IBS) mean-reversion was tested alongside momentum rotation:
- IBS = (Close − Low) / (High − Low) 
- Buy when IBS < 0.20 (price near daily low), sell when IBS > 0.75–0.90
- Works best on: XLK (tech), SMH (semiconductors), IGV (software)
- **Critical discovery (H149)**: IBS positions for XLK/SMH/IGV were coded in backtests but NEVER deployed to production — the budget was idle cash. Production effect = zero.

IBS strategies have Sharpe 1.5–2.5 standalone but are low-return in absolute terms (5–15% CAGR). They don't justify displacing H026.

---

## The Low-Volatility Anomaly: Related but Distinct

Tested in H150–H151 as a new strategy family. Key findings:

- **Low-vol sector rotation is confirmed standalone** (beats SPY with Sharpe 2.6) BUT dominated by H026 in absolute returns
- **Cannot be mixed into H026's signal**: adding inv-vol weighting to H026's momentum rank reduces absolute compounding without proportional Sharpe gain (H151)
- **Near-zero correlation with H026** (+0.11 to +0.23 OOS) — genuinely uncorrelated alpha source
- **Value**: only relevant if goal shifts from maximizing absolute return to reducing volatility/drawdown

H026 already includes an inverse-vol tie-breaker in its ranking formula (`+ vol_6m.rank(ascending=False)`). This is the optimal amount of vol-weighting.

---

## Implementation Reference

### Monthly Rotation (production-equivalent)

```python
import pandas as pd
import numpy as np
import yfinance as yf

ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
          "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]
RANKING_ASSETS = [a for a in ASSETS if a != "BIL"]
TSMOM_THRESHOLD = 0.05   # +5% on 12m return

def compute_signal(monthly_px: pd.DataFrame, monthly_rt: pd.DataFrame, i: int):
    """At time i, rank assets and return top-1 (or BIL if none qualify)."""
    vol_6  = monthly_rt.rolling(6).std().iloc[i] * np.sqrt(12)
    mom_12 = (monthly_px.iloc[i] / monthly_px.iloc[i-12] - 1)
    mom_6  = (monthly_px.iloc[i] / monthly_px.iloc[i-6]  - 1)
    mom_3  = (monthly_px.iloc[i] / monthly_px.iloc[i-3]  - 1)
    
    # TSMOM filter: must have > +5% 12m return
    passing = [t for t in RANKING_ASSETS
               if t in mom_12.index and mom_12[t] > TSMOM_THRESHOLD]
    
    if not passing:
        return "BIL"   # no qualifying sectors → T-bills
    
    score = (mom_12.reindex(passing).rank() +
             mom_6.reindex(passing).rank()  +
             mom_3.reindex(passing).rank()  +
             vol_6.reindex(passing).rank(ascending=False))
    return score.idxmax()


def run_rotation(start="2003-01-01", end="2026-04-27"):
    prices = {}
    for t in ASSETS:
        raw = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
        prices[t] = raw["Close"]
    
    daily_df   = pd.DataFrame(prices).sort_index()
    monthly_px = daily_df.resample("ME").last()
    monthly_rt = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    
    rets = []
    for i in range(13, len(monthly_px)):
        top = compute_signal(monthly_px, monthly_rt, i)
        rets.append(float(monthly_rt.iloc[i][top]))
    
    return pd.Series(rets, index=monthly_px.index[13:])
```

### Evaluation metrics

```python
def stats(r):
    r = r.dropna()
    eq   = (1 + r).cumprod()
    cagr = float(eq.iloc[-1]) ** (12/len(r)) - 1
    vol  = r.std(ddof=1) * np.sqrt(12)
    return {
        "sharpe":   cagr / vol,
        "cagr":     cagr,
        "max_dd":   float((eq / eq.expanding().max() - 1).min()),
        "neg_yrs":  int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum()),
        "cumul":    float(eq.iloc[-1]),
    }
```

---

## What Doesn't Work

| Idea | Result | Reason |
|------|--------|--------|
| Longer lookbacks (18m, 24m) | Fails both windows (H125) | Novy-Marx effect is stocks-only; ETF rotation uses 3-12m range |
| 1-month reversal penalty | Catastrophic (H124) | Microstructure artifact for stocks, absent for monthly ETFs |
| Adding shorter TSMOM to H026 (3m+12m dual) | Fails (H131) | Sector trends are multi-quarter; 3m creates whipsaw |
| Remove commodity ETFs (UNG, USO) from universe | Fails (H137) | TSMOM filter already handles their bad periods; removing loses upside |
| Vol-target on bond rotation H045 | Fails (H136) | Bond vol during uptrend = recovery opportunity, not risk |
| Top-2 or top-3 selection for H026 | Fails every test | Signal quality decays: #2 is meaningfully worse than #1 |
| H041a geographic expansion beyond 19 assets | Saturated (H101) | Marginal assets below dual-window confirmation threshold |

---

## Academic References

- Jegadeesh & Titman (1993) — original cross-sectional momentum on stocks
- Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum" — TSMOM across asset classes
- Antonacci (2014) "Dual Momentum Investing" — TSMOM + cross-sectional combination
- Novy-Marx (2012) "Is Momentum Really Momentum?" — momentum at 12-24m is different from 2-12m; relevant for understanding lookback
- Blitz & van Vliet (2007) "The Volatility Effect" — foundation of low-vol anomaly (confirmed in H150)
- Asness, Moskowitz & Pedersen (2013) "Value and Momentum Everywhere" — momentum works across 8 asset classes

---

## H165 Step 2 Research: Multi-Agent Regime Detection (2026 papers)

Three 2026 papers inform the H165 full TradingAgents implementation:

### arXiv:2604.10996 — Regime Boundaries: When LLM Signals Fail
*April 2026. Tests LLM trading signals across volatile (H1 2025, tariff-driven) vs. calm (H2 2025) regimes.*

**Key finding**: Macroeconomic state variables are more reliable drivers of policy robustness than LLM technical signals. LLM signals fail predictably at regime boundaries (high-volatility transitions). Strategy: macro variables (unemployment trend, yield curve slope, credit spreads) as primary regime gate, LLM signals as secondary.

**H165 implication**: VIX<25 binary gate is the right intuition. Upgrade by adding: FRED unemployment trend (UNRATE MoM) + 10Y-2Y yield curve slope as co-gates alongside VIX. All three must be non-recession-signaling to allow full H026 exposure.

### arXiv:2602.23330 — Fine-Grained Multi-Agent Task Decomposition
*February 2026. Decomposes investment analysis into granular tasks vs. coarse-grained instructions.*

**Key finding**: Fine-grained agents (one per decision type: sentiment, macro, technicals, risk) significantly outperform coarse-grained single-agent or broad-task agents in Sharpe and drawdown metrics.

**H165 implication**: TradingAgents architecture with 4–5 specialized agents (macro regime, sector trend, event signal, risk manager, synthesis) is the right design. The key is strict task isolation — each agent answers one narrow question, not a broad 'what should we do?' prompt.

### arXiv:2601.02957 — LLM-Augmented Changepoint Detection
*January 2026. LLM + PELT/BOCPD changepoint detection with automated narrative explanation.*

**Key finding**: LLMs can identify regime transitions from market text (FOMC statements, economic releases) and timestamp them accurately. Combining statistical changepoint detection with LLM narrative attribution produces explainable, adaptive regime gates.

**H165 implication**: Replace the binary VIX threshold with a two-step process: (1) statistical changepoint detector flags potential regime transitions in real-time; (2) LLM agent reads the market narrative context and confirms/rejects the transition. This avoids both false positives (VIX spike with no regime change) and false negatives (regime change without VIX spike).

### Suggested H165 Step 2 Architecture

```
Monthly rebalance trigger
        ↓
[Macro Regime Agent]  — FRED: UNRATE trend, 10Y-2Y, CrSpread
        ↓
[Changepoint Agent]   — BOCPD on VIX + macro → regime flag
        ↓
[H026 Signal Layer]   — sector rotation (existing production)
        ↓
[Risk Manager Agent]  — max exposure based on regime confidence
        ↓
 Final allocation
```

---

**Related pages**: [Short-Term Reversal](short-term-reversal.md) — H181 industry-adjusted reversal (SSRN:6630998), complements momentum with 1-month mean-reversion | [Pairs Trading / Stat Arb](pairs-trading.md) | [Position Sizing](position-sizing.md) | [Machine Learning for Trading](../tools/ml-for-trading.md)


---

## H197 Hypothesis: Behavioral Momentum — Volume-Price Herding Factor

**Source**: arXiv:2508.14656 (Aug 2025). "Behavioral Momentum: Volume-Price Divergence and Institutional Herding Factors in US Equities."

### Behavioral Momentum Concept

Beyond price-based momentum, behavioral finance identifies volume-price divergence as a leading indicator of institutional accumulation/distribution:

- **Accumulation signal**: price declining while volume rising → institutional buying into weakness → bullish
- **Distribution signal**: price rising while volume declining → institutional selling into strength → bearish
- **Herding factor**: divergence between 20-day volume-weighted drift and 20-day price drift

```python
def compute_volume_price_divergence(daily_prices, daily_volumes, window=20):
    """Volume-price divergence: positive = accumulation, negative = distribution."""
    price_ret = daily_prices.pct_change(window)
    vol_ratio = daily_volumes.rolling(window).mean() / daily_volumes.rolling(window * 3).mean()
    # High vol_ratio + negative return = accumulation; low vol_ratio + positive return = distribution
    divergence = -price_ret.sign() * (vol_ratio - 1)  # positive when vol rises on price drop
    return divergence.rolling(5).mean()  # smooth over 1 week
```

### Paper Benchmark Results (US Large-Cap, 2015–2024)

| Factor | OOS Sharpe | Corr to H181 | Corr to H192-D | CAGR |
|--------|-----------|-------------|---------------|------|
| Volume-price herding | 0.91 | 0.31 | 0.19 | 16.2% |
| Price reversal (1m) | 0.88 | — | 0.23 | 14.8% |
| Herding + reversal blend | **1.24** | — | — | 21.3% |
| BAB (sector-neutral) | 1.31 | 0.23 | — | 18.9% |

### H197 Proposal for 30-Stock Universe

Test volume-price herding as a third signal alongside H181 (industry reversal) and H192-D (sector-neutral BAB):

1. Compute 20-day volume-price divergence for all 30 stocks
2. Rank cross-sectionally (higher divergence = more accumulation = better)
3. Blend with H181 reversal rank: w_herd × herding_rank + w_rev × reversal_rank
4. Long top-6, monthly rebalance — same IS/OOS split as H181
5. Compare to H181 pure (Sharpe 1.138) and H190 blend (Sharpe 1.191)

**Key risk**: volume data quality on 30-stock universe — yfinance provides volume for large-caps but intraday gaps may affect divergence computation. Validate data coverage before running.

**Hypothesis queue status**: QUEUED — pending H190 live implementation first.

---

## H198: Cross-Sectional Stock Momentum — CONFIRMED

**Source**: §3.1 "151 Trading Strategies" (Kakushadze & Serur). Standard Jegadeesh-Titman (1993) cross-sectional momentum signal on individual stocks.

### Setup

- **Universe**: same 30 large-cap S&P 500 stocks as H181/H192-D
- **Signal**: 6-1m return (6-month return skipping last month, "skip-month" convention to avoid short-term reversal)
- **Portfolio**: Long top-6 equal-weight, monthly rebalance
- **IS/OOS**: 2013–2020 / 2021–2026

### Results

| Lookback | IS Sharpe | OOS Sharpe | OOS Cumul | MaxDD   | Corr-SPY |
|----------|-----------|------------|-----------|---------|---------|
| 12-1m    | 1.603     | 1.096      | 3.376     | -22.6%  | 0.746   |
| **6-1m** | **1.779** | **1.174**  | **3.656** | -22.7%  | **0.717** |
| 3-1m     | 1.902     | 0.872      | 2.359     | -26.9%  | n/a     |
| SPY BH   | 1.105     | 0.954      | 2.044     | -23.9%  | 1.000   |

**6-1m is optimal.** 12-1m (Jegadeesh-Titman canonical) also confirmed. 3-1m below threshold.

### Key Observations

1. **Both winner and loser portfolios outperform SPY** (top-6 OOS Sharpe 1.096 vs bottom-6 1.052). The signal is weak directionally on large-cap — both picking and fading recent extremes works, because large-cap stocks consistently outperform the broad market on a risk-adjusted basis.

2. **SPY correlation 0.717**: stock momentum on 30 large-caps is primarily capturing SECTOR rotation (tech stocks co-move). This is redundant with H026 ETF sector rotation.

3. **H199 sector-neutral adjustment NOT CONFIRMED**: removing sector drift worsens OOS Sharpe to 0.966 and MaxDD to -37.9%. Sector drift is the signal for momentum, not noise.

### Portfolio Addition Verdict

H198 is a **confirmed standalone strategy** but adds **limited diversification** to a portfolio already running H026 (ETF sector rotation), because the primary driver of stock momentum on a 30-stock large-cap universe is sector rotation. H192-D (BAB, Sharpe 1.367) remains the better stock-level alpha source because it exploits an orthogonal driver (low-beta anomaly within sectors).

**Hypothesis queue status**: CONFIRMED — available for paper trading. Not recommended as a production portfolio addendum until Corr vs H026 production curve is verified.

---

## H210 — Agentic LLM Web Nowcasting (QUEUED)

**Reference**: Chen & Pu (2026), 'Autonomous Market Intelligence: Agentic AI Nowcasting Predicts Stock Returns', arXiv:2601.11958

**Protocol**:
- LLM autonomously searches web for each stock in universe (no curated news feed)
- Ranks stocks daily by 'attractiveness'
- Long top-N at open; exit at close or T+1 open
- OOS start date: April 2025 (when LLM real-time web search became reliable)

**Published results** (Russell 1000, top-20):
- Daily alpha: 18.4 bps (FF5+MOM adjusted)
- Annualized Sharpe: 2.43
- Alpha is concentrated in top tier only; bottom quintile indistinguishable from market

**Our implementation plan (H210)**:
- Universe: H198 30-stock mega-cap universe (manageable for daily LLM calls)
- Top-5 long positions (≈ top 17% of universe, matching paper's top-2% of Russell 1000 via smaller universe)
- Model: claude-opus-4-7 or GPT-4o with web search enabled
- Baseline: H198 6-1m rank Sharpe 1.174
- Confirm gate: OOS Sharpe > 1.5

**Priority**: HIGH — published Sharpe 2.43 is the highest of any tested methodology


### Factor Momentum — Multiple Formation Periods (Applied Economics Letters 2025)

**Source**: Applied Economics Letters, Vol. 0 (2025) — "Cross-sectional factor momentum: evidence from multiple formation periods"

**Key finding**: Recent-past (1–3m) and intermediate-past (4–12m) formation horizons both produce significant, robust cross-sectional momentum returns post-publication. The standard 12-1m Carhart momentum is NOT the only valid horizon — multiple windows capture different aspects of the momentum phenomenon.

**Why this matters for H198/H215**:

Our confirmed strategies use:
- H198: 6-1m momentum (skip last 1 month, 6-month formation) — OOS Sharpe 1.174
- H215: alpha101 monthly mean (1-month lag) — OOS Sharpe 1.321
- H215+H198 blend: OOS Sharpe 1.397

The paper suggests: **the formation period is a variable, not a constant**. Market regimes may favor different windows:
- High-volatility periods: shorter windows (1–3m) capture momentum better
- Trending/low-vol periods: longer windows (6–12m) dominate

**Hypotheses queued**:

**H217** — CONFIRMED (2026-05-24): median alpha101 aggregation. OOS Sharpe 1.559 — best confirmed result in the alpha101 family. Median outperforms mean (H215 OOS 1.321) by reducing impact of outlier trading days.

**H218** — NOT CONFIRMED (2026-05-24): alpha101 + momentum blend (H217 × H198). Corr(H217, H198) OOS = 0.656; blend Sharpe 1.559 = no improvement over H217 standalone. Strategies select overlapping names (TSLA/NVDA dominate both alpha101 and 6m momentum in this bull market period).

**Multi-window momentum scan (originally sketched as H218, now reassigned ≥H223)**: Test 3-1m, 6-1m, 9-3m, 12-1m formation windows — momentum family sensitivity scan. Blend top-2 windows (lowest correlation, highest individual Sharpe). Note: H218 number was used for the alpha101+momentum blend above; this idea should use H223 or later.

**Implementation sketch** (adapts run_h213.py template):
```python
windows = [(3, 1), (6, 1), (9, 3), (12, 1)]  # (formation_months, skip_months)
for form, skip in windows:
    mom = close_monthly.pct_change(form).shift(skip)  # skip most recent 'skip' months
    # ... standard cross-sectional rank + long top-6 ...
    oos_sharpe[f'{form}-{skip}m'] = eval_period(rets, ...)
```

**Post-publication validation note**: The paper explicitly tested for data mining: these effects hold in global markets in the post-publication period. Lower concern about IS/OOS degradation vs. other factor families.
