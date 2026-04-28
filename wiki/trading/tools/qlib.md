---
updated: 2026-04-28
type: tool
status: candidate — Phase 2 ML strategies
---

# Microsoft Qlib — Deep Dive

AI-oriented quantitative investment platform for the full quant workflow: data → features → model training → backtesting → live serving, using the same codebase end to end.

- **GitHub**: https://github.com/microsoft/qlib — 41.3k stars, actively maintained
- **Docs**: https://qlib.readthedocs.io/
- **Latest release**: v0.9.7 (August 15, 2025)
- **License**: MIT
- **Install**: `pip install pyqlib` (imports as `qlib`)
- **Python**: 3.8–3.12 (Conda recommended)

---

## Architecture overview

Qlib is structured as six loosely-coupled layers that can each be used standalone:

```
Raw Data → Data Layer → Learning Framework → Strategy → Executor → Analysis
                ↕                ↕               ↕           ↕
           Caching           MLflow          Portfolio    Portfolio
           (3-tier)         tracking         metrics      reports
```

**Design principles:**
- Loose coupling — swap any component without touching others
- Same config works for research and production
- Registry system for dynamic component loading
- Online mode (shared Qlib-Server) vs Offline mode (local)

---

## Data layer

### Storage format & performance

Qlib stores market data in a proprietary compact binary format. The speed advantage over general databases on a standard benchmark (14 factors, 800 stocks, 2007–2020):

| Storage | Time (1 CPU) | Time (64 CPU) |
|---------|-------------|----------------|
| HDF5 | 184.4 ± 3.7s | — |
| MySQL | 365.3 ± 7.5s | — |
| MongoDB | 253.6 ± 6.7s | — |
| InfluxDB | 368.2 ± 3.6s | — |
| Qlib (no cache) | 147.0 ± 8.8s | 8.8 ± 0.6s |
| Qlib (expr cache) | 47.6 ± 1.0s | 4.2 ± 0.2s |
| **Qlib (full cache)** | **7.4 ± 0.3s** | — |

**Three-tier cache:**
1. **MemCache** — in-memory per-session
2. **ExpressionCache** — disk cache of computed factor expressions
3. **DatasetCache** — disk cache of fully-prepared datasets

### Data collection for US stocks

Qlib ships a collector for Yahoo Finance data:
```bash
# Install
pip install pyqlib

# Collect US data (daily, 2000–present)
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/us_data \
    --region us --interval 1d

# Collect 1-minute US data (much larger)
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/us_data_1min \
    --region us --interval 1min
```

Default data directory: `~/.qlib/qlib_data/cn_data` (China). Use `--region us` flag.

Custom CSV → Qlib format conversion: `scripts/dump_bin.py`

**Other supported regions:** CN (China), US, TW (Taiwan), Brazil

### Initializing Qlib

```python
import qlib
from qlib.constant import REG_US

# Initialize with US data
qlib.init(provider_uri="~/.qlib/qlib_data/us_data", region=REG_US)

# Multi-region
qlib.init(provider_uri={"us": "~/.qlib/qlib_data/us_data",
                        "cn": "~/.qlib/qlib_data/cn_data"})
```

### Point-in-Time (PIT) database

Added March 2022. Stores data as it would have been known at a given historical date — prevents look-ahead bias in fundamental features (e.g., quarterly earnings as filed, not restated).

### Data features

| Feature | Status |
|---------|--------|
| Daily OHLCV | ✓ Default |
| 1-minute bars | ✓ Supported |
| Orderbook data | ✓ `examples/orderbook_data/` |
| Point-in-time (PIT) | ✓ Since March 2022 |
| Arctic backend | ✓ Since January 2022 |
| Parquet support | ✓ Since v0.9.7 |
| MLflow integration | ✓ v0.9.7 modernized |

---

## Datasets: Alpha158 vs Alpha360

Qlib ships two standard feature sets for benchmarking models:

### Alpha158 — Engineered features
- 158 human-designed technical factors (price ratios, momentum, volatility, etc.)
- Minimal spatial relationships between features
- **Best for:** Gradient boosting (XGBoost, LightGBM), traditional ML
- Standard tabular format

### Alpha360 — Raw OHLCV features
- 360 raw price/volume features with no hand-engineering
- Strong temporal relationships in the feature matrix
- **Best for:** Deep learning, Transformer-based models
- Treated as sequence/image data

---

## Model zoo — all 20+ models

### Gradient boosting (3)
| Model | Paper |
|-------|-------|
| **LightGBM** | Ke et al., NeurIPS 2017 |
| **XGBoost** | Chen & Guestrin, KDD 2016 |
| **CatBoost** | Prokhorenkova et al., NeurIPS 2018 |

Also: Linear regression, DoubleEnsemble (LightGBM base, ICDM 2020)

