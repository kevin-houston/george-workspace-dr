# Nanoclaw Diary — Ernesto
**Purpose:** State-transfer document. If this instance is lost, a recovered instance can read this file and resume all work with full context.
**Last updated:** 2026-04-07
**Update cadence:** Nightly during dream cycle (11:15 PM CT)

---

## 1. IDENTITY & MISSION

I am **Ernesto**, a personal AI assistant running in NanoClaw for Kevin Claw (kevinclaw26@gmail.com). My primary ongoing work is systematic trading strategy research — a Karpathy-style autoresearch loop running since early 2026 that has completed 27 evaluation rounds and built a live paper trading system. I also run a daily AI podcast pipeline, portfolio advisor, and various monitoring bots.

Kevin's philosophy: test everything quantitatively, keep what's statistically significant, discard what isn't.

---

## 2. WORKSPACE LAYOUT

| Path | Purpose |
|------|---------|
| `/workspace/group/` | Main working directory (read-write) |
| `/workspace/group/trading_eval/` | All backtesting harnesses and reports |
| `/workspace/group/trading_eval/rounds/` | JSON result files for all 27 rounds |
| `/workspace/group/paper_trading/` | 8 live paper trading strategy trackers |
| `/workspace/group/pead/` | PEAD-specific scanner and trade log |
| `/workspace/group/dream_cycle/` | Nightly self-improvement pipeline |
| `/workspace/group/podcasts/` | Daily AI podcast scripts |
| `/workspace/group/robinhood-advisor/` | Portfolio advisor system |
| `/workspace/group/MEMORY.md` | Persistent memory (facts, preferences) |
| `/workspace/group/heuristics.md` | Generalizable lessons from past work |

---

## 3. TRADING STRATEGY EVALUATION — COMPLETE RECORD

### 3.1 What This Is

A systematic backtesting program run entirely in Python using yfinance, numpy, scipy, and custom harness scripts. Each "round" is a focused evaluation of a strategy category. Started at Forex (R1) and has expanded to 15 categories over 27 rounds. ~7,000+ strategy variants tested.

**Key constraint:** No vendor data. Everything uses yfinance (free). Options strategies use Black-Scholes simulation.

**Price data:** 88 large-cap tickers cached as `{TICKER}_15yr.pkl` in `/workspace/group/trading_eval/cache/`. These are pandas Series of adjusted close prices, timezone-naive DatetimeIndex, 2011–2025. New sessions often need deps installed: `python3 -m pip install yfinance pandas numpy scipy --break-system-packages -q` (and bootstrap pip first if needed with `curl -s https://bootstrap.pypa.io/get-pip.py | python3 - --break-system-packages --quiet`).

### 3.2 THE MASTER LEADERBOARD (as of R27, 2026-03-31)

Full file: `/workspace/group/trading_eval/MASTER_REPORT.md`

| Rank | Strategy | Category | Sharpe | Notes |
|------|----------|----------|--------|-------|
| 1 | PEAD Portfolio (30-stock) | PEAD | +2.394 | 30-stock equal-weight gap signals, hold 20d |
| 2 | Div Raise >=10% hold-40d | Dividend | +4.403* | *per-trade Sharpe; ~35 events/yr |
| 3 | Div Raise >=5% hold-40d | Dividend | +3.400* | More signals |
| 4 | CC around Ex-Div 10d | Dividend+Opts | +2.643 | Sell calls 10d before ex-div |
| 5 | RF on XOM (best ML) | ML | +1.744 | Random Forest, walk-forward |
| 6 | SOL 20d Momentum | Crypto | +1.682 | High CAGR, MaxDD -71.4% |
| 7 | Div Capture buy-3d sell+5d | Dividend | +1.578 | Pre-ex-div momentum |
| 8 | PEAD gap5% 20d (single) | PEAD | +1.137 | 67.8% WR, p=0.000 |
| 9 | Corn Seasonal Nov-Feb | Commodity | +1.175 | Calendar-driven, MaxDD -14.2% |
| 10 | Dogs of the Dow top-10 | Dividend | +1.203* | *annual Sharpe, p=0.003 |
| 11 | Pairs Portfolio (10-pair) | Stat Arb | +0.964 | Market neutral, MaxDD -11.9% |
| 12 | EWC/EWA Country Pair | International | +0.937 | Canada/Australia, SPY corr 0.09 |
| 13 | Risk Parity Lite | Multi-Asset | +0.865 | SPY/TLT/GLD vol-weighted |
| 14 | Bull Put Spread XOM (R28) | Options/R28 | +2.584 | IV rank>50% filter, best put spread |
| 15 | Bull Put Spread CVX (R28) | Options/R28 | +2.470 | Energy sector defined-risk |
| 16 | VIX Short Put (R28) | Options/R28 | +0.846 | 88.6% WR, structural vol floor |
| 17 | Bull Put Spread avg (R28) | Options/R28 | +0.744 | Best avg across 30 tickers |
| 18 | Iron Condor avg (R28) | Options/R28 | +0.523 | IV rank>50%, 62.8% WR |
| 19 | Covered Calls IBM | Options | +0.836 | Best static CC strategy |

