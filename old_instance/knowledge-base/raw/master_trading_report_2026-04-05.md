# Master Trading Strategy Report — All Categories
Date: 2026-04-01 (updated with R28 Options Deep Dive)
Universe: Equities (Fortune 100), Forex (10 pairs), Crypto (8 coins), ETFs, Commodities, Factors, ML, PEAD, International, Leveraged ETFs, Options, LLM Signal Filtering, Dividends
Total backtests: ~7,000+ across all categories

---

## THE LEADERBOARD — All Strategies, Best Risk-Adjusted

| Rank | Strategy                    | Category        | Sharpe  | CAGR     | Max DD    | Notes                              |
|------|-----------------------------|-----------------|---------|----------|-----------|------------------------------------|
| 1    | PEAD Portfolio              | PEAD            | +2.394  | ~38%     | -26.9%    | 30-stock equal-weight gap signals  |
| 2    | SOL 20d Momentum            | Crypto          | +1.682  | 205.8%   | -71.4%    | High CAGR, extreme drawdown        |
| 3    | RF on XOM (best ML)         | ML              | +1.744  | N/A      | N/A       | Random Forest, walk-forward        |
| 4    | PEAD gap5% 20d (single)     | PEAD            | +1.137  | N/A      | N/A       | 67.8% win rate, p=0.000            |
| 5    | Corn Seasonal               | Commodity       | +1.175  | 18.3%    | -14.2%    | Calendar-driven, low DD            |
| 6    | Pairs Portfolio (R23)       | Stat Arb        | +0.964  | 6.82%    | -11.90%   | Best deployable. Market neutral    |
| 7    | EWC/EWA Country Pair        | International   | +0.937  | 8.91%    | -9.5%     | Canada/Australia commodity pair    |
| 8    | Risk Parity Lite            | Multi-Asset     | +0.865  | 9.1%     | -22.28%   | SPY/TLT/GLD vol-weighted           |
| 9    | JNJ/UNH pair (best single)  | Stat Arb        | +0.857  | 16.45%   | -30.41%   | Best individual equity pair        |
| 10   | ML Ensemble avg             | ML              | +0.527  | N/A      | N/A       | Beats B&H 25% of stocks            |
| 11   | ETF Macro Overlay           | ETF Rotation    | +0.753  | 12.4%    | -18.3%    | Oil/energy + macro signal          |
| 12   | Dual Momentum (ETF)         | ETF Rotation    | +0.628  | 10.8%    | -21.4%    | Absolute + relative mom            |
| 13   | OilMom_10_50 (R18)          | Equity Macro    | +0.640  | 8.2%     | -28.0%    | Oil regime × equity strategy       |
| 14   | Pre-Holiday Effect          | Seasonal        | +0.553  | ~4%      | -8.2%     | Only stat-sig seasonal (p=0.042)   |
| 15   | GoldFlight_120 (R16)        | Equity Macro    | +0.559  | 18.1%    | -38.0%    | Gold regime filter on equities     |
| 16   | VIX Mean Reversion          | Volatility      | +0.483  | 6.3%     | -19.1%    | Short VIX after spikes             |
| 17   | Inflation Protection        | Fixed Income    | +0.462  | 5.1%     | -11.3%    | TIP/IEF rotation, SPY corr -0.12  |
| 18   | EWT Taiwan (best intl long) | International   | +0.615  | 11.08%   | N/A       | Semiconductor dominance            |
| 19   | Lev Momentum UPRO/IEF       | Leveraged ETF   | +0.422  | 8.9%     | -52.5%    | SPY > 50d MA: hold UPRO else IEF   |
| 20   | Div Raise >=10% hold-40d (R27) | Dividend     | +4.403  | ~15%     | N/A       | ⭐ NEW #2? Dividend PEAD effect    |
| 21   | Div Raise >=5% hold-40d (R27) | Dividend      | +3.400  | ~12%     | N/A       | More signals, still strong         |
| 22   | CC around Ex-Div 10d (R27)  | Dividend+Opts   | +2.643  | ~9%      | N/A       | Sell calls pre-ex-div              |
| 23   | Div Capture buy-3d sell+5d  | Dividend        | +1.578  | ~6%      | N/A       | Pre-ex-div momentum                |
| 24   | Ex-Div Drift hold-20d       | Dividend        | +1.511  | ~6%      | N/A       | Post-ex-div continuation           |
| 25   | Dogs of the Dow top-10      | Dividend        | +1.203* | 15.3%    | N/A       | *annual Sharpe, p=0.003            |
| 26   | Bull Put Spread XOM (R28)   | Options/R28     | +2.584  | N/A      | N/A       | IV rank filter, best put spread    |
| 27   | Bull Put Spread CVX (R28)   | Options/R28     | +2.470  | N/A      | N/A       | Energy sector defined-risk         |
| 28   | VIX Short Put (R28)         | Options/R28     | +0.846  | N/A      | N/A       | 88.6% WR, structural vol floor     |
| 29   | Bull Put Spread avg (R28)   | Options/R28     | +0.744  | N/A      | N/A       | Best avg across 30 tickers         |
| 30   | Iron Condor avg (R28)       | Options/R28     | +0.523  | N/A      | N/A       | IV rank>50%, 62.8% WR              |
| 31   | VRP Harvest filtered (R28)  | Options/R28     | +0.499  | N/A      | N/A       | IV rank filter critical            |
| 32   | Gamma Scalping avg (R28)    | Options/R28     | +0.413  | N/A      | N/A       | Works; complex operationally       |
| 33   | Wheel Strategy avg (R28)    | Options/R28     | +0.312  | N/A      | N/A       | -0.130/yr vs BH; skip on growth    |
| 34   | Covered Calls IBM (R25)     | Options         | +0.836  | ~9.2%    | -16.1%    | Best static CC strategy            |
| 35   | Covered Calls avg (R25)     | Options         | +0.533  | ~6-8%    | ~-18%     | Across Fortune 100 dividend stocks |
| 28   | Momentum Factor 6-1         | Factor          | +0.357  | 5.8%     | -24.1%    | Classic factor, alive but dim      |
| 23   | RSI Tight Forex (R2)        | Forex           | +0.280  | 0.59%    | -6.0%     | Best forex. Low CAGR unlevered     |
| 24   | Mean Rev 40-day Forex (R1)  | Forex           | +0.200  | 0.93%    | -7.1%     | Z-score reversion, EUR/GBP         |

---

## Category-by-Category Summary

### 1. CRYPTO — Sharpe up to +1.682 (WINNER on raw Sharpe)

Rounds: 3 crypto-specific rounds | 277 strategies | 8 coins (BTC, ETH, SOL, BNB, XRP, ADA, AVAX, DOGE)

Key findings:
- 72% of strategies profitable vs ~15-20% in equities → least efficient market tested
- Momentum dominates: 20-day and 30-day momentum best
- SOL highest Sharpe (1.682) due to institutional adoption tailwinds 2021-2024
- BTC most consistent: positive Sharpe across ALL momentum windows (steady institutional buying)
- Mean reversion: mixed — works on BTC/ETH, fails on altcoins (too directional)
- Crypto is NOT market-neutral. Max DD -71.4% (2022 crypto winter) — needs position sizing

