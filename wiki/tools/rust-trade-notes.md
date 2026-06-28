---
title: rust-trade — Rust Quantitative Trading & Backtesting System
added: 2026-06-27
source: https://github.com/Erio-Harrison/rust-trade
via: Kevin (Twitter/X @tom_doerr, Jun 27 2026)
category: tools
---

# rust-trade

Quantitative trading and backtesting system built with Rust. MIT licensed.

- **Repo**: github.com/Erio-Harrison/rust-trade
- **Stars**: ~449 (June 2026)
- **Language**: Rust (with TypeScript/Tauri for UI)
- **License**: MIT
- **Updated**: June 2026 (active)

## What it does

Rust-based quant trading system. Uses Tauri (Rust + TypeScript desktop framework) suggesting it has a desktop GUI. Covers quantitative trading and backtesting.

## Relevance to Kevin

- Rust offers significant performance advantage over Python for backtesting (order-of-magnitude faster iteration on large datasets)
- Tauri UI means a desktop app — could be a faster backtesting shell than George's current Python/pandas pipeline
- Not a direct replacement for George's hypothesis testing workflow (which integrates FRED, FMP, yfinance data pipelines) but interesting as a performance benchmark
- Low priority unless Kevin wants to explore Rust-based execution for live trading (latency-sensitive)
- Worth watching: if it gains MCP integration or exposes an API, could complement the existing stack
