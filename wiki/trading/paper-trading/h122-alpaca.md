---
updated: 2026-04-30
status: active
broker: Alpaca Paper ($ALPACA_API_KEY / $ALPACA_SECRET)
started: 2026-04-28
script: backtesting/paper_trading/h112_monthly.py
monitor: backtesting/paper_trading/monitor.py
log: backtesting/paper_trading/h112_monthly_trades.json
---

# H149 Alpaca Paper Portfolio

Production momentum rotation portfolio running on Alpaca paper trading.
Target → real money once 4–8 weeks of paper validation clears.

**Current production hypothesis: H149** — 100% H026 sector ETF rotation.

---

## Strategy Architecture

Single strategy: **H026 sector rotation — 100% of portfolio**.

| Parameter | Value |
|-----------|-------|
| Universe | 25 ETFs — 11 S&P sectors + BIL + GLD + TLT + IEF + TIP + DBC + AGG + GDX + DBA + SLV + UNG + EWZ + IBB + USO |
| Signal | Rank composite = rank(12m_ret) + rank(6m_ret) + rank(3m_ret) + rank(inv_6m_vol) |
| TSMOM filter | 12m return > +5% required to be eligible |
| Selection | Top-1 ETF by composite score |
| Safe harbor | BIL (T-bills) when no ETF clears the +5% threshold |
| Rebalance | First trading day of each month, 9:45 AM CT |

No IBS, no bond sub-strategy, no global equity sub-strategy. Those were eliminated across H145–H149 as H026 concentration was found to improve performance monotonically.

---

## Signal: Rank Ensemble (H120, then upgraded in H139)

```python
score = rank(12m_return) + rank(6m_return) + rank(3m_return) + rank(1/6m_vol)
# ranked within assets that pass the TSMOM filter (12m > +5%)
```

Each lookback ranked independently (1..N) then summed. TSMOM filter (12m > +5%) gates eligibility — borderline sectors (0–5% 12m return) are unreliable trend followers and are excluded.

---

## Rebalance Schedule

- **When:** First trading day of each month, 9:45 AM CT
- **How:** `python3 h112_monthly.py` (auto-detects first trading day)
- **Force:** `--force` to override date guard
- **Dry-run:** `--dry-run` to preview orders without submitting
- **Status:** `--status` to show positions without rebalancing

---

## Backtest Reference Numbers

OOS = 2018-01-01 onwards. AltOOS = 2013-01-01 onwards. Cumul = × initial equity.

| Hypothesis | OOS Cumul | AltOOS Cumul | OOS Sharpe | MaxDD | NegYrs | Key change |
|---|---|---|---|---|---|---|
| H116 | 6.56 | 14.94 | 3.845 | −3.6% | 0 | H026 12m TSMOM filter added |
| H120 | 24.77 | 85.99 | 4.354 | −3.5% | 0 | Rank ensemble (3m+6m+12m) |
| H122 | 27.88 | 103.53 | 4.535 | −3.8% | 0 | H026 vol-targeting (15% target) |
| H134 | 24.91 | 89.67 | 4.889 | −2.4% | 0 | H045 full ensemble (baseline correction) |
| H139 | 26.52 | 92.69 | 4.971 | −2.5% | 0 | H026 TSMOM +5% threshold |
| H145 | 33.85 | 125.98 | 4.801 | −2.6% | 0 | H026 weight: 27% → 30% |
| H148 | 127.95 | 675.33 | 3.153 | −7.6% | 0 | H026 100% of rotation (70% total); H041a+H045 eliminated |
| **H149** | **382.94** | **3243.08** | **3.007** | **−9.6%** | **0** | **H026 100% of portfolio; IBS cash drag removed** |

**Why H149 is the production target**: At 100% concentration, the TSMOM filter (+5% threshold) provides all crash protection — when no sector has >5% 12m return, 100% goes to BIL. The −9.6% MaxDD is acceptable for 382× OOS compounding. The Sharpe trade-off (3.007 vs 4.5+ earlier) is intentional: goal is absolute return, not risk-adjusted return.

---

## Vol-Targeting Note

Vol-targeting is coded in `h112_monthly.py` (`compute_h026_vol_scale()`) but is **structurally neutralized** at single-leg concentration. With one rotation leg:

```
effective_weight = (1.00 × scale) × (1.00 / (1.00 × scale)) = 1.00
```

The scale cancels in the renormalization step. The TSMOM filter provides all crash protection. Vol-scale is printed each run for monitoring but has no portfolio effect.

---

## Performance Tracking

Paper account started 2026-04-28.

```bash
python3 monitor.py --brief   # equity + P&L snapshot
python3 monitor.py           # full positions + drift from target
python3 monitor.py --signal  # recompute live signal (slow)
```

**First rebalance under H149**: May 1, 2026. April 28 was launched under old H122 triple-strategy setup.

### Trade Log Format

`h112_monthly_trades.json` stores each rebalance:
```json
{
  "date": "2026-05-01",
  "equity": 102444.84,
  "target": {"IBB": 102444.84},
  "eff_weights": {"h026": 1.0},
  "h026_scale": 1.0,
  "signals": {"h026": {"top_n": ["IBB"]}},
  "trades": [...]
}
```

---

## Strategy Evolution History

| H# | Key Change | Effect on OOS |
|----|-----------|---------------|
| H001–H020 | Initial ETF rotation research | Baseline established |
| H026 | H026 core: 25-asset universe + 12m TSMOM filter | Foundation |
| H083/H096 | Top-1 concentration confirmed optimal | −noise |
| H104/H107 | Universe expanded to 25 assets | +14%, +13% |
| H119/H120 | Rank ensemble (3m+6m+12m) | +28% OOS |
| H122 | Vol-targeting on H026 | +12% OOS |
| H127/H128 | 3m TSMOM on H045 bonds | +34% standalone |
| H139 | TSMOM threshold +5% for H026 | +6% OOS |
| H145–H147 | H026 weight 27% → 46% | Monotonic cumul gains |
| H148 | H026 100% of rotation; H041a/H045 eliminated | +72 OOS cumul |
| **H149** | **H026 100% of portfolio; IBS cash removed** | **+255 OOS cumul** |
| H150 | Low-Vol Anomaly tested standalone | Confirmed standalone, not deployable |
| H151 | Inv-vol mixed into H026 signal | NOT confirmed |

---

## Files

| File | Purpose |
|------|---------|
| `h112_monthly.py` | Main rebalancer (H149 production) |
| `monitor.py` | Portfolio monitor / signal recomputer |
| `h112_monthly_trades.json` | Persistent trade log |
| `kalshi_cpi.py` | Kalshi CPI nowcasting (pending PEM key) |
| `kalshi_nfp.py` | Kalshi NFP nowcasting (pending PEM key) |
| `kalshi_jobless.py` | Kalshi jobless claims (pending PEM key) |
