---
updated: 2026-08-05
type: reference
---

# Portfolio Optimization Libraries

Python libraries for combining strategies and building efficient portfolios. Directly relevant to blending our confirmed strategies (H026 ETF rotation + H191 BAB + H198 momentum + H201 TOM).

---

## Quick comparison

| Library | Version | Install | Best for |
|---------|---------|---------|---------|
| PyPortfolioOpt | 1.6.0 (Feb 2026) | `pip install pyportfolioopt` | Fast Markowitz/HRP, beginner-friendly |
| Riskfolio-Lib | 7.2.1 (Feb 2026) | `pip install riskfolio-lib` | 24 risk measures, risk parity, NCO |
| skfolio | 0.20.1 (Apr 2026) | `pip install skfolio` | sklearn API, walk-forward CV, ensembles |

---

## PyPortfolioOpt

**Repo**: github.com/PyPortfolio/PyPortfolioOpt — 4,600+ stars, MIT  
**Docs**: pyportfolioopt.readthedocs.io

Most mature and widely used. Good for classical mean-variance + HRP. Modular — swap in custom return/covariance estimators.

### Models

| Model | Class | Use case |
|-------|-------|---------|
| Maximum Sharpe | `EfficientFrontier` | Baseline long-only |
| Minimum volatility | `EfficientFrontier` | Low-vol tilt |
| Efficient return/risk | `EfficientFrontier` | Target return or vol |
| Mean-semivariance | `EfficientSemivariance` | Penalize downside only |
| Mean-CVaR | `EfficientCVaR` | Tail risk budgeting |
| HRP | `HRPOpt` | No mean estimate needed |
| Black-Litterman | `BlackLittermanModel` | Incorporate views |

### Expected return estimators

```python
from pypfopt import expected_returns
mu = expected_returns.mean_historical_return(prices)  # simple mean
mu = expected_returns.ema_historical_return(prices, span=252)  # EMA
mu = expected_returns.capm_return(prices)              # CAPM beta-adjusted
```

### Risk model estimators

```python
from pypfopt import risk_models
S = risk_models.sample_cov(prices)
S = risk_models.exp_cov(prices, span=180)              # exponential decay
S = risk_models.CovarianceShrinkage(prices).ledoit_wolf()  # Ledoit-Wolf
```

### Example: max Sharpe with Ledoit-Wolf

```python
from pypfopt import EfficientFrontier, expected_returns, risk_models
from pypfopt.discrete_allocation import DiscreteAllocation, get_latest_prices

mu = expected_returns.capm_return(prices)
S  = risk_models.CovarianceShrinkage(prices).ledoit_wolf()

ef = EfficientFrontier(mu, S)
ef.add_constraint(lambda w: w >= 0.02)   # min 2% per asset
ef.add_constraint(lambda w: w <= 0.30)   # max 30% per asset
weights = ef.max_sharpe()
cleaned = ef.clean_weights()
ef.portfolio_performance(verbose=True)
# → Expected annual return: 12.3%  Volatility: 11.1%  Sharpe: 0.96

# Discrete allocation (whole shares)
latest_prices = get_latest_prices(prices)
da = DiscreteAllocation(cleaned, latest_prices, total_portfolio_value=100000)
allocation, leftover = da.greedy_portfolio()
```

### Example: HRP (no return estimate needed)

```python
from pypfopt import HRPOpt
hrp = HRPOpt(returns=prices.pct_change().dropna())
hrp.optimize()
weights = hrp.clean_weights()
```

---

## Riskfolio-Lib

**Repo**: github.com/dcajasn/Riskfolio-Lib — 3,700+ stars, BSD  
**Docs**: riskfolio-lib.readthedocs.io  
**Author**: Dany Cajas

Most comprehensive. Built on CVXPY (compatible with MOSEK/GUROBI for large problems). 24 convex risk measures including full drawdown-based objectives. Best choice when you need risk parity or NCO.

### Risk measures available

- **Dispersion**: MV (variance), MAD, MSV (semi-variance), FLPM, SLPM
- **Drawdown**: MDD, ADD, CDaR, EDaR (entropic), UCI
- **Tail**: VaR, CVaR, EVaR (entropic), RVaR (relativistic), WR, CVRG, TGRG

### Example: HRP with CVaR

