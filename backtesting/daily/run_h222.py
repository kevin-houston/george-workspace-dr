"""
H222 — Quality Factor: Piotroski F-Score + Gross Profitability
==============================================================
Two quality signals from annual fundamentals via FMP API:

A. Piotroski F-Score (9-point binary checklist):
   - Profitability: ROA>0, CF>0, ΔROA>0, CF>accruals
   - Leverage/liquidity: ΔLeverage<0, ΔCurrentRatio>0, no dilution
   - Operating efficiency: ΔGross margin>0, ΔAsset turnover>0
   Long top-6 by F-Score, annual rebalance

B. Gross Profitability (Novy-Marx 2013):
   Signal = (Revenue - COGS) / Total Assets
   Long top-6 by GP/Assets, annual rebalance
   This single metric has near-equal power to full QMJ factor.

Data source: FMP API ($FMP_API_KEY)
Universe: same 30 large-cap stocks as H181/H192/H198
IS: 2010-2020 (needs annual data; start earlier for more IS obs)
OOS: 2021-2026
Annual rebalance: apply prior-year financials with 90-day reporting lag
  → fiscal year 2020 data available ~April 2021 → rebalance April
Confirm: OOS Sharpe > 0.7

Also measure correlation with H192-D BAB: if <0.5 → add to portfolio
"""

# TODO: implement
# 1. Fetch annual income/balance/cashflow from FMP for all 30 stocks
# 2. Compute F-Score and GP/Assets for each year
# 3. Apply annual rebalance with 90-day lag (April rebalance for prior-year data)
# 4. Compute monthly returns for top-6 portfolio
# 5. Measure OOS Sharpe and correlation with H192-D
pass
