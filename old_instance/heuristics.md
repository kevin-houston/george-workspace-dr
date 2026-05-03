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

### Quality score filtering dramatically improves PEAD (R28)
- LESSON: Statistical quality scoring (beat magnitude + price persistence + volume confirmation) on PEAD gap signals cut 54% of signals but improved Sharpe from 4.78 → 9.03 (89% lift) and reduced MaxDD from -48% → -17%. The filtered-out signals had near-zero average returns, confirming the filter separates noise from signal rather than just reducing trade count.
- LESSON: Hard filtering (drop signal if score < 50) outperforms soft filtering (scale position by score/100) because soft filtering keeps low-quality trades at reduced size, while hard filtering eliminates them entirely. When a signal is bad, smaller size does not save it.
- LESSON: Quality score is monotonically correlated with forward returns across deciles — this validates the scoring approach and suggests even higher thresholds (>=60 or >=70) could be explored in R29.
- LESSON: VIX > 30 veto is extremely effective. Excluding gap signals during high-volatility regimes removes noise without sacrificing significant upside, since gaps in high-VIX periods are less likely to be earnings-driven and more likely to be market-wide panic moves.
- WHEN: Any PEAD or event-driven gap strategy. Apply a multi-component quality score before accepting a signal. Consider hard filter at score >= 50 as starting point.
- SOURCE: R28 run 2026-04-11, /workspace/group/trading_eval/r28_pead_quality.py
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

### Factor residualization unlocks cointegration in pairs trading (R29)
- LESSON: Raw price cointegration testing on large-cap stocks finds almost no cointegrated pairs (1/45 in R29 universe). Factor residualization (OLS on SPY + sector ETF, rolling 60-day) removes common market/sector drift, revealing 19 cointegrated pairs. The common factor is masking mean-reversion that exists at the idiosyncratic level.
- LESSON: Fixed ±2σ thresholds on residualized spreads (Sharpe 1.38) outperform OU-calibrated thresholds (Sharpe 0.91). OU calibration tends to widen thresholds for slow-reverting pairs (half-life 7-30d), which allows the spread to drift further before entry — correct in theory, but in practice it just delays entry and increases drawdown.
- LESSON: When building a pairs strategy, always test factor residualization first before searching for cointegration. The pipeline should be: residualize → cointegrate → trade, not: cointegrate → trade.
- WHEN: Any pairs trading or statistical arbitrage research. Residualize before cointegration testing.
- SOURCE: /workspace/group/trading_eval/r29_pairs.py, Round 29

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

### Multi-agent LLM orchestration for financial documents
- LESSON: For SEC filing extraction tasks, Hierarchical Supervisor-Worker achieves 98.5% of maximum accuracy at 60.7% of the cost. For small-batch backtests (<25K docs/day), Reflexive Self-Correcting is acceptable and maximizes accuracy.
- LESSON: Earnings quality signals (one-time items, accruals, organic vs. cost-cut beat) are NOT reliably extracted by general LLM prompts alone. Add domain-specific hard constraints as post-processing guards outside the LLM pipeline (e.g., parse GAAP vs non-GAAP reconciliation table directly).
- LESSON: The 3 dominant failure modes in financial document LLM extraction are (1) temporal confusion (FY vs quarterly data), (2) unit/scale mismatches (thousands vs millions), (3) cross-table reference failures. Build explicit guards for all three before trusting LLM-extracted financial numbers.
- LESSON: Llama 3 70B achieves F1 0.869 vs Claude 3.5 Sonnet F1 0.929 on financial extraction — acceptable for summarization steps; use frontier models for quality judgment calls only.
- WHEN: Designing R28 EarningsQualityAgent, any future LLM pipeline reading SEC filings or financial documents
- SOURCE: arXiv:2603.22651 (March 2026) — Benchmarking Multi-Agent LLM Architectures for Financial Document Processing

### MarketSenseAI sequential Fundamentals Agent pattern
- LESSON: The highest-performing RAG pattern for earnings quality assessment is a 3-step sequential pipeline: (1) summarize SEC filing (8-K/10-Q) for beat/miss and one-time items, (2) summarize earnings call Q&A for management tone and analyst reception, (3) consolidate with 5 quarters of EPS history to assess persistence. This structure achieves Sharpe 2.87 on S&P 500 stocks with monthly rebalancing.
- LESSON: HyDE (Hypothetical Dense Embeddings) retrieval outperforms standard semantic retrieval for financial queries (answer relevancy 0.76 vs 0.48). When implementing RAG for earnings documents, generate a hypothetical answer first, then retrieve similar documents.
- LESSON: The EDGAR EFTS API provides free programmatic access to 8-K, 10-Q, and 10-K filings — no subscription needed. This is the correct free data source for an EarningsQualityAgent RAG corpus.
- WHEN: Designing R28 EarningsQualityAgent or any future LLM-augmented earnings strategy. Apply as the default pipeline structure before trying anything more complex.
- SOURCE: MarketSenseAI 2.0, arXiv:2502.00415 (Feb 2026)

### Graph clustering as pairs pre-filter (SPONGEsym)
- LESSON: Before cointegration testing in pairs trading, cluster stocks using SPONGEsym on the signed correlation matrix of factor-residualized returns (60-day lookback). Only test cointegration WITHIN clusters. This eliminates spurious inter-cluster pairs that share factor exposure rather than genuine economic linkage.
- LESSON: SPONGEsym splits stocks into positively-correlated and negatively-correlated clusters simultaneously. Pairs candidates come from within the positive cluster. Optimal cluster count = number of eigenvectors explaining 90% of correlation variance.
- LESSON: Pipeline order matters: (1) factor residualize, (2) cluster, (3) cointegration test, (4) LLM economic plausibility screen. Each stage dramatically reduces the candidate space before the expensive next step.
- WHEN: Designing R29 equity pairs trading or any future statistical arbitrage strategy.
- SOURCE: arXiv:2406.10695 (June 2024) — Statistical arbitrage in multi-pair trading strategy based on graph clustering algorithms in US equities market. IR 1.30, Sortino 3.38 on S&P 500 2006-2022.

### FinBERT PEAD accuracy + 3-day confirmation window
- LESSON: For text-based PEAD (R31), FinBERT (encoder-only, ProsusAI/finbert) outperforms BART encoder-decoder for PEAD direction classification: 57.6% positive group accuracy, 58.3% negative group accuracy. Financial domain pretraining is the decisive factor.
- LESSON: Adding a 3-day post-announcement price signal as confirmation improves classification: enter positions on day 3 (not day 0), sizing up when market and text agree, sizing down when they conflict. Sacrifices 3 days of drift but improves signal quality.
- WHEN: Implementing R31 or any text-based earnings signal strategy.
- SOURCE: Hadlock, Roberts & Lee. FinNLP Workshop, ACL 2025 (aclanthology.org/2025.finnlp-2.13).

### Index put-writing: far OTM + VIX-Kelly sizing harvests volatility risk premium
- LESSON: Systematic put-writing on index options (SPX/SPY) harvests the persistent volatility risk premium (implied vol > realized vol). Far OTM puts (delta 0.10-0.15) at short expirations (0-14 DTE) deliver the best risk-adjusted returns. Position sizing is the dominant performance driver, not strike selection.
- LESSON: VIX-scaled sizing alone helps drawdown. Kelly fraction alone maximizes return. The hybrid (Kelly fraction × (20/VIX)) achieves optimal Sharpe AND drawdown balance — particularly robust in low-volatility environments. Cap at 2x base size to avoid ruin.
- LESSON: Index put-writing is complementary to (not substitutable for) covered calls on individual stocks. R25 covered calls work on slow-moving dividend names; index puts harvest market-wide VRP on SPX/SPY. Different risk sources, can run in parallel.
- WHEN: Designing options income strategies at the portfolio level; extending R25 options research to index-level VRP harvesting (R32).
- SOURCE: arXiv:2508.16598 (Aug 2025) — 'Sizing the Risk: Kelly, VIX, and Hybrid Approaches in Put-Writing on Index Options'

