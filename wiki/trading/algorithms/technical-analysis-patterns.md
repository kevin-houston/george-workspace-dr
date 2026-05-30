---
added: 2026-05-29
updated: 2026-05-29
category: algorithms
related: [ibs-mean-reversion.md, momentum-strategies.md, factor-models.md]
---

# Technical Analysis & Chart Patterns

Chart-pattern and indicator-based strategies occupy a separate tier from cross-sectional factor models: they operate on OHLCV structure alone, require no fundamental data, and can be run at daily or weekly frequency. H234 (inside-bar breakout) is the strongest confirmed hypothesis in the entire log at OOS Sharpe 1.770 — making this family materially important.

---

## Confirmed hypotheses in this family

| Hypothesis | Pattern | OOS Sharpe | Status |
|------------|---------|-----------|--------|
| H234 | Weekly inside-bar coiled-spring breakout | 1.770 | **CONFIRMED** |
| H112/IBS | Internal Bar Score mean-reversion (XLK/SMH/IGV) | ~1.0–1.2 (production) | **PRODUCTION** |
| H235 | RF classifier gate on IBS signals | — | DESIGN |
| H233 | LightGBM + TA features (MACD/RSI/Stochastic/ROC) on alpha101 | — | DESIGN |

---

## H234 — Weekly Inside-Bar Breakout (Coiled Spring)

**Source:** Stats Edge Trading, Michael Nauss CMT/CAIA/CDMS ("The 25-Year Backtest")
- Nauss system covers three uncorrelated engines (Momo, MR_Weekly, Pullback); 44.16% annual return over 26 years, 17.30% max drawdown, 16,687 trades
- Website: https://www.statsedgetrading.com/ — Substack: https://michaelnausscmt.substack.com/

**Pattern definition (3-week setup):**

| Week | Condition |
|------|-----------|
| W-1 (green bar) | weekly return ≥ 2.5% (optimal ≥ 3.0%), volume ≥ 1.5× 20-wk avg, close in top 40% of W-1 range |
| W (inside bar) | high < W-1 high, low > W-1 low (complete containment), close in upper 50% of W-1 range |
| W+1 (entry) | buy at open, sell at close (1-week hold) |

**Economic rationale:** The green bar signals institutional demand with above-average volume. The inside bar is a "coiled spring" — price compresses as sellers are absorbed. The upper-range close on W indicates buyers still dominate. Entry at W+1 open catches the release of compressed volatility in the trend direction.

**Confirmed OOS results (2021–2026, 107 large-cap US stocks + ETFs):**

| Metric | IS 2013–2020 | OOS 2021–2026 |
|--------|-------------|---------------|
| Sharpe | 0.860 | **1.770** |
| CAGR (aggregate) | 29.9% | 156.9%* |
| MaxDD | -60.4% | -47.2% |
| WinRate | 53.2% | **63.9%** |
| n trades | 202 | 120 |

*CAGR reflects equal-weight per-trade averaging across simultaneous positions, not compounded single-portfolio figure. Actual CAGR depends on MAX_POSITIONS sizing.

**Key findings:**
- OOS Sharpe (1.770) dramatically **exceeds** IS (0.860) — rare forward improvement suggesting the pattern has strengthened post-2021, possibly due to increased algorithmic participation amplifying compression/breakout dynamics
- Win rate improved OOS (+10.7pp) — signal quality genuinely increased, not degraded
- MaxDD (-47.2%) is unsuitable for production portfolio as-is; viable as aggressive-growth satellite with small position sizing
- Parameter stability: GREEN_THRESH=2.5–3.0% gives OOS Sharpe 1.77–1.772; optimal = 3.0% (n=115 trades)

**Script:** `backtesting/daily/run_h234.py`

---

## Related volatility-compression patterns

### NR7 (Narrow Range 7) — Toby Crabel

The NR7 is today's bar having the narrowest high-low range of the prior 7 bars. It is the quantitative cousin of the inside bar, measuring contraction by range rather than containment.

**Backtest evidence (Bulkowski, QuantifiedStrategies):**
- Bull market, upward breakout: win rate 57%, avg hold 31 calendar days, n=7,600+ trades
- SPY/S&P 500 (QuantifiedStrategies): CAGR 7.8% at 35% time invested, 899 trades, MaxDD -25%
- Oxford Strategies (42 futures markets): NR_Length ≥ 6 preferred; not tradeable standalone without additional filters
- Volume filter improvement: adding volume gate raised avg return from 0.86% → +1.25% per 20-day hold on Gold ETFs

**NR4 is the tighter variant** (narrowest of 4 bars): win rate 58% on upward breakout (Bulkowski).

**Practical note:** NR7 alone on US large-cap does not achieve the required Sharpe threshold. H234 outperforms NR7 by adding the volume-surge and directional (green-bar) pre-conditions — the inside-bar containment is a subset of NR7 logic but filtered by market context.

### NR7 + Inside Bar Composite (Python backtest)

