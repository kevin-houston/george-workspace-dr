---
updated: 2026-07-30
category: options-strategies
sources:
  - arXiv:2511.07571
  - arXiv:2603.17151
  - arXiv:2603.21892
  - arXiv:2509.01743
  - SSRN:4531181
---

# Implied Volatility Surface Forecasting — 2026 Papers

Four papers materially advance IV surface modeling from late 2025 through mid-2026: **generative forecasting** (DDPM), **compact representation** (shallow NN), **symbolic parametrization** (SVI alternative), and **controllable generation** (VAE). Together they map the landscape for H448 and H449 implementation.

---

## Paper 1: Diffusion Model IV Surface Forecasting

**Citation:** Jin, C. & Agarwal, A. (2025, revised May 2026). "Forecasting implied volatility surface with generative diffusion models." arXiv:2511.07571.

**Code:** https://github.com/Austinjinc/diffusion-paper-code

### What it does
Trains a **conditional Denoising Diffusion Probabilistic Model (DDPM)** to generate arbitrage-free one-day-ahead implied volatility surfaces for SPX options. Conditioning variables:
- Exponential weighted moving averages (EWMAs) of historical IV surfaces across maturities and strikes
- Returns and squared returns of the underlying (SPY/SPX)
- Scalar risk indicators including VIX

### Key technical contribution
Historical option data frequently contains calendar or butterfly arbitrage violations. The paper introduces a **parameter-free SNR (signal-to-noise ratio) weighting scheme** that incorporates an arbitrage penalty into the DDPM loss function without needing a separate constraint optimizer.

### Empirical results
- Significantly outperforms leading GAN-based models (VolGAN, etc.) in capturing stylized facts of IV dynamics
- Conditioning on EWMAs of historical surfaces (the tractable ablation) captures ~80% of the full DDPM benefit — useful approximation for backtesting
- Evaluated on SPX index options; evaluated from 2015–2023

### Relevance to our stack
- **H448 design basis**: the VRP signal (predicted IV − realized vol) is cleaner when the IV forecast enforces no-arbitrage. Even without running the full DDPM, the EWMA-surface approximation is tractable.
- **H309 context (SPX Dispersion)**: the diffusion model could supply the implied correlation surface estimates needed for Phase 2 of H309.
- **Practical note**: requires CBOE DataShop or Polygon options data for full implementation. Var B/C of H448 use EMA approximation.

---

## Paper 2: Shallow Representation of Option Implied Information

**Citation:** Lin, J. (2026, March). "Shallow Representation of Option Implied Information." arXiv:2603.17151. Published in *q-fin.CP* (Computational Finance).

### What it does
Provides a systematic approach to build neural representations of the option-implied information embedded in the IV surface. Core insight: **a single-hidden-layer feedforward network with a specific activation is sufficient** to represent both implied density and implied volatility — deeper or wider architectures add noise rather than signal.

### Theoretical grounding
The paper revisits the explicit link between implied density and implied volatility through an alternative lens: IV is a *pointwise corrector* that maps the Black-Scholes quasi-density into the implied risk-neutral density. This framing naturally motivates shallow architectures because the corrector is low-complexity by construction.

### Key finding
Extensive experiments confirm: adding depth/width to the IV representation network **does not improve** and often degrades performance. This mirrors the general principle from the bilevel-autoresearch literature (arXiv:2603.23420): mechanism-level simplicity beats model complexity.

### Relevance to our stack
- **H449 design basis**: the shallow IV representation produces stable, low-noise implied skewness and kurtosis moments that can serve as cross-sectional equity return predictors.
- **H309 (SPX Dispersion)**: compact IV surface representation reduces data requirements for building the implied correlation surface.
- **General principle**: when building option-based features for factor models, shallow representations (rolling windows of IV moments: ATM IV, skew slope, curvature) outperform learned deep embeddings. This validates our existing approach of using VIX/VIX3M/VIX9D as IV surface proxies.

---

## Paper 3: Symbolic Regression Parametrization

**Citation:** Keller-Ressel, M. & Nikulski, H. (2026, March). "Discovering parametrizations of implied volatility with symbolic regression." arXiv:2603.21892.

### What it does
Uses **symbolic regression** to discover analytic closed-form formulas for the total implied variance (w = σ²_IV × T) as a function of log-moneyness and maturity — without imposing the SVI functional form. Key distinction from SVI:
- SVI: `w(k) = a + b(ρ(k-m) + √((k-m)² + σ²))` — 5 parameters, fixed functional form
- Symbolic approach: search over expression trees to discover the best structure data-driven

### Key results
- Discovered formulas match SVI accuracy with **fewer parameters** on some smile shapes
- Found novel parametrizations that generalize better in sparse-data regions (far strikes, long maturities)
- Numerically stable: symbolic forms avoid SVI's Butterfly-arb violations at extreme strikes

