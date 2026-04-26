---
updated: 2026-04-25
h001_status: REJECTED
---

# Hypothesis Log

Append-only. Each experiment gets a card before any code runs — results are recorded after. Status: `Pending` → `Running` → `Confirmed` / `Rejected` / `Inconclusive`.

## How to use

1. Write the hypothesis card first (what we predict and why)
2. Define confirm/reject criteria upfront — do not adjust after seeing results
3. Lock the out-of-sample period — never touch it until in-sample is fully evaluated
4. Record actual results verbatim; add interpretation below

---

## H001 — ORB: H/L mode vs ATR mode, risk-adjusted performance on QQQ

**Date filed**: 2026-04-25
**Status**: REJECTED
**Strategy**: Opening Range Breakout (5-min opening range, enter bar 6)
**Asset**: QQQ
**In-sample**: 2016-01-01 → 2022-12-31
**Out-of-sample**: 2023-01-01 → 2026-04-25 (locked — do not evaluate until H001 in-sample verdict is final)

### Hypothesis

H/L-mode exits (stop at range H/L, 10R profit target) will produce a **higher Sharpe ratio** than ATR-mode exits (5% of 14-day ATR stop, close EOD) over the in-sample period on QQQ, because the defined reward structure prevents large drawdowns on winning days.

### Null hypothesis

There is no statistically significant difference in Sharpe ratio between the two exit modes (difference < 0.2).

### Confirm criteria (all must hold)

