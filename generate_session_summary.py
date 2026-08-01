"""
Generates a self-contained HTML nightly session summary and publishes to here.now.
Usage: python3 generate_session_summary.py [YYYY-MM-DD]
Defaults to today. Prints the published URL on stdout.
"""

import sys
import re
import json
import subprocess
from pathlib import Path
from datetime import date, datetime

BASE = Path("/workspace/agent")

# ── Helpers ──────────────────────────────────────────────────────────────────

def esc(s):
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

def run(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw).stdout.strip()

# ── Data collection ───────────────────────────────────────────────────────────

def collect(target_date: str):
    data = {"date": target_date}

    # 1. Dream cycle changelog
    changelog_path = BASE / f"dream_cycle/changelogs/{target_date}.md"
    if changelog_path.exists():
        text = changelog_path.read_text()
        data["changelog"] = text
        m = re.search(r"\*\*Applied:\s*(\d+)\s*/\s*Skipped:\s*(\d+)\s*/\s*Flagged:\s*(\d+)\*\*", text)
        if m:
            data["applied"] = int(m.group(1))
            data["skipped"] = int(m.group(2))
            data["flagged"] = int(m.group(3))
        else:
            data["applied"] = data["skipped"] = data["flagged"] = 0
        # Extract section items (### lines)
        data["changelog_items"] = re.findall(r"^###\s+(.+)$", text, re.MULTILINE)
    else:
        data["changelog"] = ""
        data["applied"] = data["skipped"] = data["flagged"] = 0
        data["changelog_items"] = []

    # 2. Staged proposals
    staged_dir = BASE / f"dream_cycle/staged/{target_date}"
    proposals = []
    if staged_dir.exists():
        for f in sorted(staged_dir.glob("*.json")):
            try:
                p = json.loads(f.read_text())
                proposals.append(p)
            except Exception:
                pass
    data["proposals"] = proposals

    # 3. Git commits for this date
    commits_raw = run(
        f'git -C {BASE} log --since="{target_date} 00:00:00" '
        f'--until="{target_date} 23:59:59" --oneline'
    )
    data["commits"] = [c for c in commits_raw.splitlines() if c.strip()]

    # 4. Podcast
    podcast_path = BASE / f"podcasts/ai_podcast_{target_date}.md"
    if podcast_path.exists():
        text = podcast_path.read_text()
        m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        data["podcast_title"] = m.group(1).strip() if m else f"Podcast {target_date}"
        words = len(text.split())
        data["podcast_words"] = words
    else:
        data["podcast_title"] = None
        data["podcast_words"] = 0

    # 5. Dashboard URL
    state_path = BASE / ".herenow/state.json"
    data["dashboard_url"] = ""
    if state_path.exists():
        try:
            s = json.loads(state_path.read_text())
            data["dashboard_url"] = s.get("siteUrl", "")
        except Exception:
            pass

    # 6. Hypothesis log: hypotheses added today
    hyp_log = BASE / "wiki/trading/backtesting/hypothesis-log.md"
    new_hyps = []
    if hyp_log.exists():
        for line in hyp_log.read_text().splitlines():
            if target_date in line and re.match(r".*H\d{3}", line):
                new_hyps.append(line.strip())
    data["new_hypotheses"] = new_hyps

    return data


# ── HTML generation ───────────────────────────────────────────────────────────