### SAE-based company similarity for pairs pre-selection
- LESSON: For equity pairs trading, SAE (Sparse Autoencoder) features extracted from LLM (Llama 3.1 8B) activations on SEC 10-K descriptions outperform SIC codes (Sharpe 12.18 vs 9.70), semantic embeddings (vs 7.58-10.57), and GICS codes for pairs trading. Pre-computed features are available on HuggingFace (`marco-molinari/company_reports_with_features`) — no local LLM inference required.
- LESSON: SAE features are interpretable (each feature corresponds to a human-readable business concept), sparse (128 active features per company), and capture internal LLM representations beyond surface-level text similarity. When designing R29 or future pairs strategies, download the pre-computed features and use SAE clusters as the primary pair universe restriction instead of sector codes.
- LESSON: Pipeline order for pairs selection: factor residualize → SAE cluster filter → cointegration test → LLM economic plausibility check → Kelly-sized trade. SAE is the fastest/cheapest filter (pre-computed); LLM prompt is expensive but adds contextual validation on a small candidate set.
- WHEN: Designing any pairs or statistical arbitrage strategy. Default to SAE over SIC/GICS when building a pairs universe.
- SOURCE: arXiv:2412.02605, ACL 2025. Molinari et al. GitHub: FlexCode29/company_similarity_sae.

### Separate sentiment vs. risk in earnings call scoring
- LESSON: Analysts systematically over-react to optimism/sentiment and under-react to risk/uncertainty language in earnings calls (arXiv:2511.15214). A single 'positive tone' score mixes two signals with opposite biases. Always separate: (1) Sentiment score (optimism level), (2) Risk/uncertainty density, (3) Specificity of evidence cited.
- LESSON: Optimal composite quality score = 0.3*sentiment + 0.5*specificity + 0.2*(100-risk_density). High risk density despite positive headline = 'beat with qualifications' → reduce position size 30-50%.
- LESSON: Specificity (management cites concrete drivers: 'product X revenue +15%, region Y grew 20%') is the most predictive dimension — harder to spin, correlates with genuine earnings quality.
- WHEN: Designing LLM-based earnings quality scoring for R28 EarningsQualityAgent or any earnings call NLP pipeline.
- SOURCE: arXiv:2511.15214 (Nov 2025) — Corporate Earnings Calls and Analyst Beliefs.

### Manager evasiveness (NOR) as PEAD amplifier — upsize, don't filter
- LESSON: Manager non-responses (NORs) in earnings call Q&A amplify PEAD. When managers evade >25% of analyst questions, the market takes longer to price the beat → longer and stronger drift. NOR is an AMPLIFIER (upsize position), not a quality filter (skip if bad).
- LESSON: Detect NORs via 3-step LLM prompting: (1) identify analyst questions, (2) classify as answered/evaded, (3) compute NOR rate. Use the Q&A section already extracted for EarningsQualityAgent. Free with LLaMA 3.3.
- LESSON: High NOR effect is magnified for stocks with high institutional ownership — the two signals (NOR rate + institutional ownership) are complementary amplifiers for PEAD position sizing.
- WHEN: R28 EarningsQualityAgent implementation; any earnings strategy using Q&A section transcript scoring.
- SOURCE: arXiv:2505.18419 (May 2025) — How Do Managers' Non-Responses During Earnings Calls Affect Analyst Forecasts. Liang, Carrasco Kind.

### Metric shifting in earnings calls as topical evasion signal
- LESSON: When management changes WHICH metrics they discuss between consecutive earnings calls (high 'metric shifting'), this predicts negative future abnormal returns (-0.52%/month 5-factor alpha, t=-2.55). The signal is not WHAT they say but WHETHER they're discussing the same business drivers as last quarter. High shifting = hiding deterioration in avoided areas.
- LESSON: Add metric consistency check as a VETO (not just a score component) in any EarningsQualityAgent: if metric_consistency_score < 35 (management dropped >65% of prior topics), veto the PEAD trade regardless of specificity/sentiment/risk scores. High consistency + high specificity = strongest buy signal.
- WHEN: Designing any LLM-based earnings quality pipeline (R28 and R31). Any time comparing consecutive earnings calls or filings for the same company.
- SOURCE: arXiv:2510.03195 (Oct 2025) — From Text to Alpha. MIT, BlackRock, J.P. Morgan, Fidelity, Blackstone, QRT consortium.

### Suppress LLM extrapolation bias in fundamental quality prompts
- LESSON: LLMs systematically over-extrapolate recent stock price trends when asked to make financial predictions. In event-driven strategies, this causes the LLM to penalize stocks with large recent gaps (extrapolating mean reversion) — the OPPOSITE of the PEAD signal direction. This is an additional mechanism explaining R26 IndicatorAgent failure, distinct from the missing-RAG-context problem.
- LESSON: Always add an explicit anti-extrapolation instruction to LLM prompts used for fundamental quality assessment: "Do not consider this company's recent stock price performance, momentum, or valuation ratios. Focus exclusively on the content and quality of the earnings announcement." This is a zero-cost prompt patch that removes a systematic bias source.
- WHEN: ANY LLM prompt assessing earnings quality, signal quality, or fundamental value in an event-driven strategy. Applies to R28, R31, and any future earnings-based LLM filter.
- SOURCE: arXiv:2604.02921 (April 2026) — Debiasing LLMs by Fine-tuning. Gao, Jiang, Yan.

### Minimum Regime Performance (MRP) as durability complement to Sharpe
- LESSON: High long-term Sharpe ratio does NOT guarantee strategy durability. MRP (Minimum Regime Performance) = lowest risk-adjusted return in the strategy's worst historical regime. A strategy is 'durable' only if MRP is acceptable. Strategies that look efficient may be fragile in their worst regimes. Backtesting in a single long bull market (2018-2024) obscures this fragility.
- LESSON: Before deploying any strategy live, always compute (or at least qualitatively assess): 'What did this strategy return in the 2022 bear market, Q4 2018 selloff, and March 2020 crash?' If deeply negative, a RegimeGuard and reduced position sizing are mandatory, not optional.
- WHEN: Evaluating any backtest result before deployment. Reviewing rounds 1-30 findings for live trading eligibility. Designing RegimeGuard layers.
- SOURCE: arXiv:2604.08356 (April 9, 2026) — Measuring Strategy-Decay Risk. Alexander & Fabozzi. JPM 2025.

### OU parameter calibration for pairs trading thresholds
- LESSON: Fixed ±2σ entry/exit is suboptimal for pairs trading. Calibrate entry threshold to OU half-life: fast pairs (half-life < 3 days) → ±1.5σ_eq entry; medium (3-7 days) → ±2.0σ_eq; slow (> 7 days) → ±2.5σ_eq. Natural spread unit: σ_eq = σ/√(2θ), NOT rolling standard deviation.
- LESSON: Fit OU parameters (θ, σ, μ) via MLE on the same 60-day spread window used for cointegration testing — zero extra data cost. Half-life = ln(2)/θ. Set exit at |spread − μ| < 0.5 × σ_eq.
- WHEN: Designing or implementing any pairs trading or stat-arb strategy using z-score entry/exit rules (R29 and any future pairs work).
- SOURCE: arXiv:2604.02035 (April 2026) — RL for Speculative Trading under Exploratory Framework. Zhao, Tse, Zheng.

### Never anonymize public financial text before NLP processing
- LESSON: Anonymizing earnings call transcripts (stripping company names, product names, dollar amounts, geography) destroys MORE signal than look-ahead bias. These named entities and numbers ARE the information-carrying tokens for financial NLP models (FinBERT, Longformer). Stripping them removes the alpha signal, not just the noise.
- LESSON: EDGAR filings are public record. There is no privacy reason to anonymize them. Use raw transcripts directly. Only preprocess for chunking (512-token limit for FinBERT) and whitespace normalization.
- WHEN: Any NLP pipeline on EDGAR earnings call transcripts or financial filings (R31 text PEAD, R28 EarningsQualityAgent, any future earnings text analysis).
- SOURCE: arXiv:2511.15364 (Nov 2025) — Anonymization and Information Loss. Wu, Yang, Ying.

### 3-Specialized-Agent Pattern for Financial Disclosure Classification
- LESSON: Use THREE specialized zero-shot agents (Performance focus / Guidance focus / Risk focus) rather than one combined prompt for earnings/financial document classification. Balanced accuracy gains +5 points absolute (9% relative) via a logistic meta-classifier that learns to weight cross-agent disagreement. Single combined prompts cause LLMs to weight recent results over forward guidance due to order and sycophancy effects.
- LESSON: The meta-classifier's most valuable input is cross-agent DISAGREEMENT: when Performance=positive and Guidance=negative, this identifies 'beat but lowered guidance' — the hardest disclosure category and a reliable PEAD failure signal. Train the meta-classifier specifically to handle these mixed-signal cases.
- LESSON: Small zero-shot models work well for financial classification: Qwen2.5-3B-Instruct and Llama-3.2-3B-Instruct are adequate for Performance and Guidance agents (cheap workers). Use Qwen2.5-72B or Claude Haiku only for the Risk agent, where nuance matters most.
- WHEN: Designing any LLM evaluation layer on earnings disclosures, 8-K filings, 10-Q summaries, or any financial document with multiple independent quality dimensions. Apply to R28 Phase 2 EarningsQualityAgent, R31 transcript scoring, any future financial document NLP pipeline.
- SOURCE: arXiv:2603.20965 (March 2026) — Kirtac. 18,420 US corporate disclosures, 2018-2024.

