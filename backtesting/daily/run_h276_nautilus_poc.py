# H276: NautilusTrader execution POC for H261b commodity rotation
# Purpose: prove NautilusTrader can run our momentum strategies with Kraken integration
# NOT a new alpha hypothesis — execution infrastructure validation
#
# Architecture:
# - BacktestEngine with simulated Kraken venue
# - Strategy: top-2 asset momentum (12-1m lookback) from H261b asset universe
# - Assets: BTC/USD, ETH/USD (crypto commodity proxies), GLD (via Alpaca bridge)
# - Data: Yahoo Finance via yfinance (monthly bars) for backtest
# - Paper mode: Kraken paper API
#
# Pre-requisite: pip install nautilus_trader
# Reference: wiki/trading/tools/multi-agent-llm-trading.md#nautilustrade
# H261b baseline: OOS Sharpe 0.922, Corr(SPY)=0.218, top-2 commodity rotation
#
# Success gate: Backtest runs without error; OOS Sharpe within +/-0.2 of H261b baseline
# (different assets, so exact match not expected)
#
# See also: backtesting/paper_trading/ for Alpaca version
