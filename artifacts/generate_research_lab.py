#!/usr/bin/env python3
"""Generate Hypothesis Research Lab HTML artifact."""
import re, json
from pathlib import Path

HYPOTHESIS_LOG = Path("/workspace/agent/wiki/trading/backtesting/hypothesis-log.md")

# Strategy family assignment by H-number range and keywords
FAMILIES = [
    (range(1, 23),   "Early Experiments"),
    (range(23, 83),  "ETF Rotation"),
    (range(83, 152), "Portfolio Optimization"),
    (range(152, 156),"Pairs Trading"),
    (range(156, 159),"Stock Momentum"),
    (range(159, 166),"PEAD Core"),
    (range(161, 163),"Dividends & Options"),
    (range(163, 177),"PEAD-NLP"),
    (range(177, 182),"Global / Commodity"),
    (range(181, 190),"Short-Term Reversal"),
    (range(185, 187),"Prediction Markets"),
]

FAMILY_KEYWORDS = [
    # More specific terms checked first
    ("FinBERT", "PEAD-NLP"),
    ("GPT-4o", "PEAD-NLP"),
    ("NLP:", "PEAD-NLP"),
    ("PEAD-NLP", "PEAD-NLP"),
    ("PEAD-ML", "PEAD-NLP"),
    ("CLS Embedding", "PEAD-NLP"),
    ("Sentiment Surprise", "PEAD-NLP"),
    ("Kalshi", "Prediction Markets"),
    ("Polymarket", "Prediction Markets"),
    ("PolySwarm", "Prediction Markets"),
    ("iron condor", "Options"),
    ("0DTE", "Options"),
    ("UOA", "Options"),
    ("covered call", "Dividends & Options"),
    ("dividend", "Dividends & Options"),
    ("Kalman", "Pairs Trading"),
    ("pairs trading", "Pairs Trading"),
    ("Pairs-DL", "Pairs Trading"),
    ("GRU/LSTM", "Pairs Trading"),
    ("52-Week", "Short-Term Reversal"),
    ("52-week", "Short-Term Reversal"),
    ("reversal", "Short-Term Reversal"),
    ("H026 + H181", "Short-Term Reversal"),
    ("LightGBM", "ML / AI"),
    ("GRU", "ML / AI"),
    ("PEAD", "PEAD Core"),
    ("sector rotation", "ETF Rotation"),
    ("ETF rotation", "ETF Rotation"),
    ("commodity", "Global / Commodity"),
    ("global equity", "Global / Commodity"),
    ("international", "Global / Commodity"),
    ("low-vol", "Portfolio Optimization"),
    ("vol-target", "Portfolio Optimization"),
    ("Low-Volatility", "Portfolio Optimization"),
    ("momentum", "Stock Momentum"),
    ("ETF", "ETF Rotation"),
]

def assign_family(hnum: int, desc: str) -> str:
    desc_lower = desc.lower()
    for kw, fam in FAMILY_KEYWORDS:
        if kw.lower() in desc_lower:
            return fam
    for r, fam in FAMILIES:
        if hnum in r:
            return fam
    return "Other"

def normalize_status(raw: str) -> str:
    r = raw.upper()
    if "NOT CONFIRMED" in r:
        return "NOT CONFIRMED"
    if "PARTIAL CONFIRMED" in r or "PARTIAL SIMULATION" in r:
        return "PARTIAL"
    if "PARTIAL" in r:
        return "PARTIAL"
    if "CONFIRMED" in r:
        return "CONFIRMED"
    if "COMPLETE" in r:
        return "CONFIRMED"       # Early entries use COMPLETE = deployed/confirmed
    if "REJECTED" in r:
        return "NOT CONFIRMED"
    if "QUEUED" in r:
        return "QUEUED"
    if "PENDING" in r:
        return "QUEUED"
    if "BLOCKED" in r:
        return "BLOCKED"
    if "FLAGGED" in r:
        return "FLAGGED"
    if "INCONCLUSIVE" in r:
        return "INCONCLUSIVE"
    if "DEFERRED" in r:
        return "DEFERRED"
    if "SWEEP" in r:
        return "CONFIRMED"       # Sweep = multi-hypothesis confirmed sweep
    if "MODERATE" in r:
        return "PARTIAL"         # Moderate overfit = investable partial
    if "PRELIMINARY" in r:
        return "PARTIAL"
    return raw.strip()[:20]