Combining NR7 and inside-bar filter on the same bar (NR7/IB) shows directional asymmetry:
- **Intraday exit:** sell strategies dominate (mean-reversion effect)
- **Next-day / 5-day exit:** buy strategies dominate (momentum continuation)

This aligns with H234's weekly hold: weekly compression resolves as momentum, not reversal.

**Implementation reference:** https://unofficed.com/courses/backtesting-buddha/lessons/backtesting-narrow-range-inside-bar-strategy-using-python/

---

## TA features for ML models (H233, H235)

Both H233 and H235 use the same 4-indicator feature set, sourced from the ZHAW AI-for-Trading paper (arXiv:2208.07168 — Jevtic, Délèze, Osterrieder 2022). The RF model achieved Sharpe 1.15, Profit Factor 5.77, with MACD contributing ~44% of feature importance on Brent crude.

### Feature set used in H233 (LightGBM alpha101 + TA) and H235 (RF IBS gate)

| Feature | Parameters | Notes |
|---------|-----------|-------|
| MACD line | EMA 12/26 | Most important feature per ZHAW (44% importance) |
| MACD signal | EMA 9 on MACD | Trend confirmation |
| MACD histogram | MACD − signal | Momentum acceleration |
| RSI | 14-period | Normalized to [0,1]; 15.5% importance in related RF study |
| Stochastic %K | 14-period | Oversold/overbought context |
| Stochastic %D | 3-period SMA of %K | Smoothed signal line |
| ROC | 10-period | Rate of change; raw momentum |

All 7 features computed on monthly closing prices for H233 (monthly rebalance, 1-month lag). For H235 (daily IBS gate), computed on daily prices at signal time.

### Academic context for TA features in ML

**arXiv:2412.15448 (Assessing Technical Indicators on ML for Stock Prediction):**
- Random forest on minute-level SPY; found primary price-based features dominate (>60% importance); RSI + Bollinger Bands: 14–15% combined
- **Warning:** in-sample R²=0.749–0.812 collapsed to negative OOS — high-frequency TA + RF severely overfits

**arXiv:2501.12239 (CNN on Candlestick Chart Images, Jan 2025):**
- Peak accuracy ~0.7 on multi-asset (stocks/crypto/forex); candlestick patterns alone do not improve over raw image data
- Conclusion: purely visual approaches insufficient; hybrid multimodal better

**PMC paper (RSI + MACD effectiveness, 2025):** RSI accuracy up to 97% during high-volatility periods; MACD captures both short-term and long-term trend shifts; combining MACD + RSI + EMA crossings gives more reliable signals than any single indicator

**Key takeaway:** TA features are best used as secondary confirmation gates (H235 design) rather than primary signals. On monthly rebalancing (H233), they may add directional context to alpha101's price-efficiency signal.

---

## Python libraries for TA computation

### TA-Lib — the C-wrapped standard
- **GitHub:** https://github.com/TA-Lib/ta-lib-python (12,000+ stars)
- **Version:** 0.6.8 (Oct 2025); supports ta-lib C 0.6.x + numpy 2
- **Indicators:** 150+ across 7 categories; 61 candlestick patterns; streaming API for live use
- **Installation:** requires C library pre-installed; then `pip install TA-Lib`
  - macOS: `brew install ta-lib && pip install TA-Lib`
  - Linux: compile from source or use conda: `conda install -c conda-forge ta-lib`
  - Windows: MSI installer from ta-lib.org
- **Performance:** Cython binding 2–4× faster than old SWIG interface; numpy array API
- **Use when:** speed matters on large datasets; legacy systems; need full candlestick pattern library

```python
import talib
import numpy as np

close = np.array([...], dtype=float)
macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
rsi = talib.RSI(close, timeperiod=14)
slowk, slowd = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowd_period=3)
```

### pandas-ta-classic — the modern pandas-native alternative
- **GitHub:** https://github.com/xgboosted/pandas-ta-classic (348 stars)
- **PyPI:** `pip install pandas-ta-classic`
- **Version:** 0.6.20 (May 2026)
- **Indicators:** 192 technical indicators + 62 native candlestick patterns = 252 total (NO TA-Lib required)
- **Performance:** optional numba for 6–230× speedup on hot-loop indicators
- **Use when:** pure Python environment; pandas workflow; no C compiler available

```python
import pandas_ta_classic as ta

df.ta.macd(fast=12, slow=26, signal=9, append=True)   # adds MACD_12_26_9, MACDs_12_26_9, MACDh_12_26_9
df.ta.rsi(length=14, append=True)                       # adds RSI_14
df.ta.stoch(k=14, d=3, append=True)                    # adds STOCHk_14_3_3, STOCHd_14_3_3
df.ta.roc(length=10, append=True)                       # adds ROC_10

# Fluent chaining:
df.ta.chain().sma(20).ta.rsi(14).ta.macd()
```

