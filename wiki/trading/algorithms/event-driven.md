---
updated: 2026-05-05
type: strategy-guide
status: active — H163 CONFIRMED (FinBERT NLP); H161/H162 PARTIAL CONFIRMED; H168 IN-PROGRESS
---

# Event-Driven Trading Strategies

Systematic exploitation of price drifts triggered by discrete corporate events: earnings releases, dividend announcements, guidance changes, index additions. The edge comes from persistent *under-reaction* — prices adjust slowly, not instantly.

**Related pages**: [Options Income Strategies](options-income-strategies.md) — H162 covered-call ex-div | [Hypothesis Log](../backtesting/hypothesis-log.md) | [Momentum Strategies](momentum-strategies.md) | [NLP & Alternative Data](../tools/nlp-alternative-data.md) | [Machine Learning for Trading](../tools/ml-for-trading.md)

---

## Why Events Create Edge

Markets are not perfectly efficient around events because:
1. **Investor inattention**: many participants don't monitor every earnings release
2. **Uncertainty about persistence**: earnings beats may be one-off; market waits for confirmation
3. **Limits to arbitrage**: event positions are idiosyncratic, cannot be easily hedged by fast capital

Classic academic anchor: Ball & Brown (1968) showed prices drift for weeks after earnings. Still replicable 50+ years later (though smaller and faster-decaying).

---

## Strategy 1: Post-Earnings Announcement Drift (PEAD)

### Academic Foundation

**Jegadeesh-Titman** (earnings version), **Bernard & Thomas (1989)**: stocks in the top earnings surprise decile (SUE Q5) outperform bottom decile (SUE Q1) by 5–8% over the following 60 days.

Recent evidence:
- Long Q5/Short Q1 hedge portfolio: 5.1% risk-adjusted return over 3 months (~20% annualized) — *Quantpedia (2024)*
- ML with elastic-net over multi-quarter SUE history nearly doubles Sharpe vs simple SUE ranking
- FinBERT on earnings call transcripts achieves 57–58% accuracy for post-announcement direction
- **PEAD.txt** (Meursault et al., *JFQA* 2022): text-based SUE from transcripts earns **3.9bp daily alpha** vs 2.6bp for price-based SUE (+50% stronger); 1-SD text surprise → 3–6% of SD in 63-day CAR
- **H163 CONFIRMED** (2026-05-05): FinBERT on SEC 8-K press releases achieves OOS WR ≥ 68% (+10pp vs baseline 57.6%), MeanRet ≥ 5.5% (+2×); validates NLP filtering for PEAD
- **Independent validation (ICAIF 2025)**: arXiv:2509.24254 (138,000+ earnings press releases, 2005-2023) confirms that soft information from earnings press releases explains announcement-day returns as well as earnings surprises. FinBERT contextual embeddings outperform LDA bag-of-words. Directly corroborates H163/H174 confirmed results — the 8-K FinBERT signal is well-grounded in the academic literature.

### PEAD.txt — Text-Based Earnings Surprise (JFQA 2022)

Meursault, Liang, Routledge & Scanlon (2022, *JFQA*) construct SUE.txt from earnings call transcripts — a text-based earnings surprise measure. Key results (2010–2019 sample):
- SUE.txt spread portfolio earns **3.9bp daily alpha** vs 2.6bp for traditional price-based SUE (+50% stronger)
- 1-SD increase in text surprise → 3–6% of SD increase in 63-day CAR
- Text signal and price signal are complementary — combining both > either alone

This is the academic anchor for H168. Text from earnings disclosures carries more predictive information than gap-up price action alone.

**QuantPedia BLMECT design parameters** (highest-performing NLP-PEAD variant, 2025):
- **Sentiment surprise** = current_sentiment − mean(last 4 quarters) — stronger than absolute level
- Tercile sorting (top/bottom 33%) outperforms quintile/decile splitting
- 4-quarter baseline lookback optimal (vs. 8, 12, 20)
- 4-week holding period
- Universe: 500 most liquid stocks, price ≥ $5

H168 v2 design note: test `finbert_surprise = weighted_score_t − mean(weighted_score_{t-4q..t-1q})` alongside absolute score.

