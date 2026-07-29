---
type: tool
title: Quant Desktop Market Terminal
description: Open-source Electron/TypeScript market terminal with local probabilistic forecasts, regime engine, signal desk, and decision journal.
tags: [trading, market-terminal, forecast, regime, electron, typescript]
resource: https://github.com/eisenjimmy/Quant
---

# Quant Desktop Market Terminal

**Repo:** https://github.com/eisenjimmy/Quant  
**Stars:** ~230 | **License:** MIT | **Language:** TypeScript (Electron)  
**Status noted:** 2026-07-29 | **Version:** v2.0.0

## What It Is

Open-source desktop market terminal for macOS/Windows. Tracks ETFs and stocks with:
- Persistent reorderable watchlist + ETF holdings expansion
- Holdings-driven news + earnings context
- Annotated candlestick charts with pivots, support/resistance, risk levels
- Macro overlays on chart (jobs, CPI, 10Y yield, oil, VIX)
- Market Pulse (cross-asset 6-ticker monitor, 90-session correlation matrix, scenario analyzer)
- Technical screener: cup bases, VCP, MA alignment, near-high, RS, MACD, volume surges
- **Regime engine** (5-state), **Signal Desk** (evidence-backed scoring), **Decision Journal**, **Kronos forecast**
- Supports local llama.cpp, OpenAI, Gemini, Grok, or Claude API (all optional)

## Key Components Worth Borrowing

### 1. Kronos Probabilistic Forecast (highest relevance)
- Uses [Kronos](https://github.com/shiyu-coder/Kronos) MIT time-series model — runs **locally** via Python subprocess
- Input: up to 360 completed hourly price+volume bars
- Output: **30 independent sampled paths**, 24 trading-hour horizon (~4 sessions)
- Reports: median path, P10–P90 band, upside frequency, volatility diagnostics
- Architecture: Electron main process owns the Python worker (NDJSON streaming); renderer receives typed IPC API
- **Potential use for Kevin:** PEAD-GAP intraday entry timing — 24-bar path could inform whether to enter at open vs. wait
- **Limitation:** No news/earnings/macro input — purely price+volume. PEAD's edge is information-driven so Kronos is supplementary at best for position sizing, not signal generation.

### 2. Market Regime Engine v2 (methodology reference)
- 5 states: healthy uptrend, correction, oversold bounce, distribution/downtrend, recession-defense
- **2-session evidence persistence** before committed regime change — anti-whipsaw rule
- Every regime result carries versioned methodology + evidence ledger + decline attribution
- 90-session cross-asset correlations built in
- **Borrowable for Kevin:** The 2-session persistence rule is a clean anti-whipsaw mechanism. Kevin's H249 regime engine (SPY 200MA × VIX) could adopt this before triggering BIL override in production.

### 3. Decision Journal
- Saves: thesis, catalyst, invalidation level, exact signal snapshot at entry
- Immutable per-entry record
- **Borrowable for Kevin:** Could formalize PEAD paper trade entries — add a `thesis` and `invalidation` field to `pead_positions.json` or a parallel `trade_journal.json`. Currently positions only record ticker/entry/date.

### 4. Signal Desk (methodology reference)
- Deterministic scoring with numbered evidence items, each with source + quality status
- Anti-hallucination: evidence must pass quality gate before informing a signal score
- **Borrowable:** Methodology for structuring signal evidence in H274 (multi-agent PEAD upgrade)

## Architecture Notes

- Electron main process owns: jobs, persistence, Python subprocess, market data validation
- Renderer owns: UI only, receives narrow typed API via IPC preload
- Forecast data: atomic store, immutable snapshots, 7-day expiry
- Market data: Yahoo Finance chart path (no new API key required for base features)

## Relevance to Kevin's Stack

| Component | Relevance | Action |
|---|---|---|
| Kronos 30-path forecast | Medium — short horizon (24hr) vs 20-day PEAD hold | Evaluate for intraday PEAD entry refinement |
| Regime 2-session persistence | High — directly applicable to H249 production regime | Add to h112_monthly.py regime gate |
| Decision journal structure | High — PEAD paper trades lack thesis/invalidation fields | Extend pead_positions.json schema |
| Signal Desk evidence model | Medium — relevant to H274 multi-agent design | Reference for agent debate evidence format |
| Full terminal UI | Low — Kevin's stack is headless/programmatic | Not worth porting |