### Practical takeaway
For H448/H449 implementation: use SVI (Gatheral 2004) as baseline; symbolic regression can improve fit quality if implementing a full IV surface pipeline. The paper's open comparison vs SVI is the key table.

---

## Paper 4: Controllable VAE Generation

**Citation:** Wang, J., Liu, S. & Vuik, C. (2025, September). "Controllable Generation of Implied Volatility Surfaces with Variational Autoencoders." arXiv:2509.01743.

### What it does
A VAE framework where latent space is **explicitly disentangled** into financially interpretable shape features (vol level, slope, curvature, term structure) plus residual factors. Allows:
- Conditioning on a scenario (e.g., "bear market, VIX=35, steep inversion") → sample realistic surface
- Surface completion when some strikes/maturities are missing
- Stress testing: hold shape features fixed, vary residual to generate 1000 surface scenarios

### Relationship to DDPM (Paper 1)
- VAE: fast inference, explicit latent control, useful for risk scenarios and surface completion
- DDPM: slower, sample quality is higher, no explicit latent control
- For production use where fast scenario generation matters: VAE. For research accuracy benchmarks: DDPM.

---

## Deep Learning from IV Surfaces (Kelly et al.)

**Citation:** Kelly, B.T., Kuznetsov, B., Malamud, S., Xu, T.A. (2023, rev. 2025). "Deep Learning from Implied Volatility Surfaces." SSRN:4531181.

### What it does
Studies what predictive information about future stock returns is contained in the **entire IV surface** (all strikes × maturities), using deep learning to extract it:
- Input: full IV surface (normalized by ATM level) for each stock on each date
- Output: one-month-ahead stock return cross-section
- Finding: IV surface factors contain **alpha relative to standard equity factors** (size, value, momentum, quality, BAB)

### Key results (approx from abstract/prior readings)
- IV surface predictors explain a meaningful fraction of return cross-section variance after controlling for standard factors
- ATM IV, IV slope (skew), and term-structure slope (short vs. long maturity) are the three highest-information features
- Deep IV surface factors are NOT redundant with standard equity momentum — they carry incremental signal

### Relevance
This paper is the fundamental academic grounding for H449. The shallow NN finding (Paper 2) confirms the shallow extraction strategy; Kelly et al. confirm the cross-sectional return predictability.

---

## 2026 Applied Results: NN Corrections to Parametric Models

**Source:** Duan et al. (2026). "Option Implied Volatility and Trading Strategies Based on Neural Network Correction." *Journal of Futures Markets.* doi:10.1002/fut.70046.

A **two-stage hybrid framework**: (1) fit SABR/SVI parametric model; (2) train feedforward NN on residuals. Key findings:
- NN correction reduces IV RMSE by ~15–20% over pure SABR on SPX options
- Trading signals derived from NN-corrected IV deliver **higher Sharpe ratios** than signals from raw parametric IV
- Effect is most pronounced for **short-dated OTM options** where parametric models fail most

**Takeaway for H448**: even if not running a full DDPM, a hybrid parametric+residual-NN approach is a viable Var B that outperforms plain EWMA.

---

## Connecting to H448 and H449

| Hypothesis | Paper | Mechanism | Key variant | Gate |
|-----------|-------|-----------|-------------|------|
| H448 | arXiv:2511.07571 | DDPM-forecast IV → cleaner VRP signal for SPX | Var C: VRP + term-structure slope | OOS Sharpe ≥ 1.0, MaxDD ≤ 25% |
| H448 Var B | SSRN Duan 2026 | Parametric+NN residual correction → VRP signal | Var B: SABR+NN hybrid VRP | Same gate |
| H449 | arXiv:2603.17151 | Shallow IV moments as cross-section equity factor | Var C: L/S dollar-neutral quintiles on IVSKEW+IVKURT | OOS Sharpe ≥ 1.0 |
| H449 Var D | SSRN:4531181 | Full IV surface deep features → equity factor | Var D: deep IV surface model | OOS Sharpe ≥ 1.0 |

---

## Python Implementation

### VIX proxy approach for H448 Var A (free, production-ready)
```python
import yfinance as yf
import pandas as pd
import numpy as np

# VIX family: 9d, 30d, 93d ATM implied vol proxies
vix_tickers = {"VIX9D": "^VIX9D", "VIX": "^VIX", "VIX3M": "^VIX3M"}
vix_data = {}
for name, ticker in vix_tickers.items():
    s = yf.download(ticker, start="2010-01-01", auto_adjust=True, progress=False)["Close"]
    vix_data[name] = s.squeeze()
vix = pd.DataFrame(vix_data).ffill()

# VRP proxy: VIX (implied) vs realized vol (22-day)
spy = yf.download("SPY", start="2010-01-01", auto_adjust=True, progress=False)["Close"].squeeze()
spy_ret = spy.pct_change()
rv22 = spy_ret.rolling(22).std() * np.sqrt(252) * 100  # annualized %
vrp = vix["VIX"] - rv22  # VRP in vol points; positive = IV > RV (normal)

# Term structure slope (IV surface tilt)
ts_slope = vix["VIX3M"] - vix["VIX9D"]  # positive = upward sloping = low fear
```

