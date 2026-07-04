"""
Step 6: Portfolio simulation + cost model.

Run ONLY after IC is established (non-zero mean IC with t-stat ≥ 2.0).

Strategy:
  - Long bottom-decile gap / short top-decile (for "fade" direction, or reverse for "ride")
  - Equal weight within each leg
  - Hold to horizon (1d, 3d, or 5d)
  - Costs: 10 bps per side baseline; 25 bps stress case

Reports per config:
  - Net Sharpe (annualized from per-event returns)
  - MaxDrawdown
  - Per-event P&L distribution (mean, std, skew, 10th/90th pct)
  - Cumulative equity curve
"""

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

CACHE_DIR = Path(__file__).parent / "cache"
COST_BASELINE_BPS = 10   # per side
COST_STRESS_BPS = 25     # per side

TRAIN_END = "2023-12-31"
HOLDOUT_START = "2024-01-01"


def simulate_portfolio(
    gaps: pd.DataFrame,
    horizon: int,
    direction: str,
    z_filter: bool = False,
    events: pd.DataFrame | None = None,
    cost_bps: float = COST_BASELINE_BPS,
    decile_cutoff: float = 0.10,
    split: str = "train",
) -> dict:
    """
    Run equal-weight decile portfolio simulation for one config.

    Returns dict with equity_curve, per_event_rets, sharpe, max_dd, summary.
    """
    col = f"fwd_ret_{horizon}d"

    # Split
    if split == "train":
        gaps_s = gaps[gaps["event_date"] <= pd.Timestamp(TRAIN_END)].copy()
        if events is not None:
            events_s = events[events["date_et"] <= pd.Timestamp(TRAIN_END)].copy()
    else:
        gaps_s = gaps[gaps["event_date"] >= pd.Timestamp(HOLDOUT_START)].copy()
        if events is not None:
            events_s = events[events["date_et"] >= pd.Timestamp(HOLDOUT_START)].copy()

    if z_filter and events is not None:
        high_z = events_s[events_s["surprise_z"].abs() > 1]["event_id"].tolist()
        gaps_s = gaps_s[gaps_s["event_id"].isin(high_z)]

    valid = gaps_s[
        (~gaps_s["excluded"]) &
        (gaps_s["gap_rank_pct"].notna()) &
        (gaps_s[col].notna())
    ].copy()

    if valid.empty:
        return {}

    per_event_rets = []
    equity = [1.0]

    for event_id, grp in valid.groupby("event_id"):
        grp = grp.sort_values("gap_rank_pct")
        n = len(grp)
        if n < 20:
            continue

        cutoff_n = max(1, int(n * decile_cutoff))

        # Bottom decile (low gap = underreacted = "ride laggards")
        # Top decile (high gap = overreacted = "fade overshooters")
        bottom = grp.head(cutoff_n)
        top = grp.tail(cutoff_n)

        if direction == "fade":
            # Long bottom-decile gap (laggards), short top-decile (overshooters)
            long_ret = bottom[col].mean()
            short_ret = top[col].mean()
        else:
            # "ride": long top-decile, short bottom-decile
            long_ret = top[col].mean()
            short_ret = bottom[col].mean()

        # Gross P&L = long - short
        gross = long_ret - short_ret

        # Transaction costs: 2 sides × 2 legs = 4 × cost_bps per event
        total_cost = 4 * cost_bps / 10_000
        net = gross - total_cost

        per_event_rets.append({
            "event_id": event_id,
            "event_date": grp["event_date"].iloc[0],
            "event_type": grp["event_type"].iloc[0],
            "gross_ret": gross,
            "net_ret": net,
            "long_leg": long_ret,
            "short_leg": short_ret,
            "n_stocks": n,
        })
        equity.append(equity[-1] * (1 + net))

    if not per_event_rets:
        return {}

    ev_df = pd.DataFrame(per_event_rets)

    # Annualize: ~32 events/year pooled (NFP=12, CPI=12, FOMC=8)
    events_per_year = 32
    mean_ret = ev_df["net_ret"].mean()
    std_ret = ev_df["net_ret"].std(ddof=1)
    sharpe = (mean_ret / std_ret * np.sqrt(events_per_year)
              if std_ret > 0 else np.nan)

    # Max drawdown
    eq_series = pd.Series(equity)
    running_max = eq_series.cummax()
    dd = (eq_series - running_max) / running_max
    max_dd = dd.min()

    # Distribution
    dist = {
        "mean": round(mean_ret * 100, 3),      # %
        "std": round(std_ret * 100, 3),
        "skew": round(stats.skew(ev_df["net_ret"]), 3),
        "p10": round(ev_df["net_ret"].quantile(0.10) * 100, 3),
        "p90": round(ev_df["net_ret"].quantile(0.90) * 100, 3),
        "pct_positive": round((ev_df["net_ret"] > 0).mean(), 3),
    }

    summary = {
        "direction": direction,
        "horizon": horizon,
        "z_filter": z_filter,
        "cost_bps": cost_bps,
        "split": split,
        "n_events": len(ev_df),
        "sharpe_ann": round(sharpe, 3),
        "max_dd": round(max_dd, 4),
        "distribution": dist,
    }

    return {
        "per_event": ev_df,
        "equity_curve": pd.Series(equity),
        "summary": summary,
    }


