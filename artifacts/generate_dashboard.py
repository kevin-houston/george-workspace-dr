#!/usr/bin/env python3
"""
George Trading Command Center — HTML Artifact Generator
Reads wiki/paper-trading/hypothesis data and produces a self-contained HTML dashboard.
Run: python3 /workspace/agent/artifacts/generate_dashboard.py
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
OUT = WORKSPACE / "artifacts" / "trading_dashboard.html"

# ── Data loaders ──────────────────────────────────────────────────────────────

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default

def load_text(path):
    try:
        return Path(path).read_text()
    except Exception:
        return ""

def parse_hypothesis_log():
    """Extract H-number entries from hypothesis-log.md frontmatter."""
    text = load_text(WORKSPACE / "wiki/trading/backtesting/hypothesis-log.md")
    entries = []
    for line in text.splitlines():
        m = re.match(r'^(h\d+)_status:\s+(.+)', line.strip())
        if m:
            hnum = m.group(1).upper()
            status_text = m.group(2).strip()
            if status_text.startswith("CONFIRMED"):
                status = "CONFIRMED"
            elif status_text.startswith("NOT CONFIRMED"):
                status = "NOT CONFIRMED"
            elif status_text.startswith("QUEUED"):
                status = "QUEUED"
            elif status_text.startswith("PARTIAL"):
                status = "PARTIAL"
            elif status_text.startswith("BLOCKED"):
                status = "BLOCKED"
            elif status_text.startswith("IN-PROGRESS"):
                status = "IN-PROGRESS"
            else:
                status = "UNKNOWN"
            # Extract short description (text after status keyword up to first —)
            desc_match = re.search(r'(?:CONFIRMED|NOT CONFIRMED|QUEUED|PARTIAL|BLOCKED|IN-PROGRESS)[^—]*—\s*(.+?)(?:\.|;|$)', status_text)
            desc = desc_match.group(1).strip() if desc_match else status_text[:80]
            entries.append({"h": hnum, "status": status, "desc": desc})
    return entries

def parse_dream_cycle_changelog():
    """Get latest dream cycle changelog."""
    changelog_dir = WORKSPACE / "dream_cycle/changelogs"
    changelogs = sorted(changelog_dir.glob("*.md"), reverse=True) if changelog_dir.exists() else []
    if not changelogs:
        return {"date": "—", "applied": 0, "flagged": 0, "items": []}
    latest = changelogs[0]
    text = latest.read_text()
    date = latest.stem
    applied = int(re.search(r'\*\*Applied\*\*:\s*(\d+)', text).group(1)) if re.search(r'\*\*Applied\*\*:\s*(\d+)', text) else 0
    flagged = int(re.search(r'\*\*Flagged.*?\*\*:\s*(\d+)', text).group(1)) if re.search(r'\*\*Flagged.*?\*\*:\s*(\d+)', text) else 0
    items = re.findall(r'^\d+\.\s+\*\*(.+?)\*\*', text, re.MULTILINE)
    return {"date": date, "applied": applied, "flagged": flagged, "items": items}

def parse_dream_cycle_staged():
    """Get pending staged proposals across all dated directories."""
    staged_dir = WORKSPACE / "dream_cycle/staged"
    pending = []
    if not staged_dir.exists():
        return pending
    for date_dir in sorted(staged_dir.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        for f in sorted(date_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text())
                if d.get("apply_status") == "pending":
                    pending.append({"date": date_dir.name, "title": d.get("title",""), "risk": d.get("risk_level","")})
            except Exception:
                pass
    return pending[:10]

def parse_paper_trading_trades():
    """Last 3 ETF rotation rebalance entries."""
    trades = load_json(WORKSPACE / "backtesting/paper_trading/h112_monthly_trades.json", [])
    if isinstance(trades, list):
        return trades[-3:]
    return []

def parse_pead_state():
    cursor = load_json(WORKSPACE / "backtesting/paper_trading/pead_intraday_cursor.json", {})
    watchlist = load_json(WORKSPACE / "backtesting/paper_trading/pead_watchlist.json", {})
    positions = load_json(WORKSPACE / "backtesting/paper_trading/pead_positions.json", [])
    return {
        "last_check": cursor.get("last_date", "—"),
        "candidates": watchlist.get("candidates", []),
        "reason": watchlist.get("reason", ""),
        "open_positions": len(positions) if isinstance(positions, list) else 0,
    }

def parse_latest_research_log():
    log_dir = WORKSPACE / "wiki/trading/research-log"
    logs = sorted(log_dir.glob("*.md"), reverse=True) if log_dir.exists() else []
    if not logs:
        return {"date": "—", "summary": ""}
    latest = logs[0]
    text = latest.read_text()
    # Extract first H2 section titles
    sections = re.findall(r'^## (.+)', text, re.MULTILINE)
    return {"date": latest.stem, "sections": sections[:6]}

# ── HTML builder ──────────────────────────────────────────────────────────────

STATUS_COLOR = {
    "CONFIRMED":     ("#22c55e", "#052e16"),
    "NOT CONFIRMED": ("#ef4444", "#2d0000"),
    "QUEUED":        ("#facc15", "#1c1500"),
    "PARTIAL":       ("#fb923c", "#1e0e00"),
    "BLOCKED":       ("#94a3b8", "#1e1e2e"),
    "IN-PROGRESS":   ("#60a5fa", "#0c1a2e"),
    "UNKNOWN":       ("#6b7280", "#1a1a1a"),
    "ACTIVE":        ("#22c55e", "#052e16"),
    "INACTIVE":      ("#94a3b8", "#1e1e2e"),
}

def badge(status):
    fg, bg = STATUS_COLOR.get(status, ("#6b7280", "#1a1a1a"))
    return f'<span class="badge" style="background:{bg};color:{fg};border:1px solid {fg}40">{status}</span>'

def action_btn(label, msg, icon="💬"):
    escaped = msg.replace('"', '&quot;').replace("'", "\\'")
    return f'''<button class="action-btn" onclick="copyMsg('{escaped}')" title="Copy to clipboard, then paste to George">{icon} {label}</button>'''

def generate_html(data):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Hypothesis rows — last 15 entries
    hyp_rows = ""
    for e in data["hypotheses"][-15:]:
        fg, bg = STATUS_COLOR.get(e["status"], ("#6b7280","#1a1a1a"))
        hyp_rows += f"""
        <tr>
          <td style="color:#e2e8f0;font-weight:700">{e['h']}</td>
          <td>{badge(e['status'])}</td>
          <td style="color:#94a3b8;font-size:0.82em">{e['desc'][:90]}</td>
        </tr>"""

    # ETF rotation trades
    trade_rows = ""
    for t in data["etf_trades"]:
        tgt = ", ".join(t.get("target", {}).keys()) if t.get("target") else "—"
        eq = f"${t.get('equity', 0):,.0f}" if t.get("equity") else "—"
        trade_rows += f"""
        <tr>
          <td style="color:#e2e8f0">{t.get('date','—')}</td>
          <td style="color:#60a5fa">{tgt}</td>
          <td style="color:#22c55e">{eq}</td>
        </tr>"""

    # Dream cycle items
    dc_items = "".join(f'<li>{item}</li>' for item in data["dream_changelog"]["items"])
    staged_items = ""
    for s in data["staged_proposals"]:
        risk_color = {"low":"#22c55e","medium":"#facc15","high":"#ef4444"}.get(s["risk"],"#94a3b8")
        staged_items += f'<li><span style="color:{risk_color};font-size:0.8em;font-weight:700">[{s["risk"].upper()}]</span> {s["title"][:70]}</li>'

    # Research log sections
    research_secs = "".join(f'<li style="color:#94a3b8">{s}</li>' for s in data["research"]["sections"])

    # PEAD candidates
    pead_cands = ", ".join(data["pead"]["candidates"]) if data["pead"]["candidates"] else f'none ({data["pead"]["reason"]})'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>George — Trading Command Center</title>
<style>
  :root {{
    --bg: #0f1117;
    --surface: #1a1d2e;
    --surface2: #242840;
    --border: #2d3154;
    --text: #e2e8f0;
    --muted: #64748b;
    --green: #22c55e;
    --yellow: #facc15;
    --red: #ef4444;
    --blue: #60a5fa;
    --purple: #a78bfa;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
    line-height: 1.5;
    min-height: 100vh;
  }}
  .header {{
    background: linear-gradient(135deg, #1a1d2e 0%, #0f1117 100%);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .header h1 {{
    font-size: 1.2em;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: var(--text);
  }}
  .header h1 span {{ color: var(--blue); }}
  .header .meta {{ color: var(--muted); font-size: 0.8em; text-align: right; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 16px;
    padding: 20px 24px;
    max-width: 1600px;
    margin: 0 auto;
  }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }}
  .card.wide {{ grid-column: span 2; }}
  .card-header {{
    background: var(--surface2);
    padding: 10px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
  }}
  .card-header h2 {{ font-size: 0.85em; font-weight: 700; letter-spacing: 0.08em; color: var(--muted); text-transform: uppercase; }}
  .card-header .indicator {{ width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 6px var(--green); animation: pulse 2s infinite; }}
  .indicator.yellow {{ background: var(--yellow); box-shadow: 0 0 6px var(--yellow); }}
  .indicator.gray {{ background: var(--muted); box-shadow: none; animation: none; }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.5}} }}
  .card-body {{ padding: 14px 16px; }}
  .strategy-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }}
  .strategy-row:last-child {{ border-bottom: none; }}
  .strategy-name {{ color: var(--text); font-weight: 700; font-size: 0.9em; }}
  .strategy-meta {{ color: var(--muted); font-size: 0.78em; margin-top: 2px; }}
  .strategy-stat {{ text-align: right; }}
  .stat-val {{ color: var(--green); font-weight: 700; font-size: 0.95em; }}
  .stat-label {{ color: var(--muted); font-size: 0.75em; }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75em;
    font-weight: 700;
    letter-spacing: 0.04em;
    white-space: nowrap;
  }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ color: var(--muted); font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.06em; padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--border); }}
  td {{ padding: 7px 8px; border-bottom: 1px solid #1e2235; font-size: 0.83em; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #1e2235; }}
  .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
  .action-btn {{
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-family: inherit;
    font-size: 0.8em;
    transition: all 0.15s;
  }}
  .action-btn:hover {{ background: #2d3154; border-color: var(--blue); color: var(--blue); }}
  .action-btn:active {{ transform: scale(0.97); }}
  .toast {{
    position: fixed; bottom: 24px; right: 24px;
    background: #1e2d1e; border: 1px solid var(--green); color: var(--green);
    padding: 10px 18px; border-radius: 8px;
    font-size: 0.85em; font-weight: 700;
    opacity: 0; transition: opacity 0.2s;
    pointer-events: none; z-index: 9999;
  }}
  .toast.show {{ opacity: 1; }}
  ul {{ list-style: none; padding: 0; }}
  ul li {{ padding: 4px 0; border-bottom: 1px solid #1e2235; color: var(--muted); font-size: 0.83em; }}
  ul li:last-child {{ border-bottom: none; }}
  .metric-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 12px; }}
  .metric {{ background: var(--surface2); border-radius: 6px; padding: 10px; text-align: center; border: 1px solid var(--border); }}
  .metric-val {{ font-size: 1.1em; font-weight: 700; color: var(--green); }}
  .metric-lbl {{ font-size: 0.7em; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; margin-top: 2px; }}
  .pead-status {{ display: flex; gap: 16px; padding: 10px 0; }}
  .pead-item {{ flex: 1; background: var(--surface2); border-radius: 6px; padding: 8px 12px; border: 1px solid var(--border); }}
  .divider {{ height: 1px; background: var(--border); margin: 12px 0; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>⚡ <span>George</span> — Trading Command Center</h1>
    <div class="meta" style="margin-top:4px;font-size:0.75em;color:#475569">LLM Wiki + HTML Artifact</div>
  </div>
  <div class="meta">
    <div style="color:#22c55e;font-weight:700">● LIVE (Paper)</div>
    <div>Updated: {now}</div>
    <div>Phase 2→3 — Paper Trading Active</div>
  </div>
</div>

<div class="grid">

  <!-- PAPER TRADING STRATEGIES -->
  <div class="card">
    <div class="card-header">
      <h2>📈 Active Strategies</h2>
      <div class="indicator"></div>
    </div>
    <div class="card-body">
      <div class="strategy-row">
        <div>
          <div class="strategy-name">H026 ETF Sector Rotation</div>
          <div class="strategy-meta">H149 · 25 ETFs · TSMOM top-1 · Monthly rebalance</div>
          <div class="strategy-meta">Started: 2026-04-28</div>
        </div>
        <div class="strategy-stat">
          <div class="stat-val">3.007</div><div class="stat-label">OOS Sharpe</div>
          <div style="margin-top:4px">{badge('ACTIVE')}</div>
        </div>
      </div>
      <div class="strategy-row">
        <div>
          <div class="strategy-name">H181 Industry-Adjusted Reversal</div>
          <div class="strategy-meta">30 stocks · 8 GICS sectors · Long bottom-6</div>
          <div class="strategy-meta">Started: 2026-05-10 · Corr(H026)=0.293</div>
        </div>
        <div class="strategy-stat">
          <div class="stat-val">1.138</div><div class="stat-label">OOS Sharpe</div>
          <div style="margin-top:4px">{badge('ACTIVE')}</div>
        </div>
      </div>
      <div class="strategy-row">
        <div>
          <div class="strategy-name">PEAD-NLP H174</div>
          <div class="strategy-meta">FinBERT 8-K scorer · Gap ≥3% · 5% per position</div>
          <div class="strategy-meta">Open positions: {data['pead']['open_positions']} · Last check: {data['pead']['last_check']}</div>
        </div>
        <div class="strategy-stat">
          <div class="stat-val">80.8%</div><div class="stat-label">OOS Win Rate</div>
          <div style="margin-top:4px">{badge('ACTIVE')}</div>
        </div>
      </div>
      <div class="strategy-row">
        <div>
          <div class="strategy-name">Iron Condor (SPY)</div>
          <div class="strategy-meta">IC-2026-04-26-001 · $645p/$670p/$775c/$800c</div>
          <div class="strategy-meta">Expiry: Jun 12 · Credit: $533 · Max loss: $1,967</div>
        </div>
        <div class="strategy-stat">
          <div class="stat-val">$533</div><div class="stat-label">Credit recv.</div>
          <div style="margin-top:4px">{badge('INACTIVE')}</div>
        </div>
      </div>
      <div class="actions">
        {action_btn("Check Alpaca positions", "George check current Alpaca paper trading positions for all strategies", "📊")}
        {action_btn("H026 signal today", "George what is the H026 ETF rotation signal for today's rebalance?", "🔄")}
        {action_btn("PEAD watchlist", "George run the PEAD overnight scan and show me tomorrow's watchlist", "🔍")}
        {action_btn("H181 rebalance", "George run the H181 industry reversal rebalance and show me the target portfolio", "⚖️")}
      </div>
    </div>
  </div>

  <!-- PEAD DETAIL -->
  <div class="card">
    <div class="card-header">
      <h2>📰 PEAD-NLP Pipeline</h2>
      <div class="indicator {'gray' if not data['pead']['candidates'] else ''}"></div>
    </div>
    <div class="card-body">
      <div class="pead-status">
        <div class="pead-item">
          <div class="metric-val" style="font-size:1.4em">{data['pead']['open_positions']}</div>
          <div class="metric-lbl">Open Positions</div>
        </div>
        <div class="pead-item">
          <div class="metric-val" style="font-size:1.4em;color:#facc15">{len(data['pead']['candidates'])}</div>
          <div class="metric-lbl">Candidates Today</div>
        </div>
        <div class="pead-item">
          <div class="metric-val" style="font-size:0.85em;color:#60a5fa">{data['pead']['last_check']}</div>
          <div class="metric-lbl">Last Check</div>
        </div>
      </div>
      <div class="divider"></div>
      <div style="color:#64748b;font-size:0.82em;margin-bottom:8px">Today's candidates: <span style="color:#e2e8f0">{pead_cands}</span></div>
      <div class="divider"></div>
      <div style="color:#64748b;font-size:0.78em;margin-bottom:6px;text-transform:uppercase;letter-spacing:.06em">Pipeline stages</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px">
        <div style="background:#1e2235;border-radius:5px;padding:7px 10px;font-size:0.78em">
          <div style="color:#a78bfa;font-weight:700">1. Overnight</div>
          <div style="color:#64748b">EDGAR 8-K → FinBERT → watchlist</div>
        </div>
        <div style="background:#1e2235;border-radius:5px;padding:7px 10px;font-size:0.78em">
          <div style="color:#a78bfa;font-weight:700">2. Open</div>
          <div style="color:#64748b">Gap ≥3% → market buy OPG order</div>
        </div>
        <div style="background:#1e2235;border-radius:5px;padding:7px 10px;font-size:0.78em">
          <div style="color:#a78bfa;font-weight:700">3. Intraday</div>
          <div style="color:#64748b">Stop loss check · trailing stop</div>
        </div>
        <div style="background:#1e2235;border-radius:5px;padding:7px 10px;font-size:0.78em">
          <div style="color:#a78bfa;font-weight:700">4. Exit</div>
          <div style="color:#64748b">T+20 days or stop triggered</div>
        </div>
      </div>
      <div style="color:#64748b;font-size:0.78em;margin-bottom:6px;text-transform:uppercase;letter-spacing:.06em">H195 queued — PEAD.txt upgrade</div>
      <div style="color:#64748b;font-size:0.8em">SUE.txt: transcript FinBERT delta → larger PEAD signal for low-coverage stocks</div>
    </div>
  </div>

  <!-- HYPOTHESIS PIPELINE — wide -->
  <div class="card wide">
    <div class="card-header">
      <h2>🧪 Hypothesis Pipeline</h2>
      <span style="color:#64748b;font-size:0.8em">Last 15 entries from hypothesis-log.md</span>
    </div>
    <div class="card-body">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div>
          <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Recent results</div>
          <table>
            <thead><tr><th>H#</th><th>Status</th><th>Description</th></tr></thead>
            <tbody>{hyp_rows}</tbody>
          </table>
        </div>
        <div>
          <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Queue — next tests</div>
          <table>
            <thead><tr><th>H#</th><th>Strategy</th><th>Signal</th></tr></thead>
            <tbody>
              <tr><td style="color:#e2e8f0;font-weight:700">H190</td><td style="color:#facc15">QUEUED</td><td style="color:#94a3b8;font-size:.82em">H188+H181 blend (30-stock universe)</td></tr>
              <tr><td style="color:#e2e8f0;font-weight:700">H191</td><td style="color:#facc15">QUEUED</td><td style="color:#94a3b8;font-size:.82em">Low-Vol Decile (252d daily vol)</td></tr>
              <tr><td style="color:#e2e8f0;font-weight:700">H192</td><td style="color:#facc15">QUEUED</td><td style="color:#94a3b8;font-size:.82em">BAB-style Beta Rank</td></tr>
              <tr><td style="color:#e2e8f0;font-weight:700">H193</td><td style="color:#facc15">QUEUED</td><td style="color:#94a3b8;font-size:.82em">Sector-Neutral Low-Vol</td></tr>
              <tr><td style="color:#e2e8f0;font-weight:700">H195</td><td style="color:#facc15">QUEUED</td><td style="color:#94a3b8;font-size:.82em">PEAD.txt transcript SUE upgrade</td></tr>
            </tbody>
          </table>
          <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin:14px 0 8px">H185/H186 blockers</div>
          <div style="color:#64748b;font-size:0.8em">H185 (Kalshi PolySwarm): needs 6mo resolved market history<br>H186 (UOA): blocked — Polygon options ~$200/mo required</div>
        </div>
      </div>
      <div class="actions" style="margin-top:16px">
        {action_btn("Run H190", "George run H190: backtest the H188 + H181 blend on the 30-stock universe", "▶️")}
        {action_btn("Run H191", "George run H191: low-vol decile backtest (252d daily vol) on the 30-stock universe", "▶️")}
        {action_btn("Run H192", "George run H192: BAB-style beta rank backtest on the 30-stock universe", "▶️")}
        {action_btn("Full status", "George give me a full status report on the hypothesis pipeline and paper trading", "📋")}
      </div>
    </div>
  </div>

  <!-- ETF ROTATION TRADE LOG -->
  <div class="card">
    <div class="card-header">
      <h2>🔄 ETF Rotation Log</h2>
      <span style="color:#64748b;font-size:0.8em">H149 · H026 signal</span>
    </div>
    <div class="card-body">
      <div class="metric-grid">
        <div class="metric">
          <div class="metric-val">382×</div>
          <div class="metric-lbl">Cumul. Return</div>
        </div>
        <div class="metric">
          <div class="metric-val">3.007</div>
          <div class="metric-lbl">OOS Sharpe</div>
        </div>
        <div class="metric">
          <div class="metric-val" style="color:#ef4444">-9.6%</div>
          <div class="metric-lbl">Max DD</div>
        </div>
      </div>
      <table>
        <thead><tr><th>Date</th><th>Holdings</th><th>Equity</th></tr></thead>
        <tbody>{trade_rows if trade_rows else '<tr><td colspan="3" style="color:#64748b;text-align:center">No trade log entries yet</td></tr>'}</tbody>
      </table>
    </div>
  </div>

  <!-- DREAM CYCLE -->
  <div class="card">
    <div class="card-header">
      <h2>🌙 Dream Cycle</h2>
      <div class="indicator yellow"></div>
    </div>
    <div class="card-body">
      <div style="display:flex;gap:12px;margin-bottom:12px">
        <div class="metric" style="flex:1">
          <div class="metric-val" style="color:#22c55e">{data['dream_changelog']['applied']}</div>
          <div class="metric-lbl">Applied</div>
        </div>
        <div class="metric" style="flex:1">
          <div class="metric-val" style="color:#ef4444">{data['dream_changelog']['flagged']}</div>
          <div class="metric-lbl">Flagged</div>
        </div>
        <div class="metric" style="flex:2">
          <div class="metric-val" style="font-size:0.85em;color:#60a5fa">{data['dream_changelog']['date']}</div>
          <div class="metric-lbl">Last Run</div>
        </div>
      </div>
      <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Last applied</div>
      <ul>{dc_items or '<li style="color:#64748b">—</li>'}</ul>
      {'<div style="color:#64748b;font-size:.78em;text-transform:uppercase;letter-spacing:.06em;margin:12px 0 6px">Pending proposals</div><ul>' + staged_items + '</ul>' if staged_items else ''}
      <div class="actions">
        {action_btn("Run dream scan", "George run the dream cycle research scan for today", "🔬")}
        {action_btn("Apply staged", "George apply all pending staged dream cycle proposals", "✅")}
      </div>
    </div>
  </div>

  <!-- PERFORMANCE SUMMARY -->
  <div class="card">
    <div class="card-header">
      <h2>📊 Strategy Performance</h2>
      <span style="color:#64748b;font-size:0.8em">OOS metrics</span>
    </div>
    <div class="card-body">
      <table>
        <thead><tr><th>Strategy</th><th>Sharpe</th><th>CAGR</th><th>MaxDD</th><th>Corr</th></tr></thead>
        <tbody>
          <tr>
            <td style="color:#e2e8f0;font-weight:700">H026 ETF Rot.</td>
            <td style="color:#22c55e">3.007</td>
            <td style="color:#22c55e">—</td>
            <td style="color:#ef4444">-9.6%</td>
            <td style="color:#64748b">baseline</td>
          </tr>
          <tr>
            <td style="color:#e2e8f0;font-weight:700">H181 Ind. Rev.</td>
            <td style="color:#22c55e">1.138</td>
            <td style="color:#22c55e">24.6%</td>
            <td style="color:#ef4444">-18.4%</td>
            <td style="color:#64748b">0.293</td>
          </tr>
          <tr>
            <td style="color:#e2e8f0;font-weight:700">H188 52wk High</td>
            <td style="color:#22c55e">0.774</td>
            <td style="color:#22c55e">11.4%</td>
            <td style="color:#ef4444">-13.6%</td>
            <td style="color:#64748b">0.389†</td>
          </tr>
          <tr>
            <td style="color:#e2e8f0;font-weight:700">H174 PEAD-NLP</td>
            <td style="color:#22c55e">—</td>
            <td style="color:#22c55e">—</td>
            <td style="color:#64748b">—</td>
            <td style="color:#64748b">—</td>
          </tr>
          <tr>
            <td style="color:#e2e8f0;font-weight:700">H189 60/40 Blend</td>
            <td style="color:#22c55e">2.402</td>
            <td style="color:#64748b">—</td>
            <td style="color:#ef4444">-9.8%</td>
            <td style="color:#64748b">—</td>
          </tr>
        </tbody>
      </table>
      <div style="color:#475569;font-size:0.75em;margin-top:10px">† Corr(H188,H181). All OOS 2021-2026 except H026 (2018-2026).</div>
      <div class="actions">
        {action_btn("Portfolio report", "George generate a full portfolio performance report comparing all active strategies", "📈")}
        {action_btn("Correlation matrix", "George show me the current OOS correlation matrix across all confirmed strategies", "🔢")}
      </div>
    </div>
  </div>

  <!-- RESEARCH LOG -->
  <div class="card">
    <div class="card-header">
      <h2>📚 Research Log</h2>
      <span style="color:#64748b;font-size:0.8em">Latest: {data['research']['date']}</span>
    </div>
    <div class="card-body">
      <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Today's sessions</div>
      <ul>{research_secs or '<li style="color:#64748b">—</li>'}</ul>
      <div class="divider"></div>
      <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Wiki stats</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
        <div class="metric"><div class="metric-val">60</div><div class="metric-lbl">Pages</div></div>
        <div class="metric"><div class="metric-val">189</div><div class="metric-lbl">H-series</div></div>
        <div class="metric"><div class="metric-val" style="color:#22c55e">3</div><div class="metric-lbl">Live strats</div></div>
      </div>
      <div class="actions">
        {action_btn("Nightly research", "George run the nightly research session: read hypothesis log, pick next 2 hypotheses, test them", "🌙")}
        {action_btn("Wiki query", "George query the wiki about low-volatility anomaly and what hypotheses are queued", "🔎")}
        {action_btn("Wiki lint", "George run a wiki lint health check and fix any issues found", "🩺")}
      </div>
    </div>
  </div>

  <!-- QUICK ACTIONS -->
  <div class="card">
    <div class="card-header">
      <h2>⚡ Quick Actions</h2>
      <span style="color:#64748b;font-size:0.8em">Copy → paste to George in Telegram</span>
    </div>
    <div class="card-body">
      <div style="color:#64748b;font-size:0.78em;margin-bottom:12px">Click any button to copy the command to your clipboard, then paste it to George in Telegram.</div>
      <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">📊 Trading</div>
      <div class="actions" style="margin-top:0">
        {action_btn("Full status report", "George give me a complete status report: paper trading positions, open P&L, next rebalance dates, and any alerts", "📋")}
        {action_btn("Alpaca equity", "George check current Alpaca paper account equity and buying power", "💰")}
        {action_btn("Deploy H190", "George please deploy H190 to Alpaca paper trading after backtesting confirms it", "🚀")}
      </div>
      <div class="divider"></div>
      <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">🔬 Research</div>
      <div class="actions" style="margin-top:0">
        {action_btn("H185 Kalshi data", "George pull and cache 6 months of resolved Kalshi market history to unblock H185", "📥")}
        {action_btn("Regenerate dashboard", "George regenerate the HTML trading dashboard artifact with latest data", "🔄")}
        {action_btn("DR backup", "George run a git backup and push to GitHub", "💾")}
      </div>
      <div class="divider"></div>
      <div style="color:#64748b;font-size:0.78em;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">🌙 Nightly automation</div>
      <div class="actions" style="margin-top:0">
        {action_btn("Reschedule research", "George update the nightly research schedule to prioritize low-volatility hypotheses H191-H193", "⏰")}
        {action_btn("Pause dream cycle", "George pause the dream cycle build phase until further notice", "⏸️")}
      </div>
    </div>
  </div>

</div>

<div id="toast" class="toast">✓ Copied to clipboard</div>

<script>
function copyMsg(msg) {{
  navigator.clipboard.writeText(msg).then(() => {{
    const t = document.getElementById('toast');
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2000);
  }}).catch(() => {{
    // Fallback: prompt
    prompt('Copy this message to paste to George:', msg);
  }});
}}
</script>
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    data = {
        "hypotheses": parse_hypothesis_log(),
        "etf_trades": parse_paper_trading_trades(),
        "pead": parse_pead_state(),
        "dream_changelog": parse_dream_cycle_changelog(),
        "staged_proposals": parse_dream_cycle_staged(),
        "research": parse_latest_research_log(),
    }

    html = generate_html(data)
    OUT.write_text(html)
    print(f"✅ Dashboard written to {OUT}")
    print(f"   Hypotheses parsed: {len(data['hypotheses'])}")
    print(f"   ETF trade entries: {len(data['etf_trades'])}")
    print(f"   PEAD open positions: {data['pead']['open_positions']}")
    print(f"   Staged proposals pending: {len(data['staged_proposals'])}")
    return str(OUT)

if __name__ == "__main__":
    main()