def safe_float(s: str) -> float | None:
    try:
        return float(s.rstrip(".,;:)"))
    except:
        return None

def extract_metric(text: str, keys: list[str]) -> float | None:
    for key in keys:
        # Match key followed by = or space and a number
        m = re.search(rf'{re.escape(key)}[=:\s]+(-?[0-9]+\.?[0-9]*)', text)
        if m:
            v = safe_float(m.group(1))
            if v is not None:
                return v
    return None

def extract_oos_sharpe(text: str) -> float | None:
    # Prefer explicit OOS Sharpe
    m = re.search(r'OOS[^.]{0,60}?Sharpe[=:\s]+([0-9]+\.?[0-9]*)', text)
    if m:
        v = safe_float(m.group(1))
        if v is not None and v < 20:
            return v
    # Sharpe= pattern (avoid catching ratios like 60/40)
    for m in re.finditer(r'Sharpe[=:\s]+([0-9]+\.?[0-9]*)', text):
        v = safe_float(m.group(1))
        if v is not None and v < 20:
            return v
    return None

def extract_cagr(text: str) -> float | None:
    m = re.search(r'OOS[^.]{0,80}?CAGR[=:\s]+(-?[0-9]+\.?[0-9]*)', text)
    if m:
        return safe_float(m.group(1))
    m = re.search(r'CAGR[=:\s]+(-?[0-9]+\.?[0-9]*)%', text)
    if m:
        return safe_float(m.group(1))
    return None

def extract_maxdd(text: str) -> float | None:
    m = re.search(r'MaxDD[=:\s]+([-−]?[0-9]+\.?[0-9]*)%', text)
    if m:
        s = m.group(1).replace('−', '-')
        return safe_float(s)
    m = re.search(r'MaxDD[=:\s]+([-−]?[0-9]+\.?[0-9]*)', text)
    if m:
        s = m.group(1).replace('−', '-')
        v = safe_float(s)
        if v and v > 0:
            return -v
        return v
    return None

def extract_wr(text: str) -> float | None:
    # OOS WR%
    m = re.search(r'OOS[^.]{0,60}?WR[=:\s]+([0-9]+\.?[0-9]*)%', text)
    if m:
        return safe_float(m.group(1))
    m = re.search(r'WR[=:\s]+([0-9]+\.?[0-9]*)%', text)
    if m:
        return safe_float(m.group(1))
    m = re.search(r'win.rate[=:\s]+([0-9]+\.?[0-9]*)%', text, re.I)
    if m:
        return safe_float(m.group(1))
    return None

def parse_hypotheses():
    text = HYPOTHESIS_LOG.read_text()
    lines = text.splitlines()
    entries = []
    seen = set()

    for line in lines:
        m = re.match(r'^(h\d+)_status:\s+(.*)', line.strip())
        if not m:
            continue
        hid = m.group(1)
        num = int(hid[1:])
        if num in seen:
            continue
        seen.add(num)
        rest = m.group(2)

        # Status — try known multi-word patterns first, then single word
        STATUS_PATTERNS = [
            "NOT CONFIRMED", "PARTIAL CONFIRMED", "PARTIAL SIMULATION",
            "MODERATE OVERFIT", "MODERATE", "PARTIAL", "CONFIRMED",
            "COMPLETE", "REJECTED", "QUEUED", "BLOCKED", "FLAGGED",
            "INCONCLUSIVE", "DEFERRED", "SWEEP", "PENDING", "PRELIMINARY",
        ]
        raw_status = rest[:30]
        rest_up = rest.upper()
        for pat in STATUS_PATTERNS:
            if rest_up.startswith(pat):
                raw_status = pat
                break
        status = normalize_status(raw_status)

        # Date
        date_m = re.search(r'\((\d{4}-\d{2}-\d{2})', rest)
        date = date_m.group(1) if date_m else ""

        # Description — text after first em dash
        desc_m = re.search(r'[—–]\s*(.+)', rest)
        if desc_m:
            raw_desc = desc_m.group(1)
            # Trim to first sentence or 120 chars
            first_sent = re.split(r'\.\s+[A-Z]', raw_desc)
            desc = first_sent[0][:120].strip()
        else:
            desc = rest[:120]

        # Full text for metric extraction
        full = rest

        sharpe = extract_oos_sharpe(full)
        cagr = extract_cagr(full)
        maxdd = extract_maxdd(full)
        wr = extract_wr(full)

        # Script reference
        script_m = re.search(r'Script:\s+(\S+\.py)', full)
        script = script_m.group(1) if script_m else ""

        family = assign_family(num, desc + " " + full[:200])

        entries.append({
            "id": hid.upper(),
            "num": num,
            "status": status,
            "date": date,
            "desc": desc,
            "sharpe": sharpe,
            "cagr": cagr,
            "maxdd": maxdd,
            "wr": wr,
            "script": script,
            "family": family,
            "full": full[:500],
        })

    entries.sort(key=lambda x: x["num"])
    return entries

