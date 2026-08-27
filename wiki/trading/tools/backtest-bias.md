---
title: backtest-bias — Automated Survivorship & Integrity Checks for Price Panels
added: 2026-08-27
category: tools
url: https://github.com/Finance-broski/backtest-bias
---

# backtest-bias

**PyPI**: `backtest-bias` (`pip install backtest-bias`) · **GitHub**: [Finance-broski/backtest-bias](https://github.com/Finance-broski/backtest-bias) · **Latest**: v0.2.0 (Aug 2026) · **License**: MIT · **Author**: Ayan Jain (financebroski.com) · **Stars**: 11 (small, single-author, but legitimate — Zenodo-DOI'd, `CITATION.cff`, active commits through 2026-08-27, zero open issues)

One-line pitch: "Checks whether your backtest data is lying to you" — a small, focused library that runs automated integrity checks on a price panel (survivorship, ticker-identity continuity, universe-membership look-ahead) and returns a severity verdict plus a *measured* bias-magnitude estimate, rather than just a boolean pass/fail.

## Why this is relevant here

`backtesting/survivorship-bias.md` already documents the mechanism and manual mitigation (fja05680/sp500 CSV, point-in-time universe builder, delisting-return substitution) in depth, but the wiki has no automated *checker* — every H24x-family verdict about survivorship exposure has been argued qualitatively ("large caps rarely delist mid-index") rather than measured against the actual price panel in code. `backtest-bias` fills exactly that gap: run it against `data/sp500_historical_components.csv`-derived panels or any H-series price cache and get a quantified severity call instead of a prose argument.

It's also a closer structural match than it first appears to this project's own worst-documented bug class. The H509–H514 corrections (OB filter `as_of` date bug, PEAD `skip=0` signal-endpoint bug) are exactly the "point-in-time violation" category this library's v0.2 roadmap targets — see Roadmap below — even though that specific check isn't shipped yet.

## What ships today (v0.1 + v0.2)

| Function | Question it answers |
|---|---|
| `check_survivorship(prices)` | Does the universe contain names that died during the window, or only winners? Returns a full report: death count, severity classification, and a *measured* bias estimate in Sharpe/return-pp terms. |
| `dead_name_ratio(prices)` | Single number: fraction of names in the panel that end before the panel does. `0.0` = pure survivor-only panel — a red flag by itself. |
| `assert_integrity(prices)` | CI-gate style: raises an exception if the panel smells survivor-only, so a silent bad re-download fails a pipeline loudly instead of quietly flattering a backtest. |
| `check_identity(prices)` **(v0.2)** | Detects recycled tickers — a dead company's price history silently stitched to a new, unrelated listing that reused the same symbol. The author's own measurement: 4 such recycled tickers moved a US backtest result by **1.7 pp/yr**, more than the survivorship bias itself in that case. |
| `check_universe(prices, universe, start)` **(v0.2)** | Detects two signatures of "today's constituent list applied backwards": (1) members whose price data begins suspiciously close to or after the backtest start date, and (2) a universe where start-alive names almost never die when historical death-rate curves say they should. |

```python
import pandas as pd
from backtest_bias import check_survivorship, check_identity, check_universe

prices = pd.read_csv("h241_universe_prices.csv")  # wide (date x symbols) or long (date/symbol/close)
report = check_survivorship(prices)
print(report.summary())
# survivorship check: 195 symbols over 13.1y, 0 died in-window (0%)
# verdict: SEVERE - 195 names over 13.1y with zero deaths is the survivor-only signature;
# comparable universes lose 22%-28% of names over 9y (measured)
# expect EW returns inflated roughly +0.8-3.2 pp/yr vs an honest universe (measured, vintage-dependent)

print(check_identity(prices).summary())
print(check_universe(prices, universe=my_symbols, start="2013-01-01").summary())
```

Input handling: accepts wide or long panels, sniffs column names, tolerates NaN-padded histories; raises rather than silently guessing when it can't judge.

## Measured constants the library is built on

The author (Ayan Jain, an independent backtest auditor who runs a public "155 strategies tested, 143 killed" graveyard at financebroski.com) publishes the specific numbers behind each check in [`BIAS_TABLE.md`](https://github.com/Finance-broski/backtest-bias/blob/main/BIAS_TABLE.md):

- **24%** of the top-500 Indian stocks (as of 2015) are invisible to yfinance today (delisted/merged/renamed with no public mapping) — a universe built from current listings runs on survivors only.
- Survivor-only universes inflated equal-weight returns by **+0.8 to +3.2 pp/yr** depending on universe vintage (Indian equities, measured).
- Index-membership look-ahead added **+10% terminal wealth (cap-weighted)** and **+43% (equal-weighted)** over 2010–2021 on the widely-used Kaggle NSE dataset.
- Death-rate curve (top-500 vintages, 2012–2022): **~5–8% dead by 3yr, 11–14% by 5yr, 17–21% by 7yr, 24–30% by 10yr.** A panel with materially fewer deaths than this curve for its window length is very likely survivor-contaminated.
- US-market constants (added in v0.2): survivor-filter effect **+0.4 to +1.0 pp/yr** by vintage; yearly gaps swinging **-7.5 to +3.5 pp**; the ticker-recycling identity error **1.7 pp/yr**.

These US numbers are directly comparable in kind to `survivorship-bias.md`'s own cited constants (Ranse 2025 NIFTY Smallcap: +4.94pp/+0.097 Sharpe; Daniel/Sornette/Wohrmann: 8%/yr S&P 500 look-ahead) — same phenomenon, independently measured on a different market, same order of magnitude.

## Roadmap (not yet shipped — v0.3 and beyond)

The README explicitly lists upcoming checks: **fundamentals dated by period instead of announcement date**, **index membership applied backwards**, and **same-bar signal fills** — i.e. the exact `as_of`-date look-ahead bug class this project's own H509–H514 corrections found by hand across the OB/FVG filter family. Worth re-checking this package in a future wiki pass once v0.3 ships; it could become a mechanical first-pass check to run before any new hypothesis backtest, ahead of manual `as_of` audits.

## Limitations / honest caveats

- Very small project: 11 GitHub stars, single author, created July 2026 — legitimate (MIT, Zenodo DOI, `CITATION.cff`, no hallusquatting red flags — package name matches repo purpose exactly, author has a public track record and consistent identity across PyPI/GitHub/LinkedIn/Substack) but young and unlikely to have wide community vetting yet.
- Core measured constants come from **Indian equity markets** (NSE/BSE); the US-market numbers are newer (v0.2) and thinner (fewer measured vintages cited).
- Does not replace the manual point-in-time universe construction already documented in `survivorship-bias.md` — it's a *check*, not a data source. You still need `fja05680/sp500` or Norgate/Sharadar/CRSP for the actual point-in-time constituent list.
- Per this project's standing package-installation security policy, this has **not** been installed — this is a research/reference entry only. Before any actual `pip install backtest-bias`, follow the standard verification steps (PyPI/`pip index versions` check — done here — plus `pip-audit` after install) and note it is not yet "already in the venv or explicitly approved."

## Verdict

Legitimate, narrow, well-documented small tool. Directly fills a gap in `survivorship-bias.md` (mechanism + manual fix, but no automated check) and is thematically close to the biggest recurring bug class in this project's own hypothesis-log (H509–H514 as-of-date look-ahead). Not urgent to install today, but worth flagging as a candidate pre-backtest CI gate — either now for the survivorship checks that already ship, or once v0.3's look-ahead/point-in-time checks land.

## Related Wiki Pages

- [Survivorship Bias & Universe Construction](../backtesting/survivorship-bias.md) — mechanism, manual PIT universe builder, H241–H246 exposure assessment; this page's natural complement
- [Point-in-Time Constituent & Vintage Data Sources](../data-sources/point-in-time-constituents.md) — provider comparison for the actual PIT data this tool would audit
- [Look-Ahead Freedom — Formal Verification](../backtesting/lookahead-formal-verification.md) — arXiv:2607.04958 type-system approach to the same class of bug, at the code level rather than the data-panel level
- [Hypothesis Log](../backtesting/hypothesis-log.md) — H509–H514 as-of-date bug family this tool's roadmap (v0.3) targets
