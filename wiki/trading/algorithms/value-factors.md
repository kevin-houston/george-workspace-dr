---
added: 2026-06-14
updated: 2026-08-19
category: algorithms / fundamental / value
---

# Value Factor Investing in Systematic Trading

Strategies exploiting the **value premium** — the empirical tendency for cheap stocks
(low price relative to fundamentals) to outperform expensive stocks over long horizons.
One of the three canonical factor premia alongside momentum and quality.

---

## 1. What Is the Value Premium?

**Definition:** Stocks with low prices relative to fundamental accounting metrics
(earnings, book value, cash flow, sales) outperform high-price/fundamental stocks
over multi-year horizons.

**Academic source:** Fama & French (1992, 1993) documented the HML (high-minus-low
book-to-market) value premium; subsequent work shows it generalizes across metrics
and global markets.

**Magnitude:**
- Original Fama-French HML: ~4–5%/year annualized (1963–2022, declining post-publication)
- Post-publication (2003–2022): HML has been largely flat or negative; the "value factor
  drought" of 2017–2020 coincided with tech dominance
- FCF yield (Cash Cows approach): 2–3%/year alpha over SPY in academic samples;
  more robust than book-to-market in high-tech environments

**Why it works (contested):**
- **Risk story (Fama-French):** value stocks are in financial distress; the premium
  compensates for crash risk
- **Mispricing story:** investors overextrapolate recent growth, overvaluing growth
  stocks and undervaluing "boring" cheap stocks → mean reversion
- **Liquidity story:** value stocks tend to be smaller, less liquid; illiquidity premium

---

## 2. Value Metrics Compared

| Metric | Formula | Strengths | Weaknesses |
|--------|---------|-----------|-----------|
| **Book/Market (B/M)** | Book equity / Market cap | Long history, standardized | Intangibles era makes book value unreliable |
| **E/P (Earnings Yield)** | EPS / Price | Widely tracked | Earnings manipulation; volatile for cyclicals |
| **FCF Yield** | Free Cash Flow / Market cap | Hard to manipulate; real cash | CapEx-heavy industries look bad |
| **EV/EBITDA** | Enterprise Value / EBITDA | Capital-structure neutral | Ignores working capital |
| **P/S (Price/Sales)** | Market cap / Revenue | Works for negative-earnings firms | Ignores profitability |
| **Dividend Yield** | Annual div / Price | Observable, hard to fake | Not paid by growth firms |

**Recommendation for systematic trading:** FCF Yield or EV/EBITDA preferred over
book-to-market in modern large-cap universe — less affected by intangible asset
accounting changes post-2000.

---

## 3. Free Cash Flow Yield — The Dominant Modern Signal

**Formula:**
```
FCF Yield_i = (Operating CF - CapEx) / Market Cap
```

**Why FCF beats book-to-market:**
- Book value is distorted by intangibles (goodwill, R&D capitalization rules)
- FCF is audited cash, harder to manipulate than earnings
- FCF directly measures what investors can extract from the business
- Particularly relevant post-2010 as tech/intangibles dominate S&P 500

### COWZ ETF — Pacer US Cash Cows 100

The simplest implementable FCF-yield strategy:
- Universe: Russell 1000 (top 1000 by market cap)
- Screen: top 100 by FCF Yield
- Rebalance: quarterly
- Inception: 2016-06-05

**COWZ OOS performance (2020–2025):**
- B&H Sharpe ≈ 0.893 (vs SPY 0.998) — underperforms SPY OOS
- 2022: COWZ -9.7% vs SPY -18.2% — genuine defensive value in rate-hike bear
- 2023-2024: COWZ lagged during AI/tech bull run

**Key learning from H286 (COWZ/SPY cross-momentum):**
- Pure COWZ B&H underperforms SPY OOS 2020-2025 (Sharpe 0.893 vs 0.998)
- COWZ/SPY 6m cross-momentum signal improves to OOS Sharpe 1.031 (Corr(SPY)=0.596)
- The value premium is **regime-conditional**: FCF yield beats during value regimes
  (2022), lags during growth/momentum regimes (2023-2024)

---

## 4. FCF Yield via FMP API (H284)

