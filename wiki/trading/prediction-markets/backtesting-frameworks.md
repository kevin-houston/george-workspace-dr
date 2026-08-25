---
updated: 2026-08-25
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

### Homerun (braedonsaunders/homerun)

`github.com/braedonsaunders/homerun` — AGPL-3.0, 175 stars, 35 forks, created
Feb 2026, actively pushed as recently as 2026-08-21. Solo-maintainer project but
with a broader legitimate portfolio (same author ships `codeflow`, an unrelated
GitHub-architecture-visualization tool with its own trending traction) — no
hallusquatting/scam signals. By far the most feature-complete open-source PM
platform surveyed to date in this section: a full-stack app (FastAPI + Postgres
+ Redis backend, React/TypeScript frontend, 16 background workers) rather than a
CLI script or single-engine library like the three tools above.

**Why this is a step up from PolyBot/polymarket-arbitrage**: those two are
thin, single-purpose tools (agent-trading surface, arb scanner). Homerun bundles
strategy authoring + **microstructure-aware backtesting** + shadow-mode
paper trading + live execution behind one SDK, with 25+ pre-built strategies
spanning arbitrage (cross-platform Polymarket↔Kalshi, YES+NO mispricing,
negRisk bundle mispricing, settlement-lag plays), microstructure (flash-crash
reversion, VPIN toxicity detection), alt-data (LLM news scoring, weather
distribution forecasting, crypto 5m–4h binaries), social (whale-wallet mirroring,
27-point insider-anomaly scoring), and stat-arb/market-making.

**Backtest engine — the most rigorous fill model surveyed so far**:
- Persists Polymarket L2 order-book snapshots (25 levels/side, 0.5s sampling)
  plus trade prints into `MarketMicrostructureSnapshot` records — a real
  order-book replay, not the 2-cent flat-spread proxy Quentin-Piot's tool uses
  as a fallback.
- Fill probability from a **Cox proportional-hazards survival model** trained on
  historical order fills, with covariates: queue depth, spread, trade intensity,
  time-to-resolution, side imbalance, volatility, and measured latency.
- **Trade-vs-cancel decomposition**: splits observed depth disappearance into
  "someone took it" vs. "someone pulled it" using the trade tape — these have
  different adverse-selection implications and most naive backtesters conflate
  them.
- **Latency injection** sampled from rolling 15-min p50/p95/p99 across nine
  pipeline stages, not a single constant delay.
- Shadow-mode orders return three fill estimates (pessimistic/realistic/
  optimistic); backtest PnL vs. shadow PnL vs. live PnL are triangulated
  side-by-side per strategy to catch fill-model drift before it costs money.

**Strategy SDK** (Python, async):

```python
from services.strategies.base import BaseStrategy
from services.strategy_sdk import StrategySDK

class MacroShockStrategy(BaseStrategy):
    strategy_type = "macro_shock"
    subscriptions = [EventType.MARKET_DATA_REFRESH]
    default_config = {"source_slug": "macro_feed_source", "min_confidence": 0.55}

    async def detect_async(self, events, markets, prices) -> list[Opportunity]:
        records = await StrategySDK.get_data_records(
            source_slug=self.config.get("source_slug"), limit=100
        )
        opportunities = []
        for market in markets:
            if market.closed or not market.active:
                continue
            yes_price = float(prices.get(token_id, {}).get("mid", market.yes_price))
            if yes_price < 0.60:
                opportunities.append(self.create_opportunity(
                    title=f"Macro Shock: {market.question[:80]}", confidence=0.55
                ))
        return opportunities
```

Custom data sources subclass `BaseDataSource` with an async `fetch_async()` —
RSS/Atom, REST, Twitter/X, Chainlink oracles, and raw Binance WebSocket
(BTC/ETH/SOL/XRP) are supported out of the box.

**Install**: `git clone` + `./scripts/infra/run.sh` (one-click, auto-installs
venv/npm/Postgres), or `make setup && make dev` for local dev (frontend
`:3000`, API `:8000`, Swagger at `/docs`), or `docker compose up -d`.

**License caveat**: AGPL-3.0 is copyleft — fine for internal research use
(reading code, running locally, adapting fill-model ideas), but any modified
version made available as a network service to others would need to be
released under AGPL too. Not a blocker for how this project would use it
(local paper-trading reference, not a redistributed product), but worth
flagging before any deeper integration than "borrow the Cox-hazards fill-model
idea."

**Relevance**: The Cox-hazards fill model plus trade-vs-cancel decomposition is
the most credible answer surveyed so far to "how do we backtest PM order-book
fills without either assuming perfect fills or a flat spread proxy" — directly
relevant if H185 (Kalshi nowcasting) or the market-making angle in
`market-making.md` ever needs a real execution-quality backtest rather than
the current mid-price-fill assumption implicit in most of this project's PM
research. The 25+ built-in strategy catalog is also a useful checklist of PM
strategy archetypes to compare our own hypothesis backlog against (e.g. its
"settlement lag" and "negRisk bundle mispricing" arb variants aren't currently
covered by `other-platforms.md`'s cross-platform arb section or H185).

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
- **Cox-hazards fill model + trade-vs-cancel decomposition** from Homerun (the
  one tool here that's a genuine step beyond reference-only — 175 stars, active,
  full-stack) → the strongest available blueprint if a PM backtest ever needs
  order-book-level execution-quality modeling instead of a flat spread proxy;
  AGPL-3.0 license means "borrow the idea" not "vendor the code" for anything
  we'd redistribute
