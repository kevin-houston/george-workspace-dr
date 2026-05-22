---
updated: 2026-05-22
type: research-note
source: https://github.com/yli188/WorldQuant_alpha101_code
---

# WorldQuant 101 Formulaic Alphas — Overlap with Confirmed Strategies

The 101 alphas from Kakushadze (2015) "101 Formulaic Alphas" are intraday-data signals (OHLCV + VWAP) designed for daily cross-sectional portfolios. Mapping against our confirmed/active strategies identifies where we overlap (already covered), where we diverge (gaps worth testing), and which signals are buildable with daily OHLCV data we already have.

**Data note**: ~60 of the 101 require VWAP (intraday volume-weighted average price). Alpaca free tier provides EOD OHLCV only — no intraday VWAP. Those signals are blocked unless we upgrade data feeds. The 40 OHLCV-only signals are immediately buildable.

---

## Already Covered by Confirmed Strategies

| Alpha | Signal type | Our equivalent | Status |
|-------|-------------|----------------|--------|
| alpha019 | 250-day momentum (long-term price return) | H198 (6-1m), H212 (vol-scaled) | CONFIRMED |
| alpha081 | 50-day volume × correlation momentum | Partially covered by H212 vol-scaling | CONFIRMED (partial) |
| alpha017, alpha035 | Short-term 5-day reversal | H181 (industry-adjusted 1-week reversal) | CONFIRMED (H181) |
| alpha049, alpha051 | Binary reversal on close acceleration | Simpler variant of H181 | Covered |
| alpha009, alpha010 | 4-5 day price min/max reversal | Subsumed by H181 | Covered |

**Conclusion**: Our momentum and reversal families are well-covered. The 101 alphas don't add much in those categories beyond confirming what we already have.

---

## Gaps — High Priority (OHLCV-only, not yet tested)

### Volume-Price Divergence Signals (OHLCV-buildable)

These require only close, volume, and returns — all available from our yfinance/Alpaca data.

| Alpha | Formula sketch | Why interesting |
|-------|----------------|-----------------|
| **alpha002** | `−rank(delta(log(volume), 2)) × rank((close−open)/open)` | Negative correlation between volume change and price change rank — volume surge with no price move predicts reversal |
| **alpha013** | `−rank(cov(rank(close), rank(volume), 5))` | Negative covariance of close and volume ranks over 5 days — stocks where price and volume decouple |
| **alpha033** | `rank(−1 × (1 − open/close))` | Open-to-close ratio as a signal — bullish bar (close > open) negative signal |
| **alpha038** | `−1 × rank(ts_rank(close, 10)) × rank(close/open)` | Combines price trend rank with open-to-close ratio |
| **alpha043** | `ts_rank(volume/mean(volume,20), 20) × ts_rank(−delta(close,7), 8)` | Volume spike relative to 20-day avg × 7-day price reversal |
| **alpha053** | `−1 × delta((close−low−(high−close)) / (close−low), 9)` | Change in close position within daily range — momentum of close-range positioning |
| **alpha101** | `(close − open) / (0.001 + high − low)` | Normalized intraday close position — "where did we close within the day's range" cross-sectionally ranked |

**H215 candidate**: Test alpha002 + alpha013 cross-sectional portfolio (volume-price divergence signals) on the 30-stock universe. Hypothesis: stocks where volume surges but price doesn't follow are due for reversal. Expected Sharpe 0.6–0.9 (these are weaker signals individually but may complement momentum as a diversifier).

### Open-to-Close / Intraday Structure (OHLCV, buildable today)

| Alpha | Signal | Relevance |
|-------|--------|-----------|
| **alpha033** | `−rank(1 − open/close)` | Short bullish daily bars. Contrarian |
| **alpha038** | Price trend × (close/open) | Trend-continuation with intraday confirmation |
| **alpha101** | `(close−open)/(high−low)` | Cross-sectional close-within-range rank |

alpha101 is particularly clean: it measures where each stock closed within its daily high-low range, ranked cross-sectionally. High = closed near top of range (momentum); low = closed near bottom (reversal candidate). Buildable in 10 lines. Low correlation to our existing signals.

---

## Blocked (Require VWAP — not on free data tier)

~60 alphas require VWAP: alpha005, alpha011, alpha025, alpha041, alpha042, alpha057, alpha060, alpha061, alpha062, alpha064, alpha065, alpha066, alpha068, alpha071, alpha072, alpha073, alpha074, alpha075, alpha077, alpha078, alpha083, alpha084, alpha085, alpha086, alpha088, alpha092, alpha094, alpha095, alpha096, alpha098, alpha099 and more.

**Unlock path**: Polygon.io paid tier ($29/mo) provides 1-minute intraday bars from which daily VWAP is easily computed. Worth evaluating if alpha101 OHLCV signals confirm, as the VWAP signals are more sophisticated and less widely replicated.

---

## Notable Absences from the 101 Alphas

The 101 alphas are pure price/volume signals. They do NOT contain:
- **BAB / Low-beta anomaly** (our H192-D — OOS Sharpe 1.367): not in the 101
- **PEAD / event-driven** (H174 — OOS WR 81.8%): not in the 101
- **Calendar effects** (H201 TOM, H206 Halloween): not in the 101
- **Idiosyncratic volatility** (H213): not in the 101
- **Fundamental signals** (P/E, earnings growth): not in the 101

This means our strongest confirmed strategies all come from outside the 101 alpha universe. The 101 are complementary, not overlapping, with our core portfolio.

---

## Recommended Next Steps

1. **Build alpha101** (close-within-range) as H215: 10-line script, OHLCV-only, test on 30-stock universe. Low effort, quick to validate.
2. **Build alpha002 + alpha013 blend** as H216: volume-price divergence basket. Hypothesis: adds diversification to H212 momentum (vol-price divergence should be negatively correlated with momentum in crashes).
3. **Stage for dream cycle**: alpha033 and alpha038 (open-to-close ratio signals) — simple, OHLCV, potentially uncorrelated with existing strategies.
4. **Unlock VWAP signals**: if budget allows, $29/mo Polygon paid tier opens 60+ additional signals.

---

## H215 Design Note (alpha101 — close-within-range)

```python
# alpha101 = (close - open) / (0.001 + high - low)
# Cross-sectional rank monthly, long top-6, monthly rebalance
# Same universe as H212 (30 large-cap stocks)
# IS: 2013-2020, OOS: 2021-2026, confirm threshold: OOS Sharpe > 0.7

def compute_alpha101(ohlcv: pd.DataFrame) -> pd.Series:
    """Compute alpha101 for each stock on a given date."""
    return (ohlcv["close"] - ohlcv["open"]) / (0.001 + ohlcv["high"] - ohlcv["low"])
```

**Expected**: Sharpe 0.6–0.9 OOS. Corr(H212) likely < 0.3 (intraday structure vs. intermediate momentum). If confirmed, adds a short-horizon signal to the portfolio blend.
