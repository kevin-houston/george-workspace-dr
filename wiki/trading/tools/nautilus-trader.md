---
type: tool
title: NautilusTrader — Production Backtest + Live Execution Engine
tags: [execution-engine, backtesting, crypto, ibkr, polymarket, rust]
---

# NautilusTrader

**GitHub**: https://github.com/nautechsystems/nautilus_trader | **Stars**: 25.4k (up from 23.4k when first noted 2026-06-17, algorithms/multi-agent-llm-trading.md) | **License**: LGPL-3.0 | **Language**: Rust core + Python control plane | **Maintainer**: Nautech Systems

Deep-dive companion to the short comparison table in [algorithms/multi-agent-llm-trading.md](../algorithms/multi-agent-llm-trading.md#nautilustrader--production-execution-engine). This page is the full reference: installation, adapters, a working backtest example, pricing, and where it fits (or doesn't) relative to the current stack.

## Why it matters here

Directly relevant to **H276** (NautilusTrader crypto POC, scaffolded but not run — see CLAUDE.local.md). Three of its stable adapters map onto things already in progress or planned:

- **Kraken** — Kevin already has the Kraken CLI + a paper account ($10k USD) and a pending MCP server approval (151 native tools). NautilusTrader gives a second, execution-engine-native path to the same venue if the CLI/MCP route hits limits.
- **Polymarket** — the prediction-markets wiki section (backtesting-frameworks.md) already flagged `evan-kolberg/prediction-market-backtesting` as a NautilusTrader extension for Kalshi/Polymarket backtesting, blocked today only by Kalshi L2 book data availability upstream. NautilusTrader is the underlying engine for that path, not a separate option.
- **Interactive Brokers** — not currently used (Alpaca is the equities/options broker), but IBKR is the most-supported traditional multi-venue brokerage in NautilusTrader's adapter list, worth knowing about if Alpaca's execution quality or asset coverage ever becomes a blocker (options assignment, non-US listings, etc.).

## Installation

Python 3.12–3.14, 64-bit only. Officially supported OSes:

| OS | Version | Arch |
|---|---|---|
| Linux (Ubuntu) | 22.04+ | x86_64, ARM64 |
| macOS | 15.0+ | ARM64 |
| Windows Server | 2022+ | x86_64 |

```bash
# Recommended — uv package manager
uv pip install nautilus_trader

# Pre-release v2 wheels
uv pip install --pre nautilus_trader

# With specific adapter extras
uv pip install "nautilus_trader[docker,ib]"
```

Available extras: `betfair`, `docker`, `ib`, `polymarket`, `visualization`.

**Limitations found during research:**
- **glibc 2.35+ required on Linux** (`ldd --version` to check) — this container's Debian base should be verified before attempting install; older glibc means building from source or skipping the Rust-wheel fast path.
- Conda distributions "may work but aren't officially supported."
- 128-bit high-precision mode is the default; 64-bit standard-precision is Windows-only.
- Building from source needs the full Rust toolchain (rustup, cargo, clang/LLVM) plus `uv sync --all-extras` — meaningfully heavier than a pure-Python `pip install` and not something to do casually in an ephemeral container.

## Supported adapters (all listed as "stable" as of Aug 2026)

| Category | Venues |
|---|---|
| Crypto CEX | Binance, Coinbase, BitMEX, Bybit, Deribit, **Kraken**, OKX |
| Crypto DEX | Derive, dYdX, Hyperliquid, Lighter |
| Traditional / multi-venue | AX Exchange (derivatives), **Interactive Brokers** |
| Betting / prediction markets | Betfair, **Polymarket** |
| Data providers | Databento, Tardis, Blockchain (on-chain/DeFi) |

Each adapter normalizes to a unified domain model: venue-native symbols get mapped internally, all timestamps are UNIX epoch nanoseconds. Adapters support historical data requests, live streaming, execution-state reconciliation, and standard order submission/modification/cancellation where the venue itself allows it — coverage varies per venue for exotic order types.

Notably **absent**: no native Alpaca adapter. Any Alpaca migration would mean writing a custom adapter (REST + WebSocket client following the documented `HttpClient`/`WebSocketClient`/`InstrumentProvider`/`DataClient`/`ExecutionClient` pattern) or continuing to run Alpaca strategies outside NautilusTrader entirely.

## Minimal backtest example

```python
from decimal import Decimal
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider

engine = BacktestEngine(
    config=BacktestEngineConfig(logging=LoggingConfig(log_level="ERROR")),
)

SIM = Venue("SIM")
engine.add_venue(
    venue=SIM,
    oms_type=OmsType.NETTING,
    account_type=AccountType.MARGIN,
    starting_balances=[Money(1_000_000, USD)],
    base_currency=USD,
    default_leverage=Decimal(1),
)

instrument = TestInstrumentProvider.default_fx_ccy("EUR/USD")
engine.add_instrument(instrument)
engine.add_data(bars)          # your bar/tick data, loaded via a data catalog or adapter
engine.add_strategy(your_strategy_instance)
engine.run()
engine.dispose()
```

The pattern — engine → venue → instrument/data → strategy → run — is the same whether backtesting or live; swapping `BacktestEngine`/`BacktestNode` for `TradingNode` with a live adapter config is the only change needed to go from research to production. This "same code both ways" property is NautilusTrader's core value proposition versus vectorbt/backtrader, where research and live code paths diverge.

## Pricing

Core NautilusTrader is fully open-source (LGPL-3.0), free, no seat/usage limits. **"Nautilus Cloud"** is referenced on nautilustrader.io as a forthcoming managed offering but is "currently under active development with further details to be provided in due course" — no pricing, no GA date, not usable today. No other commercial tier exists as of this research (Aug 2026); Nautech Systems' revenue model beyond the open-source project isn't publicly documented.

## Comparison vs current stack

| Feature | NautilusTrader | vectorbt | backtrader |
|---|---|---|---|
| Core | Rust | Python/Numba | Python |
| Backtest resolution | Nanosecond (tick) | Bar | Bar |
| Live trading | 20+ venues (not Alpaca) | ✗ | Limited |
| Research → prod | Same code | Diverges | Diverges |
| Native crypto | 10+ venues | ✗ | ✗ |
| Native prediction markets | Betfair, Polymarket | ✗ | ✗ |
| Learning curve | High (Rust-adjacent config, no Alpaca) | Low | Medium |

## Verdict for this pipeline

**Not adopted for the current production stack.** Alpaca (equities/options, H041a/H026/H045/IBS) has no native adapter, and vectorbt/pandas remain simpler for the monthly-rebalance rotation strategies that dominate production. NautilusTrader earns its keep only where the current stack is genuinely thin:

1. **H276 crypto POC** — Kraken adapter is production-grade here, unlike Alpaca's crypto support.
2. **Prediction-markets execution** — if/when Kalshi/Polymarket move from paper research to live orders, the Polymarket adapter (and the `evan-kolberg` NautilusTrader-based backtester already flagged in prediction-markets/backtesting-frameworks.md) is the most mature open-source path, versus writing a bespoke order-routing script.
3. **IBKR contingency** — logged for reference if Alpaca's options/international coverage ever becomes a blocker.

No new hypothesis is proposed from this page alone — it's infrastructure reference, not an alpha source. Revisit when H276 actually runs (currently scaffolded-not-run per the trading project status note) or when Kalshi L2 data becomes available for the Polymarket/Kalshi backtester path.

## See also

- [algorithms/multi-agent-llm-trading.md](../algorithms/multi-agent-llm-trading.md) — original short mention, now points here for depth
- [prediction-markets/backtesting-frameworks.md](../prediction-markets/backtesting-frameworks.md) — `evan-kolberg/prediction-market-backtesting`, the NautilusTrader-based PM backtester
- [data-sources/crypto-data-sources.md](../data-sources/crypto-data-sources.md) — ccxt/CoinGecko as the current (non-NautilusTrader) crypto data path
- [tools/kraken-cli.md](kraken-cli.md) — the currently-active Kraken integration path (CLI + pending MCP), the practical alternative to this adapter for H276
