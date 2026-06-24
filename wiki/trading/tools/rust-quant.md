---
updated: 2026-06-24
stars: 1773
url: https://github.com/avhz/RustQuant
---

# RustQuant — Rust Quantitative Finance Library

**avhz/RustQuant** (1,773 stars, Rust, updated June 2026)

Comprehensive quantitative finance library written in Rust. QuantLib-comparable scope but Rust-native: options pricing, stochastic processes, ML, statistics, and time series.

## Capabilities

- **Options pricing**: BSM, binomial trees, Monte Carlo, Heston model, SABR
- **Greeks**: analytical and finite-difference for all standard option types
- **Stochastic processes**: GBM, Heston, CIR, Hull-White, GARCH, etc.
- **Interest rate models**: Vasicek, Hull-White, CIR
- **Statistical**: regression, PCA, Kalman filter
- **ML**: basic NN, gradient methods

## Python Integration

RustQuant provides Rust bindings. Can be called from Python via PyO3:

```bash
# If Python bindings are published on PyPI
pip install rustquant  # check current PyPI status
```

Or build from source:
```bash
git clone https://github.com/avhz/RustQuant
cd RustQuant
cargo build --release --features python
```

## When useful for our pipeline

| Use case | Value |
|----------|-------|
| Batch IV computation | 100-1000× faster than py_vollib for large options chains |
| Monte Carlo options pricing | Rust MC runs in milliseconds vs seconds in Python |
| GARCH volatility forecasting | Built-in GARCH(p,q) implementation |
| HMM-style Kalman filter | Kalman filter for H328 regime detection support |

## Practical guidance

For our current setup (Python-first, monthly/daily rebalancing), py_vollib is sufficient. RustQuant becomes relevant when:
1. H309 dispersion requires computing Greeks across hundreds of contracts at once
2. H266 iron condor needs real-time IV scanning across multiple expirations
3. Building a production options execution layer with sub-second latency requirements

Not a replacement for py_vollib in backtesting scripts — the Python overhead of data loading/pandas dominates. Use RustQuant at the inner loop (pricing/Greeks) if Python becomes a bottleneck.
