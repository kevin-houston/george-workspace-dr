"""Performance metrics for daily backtest results."""

import numpy as np
import pandas as pd


def compute_metrics(
    equity_curve: pd.Series,
    trades: pd.DataFrame,
    risk_free_rate: float = 0.05,
) -> dict:
    """Return dict of performance metrics including after-tax return."""
    if equity_curve.empty or len(equity_curve) < 2:
        return {"error": "insufficient data"}

    daily_returns = equity_curve.pct_change().dropna()
    n_days = len(daily_returns)
    years = n_days / 252

    total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

    excess = daily_returns - risk_free_rate / 252
    sharpe = (excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0.0

    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_drawdown = drawdown.min()

    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    total_trades = len(trades)
    win_rate = 0.0
    avg_hold_days = 0.0

    if total_trades > 0:
        win_rate = (trades["pnl"] > 0).mean()
        avg_hold_days = trades["hold_days"].mean() if "hold_days" in trades.columns else 0.0

    # Tax: apply STCG if avg hold < 252 days, else LTCG
    if avg_hold_days < 252:
        tax_rate = 0.37
        tax_label = "STCG"
    else:
        tax_rate = 0.20
        tax_label = "LTCG"

    after_tax_return = annualized_return * (1 - tax_rate)

    return {
        "annualized_return": round(annualized_return, 4),
        "after_tax_return": round(after_tax_return, 4),
        "tax_label": tax_label,
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_drawdown, 4),
        "calmar": round(calmar, 3),
        "total_return": round(total_return, 4),
        "win_rate": round(win_rate, 4),
        "total_trades": total_trades,
        "avg_hold_days": round(avg_hold_days, 1),
        "final_equity": round(equity_curve.iloc[-1], 2),
    }


def print_metrics(label: str, m: dict):
    print(f"\n{'='*52}")
    print(f"  {label}")
    print(f"{'='*52}")
    if "error" in m:
        print(f"  ERROR: {m['error']}")
        return
    print(f"  Ann. return:      {m['annualized_return']:.2%}")
    print(f"  After-tax return: {m['after_tax_return']:.2%}  ({m['tax_label']})")
    print(f"  Sharpe:           {m['sharpe']:.3f}")
    print(f"  Max drawdown:     {m['max_drawdown']:.2%}")
    print(f"  Calmar:           {m['calmar']:.3f}")
    print(f"  Total return:     {m['total_return']:.2%}")
    print(f"  Win rate:         {m['win_rate']:.1%}")
    print(f"  Total trades:     {m['total_trades']}")
    print(f"  Avg hold days:    {m['avg_hold_days']:.1f}")
    print(f"  Final equity:     ${m['final_equity']:,.0f}")
