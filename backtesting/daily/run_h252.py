"""
H252 — Berry Phase Rate Early-Warning Regime Detector
======================================================
Source: arXiv:2605.17117 (Hammond, May 2026)
  'Geometric Observables for Financial Regime Detection'
  Berry Phase Rate (BPR) = angular velocity of principal eigenvector of
  rolling return correlation matrix. High BPR = rapid structural change
  in market correlations = early warning of regime shift.

Paper claims:
  - Median OOS Cohen's d = 0.72 on labeled crisis windows
  - 67% fewer false alarms vs supervised RF (1.2 vs 3.6/year)
  - Mean |rho| ≈ 0.22 with classical signals (VIX, 200MA) — independent

Confirm gates:
  - OOS AUC > 0.65 on labeled crisis windows
  - Corr(BPR_z, VIX) < 0.30

Assets: SPY, TLT, GLD daily log returns, window=90 days
IS: 2000-2017  |  OOS: 2018-2026
"""

import os
import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# 1. Download price data
# ─────────────────────────────────────────────
print("Downloading price data...")
tickers = ["SPY", "TLT", "GLD"]
raw = yf.download(tickers, start="2000-01-01", end="2026-06-01",
                  auto_adjust=True, progress=False)["Close"]
raw = raw.dropna(how="all")
print(f"  Price data shape: {raw.shape}  [{raw.index[0].date()} .. {raw.index[-1].date()}]")

# Download VIX — try yfinance first
print("Downloading VIX...")
vix_raw = yf.download("^VIX", start="2000-01-01", end="2026-06-01",
                      auto_adjust=True, progress=False)["Close"]
if vix_raw.empty or int(vix_raw.isna().sum()) > 500:
    # Fallback: FRED VIXCLS
    try:
        import pandas_datareader.data as pdr
        vix_raw = pdr.DataReader("VIXCLS", "fred",
                                 start="2000-01-01", end="2026-06-01")["VIXCLS"]
        print("  VIX loaded from FRED")
    except Exception as e:
        print(f"  FRED fallback failed: {e}")
        raise
else:
    print(f"  VIX loaded from yfinance: {len(vix_raw)} rows")

vix = vix_raw.squeeze().dropna()
vix.name = "VIX"

# ─────────────────────────────────────────────
# 2. Compute log returns
# ─────────────────────────────────────────────
returns = np.log(raw / raw.shift(1)).dropna()
print(f"  Returns shape: {returns.shape}")

# ─────────────────────────────────────────────
# 3. Berry Phase Rate
# ─────────────────────────────────────────────
def berry_phase_rate(returns_df: pd.DataFrame, window: int = 90) -> pd.Series:
    """
    BPR(t) = arccos(clamp(v(t) · v(t-1), -1, 1))
    where v(t) = principal eigenvector of rolling correlation matrix at t.
    Returns: pd.Series of BPR values (radians), indexed from returns_df.index[window:].
    """
    dates = returns_df.index[window:]
    bpr = []
    prev_vec = None

    for i in range(len(dates)):
        window_ret = returns_df.iloc[i : i + window]
        corr = window_ret.corr().values

        if np.isnan(corr).any():
            bpr.append(np.nan)
            prev_vec = None
            continue

        eigvals, eigvecs = np.linalg.eigh(corr)
        # Principal eigenvector (largest eigenvalue — last column from eigh)
        v = eigvecs[:, -1].copy()

        # Sign consistency: largest-magnitude component is positive
        if v[np.argmax(np.abs(v))] < 0:
            v = -v

        if prev_vec is not None:
            dot = np.clip(np.dot(v, prev_vec), -1.0, 1.0)
            angle = np.arccos(dot)
            bpr.append(angle)
        else:
            bpr.append(np.nan)

        prev_vec = v

    return pd.Series(bpr, index=dates, name="BPR")


print("Computing Berry Phase Rate (window=90)...")
bpr = berry_phase_rate(returns, window=90)
bpr = bpr.dropna()
print(f"  BPR computed: {len(bpr)} rows [{bpr.index[0].date()} .. {bpr.index[-1].date()}]")

# ─────────────────────────────────────────────
# 4. Normalize: rolling 252-day z-score
# ─────────────────────────────────────────────
bpr_z = (bpr - bpr.rolling(252).mean()) / bpr.rolling(252).std()
bpr_z.name = "BPR_z"
bpr_z = bpr_z.dropna()
print(f"  BPR_z computed: {len(bpr_z)} rows [{bpr_z.index[0].date()} .. {bpr_z.index[-1].date()}]")

# Binary elevated signal: top ~16% of distribution
elevated = (bpr_z > 1.0).astype(int)

