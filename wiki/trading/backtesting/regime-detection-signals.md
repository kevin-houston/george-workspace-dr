---
created: 2026-06-04
updated: 2026-06-04
status: active
relevance: H249 (regime-conditional production weights), H165 (VIX gate), all production strategies
see_also:
  - wiki/trading/algorithms/regime-detection.md  # methods (HMM, SJM, Markov)
  - wiki/trading/backtesting/design-principles.md  # IS/OOS framework
---

# Regime Detection Signals — Practical Data Guide

This page covers the *data pipeline* side of regime signals: how to fetch them
from free sources, construct them without look-ahead, and wire them into a
backtest. For the statistical methods (HMM, Markov Switching, SJM) see
`algorithms/regime-detection.md`.

---

## The Three Production Signals

The confirmed and queued regime overlays in our pipeline use three macro signals:

| Signal | Source | FRED series | Free? |
|--------|--------|-------------|-------|
| SPY 200-day MA spread | yfinance `SPY` | — | Yes |
| VIX level | yfinance `^VIX` or FRED `VIXCLS` | VIXCLS | Yes |
| 10Y-2Y yield spread | FRED | `T10Y2Y` | Yes |
| 10Y yield direction | FRED | `DGS10` | Yes |
| 10Y-3M spread (inversion) | FRED | `T10Y3M` | Yes |

All are available with daily resolution going back to the 1990s. The FRED API
key is in `$FRED_API_KEY` (confirmed in pipeline).

---

## 1. SPY 200-Day Moving Average

### Construct (no look-ahead)

```python
import yfinance as yf
import pandas as pd

def spy_regime(start: str = "2000-01-01") -> pd.Series:
    """
    Returns daily bull/bear boolean series.
    True = bull (SPY above 200-day MA).
    Uses previous day's price — no look-ahead.
    """
    spy = yf.download("SPY", start=start, auto_adjust=True, progress=False)["Close"]
    ma200 = spy.rolling(200, min_periods=200).mean()
    # Shift by 1: regime on day t is based on close of day t-1
    regime = (spy > ma200).shift(1)
    return regime.rename("spy_bull")
```

**Critical**: always `.shift(1)` before using in a trade simulation. Day t's
signal is constructed from closes up to and including day t-1. Forgetting the
shift is one of the most common sources of look-ahead bias in daily strategies.

**Regime coverage** (H205 analysis, 2021–2026):
- Bull (SPY > 200MA): ~80% of trading days
- Bear (SPY ≤ 200MA): ~20% of trading days (274 of 1,336 TOM days)

**Why 200-day**: The 200-day SMA is the most widely cited institutional bull/bear
dividing line. Research shows it remains significant after accounting for
transaction costs at monthly rebalance frequency. Shorter windows (50, 100)
produce too many false signals.

---

## 2. VIX Threshold Signal

### CBOE VIX via yfinance

```python
import yfinance as yf
import pandas as pd

def vix_regime(threshold: float = 25.0, start: str = "2000-01-01") -> pd.Series:
    """
    Returns True = calm (VIX below threshold).
    Shift by 1 to avoid look-ahead.
    """
    vix = yf.download("^VIX", start=start, auto_adjust=True, progress=False)["Close"]
    regime = (vix < threshold).shift(1)
    return regime.rename(f"vix_calm_{threshold}")
```

### VIX via FRED (more reliable for long history)

```python
import requests
import pandas as pd
import os

def vix_from_fred(threshold: float = 25.0) -> pd.Series:
    """
    FRED VIXCLS series: daily CBOE VIX back to 1990-01-02.
    More complete than yfinance for pre-2010 data.
    """
    api_key = os.environ.get("FRED_API_KEY", "")
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=VIXCLS&api_key={api_key}&file_type=json"
    )
    r = requests.get(url, timeout=30)
    observations = r.json()["observations"]
    df = pd.DataFrame(observations)[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    vix = df["value"].dropna()
    vix.index = vix.index.tz_localize(None)
    # Forward-fill weekends; shift to avoid look-ahead
    vix = vix.reindex(pd.date_range(vix.index.min(), vix.index.max(), freq="B")).ffill()
    regime = (vix < threshold).shift(1)
    return regime.rename(f"vix_calm_fred_{threshold}")
```

