"""
Step 3: Beta estimation with sector shrinkage.

For each (stock, event) pair, estimates:
  ret_i = α + β_mkt × ret_mkt + β_r × ΔDGS2 + ε

using a trailing 3-year window of announcement-day observations (min 40 obs).

Shrinkage:
  β_r_shrunk = w × β_r_raw + (1-w) × β_r_sector_mean
  w = n_obs / (n_obs + k),  k = 60 (tuned on training set only)

Outputs: betas.parquet with columns:
  stock, asof_date, beta_mkt, beta_r_raw, beta_r_shrunk, n_obs, sector
"""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LinearRegression

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

SHRINKAGE_K = 60       # tune on training data only
MIN_OBS = 40
LOOKBACK_EVENTS = 90   # roughly 3 years of events at ~30/yr


def compute_betas_for_events(
    events: pd.DataFrame,
    prices: pd.DataFrame,
    dgs2: pd.Series,
    spy_rets: pd.Series,
    universe: pd.DataFrame,
    k: float = SHRINKAGE_K,
) -> pd.DataFrame:
    """
    Compute as-of-date betas for each (stock, event) pair.

    events: must have columns [event_id, type, date_et]
    prices: wide DataFrame, date × ticker, adjusted close
    dgs2: Series of daily 2Y yield
    spy_rets: Series of daily SPY returns
    universe: DataFrame with ticker, sector columns
    """
    print("=== Step 3: Beta estimation ===")

    # Build daily DGS2 change
    dgs2_chg = dgs2.diff()  # daily bps change (in percentage points, not bps)

    # All past announcement dates (pooled across types)
    event_dates = sorted(events["date_et"].dt.normalize().unique())

    # Build returns DataFrame
    price_returns = prices.pct_change()

    # Sector mapping
    sector_map = universe.set_index("ticker")["sector"].to_dict()
    tickers = [t for t in prices.columns if t in sector_map]

    # Cache existing betas
    betas_cache = CACHE_DIR / "betas.parquet"
    if betas_cache.exists():
        existing = pd.read_parquet(betas_cache)
        existing_keys = set(zip(existing["stock"], existing["asof_date"].astype(str)))
    else:
        existing = pd.DataFrame()
        existing_keys = set()

    records = []
    n_events = len(events)

    for ei, ev_row in events.iterrows():
        asof_date = ev_row["date_et"].normalize()
        asof_str = str(asof_date.date())
        event_id = ev_row["event_id"]

        if ei % 20 == 0:
            print(f"  Event {ei+1}/{n_events}: {event_id}")

        # Announcement days in lookback window (strictly before asof_date)
        prior_event_dates = [d for d in event_dates
                             if pd.Timestamp(d) < asof_date]
        lookback_dates = prior_event_dates[-LOOKBACK_EVENTS:]
        if len(lookback_dates) < MIN_OBS:
            continue

        lb_dates = pd.DatetimeIndex(lookback_dates)

        # Market returns on those dates
        mkt_on_dates = spy_rets.reindex(lb_dates).dropna()
        dgs2_on_dates = dgs2_chg.reindex(lb_dates).dropna()
        common_dates = mkt_on_dates.index.intersection(dgs2_on_dates.index)
        if len(common_dates) < MIN_OBS:
            continue

        mkt_x = mkt_on_dates.loc[common_dates].values
        dgs2_x = dgs2_on_dates.loc[common_dates].values
        X = np.column_stack([mkt_x, dgs2_x])

        for ticker in tickers:
            key = (ticker, asof_str)
            if key in existing_keys:
                continue

            stock_rets = price_returns[ticker].reindex(common_dates).values

            # Skip if too many NaN
            valid = ~np.isnan(stock_rets)
            if valid.sum() < MIN_OBS:
                records.append({
                    "stock": ticker, "asof_date": asof_date, "event_id": event_id,
                    "beta_mkt": np.nan, "beta_r_raw": np.nan, "beta_r_shrunk": np.nan,
                    "n_obs": valid.sum(), "sector": sector_map.get(ticker, "Unknown"),
                })
                continue

            # OLS: ret_i = α + β_mkt × mkt + β_r × ΔDGS2 + ε
            X_valid = X[valid]
            y_valid = stock_rets[valid]
            try:
                reg = LinearRegression(fit_intercept=True)
                reg.fit(X_valid, y_valid)
                b_mkt = reg.coef_[0]
                b_r_raw = reg.coef_[1]
                n = valid.sum()
            except Exception:
                b_mkt, b_r_raw, n = np.nan, np.nan, 0

            records.append({
                "stock": ticker, "asof_date": asof_date, "event_id": event_id,
                "beta_mkt": b_mkt, "beta_r_raw": b_r_raw, "beta_r_shrunk": np.nan,
                "n_obs": n, "sector": sector_map.get(ticker, "Unknown"),
            })

    if not records:
        print("  No new betas to compute.")
        return existing if not existing.empty else pd.DataFrame(columns=[
            "stock", "asof_date", "event_id", "beta_mkt",
            "beta_r_raw", "beta_r_shrunk", "n_obs", "sector"
        ])

    new_df = pd.DataFrame(records)
    df = pd.concat([existing, new_df]).reset_index(drop=True) if not existing.empty else new_df

    # ── Shrinkage ──────────────────────────────────────────────────────────────
    df = apply_shrinkage(df, k=k)

    df.to_parquet(betas_cache, index=False)
    print(f"  Betas saved: {len(df)} rows")
    return df


