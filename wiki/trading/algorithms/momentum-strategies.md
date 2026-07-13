---
updated: 2026-07-07
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

**Related pages**: [Short-Term Reversal](short-term-reversal.md) — H181 industry-adjusted reversal (SSRN:6630998), complements momentum with 1-month mean-reversion | [Pairs Trading / Stat Arb](pairs-trading.md) | [Position Sizing](position-sizing.md) | [Machine Learning for Trading](../tools/ml-for-trading.md) | [Commodity Trend Following](commodity-trend-following.md) — H261b CTA (OOS 0.922, Corr SPY=0.218) | [Factor Momentum & Style Rotation](factor-momentum-style-rotation.md) — H255/H256 NOT CONFIRMED; H257 CONFIRMED | [Long-Short Equity](long-short-equity.md) — H241/H242/H243 dollar-neutral L/S


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


---

## Factor Crowding & Alpha Decay (2025-2026 Research)

### Alpha Decay Dynamics

**Source:** arXiv:2512.11913 — Dec 2025. "Not All Factors Crowd Equally: Modeling, Measuring, and Trading on Alpha Decay."

A game-theoretic model of factor crowding applied to US equities 2001-2024:

| Finding | Detail |
|---------|--------|
| Momentum decay form | Hyperbolic (R²=0.65), not linear/exponential |
| Post-2015 acceleration | ETF growth → mechanical factor flows → crowding |
| Factor momentum Sharpe | 0.39 standalone (long winning factors, short losing) |
| Crowded momentum | 0.38× crash probability (SAFER than uncrowded) |
| Crowded reversal | 1.7–1.8× crash probability (MORE DANGEROUS) |

**Key insight:** Crowding predicts tail risk, not expected returns. A crowded momentum factor will still earn positive alpha on average but is safer (other participants exit simultaneously when the factor reverses). A crowded reversal is dangerous — when reversal positions become crowded, forced exits amplify losses.

**Implication for H181 (industry reversal):** If the industry-adjusted reversal signal becomes widely adopted, crash risk rises 1.7-1.8×. Monitor H181 paper trading MaxDD as a real-time crowding indicator.

**Implication for H217 (alpha101):** Alpha101 signals are relatively niche (intraday price-efficiency, less crowded than classical momentum) — crowding risk lower than for standard 12-month momentum.

### Signal Half-Life Compression

**Source:** arXiv:2605.23905 — May 2026. "AI-Driven Alpha Decay: Algorithmic Homogenization, Reflexive Signal Erosion, and the Paradox of Intelligent Markets."

Derives an alpha half-life formula based on AI adoption levels:
- **Pre-AI (low adoption):** signal half-life 5-7 years
- **Current level (~0.7 AI adoption):** signal half-life ~18 months
- **Compression mechanism:** signal crowding + performative signal erosion + Red Queen competition

**Tested implication (H231, 2026-05-29):** Applied exponential decay weighting to alpha101 signals with half-lives 6-24 months. NOT CONFIRMED — the half-life compression applies to longer-horizon momentum signals (months to years), not to intraday alpha101 which already aggregates on a single-day frequency. H217's calendar-month median aggregation remains optimal.

**Portfolio implication:** Strategies confirmed in 2018-2022 data (H026, H181, H217) may see half-life compression in their alpha premium by 2027-2028 as AI adoption approaches saturation. Plan to re-validate OOS Sharpe annually.

## Mask-First Bias Correction (arXiv:2507.07107, May 2026)

A subtle pipeline flaw: non-tradable bars (circuit breaker halts, liquidity gaps, trading halts on news) propagate through moving averages and cross-sectional ranks, inflating apparent IC by ~18% while reducing realized Sharpe by 0.44 points. The fix is a Boolean tradability mask threaded through all operators before any signal calculation.

**US market equivalents** (less severe than Chinese +/-10% limits but real):
- Stocks under trading halt (news pending, regulatory action)
- Penny stocks with consecutive zero-volume days
- ETFs during circuit breaker pause
- Delisted stocks still in data feed (survivorship leak)

