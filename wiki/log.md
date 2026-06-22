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

## [2026-05-10] deploy | H181 paper trading + wiki audit fixes

Three tasks completed per Kevin's review of lint report:

1. **sources_indexed audited and corrected**: wiki/index.md `sources_indexed: 3 → 1`. Confirmed via glob: sources/ directory contains exactly 1 file (jpmorgan-portfolio-approach-impact-investment-2012.md). Count of 3 was a legacy artifact from in-memory ingest tracking.

2. **H181 deployed to Alpaca paper trading**: 
   - Created `backtesting/paper_trading/h181_monthly.py` — monthly industry-adjusted reversal rebalancer. Signal: REV^IN = prior-month return minus equal-weight GICS-sector avg; long bottom-6 equal-weight. Alpaca paper account, --dry-run/--status/--force CLI flags.
   - Created `wiki/trading/paper-trading/h181-alpaca.md` — deployment guide (signal logic, universe table, workflow, risks, path to real money)
   - Updated `wiki/trading/paper-trading/index.md` — H181 added as active strategy; date updated 2026-04-30→2026-05-10
   - Updated `wiki/index.md` — h181-alpaca.md added to Paper Trading section

3. **Cross-reference pass on event-driven.md**: Added `[NLP & Alternative Data](../tools/nlp-alternative-data.md)` and `[Machine Learning for Trading](../tools/ml-for-trading.md)` to Related Pages line (line 11). Both tools pages are directly relevant to H163/H168/H174 PEAD-NLP strategies documented in event-driven.md.

## [2026-05-11] wiki | Low-Volatility Anomaly page + dream cycle scan

Phase 1: Created `wiki/trading/algorithms/low-volatility.md` (new strategy family page). Covers Blitz & Vliet low-vol decile (Sharpe 0.72, 3yr weekly vol signal), Frazzini-Pedersen BAB (Sharpe 0.78 US 1926–2012, market-neutral beta factor), minimum variance (skfolio), and sector-neutral variant (most crowding-resistant post-SPLV/USMV). Python implementations for all three signal types. H191–H193 queued. Added to wiki/index.md (pages 59→60) and trading/index.md.

Phase 2: Dream cycle scan across 5 angles. 10 papers/repos found, 4 staged:
1. PEAD.txt (JFQA) + arXiv:2509.24254 — text-based SUE from transcripts/press release structure → H195 pathway
2. PolySwarm (arXiv:2604.03888) — 50-persona Bayesian swarm for Kalshi/Polymarket → H185 methodology
3. Spectre GPU backtester — for future large-universe expansion
4. arXiv:2505.16090 — FinBERT vs GPT-4o-mini decision tree for NLP tasks

## [2026-05-10] research | Nightly session — H188, H189

2 hypotheses tested and evaluated.

**H188 — 52-Week High Proximity Momentum (George & Hwang 2004): CONFIRMED**
Signal: prox_i = last_close / max(prior 252 trading days). Long top-6 monthly. IS 2012–2020 Sharpe 1.104; OOS 2021–2026 Sharpe 0.774, CAGR 11.4%, MaxDD −13.6%, 0 negative years. Corr(H188, H181) OOS = 0.389 (both long-only, share market factor).

**H189 — H026 + H181 Monthly Blend (Portfolio Construction): CONFIRMED (blend adds value)**
Corr(H026, H181) OOS = 0.099 (near-zero). All tested blends (90/10 through 50/50) produce higher OOS Sharpe than pure H026 (2.222 → 2.402 at 60/40). Trade-off: cumulative return drops dramatically (62× → 21× at 60/40). Practical recommendation: separate capital buckets, not blended account. H190 (H188+H181 blend on same 30-stock universe) queued as next natural test.

Files: backtesting/daily/run_h188.py, backtesting/daily/run_h189.py. Hypothesis log updated with H188+H189 cards.

## [2026-05-12] expand | short-term-reversal.md
Pages updated: 1. Pages created: 0. Key sources: Jegadeesh (1990), Lehmann (1990), Nagel (2012), Stosik & Zaremba (2026), Quantpedia benchmark.