*Note: Dividend Raise and CC Ex-Div Sharpe numbers are per-trade normalized (same method as all event-driven strategies). Comparable within our eval framework.

### 3.3 CATEGORY SUMMARIES

**PEAD (Post-Earnings Announcement Drift)** — Best portfolio strategy.
- Signal: stock gaps up >5% at market open (proxy for earnings surprise)
- Hold 20 trading days, long only
- 30-stock universe gives ~8-10 uncorrelated signals/month → Sharpe 2.394
- Short side DOES NOT WORK (negative gaps mean-revert, not drift)
- Key risk: systemic crash correlation (all positions hit simultaneously)
- Files: `pead_harness.py`, `PEAD_REPORT.md`

**Dividend Raise Signal** — Potentially the single best per-event edge found.
- Signal: company raises quarterly dividend >=10% vs prior payment
- Entry: ex-dividend date (announcement is 2-6 weeks earlier; we capture the drift tail)
- Hold 40 trading days
- WR 64.9%, p=0.000, n=345 events over 10 years
- Same mechanism as PEAD: institutional accumulation continues post-announcement
- Entering at announcement date (not ex-date) would capture even more drift
- Files: `dividend_harness.py`, `DIVIDEND_REPORT.md`

**Statistical Arbitrage (Pairs)** — Best RISK-ADJUSTED strategy.
- Formal cointegration failed on all 75 tested pairs (structural breaks over 10y)
- Solution: 60-day rolling z-score, ±1.5σ entry, ±0.5σ exit, stop at ±4.0σ
- Best single pair: JNJ/UNH (Sharpe +0.857)
- 10-pair portfolio: Sharpe +0.964, MaxDD -11.9%, ~zero beta
- Best pairs book: JNJ/UNH, LMT/NOC, DE/CAT, BAC/GS, BAC/WFC, JNJ/PFE, CVX/COP, COST/PG, EWC/EWA, PFE/MRK
- Kalman filter: helps slowly-evolving pairs, DESTROYS stable ones — use sparingly
- Files: `pairs_harness.py`, `PAIRS_REPORT.md`

**Crypto Momentum** — Highest raw CAGR, high drawdown.
- SOL 20d momentum: Sharpe +1.682, CAGR 205.8%, MaxDD -71.4%
- BTC 30d momentum: Sharpe +1.298, consistent across all windows
- 72% of crypto strategies profitable vs ~15-20% in equities (least efficient market)
- Real-money sizing must be tiny (2-5% of portfolio) due to drawdown
- Files: `crypto_harness.py`

**Commodity Seasonals** — Calendar-driven, simple, real.
- Corn long Nov-Feb: Sharpe +1.175, CAGR 18.3%, MaxDD -14.2%
- Natural Gas winter: Sharpe +0.891
- Gold has NO reliable seasonal (macro-driven, not calendar)
- Files: `etf_commodity_harness.py`

**ML Approaches** — Competitive but not dominant.
- Best: Random Forest on XOM, Sharpe +1.744
- Ensemble avg: +0.527
- Beats buy-and-hold on only 25-35% of stocks
- Best features: vol_20d, close/SMA60, RSI_14, close/SMA200, ret_20d
- Energy (XOM) and staples (WMT, PG) work; tech too noisy
- Files: `ml_harness.py`, `ML_REPORT.md`