### LLM Trading Action Instability — Use as Factor Generator, Not Executor
- LESSON: Direct LLM trade execution produces 'severe behavioral instability in sequential decision-making': action flipping across adjacent time steps, inconsistent sequences under deterministic decoding, extreme run-to-run variance. Root cause: stateless autoregressive architecture has no persistent market state memory. This is architectural — NOT fixed by better models.
- LESSON: The correct LLM boundary in trading systems: LLM outputs → alpha factor scores, quality ratings, plausibility scores, or strategy parameters. Feed into a DETERMINISTIC execution engine. Never let LLM outputs directly map to buy/sell/hold actions.
- LESSON: Benchmarks that test LLMs on direct trading action sequences produce 'unreliable, non-reproducible evaluations' — performance claims from such systems are not comparable across papers and should be ignored.
- WHEN: Evaluating any paper claiming LLM-based trading outperformance. Reviewing R28/R29/R33 agent designs — confirm all LLM outputs are scores/factors, not actions. Consistent with R26 IndicatorAgent lesson and FINSABER findings.
- SOURCE: arXiv:2602.18481 (Feb 2026) — AlphaForgeBench. Benchmarking End-to-End Trading Strategy Design with LLMs.

### SAE-FiRE: Sparse Autoencoder feature selection for earnings transcripts
- LESSON: For long earnings documents (5000+ words), decompose LLM activations through a Sparse Autoencoder then apply tree-based feature selection (top-1500/4500 features) before classification. SAE-FiRE achieves F1 0.757 on conference call transcripts (Gemma 2-9B), beating Hierarchical FinBERT (0.721) and Longformer (0.718) baselines. AUC 0.668 on transcripts; 0.703 on financial news — combine both for strongest signal.
- LESSON: Use tree-based (XGBoost) feature selection, NOT ANOVA F-tests. ANOVA selects linearly discriminative dimensions; tree-based captures interaction effects that matter in financial text. Top-k=1500 for 16K SAE (2B model), top-k=4500 for 131K SAE (9B model).
- LESSON: For earnings surprise direction classification, optimal free model is Gemma 2-9B with SAE-FiRE. Adequate alternative: Llama 3.1-8B (F1 0.759 on transcripts, near-identical). Both are free/open-source.
- WHEN: Designing R31 text PEAD upgrade or any earnings classification pipeline using full transcripts or 10-Q MD&A sections. Apply as replacement for naive FinBERT chunking when documents exceed 512 tokens.
- SOURCE: SAE-FiRE, arXiv:2505.14420 (May 2025, revised Oct 2025). 9,324 earnings transcripts 2012-2014 + SEC 10-Q MD&A + FNSPID Nasdaq news.

### Drift Regimes Factor: regime-gated value+reversal for concentrated alpha
- LESSON: Value and short-term reversal signals are highly regime-dependent. Trading them ONLY when the stock is in a 'drift regime' (>60% positive-return days in trailing 63-day window) achieves Sharpe 13.19 OOS on S&P500 2004-2024 at 0.6bp costs (Sharpe 6.3 at 10bp). EDGE_i,t = (0.7*value_pctile + 0.3*(-10d_return z-score)) * I(UpFraction_i,t > 0.60). The regime gate removes the same signals when the stock is in a choppy/neutral phase.
- LESSON: The value metric in this factor is 'inverse stock price percentile' — simple, low-cost. R-squared to standard factors < 3%, so alpha is genuinely incremental (not a disguised value or reversal tilt).
- LESSON: The UpFraction > 0.60 over 63 days is a useful MODIFIER for existing signals. Consider it as an optional overlay on PEAD: require that the stock was in a drift regime in the 63 days before earnings as an additional quality filter.
- WHEN: Designing a new long-short equity factor round (candidate R33). Also usable as an overlay filter on R28 PEAD signals.
- SOURCE: arXiv:2511.12490 (Nov 2025) — 'Discovery of a 13-Sharpe OOS Factor: Drift Regimes'. Walk-forward validated, frozen parameters, 20-year S&P500 (2004-2024).

### LLM filter primary effect is loss reduction — use ranking not hard threshold
- LESSON: When using an LLM to filter pairs/signals, its primary contribution is cutting large losers (~40-47% loss reduction per filtered trade), NOT improving win rate (+3pp). A hard pass/fail threshold (e.g., score>=40) captures less value than a RANKING approach (keep top-N by score out of K candidates). Use continuous scoring + rank-based selection, not binary veto.
- LESSON: Prompt the LLM to also predict the expected CO-MOVEMENT SIGN (+1/-1). The LLM can correct sign errors from purely statistical methods (Granger causality / cointegration). If LLM sign disagrees with statistical sign, skip the pair (conservative) or flip trade direction (aggressive — start with skip).
- WHEN: Any pairs trading, lead-lag, or event-driven strategy where an LLM is used as a signal filter overlay.
- SOURCE: arXiv:2602.07048 (Kim et al., Feb 2026) — prediction market pairs trading, 18 rolling evaluations. Win rate: 51.4%→54.5%; Avg loss: -$649→-$347 (46.5% reduction); Total PnL: +205%. Granger top-100 → LLM score → trade top-20. GPT-5-nano.

### Cost-aware threshold calibration for stat arb (OU-thresholding collapses after costs)
- LESSON: Classical OU-thresholding achieves gross SR 0.18 but collapses to net SR -6.45 due to excessive rebalancing. When calibrating entry/exit thresholds for any mean-reversion strategy, optimize against NET-OF-COST Sharpe on a validation set, not gross. Add a realistic per-trade cost term (suggest 5bps/unit turnover) to the objective.
- LESSON: Attention-weighted factor residualization (conditioned on firm characteristics) beats PCA residualization for stat arb net SR by 45% (Net SR 2.28 vs 1.57). Past returns/momentum characteristics are the dominant signal inputs — value/profitability contribute marginally.
- WHEN: R29 pairs trading threshold calibration; any future stat arb research round.
- SOURCE: arXiv:2510.11616 (Epstein, Wang, Choi, Pelger — Stanford, ACM ICAIF 2025). 24-year OOS, 500 US stocks, 39 firm characteristics.

### LLM as market logic extractor for factor generation (AlphaLogics)
- LESSON: Multi-agent LLM pipelines that (1) extract explicit market logic from existing factors, (2) generate new factors constrained by that logic, (3) refine logic via backtesting feedback — produce interpretable AND performant factors (CSI 500 IR=1.53, S&P 500 IR=1.27). More auditable than pure evolutionary search.
- WHEN: Factor generation / alpha mining rounds. Start by extracting logic from existing 146-strategy harness before generating new ones.
- SOURCE: arXiv:2603.20247 (AlphaLogics, Shenzhen U., March 2026)

### Evolutionary trajectory optimization for LLM alpha mining (QuantaAlpha)
- LESSON: Treating each LLM mining run as a 'trajectory' and applying evolutionary operators (mutation = rewrite sub-optimal decision nodes while keeping upstream steps; crossover = merge high-reward segments from two parent trajectories) produces factors with IC 0.1501 vs IC 0.0966 for single-run AlphaAgent (+55% improvement on CSI300). The key insight is localizing WHY a trajectory underperforms, not resampling randomly.
- LESSON: Evolutionary alpha mining (QuantaAlpha) achieves S&P 500 zero-shot transfer from CSI300 factors: 137% cumulative excess return 2022–2025 without retraining. OHLCV+VWAP only — no fundamentals, news, or alternative data required. This is the current SOTA for formula factor generation frameworks.
- LESSON: Claude-4.5-Sonnet achieves functional results as backbone LLM in QuantaAlpha (IC ~0.1252 vs GPT-5.2 IC 0.1501, ~16% degradation). For R33, use Claude Sonnet as CHAT_MODEL and o3-mini or DeepSeek-R1 as REASONING_MODEL (hypothesis generation has highest leverage — use the best available reasoning model there).
- LESSON: Factor diversity constraint for any formula factor pool: admit a new factor only if its absolute correlation with every existing pool member is < 0.70, ranked by RankIC descending. Cap pool at 50% of total mined factors per iteration. This prevents redundancy without sacrificing predictive power.
- WHEN: Designing any LLM-driven formula factor generation system (R33 and beyond). QuantaAlpha's evolutionary approach is preferred over AlphaAgent (single-run) or static LLM prompting.
- SOURCE: arXiv:2602.07085 (Feb 2026, KDD 2025) — QuantaAlpha: An Evolutionary Framework for LLM-Driven Alpha Mining. GitHub: QuantaAlpha/QuantaAlpha (668 stars).

