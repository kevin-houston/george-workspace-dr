---
created: 2026-07-15
updated: 2026-07-15
type: concept
category: AI Industry
---

# What Useful Alphas? — Chen & Welch (arXiv:2607.06502)

**Source:** Chen, Andrew Y. and Welch, Ivo. "What Useful Alphas?" arXiv:2607.06502. Federal Reserve Board / UCLA. July 8, 2026.

**Related pages:** [LLM Alpha Mining Systems 2026](llm-alpha-mining-systems-2026.md) | [Momentum Strategies](../trading/algorithms/momentum-strategies.md) | [Hypothesis Log](../trading/backtesting/hypothesis-log.md) | [Multiple Testing & Statistical Significance](../trading/backtesting/multiple-testing.md)

---

## Core Finding

Examining ~200 published long-short anomaly equity portfolios from academic literature:

| Sample restriction | Median return (bp/month) |
|---|---|
| All stocks, all years (pre-2005) | 48 bp |
| Post-2005 only | 19 bp |
| Non-micro top-3,000 stocks only | 26 bp |
| Post-2005 AND non-micro top-3,000 | **7 bp** |

The 7 bp figure — approximately 0.84% annualized — is economically negligible. Even modest transaction cost allowances eliminate it entirely.

**Conclusion:** Published academic anomalies have been **useless to non-micro-cap portfolio managers in the 21st century**.

---

## Why This Matters for Kevin's Trading Project

### Validates the NOT CONFIRMED pattern

The hypothesis log shows a high NOT CONFIRMED rate (roughly 60%) across H240–H380. This paper provides the academic explanation: most anomalies were discovered on pre-2005 data, on micro-cap stocks, or both. Strategies that rely on textbook anomalies (GEM/PACS, factor ETFs, sector breadth timing) failing OOS is not a methodology error — it is the expected result given Chen & Welch's finding.

**Specific NOT CONFIRMED hypotheses this explains:**
- H255 (Factor ETF Momentum) — most factor ETFs contain large-cap non-micro stocks post-2005
- H256 (Dual Momentum/GEM) — relies on documented IS anomaly that decayed post-2005
- H300 (yield curve timing) — macro anomaly from pre-2005 literature
- H298 (weekly ETF reversal) — Lehmann 1990 finding pre-dates 2005
- H337 (GP/A quality tiebreaker) — quality signal strongest in small/micro caps

### Highlights what survives

The paper confirms that a small subset of signals **do** survive the post-2005, non-micro filter:
- **Momentum** (cross-sectional, 6-12 month) — H198's 6-1m momentum is precisely the surviving anomaly family
- **Market microstructure** — short-term reversal in liquid non-micro stocks (H181 OOS 1.138)
- **Event-driven / information signals** — NLP-based PEAD (H163/H174) exploits announcement information, not a static factor

### Implications for dream cycle hypothesis generation

New hypotheses should target:
1. **Information-based alpha** (8-K NLP, earnings call sentiment, alternative data) — not exhausted by arbitrage in non-micro universe
2. **Structural alpha** (IBS mean-reversion, options VRP) — microstructure effects, not factor anomalies
3. **Adaptive/regime-conditional signals** — static factor portfolios decay; regime-aware strategies (H249, H301, H361, H362) resist decay

Avoid: new factor combinations from academic papers published before 2010. The anomaly zoo is effectively closed for non-micro investors.

---

## Mechanism: Why Did Anomalies Decay?

The authors identify three candidate explanations consistent with the data:

1. **Publication and arbitrage**: after publication, institutional capital crowds the trade, eliminating the spread
2. **Market electronification**: post-2008 electronic market structure reduced microstructure-based alpha
3. **Survivorship in publishing**: journals over-select anomalies with large IS IS Sharpe — inflated by data-mining, not genuine alpha

All three likely contribute. The cross-sectional pattern (micro-cap anomalies survive longer) is most consistent with explanation 1 — arbitrageurs face higher costs in micro-cap and avoid them, letting IS anomalies persist there.

---

## Connection to H198 / Production Portfolio

Cross-sectional momentum (H198, H026 ETF rotation) survives for reasons distinct from the typical factor anomaly:
- **Behavioral persistence**: herding, disposition effect, and underreaction to earnings are not purely arbitraged away
- **Monthly rebalancing**: avoids the microstructure crowding that kills short-term signals
- **Order Block enhancement** (H344-H346): selecting within momentum using regime signals improves OOS further — exactly the regime-conditional pattern Chen & Welch implicitly endorse

---

## Cross-References

- [Multiple Testing & Statistical Significance](../trading/backtesting/multiple-testing.md) — deflated Sharpe ratio; why most published Sharpe ratios are inflated
- [Signal Half-Life & Alpha Decay](../trading/backtesting/signal-halflife.md) — AI-driven compression of momentum half-life; consistent with post-2005 decay
- [LLM Alpha Mining Systems 2026](llm-alpha-mining-systems-2026.md) — LLM-discovered alphas face same decay risk unless tested post-2005 non-micro
- [Shared Strategy Evaluation Checklist](../trading/shared-eval-checklist.md) — item 3 (OOS regime coverage) should now explicitly require post-2005 non-micro test