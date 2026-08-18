---
title: public-apis — Curated Free API Directory
added: 2026-08-18
category: tools
url: https://github.com/public-apis/public-apis
---

# public-apis

The largest general-purpose curated list of free, public APIs — organized into ~60 categories (Finance, Machine Learning, Government, Health, Geocoding, Cryptocurrency, News, Science & Math, etc.). ~464k stars, MIT license, actively maintained (last push 2026-08-17). Not a tool itself — a directory/index for discovering data sources.

## Finance Category — Notable Entries

Most of the well-known names we already use are listed (Alpaca, Alpha Vantage, FMP, FRED, Polygon, Yahoo Finance, SEC EDGAR), which is a decent sanity check that our existing stack tracks the mainstream free-tier options. Standouts we don't currently use:

- **CongressInvests** (`congressinvests.com`) — real-time U.S. congressional stock trade disclosures from Senate EFD/House Clerk filings, `apiKey`. Overlaps with the Congressional trading angle already noted in `alternative-data.md`; worth a diff-check against what we're pulling there.
- **Dino.markets** (`dino.markets`) — matched Kalshi/Polymarket prediction-market data with cross-venue spreads, `apiKey`. Directly relevant to the Prediction Markets wiki section's cross-market arb work (`algorithmic-strategies.md`).
- **OpenFIGI** (`openfigi.com`) — Bloomberg LP symbology (equity/index/futures/options), free, no auth required beyond apiKey. Useful for ticker/instrument identifier resolution across data vendors.
- **Portfolio Optimizer** (`portfoliooptimizer.io`) — hosted portfolio analysis/optimization API, no auth. Possible lightweight alternative/cross-check to the local PyPortfolioOpt/Riskfolio-Lib stack in `portfolio-optimization.md`.
- **BriefTape / Filingrail / Edgrapi / StockFit / Zelothorn** — several newer (2026) hosted wrappers around SEC EDGAR that pre-normalize filings/XBRL/8-K events into JSON. Potential shortcuts vs. our own EDGAR parsing pipeline (`edgar-fundamentals.md`, `sec-8k-event-taxonomy-2026.md`) — unverified quality/coverage, would need evaluation before relying on any of them for PEAD.
- **Halal Terminal** — Shariah-compliant screening; niche, no current use case.

## Relevance to George's Stack

Logged as a reference directory, not adopted. No action taken — flagged per Kevin's request ("note this"). If a future hypothesis needs a specific data type (e.g., congressional trades, cross-venue prediction-market spreads, symbology resolution), check this list first before searching from scratch.
