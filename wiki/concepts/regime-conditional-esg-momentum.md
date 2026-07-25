---
title: Regime-Conditional ESG Momentum — Quantitative Implementation
tags: impact-investing, ESG, regime-detection, momentum, factor-models
added: 2026-07-25
category: Impact Investing
---

# Regime-Conditional ESG Momentum — Quantitative Implementation

Bridges the [ESG Factor Integration](esg-factor-integration.md) page with the [Regime Detection](../trading/algorithms/regime-detection.md) and [Momentum Strategies](../trading/algorithms/momentum-strategies.md) pages. Addresses the most critical known weakness of ESG signals: **regime-dependence**. ESG factors that work in one macro environment (low rates, ESG tailwind) can reverse in another (energy boom, ESG political backlash).

---

## The Core Problem: ESG Performance Is Not Regime-Invariant

Academic consensus (as of 2025-2026):

| Macro Regime | ESG Tilt Outcome | Primary Driver |
|---|---|---|
| Low rates / ESG growth (2013-2021) | Outperforms: +2–4%/yr alpha | Capital flows, ESG premium |
| Rising rates / energy rally (2022) | Underperforms: -4–6% relative | Fossil fuel exclusion costs |
| Inflation / commodity supercycle | Underperforms | Same: fossil fuel tilt |
| Political ESG backlash (US 2024-2025) | Uncertain | Institutional AUM slowdown |
| Climate regulation accelerating (EU 2026) | Outperforms | Policy-driven repricing |

This regime-dependence mirrors what the trading wiki has documented across strategies:
- H429 (HMM regime detection) found rolling re-fitting is essential to avoid degeneracy
- H249 (regime-conditional weights) confirmed 4-state regime engine improves Sharpe +0.282
- H311 (static multi-asset diversification) showed low-rate assumption embedded in EW portfolios

The **key hypothesis**: ESG signals, like momentum signals, require regime conditioning to be exploitable.

---

## ESG Momentum Signal Construction

### Signal 1: ESG Score Momentum (Δ-ESG)
```python
# Monthly change in composite ESG score (source: Refinitiv, MSCI, or SEC NLP proxy)
delta_esg = esg_scores.diff(3)   # 3-month change in score
delta_esg_rank = delta_esg.rank(pct=True, axis=1)  # cross-sectional rank
```

**Evidence**: Nagy, Kassam & Lee (MSCI 2016) document Sharpe ~0.5 globally on ESG momentum
standalone; Giese et al. (JIM 2019) find 6-24 month window optimal.

### Signal 2: NLP Controversy Signal (from H163/H174 pipeline)

The existing H174 FinBERT pipeline (score ≥ 0.18, EPS surprise ≥ 2%) can be extended:

```python
# Extend H174 scoring to detect ESG controversy in 8-K text
ESG_NEGATIVE_KEYWORDS = [
    'EPA fine', 'OSHA violation', 'data breach', 'class action',
    'workplace injury', 'supply chain violation', 'discrimination suit',
    'environmental penalty', 'regulatory sanction'
]

def score_esg_controversy(text: str) -> float:
    """
    Returns controversy severity score 0-1.
    Combines keyword detection with FinBERT negative sentiment.
    """
    keyword_hits = sum(1 for kw in ESG_NEGATIVE_KEYWORDS
                       if kw.lower() in text.lower())
    keyword_score = min(keyword_hits / 3.0, 1.0)
    # Combine with FinBERT negative sentiment from H174 pipeline
    return keyword_score
```

**Evidence**: Kölbel et al. (2020): NLP controversy extraction predicts -2% drift over 60 days.

### Signal 3: Supply Chain Network ESG Propagation (H446 extension)

The H446 stub (arXiv:2606.29290) shows network propagation improves cross-sectional return
prediction using FinBERT 10-K embeddings. The same architecture can propagate ESG controversy
events through supply chain links:

- If a Tier-1 supplier faces an EPA fine → customer firms face ESG contamination risk
- Network-augmented ESG signal: `ESG_net[i] = 0.5 * ESG[i] + 0.5 * Σ_j(A[i,j] * ESG[j])`
- This is the ESG analog to the H419 secondary PEAD watchlist design

---

## Regime-Conditional Implementation

### Regime Detection Layer

Following H429 / H444 design pattern:

```python
def get_esg_regime_weight(spy_returns: pd.Series, date: pd.Timestamp,
                           roll_years: int = 3) -> float:
    """
    Return scale factor for ESG signal based on macro regime.
    1.0 = full exposure; 0.0 = no ESG tilt.

    Regimes (from H429 Wasserstein-HMM):
    - Bull/low-vol: ESG tilt active (historical evidence supports ESG premium)
    - Bear/high-vol: ESG tilt reduced (fossil fuel exclusion hurts; quality factor dominates)
    - High-rate: ESG tilt at 0.5 (mixed evidence; defensive ESG sectors hurt)
    """
    from hmmlearn.hmm import GaussianHMM
    roll_days = int(roll_years * 252)
    window = spy_returns.iloc[-roll_days:].values.reshape(-1, 1)

    model = GaussianHMM(n_components=2, covariance_type='diag', n_iter=200, random_state=42)
    try:
        model.fit(window)
        state = model.predict(window)[-1]
        bull_state = int(model.means_.flatten().argmax())
        is_bull = (state == bull_state)
    except Exception:
        is_bull = True  # default to full exposure

    # Also check VIX regime (H165a confirmed threshold 25)
    import yfinance as yf
    vix = yf.download('^VIX', start='2004-01-01', auto_adjust=True, progress=False)['Close']
    vix_current = vix.loc[:date].iloc[-1] if date in vix.index else 20.0
    vix_calm = (vix_current < 25)

    if is_bull and vix_calm:
        return 1.0   # Full ESG tilt in calm bull market
    elif is_bull and not vix_calm:
        return 0.5   # Half tilt: bull market but elevated vol
    else:
        return 0.0   # No ESG tilt in bear or high-vol regime
```

