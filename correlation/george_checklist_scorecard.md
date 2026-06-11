# George H-Series — Retroactive Checklist Scorecard
Date: 2026-06-11 | Evaluated by: George

Legend: ✅ PASS | ⚠️ RISK/GAP | ❌ FAIL | — N/A

---

## Production Portfolio Strategies

### H041a — 19-asset ETF Rotation (Top-1 Momentum)

| Check | Status | Notes |
|-------|--------|-------|
| P1 Look-ahead guard | ✅ | Monthly signal lagged; `.shift(1)` applied in all backtests |
| P2 NLP timestamp | — | No NLP |
| P3 Cost model | ✅ | ~Monthly rebalance; 1-2 trades/month; 5bps immaterial |
| P4 Soft OOS gate | ✅ | OOS confirmed; part of combined production OOS Sharpe 4.158 |
| P5 Regime coverage | ✅ | 2004–2025; 2022 bear included |
| P6 Universe/survivorship | ✅ | 19 fixed ETFs; survivorship-bias-free by definition |
| P7 After-tax flag | ⚠️ | Pre-tax only. Monthly holds → mostly short-term gains at 37% |
| P8 Bear case | ⚠️ | Momentum crash risk (momentum strategies historically crash hard in reversals); top-1 concentration amplifies this. No fallback if ETF closes. 2022 covered but concentrated rotation barely stayed positive. |

**Sign-off:** PASS with after-tax gap

---

### H026 — 25-asset Sector+Alts ETF Rotation (Top-1)

| Check | Status | Notes |
|-------|--------|-------|
| P1 Look-ahead guard | ✅ | Monthly signal lagged |
| P2 NLP timestamp | — | No NLP |
| P3 Cost model | ✅ | Monthly rebalance; 5bps immaterial |
| P4 Soft OOS gate | ✅ | Confirmed production |
| P5 Regime coverage | ✅ | 2004–2025 |
| P6 Universe/survivorship | ✅ | 25 fixed ETFs; survivorship-bias-free |
| P7 After-tax flag | ⚠️ | Pre-tax only; short-term gains at 37% |
| P8 Bear case | ⚠️ | Same momentum crash risk as H041a. Broader universe (alts included) provides some defensive escape but 2022 alts also fell. Likely highly correlated with H041a — pending matrix confirmation. |

**Sign-off:** PASS with after-tax gap

---

### H045 — 13-asset Bond ETF Rotation (Top-2)

| Check | Status | Notes |
|-------|--------|-------|
| P1 Look-ahead guard | ✅ | Monthly signal lagged |
| P2 NLP timestamp | — | No NLP |
| P3 Cost model | ✅ | Monthly rebalance; minimal turnover |
| P4 Soft OOS gate | ✅ | Confirmed production |
| P5 Regime coverage | ✅ | 2022 bond crash is the critical stress test; strategy survived |
| P6 Universe/survivorship | ✅ | 13 fixed bond ETFs; survivorship-bias-free |
| P7 After-tax flag | ⚠️ | Pre-tax. Bond ETF income taxed as ordinary income; capital gains short-term at 37% |
| P8 Bear case | ⚠️ | Structural rising-rate risk: 2022 showed all bond ETFs fell simultaneously; strategy rotated but couldn't escape fully. If rate cycle repeats, defensive rotation has limited escape valves. Long-duration positions are most exposed. |

**Sign-off:** PASS with after-tax gap

---

### XLK IBS / SMH IBS / IGV IBS — Internal Bar Score Mean Reversion

| Check | Status | Notes |
|-------|--------|-------|
| P1 Look-ahead guard | ✅ | IBS = (close-low)/(high-low) uses same-day OHLC; entry at next open. No look-ahead. |
| P2 NLP timestamp | — | No NLP |
| P3 Cost model | ⚠️ | High turnover (daily signals). Net-of-cost Sharpe not explicitly calculated for IBS. At ~200 trades/yr × 5bps = 1% annual drag. Need explicit calculation. |
| P4 Soft OOS gate | ✅ | Confirmed production; in live paper trading |
| P5 Regime coverage | ✅ | Multi-year backtest includes 2022 |
| P6 Universe/survivorship | ✅ | 3 fixed ETFs; no survivorship bias |
| P7 After-tax flag | ❌ | **Critical gap.** Daily mean reversion = essentially all short-term gains taxed at 37% ordinary income rate. Pre-tax Sharpe is misleading for this strategy. After-tax returns likely substantially lower. |
| P8 Bear case | ⚠️ | Mean reversion fails in persistent trending markets. Strong directional moves (March 2020 crash, 2022 tech rout) produce strings of losses. Tech sector concentration means all 3 ETFs are correlated — not 3 independent bets. |

**Sign-off:** FLAG — after-tax gap is material for a daily-turnover strategy. After-tax Sharpe calculation needed before production promotion.

---

## Active Paper Trading Strategy

### H163/H174 — PEAD FinBERT (8-K NLP + EPS Surprise)

| Check | Status | Notes |
|-------|--------|-------|
| P1 Look-ahead guard | ✅ | EDGAR accession timestamp = T=0; signal fires at next market open only |
| P2 NLP timestamp | ✅ | T=0 = EDGAR ATOM feed accession timestamp. After-hours filings → next open. Intraday filings → next open (conservative). |
| P3 Cost model | ✅ | Gap trades typically 2-5%; 10bps round-trip cost is immaterial |
| P4 Soft OOS gate | ⚠️ | OOS IS confirmed (n=22, WR=81.8%). Paper trading only ~2.5 months; 60-day soft gate not yet evaluable. |
| P5 Regime coverage | ✅ | IS period spans 2022 bear + 2024 rally |
| P6 Universe/survivorship | ⚠️ | Universe = current EDGAR filers with Polygon EPS data. No point-in-time constituent tracking. Delisted companies from IS period missing from OOS — mild survivorship bias in IS Sharpe. |
| P7 After-tax flag | ⚠️ | Pre-tax. ~20-day holds → short-term gains at 37% |
| P8 Bear case | ⚠️ | FinBERT model may drift as 8-K filing language evolves. EPS surprise data depends on Polygon analyst estimates coverage — gaps exist for small-caps. EDGAR API has been reliable but has no fallback. n=22 OOS is statistically thin — WR=81.8% confidence interval is wide. |

**Sign-off:** PASS — continue paper trading; re-evaluate at 60-day mark.

---

## Summary Table

| Strategy | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | Verdict |
|----------|----|----|----|----|----|----|----|----|---------|
| H041a | ✅ | — | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | PASS w/ gap |
| H026 | ✅ | — | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | PASS w/ gap |
| H045 | ✅ | — | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | PASS w/ gap |
| XLK/SMH/IGV IBS | ✅ | — | ⚠️ | ✅ | ✅ | ✅ | ❌ | ⚠️ | FLAG — after-tax calc needed |
| H163/H174 PEAD | ✅ | ✅ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ⚠️ | PASS — monitor 60-day gate |

### Key Gaps Identified

1. **After-tax Sharpe** not calculated for any strategy — all report pre-tax. IBS is the most urgent given daily turnover.
2. **IBS net-of-cost Sharpe** not explicitly stated — need to verify daily turnover doesn't erode it.
3. **H041a/H026 correlation** — likely highly correlated (both are top-1 ETF momentum). Pending matrix.
4. **PEAD 60-day paper gate** — evaluable ~mid-July 2026.