def apply_shrinkage(df: pd.DataFrame, k: float = SHRINKAGE_K) -> pd.DataFrame:
    """
    Apply sector-mean shrinkage to β_r_raw.
    β_r_shrunk = w × β_r_raw + (1-w) × sector_mean
    w = n_obs / (n_obs + k)
    Computed separately for each (event_id, sector) group.
    """
    df = df.copy()
    df["beta_r_shrunk"] = np.nan

    for (event_id, sector), grp in df.groupby(["event_id", "sector"]):
        valid = grp["beta_r_raw"].notna() & (grp["n_obs"] >= MIN_OBS)
        sector_mean = grp.loc[valid, "beta_r_raw"].mean()
        if np.isnan(sector_mean):
            sector_mean = 0.0

        idx = grp.index
        n_obs = grp.loc[idx, "n_obs"].values
        b_raw = grp.loc[idx, "beta_r_raw"].values
        w = n_obs / (n_obs + k)
        shrunk = w * b_raw + (1 - w) * sector_mean
        df.loc[idx, "beta_r_shrunk"] = shrunk

    return df


def beta_rank_stability(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Spearman rank correlation of β_r_shrunk between adjacent events.
    Returns per-stock stability score. Spec guardrail: should be > 0.6.
    """
    from scipy.stats import spearmanr

    df = df.sort_values(["stock", "asof_date"])
    stability = []

    for ticker, grp in df.groupby("stock"):
        grp = grp.sort_values("asof_date").dropna(subset=["beta_r_shrunk"])
        if len(grp) < 10:
            continue
        betas = grp["beta_r_shrunk"].values
        rho, _ = spearmanr(betas[:-1], betas[1:])
        stability.append({"stock": ticker, "beta_rank_stability": rho, "n_events": len(grp)})

    result = pd.DataFrame(stability)
    if not result.empty:
        median_stab = result["beta_rank_stability"].median()
        low_stab = (result["beta_rank_stability"] < 0.6).mean()
        print(f"\nBeta rank stability:")
        print(f"  Median Spearman ρ: {median_stab:.3f} (spec guardrail: > 0.6)")
        print(f"  % stocks below 0.6: {100*low_stab:.1f}%")
        if median_stab < 0.6:
            print("  ⚠️  WARNING: Median beta stability below guardrail. Gap rankings may be noise.")
    return result


if __name__ == "__main__":
    from price_data import build_price_data
    from calendar_ingest import build_events_table

    data = build_price_data()
    events = build_events_table()
    events = events.dropna(subset=["actual", "consensus"])

    betas = compute_betas_for_events(
        events, data["prices"], data["dgs2"], data["spy_rets"], data["universe"]
    )
    stab = beta_rank_stability(betas)
    print(betas.describe())