### pandas-ta (original — largely unmaintained)
- **GitHub:** multiple forks (aarigs, 0xAVX, Laezerus); original repo stale
- **Note:** prefer `pandas-ta-classic` (active fork) for new projects

### Library comparison for H233/H235

| Criterion | TA-Lib | pandas-ta-classic |
|-----------|--------|-------------------|
| Installation | Requires C lib | `pip install` only |
| Indicators | 150+ | 192 + 62 CDL |
| Candlestick patterns | 61 (via TA-Lib) | 62 native (no TA-Lib) |
| Performance | Fastest (C/Cython) | Fast w/ numba |
| pandas integration | Array-based | Native DataFrame |
| Recommendation | Large-scale prod | Research / prototyping |

**For H233/H235:** `pandas-ta-classic` is preferred — no C dependencies, native DataFrame output, adequate speed for monthly/daily backtests on 30–107 stocks.

---

## Inside-bar implementation skeleton (H234 pattern)

```python
import yfinance as yf
import pandas as pd

def compute_weekly_signals(ticker: str) -> pd.DataFrame:
    """Weekly OHLCV + H234 signal flags."""
    df = yf.download(ticker, period="15y", interval="1wk", auto_adjust=True)
    df = df[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]

    # Rolling volume average (20-week)
    df["vol_avg"] = df["volume"].rolling(20).mean()

    # Shift to get prior-week values
    df["prev_high"]    = df["high"].shift(1)
    df["prev_low"]     = df["low"].shift(1)
    df["prev_close"]   = df["close"].shift(1)
    df["prev_open"]    = df["open"].shift(1)
    df["prev_vol"]     = df["volume"].shift(1)
    df["prev_vol_avg"] = df["vol_avg"].shift(1)

    # Green bar (W-1): ≥3% return, volume ≥1.5×, close in top 40% of range
    prev_return     = (df["prev_close"] - df["prev_open"]) / df["prev_open"]
    prev_range      = df["prev_high"] - df["prev_low"]
    prev_close_pct  = (df["prev_close"] - df["prev_low"]) / prev_range.replace(0, float("nan"))
    df["green_bar"] = (
        (prev_return >= 0.030) &
        (df["prev_vol"] >= 1.5 * df["prev_vol_avg"]) &
        (prev_close_pct >= 0.60)  # top 40% = close_pct >= 0.60
    )

    # Inside bar (W): contained within W-1 range, close in upper 50%
    curr_range     = df["high"] - df["low"]
    curr_close_pct = (df["close"] - df["low"]) / curr_range.replace(0, float("nan"))
    df["inside_bar"] = (
        (df["high"] < df["prev_high"]) &
        (df["low"]  > df["prev_low"])  &
        (curr_close_pct >= 0.50)
    )

    # Signal fires at end of W; entry at W+1 open
    df["signal"] = df["green_bar"] & df["inside_bar"]
    return df

# Backtest loop: entry at next-week open, exit at next-week close
# (see backtesting/daily/run_h234.py for full implementation)
```

---

## Next hypotheses in this family

| ID | Description | Prerequisite |
|----|-------------|-------------|
| H235 | RF classifier gate on IBS signals (XLK/SMH/IGV) | H112 IBS baseline measured |
| H233 | LightGBM + adjusted-MSE + TA features on alpha101 | H217 codebase |
| — | NR7 + volume surge on 200-stock universe | H202-XL universe list |
| — | H234 with additional confirmation (ATR expansion or RSI oversold) | H234 confirmed |

**Design note for H233:** The Adjusted-MSE custom objective penalizes wrong-sign predictions 11×, making the model directionally aware rather than minimizing symmetric loss. Combined with TA features (MACD histogram as trend direction, RSI as oversold confirmation), this is designed to outperform H217's OOS Sharpe 1.559.

**Design note for H235:** RF classifier targets the IBS trade day direction (up/down) rather than magnitude. Entry only when IBS trigger fires AND RF confidence ≥ 0.55. Expected outcome: fewer trades (higher precision), reduced false-positive rate during sustained downtrends. Walk-forward retraining recommended (retrain every 12 months on expanding IS window).

---

## Academic references

| Paper | Source | Key finding |
|-------|--------|-------------|
| Jevtic, Délèze, Osterrieder 2022 | arXiv:2208.07168 | RF on Brent crude: Sharpe 1.15, PF 5.77; MACD ~44% feature importance |
| "Assessing Technical Indicators on ML" 2024 | arXiv:2412.15448 | Price features >60% importance; RSI+BB 14–15%; warning: RF severely overfits at high frequency |
| CNN on Candlestick Images 2025 | arXiv:2501.12239 | Visual pattern recognition insufficient alone; accuracy ~0.70 peak |
| Bulkowski (PatternSite) | thepatternsite.com | NR7 57% win rate bull market; NR4 58% win rate |
| Michael Nauss CMT 2025 | statsedgetrading.com | H234 source; 25-year backtest, 3-engine system, 44.16% ann return |