Expanded `wiki/trading/algorithms/short-term-reversal.md` from 132 → 230 lines. Added: full literature foundation (seminal papers table, two-theory taxonomy), Nagel (2012) VIX-conditional Sharpe finding, return decay profile (half-life 2.5 days, month-1 to month-2 drop), 52-week-high / turnover interaction regime table, transaction cost tiering by market cap (large-cap: +30–50 bps/week net), Quantpedia benchmark (Sharpe 1.09, CAGR 16.25%, MaxDD −52.94%), extended Python code section (VIX-adjusted sizing, regime classifier), crisis behavior / execution timing notes, and full key references list with links.

## [2026-05-17] lint | Health check
Issues found: 15. Auto-fixed: 13. Needs review: 2.

**Auto-fixed:**
- wiki/index.md: Added calendar-anomalies.md, deep-rl-trading.md to Algorithms section
- wiki/index.md: Added portfolio-optimization.md to Tools section
- wiki/index.md: Added research log entries 2026-05-12 through 05-17
- wiki/index.md: Updated Hypothesis Log summary (H001-H187 stale → H001-H209 current)
- wiki/index.md: Updated Low-Volatility summary (H191-H193 queued → all completed, research closed)
- wiki/index.md: Updated Momentum Strategies summary (H001-H165 → H001-H202)
- wiki/index.md: Updated frontmatter (date 05-11 → 05-17, pages 60 → 75)
- trading/index.md: Added 2026-05-12 research log (orphan page resolved)
- calendar-anomalies.md: Added Related pages cross-references
- deep-rl-trading.md: Added Related pages cross-references to ml-for-trading.md
- position-sizing.md: Added Related pages link to portfolio-optimization.md
- paper-trading/index.md: Added PEAD-NLP as active strategy (missing since 2026-05-06 launch)
- paper-trading/index.md: Updated frontmatter date

**Needs review (flagged for Kevin):**
- No 2026-05-16 research log exists — was this day skipped or was it a gap?
- Source gaps: no wiki coverage of macro/regime analysis, after-tax return modeling (noted in decisions log as Kevin requirement)

## [2026-05-18] wiki expansion | H205/H202-XL scan

Pages updated: calendar-anomalies.md (Schroeder 2025 Halloween mechanism, H206 success gates), low-volatility.md (H205 design + regime-conditional BAB risk flag). Page created: research-log/2026-05-18.md. Staged proposals: 4 (H205 design, H206 strengthened, H202-XL large-universe support, H205 regime-conditional risk flag). Scan: arxiv:2507.07107 (gradient boosting 500-stock universe), arxiv:2511.12129 (S&P 500 ML stock selection), arxiv:2602.00196 (cross-sectional rank standardization essential for equity ML), Schroeder IJFS 2025 (SEC disclosure seasonality → Halloween mechanism), ScienceDirect 2025 (regime-conditional BAB in Asia). H205 backtest run_h205.py scheduled tonight.

## [2026-05-20] ingest | Phynance — Kakushadze (arXiv:1405.1948)
Pages created: 1 (sources/phynance-kakushadze-2014.md). Pages updated: 3 (bsm-information-geometry.md cross-reference added; wiki/index.md source entry; wiki/log.md). Key entities: Zura Kakushadze, Quantigic Solutions LLC. Covers: Itô calculus, Girsanov theorem, path integrals, BSM derivation, Greeks, Vasicek/CIR/HJM/BGM interest rate models, quant interview problems. Connected to H162 options income, Dean 2026 information geometry work.

## [2026-05-24] lint | Health check
Issues found: 21. Auto-fixed: 19. Needs review: 0 (one contradiction resolved inline).

**Fixed:**
- wiki/index.md: Added 6 missing algorithm/tool/data pages (alpha101-overlap, factor-models, quality-factor, regime-detection, earnings-events, quant-firm-repos)
- wiki/index.md: Added 6 missing research logs (2026-05-18 through 2026-05-24)
- wiki/index.md: Updated hypothesis-log entry (frontier H209→H221/H222; added H215/H217/H220 confirmed)
- wiki/index.md: Updated momentum-strategies entry (added H215/H217/H220)
- wiki/index.md: Updated frontmatter (date 2026-05-20→2026-05-24, pages 76→87)
- trading/index.md: Fixed alpha101-overlap description (staged→CONFIRMED)
- trading/index.md: Added research logs 2026-05-21 and 2026-05-24
- factor-models.md: Added cross-reference to quality-factor.md
- momentum-strategies.md: Resolved H218 naming collision (multi-window momentum idea was never tested; H218 was used for alpha101+momentum blend; multi-window reassigned to ≥H223)

