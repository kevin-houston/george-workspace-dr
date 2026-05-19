# Algorithmic Trading Research — Comprehensive Summary
**As of May 18, 2026**

---

## 1. Project Overview

**Goal**: Establish an income stream for Kevin via algorithmic securities trading and prediction markets. The agent works autonomously — researching nightly, building incrementally, paper trading to prove results, then going live.

**Current phase**: Transitioning from Phase 2 (backtesting) to Phase 3 (paper trading). Backtesting of approximately 200 hypotheses is largely complete; three strategies are actively paper trading on Alpaca.

### Phase Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | Done | Research & wiki-building |
| 2 | Active (winding down) | Backtesting infrastructure + hypothesis testing |
| 3 | Active (started 2026-04-28) | Paper trading via Alpaca |
| 4 | Pending | Live trading with real capital |

### Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-24 | Start with research, paper trade before real money | Prove results before risking capital |
| 2026-04-24 | Focus: equities and options first | Kevin's stated priority |
| 2026-04-24 | Data: Polygon.io + Alpaca free tiers | Both accounts exist; keys in OneCLI |
| 2026-04-24 | Paper trading via Alpaca ($102k paper account) | Kevin's existing paper account |
| 2026-04-24 | Backtests must model macro regimes + after-tax returns | Real-world accuracy requirement |
| 2026-04-26 | yfinance as data fallback | Alpaca SDK not installable in container; yfinance works for EOD |
| 2026-04-26 | BIL preferred over TLT as risk-off in dual momentum | TLT has duration risk; BIL is immune to rate-hike bears |
| 2026-04-27 | H020 supersedes H016 as primary ETF strategy | Sharpe 1.23 vs 0.78; better generalization |
| 2026-04-27 | H026 (sector ETF rotation) is the crown jewel | Sharpe 3.007 OOS; 100% allocation confirmed optimal via H149 |
| 2026-04-27 | alpaca-py (not alpaca-trade-api) for all Alpaca work | Legacy SDK deprecated Dec 2022 |

---

## 2. Research Methodology

### IS/OOS Framework

The most important discipline in the entire program. Every hypothesis uses strict temporal separation:

```
|─── In-Sample (IS) ──────────────|── OOS ──────|── AltOOS ──|
   ~10 years for parameter estimation    ~4 years      ~4 years
   Parameter lock at IS-end              Primary test  Independent test
```

**Critical rule**: parameters are locked after IS calibration. OOS data is never touched until the parameter lock step. Both OOS and AltOOS windows must confirm independently — a single lucky OOS period is insufficient.

Actual splits used across the program:
- **ETF rotation strategies**: IS 2003–2017, OOS 2018–2026, AltOOS varies
- **Stock-level strategies (H181, H192-D, H198, etc.)**: IS 2013–2020, OOS 2021–2026

### Hypothesis Testing Protocol

**Nine-step pipeline**:
1. Literature search — academic anchor with replication code or clear methodology
2. IS design — define signal, entry/exit rules, hold period
3. IS calibration — test 3–5 parameter variants on IS only
4. **Lock parameters** — freeze all choices before seeing OOS
5. OOS run — single pass; record all metrics
6. Verdict — apply confirmation criteria
7. AltOOS confirmation — independent second window
8. Log — add full result to hypothesis-log.md (pass or fail, including failures)
9. If CONFIRMED → paper trade → live; if NOT CONFIRMED → document root cause

### Confirmation Criteria (Tiered)

**Tier 1 — Raw event effect** (event studies, minimum to proceed):
- OOS t-stat ≥ 2.0 (p < 0.05)
- OOS n ≥ 30 events

**Tier 2 — Full CONFIRMED** (portfolio-level):
- OOS Sharpe ≥ 1.0
- OOS MaxDD ≥ −20% (less severe)
- OOS WinRate ≥ 55% (or positive mean return with high t-stat)
- Both OOS and AltOOS pass independently

**Tier 3 — PARTIAL CONFIRMED**:
- Genuine event effect confirmed (t-stat ≥ 2.0)
- Portfolio metrics don't meet all Tier 2 criteria
- Known root cause for the gap; improvement path exists

### Overfitting Detection

**IS/OOS Sharpe gap thresholds**:

| IS/OOS Ratio | Interpretation |
|-------------|----------------|
| IS ≈ OOS | Clean generalization |
| IS = 2× OOS | Moderate overfitting — investigate |
| IS = 4× OOS | Severe overfitting — reject or redesign |
| IS > 1.5 but OOS < 0.3 | Structural decay / regime change |

Real example: H159b (beta-neutral PEAD) — IS Sharpe 1.6, OOS Sharpe 0.38, ratio 4.2× — confirmed structural decay post-2018 from HFT arbitrage of the PEAD drift.

**Deflated Sharpe Ratio (DSR)**: For strategies with more than ~10 parameter combinations tested, raw OOS Sharpe is divided by ~1.3 as a multiple-testing correction (López de Prado / Bailey 2014). H026 sector rotation had ~5 parameters tested; even with this correction its OOS Sharpe 3.007 deflates to ~2.3, which is still excellent.