**Source:** FMP `stable/key-metrics` endpoint returns pre-computed `freeCashFlowYield`
for 5 annual fiscal years.

```python
import requests
import os

FMP_BASE = "https://financialmodelingprep.com/stable"
FMP_KEY = os.environ["FMP_API_KEY"]

def fetch_fmp_annual_fcf_yield(ticker):
    url = f"{FMP_BASE}/key-metrics?symbol={ticker}&limit=5&apikey={FMP_KEY}"
    rows = requests.get(url, timeout=20).json()
    result = {}
    for row in rows:
        date_str = row.get("date", "")
        val = row.get("freeCashFlowYield")
        if date_str and val is not None:
            result[date_str] = float(val)
    return result

# Signal construction:
# - Annual rebalance at end of Q1 (March 31)
# - Use only FY data ending ≤ Dec 31 of prior year (3-month reporting lag)
# - Rank by FCF yield; long top-10 equal-weight
```

**H284 results (CONFIRMED — weak):**
- IS (Apr 2022–Mar 2024): Sharpe=0.679
- OOS (Apr 2024–present): Sharpe=1.297, MaxDD=-10.3%
- ⚠️ Major caveats: only 21/50 tickers covered on FMP free tier; banks inflate
  FCF yield (no CapEx → FCF ≈ net income for JPM/WFC/BAC); only 4 annual rebalances

**Free-tier coverage gap:** FMP free tier drops ~40% of tickers silently. Financially
distressed or small tickers absent. The resulting portfolio is biased toward
well-covered large-caps. **Must exclude financials sector** for clean FCF/P test.

---

## 5. Quality ETF Rotation (H285)

Rotating among quality-factor ETFs (QUAL, SPHQ, DGRW) by 6-month momentum:

- **Result:** OOS Sharpe 0.932 > gate, but Corr(SPY) = 0.969 — near-perfect SPY
  correlation. Not additive to production portfolio.
- **Key finding:** QUAL B&H actually *underperforms* SPY by -1.59%/year OOS.
  The quality factor (as captured by QUAL) lost alpha in 2020-2025.

---

## 6. Macro Regime-Gated FCF/P (H286 — CONFIRMED)

The **COWZ/SPY 6m cross-momentum** signal is the strongest confirmed value variant:

```python
# Signal: hold COWZ when COWZ 6m return > SPY 6m return, else hold SPY
# Escape: shift to BIL when SPY < 200-day MA

cowz_6m = cowz_prices.pct_change(6)
spy_6m  = spy_prices.pct_change(6)

# Hold COWZ when value is outperforming growth
signal = cowz_6m > spy_6m     # monthly rebalance
escape = spy_prices > spy_prices.rolling(200).mean()  # market regime gate
```

**H286 Variant B results (OOS 2021-2025):**
- Sharpe=1.031, MaxDD=-16.2%, NegYrs=2, Corr(SPY)=0.596

**Why Corr=0.596 matters:** Below 0.60 threshold for diversification assessment —
H286 Var B is one of the few confirmed equity strategies with genuinely low SPY
correlation. This comes from the 2022 value regime (COWZ returned +2% vs SPY -18%).

**Limitation:** Only 1 year of genuine value outperformance (2022) in the OOS window.
Need 3+ more years of data before production consideration.

---

## 7. Valuation-Based Market Timing

Beyond cross-sectional stock selection, value metrics can time the *market*:

### Shiller CAPE (Cyclically Adjusted P/E)

- Long-run mean reversion: high CAPE → lower 10-year forward returns
- CAPE as of 2026: ~34 (elevated vs long-run mean ~17)
- **Tactical use:** reduce equity allocation when CAPE > 2 SD above historical mean
- **Limitation:** CAPE is a poor timing signal over 1-3 year horizons (can stay
  elevated for decades); not suitable for monthly rebalancing

### Earnings Yield vs Treasury Yield ("Fed Model")

- Buy equity when E/P (earnings yield) > 10-year Treasury yield
- Popular in 1980s; largely discredited as a standalone timer
- The 2022-2024 rate-hike cycle broke the Fed Model (both equity E/P and bond yields
  rose together, model gave no clear signal)

---

## 8. The Value vs. Momentum Tension

