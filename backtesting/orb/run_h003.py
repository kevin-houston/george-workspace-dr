"""
H003: ORB edge is leverage-dependent — TQQQ > QQQ > SPY by Sharpe.

Tests ATR-mode exits (winner from H001) on all three assets, same period.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backtesting.orb.data import fetch_bars
from backtesting.orb.signals import generate_signals
from backtesting.orb.engine import simulate
from backtesting.orb.metrics import compute_metrics, print_metrics

IN_SAMPLE_START = "2016-01-01"
IN_SAMPLE_END = "2022-12-31"
STARTING_EQUITY = 25_000.0

assets = ["SPY", "QQQ", "TQQQ"]
results = {}

for symbol in assets:
    print(f"\nProcessing {symbol}...")
    bars = fetch_bars(symbol, IN_SAMPLE_START, IN_SAMPLE_END)
    _, signal_records = generate_signals(bars)

    trades_atr = simulate(signal_records, bars, mode="atr", starting_equity=STARTING_EQUITY)
    trades_hl = simulate(signal_records, bars, mode="hl", starting_equity=STARTING_EQUITY)

    m_atr = compute_metrics(trades_atr, STARTING_EQUITY)
    m_hl = compute_metrics(trades_hl, STARTING_EQUITY)

    print_metrics(f"H003 — ATR mode | {symbol}", m_atr)
    print_metrics(f"H003 — H/L mode | {symbol}", m_hl)

    results[symbol] = {"atr": m_atr, "hl": m_hl}

# H003 Verdict
print("\n" + "="*50)
print("H003 VERDICT")
print("="*50)

sharpes = {s: results[s]["atr"].get("sharpe", 0) for s in assets}
trades_ok = all(results[s]["atr"].get("total_trades", 0) >= 200 for s in assets)

print(f"  ATR Sharpe — SPY: {sharpes['SPY']}  QQQ: {sharpes['QQQ']}  TQQQ: {sharpes['TQQQ']}")
print(f"  Trade counts OK (≥200): {trades_ok}")

if not trades_ok:
    low = [s for s in assets if results[s]["atr"].get("total_trades", 0) < 200]
    verdict = f"INCONCLUSIVE — fewer than 200 trades for: {low}"
elif sharpes["TQQQ"] > sharpes["QQQ"] > sharpes["SPY"]:
    verdict = "CONFIRMED — edge increases with leverage as predicted"
elif sharpes["TQQQ"] > sharpes["QQQ"] or sharpes["QQQ"] > sharpes["SPY"]:
    verdict = "PARTIALLY CONFIRMED — leverage helps but order not strict"
else:
    verdict = "REJECTED — leverage does not monotonically improve Sharpe"

print(f"  Verdict:  {verdict}")

out_path = Path(__file__).parent / "hypotheses/results/H003.json"
with open(out_path, "w") as f:
    json.dump({"hypothesis": "H003", "mode": "atr",
               "results": results, "verdict": verdict}, f, indent=2, default=str)
print(f"\nResults saved to {out_path}")
