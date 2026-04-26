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

## [2026-04-25] ingest | 151 Trading Strategies (Kakushadze & Serur 2018)

Source: ssrn-3247865-151-trading-strategies.pdf (1.6MB, 361 pages). Strategy catalog created at trading/strategies/151-trading-strategies.md. Covers 151+ strategies across all asset classes with formulas and R source code. Prioritized Tier 1 strategies for immediate implementation: Dual-Momentum Sector Rotation (§4.1.2), Sector Rotation + MA Filter (§4.1.1), Dual MA Crossover (§3.12), IBS Mean-Reversion (§4.4). Daily backtesting framework under construction (backtesting/daily/).