### SVI surface parametrization (with arbitrage check)
```python
import numpy as np
from scipy.optimize import minimize

def svi(k, a, b, rho, m, sigma):
    """SVI total variance: w(k) = a + b*(rho*(k-m) + sqrt((k-m)**2 + sigma**2))"""
    return a + b * (rho * (k - m) + np.sqrt((k - m)**2 + sigma**2))

def svi_calendar_arb_check(params_t1, params_t2, k_grid=np.linspace(-1, 1, 50)):
    """Return True if no calendar arbitrage (w_t2 >= w_t1 everywhere)."""
    w1 = svi(k_grid, *params_t1)
    w2 = svi(k_grid, *params_t2)
    return bool(np.all(w2 >= w1 - 1e-8))

def fit_svi_slice(k_obs, iv_obs, T):
    """Fit SVI to one maturity slice. k = log-moneyness, iv in decimal."""
    w_obs = iv_obs**2 * T  # total variance
    def loss(p):
        w_fit = svi(k_obs, *p)
        return np.sum((w_fit - w_obs)**2)
    # No-arb constraints: a>0, b>0, |rho|<1, sigma>0
    bounds = [(-0.5, 0.5), (1e-4, 2.0), (-0.99, 0.99), (-1.0, 1.0), (1e-4, 2.0)]
    result = minimize(loss, x0=[0.04, 0.2, -0.3, 0.0, 0.3], bounds=bounds, method="L-BFGS-B")
    return result.x
```

### IV moment extraction for H449 factor (Polygon data)
```python
import os
import requests

POLYGON_KEY = os.environ["POLYGON_API_KEY"]

def get_option_chain_iv_moments(ticker, date_str):
    """
    Fetch option chain snapshot from Polygon, return ATM IV, skew slope, curvature.
    date_str: 'YYYY-MM-DD'
    """
    url = f"https://api.polygon.io/v3/snapshot/options/{ticker}"
    params = {"apiKey": POLYGON_KEY, "limit": 250}
    r = requests.get(url, params=params)
    chains = r.json().get("results", [])
    
    records = []
    for c in chains:
        d = c.get("details", {})
        greeks = c.get("greeks", {})
        records.append({
            "strike": d.get("strike_price"),
            "expiry": d.get("expiration_date"),
            "type": d.get("contract_type"),
            "iv": c.get("implied_volatility"),
            "delta": greeks.get("delta"),
        })
    df = pd.DataFrame(records).dropna()
    
    # Near-term slice (~30 DTE)
    df["expiry"] = pd.to_datetime(df["expiry"])
    ref_date = pd.Timestamp(date_str)
    df["dte"] = (df["expiry"] - ref_date).dt.days
    near_term = df[(df["dte"] >= 20) & (df["dte"] <= 45)]
    calls = near_term[near_term["type"] == "call"].copy()
    calls["moneyness"] = calls["delta"].abs()  # proxy for moneyness
    
    if len(calls) < 5:
        return None
    
    # ATM IV: call with delta closest to 0.5
    atm = calls.iloc[(calls["moneyness"] - 0.5).abs().argsort()[:1]]
    atm_iv = atm["iv"].iloc[0]
    
    # Skew: IV(delta=0.25 put) - IV(delta=0.25 call) — negative = left skew (normal for equity)
    puts = near_term[near_term["type"] == "put"]
    otm_put = puts.iloc[(puts["delta"].abs() - 0.25).abs().argsort()[:1]]
    otm_call = calls.iloc[(calls["moneyness"] - 0.25).abs().argsort()[:1]]
    skew = (otm_put["iv"].iloc[0] - otm_call["iv"].iloc[0]) if len(otm_put) > 0 else np.nan
    
    return {"atm_iv": atm_iv, "skew": skew, "dte": near_term["dte"].mean()}
```

### Arbitrage-free surface check
```python
def check_surface_arbitrage(iv_surface_df):
    """
    iv_surface_df: DataFrame indexed by (strike, expiry), column 'iv'
    Returns dict of violations found.
    """
    violations = {"calendar": [], "butterfly": []}
    expiries = sorted(iv_surface_df.index.get_level_values("expiry").unique())
    
    for i, T1 in enumerate(expiries[:-1]):
        T2 = expiries[i+1]
        slice1 = iv_surface_df.xs(T1, level="expiry")["iv"]
        slice2 = iv_surface_df.xs(T2, level="expiry")["iv"]
        shared_strikes = slice1.index.intersection(slice2.index)
        w1 = slice1.loc[shared_strikes]**2 * T1
        w2 = slice2.loc[shared_strikes]**2 * T2
        cal_viols = shared_strikes[(w2 < w1 - 1e-6)].tolist()
        if cal_viols:
            violations["calendar"].append({"T1": T1, "T2": T2, "strikes": cal_viols})
    
    return violations
```