### Signal Construction

**SUE (Standardized Unexpected Earnings)**:
```
SUE = (actual_EPS - expected_EPS) / std_dev(surprise_series)
```
Expected EPS = seasonal random walk with drift (prior 8 quarters), OR analyst consensus estimate.

**EAR (Earnings Announcement Return)**:
Abnormal return in 3-day window `[-1, +1]` around announcement, adjusted for market factor.

**Combined signal** (strongest in practice):
- Long: top decile by BOTH SUE and EAR
- Short: bottom decile by BOTH
- 12.5% annual abnormal return in backtests (Bernard & Thomas)

**Gap entry variant** (H159 implementation):
- Trigger: open/prev_close gap ≥ +5% on earnings day
- Enter at market open, hold N days
- Avoids needing analyst EPS estimates (observable from price action alone)

H159 OOS findings (2018–2026):
- Raw event effect: n=374, mean 20-day return = +4.39%, win rate 63.9%, t-stat = 5.64 → **confirmed effect**
- Unhedged portfolio: MaxDD −43 to −58%, Sharpe 0.06–0.44 → **fails as standalone** (market beta kills it in 2020, 2022 crashes)

### Why Unhedged PEAD Fails

Long-only PEAD holds ~30 simultaneous positions at all times, all long equity, all correlated with SPY. In a bear market all 30 positions crash together. The event alpha is real but drowned by beta.

### Beta-Neutral PEAD: H159b — NOT CONFIRMED

Pair each PEAD long with a proportional SPY short:
```
position_spy_short = rolling_60d_beta(stock, SPY) × position_size
```

**H159b OOS results** (best of 4 variants — gap>5%, n=15, hold=20d):
- OOS Sharpe = 0.382, MaxDD = −48.68%, NegYrs = 3
- Beta hedge achieved Corr(SPY) = −0.05 to −0.11 (was 0.59–0.67) ✓
- MaxDD still −48–54% — far above −20% threshold ✗

**Why it still fails**: beta hedging removes market correlation but cannot hedge idiosyncratic risk. Gap-up stocks collapse 50%+ for company-specific reasons unrelated to SPY. The IS/OOS gap (IS Sharpe 1.6 → OOS 0.38) confirms PEAD structural decay post-2018: HFT/algos arbitrage the drift faster than 30-stock equal-weight can exploit.

**Rolling beta calculation** (statsmodels):
```python
from statsmodels.regression.rolling import RollingOLS
import pandas as pd, numpy as np

def rolling_beta(stock_ret, spy_ret, window=60):
    df = pd.DataFrame({'y': stock_ret, 'x': spy_ret}).dropna()
    model = RollingOLS(df['y'], sm.add_constant(df['x']), window=window)
    result = model.fit()
    return result.params['x']  # beta series
```

**Remaining PEAD improvement paths**:
- H163 — FinBERT NLP filter (raise win rate above 64% via transcript sentiment; currently running)
- H164 — ElasticNet 8-quarter SUE history: NOT CONFIRMED (data blocker: FMP v3 deprecated, only 4yr history via yfinance; model collapses to near-zero coefficients)
- H168 — Speaker-weighted FinBERT (analyst Q&A weighted 49%, CFO 30%): QUEUED after H163

### Data Sources for PEAD

| Source | What you get | Cost | Python |
|--------|-------------|------|--------|
| **yfinance** | Earnings dates (approx), EPS actual | Free | `yf.Ticker('AAPL').earnings_dates` |
| **Finnhub** | Earnings calendar, EPS estimate + actual | Free 60 req/min | `GET /calendar/earnings?from=&to=` |
| **FMP** (Financial Modeling Prep) | Historical EPS surprises, SUE-ready data | Free 250 req/day | `GET /v3/earnings-surprises/{symbol}` |
| **Alpaca** | `GET /v1beta1/screener/stocks/most-actives` + corporate events | Free | alpaca-py |
| **EDGAR** | 10-Q/10-K actual EPS | Free | `python-edgar`, direct SEC XBRL API |