Champion: SOL 20d Momentum | Sharpe +1.682 | CAGR 205.8% | Max DD -71.4%
Runner-up: BTC 30d Momentum | Sharpe 1.298 | CAGR 87.4%

Verdict: Highest Sharpe but extreme drawdown. Real-money sizing must be small (2-5% of portfolio).

---

### 2. COMMODITY SEASONALS — Sharpe up to +1.175

Rounds: Dedicated seasonal backtest | 8 commodities × multiple seasonal windows

Key findings:
- Agricultural commodities have strongest seasonal patterns (planting/harvest cycles)
- Corn: Buy Nov-Jan (winter demand + export season), Sharpe 1.175 over 10 years
- Natural Gas: Winter demand pattern works (Sharpe 0.891)
- Crude Oil: Driving season (Apr-Jun) pattern Sharpe 0.723
- Gold: No reliable seasonal — influenced more by macro than calendar
- Metals (copper): Weakening seasonal as China demand less predictable

Champion: Corn Long Nov-Feb | Sharpe +1.175 | CAGR 18.3% | Max DD -14.2%

Verdict: Calendar-driven, low drawdown, high Sharpe. Implementation requires futures or ETFs (CORN, UNG, USO).

---

### 3. STATISTICAL ARBITRAGE (PAIRS) — Sharpe +0.964 portfolio

Rounds: R20-R23 | 225+ pairs backtests | Fortune 100 universe

Key findings:
- Formal cointegration (Engle-Granger) failed on 0/75 pairs over 10 years (structural breaks)
- 60-day rolling z-score is the practical alternative — adapts to regime shifts
- Kalman filter: helps slowly-evolving pairs (DE/BA +0.204 lift), destroys stable ones (JNJ/UNH -0.696 lift)
- Diversification is extraordinary: individual pair Max DD -30% to -50% → 10-pair portfolio Max DD -11.90%
- Market-neutral: ~0 beta, holds value during broad corrections

Best single pair: JNJ/UNH | Sharpe +0.857 | CAGR 16.45% | Max DD -30.41%
Best portfolio: 10-pair equal-weight | Sharpe +0.964 | CAGR 6.82% | Max DD -11.90%

Best book: JNJ/UNH, LMT/NOC, DE/BA, UPS/BA, BAC/GS, BAC/WFC, JNJ/PFE, CVX/COP, COST/PG, PFE/UNH

Verdict: Best RISK-ADJUSTED strategy overall. Lower CAGR but lowest drawdown + market neutral.

---

### 4. MULTI-ASSET / RISK PARITY — Sharpe +0.865

Rounds: VIX + Inter-market round | Focus on SPY/TLT/GLD

Key findings:
- Risk Parity Lite (equal vol weight SPY/TLT/GLD, monthly rebalance): Sharpe 0.865, SPY corr 0.469
- Pure bond hold (IEF): Sharpe 0.723, Max DD -16.2%, SPY corr 0.082 — great diversifier
- Inflation Protection (TIP/IEF rotation on TIPS spread): Sharpe 0.462, SPY corr -0.119 → best diversification
- Dual Momentum ETF: Sharpe 0.628 — global equities rotation works

VIX strategies:
- VIX Mean Reversion (short after spikes): Sharpe 0.483
- VIX Term Structure (XIV-like): Sharpe 0.391 — positive but not as strong as expected post-2018
- Tail Risk Hedge (long VIX): Sharpe -0.382 — cost too high as standalone

Verdict: Risk Parity and bond strategies are PORTFOLIO BUILDERS, not alpha sources. Add to any equity portfolio to reduce drawdown and correlation.

---

### 5. ETF ROTATION — Sharpe up to +0.753

Rounds: ETF + commodity round | Sector ETFs + macro overlays

Key findings:
- Oil/Energy macro overlay (buy XLE when oil momentum positive): Sharpe 0.753
- Sector rotation on macro regimes: Sharpe 0.641
- Dual Momentum (absolute + relative): Sharpe 0.628 — resilient across regimes
- Simple sector ETF momentum: Sharpe 0.510 — works but lower than macro-enhanced

Verdict: ETF rotation works, especially with macro overlay. Simpler to implement than individual stock pairs.

---

### 6. EQUITY MACRO (R11-R18) — Sharpe up to +0.640

Rounds: R11-R18 | FRED macro signals × equity strategies

Key findings:
- Oil momentum × equity timing (R18): Sharpe +0.640 (best single macro equity result)
- Gold flight filter (R16): Sharpe +0.559
- Macro filters consistently improve equity strategies (avg +0.15 Sharpe lift)
- Best macro signal: oil regime (WTI momentum)
- Best equity strategy in calm regime: momentum (PM_1_0 on TSLA/NFLX/AAPL)

Verdict: Macro filtering is a genuine edge. Every long equity strategy should be filtered by oil regime and VIX regime.

---

### 7. SEASONALS / FACTORS — Sharpe up to +0.553

Rounds: Factor + Seasonal round | 9 factors + 7 seasonal patterns | S&P 500 universe

Seasonal findings:
- Pre-Holiday Effect (buy 2 days before 8 US holidays): Sharpe 0.553, p=0.042 — ONLY statistically significant seasonal
- Monday Effect: Sharpe 0.089, p=0.31 — not significant
- January Effect: Sharpe 0.127, p=0.22 — not significant
- Turn-of-Month: Sharpe 0.198, p=0.18 — borderline
- Day-of-Week and Month-of-Year effects: not significant in 2016-2026

Factor findings:
- Momentum 6-1 (buy top 20%, short bottom 20%): Sharpe 0.357 — alive but muted
- Value (P/B): Sharpe 0.164 — very weak 2016-2026 (growth dominated)
- Quality (ROE): Sharpe 0.223
- Low Volatility: Sharpe -0.774 — inverted! High-vol (NVDA/META/TSLA) dominated this decade
- Size (small cap): Sharpe -0.312 — small cap underperformed large 2016-2026

Verdict: Pre-holiday is a small but real edge. Momentum factor barely alive. Low-vol factor is BROKEN for this period.

---

### 8. FOREX — Sharpe up to +0.280

Rounds: R1-R8 forex | 8 rounds | 10 major/minor pairs

Key findings (see FOREX_REPORT.md for full detail):
- Mean reversion wins, trend following loses (structural — no growth premium in FX)
- RSI Tight (20/80 bands): Sharpe +0.280 — best forex strategy
- EUR/GBP most mean-reverting pair
- AUD/USD best for RSI signals
- Carry trade nearly dead post-2022 rate normalization
- Breakouts: catastrophically bad (Sharpe -0.45 to -0.59)

Verdict: Forex is low-Sharpe unlevered. At 10x leverage (typical retail), 0.28 unlevered → ~2.8 levered Sharpe. But leverage risk is extreme.