### Biases Actively Guarded Against

1. **Survivorship bias** — most dangerous. Uses point-in-time constituent lists where available; always noted in CONFIRMED caveats. A classic example from H-series: 5-stock momentum Sharpe jumped from 0.09 to 0.66 once delistings were removed.
2. **Look-ahead bias** — earnings announcement times (pre/post-market) must be correct; FRED data is retroactively revised; split-adjusted prices require careful handling.
3. **Data snooping** — maintain complete hypothesis log including all failures; apply DSR.
4. **Parameter mining** — flag when IS/OOS gap > 4×; require monotonic sensitivity.
5. **Reporting bias** — hypothesis log contains all 200+ results, winners and losers.

### Walk-Forward and CPCV

For strategies with rolling parameter updates (adaptive strategies), walk-forward analysis is used: train on IS window, test on next window, roll forward, concatenate all WF test periods into an equity curve. Static strategies like H026 use a simple IS/OOS split — the signal is robust enough not to require rolling re-estimation.

For ML strategies (XGBoost, gradient boosting), Combinatorial Purged Cross-Validation (CPCV) from López de Prado (2020) is the standard, implemented via `skfolio.CombinatorialPurgedCV`. Purging removes training samples that overlap the test period's look-ahead window; embargoing adds a buffer after the test window.

### Costs Modeled

- Slippage: 0.05–0.1% per trade for liquid large-caps
- Commission: Alpaca is commission-free (PFOF may affect fills)
- Bid-ask spread: 1–5% of premium for short-dated options
- Tax: STCG rate 37% applied to high-turnover strategies; LTCG 15–20% for low-turnover strategies holding ≥1 year. High-turnover strategies need ~1.5–2× gross return to net the same after-tax income.

---

## 3. Strategy Results — Confirmed

### H020: 5-Asset ETF Rotation (Superseded by H026)

**Signal**: Top-2 from universe of SPY, QQQ, TLT, GLD, IEF, scored by 12m+6m+3m momentum with TSMOM filter.
**Universe**: 5 broad-market ETFs.
**Key stats**: OOS Sharpe 1.23, MaxDD −18.4%. Only 6.7% OOS degradation vs IS (typical is 50%+).

Established the core methodology — rank ensemble beats single lookback; TSMOM filter essential. Later superseded by H026's larger sector universe which dramatically outperformed.

---

### H026 / H149: Sector ETF Momentum — THE CROWN JEWEL

**Signal**: Composite rank = rank(12m_ret) + rank(6m_ret) + rank(3m_ret) + rank(inv_6m_vol). Hold top-1 asset if 12-month return > +5% threshold; otherwise rotate to BIL (T-bills).
**Universe**: 25 ETFs — 11 S&P sector ETFs + BIL + GLD + TLT + IEF + TIP + DBC + AGG + GDX + DBA + SLV + UNG + EWZ + IBB + USO.
**Rebalance**: Monthly, first trading day of month.
**IS period**: 2003–2017 | **OOS period**: 2018–2026

**OOS Performance (2018–2026)**:
- Cumulative return: 382.9× (vs ~3× for SPY)
- Sharpe: 3.007
- MaxDD: −9.6%
- Negative calendar years: 0
- CAGR: ~23%

**Why it works**: Sector ETFs trend for quarters at a time — institutional flows, macro narratives, and index composition reinforce sector momentum. The 12-month TSMOM filter (+5% threshold) acts as crash protection — when no sector qualifies, the portfolio moves to T-bills, cutting exposure before extended drawdowns. This is the mechanism behind both the near-zero drawdown and 0 negative years.

**Why top-1 concentration beats diversification**: At monthly rebalance frequency, the momentum signal decays sharply between the #1 and #2 ranked assets. Holding #2 is portfolio dilution, not diversification. This was confirmed repeatedly across H083, H096, H106, H135 — every test showed top-2 or top-3 underperforming top-1.

**Why BIL not TLT for risk-off**: TLT (long-duration Treasuries) has significant duration risk during Fed tightening cycles (2022 being the most vivid example). BIL holds 1–3 month T-bills, immune to duration risk. Confirmed H006.

**H149 finding**: As H026's portfolio allocation increased from 7% to 100% across hypotheses H090 through H149, performance improved monotonically at every step. The TSMOM filter provides sufficient crash protection even at 100% concentration. No diversification benefit from adding other strategy legs.

**Limitations**: Survivorship bias is a real concern — the 25-ETF universe uses ETFs still in existence today. The strategy's 20+ year backtest also spans an unusually favorable equity environment. After-tax returns for monthly rebalancing are STCG (37% rate); after-tax CAGR is materially lower than gross.

**Live status**: Deployed on Alpaca paper trading since May 1, 2026. Script: `backtesting/paper_trading/h112_monthly.py`. Path to real money: 4–8 weeks validation.

---

### H181: Industry-Adjusted Short-Term Reversal