```python
# Finnhub earnings calendar
import requests, os
API_KEY = os.getenv("FINNHUB_API_KEY")  # use $NEWSAPI_KEY fallback for non-Finnhub

resp = requests.get(
    "https://finnhub.io/api/v1/calendar/earnings",
    params={"from": "2024-01-01", "to": "2024-03-31", "token": API_KEY}
)
events = resp.json()["earningsCalendar"]
# Fields: date, symbol, epsEstimate, epsActual, revenueEstimate, revenueActual
```

```python
# yfinance — get next earnings date and historical surprises
import yfinance as yf
t = yf.Ticker("AAPL")
print(t.earnings_dates.head(8))          # historical announcement dates
print(t.earnings_history)               # actual vs estimate history
```

---

## Strategy 2: Dividend Announcement Drift

### Academic Foundation

- **DRAD (Dividend Raise Announcement Drift)**: Firms announcing dividend increases of ≥10% show +1.39% AAR on announcement day (Warsaw 2024 study across 395 events, 2015–2024)
- Post-announcement: price holds and drifts slightly further positive for ~20 days
- Dividend decreases show persistent negative drift (−2.97% by day +16) — asymmetric
- Signal is stronger for first-ever dividend / unexpected large raises

**H161 result (PARTIAL CONFIRMED)**: Enter at close of announcement day, hold 40 days. OOS (2018–2026): n=499, WR=59.1%, MeanRet=1.97%, t=4.10 (p<0.0001). Portfolio OOS Sharpe=4.298, MaxDD=−18.06%, Corr(SPY)=0.001. Criteria: 3/3. Key caveat: Sharpe inflated by exit-day P&L model (true Sharpe ~1–2); IS (2007–2017) fails due to GFC. Signal fires frequently for dividend aristocrats (≈6.6 raises/stock/year).

### Signal Construction

```python
# Detect dividend increases ≥10%
import yfinance as yf, pandas as pd

def get_dividend_raises(ticker, min_pct=0.10):
    t = yf.Ticker(ticker)
    divs = t.dividends
    if len(divs) < 2:
        return pd.Series(dtype=float)
    pct_change = divs.pct_change()
    raises = pct_change[pct_change >= min_pct]
    return raises
```

For systematic scanning, use FMP's dividend calendar:
```python
# FMP dividend calendar — upcoming ex-dates
resp = requests.get(
    f"https://financialmodelingprep.com/api/v3/stock_dividend_calendar",
    params={"from": "2024-01-01", "to": "2024-01-31",
            "apikey": os.getenv("FMP_API_KEY")}
)
```

### Ex-Dividend Price Anomaly

Price typically drops by approximately the dividend amount on ex-date. Mean reversion / arbitrage opportunities:
- Day before ex-date: small positive bias (dividend capture buyers)
- Ex-date: mechanical drop, then recovery if yield-seekers re-enter
- **H162 implementation**: sell covered call 10 days before ex-date (collected premium + dividend — risk = early assignment)

**H162 result (PARTIAL CONFIRMED)**: Universe: 50 large-cap dividend payers, 3509 quarterly ex-date events. OOS: WR=68.3%, MeanRet=0.62%, t=6.47. Portfolio OOS Sharpe=2.015, MaxDD=−16.17%, Corr(SPY)=0.167. vs. JEPI ETF: 2.015 vs 1.047 Sharpe (1.9×). Key caveats: (1) call leg loses money OOS (MeanRet=−0.14%, t=−1.92) — no IV risk premium; (2) true driver is stock drift before ex-dates (stock-only OOS MeanRet=0.76%, covered call reduces to 0.62%); (3) BS+HV proxy only — real bid-ask on short-dated options eats 0.2–0.4%. Strategy is "stock drift with a premium cushion," not an options income play.

---

## Market-Neutral Portfolio Construction

### Core Principle

Event portfolios suffer from market beta. Fix: hedge each long with a proportional short.

**Three approaches** (increasing complexity):

| Method | Hedge | Complexity | Residual risk |
|--------|-------|------------|---------------|
| Market-neutral | Short SPY proportional to β | Low | Sector, idiosyncratic |
| Sector-neutral | Short sector ETF (e.g. XLK) | Medium | Idiosyncratic |
| Factor-neutral | Short SPY + sector + size | High | Pure event alpha |