# ─────────────────────────────────────────────
# 5. Label crisis windows (20 trading days BEFORE onset)
# ─────────────────────────────────────────────
crises = [
    ("Dot-com peak",     "2000-03-24"),
    ("9/11",             "2001-09-11"),
    ("WorldCom fraud",   "2002-06-25"),
    ("GFC onset",        "2008-09-15"),
    ("Flash Crash",      "2010-05-06"),
    ("EU Debt Crisis",   "2011-08-08"),
    ("China selloff",    "2015-08-24"),
    ("Oil crash",        "2016-01-20"),
    ("Vol spike",        "2018-02-05"),
    ("Q4 2018 selloff",  "2018-12-24"),
    ("COVID crash",      "2020-02-24"),
    ("COVID recovery",   "2020-03-23"),
    ("2022 rate shock",  "2022-01-03"),
    ("SVB crisis",       "2023-03-10"),
]

# Build a date index spanning the BPR_z series
all_dates = bpr_z.index
crisis_label = pd.Series(0, index=all_dates, name="crisis")

for name, onset_str in crises:
    onset = pd.Timestamp(onset_str)
    # Find the 20 trading days strictly before the onset date
    pre_dates = all_dates[all_dates < onset]
    if len(pre_dates) == 0:
        print(f"  Warning: no dates before {name} ({onset_str}) in BPR_z")
        continue
    window_start = pre_dates[-20] if len(pre_dates) >= 20 else pre_dates[0]
    mask = (all_dates >= window_start) & (all_dates < onset)
    crisis_label.loc[mask] = 1

n_crisis = int(crisis_label.sum())
print(f"  Crisis labels: {n_crisis} days marked (of {len(crisis_label)} total)")

# ─────────────────────────────────────────────
# 6. Align VIX with BPR_z
# ─────────────────────────────────────────────
vix_aligned = vix.reindex(bpr_z.index).ffill()

# ─────────────────────────────────────────────
# 7. IS / OOS split
# ─────────────────────────────────────────────
IS_END  = "2017-12-31"
OOS_START = "2018-01-01"

mask_is  = bpr_z.index <= IS_END
mask_oos = bpr_z.index >= OOS_START

print(f"\n  IS: {mask_is.sum()} days | OOS: {mask_oos.sum()} days")

# Full-period AUC
auc_full = roc_auc_score(crisis_label, bpr_z)

# IS AUC
if crisis_label[mask_is].sum() > 0 and crisis_label[mask_is].sum() < mask_is.sum():
    auc_is = roc_auc_score(crisis_label[mask_is], bpr_z[mask_is])
else:
    auc_is = float("nan")
    print("  Warning: IS crisis labels degenerate — cannot compute IS AUC")

# OOS AUC
if crisis_label[mask_oos].sum() > 0 and crisis_label[mask_oos].sum() < mask_oos.sum():
    auc_oos = roc_auc_score(crisis_label[mask_oos], bpr_z[mask_oos])
else:
    auc_oos = float("nan")
    print("  Warning: OOS crisis labels degenerate — cannot compute OOS AUC")

# ─────────────────────────────────────────────
# 8. VIX correlation
# ─────────────────────────────────────────────
corr_vix = float(bpr_z.corr(vix_aligned))

# ─────────────────────────────────────────────
# 9. False alarm rate (OOS)
# ─────────────────────────────────────────────
# Elevated = signal raised; false alarm = elevated AND no crisis in [-5, +20] window
# We use a lenient "within 20 days of any crisis onset" definition for false alarms

def days_to_nearest_crisis(dates, crises):
    """Return minimum trading-day distance from each date to any crisis onset."""
    crisis_dates = [pd.Timestamp(d) for _, d in crises
                    if pd.Timestamp(d) >= dates[0] and pd.Timestamp(d) <= dates[-1]]
    dist = pd.Series(np.inf, index=dates)
    for cd in crisis_dates:
        delta = np.abs((dates - cd).days)
        dist = np.minimum(dist, delta)
    return dist

oos_dates = bpr_z.index[mask_oos]
dist_oos = days_to_nearest_crisis(oos_dates, crises)

elevated_oos = elevated[mask_oos]
# False alarm: elevated AND more than 30 calendar days from any crisis onset
false_alarm_mask = (elevated_oos == 1) & (dist_oos > 30)
n_elevated_oos = int(elevated_oos.sum())
n_false_alarms = int(false_alarm_mask.sum())
false_alarm_rate_oos = (n_false_alarms / n_elevated_oos) if n_elevated_oos > 0 else float("nan")

# Annualized false alarm count (OOS spans ~8 years)
oos_years = len(oos_dates) / 252
false_alarms_per_year = n_false_alarms / oos_years if oos_years > 0 else float("nan")

