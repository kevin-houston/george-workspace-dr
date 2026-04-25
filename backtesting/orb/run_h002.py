"""
H002: ATR mode outperforms H/L mode in risk-off regimes (SPY below 200-day SMA).

Regime definition: SPY 200-day SMA (market-based) instead of USREC (too sparse).
risk-on  = SPY above 200d SMA
risk-off = SPY below 200d SMA (captures 2018 Q4, 2020 crash, 2022 bear market)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backtesting.orb.data import fetch_bars
from backtesting.orb.signals import generate_signals
from backtesting.orb.engine import simulate
from backtesting.orb.metrics import compute_metrics, print_metrics
from backtesting.orb.regime import tag_dataframe

SYMBOL = "QQQ"
IN_SAMPLE_START = "2016-01-01"
IN_SAMPLE_END = "2022-12-31"
STARTING_EQUITY = 25_000.0

print(f"Loading {SYMBOL} bars (cached)...")
bars = fetch_bars(SYMBOL, IN_SAMPLE_START, IN_SAMPLE_END)

print("Generating signals...")
_, signal_records = generate_signals(bars)

print("Simulating H/L and ATR modes...")
trades_hl = simulate(signal_records, bars, mode="hl", starting_equity=STARTING_EQUITY)
trades_atr = simulate(signal_records, bars, mode="atr", starting_equity=STARTING_EQUITY)

print("Tagging regimes (SPY 200-day SMA)...")
trades_hl = tag_dataframe(trades_hl, method="spy200")
trades_atr = tag_dataframe(trades_atr, method="spy200")

print(f"\nRegime distribution (H/L trades): {trades_hl['regime'].value_counts().to_dict()}")
print(f"Regime distribution (ATR trades): {trades_atr['regime'].value_counts().to_dict()}")

results = {}

for regime in ["risk-on", "risk-off"]:
    hl_grp = trades_hl[trades_hl["regime"] == regime]
    atr_grp = trades_atr[trades_atr["regime"] == regime]

    m_hl = compute_metrics(hl_grp, STARTING_EQUITY)
    m_atr = compute_metrics(atr_grp, STARTING_EQUITY)

    print_metrics(f"H002 — H/L mode | {regime}", m_hl)
    print_metrics(f"H002 — ATR mode | {regime}", m_atr)

    results[regime] = {"hl": m_hl, "atr": m_atr}

# H002 Verdict
print("\n" + "="*50)
print("H002 VERDICT")
print("="*50)

riskoff_hl = results.get("risk-off", {}).get("hl", {})
riskoff_atr = results.get("risk-off", {}).get("atr", {})

hl_sharpe = riskoff_hl.get("sharpe", 0)
atr_sharpe = riskoff_atr.get("sharpe", 0)
hl_trades = riskoff_hl.get("total_trades", 0)
atr_trades = riskoff_atr.get("total_trades", 0)
min_trades = min(hl_trades, atr_trades)

print(f"  Risk-off trades:  H/L={hl_trades}, ATR={atr_trades}")
print(f"  Sharpe(H/L):      {hl_sharpe}")
print(f"  Sharpe(ATR):      {atr_sharpe}")
diff = atr_sharpe - hl_sharpe
print(f"  ATR advantage:    {diff:+.3f}  (need ≥ +0.15 to confirm)")

if min_trades < 20:
    verdict = "INCONCLUSIVE — fewer than 20 risk-off trades"
elif diff >= 0.15:
    verdict = "CONFIRMED — ATR mode superior in risk-off regimes"
elif diff <= -0.15:
    verdict = "REJECTED — H/L mode equal or superior in risk-off regimes"
else:
    verdict = "INCONCLUSIVE — difference below threshold"

print(f"  Verdict:          {verdict}")

out_path = Path(__file__).parent / "hypotheses/results/H002.json"
with open(out_path, "w") as f:
    json.dump({"hypothesis": "H002", "regime_method": "SPY 200-day SMA",
               "results": results, "verdict": verdict}, f, indent=2, default=str)
print(f"\nResults saved to {out_path}")