**Critical interaction:** Value and momentum are *negatively correlated* at the stock
level (−0.30 to −0.50). A stock near its 52-week high (high momentum) is often
expensive (low value); a beaten-down value stock often has poor momentum.

**Blending approaches:**
1. **AQR combo:** Hold separate value and momentum portfolios; the negative correlation
   provides natural hedging (Asness, Moskowitz & Pedersen 2013)
2. **Price-to-52wk-high hybrid:** Only buy cheap stocks that are showing price recovery
   (e.g., FCF yield top quartile AND price > 6m average); filters for "value with
   momentum confirmation"
3. **Regime switching:** Momentum in bull markets, value in bear/recovery markets

**From H286:** The COWZ/SPY cross-momentum signal implicitly implements this — it
holds value (COWZ) when value is showing relative momentum vs SPY, and switches to
SPY otherwise. This is a practical momentum-conditioned value tilt.

---

## 9. Data Sources for Value Factors

| Source | Metric | Free? | Python |
|--------|--------|-------|--------|
| FMP `stable/key-metrics` | FCF Yield, P/E, P/B, EV/EBITDA | Yes (5yr, ~60% coverage) | `requests.get(url).json()` |
| EDGAR XBRL `companyfacts` | Raw income stmt / balance sheet | Yes (2009–present) | See edgar-fundamentals.md |
| yfinance `.info` | P/E, P/B, trailing P/S | Yes (spotty) | `yf.Ticker(t).info["trailingPE"]` |
| COWZ ETF | Top-100 FCF yield screen (Russell 1000) | Via yfinance | `yf.download("COWZ")` |
| Quiver Quant | Congressional trades, insider buying | $30/mo | REST API |
| Compustat | Gold standard — point-in-time fundamentals | ~$50k/yr | Bloomberg/Wharton |

**Free tier limitation:** FMP free tier is most convenient but drops ~40% of tickers
silently and excludes financials correctly (no FCF signal there). EDGAR XBRL covers
2009+ and 100% of SEC filers — use for production-grade tests.

---

## 10. 2026 Research Update: Value-Momentum Intersection & FCF Yield Ranking

**Researched 2026-08-19** (nightly wiki rotation — Algorithms section, thinnest by
genuine-new-page recency: last touched 2026-07-29, vs. every other top-level trading
section touched within the prior 9 days).

### FCF yield's standing among valuation ratios

Alpha Architect's 40-year backtest (1971–2010) ranking every major single-factor
valuation ratio found **FCF Yield placed 2nd-best**, delivering ~16.6% average annual
return to the top decile — trailing only EBITDA/EV in that study, and ahead of
book-to-market, E/P, and dividend yield individually. This corroborates the wiki's
existing §2 recommendation (FCF Yield / EV-EBITDA over B/M in a modern universe) with
an explicit long-sample ranking rather than a qualitative claim.

### The value + momentum intersection — concrete magnitude

Directly actionable against **Open question #4** below (previously speculative,
"reduces universe to ~5–8 stocks but higher precision"): a 2026 Quant Investing /
Alpha Architect-style analysis quantifies the effect. Restricting the investable
universe to stocks in the **top 20% by FCF yield AND top 20% by trailing 12-month
price return** (a pure intersection filter, no scoring/blend) produced a **506.3%**
higher cumulative return over the sample period than holding the top-20%-FCF-yield
decile alone. This is the sharpest documented magnitude yet for the value/momentum
combo referenced qualitatively in §8 (AQR combo, Asness/Moskowitz/Pedersen 2013) —
prior wiki coverage had the *mechanism* (negative value/momentum correlation → natural
diversification) but not this *intersection-filter* magnitude.

Mechanism note: this is a **conjunctive AND filter**, not a rank-blend. It differs from
H286 (COWZ/SPY cross-momentum, a value-timing signal) and from AQR's separate-sleeves
approach — it directly narrows the value universe to only "cheap stocks that are
already recovering," which the existing wiki text flags (§8.2) as the more
precision-oriented of the three blending approaches but had not yet quantified.

### Quality-value reinforcement