STYLE = """
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--surface:#161b22;--surface2:#1c2128;--border:#30363d;
  --text:#e6edf3;--muted:#8b949e;
  --green:#3fb950;--red:#f85149;--yellow:#d29922;--blue:#58a6ff;--orange:#f0883e;
}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;line-height:1.6;padding:0;}

.header{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:baseline;justify-content:space-between;}
.header-title{font-size:16px;font-weight:700;letter-spacing:.3px;}
.header-sub{color:var(--muted);font-size:12px;}

.main{padding:20px 24px;max-width:1000px;margin:0 auto;display:flex;flex-direction:column;gap:16px;}

/* KPI row */
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 16px;}
.kpi-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:4px;}
.kpi-value{font-size:26px;font-weight:700;line-height:1.1;}
.kpi-value.green{color:var(--green);}
.kpi-value.blue{color:var(--blue);}
.kpi-value.yellow{color:var(--yellow);}
.kpi-value.red{color:var(--red);}
.kpi-value.muted{color:var(--muted);}

/* Section card */
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden;}
.card-header{padding:10px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.card-title{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);}
.card-badge{font-size:11px;background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:2px 8px;color:var(--muted);}
.card-body{padding:14px 16px;}

/* Proposals */
.proposal{padding:10px 0;border-bottom:1px solid var(--border);}
.proposal:last-child{border-bottom:none;}
.proposal-header{display:flex;align-items:baseline;gap:8px;margin-bottom:4px;}
.proposal-title{font-size:13px;font-weight:600;}
.risk-badge{font-size:10px;font-weight:600;padding:1px 7px;border-radius:8px;text-transform:uppercase;letter-spacing:.04em;}
.risk-medium{background:rgba(210,153,34,.18);color:var(--yellow);border:1px solid rgba(210,153,34,.3);}
.risk-high{background:rgba(248,81,73,.18);color:var(--red);border:1px solid rgba(248,81,73,.3);}
.risk-low{background:rgba(63,185,80,.18);color:var(--green);border:1px solid rgba(63,185,80,.3);}
.proposal-rationale{font-size:12px;color:var(--muted);margin-top:3px;}
.proposal-target{font-size:11px;color:var(--blue);font-family:monospace;margin-top:3px;}

/* Commit list */
.commit{padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;display:flex;gap:10px;}
.commit:last-child{border-bottom:none;}
.commit-hash{font-family:monospace;color:var(--blue);flex-shrink:0;}
.commit-msg{color:var(--text);}

/* Podcast */
.podcast-pill{display:inline-flex;align-items:center;gap:8px;background:var(--surface2);border:1px solid var(--border);border-radius:20px;padding:6px 14px;font-size:12px;}
.podcast-dot{width:8px;height:8px;border-radius:50%;background:var(--green);}

/* Links */
.link-row{display:flex;flex-wrap:wrap;gap:10px;}
.link-btn{display:inline-block;padding:7px 14px;border-radius:6px;font-size:12px;font-weight:500;text-decoration:none;border:1px solid var(--border);color:var(--blue);background:var(--surface);}
.link-btn:hover{border-color:var(--blue);}

/* Raw changelog */
pre{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:12px;font-size:11px;overflow-x:auto;white-space:pre-wrap;color:var(--muted);margin-top:10px;}

.empty{color:var(--muted);font-size:12px;padding:4px 0;}
</style>
"""

def risk_badge(risk):
    r = (risk or "").lower()
    cls = "risk-medium" if "medium" in r else ("risk-high" if "high" in r else "risk-low")
    return f'<span class="risk-badge {cls}">{esc(risk or "low")}</span>'


def generate_html(d):
    target_date = d["date"]
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M CT")

    # KPI row
    commit_count = len(d["commits"])
    applied = d["applied"]
    flagged = d["flagged"]
    podcast_ok = 1 if d["podcast_title"] else 0

    kpi_html = f"""
    <div class="kpi-row">
      <div class="kpi"><div class="kpi-label">Proposals Applied</div>
        <div class="kpi-value {'green' if applied > 0 else 'muted'}">{applied}</div></div>
      <div class="kpi"><div class="kpi-label">Flagged</div>
        <div class="kpi-value {'red' if flagged > 0 else 'muted'}">{flagged}</div></div>
      <div class="kpi"><div class="kpi-label">Commits</div>
        <div class="kpi-value blue">{commit_count}</div></div>
      <div class="kpi"><div class="kpi-label">Podcast</div>
        <div class="kpi-value {'green' if podcast_ok else 'muted'}">{('✓' if podcast_ok else '—')}</div></div>
    </div>"""

    # Dream cycle proposals
    if d["proposals"]:
        props_html = ""
        for p in d["proposals"]:
            status = p.get("apply_status", "pending")
            status_color = "green" if status == "applied" else ("red" if status == "skipped" else "yellow")
            rationale = (p.get("rationale") or "")[:300]
            if len(p.get("rationale") or "") > 300:
                rationale += "…"
            props_html += f"""
            <div class="proposal">
              <div class="proposal-header">
                <span class="proposal-title">{esc(p.get('title',''))}</span>
                {risk_badge(p.get('risk_level',''))}
                <span style="font-size:11px;color:var(--{status_color})">{esc(status)}</span>
              </div>
              <div class="proposal-rationale">{esc(rationale)}</div>
              <div class="proposal-target">{esc(p.get('target_file',''))}</div>
            </div>"""
        dc_body = props_html
    elif d["changelog_items"]:
        items_html = "".join(
            f'<div class="proposal"><div class="proposal-title">{esc(item)}</div></div>'
            for item in d["changelog_items"]
        )
        dc_body = items_html
    elif d["changelog"]:
        dc_body = f'<pre>{esc(d["changelog"][:2000])}</pre>'
    else:
        dc_body = '<p class="empty">No dream cycle data for this date.</p>'

    dc_section = f"""
    <div class="card">
      <div class="card-header">
        <span class="card-title">Dream Cycle</span>
        <span class="card-badge">{applied} applied · {flagged} flagged · {d['skipped']} skipped</span>
      </div>
      <div class="card-body">{dc_body}</div>
    </div>"""

    # Commits
    if d["commits"]:
        commits_html = "".join(
            f'<div class="commit"><span class="commit-hash">{esc(c[:7])}</span>'
            f'<span class="commit-msg">{esc(c[8:])}</span></div>'
            for c in d["commits"]
        )
    else:
        commits_html = '<p class="empty">No commits today.</p>'

    commits_section = f"""
    <div class="card">
      <div class="card-header">
        <span class="card-title">Commits</span>
        <span class="card-badge">{commit_count} today</span>
      </div>
      <div class="card-body">{commits_html}</div>
    </div>"""

    # Podcast
    if d["podcast_title"]:
        podcast_html = f"""
        <div class="card">
          <div class="card-header"><span class="card-title">AI Podcast</span></div>
          <div class="card-body">
            <div class="podcast-pill">
              <span class="podcast-dot"></span>
              <span>{esc(d['podcast_title'])}</span>
              <span style="color:var(--muted)">{d['podcast_words']:,} words</span>
            </div>
          </div>
        </div>"""
    else:
        podcast_html = ""

    # Links
    links = []
    if d["dashboard_url"]:
        links.append(f'<a class="link-btn" href="{esc(d["dashboard_url"])}" target="_blank">Dashboard ↗</a>')
        links.append(f'<a class="link-btn" href="{esc(d["dashboard_url"])}hypothesis-log.html" target="_blank">Hypothesis Log ↗</a>')
        links.append(f'<a class="link-btn" href="{esc(d["dashboard_url"])}portfolio-editor.html" target="_blank">Portfolio Editor ↗</a>')
    links_section = f"""
    <div class="card">
      <div class="card-header"><span class="card-title">Links</span></div>
      <div class="card-body">
        <div class="link-row">{''.join(links) or '<span class="empty">Dashboard not published yet.</span>'}</div>
      </div>
    </div>""" if links else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>George — Session Summary — {target_date}</title>
  {STYLE}