## 2026-05-25 — Ingest: Stanford MS&E 448 HFT paper
**Type:** source ingest (manual, Kevin provided URL)
**Source:** "High Frequency Trading Strategies" — Stanford MS&E 448, 2021 (Sasson, Ho, Samson). 14pp.
**File:** sources/stanford_msande448_2021_gr1.pdf
**New pages:** algorithms/market-microstructure.md
**Summary:** Two HFT strategies — Microprice (Stoikov 2017, fair price from imbalance + spread) and Avellaneda-Stoikov optimal market making (inventory-adjusted bid/ask). AS reduces inventory std 3–4x vs symmetric quoting. Not actionable without L2 order book data; flagged as future execution layer for intraday entries (potential H230+ range).

## [2026-05-25] ingest | AI Decoupling (vintagedata.org)

**Type:** concept ingest (Kevin provided URL)
**Source:** "The AI Decoupling" — vintagedata.org blog, 2026
**URL:** https://vintagedata.org/blog/posts/the-ai-decoupling
**New pages:** concepts/ai-decoupling.md
**Index section:** AI Industry (new section)
**Summary:** Argues that 2025–2026 saw a structural split between AI and traditional SaaS/cloud — different valuations, growth, talent. Three drivers: sparse MoE economics, synthetic data pipelines (~150T tokens), token pricing incompatibility with enterprise CFO models. Chinese alternative: build your own rather than buy services. Models now constitute an expanding economic layer, not just products.

## [2026-05-27] ingest | xang1234/stock-screener
Pages created: 1 (wiki/tools/stock-screener.md). Pages updated: 1 (wiki/trading/index.md). Key entities: xang1234/stock-screener GitHub repo, Minervini Template screener, CANSLIM screener, IBD 197 industry groups, StockBee-style market breadth, MCP integration. Cross-references: H181 (IBD vs GICS granularity), H165 (breadth as regime signal), H217/H228 (Minervini pre-filter angle). Source: https://github.com/xang1234/stock-screener

## [2026-05-29] dream-cycle | AI Industry wiki expansion

**Type:** wiki expansion (dream cycle nightly session)
**New pages:** 3
- wiki/ai-industry/model-landscape-2026.md — frontier model snapshot May 2026: GPT-5.5/Claude Opus 4.7/Gemini 3.1/Grok 4/DeepSeek V3.2; benchmark table; 10x cost collapse; open-weight gap closed
- wiki/ai-industry/agent-frameworks-2026.md — LangGraph/CrewAI/AutoGen(maintenance)/Agno/PydanticAI; architecture patterns; AutoGen maintenance mode warning
- wiki/ai-industry/ai-infrastructure-2026.md — GPU cloud providers (Lambda/CoreWeave/RunPod); H100/B200 pricing; vLLM/SGLang/TGI inference servers; production LLM cost structure
**Index section:** AI Industry (expanded from 1 page to 4 pages)
**Sources:** techiehub.blog, awesomeagents.ai, gpu.fm (all April 2026)

## [2026-05-29] ingest | Prediction Arena (arXiv:2604.07355)
Pages created: 2 (sources/prediction-arena-2026.md, trading/prediction-markets/ai-model-benchmarks.md). Pages updated: 1 (wiki/index.md). Key entities: Arcada Labs, Kalshi, Polymarket, glm-4.7, grok-4-20-checkpoint, gpt-5.2, claude-opus-4-5, claude-opus-4-6, gpt-5.4, gemini-3.1-pro-preview. Key finding: all 6 frontier models lost money on Kalshi over 57 days (−16% to −30.8%); Polymarket avg −1.1% vs −22.6% Kalshi; research quantity uncorrelated with performance; initial prediction accuracy is #1 driver. Cohort 2: claude-opus-4-6 worst Polymarket performer (−10.06%) in 3-day trial.

## [2026-05-30] lint | Health check
Issues found: 16. Auto-fixed: 15. Needs review: 1.

