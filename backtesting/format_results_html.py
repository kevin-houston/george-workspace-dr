"""
Converts a backtest results .txt file to a self-contained HTML page.
Usage: python3 format_results_html.py <results_file.txt> [output.html]
If output not specified, writes to same path with .html extension.
"""

import sys
import re
from pathlib import Path
from datetime import datetime

STYLE = """
<style>
  :root { --bg:#0d1117; --surface:#161b22; --border:#30363d;
          --text:#e6edf3; --muted:#8b949e; --green:#3fb950;
          --red:#f85149; --yellow:#d29922; --blue:#58a6ff; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:'SF Mono',Consolas,monospace;
         font-size:13px; line-height:1.6; padding:24px; }
  h1 { font-size:18px; font-weight:600; margin-bottom:4px; }
  .subtitle { color:var(--muted); font-size:12px; margin-bottom:24px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:24px; }
  .card { background:var(--surface); border:1px solid var(--border); border-radius:8px;
          padding:14px 16px; }
  .card-label { color:var(--muted); font-size:11px; text-transform:uppercase;
                letter-spacing:.08em; margin-bottom:4px; }
  .card-value { font-size:22px; font-weight:700; }
  .card-value.good { color:var(--green); }
  .card-value.bad  { color:var(--red); }
  .card-value.warn { color:var(--yellow); }
  .card-value.neu  { color:var(--blue); }
  .section { background:var(--surface); border:1px solid var(--border);
             border-radius:8px; padding:16px; margin-bottom:16px; }
  .section-title { font-size:13px; font-weight:600; color:var(--muted);
                   text-transform:uppercase; letter-spacing:.08em; margin-bottom:12px; }
  table { width:100%; border-collapse:collapse; }
  th { color:var(--muted); font-size:11px; text-transform:uppercase;
       letter-spacing:.06em; padding:6px 10px; text-align:left;
       border-bottom:1px solid var(--border); }
  td { padding:8px 10px; border-bottom:1px solid var(--border); }
  tr:last-child td { border-bottom:none; }
  .verdict { display:inline-block; padding:4px 12px; border-radius:20px;
             font-size:12px; font-weight:700; letter-spacing:.05em; }
  .verdict.confirmed { background:rgba(63,185,80,.15); color:var(--green);
                       border:1px solid rgba(63,185,80,.4); }
  .verdict.not-confirmed { background:rgba(248,81,73,.15); color:var(--red);
                           border:1px solid rgba(248,81,73,.4); }
  .verdict.partial { background:rgba(210,153,34,.15); color:var(--yellow);
                     border:1px solid rgba(210,153,34,.4); }
  pre { background:var(--bg); border:1px solid var(--border); border-radius:6px;
        padding:12px; overflow-x:auto; white-space:pre-wrap; color:var(--muted);
        font-size:12px; margin-top:8px; }
</style>
"""

def parse_txt(text):
    """Extract key metrics from standard result file format."""
    data = {}

    # Title line (first non-empty line)
    lines = text.strip().splitlines()
    data['title'] = lines[0].strip() if lines else 'Backtest Results'

    # Run date
    m = re.search(r'Run:\s*(.+)', text)
    data['run_date'] = m.group(1).strip() if m else ''

    # IS metrics
    m = re.search(r'IS\s+months:\s*(\d+)\s*\|\s*Cumul=([\d.]+)×?\s*CAGR=([\d.]+)%\s*Sharpe=([\d.]+)\s*MaxDD=(-[\d.]+)%\s*NegYrs=(\d+)', text)
    if m:
        data['is'] = {
            'months': m.group(1), 'cumul': m.group(2), 'cagr': m.group(3),
            'sharpe': m.group(4), 'maxdd': m.group(5), 'neg_yrs': m.group(6)
        }

    # OOS metrics
    m = re.search(r'OOS\s+months:\s*(\d+)\s*\|\s*Cumul=([\d.]+)×?\s*CAGR=([\d.]+)%\s*Sharpe=([\d.]+)\s*MaxDD=(-[\d.]+)%\s*NegYrs=(\d+)', text)
    if m:
        data['oos'] = {
            'months': m.group(1), 'cumul': m.group(2), 'cagr': m.group(3),
            'sharpe': m.group(4), 'maxdd': m.group(5), 'neg_yrs': m.group(6)
        }

    # SPY benchmarks
    m = re.search(r'SPY IS:\s*Cumul=([\d.]+)×?\s*Sharpe=([\d.]+)', text)
    if m:
        data['spy_is'] = {'cumul': m.group(1), 'sharpe': m.group(2)}
    m = re.search(r'SPY OOS:\s*Cumul=([\d.]+)×?\s*Sharpe=([\d.]+)', text)
    if m:
        data['spy_oos'] = {'cumul': m.group(1), 'sharpe': m.group(2)}

    # Verdict
    m = re.search(r'VERDICT:\s*(.+)', text)
    data['verdict'] = m.group(1).strip() if m else ''

    return data


