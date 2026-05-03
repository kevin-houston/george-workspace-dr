# LLM Signal Research

*The core finding from R26 and the subsequent literature review is that LLMs should not be used as technical signal filters on event-driven strategies like PEAD — the LLM penalizes exactly the "ugly" setups that are strong signals. However, LLMs add genuine value in three specific roles: (1) economic plausibility screening for pairs trading, (2) narrative generation for product features, and (3) RAG-grounded fundamental quality assessment. The key variable is what question you ask the LLM, not whether you use one.*

---

## R26: LLM Indicator Filter on PEAD

**Setup**: IndicatorAgent scoring on 80 PEAD events | 15 large-caps | 2021-2025
**Inspired by**: QuantAgent (arXiv:2509.09995)

### Results ⚠️

| Signal Group | Sharpe | Win Rate |
|-------------|--------|----------|
| Baseline (all signals) | 0.771 | 51% |
| LLM-confirmed signals | **0.716** | 48% |
| LLM-rejected signals | **0.904** | 56% |

**The signals the IndicatorAgent would reject outperform those it confirms by 26% Sharpe.**

60% of signals were confirmed (n=48); the other 40% (n=32) had HIGHER forward returns.

### Why It Failed

PEAD fires when RSI is 60-75+ and price is extended above moving averages — exactly the conditions IndicatorAgent penalizes as "overbought." Institutions chasing an earnings beat do not care about chart aesthetics. The ugly setup IS the signal.

**Technical patterns → LLM filtering HELPS (cleaner setups, better context)**
**Event-driven patterns (PEAD) → LLM filtering HURTS ("overbought" IS the signal)**

---

## When LLM Filtering Helps vs. Hurts

| Use Case | LLM Role | Expected Effect | Evidence |
|----------|----------|-----------------|---------|
| PEAD signal filter | Technical judge | HURTS | R26 confirmed |
| Pairs trading filter | Economic plausibility judge | HELPS | arXiv:2602.07048 |
| PEAD narrative generation | Story writer | Value-add (product) | R26 insight |
| Regime assessment | Portfolio-level switch | Predicted HELPS | Hypothesis R28 |
| Earnings quality (with RAG) | Fundamental judge | Expected HELPS | arXiv:2602.00196 |
| Bare entry/exit timing | Market timer | HURTS | FINSABER confirmed |

---

## FINSABER: LLM Investing Failure Modes

Source: arXiv:2505.07078 (May 2025) — 20-year, 100+ symbol study

- LLMs are **overly conservative in bull markets** (miss gains) and **overly aggressive in bear markets** (incur losses)
- This is the OPPOSITE of optimal behavior
- Root cause: **poor regime detection**, not poor stock selection
- Validates R26: the LLM fails on timing, not on fundamental judgment

**Lesson**: Before adding any LLM timing to any strategy, add explicit regime-aware hard rules (VIX threshold, trend filter, SMA regime) as a hard constraint first. LLM judgment is NOT a substitute for regime detection.

---

## LLM Semantic Filter for Pairs (Predicted to Help)

Source: arXiv:2602.07048 (Feb 2026)

The R26 LLM filter asked: *"Is this chart overbought?"* (technical, wrong question for PEAD)
The R29 LLM filter will ask: *"Does an economic mechanism explain why A and B should co-move?"* (semantic, right question for pairs)

### Paper Results (Different Dataset)
- Statistical-only baseline vs. two-stage (stats + LLM filter):
  - PnL: +205%
  - Win rate: 51.4% → 54.5%
  - Average loss magnitude: **-46.5%** (dominant effect is loss reduction)

The dominant driver is **downside control, not return enhancement**. The LLM eliminates the worst pairs (spurious statistical correlation with no economic backing) rather than finding the best pairs.

**Prompt pattern for R29**:
> "Stock A: [description, sector, business model]. Stock B: [description, sector, business model]. Statistical analysis shows cointegration. Is there a plausible economic mechanism explaining why A and B should track each other over time? Score 0-100."
> Skip pairs scoring < 40.

---

## RAG-Grounded LLM: The Fix for Bare Prompts

Source: arXiv:2602.00196 (Jan 2026) — Generative AI for Stock Selection

**Why bare LLM filtering failed (R26)**: No grounding → the LLM applies generic heuristics ("looks overbought") that are wrong for event-driven strategies.

**LLM with RAG**: +14% to +91% Sharpe improvement vs. baseline; **RAG corpus quality is the pivotal variable**

Minimum viable RAG corpus per earnings event:
1. 8-K text for the quarter
2. Top 3 news headlines on earnings day
3. Last quarter's guidance language

This provides enough context to distinguish "organic beat" from "one-time item" reliably.

**Application to R28**: Build mini-RAG per PEAD event → EarningsQualityAgent asks "Is this an organic earnings beat?" not "Is the chart overbought?"

---

## QuantAgent (arXiv:2509.09995)

Architecture: 4 specialized agents — Indicator, Pattern, Trend, Risk
- Zero-shot on OHLC data: **80% directional accuracy** on 4H intervals
- Outperforms rule-based + neural baselines on BTC, Nasdaq futures, 8 other instruments
- Limitation: accuracy degrades on sub-15-min bars; not suitable for HFT
- GitHub: https://github.com/Y-Research-SBU/QuantAgent

**Kevin's application**: R26 was inspired by QuantAgent but used IndicatorAgent only (one of four agents). Full multi-agent system on PEAD remains untested with the fundamental/news agents.

**Product application**: LLM-generated signal narratives as premium feature in Macro Regime Dashboard product

---

## FinBERT as Exit Sentinel (Not Entry Filter)

Source: arXiv:2601.19504 (Jan 2026) — Sharpe 1.68, 135% return vs S&P 53% (Jan 2023–Jan 2025)

The key pattern: FinBERT used as **EXIT risk control** (sentiment < -0.70 → exit), NOT as entry filter.

- Entry filtering kills too many signals (false negatives are expensive)
- Exit risk control only fires on strong negative news (rare, high-threshold)
- Prevents holding through news-driven crashes without suppressing entries on neutral-news days

**Application**: Add FinBERT exit sentinel to dividend covered-call strategies. When news sentiment on the underlying drops below -0.70, close the covered call position regardless of technical status.

---

## Related Topics

- [[pead-strategy]] — Full R26 context and PEAD mechanics
- [[pairs-trading]] — R29 LLM semantic filter design
- [[research-agenda]] — R28 (TradingAgents overlay), R31 (text PEAD)
- [[ai-research-papers]] — Paper summaries for QuantAgent, FINSABER, etc.
- [[ml-for-trading]] — Non-LLM ML approaches

## Sources
- Master Trading Report (R26, R28 sections): raw/master_trading_report_2026-04-05.md
- Memory Snapshot (R26-R32 findings, paper summaries): raw/MEMORY_snapshot_2026-04-05.md
- Heuristics Snapshot (LLM lessons): raw/heuristics_snapshot_2026-04-05.md
