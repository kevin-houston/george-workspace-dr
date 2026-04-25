---
updated: 2026-04-24
type: tool
status: candidate
---

# Microsoft Qlib

AI-oriented quantitative investment platform designed to take a quant idea from research through production with the same codebase.

- GitHub: https://github.com/microsoft/qlib
- Docs: https://qlib.readthedocs.io/
- Install: `pip install pyqlib` (imports as `qlib`)
- Python: 3.8+

## Architecture

- **Data layer**: Proprietary `.bin` binary format, 20-50x faster than general DBs. Three-tier cache: MemCache → ExpressionCache → DatasetCache.
- **Workflow**: Raw data → Processors → Dataset → Model → Backtest → Production. Same config works for both research and prod.
- **Execution**: Nested Decision Execution Framework supports multi-level strategies (e.g. daily alpha nested inside intraday executor).
- **Recent addition**: RD-Agent integration for LLM-driven autonomous factor discovery.

## Models supported out of the box

| Category | Models |
|----------|--------|
| Gradient boosting | XGBoost, LightGBM, CatBoost |
| Deep learning | LSTM, GRU, ALSTM, GATs, Transformer, Localformer, TFT, TabNet, KRNN, Sandwich |
| Learning paradigms | Supervised, market dynamics modeling, reinforcement learning |

## Data sources (native connectors)

- Yahoo Finance (US stocks) — official collector script
- TUSHARE (Chinese A-shares)
- Hong Kong stocks — static packages
- Custom CSV/Parquet via `scripts/dump_bin.py`

## Best for

- ML-heavy alpha factor mining
- Portfolio optimization
- Researchers wanting to compare many models quickly
- Teams needing research→production consistency

## Not ideal for

- Simple classical strategies (momentum, mean reversion) — overkill
- Live broker integration (no Alpaca/IB connector out of the box)

## Assessment for this project

Strong candidate for **Phase 2 backtesting** of ML-based strategies. Steep initial setup but pays off for systematic factor research. Start with Backtrader for classical strategies, bring in Qlib for ML experimentation.