Multiple 2026 sources restate the standard finding that combining quality screens
(profitability, low accruals — see [quality-factor.md](quality-factor.md)) with
valuation avoids the classic "value trap" (cheap because deteriorating, not because
mispriced). No new magnitude beyond what quality-factor.md already documents via
Piotroski F-Score / Novy-Marx GP/A — noted here only to confirm the 2026 literature
still treats quality as the standard value-trap filter, not a newer alternative.

### H522 proposed: FCF-yield × 12-1 momentum intersection filter

Builds directly on Open question #4 (below) with the Alpha Architect-style magnitude
as prior justification for expecting a real effect, not just a plausible mechanism:

- **Universe**: existing 50-stock FMP-covered universe from H284 (excluding
  financials, per H284's documented bank-FCF-distortion caveat)
- **Filter**: top quartile FCF yield (FMP `key-metrics`) AND top quartile 12-1m
  momentum (skip most recent month, per H198's confirmed skip-month convention)
  — intersection, not rank-sum
- **Rebalance**: monthly (vs. H284's quarterly-only cadence — momentum leg needs
  monthly refresh even though the FCF leg is still annual-lagged)
- **IS/OOS**: same split as H284 (IS Apr 2022–Mar 2024 / OOS Apr 2024–present) for
  direct comparability; note this window is short (H284's own caveat: "only 4 annual
  rebalances") and a confirmation here should be treated as directional, not final
- **Gate**: OOS Sharpe > 1.297 (H284 baseline) AND intersection universe ≥ 5 names/month
  (avoid over-concentration from a double-restrictive filter)
- **Key risk carried over from H284**: FMP free-tier ~40% silent coverage gap will bite
  harder once a second filter (momentum) is applied on top of the already-reduced FCF
  universe — worth an explicit qualifying-names-per-month diagnostic in the script,
  not just a final Sharpe number

Staged as a low-risk research-lead in tonight's dream-cycle proposals (see Phase 2 scan
summary) rather than run directly — this needs the H284 script as a base and a
qualifying-universe-size sanity check before a full backtest is worth the run time.

---

## 11. Hypothesis Log

| H# | Signal | Verdict | OOS Sharpe | Key Caveat |
|----|--------|---------|-----------|-----------|
| H284 | FCF Yield via FMP (annual rebalance, top-10) | CONFIRMED-WEAK | 1.297 | Only 21/50 tickers; banks dominate; 4 data points |
| H285 | Quality ETF rotation (QUAL/SPHQ/DGRW) | CONFIRMED-WEAK | 0.932 | Corr(SPY)=0.969; not additive |
| H286 | COWZ/SPY cross-momentum + BIL escape | CONFIRMED | 1.031 | Corr(SPY)=0.596; 1 value year in OOS |

### Open questions / next steps

1. **H284-fix:** Re-run excluding financials sector; use EDGAR XBRL for full coverage
2. **H293 candidate:** EV/EBITDA cross-section on 50-stock universe (SEC EDGAR quarterly)
3. **COWZ vs SCHD:** Test dividend-growth (SCHD) as alternative FCF-proxy ETF
4. **Value + momentum combo:** Long FCF top-quartile AND momentum top-quartile stocks
   (intersection filter, reduces universe to ~5–8 stocks but higher precision) —
   **quantified 2026-08-19, see §10**: a 2026 analysis reports +506.3% cumulative
   return from this exact intersection filter vs. FCF-yield-alone; staged as H522

---

## Cross-References

- [Quality Factor (QMJ, Piotroski, GP/Assets)](quality-factor.md) — quality is a
  close relative of value; QMJ = high quality minus junk
- [Factor Momentum & Style Rotation](factor-momentum-style-rotation.md) — VLUE ETF
  performance in H255; value factor had negative alpha 2020-2025 in ETF rotation test
- [Momentum Strategies](momentum-strategies.md) — negative value/momentum correlation;
  blending rationale
- [Low-Volatility Anomaly](low-volatility.md) — low-vol stocks often "value-ish"; BAB
  vs value premium overlap
- [Alternative Data Sources](../data-sources/alternative-data.md) — FCF data via FMP
  and EDGAR
- [Behavioral Finance Signals](behavioral-finance-signals.md) — disposition effect
  (CGO) as value-adjacent signal; lottery premium (MAX) is value's mirror image