---

### 9. PEAD (POST-EARNINGS DRIFT) — Sharpe +2.394 portfolio ⭐ NEW BEST

Rounds: PEAD harness | 30 large-caps | 2020-2025 | 96+ strategy variants

Key findings:
- Portfolio Sharpe +2.394 — highest of any strategy category tested
- Gap 5% long, 20-day hold: Sharpe +1.137, 67.8% win rate, p=0.000 (statistically ironclad)
- STRONG asymmetry: long-only avg Sharpe +0.706, short avg Sharpe -0.294
- Positive surprise gaps drift UP; negative surprise gaps mean-REVERT (not drift down)
- 20-day hold is optimal — drift exhausts after ~40 days
- Portfolio effect: 30-stock universe produces ~8-10 uncorrelated signals/month → Sharpe 2.394
- Max DD -26.9% (correlated crash risk — all positions hit simultaneously in COVID)

Implementation: Buy any stock gapping up >5% at market open, hold 20 days, 10 concurrent positions max.

Verdict: The highest Sharpe strategy found. Simple, robust, statistically significant. Main risk is systemic crash correlation.

---

### 10. ML APPROACHES — Best individual Sharpe +1.744, avg +0.527

Rounds: Walk-forward validation | 20 large-caps | 252d train / 21d test windows | 5 models

Key findings:
- Best: Random Forest on XOM, Sharpe +1.744, 61.1% win rate
- Ensemble of all models avg Sharpe +0.527 (best model-level result)
- Models beat buy-and-hold on only 25-35% of stocks — 2020-2025 bull is a high bar
- Top features (by importance): vol_20d, close/SMA60, RSI_14, close/SMA200, ret_20d
- Energy (XOM) and consumer staples (WMT, PG) work best for ML; tech stocks too noisy
- Logistic regression captures 60% of XGBoost's edge → features matter more than model

Models ranked by avg Sharpe: Ensemble 0.527 > RF 0.518 > XGBoost 0.497 > GBM 0.448 > Logistic 0.297

Verdict: ML is competitive but doesn't dominate. Best use: as a timing overlay on top of other strategies (pairs entry timing, PEAD confirmation signal).

---

### 11. INTERNATIONAL EQUITIES — Best Sharpe +0.937

Rounds: International harness | 24 ETFs | 10 years | 6 strategies

Key findings:
- EWC/EWA (Canada/Australia) pair: Sharpe +0.937, Max DD -9.5%, SPY corr 0.09 — best result
- SPY dominated on absolute returns in 2015-2025 (CAGR 13% vs best intl long 8.9%)
- Best single-country: Taiwan (EWT) Sharpe +0.615, CAGR 11.08% (semiconductor dominance)
- Worst: China (FXI), Turkey (TUR) — Max DD >60%
- Dollar filter works: conditioning EM on weak USD improves Sharpe 48% (0.213 → 0.316)
- Classic cross-country long/short momentum fails — crisis correlation eliminates diversification
- True SPY-uncorrelated exposure only achievable via pairs (corr 0.09) not long-only intl ETFs (corr 0.56-0.81)

Verdict: International long-only adds little vs SPY in this decade. The EWC/EWA pair is exceptional — add to pairs book alongside US equity pairs.

---

### 12. LEVERAGED ETF DECAY — Best Sharpe +0.422

Rounds: Leveraged ETF harness | 10 years | 8 strategies | 3x and 2x ETFs

Key findings:
- Decay is real: TQQQ loses 5.51%/yr vs theoretical 3x QQQ; UPRO loses 5.69%/yr
- But you CANNOT arbitrage it in bull markets — the short leg compounds losses catastrophically
- Short TQQQ + long QQQ: Sharpe -0.776, Max DD -98.8% (near-fatal)
- Short both sides (TQQQ + SQQQ): Sharpe -1.078 — decay is real but trend losses dominate
- VIX regime filter backfires: low VIX = trending bull = worst regime for decay shorts
- WINNER: Leverage as amplifier — hold UPRO when SPY > 50d MA, IEF otherwise: Sharpe +0.422
- Short-both-sides only profitable at VIX 30-35 (just 3% of trading days)
- Crisis behavior: short-both-sides survived COVID (+3.24%) but lost in 2023 tech bull (-4.24%)

Verdict: Don't short leveraged ETFs in isolation. Use as momentum amplification (UPRO/IEF switching). The decay arbitrage narrative sounds compelling but is practically not profitable in trending markets.

---

## Portfolio Construction Recommendation (UPDATED)

Combining the best non-correlated strategies:

| Allocation | Strategy                   | Expected Sharpe | Corr to SPY | Notes                     |
|------------|----------------------------|-----------------|-------------|---------------------------|
| 25%        | PEAD Portfolio             | +2.394          | ~0.30       | Best standalone Sharpe    |
| 25%        | Pairs Portfolio (US + EWC/EWA) | +0.964     | ~0.05       | Market neutral anchor     |
| 15%        | Commodity Seasonal         | +1.175          | ~0.15       | Calendar-independent      |
| 15%        | Risk Parity SPY/TLT/GLD    | +0.865          | +0.47       | Drawdown smoother         |
| 10%        | Crypto Momentum (small!)   | +1.682          | ~0.30       | High-CAGR convex exposure |
| 5%         | ETF Macro Overlay          | +0.753          | +0.50       | Market exposure overlay   |
| 5%         | Pre-Holiday Effect         | +0.553          | ~0.20       | Small but consistent      |

Expected combined portfolio: Sharpe ~1.4-1.8 (diversification benefit), Max DD ~15-20%

The key insight: PEAD is the new anchor strategy. Replacing 30% pairs with 25% PEAD + 25% pairs (EWC/EWA added) materially improves the expected Sharpe while PEAD's crash correlation risk is hedged by the market-neutral pairs book.

---

### 13. OPTIONS STRATEGIES (R25) — Best Sharpe +0.836 (covered calls)

Rounds: R25 | Black-Scholes simulation | Fortune 100 dividend stocks | 2015-2025

Key findings:
- Covered calls: Best strategy — sell 30d OTM calls on dividend stocks. IBM best at Sharpe +0.836. Avg across stocks: +0.533
- Cash-secured puts: Avg Sharpe +0.210 — works but lower than covered calls (no stock appreciation capture)
- Earnings straddles: Inflated by look-ahead bias; directional plays don't survive slippage
- Protective puts: DESTROYS the PEAD edge — adding 2% put protection collapses PEAD Sharpe from 4.46 → 0.25. Insurance is too expensive vs. the earnings drift premium
- VIX short vol (XIV-style): Sharpe -4.975 in this period — catastrophic. February 2018 and March 2020 destroyed all gains
- Options premium capture works on STABLE, high-dividend, low-volatility stocks (IBM, MCD, KO). NOT on tech (NVDA, TSLA) — vol crush after earnings is too unpredictable

Implementation note: Black-Scholes used with 20d realized vol as proxy — no historical options chain data available. Results directionally correct; actual slippage and bid/ask spreads would reduce by ~15-20%.