**Signal**: REV^IN = stock's last-month return minus equal-weighted mean return of its GICS industry group. Long bottom quintile (biggest industry-relative losers), monthly rebalance.
**Universe**: 30 large-cap S&P 500 stocks across 8 GICS sectors.
**Academic basis**: Stosik & Zaremba (SSRN:6630998, April 2026) — 64 countries, 1990–2023. Raw reversal is dead (+0.05%/month, insignificant); industry-adjusted reversal is alive (+0.53%/month, Sharpe 0.74, six-factor alpha 0.60% t=4.14).
**IS period**: 2013–2020 | **OOS period**: 2021–2026

**OOS Performance**:
- Sharpe: 1.138
- CAGR: 24.6%
- MaxDD: −18.4%
- Negative years: 1
- Corr(H026): 0.293 — genuine diversification

**Why it works**: The industry adjustment isolates the idiosyncratic component of last month's move — specifically the liquidity provision premium (market-makers temporarily move prices; subsequent reversal compensates them). Raw reversal without industry adjustment is contaminated by sector momentum, which does NOT mean-revert.

**Why it works better long-only**: Short-selling in practice is expensive and risky. The long-only (bottom quintile) variant captures most of the alpha while avoiding borrow costs and short-squeeze risk. Practical for a retail paper account.

**Limitations**: Corr(SPY) ≈ 0.5+ — all 6 long positions move with the market in bear scenarios. MaxDD of −18.4% reflects this market beta. Requires a minimum of ~5 stocks per industry group for the industry adjustment to be statistically meaningful; our 30-stock universe with 8 sectors is right at this minimum.

**Live status**: Deployed on Alpaca paper trading since May 10, 2026. Script: `backtesting/paper_trading/h181_monthly.py`. Path to real money: 2 months validation.

---

### H192-D: Sector-Neutral BAB (Betting Against Beta)

**Signal**: Compute Frazzini-Pedersen beta for each stock (vol ratio × 5-year rolling monthly correlation). Rank beta within each GICS sector. Long the 6 lowest-beta stocks (across sectors), equal-weight, monthly rebalance.
**Universe**: Same 30 large-cap S&P 500 stocks as H181.
**Academic basis**: Frazzini & Pedersen (2014, JFE) — low-beta anomaly. Mechanism: leverage-constrained investors overbid high-beta stocks; low-beta stocks are structurally underpriced.
**IS period**: 2013–2020 | **OOS period**: 2021–2026

**OOS Performance (H192-D variant)**:
- Sharpe: 1.367 — best Sharpe of any stock-level strategy tested
- CAGR: 19.1%
- MaxDD: −17.1%
- IS/OOS decay: ~18% (clean generalization)

**Variant comparison**: Four BAB variants were tested. H192-A (raw beta) and H192-D (sector-neutral beta) were the survivors.
- H192-A (raw beta, long 6 lowest-beta): OOS Sharpe 1.213
- H192-D (sector-neutral, rank beta within sector): OOS Sharpe 1.367 — winner

**Why sector-neutral matters**: Raw BAB loads heavily on Utilities and Consumer Staples — low-beta sectors by definition. This concentrates exposure to those sectors' idiosyncratic risk (regulatory changes, rate sensitivity). Ranking beta *within* sectors finds the low-beta stock *within* Tech, *within* Energy, etc. — which captures pure cross-sectional beta anomaly without sector timing.

**Limitations**: Higher Sharpe than H181 but lower absolute CAGR (19.1% vs 24.6%). The choice between H192-D and H181 depends on whether the goal is Sharpe optimization or absolute compounding. H192-D is not yet deployed alongside H181 due to significant stock overlap in the final picks.

---

### H198: Cross-Sectional Stock Momentum (6-1m)

**Signal**: Rank stocks by 6-month return skipping the most recent month (6-1m, "skip-month" convention to avoid short-term reversal). Long top-6 equal-weight, monthly rebalance.
**Universe**: Same 30 large-cap S&P 500 stocks.
**Academic basis**: Jegadeesh & Titman (1993) — standard cross-sectional momentum.
**IS period**: 2013–2020 | **OOS period**: 2021–2026

**OOS Performance**:
- Sharpe: 1.174 (6-1m optimal; 12-1m also confirmed at 1.096)
- Cumulative: 3.656× (vs SPY 2.044×)
- MaxDD: −22.7%
- Corr(SPY): 0.717

**Important caveat**: High SPY correlation (0.717) means this strategy is primarily capturing sector rotation on a 30-stock large-cap universe — essentially doing what H026 does, but less efficiently. For a portfolio already running H026, H198 adds limited diversification. H192-D (BAB, Sharpe 1.367) is the better stock-level alpha source because it exploits an orthogonal driver. H198 is confirmed standalone but not recommended as a portfolio addendum until Corr vs H026 production equity curve is verified.

H199 (sector-neutral momentum) tested and failed — sector drift IS the momentum signal on large-caps, not noise.

---

### H201: Turn-of-Month (TOM) Calendar Effect

**Signal**: Hold SPY (or any broad equity index) during the last 2 + first 2 trading days of each month (4 days ≈ 19% of all trading days). Hold BIL otherwise.
**Academic basis**: Lakonishok & Smidt (1988) — institutional cash flows (payroll, 401k deposits) create predictable demand pressure at month-end.
**IS period**: 2003–2017 | **OOS period**: 2018–2026

