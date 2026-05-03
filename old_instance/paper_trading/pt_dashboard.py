#!/usr/bin/env python3
"""
Unified paper trading dashboard — generates and publishes to here.now.
Reads all 5 strategy portfolio files and builds a single HTML page.
"""

import sys, json, math, subprocess
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR        = Path(__file__).parent
PEAD_FILE            = Path('/workspace/group/pead/pead_trades.json')
PEAD_R28_FILE        = SCRIPT_DIR / 'pead_r28_portfolio.json'
CRYPTO_FILE          = SCRIPT_DIR / 'crypto_portfolio.json'
CORN_FILE            = SCRIPT_DIR / 'corn_portfolio.json'
PAIRS_FILE           = SCRIPT_DIR / 'pairs_portfolio.json'
PAIRS_R29_FILE       = SCRIPT_DIR / 'pairs_r29_portfolio.json'
ML_FILE              = SCRIPT_DIR / 'ml_portfolio.json'
DIV_RAISE_FILE       = SCRIPT_DIR / 'div_raise_portfolio.json'
DIV_RAISE_5PCT_FILE  = SCRIPT_DIR / 'div_raise_5pct_portfolio.json'
DIV_CC_FILE          = SCRIPT_DIR / 'div_cc_portfolio.json'
DIV_CAPTURE_FILE     = SCRIPT_DIR / 'div_capture_portfolio.json'
SITE_DIR          = SCRIPT_DIR / 'site'
PUBLISHER         = Path('/workspace/group/herenow.py')
STATE_FILE        = Path.home() / '.herenow' / 'state.json'
DASHBOARD_SLUG    = 'paper-trading-dashboard'

STRATEGIES = [
    {'key': 'pead_r28',       'label': 'PEAD R28 Quality Filter',     'backtest_sharpe': 9.028, 'color': '#4f46e5'},
    {'key': 'div_raise',      'label': 'Dividend Raise ≥10%',         'backtest_sharpe': 4.403, 'color': '#ec4899'},
    {'key': 'div_raise_5pct', 'label': 'Dividend Raise ≥5%',          'backtest_sharpe': 3.400, 'color': '#db2777'},
    {'key': 'div_cc',         'label': 'Covered Calls (Ex-Div)',       'backtest_sharpe': 2.643, 'color': '#f97316'},
    {'key': 'pead',           'label': 'PEAD Portfolio (baseline)',    'backtest_sharpe': 2.394, 'color': '#6366f1'},
    {'key': 'pairs_r29',      'label': 'Pairs R29 (Residualized)',     'backtest_sharpe': 1.3802,'color': '#0ea5e9'},
    {'key': 'crypto',         'label': 'Crypto Momentum',              'backtest_sharpe': 1.682, 'color': '#f59e0b'},
    {'key': 'div_capture',    'label': 'Dividend Capture',             'backtest_sharpe': 1.578, 'color': '#14b8a6'},
    {'key': 'corn',           'label': 'Corn Seasonal',                'backtest_sharpe': 1.175, 'color': '#10b981'},
    {'key': 'pairs',          'label': 'Pairs Portfolio (R23)',        'backtest_sharpe': 0.964, 'color': '#3b82f6'},
    {'key': 'ml',             'label': 'ML Ensemble',                  'backtest_sharpe': 0.527, 'color': '#8b5cf6'},
]

TOTAL_CAPITAL = 55000.0  # 11 strategies × $5k

def load_json(path: Path) -> dict:
    if path and path.exists():
        with open(path) as f: return json.load(f)
    return {}

def pct(v): return f"{v*100:+.1f}%" if v is not None else "—"

def compute_sharpe(trades: list, ret_key: str = 'return_pct') -> float | None:
    r = [t.get(ret_key, 0) for t in trades if ret_key in t]
    if len(r) < 3: return None
    mean = sum(r) / len(r)
    std  = math.sqrt(sum((x - mean)**2 for x in r) / len(r))
    if std == 0: return None
    return round(mean / std * math.sqrt(252 / 20), 2)

