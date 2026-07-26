---
updated: 2026-07-26
category: disaster-recovery
---

# Strategy Reconstruction Guide

If the backtesting code is lost but the wiki survives, this page documents how to reconstruct each confirmed production strategy from first principles using the wiki knowledge base.

This is the **semantic layer** counterpart to [Operational Runbook 2026](runbook-2026.md) (which covers infrastructure) and [Git Backup](git-backup.md) (which covers code recovery). Use this if git restore fails and the code is unrecoverable.

---

## Quick Reference: Production Portfolio

| Strategy | Weight | Wiki Page | Key Script |
|----------|--------|-----------|------------|
| H026 ETF Rotation | 27% | [Momentum Strategies](../trading/algorithms/momentum-strategies.md) | `backtesting/daily/run_h026.py` |
| H041a 19-asset Rotation | 22% | [Momentum Strategies](../trading/algorithms/momentum-strategies.md) | `backtesting/daily/run_h041a.py` |
| H045 Bond Rotation | 21% | [Fixed Income](../trading/algorithms/fixed-income-bond-rotation.md) | `backtesting/daily/run_h045.py` |
| XLK IBS | 20% | [IBS Mean-Reversion](../trading/algorithms/ibs-mean-reversion.md) | `backtesting/paper_trading/h112_monthly.py` |
| SMH IBS | 8% | [IBS Mean-Reversion](../trading/algorithms/ibs-mean-reversion.md) | same as XLK |
| IGV IBS | 2% | [IBS Mean-Reversion](../trading/algorithms/ibs-mean-reversion.md) | same as XLK |

**Combined OOS Sharpe: 4.158 | MaxDD: −3.60% | CAGR: ~23.5% | Zero negative years 2004–2025**

---

## Reconstructing H026 ETF Rotation (27%)

### Core logic
1. Universe: 25 ETFs — see [Momentum Strategies](../trading/algorithms/momentum-strategies.md) for the exact ticker list (SPY, QQQ, IWM, MDY, EFA, EEM, VGK, EWJ, TLT, IEF, SHY, LQD, HYG, GLD, SLV, DBC, USO, VNQ, REM, XLK, XLV, XLE, XLF, XLU, XLP).
2. Signal: 12-month momentum skipping the most recent 1 month: `r = price[-21] / price[-252] - 1`. Use month-end adjusted close from yfinance.
3. Selection: top-1 ETF by momentum score. If top-1 has negative momentum, hold SHY (cash proxy).
4. Rebalance: monthly, at month-end close.
5. Safety overlay (H301 confirmed +27.4% Sharpe improvement): if `SPY < SPY.rolling(200).mean()` at month-end, override to SHY regardless of momentum rank.

### Reconstruction code skeleton
```python
import yfinance as yf
import pandas as pd

UNIVERSE = ['SPY','QQQ','IWM','MDY','EFA','EEM','VGK','EWJ',
            'TLT','IEF','SHY','LQD','HYG','GLD','SLV','DBC',
            'USO','VNQ','REM','XLK','XLV','XLE','XLF','XLU','XLP']

prices = yf.download(UNIVERSE, start='2003-01-01', auto_adjust=True)['Close']
monthly = prices.resample('ME').last()

# Momentum signal (12m-1m)
mom = monthly.shift(1) / monthly.shift(12) - 1   # shift(1) = use last month's prices

# SPY 200-day MA overlay (computed on daily, resampled to monthly)
spy_daily = prices['SPY']
spy_ma200 = spy_daily.rolling(200).mean().resample('ME').last()

for date in monthly.index[12:]:
    scores = mom.loc[date].dropna()
    pick = scores.idxmax() if scores.max() > 0 else 'SHY'
    # Safety overlay
    if spy_daily.loc[:date].iloc[-1] < spy_ma200.loc[:date].iloc[-1]:
        pick = 'SHY'
    # ... hold pick until next month-end
```

### Critical pitfalls
- **Look-ahead**: always `.shift(1)` the momentum signal so you only see prices up to the previous month-end
- **H256 incident pattern**: `r12 = prices[-1] / prices[-252]` (not shifted) produces dramatically inflated OOS — always shift
- **Cost model**: assume 0.1% round-trip per rebalance (~1.2% per year on top-1 monthly turnover)

---

## Reconstructing H041a 19-Asset Rotation (22%)

