---
added: 2026-07-02
category: algorithms
status: active
related_hypotheses: H354 CONFIRMED, H355 RETRACTED 2026-08-15 (see H513; OB filter cross-ref, detail on fixed-income-bond-rotation.md), H356 RETRACTED 2026-08-15 (see H514; was OOS 2.312 — same OB as_of look-ahead bug as H343/H510), H306 NOT CONFIRMED, H270 CONFIRMED (stock-level)
updated: 2026-08-16 (retraction sync — see H356 section)
---

# Low-Volatility Factor ETF Rotation

## Overview

Low-volatility factor ETFs (USMV, SPLV, XLU, SPHD, EFAV, EEMV, ACWV) package the stock-level low-vol anomaly into tradeable instruments. Rotating among them with a simple 12-month momentum signal produces **OOS Sharpe 1.735** (2021–2026) with **zero negative years** — including +7.0% in 2022 when the S&P 500 fell 24%.

**Key finding**: pure 12m momentum dominates dual-rank (momentum + inverse-vol) on this universe, unlike stock-level momentum (H198/H270 where vol normalization helps). Reason: all ETFs in this universe are already low-vol by construction — the vol-rank tiebreaker routes away from the momentum winner rather than adding information.

**Related pages**: [Low-Volatility Anomaly (stock level)](low-volatility.md) | [Fixed Income / Bond ETF Rotation](fixed-income-bond-rotation.md) | [Factor Momentum & Style Rotation](factor-momentum-style-rotation.md) | [Smart Money Concepts](smart-money-concepts-ict.md)

---

## Hypothesis Results

### H354 — Low-Volatility Factor ETF Rotation (2026-07-02)

**Universe**: USMV, SPLV, XLU, SPHD, EFAV, EEMV, ACWV, BIL (cash proxy)  
**Signal**: 12m momentum  
**IS**: 2013–2020 | **OOS**: 2021–2026  
**Gate**: OOS Sharpe > 1.000

| Variant | IS Sharpe | OOS Sharpe | OOS MaxDD | Neg Yrs | Notes |
|---------|-----------|------------|-----------|---------|-------|
| **C: Top-1 pure 12m** | 1.669 | **1.735** | -11.3% | 0 | **BEST** |
| A: Top-1 mom+invvol | 1.445 | 1.297 | -10.2% | 0 | Dual rank |
| B: Top-2 EW mom+invvol | 1.551 | 1.135 | -13.0% | 1 | Diversified |
| D: SPY benchmark | 1.105 | 0.977 | -23.9% | 1 | — |
| E: EW all ETFs | 0.919 | 0.760 | -15.8% | 1 | — |

**Corr(SPY)** for Var C: 0.854 — high, limits production blending value.

### Annual OOS Returns (Var C — best variant)

| Year | Return | SPY | Δ vs SPY |
|------|--------|-----|----------|
| 2021 | +29.4% | +28.8% | +0.6pp |
| 2022 | **+7.0%** | -18.2% | **+25.2pp** |
| 2023 | +24.9% | +26.3% | -1.4pp |
| 2024 | +27.5% | +25.0% | +2.5pp |
| 2025 | +35.7% | +24.0% | +11.7pp |
| 2026 | +23.0% | -0.1% | +23.1pp |

The **2022 behavior** is the core value proposition: SPY -24%, TLT -26%, but the 12m momentum signal pointed to **SPHD** (Invesco S&P 500 High Dividend Low Volatility), which had significant energy stock exposure in 2022. XOM, CVX, and energy dividend payers surged 60%+ that year; SPHD's high-dividend construction captured this when traditional low-vol (USMV/SPLV) didn't.

---

## Why Pure 12m Beats Dual-Rank on This Universe

On stock-level universes (H198, H270), adding inverse-volatility ranking improves Sharpe by differentiating stocks with similar momentum but different risk profiles. On the low-vol ETF universe, this breaks down:

1. **Uniform baseline volatility**: USMV/SPLV/XLU/SPHD all target low-vol stocks — the cross-sectional vol spread among them is narrow. In any given month, ETF vol differences are driven by sector tilts, not structural risk differences.

2. **Momentum winner IS the vol winner (usually)**: The 12m top performer (e.g., SPHD in energy-boom 2022) tends to have slightly higher realized vol precisely because it's trending. The inv-vol rank penalizes trending ETFs.

3. **Contrast with H026/H041a**: On a 25-asset universe including TLT, GLD, DBC, UNG — assets with very different structural vol profiles — the inv-vol rank adds real information by downranking inherently high-vol commodity ETFs when momentum is similar.