def trading_days_between(start: date, end: date) -> int:
    count, cur = 0, start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5: count += 1
        cur += timedelta(days=1)
    return count

def get_pead_summary(d: dict) -> dict:
    if not d: return {'pnl': 0, 'n_trades': 0, 'wins': 0, 'open': 0, 'sharpe': None}
    closed = d.get('closed_positions', [])
    opens  = d.get('open_positions', [])
    pnl    = sum(p.get('pnl_usd', 0) for p in closed)
    n      = len(closed)
    wins   = sum(1 for p in closed if p.get('win'))
    sh     = compute_sharpe(closed)
    return {'pnl': pnl, 'n_trades': n, 'wins': wins, 'open': len(opens), 'sharpe': sh,
            'portfolio_value': 5000 + pnl}

def get_crypto_summary(d: dict) -> dict:
    if not d: return {'pnl': 0, 'n_trades': 0, 'wins': 0, 'open': 0, 'sharpe': None}
    trades = d.get('trades', [])
    pnl    = sum(t.get('pnl_usd', 0) for t in trades)
    n      = len(trades)
    wins   = sum(1 for t in trades if t.get('win'))
    # Unrealized
    open_p = d.get('positions', {})
    prices = d.get('current_prices', {})
    unreal = 0.0
    for name, pos in open_p.items():
        cp = prices.get(name, {}).get('price')
        if cp: unreal += pos['shares'] * (cp - pos['entry_price'])
    return {'pnl': pnl, 'n_trades': n, 'wins': wins, 'open': len(open_p),
            'unrealized': unreal, 'sharpe': compute_sharpe(trades),
            'portfolio_value': 5000 + pnl + unreal}

def get_corn_summary(d: dict) -> dict:
    if not d: return {'pnl': 0, 'n_trades': 0, 'wins': 0, 'open': 0}
    trades = d.get('trades', [])
    pnl    = sum(t.get('pnl_usd', 0) for t in trades)
    n      = len(trades)
    wins   = sum(1 for t in trades if t.get('win'))
    open_p = d.get('positions', {})
    return {'pnl': pnl, 'n_trades': n, 'wins': wins, 'open': len(open_p),
            'sharpe': compute_sharpe(trades), 'portfolio_value': 5000 + pnl}

def get_pairs_summary(d: dict) -> dict:
    if not d: return {'pnl': 0, 'n_trades': 0, 'wins': 0, 'open': 0}
    trades = d.get('trades', [])
    pnl    = sum(t.get('pnl_usd', 0) for t in trades)
    n      = len(trades)
    wins   = sum(1 for t in trades if t.get('win'))
    open_p = d.get('open_positions', {})
    return {'pnl': pnl, 'n_trades': n, 'wins': wins, 'open': len(open_p),
            'sharpe': compute_sharpe(trades, 'pnl_usd'),  # pnl-based for pairs
            'portfolio_value': 5000 + pnl}

def get_ml_summary(d: dict) -> dict:
    if not d: return {'pnl': 0, 'n_trades': 0, 'wins': 0, 'open': 0}
    trades = d.get('trades', [])
    pnl    = sum(t.get('pnl_usd', 0) for t in trades)
    n      = len(trades)
    wins   = sum(1 for t in trades if t.get('win'))
    open_p = d.get('open_positions', {})
    return {'pnl': pnl, 'n_trades': n, 'wins': wins, 'open': len(open_p),
            'sharpe': compute_sharpe(trades), 'portfolio_value': 5000 + pnl}

def get_generic_summary(d: dict) -> dict:
    """Works for div_raise, div_capture, div_cc — all use same schema."""
    if not d: return {'pnl': 0, 'n_trades': 0, 'wins': 0, 'open': 0, 'sharpe': None}
    trades = d.get('trades', [])
    pnl    = sum(t.get('pnl_usd', 0) for t in trades)
    n      = len(trades)
    wins   = sum(1 for t in trades if t.get('win'))
    open_p = d.get('open_positions', {})
    return {'pnl': pnl, 'n_trades': n, 'wins': wins, 'open': len(open_p),
            'sharpe': compute_sharpe(trades), 'portfolio_value': 5000 + pnl}

