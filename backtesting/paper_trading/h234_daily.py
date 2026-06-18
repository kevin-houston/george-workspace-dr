#!/usr/bin/env python3
"""
H234 Daily — Inside-Bar Coiled Spring (STUB)

Strategy confirmed: OOS Sharpe 1.770 (strongest single-strategy confirmed).
Pattern: daily inside-bar on S&P 500 stocks. Entry: gap-up next day above prior high.

Status: stub — implementation in progress.
$5k virtual account allocated in strategy_equity ("H234").

Usage:
    python3 h234_daily.py            # live run (currently no-op)
    python3 h234_daily.py --status   # show account status
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import strategy_equity as se

STRATEGY_ID = "H234"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    strat_equity = se.current_equity(STRATEGY_ID)
    print(f"\nH234 Inside-Bar Coiled Spring — {date.today()}")
    print(f"Status: STUB (not yet implemented)")
    print(f"H234 strategy equity: ${strat_equity:,.2f}  (cash: ${se.get_cash(STRATEGY_ID):,.2f})")
    print(f"Backtest OOS Sharpe: 1.770 (strongest confirmed)")
    print(f"\nImplementation checklist:")
    print(f"  [ ] Daily scanner: identify inside-bar candles across S&P 500 universe")
    print(f"  [ ] Pre-market: filter candidates with gap > prior high")
    print(f"  [ ] Entry at open with market order, sized from H234 strategy equity")
    print(f"  [ ] Exit: trailing stop or N-day time exit")


if __name__ == "__main__":
    main()