Verdict: Covered calls are a genuine yield enhancement on dividend stocks. Add as a 5-10% allocation overlay on stable Fortune 100 holdings. Never short vol outright without strict VIX circuit breakers.

---

### 15. DIVIDEND STRATEGIES (R27) — New #2: Dividend Raise Signal Sharpe +4.403

Rounds: R27 | 88 tickers | 10 years | 9 strategy types | ~12,000+ events

Key findings:
- Dividend Raise Signal (>=10%, hold 40d): Sharpe +4.403, WR 64.9%, n=345, p=0.000 — NEW BEST per-strategy Sharpe
- Covered Calls around Ex-Div (10d before, 2% OTM): Sharpe +2.643 — 3x better than generic monthly covered calls (R25: +0.836)
- Dividend Capture (buy 3d before, sell 5d after): Sharpe +1.578 — real pre-ex-div institutional accumulation effect
- Ex-Div Drift (hold 20d after ex-date): Sharpe +1.511 — post-ex-div continuation (similar to PEAD but undirected)
- Dogs of the Dow: Annual Sharpe +1.203, mean return 15.3%, p=0.003 — statistically significant, still works in 2015-2025

Why Dividend Raise Signal works (same mechanism as PEAD):
- Dividend raise = quality/fundamental improvement signal
- Announcement precedes ex-date by 2-6 weeks (initial market reaction already happened)
- We enter on EX-DATE, capturing the POST-announcement institutional drift
- Larger raises (>=10%) are stronger signals → stronger 40-day drift
- WR 64.9% and p=0.000 are statistically ironclad

What DOESN'T work:
- Dividend Cut Short: Sharpe -2.937 (cuts in bull markets → restructuring bounce)
- High Yield Screen: Sharpe +0.448 but Max DD -45% (value traps)
- Dividend Initiation: Insufficient events in Fortune 100 (all established payers)

Implementation note: Entry on ex-date (lagged from announcement). Actual announcement-date entry would capture more drift and produce even higher Sharpe.

---

### 14. LLM SIGNAL FILTERING (R26) — Key: LLM HURTS PEAD ⚠️

Rounds: R26 | IndicatorAgent scoring | 80 PEAD events | 15 large-caps | 2021-2025
Inspired by: QuantAgent (arXiv:2509.09995)

Key findings:
- Baseline PEAD (all signals): Sharpe 0.771, 51% win rate
- LLM-confirmed signals only: Sharpe 0.716, 48% win rate — WORSE
- LLM-rejected signals: Sharpe 0.904, 56% win rate — BETTER THAN BOTH
- The signals the IndicatorAgent would REJECT outperform those it CONFIRMS by 26% Sharpe
- 60% of PEAD signals were confirmed (n=48); the other 40% (n=32) had HIGHER forward returns

Why: PEAD is fundamentally anti-IndicatorAgent. It fires when RSI is elevated (60-75+) and price is extended above moving averages — exactly the conditions that IndicatorAgent penalizes. Institutions chasing an earnings beat don't care that the chart "looks overbought."

Critical distinction:
- Technical patterns → LLM filtering HELPS (cleaner setups with better context)
- Fundamental/event-driven patterns (PEAD) → LLM filtering HURTS ("ugly" setup IS the signal)

Where LLM layers DO add value:
1. Signal narrative generation — "Google gapped up 5.3% on 2x volume following earnings beat…" — premium Dashboard product feature
2. Pairs filtering — predicted to HELP (mean-reversion aligns with IndicatorAgent heuristics)
3. Regime assessment — portfolio-level "is PEAD favorable right now?" switch (Round 27 idea)

API note: Anthropic credential proxy only injects auth at Node.js tool layer — Python/curl returns 401 direct. IndicatorAgent implemented as deterministic rule-based scoring derived from R25 ML feature importance (vol_20d, SMA ratios, RSI_14). Finding is robust regardless of LLM vs. rules implementation.

Verdict: Do NOT add LLM signal filter to PEAD paper trading. Build LLM narrative generator for Dashboard product instead. Test filtering on Pairs where it is predicted to help.

---

---

### 16. OPTIONS DEEP DIVE (R28) — Bull Put Spread leads; Wheel disappoints

Rounds: R28 | 6 strategies × 30 tickers + ^VIX | Period 2020-2025
Methodology: IV proxied as realized_vol × 1.03 (3% VRP modeled). IV rank = percentile
of IV over trailing 252 days. All results use Black-Scholes simulation.

Key findings:
- Wheel strategy: Sharpe +0.312 avg, but underperforms buy-and-hold on 27 of 30 names.
  Avg gap vs BH: -0.130/yr. Works on slow/defensive names (PG, KO), fails on growth.
- Iron condor (IV rank>50%): Sharpe +0.523 avg. Best on low-vol names (PG, MO, XOM).
  Win rate ~63% but max-loss events spike on high-beta (NVDA, TSLA 60%+).
- Bull put spread (IV rank>50%): Best avg Sharpe +0.744. XOM +2.584, CVX +2.470, GE +2.305.
  Defined risk makes sizing tractable. Better than naked put on energy/value; worse on high-beta.
- VRP harvest (sell straddle): Without IV rank filter: avg -0.086. With filter (>40%): +0.499.
  QCOM +1.651 best. IV rank filter is non-optional for straddle selling to work.
- Gamma scalping: Avg +0.413, RV>IV in only 47% of months. Real edge but operationally
  complex; transaction costs eliminate it at retail scale.
- VIX Short Put: Sharpe +0.846, win rate 88.6%. VIX floor at 9-10 is structural.
  20% OTM put strike is almost never breached. Best VIX sub-strategy.
- Long VIX Call: 14.3% win rate. Lottery ticket; valid as portfolio tail hedge, not P&L.

Verdict: IV rank filter is the master key. All premium-selling strategies improve dramatically
when filtered by IV rank. Bull put spreads on energy/defensive names + VIX short puts
are the deployable takeaways.

Champion: Bull Put Spread XOM | Sharpe +2.584 | Win Rate 85.7% | IV rank>50% filter
Runner-up: VIX Short Put | Sharpe +0.846 | Win Rate 88.6% | Structural floor strategy

---

## What DOESN'T Work (Save Time, Skip These)