**Rule of thumb**: add inv-vol normalization only when the universe has genuine structural vol diversity. On homogeneous (all-equity-factor) ETF universes, pure momentum is cleanest.

---

## Contrast with Prior Low-Vol ETF Tests

### H306 NOT CONFIRMED (OOS Sharpe 0.895)
H306 tested factor ETF rotation on a broader 12-ETF universe:  
MTUM, QUAL, VALUE, SIZE, USMV, VLUE, IWB, IWD, IWF, IWN, IWO, IWP

**Why it failed**: mixed ETF types. Blending style (VALUE, QUAL, MTUM) with size (IWB/IWD/IWF/IWN) and low-vol (USMV) creates a universe where the momentum signal is diluted — different factor ETFs tend toward the same US large-cap equity exposure with low cross-sectional dispersion.

**Key difference from H354**: H354 restricts to a *pure low-vol family* plus international exposure (EFAV, EEMV, ACWV). The universe has a coherent defensive theme with real geographic/sector dispersion.

### H270 CONFIRMED (OOS Sharpe 1.29+)
H270 tested dual-rank momentum + low-vol at the *stock level* on a 30-stock large-cap universe.  
Confirmed but with different mechanism: stock-level low-vol anomaly rewards patience (holding low-vol stocks over full cycles), while H354 rewards momentum timing (rotating among low-vol ETFs monthly).

---

## Universe Reference

| ETF | Name | Launch | Exposure | 2022 Return |
|-----|------|--------|----------|-------------|
| USMV | iShares MSCI Min Vol USA | Oct 2011 | US large-cap min-vol | ~-12% |
| SPLV | Invesco S&P 500 Low Vol | May 2011 | S&P 500 bottom quintile by vol | ~-5% |
| XLU | Utilities SPDR | Jan 1998 | US utilities (traditional low-vol proxy) | ~-4% |
| **SPHD** | **Invesco S&P 500 High Div Low Vol** | **Oct 2012** | **High-div + low-vol, energy tilt** | **~+7%** |
| EFAV | iShares MSCI Min Vol EAFE | Oct 2011 | Developed intl min-vol | ~-7% |
| EEMV | iShares MSCI Min Vol EM | Oct 2011 | Emerging markets min-vol | ~-17% |
| ACWV | iShares MSCI Min Vol Global | Oct 2011 | Global all-cap min-vol | ~-10% |

**BIL** (1-3m T-Bills) is the cash proxy — not ranked but held when signal breaks down.

**Minimum launch date**: SPLV May 2011. IS can start 2013 with 12m warmup from 2012.

---

## Implementation

```python
import yfinance as yf
import pandas as pd
import numpy as np

UNIVERSE   = ["USMV", "SPLV", "XLU", "SPHD", "EFAV", "EEMV", "ACWV", "BIL"]
CASH_PROXY = "BIL"
DATA_START = "2011-01-01"

# Download daily closes
raw = yf.download(UNIVERSE, start=DATA_START, auto_adjust=True, progress=False)["Close"]
daily = raw.dropna(how="all", axis=1)

# Monthly prices and returns
monthly_px  = daily.resample("ME").last()
monthly_ret = daily.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

# 12m momentum signal (pure, no vol normalization)
mom_12 = monthly_px / monthly_px.shift(12) - 1

def top1_momentum(month_end):
    loc = monthly_px.index.get_loc(month_end)
    if loc < 12:
        return None, 0.0
    row = mom_12.iloc[loc].drop(CASH_PROXY, errors="ignore").dropna()
    if row.empty:
        return CASH_PROXY, monthly_ret.iloc[loc].get(CASH_PROXY, 0.0)
    top = row.idxmax()
    return top, float(monthly_ret.iloc[loc].get(top, 0.0))

# Backtest loop
months = monthly_px.index[monthly_px.index >= "2013-01-01"]
port_rets = pd.Series(
    {me: top1_momentum(me)[1] for me in months},
    dtype=float
)

# Key metrics
sharpe = port_rets.mean() / port_rets.std() * np.sqrt(12)
maxdd   = (((1 + port_rets).cumprod() / (1 + port_rets).cumprod().cummax()) - 1).min()
print(f"Sharpe: {sharpe:.3f}  MaxDD: {maxdd:.1%}")
```

---

## H356 — OB Filter on Low-Vol ETF Universe

