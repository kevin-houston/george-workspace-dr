# Wiki Log

Append-only chronological record of all wiki activity.
Parse with: `grep "^## \[" wiki/log.md | tail -10`

---

## [2026-04-24] init | Wiki initialized

Wiki created. Sources: 0. Pages: 0.

## [2026-04-24] create | DR section initialized

Pages created: 3 (dr/overview.md, dr/git-backup.md, dr/diary.md). Session 1 diary entry written. Index updated.

## [2026-04-26] research | Options strategies + LEAN evaluation

Three pages created: options-income-strategies.md (iron condor, CSP/wheel, covered calls, VRP; win rates + code), options-data.md (ThetaData/ORATS/QuantConnect comparison), lean-quantconnect.md (LEAN capabilities, cloud vs. local paths, Docker pending). Key finding: wheel underperforms buy-and-hold on SPY; iron condor has strongest evidence base. LEAN is the right engine for options but needs Docker or QC account.

## [2026-04-26] lint | Health check

Issues found: 9. Auto-fixed: 9. Needs review: 0. Fixed: index gap (research-log/2026-04-26 added), page count corrected (22→24), trading/index.md phase updated (Phase 1→2 active), H007 numbering conflict resolved (MA Crossover→H008, IBS→H009), 3 cross-references added (options-income↔lean, options-income↔options-data, 151-strategies↔hypothesis-log), hypothesis-log frontmatter completed (H002-H007 statuses), index entry for hypothesis-log updated, research-log/2026-04-26 updated with H006 results, lean-quantconnect.md updated with algorithm status table.

## [2026-04-26] backtest | H007 results + LEAN Docker breakthrough