**Options Strategies** — Covered calls are real; short vol is catastrophic.
- Covered calls on dividend stocks: avg Sharpe +0.533, IBM best at +0.836
- CC timed around ex-div (10d before, 2% OTM): Sharpe +2.643 — 3x better
- VIX short vol: Sharpe -4.975 (Feb 2018 and Mar 2020 were fatal)
- Protective puts on PEAD: DESTROYS edge (Sharpe 4.46 → 0.25)
- Files: `options_harness.py`, `OPTIONS_REPORT.md`

**LLM Signal Filtering (R26)** — Key finding: LLM hurts event-driven strategies.
- Baseline PEAD Sharpe 0.771 → LLM-confirmed: 0.716 → LLM-rejected: 0.904
- PEAD fires when RSI is elevated and price extended — exactly what LLM penalizes
- "Ugly" overbought setup IS the signal. Don't filter it out.
- LLM is better as: narrative generator, regime classifier, pairs filter
- Credential proxy only injects auth at Node.js layer; Python/curl to api.anthropic.com returns 401
- Files: `llm_signal_harness.py`, `LLM_SIGNAL_REPORT.md`

**International Equities** — Long-only adds little vs SPY; pairs work.
- EWC/EWA (Canada/Australia): Sharpe +0.937, SPY corr 0.09 — add to pairs book
- Taiwan (EWT): best single-country, Sharpe +0.615
- China/Turkey: MaxDD >60%, skip
- Dollar filter: conditioning EM on weak USD improves Sharpe 48%
- Files: `intl_harness.py`, `INTL_REPORT.md`

**Leveraged ETF Decay** — Don't short; use as amplifier.
- TQQQ loses 5.51%/yr vs theoretical 3x QQQ. Decay is real but unshortable in bull markets.
- Short TQQQ + long QQQ: MaxDD -98.8% (near fatal)
- Best: UPRO/IEF momentum switching (hold UPRO when SPY > 50d MA, else IEF): Sharpe +0.422
- Files: `lev_etf_harness.py`, `LEV_ETF_REPORT.md`

**What DOESN'T Work (save time, skip these):**
- Tech sector pairs (structural divergence, NVDA 10x)
- Forex trend/breakout (Sharpe -0.45 to -0.59)
- Low volatility factor (inverted 2016-2026)
- Short dividend cutters (restructuring bounce in bull markets)
- PEAD short side
- Protective puts on PEAD
- Short VIX outright (Sharpe -4.975)
- LLM filter on PEAD

### 3.4 ROUND HISTORY

| Round | Category | Key Result File |
|-------|----------|----------------|
| R1-R8 | Forex | forex_round_1-8.json |
| R9-R10 | Candle patterns | candle_results.json |
| R11-R18 | Equity macro (FRED signals × equities) | (various) |
| R19 | Candle × macro combined | candle_macro_round19.json |
| R20-R23 | Statistical arbitrage / pairs | (full_run.log) |
| R24a | Crypto | crypto_results.json |
| R24b | ETF/Commodity | etf_commodity_results.json |
| R24c | Factor/Seasonal | factor_seasonal_results.json |
| R24d | VIX/Intermarket | (in etf file) |
| R24e | International equities | intl_results.json |
| R24f | Leveraged ETF decay | lev_etf_results.json |
| R24g | Machine learning | ml_results.json (in rounds/) |
| R24h | PEAD | pead_results.json (in rounds/) |
| R25 | Options strategies | options_results.json |
| R26 | LLM signal filtering | llm_signal_results.json |
| R27 | Dividend strategies | dividend_results.json |

**R28 COMPLETE (2026-04-01):** Options Deep Dive — Wheel/Multi-Leg/Greeks/VIX. Results: Bull Put Spread avg +0.744 (best), VIX Short Put +0.846, Iron Condor +0.523. Wheel disappoints (-0.130/yr vs BH). IV rank filter critical for all premium-selling.

**Next queued round:** R29 — LLM filter on Pairs (predicted to HELP unlike PEAD)
- Hypothesis: Fundamental/news/sentiment agents improve PEAD Sharpe (unlike IndicatorAgent which hurt it)
- Architecture: EarningsQualityAgent (was it real beat or one-time?), NewsAgent (sentiment), RegimeGuard (skip if VIX > 30)
- Design spec in MASTER_REPORT.md bottom section

### 3.5 RECOMMENDED PORTFOLIO ALLOCATION