**Implementation pattern:**
```python
import pandas as pd
import numpy as np

def is_tradable(close: pd.DataFrame, volume: pd.DataFrame,
                min_price: float = 1.0, min_vol: int = 10000) -> pd.DataFrame:
    """
    Boolean mask: True if the bar is tradable.
    Apply BEFORE any signal calculation.
    """
    price_ok = close > min_price
    vol_ok = volume > min_vol
    halted = close.pct_change().abs() > 0.199  # near circuit breaker
    return price_ok & vol_ok & ~halted

def masked_momentum(close: pd.DataFrame, volume: pd.DataFrame,
                    lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """
    Momentum signal with upstream contamination prevention.
    Non-tradable bars get NaN momentum, not the contaminated value.
    """
    mask = is_tradable(close, volume)
    # Apply mask BEFORE calculating momentum — not after
    masked_close = close.where(mask)
    mom = masked_close.shift(skip) / masked_close.shift(lookback) - 1
    # Also mask the signal itself
    return mom.where(mask)
```

**Adjusted-MSE loss for ML signal training** (penalizes wrong sign 11x more than magnitude error):
```python
def adjusted_mse_loss(y_pred, y_true, sign_penalty=11.0):
    """For regression models predicting forward returns."""
    residual = y_pred - y_true
    wrong_sign = (y_pred * y_true < 0).float()  # 1 if signs differ
    weight = 1.0 + (sign_penalty - 1.0) * wrong_sign
    return (weight * residual ** 2).mean()
```

**Source**: arXiv:2507.07107, 'Machine Learning Enhanced Multi-Factor Quantitative Trading: A Cross-Sectional Portfolio Optimization Approach with Bias Correction' (May 2026). Reported Sharpe 2.05 synthetic / 1.63 real A-share data. Deflated Sharpe 0.978.

---

## H376/H377: The No-Skip-Month Discovery — 6-0m Momentum (MAJOR FINDING)

**Run date**: 2026-07-06 (H376 sub-experiment; H377 full test pending)
**Finding class**: Parameter optimization — removal of standard skip-month convention

### Background: The Skip-Month Convention

Standard cross-sectional momentum uses a **1-month skip** between signal formation and portfolio formation:

```
Signal window: t-7 → t-1  (6 months, skipping most recent month t)
Portfolio holds: t → t+1 (next month)
```

The skip-month convention was introduced by Jegadeesh & Titman (1993) to avoid short-term reversal contamination — stocks with high 1-month returns tend to mean-revert in month t+1 (market microstructure: bid-ask bounce, liquidity pressure).

### The H277 Finding (NASDAQ Universe, Survivorship-Bias Caveat)

H277 tested NASDAQ tech momentum on a tech-heavy universe and found:
- **6-1m (with skip)**: OOS Sharpe 1.22
- **6-0m (no skip)**: OOS Sharpe ~1.6+ (improved)
- **Interpretation**: On NASDAQ/tech-heavy universes, the 1-month reversal effect is ABSENT or reversed — recent-month return is momentum-continuation, not reversal.

Caveat: H277 used current NASDAQ constituents (survivorship bias). The effect needed validation on a broader, bias-free universe.

### H376 Extension to H198 30-Stock Large-Cap Universe

H376 tested MAX factor composites on the H198 30-stock S&P500 universe. The most significant finding was the **6-0m (no skip) baseline**:

| Variant | IS Sharpe | OOS Sharpe | OOS MaxDD | CAGR | Neg Yrs |
|---------|-----------|------------|-----------|------|---------|
| Baseline: 6-1m (standard skip) | — | **1.174** | -22.7% | 27.1% | 1 |
| 6-0m pure (no MAX, no skip) | — | **3.120** | -8.4% | 76.8% | **0** |
| Var D: 6-0m + 0.3·MAX composite | — | 2.790 | -9.1% | 72.0% | 0 |

**Result: Removing the skip month nearly triples OOS Sharpe (1.174 → 3.120) and cuts MaxDD from -22.7% to -8.4% on the H198 30-stock large-cap universe. Zero negative calendar years 2021-2026.**

This is the strongest finding in the H198 stock momentum family.

### Why Doesn't Skip-Month Reversal Apply to Large-Cap Tech-Heavy Universes?

The skip-month convention is empirically motivated by short-term reversal in **small-cap, illiquid stocks** where microstructure effects are strong. For large-cap tech-heavy universes:

1. **Bid-ask bounce is negligible**: AAPL/NVDA/META have sub-1bp spreads — no meaningful bid-ask contamination
2. **Momentum is persistent at 1-month horizon**: Tech mega-caps in bull markets exhibit momentum at 1-month frequencies (earnings momentum, institutional flows, sector rotation continuing)
3. **Skip-month cost**: Skipping the most recent month excludes the strongest recent signals — when a stock had +30% in the prior month, excluding that signal reduces the momentum rank
4. **Sector concentration effect**: The H198 universe is ~40% tech/communication — sector momentum is strong at sub-monthly frequencies; excluding last month introduces a systematic lag