### Recurrent neural networks (PyTorch)
| Model | Paper |
|-------|-------|
| **LSTM** | Hochreiter & Schmidhuber 1997 |
| **GRU** | Cho et al. 2014 |
| **ALSTM** (Attention LSTM) | Qin et al., IJCAI 2017 |
| KRNN | — |

### Transformer & attention (PyTorch)
| Model | Notes |
|-------|-------|
| **Transformer** | Vaswani et al., NeurIPS 2017 |
| **Localformer** | Jiang et al. — efficient local attention |
| **GATs** (Graph Attention) | Velickovic et al. 2017 |
| **TRA** (Temporal Routing Adaptor) | Dong et al., KDD 2021 |
| **TFT** (Temporal Fusion Transformer) | Lim et al. 2019 |

### Temporal & convolutional
| Model | Notes |
|-------|-------|
| **TCN** | Bai et al. 2018 |
| **TCTS** | Wu et al., ICML 2021 |
| **SFM** | Zhang et al., KDD 2017 |
| **ADARNN** | Du et al. 2021 |

### Specialized quant models
| Model | Notes |
|-------|-------|
| **HIST** | Xu et al. 2021 — stock concept graph integration |
| **IGMTF** | Xu et al. 2021 — multi-scale temporal fusion |
| **ADD** | Tang et al. 2020 |
| **Sandwich** | Specialized architecture |
| **MLP** | Standard multilayer perceptron |
| **TabNet** | Arik & Pfister, AAAI 2019 |

---

## Benchmark results

All results are mean ± std over 20 random seeds. Test period: 2017-01-01 to 2020-08-01.

### Alpha158 (tabular features) — top performers

| Model | IC | ICIR | Ann. Return | Info Ratio | Max DD |
|-------|-----|------|-------------|------------|--------|
| **DoubleEnsemble** | 0.0521 | 0.4223 | 11.58% | 1.343 | −9.20% |
| XGBoost | 0.0498 | 0.3779 | 7.80% | 0.907 | −11.68% |
| LightGBM | 0.0448 | 0.3660 | 9.01% | 1.016 | −10.38% |
| TRA | 0.0440 | 0.3535 | 7.18% | 1.084 | −7.60% |
| MLP | 0.0376 | 0.2846 | 8.95% | 1.141 | −11.03% |

### Alpha360 (raw OHLCV features) — top performers

| Model | IC | ICIR | Ann. Return | Info Ratio | Max DD |
|-------|-----|------|-------------|------------|--------|
| **HIST** | 0.0522 | 0.3530 | 9.87% | 1.373 | −6.81% |
| **IGMTF** | 0.0480 | 0.3589 | 9.46% | 1.351 | −7.16% |
| TRA | 0.0485 | 0.3787 | 9.20% | 1.279 | −8.34% |
| TCTS | 0.0508 | 0.3931 | 8.93% | 1.226 | −8.57% |
| GATs | 0.0476 | 0.3508 | 8.24% | 1.108 | −8.94% |

**IC (Information Coefficient):** Pearson correlation between model score and realized return. ~0.05 is considered good in practice.
**ICIR:** IC mean / IC std — measures signal consistency. Higher is better.

---

## Workflow engine

Two execution modes, both supported:

### Mode 1: qrun (config-driven, no code required)

```bash
# Run full pipeline (data → train → backtest → report)
python -m qlib.workflow.cli examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

YAML config specifies everything: dataset, model, backtest period, trading costs.

### Mode 2: Programmatic (Python API)

```python
# Standard workflow pattern
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord

with R.start(experiment_name="my_experiment"):
    model.fit(dataset)
    recorder = R.get_recorder()
    sr = SignalRecord(model, dataset, recorder)
    sr.generate()
    par = PortAnaRecord(recorder, port_analysis_config, "day")
    par.generate()