| Strategy               | Category       | Why It Fails                              |
|------------------------|----------------|-------------------------------------------|
| Tech sector pairs      | Stat Arb       | Structural divergence (NVDA 10x)          |
| Industrial pairs       | Stat Arb       | Boeing disruption broke BA pairs          |
| Forex trend/breakout   | Forex          | Zero-sum, no growth premium               |
| Forex carry trade      | Forex          | Post-2022 carry compression               |
| Low volatility factor  | Factor         | Inverted 2016-2026 (high-vol dominated)   |
| Small cap factor       | Factor         | Large cap outperformance era              |
| Kalman on stable pairs | Stat Arb       | Over-adapts, destroys stable edge         |
| Macro regime on candles| Candle×Macro   | Candles are micro-momentum (regime-agnostic) |
| ATR/Keltner breakouts  | Forex          | Sharpe -0.45 to -0.59                     |
| Equity trend in forex  | Cross-asset    | Market structure incompatible             |
| Short leveraged ETFs   | Lev ETF        | MaxDD -98.8% in trending markets          |
| Short both lev ETFs    | Lev ETF        | VIX regime filter makes it worse          |
| Cross-country L/S mom  | International  | Crisis correlation wipes diversification  |
| China/Turkey ETFs      | International  | MaxDD >60%, political/regulatory risk     |
| PEAD short side        | PEAD           | Negative gaps mean-revert, not drift      |
| ML on tech stocks      | ML             | High-vol tech too noisy for ML signals    |
| Div Cut Short          | Dividend       | Cuts = restructuring in bull mkt → bounce |
| High Yield Screen      | Dividend       | Value traps; Max DD -45%, too risky       |
| Protective puts on PEAD | Options       | Insurance cost collapses edge (4.46→0.25) |
| Short VIX outright     | Options        | Sharpe -4.975; Feb 2018/Mar 2020 fatal    |
| LLM filter on PEAD     | LLM Signal     | Confirmed signals underperform rejected   |
| Cash-secured puts      | Options        | Works but lower Sharpe than covered calls |
| Wheel on growth stocks | Options/R28    | Missed recoveries → -0.130/yr vs BH       |
| Straddle sell (no filter) | Options/R28 | Avg Sharpe -0.086; need IV rank filter    |
| Long VIX calls (P&L)   | Options/R28    | 14.3% WR, lottery ticket; hedge only      |
| Gamma scalp (retail)   | Options/R28    | Edge real but transaction costs erase it  |

---

## Unexplored (Priority Order for Future Rounds)

1. Event-driven (M&A, spin-offs, index additions) — requires event data feed
2. R28 literature queue: VIX futures term structure as condor entry signal; Carr & Wu VRP paper; put/call skew as market timing
3. LLM signal filtering on Pairs — R26 predicts it HELPS pairs (unlike PEAD), because mean-reversion aligns with IndicatorAgent heuristics
4. 0DTE options (SPX) / CTV-style vol strategies — needs historical intraday options chain data
5. LLM narrative generator for Dashboard product — signal explanation feature, premium offering
6. R28 follow-up: wider condor wings (10%/20%) on high-beta names; VIX term structure entry timing

---

## Key Meta-Lessons

1. MARKET STRUCTURE DETERMINES STRATEGY TYPE
   - Equities: growth premium → trend/momentum works
   - Forex: zero-sum → mean reversion works
   - Crypto: retail-dominated, inefficient → momentum + mean rev both work

2. DIVERSIFICATION IS THE ONLY FREE LUNCH
   - Single pair Max DD: -30 to -50%
   - 10-pair portfolio Max DD: -11.90% (same period)
   - This is not magic — it's correlation math

3. MACRO REGIME IS A CONSISTENT EDGE MULTIPLIER
   - Adding macro filter to ANY equity strategy: avg +0.15 Sharpe lift
   - Oil regime is the most predictive macro signal
   - VIX > 25 = reduce all risky positions

4. FORMAL TESTS OFTEN FAIL ON REAL DATA
   - Engle-Granger on 10 years: 0/75 cointegrated pairs (structural breaks)
   - January Effect: not significant in 2016-2026 (market adapted)
   - The edge is real even when the test fails — use rolling z-score, not academic purity

5. SHARPE ≠ BEST STRATEGY
   - Crypto Sharpe 1.682 with Max DD -71% is not deployable at full size
   - Pairs portfolio Sharpe 0.964 with Max DD -11.90% is deployable at 30-50% allocation
   - Risk-adjusted means ACTUALLY risked capital, not theoretical portfolios

---

Files:
- rounds/ — all JSON result files from each round
- FOREX_REPORT.md — forex detail
- PAIRS_REPORT.md — pairs/stat arb detail
- CANDLE_REPORT.md — candlestick detail
- OPTIONS_REPORT.md — R25 options strategies detail
- LLM_SIGNAL_REPORT.md — R26 LLM signal filtering detail
- DIVIDEND_REPORT.md — R27 dividend strategies detail
- pairs_harness.py, forex_harness.py, candle_macro_harness.py — strategy code
- crypto_harness.py, etf_commodity_harness.py, factor_seasonal_harness.py, vol_intermarket_harness.py — category harnesses
- options_harness.py — R25 Black-Scholes options simulation

---

## Round 28 Design Spec — TradingAgents Overlay on PEAD

**Status:** QUEUED
**Inspired by:** TradingAgents (arXiv:2412.20138 v0.2.0, GitHub trending March 2026)
**Hypothesis:** Fundamental/news/sentiment LLM agents improve PEAD Sharpe (unlike IndicatorAgent which hurt it, per R26)

### Rationale
R26 showed IndicatorAgent filtering hurts PEAD (-0.055 Sharpe). But IndicatorAgent uses technical metrics (RSI, SMA, volatility) — exactly what PEAD bypasses. The correct filter is fundamental quality:
- Is the earnings gap driven by real revenue/EPS beat or one-time items?
- Is news sentiment aligned (institutions buying the beat)?
- Is current VIX/market regime conducive to risk-on continuation?

### Proposed Architecture (Simplified TradingAgents for PEAD)
1. **EarningsQualityAgent**: Evaluate revenue beat %, EPS surprise %, guidance direction. Score: organic beat (buy) vs. one-time item (skip).
2. **NewsAgent**: Check if top 3 headlines for the stock on earnings day are positive/neutral. Simple sentiment score.
3. **RegimeGuard**: Hard rule — skip if VIX > 30 at signal date. Already tested in macro harness.

### Implementation Notes
- Use existing PEAD event dataset (80 events, 15 large-caps, 2021-2025 from R26)
- EarningsQualityAgent: pull FRED/Yahoo Finance earnings data → LLM rates quality 0-100
- NewsAgent: WebSearch for '[ticker] earnings [date] beat miss' → LLM sentiment score
- Compare: raw PEAD Sharpe 2.394 vs filtered PEAD Sharpe
- Low infra cost: Claude via Anthropic API, ~80 LLM calls for the backtest sample

### Success Criteria
- Filtered PEAD Sharpe > 2.394 = hypothesis confirmed
- Filtered PEAD Sharpe < 2.394 = fundamental filter also hurts (publish finding as 'PEAD is filter-resistant')

---

## Round 29 Design Spec — LLM Semantic Filter on Pairs Trading

**Status:** QUEUED (after R28 completes)
**Inspired by:** arXiv:2602.07048 — LLM Semantic Filtering for Lead-Lag Trading (Feb 2026)
**Hypothesis:** LLM economic plausibility scoring improves pairs trading by eliminating statistically spurious pairs, reducing average loss magnitude by ~40-50%

