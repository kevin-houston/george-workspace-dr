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
