---
updated: 2026-08-02
status: research
category: paper-trading
---

# Dynamic / Adaptive Multi-Strategy Capital Allocation

## Why this page exists

[Performance Attribution](performance-attribution.md) covers **static target-weight**
attribution (Brinson allocation + selection effect) against a fixed sleeve table:
H026 27% / H041a 22% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%. That
framework explains *why* the portfolio moved, but the weights themselves never
adapt — they're hand-set and only change when a new hypothesis is manually folded
in (e.g. H301's SPY 200MA overlay). This page covers the complementary problem:
**algorithmically re-weighting capital across strategy sleeves over time, based on
each sleeve's realized recent performance**, without George or Kevin manually
re-deriving target weights.

Two academic/OSS traditions apply here:

1. **Online Portfolio Selection (OPS)** — sequential regret-minimization algorithms
   (Cover's Universal Portfolio and descendants) that reweight *every period* to
   track the best-in-hindsight fixed-weight portfolio, with provable worst-case
   bounds.
2. **Multi-armed bandits (MAB) over strategies** — treat each strategy sleeve as a
   bandit "arm" and use exploration/exploitation algorithms (Thompson Sampling and
   its non-stationary variants) to shift capital toward sleeves currently
   outperforming, while still probing underweighted sleeves for regime changes.

## 1. Online Portfolio Selection — `universal-portfolios` (Marigold)

- **GitHub**: [Marigold/universal-portfolios](https://github.com/Marigold/universal-portfolios)
- **Install**: `pip install universal-portfolios`
- **Stats** (as of this research, 2026-08-02): 858 stars, 221 forks, 98 commits,
  9 contributors, actively maintained (open issues/PRs still being triaged).
- **What it implements**: 20+ OPS algorithms across four families —
  - *Benchmarks*: BAH (buy-and-hold), CRP (constant rebalanced portfolio), Markowitz,
    BCRP (best CRP in hindsight), Best-so-far, DCRP
  - *Follow-the-winner*: Universal Portfolio (Cover 1991), Exponential Gradient,
    OLMAR (Online Moving Average Reversion), ONS (Online Newton Step), CWMR, WMAMR
  - *Follow-the-loser*: Anticor, PAMR (Passive Aggressive Mean Reversion), CORN,
    RMR (Robust Median Reversion), RPRT
  - *Pattern matching*: BNN (nearest-neighbor), Kelly, MPT

**API pattern** (from the repo's own examples):

```python
from universal import tools
from universal.algos import CRP, OLMAR, Anticor

# quickrun() takes a DataFrame of asset/strategy returns (or prices) indexed by date
tools.quickrun(CRP())
```

The key adaptation for George's use case: instead of feeding it individual stock
prices, feed it a DataFrame of **daily NAV series per strategy sleeve** (H026,
H041a, H045, XLK IBS, SMH IBS, IGV IBS, H174 PEAD) built from
`strategy_accounts.json`. OPS algorithms are asset-agnostic — they only need a
price/NAV series per "instrument," and a strategy's cumulative equity curve is
exactly that.

```python
import pandas as pd
from universal.algos import OLMAR
from universal.result import AlgoResult

# nav_df: DataFrame, index=date, columns=strategy names, values=cumulative NAV
nav_df = build_sleeve_nav_df()  # from strategy_accounts.json equity history

algo = OLMAR(window=5, eps=10)  # 5-day lookback, reversion threshold
result: AlgoResult = algo.run(nav_df)

print(result.sharpe, result.total_wealth)
latest_weights = result.weights.iloc[-1]  # today's target allocation across sleeves
```

**Caveats for this use case**: OPS algorithms assume you can freely rebalance
into any "asset" at any time and that price series are the *only* signal (no
regime/macro context). George's sleeves have different rebalance cadences (H026/H041a/H045
monthly, IBS sleeves near-daily, PEAD event-driven) — feeding daily NAV series
smooths over this but the *executed* rebalance would still need to respect each
sleeve's native cadence. Best framed as a **target-weight generator** that George
computes weekly/monthly and feeds into the existing rebalance scripts, not a
literal daily live-trading engine.

## 2. Bandit-based strategy selection — "Bandit Networks" (ADTS / CADTS)

- **Paper**: "Improving Portfolio Optimization Results with Bandit Networks,"
  *Computational Economics* (Springer, 2025), DOI
  [10.1007/s10614-025-11090-0](https://doi.org/10.1007/s10614-025-11090-0).
  Full text is paywalled (Springer IDP login-gated) — only the abstract/summary
  was reachable during this research pass; flagging for a follow-up fetch via
  Sci-Hub-adjacent or arXiv preprint search if a free version surfaces.
- **Core idea**: define each **trading strategy** (not each asset) as a bandit
  arm. This is the opposite of the usual MAB-for-trading framing (arm = stock)
  and is the right fit for George's setup, where the "arms" are already
  well-defined, backtested strategies (H026, H041a, H045, H174, IBS sleeves).
  Framing strategies as arms keeps the action space small (7 arms) regardless of
  how many underlying assets each strategy trades — this avoids the
  dimensionality blowup that kills naive per-asset bandit approaches.
- **ADTS** = Adaptive Discounted Thompson Sampling — standard Thompson Sampling
  (Beta-Bernoulli or Gaussian reward posteriors per arm) with a *discount factor*
  applied to older observations, so the posterior tracks recent performance more
  than stale history — directly relevant since strategy edges decay (see H437/H435/H436
  showing 2024-2026 OOS Sharpe compression vs historical backtests).
  Standard update (Gaussian reward case, per strategy arm *i*):
  ```
  μ_i, σ²_i  ~ posterior over arm i's mean daily return
  On new observation r_t for arm i:
      μ_i ← discount·μ_i + (1-discount)·r_t   (exponentially-weighted mean)
      σ²_i ← discount·σ²_i + (1-discount)·(r_t - μ_i)²
  Sample θ_i ~ N(μ_i, σ²_i) for every arm each period
  Allocate more capital to arms with higher sampled θ_i (proportional or top-k)
  ```
- **CADTS** = Combinatorial ADTS — extends ADTS to select/weight a *subset* of
  arms simultaneously each period (relevant here since George runs all 7 sleeves
  concurrently rather than picking one) rather than pure single-arm-per-round
  bandit selection.
- **Practical read**: since the full backtest numbers were not accessible this
  pass, this is logged as a **research lead, not yet validated** — see the
  dream-cycle staged proposal filed alongside this page for a follow-up scan
  once a non-paywalled version (arXiv preprint or author's site) is found.

## 3. Bandit-over-bandit for non-stationary regimes — PRBO

- **Paper**: arXiv [2208.02901](https://arxiv.org/abs/2208.02901) — tests a
  Nonstationary Continuum-Armed Bandit (NCAB) approach for automated trading
  strategy parameter tuning, benchmarked against PRSH (a prior "shift"-based
  bandit strategy) on the Bristol Stock Exchange simulator.
- **Code**: [HarmoniaLeo/PRZI-Bayesian-Optimisation](https://github.com/HarmoniaLeo/PRZI-Bayesian-Optimisation)
- **Relevance**: this is "bandit-over-bandit" — an outer bandit loop that
  periodically re-tunes the inner bandit's own hyperparameters (e.g. ADTS's
  discount factor) as the market regime shifts, rather than fixing them once.
  Directly composable with the ADTS/CADTS approach above: use PRBO's outer loop
  to adapt ADTS's discount rate based on recent regime volatility (tie-in to the
  existing VIX/200MA regime gates already used in H249/H286/H301/H362).
- Tested on a market simulator (Bristol Stock Exchange), not real historical
  asset data — treat as an algorithmic pattern to borrow, not a directly
  transferable backtest result.

## 4. FinRL-X (context, not new)

Already referenced in [`algorithms/deep-rl-trading.md`](../algorithms/deep-rl-trading.md).
Combines deep RL policies with ensemble strategy selection — the heaviest-weight
option of the four (full DRL training pipeline vs. the lightweight OLPS/bandit
math above). Not the recommended starting point given George's infra (no GPU
training pipeline currently running) — noted here only to avoid re-discovering
it as "new" in a future scan.

## Recommended next step (staged as a hypothesis, not yet run)

None of the above has been backtested against George's actual sleeve returns
yet. The natural hypothesis-numbered next step (proposed as **H-next** in the
dream-cycle staging for tonight, see `dream_cycle/staged/2026-08-02/`):

> Build `nav_df` from `strategy_accounts.json` sleeve equity curves (H026,
> H041a, H045, H174 PEAD, XLK/SMH/IGV IBS), run `universal-portfolios`' OLMAR
> and CRP algorithms against it in backtest, and compare OOS Sharpe/MaxDD of
> the dynamically-reweighted blend vs. the current static target-weight blend
> (OOS Sharpe 4.158, MaxDD −3.60%). Gate: must beat 4.158 Sharpe AND not
> increase MaxDD beyond -5% to be worth the added operational complexity of a
> non-static rebalance schedule.

This is a **medium-effort, well-scoped** backtest — `universal-portfolios` is
pip-installable today and George already has the sleeve return history needed
to build `nav_df`. Estimated at one focused research session (write
`run_hNNN_dynamic_allocation.py`, similar structure to existing `run_hNNN.py`
scripts).

## See Also

- [Performance Attribution](performance-attribution.md) — existing static target-weight Brinson framework this page extends
- [Strategy Blending & Correlation Management](../backtesting/strategy-blending-correlation.md) — IC-weighted blending (a simpler static alternative to full OPS/bandit reweighting)
- [Deep RL Trading](../algorithms/deep-rl-trading.md) — FinRL-X context
