# H265b: Drift-Regime Conditional Value + Short-Term Reversal
# Source: arXiv:2511.12490 — paper's ACTUAL signals (not momentum as in H265)
# Drift gate: fraction positive daily returns in trailing 63 days > 0.60
# Signals: VALUE (book-to-price) + SHORT-TERM REVERSAL (negative 1-month return)
# CRITICAL: must use rolling S&P 500 constituents, NOT fixed 2025-known universe
# OOS target: Sharpe > 1.0 (lowered from H265 due to survivorship correction)
# Scaffold only — requires point-in-time constituent data