```python
import riskfolio as rp

port = rp.HCPortfolio(returns=returns)
weights = port.optimization(
    model='HRP',
    codependence='pearson',
    rm='CVaR',          # risk measure for clustering
    rf=0,
    linkage='ward',
    max_k=10,           # max number of clusters
    leaf_order=True,
)
```

### Example: Risk parity (equal risk contribution)

```python
port = rp.Portfolio(returns=returns)
port.assets_stats(method_mu='hist', method_cov='ledoit')

weights = port.rp_optimization(
    model='Classic',
    rm='MV',           # minimize variance subject to equal risk contribution
    rf=0,
    b=None,            # equal risk budgets
    hist=True,
)
```

### Example: NCO (Nested Clustered Optimization)

```python
weights = port.optimization(
    model='NCO',
    codependence='pearson',
    covariance='hist',
    obj='Sharpe',
    rm='MV',
    rf=0,
    l=0,
)
```

---

## skfolio

**Repo**: github.com/skfolio/skfolio — 1,300+ stars, BSD  
**Docs**: skfolio.org  
**Paper**: arXiv:2507.04176

Newest of the three. API mirrors scikit-learn — uses `fit()` / `predict()` / `cross_validate()`. Walk-forward CV and combinatorial purged CV built-in. Best choice when integrating portfolio optimization into an ML pipeline or doing rigorous out-of-sample validation.

### Example: walk-forward CV comparison

```python
from skfolio import Population
from skfolio.optimization import MeanRisk, HierarchicalRiskParity, EqualWeighted
from skfolio.model_selection import WalkForward, cross_validate
from skfolio.preprocessing import prices_to_returns

X = prices_to_returns(prices)

models = {
    "EW":  EqualWeighted(),
    "MV":  MeanRisk(risk_measure="Variance"),
    "HRP": HierarchicalRiskParity(),
}

cv = WalkForward(train_size=252, test_size=21)  # 1yr train, 1mo test
for name, model in models.items():
    scores = cross_validate(model, X, cv=cv, scoring=["sharpe_ratio", "max_drawdown"])
    print(f"{name}: Sharpe={scores['test_sharpe_ratio'].mean():.3f}")
```

### Example: Black-Litterman with views

```python
from skfolio.optimization import BlackLitterman
from skfolio.prior import BlackLittermanPrior

# Views: AAPL +5% above equilibrium, MSFT -2%
prior = BlackLittermanPrior(
    views={"AAPL": 0.05, "MSFT": -0.02},
    views_uncertainty=0.1,
)
model = BlackLitterman(prior=prior)
model.fit(X)
print(model.weights_)
```

### Example: Stacking (ensemble)

```python
from skfolio.optimization import StackingOptimization

# Blend MV + HRP outputs as inputs to a meta-optimizer
stacking = StackingOptimization(
    estimators=[("mv", MeanRisk()), ("hrp", HierarchicalRiskParity())],
    final_estimator=MeanRisk(),
)
stacking.fit(X)
```

---

## Applying to our strategy blend

We have 4 confirmed building blocks:

| Strategy | File | OOS Sharpe | Beta |
|----------|------|------------|------|
| H026 ETF rotation | paper-trading/h122-alpaca.md | ~1.2 | ~0.5 |
| H191 BAB | backtesting/results/ | 1.367 | ~0 |
| H198 momentum (6-1m) | backtesting/results/ | 1.174 | ~0.6 |
| H201 TOM | backtesting/results/h201_turn_of_month.json | 0.740 | ~0.75 |

### Pattern for combining (monthly rebalance)

```python
import pandas as pd
import riskfolio as rp

# Load monthly returns for each strategy
strat_returns = pd.DataFrame({
    "H026": h026_monthly,
    "BAB":  bab_monthly,
    "MOM":  mom_monthly,
    "TOM":  tom_monthly,
})

port = rp.Portfolio(returns=strat_returns)
port.assets_stats(method_mu='hist', method_cov='ledoit')

# Risk parity — equal volatility contribution across strategies
weights = port.rp_optimization(model='Classic', rm='MV', rf=0)
print(weights)
```

### Practical notes

- **Use HRP / risk parity** when correlations are unstable (they often are between momentum and defensive strategies).
- **Avoid maximum Sharpe** with few assets (4–10 strategies): grossly overfit to in-sample data.
- **Ledoit-Wolf shrinkage** is better than sample covariance when n_assets approaches n_periods.
- **Rebalance monthly** for strategy-of-strategies; daily rebalancing adds turnover with little benefit.
- **Lookback window**: 12–24 months for monthly strategy returns (not enough data for longer).