### Anonymize tickers before LLM evaluation (BlindTrade / MemGuard-Alpha)
- LESSON: LLMs exhibit systematic memorization bias when ticker symbols are provided in prompts — they recall training-data associations (analyst reports, historical spreads) rather than reasoning from first principles. Anonymizing tickers as 'COMPANY_A' + 2-sentence business model summary produces HIGHER IC on holdout data (IC 0.0515 for Risk-Regime agent in BlindTrade OOS 2025). The signal is MORE predictive when LLM is forced to reason, not recall.
- LESSON: Contaminated LLM signals deliver 2.13 bps/day vs clean signals 14.48 bps/day — 7x difference. In-sample accuracy rises with contamination (40.8% → 52.5%) while OOS accuracy falls (47% → 42%). Signature: great backtest, collapsing live. Diagnostic: run same prompt with 2 LLMs of different training cutoffs. High agreement on historical data = memorization flag.
- WHEN: ANY LLM call that evaluates a specific stock, pair, or company in a backtest context. Applies to R29 LLM filter, R28 Phase 2 EarningsQualityAgent, and any future LLM scoring of historical signals.
- SOURCE: arXiv:2603.17692 (BlindTrade, Korea University, March 2026); arXiv:2603.26797 (MemGuard-Alpha, April 2026)

### LLM multi-agent consensus > single LLM + uniform trust (TrustTrade)
- LESSON: 'Uniform trust' — treating all LLM outputs as equally informative — is the root failure mode of LLM trading systems. Running multiple independent agents with focused, domain-specific prompts and discarding divergent signals outperforms single-LLM approaches and naive information fusion. Adding more data sources to a single LLM prompt HURTS performance (noise injection). Selective consensus on high-agreement signals is what helps.
- LESSON: A Risk Manager stage adds no value in an Analyst → Trader pipeline (TrustTrade finding). The Analyst → Trader step captures nearly all the performance gain; adding oversight layers overlaps with the Trader and dilutes returns. Keep LLM pipelines short.
- WHEN: Any LLM scoring pipeline with multiple information dimensions (fundamentals, supply chain, pricing, etc.). Use 2-3 narrowly focused agents + consensus gate instead of one broad prompt.
- SOURCE: arXiv:2603.22567 (TrustTrade, Harvard, March 2026)

### Static cointegration pairs don't persist — adaptive discovery required (DeltaLag)
- LESSON: Lead-lag relationships discovered statistically on historical data exhibit 'weak momentum' — they do NOT reliably persist out-of-sample. Precomputed correlation graphs based on historical data substantially underperform adaptive real-time discovery (Sharpe 0.77 vs 2.12 on S&P 500 for statistical vs DeltaLag). Implication for R29: the 19 cointegrated pairs found on 2018-2023 training data may not persist in live trading. The LLM plausibility filter partially mitigates this by requiring economic rationale.
- LESSON: Cross-asset lead-lag signals are more predictive than own-history signals (DeltaLag cross-attention Sharpe 2.12 vs SelfLagNet 1.56). When designing pair-selection methods, prefer models that discover relationships ACROSS assets, not just exploiting a stock's own autocorrelation.
- WHEN: Designing pairs trading pair-selection methodology. Skepticism toward any pairs strategy that relies purely on historical cointegration without dynamic revalidation.
- SOURCE: arXiv:2511.00390 (DeltaLag, HKUST/UCLA/Oxford, ICAIF 2025)

### Track failure constraints alongside success patterns in iterative alpha mining
- LESSON: FactorMiner (arXiv:2602.14670) achieves low inter-factor redundancy (avg pairwise corr 0.25-0.31) by explicitly storing both SUCCESS patterns (high-IC formula motifs to replicate) AND FAILURE constraints (formula patterns that consistently fail: algebraically degenerate, trivially correlated with existing factors, or negative IC). The LLM retrieves both before generating the next candidate — not just what worked, but what to avoid.
- LESSON: For any iterative LLM-driven search (factor mining, strategy generation), maintain two memory pools: (1) a 'what-worked' pool (current George pattern via heuristics.md), and (2) a 'what-failed' exclusion pool. Provide the exclusion pool as context before generating new candidates to prevent re-exploring known dead ends.
- LESSON: 4-stage validation gating is faster than full backtest on every candidate: fast IC on reduced subset → correlation vs existing pool → intra-batch dedup → full validation. Only ~15-20% of generated candidates pass all 4 stages; running full backtest on all would be 5x slower with no quality benefit.
- WHEN: Designing R33 QuantaAlpha implementation. Any iterative LLM-driven generation loop where past failures carry useful information.
- SOURCE: arXiv:2602.14670 (FactorMiner, Tsinghua U., Feb 2026). CSI500: +40% IC vs AlphaAgent baseline.

### Multi-layer regime stack: Wasserstein HMM needs non-overlapping windows
- LESSON: When computing Wasserstein distance for HMM features, use two non-overlapping windows [i-2w, i-w] vs [i-w, i] rather than partially overlapping ones. Overlapping windows produce near-zero distances and cause the HMM to collapse to one dominant state. Non-overlapping windows gave 43/57% state split vs 97/3% with overlap.
- LESSON: For GaussianHMM to discriminate regimes well, scale features (StandardScaler) before fitting, use covariance_type='full' not 'diag', and augment the Wasserstein distance with return level, volatility, skewness, and drawdown. The drawdown feature is the most discriminating for bull/bear separation.
- LESSON: K-Means on EF coefficients (r_MVP, sigma_MVP, u) reliably clusters into 3 regimes (bear ~28%, neutral ~51%, bull ~22%) with ann. returns 3.5% / 13.8% / 29.5% — consistent with the Markov-Markowitz paper. This is a robust portfolio-level signal.
- WHEN: Building multi-layer market regime detection stacks. Any HMM-based regime detection using distributional features.
- SOURCE: R35 regime stack implementation (r35_regime_stack.py), arXiv:2603.04441, arXiv:2604.07870

### Bayesian confidence-weighted aggregation for multi-agent earnings scoring
- LESSON: Fixed-weight aggregation (0.3*sentiment + 0.5*specificity + 0.2*risk) treats all sub-agents as equally reliable regardless of event type. PolySwarm (arXiv:2604.03888) shows confidence-weighted Bayesian aggregation consistently outperforms fixed weights when agents have variable signal quality per event. Upgrade: have each sub-agent output a score (0-100) AND a confidence (0-1). Final quality_score = sum(score_i * confidence_i) / sum(confidence_i). Low-confidence outputs are automatically down-weighted.
- LESSON: The confidence field should reflect: 'How clearly does the transcript text support this score?' (not 'how confident am I in general'). A Specificity agent should output confidence=0.9 if the transcript has concrete revenue numbers, confidence=0.2 if it's all vague language. This allows the high-evidence agent to dominate per-event without changing the overall architecture.
- LESSON: Bayesian aggregation is most valuable when sub-agents specialize narrowly (Performance vs Guidance vs Risk). Narrow prompts produce more calibrated confidence estimates. Match with arXiv:2603.22567 TrustTrade finding that narrowly-focused agents outperform broad combined prompts.
- WHEN: Implementing R28 EarningsQualityAgent. Any multi-agent scoring pipeline where sub-agent reliability varies per event type.
- SOURCE: arXiv:2604.03888 (PolySwarm, April 2026); arXiv:2603.22567 (TrustTrade, Harvard, March 2026)

### Implementation risk: backtest Sharpe numbers carry engine-dependent uncertainty
- LESSON: Backtest results are NOT engine-agnostic. Transaction cost handling alone causes up to 3.71% divergence in strategy metrics across different backtest engines (arXiv:2603.20319). All George backtest results are single-engine (custom yfinance + Python). The DIRECTION of strategy ranking is stable (Conclusion Stability Index=1 across 5 engines), but absolute Sharpe magnitudes carry ~2-4% uncertainty from implementation artifacts.
- LESSON: Add a conservative 5bp/trade friction buffer to any strategy being evaluated for live trading, even if the backtest already includes transaction costs. This covers implementation risk from order routing, partial fills, and price impact not modeled in yfinance-based backtests.
- LESSON: Zero-cost backtests are perfectly engine-consistent. The divergence only appears with non-zero costs. This means strategies with very low turnover (PEAD 5-15 trades/quarter, Div Raise monthly) are less affected by implementation risk than high-turnover strategies (pairs trading with daily rebalancing).
- WHEN: Evaluating any strategy backtest result for live trading eligibility. High priority for R29 pairs (daily rebalancing = highest implementation risk) and R32 SPX puts (options execution slippage).
- SOURCE: arXiv:2603.20319 (Implementation Risk in Portfolio Backtesting, March 2026)

