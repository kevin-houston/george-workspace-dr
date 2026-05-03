# Skills Index

Catalog of utility scripts and tools available in the workspace.
Updated by dream cycle nightly.

## Trading & Research

- `trading_eval/harness.py` — 146-strategy backtest engine (Fortune 100 equities)
- `trading_eval/macro_harness.py` — 25 FRED series macro regime classifier
- `trading_eval/candle_harness.py` — 25 candlestick patterns (R9-R10)
- `trading_eval/candle_macro_harness.py` — Candle × Macro combined harness (R19)
- `trading_eval/pead_harness.py` — PEAD gap-up signal backtest
- `trading_eval/dividend_harness.py` — Dividend raise / capture / CC strategies (R27)
- `trading_eval/pairs_harness.py` — Stat arb / cointegration pairs (R20-R23)
- `trading_eval/ml_harness.py` — ML ensemble (RF, XGBoost, GBM, Logistic)
- `trading_eval/options_harness.py` — Covered calls, condors, spreads, VIX puts (R25)
- `trading_eval/r28_harness.py` — Options deep dive: Bull Put Spread, Wheel, IV rank filter (R28)
- `trading_eval/llm_signal_harness.py` — LLM IndicatorAgent filter on signals (R26)
- `trading_eval/crypto_harness.py` — BTC/SOL momentum strategies
- `trading_eval/etf_commodity_harness.py` — Corn/NG seasonal, leveraged ETF
- `trading_eval/intl_harness.py` — International equities, EWC/EWA pairs
- `trading_eval/macro_cache/` — Cached FRED series data

## Paper Trading (Live)

- `pead/pead_scanner.py` — Daily PEAD gap scanner + exit checker (9:45 AM)
- `paper_trading/pt_div_raise.py` — Dividend raise signal tracker
- `paper_trading/pt_div_cc.py` — CC around ex-div tracker
- `paper_trading/pt_crypto.py` — SOL + BTC momentum tracker
- `paper_trading/pt_div_capture.py` — Dividend capture tracker
- `paper_trading/pt_corn.py` — Corn seasonal tracker
- `paper_trading/pt_pairs.py` — 10-pair stat arb tracker
- `paper_trading/pt_ml.py` — ML ensemble tracker
- `paper_trading/pt_dashboard.py` — Builds static HTML dashboard from all portfolios

## Portfolio & Publishing

- `herenow.py` — here.now publisher (stdlib only; POST manifest → PUT files → POST finalize)
- `robinhood-advisor/advisor.py` — Portfolio analysis orchestrator
- `robinhood-advisor/send_email_report.py` — Gmail SMTP email sender

## Content Generation

- `daily_ai_podcast_generator.py` — Podcast script template helper (stdlib only)
- `generate_podcast_audio_edge.py` — Edge TTS audio generator (Alex + Jordan voices, requires edge-tts)
- `generate_and_email_podcast.py` — Full pipeline: TTS → MP3 merge → Gmail email
  - Auto-installs edge-tts to /tmp/podcast_deps
  - Python MP3 concat fallback (no ffmpeg required)
  - Reads Gmail password from /workspace/group/.env

## Memory / State

- `MEMORY.md` — Primary persistent state (research findings, preferences, blockers)
- `NANOCLAW_DIARY.md` — Full state-transfer document for recovery after container loss
- `heuristics.md` — ERL-inspired generalizable lesson pool
- `skills_index.md` — This file

## Dream Cycle

- `dream_cycle/staged/{DATE}/` — Proposed changes (JSON, apply_status: pending/applied)
- `dream_cycle/changelogs/` — Applied change logs
- `dream_cycle/research/` — Nightly scan notes and deep research
- `dream_cycle/STAGED_SCHEMA.md` — JSON schema for staged proposals