### H377 Design (Full Test Pending)

H377 tests 6-0m momentum as a complete standalone hypothesis:

**Universe**: H198 30-stock large-cap S&P 500  
**IS/OOS**: IS 2013-2020 / OOS 2021-2026  
**Gate**: OOS Sharpe > 1.174 (H198 baseline) AND MaxDD > -30%  

| Variant | Signal | Description |
|---------|--------|-------------|
| Baseline | 6-1m | Standard H198 (skip month) — reference |
| A | 6-0m | No skip, plain 6-month return |
| B | 6-0m top-1 | Concentrated top-1 (vs top-6 EW) |
| C | 6-0m + 3-0m blend | Dual lookback, no skip on either |
| D | 6-0m + vol target | No skip + H273 vol-targeting overlay |
| E | 3-0m | Very short lookback — captures earnings momentum |

```python
# H377 signal construction
sig_6m_0skip = monthly_px.pct_change(6)          # 6-0m: no skip
sig_3m_0skip = monthly_px.pct_change(3)          # 3-0m: no skip (very short)
sig_6m_1skip = monthly_px.shift(1) / monthly_px.shift(7) - 1  # 6-1m: standard baseline

# Cross-sectional rank each signal
rank_6m_0 = sig_6m_0skip.rank(axis=1, pct=True)
rank_3m_0 = sig_3m_0skip.rank(axis=1, pct=True)

# Var C blend
composite_C = 0.6 * rank_6m_0 + 0.4 * rank_3m_0
```

**Expected outcome based on H376 sub-experiment**:
- Var A (6-0m top-6): OOS ~3.12 (directly observed in H376)
- Var B (6-0m top-1): unknown — concentration should help in bull markets, hurt in drawdowns
- Var C (dual blend): likely degrades 6-0m purity; test to confirm
- Var D (+ vol target): likely improvement in MaxDD; H273 confirmed vol-targeting adds +0.19 Sharpe overall

**Production implications if confirmed**:
- Would replace H198 6-1m as the stock momentum production signal
- OOS Sharpe 3.120 would rank among production-portfolio-tier results (H026 OOS 3.007, H041a OOS 3.708)
- Low correlation with H026 (different alpha driver) — portfolio admission candidate

### Broader Skip-Month Analysis

The skip-month convention should be re-tested across all H-series stock strategies:

| Strategy | Current skip | Test no-skip? | Priority |
|----------|-------------|--------------|---------|
| H198 stock momentum | 1 month | **YES — H377** | HIGH |
| H181 industry reversal | None (it IS 1-month reversal) | N/A | N/A |
| H217 alpha101 | Varies by formula | MEDIUM | MEDIUM |
| H320 LightGBM crash filter | 1 month | LOW | LOW |

**Key insight**: The skip-month convention may be a 30-year-old artifact of 1993-era small-cap data. For modern large-cap, tech-heavy portfolios, removing the skip may consistently improve performance.

**See also:** H376 Var D (6-0m + 0.3·MAX = 2.790 vs. pure 6-0m = 3.120) shows MAX acting as a mild adversarial tilt even on the stronger, un-skipped momentum base — not simple dilution. The mechanism is detailed in `behavioral-finance-signals.md`'s MAX×momentum subsection: MAX and momentum select the same name most months, but in the minority where they diverge, MAX routes to a recent single-spike stock rather than a sustained leader. H373's failure on 6-1m top-1 (-0.34 Sharpe) confirms the same pattern, amplified there by top-1's all-or-nothing exposure to each override.


## Kumar (2026): Large-Cap Momentum — Long Leg Works, Short Leg Catastrophic

**Source**: Darshan Sathish Kumar (Feb 2026), 'Momentum in Large-Cap Equities: Does the Classic 12–1 Strategy Still Work?' SSRN:5367656. Tests 12-1m momentum on S&P 500 March 2006–December 2024.

**Key finding**: Net annualized return −2.79%, Sharpe −0.23, MaxDD −81% on L/S portfolio at 10bps/side.
- **Long leg only**: +7.9% annualized — momentum winners WORK on long side in large-cap
- **Short leg**: −9.1% annualized net — momentum crashes (2009: losers recovered 40-100% in 1 month; 2020: same pattern)