# ─────────────────────────────────────────────
# 10. Cohen's d on crisis vs non-crisis BPR_z
# ─────────────────────────────────────────────
bpr_z_crisis     = bpr_z[crisis_label == 1]
bpr_z_non_crisis = bpr_z[crisis_label == 0]
cohens_d = float(
    (bpr_z_crisis.mean() - bpr_z_non_crisis.mean()) /
    np.sqrt((bpr_z_crisis.std()**2 + bpr_z_non_crisis.std()**2) / 2)
)

# ─────────────────────────────────────────────
# 11. Print summary
# ─────────────────────────────────────────────
GATE_AUC  = 0.65
GATE_CORR = 0.30

passed_auc  = (not np.isnan(auc_oos)) and (auc_oos > GATE_AUC)
passed_corr = abs(corr_vix) < GATE_CORR
status = "CONFIRMED" if (passed_auc and passed_corr) else "NOT CONFIRMED"

print("\n" + "="*55)
print(f"  H252 RESULT: {status}")
print(f"  Full AUC:    {auc_full:.4f}")
print(f"  IS AUC:      {auc_is:.4f}")
print(f"  OOS AUC:     {auc_oos:.4f}  (gate > {GATE_AUC})")
print(f"  Corr(BPR,VIX): {corr_vix:.4f}  (gate < {GATE_CORR})")
print(f"  Cohen's d (full): {cohens_d:.4f}  (paper claims 0.72)")
print(f"  OOS elevated days: {n_elevated_oos}")
print(f"  OOS false alarms:  {n_false_alarms}  ({false_alarms_per_year:.1f}/year)")
print(f"  OOS false alarm rate: {false_alarm_rate_oos:.3f}")
print("="*55)

# Gate check details
print(f"\n  Gate 1 (OOS AUC > {GATE_AUC}): {'PASS' if passed_auc else 'FAIL'}")
print(f"  Gate 2 (|Corr VIX| < {GATE_CORR}): {'PASS' if passed_corr else 'FAIL'}")

# ─────────────────────────────────────────────
# 12. Save results JSON
# ─────────────────────────────────────────────
notes_parts = []
if passed_auc and passed_corr:
    notes_parts.append(
        f"Both confirm gates passed. OOS AUC {auc_oos:.3f} > 0.65; "
        f"|Corr(BPR,VIX)| = {abs(corr_vix):.3f} < 0.30 — largely independent of VIX. "
        f"Cohen's d {cohens_d:.3f} vs paper claim 0.72. "
        f"OOS false alarm rate {false_alarm_rate_oos:.2f} ({false_alarms_per_year:.1f}/year). "
        "BPR provides early geometric warning complementary to H249 regime engine."
    )
elif not passed_auc and passed_corr:
    notes_parts.append(
        f"OOS AUC {auc_oos:.3f} below gate 0.65. "
        f"VIX correlation {corr_vix:.3f} within independence threshold. "
        f"Cohen's d {cohens_d:.3f}. "
        "Geometric signal statistically independent of VIX but insufficient discriminative power on labeled crises."
    )
elif passed_auc and not passed_corr:
    notes_parts.append(
        f"OOS AUC {auc_oos:.3f} passes gate. "
        f"But |Corr(BPR,VIX)| = {abs(corr_vix):.3f} >= 0.30 — too correlated with VIX to add independent value. "
        f"Cohen's d {cohens_d:.3f}."
    )
else:
    notes_parts.append(
        f"Both gates failed. OOS AUC {auc_oos:.3f} (gate 0.65); "
        f"|Corr VIX| = {abs(corr_vix):.3f} (gate 0.30). "
        f"Cohen's d {cohens_d:.3f}."
    )

results = {
    "hypothesis": "H252",
    "status": status,
    "full_auc": round(float(auc_full), 4),
    "is_auc": round(float(auc_is), 4) if not np.isnan(auc_is) else None,
    "oos_auc": round(float(auc_oos), 4) if not np.isnan(auc_oos) else None,
    "corr_vix": round(float(corr_vix), 4),
    "cohens_d_full": round(float(cohens_d), 4),
    "false_alarm_rate_oos": round(float(false_alarm_rate_oos), 4) if not np.isnan(false_alarm_rate_oos) else None,
    "false_alarms_per_year_oos": round(float(false_alarms_per_year), 2) if not np.isnan(false_alarms_per_year) else None,
    "n_elevated_oos": n_elevated_oos,
    "n_false_alarms_oos": n_false_alarms,
    "confirm_gate_auc": GATE_AUC,
    "confirm_gate_corr": GATE_CORR,
    "assets": ["SPY", "TLT", "GLD"],
    "window_days": 90,
    "bpr_z_norm_window": 252,
    "is_period": "2000-2017",
    "oos_period": "2018-2026",
    "n_crises_labeled": len(crises),
    "notes": " ".join(notes_parts),
}

out_path = "/workspace/agent/backtesting/results/h252_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")

# ─────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────
print(f"\nH252 complete — status: {status}")
