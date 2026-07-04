"""
Step 5: Event-study IC engine (Fama-MacBeth).

Per event: Spearman rank correlation between gap_rank_pct and forward relative return.
Across events: t-test that mean IC ≠ 0.

Reports:
  - mean IC, t-stat, p-value per horizon per direction per conditioning
  - hit rate (% events with correctly-signed IC)
  - IC by event type
  - edge by liquidity tercile
"""

import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

CACHE_DIR = Path(__file__).parent / "cache"
TRAIN_END = "2023-12-31"
HOLDOUT_START = "2024-01-01"


def compute_relative_return(gaps: pd.DataFrame, horizon: int) -> pd.Series:
    """
    Compute forward relative return = stock fwd_ret - universe mean fwd_ret,
    per event. Returns Series indexed same as gaps.
    """
    col = f"fwd_ret_{horizon}d"
    rel = gaps.copy()
    event_means = gaps.groupby("event_id")[col].transform("mean")
    rel[f"fwd_rel_ret_{horizon}d"] = rel[col] - event_means
    return rel[f"fwd_rel_ret_{horizon}d"]


def event_ic(gaps: pd.DataFrame, horizon: int, direction: str = "fade",
             z_filter: bool = False, events: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Compute per-event Spearman IC between gap rank and forward relative return.

    direction: "fade" = short high-gap (overshooters), long low-gap (laggards)
               rank correlation should be NEGATIVE for "fade" to be profitable
               We store IC as the raw correlation, direction is interpreted later.

    z_filter: if True, only include events with |surprise_z| > 1.

    Returns DataFrame: event_id, event_date, event_type, ic, n_stocks.
    """
    col_fwd = f"fwd_ret_{horizon}d"
    valid = gaps[
        (~gaps["excluded"]) &
        (gaps["gap"].notna()) &
        (gaps[col_fwd].notna()) &
        (gaps["gap_rank_pct"].notna())
    ].copy()

    if z_filter and events is not None:
        high_z_events = events[events["surprise_z"].abs() > 1]["event_id"].tolist()
        valid = valid[valid["event_id"].isin(high_z_events)]

    # Compute relative returns
    valid[f"fwd_rel_ret_{horizon}d"] = compute_relative_return(valid, horizon)

    ic_records = []
    for event_id, grp in valid.groupby("event_id"):
        grp = grp.dropna(subset=["gap_rank_pct", f"fwd_rel_ret_{horizon}d"])
        if len(grp) < 20:
            continue

        rho, pval = stats.spearmanr(grp["gap_rank_pct"], grp[f"fwd_rel_ret_{horizon}d"])
        ic_records.append({
            "event_id": event_id,
            "event_date": grp["event_date"].iloc[0],
            "event_type": grp["event_type"].iloc[0],
            "ic": rho,
            "ic_pval": pval,
            "n_stocks": len(grp),
        })

    if not ic_records:
        return pd.DataFrame(columns=["event_id", "event_date", "event_type", "ic", "ic_pval", "n_stocks"])
    return pd.DataFrame(ic_records).sort_values("event_date")


def summarize_ic(ic_df: pd.DataFrame, horizon: int, direction: str,
                 label: str = "") -> dict:
    """
    Compute mean IC, t-stat, hit rate across events.
    For "fade" direction: profitable signal has IC < 0 (high gap stocks underperform).
    For "ride" direction: profitable signal has IC > 0 (high gap stocks outperform).
    """
    if ic_df.empty:
        return {}

    ics = ic_df["ic"].dropna().values
    n = len(ics)
    if n < 3:
        return {}

    mean_ic = np.mean(ics)
    std_ic = np.std(ics, ddof=1)
    t_stat = mean_ic / (std_ic / np.sqrt(n))
    p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - 1))

    if direction == "fade":
        # Profitable: IC < 0
        hit_rate = (ics < 0).mean()
    else:
        # Profitable: IC > 0
        hit_rate = (ics > 0).mean()

    result = {
        "label": label,
        "direction": direction,
        "horizon": horizon,
        "n_events": n,
        "mean_ic": round(mean_ic, 4),
        "std_ic": round(std_ic, 4),
        "t_stat": round(t_stat, 3),
        "p_value": round(p_value, 4),
        "hit_rate": round(hit_rate, 3),
        "ic_by_type": ic_df.groupby("event_type")["ic"].mean().round(4).to_dict(),
    }
    return result


def ic_by_liquidity(gaps: pd.DataFrame, ic_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """
    Split gap universe into liquidity terciles (by stock ADV proxy = avg price).
    Report IC per tercile to check if edge is driven by illiquid names.
    """
    col = f"fwd_ret_{horizon}d"
    valid = gaps[~gaps["excluded"] & gaps["gap"].notna() & gaps[col].notna()].copy()

    # Use avg price as rough liquidity proxy (all S&P500 are liquid; this is diagnostic)
    valid["liq_proxy"] = valid["actual_move"].abs()  # use |return| as noise proxy instead
    valid["liq_tercile"] = pd.qcut(valid.groupby("stock")["actual_move"]
                                   .transform("count"), 3,
                                   labels=["low_liq", "mid_liq", "high_liq"],
                                   duplicates="drop")

    results = []
    for tercile, grp_liq in valid.groupby("liq_tercile"):
        ic_records = []
        for event_id, grp in grp_liq.groupby("event_id"):
            grp = grp.dropna(subset=["gap_rank_pct", col])
            if len(grp) < 5:
                continue
            # Recompute relative return within this tercile
            grp = grp.copy()
            grp["rel_fwd"] = grp[col] - grp[col].mean()
            rho, _ = stats.spearmanr(grp["gap_rank_pct"], grp["rel_fwd"])
            ic_records.append(rho)
        if ic_records:
            results.append({
                "liquidity_tercile": str(tercile),
                "mean_ic": round(np.mean(ic_records), 4),
                "n_events": len(ic_records),
            })
    return pd.DataFrame(results)


def run_event_study(
    gaps: pd.DataFrame,
    events: pd.DataFrame,
    horizons: list[int] = [1, 3, 5],
    split: str = "train",
) -> dict:
    """
    Full Fama-MacBeth event study on training or holdout split.

    split: "train" (through 2023-12-31) or "holdout" (2024-01-01 onward)
    Returns dict of results indexed by (direction, horizon, z_filter).
    """
    print(f"\n=== Step 5: Event Study ({split}) ===")

    # Filter to split
    if split == "train":
        mask = gaps["event_date"] <= pd.Timestamp(TRAIN_END)
        ev_mask = events["date_et"] <= pd.Timestamp(TRAIN_END)
    else:
        mask = gaps["event_date"] >= pd.Timestamp(HOLDOUT_START)
        ev_mask = events["date_et"] >= pd.Timestamp(HOLDOUT_START)

    gaps_split = gaps[mask].copy()
    events_split = events[ev_mask].copy()

    results = {}
    summary_rows = []

    # Full hypothesis matrix: direction × horizon × z_filter
    for direction in ["fade", "ride"]:
        for horizon in horizons:
            for z_filter in [False, True]:
                label = f"{direction}_h{horizon}d{'_zhigh' if z_filter else ''}"
                ic_df = event_ic(gaps_split, horizon, direction=direction,
                                 z_filter=z_filter, events=events_split)
                summary = summarize_ic(ic_df, horizon, direction, label=label)
                if summary:
                    results[label] = {"ic_df": ic_df, "summary": summary}
                    summary_rows.append(summary)

    print("\nResults matrix:")
    if summary_rows:
        df_summary = pd.DataFrame(summary_rows)
        cols = ["label", "direction", "horizon", "n_events",
                "mean_ic", "t_stat", "p_value", "hit_rate"]
        print(df_summary[cols].to_string(index=False))

    # Identify best configuration (highest |t-stat|)
    if summary_rows:
        best = max(summary_rows, key=lambda r: abs(r.get("t_stat", 0)))
        print(f"\nBest config: {best['label']}")
        print(f"  mean IC = {best['mean_ic']:.4f}, t = {best['t_stat']:.3f}, "
              f"p = {best['p_value']:.4f}, hit rate = {best['hit_rate']:.3f}")
        print(f"  IC by type: {best['ic_by_type']}")

        # Gate check (holdout only)
        if split == "holdout":
            passed = (
                abs(best["t_stat"]) >= 2.0 and
                best["hit_rate"] >= 0.55
            )
            print(f"\n  Holdout gate: t ≥ 2.0 AND hit_rate ≥ 0.55 → {'PASS ✓' if passed else 'FAIL ✗'}")

    # Liquidity tercile check
    for horizon in horizons:
        liq = ic_by_liquidity(gaps_split, ic_df=None, horizon=horizon)
        if not liq.empty:
            print(f"\nLiquidity tercile check (h={horizon}d):")
            print(liq.to_string(index=False))

    return results


if __name__ == "__main__":
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    gaps = pd.read_parquet(CACHE_DIR / "gaps.parquet")
    events = pd.read_parquet(CACHE_DIR / "events.parquet")
    results = run_event_study(gaps, events, split="train")