### Threshold selection (confirmed empirically, H165a)

| Threshold | Months forced to BIL vs pure TSMOM | OOS Sharpe improvement on H026 |
|-----------|-----------------------------------|-------------------------------|
| 12 | Too few (only 2020 COVID) | +0.08 |
| 15 | Few (misses 2022) | +0.15 |
| 20 | Moderate | +0.22 |
| **25** | **46 additional months** | **+0.429** |
| 30 | Too many | +0.31 |

**Confirmed**: VIX < 25 is the optimal threshold from H165a. Captures genuine stress
regimes (2008–2009, 2020 COVID, 2022 rate shock) without over-filtering choppy but
benign markets (2015, 2018 Q4).

---

## 3. FRED Yield Curve Signals

The yield curve provides forward-looking macro regime information not captured by
price-based signals. Three FRED series are relevant:

| Series | Description | Signal direction |
|--------|-------------|-----------------|
| `T10Y2Y` | 10-year minus 2-year spread | Negative = inversion = recession risk |
| `T10Y3M` | 10-year minus 3-month spread | Better recession predictor (NY Fed model) |
| `DGS10` | 10-year Treasury constant maturity | Level and direction of rates |

### Fetch all three

```python
import requests, os, pandas as pd

FRED_SERIES = {
    "T10Y2Y":  "10Y-2Y spread",
    "T10Y3M":  "10Y-3M spread",
    "DGS10":   "10Y yield",
    "DGS2":    "2Y yield",
}

def fetch_fred_series(series_id: str, start: str = "2000-01-01") -> pd.Series:
    api_key = os.environ.get("FRED_API_KEY", "")
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&observation_start={start}"
        f"&api_key={api_key}&file_type=json"
    )
    r = requests.get(url, timeout=30)
    obs = r.json()["observations"]
    df = pd.DataFrame(obs)[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    s = df["value"].dropna()
    s.index = s.index.tz_localize(None)
    return s

# Example usage
t10y2y = fetch_fred_series("T10Y2Y")   # negative = inverted
t10y3m = fetch_fred_series("T10Y3M")   # negative = inverted (NY Fed preferred)
dgs10  = fetch_fred_series("DGS10")    # absolute level
```

### Derived signals

```python
def yield_curve_signals(t10y2y: pd.Series, dgs10: pd.Series) -> pd.DataFrame:
    """
    Compute regime flags from yield curve.
    All signals shifted by 1 to avoid look-ahead.
    """
    signals = pd.DataFrame(index=t10y2y.index)

    # 1. Inversion signal (last 5-day avg to avoid day-of noise)
    signals["inverted"] = (t10y2y.rolling(5).mean() < 0).shift(1)

    # 2. Rate relief (10Y falling — 3-month rolling change < 0)
    signals["rate_falling"] = (dgs10.diff(63) < 0).shift(1)  # 63 trading days ≈ 3 months

    # 3. Rate spike (10Y rising >50bps in prior quarter — H249 rate-hike modifier)
    signals["rate_hike"] = (dgs10.diff(63) > 0.50).shift(1)

    # 4. Rate level regime (high rates = >4% historically challenging for growth)
    signals["high_rates"] = (dgs10 > 4.0).shift(1)

    return signals
```

### Yield curve interpretation for our strategies