| Weight | Strategy | Expected Sharpe | Notes |
|--------|----------|----------------|-------|
| 25% | PEAD Portfolio | +2.394 | Anchor strategy |
| 20% | Pairs Portfolio (US + EWC/EWA) | +0.964 | Market neutral hedge |
| 15% | Dividend Raise Signal | high | Quarterly, event-driven |
| 15% | Commodity Seasonal | +1.175 | Low correlation, calendar |
| 10% | Risk Parity SPY/TLT/GLD | +0.865 | Drawdown smoother |
| 10% | Crypto Momentum (small!) | +1.682 | High-CAGR convex exposure |
| 5% | CC around Ex-Div | +2.643 | Yield overlay |

---

## 4. PAPER TRADING INFRASTRUCTURE

### 4.1 Overview

8 strategies running in parallel virtual paper trading. All initialized 2026-03-31. $5,000 virtual capital each, $40,000 total.

Dashboard published daily to here.now — check `~/.herenow/state.json` for current URL slug (`paper-trading-dashboard`).

### 4.2 Strategy Files

| Strategy | Script | Portfolio JSON | Backtest Sharpe | Status |
|----------|--------|---------------|-----------------|--------|
| PEAD Portfolio | `/workspace/group/pead/pead_scanner.py` | `pead_trades.json` | +2.394 | Live, scanning daily |
| Dividend Raise Signal | `paper_trading/pt_div_raise.py` | `div_raise_portfolio.json` | +4.403 | Live, awaiting signals |
| CC around Ex-Div | `paper_trading/pt_div_cc.py` | `div_cc_portfolio.json` | +2.643 | Live, awaiting signals |
| Crypto Momentum | `paper_trading/pt_crypto.py` | `crypto_portfolio.json` | +1.682 | Live |
| Dividend Capture | `paper_trading/pt_div_capture.py` | `div_capture_portfolio.json` | +1.578 | Live, awaiting signals |
| Corn Seasonal | `paper_trading/pt_corn.py` | `corn_portfolio.json` | +1.175 | Off-season (enters Nov) |
| Pairs Portfolio | `paper_trading/pt_pairs.py` | `pairs_portfolio.json` | +0.964 | Live |
| ML Ensemble | `paper_trading/pt_ml.py` | `ml_portfolio.json` | +0.527 | Live, weekly retrain |

### 4.3 Paper Trade Logic Summaries

**PEAD:** Download daily open/prev-close for 30 large-caps. Gap >3% or >5% at open = signal. Enter at open, hold 20 trading days, $500/trade, max 10 positions. Two buckets (3pct and 5pct). Script: `pead_scanner.py --exit` then `pead_scanner.py`.

**Dividend Raise Signal:** Scan 50 stocks for dividend raises ≥10% vs prior payment. Entry on ex-date close, hold 40 trading days. $500/trade, max 10 positions.

**CC around Ex-Div:** Find tickers with ex-dates exactly 10 trading days away. Sell BS-priced 2% OTM call. Close at ex-date. Key: `bs_call(S, K, T, sigma)` using scipy norm.

**Crypto Momentum:** SOL + BTC. Signal = close > 20d SMA → long. $2,500 per coin. Exit when signal flips.

**Dividend Capture:** Enter 3 trading days before ex-date, exit 5 trading days after. $500/trade, max 10.

**Corn Seasonal:** Long CORN + UNG from Nov 1 → Mar 1. Currently off-season. Next entry: Nov 2026.

**Pairs:** 10 pairs, 60d rolling z-score, ±1.5σ entry, ±0.5σ exit, stop ±4.0σ. $500/leg.

**ML Ensemble:** XGBoost + RF + GBM + Logistic on XOM/WMT/PG/JPM/HD. Weekly retrain, 252d train / 21d test. Prob >0.60 → long 5 days. $1,000/position.

### 4.4 Dashboard

- Publisher: `/workspace/group/herenow.py` (pure Python stdlib, no third-party deps)
- Dashboard builder: `paper_trading/pt_dashboard.py`
- Site built to: `paper_trading/site/index.html`
- Slug: `paper-trading-dashboard` (persistent URL, stored in `~/.herenow/state.json`)
- here.now API: POST manifest → PUT files to presigned URLs → POST finalize

---

## 5. SCHEDULED TASKS

*Recreated 2026-04-02 after container reinstall. New task IDs below.*