### Rolling Beta Hedge (practical implementation)

```python
import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
import statsmodels.api as sm

def compute_rolling_beta(asset_ret, mkt_ret, window=60):
    """60-day rolling OLS beta. Returns series aligned to asset_ret.index."""
    betas = pd.Series(index=asset_ret.index, dtype=float)
    for i in range(window, len(asset_ret)):
        y = asset_ret.iloc[i-window:i].values
        x = sm.add_constant(mkt_ret.iloc[i-window:i].values)
        try:
            b = OLS(y, x).fit().params[1]
        except Exception:
            b = 1.0
        betas.iloc[i] = b
    return betas.fillna(1.0)

def beta_neutral_return(long_ret, spy_ret, beta_at_entry):
    """
    long_ret: series of daily returns for the long leg
    spy_ret: SPY daily returns over same period
    beta_at_entry: scalar beta computed just before trade entry
    Returns: market-neutral return series
    """
    hedged = long_ret - beta_at_entry * spy_ret
    return hedged
```

### Position Sizing in an Event Portfolio

- Cap individual positions at 5% of portfolio (max 20 simultaneous events)
- Scale by signal strength: `weight ∝ abs(SUE) / sum(abs(SUE))`
- Equal-weight is competitive in practice (low signal-to-noise)

---

## Implementation Checklist

### Pre-trade
- [ ] Confirm earnings/event date is NOT estimated — use actual filing timestamp
- [ ] Filter: exclude stocks with options expiry within 3 days (IV crush noise)
- [ ] Check liquidity: avg daily volume ≥ 500k shares
- [ ] Compute rolling 60-day beta vs SPY before event

### Entry
- [ ] Gap trades: enter at market open on event day
- [ ] SUE trades: enter at close of event day (2-day delay avoids gap noise)
- [ ] Record SPY price at entry for hedge ratio

### During hold
- [ ] Monitor for secondary events (guidance revision, index rebalance) that invalidate the drift thesis

### Exit
- [ ] Hard exit at N days (10, 20, or 40 depending on strategy variant)
- [ ] Softer: exit if position returns >2× expected α (early profit-taking)

---

## Common Pitfalls

**Look-ahead bias**: earnings announcement times (before/after market) matter. A "same-day" entry using closing price on announcement day has look-ahead if announcement came after close. Use `yf.Ticker().earnings_dates` — it includes time where available.

**Survivorship bias**: backtesting on stocks still listed today inflates returns. Use point-in-time constituent lists (Compustat, CRSP) for production-grade tests.

**Transaction costs**: PEAD requires frequent entry/exit of 20–30 positions. At 0.1% RT cost, high-frequency rebalancing (~monthly turnover of 100%) costs ~1.2% annually — manageable if net alpha is 4–6%.

**Earnings date uncertainty**: some providers return estimated dates (±3 days). This can cause entry on wrong day. Finnhub and FMP are more reliable than yfinance for event timestamps.

---

## Hypothesis Status Summary

| H# | Strategy | Status | OOS Sharpe | Key Finding |
|----|----------|--------|-----------|-------------|
| H159 | PEAD — gap entry, unhedged | PARTIAL | 0.44 | Effect real (t=5.64) but beta kills portfolio |
| H159b | PEAD — beta-neutral (rolling 60d OLS) | NOT CONFIRMED | 0.382 | Beta hedge works (Corr→0) but idiosyncratic risk still −49% DD |
| H161 | Dividend raise ≥10% → enter close, hold 40d | PARTIAL CONFIRMED | 4.298* | Strong OOS signal (t=4.10); *Sharpe inflated by exit-day model |
| H162 | Covered calls 10d before ex-div | PARTIAL CONFIRMED | 2.015* | Stock drift is true driver; call leg loses OOS; *exit-day Sharpe inflation |
| H163 | PEAD + FinBERT filter | **CONFIRMED** | — | OOS WR ≥68% (+10pp vs baseline 57.6%), MeanRet ≥5.5% (+2×); first NLP PEAD confirmation |
| H164 | PEAD + ElasticNet 8-quarter SUE | NOT CONFIRMED | — | FMP v3 deprecated; 4yr IS insufficient for model training |
| H168 | PEAD + speaker-weighted FinBERT (AV transcripts) | IN-PROGRESS | — | Transcript download ongoing (25/day AV limit); GAP=0.03, ~203 events |
| H171 | PEAD + GPT-4o-mini earnings sentiment (H168 variant) | QUEUED | — | $0.48 total cost; shares H168 transcript cache; queue after H168 |