| Condition | What it means | Strategy implications |
|-----------|--------------|----------------------|
| T10Y2Y < 0 (inverted) | Recession risk elevated; funded by short rates higher than long | Shift toward H045 bonds; reduce H041a growth |
| T10Y3M < -0.5 (deep inversion) | NY Fed recession probability > 40% | Maximize bond/defensive exposure |
| DGS10 rising >50bps/quarter | Rate shock regime | Hurt: TLT, low-vol, bond proxies. Favor: IBS tech ETFs (XLK), H041a with momentum filter |
| DGS10 falling | Rate relief | Benefit: TLT, H045, quality/growth. IBS less advantaged |
| DGS10 level < 2% | Low-rate regime | H045 bonds less attractive; H026/H041a growth-tilted |

---

## 4. Composite Regime Construction

### H249-style: four-state regime

```python
def build_composite_regime(
    spy_bull: pd.Series,
    vix_calm: pd.Series,
    vix_threshold_upper: float = 25.0,
    vix_threshold_mid: float = 20.0
) -> pd.Series:
    """
    Four states:
      0: bear_volatile  (SPY < 200MA, VIX >= 25)
      1: bear_calm      (SPY < 200MA, VIX < 25)
      2: bull_volatile  (SPY > 200MA, VIX 20-25)
      3: bull_calm      (SPY > 200MA, VIX < 20)
    """
    vix = yf.download("^VIX", auto_adjust=True, progress=False)["Close"]
    vix_mid = (vix < vix_threshold_mid).shift(1)
    vix_high = (vix >= vix_threshold_upper).shift(1)

    state = pd.Series("bull_calm", index=spy_bull.index)
    state[spy_bull & ~vix_mid]  = "bull_volatile"
    state[~spy_bull & ~vix_high] = "bear_calm"
    state[~spy_bull & vix_high] = "bear_volatile"
    return state
```

### Xiong (2026) continuous score approach (arXiv:2605.20636)

Rather than discrete bins, map raw signals to a continuous [−1, 1] score and
use a tanh to determine exposure tilt. This avoids cliff-edge regime transitions:

```python
import numpy as np

def continuous_regime_score(
    spy: pd.Series,    # SPY close
    vix: pd.Series,    # VIX close (FRED VIXCLS or ^VIX)
    dgs10: pd.Series,  # 10Y yield (FRED DGS10)
    spy_window: int = 200
) -> pd.Series:
    """
    Continuous macro regime score (Xiong 2026 style).
    Positive = growth-favorable. Negative = defensive.
    All inputs shift(1) applied below to prevent look-ahead.

    Components:
    1. Rate relief   = -dgs10.diff(63)  (falling rates → positive)
    2. SPY drawdown  = (spy / spy.rolling(252).max() - 1)  (< 0 means stressed)
    3. VIX stress    = (25 - vix) / 10   (negative when VIX > 25)
    """
    # Align all on trading dates
    common = spy.index.intersection(vix.index).intersection(dgs10.index)
    spy   = spy.reindex(common).ffill()
    vix   = vix.reindex(common).ffill()
    dgs10 = dgs10.reindex(common).ffill()

    # Rate relief signal (positive when rates falling)
    rate_relief = -dgs10.diff(63)

    # SPY drawdown depth (0 = at ATH, -1 = complete drawdown)
    spy_dd = spy / spy.rolling(252, min_periods=50).max() - 1

    # VIX stress relief (positive when calm)
    vix_relief = (25.0 - vix) / 10.0

    # Composite (equal weight) → tanh to bound [-1, 1]
    raw_score = (
        rate_relief.clip(-2, 2) / 2
        + spy_dd.clip(-1, 0) * 2    # amplify bear signal
        + vix_relief.clip(-3, 3) / 3
    ) / 3.0

    score = np.tanh(raw_score)

    # CRITICAL: shift by 1 before returning
    return score.shift(1).rename("regime_score")
```

**Interpretation**:
- `score > 0.3`: favor growth/momentum (increase H026/H041a weights by 5-10%)
- `score < -0.3`: favor defensive/bonds (increase H045 weights by 8-15%)
- `|score| < 0.3`: near static weights

---

## 5. Data Alignment and Look-Ahead Rules

### Calendar alignment