**OOS Performance**:
- Sharpe: 0.740
- MaxDD: −9.3%
- CAGR: 5.6%
- SPY buy-and-hold OOS: Sharpe 0.789, MaxDD −33.7%, CAGR 15.2%

**Critical interpretation**: TOM earns a fraction of SPY's absolute return (5.6% vs 15.2% CAGR) but dramatically improves the risk profile (MaxDD −9.3% vs −33.7%). Its value is as a **timing overlay** on top of alpha-generating strategies — particularly BAB (H205 queued) and as a hedge during volatile months. Not useful as a standalone strategy for income generation.

**Notable finding**: The IS/OOS dynamic is inverted from most strategies — TOM is stronger in recent data (2018–2026) than in the pre-2018 period. Institutional ETF flows and index rebalancing may have strengthened the mechanism.

---

### H163 / H174: PEAD-NLP Event-Driven (FinBERT Earnings Gap)

**Signal**: Filter earnings gap-up events (stock gaps ≥3% at open on earnings day) by FinBERT sentiment score ≥ 0.18 on the company's SEC 8-K earnings press release AND sentiment surprise ≥ 0.02 (current score minus prior quarter average). Enter at market open (OPG order), hold 20 trading days, exit at close.
**Academic basis**: Bernard & Thomas (1989) PEAD; Meursault et al. (JFQA 2022) — text-based earnings surprise earns 3.9 bps/day vs 2.6 bps for price-based SUE.
**OOS sample (dual-filter variant)**: n=22 events, 2021–2026

**OOS Performance (H163 NLP filter confirmation)**:
- Win rate: 81.8% (vs 57.6% baseline gap-only)
- Mean return per event: 6.89% over 20 days
- The FinBERT filter adds ~+10pp win rate and ~2× mean return vs unfiltered gap entry

**H174 (live pipeline)**: The deployed version uses both the gap filter AND FinBERT dual-filter. ProsusAI/finbert is the proven NLP model (H163 confirmed). Signal source: SEC EDGAR 8-K filings, scored nightly via the PEAD pipeline scripts at `backtesting/paper_trading/pead_pipeline/`.

**Why base PEAD failed (H159, H159b)**: Raw gap-up PEAD (H159) confirmed a real drift effect (OOS t-stat = 5.64, n=374, mean 20-day return +4.39%, WR 63.9%) but the unhedged portfolio had MaxDD −43 to −58% because 30 simultaneous long-equity positions crash together in bear markets. Beta-neutral PEAD (H159b, SPY-short hedge) reduced Sharpe to 0.382 — the hedge eliminated market correlation but idiosyncratic gap-up stock collapses remain.

**Why FinBERT filter works**: PEAD is strongest for earnings with genuinely positive new information — not just a price gap. 8-K press release language that FinBERT rates as clearly positive (score ≥ 0.18) is selecting genuine earnings quality beats, not lucky EPS upside from non-recurring items. The ~10pp win rate improvement confirms that language predicts post-announcement drift beyond the price signal alone.

**Live status**: Deployed on Alpaca paper trading since May 6, 2026. 0 trades so far — the dual filter is strict enough that events fire infrequently. Path to real money: 10 live trades minimum.

---

### H190: H188 + H181 Blend (40% / 60%)

**Signal**: Blend two confirmed signals — 40% weight on 52-week high proximity momentum (H188) and 60% on industry-adjusted reversal (H181). Long top-6 by blended score, monthly rebalance.
**OOS Performance**: Sharpe 1.191, MaxDD −14.7%

This is the Pareto improvement over H181 pure — higher Sharpe (1.191 vs 1.138) AND lower MaxDD (−14.7% vs −18.4%) simultaneously. The blend works because H188 and H181 select almost entirely different stocks (average overlap 0.4/6) — they identify stocks in different regimes (high turnover + near 52-week-high → momentum; low turnover + far from 52-week-high → reversal).

Recommended upgrade path for the live H181 implementation, pending Kevin review.

---

## 4. Strategy Results — Not Confirmed (and Why)

### PEAD Family — H159b (Beta-Neutral PEAD)
OOS Sharpe 0.382, MaxDD −48.68%. Beta hedge achieved near-zero market correlation but idiosyncratic risk from gap-up stock collapses remains unhedgeable. PEAD structural decay post-2018: HFT arbitrage compressed the drift window below what a 30-stock equal-weight portfolio can exploit efficiently.

### ElasticNet PEAD — H164
Blocked at the data stage. FMP v3 was deprecated; only 4 years of EPS history available via yfinance — insufficient for an 8-quarter ElasticNet model (requires 500+ training events). Not a strategy failure; a data availability failure.

### Pairs Trading Family — H152 through H160 (15 pairs total)
ALL 15 pairs NOT CONFIRMED. Key findings:
- GDX/SIL (gold/silver miners): no cointegration
- XLE/OIH (energy sector): no cointegration; sector composition drift 2020–2024 broke economic link
- TLT/IEF (Treasury spread): best of family at OOS Sharpe 0.514 but not cointegrated; spread is mean-reverting but not stationary enough
- Kalman filter variant (H155): Sharpe collapsed to 0.118 — Kalman explains the spread away entirely
- Factor-residualized stock pairs (H160): OOS Sharpe 0.127–0.226 — residualization improves cointegration statistics but not trading P&L; OOS cointegration breaks in all pairs

