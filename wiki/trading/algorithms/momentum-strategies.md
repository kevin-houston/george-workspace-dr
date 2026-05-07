---
updated: 2026-04-30
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
