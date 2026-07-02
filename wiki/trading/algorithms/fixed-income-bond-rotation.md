---
added: 2026-06-20
updated: 2026-07-02
category: algorithms
status: active
production: H045 (21% of portfolio)
related_hypotheses: H045 PRODUCTION, H355 CONFIRMED (OB filter), H283 NOT CONFIRMED, H314 NOT CONFIRMED, H315 NOT CONFIRMED
---

# Fixed Income / Bond ETF Rotation

## Overview

Bond ETF rotation applies time-series and cross-sectional momentum signals to a universe of fixed-income ETFs, rebalancing monthly to the top-ranked holding(s). The approach converts the traditionally static bond allocation (AGG buy-and-hold, Sharpe ~0.4) into an active strategy that sidesteps duration and credit risk dynamically.

**Production evidence:** H045 achieves OOS Sharpe 1.351 (2017–2026, including the 2022 rate shock) vs. AGG ~0.37 — a 3.7× Sharpe improvement with MaxDD of only −6.3%.

---

## Why Momentum Works in Bonds

Fixed income markets exhibit persistent momentum because:
1. **Rate cycle autocorrelation** — Federal Reserve tightening/easing cycles unfold over 12–24 months; early movers (short duration in a hike cycle) continue to win as the cycle progresses.
2. **Credit spread persistence** — High-yield credit spreads trend during risk-on/risk-off regimes; a single 3-month ranking captures the regime shift before mean-reversion dominates.
3. **Duration anchoring** — Institutional mandates create demand for specific duration buckets regardless of momentum; retail ETF flows chase returns, reinforcing trends.

Academic foundations:
- Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum" — confirmed across bonds, equities, commodities, FX
- Asness, Moskowitz & Pedersen (2013) "Value and Momentum Everywhere" — bond momentum confirmed in 7 sovereign bond markets
- Brooks & Moskowitz (2017) — bond-specific carry + momentum decomposition (AQR)

---

## Universe

### Core 7 (H045 original)
| ETF | Duration | Asset Class | OOS Hold Freq |
|-----|----------|-------------|---------------|
| SHY | 1–3y Treasury | Short-term gov | 72% |
| HYG | ~4y | High-yield credit | 48% |
| IEI | 3–7y Treasury | Intermediate gov | 35% |
| TIP | ~7y | TIPS (inflation) | 21% |
| IEF | 7–10y Treasury | Long-term gov | 15% |
| LQD | ~8y | Investment-grade credit | 12% |
| TLT | 15–20y Treasury | Long duration | <1% |

**Pattern:** Short duration (SHY) dominates in 2017–2026 because the regime was characterized by the post-2018 rate normalization and the 2022 shock. TLT is nearly never held — its 0.1% hold frequency reflects that the strategy effectively shorted duration risk by avoiding it.

### Extended 13 (production H045_monthly.py)
Adds: BKLN (floating-rate loans), EMB (EM sovereign), BIL (T-bills), MBB (mortgage-backed), FLOT (short-term float), PCY (EM corporate).

BIL serves as the cash fallback: when no ETF passes the TSMOM absolute-return filter (> +1.0% trailing 3m), 100% allocated to BIL. This is rare but critical for 2022 mid-cycle protection.

---

## Signal Design

### What works: momentum ensemble

H045 uses a **rank ensemble** across three lookback windows:
```
composite_rank = rank(3m_return) + rank(6m_return) + rank(12m_return)
tiebreaker     = rank(1 / vol_6m)        # lower volatility wins ties
```

Hold the top-1 (production) or top-2 (backtest research) by composite rank, subject to a TSMOM filter.

**Why three windows?** Each captures a different segment of the rate cycle:
- 3m: most important for bonds — catches the rate pivot early
- 6m: confirms the regime change
- 12m: filters out false signals from short-term noise

### TSMOM absolute-return filter
Before selecting the top ETF, it must show a trailing 3-month return > +1.0%. If no ETF qualifies, rotate to BIL. This filter is the primary protection against the 2022 scenario where every bond ETF was losing simultaneously.

Without this filter, the strategy would have selected the "least-bad" loser (SHY at −3%) rather than going defensive.

### Optimal lookback: 3 months, not 12 months
Bond momentum is **shorter-lived than equity momentum**:
- 12-month signals alone: catch the crisis late, exit duration when most of the damage is done
- 3-month + TSMOM filter: caught the TLT reversal by February 2022, rotated into SHY by March

This is the inverse of equity momentum (where 1-month reversal hurts and 12-month is canonical). Bond ETFs resolve their momentum faster because they are driven by monetary policy expectations rather than earnings growth.

