#!/usr/bin/env python3
"""
Generate and publish the PEAD paper tracker HTML page to here.now.
Run daily at 4:40 PM CT after pead_scanner.py --exit completes.
"""

import sys, json, math, subprocess
from datetime import date, timedelta
from pathlib import Path

TRADES_FILE = Path(__file__).parent / "pead_trades.json"
SITE_DIR    = Path(__file__).parent / "site"
PUBLISHER   = Path(__file__).parent.parent / "herenow.py"
STATE_FILE  = Path.home() / ".herenow" / "state.json"
SLUG_KEY    = "pead-tracker"   # friendly name for state lookup

def trading_days_between(start, end):
    count, cur = 0, start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5: count += 1
        cur += timedelta(days=1)
    return count

def win_rate(trades, bucket=None):
    t = [x for x in trades if bucket is None or x.get("threshold") == bucket]
    if not t: return None
    return sum(1 for x in t if x.get("win")) / len(t) * 100

def avg_return(trades, bucket=None):
    t = [x for x in trades if bucket is None or x.get("threshold") == bucket]
    if not t: return None
    return sum(x.get("return_pct", 0) for x in t) / len(t) * 100

def compute_sharpe(trades, bucket=None):
    r = [x.get("return_pct", 0) for x in trades
         if bucket is None or x.get("threshold") == bucket]
    if len(r) < 3: return None
    mean = sum(r) / len(r)
    std = math.sqrt(sum((x - mean) ** 2 for x in r) / len(r))
    if std == 0: return None
    return round(mean / std * math.sqrt(252 / 20), 2)

def badge(val, positive_good=True):
    if val is None: return "<span class='neutral'>—</span>"
    ok = val > 0 if positive_good else val < 0
    cls = "win" if ok else "loss"
    return f"<span class='{cls}'>{val:+.1f}%</span>"

