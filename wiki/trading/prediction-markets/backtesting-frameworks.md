---
updated: 2026-08-05
---

# Prediction Market Backtesting Frameworks & Agent Trading Tools

Complements `other-platforms.md`'s "Open Datasets & Unified APIs" section (jon-becker's
36GB dataset, pmxt unified SDK). This page covers the **execution/backtest tooling
layer** built on top of that data — open-source backtesting engines purpose-built
for prediction markets, and agent-driven trading frameworks with MCP integration.
Neither category was previously documented here.

## Quant-style backtesters

### prediction-market-backtester (Quentin-Piot)

`github.com/Quentin-Piot/prediction-market-backtester` — MIT, 6 stars, 15 commits.
Small but well-scoped: a "quant-style backtesting engine for prediction markets
(Polymarket + Kalshi), focused on correctness, reproducibility, and performance."

**Execution model** (the useful part — matches how we'd want to model PM fills):
- Buys fill at ask, sells fill at bid (explicit, conservative — no mid-price fills)
- Default 2-cent spread proxy when a richer order-book snapshot isn't available
- Fees as percent-of-notional; slippage configurable in basis points
- Latency modeled via delayed order activation (in bars, not wall-clock)
- Risk controls enforce max exposure as gross cash-at-risk, not raw notional
- **Known gap**: no order-book depth or partial-fill modeling yet — fills are
  all-or-nothing once eligible

**Install**: no PyPI package; clone + `uv sync --dev`, data via `make setup`
(configurable `DATA_URL`).

```bash
pm-bt backtest --venue kalshi --market KXPGATOUR-APIPBM25-CMOR \
  --strategy momentum --config configs/momentum/default.yaml \
  --start-ts 2025-03-03T00:00:00Z --end-ts 2025-03-10T00:00:00Z
```

**Relevance**: The ask/bid fill convention here is exactly what our own
`backtesting/design-principles.md` transaction-cost discipline would demand for a
PM strategy — worth adopting the same convention if H185 (Kalshi nowcasting) ever
gets a dedicated backtest harness, rather than assuming mid-price fills.

### prediction-market-backtesting (evan-kolberg)

`github.com/evan-kolberg/prediction-market-backtesting` — mixed MIT/LGPL-3.0,
1.1K stars, 181 forks, active. A NautilusTrader extension rather than a standalone
engine — inherits NautilusTrader's event-driven backtest core and adds PM-specific
data adapters and charting (multi-market equity/P&L visualization).

**Venue support**:
| Venue | Status |
|---|---|
| Polymarket | Fully supported; live sandbox plumbing for BTC 5-min markets (v4.1-alpha) |
| Limitless.exchange | Planned |
| Opinion.trade | Planned |
| Kalshi | **Blocked** — "support depends on access to L2 historical book data," which isn't available; current Kalshi code is "research and fee-modeling plumbing, not a public runnable backtest path" |

Setup guide: `evan-kolberg.github.io/prediction-market-backtesting/setup/`.

**Relevance**: The Kalshi L2-data blocker is worth noting for H185 — if we ever
need order-book-level Kalshi backtesting rather than trade-tape replay, this is
already a known dead end upstream, not just a data problem specific to us.
`PredictionMarketBench` (arXiv:2602.00133, already in `ai-model-benchmarks.md`)
remains the working Kalshi LOB replay path.

## Agent-driven trading frameworks

### PolyBot (cryptuon/polybot)

`github.com/cryptuon/polybot` — MIT, 8 stars. An agent-first trading framework:
built for AI agents (Claude, GPT, MCP clients) and humans to trade PM venues
safely, with paper-trading as the default and mandatory human approval before
any live order.

- **MCP server**: 25+ typed tools exposed natively; also ships a Claude Code
  Skill (`/polybot`) for direct CLI access
- **Venues**: Polymarket, Kalshi, Opinion, plus Binance for hedging
- **Safety model**: "Every strategy paper-trades by default; promote to live
  per-strategy, reversibly." Agents propose trades, humans execute the final
  live decision. Position limits, daily loss caps, and exposure controls
  enforced platform-wide before order submission.

```bash
pip install polybot-trader
cp .env.example .env       # Polymarket credentials
polybot db init
polybot start               # dashboard at localhost:8000/ui
```

**Relevance**: This is the closest existing open-source analog to how George
already operates (NanoClaw agent + MCP tools + human approval gate on
consequential actions) applied specifically to PM trading — a reference
implementation if a Kalshi/Polymarket MCP server is ever added to this
instance's toolset (see `automated-pipeline.md` for the current in-house
event-driven loop design).

### polymarket-arbitrage (ImMike)

`github.com/ImMike/polymarket-arbitrage` — Python. Watches 10,000+ markets for
cross-platform (Polymarket ↔ Kalshi) pricing inefficiencies via text-similarity
matching between market titles (rather than manual ticker mapping). Ships both a
CLI and a web dashboard mode.

**Relevance**: Text-similarity market matching is a meaningfully different
approach from the manual ticker-pair mapping implied in `other-platforms.md`'s
cross-platform arb section — useful if the arb universe needs to scale past a
hand-maintained pair list.

## Assessment vs. current stack

None of these are drop-in replacements for the in-house `automated-pipeline.md`
design — all are early-stage (single-digit to low-hundreds stars, except the
NautilusTrader extension). Value is reference/pattern, not adoption:

- **Fill-model discipline** from Quentin-Piot's ask/bid convention → apply to any
  future PM backtest harness
- **NautilusTrader-as-PM-backtester** pattern from evan-kolberg → an option if we
  ever want unified equities+PM backtesting in one engine, once Kalshi L2 data
  becomes available upstream
- **MCP-first agent trading** pattern from PolyBot → closest prior art to "give
  George native Kalshi/Polymarket tools with a paper-trade default and human
  approval for live orders," worth revisiting if H185 graduates past nowcasting
  research into live execution