---

## Further Reading

- Bernard & Thomas (1989) — "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?" *JAE*
- Jegadeesh & Titman (1993) — "Returns to Buying Winners and Selling Losers" *JF*
- Sloan (1996) — accruals anomaly (related: accrual-based earnings quality signal)
- Quantpedia: [Post-Earnings Announcement Effect](https://quantpedia.com/strategies/post-earnings-announcement-effect)
- CFA Institute (2025): "Can Generative AI Disrupt PEAD?"
- ACL 2025: "Enhancing PEAD Measurement with Large Language Models" (FinBERT achieves 57.6–58.3%)

---

## H165 Design Caution — LLM Market Timing (KDD 2026 Finding)

KDD 2026 paper (arXiv:2505.07078, Li et al.) ran FINSABER backtest across 20 years and 100+ symbols: LLM-based timing strategies **do NOT outperform passive benchmarks** in the long run. Failure modes: overly conservative in bull markets (underperforms passive), overly aggressive in bear markets (incurs heavy losses).

**Implication for H165 (TradingAgents):** Do NOT use TradingAgents as a standalone market timer generating direct buy/sell signals. Use only as a **regime gate** — an additional confirmation layer that blocks entries during macro bear regimes (e.g., when LLM + macro data agrees recession is likely, exit H026 to BIL faster than 12m TSMOM alone).

The paper recommends: 'focus on trend detection and regime-aware risk controls over mere scaling of framework complexity.' H026's TSMOM filter already provides trend detection; TradingAgents should augment it with macro regime awareness, not replace it.

**Benchmark before committing API costs**: test a simple VIX threshold (VIX > 30 → BIL) first. If VIX alone achieves the same regime protection as TradingAgents, the LLM layer adds complexity without benefit.

---

## Supporting Literature: Press Release Section Extraction

**arXiv:2509.24254** — *Extracting the Structure of Press Releases for Predicting Earnings Announcement Returns* (Spinos et al., Oct 2025)

Key findings directly relevant to H175 (sec-parser press release section extraction):

1. **Soft information is as predictive as hard surprises**: The textual content of earnings press releases explains abnormal returns comparably to earnings beat/miss magnitude. This validates the H175/H163 approach of using NLP on press releases directly.

2. **FinBERT > LDA for structured extraction**: FinBERT embeddings outperform LDA topic modeling for extracting return-predictive signals from press releases. Confirms FinBERT as the right scorer (already our approach in H163/H174).

3. **Section structure matters**: Predictive power varies by section. Guidance/outlook paragraphs and management commentary sections carry more signal than boilerplate financial tables. The paper's section classification maps well to the sec-parser extraction structure.

4. **Section-level sentiment > full-document sentiment**: Scoring individual sections (outlook, summary, highlights) and weighting them outperforms whole-document scoring. This is the H175 hypothesis: apply FinBERT to *specific sections* extracted by sec-parser rather than the full 8-K text.

**Implementation note for H175**: Target these sections in order of signal strength:
- Forward-looking statements / guidance
- Management summary / key highlights  
- Q&A discussion summary (if included in press release)
- Financial results narrative (above tables)
- Exclude: raw financial tables, boilerplate legal disclaimers

---

## Text-Based Earnings Surprise (PEAD.txt)

**Source**: Bochkay, Hales & Chava (2023). "PEAD.txt: Post-Earnings-Announcement Drift Using Text." *Journal of Financial and Quantitative Analysis*.

Classic PEAD uses standardized unexpected earnings (SUE = reported EPS − consensus / std). **PEAD.txt** constructs an analogous surprise measure from the *text* of earnings calls:

- **SUE.txt**: sentiment change in earnings call transcript vs prior quarter transcript, scored via FinBERT
- Generates *larger* PEAD than numeric SUE — especially for firms with low analyst coverage (less efficient pricing of soft information)
- Combining numeric SUE + SUE.txt further improves signal

**Application to H163/H174**: Current pipeline uses FinBERT on 8-K press releases with gap filter. Upgrade path (H195):
1. Download earnings call transcripts (AlphaVantage or Seeking Alpha)
2. Compute SUE.txt = (current quarter FinBERT score) − (prior quarter FinBERT score)
3. Add SUE.txt as second filter alongside existing 8-K gap filter
4. Expected improvement: higher OOS win rate for low-analyst-coverage stocks

See also: arXiv:2509.24254 — press release *structure* (section-level FinBERT on intro, highlights, guidance sections) as informative as earnings surprise.

---

## Multi-Agent LLM Architecture: Fine-Grained Task Decomposition

**Source**: arXiv:2602.23330 (Feb 2026). "Toward Expert Investment Teams: A Multi-Agent LLM System with Fine-Grained Trading Tasks."

Key finding: **specialist agents > generalist agents** for investment decisions. Decomposing analysis into fine-grained subtasks (sentiment analysis, numerical fundamentals, macro context, risk assessment) significantly outperforms monolithic LLM or coarse analyst/trader split. Critical driver is *alignment* between agent outputs and the decision-maker's preference structure — not raw model capability.

**Architecture pattern**:
```
DataIngestion → SpecialistTeam → DecisionSynthesis → Execution
     ↓               ↓ ↓ ↓            ↓
  earnings      sentiment   momentum   risk
  transcripts   agent       agent      agent
  10-K/10-Q              ↘  ↓  ↗
                       Portfolio Manager
                       (trades on consensus)
```

**Contrast with PolySwarm (2_polyswarm_kalshi_h185.json)**: PolySwarm uses 50 heterogeneous personas voting on a single question. This paper uses ~5 specialist agents each focused on a distinct data modality. For structured financial signals, the specialist approach may be more reliable; for prediction market questions, the persona diversity approach may be better.

**Application to H171**: Current H171 design uses a single FinBERT+GPT-4o pipeline on 8-Ks. Upgrade path: add separate fundamental-analysis agent (numeric EPS/revenue surprise), separate macro-context agent (sector rotation, rates), separate risk agent (VIX, beta), and synthesize with a Portfolio Manager agent. Expected benefit: better signal quality on edge cases (guidance beats beat but tone negative).

---

## LLM Pitfall Checklist for PEAD Pipeline (H163/H174)

**Source**: arXiv:2605.05211 (Zhang & Zhang, 2026). "A Review of Large Language Models for Stock Price Forecasting from a Hedge-Fund Perspective." IEEE CAI 2026.

Six failure modes to audit before deploying any LLM-based signal live:

| # | Pitfall | H163/H174 Status | Action |
|---|---------|-----------------|--------|
| 1 | Sentiment fragility to prompt phrasing | **Unknown** — FinBERT is fixed-weight, not prompted, so less fragile than GPT-based | Test FinBERT score stability across small 8-K paraphrase variants |
| 2 | Horizon mismatch (trained on daily, deployed at open) | **Managed** — OPG orders capture same-day gap | Confirm FinBERT was trained on press-release-length texts, not summaries |
| 3 | Data leakage from pre-training corpus | **Risk** — FinBERT trained on pre-2023 financial news; 8-Ks from 2022-2024 may appear in training data | Use post-2024 OOS results as primary performance metric |
| 4 | Illiquidity premia mis-attribution | **Partial risk** — small-cap PEAD stocks are illiquid; paper results may not survive execution | Add $2B+ market cap filter; verify live paper fills vs backtest |
| 5 | Evaluation without transaction costs | **Managed** — H174 backtest includes 5 bps per side slippage | Re-run with 15 bps to stress-test |
| 6 | R² ceiling — returns are ~1% predictable; LLM adds ~0.1% | **Acceptable** — PEAD exploits event-driven gap, not return level prediction | |

**Priority actions**:
1. Apply $2B+ market cap filter to watchlist screener
2. Compute FinBERT score variance on 10 paraphrases of a typical 8-K press release opening paragraph
3. Re-run H174 backtest from 2024-01-01 onward (post-training data leakage cutoff)

## FinNLP 2025 — LLM-Enhanced PEAD (Hadlock, Roberts & Lee)

Hadlock, Roberts & Lee (2025). 'Enhancing Post Earnings Announcement Drift Measurement with Large Language Models.' *FinNLP Workshop 2025*, ACL Anthology 2025.finnlp-2.13. Suzhou, China, November 2025.

Directly relevant to H163/H174 confirmed pipeline. Proposes LLM-based enhancement of PEAD measurement (the drift signal itself) beyond FinBERT sentiment scoring. Unlike H168 (transcript availability bias) and H171 (GPT on transcripts), this paper targets 8-K press releases — same source as H163, which has 100% EDGAR coverage.

**Implication for research queue**: Candidate H176 — replace H163 FinBERT sentiment score with LLM-enhanced measurement from Hadlock 2025 method on same 8-K corpus. Compare OOS WR and MeanRet vs H174 confirmed baseline (score≥0.18, WR=80.8%, MeanRet=6.22%). Low implementation risk since EDGAR coverage is already solved.

**Priority**: MEDIUM — H174 confirmed baseline is already strong (WR 80.8%); LLM enhancement would need to show measurable lift. Queue after H206/H202-XL.

---

### Press Release Structure Features (H174 enhancement candidate)

**Reference**: arXiv:2509.24254 (Sep 2025), 138k press releases 2005-2023

Structural features of 8-K press releases that predict announcement-day returns beyond pure FinBERT sentiment:

```python
def extract_press_release_features(text: str) -> dict:
    """Extract structural features predictive of announcement return."""
    lines = text.split('\n')
    return {
        'has_guidance_section': any('guidance' in l.lower() or 'outlook' in l.lower() for l in lines),
        'has_non_gaap_tables': 'non-gaap' in text.lower() or 'adjusted' in text.lower(),
        'forward_looking_ratio': sum(1 for l in lines if any(w in l.lower() for w in ['expect', 'forecast', 'anticipate', 'project'])) / max(len(lines), 1),
        'paragraph_count': text.count('\n\n'),
        'numeric_density': sum(c.isdigit() for c in text) / max(len(text), 1),
    }
```

**Integration with H174**: add these features as a 3rd filter gate (after FinBERT score and EPS surprise). Papers find: presence of forward guidance and non-GAAP table emphasis predicts stronger positive drift; absence of guidance → neutral or negative drift regardless of headline EPS surprise.

---

### Earnings Call Transcript Analysis — H174 Enhancement Candidate (PEAD.txt)

**Reference**: FinNLP 2025 Workshop (ACL), Hadlock, Roberts & Lee  
**Finding**: Text-based PEAD from earnings call transcripts (PEAD.txt) maintains meaningful alpha even as numeric PEAD (EPS surprise) has attenuated. FinBERT classification accuracy: 57.6–58.3% on directional PEAD signal from transcripts.

**Incremental information sources in earnings calls (not in 8-K press releases)**:
- CEO/CFO tone and hedging language ('we expect', 'we are cautious about' vs. 'we are confident in')
- Guidance precision — vague guidance → negative drift; specific quantitative guidance → positive drift
- Analyst Q&A section — pushback from analysts is a strong negative signal
- Management responsiveness — deflecting vs. directly answering questions correlates with subsequent drift

**Implementation path**:
```python
# Current H174 pipeline (8-K only)
score_8k = finbert_score(fetch_8k_item202(ticker))

# Proposed H174+ pipeline (8-K + transcript)
from sec_edgar_downloader import Downloader
# Fetch 8-K first
score_8k = finbert_score(fetch_8k_item202(ticker))
# Then fetch earnings call transcript (Item 9.01 attachments or Seeking Alpha)
transcript = fetch_earnings_transcript(ticker, date)  # via scraped source
score_transcript = finbert_score(transcript[:2048])   # score first 2048 tokens
# Composite: weight 8-K 60%, transcript 40%
composite_score = 0.60 * score_8k + 0.40 * score_transcript
```

**Free transcript sources**: Motley Fool (scraped), Seeking Alpha (requires subscription), SEC EDGAR 8-K Item 9.01 exhibits (some transcripts filed there), Earnings Whispers, stockanalysis.com  
**Caution**: Transcript availability lag — transcripts often posted 2–4 hours after earnings call, which may be after market open. 8-K is usually immediate. The benefit is incremental (57.6% vs. baseline FinBERT 57–58% on 8-K), not transformative.


### SUE.txt — LLM-Derived Earnings Surprise Signal (H174 Enhancement Candidate)

**Source**: ACL FinnLP Workshop 2025 — "Enhancing Post Earnings Announcement Drift Measurement with Large Language Models"

Classical PEAD uses **numeric SUE** (Standardized Unexpected Earnings = (actual EPS − consensus EPS) / std dev of prior forecast errors). This paper shows **text-based SUE (SUE.txt)** — derived from LLM extraction of earnings disclosures — produces a stronger PEAD signal than numeric SUE alone.

**Mechanism**: LLM reads earnings press release or transcript, identifies specific language about:
- Forward guidance vs. prior quarter language
- Management surprise/confidence markers
- Revenue quality commentary (recurring vs. one-time items)
- Analyst Q&A sentiment

Generates a contextual surprise score that captures *what management says* about the numbers, not just the numbers themselves. Outperforms numeric SUE in PEAD magnitude.

**H174 application** — our current pipeline computes:
```python
# Current (pead_overnight.py)
sentiment_score = finbert(earnings_text)  # press release sentiment
surprise = score - prior_4q_mean         # vs. prior quarter baseline
```

**Proposed upgrade** — add SUE.txt as a second signal:
```python
# Proposed: composite PEAD signal
eps_surprise_pct = (actual_eps - consensus_eps) / abs(consensus_eps)  # from FMP API
finbert_surprise  = finbert(press_release_text) - prior_finbert_mean  # current method
sue_txt           = llm_extract_surprise(full_release_text)           # new: LLM contextual

# Composite: weight by out-of-sample correlation
composite = 0.4 * eps_surprise_pct + 0.4 * finbert_surprise + 0.2 * sue_txt
```

**Prerequisites**: FMP API for numeric EPS surprise (already have $FMP_API_KEY); LLM call (already have $OPENAI_API_KEY via proxy). Low implementation cost — add ~20 lines to pead_overnight.py.

**Expected lift**: Paper reports SUE.txt > numeric SUE in PEAD magnitude. Combined signal likely improves signal-to-noise vs. either alone. Hypothesis: composite win-rate improves from current 81.8% toward 85%+.

**Priority**: MEDIUM — queue after current live trading proves stable; test on holdout set first.


## H225 Candidate — LLM-Upgraded PEAD Signal (ACL FinNLP 2025)

**Source:** "Enhancing Post Earnings Announcement Drift Measurement with Large Language Models" (ACL FinNLP 2025 workshop)

**Key finding:** Press release text (soft information) is as informative as EPS surprise (hard information) for predicting post-announcement drift. FinBERT achieves 57.6-58.3% directional accuracy across 138,000 press releases (2005-2023). GPT-4 class models outperform FinBERT on nuanced soft information extraction.

**H225 Design:**
- Replace H174's FinBERT scoring (`ProsusAI/finbert`) with OpenAI GPT-4o-mini scoring of earnings press releases
- Signal: LLM scores the full 8-K Item 2.02 text for earnings quality on [-1, +1] scale
- Keep H174's dual filter: LLM_score ≥ 0.18 AND EPS_surprise ≥ 0.02
- Baseline: H174 OOS WR=81.8%, MeanRet=6.89%, n=22
- Cost: ~$0.002 per press release (GPT-4o-mini input pricing) — ~$0.20/year for 100 earnings events
- Confirm: OOS WR > 83% or MeanRet > 7.5% (meaningful improvement over H174)

**Implementation note:** pead_overnight.py already downloads and scores 8-K text. Replace the `score_document()` FinBERT call with `openai.chat.completions.create()` call with a structured prompt asking for directional earnings quality score. `$OPENAI_API_KEY` is available in env.

**Reference:** ACL Anthology 2025.finnlp-2.13