| Task ID | Schedule | Purpose |
|---------|----------|---------|
| task-1775189332787-3rh4ew | 4 AM daily | Dream Cycle BUILD phase — apply staged changes |
| task-1775189327757-q53r1e | 11:15 PM daily | Dream Cycle RESEARCH phase (scan/reflect/research/stage) |
| task-1775189318380-jx7wuf | 4:35 PM weekdays | Run all 8 paper trading strategies + publish dashboard |
| task-1775189313254-j7wdtv | 9:45 AM weekdays | PEAD gap scanner (market open entry scan) |
| task-1775234497467-6m3dye | 6 AM daily | Generate daily AI podcast script |
| task-1775189338264-s6585c | 6:35 AM weekdays | Portfolio advisor analysis → email to Kevin |
| task-1775189342806-ahliy2 | 4 PM daily | Daily system maintenance summary to Kevin |
| task-1775189381951-bk02id | Every 15 min | Price alert monitor |
| task-1775189356604-six1m2 | 8 AM 1st of month | Monthly momentum signal check |
| task-1775189350283-yaf68l | 4:30 PM Mondays | Weekly mean reversion z-score check |
| task-1775189365019-giam2i | 6 AM 1st of month | Portfolio rebalancing bot |
| task-1775189371220-9odzbg | 6 AM Mondays | Dividend capture scanner (legacy, pre-paper-trading) |
| task-1775189377409-ppw094 | 7 AM weekdays | Price alert bot |

---

## 6. DREAM CYCLE

**Location:** `/workspace/group/dream_cycle/`

**Architecture (4-phase nightly):**
1. **Scan** — Search arXiv, HuggingFace, GitHub for relevant papers/tools
2. **Reflect** — Read MEMORY.md, recent logs, failures.md for context
3. **Deep Research** — Follow citations, fetch full papers for promising findings
4. **Evaluate + Stage** — Write JSON proposals to `staged/YYYY-MM-DD/`

**4 AM BUILD phase:** Reads staged proposals, applies low/medium risk changes, flags high-risk for Kevin's review. Writes changelog to `changelogs/`.

**Staged change schema** (`STAGED_SCHEMA.md`):
```json
{
  "id": "unique-id",
  "type": "prompt_update|code_patch|memory_update|new_file",
  "risk_level": "low|medium|high",
  "target_file": "/path/to/file",
  "content": "...",
  "action": "append|replace|create",
  "apply_status": "pending|applied|skipped"
}
```

**First dream cycle run:** 2026-03-31. Top finding: QuantAgent (arXiv:2509.09995). Applied: MEMORY.md updates, skills_index.md, CLAUDE.md memory discipline guidelines.

**R28 literature queue (add to dream cycle Scan phase):**
- Carr & Wu (2009) "Variance Risk Premiums" — quantify IV-RV gap
- Bakshi & Kapadia (2003) "Delta-Hedged Gains and the Negative Market Volatility Risk Premium"
- Simon & Campasano (2014) "The VIX Futures Basis: Evidence and Trading Strategies"
- Cboe VIX options white papers — term structure strategies
- VIX futures term structure (VX1/VX2 roll) as entry signal for condors

---

## 7. OTHER ACTIVE SYSTEMS

### Daily AI Podcast
- Script generation: `daily_ai_podcast_generator.py` (6 AM daily)
- Output: `/workspace/group/podcasts/ai_podcast_YYYY-MM-DD.md`
- Format: NotebookLM-style, Alex (male) + Jordan (female) hosts
- Process: 6 WebSearches → score/select 4-5 stories → WebFetch full articles → write 1,800-2,400 word script
- Latest episode: "The Machine Crosses the Line" (2026-04-01) — GPT-5.4 crosses human baseline, Anthropic/Pentagon standoff, federal vs. state AI regulation war, tariffs vs. $3T AI buildout

### Portfolio Advisor
- Main script: `send_latest_report.py` (6:35 AM weekdays)
- Report generation: runs earlier at 6:30 AM, stored as `daily_report_YYYYMMDD.txt`
- Emails to: kevinclaw26@gmail.com via Gmail SMTP
- Subject format: "Portfolio Analysis - [Month DD, YYYY]"
- Robinhood data: fetched via `fetch_robinhood_portfolio.py` / `fetch_robinhood_value.py`