LEAN now runs via direct `docker run` (bypassing CLI's Docker-in-Docker path bug). Key: host path `/home/kevin/nc/nanoclaw-v2/groups/dm-with-kevin/` maps to container `/workspace/agent/`. Helper script: `backtesting/lean/run_lean.sh`. BuyHold validation: 24.8% CAGR 2019-2021, matches SPY reality. H007 iron condor: BSM simulation -1.6% CAGR, 67% win rate — INCONCLUSIVE pending real options data (BSM misses put skew). Full LEAN run awaits QC account or ThetaData. QC cloud path blocked (paid organization account required). H007 card written.

## [2026-04-26] backtest | H006 results + LEAN iron condor scaffold

H006 run: dual momentum with BIL (SGOV proxy) vs. TLT safe haven. Key finding: BIL beats TLT OOS (Calmar 0.430 vs 0.349, Sharpe 0.423 vs 0.343) but neither beats SPY buy-and-hold after tax (7.33% vs 10.84%). LEAN iron condor algorithm written at backtesting/lean/IronCondor/main.py — ready to run once Docker is approved. Docker install request submitted (pending admin approval). Hypothesis log updated with H006 card + H007 planned.

## [2026-04-25] ingest | 151 Trading Strategies (Kakushadze & Serur 2018)

Source: ssrn-3247865-151-trading-strategies.pdf (1.6MB, 361 pages). Strategy catalog created at trading/strategies/151-trading-strategies.md. Covers 151+ strategies across all asset classes with formulas and R source code. Prioritized Tier 1 strategies for immediate implementation: Dual-Momentum Sector Rotation (§4.1.2), Sector Rotation + MA Filter (§4.1.1), Dual MA Crossover (§3.12), IBS Mean-Reversion (§4.4). Daily backtesting framework under construction (backtesting/daily/).

## [2026-04-28] ingest | SSRN 6630259 — Dean 2026, BSM as flat limit of information geometry

Source: sources/ssrn-6630259-bsm-flat-limit-info-geometry.pdf
Pages created: trading/algorithms/bsm-information-geometry.md
Index updated: wiki/index.md (sources: 1→2, pages: 24→25)

Key: BSM = flat slice of Fisher manifold (valid ~7 days ATM). Smile = curvature of leverage-corrected manifold (R=-2 constant). Zero-free-parameter LEAPS skew prediction within 19% (σ₀, ν, ρ from time-series). Stable attractor at (ν/σ₀, ρ*)≈(9.2,-0.84) adjacent to bifurcation locus |ρ|=√(2/3). SABR β=1 derives from Čencov's theorem.

## [2026-04-28] backtest | H113 + H114 — Low-Vol Anomaly and ETF Pairs Trading

H113 (§3.4 Low-Vol Anomaly): NOT CONFIRMED at ETF level. Pure vol ranking always selects BIL (T-bills). Earns ~2.5% CAGR with 6 negative years. Composite signal already implements low-vol anomaly via BIL inclusion. Stock-level implementation would require individual equity universe.

H114 (§3.8 ETF Pairs Trading): NOT CONFIRMED. All 5 pairs lose money across IS + OOS. Best pair XLK/QQQ: OOS Sharpe -0.343, Cumul 0.88 (6 negative years). Root cause: monthly rebalance too slow for mean-reversion; pairs diverge structurally over multi-year horizons. No pair qualifies for blend test.

Hypothesis log updated with H113 + H114 cards.

## [2026-04-28] backtest | H115 + H116 — TSMOM filter confirmed; major production upgrade

H115 (TSMOM): CONFIRMED. Pure TSMOM standalone: OOS Sharpe 1.756, CAGR 19.4%, 1 negative year. Key finding: TSMOM as FILTER on H026 (prevent selecting negative-12m assets) boosts H026 OOS from 7.96→13.13, with no change in NegYrs. Production impact: OOS +0.84, AltOOS +2.12.

H116 (combination search): CONFIRMED. H026 filter only is optimal — adding H041a or H045 filters provides no incremental improvement. New production baseline: OOS 6.5635, AltOOS 14.9411 (vs H112 5.7265 / 12.8207). MaxDD unchanged at -3.6%, 0 negative years.

H117 (Sell in May): NOT CONFIRMED. Summer months (May-Oct) are NOT weak in modern data — July +2.33%, Oct +1.16% among best months. TSMOM filter already handles trend avoidance adaptively. Seasonal filter degrades all combinations.

Action required: Update h112_monthly.py to add tsmom_filter=True on H026 (pending Kevin review).

## [2026-04-29] research | Vectorbt H116 implementation + Kalshi API deep dive

Session 7. Two major expansions:

Backtrader vs Vectorbt: Added complete H116 ETF rotation implementation using Vectorbt `Portfolio.from_orders()`. Key discovery: `call_seq='auto'`, `cash_sharing=True`, and `group_by=True` must all be set together for correct multi-asset monthly rebalancing. Also added full Backtrader H116Rotation strategy class with composite momentum score. Vectorbt v1.0.0 released April 22, 2026 (Production/Stable; Python 3.10-3.13; Apache 2.0 + Commons Clause).

Kalshi API deep dive: Expanded kalshi.md from 84→220 lines. RSA-PSS authentication with env vars, full REST endpoint reference (public + auth), WebSocket channels, fee formula (peaks at $0.50; maker 4× cheaper than taker), rate limit tiers (200-4000 tokens/sec), complete CPI nowcasting strategy with ARIMA+FRED data pipeline and Kelly-sized order submission. Kalshi Timeless (CFTC perp contracts) launched April 27, 2026.

## [2026-04-30] research | Momentum + Pairs Trading strategy guides

Session 8. Created two major algorithm wiki pages:

algorithms/momentum-strategies.md (new, ~300 lines): Full H-series findings H001–H149. Production strategy H026 ETF rotation (Sharpe 3.007, MaxDD -9.6%, 382× OOS). H026 signal formula, TSMOM filter, vol-targeting, all parameters. H149 deployment (100% rotation). H150 confirmed standalone low-vol anomaly. H151 confirmed vol-weighting degrades H026.

algorithms/pairs-trading.md (new, ~250 lines): Academic foundation (Engle-Granger, Gatev-Goetzmann-Rouwenhorst), ETF pairs rationale, OLS/Kalman mechanics, H152–H155 NOT CONFIRMED findings, H160 factor-residualized pairs design, code skeleton. H026 paper trading production code updated to H149 (100% rotation, removed H041a/H045 legs).

## [2026-05-01] research | H152 pairs backtest + Kalshi RSA fix + Kraken CLI

Session 9. Three workstreams:

H152 (GDX/SIL pairs trading): NOT CONFIRMED. Cointegration holds IS (p=0.031) but breaks OOS (p=0.465). OOS: Sharpe -0.613, cumul 0.50, MaxDD -58.9%. Root cause: gold/silver ratio drifted post-2018. ETF pairs confirmed market-neutral (corr=-0.102 with H026).

Kalshi RSA fix: Replaced kalshi_py SDK with self-contained KalshiAuthenticatedClient using RSA-PSS signing (not PKCS1v15). Live auth test confirms balance $10.00 returned. Fixed kalshi_cpi.py, kalshi_nfp.py, kalshi_jobless.py. Created backtesting/paper_trading/kalshi_client.py.

Kraken CLI: Expanded wiki from 74→220 lines covering all 50 agent skills, 7 MCP service groups, complete command reference, comparison table vs Alpaca.

## [2026-05-02] research | H155 Kalman TLT/IEF + H156 stock momentum + prediction market expansions

Session 10. Four workstreams:

H155 (Kalman filter on TLT/IEF): NOT CONFIRMED. All 6 variants WORSE than static OLS (H154). Kalman adapts β in real time, collapsing spread half-life to 0.7–2.1d — self-defeating. ETF pairs family exhausted (H152–H155 all NOT CONFIRMED).

H156 (cross-sectional stock momentum, NASDAQ): PARTIAL. Best n=20: OOS Sharpe=0.866, cumul=4.18×. Beats SPY but not QQQ. Survivorship-biased universe. H157/H158 queued.

Prediction market wiki: algorithmic-strategies.md expanded (cross-market arb, full Python nowcasting lifecycle, calibration, Timeless funding arb, IBKR ForecastTrader API). other-platforms.md expanded (IBKR full API, Kalshi Timeless perp mechanics, emerging platforms).

## [2026-05-03] research | nightly — event-driven wiki + arXiv dream cycle scan

Nightly session. Two phases:

Phase 1 — Created algorithms/event-driven.md (new, ~220 lines): PEAD theory (Ball & Brown 1968, Bernard & Thomas 1989), beta-neutral construction with rolling 60-day OLS code, dividend announcement drift (+1.39% AAR on increase day), data source matrix (Finnhub/FMP/yfinance with examples), H159b design sketch and code, implementation checklist, H159/H159b/H161/H162 queued hypotheses table. trading/index.md updated.

Phase 2 — arXiv/GitHub scan. 10 papers catalogued in dream_cycle/research/2026-05-03_scan.json. 5 staged proposals: H163 (PEAD FinBERT NLP filter), H164 (elastic-net 8-quarter SUE), H165 (TradingAgents macro regime), H166 FLAGGED (Pairs-DL, H160 prereq), H167 FLAGGED (ML multi-factor, needs bias-free data). Dream cycle build phase applied H163–H165 as QUEUED; H166–H167 flagged for Kevin review.

## [2026-05-03] lint | Health check

Issues found: 22. Auto-fixed: 19. Needs review: 3.

Fixed: index gaps (14 pages added to wiki/index.md), pages frontmatter corrected (25→38), updated date (2026-04-28→2026-05-03), hypothesis-log description updated (H001-H007→H001-H167), paper-trading/index.md stale May holdings row, 4 cross-references added (alpaca↔alpaca-automation, alpaca↔paper-trading, momentum-strategies↔pairs/event-driven/position-sizing/hypothesis-log, pairs-trading↔momentum/event-driven/hypothesis-log), log.md sessions 8-11 backfilled.

Needs review (source gaps): (1) No options execution mechanics page — fills, slippage, assignment risk; (2) No live trading checklist page; (3) No tax treatment page — wash sale rules, Section 1256, short-term vs long-term cap gains.

## [2026-05-04] research | nightly — NLP tools wiki + dream cycle PEAD/pairs/LLM scan

Phase 1: Created tools/nlp-alternative-data.md (~230 lines). Key finding: speaker-weighted FinBERT (Analyst 49%, CFO 30%, Exec 16%) generates OOS IC=0.142 and 2.03%/month alpha vs FF5 on 16k earnings calls — upgrades H163 design. edgartools (v5.30.2, MIT, 2.1k stars) confirmed as best 8-K Item 2.02 parser (no API key). LM dictionary fully subsumed by FinBERT (LM t=0.86, FinBERT t=5.90). KDD 2026 paper: LLM timing strategies fail long-run; H165 restricted to regime gate role only.

Phase 2: 5 papers/repos catalogued. 3 proposals staged: H168 (speaker-weighted FinBERT PEAD, arXiv:2604.13260), H169 (LLM 10-K embedding pair selection for H160+, arXiv:2604.19476), H165 design note (LLM timing caution, KDD 2026). Scan saved to dream_cycle/research/2026-05-04_scan.json.

## [2026-05-06] research | PEAD live deployment guide + dream cycle arXiv scan

Phase 1: Created paper-trading/pead-nlp-alpaca.md (~250 lines) — full Alpaca deployment architecture for H163/H174 confirmed PEAD-NLP strategy. Covers Alpaca WebSocket streaming (gap detection), EDGAR overnight polling (edgartools + EFTS), FinBERT scoring pipeline, OPG order submission, fractional stop-loss pattern, and 20-day MOC exit. Key finding: Alpaca fractional shares cannot use bracket orders — stop-loss must be submitted as separate GTC order. Index and log updated.

Phase 2: 12 papers/repos scanned. 4 staged proposals: H175 (sec-parser Item 2.02 extraction + EPS surprise gate, arXiv:2509.24254), H176 (GPT-4o-mini relative sentiment, FinDPO revival of H173, arXiv:2507.18417), H177 FLAGGED (Janus-Q hierarchical reward model, ~20h, arXiv:2602.19919), wiki update for sec-parser tool. Consistent finding: 2025-2026 literature validates H163/H168 direction — structured earnings NLP outperforms flat sentiment; Sharpe 2.0 achievable with preference-optimized LLM sentiment.

## [2026-05-05] ingest | A Portfolio Approach to Impact Investment (J.P. Morgan, 2012)

Pages created: 5. Pages updated: 2 (index, log). Key entities: Yasemin Saltuk, J.P. Morgan Social Finance, PGGM, F.B. Heron Foundation, GIIN, Rockefeller Foundation. Core concept: Three-Dimensional Portfolio Framework (Impact/Return/Risk triangle extending MPT). Saved PDF to sources/jpmorgan-portfolio-approach-impact-investment-2012.pdf.

## [2026-05-03] backtest | H159b — Beta-Neutral PEAD NOT CONFIRMED

H159b (Beta-Neutral PEAD): NOT CONFIRMED. Rolling 60-day OLS beta hedge successfully achieves market neutrality (Corr(SPY) = −0.05 to −0.11 vs H159's 0.59–0.67), but MaxDD remains −48–54% — far above the −20% target. Best variant D (n=15, hold=20d): OOS Sharpe=0.382, CAGR=11.51%, MaxDD=−48.68%, NegYrs=3. Root cause: drawdowns are idiosyncratic (individual stock collapses unrelated to SPY), not market-correlated. Beta hedging removes market risk but not name risk. Large IS/OOS gap (IS Sharpe 1.6–2.0 → OOS 0.38) confirms structural PEAD decay in 2018+ — HFT has partially arbitraged gap-up drift. Path forward: H163 (FinBERT NLP filter), H164 (elastic-net 8-quarter SUE history) to improve signal quality before revisiting beta-neutral construction.

## [2026-05-10] lint | Health check

Issues found: 20. Auto-fixed: 17. Needs review: 3.

**Auto-fixed (17):**
- Index gaps: 14 pages on disk not in wiki/index.md — all added (7 research logs 2026-05-04 to 2026-05-10; pead-nlp-alpaca, walk-forward-cpcv, short-term-reversal, sector-classification, nlp-alternative-data, transaction-costs, ml-for-trading)
- Stale descriptions fixed (3): hypothesis-log (was "H163–H165 QUEUED" → now reflects H163/H174/H181 CONFIRMED, H184 NOT CONFIRMED, H185-H187 queued); event-driven (updated to H163 CONFIRMED); pairs-trading (was "H160 queued" → now "family EXHAUSTED")
- Index frontmatter: updated to 2026-05-10, pages 43→59
- Missing cross-references added (2): short-term-reversal linked from momentum-strategies.md; transaction-costs + walk-forward-cpcv linked from design-principles.md

**Needs review (3):**
1. wiki/index.md `sources_indexed: 3` — sources/ directory has only 1 file (jpmorgan-portfolio-approach); count appears wrong, but may reference in-memory ingests not saved to sources/
2. wiki/trading/paper-trading/index.md — may be stale; hasn't been checked for H181 deployment status (Kevin decision pending)
3. wiki/trading/algorithms/event-driven.md Related Pages section — should add links to nlp-alternative-data.md and ml-for-trading.md (new tools pages not yet cross-referenced from event-driven)