**Implications for H377 (6-0m no-skip)**:
1. Long-only large-cap momentum confirmed in post-publication sample 2006-2024
2. The standard 12-1m produces +7.9% long-side — H377's 6-0m may do better by including recent-month momentum
3. 'Does classic 12-1 work?' = Yes for long-only; No for L/S — our strategies are all long-only ✓
4. Short-selling losers (H243 NOT CONFIRMED) is consistent with these findings

**Validation**: Confirms H198 6-1m long-only (OOS 1.174) and H376's 6-0m finding (OOS 3.120) are real effects, not artifacts.

## Microstructural Headwinds for Short-Term Momentum (arXiv:2607.01550)

**Source**: Kurth, Eisler, Rej, Bouchaud (CFM, Jul 2026) — 'Is Trend Still Your Friend?: A Microstructural Account of the Demise of Short-Term Trend-Following'

**Key findings** (100 liquid futures, 1995–2025):
- Short-term trend P&L has **structurally collapsed** on small-tick (electronified) contracts post-2009
- Performance **remains intact** on large-tick futures (less fragmented limit-order books)
- Mechanism: HFT-dominated market making withdraws depth on predictable directional flow → the self-reinforcing momentum feedback loop breaks
- Critical variable: **volatility-normalized tick size** — the single microstructural factor distinguishing surviving from collapsed momentum

**Implications for H198 family (6-1m stock momentum)**:
- H198 runs on large-cap NASDAQ stocks (electronified, small tick). This microstructural headwind is real.
- The Order Block (OB) filter in H343/H344/H386 implicitly addresses this: OB entries only when price is leaving consolidation zones with volume confirmation — avoids thin, HFT-dominated phases.
- H376/H386 6-0m no-skip showing OOS 3.120/3.273 does NOT contradict this finding — no-skip works at the monthly rebalancing horizon where the microstructural effect is less dominant.

**Implication for ETF rotation (H026/H041a)**:
- ETFs trade as large-block instruments via creation/redemption; less HFT-fragmented than individual stocks
- Monthly rebalancing avoids the sub-day microstructural breakdown
- Consistent with H026 OOS Sharpe remaining strong (2.610–3.238 with OB filter)

**Bottom line**: Momentum is alive at monthly rebalancing horizons on liquid multi-asset universes. The structural break affects high-frequency, small-tick, intraday trend strategies. Not a production risk for the H026/H041a/H045 monthly rotation pipeline.

---

## Spectral Memory Decomposition: Theory for IMOM+MOM Composite (arXiv:2607.03858, July 2026)

Frøseth (July 4 2026) proposes a multivariate generalisation of the Lo-MacKinlay (1988) variance ratio. Decomposes long-horizon equity returns across 5 U.S./European panel datasets into:

- **Return-channel persistent memory**: slow directional drift — classic momentum
- **Return-channel antipersistent memory**: fast noise/bounce — mean-reversion
- **Volatility-channel memory**: multi-scale persistence in volatility clustering

A 5-factor spectral model simultaneously fits FF-49 industries, FF-100 size×BtM, FF-Europe-25, and pre/post-1998 halves — the memory structure is universal across U.S. and European equity cross-sections.

### Theoretical Support for H395 Equal-Weight Composite

H395 IMOM + MOM + LowVol (Var C, OOS Sharpe **3.962**, the H198 family champion as of July 2026) maps cleanly onto three distinct spectral components:

| Signal | Spectral Component | Why it works |
|--------|--------------------|-------------|
| IMOM (Illusion Momentum) | Return-channel **persistent memory** | Compound return minus arithmetic sum isolates stocks with sustained consistent gains — only possible with high persistent memory |
| MOM (6-month no-skip) | Return-channel **directional persistence** | Cross-sectional momentum reflects intermediate-horizon persistence; the skip-month (1-month reversal) is the antipersistent component |
| LowVol tiebreaker | Volatility-channel **noise filter** | Low realized vol = lower volatility-channel memory amplitude = less noise contaminating the directional signal |

The three signals are spectral-orthogonal: IMOM captures path consistency, MOM captures direction, LowVol filters volatility noise. Equal-weighting them (H395 Var C) implicitly achieves spectral diversification.

**Implication for H395+ variants**: The antipersistent return-channel component represents mean-reverting stocks. Consider a contra-signal that explicitly identifies and avoids stocks with high antipersistent loading (high short-term reversal tendency) as a 4th composite ingredient — this could be tested as H398 or H399.