**Index gaps fixed (14 pages added to index.md):**
- trading/algorithms/ibs-mean-reversion.md
- trading/algorithms/market-microstructure.md
- trading/algorithms/technical-analysis-patterns.md
- trading/backtesting/multiple-testing.md
- trading/data-sources/edgar-fundamentals.md
- trading/paper-trading/live-graduation-criteria.md
- trading/prediction-markets/nowcasting-playbook.md
- tools/stock-screener.md
- Research logs 2026-05-25 through 2026-05-30

**Stale content fixed:**
- Hypothesis log index entry updated: H001-H222 → H001-H235 with current frontier
- Page count updated: 92 → 108
- design-principles.md summary updated to mention GT-Score

**Cross-references added:**
- paper-trading/index.md → live-graduation-criteria.md
- kalshi.md → nowcasting-playbook.md

**Needs review (1):**
- H112 IBS OOS Sharpe discrepancy: ibs-mean-reversion.md implies ~1.0–1.2 (historical estimate) but H235 backtest measured 2.129 for 2021–2026 OOS period. The historical estimate was from earlier sessions; the fresh measurement is more accurate. Consider updating ibs-mean-reversion.md to document the 2.129 OOS Sharpe.

## [2026-06-04] create | Regime Detection Signals practical data guide

Page created: `trading/backtesting/regime-detection-signals.md`

Fills the gap in the backtesting section (previously 5 pages; now 6). Companion
to `algorithms/regime-detection.md` (methods focus) — this new page focuses on
data sourcing, look-ahead avoidance, and production code patterns.

**Key content:**
- SPY 200-day MA signal (yfinance; `.shift(1)` discipline)
- VIX threshold (FRED VIXCLS vs yfinance ^VIX; confirmed threshold VIX=25 from H165a)
- FRED yield curve signals (T10Y2Y, T10Y3M, DGS10): inversion, rate direction, rate hike modifier
- Composite 4-state regime (H249 design: bull/bear × calm/volatile)
- Continuous smooth-score approach (Xiong 2026, arXiv:2605.20636)
- Calendar alignment, FRED release lag, persistence filtering
- Complete H249 production code snippet

**Motivation:** H249 (regime-conditional production portfolio weights) is under test;
this page documents the exact signal construction to prevent look-ahead errors and
provides the data pipeline reference for all future regime-conditional strategies.

Index updated: pages 108 → 109

## [2026-06-07] lint | Health check
Issues found: 18. Auto-fixed: 17. Needs review: 1.

**Index gaps fixed (13 pages added to index):**
- trading/algorithms/commodity-trend-following.md
- trading/algorithms/factor-momentum-style-rotation.md
- trading/algorithms/long-short-equity.md
- trading/backtesting/signal-halflife.md
- trading/backtesting/survivorship-bias.md
- trading/paper-trading/tax-and-after-tax-returns.md
- trading/tools/quantdinger-notes.md
- Research logs: 2026-05-31, 2026-06-02, 2026-06-03, 2026-06-05, 2026-06-06, 2026-06-07

**Frontmatter fixed:** pages 109→122, updated 2026-06-04→2026-06-07

**Hypothesis log entry updated:** frontier H232-H237→H258/H260/H262; added H257/H261b CONFIRMED

**Cross-references fixed (4 links added):**
- design-principles.md → signal-halflife.md, survivorship-bias.md (both locations)
- momentum-strategies.md → commodity-trend-following.md, factor-momentum-style-rotation.md, long-short-equity.md

**Needs review (1):**
- tax-and-after-tax-returns.md not yet cross-referenced from paper-trading/index.md — check if paper-trading index has a related-pages footer to update
## [2026-06-10] ingest | QuantMind (github.com/LLMQuant/quant-mind)
Pages created: 1 (wiki/trading/tools/quant-mind.md). Pages updated: 1 (index.md). Key entities: LLMQuant, paper_flow API, batch_run, FilesystemMemory (planned). NeurIPS 2025 Workshop. Integration candidate for dream cycle Phase 2 arXiv scan.