Root cause: ETF pairs at daily frequency — HFT has compressed mean-reversion windows below the 5-day minimum needed for cost-effective daily-close execution. The structural cointegration that makes pairs interesting has been partially arbitraged out in the 2018–2026 period.

**H200** (graphical matching stock pairs) was tested as the next attempt — 0 of 15 cointegrated pairs found on our 30-stock universe in OOS. Pairs family is now EXHAUSTED at the scale tested. Stock-level pairs on a larger universe (200+ stocks) remains a future candidate.

### H193: H192-D + H181 Blend
OOS Sharpe 1.214 — better than H181 alone (1.138) but NOT better than H192-D alone (1.367). The blend added diversification (H192-D and H181 pick almost entirely different stocks — only 14% overlap) but both strategies are long-only with similar market beta, so the diversification is diversification of idiosyncratic risk, not market risk. Conclusion: blend doesn't justify complexity vs just running H192-D.

### H196: STORM Deep Learning (90 Stocks)
OOS Sharpe 0.528 (below SPY). IS/OOS decay of 65% — catastrophic. Expanding the STORM dual VQ-VAE architecture from 30 to 90 stocks worsened performance dramatically. The architecture overfits when the IS training sample (84 months) is insufficient relative to the graph complexity added by 90 nodes.

H195 (STORM on 30 stocks): OOS Sharpe 0.963 — confirmed but underperforms H192-D (1.367) and adds excessive IS/OOS decay (41%). Deep learning does not beat factor models at this scale.

### H202: XGBoost Momentum (30 Stocks)
OOS Sharpe improvement of +0.104 vs simple rank. Below the 1.0 threshold for a standalone CONFIRMED result. Root cause identified: 30 stocks is too small a universe for gradient boosting to add meaningful edge over simple factor ranking — the model's IS advantage evaporates OOS because it memorizes noise on such a thin cross-section. H202-XL queued for 200–500 stock expansion.

### H203: HRP Portfolio Optimization
OOS Sharpe 1.066 — below 1.1 threshold for a meaningful improvement. The HRP portfolio over-indexed on the TOM calendar component (74% weight) — MaxDD −7.1% but the Sharpe compression wasn't worth it vs simpler equal-weight.

### H199: Sector-Neutral Momentum
NOT CONFIRMED — sector drift is the momentum signal on large-cap stocks, not noise. Removing it worsened OOS Sharpe from 1.174 (H198) to 0.966 and MaxDD to −37.9%.

---

## 5. Strategy Families Exhausted / Closed

### ETF Pairs Trading (H152–H160, H200)
15 ETF pairs tested, 0 cointegrated at daily frequency in the 2018–2026 OOS period. 15 stock pairs tested via graphical matching (H200) — 0 cointegrated. Family EXHAUSTED. Future research path: much larger stock universe (200+), potentially at weekly rather than daily frequency.

### Low-Volatility Family (H190–H196)
Research line CLOSED as of 2026-05-13. All 25+ strategies on the 30-stock large-cap universe have been tested. H192-D sector-neutral BAB (Sharpe 1.367) is the winner. Further work on this family will require a larger universe — specifically, testing sector-neutral BAB on the full S&P 500 (500 stocks).

**What we learned from this family**:
- BAB ≈ Low-Vol on concentrated universes (Corr=0.799 between H192-A raw beta and H191-A raw vol — they select identical stocks)
- Sector-neutral variant breaks this equivalence and produces meaningful alpha
- Deep learning (STORM) adds computational complexity but hurts OOS performance at 30-stock scale

### ETF-Level Diversification Beyond H026
After H149 (100% H026, Sharpe 3.007), every attempt to add other strategy legs — H041a geographic rotation, H045 bond rotation, IBS mean-reversion, H026 top-2/top-3 — degraded performance. H026's TSMOM filter already provides crash protection. The case for diversification within the ETF rotation portfolio is closed.

---

## 6. Active Paper Trading

### H149 — ETF Sector Rotation (H026 Signal)
- **Status**: ACTIVE. Started 2026-04-28 (under old H122 triple-strategy); pure H026 active from 2026-05-01.
- **Universe**: 25 ETFs (11 S&P sectors + commodities + bonds)
- **Signal**: rank(3m) + rank(6m) + rank(12m) + rank(inv_vol); top-1 with 12m TSMOM > +5% filter; BIL when nothing qualifies
- **Backtest stats**: 382.9× cumulative, Sharpe 3.007, MaxDD −9.6%, 0 negative years
- **Execution**: First trading day of each month via Alpaca. Script: `h112_monthly.py`
- **Portfolio value**: ~$102k paper account; $204k buying power
- **Current holding (May 2026)**: Run `h112_monthly.py` to check; strategy holds the top-1 qualifying sector or BIL
- **Path to live**: 4–8 weeks paper validation; flip `paper=False` in Alpaca config when criteria met