---

## Install requirements

```bash
pip install pyportfolioopt riskfolio-lib skfolio cvxpy
# Optional solvers for large problems (Riskfolio-Lib):
# pip install clarabel  # open-source, fast, replaces ECOS
```

Note: Riskfolio-Lib v7+ uses Clarabel as default solver (replaces ECOS which was removed from CVXPY). No license needed.

## Differentiable Financial Objectives (arXiv:2605.28853, May 2026)

Paper: "Financially Guided Deep Portfolio Optimization" — Fernandes & Desell, submitted 16 May 2026.

**Key idea:** Replace predict-then-optimize with end-to-end differentiable surrogate losses that directly optimize Sharpe, Omega, CVaR, and Risk Parity during model training. Neural network learns portfolio weights directly via backpropagation.

**Best model:** AttentionLSTM + composite Omega-CVaR-RiskParity loss  
OOS 2022-2023 (50 S&P 500 stocks, 2007-2023 IS):  
- Sharpe: 0.29 (vs S&P 500: -0.02)  
- Total return: +7.86% (vs S&P 500: -4.52%)  
- Outperforms HRP, NCO, MVP, equal-weight in bear market period

**Differentiable loss formulas (for reference):**

Sharpe surrogate:  
```python
# Differentiable Sharpe (negative, for minimization)
def neg_sharpe_loss(weights, returns_matrix):
    port_returns = returns_matrix @ weights  # [T,]
    return -(port_returns.mean() / (port_returns.std() + 1e-8))
```

CVaR surrogate (alpha=0.05):  
```python
def cvar_loss(weights, returns_matrix, alpha=0.05):
    port_returns = returns_matrix @ weights
    var = torch.quantile(port_returns, alpha)
    return -torch.mean(port_returns[port_returns <= var])
```

**Application to our stack:**
- Current H228 blend (H217+H181 at 50/50) uses fixed weights. Could substitute a walk-forward Omega-CVaR optimizer using Riskfolio-Lib's custom objective support.
- The expanding-window walk-forward is the same framework used in our backtesting (15 IS folds, 8 OOS folds from 2007-2023).
- **Prerequisite:** PyTorch installed (already in venv); sentence-transformers as proxy.

**Related:** [Position Sizing & Portfolio Construction](../algorithms/position-sizing.md), H228 (current best blend)

---

## cvxportfolio — Cost-Aware Convex Optimization Backtesting (added 2026-08-05)

`github.com/cvxgrp/cvxportfolio` -- Stanford CVXGRP (Boyd optimization group), 1,246 stars, GPL-3.0, actively maintained (last push 2026-04-27).

**What it fills**: The existing coverage above (PyPortfolioOpt, Riskfolio-Lib, skfolio) handles convex/risk-parity portfolio *optimization* only. None of them combine that with a **cost-aware backtest loop** -- cvxportfolio bakes transaction costs and market impact directly into the optimization objective at each rebalance, rather than applying costs as a post-hoc haircut on top of optimizer output the way our current backtests do.

```bash
pip install cvxportfolio
```

```python
import cvxportfolio as cvx

# Define cost-aware objective: mean-variance minus transaction cost minus holding cost
objective = cvx.ReturnsForecast() - 0.5 * cvx.FullCovariance() - cvx.StocksTransactionCost() - cvx.StocksHoldingCost()
constraints = [cvx.LeverageLimit(1)]
policy = cvx.SinglePeriodOptimization(objective, constraints)

simulator = cvx.StockMarketSimulator(universe=["SPY", "TLT", "GLD", "DBC"])
result = simulator.backtest(policy, start_time="2013-01-01", end_time="2026-01-01")
print(result.sharpe_ratio, result.max_drawdown)
```

**Relevance to production strategies**: Directly testable against the current top-1/top-2 monthly rotation logic in H026 (25-asset sector+alts), H045 (13-asset bonds), and H041a (19-asset) -- would answer whether a convex-optimized weight vector with in-loop transaction costs beats simple top-N selection once realistic costs are modeled at the optimization stage rather than estimated afterward. Not yet backtested against our universes; logged as a tool to evaluate, not a confirmed improvement.

**See also**: [Performance Attribution](../paper-trading/performance-attribution.md) — where these optimizer outputs get monitored and evaluated live.