</head>
<body>
  <div class="header">
    <div>
      <div class="header-title">George &mdash; Session Summary &mdash; {target_date}</div>
    </div>
    <div class="header-sub">Generated {generated_at}</div>
  </div>
  <div class="main">
    {kpi_html}
    {dc_section}
    {commits_section}
    {podcast_html}
    {links_section}
  </div>
</body>
</html>"""


# ── Publish ───────────────────────────────────────────────────────────────────

def ensure_deps():
    """Install /tmp/jq and /tmp/file stub if missing."""
    import os, urllib.request
    jq = Path("/tmp/jq")
    if not jq.exists():
        urllib.request.urlretrieve(
            "https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-linux-amd64",
            "/tmp/jq"
        )
        jq.chmod(0o755)

    file_stub = Path("/tmp/file")
    if not file_stub.exists():
        file_stub.write_text(
            '#!/usr/bin/env node\n'
            'const e=require("path").extname(process.argv[process.argv.length-1]).toLowerCase();'
            'const m={".html":"text/html",".css":"text/css",".js":"application/javascript",'
            '".json":"application/json",".png":"image/png",".jpg":"image/jpeg",".mp3":"audio/mpeg"};'
            'console.log(m[e]||"application/octet-stream");\n'
        )
        file_stub.chmod(0o755)


def ensure_skill():
    skill_path = Path.home() / ".agents/skills/here-now"
    if not skill_path.exists():
        subprocess.run(
            "npx skills add heredotnow/skill@here-now -y -g",
            shell=True, capture_output=True
        )


def publish(html_path: Path):
    ensure_deps()
    ensure_skill()
    skill_publish = Path.home() / ".agents/skills/here-now/scripts/publish.sh"
    env_path = "PATH=/tmp:" + __import__("os").environ.get("PATH", "/usr/bin")
    result = subprocess.run(
        f'{env_path} bash {skill_publish} {html_path.parent}',
        shell=True, capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    m = re.search(r'publish_result\.site_url=(\S+)', output)
    return m.group(1) if m else None


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else str(date.today())

    # Validate date format
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print(f"Error: invalid date '{target_date}', expected YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    data = collect(target_date)
    html = generate_html(data)

    # Write to a dedicated summaries directory
    out_dir = BASE / "summaries"
    out_dir.mkdir(exist_ok=True)
    html_path = out_dir / f"session-summary-{target_date}.html"
    html_path.write_text(html)

    url = publish(html_path)
    if url:
        print(url)
    else:
        print(f"Published locally: {html_path}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