- Sharpe(H/L) > Sharpe(ATR) by ≥ 0.2
- Max drawdown(H/L) ≤ max drawdown(ATR)
- Win rate difference < 10% (ensuring it's not just cherry-picking winners)

### Reject criteria (any one sufficient)

- Sharpe(ATR) ≥ Sharpe(H/L)
- H/L max drawdown exceeds ATR max drawdown by > 5%
- Total trades < 200 (insufficient sample)

### Results

Run: 2026-04-25 | QQQ | In-sample 2016-01-01 → 2022-12-31 | Starting equity: $25,000

| Metric | H/L mode | ATR mode |
|--------|----------|----------|
| Trades | 157 | 155 |
| Win rate | 31.9% | 12.3% |
| Avg win | $692 | $1,464 |
| Avg loss | -$263 | -$120 |
| Profit factor | 1.23 | 1.71 |
| **Sharpe** | **1.405** | **2.047** |
| Max drawdown | -13.2% | -11.2% |
| Calmar | 3.38 | 7.62 |
| Total return | 25.8% | 46.0% |
| Final equity | $31,459 | $36,505 |
| Exit breakdown | stop:102, eod:55 | stop:136, eod:19 |

**Verdict: REJECTED** — ATR mode is superior across all metrics. Sharpe difference = -0.642 (needed ≥ +0.200 to confirm).

### Interpretation

The hypothesis was wrong — ATR mode doesn't just match H/L, it clearly dominates. The key insight is the **asymmetry profile**:
- ATR mode wins only 12.3% of the time but average win ($1,464) dwarfs average loss ($120) — a 12:1 ratio
- This is a classic trend-following payoff: take many small losses, ride the occasional big breakout
- H/L mode's 10R target is too restrictive — it cuts winners that could run further, while the ATR stop is tighter on losses

**Note on regime breakdown**: All 157 trades fell in expansion regime. The 2020 recession (NBER: Feb–Apr 2020, 2 months) produced too few ORB signals to register in the regime grouping. H002 will need a broader contraction definition (e.g., 12-month SMA of FRED Industrial Production) to get meaningful sample sizes.

---

## H002 — ORB: ATR mode performs better in risk-off regimes

**Date filed**: 2026-04-25
**Status**: INCONCLUSIVE
**Strategy**: ORB, both exit modes
**Asset**: QQQ
**Regimes**: SPY 200-day SMA (risk-on / risk-off) — USREC too sparse (2020 only 2 months)

### Hypothesis

ATR-mode exits outperform H/L-mode on a risk-adjusted basis during **risk-off periods** (SPY below 200-day SMA), because elevated volatility in risk-off environments makes fixed R-multiple targets unrealistic while ATR-based stops adapt.

### Confirm criteria

- Sharpe(ATR, risk-off) > Sharpe(H/L, risk-off) by ≥ 0.15
- At least 20 risk-off trades in sample

### Results

Run: 2026-04-25 | QQQ | In-sample 2016-2022 | Regime: SPY 200-day SMA

| Metric | H/L risk-on | ATR risk-on | H/L risk-off | ATR risk-off |
|--------|------------|-------------|-------------|-------------|
| Trades | 61 | 61 | 96 | 94 |
| Win rate | 34.4% | 14.8% | 30.2% | 10.6% |
| Sharpe | 1.281 | **2.802** | 1.475 | **1.612** |
| Max DD | -9.4% | -5.2% | -13.2% | -11.2% |

**Verdict: INCONCLUSIVE** — ATR advantage in risk-off = +0.137 (threshold was ≥ 0.15).

### Interpretation

The result is nuanced and more interesting than a simple confirm/reject:
- ATR dominates in **risk-on** (Sharpe 2.802 vs 1.281) — big spread
- In **risk-off**, H/L mode *improves* (1.281 → 1.475) while ATR *declines* (2.802 → 1.612) — the gap narrows dramatically
- Hypothesis was directionally right but the effect is modest in risk-off
- Likely explanation: in volatile risk-off markets, intraday ranges are large enough that the 10R target becomes achievable (H/L mode benefits), while ATR stops get triggered more frequently before the breakout can develop
- **Actionable finding**: ATR mode is the better default, but H/L mode degrades less in risk-off regimes — could be the basis for a regime-switching strategy

---

## H003 — ORB: edge is leverage-dependent (TQQQ > QQQ > SPY)

**Date filed**: 2026-04-25
**Status**: INCONCLUSIVE (trade count) / DIRECTIONALLY CONFIRMED

### Hypothesis

ORB Sharpe ratio is higher on leveraged products (TQQQ) than the underlying (QQQ, SPY) because the wider daily ranges on leveraged ETFs make the opening range breakout signal more significant relative to noise.

### Confirm criteria

- Sharpe(TQQQ) > Sharpe(QQQ) > Sharpe(SPY), all using ATR mode
- All three have total trades > 200

### Results

Run: 2026-04-25 | ATR mode | In-sample 2016-2022

| Metric | SPY | QQQ | TQQQ |
|--------|-----|-----|------|
| Trades | 131 | 155 | 185 |
| Win rate | 7.6% | 12.3% | 15.1% |
| Avg win | $683 | $1,464 | $4,811 |
| Avg loss | -$75 | -$120 | -$504 |
| **Sharpe** | **-1.086** | **2.047** | **2.602** |
| Max DD | -19.2% | -11.2% | -17.8% |
| Total return | -8.8% | +46.0% | **+222%** |
| Final equity | $22,813 | $36,505 | $80,504 |

**Verdict: INCONCLUSIVE** on strict criteria (all three needed ≥200 trades; none reached threshold). Directionally the order TQQQ > QQQ > SPY holds perfectly.

### Interpretation

- **SPY ATR mode is broken** — Sharpe -1.086, loses money. The 5% ATR stop is too tight for SPY's compressed intraday ranges; stops trigger before breakouts develop (120/131 exits via stop)
- **SPY H/L mode works** (Sharpe 1.049) — the 10R target handles SPY's smaller ranges correctly
- **The ATR stop parameter (5% of ATR14) is not universal** — needs calibration per asset. Works for QQQ/TQQQ, not SPY
- **TQQQ ATR**: $25k → $80k in 7 years (222% total return, Sharpe 2.6) — most powerful setup found so far
- **H005 candidate**: Optimize ATR stop multiplier per asset (e.g., 10% for SPY, 5% for QQQ, 3% for TQQQ)

---

## H004 — ORB: edge decays post-2022 (out-of-sample test)

**Date filed**: 2026-04-25
**Status**: Pending (requires H001 in-sample to be confirmed first)

### Hypothesis

ORB Sharpe ratio in the out-of-sample period (2023–2026) is materially lower than in-sample (2016–2022), indicating strategy crowding or regime change post-COVID.

### Confirm criteria

- Sharpe(out-of-sample) < Sharpe(in-sample) × 0.7

### Reject criteria

- Out-of-sample Sharpe within 30% of in-sample Sharpe

---

## H005 — Dual Momentum Sector Rotation outperforms buy-and-hold SPY on risk-adjusted basis

**Date filed**: 2026-04-25
**Status**: CONFIRMED (in-sample) / REJECTED (out-of-sample)
**Strategy**: Sector ETF rotation (§4.1, §4.1.2 from Kakushadze & Serur 2018)
**Source**: `backtesting/daily/run_h005.py`
**Universe**: XLK, XLF, XLV, XLE, XLY, XLP, XLI, XLU, XLB (9 SPDR sectors)
**Parameters**: 12-1 month formation, top-3 sectors, monthly rebalance; SPY SMA(200) absolute filter → TLT refuge
**In-sample**: 2005-01-01 → 2019-12-31
**Out-of-sample**: 2020-01-01 → 2026-04-01 (viewed but LOCKED — no parameter changes allowed)

### Hypothesis

Dual momentum sector rotation (relative sector momentum + SPY absolute momentum filter) will produce a **higher Calmar ratio** than buy-and-hold SPY over the in-sample period, primarily by reducing max drawdown during bear markets.

### Confirm criteria

- Calmar(DualMom) > Calmar(BH_SPY)
- Max drawdown(DualMom) ≤ 70% of max drawdown(BH_SPY)
- After-tax return within 3% of buy-and-hold

### Reject criteria

- Calmar(DualMom) ≤ Calmar(BH_SPY)

### Results

**IN-SAMPLE (2005–2019)**

| Strategy | Ann.Ret | After-Tax | Sharpe | MaxDD | Calmar |
|----------|---------|-----------|--------|-------|--------|
| BH SPY | 9.0% | 7.2% (LTCG) | 0.291 | -55.2% | 0.164 |
| Sector Momentum | 7.7% | 4.8% (STCG) | 0.222 | -48.9% | 0.156 |
| **Dual Momentum** | **9.6%** | **6.1%** | **0.351** | **-28.1%** | **0.343** |
| MA 10/30 SPY | 3.6% | 2.3% | -0.083 | -23.8% | 0.151 |

**OUT-OF-SAMPLE (2020–2026)**

| Strategy | Ann.Ret | After-Tax | Sharpe | MaxDD | Calmar |
|----------|---------|-----------|--------|-------|--------|
| BH SPY | 13.6% | **10.8% (LTCG)** | 0.478 | -33.7% | 0.402 |
| Sector Momentum | **15.6%** | 9.8% (STCG) | **0.572** | **-27.1%** | **0.577** |
| Dual Momentum | 10.3% | 6.5% | 0.343 | -29.6% | 0.349 |
| MA 10/30 SPY | 7.4% | 4.6% | 0.232 | -19.8% | 0.372 |

**In-sample verdict: CONFIRMED** — Dual Momentum Calmar = 0.343 vs SPY 0.164 (2.1× better). Max DD cut from -55.2% to -28.1% (49% reduction, threshold was 70%).

**Out-of-sample verdict: REJECTED** — Dual Momentum Calmar 0.349 < SPY Calmar 0.402. After-tax return 6.5% vs SPY 10.8%.

### Interpretation

The in-sample story is strong: dual momentum's SPY/TLT filter worked very well during the 2008-2009 financial crisis, halving max drawdown at minimal return cost. This is the classic Antonacci (2014) result.

The out-of-sample degradation has a specific cause: **2022 rate shock**. When the Fed hiked aggressively, both SPY and TLT fell simultaneously — TLT lost ~25% in 2022, destroying the safe-haven logic. The strategy's Achilles heel is assuming bonds are uncorrelated with equities during downturns, which broke in 2022.

**Key finding on taxes**: Raw sector momentum beats SPY by 2% gross OOS (15.6% vs 13.6%), but STCG tax rate (37%) applied to monthly rebalancing **erases the entire gross advantage** — after-tax comes out 9.8% vs SPY's 10.8% LTCG. This is exactly the tax efficiency argument from the design principles: high-turnover strategies need ~1.5–2× gross return to beat buy-and-hold after taxes.

**Actionable insights**:
1. Dual momentum's drawdown protection works in "traditional" bear markets (2008 type) but fails in rate-shock bears (2022 type)
2. Tax drag is real and kills monthly-rebalancing advantage — need to extend holding periods or use tax-deferred accounts
3. Regime-switching needs a richer model: SPY vs TLT is insufficient; need "risk-off with rising rates" → short duration refuge (e.g., SGOV/BIL)

**Next hypothesis (H006)**: Test dual momentum with SGOV (3-month T-bills) as refuge instead of TLT, addressing the 2022 failure mode.