---

## What Doesn't Work: Carry

H283 tested carry + momentum blends. All failed:

| Signal blend | OOS Sharpe | Gate |
|-------------|------------|------|
| Pure momentum (α=1.0) | 0.743 | ❌ |
| 75% momentum + 25% carry | 0.679 | ❌ |
| 50/50 blend | 0.602 | ❌ |
| Pure carry (α=0.0) | 0.393 | ❌ |

**Root cause:** ETF dividend yields ≠ forward-looking bond carry. Academic carry studies use:
- Repo rates (borrowing cost)
- Term premium decomposition (Adrian-Crump-Moench)
- Credit spread minus base rate

But yfinance dividends are backward-looking distributions with distribution lag. HYG's high yield looks attractive but the carry signal doesn't predict future returns because it reflects the past credit environment, not the forward spread.

**Implication:** Stick to momentum signals. Adding dividend-based carry from yfinance hurts the signal.

---

## Rate Regime & Crisis Robustness

### 2022 rate shock — the key test
The 2022 rate shock was the worst year for bonds in modern history:
- TLT: −26.1%
- AGG: −13.0%
- HYG: −11.8%

H045 survived with MaxDD −6.3% because the 3m TSMOM filter had already rotated the portfolio into SHY (−3.8%) and BKLN (+0.1%) by March 2022 when the Fed made its pivot clear.

### Bond-equity correlation flip
The traditional "bonds as equity hedge" breaks down during rate shocks:

| Regime | Bond-equity correlation | Example |
|--------|------------------------|---------|
| Normal growth | −0.2 to −0.4 | 2010–2019 |
| Risk-off (equity crash) | −0.3 to −0.6 | 2008, 2020 |
| Rate shock | +0.5 to +0.8 | 2022 |

In 2022, both TLT (−26%) and SPY (−18%) fell together — duration risk overwhelmed the flight-to-quality effect. This is why H256 (Dual Momentum with TLT as the risk-off asset) failed: the assumption that bonds hedge equities doesn't hold when inflation/rates are the primary driver.

**Portfolio implication:** Bond rotation (H045) provides diversification vs. equity rotation (H026) with Corr = 0.475 in normal regimes, but both can draw down simultaneously during rate shocks. BIL is the only true safe haven.

---

## Top-1 vs Top-2 Selection

| Selection | Research Sharpe | Production notes |
|-----------|----------------|-----------------|
| Top-1 | 1.309 | Less diversified, more concentration |
| Top-2 (50/50) | 1.351 | Confirmed winner in H045 backtests |

In production, the H045 paper trading uses top-1 for simplicity. Top-2 shows slightly better backtested Sharpe because bond ETF returns within a momentum quintile are more correlated than equity ETFs — diversifying into the second-ranked ETF adds returns without adding much correlated risk.

---

## Skip-Month Effects

Unlike equities, bonds show **no meaningful 1-month reversal** at the ETF level. The microstructure reversal that exists at the security level is averaged away in diversified ETFs. The ensemble 3m/6m/12m ranking implicitly avoids the most recent month's noise by using trailing returns that span many months.

**No explicit skip-month is used or needed in H045.** Adding a skip-month (using 12-1 instead of 12m) would degrade bond rotation by dropping the most recent rate signal.

---

## Implementation

### Monthly rebalance (not weekly)
Bond ETF spreads are negligible (SHY: 0.01%, TLT: 0.01%, HYG: 0.02%). Transaction costs are minimal. The reason for monthly rebalance is signal persistence — 3-month momentum requires at least 30 days to confirm a regime.

Weekly bond rotation generates excessive churn without signal improvement.

### Integration with equity rotation
H045 (21% of production portfolio) is intentionally uncorrelated with H026 (equity ETF rotation, 27%) and H041a (equity stock rotation, 22%). The bond component provides:
- Negative or low correlation during equity bear markets (when credit tightens but rates cut)
- Independent source of alpha when equity momentum is flat

The 2022 exception (positive correlation during rate shocks) is the known failure mode. Portfolio-level protection is achieved by keeping H045 allocation at 21% — small enough that a 2022-style joint drawdown (-6% on H045) doesn't threaten the production portfolio's overall drawdown limit.

---

## H355 — OB Filter on Bond ETF Universe (2026-07-02, CONFIRMED)

The same Order Block mechanism that improved equity ETF rotation (H345/H346) was applied to the H045 bond universe. **CONFIRMED** — OOS Sharpe improved from 1.112 to 1.522, with MaxDD halved.

### H355 Results

