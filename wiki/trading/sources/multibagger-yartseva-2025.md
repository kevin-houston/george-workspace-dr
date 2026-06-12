---
created: 2026-06-12
updated: 2026-06-12
type: source_summary
authors: Anna Yartseva (Birmingham City University)
published: February 2025
source: CAFÉ Working Paper No. 33
url: https://www.open-access.bcu.ac.uk/16180/1/The%20Alchemy%20of%20Multibagger%20Stocks%20-%20Anna%20Yartseva%20-%20CAFE%20Working%20Paper%2033%20%282025%29.pdf
---

# The Alchemy of Multibagger Stocks — Yartseva 2025

**Author:** Anna Yartseva, Birmingham City University  
**Published:** February 2025 — CAFÉ Working Paper No. 33

Empirical study of what drives 10x+ stock returns (multibaggers) in US markets. Identifies FCF yield as the dominant predictive factor, contradicts EPS-growth narrative, and reveals counterintuitive entry signals based on proximity to price range extremes.

---

## What the Paper Studies

- **Universe:** 464 US multibagger stocks achieving 10x+ total returns, 2009–2024
- **Method:** Dynamic factor models (time-series + cross-sectional regression)
- **Comparison group:** S&P 500 and matched non-multibagger control sample
- **Objective:** Identify pre-event characteristics that distinguish multibaggers *before* the run

---

## Descriptive Stats — The Multibagger Sample at Entry

| Metric | Median at Entry (2009 cohort) |
|---|---|
| Market cap | $348M |
| Price/Sales | 0.6× |
| Price/Book | 1.1× |
| Forward P/E | 11.3× |

Key observation: multibaggers look like **cheap, small, boring stocks** at entry — not high-flying growth names. Median P/S of 0.6 and P/B of 1.1 indicate deep-value characteristics.

---

## Key Empirical Findings

### 1. FCF Yield is the #1 Driver

FCF/P (free cash flow yield) has the **largest coefficient in all dynamic models** — the single most predictive variable for subsequent multibagger performance. A company must be generating real cash relative to its price. This is not the same as earnings yield — it filters out accruals-based "earnings."

### 2. EPS Growth is NOT Significant

Contradicts conventional wisdom. Strong EPS growth alone does NOT predict multibagger status. The value characteristic dominates the growth characteristic.

### 3. Value > Growth — Both Must Be Present

B/M (book-to-market) and FCF/P have the largest coefficients across models. The winning template is not pure growth nor pure value — it is **value-priced growth**. A growth stock that also screens as cheap on cash flow metrics.

### 4. Size Effect is Dramatic

| Market Cap Bucket | Excess Return |
|---|---|
| Small-cap (<$250M) | +37.7% |
| Large-cap | +9.7% |

The small-cap premium for multibaggers is enormous. Large-cap 10x opportunities exist but are significantly rarer in both frequency and magnitude.

### 5. Profitability: ROA Matters, Not ROE

ROA is significant in dynamic models. ROE and operating margin are NOT significant. This isolates asset efficiency — how well the business converts its asset base into profit — from leverage effects (which inflate ROE) or accounting margin differences across industries.

### 6. Investment Pattern: Asset Growth Direction Matters

Two separate findings:
- **Aggressive asset growth is good** — expanding businesses outperform
- **BUT: `asset_growth > EBITDA_growth` is bad** — a spread of −22.8pp in next-year returns when capital is being deployed faster than earnings are growing

The signal is not asset growth in isolation but whether earnings are keeping pace with asset expansion. Over-investment without commensurate earnings growth is a strong negative predictor.

### 7. Momentum is INVERTED at 12m High

Proximity to the 52-week high **predicts lower next-year returns**. Conversely:
- Best entry: **near the 12-month low**, following a 6-month price decline
- The typical narrative (buy breakouts, buy near 52w high) is reversed for multibagger entry
- This is consistent with contrarian entry / mean-reversion at the individual stock level before a fundamental re-rating

Note: this does not contradict cross-sectional momentum (H198, H217) — that signal operates across the stock universe. This finding is about *when to enter a single stock* within its own price history.

### 8. Interest Rate Regime Overlay

Rising interest rates depress multibagger returns by **8–12 percentage points**. High-rate environments favor large, profitable, cash-generative companies — not the small, re-rating growth stories that multibaggers represent. This is a macro overlay signal, not a stock-level factor.

### 9. NOT Significant Factors