def run_portfolio_sims(
    gaps: pd.DataFrame,
    events: pd.DataFrame,
    best_config: dict,
    horizons: list[int] = [1, 3, 5],
    split: str = "train",
) -> list[dict]:
    """
    Run portfolio simulations for the best training config at both cost levels.
    best_config: dict with keys direction, horizon, z_filter.
    """
    print(f"\n=== Step 6: Portfolio Simulation ({split}) ===")

    direction = best_config.get("direction", "fade")
    horizon = best_config.get("horizon", 3)
    z_filter = best_config.get("z_filter", False)

    results = []
    for cost_label, cost in [("baseline (10bps)", COST_BASELINE_BPS),
                              ("stress (25bps)", COST_STRESS_BPS)]:
        sim = simulate_portfolio(
            gaps, horizon, direction, z_filter=z_filter,
            events=events, cost_bps=cost, split=split
        )
        if sim:
            s = sim["summary"]
            print(f"\n  {cost_label}:")
            print(f"    Sharpe (ann): {s['sharpe_ann']}")
            print(f"    MaxDD:        {s['max_dd']:.2%}")
            print(f"    Mean ret/event: {s['distribution']['mean']:.3f}%")
            print(f"    Skew: {s['distribution']['skew']:.2f}, "
                  f"P10/P90: {s['distribution']['p10']:.2f}% / "
                  f"{s['distribution']['p90']:.2f}%")
            print(f"    % positive events: {s['distribution']['pct_positive']:.1%}")
            results.append(sim)

    return results


def holdout_evaluation(
    gaps: pd.DataFrame,
    events: pd.DataFrame,
    best_config: dict,
) -> dict:
    """
    Single holdout run. Called exactly once.
    Logs result to cache/holdout_result.json.
    """
    import json

    hold_cache = CACHE_DIR / "holdout_result.json"
    if hold_cache.exists():
        print("\n⚠️  Holdout already evaluated. Not re-running to preserve integrity.")
        return json.loads(hold_cache.read_text())

    print("\n=== HOLDOUT EVALUATION (single run) ===")
    from event_study import run_event_study

    # IC evaluation
    hold_results = run_event_study(gaps, events, split="holdout")
    sims = run_portfolio_sims(gaps, events, best_config, split="holdout")

    holdout_summary = {
        "best_config": best_config,
        "ic_results": {k: v["summary"] for k, v in hold_results.items()},
        "portfolio_results": [s["summary"] for s in sims] if sims else [],
    }

    hold_cache.write_text(json.dumps(holdout_summary, indent=2))
    print(f"\nHoldout result logged to {hold_cache}")
    return holdout_summary


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from event_study import run_event_study

    gaps = pd.read_parquet(CACHE_DIR / "gaps.parquet")
    events = pd.read_parquet(CACHE_DIR / "events.parquet")

    train_results = run_event_study(gaps, events, split="train")

    if train_results:
        # Pick best config by |t-stat|
        best = max(
            [v["summary"] for v in train_results.values()],
            key=lambda r: abs(r.get("t_stat", 0))
        )
        best_config = {
            "direction": best["direction"],
            "horizon": best["horizon"],
            "z_filter": "_zhigh" in best["label"],
        }
        run_portfolio_sims(gaps, events, best_config, split="train")