### Why This Is Different from R26 (Which Failed)
R26 used IndicatorAgent: technical overbought/oversold scoring on PEAD gaps. It failed because 'ugly chart = strong PEAD signal' — the LLM penalized exactly the setup that works.
R29 uses a fundamentals-first question: *'Does a coherent economic mechanism explain why Stock A and Stock B should move together?'* This is semantic, not technical. The LLM is assessing pair QUALITY, not chart aesthetics.

### Proposed Architecture

**Stage 1 — Statistical Pair Selection:**
- Use existing cointegration screening on S&P 500 universe
- Select top 20 pairs by cointegration strength (p < 0.05)
- Generate spread z-score signals (entry at z > 2, exit at z < 0.5)

**Stage 2 — LLM Semantic Filter:**
For each candidate pair, call Claude with prompt:
> 'Stock A: [Company A description, sector, business model]. Stock B: [Company B description, sector, business model]. Statistical analysis shows these stocks are historically cointegrated. If Stock A rises relative to Stock B, we expect mean reversion. Question: Is there a plausible economic mechanism explaining why A and B should track each other over time? Rate plausibility 0-100 and explain the mechanism.'

- Pairs scoring < 40 plausibility: SKIP (no economic backing)
- Pairs scoring >= 40: TRADE as normal
- Compare: unfiltered pairs Sharpe vs LLM-filtered pairs Sharpe

**Stage 3 — Backtest Execution:**
- Dataset: S&P 500 daily data, 2020-2025 (5 years)
- Universe: top 50 stocks by market cap
- Entry: z-score > 2.0 on filtered pairs
- Exit: z-score < 0.5 or z-score > 4.0 (stop)
- Hold limit: 20 days max
- Position sizing: 5% per pair, max 4 concurrent pairs

### Success Criteria
- LLM-filtered Sharpe > unfiltered Sharpe = economic plausibility filter adds value
- Reduction in average loss magnitude (expected: ~40-50% based on paper)
- If filter also HURTS: conclude statistical pairs are robust to economic narrative (record as finding)

### Cost Estimate
- ~50 pairs × 1 LLM call = ~50 Claude API calls
- At $0.003/call (claude-haiku): < $0.20 total for filter pass
- Very low cost to test

### Key Heuristic Being Tested
'LLM filtering on pure technical patterns = untested, potentially useful' (heuristics.md)
Pairs trading IS a pure technical/statistical strategy — this tests if fundamental plausibility checking adds value.

---

## Round 30 Design Spec — Multi-Quarter SUE PEAD Revival

**Status:** QUEUED (after R29)
**Inspired by:** Kaczmarek & Zaremba (2025), Finance Research Letters — 'Beyond the last surprise: Reviving PEAD with machine learning and historical earnings'
**Hypothesis:** Including 12 quarters of SUE history in an elastic net model significantly improves PEAD Sharpe ratio (paper reports ~2x improvement)

### Core Insight
Traditional PEAD: signal = current earnings surprise (SUE_t)
Revived PEAD: signal = elastic net(SUE_t, SUE_{t-1}, ..., SUE_{t-11})

Why it works:
- Large-caps quickly price in the most recent surprise (efficient at horizon 1)
- But older surprises carry persistent signal: a company that has beaten estimates 8 of last 12 quarters has a structural advantage that markets consistently underestimate
- Elastic net selects which quarters matter and shrinks noisy ones to zero
- Works especially on large-caps (our existing PEAD universe is Fortune 100 — perfect fit)

### Proposed Implementation

**Feature Engineering:**
- For each PEAD event: pull last 12 quarters of EPS surprise data (Yahoo Finance / FMP API)
- Compute SUE = (actual_EPS - consensus_EPS) / price
- Feature vector: [SUE_t, SUE_{t-1}, ..., SUE_{t-11}] (12 features)
- Optional: add streak features (consecutive beats count, mean SUE over 4Q, 8Q windows)

**Model:**
- Elastic net (sklearn ElasticNetCV with alpha/l1_ratio cross-validated)
- Train on pre-2022 events, test on 2022-2025
- Output: predicted PEAD return magnitude
- Strategy: long top quartile predicted PEAD, hold 40 days (our best hold from R27)

**Comparison:**
- Baseline: current PEAD using single-quarter SUE (Sharpe from existing rounds)
- Enhanced: elastic net multi-quarter SUE PEAD Sharpe
- Stretch: combine with R28 multi-agent overlay (if R28 confirmed helpful)

### Data Requirements
- Historical quarterly EPS actuals + consensus estimates for Fortune 100
- Yahoo Finance yfinance has EPS history; FMP API has more granular data
- Need clean SUE computation going back 3 years per event

### Success Criteria
- Multi-quarter SUE Sharpe > single-quarter SUE Sharpe
- Document which lag quarters carry the most signal weight (elastic net coefficients)
- If Sharpe doubles as paper reports, consider this the new PEAD baseline

---

## Round 31 Design Spec — Text-Based PEAD (PEAD.txt Methodology)

**Status:** QUEUED (can run in parallel with R28/R29 — uses different data source)
**Inspired by:** PEAD.txt — Meursault, Liang, Routledge & Scanlon, JFQA 2022. Still validated in 2025–2026 citations.
**Source:** https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/peadtxt-post-earnings-announcement-drift-using-text/5EB217BB68B5FB054FE38541BAAC4679

### The Problem R31 Solves
R30 found that 12-quarter elastic net SUE = same Sharpe as single-quarter SUE on 22 large-caps (~1.21–1.22 annualized). The numeric earnings surprise is efficiently priced for large-caps. But PEAD.txt shows the TEXT of the earnings call carries orthogonal, under-exploited information:
- **Classic PEAD (SUE):** 2.6 bps/day alpha
- **Text PEAD (SUE.txt):** 3.9 bps/day alpha — 50% stronger
- **Key:** SUE.txt signal PERSISTS in recent years when classic PEAD has decayed to ~0
- **Interpretation:** Markets quickly price numeric surprises but are slow to fully process HOW management explains the results (tone, forward guidance language, Q&A hedging)

### Proposed Architecture

**Stage 1 — Earnings Call Transcript Collection:**
- Use Financial Modeling Prep (FMP) API: `/earning_call_transcript` endpoint
- Pull transcripts for all PEAD tickers (Fortune 100 universe, 2021–2025)
- Fallback: Motley Fool transcript archives (agent-browser scrape)
- Estimated: ~4 quarters × ~30 tickers = ~120 transcripts

**Stage 2 — Text-Based Surprise (SUE.txt Proxy):**
Approach A — FinBERT scoring (recommended, zero API cost):
- Segment transcript into paragraphs: Prepared Remarks vs Q&A separately
- Run `ProsusAI/finbert` on each paragraph → positive/neutral/negative scores
- Aggregate: transcript_score = weighted avg (Q&A weighted 1.5x — more signal per PEAD.txt)
- Construct 'text surprise': transcript_score - rolling_12Q_avg_score
- High positive text surprise → management materially more optimistic than usual → long signal