### here.now Publisher
- File: `/workspace/group/herenow.py`
- Pure Python stdlib (no third-party deps — replaced a high-risk npm skill)
- 3-step API: POST manifest → PUT files to presigned URLs → POST finalize
- State: `~/.herenow/state.json` (slugs + claim tokens for persistent URLs)
- Usage: `python3 herenow.py [directory] --slug [slug] --title [title]`

---

## 8. KEY TECHNICAL FACTS FOR RECOVERY

### Python Environment
- Container resets clear pip each session
- Bootstrap: `curl -s https://bootstrap.pypa.io/get-pip.py | python3 - --break-system-packages --quiet`
- Then: `python3 -m pip install yfinance pandas numpy scipy --break-system-packages -q`
- Cached prices: `trading_eval/cache/*_15yr.pkl` — pandas Series, adjusted close, tz-naive

### Credential Proxy
- `HTTPS_PROXY=http://x:aoc_...@host.docker.internal:10255`
- Injects auth ONLY at Node.js tool layer (WebFetch, WebSearch)
- Python `urllib.request` and `curl` return 401 for api.anthropic.com
- Workaround: use Claude tools (WebSearch/WebFetch) for API calls, or rule-based proxies

### yfinance Data Format (2026)
- Single-ticker download returns MultiIndex columns: `('Close', 'TICKER')`
- Use `.squeeze()` to collapse: `hist['Close'].squeeze()`
- Dividend data: `yf.Ticker(t).dividends` → tz-aware Series, strip with `.tz_localize(None)`
- 15yr cache files are plain Close Series (tz-aware), strip tz before use

### Price Adjustment Note
- Cache uses `auto_adjust=True` → dividends baked into adjusted prices
- Do NOT add `div_amount` to returns on top of adjusted prices (double-counts)
- Dividend capture and CC strategies corrected for this in R27

---

## 9. KEVIN'S PREFERENCES & CONTEXT

- Wants WhatsApp messages in *single asterisks* for bold (NOT **double**)
- No markdown in messages — WhatsApp/Telegram formatting only
- Prefers concise messages, bullets with •
- Email: kevinclaw26@gmail.com
- Trading is the primary interest; always eager to run more eval rounds
- Likes the "run it and find out" philosophy — launch parallel agents when possible
- Side hustle school project exists (Gumroad) but is lower priority than trading eval

---

## 10. HOW TO RESUME AFTER RECOVERY

1. **Read this file first** — you're doing that now ✓
2. **Read `/workspace/group/MEMORY.md`** — persistent facts about Kevin and system state
3. **Read `/workspace/group/heuristics.md`** — generalizable lessons (check before any task)
4. **Check scheduled tasks** — `mcp__nanoclaw__list_tasks()` — verify all 13 tasks are still active
5. **Check paper trading state** — read `paper_trading/*.json` and `pead/pead_trades.json`
6. **For trading eval work:** read `trading_eval/MASTER_REPORT.md` — the full leaderboard and findings
7. **For next eval round:** R29 — LLM filter on Pairs (see MASTER_REPORT.md Unexplored section). R28 complete (Options Deep Dive) — results in `trading_eval/rounds/r28_options_advanced.json` and `R28_OPTIONS_REPORT.md`
8. **Bootstrap Python deps** before running any harness scripts (see Section 8)

**Most important ongoing task:** Paper trading is live. The 4:35 PM daily task runs all 8 strategy scripts. The 9:45 AM task runs the PEAD gap scanner. These should be running automatically — just verify the task IDs are still active.

---

## 11. DIARY UPDATE INSTRUCTIONS (FOR DREAM CYCLE)

During the nightly dream cycle, update this file with:
- Any new eval rounds completed (add to leaderboard table and round history)
- Changes to paper trading infrastructure
- New scheduled tasks added or removed
- Significant findings or decisions
- Update "Last updated" date at top

Keep this file under 500 lines if possible. Split into subdocuments if it grows larger.

**Also maintain these DR files on any system change:**
- `/workspace/group/TASK_REGISTRY.md` — Update whenever a task is added, changed, or removed (include full prompt)
- `/workspace/group/DISASTER_RECOVERY_README.md` — Update "Last updated" date if the recovery procedure changes
- `/workspace/group/skills_index.md` — Update when new scripts are created or old ones removed

---
*This diary was created 2026-04-01 at Kevin's request following an openclaw catastrophic failure. It is the primary state-transfer document for George.*
