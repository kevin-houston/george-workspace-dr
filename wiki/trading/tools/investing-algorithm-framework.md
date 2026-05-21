---
updated: 2026-05-20
type: tool
status: noted — interesting for dashboard/storage; crypto-focused live trading
---

# Investing Algorithm Framework (IAF)

Python quant framework covering the full workflow: define → vector backtest → event-driven backtest → compare → deploy live.

- **GitHub**: https://github.com/coding-kitties/investing-algorithm-framework
- **Stars**: 1.2k stars, 170 forks (active; v8.9.0, 285 releases)
- **License**: Apache 2.0
- **Install**: `pip install investing-algorithm-framework`
- **Author**: coding-kitties (MDUYN)
- **Marketplace**: Finterion — monetize strategies

---

## Core concept

One `TradingStrategy` class runs unchanged across all four modes:
1. **Vector backtest** — fast signal analysis (numpy-based)
2. **Event-driven backtest** — realistic execution simulation
3. **Paper trading** — live paper mode
4. **Live trading** — CCXT exchanges + custom `OrderExecutor`

This eliminates the most common quant workflow pain: rewriting strategy logic when moving from research to production.

---

## Distinctive features

### Tiered backtest storage
- `.iafbt` binary bundle format: ~21× smaller than directory-based layouts, zstd + msgpack
- **Tier-1 SQLite index**: one row per bundle; rank 10k+ backtests by Sharpe/Calmar in sub-100ms without decoding Parquet blobs
- CLI: `iaf index ./my-backtests/ && iaf rank --by sharpe_ratio -n 20`
- Enables large-scale parameter sweeps (thousands of variants) with fast filtering

### HTML comparison dashboard
- Single self-contained HTML file, no server
- Overlay equity curves, rolling Sharpe, drawdown, monthly heatmaps, benchmark comparison
- Monte Carlo permutation test results included
- Direct output from `BacktestReport(backtests=winners).save("report.html")`

### Monte Carlo / permutation testing
- Randomizes trade order and timing to test whether results could occur by chance
- Assesses statistical robustness, not just point Sharpe estimate
- Built-in, not a separate library integration

### Cross-sectional pipelines
- Native support for ranking/filtering entire universes of symbols each iteration
- Factor tables per bar — relevant for H202-XL and H210 designs

### Declarative risk rules
```python
stop_losses = [StopLossRule(symbol="BTC", percentage_threshold=5, trailing=True)]
scaling_rules = [ScalingRule(scale_in_percentage=[50,30,20], max_entries=3)]
cooldowns = [CooldownRule(trigger="sell", blocks="buy", bars=12)]
```
Rules enforced identically in both vector and event-driven engines.

---

## Comparison to our existing tools

| Feature | IAF | Qlib | Vectorbt | Backtrader | LEAN |
|---------|-----|------|----------|------------|------|
| Vector backtest | ✓ | ✓ | ✓✓ (faster) | ✗ | ✗ |
| Event-driven | ✓ | partial | ✗ | ✓✓ | ✓✓ |
| Live trading | ✓ (CCXT) | ✗ | ✗ | ✓ (limited) | ✓✓ |
| US equities / Alpaca | custom executor | ✗ | ✗ | ✓ | ✓ |
| ML/factor model native | limited | ✓✓ | ✗ | ✗ | ✗ |
| HTML dashboard | ✓✓ | ✗ | ✓ | ✗ | ✗ |
| Storage layer (10k+ runs) | ✓✓ | ✗ | ✗ | ✗ | ✗ |
| Monte Carlo testing | ✓ | ✗ | ✗ | ✗ | ✗ |
| Options | ✗ | ✗ | ✗ | ✗ | ✓✓ |
| Stars | 1.2k | 41k | 3.5k | 8k | 9k |

### vs Qlib
Qlib is stronger for ML feature engineering, factor research, and model pipelines. IAF is more Pythonic and has a cleaner research-to-production path for simpler strategies. Qlib has no live trading story; IAF does (for supported exchanges).

### vs Vectorbt
Vectorbt is faster for pure vector backtesting. IAF adds event-driven mode and live deployment that Vectorbt lacks. For pure speed on large parameter sweeps, Vectorbt still wins.

### vs Backtrader
IAF is the modern replacement: same event-driven core but with HTML dashboards, Monte Carlo, tiered storage, and cloud deployment. Backtrader is older and less maintained.

### vs LEAN
LEAN is more institutional (options, futures, fractional shares, built-in brokerage integrations including Alpaca). IAF has better developer ergonomics and the storage/dashboard layer. LEAN wins on US equity completeness; IAF wins on simplicity and cross-asset breadth via CCXT.

---

## Relevance to our project

**High-value features:**
1. **Tiered storage + HTML dashboard** — genuinely useful once we have 50+ hypothesis backtests. Currently we produce `.txt` result files; IAF's SQLite-indexed `.iafbt` format would let us filter/rank all H001–H210 results in milliseconds.
2. **Monte Carlo permutation testing** — currently absent from our pipeline. Would strengthen confirmation criteria (see Backtesting Design Principles wiki).
3. **Cross-sectional pipelines** — relevant for H202-XL and H210 universe scoring.

**Limitations for our use case:**
- Live trading targets CCXT exchanges (Binance, Kraken crypto, Bitvavo). No native Alpaca support — would need a custom `OrderExecutor`.
- We already have a working Alpaca paper trading pipeline. Migrating would be significant work.
- Our existing vectorbt/custom scripts are sufficient for current hypothesis volume.

**Verdict**: Worth watching but not a near-term integration priority. The storage layer and HTML dashboard are the most compelling features — potentially worth adopting as a reporting layer on top of our existing backtest results without full framework migration.

---

## Related wiki pages
- [Qlib](qlib.md) — ML-native quant platform; stronger for factor research
- [Backtrader vs Vectorbt](backtrader-vs-vectorbt.md) — framework comparison
- [LEAN / QuantConnect](lean-quantconnect.md) — best for options and US equity production
- [Backtesting Design Principles](../backtesting/design-principles.md) — IS/OOS and confirmation criteria