def fmt_pnl(v):
    cls = 'win' if v >= 0 else 'loss'
    return f"<span class='{cls}'>${v:+,.2f}</span>"

def fmt_sharpe(v):
    if v is None: return "<span class='neutral'>—</span>"
    cls = 'win' if v > 0 else 'loss'
    return f"<span class='{cls}'>{v:.2f}</span>"

def build_strategy_card(strat: dict, summary: dict) -> str:
    pv   = summary.get('portfolio_value', 5000)
    pnl  = summary.get('pnl', 0)
    n    = summary.get('n_trades', 0)
    wins = summary.get('wins', 0)
    wr   = f"{wins/n*100:.0f}%" if n > 0 else "—"
    sh   = summary.get('sharpe')
    op   = summary.get('open', 0)
    pnl_cls = 'win' if pnl >= 0 else 'loss'
    color   = strat['color']
    ret_pct = (pv / 5000 - 1) * 100
    ret_cls = 'win' if ret_pct >= 0 else 'loss'

    return f"""
    <div class="strat-card">
      <div class="strat-header" style="border-left:4px solid {color}; padding-left:12px;">
        <div class="strat-name">{strat['label']}</div>
        <div class="strat-meta">Backtest Sharpe: {strat['backtest_sharpe']}</div>
      </div>
      <div class="strat-stats">
        <div class="stat-item">
          <div class="stat-label">Portfolio</div>
          <div class="stat-value">${pv:,.2f}</div>
          <div class="stat-sub {ret_cls}">{ret_pct:+.1f}%</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">P&amp;L</div>
          <div class="stat-value {pnl_cls}">${pnl:+,.2f}</div>
          <div class="stat-sub">{n} trades</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Win Rate</div>
          <div class="stat-value">{wr}</div>
          <div class="stat-sub">{wins}/{n} wins</div>
        </div>
        <div class="stat-item">
          <div class="stat-label">Live Sharpe</div>
          <div class="stat-value">{fmt_sharpe(sh)}</div>
          <div class="stat-sub">{op} open</div>
        </div>
      </div>
    </div>"""