def build_html(data: dict) -> str:
    today = date.today()
    closed = data.get("closed_positions", [])
    opens  = data.get("open_positions", [])
    stats  = data.get("stats", {})

    total_pnl       = sum(p.get("pnl_usd", 0) for p in closed)
    total_trades    = sum(stats.get(b, {}).get("n_trades", 0) for b in ["3pct", "5pct"])
    total_wins      = sum(stats.get(b, {}).get("wins", 0)     for b in ["3pct", "5pct"])
    wr_all          = f"{total_wins/total_trades*100:.0f}%" if total_trades else "—"
    portfolio_value = 5000 + total_pnl
    sharpe_all      = compute_sharpe(closed)
    sharpe_str      = f"{sharpe_all:.2f}" if sharpe_all is not None else "—"
    pnl_cls         = "win" if total_pnl >= 0 else "loss"

    # Open positions rows
    open_rows = ""
    for p in sorted(opens, key=lambda x: x["entry_date"]):
        entry    = date.fromisoformat(p["entry_date"])
        held     = trading_days_between(entry, today)
        left     = 20 - held
        pct_done = min(held / 20 * 100, 100)
        open_rows += f"""
        <tr>
          <td><b>{p['symbol']}</b></td>
          <td><span class="badge {'badge-5' if p['threshold']=='5pct' else 'badge-3'}">{p['threshold']}</span></td>
          <td>${p['entry_price']:.2f}</td>
          <td>{p['gap_pct']*100:.1f}%</td>
          <td>{p['entry_date']}</td>
          <td>
            <div class="progress-bar"><div class="progress-fill" style="width:{pct_done:.0f}%"></div></div>
            day {held}/20 &nbsp;({left}d left)
          </td>
          <td>{p['target_exit_date']}</td>
        </tr>"""

    if not opens:
        open_rows = "<tr><td colspan='7' class='empty'>No open positions</td></tr>"

    # Closed trades rows (most recent first)
    closed_rows = ""
    for p in sorted(closed, key=lambda x: x.get("exit_date",""), reverse=True)[:20]:
        icon = "✅" if p.get("win") else "❌"
        ret  = p.get("return_pct", 0) * 100
        ret_cls = "win" if ret >= 0 else "loss"
        closed_rows += f"""
        <tr>
          <td>{icon} <b>{p['symbol']}</b></td>
          <td><span class="badge {'badge-5' if p['threshold']=='5pct' else 'badge-3'}">{p['threshold']}</span></td>
          <td>${p['entry_price']:.2f}</td>
          <td>${p.get('exit_price',0):.2f}</td>
          <td class="{ret_cls}">{ret:+.1f}%</td>
          <td class="{ret_cls}">${p.get('pnl_usd',0):+.2f}</td>
          <td>{p.get('entry_date','')}</td>
          <td>{p.get('exit_date','')}</td>
        </tr>"""

    if not closed:
        closed_rows = "<tr><td colspan='8' class='empty'>No closed trades yet</td></tr>"

    # Per-threshold stats cards
    thresh_cards = ""
    for bucket, label in [("5pct","5% Gap"), ("3pct","3% Gap")]:
        s  = stats.get(bucket, {})
        n  = s.get("n_trades", 0)
        sh = compute_sharpe(closed, bucket)
        wr = win_rate(closed, bucket)
        ar = avg_return(closed, bucket)
        thresh_cards += f"""
        <div class="card">
          <div class="card-label">{label} Threshold</div>
          <div class="card-value">{n} trades</div>
          <div class="card-sub">
            Win rate: <b>{f"{wr:.0f}%" if wr is not None else "—"}</b> &nbsp;|&nbsp;
            Avg ret: <b class="{'win' if ar and ar>0 else 'loss'}">{f"{ar:+.1f}%" if ar is not None else "—"}</b><br>
            Sharpe: <b>{sh if sh is not None else "—"}</b> &nbsp;|&nbsp;
            P&amp;L: <b class="{'win' if s.get('total_pnl',0)>=0 else 'loss'}">${s.get('total_pnl',0):+.2f}</b>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PEAD Paper Tracker</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #0f1117; color: #e2e8f0; min-height: 100vh; padding: 24px; }}
    h1   {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; }}
    .sub {{ color: #94a3b8; font-size: 0.875rem; margin-bottom: 24px; }}
    .cards {{ display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 28px; }}
    .card {{ background: #1e2433; border-radius: 12px; padding: 20px; min-width: 180px; flex: 1; }}
    .card-label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em;
                   color: #64748b; margin-bottom: 6px; }}
    .card-value {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 4px; }}
    .card-sub   {{ font-size: 0.8rem; color: #94a3b8; line-height: 1.6; }}
    .win  {{ color: #22c55e; }} .loss {{ color: #ef4444; }} .neutral {{ color: #94a3b8; }}
    section {{ background: #1e2433; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
    h2   {{ font-size: 1rem; font-weight: 600; margin-bottom: 14px; color: #cbd5e1; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th   {{ text-align: left; padding: 8px 10px; color: #64748b; font-weight: 500;
            border-bottom: 1px solid #2d3748; }}
    td   {{ padding: 10px; border-bottom: 1px solid #1a2030; }}
    tr:last-child td {{ border-bottom: none; }}
    .empty {{ color: #64748b; text-align: center; padding: 20px; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }}
    .badge-5 {{ background: #1d4ed8; color: #bfdbfe; }}
    .badge-3 {{ background: #6d28d9; color: #ddd6fe; }}
    .progress-bar {{ background: #2d3748; border-radius: 4px; height: 6px; width: 100px;
                     display: inline-block; vertical-align: middle; margin-right: 6px; }}
    .progress-fill {{ background: #3b82f6; height: 100%; border-radius: 4px; }}
    .pnl-big {{ font-size: 2rem; font-weight: 800; }}
    footer {{ text-align: center; color: #475569; font-size: 0.75rem; margin-top: 24px; }}
  </style>
</head>
<body>
  <h1>📊 PEAD Paper Tracker</h1>
  <div class="sub">Updated {today.strftime('%B %d, %Y')} &nbsp;·&nbsp; $5,000 virtual portfolio &nbsp;·&nbsp; 20-day hold &nbsp;·&nbsp; 30-stock universe</div>

  <div class="cards">
    <div class="card">
      <div class="card-label">Portfolio Value</div>
      <div class="card-value pnl-big">${portfolio_value:,.2f}</div>
      <div class="card-sub">Started $5,000.00</div>
    </div>
    <div class="card">
      <div class="card-label">Realized P&amp;L</div>
      <div class="card-value {pnl_cls}">${total_pnl:+,.2f}</div>
      <div class="card-sub">{total_trades} closed trades</div>
    </div>
    <div class="card">
      <div class="card-label">Win Rate</div>
      <div class="card-value">{wr_all}</div>
      <div class="card-sub">Backtest target: 67.8%</div>
    </div>
    <div class="card">
      <div class="card-label">Sharpe Ratio</div>
      <div class="card-value">{sharpe_str}</div>
      <div class="card-sub">Backtest target: 2.39</div>
    </div>
    <div class="card">
      <div class="card-label">Open Positions</div>
      <div class="card-value">{len(opens)}/10</div>
      <div class="card-sub">${len(opens)*500:,} deployed</div>
    </div>
    {thresh_cards}
  </div>

  <section>
    <h2>Open Positions</h2>
    <table>
      <thead><tr><th>Symbol</th><th>Threshold</th><th>Entry</th><th>Gap</th><th>Entry Date</th><th>Progress</th><th>Exit Date</th></tr></thead>
      <tbody>{open_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>Closed Trades (last 20)</h2>
    <table>
      <thead><tr><th>Symbol</th><th>Threshold</th><th>Entry</th><th>Exit</th><th>Return</th><th>P&amp;L</th><th>Opened</th><th>Closed</th></tr></thead>
      <tbody>{closed_rows}</tbody>
    </table>
  </section>

  <footer>PEAD Paper Tracker · George · Backtest Sharpe 2.394 (gap≥5%, 20d hold) · Not financial advice</footer>
</body>
</html>"""

def get_existing_slug() -> str | None:
    """Load previously published slug from state file."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
        publishes = state.get("publishes", {})
        # Look for our named key first, then any pead slug
        if SLUG_KEY in publishes:
            return SLUG_KEY
        for slug in publishes:
            if "pead" in slug.lower():
                return slug
    return None

def main():
    if not TRADES_FILE.exists():
        print("No trades file — nothing to publish.", file=sys.stderr)
        sys.exit(1)

    with open(TRADES_FILE) as f:
        data = json.load(f)

    SITE_DIR.mkdir(exist_ok=True)
    html = build_html(data)
    index = SITE_DIR / "index.html"
    index.write_text(html, encoding="utf-8")

    # Determine slug for update vs new publish
    slug = get_existing_slug()

    cmd = [sys.executable, str(PUBLISHER), str(SITE_DIR), "--title", "PEAD Paper Tracker"]
    if slug:
        cmd += ["--slug", slug]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    url = result.stdout.strip()
    print(url)

if __name__ == "__main__":
    main()
