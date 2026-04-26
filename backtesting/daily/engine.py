"""Vectorized daily backtester."""

import numpy as np
import pandas as pd

from .metrics import compute_metrics


class DailyBacktester:
    def __init__(
        self,
        prices: pd.DataFrame,
        signals: pd.DataFrame,
        starting_equity: float = 100_000.0,
        slippage_bps: float = 10.0,
        tax_rate_stcg: float = 0.37,
        tax_rate_ltcg: float = 0.20,
        ltcg_threshold_days: int = 252,
    ):
        """
        prices: daily close prices, DatetimeIndex × symbols.
        signals: daily target weights, DatetimeIndex × symbols (aligned to prices).
               Weights executed at NEXT day's open (approx next day's close ± slippage).
        """
        if isinstance(signals, pd.Series):
            signals = signals.to_frame()

        # Align on common dates
        common = prices.index.intersection(signals.index)
        self.prices = prices.loc[common]
        self.signals = signals.loc[common].reindex(columns=prices.columns, fill_value=0.0)
        self.starting_equity = starting_equity
        self.slippage_bps = slippage_bps
        self.tax_rate_stcg = tax_rate_stcg
        self.tax_rate_ltcg = tax_rate_ltcg
        self.ltcg_threshold_days = ltcg_threshold_days
        self._equity_curve: pd.Series | None = None
        self._trades: pd.DataFrame | None = None

    def run(self) -> tuple[pd.Series, pd.DataFrame]:
        """Run backtest. Returns (equity_curve, trades_df)."""
        prices = self.prices
        signals = self.signals
        slip = self.slippage_bps / 10_000

        n = len(prices)
        equity = self.starting_equity
        equity_values = [equity]

        # Track open positions: symbol → {entry_price, weight, date_in, shares}
        open_positions: dict[str, dict] = {}
        trades: list[dict] = []

        # signals[t] → executed on day t+1
        prev_weights: dict[str, float] = {}

        for i in range(1, n):
            today = prices.index[i]
            today_prices = prices.iloc[i]

            target_weights = signals.iloc[i - 1]  # signal from previous day

            # Determine rebalance: symbols entering, exiting, or changing weight
            current_syms = set(sym for sym, w in prev_weights.items() if w > 0)
            target_syms = set(sym for sym in target_weights.index if target_weights[sym] > 1e-9)

            exit_syms = current_syms - target_syms
            entry_syms = target_syms - current_syms
            rebal_syms = current_syms & target_syms

            # Exit positions
            for sym in exit_syms:
                if sym not in open_positions:
                    continue
                pos = open_positions.pop(sym)
                exit_price = today_prices.get(sym, np.nan)
                if np.isnan(exit_price):
                    continue
                exit_price_adj = exit_price * (1 - slip)
                pnl = (exit_price_adj - pos["entry_price"]) * pos["shares"]
                hold_days = (today - pos["date_in"]).days
                trades.append({
                    "date_in": pos["date_in"],
                    "date_out": today,
                    "symbol": sym,
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price_adj,
                    "shares": pos["shares"],
                    "pnl": pnl,
                    "hold_days": hold_days,
                })
                equity += pnl

            # Rebalance existing positions (close and reopen at new size)
            for sym in rebal_syms:
                new_w = target_weights[sym]
                old_w = prev_weights.get(sym, 0.0)
                if abs(new_w - old_w) < 1e-6:
                    continue
                if sym not in open_positions:
                    continue
                pos = open_positions.pop(sym)
                exit_price = today_prices.get(sym, np.nan)
                if np.isnan(exit_price):
                    continue
                exit_price_adj = exit_price * (1 - slip)
                pnl = (exit_price_adj - pos["entry_price"]) * pos["shares"]
                hold_days = (today - pos["date_in"]).days
                trades.append({
                    "date_in": pos["date_in"],
                    "date_out": today,
                    "symbol": sym,
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price_adj,
                    "shares": pos["shares"],
                    "pnl": pnl,
                    "hold_days": hold_days,
                })
                equity += pnl
                # Reopen with new weight
                entry_price_adj = exit_price * (1 + slip)
                shares = (equity * new_w) / entry_price_adj
                open_positions[sym] = {
                    "entry_price": entry_price_adj,
                    "shares": shares,
                    "date_in": today,
                    "weight": new_w,
                }

            # Open new positions
            for sym in entry_syms:
                entry_price = today_prices.get(sym, np.nan)
                if np.isnan(entry_price):
                    continue
                w = target_weights[sym]
                entry_price_adj = entry_price * (1 + slip)
                shares = (equity * w) / entry_price_adj
                open_positions[sym] = {
                    "entry_price": entry_price_adj,
                    "shares": shares,
                    "date_in": today,
                    "weight": w,
                }

            prev_weights = {sym: target_weights[sym] for sym in target_weights.index}

            # Mark-to-market equity: cash + market value of open positions
            mtm_equity = equity
            for sym, pos in open_positions.items():
                current_price = today_prices.get(sym, np.nan)
                if not np.isnan(current_price):
                    mtm_equity += (current_price - pos["entry_price"]) * pos["shares"]

            equity_values.append(mtm_equity)

        # Close all remaining positions at last price
        last_prices = prices.iloc[-1]
        last_date = prices.index[-1]
        for sym, pos in open_positions.items():
            exit_price = last_prices.get(sym, np.nan)
            if np.isnan(exit_price):
                continue
            exit_price_adj = exit_price * (1 - slip)
            pnl = (exit_price_adj - pos["entry_price"]) * pos["shares"]
            hold_days = (last_date - pos["date_in"]).days
            trades.append({
                "date_in": pos["date_in"],
                "date_out": last_date,
                "symbol": sym,
                "entry_price": pos["entry_price"],
                "exit_price": exit_price_adj,
                "shares": pos["shares"],
                "pnl": pnl,
                "hold_days": hold_days,
            })

        self._equity_curve = pd.Series(equity_values, index=prices.index, name="equity")
        self._trades = pd.DataFrame(trades) if trades else pd.DataFrame(
            columns=["date_in", "date_out", "symbol", "entry_price", "exit_price", "shares", "pnl", "hold_days"]
        )
        return self._equity_curve, self._trades

    def metrics(self) -> dict:
        if self._equity_curve is None:
            self.run()
        return compute_metrics(self._equity_curve, self._trades)