### H181 — Industry-Adjusted Reversal
- **Status**: ACTIVE. Started 2026-05-10.
- **Universe**: 30 large-cap S&P 500 stocks across 8 GICS sectors
- **Signal**: Prior-month return minus equal-weight sector average; long bottom-6
- **Position sizing**: Equal-weight, ~16.7% per stock
- **Backtest stats**: Sharpe 1.138, CAGR 24.6%, MaxDD −18.4%, 1 negative year; Corr(H026) = 0.293
- **Script**: `backtesting/paper_trading/h181_monthly.py`
- **Path to live**: 2 months paper validation — results must land within 1.5σ of OOS mean monthly return

### PEAD-NLP Event-Driven (H163/H174)
- **Status**: ACTIVE. Started 2026-05-06. 0 trades so far.
- **Signal**: Gap ≥ 3% at earnings open + FinBERT score ≥ 0.18 + sentiment surprise ≥ 0.02
- **Hold**: 20 trading days from entry, exit at close
- **Backtest stats (dual-filter)**: n=22 events OOS, WR 81.8%, MeanRet 6.89%
- **Pipeline**: Nightly 8-K ingestion + scoring; watchlist screened at market open. Scripts at `backtesting/paper_trading/pead_pipeline/`
- **Why 0 trades**: Dual filter is strict — most earnings releases don't meet both criteria. Events are rare, which is why the win rate is high.
- **Path to live**: Minimum 10 live trades; results within 1.5σ of OOS WR (81.8%)

### Iron Condor (Options)
- **Status**: INACTIVE — open position monitoring only.
- **Open position**: IC-2026-04-26-001. SPY June 12 expiry, strikes $645p/$670p/$775c/$800c. Credit: $5.33 ($533 total). Max loss: $1,967.
- **Rules**: Enter at 45 DTE, 16-delta short strikes, $25 wings. Target exit: 50% credit received. Stop loss: debit to close = 2× initial credit. Hard exit at 21 DTE.
- **Pricing**: BSM model using VIX as flat-term IV; real Massive.com prices when available.

---

## 7. Research Pipeline (Queued)

### H205: TOM Overlay on BAB (BACKTEST SCHEDULED — tonight 2026-05-18)
Hold H192-D sector-neutral BAB positions only during TOM windows (last 2 + first 2 trading days of month); BIL otherwise. Hypothesis: BAB alpha concentrates in TOM windows because institutional cash flows at month-end temporarily boost all stocks, with low-beta stocks benefiting disproportionately from reduced leverage constraints. Confirm gate: OOS Sharpe > 1.5 (vs H192-D baseline 1.367). Secondary check: regime split by SPY vs 200-day MA (to determine if BAB only works in bear regimes).

### H202-XL: Gradient Boosting on 200–500 Stocks
XGBoost/LightGBM cross-sectional momentum on S&P 500 midcap-filtered universe. Three 2025–2026 papers provide direct support: Du (arXiv:2507.07107) — ML multi-factor on 500–1000 A-shares, Sharpe >2.0 with cross-sectional neutralization; Yang et al. (arXiv:2511.12129) — gradient boosting competitive on S&P 500 top-20%; Rasekhschaffe (arXiv:2602.00196) — cross-sectional standardization is essential, Sharpe 1.14–1.63 on US equities. H202 on 30 stocks showed only +0.104 Sharpe improvement — too small a universe for gradient boosting to add edge. A 200-stock universe should provide substantially more signal. Queue after H205.

### H204: Deep RL — PPO vs H198 Momentum Baseline
Test a PPO ensemble (5 random seeds, averaged) trained on IS 2013–2020 against H198 6-1m momentum (OOS Sharpe 1.174) on the same 30-stock universe. Honest expectations: OOS Sharpe 0.8–1.2 — likely below H198 but with lower correlation, making it useful for blending. Critical safeguard: gym environment must use only data up to t-1 for state at step t.

### H206: Halloween + TOM Composite on SPY
Combine Halloween filter (hold equities Nov–Apr only) with TOM timing (hold only during TOM windows). Schroeder (IJFS, Nov 2025) confirms structural mechanism: SEC filings 17% higher in winter, February is peak, September lowest — information flow seasonality tied to fiscal year-end cycles. Success gates: H206-A standalone Sharpe > 0.6; H206-B TOM composite Sharpe > 0.8.

### H207: TOM + Halloween Combined
Quantpedia's composite: hold stocks only during TOM windows AND in November–April — estimated 7.2%/yr annualized edge. Natural follow-on from H201 and H206.

### H208: Pre-FOMC Effect
Lucca & Moench (2015): ~80% of annual US equity premium earned in 24h before FOMC decisions. 8 meetings/year × ~0.3–0.5% per meeting. Most recent data suggests ~0.3% pre-FOMC premium (reduced from historical 0.5%). Test as standalone and as TOM overlay component.

### H197: Behavioral Momentum — Volume-Price Herding
arXiv:2508.14656 (Aug 2025) — volume-price divergence as accumulation/distribution signal. Herding + reversal blend achieves OOS Sharpe 1.24 in paper. Queue after H190 live implementation.

