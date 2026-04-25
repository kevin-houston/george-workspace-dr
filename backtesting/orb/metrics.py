"""
Performance metrics for backtest results.
"""

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame, starting_equity: float = 25_000.0) -> dict:
    if trades.empty:
        return {"error": "no trades"}

    equity_curve = trades["equity"]
    net_pnl = trades["net_pnl"]

    # Daily returns
    trades = trades.copy()
    trades["prev_equity"] = trades["equity"].shift(1).fillna(starting_equity)
    trades["ret"] = trades["net_pnl"] / trades["prev_equity"]

    total_trades = len(trades)
    winners = trades[trades["net_pnl"] > 0]
    losers = trades[trades["net_pnl"] <= 0]

    win_rate = len(winners) / total_trades if total_trades > 0 else 0

    avg_win = winners["net_pnl"].mean() if len(winners) > 0 else 0
    avg_loss = losers["net_pnl"].mean() if len(losers) > 0 else 0
    profit_factor = (winners["net_pnl"].sum() / abs(losers["net_pnl"].sum())
                     if len(losers) > 0 and losers["net_pnl"].sum() != 0 else float("inf"))

    # Sharpe (annualized, assuming ~252 trading days)
    mean_ret = trades["ret"].mean()
    std_ret = trades["ret"].std()
    sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0

    # Max drawdown
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_drawdown = drawdown.min()

    # Calmar ratio
    total_return = (equity_curve.iloc[-1] - starting_equity) / starting_equity
    years = total_trades / 252
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0

    exit_counts = trades["exit_reason"].value_counts().to_dict()

    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 3),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_drawdown, 4),
        "calmar": round(calmar, 3),
        "total_return": round(total_return, 4),
        "annualized_return": round(annualized_return, 4),
        "final_equity": round(equity_curve.iloc[-1], 2),
        "exit_breakdown": exit_counts,
    }


def print_metrics(label: str, m: dict):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    if "error" in m:
        print(f"  ERROR: {m['error']}")
        return
    print(f"  Trades:          {m['total_trades']}")
    print(f"  Win rate:        {m['win_rate']:.1%}")
    print(f"  Avg win/loss:    ${m['avg_win']:.0f} / ${m['avg_loss']:.0f}")
    print(f"  Profit factor:   {m['profit_factor']:.2f}")
    print(f"  Sharpe:          {m['sharpe']:.3f}")
    print(f"  Max drawdown:    {m['max_drawdown']:.1%}")
    print(f"  Calmar:          {m['calmar']:.3f}")
    print(f"  Total return:    {m['total_return']:.1%}")
    print(f"  Ann. return:     {m['annualized_return']:.1%}")
    print(f"  Final equity:    ${m['final_equity']:,.0f}")
    print(f"  Exit breakdown:  {m['exit_breakdown']}")
