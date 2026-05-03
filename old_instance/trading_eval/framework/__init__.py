"""
NanoClaw Trading Eval Framework v1.0
Standardized harness base + analysis layer for all eval rounds R29+.
"""
from .base_harness import (
    TradeLogger,
    fetch_data,
    get_close,
    bs_call, bs_put, bs_delta_call, bs_delta_put, bs_gamma, bs_theta_call, bs_vega,
    realized_vol, iv_estimate, iv_rank,
    build_regime_calendar, get_trade_regime,
    REGIME_CRISIS, REGIME_BEAR, REGIME_HIGH_VOL,
    REGIME_BULL, REGIME_LOW_VOL, REGIME_UNKNOWN,
    RF, IV_PREMIUM,
    EVAL_DIR, CACHE_DIR, TRADE_LOG_DIR,
)

__version__ = '1.0.0'
__all__ = [
    'TradeLogger',
    'fetch_data', 'get_close',
    'bs_call', 'bs_put', 'bs_delta_call', 'bs_delta_put',
    'bs_gamma', 'bs_theta_call', 'bs_vega',
    'realized_vol', 'iv_estimate', 'iv_rank',
    'build_regime_calendar', 'get_trade_regime',
    'REGIME_CRISIS', 'REGIME_BEAR', 'REGIME_HIGH_VOL',
    'REGIME_BULL', 'REGIME_LOW_VOL', 'REGIME_UNKNOWN',
    'RF', 'IV_PREMIUM',
    'EVAL_DIR', 'CACHE_DIR', 'TRADE_LOG_DIR',
]
