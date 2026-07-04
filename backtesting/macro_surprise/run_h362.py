"""
H362 — Macro Surprise Mispricing Strategy
==========================================
Source: Kevin Houston build spec (2026-07-03)

Hypothesis:
  Scheduled macro releases (NFP, CPI, FOMC) reprice the 2Y yield instantly,
  but individual stocks reprice against their rate sensitivity unevenly.
  The cross-sectional gap between actual and predicted stock moves on event days
  predicts forward relative returns over 1–5 trading days.

Build order (per spec §9):
  1. Calendar ingestion + surprise table
  2. Price/yield ingestion
  3. Beta estimation (shrinkage)
  4. Gap computation
  5. Event-study IC engine
  6. Portfolio simulation
  7. Holdout evaluation (single run, spec §6 protocol)

IS:  through 2023-12-31
OOS: 2024-01-01 → present (touched exactly once, per winning config)

Gate (holdout): t-stat ≥ 2.0 AND hit_rate ≥ 55%
"""

import sys
import json
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
CACHE = BASE / "cache"
CACHE.mkdir(exist_ok=True)

from calendar_ingest import build_events_table
from price_data import build_price_data
from beta_module import compute_betas_for_events, beta_rank_stability
from gap_engine import build_gaps_table
from event_study import run_event_study
from portfolio_sim import run_portfolio_sims, holdout_evaluation


def load_or_build(path: Path, builder, *args, **kwargs):
    """Load cached parquet or rebuild."""
    if path.exists():
        print(f"  Loading cached {path.name}...")
        return pd.read_parquet(path)
    print(f"  Building {path.name}...")
    return builder(*args, **kwargs)


def main(run_holdout: bool = False):
    print("=" * 70)
    print("H362 — Macro Surprise Mispricing Backtest")
    print("=" * 70)

    # ── Step 1: Calendar ──────────────────────────────────────────────────────
    events = load_or_build(
        CACHE / "events.parquet",
        build_events_table,
        start_year=2010, end_year=2026, verify_alfred=False
    )
    events = events.dropna(subset=["actual", "consensus", "surprise"])
    print(f"\nEvents loaded: {len(events)} ({events.groupby('type').size().to_dict()})")

    # ── Step 2: Price/yield ────────────────────────────────────────────────────
    price_data = build_price_data(start="2007-01-01")

    # ── Step 3: Betas ─────────────────────────────────────────────────────────
    betas = load_or_build(
        CACHE / "betas.parquet",
        compute_betas_for_events,
        events, price_data["prices"], price_data["dgs2"],
        price_data["spy_rets"], price_data["universe"]
    )

    # Beta rank stability guardrail
    stab = beta_rank_stability(betas)
    if not stab.empty:
        median_stab = stab["beta_rank_stability"].median()
        if median_stab < 0.6:
            print(f"\n⚠️  GUARDRAIL: Median beta stability {median_stab:.3f} < 0.6")
            print("   Gap rankings are potentially noise. Proceed with caution.")

    # ── Step 4: Gaps ──────────────────────────────────────────────────────────
    gaps = load_or_build(
        CACHE / "gaps.parquet",
        build_gaps_table,
        events, betas, price_data["prices"], price_data["dgs2"],
        price_data["spy_rets"], price_data["earnings"]
    )

    # ── Step 5: Event study (training set) ────────────────────────────────────
    train_results = run_event_study(gaps, events, horizons=[1, 3, 5], split="train")

    if not train_results:
        print("\nNo IC results computed. Check data quality.")
        return

    # Select best config by |t-stat| on training set
    summaries = [v["summary"] for v in train_results.values()]
    best = max(summaries, key=lambda r: abs(r.get("t_stat", 0)))
    best_config = {
        "direction": best["direction"],
        "horizon": best["horizon"],
        "z_filter": "_zhigh" in best["label"],
    }

    print(f"\n{'='*50}")
    print(f"BEST TRAINING CONFIG: {best['label']}")
    print(f"  mean IC = {best['mean_ic']:.4f}")
    print(f"  t-stat  = {best['t_stat']:.3f}  (gate: ≥ 2.0 on holdout)")
    print(f"  hit_rate = {best['hit_rate']:.1%}  (gate: ≥ 55% on holdout)")
    print(f"  IC by type: {best['ic_by_type']}")

    # Training IC must be plausibly non-zero before touching holdout
    if abs(best["t_stat"]) < 1.5:
        print("\n⚠️  Training t-stat < 1.5. No signal in training data.")
        print("   Holdout evaluation would be wasteful. Stopping here.")
        print("   H362: NOT CONFIRMED (no training signal)")
        return

    # ── Step 6: Portfolio simulation (training) ────────────────────────────────
    run_portfolio_sims(gaps, events, best_config, split="train")

    # ── Step 7: Holdout (single run, gated) ───────────────────────────────────
    if run_holdout:
        hold = holdout_evaluation(gaps, events, best_config)
        # Interpret
        if hold.get("ic_results"):
            best_hold = max(
                hold["ic_results"].values(),
                key=lambda r: abs(r.get("t_stat", 0))
            )
            t = best_hold.get("t_stat", 0)
            hr = best_hold.get("hit_rate", 0)
            passed = abs(t) >= 2.0 and hr >= 0.55
            print(f"\n{'='*50}")
            print(f"HOLDOUT RESULT: {'PASS ✓' if passed else 'FAIL ✗'}")
            print(f"  t-stat = {t:.3f}, hit_rate = {hr:.1%}")
            if passed:
                print("  H362: CONFIRMED — proceed to paper trading (2 full cycles per event type)")
            else:
                print("  H362: NOT CONFIRMED — holdout failed, no re-tuning permitted")
    else:
        print("\n⚠️  Holdout not run (--holdout flag not set).")
        print("   Review training results, then run with --holdout to evaluate.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="H362 Macro Surprise Mispricing Backtest")
    parser.add_argument(
        "--holdout", action="store_true",
        help="Run holdout evaluation (single use — irreversible per overfitting protocol)"
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Force rebuild of all cached data files"
    )
    args = parser.parse_args()

    if args.rebuild:
        import shutil
        for f in CACHE.glob("*.parquet"):
            f.unlink()
        print("Cache cleared.")

    main(run_holdout=args.holdout)