### Core logic
Same as H026 but with a 19-asset universe focused on global equity and sector ETFs (no bond-heavy assets in the set — the diversification comes from blending with H045). Universe: SPY, QQQ, IWM, EFA, EEM, VGK, EWJ, XLK, XLV, XLE, XLF, XLU, XLP, GLD, SLV, DBC, USO, VNQ, REM. Apply same 12m-1m momentum, top-1 pick, SPY 200MA overlay.

---

## Reconstructing H045 Bond Rotation (21%)

### Core logic
1. Universe: 13 bond ETFs — TLT, IEF, SHY, LQD, HYG, MUB, TIP, VGLT, BND, AGG, BNDX, EMB, PCY.
2. Signal: **ensemble momentum** — average of 3m, 6m, and 12m price returns (all shifted 1 month): `r_ensemble = (r3m + r6m + r12m) / 3`.
3. Selection: top-**2** ETFs by ensemble score. Equal-weight the two picks.
4. Rebalance: monthly at month-end.
5. No cash override — if top-2 both negative, hold SHY.

**Key finding**: 12m-only momentum degrades on bonds vs the 3m/6m/12m ensemble. SHY dominates 72% of OOS months (2018-2026 rate shock era). See [Fixed Income](../trading/algorithms/fixed-income-bond-rotation.md).

---

## Reconstructing IBS Mean-Reversion (XLK 20% / SMH 8% / IGV 2%)

### Core logic
Internal Bar Strength (IBS) = `(Close - Low) / (High - Low)` computed daily.

Entry signal: IBS < 0.2 (close near daily low = oversold).
Exit signal: IBS > 0.8 (close near daily high = overbought) OR 3-day holding period exceeded.

Apply to three tech ETFs independently:
- XLK (20% of portfolio)
- SMH (8% of portfolio)
- IGV (2% of portfolio)

Monthly rebalancing of the IBS allocation within H112 monthly rebalancer: the tech sector ETFs are held at these weights when no IBS trade is active. During an active IBS trade, the position may be temporarily 100% in the target ETF.

**Key finding**: H062–H112 confirmed; OOS Sharpe 2.129 (2021–2026). The IBS anomaly is theoretically grounded by the FRI magnitude-decomposition finding (arXiv:2606.29591) — SPY lag-1 autocorrelation is entirely magnitude-driven, validated for single-stock and sector ETF IBS. See [IBS Mean-Reversion](../trading/algorithms/ibs-mean-reversion.md).

### Critical parameters
- `ibs_low = 0.2` — do not lower to generate more signals
- `ibs_high = 0.8` — exit threshold
- Maximum hold: 3 trading days
- Trade on close (MOC orders) — not intraday

---

## Reconstructing Live PEAD Pipeline (not in production portfolio weight but actively paper trading)

### Core logic (H174 confirmed)
1. **Overnight pass** (11 PM CT): scan EDGAR ATOM feed for 8-K filings from universe tickers. Download and score with FinBERT (ProsusAI/finbert). Filter: `score >= 0.18 AND EPS surprise >= 0.02`. Write to `pead_watchlist.json`.
2. **Open pass** (9:32 AM CT): for each ticker on the watchlist, submit OPG (market-on-open) buy order via Alpaca paper account.
3. **Exit pass** (2:46 PM CT): close positions after 20 trading days.

### Key thresholds
- FinBERT score threshold: `>= 0.18` (NOT 0.15 — this was explicitly confirmed in H174)
- EPS surprise threshold: `>= 0.02` (2% beat)
- Win rate OOS: 81.8% (22 events)

---

## Strategy Blending — Emergency Reconstruction

If the `strategy_accounts.json` file is lost, the allocation weights are:

```python
WEIGHTS = {
    'H026':  0.27,   # 25-ETF momentum rotation
    'H041a': 0.22,   # 19-ETF rotation
    'H045':  0.21,   # 13-bond ETF rotation
    'XLK_IBS': 0.20, # XLK IBS mean-reversion
    'SMH_IBS': 0.08, # SMH IBS mean-reversion
    'IGV_IBS': 0.02, # IGV IBS mean-reversion
}
# Total Alpaca paper account: ~$102k
# Per-strategy virtual allocation = total * weight
```

Reset procedure: see [Paper Trading Reset](../paper-trading/index.md) and `backtesting/paper_trading/reset_paper_accounts.py`.

---

## Related Pages

- [DR Overview](overview.md)
- [Operational Runbook 2026](runbook-2026.md)
- [Git Backup Setup](git-backup.md)
- [Hypothesis Log](../backtesting/hypothesis-log.md)
- [Shared Strategy Evaluation Checklist](../shared-eval-checklist.md)