## [2026-06-10] ingest | fireworks-tech-graph (github.com/yizhiyanhua-ai/fireworks-tech-graph)
Pages created: 1 (wiki/tools/fireworks-tech-graph.md). Pages updated: 1 (index.md). Key entities: Brad Zhang (bradzhang.dev), Claude Code skill, SVG/PNG diagram generation. 8 styles including Claude Official and Dark Luxury. 14 diagram types. AI/Agent domain patterns built-in (RAG, Multi-Agent, Tool Call, Mem0). MIT license. Not a trading tool — documentation/visualization use case.

## [2026-06-11] ingest | AI-Trader (github.com/HKUDS/AI-Trader)
Pages created: 1 (wiki/trading/tools/ai-trader.md). Pages updated: 1 (trading/index.md). Key entities: HKUDS, ai4trade.ai, SKILL.md agent integration. Companion to Vibe-Trading (same lab). Social/agent trading platform: signal publishing, copy-trading, collective intelligence, Polymarket paper trading. MIT self-hostable. Assessment: low-medium priority; interesting for signal publishing and discovery, not for blindly copying signals.

## [2026-06-11] ingest | ContestTrade (github.com/FinStep-AI/ContestTrade)
Pages created: 1 (wiki/trading/tools/contesttrade.md). Pages updated: 1 (trading/index.md). Key entities: FinStep-AI, arXiv:2508.00554 (Zhao et al. 2025), internal contest mechanism (dual-stage: data team + research team with scoring/selection layers). Event-driven stock selection. US market support in V2.0. Architecturally novel: contest selection vs. consensus/debate; relevant to H274/H280 multi-agent designs.

## [2026-06-11] ingest | QuantMuse (github.com/0xemmkty/QuantMuse)
Pages created: 1 (wiki/trading/tools/quantmuse.md). Pages updated: 1 (trading/index.md). Key entities: FactorCalculator, FactorScreener, BacktestEngine, LLMIntegration, C++ core engine. Multi-factor (momentum/value/quality/volatility) + LLM + ML. MIT. Assessment: moderate overlap with existing stack; FactorCalculator API is the most useful piece; not a replacement for our run_hNNN.py pipeline.

## [2026-06-13] ingest | Algorithmic Aspects of Strategic Trading (arXiv:2502.07606)
Pages created: 1 (trading/sources/kearns-shi-2025-strategic-trading.md). Pages updated: 1 (index.md). Key entities: Michael Kearns, Mirah Shi, Neil Chriss (precursor model), FTPL (Follow the Perturbed Leader), CCE (Coarse Correlated Equilibria). Core result: multi-player execution game decomposes into potential game (temporary impact) + constant-sum game (permanent impact), parameterized by κ. κ=0→spread orders; κ=2→front-run. FTPL achieves no-regret CCE in O(nθ²T²) per round. Companion to arXiv:2605.23905 (AI alpha decay). Not actionable at current scale; relevant for institutional execution.

## [2026-06-14] lint | Health check
Pages consulted: wiki/index.md + 20 individual wiki pages. 19 index gaps found and fixed. Pages count updated 124→143. New page created: no (all gaps were existing files not yet indexed).

**Index gaps fixed (19):**
- trading/algorithms/volatility-risk-premium.md
- trading/shared-eval-checklist.md
- tools/claude-code-video-toolkit.md
- trading/tools/multi-agent-llm-trading.md
- trading/tools/quant-mind.md
- trading/tools/ai-trader.md
- trading/tools/contesttrade.md
- trading/tools/quantmuse.md
- trading/data-sources/alternative-data.md
- trading/data-sources/crypto-data-sources.md
- trading/paper-trading/execution-quality.md
- trading/prediction-markets/superforecasting-methods.md
- trading/sources/multibagger-yartseva-2025.md
- trading/research-log/2026-06-08.md through 2026-06-13.md (6 logs)

**No contradictions found.** No orphan pages found (all pages linked from index or trading/index.md). Stale content: hypothesis-log.md frontier note shows H290–H292 but H293/H294 now staged — update on next build cycle run. VRP parenthetical in trading/index.md is cosmetic (description text appended vs separate line) — not a structural issue.

## [2026-06-16] lint | Health check

Pages consulted: index.md, log.md, trading/algorithms/market-timing-overlays.md, trading/research-log/2026-06-15.md.

Issues found: 3. Auto-fixed: 3. Needs review: 0.