The following showed no predictive power in this study:
- P/E ratio
- Debt ratios (leverage, debt/equity, interest coverage)
- R&D spending
- Altman Z-score

The absence of P/E significance is notable — the market's earnings multiple is not predictive, but the cash flow multiple (FCF/P) is. Debt levels do not distinguish multibaggers from controls.

---

## Factor Summary Table

| Factor | Direction | Magnitude | Notes |
|---|---|---|---|
| FCF/P (FCF yield) | + | Largest coefficient | #1 predictor across all models |
| B/M (book-to-market) | + | Large | Value signal — confirms deep-value entry |
| Market cap | − | Large | Small-cap: +37.7% excess vs large-cap +9.7% |
| ROA | + | Significant | Dynamic models only; ROE and op. margin NOT sig |
| Asset growth | + | Positive | Expanding business is good... |
| asset_growth − EBITDA_growth | − | −22.8pp | ...unless capex is outrunning earnings |
| 12m high proximity | − | Negative | Near high = bad entry; near low = good entry |
| Interest rates (rising) | − | 8–12pp | Macro overlay — rate hikes depress returns |
| EPS growth | 0 | NOT sig | Contradicts conventional wisdom |
| P/E ratio | 0 | NOT sig | Earnings multiple irrelevant |
| Debt ratios | 0 | NOT sig | Leverage doesn't distinguish |
| R&D spend | 0 | NOT sig | Innovation spending not predictive |
| Altman Z-score | 0 | NOT sig | Distress score not predictive |

---

## Implications for the Trading Pipeline

### A. FCF/P Screening as Universe Filter

FCF yield ranking could serve as a pre-filter for momentum universes (H277, H228):
- Build a universe from top-decile FCF/P stocks in small-cap space (<$250M market cap)
- Apply existing momentum signal on top of this value-screened universe
- Hypothesis: momentum works better within a fundamentally sound value-screened cohort

### B. Negative Filter: `asset_growth > EBITDA_growth`

Implement as an exclusion criterion in stock selection:
- If a company's asset base is growing faster than its EBITDA, drop it from the buy universe
- This is a single-quarter or trailing-four-quarter computation from EDGAR XBRL data
- Signal: −22.8pp return impact is large enough to justify systematic filtering

### C. 12-Month Price Range as Entry Signal

Near-52w-low is a better entry point than near-52w-high:
- Compute `(price − 52w_low) / (52w_high − 52w_low)` — a value in [0,1]
- Low values (e.g., <0.25) combined with FCF/P screening = candidate entry
- This reverses the conventional breakout-entry logic and suggests waiting for pullbacks
- Consistent with H174 PEAD entry discipline: entry after a gap-down (near recent low) following positive fundamental event

### D. Interest Rate Regime Macro Overlay

For any growth-stock-heavy strategy:
- Apply rate-hike regime flag as a macro overlay (already built in H249 framework)
- Reduce or eliminate exposure to small-cap FCF-yield growth stocks during FOMC rate-hike cycles
- 8–12pp drag per hike cycle justifies a defensive tilt to large-cap value during tightening

---

## Proposed Hypothesis

**H285 (tentative):** FCF-yield-ranked small-cap stock universe with asset_growth > EBITDA_growth exclusion and 12m-low entry timing. Test whether a 50-100 stock universe filtered on:
1. Market cap <$500M
2. FCF/P top decile (within size bucket)
3. asset_growth < EBITDA_growth (capex discipline gate)
4. Price in lower 25% of 52w range

...produces a confirmation-worthy alpha signal using H198/H217-style momentum execution.

Data requirement: EDGAR XBRL (CompanyFacts) for FCF + EBITDA + asset history. Free 15-year history available (see `data-sources/edgar-fundamentals.md`).

---

## Cross-References

- [Momentum Strategies](../algorithms/momentum-strategies.md) — H277, H228, H198, H217 momentum signals
- [Factor Models & Cross-Sectional Alpha](../algorithms/factor-models.md) — value factor framework
- [Low-Volatility Anomaly](../algorithms/low-volatility.md) — size effect overlap
- [Quality Factor (QMJ)](../algorithms/quality-factor.md) — ROA / profitability signals
- [SEC EDGAR XBRL Fundamentals](../data-sources/edgar-fundamentals.md) — FCF, EBITDA, asset data source
- [Regime Detection Signals](../backtesting/regime-detection-signals.md) — rate-hike overlay
- [Signal Half-Life & Alpha Decay](../backtesting/signal-halflife.md) — decay profile for fundamental signals
