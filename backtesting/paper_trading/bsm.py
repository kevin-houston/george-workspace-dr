"""BSM pricing and Greeks (shared with H007 simulation)."""

import math
from scipy.stats import norm


def bsm(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    """Black-Scholes option price."""
    if T <= 0:
        return max(0.0, (S - K) if right.upper() == "C" else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if right.upper() == "C":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def delta(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    """BSM delta."""
    if T <= 0:
        if right.upper() == "C":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1) if right.upper() == "C" else norm.cdf(d1) - 1.0


def theta_daily(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float:
    """BSM theta per day (negative = time decay)."""
    if T <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    t1 = -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
    if right.upper() == "C":
        t2 = -r * K * math.exp(-r * T) * norm.cdf(d2)
    else:
        t2 = r * K * math.exp(-r * T) * norm.cdf(-d2)
    return (t1 + t2) / 365.0


def strike_for_delta(S: float, T: float, r: float, sigma: float,
                     target_delta: float, right: str) -> float:
    """Analytically solve for strike given target absolute delta."""
    if right.upper() == "C":
        d1 = norm.ppf(target_delta)
    else:
        d1 = norm.ppf(1 - abs(target_delta))
    log_ratio = d1 * sigma * math.sqrt(T) - (r + 0.5 * sigma**2) * T
    return S * math.exp(-log_ratio)
