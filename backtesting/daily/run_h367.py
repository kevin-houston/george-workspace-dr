"""
H367 — HMM + RL Regime Allocation on SPY/TLT/GLD
Source: arXiv:2605.27848 (Verma et al., May 2026)
Based on: H251 (3-state Gaussian HMM, OOS Sharpe 0.941)

Hypothesis: Replace H251's static regime-conditional weights with a PPO-trained
RL policy. Paper achieves Sharpe 1.68 vs static 0.92 on same 3-asset universe.
Gate: OOS Sharpe > 1.532 (H311 EW-4+VIX<20 benchmark), MaxDD < -10%

Universe: SPY, TLT, GLD
IS: 2004-01-01 to 2020-12-31
OOS: 2021-01-01 to 2026-06-30

Implementation notes:
- Start with H251 HMM regime labels as features
- Add daily returns, VIX, yield curve as additional state inputs
- RL episode = 1 year; reward = risk-adjusted return
- Train on IS; freeze policy for OOS evaluation — do NOT re-train in OOS
- Dependencies: hmmlearn (H251), stable-baselines3 (PPO)
"""

UNIVERSE = ['SPY', 'TLT', 'GLD']
IS_END = '2020-12-31'
OOS_START = '2021-01-01'
N_STATES = 3  # match H251
GATE_SHARPE = 1.532

# TODO: implement PPO policy over HMM state features
# 1. Load H251 HMM (or retrain on IS data)
# 2. Extract daily regime state probabilities as RL state features
# 3. Define RL environment: state = [regime_probs, VIX, yield_curve, returns_5d]
# 4. Train PPO agent with reward = rolling Sharpe of allocation
# 5. Evaluate frozen policy on OOS; compare vs H251 static weights and H311 gate
