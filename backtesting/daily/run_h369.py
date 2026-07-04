"""
H369 — ReCAP: Regime-Adaptive Continual Learning for ETF Rotation
Source: arXiv:2606.00143 (ReCAP framework)

Hypothesis: Apply regime-aware continual learning to the production H026/H041a/H045 blend.
Instead of fixed rolling-window refitting, maintain per-regime weight estimates and
transfer knowledge across regime transitions — avoiding catastrophic forgetting of
crisis-era learning.

Gate: OOS Sharpe > 4.158 (production baseline) AND MaxDD better than -3.60%
Universe: Production portfolio (H041a 22% / H026 27% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%)
IS: 2004-01-01 to 2019-12-31
OOS: 2020-01-01 to 2026-06-30

Implementation notes:
- Use H249 regime engine (SPY 200MA x VIX + rate-hike modifier) for regime detection
- Maintain per-regime weight estimates for the 3 core strategies
- On regime transition: transfer 50% of prior regime's estimates to new regime module
- Simple version first (50/50 blending); add EWC only if simple version shows promise
- The core insight is regime-memory, not the specific EWC method
"""

# Production strategy weights (baseline)
BASELINE_WEIGHTS = {
    'H041a': 0.22,
    'H026':  0.27,
    'H045':  0.21,
    'XLK_IBS': 0.20,
    'SMH_IBS': 0.08,
    'IGV_IBS': 0.02,
}
IS_END = '2019-12-31'
OOS_START = '2020-01-01'
GATE_SHARPE = 4.158
GATE_MDD = -0.036  # -3.60%

# Regime definitions (from H249)
# bull_quiet: SPY > 200MA AND VIX < 20
# bull_volatile: SPY > 200MA AND VIX >= 20
# bear_quiet: SPY < 200MA AND VIX < 20
# bear_volatile: SPY < 200MA AND VIX >= 20

# TODO: implement ReCAP framework
# 1. Run production strategies through IS period, compute monthly returns per strategy
# 2. Label each month with H249 regime
# 3. For each regime, maintain exponentially-weighted average of strategy performance
# 4. On regime transition: new_weights[regime_new] = 0.5 * weights[regime_prev] + 0.5 * prior[regime_new]
# 5. Monthly rebalance using regime-adjusted weights; evaluate on OOS 2020-2026
