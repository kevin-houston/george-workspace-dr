# George's Heuristic Pool

Persistent lessons extracted from past task trajectories. Organized by domain.
Update after any task that produces a new generalizable lesson.
Retrieve relevant heuristics at the start of complex tasks.

---

## Tools & Environment

### sys.path in containers
- LESSON: Never use `pip install --user` in containers. Use `--target=/tmp/deps` and add to sys.path explicitly.
- WHEN: Any time installing Python packages inside NanoClaw container
- SOURCE: failures.md, March 2026 edge-tts incidents

### X.com / Twitter scraping
- LESSON: X.com login walls block agent-browser reliably. Use WebSearch as primary source for Twitter content instead of scraping.
- WHEN: Any task requiring social media content from X.com
- SOURCE: system_maintenance_log.md, X scraping unreliability March 2026

### Instagram scraping
- LESSON: scrape_instagram.sh is broken (as of March 18, 2026). Don't attempt to call it until Kevin reports debugging. Use alternative content sources.
- WHEN: Any podcast or content task that would normally pull Instagram content
- SOURCE: system_maintenance_log.md

### Container network limitations
- LESSON: Container cannot fetch live prices or access Robinhood API. All live price/portfolio tasks must run on MX Linux host via cron or manual execution.
- WHEN: Any task requiring live market data or Robinhood integration
- SOURCE: system_maintenance_log.md

---

## Research & Backtesting

### LLM signal filtering on event-driven strategies
- LESSON: LLM IndicatorAgent filtering HURTS event-driven strategies (PEAD: confirmed Sharpe 0.716 vs rejected Sharpe 0.904). PEAD fires on 'overbought' gaps that technical indicators penalize — the ugly setup IS the signal.
- WHEN: Designing any LLM filter layer on earnings/event-driven strategies
- SOURCE: trading_eval/LLM_SIGNAL_REPORT.md, Round 26

### LLM as narrator not filter
- LESSON: For PEAD and dividend strategies, LLM adds value as a NARRATIVE GENERATOR (explaining the trade for product features) not as a SIGNAL FILTER. Keep them separate.
- WHEN: Any LLM-augmented trading research design
- SOURCE: trading_eval/LLM_SIGNAL_REPORT.md

### Candle patterns and macro regimes
- LESSON: Macro regime filter does NOT improve 3-10 day candle signals (avg Sharpe lift: -0.059). Candle patterns are short-term, regime-agnostic. Exception: BullMarubozu gains +0.107 lift in calm regime.
- WHEN: Designing any candle + macro combined strategy
- SOURCE: trading_eval/CANDLE_REPORT.md, Round 19

### Options on high-growth stocks
- LESSON: Covered calls on high-growth stocks (IBM, XOM with large moves) significantly underperform buy-and-hold (-10.9% for IBM). Covered calls work best on slow-moving dividend names (KO, MO, T, VZ, PG).
- WHEN: Designing covered call or income strategies
- SOURCE: trading_eval/OPTIONS_REPORT.md, Round 25

### Protective puts destroy PEAD
- LESSON: Protective puts on PEAD portfolio drop Sharpe from 4.46 to 0.25. The protection cost overwhelms the signal edge. Size positions small instead.
- WHEN: Any attempt to hedge PEAD with options
- SOURCE: trading_eval/OPTIONS_REPORT.md, Round 25

### PEAD short side requires broad universe
- LESSON: The short leg of elastic net PEAD adds NO alpha on 22 large-caps (short leg Sharpe: -0.137, win rate 36%). The model predicts negative drift for only 36/2352 obs. Large-caps are too efficiently priced. Short signals in PEAD require small/mid-cap universe (500+ stocks) where persistent negative drift exists post-earnings.
- LESSON: Per-observation walk-forward is impractical at scale (timeouts at ~500 obs). Use calendar-quarter walk-forward instead — same predictive validity, ~25x faster.
- WHEN: Designing long-short PEAD strategies; choosing walk-forward granularity
- SOURCE: trading_eval/R30B_SUE_LONGSHORT_REPORT.md, Round 30b

---

## Podcast & Content Pipeline