def build_html(summaries: dict) -> str:
    today = date.today()
    total_pnl = sum(s.get('pnl', 0) for s in summaries.values())
    total_val = sum(s.get('portfolio_value', 5000) for s in summaries.values())
    total_ret = (total_val / TOTAL_CAPITAL - 1) * 100

    cards = ''.join(build_strategy_card(s, summaries.get(s['key'], {})) for s in STRATEGIES)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Paper Trading Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #0f1117; color: #e2e8f0; padding: 24px; min-height: 100vh; }}
    h1   {{ font-size: 1.6rem; font-weight: 800; margin-bottom: 4px; }}
    .sub {{ color: #94a3b8; font-size: 0.875rem; margin-bottom: 28px; }}
    .overview {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 28px; }}
    .ov-card {{ background: #1e2433; border-radius: 12px; padding: 20px; flex: 1; min-width: 160px; }}
    .ov-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: .06em; color: #64748b; margin-bottom: 6px; }}
    .ov-value {{ font-size: 1.8rem; font-weight: 800; }}
    .ov-sub   {{ font-size: 0.8rem; color: #94a3b8; margin-top: 4px; }}
    .section-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: .08em;
                      color: #475569; margin: 20px 0 10px; }}
    .strat-card {{ background: #1e2433; border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
    .strat-header {{ margin-bottom: 16px; }}
    .strat-name {{ font-size: 1.1rem; font-weight: 700; }}
    .strat-meta {{ font-size: 0.75rem; color: #64748b; margin-top: 2px; }}
    .strat-stats {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .stat-item {{ flex: 1; min-width: 90px; background: #141824; border-radius: 8px; padding: 12px; }}
    .stat-label {{ font-size: 0.65rem; text-transform: uppercase; color: #64748b; margin-bottom: 4px; letter-spacing: .05em; }}
    .stat-value {{ font-size: 1.1rem; font-weight: 700; }}
    .stat-sub   {{ font-size: 0.75rem; color: #94a3b8; margin-top: 2px; }}
    .win  {{ color: #22c55e; }} .loss {{ color: #ef4444; }} .neutral {{ color: #94a3b8; }}
    footer {{ text-align: center; color: #475569; font-size: 0.75rem; margin-top: 32px; }}
  </style>
</head>
<body>
  <h1>📈 Paper Trading Dashboard</h1>
  <div class="sub">Updated {today.strftime('%B %d, %Y')} &nbsp;·&nbsp; 11 strategies &nbsp;·&nbsp; $5,000 virtual each &nbsp;·&nbsp; $55,000 total</div>

  <div class="overview">
    <div class="ov-card">
      <div class="ov-label">Total Portfolio</div>
      <div class="ov-value">${total_val:,.0f}</div>
      <div class="ov-sub">Started ${TOTAL_CAPITAL:,.0f}</div>
    </div>
    <div class="ov-card">
      <div class="ov-label">Total P&amp;L</div>
      <div class="ov-value {'win' if total_pnl >= 0 else 'loss'}">${total_pnl:+,.2f}</div>
      <div class="ov-sub {'win' if total_ret >= 0 else 'loss'}">{total_ret:+.1f}% overall</div>
    </div>
  </div>

  {cards}

  <footer>Paper Trading Dashboard · George · All figures virtual, not real money · Not financial advice</footer>
</body>
</html>"""

def get_slug() -> str | None:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
        publishes = state.get('publishes', {})
        if DASHBOARD_SLUG in publishes: return DASHBOARD_SLUG
        for slug in publishes:
            if 'paper' in slug.lower() or 'trading' in slug.lower(): return slug
    return None

def main():
    pead_d            = load_json(PEAD_FILE)
    pead_r28_d        = load_json(PEAD_R28_FILE)
    crypto_d          = load_json(CRYPTO_FILE)
    corn_d            = load_json(CORN_FILE)
    pairs_d           = load_json(PAIRS_FILE)
    pairs_r29_d       = load_json(PAIRS_R29_FILE)
    ml_d              = load_json(ML_FILE)
    div_raise_d       = load_json(DIV_RAISE_FILE)
    div_raise_5pct_d  = load_json(DIV_RAISE_5PCT_FILE)
    div_cc_d          = load_json(DIV_CC_FILE)
    div_capture_d     = load_json(DIV_CAPTURE_FILE)

    summaries = {
        'pead':           get_pead_summary(pead_d),
        'pead_r28':       get_generic_summary(pead_r28_d),
        'crypto':         get_crypto_summary(crypto_d),
        'corn':           get_corn_summary(corn_d),
        'pairs':          get_pairs_summary(pairs_d),
        'pairs_r29':      get_pairs_summary(pairs_r29_d),
        'ml':             get_ml_summary(ml_d),
        'div_raise':      get_generic_summary(div_raise_d),
        'div_raise_5pct': get_generic_summary(div_raise_5pct_d),
        'div_cc':         get_generic_summary(div_cc_d),
        'div_capture':    get_generic_summary(div_capture_d),
    }

    SITE_DIR.mkdir(exist_ok=True)
    html = build_html(summaries)
    (SITE_DIR / 'index.html').write_text(html, encoding='utf-8')

    slug = get_slug()
    cmd  = [sys.executable, str(PUBLISHER), str(SITE_DIR), '--title', 'Paper Trading Dashboard']
    if slug: cmd += ['--slug', slug]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    url = result.stdout.strip()
    print(url)

if __name__ == '__main__':
    main()