FRED series use business day calendar; yfinance uses trading calendar. The two
don't always align perfectly (holidays, data release timing). Best practice:

```python
def align_to_trading_calendar(fred_series: pd.Series, spy_index: pd.DatetimeIndex) -> pd.Series:
    """
    Reindex FRED series to trading calendar.
    Forward-fill up to 5 business days for weekends/holidays.
    """
    return fred_series.reindex(spy_index, method="ffill", limit=5)
```

### FRED release lag

Most FRED economic series have a 1-2 day publication lag. VIX and yields are
same-day data (published intraday). For backtesting:
- **VIX / yields**: `.shift(1)` is sufficient (published same day, available next open)
- **FRED macro indicators** (GDP, PCE, payrolls): add an additional 3–5 day lag
- **Yield spreads (T10Y2Y, T10Y3M)**: `.shift(1)` is sufficient (daily FRED update)

### Never use `smoothed_marginal_probabilities` in backtests

If using `statsmodels MarkovRegression` for regime detection:
- `smoothed_marginal_probabilities` uses future data (backward pass) — **look-ahead bias**
- `filtered_marginal_probabilities` is safe — uses only information up to time t

```python
# CORRECT — no look-ahead
regime_probs = res.filtered_marginal_probabilities

# WRONG — introduces look-ahead bias (uses all future data)
# regime_probs = res.smoothed_marginal_probabilities
```

---

## 6. Regime Persistence Filtering

Short-duration regime switches (1–3 days) are noise, not signal. Filter them
before using in monthly strategies:

```python
def filter_short_regimes(regime: pd.Series, min_days: int = 5) -> pd.Series:
    """
    Enforce minimum regime duration.
    For monthly rebalance strategies, use min_days=5 (1 trading week).
    For daily strategies, min_days=2 reduces false signals.
    """
    smoothed = regime.copy()
    i = 0
    while i < len(smoothed):
        j = i
        while j < len(smoothed) and smoothed.iloc[j] == smoothed.iloc[i]:
            j += 1
        if j - i < min_days:
            prev = smoothed.iloc[i-1] if i > 0 else smoothed.iloc[j] if j < len(smoothed) else smoothed.iloc[i]
            smoothed.iloc[i:j] = prev
        i = j
    return smoothed
```

---

## 7. Complete Production Snippet (H249 style)

```python
import yfinance as yf
import pandas as pd
import os
import requests

FRED_KEY = os.environ.get("FRED_API_KEY", "")

def build_h249_regime_signals(start: str = "2005-01-01") -> pd.DataFrame:
    """
    Build all three production regime signals for H249.
    Returns DataFrame with columns: spy_bull, vix_calm, rate_hike, regime_4state.
    All columns are lag-corrected (shift(1) applied).
    """
    # 1. SPY 200-day MA
    spy = yf.download("SPY", start=start, auto_adjust=True, progress=False)["Close"]
    spy_bull = (spy > spy.rolling(200).mean()).shift(1).rename("spy_bull")

    # 2. VIX (FRED for completeness)
    r = requests.get(
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=VIXCLS&observation_start={start}&api_key={FRED_KEY}&file_type=json",
        timeout=30
    )
    obs = r.json()["observations"]
    vix = pd.to_numeric(
        pd.DataFrame(obs).set_index(pd.to_datetime(pd.DataFrame(obs)["date"]))["value"],
        errors="coerce"
    ).dropna()
    vix.index = vix.index.tz_localize(None)
    vix = vix.reindex(spy.index, method="ffill")
    vix_calm = (vix < 25.0).shift(1).rename("vix_calm")

    # 3. 10Y yield direction (FRED DGS10)
    r2 = requests.get(
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=DGS10&observation_start={start}&api_key={FRED_KEY}&file_type=json",
        timeout=30
    )
    obs2 = r2.json()["observations"]
    dgs10 = pd.to_numeric(
        pd.DataFrame(obs2).set_index(pd.to_datetime(pd.DataFrame(obs2)["date"]))["value"],
        errors="coerce"
    ).dropna()
    dgs10.index = dgs10.index.tz_localize(None)
    dgs10 = dgs10.reindex(spy.index, method="ffill")
    rate_hike = (dgs10.diff(63) > 0.50).shift(1).rename("rate_hike")

    # 4. 4-state composite regime
    def classify_regime(row):
        bull = row["spy_bull"]
        calm = row["vix_calm"]
        if bull and calm:    return "bull_calm"
        if bull and not calm: return "bull_volatile"
        if not bull and calm: return "bear_calm"
        return "bear_volatile"

    signals = pd.concat([spy_bull, vix_calm, rate_hike], axis=1).dropna()
    signals["regime_4state"] = signals.apply(classify_regime, axis=1)
    return signals
```