---

## Prior Related Work in Wiki

- [Volatility Risk Premium](volatility-risk-premium.md) — IV > RV ~85% of time; VRP 2–4 vol pts; short-vol Sharpe ~1.0; H266 queued
- [SPX Dispersion Trading & Variance Risk Premium](spx-dispersion-variance.md) — H309 PARTIAL; implied correlation premium 6–18pp historically
- [BSM as Flat Limit of Information Geometry](bsm-information-geometry.md) — SSRN 6630259; smile = manifold curvature; zero-free-parameter LEAPS prediction within 19%
- [Options Data Sources](../data-sources/options-data.md) — ThetaData (cheapest), ORATS (best IV surface), Polygon (real-time only)
- [Options Backtesting Methodology](../backtesting/options-backtesting-methodology.md) — path-dependency, vol surface evolution, 4-tier data pipeline

---

## Data Sources and Practical Notes

### Getting IV surface data without CBOE DataShop
| Source | Cost | Coverage | Best for |
|--------|------|----------|---------|
| `^VIX`, `^VIX9D`, `^VIX3M` via yfinance | Free | SPX ATM only, 3 maturities | H448 Var A/B/C |
| Polygon options API (`$POLYGON_API_KEY`) | Have key | EOD option chains, full strike grid | H449 cross-section |
| ThetaData | $20/mo student | Full SPX options history to 2005 | H448 full DDPM |
| ORATS | $99/mo | Smoothed historical IV surface | Best quality |

### Python libraries
- **`py_vollib`**: fast BSM greeks and IV calculation; pip install py-vollib
- **`FinancePy`**: comprehensive options math including SVI calibration; pip install financepy
- **`QuantLib` (via `QuantLib-Python`)**: industry standard; SABR SmileSection with no-arb enforcement
- **`arch`**: realized variance estimation (GK, Parkinson, Yang-Zhang estimators for RV computation in VRP)

### Arbitrage-free surface check (quick)
For any IV surface snapshot, check:
- **Calendar spread**: total variance w(T2) ≥ w(T1) for T2 > T1 at same strike
- **Butterfly spread**: IV(K-dk) + IV(K+dk) > 2×IV(K) for any strike K
- **Lee moment bound**: IV(k,T) ≤ √(2|k|/T + ...) — prevents IV from diverging too fast at wings
- Use `py_vollib` or `FinancePy` for fast arbitrage screening

### H448 implementation path (least to most complex)
1. **Var A** — VRP(t) = VIX - RV22d on SPY → monthly signal → gate strategy (fully tractable now)
2. **Var B** — EWMA IV surface + NN residual correction → cleaner VRP (Duan et al. 2026 approach)
3. **Var C** — Full DDPM (Jin & Agarwal 2025) → needs ThetaData or Polygon historical options
4. **Var D** — Kelly et al. deep IV surface → full option chain per stock, very data-heavy

### Reference GitHub repos
- https://github.com/Austinjinc/diffusion-paper-code — DDPM IV forecasting code (Paper 1)
- https://github.com/XanderRobbins/Arbitrage-Free-Volatility-Surface — SVI + Heston Python toolkit

---

## Negative Result: Time Series Foundation Models for Realized Volatility

**arXiv:2607.05291** — "Forecasting Realized Volatility with Time Series Foundation Models" (July 2026). Evaluates 9 zero-shot TSFMs (including Tiny Time Mixers TTM) against 8 econometric benchmarks on the VOLARE dataset (50 assets: equities, forex, futures).

**Finding:** TSFMs provide no reliable improvement over Log-HAR for realized volatility forecasting. Only TTM beats Log-HAR by a narrow margin; the short-horizon advantage reflects better forecast *scaling* rather than better dynamics prediction. "Foundation models do not deliver a uniform gain — the advantage is concentrated in a few outlier assets."

**Implication for H448:** The RV leg of the VRP signal (IV_forecast − RV_realized) should use **RV22d (22-day rolling realized vol)**, not a TSFM. TSFM complexity adds engineering overhead with negligible signal improvement.

**Best practice for H448:** VRP = VIX − RV22d (simple, fast, tested). Only upgrade RV estimator if Garman-Klass or Yang-Zhang intraday estimators show material improvement — they better capture overnight jumps without adding ML complexity.

**What TSFMs ARE good for:** Cross-sectional return prediction where training data is large and diverse. NOT recommended for univariate vol-of-vol forecasting where HAR already captures the relevant persistence structure.