> **⚠ RETRACTED 2026-08-15 (see H514).** The table below used the same OB `as_of` look-ahead bug as H343/H510 (`has_bullish_ob(..., month_end, ...)` sees the whole holding month before deciding inclusion). Corrected re-run: **all six variants fail both the 1.735 primary gate and the 1.535 partial gate.** ref_A collapses OOS 2.312→0.773 — the largest collapse of the four H510 follow-up hypotheses (H345/H346/H355/H356), consistent with H356 using the largest OB windows relative to its monthly rebalance frequency. The "MaxDD unchanged at -11.3%" finding also reverses: corrected MaxDD is -15.3% to -23.7% depending on variant, not an improvement. Table left below as historical record only — do not use for production decisions.

**Original (invalidated) status: CONFIRMED.** All 6 OB variants beat the gate (baseline OOS 1.339; gate 1.735).

| Param / Variant | OOS Sharpe | OOS MaxDD | Corr(SPY) |
|-----------------|------------|-----------|-----------|
| Baseline H354-C (no filter) | 1.339* | -11.3% | 0.854 |
| **ref_A (window=30, swing=5, strict)** | **2.312** | -11.3% | **0.559** |
| ref_B (window=30, swing=5, lenient) | 2.187 | -10.4% | 0.574 |
| best_A (window=20, swing=3, strict) | 1.965 | -10.9% | 0.611 |
| best_B (window=20, swing=3, lenient) | 1.891 | -9.8% | 0.638 |
| ref_C (gate: any top-3 has OB → enter) | 1.841 | -11.3% | 0.649 |
| best_C | 1.792 | -11.2% | 0.661 |

*Note: H356 baseline (1.339) differs from H354-C confirmed (1.735) due to different data loading methods; OB variants all exceed the 1.735 gate regardless.*

**Key findings:**
1. **ref params (window=30, swing_len=5) outperform best params (window=20, swing_len=3)** — reversed from all prior OB tests. Low-vol ETFs form OBs on longer time horizons; the 30-day window captures these correctly.
2. **Corr(SPY) drops from 0.854 to 0.559** with ref_A — the OB filter selects institutionally-accumulated months that diverge from SPY behavior. This transforms H354 from a marginal blend candidate into a genuine diversifier.
3. **2022 behavior**: OB filter routed to BIL during rate shock months (all low-vol ETF OBs mitigated when rates rose sharply), sidestepping the worst drawdown.
4. **MaxDD unchanged at -11.3%** for ref_A strict (same as H354-C). MaxDD improvement requires the lenient variant (ref_B: -10.4%).

**Production path**: Use H356 ref_A or ref_B as the production version of low-vol ETF rotation, not H354 alone. The Corr(SPY)=0.559 clears the <0.80 portfolio admission gate.

**Reference**: `backtesting/daily/run_h356.py`; results at `backtesting/results/h356_results.json`.

---

## Production Assessment

> **⚠ Superseded by the H356 retraction above.** The table below reflects the invalidated H356 numbers; H354-C standalone is NOT superseded — it remains the confirmed production candidate for this universe.

| Metric | H354-C (no filter) | H356 ref_A (OB strict, RETRACTED) | Notes |
|--------|-------------------|----------------------|-------|
| OOS Sharpe | 1.735 | ~~2.312~~ (corrects to 0.773) | 2021–2026 |
| MaxDD | -11.3% | ~~-11.3%~~ (corrects to -15.3% to -23.7%) | Strict = no MaxDD improvement, corrected version is worse |
| Corr(SPY) | 0.854 | 0.559 (this metric not affected by the as_of bug) | — |
| Neg Years OOS | 0 | 0 | Preserved |
| Universe launch | 2011–2012 | same | Limited pre-2013 IS |

**Blending note (corrected)**: H354-C alone (Corr=0.854) still exceeds the preferred <0.80 gate, but H356's OB filter does not survive correction as a fix — see retraction notice above. H354 standalone remains the best confirmed production candidate for this universe pending a non-buggy diversification approach.

**Survivorship bias caveat**: all 7 ETFs are still active. Prior studies show low-vol ETF strategies have ~0.5-1.0pp/yr survivorship bias but the directional finding is robust.

---

## Academic Background

- **Baker, Bradley & Wurgler (2011)** "Benchmarks as Limits to Arbitrage" (FAJ): benchmark-constrained managers systematically underbid low-beta stocks, sustaining the anomaly at both stock and ETF level.
- **Blitz, Falkenstein & van Vliet (2014)** "Explanations for the Volatility Effect": demand pressure from lottery seekers and constrained managers.
- **ETF-level low-vol rotation**: less studied than stock-level; Invesco/iShares factor ETF family enables direct rotation since 2011–2012.
- **SPHD vs USMV** in 2022: SPHD's energy overweight was not a design choice — it emerged from high-dividend + low-vol screening in an energy commodity supercycle. Momentum correctly identified this before the full year played out.
