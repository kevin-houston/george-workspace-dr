---
updated: 2026-05-22
type: reference
source: https://x.com/zostaff/status/2056351832088207385
---

# Open Source Repos from Hedge Funds & Quant Firms

**Source**: @zostaff thread (May 18, 2026, 792K views) — 22 repos from 7 firms.

Firms that publish nothing: Renaissance Technologies, Citadel, Bridgewater, Millennium, Point72. Their silence is itself signal: firms whose edge is the *alpha discovered* lock everything down. Firms whose edge is the *people hired* open-source tools to attract PhDs.

---

## Highest Priority for This Project

### man-group/ArcticDB ⭐⭐⭐
https://github.com/man-group/ArcticDB — 2.3k stars  
Time-series database that stores in S3 (or local). Pandas in, pandas out. No server. Bloomberg paid Man Group to license it. If you store OHLCV/factor data in CSV, this is the upgrade. BSL license: free for non-commercial use, paid for production commercial deployment.

### man-group/dtale ⭐⭐⭐
https://github.com/man-group/dtale — 5.1k stars  
Excel-style interactive UI for pandas DataFrames in the browser. One import line. Filters, correlations, charts. Useful for ad-hoc exploration of backtest results and factor matrices.

### yli188/WorldQuant_alpha101_code ⭐⭐⭐
https://github.com/yli188/WorldQuant_alpha101_code — 748 stars  
Community Python implementation of all 101 formulaic alpha signals from WorldQuant's "101 Formulaic Alphas" paper — the most cited work in quant research for 10+ years. Directly relevant to H202-XL cross-sectional alpha factor engineering. Fork of choice for learning how alpha researchers think.

---

## Worth Knowing

### man-group/notebooker ⭐⭐
https://github.com/man-group/notebooker — 900 stars  
Turns Jupyter notebooks into a scheduled reporting engine. Could replace the ad-hoc EOD dashboard script with parameterized, scheduled notebook reports.

### man-group/PyBloqs ⭐⭐
https://github.com/man-group/PyBloqs — 183 stars  
HTML report blocks assembled from Python. Tables, charts, layout — no frontend needed. Complement to dtale for static reports.

### twosigma/flint ⭐
https://github.com/twosigma/flint — 1k stars  
Time-series joins on Apache Spark with temporal tolerance (find nearest quote for each trade). Requires Spark — overkill at current scale but useful at 500+ stock universe.

---

## Infrastructure / Engineering (lower direct relevance)

### deshaw/pyflyby
https://github.com/deshaw/pyflyby — 409 stars  
Auto-import for IPython/Jupyter. Saves time in notebooks.

### deshaw/versioned-hdf5
https://github.com/deshaw/versioned-hdf5 — 89 stars  
Git-like version control for HDF5 files. Built with Quansight Labs.

### optiver/timestamp9
https://github.com/optiver/timestamp9 — 65 stars  
Nanosecond timestamps for Python. Relevant if moving to intraday HFT data.

### hudson-trading/corral
https://github.com/hudson-trading/corral — 175 stars  
Structured concurrency for C++20. HRT's trading infrastructure backbone. Not Python-relevant.

### janestreet/magic-trace
https://github.com/janestreet/magic-trace — 5.3k stars  
High-resolution CPU instruction tracer using Intel PT. When a profiler isn't enough.

---

## Why firms share (or don't)

Three patterns:
1. **Recruiting brand** (Two Sigma, D.E. Shaw, Jane Street, HRT): open source is the showcase to attract top engineers. Jane Street's magic-trace = 5.3k stars = thousands of infra engineers who now know where to send a CV.
2. **Marketing** (Man Group): publicly listed, Bloomberg already licensed their main IP (ArcticDB). Rest is brand.
3. **Paranoia** (Renaissance, Citadel, Bridgewater): any public code = hint to competitors. Renaissance NDAs prevent former employees from writing detailed resumes.

**Key insight**: The open/closed split maps onto competitive moat theory:
- If edge = people you hire → open the code, attract more PhDs
- If edge = alpha you discover → close everything

Two Sigma and Renaissance have both been right for 25+ years simultaneously.
