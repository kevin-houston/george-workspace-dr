"""
Run H001: ORB H/L mode vs ATR mode on QQQ, in-sample 2016-2022.
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

print(f"Fetching {SYMBOL} 1-min bars {IN_SAMPLE_START} → {IN_SAMPLE_END}...")
bars = fetch_bars(SYMBOL, IN_SAMPLE_START, IN_SAMPLE_END)
print(f"  {len(bars):,} bars loaded")

print("Generating ORB signals...")
signals_df, signal_records = generate_signals(bars)
total_signals = len(signals_df[signals_df["signal"] != 0])
print(f"  {len(signals_df)} trading days, {total_signals} signals")

print("\nRunning H/L mode simulation...")
trades_hl = simulate(signal_records, bars, mode="hl", starting_equity=STARTING_EQUITY)
trades_hl = tag_dataframe(trades_hl)

print("Running ATR mode simulation...")
trades_atr = simulate(signal_records, bars, mode="atr", starting_equity=STARTING_EQUITY)
trades_atr = tag_dataframe(trades_atr)

m_hl = compute_metrics(trades_hl, STARTING_EQUITY)
m_atr = compute_metrics(trades_atr, STARTING_EQUITY)

print_metrics("H001 — H/L mode (QQQ in-sample 2016-2022)", m_hl)
print_metrics("H001 — ATR mode (QQQ in-sample 2016-2022)", m_atr)

# Regime breakdown
for mode_label, trades in [("hl", trades_hl), ("atr", trades_atr)]:
    print(f"\n--- {mode_label.upper()} mode by regime ---")
    for regime, grp in trades.groupby("regime"):
        m = compute_metrics(grp, STARTING_EQUITY)
        print(f"  {regime}: trades={m['total_trades']}, sharpe={m['sharpe']}, "
              f"win_rate={m['win_rate']:.1%}, drawdown={m['max_drawdown']:.1%}")

# Save results
results = {
    "hypothesis": "H001",
    "symbol": SYMBOL,
    "period": f"{IN_SAMPLE_START} to {IN_SAMPLE_END}",
    "hl_mode": m_hl,
    "atr_mode": m_atr,
}

out_path = Path(__file__).parent / "hypotheses/results/H001.json"
out_path.parent.mkdir(exist_ok=True)
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)

print(f"\nResults saved to {out_path}")

# H001 verdict
print("\n" + "="*50)
print("H001 VERDICT")
print("="*50)
sharpe_diff = m_hl["sharpe"] - m_atr["sharpe"]
dd_hl = m_hl["max_drawdown"]
dd_atr = m_atr["max_drawdown"]

if (sharpe_diff >= 0.2
        and dd_hl >= dd_atr  # hl drawdown ≤ atr drawdown (less negative = better)
        and abs(m_hl["win_rate"] - m_atr["win_rate"]) < 0.10
        and m_hl["total_trades"] >= 200):
    verdict = "CONFIRMED"
elif m_atr["sharpe"] >= m_hl["sharpe"] or sharpe_diff < -0.01:
    verdict = "REJECTED — ATR mode equal or superior"
elif m_hl["total_trades"] < 200:
    verdict = "INCONCLUSIVE — insufficient trades"
else:
    verdict = "INCONCLUSIVE — criteria partially met"

print(f"  Sharpe(H/L): {m_hl['sharpe']}  |  Sharpe(ATR): {m_atr['sharpe']}")
print(f"  Difference:  {sharpe_diff:+.3f}  (need ≥ +0.200 to confirm)")
print(f"  Verdict:     {verdict}")