def color_sharpe(v):
    try:
        f = float(v)
        return 'good' if f >= 1.0 else ('warn' if f >= 0.5 else 'bad')
    except: return 'neu'

def color_maxdd(v):
    try:
        f = float(v)
        return 'good' if f > -15 else ('warn' if f > -25 else 'bad')
    except: return 'neu'

def verdict_class(v):
    v = v.upper()
    if 'CONFIRMED' in v and 'NOT' not in v: return 'confirmed'
    if 'NOT CONFIRMED' in v: return 'not-confirmed'
    if 'PARTIAL' in v: return 'partial'
    return ''


def generate_html(txt_path):
    text = Path(txt_path).read_text()
    d = parse_txt(text)
    title = d.get('title', 'Backtest Results')
    run_date = d.get('run_date', '')
    verdict = d.get('verdict', '')
    vc = verdict_class(verdict)

    oos = d.get('oos', {})
    is_ = d.get('is_', d.get('is', {}))
    spy_oos = d.get('spy_oos', {})

    cards_html = ''
    if oos:
        cards = [
            ('OOS Sharpe',  oos.get('sharpe','—'),  color_sharpe(oos.get('sharpe',''))),
            ('OOS CAGR',    oos.get('cagr','—')+'%', 'good' if float(oos.get('cagr',0) or 0) > 10 else 'warn'),
            ('OOS Cumul',   oos.get('cumul','—')+'×', 'good'),
            ('Max DD',      oos.get('maxdd','—')+'%', color_maxdd(oos.get('maxdd',''))),
            ('Neg Years',   oos.get('neg_yrs','—'),  'good' if oos.get('neg_yrs','0')=='0' else 'warn'),
            ('OOS Months',  oos.get('months','—'),   'neu'),
        ]
        cards_html = '<div class="grid">' + ''.join(
            f'<div class="card"><div class="card-label">{lbl}</div>'
            f'<div class="card-value {cls}">{val}</div></div>'
            for lbl, val, cls in cards
        ) + '</div>'

    # Comparison table
    rows = []
    if is_:
        rows.append(('IS', is_.get('sharpe','—'), is_.get('cagr','—')+'%',
                     is_.get('cumul','—')+'×', is_.get('maxdd','—')+'%', is_.get('neg_yrs','—')))
    if oos:
        rows.append(('OOS', oos.get('sharpe','—'), oos.get('cagr','—')+'%',
                     oos.get('cumul','—')+'×', oos.get('maxdd','—')+'%', oos.get('neg_yrs','—')))
    if spy_oos:
        rows.append(('SPY OOS', spy_oos.get('sharpe','—'), '—',
                     spy_oos.get('cumul','—')+'×', '—', '—'))

    table_rows = ''.join(
        f'<tr><td><strong>{r[0]}</strong></td><td>{r[1]}</td><td>{r[2]}</td>'
        f'<td>{r[3]}</td><td>{r[4]}</td><td>{r[5]}</td></tr>'
        for r in rows
    )
    table_html = f'''
    <div class="section">
      <div class="section-title">Performance Summary</div>
      <table>
        <thead><tr><th>Period</th><th>Sharpe</th><th>CAGR</th><th>Cumul</th><th>MaxDD</th><th>Neg Yrs</th></tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>''' if rows else ''

    verdict_html = f'<div class="verdict {vc}">{verdict}</div>' if verdict else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{title}</title>{STYLE}</head>
<body>
  <h1>{title}</h1>
  <div class="subtitle">Run: {run_date} &nbsp;·&nbsp; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  {verdict_html}
  <br>
  {cards_html}
  {table_html}
  <div class="section">
    <div class="section-title">Raw Output</div>
    <pre>{text}</pre>
  </div>
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 format_results_html.py <results.txt> [output.html]")
        sys.exit(1)
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_suffix('.html')
    html = generate_html(inp)
    out.write_text(html)
    print(f"Written: {out}")


if __name__ == '__main__':
    main()