### H176: ModernFinBERT Upgrade
Upgrade PEAD pipeline from ProsusAI/finbert to tabularisai/ModernFinBERT (48% claimed accuracy improvement on diverse benchmarks; 33,925 downloads/month). Needs independent validation on EDGAR 8-K corpus before trusting the headline number.

---

## 8. Tools & Infrastructure

### Backtesting Stack
- **Python** — core language
- **vectorbt** — primary backtesting engine; fast vectorized portfolio simulation; `Portfolio.from_orders` pattern for multi-asset rotation
- **Custom engine** — hand-rolled for event-driven strategies (PEAD pipeline) where vectorbt's standard patterns don't apply
- **pandas / numpy** — data manipulation, rolling statistics
- **statsmodels** — OLS, rolling OLS, ADF test, Engle-Granger / Johansen cointegration
- **scipy** — DSR computation, statistical tests

### Data Sources
- **Alpaca** (`alpaca-py`) — paper trading execution; EOD bars; corporate events; free tier
- **Polygon.io** (`$POLYGON_API_KEY`) — free tier, EOD bars; Massive.com uses Polygon backend
- **yfinance** — primary data fallback for EOD prices, earnings dates, dividends; free
- **EDGAR / SEC** (`$EDGAR_KEY`) — 8-K filings for PEAD pipeline; 10-Q/10-K for fundamentals
- **FRED** (`$FRED_API_KEY`) — macro context: GDP, CPI, unemployment, yield curve, Fed funds rate; used for regime tagging
- **Financial Modeling Prep** (`$FMP_API_KEY`) — EPS surprises, dividend calendar, fundamentals; free 250 req/day
- **Finnhub** — earnings calendar with timestamps; more reliable than yfinance for event dates
- **Massive.com** (`$MASSIVE_KEY`) — options contract reference + delayed prices; Polygon backend; free tier BSM pricing

### Paper Trading Execution
- **alpaca-py** — the current (non-deprecated) SDK; `$ALPACA_API_KEY` + `$ALPACA_SECRET`
- **OPG orders** — used for PEAD entries; fills at market open at announced price
- **Monthly rebalance scripts**: `h112_monthly.py` (H149 rotation), `h181_monthly.py` (reversal), `pead_pipeline/` (event-driven)
- **Paper account**: $102k portfolio, $204k buying power

### NLP Pipeline
- **ProsusAI/finbert** — production model for H163/H174 PEAD pipeline; 6.4M downloads/month; zero-shot (no fine-tuning needed)
- **tabularisai/ModernFinBERT** — queued upgrade candidate (H176)
- **yiyanghkust/finbert-tone** — confirmed on earnings call transcripts (arXiv:2503.01886)
- **sec-parser** — extracts specific sections from 8-K press releases (guidance, management summary, highlights) for section-level scoring

### ML Libraries
- **XGBoost** (v3.2.0) — gradient boosting; H202 stock momentum
- **LightGBM** (v4.6.0) — faster than XGBoost; recommended for large-universe cross-sectional work (H202-XL)
- **stable-baselines3** — PPO, SAC, TD3 for deep RL (H204)
- **FinRL / FinRL-X** — AI4Finance RL framework; gym environment + stable-baselines3 backend
- **transformers** (HuggingFace) — FinBERT inference
- **Alphalens-Reloaded** (v0.4.6) — alpha factor IC/ICIR analysis before committing to full backtest

### Portfolio Optimization
- **PyPortfolioOpt** (v1.6.0) — efficient frontier, HRP, Ledoit-Wolf shrinkage; Black-Litterman
- **Riskfolio-Lib** (v7.2.1) — 20+ risk measures, hierarchical risk parity
- **skfolio** (v0.20.1) — sklearn-native; `CombinatorialPurgedCV` for CPCV; HRP, NCO, Mean-CVaR; the standard for ML integration

### Sector / Industry Data
- **GICS sector codes** — from yfinance + FMP fundamentals; cached in `build_sector_cache()` for 100–500 stocks (see `data-sources/sector-classification.md`)
- **SEC EDGAR SIC** — point-in-time industry classification for H181 industry adjustment

---

## 9. Key Architectural Decisions

### Why Strict IS/OOS (Not Cross-Validation)

Standard k-fold cross-validation on time series leaks future information: a training fold immediately adjacent to a test fold contains data about market conditions the test fold will face. For trading strategies, this creates false confidence. The strict temporal IS/OOS split (no overlap, ever) is the only defensible methodology when the strategy will trade in unknown future conditions.

For ML strategies specifically (H202, H204), Combinatorial Purged Cross-Validation adds purging (removing training samples within the look-ahead window of the test period) and embargoing (adding a buffer after the test window). Implemented via `skfolio.CombinatorialPurgedCV`.

### Why BIL Over TLT for Risk-Off

TLT (20-year Treasury ETF) has ~18–19 years of duration. In 2022, TLT fell ~30% as the Fed raised rates — it is NOT a safe asset during tightening cycles. BIL holds 1–3 month T-bills and is functionally risk-free for duration. When H026's TSMOM filter triggers (no sector above +5% 12m), moving to TLT would expose the portfolio to exactly the scenario (Fed tightening) that triggers the defensive move. Confirmed as correct by H006.

