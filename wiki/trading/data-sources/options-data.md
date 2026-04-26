---
updated: 2026-04-26
---

# Options Data Sources

Backtesting options strategies requires historical contracts data with Greeks and IV. No truly free source exists for production-grade backtesting.

---

## Source Comparison

### ThetaData (Recommended — Best Value)
- **URL**: thetadata.net
- **Cost**: Paid subscription (lowest cost among professional providers)
- **Data**: 1st, 2nd, 3rd order Greeks (delta, gamma, theta, vega, rho), trade + quote data, IV
- **History**: Back to 2005
- **Formats**: REST API, WebSocket streaming, Python SDK
- **Bulk downloads**: Yes (convenient for backtesting)
- **QuantConnect integration**: Yes
- **Verdict**: Best starting point for serious options backtesting on a budget

### ORATS (Best IV Surface Data)
- **URL**: orats.com
- **Cost**: Paid ($100 non-refundable deposit toward first invoice)
- **Data**: Historical EOD since 2007; minute-level since Aug 2020
- **Unique**: Full IV surface parameterization — skewness, kurtosis, term structure
- **Coverage**: 5,000+ symbols, updated 14 min before market close
- **Verdict**: Best for volatility surface research (IV skew, calendar spreads, VRP studies)

### QuantConnect Built-in Data (Best for LEAN Backtesting)
- **Cost**: Free (via QuantConnect cloud; 10 backtests/day free tier)
- **Data**: Minute-level options data with daily Greeks snapshots
- **History**: ~2010 for US equity options
- **Verdict**: Best starting point — no separate data cost if using LEAN/QuantConnect

### Polygon.io Free Tier
- **Cost**: Free
- **Options data**: EOD aggregates + current snapshot (Greeks, IV, OI)
- **Critical limit**: **No historical Greeks/IV time-series** — only current values
- **Use case**: Real-time scanning for entry signals; not useful for historical backtesting
- **History**: 2014+ for options contracts

### Alpaca
- **Cost**: Free
- **Options data**: Historical bars, quotes, trades, snapshots since Feb 2024
- **Greeks**: Available in real-time OptionsSnapshot
- **History**: Very limited (2024 only) — not useful for backtesting pre-2024 strategies
- **Verdict**: Good for live trading integration; not useful for backtesting

---

## What You Actually Need for Each Strategy

| Strategy | Minimum Data Needed |
|----------|---------------------|
| Iron condor backtest | Historical chains with bid/ask + delta + DTE |
| VRP harvesting | Historical IV vs. realized vol; daily Greeks |
| IV surface strategies | Full term structure + skew parameterization → ORATS |
| Real-time scanning | Current Greeks/IV snapshot → Polygon or Alpaca free |

---

## Practical Path Forward

1. **Now**: Use QuantConnect cloud free tier for LEAN options backtesting (Greeks included)
2. **Month 2**: Subscribe to ThetaData for bulk historical downloads + independent backtesting
3. **If doing VRP/skew research**: Trial ORATS ($100 applied to invoice)

We do NOT have options data keys in OneCLI as of 2026-04-26. Polygon free tier covers Greeks for live scanning but not backtesting history.