### Walk-forward window length is a hyperparameter — scan before fixing
- LESSON: Fixed walk-forward window sizes (252/63, or calendar-quarter) are arbitrary. arXiv:2602.10785 shows that scanning 1-28 day test window lengths achieves ~50% drawdown reduction by finding windows where strategy performance is most stable OOS. The optimal window is strategy-dependent: PEAD (5-15d hold) suits shorter test windows; Div Raise (40d hold) suits longer ones. Treat (train_window, test_window) as a hyperparameter pair with a 2D grid search.
- LESSON: A combined portfolio using multiple window-length variants achieves the strongest risk-adjusted performance. If running the same strategy with 3-5 different window configurations and averaging signals, you get diversification across temporal regimes without changing strategy logic.
- LESSON: Do NOT optimize window lengths on the full history. Use a small validation set (first 20% of data) to find the best window combination, then lock it for the full walk-forward OOS test. Otherwise you get meta-overfitting.
- WHEN: Setting up any new strategy walk-forward in rounds R28, R31, R32, and beyond. Quick scan: test train=[126, 252, 504] x test=[21, 42, 63, 126] = 12 combinations before committing to a single window.
- SOURCE: arXiv:2602.10785 (Novel Approach to Trading Strategy Parameter Optimization, 2026)

### Eva-4B as evasion classifier for earnings Q&A (upgrade from ad-hoc NOR detection)
- LESSON: Eva-4B (HuggingFace: `FutureMa/Eva-4B-V2`, Apache 2.0, 4B params, Qwen3-4B base) achieves 84.9% Macro-F1 on earnings call evasion detection — outperforming Claude Opus 4.5, GPT-5.2, Gemini 3 Flash. Use it instead of ad-hoc 3-step LLM prompting for NOR rate computation in EarningsQualityAgent.
- LESSON: Eva-4B outputs 3 classes: 'direct', 'intermediate', 'fully_evasive'. NOR_rate = fraction of (intermediate + fully_evasive) answers per call. Threshold 25-50% = PEAD position amplifier (information asymmetry). Threshold >50% = BEARISH VETO (management hiding bad news). These are DIFFERENT signals — don't conflate.
- LESSON: Quantified evidence: +40pp evasion rise → -0.74% 1-day return; 63% underperformance probability within 180 days for high-evasion companies (EvasionBench paper). Extreme evasion is NOT an opportunity; it is a risk flag.
- WHEN: R28 EarningsQualityAgent Q&A scoring. Any pipeline detecting managerial evasion, non-responses, or deflection in earnings calls.
- SOURCE: arXiv:2601.09142 (EvasionBench, Jan 2026). GitHub: IIIIQIIII/EvasionBench. HF: FutureMa/Eva-4B-V2.

### Acoustic camouflage: do NOT add prosodic or speech features to earnings call NLP
- LESSON: Acoustic/prosodic features from earnings calls (pitch, speaking rate, vocal energy) DEGRADE NLP model performance. Adding them drops recall from 66.25% to 47.08% (a significant reversal). Root cause: media-trained executives suppress natural vocal stress signals — those features carry only noise for this population.
- LESSON: Do NOT attempt multimodal (text + audio) earnings call analysis under the assumption that 'voice stress' reveals truth. NLP-only models are strictly superior for corporate earnings calls where speakers are trained professionals.
- WHEN: Designing any earnings call ML pipeline (R28, R31, any future). Reject any proposal to add audio/acoustic features.
- SOURCE: arXiv:2604.14619 (Acoustic Camouflage Phenomenon, April 2026)

### AlphaPROBE DAG navigation prevents redundant factor generation
- LESSON: Model the factor pool as a Directed Acyclic Graph (DAG) where each generated factor records its full lineage. Use a Bayesian retriever that penalizes over-explored nodes: prior weight = quality × (1-ω)^n_retrievals. This prevents re-generating near-duplicates of high-IC factors — the primary failure mode of naive mutation-based alpha mining.
- LESSON: AlphaPROBE achieves ~5.84% IC on CSI300 (vs AlphaAgent ~3.5%) because ancestral lineage context prevents ignoring the 'what-already-worked-and-why' trail. Combine with FactorMiner's failure exclusion pool: success DAG + failure exclusion list = full coverage of explored solution space.
- WHEN: R33 factor mining implementation. Any LLM-driven alpha search where pool redundancy is a concern.
- SOURCE: arXiv:2602.11917 (AlphaPROBE, Feb 2026). GitHub: gta0804/AlphaPROBE (Apache 2.0).

### Retail investor horizon composition predicts PEAD magnitude
- LESSON: Stocks favored by long-horizon retail investors (self-reported, e.g., StockTwits) show LARGER and MORE PERSISTENT PEAD after earnings beats — these investors underreact, leaving drift on the table. Short-horizon retail dominance predicts overreaction and reversal instead.
- LESSON: Zero-cost L/S (long long-horizon stocks, short short-horizon stocks post-earnings) generates 0.43%/month alpha (~5.2% annualized) — meaningful as a position-sizing modifier, not strong enough standalone.
- LESSON: Practical proxy if StockTwits access is unavailable: quarterly 13-F institutional ownership percentile. High institutional ownership ≈ more fundamental-focused investor base → stronger PEAD. Use as amplifier filter (>=60th pctile inst. ownership = upsize 1.25x) on any PEAD strategy.
- WHEN: R31b text PEAD; any future PEAD strategy with per-trade position sizing. R34 concept.
- SOURCE: arXiv:2512.00280 (Retail Investor Horizon and Earnings Announcements, Dec 2025)

### LLM relationship taxonomy for stat arb pair selection
- LESSON: For pairs/stat-arb strategies, LLM should classify pair relationships into 6 CATEGORIES (competitor/supply_chain/peer/substitute/complement/unrelated), NOT produce a scalar score. Competitors and substitutes DIVERGE rather than mean-revert — they are the correct EXCLUSIONS from a stat-arb universe, not a ranking issue.
- LESSON: Scalar 'mechanism_strength' scores mix valid and invalid pair types into a continuum. A low-score supply-chain pair (e.g., a young relationship) is more tradeable than a high-score competitor pair. Category classification + threshold is superior to ranking alone.
- WHEN: Any pairs trading or cross-stock mean-reversion strategy where LLM is used for pair selection. Apply as upgrade to R29 LLM filter prompt.
- SOURCE: arXiv:2604.19476 (April 2026). S&P 500 2011-2019: Sharpe 0.742 → 0.820, MaxDD -10.47% → -7.85%.

### Workflow falsification audit before claiming new alpha
- LESSON: At K=1000 strategy candidates searched, 100% of in-sample apparent winners are statistical artifacts. FeatureMining workflows have the highest false positive rate (100% IS failure at K=400). Any pipeline that generates 100s of features or factors must be falsified against synthetic null environments BEFORE claiming out-of-sample alpha.
- LESSON: Effective multiplicity K̂_eff = (Σλ_i)² / Σλ²_i — at K=500 correlated strategies, K̂_eff may be 5. Scale significance thresholds accordingly. Standard p<0.05 is meaningless without effective multiplicity correction.
- WHEN: Before deploying any LLM-mined factor (R33), any new composite signal (R28 Phase 2), or any strategy found via adaptive spec search. Run at minimum: Bid-Ask Bounce Placebo (timing errors) and Factor Null (is it just a known risk premium?).
- SOURCE: arXiv:2604.15531 (April 2026) — Spurious Predictability in Financial Machine Learning.

### Dynamic agent weighting by macro calendar in multi-agent LLM systems
- LESSON: Static equal-weight multi-agent LLM systems leave alpha on the table. Agent contributions ROTATE with macro calendar: Fundamentals/Earnings agent leads in earnings-driven periods; Macro agent leads during Fed/tariff/macro-uncertainty periods. A meta-agent that detects the current regime and shifts weights captures incremental alpha.
- LESSON: Live (no look-ahead bias) validation of multi-agent LLM equity signal: +25.2pp compound excess, 99.7th percentile, over 19 months on S&P 500. But Jensen's alpha is only p=0.17 — 19 months is short; statistical confidence requires 36+ months. Track live performance before adding complexity.
- WHEN: Designing any multi-agent LLM scoring pipeline (R28 Phase 2, R29 3-agent consensus). Add macro calendar metadata to agent weights: during Fed/tariff periods, up-weight Macro/Risk agent; during earnings seasons, up-weight Fundamentals/Specificity agent.
- SOURCE: arXiv:2604.17327 (April 2026) — Signal or Noise in Multi-Agent LLM Stock Recommendations?