1. **Orphan: market-timing-overlays.md** — created 2026-06-15 but not added to index. Fixed: added to Algorithms section with H296/H301/H300/H299 summary.
2. **Orphan: research-log/2026-06-15.md** — nightly session log not indexed. Fixed: added to Research Logs.
3. **Stale: Hypothesis Log entry** — still showed "H001–H292". Fixed: updated to H001–H301 with current frontier.
4. Index frontmatter bumped: updated 2026-06-14→2026-06-16, pages 143→145.

## [2026-06-18] ingest | awesome-finance-mcp (BlockRunAI/awesome-finance-mcp)

Pages created: 1 (trading/tools/awesome-finance-mcp.md). Pages updated: 2 (trading/index.md, trading/tools/nlp-alternative-data.md via dream cycle build).

Source: https://github.com/BlockRunAI/awesome-finance-mcp. Noted by Kevin 2026-06-18.

Key findings: HIGH priority — install Alpaca MCP (`alpacahq/alpaca-mcp-server`) for native order management alongside existing REST code; install FMP MCP (`imbenrabi/Financial-Modeling-Prep-MCP-Server`) for H308 FCF/P data. Massive MCP already live. CCXT/QuantConnect/TradingView/AV MCPs medium priority. DeFi/personal finance/Korea MCPs not relevant.

## [2026-06-21] lint | Health check

Pages consulted: 15+ (index.md, trading/index.md, all 8 gap files, hypothesis-log.md, model-landscape-2026.md).

**Issues found:** 13. **Auto-fixed:** 11. **Needs review:** 2.

### Auto-fixed

1. **Index gap**: `trading/algorithms/multi-agent-llm-trading.md` added to main wiki/index.md (Algorithms section, expanded 2026-06-17)
2. **Index gap**: `trading/algorithms/spx-dispersion-variance.md` added to main wiki/index.md (new 2026-06-19)
3. **Index gap**: `trading/algorithms/fixed-income-bond-rotation.md` added to main wiki/index.md (new 2026-06-20)
4. **Index gap**: `trading/paper-trading/risk-controls-and-monitoring.md` added to main wiki/index.md (Paper Trading section, new 2026-06-17)
5. **Index gap**: `trading/tools/awesome-finance-mcp.md` added to main wiki/index.md (Tools section, new 2026-06-18)
6. **Index gap**: `trading/research-log/2026-06-17.md` added to main wiki/index.md Research Logs section
7. **Index gap**: `trading/research-log/2026-06-19.md` added to main wiki/index.md Research Logs section
8. **Index gap**: `trading/research-log/2026-06-20.md` added to main wiki/index.md Research Logs section
9. **Index gap**: `trading/research-log/2026-06-17.md` added to trading/index.md Research Log section
10. **Index gap**: `trading/research-log/2026-06-19.md` added to trading/index.md Research Log section
11. **Stale content**: Hypothesis Log entry in main wiki/index.md updated: frontier H309 → H320; recent results summarized

### Needs Kevin's review

12. **Duplicate/overlap**: Two `multi-agent-llm-trading.md` files — `trading/algorithms/` (algorithm design view, updated 2026-06-17) and `trading/tools/` (platform listing, added 2026-06-10) — both cover TradingAgents arXiv:2412.20138 with some overlap. Should add cross-references between them, or merge into one page with an algorithms-vs-tools split.

13. **Stale content**: `wiki/ai-industry/model-landscape-2026.md` last updated 2026-05-29. Since then: (a) DeepSeek V4 released April 24 on Huawei Ascend 910C (1.6T param, $3.48/M output tokens); (b) Claude Fable 5 + Mythos 5 export-banned June 12; (c) xAI absorbed into SpaceX → SpaceXAI (Feb 2026). Page needs a major refresh.

New page count: 156 (was 147).

## [2026-06-21] merge | Multi-Agent LLM Trading pages consolidated

Merged `trading/tools/multi-agent-llm-trading.md` (added 2026-06-10) into `trading/algorithms/multi-agent-llm-trading.md` (expanded 2026-06-17). The tools/ version had unique content: Agent Market Arena section, CBS reliability code, NautilusTrader comparison table, design principles (when to use / not use), cost model, key papers summary table, StockBench, FinRL-Trading & Lumibot, Self-Driving Portfolio. The algorithms/ version had unique content: taxonomy table, MadEvolve section, coordination patterns table, H274 implementation detail. All content preserved in the merged algorithms/ file. tools/ file deleted.

