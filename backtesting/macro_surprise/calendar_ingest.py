"""
Step 1: Economic calendar ingestion + surprise table.

Sources:
  - superpilot69/fred-us-macro-open-data (GitHub)
    FRED vintage event data enriched with Investing.com consensus forecasts.
    Covers: PAYEMS (NFP), CPIAUCNS (CPI YoY), CPILFENS (Core CPI YoY), DFEDTARU (FOMC)
  - FRED ALFRED archive for vintage (first-print) actual cross-check

Output: events.parquet with columns:
  event_id, type, date_et, actual_first_print, consensus, prior,
  surprise, surprise_z, alfred_actual (for cross-check)

Notes:
  - CPI is YoY percent (not m/m) since that's what the dataset provides with consensus coverage
  - FOMC only includes rate-change events (31 since 2010)
  - NFP actual = first-print value from Investing.com consensus data (avoids lookahead)
"""

import os
import time
import json
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, timedelta
from typing import Optional

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

FRED_KEY = os.environ.get("FRED_API_KEY", "")

CA_BUNDLE = "/tmp/onecli-combined-ca.pem"
if not Path(CA_BUNDLE).exists():
    CA_BUNDLE = True

import functools
_orig_request = requests.Session.request
def _patched_request(self, method, url, **kwargs):
    if "verify" not in kwargs:
        kwargs["verify"] = CA_BUNDLE
    return _orig_request(self, method, url, **kwargs)
requests.Session.request = _patched_request

# GitHub raw URL for the events dataset
EVENTS_URL = (
    "https://raw.githubusercontent.com/superpilot69/fred-us-macro-open-data"
    "/main/data/fred-us-macro-events.json"
)

# FRED series → canonical event type
SERIES_TO_TYPE = {
    "PAYEMS":    "NFP",       # Nonfarm payrolls monthly change
    "CPIAUCNS":  "CPI",       # Headline CPI YoY
    "CPILFENS":  "CPI_CORE",  # Core CPI YoY
    "DFEDTARU":  "FOMC",      # Fed funds target upper limit
}

EVENT_TYPES = {"NFP", "CPI", "FOMC"}  # CPI_CORE included as CPI supplement

# FRED ALFRED series for cross-check
ALFRED_SERIES = {
    "NFP":      "PAYEMS",
    "CPI":      "CPIAUCSL",
    "CPI_CORE": "CPILFESL",
}


def fetch_macro_events(start_year: int = 2010, end_year: int = 2026) -> pd.DataFrame:
    """
    Download and parse the superpilot69/fred-us-macro-open-data events JSON.
    Returns DataFrame with columns matching our pipeline expectations.
    """
    cache_file = CACHE_DIR / f"macro_events_{start_year}_{end_year}.json"

    if cache_file.exists():
        print("  Loading cached macro events...")
        raw = json.loads(cache_file.read_text())
    else:
        print(f"  Downloading macro events from GitHub...")
        resp = requests.get(EVENTS_URL, timeout=60)
        resp.raise_for_status()
        raw = resp.json()
        cache_file.write_text(json.dumps(raw))

    events_raw = raw.get("events", [])
    print(f"  Raw events: {len(events_raw)}")

    records = []
    for e in events_raw:
        meta = e.get("metadata", {})
        series_id = meta.get("seriesId", "")
        etype = SERIES_TO_TYPE.get(series_id)
        if etype is None:
            continue

        release_date = meta.get("releaseDate", "")
        if not release_date:
            continue

        # Filter by year range
        try:
            rdate = pd.to_datetime(release_date)
        except Exception:
            continue
        if rdate.year < start_year or rdate.year > end_year:
            continue

        consensus = meta.get("consensus", {}) or {}
        actual = consensus.get("actual")       # first-print value
        forecast = consensus.get("forecast")   # consensus forecast
        prior = consensus.get("previous")      # prior period first-print

        # FOMC: actual/forecast are the target rate level; compute surprise as basis-point change
        # For NFP: actual/forecast are thousands, surprise = actual - forecast
        # For CPI: actual/forecast are YoY percent, surprise = actual - forecast

        records.append({
            "series_id":    series_id,
            "type":         etype,
            "date_et":      rdate,
            "actual":       actual,
            "consensus":    forecast,
            "prior":        prior,
            "raw_value":    meta.get("rawValue"),
            "value_kind":   meta.get("valueKind"),
        })

    df = pd.DataFrame(records)
    if df.empty:
        print("  ERROR: No events parsed.")
        return df

    print(f"  Parsed {len(df)} events")
    for etype, grp in df.groupby("type"):
        has_consensus = grp["actual"].notna() & grp["consensus"].notna()
        print(f"    {etype}: {len(grp)} total, {has_consensus.sum()} with consensus")

    return df


