---
updated: 2026-05-10
status: active — deployed 2026-05-10
---

# H181 Alpaca Paper Trading — Industry-Adjusted Short-Term Reversal

**Hypothesis**: H181 CONFIRMED (OOS Sharpe 1.138, CAGR 24.6%, MaxDD −18.4%, 2021–2026)
**Signal**: REV^IN_i = R_i(t) − R̄_industry(t) — prior month return minus equal-weight GICS-sector average
**Source paper**: SSRN:6630998 (Stosik & Zaremba, "Short-Term Reversal Premium")

**Related pages**: [Short-Term Reversal](../algorithms/short-term-reversal.md) | [Paper Trading Index](index.md) | [H149 Alpaca ETF Rotation](h122-alpaca.md)

---

## Strategy Summary

| Parameter | Value |
|-----------|-------|
| Universe | 30 large-cap S&P 500 stocks, 8 GICS sectors |
| Signal | Prior-month return minus sector equal-weight average |
| Portfolio | Long bottom-6 (most negative adj-reversal), equal-weight |
| Rebalance | Monthly — first trading day of each month |
| Position size | 1/6 of equity per stock (~16.7%) |
| OOS Sharpe | 1.138 (2021–2026) |
| OOS CAGR | 24.6% |
| OOS MaxDD | −18.4% |
| Corr(H026) | 0.293 — genuine diversification |

---

## Signal Logic

The industry-adjusted reversal strips out sector-level trends and isolates stock-specific underperformance:

```
REV^IN_i = R_i(t) - R̄_sector(t)

where:
  R_i(t)         = stock i's prior-calendar-month return
  R̄_sector(t)   = equal-weight average return of all stocks in same GICS sector
```

Stocks with the most negative REV^IN (i.e., underperformed their sector the most) are expected to mean-revert upward. The industry adjustment is critical — without it, the signal degrades to plain reversal which has much weaker OOS performance.

---

## Universe — 30 Stocks

| Sector | Tickers |
|--------|---------|
| Information Technology | AAPL, MSFT, NVDA, AVGO, QCOM, AMD, IBM |
| Financials | V, MA, BAC, WFC, JPM |
| Health Care | UNH, LLY, PFE, JNJ, ABBV |
| Consumer Discretionary | AMZN, TSLA, HD, SBUX, LOW |
| Consumer Staples | WMT, COST |
| Communication Services | GOOGL, META |
| Energy | CVX, XOM |
| Industrials | BA, CAT |

---

## Deployment

### Script

```
backtesting/paper_trading/h181_monthly.py
```

### Commands

```bash
# Check current positions
python3 h181_monthly.py --status

# Dry run — see planned trades without submitting
python3 h181_monthly.py --dry-run

# Live rebalance (first trading day of month only)
python3 h181_monthly.py

# Force rebalance regardless of date
python3 h181_monthly.py --force
```

### Required environment variables

```
ALPACA_API_KEY    Alpaca paper account API key
ALPACA_SECRET     Alpaca paper account secret
```

---

## Monthly Workflow

**On the first trading day of each month (~9:45 AM CT):**

1. Script downloads last ~65 days of daily price data for all 30 stocks
2. Resamples to month-end closes, computes prior-month returns
3. Subtracts equal-weight sector mean → REV^IN signal
4. Selects bottom-6 (most negative adj-reversal)
5. Diffs against current Alpaca positions
6. Submits sell orders first (free cash), then buy orders
7. Logs to `h181_monthly_trades.json`

**Coordination with H149:**
Both strategies run on the first trading day of the month. Run H181 after H149 so equity balance is stable after H149's trades settle. In practice, H149 trades ETFs while H181 trades individual stocks — no symbol overlap.

---

## Performance vs Benchmark

| Metric | H181 OOS | SPY OOS |
|--------|----------|---------|
| Sharpe | 1.138 | ~0.8 |
| CAGR | 24.6% | ~14% |
| MaxDD | −18.4% | ~−24% |
| Neg years | 1 | 2 |
| Corr(H026) | 0.293 | — |

---

## Known Risks

- **Idiosyncratic risk**: unlike H026's ETF rotation, individual stocks can gap down 20–50% on bad earnings or fraud. MaxDD −18.4% reflects this.
- **Survivorship bias**: backtest universe is current S&P 500 members (large-cap survivorship). Paper trading performance may differ on newly-added or dropped constituents.
- **Sector balance**: the 30-stock universe has 7 IT stocks — more IT exposure than a broad index. The adj-reversal signal corrects for intra-sector effects but not cross-sector sector weight.
- **Short-term transaction costs**: monthly rebalancing means ~6 new positions per month. At $0 commission (Alpaca) with fractional shares, costs are minimal. At a paid broker, the ~6 round-trips would add ~0.5% drag.

---

## Path to Real Money

1. **Weeks 1–4**: Paper trade, verify signal matches backtest (6 stocks selected per month, roughly equal adj-reversal spread across sectors)
2. **Weeks 5–8**: Compare paper trade monthly return to backtest OOS monthly return distribution
3. **Gate check**: If 2+ months of paper results are within 1.5σ of OOS mean, flip `paper=False` in `get_client()` and deploy with small initial capital (~10% of H149 allocation)
4. **Full deployment**: After 3 months of live data, scale to target allocation

---

## Trade Log

Trades are appended to `backtesting/paper_trading/h181_monthly_trades.json`:

```json
{
  "date": "2026-05-01",
  "equity": 100000.00,
  "long_tickers": ["PFE", "BA", "WFC", "SBUX", "AMD", "META"],
  "target": {"PFE": 16666, "BA": 16666, ...},
  "adj_reversal": {"PFE": -0.0823, "BA": -0.0712, ...},
  "trades": [...]
}
```