### RMT complexity gap for crash detection + false recovery identification
- LESSON: The RMT complexity gap (normalized largest eigenvalue MINUS average pairwise correlation of the return correlation matrix) reliably detects market synchronization during exogenous shocks. Gap < 0.05 = synchronization = worst regime for all long-short and stat-arb strategies. Validated on COVID-19, 2025 Liberation Day tariff shock, 2024 Japan/China shocks.
- LESSON: After a shock, the gap shows a 'false recovery' phase — it briefly widens (looks like mean reversion is back) then collapses again before true recovery. Automated systems that re-enter at false recovery amplify losses. Track 10-day gap trend, not just current level: gap rising AND trend recently turned down = false recovery = stay out.
- LESSON: RMT complexity gap is computable from yfinance daily returns (~20 lines numpy). Use it as a RegimeGuard input: gap < 0.05 = skip all new strategy entries regardless of VIX level.
- WHEN: R35 regime stack (4th layer). R28 RegimeGuard enhancement. Any strategy that runs long-short or stat-arb with daily rebalancing.
- SOURCE: arXiv:2604.19107 (April 21, 2026) — Structural Dynamics of G5 Stock Markets During Exogenous Shocks.

### Anti-extrapolation PROMPT fails — LoRA fine-tuning required
- LESSON: Anti-extrapolation instructions in LLM prompts ('ignore recent price performance') have LIMITED efficacy. The bias is encoded in model parameters (pretraining + alignment). Prompting only modifies surface inputs; the parameter-level bias persists. Confirmed on Qwen3-32B: overreaction coefficient 0.394 → unchanged with prompting, but reversed to -0.120 after LoRA fine-tuning on rational benchmark forecasts.
- LESSON: The correct bias mitigation hierarchy: (1) BEST: LoRA fine-tuning on rational forecast examples (removes bias at parameter level); (2) GOOD: Ticker anonymization + business description (restricts context that triggers memorized price associations — BlindTrade arXiv:2603.17692); (3) WEAK: Anti-extrapolation instruction (keep as cheap guardrail but don't rely on it alone).
- LESSON: Update to 'Suppress LLM extrapolation bias' heuristic: the anti-extrapolation prompt is not sufficient. Anonymization is the most practical runtime defense without fine-tuning. If IS/OOS divergence is detected (CMMD test), schedule LoRA fine-tuning on labeled data.
- WHEN: Any LLM call making financial predictions or quality assessments in R28 Phase 2, R29 LLM filter, and any future earnings scoring pipeline.
- SOURCE: arXiv:2604.02921 (April 2026) full paper — Debiasing LLMs by Fine-tuning. Qwen3-32B tested.

### Regime-timing haircut for marketed backtests (arXiv:2604.18821)
- LESSON: Marketed backtests predominantly reflect the common factor regime at the time of backtest construction, not portable strategy-specific alpha. 75-81% of pro-forma outperformance evaporates after peer-benchmark adjustment.
- LESSON: Practical haircut formula: Expected live return = Backtest return − (5pp × regime_extremity_z_score). A strategy backtested during a strong bull market (z-score ~+2) faces ~10pp live deterioration. Apply on top of the 5bp/trade friction buffer (arXiv:2603.20319).
- LESSON: Risk metrics also deteriorate live: MaxDD worse in 54% of strategies, Sortino worse in 59%. Do not treat backtest risk numbers as reliable floor estimates.
- LESSON: Cold-regime launches perform slightly better live (+0.8%); hot-regime launches -3.5% to -4.5% by quintile. Our 2018-2024 backtest window is a predominantly warm/hot regime for US equities. All George Sharpe estimates should be deflated 10-20% before deployment decisions.
- WHEN: Evaluating any strategy for live trading eligibility. Reviewing rounds 28-35 results. Setting position sizing for live deployment.
- SOURCE: arXiv:2604.18821 (Chang Liu, U. Trento / Resonanz Capital, April 2026). 1,726 strategies, 10 global institutions. Journal of Asset Management (under review).

### LLM agent disposition effect and model selection for scoring agents
- LESSON: LLMs exhibit a documented DISPOSITION EFFECT (selling winners early) and recency-extrapolation in simulated markets (arXiv:2604.18373). These biases vary dramatically by model architecture: o3-mini 100% bubble formation, GPT-4o Mini high propensity; Qwen 2.5 / DeepSeek V3 near-rational (near-zero MSE from fundamental value).
- LESSON: For R28 Phase 2 and R29 LLM scoring agents, PREFER Qwen2.5-7B-Instruct or Qwen3-series over GPT-4o-mini as scoring worker models. Low bubble-propensity models produce more calibrated fundamental quality scores.
- LESSON: Prompt suppression instructions CAN modulate behavioral biases (e.g., momentum chasing, speculative bubbles) by ~5 units in the reasoning features. This is DIFFERENT from parameter-level extrapolation bias (arXiv:2604.02921): for behavioral choices, prompting works; for statistical extrapolation of recent returns, prompting doesn't work. Distinction matters for prompt design.
- LESSON: Heterogeneous LLM populations (mixing bubble-prone and stable models) still form bubbles 50% of the time even when bubble-formers are a minority. For a consensus gate requiring 2/3 agreement: if 1 agent is bubble-prone and 1 is stable, the bubble-prone agent's overconfidence can win. Screen models for bubble propensity before adding them to a consensus pipeline.
- WHEN: Selecting LLM models for R28 Phase 2, R29 LLM filter, any multi-agent scoring system. Writing prompt instructions for scoring agents.
- SOURCE: arXiv:2604.18373 (Ouyang & Sui, Oxford/CUHK, April 2026); arXiv:2604.18602 (Saxena et al., April 2026)

### Anti-extrapolation prompt is weak — anonymization + fine-tuning are real defenses
- LESSON: Adding 'Do not consider recent price performance' to LLM prompts has limited efficacy against extrapolation bias. The bias is parameter-encoded (pretraining + RLHF), not surface-level. Tested on Qwen3-32B: overreaction coefficient 0.394 with prompting remains high; only LoRA fine-tuning reverses it to -0.120.
- LESSON: For inference-time defense without fine-tuning, BlindTrade anonymization (replacing tickers with business descriptions) is the most effective approach — it bypasses the memorized price-association pathway rather than asking the model to ignore it.
- LESSON: Keep anti-extrapolation prompts as cheap weak guardrails, but design pipelines to not depend on them. True defense hierarchy: (1) LoRA fine-tuning on rational labels (parameter level), (2) anonymization (context restriction), (3) anti-extrapolation prompt (surface-level, limited).
- WHEN: Any generative LLM call making financial quality assessments in R28 Phase 2, R29 LLM filter, future earnings scoring.
- SOURCE: arXiv:2604.02921 (April 2026) full paper — Debiasing LLMs by Fine-tuning.

### Regime-timing haircut: 5pp × regime_extremity_z for live performance expectations
- LESSON: 75-81% of backtest outperformance is common factor regime exposure, NOT portable alpha. After peer-benchmark adjustment, the pro-forma edge nearly vanishes. Strategies launched in hot markets face 4+pp worse decay than cold-market launches.
- LESSON: Apply haircut formula before any live deployment decision: Expected live return = Backtest return - (5pp × regime_extremity_z_score). Our 2018-2024 backtest window = warm/hot US equity regime. Discount ALL George backtest Sharpe estimates by 10-20% additional beyond 5bp/trade friction (arXiv:2603.20319). Risk metrics (MaxDD, Sortino) also deteriorate live in 54-59% of strategies.
- WHEN: Evaluating rounds 28-35 for live trading eligibility. Setting position sizing. Post-R35 MRP diagnostic pass.
- SOURCE: arXiv:2604.18821 (Chang Liu, April 2026). 1,726 strategies, 10 global institutions.

### LLM model selection: Qwen family is low bubble-propensity for scoring agents
- LESSON: LLM bubble propensity varies dramatically: o3-mini and GPT-4o Mini show 100% or near-100% bubble formation in simulated markets; Qwen 2.5 and DeepSeek V3 show near-zero. For multi-agent scoring systems (R28 Phase 2, R29 LLM filter), prefer Qwen2.5-7B-Instruct or Qwen3-series as worker scoring agents.
- LESSON: Prompt suppression instructions DO work for behavioral tendencies (bubble chasing, momentum riding) — this is different from statistical extrapolation bias where prompting fails. Add cognitive framing prompts ('focus on fundamental value; do not chase momentum') for scoring agents in multi-agent pipelines.
- LESSON: Heterogeneous LLM populations form bubbles in 50% of markets even when bubble-formers are a minority — a single bubble-prone sub-agent can pull consensus. Screen every sub-agent model before production deployment.
- WHEN: Selecting models for any multi-agent LLM scoring pipeline. Designing R28 Phase 2 or R29 3-agent system.
- SOURCE: arXiv:2604.18373 (Ouyang & Sui, Oxford/CUHK, April 2026); arXiv:2604.18602 (Saxena et al., April 2026)

### Regime-dependent specialist pool routing (not binary VIX threshold)
- LESSON: The best strategy is regime-dependent, not stable. Maintain a CALM pool (LLM-augmented signal strategies: PEAD, Div Raise) and a STRESS pool (pure statistical strategies, no LLM dependency). Route via continuous stress probability = logistic(VIX_z + yield_curve_z + credit_spread_z) rather than a binary VIX threshold. Stress_prob > 0.6 = disable all LLM-dependent layers.
- LESSON: Calm regime specialists: GRU/HAR-RV/XGBoost-type models (adaptive, data-rich). Stress regime specialists: GARCH/FIGARCH-type (robust, heavy-tailed). Same principle applies at strategy level: LLM-augmented strategies underperform in stressed markets; pure statistical strategies are more robust.
- WHEN: RegimeGuard architecture decisions; R35 multi-strategy portfolio construction; any design that uses LLM signals that are regime-conditional.
- SOURCE: arXiv:2604.10402 (Risk-Sensitive Specialist Routing, April 2026). Consistent with arXiv:2604.10996 (LLM features decouple in macro shocks).

### Cognitive alpha reasoning before mutation
- LESSON: Before mutating or crossing over an alpha factor formula, prompt the LLM to first explain WHY the current formula is expected to work (economic mechanism). LLMs that reason about mechanism first generate economically plausible variants; blind mutation generates algebraically degenerate or spuriously correlated factors.
- LESSON: Use randomized temperature {0.7–1.2} for generation agents (ensures diversity in mutations/crossovers) and fixed low temperature (0.7–0.8) for quality-checking agents (ensures consistency in validation judgments). Mode collapse in generation = near-duplicate factor pool.
- WHEN: Any LLM-driven alpha mining iteration (R33 QuantaAlpha, AlphaPROBE, or future factor generation rounds).
- SOURCE: arXiv:2511.18850 (CogAlpha, revised April 2026). IC 0.0591 vs AlphaAgent 0.0246 (2.4x improvement on CSI300, validated on S&P 500).

### Code coverage as financial math hallucination guard
- LESSON: LLM-generated financial math code must pass ≥95% code coverage test before acceptance. Without this, LLMs generate 'algebraically plausible' but mathematically degenerate code (look-ahead in rolling windows, division-by-zero edge cases, incorrect annualization). Coverage threshold is an 'un-hackable' guard that prevents hallucination from propagating into backtest results.
- LESSON: When generated code fails validation, run 'Epistemic Autopsy': convert the failure to structured JSON {failure_type, formula, failure_reason, excluded_patterns} and prepend to the next generation prompt as exclusion context. This prevents re-generating the same class of failure.
- WHEN: R33 QuantaAlpha implementation; any session where Claude generates Python factor code for backtesting. Run pytest with coverage report before executing generated code on full dataset.
- SOURCE: arXiv:2604.11477 (OOM-RL, April 2026). System matured from Sharpe 0.35 (Phase 1) to Sharpe 2.06 (Phase 3) via architectural discipline.

### Purpose-conditioned bias: never reveal downstream trading objective in LLM prompts
- LESSON: When an LLM is told its output will be used to 'predict stock returns' or 'decide whether to initiate a trade', it exploits memorized training patterns to produce biased, goal-aligned scores. Pre-cutoff advantage: +0.483pp/month (p<0.05); post-cutoff: advantage collapses and OOS R² falls -5.37%/quarter. This is the 'purpose-conditioned cognition' effect — the LLM acts as a prediction agent rather than a neutral measurement tool.
- LESSON: This is a THIRD LLM contamination vector (distinct from ticker memorization arXiv:2603.17692 and extrapolation bias arXiv:2604.02921). Mitigation: Goal-blind prompts — never mention 'trading decision', 'PEAD trade', 'stock return prediction'. Say 'assess the fundamental quality of this earnings announcement as a financial analyst' NOT 'to decide whether to initiate a PEAD trade'. Do NOT mention: 'PEAD', 'trade', 'buy', 'sell', 'stock return'. Same applies to pairs plausibility prompts: say 'evaluate the economic relationship between Company A and Company B' not 'evaluate whether to trade the spread'.
- LESSON: Goal-blind prompts outperform goal-aware prompts OUT-OF-SAMPLE. The apparent in-sample boost from goal disclosure is memorization artifact. Full three-vector defense: (1) Goal-blind prompt (this lesson), (2) BlindTrade ticker anonymization, (3) Anti-extrapolation instruction (weak).
- WHEN: ANY LLM prompt used for earnings quality scoring (R28 Phase 2 EarningsQualityAgent), pair plausibility scoring (R29 LLM filter), or any intermediate LLM measure that feeds into a trading decision. Apply universally as zero-cost prompt design rule.
- SOURCE: arXiv:2602.09504 (Cao, Jiang, Xu — Feb 2026). GPT-4o-mini on earnings call transcripts. Effect: +0.483pp/month IS, collapses post-cutoff.

### GFlowNet diversity advantage for alpha mining
- LESSON: GFlowNet-based alpha generators (AlphaSAGE, arXiv:2509.25055) sample factors proportional to reward rather than argmax — they explore the full distribution of good solutions rather than collapsing to a single optimum. This produces more diverse, uncorrelated alphas than RL-based generators (AlphaGen-PPO), which suffer mode collapse and redundant factor discovery.
- WHEN: Building alpha libraries for R33 or any factor mining task. After running RL-based generators (QuantaAlpha, AlphaCFG), add a GFlowNet generator to fill uncorrelated niches. Measure pairwise IC of the combined pool before Lasso weighting.
- SOURCE: arXiv:2509.25055 (AlphaSAGE, Sep 2025), github.com/BerkinChen/AlphaSAGE. 2026-04-25 dream cycle.

### Prefer validated scoring taxonomies over ad-hoc LLM prompts for text quality scoring
- LESSON: For multi-dimension text scoring tasks (earnings call quality, analyst evasion, document clarity), prefer taxonomies with public annotated datasets and benchmark F1 scores over designing dimensions from scratch. Validated taxonomies (e.g., SubjECTive-QA's Assertive/Cautious/Optimistic/Specific/Clear/Relevant) transfer better across companies and time periods, can be calibrated against ground truth, and reduce design risk.
- WHEN: Any new LLM scoring dimension for R28/R31/R29 — first check if a validated public dataset covers the construct before designing novel prompts. SubjECTive-QA covers earnings call Q&A quality with 49K annotations. Check HuggingFace for domain-specific benchmarks before building from scratch.
- SOURCE: arXiv:2410.20651 (SubjECTive-QA, NeurIPS 2024), gtfintechlab/SubjECTive-QA. 2026-04-25 dream cycle.

### Factor family durability on US equities: range/vol persist, trend decays
- LESSON: On US equities (~500 stocks), range and volatility formula families are the most OOS-durable alpha factors (HAC-significant IC through 2025-2026 holdout). Trend/momentum formula families decay fastest — the weakest in-sample trend factor collapses materially OOS. When mining or seeding LLM factor generation on US equities, bias toward range and volatility families.
- LESSON: Family-aware selection prevents intra-family crowding. After applying correlation diversity filter (|corr|<0.70), explicitly enforce at least one representative from each factor family (range, volatility, trend, reversal, volume) in the final pool. Otherwise volatility factors alone dominate despite their pairwise corr being just below threshold.
- LESSON: Dual-channel RAG for factor generation: positive channel = high-IC factor examples from validated families (range, vol); negative channel = structured failure records (Epistemic Autopsy JSON from failed IC candidates). Both channels retrieved per LLM generation call. Negative channel is as important as positive for guiding away from dead-end formula patterns.
- WHEN: R33 QuantaAlpha seed construction and any LLM-driven factor mining round. Use range/vol family examples as positive RAG. Use Epistemic Autopsy failures as negative RAG.
- SOURCE: arXiv:2604.09601 (Hubble, April 2026). US ~500 stocks, OOS 2025-06 to 2026-03.

### Latent build-up phase precedes market stress — current regime signals miss it
- LESSON: Market stress regimes are preceded by a detectable 'latent build-up' phase where depth erosion and microstructure entropy rise BEFORE price impact occurs. Classical regime detection (HMM, VIX, RMT gap) triggers AT or AFTER stress onset — they are reactive. True early warning requires monitoring the build-up phase.
- LESSON: In LOB data, depth erosion (market makers quietly withdrawing resting orders) and HMM entropy (rising ambiguity in state transitions) are the dominant pre-crash signals — achieving +18-38 timestep/second lead with precision 1.0. Current R35 stack signals (RMT gap, Wasserstein HMM, skewness dispersion) are concurrent or lagging.
- LESSON: Daily yfinance proxies for depth erosion are experimental and UNVALIDATED: High-Low/Close ratio expansion + HMM state posterior entropy rise. Do not deploy without explicit backtesting. This is a concept for when LOB level-2 data is available (Polygon.io, IEX Cloud, IBKR).
- WHEN: R35 regime stack design (5th layer concept); any strategy requiring pre-emptive position reduction before stress onset. Flag as 'requires LOB data upgrade' until level-2 feed is secured.
- SOURCE: arXiv:2604.20949 (Hiremath & Hiremath, April 2026). GitHub: prakulhiremath/LOB-Latent-Regimes.

### CRISP optimizer for alpha-signal portfolio construction
- LESSON: When combining alpha factor signals into a portfolio, CRISP (P_γ·w = μ where P_γ = (1−γ)D + γΣ) achieves 80-94% of oracle Sharpe across all regimes. Standard Markowitz (γ=1) overfits with limited history; inverse-variance (γ=0) ignores alpha. CRISP interpolates optimally. Optimal γ* ≈ 1/(1 + c·κ(C)²·N/(T·IC²)). Safe default: γ=0.5 (OOS plateau width 0.38 — nearby γ values perform nearly the same).
- LESSON: For mined factor portfolios with estimated IC ≈ 0.05-0.10, use γ=0.3-0.5. For IC > 0.12 (QuantaAlpha-level), use γ=0.6-0.7. When IC is uncertain (stressed regime, VIX>25), default to γ=0.2 (closer to inverse-variance). This upgrades Lasso sparse weighting to an IC-adaptive method.
- WHEN: R33 factor portfolio final construction step; any multi-signal combination with known alpha estimate; R28/R29 when combining LLM-derived scores.
- SOURCE: arXiv:2604.23833 (Wuebben, April 2026)

### LLM representation homogeneity risk in multi-agent pipelines
- LESSON: Representation homogeneity (agents sharing a foundation model backbone) dominates risk-aversion heterogeneity in driving crash frequency and tail risk (arXiv:2604.22818). Fragility doesn't require identical agents — only similar enough foundations. In normal markets, homogeneity suppresses perceived volatility → false security → synchronized collapse.
- LESSON: In any multi-LLM scoring pipeline (R28 3-agent, R29 LLM filter, R33 factor mining), use backbones from ≥2 different model families (e.g., Claude + Qwen, not two Claude instances). Same backbone = correlated representations = correlated failures under regime shift.
- LESSON: Cross-LLM-agent forecast dispersion is a systemic risk leading indicator. Sharp DROP in dispersion of fundamental outlook scores across a broad universe = high-homogeneity fragile state → reduce position sizes proactively.
- WHEN: R33 multi-generator factor mining; R28 Phase 2 multi-agent scoring design; R35 regime stack monitoring.
- SOURCE: arXiv:2604.22818 (Qiu & Han, April 2026)

### Asymmetric beta pre-filter for pairs trading
- LESSON: Pairs where one asset has significantly different upside vs downside beta profiles relative to the other generate spurious spread dynamics during market directional moves — these are NOT mean-reversion opportunities. Compute rolling upside_beta and downside_beta separately (OLS on SPY>0 and SPY<0 days). Require |upside_beta_A - upside_beta_B| < 0.4 AND |downside_beta_A - downside_beta_B| < 0.4 before entering a spread position.
- WHEN: Any pairs trading or stat-arb strategy. Apply as Stage 0.5 between factor residualization and cointegration testing in R29 LLM filter.
- SOURCE: arXiv:2604.22933 (Conlon, Cotter, Kynigakis, April 2026) — ML Forecasts of Asymmetric Betas.

### LLM model size gradient in fundamental signal extraction
- LESSON: Within the same knowledge cutoff, larger LLM models extract stronger fundamental signals from public textual information. Effect is ~30% stronger per model tier (GPT-4.1 vs GPT-4.1-mini vs GPT-4.1-nano; gamma=0.0122 vs 0.0093 vs 0.0065). Use frontier-tier models (Claude-Sonnet, not Claude-Haiku) for quality-judgment sub-agents where the call volume is low (<50/day). Reserve Haiku for high-volume cheap classification only.
- LESSON: LLM fundamental quality signals are STRONGEST for high analyst-coverage stocks (interaction t=2.44). For PEAD on large-cap / S&P 500 stocks, LLM scoring is MORE reliable than for small-caps, because large-caps have richer dispersed information environments that LLMs aggregate well.
- WHEN: Designing any LLM scoring pipeline (R28 Phase 2, R29 LLM filter, R31 text PEAD). Model selection for worker agents.
- SOURCE: arXiv:2604.21433 (Lehner & Lopez-Lira, April 2026) — ChatGPT as Time Capsule.

### Multi-judge consistency gate before deploying LLM scoring systems (ValueAlpha)
- LESSON: A single LLM judge's score is insufficient to trust for deployment decisions. Before using an LLM score to filter trading signals, validate inter-model consistency using quadratic-weighted kappa across 3 LLM families (e.g., Claude + Qwen + Gemini). Require κ̄w >= 0.4. Below this threshold: report as methodology finding only, do not deploy.
- LESSON: 'Score-only output is malformed.' Require each LLM scoring call to output: score + relationship type + 3-5 sentence reasoning + confidence. Terse (<60 token) responses receive a -2.81 rubric penalty from multi-judge validators — brevity is penalized even when correct.
- LESSON: Use ABSOLUTE scoring (0-100) not pairwise comparison in LLM judge prompts. 8 of 9 LLM judge models show degenerate positional bias ('always-A') in pairwise comparison tasks. Absolute rubric scoring is far more reliable.
- WHEN: Before deploying any LLM-based scoring system to filter trades (R29 LLM plausibility filter, R28 Phase 2 EarningsQualityAgent). Combine with CMMD contamination check for complete pre-deployment validation: (1) ValueAlpha kappa gate = checks consistency, (2) CMMD = checks memorization.
- SOURCE: arXiv:2604.25224 (ValueAlpha, April 28 2026); arXiv:2604.23478 (JudgeSense, April 26 2026)

### Falsifiable hypothesis + append-only trace for iterative LLM alpha mining
- LESSON: Each generated factor candidate in an LLM alpha mining loop must specify a FALSIFIABLE HYPOTHESIS before code generation (5 required fields: name, falsifiable hypothesis, economic rationale, candidate type, executable recipe). This prevents the LLM from generating algebraically plausible but economically meaningless factors.
- LESSON: Maintain an append-only experiment trace — never delete failed hypothesis records. This is the enforcement mechanism preventing hypothesis re-exploration. Pair with FactorMiner's failure exclusion pool (structured JSON) as dual memory: trace = history, failure pool = negative RAG context.
- LESSON: Apply IC gate ONLY on the in-sample training window. Never use validation or test set for selection decisions. This is the correct protocol for clean holdout integrity.
- WHEN: R33 QuantaAlpha/AlphaPROBE factor mining; any iterative LLM-driven generation loop where past failures carry information.
- SOURCE: arXiv:2604.26747 (Hypotheses to Factors, April 29 2026; Sharpe 1.55 OOS on crypto 2024-2026)

### Efficient multivariate Kelly: O(N) exact solution for N independent bets
- LESSON: Traditional multivariate Kelly requires O(2^N) computation — intractable for N > 30. For N independent simultaneous positions (e.g., 20 pairs trades), the integral transform method reduces this to O(N). For correlated positions, the decomposition method provides upper/lower bounds with sigmoidal accuracy scaling (predictable suboptimality given subproblem size).
- LESSON: With <= 30 simultaneous positions (R29 pairs portfolio), exact multivariate Kelly is computationally trivial. No approximation needed. Estimate per-pair outcome probabilities from historical spread distribution (z-score entry → historical P(mean reversion within hold period)).
- WHEN: Position sizing for R29 pairs portfolio (20 simultaneous positions); R32 multi-strike options; any multi-position strategy where Kelly optimization was avoided due to combinatorial complexity.
- SOURCE: arXiv:2604.24723 (Tepelyan & Lam, April 27-29 2026)