def fetch_alfred_vintage(series_id: str, obs_date: str) -> Optional[float]:
    """
    Get the first-print (vintage) value from FRED ALFRED for cross-check.
    """
    if not FRED_KEY:
        return None

    cache_file = CACHE_DIR / f"alfred_{series_id}_{obs_date}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text()).get("value")

    obs_dt = pd.to_datetime(obs_date)
    rt_end = (obs_dt + timedelta(days=45)).strftime("%Y-%m-%d")

    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&realtime_start={obs_date}&realtime_end={rt_end}"
        f"&sort_order=asc&limit=5&api_key={FRED_KEY}&file_type=json"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        obs = data.get("observations", [])
        target = obs_dt
        best = None
        best_delta = timedelta(days=999)
        for o in obs:
            try:
                val = float(o["value"])
                dt = pd.to_datetime(o["date"])
                delta = abs(dt - target)
                if delta < best_delta:
                    best = val
                    best_delta = delta
            except Exception:
                pass
        cache_file.write_text(json.dumps({"value": best}))
        time.sleep(0.3)
        return best
    except Exception as err:
        print(f"  ALFRED error {series_id} {obs_date}: {err}")
        return None


def compute_surprise_z(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add surprise and surprise_z columns.
    surprise = actual - consensus
    surprise_z = surprise / trailing std (min 24 obs, expanding, strictly prior)
    """
    df = df.copy().sort_values(["type", "date_et"])
    df["surprise"] = df["actual"] - df["consensus"]

    records = []
    for etype, grp in df.groupby("type"):
        grp = grp.sort_values("date_et").copy()
        surprises = grp["surprise"].values
        z_scores = []
        for i in range(len(surprises)):
            # Exclude NaN from window (events without consensus don't inform std)
            window_valid = surprises[:i][~pd.isna(surprises[:i])]
            if len(window_valid) < 24 or pd.isna(surprises[i]):
                z_scores.append(np.nan)
            else:
                std = np.std(window_valid, ddof=1)
                z_scores.append(surprises[i] / std if std > 0 else np.nan)
        grp["surprise_z"] = z_scores
        records.append(grp)

    return pd.concat(records).sort_values("date_et").reset_index(drop=True)


def build_events_table(start_year: int = 2010, end_year: int = 2026,
                       verify_alfred: bool = True) -> pd.DataFrame:
    """
    Full pipeline: fetch events → ALFRED cross-check → surprise z-scores.
    Returns events DataFrame and saves to cache/events.parquet.
    """
    out_path = CACHE_DIR / "events.parquet"

    print("=== Step 1: Calendar ingestion ===")
    df = fetch_macro_events(start_year, end_year)

    if df.empty:
        print("ERROR: No events fetched.")
        return df

    # Deduplicate: keep one row per (type, date_et), preferring non-null actual
    df = df.sort_values(["type", "date_et", "actual"], na_position="last")
    df = df.drop_duplicates(subset=["type", "date_et"], keep="first")
    df = df.reset_index(drop=True)

    df["event_id"] = [f"{row.type}_{row.date_et.strftime('%Y%m%d')}"
                      for row in df.itertuples()]

    # ALFRED cross-check (optional, informational)
    if verify_alfred and FRED_KEY:
        print("Cross-checking actuals against FRED ALFRED...")
        alfred_vals = []
        for _, row in df.iterrows():
            series = ALFRED_SERIES.get(row["type"])
            if series and pd.notna(row["date_et"]):
                val = fetch_alfred_vintage(series, row["date_et"].strftime("%Y-%m-%d"))
            else:
                val = None
            alfred_vals.append(val)
        df["alfred_actual"] = alfred_vals
    else:
        df["alfred_actual"] = None

    # Compute surprise z-scores
    df = compute_surprise_z(df)

    # Report coverage
    df_valid = df.dropna(subset=["actual", "consensus", "surprise"])
    print(f"\n  Total events with actual+consensus: {len(df_valid)}")
    for etype, grp in df_valid.groupby("type"):
        print(f"    {etype}: {len(grp)} events, "
              f"date range: {grp['date_et'].min().date()} – {grp['date_et'].max().date()}")

    df_valid.to_parquet(out_path, index=False)
    print(f"  Saved → {out_path}")
    return df_valid


if __name__ == "__main__":
    df = build_events_table(start_year=2010, end_year=2026, verify_alfred=False)
    print(df[["event_id", "type", "date_et", "actual", "consensus",
              "surprise", "surprise_z"]].tail(20).to_string())