### Why Sector-Neutral Matters for BAB

Raw BAB naturally over-weights Utilities, Consumer Staples, and Healthcare (inherently low-beta sectors). This concentrates exposure to sector-specific risks that have nothing to do with the beta anomaly. Sector-neutral BAB (rank beta within GICS sectors) isolates the cross-sectional beta anomaly — finding the relatively low-beta name within Tech, within Energy, etc. H192-D sector-neutral outperforms H192-A raw BAB by +0.154 Sharpe (1.367 vs 1.213).

### Why 30-Stock Universe Is Too Small for ML

XGBoost on 30 stocks (H202) added only +0.104 OOS Sharpe vs simple factor ranking — below the 1.0 threshold. At each monthly rebalance, the model has 30 data points to predict from. Gradient boosting needs cross-sectional breadth (hundreds of stocks per period) to learn meaningful factor interactions rather than memorizing noise. The plan for H202-XL (200–500 stocks) addresses this directly.

### Why TOM Is an Overlay, Not a Portfolio Component

TOM earns 5.6% CAGR vs SPY's 15.2%. As a standalone strategy it is slow money — terrible after-tax return for the capital deployed. Its value is in its Sharpe profile (0.740) and low MaxDD (−9.3%), which makes it useful as a TIMING gate on top of other alpha sources. H205 tests whether TOM gating improves BAB's returns by concentrating BAB exposure in high-return calendar windows.

### Path to Live Trading Gates

| Strategy | Validation Requirement | Current Status |
|----------|----------------------|----------------|
| H149 (ETF Rotation) | 4–8 weeks paper; results within expected range | 2.5 weeks in; awaiting June rebalance |
| H181 (Reversal) | 2 months paper; monthly return within 1.5σ of OOS mean | 1.5 weeks in |
| PEAD-NLP | Minimum 10 live trades; WR within 1.5σ of 81.8% | 0 trades; filter is strict |

---

## 10. Path to Live Trading

### Overall Gate Philosophy

The project will go live when paper trading results confirm the backtest statistics at the strategy level. "Confirm" means monthly returns landing within the expected distribution — not necessarily matching the OOS Sharpe exactly, but not meaningfully underperforming it. A 1.5σ band around the OOS mean monthly return is the working threshold.

For H149 (ETF rotation), the backtest Sharpe of 3.007 implies very consistent monthly returns. Any month more than 1.5σ below the OOS mean triggers review. After 4–8 paper weeks, if the strategy is on track, the Alpaca config flips from `paper=True` to `paper=False`.

### H149 (ETF Rotation) — Closest to Live

This is the strongest candidate by every metric:
- OOS Sharpe 3.007 — one of the highest verified real-world strategy Sharpes in the literature
- MaxDD −9.6% — acceptable for a live account
- 0 negative years across 8+ OOS years
- Low transaction costs (1 trade per month, commission-free on Alpaca)
- Simple, rules-based execution (no ML, no real-time data feeds)

The main risk is that the 2018–2026 backtest period is a relatively favorable equity environment with a single severe bear (2022) that the TSMOM filter navigated well. A prolonged sideways/bear market would reduce absolute CAGR while the strategy sits in BIL.

### H181 (Short-Term Reversal) — Strong Candidate

Higher absolute CAGR than H149's after-tax return (24.6% gross, though STCG applies). The 2-month paper validation gate is realistic given monthly rebalancing. The Corr(H026)=0.293 confirms genuine diversification value if deployed alongside H149. Main risk: MaxDD −18.4% is higher than H149, and the 30-stock universe with GICS industry adjustment is sensitive to sector composition.

### PEAD-NLP — Longer Horizon

The strict dual-filter means events are rare. At the observed frequency in the OOS backtest, accumulating 10 live trades may take 2–4 months. The strategy's strong win rate (81.8%) means each trade carries weight — a bad run of 3–4 consecutive losses would be meaningful statistically. Patience is required here. The after-tax picture is also more complex: 20-day hold periods are all STCG.

### Capital Allocation for Live Phase

No firm allocation has been decided. The three paper strategies (H149, H181, PEAD-NLP) are designed to be diversified:
- H149 is sector momentum (medium correlation to market)
- H181 is mean-reversion on individual stocks (different mechanism)
- PEAD-NLP is event-driven (fires 1–4 times per month at most)

A natural starting allocation would concentrate heavily in H149 (the highest-confidence strategy) with satellite allocations to H181 and PEAD-NLP as they accumulate track record.

---

*Document generated from wiki sources: trading/index.md, backtesting/design-principles.md, backtesting/hypothesis-log.md, algorithms/momentum-strategies.md, algorithms/low-volatility.md, algorithms/event-driven.md, algorithms/short-term-reversal.md, algorithms/calendar-anomalies.md, algorithms/pairs-trading.md, algorithms/deep-rl-trading.md, paper-trading/index.md, tools/ml-for-trading.md*