### Podcast script format
- LESSON: The audio generator supports two formats: structured (## INTRO...## SOURCES) and fallback (** [INTRO] ** bold speaker labels). Always use consistent labeling or the parser may silently extract 0 segments.
- WHEN: Writing or modifying podcast script generation prompts
- SOURCE: failures.md, March 14, 2026

### ffmpeg unavailable in container
- LESSON: ffmpeg is not installed in the container and cannot be. Python MP3 concatenation (byte-level merge of CBR MP3s) is the reliable fallback for segment merging.
- WHEN: Any audio file merging task in container
- SOURCE: failures.md, March 22-23, 2026

---

## Memory & Self-Improvement

### When NOT to write to MEMORY.md
- LESSON: Only write facts that will still be relevant in 30 days. Don't write debugging details after resolution, one-time observations, or things Kevin can re-tell easily. Ask: 'Would I need this in 30 days?'
- WHEN: Every MEMORY.md update decision
- SOURCE: mem-agent research (HuggingFace, March 2026), CLAUDE.md Memory Discipline section

### Dream cycle genealogy
- LESSON: When staged changes are applied, note in the next night's reflection which applied changes produced measurable effects. This completes the POISE-style feedback loop.
- WHEN: Every dream cycle reflection phase
- SOURCE: POISE paper (arXiv:2603.23951), ERL (arXiv:2603.24639)

### LLM regime blindness (FINSABER validation)
- LESSON: LLMs used for market timing are overly conservative in bull markets (miss gains) and overly aggressive in bear markets (incur losses) — the opposite of optimal. This is confirmed externally by FINSABER (arXiv:2505.07078, 20-year, 100+ symbol study). Root cause: poor regime detection.
- LESSON: Before adding LLM timing to any strategy, first add explicit regime-aware rules (VIX threshold, trend filter, SMA regime) as a hard constraint. LLM judgment is NOT a substitute for regime detection.
- WHEN: Any design that uses an LLM for entry/exit timing decisions
- SOURCE: FINSABER arXiv:2505.07078, validates George R26 LLM filter finding

### FinBERT as exit sentinel (not entry)
- LESSON: FinBERT adds value as an EXIT risk control, not an entry filter. Threshold: sentiment score < -0.70 = exit regardless of technical signal. This prevents holding through news-driven crashes without suppressing entries on neutral-news days.
- LESSON: Distinguish entry filtering (which kills too many signals) from exit risk control (which only fires on strong negative news). Keep exit sentinels on a high threshold so they fire rarely.
- WHEN: Adding sentiment layers to dividend or covered-call income strategies
- SOURCE: Generating Alpha arXiv:2601.19504 (Sharpe 1.68 with this pattern)

### LLM as economic plausibility judge for pairs
- LESSON: For pairs/stat-arb strategies, LLM should ask 'does a plausible economic mechanism exist between A and B?' — NOT 'is the chart overbought?'. Economic plausibility screening eliminated ~46% of average loss magnitude in arXiv:2602.07048. The dominant effect is loss reduction, not return enhancement.
- LESSON: The right LLM pairs filter question: 'Is there a coherent reason why [Company A] and [Company B] would mean-revert toward each other over time?' Score 0-100. Skip pairs < 40.
- WHEN: Designing R29 LLM filter on pairs trading
- SOURCE: arXiv:2602.07048 (Feb 2026)

### Multi-quarter SUE elastic net (long-only vs long-short)
- LESSON: Elastic net trained on 12 quarters of earnings surprise history produces near-universal long bias (~98.5%) when trained on long-only returns from a bull market. The model learns positive market drift, not purely the earnings signal. This lowers per-trade info ratio vs a selective threshold filter.
- LESSON: To replicate Kaczmarek & Zaremba (2025) Sharpe doubling, you need long-short implementation: short when EN predicts negative return, long when positive. Long-only dilutes the alpha by adding marginal trades.
- LESSON: When comparing frequency-adjusted Sharpes (accounting for trade count per year), long-only EN and the simple SUE > 3% baseline perform nearly identically (~1.21 vs ~1.22). The apparent Sharpe gap is a trade-frequency artifact.
- LESSON: Alpha Vantage free tier (25 req/day) is a hard constraint — plan universe size accordingly. Upgrade to premium or cache all data in batch before running broad experiments.
- WHEN: Any PEAD or earnings-surprise strategy using regression models
- SOURCE: R30 backtest (r30_sue_results.json), Kaczmarek & Zaremba (Finance Research Letters, 2025)

### Text-based earnings signals outlast numeric PEAD
- LESSON: Numeric earnings surprise (SUE) is efficiently priced in large-caps — classic PEAD has decayed to ~0 in recent years on large-caps. But TEXT-based surprise from earnings call transcripts (tone, guidance language, Q&A responses) generates 50% stronger daily alpha (3.9 vs 2.6 bps) and PERSISTS when numeric signal has faded.
- LESSON: The Q&A section of earnings calls carries MORE signal than prepared remarks (management controls prepared remarks; Q&A reveals real uncertainty). Weight Q&A segments 1.5x in transcript scoring.
- LESSON: Use FinBERT (`ProsusAI/finbert`) for fast, free transcript scoring. Construct text surprise as: (this_quarter_score − trailing_12Q_avg_score). Score > 0 = management tone more positive than usual = long signal.
- WHEN: Any PEAD-variant design (R31 and beyond); any strategy that uses earnings events as signal entry
- SOURCE: PEAD.txt, JFQA 2022 (Meursault, Liang, Routledge, Scanlon); confirmed in 2025–2026 citations

### LLM filtering needs RAG context — bare prompts hallucinate judgment
- LESSON: Bare LLM signal filtering (R26: IndicatorAgent with only price/indicator data) fails because the LLM has no grounding for the specific stock's context. It applies generic heuristics ('this looks overbought') that are wrong for event-driven strategies.
- LESSON: LLM with RAG (8-K filing + news headlines + prior guidance) achieves +14% to +91% Sharpe improvement vs baseline. The RAG corpus quality is the pivotal variable.
- LESSON: Minimum viable RAG corpus per earnings event: (1) 8-K text for the quarter, (2) top 3 news headlines on earnings day, (3) last quarter's guidance language. This provides enough context for the LLM to distinguish 'organic beat' from 'one-time item' reliably.
- WHEN: Designing any LLM-based filter on trading signals, especially R28 EarningsQualityAgent. Any time bare LLM filtering was tried and failed.
- SOURCE: Generative AI for Stock Selection, arXiv:2602.00196 (Rasekhschaffe, Jan 2026); extends R26 LLM filter failure lesson

### Factor-purging residuals for pairs trading
- LESSON: Before testing cointegration on candidate pairs, residualize each asset's return series against market and sector factors: `residual_i = return_i - beta_mkt * mkt_return - beta_sector * sector_return`. Then test cointegration on residuals, NOT raw prices. Eliminates spurious spread divergences caused by factor moves rather than genuine mispricing.
- LESSON: Classical pairs trading frequently generates false signals when market or sector rotations cause temporary spread widening in otherwise cointegrated pairs. Joint factor + signal optimization achieves Net Sharpe 2.3 vs <0.5 for naive cointegration. Factor purging is the low-cost approximation of this benefit, implementable in ~10 lines of Python.
- WHEN: Designing any pairs trading or statistical arbitrage strategy. Apply as Stage 0 in R29 before cointegration testing and LLM economic plausibility scoring.
- SOURCE: Attention Factors for Statistical Arbitrage, arXiv:2510.11616 (Oct 2025, ACM ICAIF 2025). Epstein, Wang, Choi, Pelger.

### Index put-writing: far OTM + VIX-Kelly sizing harvests volatility risk premium
- LESSON: Systematic put-writing on index options (SPX/SPY) harvests the persistent volatility risk premium (implied vol > realized vol). Far OTM puts (delta 0.10-0.15) at short expirations (0-14 DTE) deliver the best risk-adjusted returns. Position sizing is the dominant performance driver, not strike selection.
- LESSON: VIX-scaled sizing alone helps drawdown. Kelly fraction alone maximizes return. The hybrid (Kelly fraction × (20/VIX)) achieves optimal Sharpe AND drawdown balance — particularly robust in low-volatility environments. Cap at 2x base size to avoid ruin.
- LESSON: Index put-writing is complementary to (not substitutable for) covered calls on individual stocks. R25 covered calls work on slow-moving dividend names; index puts harvest market-wide VRP on SPX/SPY. Different risk sources, can run in parallel.
- WHEN: Designing options income strategies at the portfolio level; extending R25 options research to index-level VRP harvesting (R32).
- SOURCE: arXiv:2508.16598 (Aug 2025) — 'Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put-Writing on Index Options'
