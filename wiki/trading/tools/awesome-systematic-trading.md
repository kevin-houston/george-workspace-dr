---
added: 2026-08-07
updated: 2026-08-07
category: tools
url: https://github.com/paperswithbacktest/awesome-systematic-trading
relevance: hypothesis sourcing, library/broker/data-source reference
---

# Awesome Systematic Trading (paperswithbacktest)

Curated "awesome list" for quantitative/systematic trading, maintained by the
paperswithbacktest.com team. Kevin flagged it 2026-08-07 (previously noted in
passing during the 2026-06-06 dream cycle scan but never given its own page).

## What it contains

- **97 libraries/packages**, grouped by function: backtesting/live-trading
  frameworks (event-driven and vectorized), crypto-specific tools, trading
  bots/alpha models, analytics (indicators/metrics/optimization/pricing/risk),
  broker APIs, data sources, ML/data-science tooling, databases, visualization.
- **40+ strategies** described by institutional and academic sources — the
  most directly useful section for hypothesis sourcing, parallel to how the
  hypothesis-log pulls from arXiv papers.
- Educational resources: 55 books (beginner/biography/coding/crypto/HFT/ML),
  23 videos/interviews, blogs and courses.
- Covers stocks, futures, options, crypto, and commodities; both research and
  live-implementation angles.

## Notable libraries already in George's stack or worth checking against it

- **vectorbt** — already compared in `backtrader-vs-vectorbt.md`.
- **CCXT** — 100+ exchange crypto API; relevant to the Kraken CLI work
  (`kraken-cli.md`) if broader crypto exchange coverage is ever needed.
- **yfinance** — already the primary equity data source across the
  hypothesis-log backtests.
- **OpenBB Terminal** — investment research platform, not yet evaluated here.
- **vnpy**, **Freqtrade**, **zipline** — full trading-system/backtest
  platforms, not yet evaluated against the existing `run_hNNN.py` framework;
  lower priority since the current lightweight pandas-based framework already
  covers the needed IS/OOS/WF backtest discipline.

## Metrics (as of 2026-08-07 check)

12.8k stars, 1.6k forks, actively maintained (13 open issues, 42 open PRs),
primarily Python with Go/Rust alternatives listed. Includes a Chinese-language
README variant.

## Use going forward

Treat as a **reference index, not a source to ingest wholesale** — the
"40+ strategies" section is the highest-value part for the nightly dream-cycle
scan's hypothesis-sourcing angles (parallel to the arXiv scan angles already
in use); check it periodically for strategies not yet covered by H001-H494
rather than re-reading it in full each time. The library/tool sections are a
good first stop before evaluating any new backtesting framework or data
source, to confirm whether something already in the current stack (yfinance,
Alpaca, vectorbt-adjacent patterns) already covers the need.

## Related pages

- [Backtrader vs vectorbt](backtrader-vs-vectorbt.md)
- [Kraken CLI](kraken-cli.md)
- [QuantMind](quant-mind.md)
- [Hypothesis Log](../backtesting/hypothesis-log.md)