```

### Mode 3: Batch (run_all_model.py)

```bash
# Train and evaluate all models, collect performance table
python run_all_model.py --models LightGBM XGBoost LSTM
```

---

## Execution framework (Nested Decision)

Qlib's most sophisticated feature: a hierarchical execution framework that supports multi-level trading strategies. A daily alpha model can drive an intraday executor that minimizes market impact.

```
NestedExecutor
├── outer_strategy: TopkDropoutStrategy (daily rebalancing decisions)
│   └── inner_executor: SimulatorExecutor (intraday execution)
│       └── inner_strategy: TWAPStrategy (intraday slicing)
└── SimulatorExecutor (single-level fallback)
```

**Key executor parameters:**
- `time_per_step`: Trading frequency (generates trading calendar)
- `indicator_config`: Metrics — price advantage, fulfillment rate
- `trade_type`: "serial" or "parallel" order execution
- `track_data`: Collect decision data for RL training
- `settle_type`: Position settlement timing

**Order structure:**
```python
Order(
    stock_id="AAPL",
    amount=100.0,           # float, non-negative
    direction=OrderDir.BUY, # or OrderDir.SELL
    start_time=pd.Timestamp("2024-01-15 09:30:00"),
    end_time=pd.Timestamp("2024-01-15 16:00:00"),
)
```

---

## Strategies

### TopkDropoutStrategy (primary)
Default strategy for long-only factor portfolios:
- Holds top-k stocks by model score
- Drops n stocks per period (reduces turnover)
- Configurable rebalancing frequency

### EnhancedIndexingStrategy
Tracks a benchmark index while adding alpha via model signals.

### RL-based strategies
Full reinforcement learning integration via `examples/rl/` and `examples/rl_order_execution/`. Agent learns execution policies from the trading environment.

---

## RD-Agent — LLM-driven factor discovery

Released August 8, 2024. A companion project that uses LLM agents to autonomously propose, implement, and evaluate new alpha factors and model architectures.

- **GitHub**: https://github.com/microsoft/RD-Agent
- **Paper**: "R&D-Agent-Quant" (arXiv:2505.15155, 2025)
- **Requires**: Linux, Python 3.10+, Docker, LiteLLM backend (OpenAI, DeepSeek, Azure)

**Three modes:**
```bash
rdagent fin_factor    # Autonomous factor mining loop
rdagent fin_model     # Autonomous model optimization loop
rdagent fin_joint     # Coordinated factor+model co-optimization
```

**How it works:**
- **R (Research)**: LLM proposes factor ideas and hypotheses based on financial literature and existing results
- **D (Development)**: LLM writes, debugs, and tests the implementation in Qlib
- Loop continues: evaluate → feedback → propose refinement → re-implement

**Performance on MLE-bench (75 Kaggle competitions):** ~30% success rate with o3/GPT-4.1. Leads the benchmark for ML engineering automation.

**Practical use for this project:** With `$OPENAI_API_KEY` available, we could run `rdagent fin_factor` against the US market data to autonomously generate novel alpha factors. The cost would be API credits per iteration (~hundreds of LLM calls per run).

---

## Working with US stocks — quick start

```python
import qlib
from qlib.constant import REG_US
from qlib.data import D

# 1. Initialize
qlib.init(provider_uri="~/.qlib/qlib_data/us_data", region=REG_US)

# 2. Get features from data
instruments = D.instruments(market="nasdaq100")
features = D.features(
    instruments,
    fields=["$close", "$volume", "Ref($close, 1)", "Mean($close, 10)"],
    start_time="2020-01-01",
    end_time="2024-01-01",
    freq="day",
)

# 3. Define dataset
from qlib.contrib.data.handler import Alpha158
handler = Alpha158(instruments="nasdaq100", start_time="2018-01-01", end_time="2024-01-01")

# 4. Train a model
from qlib.contrib.model.gbdt import LGBModel
model = LGBModel(...)
model.fit(dataset)

# 5. Run backtest via qrun (easiest path)
# python -m qlib.workflow.cli examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

---

## Configuration system

```python
from qlib.config import C

# Access config
C["provider_uri"]          # Data path
C["dataset_cache_dir"]     # Cache directory

# Environment variables (pydantic v0.9.7+)
# QLIB_PROVIDER_URI=...   — set data path
# QLIB_MLFLOW_...         — MLflow configuration
```

**MLflow integration** (experiment tracking):
- All runs auto-logged to MLflow with model params, metrics, artifacts
- Configurable experiment names and tracking URI
- Supports comparing runs across models/configurations

---

## Installation (this project)

```bash
pip install pyqlib lightgbm xgboost catboost torch torchvision --break-system-packages

# Collect US data (one-time, ~500MB for daily bars)
python -m qlib.run.get_data qlib_data \
    --target_dir ~/.qlib/qlib_data/us_data \
    --region us --interval 1d
```

**System requirements:** 16GB RAM recommended, 5GB disk minimum for US daily data.

---

## Assessment for this project

| Criteria | Rating | Notes |
|----------|--------|-------|
| Classical strategies | ✗ | Overkill; use yfinance + pandas directly |
| ML alpha factors | ✓✓ | Native strength; Alpha158/Alpha360 ready |
| LLM factor discovery (RD-Agent) | ✓ | Needs OpenAI budget; container must be Linux |
| Live trading | ✗ | No Alpaca/IB connector built in — requires custom bridge |
| Documentation | ✓✓ | Excellent; 20+ example workflows |
| Setup cost | Medium | One-time data collection; then fast via caching |

**Recommended use in this project:**
1. **Phase 2 extension**: After classical backtesting (H-series), use Qlib's Alpha158/Alpha360 + LightGBM/DoubleEnsemble to generate ML alpha factors for H041a's rotation universe
2. **Not a replacement** for the current backtesting framework — keep yfinance + pandas for the H-series momentum strategies
3. **RD-Agent experiment**: One trial run of `rdagent fin_factor` against NASDAQ-100 would be a low-cost way to discover novel factors automatically

**Key limitation for live trading:** Qlib has no built-in Alpaca, Interactive Brokers, or other retail broker connector. Need to build a bridge from Qlib signal output → Alpaca order submission.
