---
date: 2026-05-30
type: wiki-expansion
section: paper-trading
---

# Research Log — 2026-05-30

## Phase 1: Wiki Expansion — Paper Trading (thinnest section, 3 pages)

**New page:** `wiki/trading/paper-trading/live-graduation-criteria.md`

The Paper Trading section had only 3 pages (h122-alpaca, pead-nlp-alpaca, h181-alpaca), all deployment logs with no methodology. Added a methodological reference page covering:

### Key additions

**SPRT graduation test (Wald 1945)** — Sequential Probability Ratio Test applied to strategy validation:
- H0: strategy WR dropped to 60% (broken), H1: WR = 80% (working as confirmed)
- α=0.05, β=0.10 → log(A)=2.89 upper threshold, log(B)=−2.25 lower threshold
- Advantage over fixed-sample tests: valid to check after every trade; minimizes required trade count

**Minimum sample sizes** from first principles:
- PEAD H174: 20 qualifying events minimum (SE ≈ 8.6pp on 20 trades given 81.8% WR)
- Monthly strategies (H026, H181): 6 months minimum, 12 preferred
- IBS: 60 signals minimum

**Regime coverage gates** — paper trading results only valid if period includes:
- ≥1 month with VIX > 20
- ≥1 month with SPY < −3%
- ≥1 TSMOM filter event (BIL month) for H026

**Performance attribution framework** — decomposing paper vs live divergence:
- Slippage drag estimated: H026 ~0.36%/yr, H181 ~3.6%/yr, PEAD ~1.2–2.4%/yr, IBS ~4.7–9.4%/yr
- Normal residual range: −1.0% to +0.5%/month
- H026 is most fill-insensitive (ETF spreads 0.03%); IBS is most drag-sensitive (6 trades/week)

**Current status:** No strategy has cleared all three gates yet. H026 earliest graduation Q3 2026; PEAD ~October 2026 (needs ~15 more qualifying events at current rate).

### Sources consulted

- Alpaca Markets live/paper comparison guide (alpaca.markets/learn)
- TradersPost paper trading reliability guide
- SPRT theory from Wald (1945) and statsig.com SPRT documentation
- López de Prado (2018) — Chapter 11 strategy evaluation framework

---

## Phase 2: Dream Cycle Scan

See: `dream_cycle/research/2026-05-30_scan.json`

Papers and repos scanned across 5 angles:

### Pairs Trading + LLM (Angle 1)
No new LLM+cointegration papers found on arXiv 2025-2026. The pairs family remains exhausted for daily frequency US equities. No proposals.

### PEAD + Earnings NLP (Angle 2)
- arXiv:2605.25894 (May 2026): Multi-modal PEAD prediction — FinBERT sentiment + fundamentals + price features, Transformer model superior sensitivity. No specific Sharpe numbers but confirms FinBERT still valuable for earnings day prediction. Low relevance (no new data source or signal edge over H174).
- arXiv:2512.19484 (Dec 2025): LLM-extracted event features from news for cross-sectional return prediction. Broader than PEAD, no earnings-specific focus. Medium relevance for future H238+ work.
- "Beyond the last surprise: Reviving PEAD with machine learning and historical earnings" (Kaczmarek & Zaremba, 2025): Historical EPS surprise patterns + ML. Potentially relevant but H164 already tested elastic-net SUE with 4yr yfinance limit — this is blocked by same data constraint. No stage.

### Cross-Sectional Momentum (Angle 3)
- arXiv:2511.12490 (Nov 2025): **"Discovery of a 13-Sharpe OOS Factor: Drift Regimes Unlock Hidden Cross-Sectional Predictability"** — drift regime defined as >60% positive days in trailing 63-day window; STAGED as H237 (new hypothesis variant of H221 with better regime definition).
- arXiv:2512.11913 (Dec 2025): "Not All Factors Crowd Equally: Modeling, Measuring, and Trading on Alpha Decay" — factor crowding accelerated post-2015 (ETF growth), crowding predicts tail risk not average returns, momentum R²=0.65 with crowding model. STAGED as wiki update to algorithms/momentum-strategies.md.
- arXiv:2602.00080 (Jan 2026): GT-Score — composite objective function for reducing backtesting overfitting: 98% improvement in generalization ratio vs Sharpe optimization. STAGED as wiki update to backtesting/design-principles.md.

### Multi-Agent LLM Trading (Angle 4)
- arXiv:2602.07085 (Feb 2026): AlphaAgent — LLM-driven alpha mining with AST-based originality enforcement, anti-crowding regularization. Tests on both CSI 500 and S&P 500. GitHub: github.com/RndmVariableQ/AlphaAgent. Complements QuantaAlpha (already noted). STAGED as wiki update to tools/ml-for-trading.md.
- arXiv:2605.19337 (May 2026): "Agentic Trading: When LLM Agents Meet Financial Markets" — systematic review of 77 studies; key finding: only 2/19 have valid time-consistent splits, 15/19 are R0 reproducibility. Important caveat for all LLM trading results. STAGED in wiki update.

### GitHub Trending Quant (Angle 5)
- QuantaAlpha (arXiv:2602.07085): ~995 GitHub stars, Feb 2026. LLM + evolutionary algorithm for factor mining. CSI 300 primary, transfers to S&P 500. Primarily suited for broader universe (200+ stocks). No stage — similar to AlphaCrafter H209.
- AlphaAgent (github.com/RndmVariableQ/AlphaAgent): Anti-crowding regularization. Both CSI 500 and S&P 500. Potentially more robust than QuantaAlpha for US equities due to originality enforcement.

### Proposals staged: 4
1. `1_h237_drift_regime_reversal.json` — new hypothesis
2. `2_gt_score_wiki.json` — wiki update backtesting
3. `3_alphabot_wiki.json` — wiki update tools  
4. `4_factor_crowding_wiki.json` — wiki update algorithms