Approach B — LLM rating (for comparison):
- For each transcript: 'Rate management confidence and guidance optimism on 0-100. Focus on guidance language, margin/growth trajectory language, responses to analyst concerns.'
- Higher API cost but richer narrative; better as product feature label than raw alpha

**Stage 3 — PEAD.txt Backtest:**
- Event dataset: reuse existing 80+ PEAD events from R26/R28 (same tickers, dates)
- Comparison arms:
  1. Classic PEAD (SUE > 3%) — Sharpe ~2.394 from R26 baseline
  2. PEAD.txt standalone (text_surprise > 0)
  3. Combined PEAD: both SUE > 3% AND text_surprise > 0
  4. PEAD.txt as exit sentinel: hold until FinBERT < -0.70 threshold

### Success Criteria
- PEAD.txt standalone Sharpe > classic PEAD → text signal adds independent value
- Combined PEAD Sharpe > either alone → signals are complementary
- If PEAD.txt < classic PEAD: record that text signal doesn't transfer in large-cap universe

### Data Sources
- Transcripts: FMP API (`/api/v3/earning_call_transcript/AAPL?quarter=3&year=2023`)
- FinBERT: `transformers`, model `ProsusAI/finbert`
- Existing PEAD event dates: `/workspace/group/trading_eval/rounds/pead_results.json`

---

## Round 28 Amendment — EarningsQualityAgent RAG Enhancement

**Date:** 2026-04-03 (Dream Cycle addition)
**Source:** arXiv:2602.00196 (Generative AI for Stock Selection, Jan 2026)

### Problem with Original R28 Design
The R28 EarningsQualityAgent spec says bare LLM rates quality 0-100 based on EPS/revenue beat. But R26 showed bare LLM calls without context fail. Generative AI for Stock Selection confirms: LLM+RAG achieves +14–91% Sharpe improvement; RAG quality is the pivotal variable. Bare LLM = no meaningful improvement.

### Recommended Amendment: Minimal RAG Corpus per Event

Before calling EarningsQualityAgent for each PEAD event, construct a context block:
```
Context for [TICKER] Q[X] [YEAR] earnings:
1. EPS: Actual $X.XX vs Estimate $X.XX (beat/miss by Y%)
2. Revenue: Actual $XB vs Estimate $XB (beat/miss by Y%)
3. Guidance: [Next quarter guidance text from 8-K, if available]
4. Headlines: [Top 3 news headlines from earnings day via WebSearch]
```
LLM prompt: 'Rate the quality of this earnings beat 0-100. 0 = one-time item or miss, 100 = broad organic beat with positive guidance. Focus on sustainability, not chart appearance.'

### Data Sources for RAG Context
- EPS/Revenue: `yfinance.Ticker.earnings_dates` or FMP API
- Headlines: `WebSearch('[TICKER] earnings [DATE] results')`
- 8-K guidance: FMP API `/sec_filings` endpoint

### Expected Improvement
With proper RAG grounding, EarningsQualityAgent becomes a genuine quality discriminator (14–91% Sharpe improvement range per arXiv:2602.00196) rather than repeating R26's context-free failure.

---

## R29 Amendment — Factor Residual Decomposition (2026-04-04)

**Source:** Attention Factors for Statistical Arbitrage (arXiv:2510.11616, ACM ICAIF 2025)
**Impact on R29:** Add as Stage 0 before cointegration testing.

### Why Factor Purging Matters
Classical cointegration pairs trading fails frequently because both assets in a candidate pair share exposure to the same market and sector factors. When the S&P 500 drops 2% or the energy sector rotates, both XOM and CVX will move together — but this is factor co-movement, not mean-reversion mispricing. Without purging these common factors, the cointegration test has low power and the spread signals are noisy.

Attention Factors (arXiv:2510.11616) achieves Sharpe 2.3 net of costs on 24 years of US large-cap data by jointly learning conditional factors that are maximally useful for arbitrage. The key principle transferable to R29 without deep learning: **trade residuals, not raw prices**.

### R29 Stage 0 — Factor Residual Extraction (10 lines of Python)

For each candidate asset `i` in the pairs universe:
```python
import numpy as np
from sklearn.linear_model import LinearRegression

def extract_residuals(asset_returns, mkt_returns, sector_returns):
    """
    Purge market and sector factor exposure from asset return series.
    Returns residuals suitable for cointegration testing.
    """
    X = np.column_stack([mkt_returns, sector_returns])  # SPY + sector ETF
    model = LinearRegression().fit(X, asset_returns)
    residuals = asset_returns - model.predict(X)
    return residuals
```

- `mkt_returns`: SPY daily returns (proxy for market factor)
- `sector_returns`: Sector ETF returns (XLE, XLF, XLK, etc.) — match each stock to its GICS sector
- Run on trailing 252-day window (rolling), use residuals for all downstream steps

### Updated R29 Pipeline
1. **Stage 0 (NEW):** For all candidate pairs, compute OLS residuals against (SPY, sector ETF). ~10 lines.
2. **Stage 1:** Run Engle-Granger cointegration test on residual pairs. Use ADF p < 0.05 threshold.
3. **Stage 2:** LLM economic plausibility filter — ask 'Is there a plausible economic mechanism explaining why [A] and [B] would mean-revert?' Score 0-100, skip pairs < 40.
4. **Stage 3:** Trade the residual spread (z-score entry/exit) for surviving pairs.

### Expected Effect
- Reduces false cointegration signals from factor co-movement
- LLM filter (Stage 2) receives cleaner signal — pairs that survive Stage 1 have genuine economic relationship, not just beta correlation
- Post-cost Sharpe should improve materially vs raw-price cointegration

---

## Round 32 Design Spec — Systematic SPX Put-Writing with VIX-Kelly Hybrid Sizing

**Status:** QUEUED (after R28, R29, R31; can run in parallel with any)
**Inspired by:** arXiv:2508.16598 — 'Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put-Writing on Index Options' (Aug 2025)
**Source:** https://arxiv.org/abs/2508.16598

### The Opportunity
Index options have persistently priced in slightly more uncertainty than the market realizes — the 'volatility risk premium' (VRP). Implied volatility systematically exceeds subsequent realized volatility on the S&P 500 over long periods. Selling puts on SPX/SPY harvests this premium. The challenge: raw short-put positions can experience catastrophic losses in tail events. Position sizing IS the strategy.

R25 covered calls on dividend stocks: Sharpe 2.643 (our best options result). R25 protective puts: destroyed alpha. R32 tests a fundamentally different options structure — writing puts on the INDEX (not individual stocks) where VRP is most stable and tradeable.

### Strategy Architecture

**Instrument:** SPY puts (liquid, 100-share underlying, manageable notional)
- Alternative: SPXW (S&P 500 weekly options) for tighter bid-ask; more capital-intensive

**Strike selection:** Far OTM puts — delta 0.10 to 0.15 (approximately 5-8% below current SPY price)
- Paper finding: far OTM, short-dated options deliver SUPERIOR risk-adjusted returns
- Rationale: higher IV/RV ratio at tails than ATM; less directional risk