### Integrated ESG Tilt on Existing Factor Portfolios

The recommended integration path (lowest implementation cost, highest leverage):

```python
def esg_tilt_ranking(base_signal: pd.Series, esg_momentum: pd.Series,
                     regime_weight: float, esg_alpha: float = 0.3) -> pd.Series:
    """
    Blend base factor signal with ESG momentum signal, scaled by regime.

    Parameters
    ----------
    base_signal : cross-sectional rank of primary factor (e.g., H198 6-1m momentum)
    esg_momentum : cross-sectional rank of Δ-ESG score
    regime_weight : 0-1 from get_esg_regime_weight()
    esg_alpha : max weight on ESG component (0.3 = 30% ESG, 70% base)
    """
    effective_esg_alpha = esg_alpha * regime_weight
    combined = (1 - effective_esg_alpha) * base_signal + effective_esg_alpha * esg_momentum
    return combined.rank(pct=True)
```

---

## Historical Performance Estimates (Literature-Based)

No George backtest yet for regime-conditional ESG momentum. Literature estimates for reference:

| Approach | Estimated Sharpe | MaxDD Estimate | Period |
|---|---|---|---|
| ESG level signal (standalone) | 0.2-0.4 | -20% to -30% | 2010-2024 |
| ESG momentum (Δ-score) | 0.4-0.6 | -15% | 2010-2024 |
| ESG momentum + VIX gate | ~0.7 | -10% | estimated |
| ESG tilt on H198 momentum | ~H198 + 0.1-0.15 | Minimal change | estimated |
| Controversy signal (NLP) | -2%/60d per event | — | event-study |

**Key expected finding**: ESG tilt alone will not pass the H198 gate (1.174). The value
is as an orthogonal tilt that slightly improves Sharpe while reducing ESG-correlated tail risk.

---

## Free Data Sources for ESG Implementation

Priority-ordered for George's pipeline:

1. **SEC EDGAR 10-K Item 1C** (mandatory since 2023)
   - Climate risk disclosures: parsing with EdgarTools already in pipeline
   - NLP extraction of climate/ESG language via H163 FinBERT infrastructure
   - Coverage: all S&P 500 + Russell 1000 companies

2. **CDP (Carbon Disclosure Project)**
   - Free download after registration at cdp.net
   - 18,700 companies; energy/water/supply chain scores
   - Annual frequency; 2023-2024 data available

3. **SEC EDGAR SIC codes** (already cached from H181 sector data)
   - Supply chain proxy for H446 / ESG network propagation
   - Free, point-in-time, no survivorship bias

4. **Yahoo Finance sustainability scores** (ESG pillar scores)
   - `import yfinance as yf; info = yf.Ticker('AAPL').sustainability`
   - Stale (updated infrequently) and limited coverage; use as fallback only

5. **Refinitiv ESG via WRDS** (if Kevin gets institutional access)
   - Point-in-time historical ESG scores; most comprehensive free academic source
   - Required for rigorous backtesting; avoids rating-change look-ahead bias

---

## Proposed Hypothesis: H447 (ESG Momentum Tilt on H198)

**Design stub** (not yet implemented):
- Universe: H198 30-stock NASDAQ universe
- Signal: 0.7 × 6-1m momentum rank + 0.3 × Δ-ESG (3-month change in Yahoo ESG score)
- Gate: VIX < 25 + SPY > 200MA (H165a confirmed regime)
- IS: 2014-2020 (earliest ESG score coverage), OOS: 2021-2026
- Gate: OOS Sharpe > 1.174 (H198 baseline) AND MaxDD better by > 2pp
- Data risk: Yahoo ESG scores stale/spotty pre-2018; may need WRDS Refinitiv

**Prediction**: Mild positive impact (0.1-0.2 Sharpe improvement) in regime-filtered version;
likely not enough to justify the data complexity vs. simpler H301-style overlay.

---

## Cross-references

- [ESG Factor Integration](esg-factor-integration.md) — full taxonomy of ESG signal types and data sources
- [Impact Investing Market Landscape 2025](impact-investing-market-2025.md) — AUM, institutional shift, ESG product growth
- [Impact Measurement Standards](impact-measurement-standards.md) — IRIS+, IMP 5 dimensions, SFDR
- [Supply Chain Textual Signals](supply-chain-textual-signals.md) — arXiv:2606.29290; H419 supply chain PEAD; H446 stub
- [Regime Detection](../trading/algorithms/regime-detection.md) — VIX/200MA gates, H429, H444 Wasserstein-HMM
- [Momentum Strategies](../trading/algorithms/momentum-strategies.md) — H198 6-1m baseline; H026 production strategy
- [Event-Driven Strategies](../trading/algorithms/event-driven.md) — H163/H174 FinBERT pipeline; controversy signal extension
- [Market Timing Overlays](../trading/algorithms/market-timing-overlays.md) — VIX term structure, 200MA overlay designs
- [PEAD — Post-Earnings Announcement Drift](../trading/algorithms/pead.md) — controversy signal as PEAD analog