def status_color(s: str) -> str:
    return {
        "CONFIRMED": "#22c55e",
        "PARTIAL": "#f97316",
        "NOT CONFIRMED": "#ef4444",
        "QUEUED": "#eab308",
        "BLOCKED": "#6b7280",
        "FLAGGED": "#a855f7",
        "INCONCLUSIVE": "#94a3b8",
        "DEFERRED": "#64748b",
    }.get(s, "#94a3b8")

def status_bg(s: str) -> str:
    return {
        "CONFIRMED": "#14532d",
        "PARTIAL": "#431407",
        "NOT CONFIRMED": "#450a0a",
        "QUEUED": "#422006",
        "BLOCKED": "#1f2937",
        "FLAGGED": "#3b0764",
        "INCONCLUSIVE": "#1e293b",
        "DEFERRED": "#0f172a",
    }.get(s, "#1e293b")

def generate_html(entries: list[dict]) -> str:
    # Compute stats
    total = len(entries)
    status_counts = {}
    for e in entries:
        status_counts[e["status"]] = status_counts.get(e["status"], 0) + 1

    confirmed = status_counts.get("CONFIRMED", 0)
    partial = status_counts.get("PARTIAL", 0)
    not_confirmed = status_counts.get("NOT CONFIRMED", 0)
    queued = status_counts.get("QUEUED", 0)
    blocked = status_counts.get("BLOCKED", 0)
    flagged = status_counts.get("FLAGGED", 0)
    other = total - confirmed - partial - not_confirmed - queued - blocked - flagged
    confirm_rate = round((confirmed + partial) / total * 100, 1)

    # Family stats
    family_stats = {}
    for e in entries:
        f = e["family"]
        if f not in family_stats:
            family_stats[f] = {"total": 0, "confirmed": 0}
        family_stats[f]["total"] += 1
        if e["status"] in ("CONFIRMED", "PARTIAL"):
            family_stats[f]["confirmed"] += 1

    # Serialize to JS
    js_data = json.dumps(entries, indent=0)

    funnel_stages = [
        ("Total", total, "#3b82f6"),
        ("Tested", total - queued - blocked - flagged, "#8b5cf6"),
        ("Partial+", confirmed + partial + not_confirmed, "#06b6d4"),
        ("Confirmed+", confirmed + partial, "#22c55e"),
        ("Confirmed", confirmed, "#16a34a"),
    ]

    funnel_html = ""
    max_val = funnel_stages[0][1]
    for label, val, color in funnel_stages:
        pct = round(val / max_val * 100)
        funnel_html += f"""
        <div class="funnel-stage">
          <div class="funnel-bar" style="width:{pct}%;background:{color}">
            <span class="funnel-num">{val}</span>
          </div>
          <span class="funnel-label">{label}</span>
        </div>"""

    family_rows = ""
    for fam, stats in sorted(family_stats.items(), key=lambda x: -x[1]["total"]):
        rate = round(stats["confirmed"] / stats["total"] * 100) if stats["total"] else 0
        bar_w = rate
        family_rows += f"""
        <tr class="family-row" onclick="filterByFamily('{fam}')">
          <td>{fam}</td>
          <td style="text-align:center">{stats['total']}</td>
          <td style="text-align:center">{stats['confirmed']}</td>
          <td>
            <div class="mini-bar">
              <div class="mini-fill" style="width:{bar_w}%;background:{'#22c55e' if rate>=50 else '#ef4444'}"></div>
              <span>{rate}%</span>
            </div>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hypothesis Research Lab</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0f1a;color:#e2e8f0;min-height:100vh;overflow-x:hidden}}

  /* Layout */
  .top-bar{{padding:16px 20px;background:#0f172a;border-bottom:1px solid #1e293b;display:flex;align-items:center;gap:16px}}
  .top-bar h1{{font-size:18px;font-weight:700;color:#f8fafc;letter-spacing:-0.02em}}
  .top-bar .subtitle{{font-size:12px;color:#64748b}}
  .main{{display:grid;grid-template-columns:1fr 340px;gap:0;height:calc(100vh - 60px)}}
  .left-panel{{display:flex;flex-direction:column;overflow:hidden;border-right:1px solid #1e293b}}
  .right-panel{{display:flex;flex-direction:column;overflow:hidden;background:#0d1424}}

  /* Stats bar */
  .stats-bar{{padding:12px 16px;background:#0f172a;border-bottom:1px solid #1e293b;display:flex;gap:16px;flex-wrap:wrap;align-items:center}}
  .stat-chip{{display:flex;flex-direction:column;align-items:center;padding:6px 14px;border-radius:8px;min-width:80px}}
  .stat-num{{font-size:20px;font-weight:700;line-height:1}}
  .stat-label{{font-size:10px;color:#64748b;margin-top:2px;text-transform:uppercase;letter-spacing:0.05em}}

  /* Funnel */
  .funnel-section{{padding:12px 16px;background:#0f172a;border-bottom:1px solid #1e293b}}
  .funnel-title{{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px}}
  .funnel-stage{{display:flex;align-items:center;gap:8px;margin-bottom:4px}}
  .funnel-bar{{height:22px;border-radius:4px;display:flex;align-items:center;padding-left:8px;min-width:40px;transition:width 0.3s}}
  .funnel-num{{font-size:12px;font-weight:700;color:#fff}}
  .funnel-label{{font-size:11px;color:#94a3b8;min-width:80px}}

  /* Toolbar */
  .toolbar{{padding:10px 12px;background:#111827;border-bottom:1px solid #1e293b;display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
  .search-box{{flex:1;min-width:160px;background:#1e293b;border:1px solid #334155;border-radius:6px;padding:6px 10px;color:#e2e8f0;font-size:13px;outline:none}}
  .search-box:focus{{border-color:#3b82f6}}
  .search-box::placeholder{{color:#475569}}
  .filter-select{{background:#1e293b;border:1px solid #334155;border-radius:6px;padding:6px 8px;color:#e2e8f0;font-size:12px;outline:none;cursor:pointer}}
  .filter-select:focus{{border-color:#3b82f6}}
  .clear-btn{{background:#1e293b;border:1px solid #334155;border-radius:6px;padding:6px 10px;color:#94a3b8;font-size:12px;cursor:pointer}}
  .clear-btn:hover{{color:#e2e8f0;border-color:#475569}}
  .count-label{{font-size:11px;color:#475569;white-space:nowrap}}

  /* Table */
  .table-wrap{{flex:1;overflow-y:auto}}
  .hyp-table{{width:100%;border-collapse:collapse;font-size:12px}}
  .hyp-table th{{position:sticky;top:0;background:#111827;color:#64748b;font-weight:500;padding:8px 10px;text-align:left;border-bottom:1px solid #1e293b;cursor:pointer;user-select:none;white-space:nowrap}}
  .hyp-table th:hover{{color:#94a3b8}}
  .hyp-table th.sorted{{color:#3b82f6}}
  .hyp-table td{{padding:7px 10px;border-bottom:1px solid #111827;vertical-align:middle}}
  .hyp-table tr{{cursor:pointer;transition:background 0.1s}}
  .hyp-table tr:hover td{{background:#1a2436}}
  .hyp-table tr.selected td{{background:#1e3a5f!important}}
  .hyp-table tr.hidden{{display:none}}

  /* Badges */
  .badge{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:600;letter-spacing:0.03em;white-space:nowrap}}
  .hid{{font-weight:700;color:#60a5fa;font-family:monospace;font-size:11px}}
  .metric{{font-family:monospace;font-size:11px}}
  .metric.good{{color:#22c55e}}
  .metric.ok{{color:#f97316}}
  .metric.bad{{color:#ef4444}}
  .metric.na{{color:#475569}}
  .desc-cell{{color:#94a3b8;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .family-tag{{font-size:10px;color:#64748b;background:#1e293b;padding:2px 5px;border-radius:3px;white-space:nowrap}}

  /* Right panel */
  .rp-header{{padding:14px 16px;border-bottom:1px solid #1e293b;background:#0f172a}}
  .rp-title{{font-size:13px;font-weight:600;color:#94a3b8}}

  /* Detail card */
  .detail-card{{padding:16px;overflow-y:auto;flex:1}}
  .detail-card .empty{{color:#334155;font-size:13px;text-align:center;margin-top:60px;line-height:1.8}}
  .detail-hid{{font-size:28px;font-weight:800;color:#60a5fa;font-family:monospace;margin-bottom:4px}}
  .detail-status{{margin-bottom:12px}}
  .detail-desc{{font-size:13px;color:#cbd5e1;line-height:1.7;margin-bottom:16px;padding:10px;background:#111827;border-radius:6px;border-left:3px solid #3b82f6}}
  .metrics-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}}
  .metric-card{{background:#111827;border:1px solid #1e293b;border-radius:6px;padding:10px}}
  .metric-card .label{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px}}
  .metric-card .value{{font-size:18px;font-weight:700;font-family:monospace}}
  .detail-section{{margin-bottom:12px}}
  .detail-section-title{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px}}
  .detail-full{{font-size:11px;color:#64748b;line-height:1.6;background:#080e18;padding:10px;border-radius:6px;max-height:180px;overflow-y:auto}}
  .copy-btn{{display:block;width:100%;background:#1e293b;border:1px solid #334155;border-radius:6px;padding:8px;color:#94a3b8;font-size:12px;cursor:pointer;text-align:center;margin-top:8px;transition:all 0.15s}}
  .copy-btn:hover{{background:#2d3f55;color:#e2e8f0}}
  .copy-btn.copied{{background:#14532d;border-color:#16a34a;color:#22c55e}}
  .script-link{{font-family:monospace;font-size:11px;color:#7dd3fc;padding:2px 0}}

  /* Family panel */
  .family-section{{padding:0 0 12px 0;border-top:1px solid #1e293b}}
  .family-section-title{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;padding:10px 16px 6px}}
  .family-table{{width:100%;border-collapse:collapse;font-size:11px}}
  .family-table th{{color:#475569;font-weight:500;padding:4px 16px;text-align:left}}
  .family-row{{cursor:pointer;transition:background 0.1s}}
  .family-row:hover td{{background:#1a2436}}
  .family-row td{{padding:5px 16px;border-bottom:1px solid #0f172a;color:#94a3b8}}
  .family-row td:first-child{{color:#cbd5e1}}
  .mini-bar{{display:flex;align-items:center;gap:6px}}
  .mini-bar div{{height:6px;border-radius:3px;min-width:2px;flex-shrink:0}}
  .mini-bar span{{font-size:10px;color:#64748b}}
  .active-filter{{display:none;font-size:10px;color:#3b82f6;background:#1e293b;padding:2px 8px;border-radius:4px;align-items:center;gap:4px}}
  .active-filter.visible{{display:inline-flex}}

  /* Sort arrows */
  .sort-arrow{{display:inline-block;margin-left:3px;opacity:0.4}}
  .sorted .sort-arrow{{opacity:1}}

  /* Scrollbar */
  ::-webkit-scrollbar{{width:6px;height:6px}}
  ::-webkit-scrollbar-track{{background:#0a0f1a}}
  ::-webkit-scrollbar-thumb{{background:#1e293b;border-radius:3px}}
  ::-webkit-scrollbar-thumb:hover{{background:#334155}}

  @media(max-width:900px){{
    .main{{grid-template-columns:1fr}}
    .right-panel{{height:400px}}
  }}
</style>
</head>
<body>

<div class="top-bar">
  <div>
    <h1>Hypothesis Research Lab</h1>
    <div class="subtitle">Systematic strategy discovery pipeline · {total} hypotheses tested</div>
  </div>
</div>

<div class="stats-bar">
  <div class="stat-chip" style="background:#14532d">
    <span class="stat-num" style="color:#22c55e">{confirmed}</span>
    <span class="stat-label">Confirmed</span>
  </div>
  <div class="stat-chip" style="background:#1c1917">
    <span class="stat-num" style="color:#f97316">{partial}</span>
    <span class="stat-label">Partial</span>
  </div>
  <div class="stat-chip" style="background:#450a0a">
    <span class="stat-num" style="color:#ef4444">{not_confirmed}</span>
    <span class="stat-label">Not Confirmed</span>
  </div>
  <div class="stat-chip" style="background:#422006">
    <span class="stat-num" style="color:#eab308">{queued}</span>
    <span class="stat-label">Queued</span>
  </div>
  <div class="stat-chip" style="background:#1f2937">
    <span class="stat-num" style="color:#6b7280">{blocked + flagged}</span>
    <span class="stat-label">Blocked/Flagged</span>
  </div>
  <div class="stat-chip" style="background:#1e1b4b;margin-left:auto">
    <span class="stat-num" style="color:#818cf8">{confirm_rate}%</span>
    <span class="stat-label">Confirm Rate</span>
  </div>
</div>

<div class="funnel-section">
  <div class="funnel-title">Pipeline Funnel</div>
  {funnel_html}
</div>

<div class="main">
  <div class="left-panel">
    <div class="toolbar">
      <input type="text" class="search-box" id="searchBox" placeholder="Search H-number, description, keyword…" oninput="applyFilters()">
      <select class="filter-select" id="statusFilter" onchange="applyFilters()">
        <option value="">All Status</option>
        <option value="CONFIRMED">Confirmed</option>
        <option value="PARTIAL">Partial</option>
        <option value="NOT CONFIRMED">Not Confirmed</option>
        <option value="QUEUED">Queued</option>
        <option value="BLOCKED">Blocked</option>
        <option value="FLAGGED">Flagged</option>
      </select>
      <select class="filter-select" id="familyFilter" onchange="applyFilters()">
        <option value="">All Families</option>
        {chr(10).join(f'<option value="{f}">{f}</option>' for f in sorted(family_stats.keys()))}
      </select>
      <button class="clear-btn" onclick="clearFilters()">✕ Clear</button>
      <span class="count-label" id="countLabel">{total} shown</span>
    </div>
    <div class="table-wrap">
      <table class="hyp-table" id="hypTable">
        <thead>
          <tr>
            <th onclick="sortBy('num')" id="th-num">H# <span class="sort-arrow" id="arr-num">↕</span></th>
            <th onclick="sortBy('status')" id="th-status">Status <span class="sort-arrow" id="arr-status">↕</span></th>
            <th>Description</th>
            <th onclick="sortBy('sharpe')" id="th-sharpe">Sharpe <span class="sort-arrow" id="arr-sharpe">↕</span></th>
            <th onclick="sortBy('maxdd')" id="th-maxdd">MaxDD <span class="sort-arrow" id="arr-maxdd">↕</span></th>
            <th onclick="sortBy('date')" id="th-date">Date <span class="sort-arrow" id="arr-date">↕</span></th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>

  <div class="right-panel">
    <div class="rp-header" style="display:flex;align-items:center;justify-content:space-between">
      <span class="rp-title">Detail</span>
      <span class="active-filter" id="activeFilterChip"></span>
    </div>
    <div class="detail-card" id="detailCard">
      <div class="empty">← Click any row to explore<br>Use filters to slice the pipeline<br>Click a family to filter by it</div>
    </div>
    <div class="family-section">
      <div class="family-section-title">Strategy Families</div>
      <table class="family-table">
        <thead><tr><th>Family</th><th>N</th><th>✓</th><th>Hit Rate</th></tr></thead>
        <tbody>{family_rows}</tbody>
      </table>
    </div>
  </div>
</div>

<script>
const DATA = {js_data};

let sortKey = 'num';
let sortDir = 1;
let selectedId = null;
let familyFilterValue = '';

function statusColor(s) {{
  const map = {{
    'CONFIRMED':'#22c55e','PARTIAL':'#f97316','NOT CONFIRMED':'#ef4444',
    'QUEUED':'#eab308','BLOCKED':'#6b7280','FLAGGED':'#a855f7',
    'INCONCLUSIVE':'#94a3b8','DEFERRED':'#64748b'
  }};
  return map[s] || '#94a3b8';
}}
function statusBg(s) {{
  const map = {{
    'CONFIRMED':'#14532d','PARTIAL':'#431407','NOT CONFIRMED':'#450a0a',
    'QUEUED':'#422006','BLOCKED':'#1f2937','FLAGGED':'#3b0764',
    'INCONCLUSIVE':'#1e293b','DEFERRED':'#0f172a'
  }};
  return map[s] || '#1e293b';
}}
function metricClass(v, key) {{
  if (v === null || v === undefined) return 'na';
  if (key === 'sharpe') return v >= 1.0 ? 'good' : v >= 0.5 ? 'ok' : 'bad';
  if (key === 'maxdd') return v >= -15 ? 'good' : v >= -25 ? 'ok' : 'bad';
  if (key === 'cagr') return v >= 15 ? 'good' : v >= 5 ? 'ok' : 'bad';
  return '';
}}
function fmt(v, decimals=2) {{
  if (v === null || v === undefined) return '<span class="metric na">—</span>';
  return v;
}}
function fmtSharpe(v) {{
  if (v === null || v === undefined) return '<span class="metric na">—</span>';
  const cls = metricClass(v, 'sharpe');
  return `<span class="metric ${{cls}}">${{v.toFixed(2)}}</span>`;
}}
function fmtDD(v) {{
  if (v === null || v === undefined) return '<span class="metric na">—</span>';
  const cls = metricClass(v, 'maxdd');
  const sign = v > 0 ? '-' : '';
  return `<span class="metric ${{cls}}">${{v < 0 ? v.toFixed(1) : '-'+v.toFixed(1)}}%</span>`;
}}

function renderTable() {{
  const tbody = document.getElementById('tableBody');
  const q = document.getElementById('searchBox').value.toLowerCase();
  const sf = document.getElementById('statusFilter').value;
  const ff = document.getElementById('familyFilter').value || familyFilterValue;

  let rows = [...DATA];
  if (q) rows = rows.filter(r =>
    r.id.toLowerCase().includes(q) ||
    r.desc.toLowerCase().includes(q) ||
    r.family.toLowerCase().includes(q) ||
    r.full.toLowerCase().includes(q)
  );
  if (sf) rows = rows.filter(r => r.status === sf);
  if (ff) rows = rows.filter(r => r.family === ff);

  rows.sort((a, b) => {{
    let av = a[sortKey], bv = b[sortKey];
    if (av === null || av === undefined) av = sortDir === 1 ? -Infinity : Infinity;
    if (bv === null || bv === undefined) bv = sortDir === 1 ? -Infinity : Infinity;
    if (typeof av === 'string') return sortDir * av.localeCompare(bv);
    return sortDir * (av - bv);
  }});

  tbody.innerHTML = rows.map(r => `
    <tr id="row-${{r.id}}" onclick="selectHyp('${{r.id}}')" class="${{selectedId === r.id ? 'selected' : ''}}">
      <td><span class="hid">${{r.id}}</span></td>
      <td><span class="badge" style="background:${{statusBg(r.status)}};color:${{statusColor(r.status)}}">${{r.status}}</span></td>
      <td><span class="desc-cell" title="${{r.desc}}">${{r.desc}}</span></td>
      <td>${{fmtSharpe(r.sharpe)}}</td>
      <td>${{fmtDD(r.maxdd)}}</td>
      <td style="color:#475569;font-size:11px">${{r.date || '—'}}</td>
    </tr>
  `).join('');

  document.getElementById('countLabel').textContent = `${{rows.length}} shown`;
  updateSortArrows();
}}

function applyFilters() {{
  familyFilterValue = '';
  document.getElementById('activeFilterChip').className = 'active-filter';
  renderTable();
}}

function clearFilters() {{
  document.getElementById('searchBox').value = '';
  document.getElementById('statusFilter').value = '';
  document.getElementById('familyFilter').value = '';
  familyFilterValue = '';
  document.getElementById('activeFilterChip').className = 'active-filter';
  renderTable();
}}

function filterByFamily(fam) {{
  familyFilterValue = fam;
  document.getElementById('familyFilter').value = '';
  const chip = document.getElementById('activeFilterChip');
  chip.textContent = '× ' + fam;
  chip.className = 'active-filter visible';
  chip.onclick = clearFilters;
  renderTable();
}}

function sortBy(key) {{
  if (sortKey === key) sortDir *= -1;
  else {{ sortKey = key; sortDir = -1; }}
  renderTable();
}}

function updateSortArrows() {{
  ['num','status','sharpe','maxdd','date'].forEach(k => {{
    const el = document.getElementById('arr-'+k);
    if (!el) return;
    el.textContent = sortKey === k ? (sortDir === 1 ? '↑' : '↓') : '↕';
    el.style.opacity = sortKey === k ? '1' : '0.3';
  }});
}}

function selectHyp(id) {{
  selectedId = id;
  const h = DATA.find(d => d.id === id);
  if (!h) return;

  // Update table selection
  document.querySelectorAll('.hyp-table tr').forEach(tr => tr.classList.remove('selected'));
  const row = document.getElementById('row-'+id);
  if (row) row.classList.add('selected');

  const sc = h.sharpe !== null ? `color:${{statusColor(metricClass(h.sharpe,'sharpe') === 'good' ? 'CONFIRMED' : metricClass(h.sharpe,'sharpe') === 'ok' ? 'PARTIAL' : 'NOT CONFIRMED')}}` : 'color:#475569';

  const metricsHtml = `
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="label">OOS Sharpe</div>
        <div class="value" style="${{h.sharpe !== null ? 'color:'+statusColor(metricClass(h.sharpe,'sharpe')==='good'?'CONFIRMED':metricClass(h.sharpe,'sharpe')==='ok'?'PARTIAL':'NOT CONFIRMED') : 'color:#334155'}}">${{h.sharpe !== null ? h.sharpe.toFixed(3) : '—'}}</div>
      </div>
      <div class="metric-card">
        <div class="label">OOS MaxDD</div>
        <div class="value" style="${{h.maxdd !== null ? 'color:'+statusColor(metricClass(h.maxdd,'maxdd')==='good'?'CONFIRMED':metricClass(h.maxdd,'maxdd')==='ok'?'PARTIAL':'NOT CONFIRMED') : 'color:#334155'}}">${{h.maxdd !== null ? h.maxdd.toFixed(1)+'%' : '—'}}</div>
      </div>
      <div class="metric-card">
        <div class="label">OOS CAGR</div>
        <div class="value" style="${{h.cagr !== null ? 'color:'+statusColor(metricClass(h.cagr,'cagr')==='good'?'CONFIRMED':metricClass(h.cagr,'cagr')==='ok'?'PARTIAL':'NOT CONFIRMED') : 'color:#334155'}}">${{h.cagr !== null ? h.cagr.toFixed(1)+'%' : '—'}}</div>
      </div>
      <div class="metric-card">
        <div class="label">OOS Win Rate</div>
        <div class="value" style="${{h.wr !== null ? 'color:#60a5fa' : 'color:#334155'}}">${{h.wr !== null ? h.wr.toFixed(1)+'%' : '—'}}</div>
      </div>
    </div>`;

  document.getElementById('detailCard').innerHTML = `
    <div class="detail-hid">${{h.id}}</div>
    <div class="detail-status">
      <span class="badge" style="background:${{statusBg(h.status)}};color:${{statusColor(h.status)}};font-size:12px;padding:4px 10px">${{h.status}}</span>
      ${{h.date ? `<span style="color:#475569;font-size:11px;margin-left:8px">${{h.date}}</span>` : ''}}
      <span class="family-tag" style="margin-left:8px">${{h.family}}</span>
    </div>
    <div class="detail-desc">${{h.desc}}</div>
    ${{metricsHtml}}
    <div class="detail-section">
      <div class="detail-section-title">Full Entry (truncated)</div>
      <div class="detail-full">${{h.full.replace(/</g,'&lt;').replace(/>/g,'&gt;')}}</div>
    </div>
    ${{h.script ? `<div class="detail-section"><div class="detail-section-title">Script</div><div class="script-link">${{h.script}}</div></div>` : ''}}
    <button class="copy-btn" id="copyBtn" onclick="copyToClipboard('${{id}}')">📋 Copy H${{h.num}} summary to clipboard</button>
  `;
}}

function copyToClipboard(id) {{
  const h = DATA.find(d => d.id === id);
  if (!h) return;
  const text = `${{h.id}} [${{h.status}}] — ${{h.desc}}
Sharpe: ${{h.sharpe ?? 'N/A'}} | MaxDD: ${{h.maxdd ?? 'N/A'}}% | CAGR: ${{h.cagr ?? 'N/A'}}% | Family: ${{h.family}}
${{h.script ? 'Script: '+h.script : ''}}`;
  navigator.clipboard.writeText(text).then(() => {{
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✓ Copied!';
    btn.classList.add('copied');
    setTimeout(() => {{
      btn.textContent = '📋 Copy H${{h.num}} summary to clipboard';
      btn.classList.remove('copied');
    }}, 2000);
  }});
}}

// Init
renderTable();
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("Parsing hypotheses...")
    entries = parse_hypotheses()
    print(f"Parsed {len(entries)} entries")

    status_counts = {}
    for e in entries:
        status_counts[e["status"]] = status_counts.get(e["status"], 0) + 1
    for k, v in sorted(status_counts.items()):
        print(f"  {k}: {v}")

    print("Generating HTML...")
    html = generate_html(entries)

    out = Path("/workspace/agent/artifacts/research_lab.html")
    out.write_text(html)
    print(f"Written: {out} ({len(html):,} bytes)")