Updated references: trading/index.md (removed tools/ entry, updated algorithms/ description); main wiki/index.md (removed tools/ entry, updated algorithms/ description). Page count unchanged from lint pass.

## [2026-06-21] update | AI Model Landscape 2026 refreshed

Updated `wiki/ai-industry/model-landscape-2026.md` (was last edited 2026-05-29). Changes:
- DeepSeek section: V3.2 → V4 (released April 24, 2026); 1.6T params MoE; open-source; trained on Huawei Ascend 910C; V4-Pro $3.48/M, V4-Flash $0.28/M; CFR "best available open-source option"; IP theft allegations
- Anthropic section: added Fable 5 + Mythos 5 export ban (June 12, Day 9 unresolved); single-provider risk note; Claude Code 63% developer adoption
- xAI section: renamed to SpaceXAI; xAI absorbed Feb 2026; Cursor $60B acquisition filed June 16, Q3 2026 target
- Added new "Geopolitical & Regulatory Context" section: export controls on deployed models (unprecedented), Ascend 910C milestone, feedback loop analysis, multi-provider hygiene recommendation
- Updated pricing table and model table to reflect V4
- Updated wiki/index.md entry description

## [2026-06-21] ingest | awesome-quant-ai (leoncuhk)

Source: https://github.com/leoncuhk/awesome-quant-ai (377 stars, Apache-2.0)
Pages created: 1 (trading/tools/awesome-quant-ai.md). Pages updated: 2 (index.md, trading/index.md).
Key entities: TradingAgents, FinRobot, FinRL, Vibe-Trading, Chronos, TimesFM, Moirai, DeepMarket, FinDiff, Flashbots.
Cross-references: H279/H280/H281 (staged LLM hypotheses), multi-agent-llm-trading.md, quant-firm-repos.md.
Notable: TS foundation models (Chronos, TimesFM, Moirai) flagged as unexplored signal layer; diffusion synthetic data relevant for regime simulation.

## [2026-06-22] ingest | hermes-gpt (X Article by @tonysimons_)
Pages created: 1 (tools/hermes-gpt.md). Pages updated: 2 (index.md, log.md).
Source: https://x.com/tonysimons_/status/2067773819322831061
Key entities: hermes-gpt (github.com/asimons81/hermes-gpt), Hermes Agent (@tonysimons_ local agent stack).
Key insight: local MCP sidecar eliminates context-stuffing tax; ChatGPT fetches on-demand → Codex quota untouched.
Cross-references: tools/openalice.md, trading/algorithms/multi-agent-llm-trading.md.

## [2026-06-22] ingest | ATLAS — Self-Improving AI Trading Agents (GitHub)
Pages created: 1 (trading/tools/atlas-gic.md). Pages updated: 2 (index.md, log.md).
Source: https://github.com/chrisworsey55/atlas-gic (via https://x.com/tom_doerr/status/2068824434425610668)
Key entities: ATLAS, General Intelligence Capital, Chris Worsey, MiroFish, Karpathy autoresearch.
Key connections: JANUS = H318 analog; PRISM = H323 analog; PRISM crisis/recovery failure validates HMM pre-training over reactive loop.
Cross-references: multi-agent-llm-trading.md, regime-detection.md, hypothesis-log.md (H318/H323).

## [2026-06-22] ingest | awesome-codex-subagents (VoltAgent)
Pages created: 1 (tools/awesome-codex-subagents.md). Pages updated: 2 (index.md, log.md).
Source: https://github.com/VoltAgent/awesome-codex-subagents (via https://x.com/tom_doerr/status/2069056644793688477)
Key entities: VoltAgent, awesome-codex-subagents, quant-analyst subagent, fintech-engineer subagent.
Key insight: quant-analyst.toml checklist mirrors our shared-eval-checklist.md; useful template for hypothesis review agents.
Cross-references: tools/hermes-gpt.md, trading/shared-eval-checklist.md, trading/algorithms/multi-agent-llm-trading.md.