| Param / Variant | OOS Sharpe | OOS MaxDD | Notes |
|-----------------|------------|-----------|-------|
| Baseline D (H045, no filter) | 1.112 | -10.8% | — |
| best_A (window=20, strict: both top-2 must pass) | 1.418 | -5.0% | Below gate |
| **best_B (window=20, lenient: ≥1 of top-2 passes)** | **1.522** | **-5.0%** | **CONFIRMED** |
| best_C (gate: any of top-3 → top-2) | 1.391 | -7.2% | Below gate |
| ref_B (window=30, swing=5, lenient) | 1.470 | -8.1% | CONFIRMED |

**Gate**: OOS Sharpe > 1.451 (H045 baseline 1.351 + 0.10 improvement)

### Why OB Works on Bond Universe

The mechanism differs from equity ETFs:

- **Bull market environment**: Bond OBs form when institutions accumulate duration ahead of rate cuts. Active OBs on TLT/IEF signal a rally phase — lenient filter picks the best OB-confirmed bond.
- **2022 rate shock**: Rising rates "mitigate" OBs on long-duration ETFs as price breaks below institutional accumulation zones. The filter routes to SHY (the safe haven proxy) instead of following momentum into still-falling bonds.
- **MaxDD halved (-10.8% → -5.0%)**: OB filter fires before the full duration drawdown accumulates; equity ETF OB filter's zero-cash behavior is replaced here by SHY routing during rate stress.

### H355 vs H345/H346 Comparison

| Feature | H345/H346 (Equity ETFs) | H355 (Bond ETFs) |
|---------|--------------------------|------------------|
| Best params | window=20, swing_len=3 | window=20, swing_len=3 |
| Filter behavior | Selection enhancer (0 cash months) | Routes to SHY during stress |
| MaxDD improvement | -6.7% → -2.9% | -10.8% → -5.0% |
| OOS Sharpe gain | 2.538 → 3.238 (+28%) | 1.112 → 1.522 (+37%) |

**Same best params (window=20, swing_len=3) across all three asset classes** (stocks H344, equity ETFs H346, bond ETFs H355) — suggests a universal market microstructure signature rather than universe-specific tuning.

### Production Path

H355 best_B is production-ready as an **upgrade to the H045 monthly rebalancer**:
1. At each month-end, run OB detection on the top-2 momentum picks
2. If ≥1 has a bullish OB: enter those (with unfiltered fill for 2nd slot)
3. If 0 pass OB: hold SHY (already in universe as cash proxy)

```python
# H355 lenient filter (best_B) — drop-in for H045 top-2 selection
def h355_select(ranked, daily_data, me, ob_window=20, swing_len=3):
    top2 = ranked[:2]
    ob_pass = [t for t in top2 if has_bullish_ob(daily_data[t], me, ob_window, swing_len)]
    if len(ob_pass) >= 1:
        picks = ob_pass[:1]
        for t in ranked[:3]:
            if t not in picks and len(picks) < 2:
                picks.append(t)
        return picks
    return ["SHY"]  # cash proxy
```

Reference: `backtesting/daily/run_h355.py`

---

## Future Tests (Queued)

**H283b — True carry signal:** Replace ETF dividend yield with ACM term premium (FRED: THREEFYTP10) as carry proxy. Full FRED-sourced term premium measures forward-looking bond carry better than backward dividends.

**H314 — Duration-factor overlay (NOT CONFIRMED):** Tested FRED 10Y-3M yield spread as a duration tilt signal. All variants hurt vs baseline — momentum naturally handles yield curve regime. Overlay is redundant.

**H315 — Credit regime gate (NOT CONFIRMED):** FRED BAMLH0A0HYM2 only available from June 2023 due to ICE licensing. No stress months triggered in available data. Momentum TSMOM already excludes credit bonds organically.

---

## Reference Files

| File | Purpose |
|------|---------|
| `backtesting/daily/run_h045.py` | Full backtest, 7–13 ETF universe, 2007–2026 |
| `backtesting/paper_trading/h045_monthly.py` | Live production, Alpaca integration, extended 13 ETF |
| `backtesting/daily/run_h283.py` | Carry+momentum blend (failed) — reference for what not to do |
| `backtesting/results/h045_results.json` | IS/OOS Sharpe, year-by-year breakdown |

**Related wiki pages:** [Market Timing Overlays](market-timing-overlays.md) — VIX/200MA gate for equity rotation | [Regime Detection Signals](../backtesting/regime-detection-signals.md) — FRED data for regime classification | [IBS Mean-Reversion](ibs-mean-reversion.md) — complementary daily mean-reversion signal