---

## 8. Performance Notes from Confirmed Tests

| Test | Signal used | Result |
|------|------------|--------|
| H165a (confirmed) | VIX < 25 gate on H026 | +0.429 OOS Sharpe; 46 bear months avoided |
| H205 regime split | SPY 200MA on TOM/BAB | Bear regime 13.8% ann_ret; 3.6× per-day premium vs bull |
| H249 (queued) | 4-state composite on production blend | IS 2008-2017 under test; OOS threshold +0.20 Sharpe |
| arXiv:2605.20636 | Continuous score: rate+VIX+SPY-DD | Sharpe 1.01, CAGR 19.24% (2017-2026, growth/defensive) |
| arXiv:2605.27848 | 3-state HMM (low/trans/high-vol) | RL-enhanced HMM outperforms passive SPY; SPY/TLT/GLD |
| arXiv:2410.14841 | SJM factor timing (6 factors) | IR 0.05 → 0.40 (8×) vs equal-weight (2000-2023) |

---

## 9. FRED API Reference

```python
# Key FRED series for regime detection:
FRED_REGIME_SERIES = {
    "VIXCLS":  "CBOE Volatility Index (daily, back to 1990)",
    "T10Y2Y":  "10-Year minus 2-Year Treasury spread (daily)",
    "T10Y3M":  "10-Year minus 3-Month spread — NY Fed recession indicator",
    "DGS10":   "10-Year Treasury constant maturity (daily)",
    "DGS2":    "2-Year Treasury constant maturity",
    "DGS1MO":  "1-Month Treasury bill rate",
    "USREC":   "NBER recession indicator (monthly, binary 0/1)",
    "BAMLH0A0HYM2": "High-yield spread (OAS) — credit stress indicator",
    "STLFSI4": "St. Louis Fed Financial Stress Index (weekly)",
}
# Access: https://api.stlouisfed.org/fred/series/observations?series_id={ID}&api_key={KEY}&file_type=json
```

**NBER recession indicator** (`USREC`): binary monthly series. Can be used as
ground truth to validate that regime signals correctly identify recession periods.
Note: NBER recession declarations lag by 6–18 months — do NOT use as a live signal.

---

## References

- Frazzini & Pedersen (2014). "Betting Against Beta." Journal of Financial Economics.
- Xiong, Z. (2026). "Continuous Timing Signals for Growth-Defensive Style Allocation." arXiv:2605.20636.
- Verma et al. (2026). "Regime-Based Portfolio Allocation Using HMM and RL." arXiv:2605.27848.
- Shu & Mulvey (2024). "Downside Risk Reduction Using Regime-Switching Signals: SJM." arXiv:2402.05272.
- Luo, Wang & Jussa (2025). "Dynamic allocation: extremes, tail dependence, and regime Shifts." arXiv:2506.12587.
- Shu & Mulvey (2024). "Dynamic Factor Allocation Leveraging Regime-Switching Signals." arXiv:2410.14841.
- FRED API documentation: https://fred.stlouisfed.org/docs/api/fred/
- See also: `algorithms/regime-detection.md` (HMM / Statistical Jump Model methods)