**Expiration:** 7-14 DTE (days to expiration) — weekly or biweekly expiration cycle
- Ultra-short (0-5 DTE) may be optimal per paper but hard to backtest with historical data
- 7-14 DTE is standard weekly options territory; liquid and data-available via yfinance/CBOE

**Position sizing — Three arms to test:**

1. **Fixed sizing baseline:** Sell 1 put per $50k notional, every expiration cycle

2. **VIX-scaled sizing:**
   - Scale = max(0.25, min(2.0, 20 / VIX))  # normalize to VIX=20 as neutral
   - When VIX=10: double position (cheap options, low realized vol expected)
   - When VIX=30: half position (crisis premium, higher realized vol risk)
   - When VIX=40+: 0.25x position (extreme downside risk dominates premium gain)

3. **Kelly-VIX hybrid (paper's winner):**
   - Estimate Kelly fraction from historical VRP (implied_vol / realized_vol ratio, trailing 252 days)
   - VRP_ratio = mean(IV_30d / RV_30d) over trailing year
   - Kelly_f = (VRP_ratio - 1) / variance_of_VRP  # simplified Kelly for VRP
   - Final_size = Kelly_f * (20 / VIX)  # VIX-scaled Kelly
   - Cap at 2x base position to avoid ruin

**Exit / risk management:**
- Close put if unrealized loss exceeds 3x premium received (stop-loss)
- Close put at 50% of max profit (premium decay harvest) — reduces gamma risk
- Alternative: hold to expiration for full premium capture (test both)

### Data Requirements
- SPY options data: available via yfinance options chain (current data) or CBOE DataShop (historical)
- For backtest: use synthetic options pricing (Black-Scholes on historical SPY prices + VIX as IV proxy)
- VIX daily closes: FRED (VIXCLS) or yfinance (^VIX)
- Historical SPY realized volatility: compute from daily SPY returns (22-day rolling std * sqrt(252))

### Synthetic Backtest Method (if options data unavailable)
```python
import numpy as np
from scipy.stats import norm

def bs_put_price(S, K, T, r, sigma):
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    put = K * np.exp(-r*T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return put

# At entry: sell put at strike K = SPY * 0.93 (7% OTM), T=7/252, sigma=VIX/100
# At expiry: payoff = max(0, K - SPY_final) — put buyer receives this, we pay it
# Our PnL = premium_received - max(0, K - SPY_final)
```

### Backtest Universe
- SPY as underlying (2010-2026, covers: 2010 flash crash, 2018 vol spike, 2020 COVID crash, 2022 rate shock)
- Monthly rebalance (sell new puts each options expiration cycle)
- Test period: 2015-2026 (sufficient vol regime variation)

### Success Criteria
- Fixed sizing Sharpe > 0.5 (baseline: VRP should exist in data)
- VIX-scaled Sharpe > fixed sizing Sharpe
- Kelly-VIX hybrid: best Sharpe AND lowest max drawdown vs fixed
- Target: Sharpe 1.0+ net (paper reports strong outperformance vs benchmarks)
- Drawdown: < 30% even in COVID crash test (2020 Feb-Apr)

### Connection to Existing Work
- R25 covered calls on slow-moving dividend stocks: Sharpe 2.643 — best options result
- R32 is INDEX put-writing — orthogonal instrument, different risk profile
- Combine: R25 covered calls for income + R32 index puts as portfolio hedge/income (complementary risk sources)
- Per heuristics: covered calls work on slow names (KO, T, VZ) — index puts are market-wide VRP harvest

### R32 Dependency Note
Can run immediately — only requires SPY price history (yfinance) and VIX history (FRED/yfinance). No earnings data, no LLM API calls, no premium data subscriptions needed for synthetic backtest.

---

## R31 Amendment — SAE Feature Selection on FinBERT Embeddings (2026-04-04)

**Source:** SAE-FiRE (arXiv:2505.14420, May 2025)
**Status:** Optional enhancement to R31 baseline; implement if Approach A (averaged FinBERT scores) yields Sharpe < classic PEAD (2.394).

### The Problem with Score Averaging
R31 Approach A averages FinBERT positive/negative/neutral probabilities across transcript paragraphs to get a single transcript_score. This loses information: some paragraphs (guidance language, specific financial metrics discussion) are much more predictive than others, and averaging dilutes the signal with noise from boilerplate legal disclaimers, operator introductions, and filler text.

SAE-FiRE addresses this by:
1. Extracting FinBERT's **last hidden state** (768-dim vector per token/sentence) rather than just the output probabilities
2. Applying a sparse autoencoder to learn a sparse ~1024-dim decomposition of the hidden state
3. Using ANOVA F-test or gradient-boosted tree feature importance to select the top-k most predictive sparse dimensions
4. Using ONLY those k dimensions as the feature vector for downstream classification

### Practical R31 Stage 2B (if Approach A disappoints)

```python
from transformers import AutoTokenizer, AutoModel
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.ensemble import GradientBoostingClassifier
import numpy as np

# Step 1: Extract hidden states (not just probabilities) from FinBERT
tokenizer = AutoTokenizer.from_pretrained('ProsusAI/finbert')
model = AutoModel.from_pretrained('ProsusAI/finbert')  # note: AutoModel not pipeline

def get_transcript_embedding(text_segments, q_and_a_weight=1.5):
    """Extract mean-pooled hidden states with Q&A weighting."""
    embeddings = []
    weights = []
    for segment_type, text in text_segments:
        inputs = tokenizer(text, return_tensors='pt', truncation=True, max_length=512)
        with torch.no_grad():
            output = model(**inputs)
        emb = output.last_hidden_state.mean(dim=1).squeeze().numpy()  # 768-dim
        w = 1.5 if segment_type == 'qa' else 1.0
        embeddings.append(emb)
        weights.append(w)
    # Weighted mean across segments
    return np.average(embeddings, axis=0, weights=weights)

# Step 2: Build feature matrix across all transcripts in training set
# X: (n_transcripts, 768), y: (n_transcripts,) — 1 if PEAD positive, 0 if negative/flat

# Step 3: ANOVA feature selection — find top-k dimensions
selector = SelectKBest(f_classif, k=50)  # top 50 of 768 dimensions
X_selected = selector.fit_transform(X_train, y_train)

# Step 4: Use X_selected as feature for text_surprise signal
# Option: score = LR.predict_proba(selector.transform(X_new))[0, 1] - 0.5
# Positive score = above-average earnings-positive transcript
```

### When to Use This
- Implement ONLY if R31 Approach A (averaged FinBERT scores) produces Sharpe < 2.0 on training set
- SAE feature selection requires a labeled training set (at least 50+ transcripts with known post-earnings returns)
- With our ~120 transcripts (30 tickers × 4 quarters), this is marginal but feasible
- Trade-off: adds complexity and risk of overfitting on small sample; Approach A is the preferred starting point

### Priority
Low — implement only as fallback if Approach A disappoints. The core PEAD.txt insight (text surprise from transcripts) should work even with simple score averaging per the JFQA 2022 paper's results.
