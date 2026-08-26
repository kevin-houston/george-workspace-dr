---
created: 2026-08-26
updated: 2026-08-26
type: source_summary
authors: Weixian Waylon Li, Hyeonjun Kim, Mihai Cucuringu, Tiejun Ma
published: KDD 2026 (Datasets & Benchmarks Track, Oral), originally arXiv May 2025
source: arXiv:2505.07078
url: https://arxiv.org/abs/2505.07078
code: https://github.com/waylonli/FINSABER
license: Apache-2.0 (code); paper KDD 2026
---

# Can LLM-based Financial Investing Strategies Outperform the Market in Long Run? (Li, Kim, Cucuringu & Ma, KDD 2026)

**Authors:** Weixian Waylon Li, Hyeonjun Kim, Mihai Cucuringu, Tiejun Ma
**Venue:** KDD 2026, Datasets & Benchmarks Track, Oral presentation (Jeju Island, Korea)

Already cited in passing in [Alpha Illusion — LLM Validation Checklist](../algorithms/llm-alpha-validation.md) (line 49, "FINSABER... found LLM advantages reported in prior literature 'deteriorate significantly under broader cross-section'"), but not yet ingested as its own source page with the methodology, mechanism, or the now-released open-source benchmark code. This page fills that gap.

## The question

Most published LLM-timing-strategy results (FinMem, FinAgent, TradingAgents, etc. — the same systems audited by Sheng et al. 2025's Alpha Illusion paper) are backtested on narrow windows (often 1-2 years) and small stock lists (often <20 names). Do the reported advantages survive when tested on the scale real production strategies actually need: two decades and 100+ symbols?

## Method: FINSABER framework

The authors built and open-sourced **FINSABER** (`pip install finsaber`, Apache-2.0, 143★, actively maintained — last push 2026-08-20, in active development as "FINSABER-2"), a three-module backtesting framework purpose-built to close known LLM-backtest bias gaps:

1. **Multi-source data module** — daily OHLCV (price), per-ticker news text by date, and quarterly/annual filings (`filing_q`/`filing_k`), loaded from a parquet dataset or in-memory dicts.
2. **Modular strategy base** — supports buy-and-hold, technical, ML, and LLM-agent strategies under one harness so an LLM component can be ablated in/out against the same data.
3. **Bias-aware two-step backtesting pipeline** — the README states explicit rules that map directly onto bugs George's own pipeline has hit before: "Use adjusted OHLC for price simulation and raw volume for liquidity caps" and **"Date-only news or filing data should be treated as available no earlier than the next trading decision"** — i.e., a built-in guard against exactly the as-of-date look-ahead bug class that H510-H514 found in George's own OB-filter code. Execution timing defaults to `execution_timing: "next_open"` specifically to prevent same-day-close bias.

Minimal usage:
```python
from finsaber import FINSABERBt, FinsaberParquetDataset
from finsaber.strategy.timing import BuyAndHoldStrategy

data = FinsaberParquetDataset("/path/to/sp500_2000_2025_parquet")
config = {
    "data_loader": data,
    "tickers": ["AAPL"],
    "date_from": "2024-01-02",
    "date_to": "2024-01-10",
    "setup_name": "demo_buy_hold",
    "execution_timing": "next_open",
}
results = FINSABERBt(config).run_iterative_tickers(BuyAndHoldStrategy)
```
LLM inference cost is tracked as a first-class cost line via `finsaber.toolkit.llm_cost_monitor`, feeding into `total_trading_cost` — directly operationalizing Sheng et al.'s P5 "inference latency/cost is a real-world friction" requirement rather than leaving it as a checklist item nobody measures.

## Result

Testing LLM timing strategies over **two decades and 100+ stock symbols** (vs. the 1-2 year / <20-symbol scope of most prior LLM-trading papers):

- **Reported LLM advantages deteriorate significantly** once evaluated on a broader cross-section and longer horizon.
- **Regime-conditional failure mode, not uniform underperformance**: LLM strategies underperform passive benchmarks *in bull markets* (excessive conservatism — the agents hedge/de-risk when a dumb buy-and-hold would have compounded) and *overtrade/over-aggress in bear markets*, taking losses a simpler trend rule would have avoided.
- Attribution: much of the previously-reported edge in the literature traces to **survivorship and data-snooping bias** in small hand-picked stock universes and short windows, not to genuine LLM skill.
- Authors' explicit recommendation: focus engineering effort on **trend detection and regime-aware risk controls**, not on scaling framework/agent complexity (more agents, more debate rounds, bigger models) — complexity was not the bottleneck.

## Relevance to George's stack

This is independent, large-scale, mechanism-level confirmation of a pattern George has already found empirically at much smaller scale:

1. **Directly corroborates H520/H521's "LLM multi-agent trading exhibits degeneracy" finding** (cited in the trading index as the reason H280/H281/H319 are deprioritized) — FINSABER's regime-conditional failure mode (too conservative in bulls, too aggressive in bears) gives a *specific mechanism* for that degeneracy rather than just an aggregate Sharpe miss, which is more useful for deciding whether any future LLM-trading hypothesis is salvageable versus structurally doomed.
2. **The "next-trading-decision" news/filing availability rule is a ready-made structural fix**, not just a checklist item, for the exact bug class H509-H514 found by hand (unshifted signals, `as_of` dates that leak the current period's own close). If George ever builds a from-scratch backtester for a text/filing-driven hypothesis (PEAD family, H316/H319 semantic pairs), FINSABER's data-loader convention is a concrete pattern to copy rather than reinvent.
3. **Adds a fourth citation to the "LLM-alpha skepticism" cluster** alongside Sheng et al. 2605.16895 (Alpha Illusion), the price-vs-embedding EMH test (arXiv:2509.01590), and George's own H520/H521 — now four independent lines of evidence, spanning theory-audit, empirical clustering, empirical backtesting-at-scale, and George's own replication, all pointing the same direction: LLM trading-agent alpha claims in the literature do not survive scale, longer horizons, or honest cost/bias accounting. This further lowers the prior on H280 (MarketSenseAI) and H319 (LLM semantic network) being worth running without a much narrower, mechanism-specific hypothesis design.
4. **Not immediately actionable as a hypothesis** — this is a benchmark/methodology paper, not a strategy paper. No new H-number proposed from this alone; it strengthens the case for keeping H280/H281/H319 deprioritized rather than opening new work.

## See Also

- [Alpha Illusion — LLM Validation Checklist](../algorithms/llm-alpha-validation.md) — the 6-test structural validity framework this paper's Test 3 (Counterfactual Robustness) citation comes from; now cross-linked back to this fuller writeup
- [Multi-Agent LLM Trading](../algorithms/multi-agent-llm-trading.md) — H520/H521 degeneracy finding this paper independently corroborates
- [LLM Embeddings vs. Price — EMH Test](llm-embeddings-vs-price-stock-clustering-2025.md) — companion skepticism-cluster paper, same conclusion (LLM text signal loses to simpler baseline at scale) via a different mechanism (clustering RMSE vs. backtested Sharpe)
