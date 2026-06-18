#!/usr/bin/env python3
"""
generate_eod_dashboard.py — End-of-day paper trading HTML dashboard.

Per-strategy $5k virtual accounts tracked in strategy_accounts.json.
Each tile shows: starting equity → current equity, total return,
backtest Sharpe vs live Sharpe, closed trades, open positions.
"""

import json
import math
import os
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

warnings.filterwarnings("ignore")

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _ra
_orig_send = _ra.HTTPAdapter.send
def _no_verify_send(self, request, **kwargs):
    kwargs['verify'] = False
    return _orig_send(self, request, **kwargs)
_ra.HTTPAdapter.send = _no_verify_send

WORKSPACE   = Path(__file__).resolve().parent
PAPER_DIR   = WORKSPACE / "backtesting" / "paper_trading"
REPORTS_DIR = WORKSPACE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(PAPER_DIR))
import strategy_equity as se

TODAY    = date.today().isoformat()
TODAY_DT = date.today()
NOW      = datetime.now().strftime("%Y-%m-%d %H:%M")

# Display config per strategy (color, detail notes)
DISPLAY = {
    "H026":  {"color": "#3b82f6", "type": "ETF Momentum · Monthly"},
    "H041a": {"color": "#06b6d4", "type": "Global Equity · Monthly"},
    "H045":  {"color": "#8b5cf6", "type": "Bond ETF · Monthly"},
    "IBS":   {"color": "#a78bfa", "type": "IBS Mean-Reversion · Daily"},
    "H174":  {"color": "#f59e0b", "type": "PEAD Earnings NLP · Daily"},
    "H234":  {"color": "#ec4899", "type": "Inside-Bar Coiled Spring · Daily"},
}


# ── Alpaca account summary ───────────────────────────────────────────────────

def get_alpaca_state() -> dict:
    out = {"equity": None, "day_pnl": None, "day_pnl_pct": None,
           "buying_power": None, "n_positions": 0, "error": None, "position_map": {}}
    try:
        from alpaca.trading.client import TradingClient
        api_key = os.environ.get("ALPACA_API_KEY", "")
        secret  = os.environ.get("ALPACA_SECRET", "")
        if not api_key or not secret:
            out["error"] = "ALPACA credentials not set"
            return out
        client = TradingClient(api_key, secret, paper=True)
        acct   = client.get_account()
        eq     = float(acct.equity)
        last   = float(acct.last_equity)
        out.update({
            "equity":      eq,
            "day_pnl":     eq - last,
            "day_pnl_pct": (eq - last) / last * 100 if last else 0,
            "buying_power": float(acct.buying_power),
        })
        pm = {}
        for p in client.get_all_positions():
            pm[p.symbol] = {
                "qty":             float(p.qty),
                "avg_cost":        float(p.avg_entry_price),
                "current_price":   float(p.current_price),
                "market_value":    float(p.market_value),
                "unrealized_pl":   float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc) * 100,
            }
        out["position_map"] = pm
        out["n_positions"]  = len(pm)
    except Exception as e:
        out["error"] = str(e)
    return out


def get_recent_orders(n: int = 20) -> list:
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        client = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET"], paper=True)
        orders = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.ALL, limit=n))
        return [
            {
                "symbol":           o.symbol,
                "side":             o.side.value,
                "qty":              float(o.qty or 0),
                "notional":         float(o.notional) if o.notional else float((o.qty or 0) * (o.filled_avg_price or 0)),
                "status":           o.status.value,
                "filled_at":        str(o.filled_at)[:16] if o.filled_at else "",
                "filled_avg_price": float(o.filled_avg_price or 0),
            }
            for o in orders
        ]
    except Exception:
        return []


# ── Live Sharpe ──────────────────────────────────────────────────────────────

def live_sharpe(strat_id: str) -> float | None:
    return se.live_sharpe(strat_id)


# ── Sparkline SVG ────────────────────────────────────────────────────────────

def make_sparkline(history: list, color: str, w: int = 120, h: int = 36) -> str:
    """Generate a small inline SVG equity curve."""
    if len(history) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    vals = [entry["equity"] for entry in history]
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1
    pts = []
    for i, v in enumerate(vals):
        x = round(i / (len(vals) - 1) * w, 1)
        y = round(h - (v - mn) / rng * (h - 4) - 2, 1)
        pts.append(f"{x},{y}")
    path = "M " + " L ".join(pts)
    trend_color = color if vals[-1] >= vals[0] else "#f87171"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<path d="{path}" fill="none" stroke="{trend_color}" stroke-width="1.5" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>')


# ── HTML helpers ─────────────────────────────────────────────────────────────

def pct_color(v: float) -> str:
    return "#4ade80" if v > 0 else "#f87171" if v < 0 else "#94a3b8"

def fmt_dollar(v: float, sign: bool = False) -> str:
    s = "+" if (sign and v > 0) else ""
    return f"{s}${v:,.2f}"

def fmt_pct(v: float) -> str:
    s = "+" if v > 0 else ""
    return f"{s}{v:.2f}%"

def days_active(start_date_str: str) -> int:
    try:
        return (TODAY_DT - date.fromisoformat(start_date_str)).days
    except Exception:
        return 0

def tail_log(path: Path, n: int = 25) -> list:
    if not path.exists():
        return []
    return path.read_text().splitlines()[-n:]

def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default if default is not None else []


# ── Strategy tile ─────────────────────────────────────────────────────────────

def build_strategy_tile(strat_id: str, data: dict, pos_map: dict) -> str:
    disp   = DISPLAY.get(strat_id, {"color": "#64748b", "type": ""})
    color  = disp["color"]
    stype  = disp["type"]
    name   = data["name"]
    desc   = data["description"]
    status = data["status"]
    start  = data["start_equity"]
    curr   = se.current_equity(strat_id)
    ret    = (curr - start) / start * 100
    cash   = data["cash"]
    closed = data["closed_trades"]
    hist   = data["equity_history"]
    open_p = data["open_positions"]
    n_closed = len(closed)

    # Win rate from closed trades
    if n_closed:
        wins = sum(1 for t in closed if t["return"] > 0)
        wr_str = f"{wins/n_closed*100:.0f}%"
        avg_ret = sum(t["return"] for t in closed) / n_closed * 100
    else:
        wr_str = "—"
        avg_ret = 0.0

    # Sharpe comparison
    bt_sharpe = data.get("backtest_sharpe")
    lv_sharpe = live_sharpe(strat_id)
    sharpe_html = ""
    if bt_sharpe:
        lv_str = f"{lv_sharpe:.2f}" if lv_sharpe is not None else "—"
        sharpe_html = (
            f'<div class="sharpe-pair">'
            f'<span class="sp-label">Backtest</span>'
            f'<span class="sp-val" style="color:{color}">{bt_sharpe:.2f}</span>'
            f'<span class="sp-divider">vs</span>'
            f'<span class="sp-label">Live</span>'
            f'<span class="sp-val" style="color:{pct_color(lv_sharpe or 0)}">{lv_str}</span>'
            f'</div>'
        )
    else:
        sharpe_html = f'<div class="sharpe-pair"><span class="sp-label" style="color:#64748b">{data.get("backtest_oos_period","")}</span></div>'

    # Open positions display
    if open_p:
        tickers = list(open_p.keys())
        pos_html = ", ".join(
            f'<span style="color:{color};font-weight:600">{t}</span>' for t in tickers
        )
    else:
        pos_html = '<span style="color:#475569">CASH</span>'

    # Sparkline
    spark = make_sparkline(hist, color) if len(hist) >= 2 else ""

    # Status badge
    if status == "stub":
        status_badge = '<span class="status-badge stub">Stub</span>'
    elif status == "active":
        status_badge = '<span class="status-badge active">Active</span>'
    else:
        status_badge = f'<span class="status-badge">{status}</span>'

    ret_color = pct_color(ret)
    return f"""
<div class="tile" style="border-top:3px solid {color}">
  <div class="tile-header">
    <div>
      <div class="tile-name" style="color:{color}">{name}</div>
      <div class="tile-type">{stype}</div>
    </div>
    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
      {status_badge}
      {spark}
    </div>
  </div>

  <div class="equity-bar">
    <div class="eq-start">
      <div class="eq-label">Start</div>
      <div class="eq-val">{fmt_dollar(start)}</div>
    </div>
    <div class="eq-arrow">→</div>
    <div class="eq-current">
      <div class="eq-label">Now</div>
      <div class="eq-val" style="font-size:1.3rem">{fmt_dollar(curr)}</div>
    </div>
    <div class="eq-return" style="color:{ret_color}">
      <div class="eq-label">Return</div>
      <div class="eq-val" style="color:{ret_color}">{fmt_pct(ret)}</div>
    </div>
  </div>

  {sharpe_html}

  <div class="tile-meta">
    <div class="meta-item">
      <span class="meta-label">Closed Trades</span>
      <span class="meta-val">{n_closed}</span>
    </div>
    <div class="meta-item">
      <span class="meta-label">Win Rate</span>
      <span class="meta-val">{wr_str}</span>
    </div>
    <div class="meta-item">
      <span class="meta-label">Cash</span>
      <span class="meta-val">{fmt_dollar(cash)}</span>
    </div>
  </div>

  <div class="tile-positions">
    <span class="meta-label">Holding: </span>{pos_html}
  </div>
</div>"""


# ── PEAD detail section ──────────────────────────────────────────────────────

def pead_detail_html(watchlist: dict) -> str:
    se_data     = se.summary("H174")
    closed      = se.get_closed_trades("H174")
    open_pos    = se.get_open_positions("H174")

    closed_pnls = [t["return"] * 100 for t in closed]
    wins        = [p for p in closed_pnls if p > 0]
    losses      = [p for p in closed_pnls if p <= 0]
    wr          = len(wins) / len(closed_pnls) * 100 if closed_pnls else 0
    aw          = sum(wins)   / len(wins)   if wins   else 0
    al          = sum(losses) / len(losses) if losses else 0

    # Open positions table
    if not open_pos:
        open_rows = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">No open PEAD positions</td></tr>'
    else:
        rows = []
        for sym, pos in open_pos.items():
            try:
                held = (TODAY_DT - date.fromisoformat(pos["entry_date"])).days
            except Exception:
                held = "?"
            rows.append(
                f'<tr><td><strong>{sym}</strong></td>'
                f'<td>{pos["entry_date"]}</td>'
                f'<td style="text-align:right">{held}d</td>'
                f'<td style="text-align:right">${pos["entry_price"]:.2f}</td>'
                f'<td style="text-align:right">${pos["cost_basis"]:,.0f}</td></tr>'
            )
        open_rows = "\n".join(rows)

    # Closed trades (recent 8)
    if not closed:
        closed_rows = '<tr><td colspan="4" style="text-align:center;color:#64748b;padding:14px">No closed trades yet</td></tr>'
    else:
        rows = []
        for t in reversed(closed[-8:]):
            ret_pct = t["return"] * 100
            pnl_str = f'<span style="color:{pct_color(ret_pct)};font-weight:600">{fmt_pct(ret_pct)}</span>'
            rows.append(
                f'<tr><td><strong>{t["symbol"]}</strong></td>'
                f'<td>{t["entry_date"]} → {t["exit_date"]}</td>'
                f'<td style="text-align:right">${t["entry_price"]:.2f} → ${t["exit_price"]:.2f}</td>'
                f'<td style="text-align:right">{pnl_str}</td></tr>'
            )
        closed_rows = "\n".join(rows)

    # Watchlist
    wl_cands  = watchlist.get("candidates", [])
    wl_scores = watchlist.get("scores", {})
    wl_date   = watchlist.get("date", "—")
    if not wl_cands:
        wl_html = f'<p style="color:#64748b;padding:10px 0">No candidates tonight ({watchlist.get("reason","")})</p>'
    else:
        wl_rows = "".join(
            f'<tr><td><strong>{t}</strong></td>'
            f'<td style="text-align:right">{wl_scores.get(t,{}).get("score", wl_scores.get(t,"?"))}</td></tr>'
            for t in wl_cands
        )
        wl_html = f'<table><thead><tr><th>Ticker</th><th style="text-align:right">NLP Score</th></tr></thead><tbody>{wl_rows}</tbody></table>'

    return f"""
<div class="stat-row" style="margin-bottom:14px">
  <div class="stat"><div class="stat-label">Trades</div><div class="stat-val">{len(closed)}</div></div>
  <div class="stat"><div class="stat-label">Win Rate</div><div class="stat-val" style="color:{pct_color(wr-50)}">{wr:.0f}%</div></div>
  <div class="stat"><div class="stat-label">Avg Win</div><div class="stat-val" style="color:#4ade80">{aw:+.1f}%</div></div>
  <div class="stat"><div class="stat-label">Avg Loss</div><div class="stat-val" style="color:#f87171">{al:.1f}%</div></div>
</div>
<div class="two-col">
  <div>
    <div class="subsec-label">Open Positions</div>
    <table>
      <thead><tr><th>Ticker</th><th>Entry Date</th><th>Held</th><th style="text-align:right">Entry Price</th><th style="text-align:right">Cost</th></tr></thead>
      <tbody>{open_rows}</tbody>
    </table>
    <div class="subsec-label" style="margin-top:14px">Recent Closed</div>
    <table>
      <thead><tr><th>Ticker</th><th>Dates</th><th style="text-align:right">Prices</th><th style="text-align:right">Return</th></tr></thead>
      <tbody>{closed_rows}</tbody>
    </table>
  </div>
  <div>
    <div class="subsec-label">Tonight's Watchlist ({wl_date})</div>
    {wl_html}
  </div>
</div>"""


# ── Main HTML builder ─────────────────────────────────────────────────────────

def build_html(acct: dict, orders: list, watchlist: dict) -> str:
    accounts = json.loads((PAPER_DIR / "strategy_accounts.json").read_text())
    strategies = accounts["strategies"]
    strat_order = ["H026", "H041a", "H045", "IBS", "H174", "H234"]

    eq        = acct.get("equity")
    day_pnl   = acct.get("day_pnl")
    day_pct   = acct.get("day_pnl_pct", 0)
    bp        = acct.get("buying_power")
    n_pos     = acct.get("n_positions", 0)
    err       = acct.get("error")
    pos_map   = acct.get("position_map", {})

    eq_str      = fmt_dollar(eq)         if eq       is not None else "—"
    bp_str      = fmt_dollar(bp)         if bp       is not None else "—"
    dpnl_str    = fmt_dollar(day_pnl, sign=True) if day_pnl is not None else "—"
    dpct_str    = fmt_pct(day_pct)       if day_pnl  is not None else "—"
    dpnl_color  = pct_color(day_pnl or 0)
    err_banner  = f'<div class="error-banner">⚠ Alpaca: {err}</div>' if err else ""

    # Total virtual portfolio
    total_virtual = sum(se.current_equity(sid) for sid in strat_order if sid in strategies)
    total_start   = sum(strategies[sid]["start_equity"] for sid in strat_order if sid in strategies)
    total_ret     = (total_virtual - total_start) / total_start * 100

    # Strategy tiles
    tiles_html = "\n".join(
        build_strategy_tile(sid, strategies[sid], pos_map)
        for sid in strat_order if sid in strategies
    )

    # Activity logs
    open_log      = tail_log(PAPER_DIR / "pead_open.log")
    exits_log     = tail_log(PAPER_DIR / "pead_exits.log")
    overnight_log = tail_log(PAPER_DIR / "pead_overnight.log")

    def log_block(lines, label):
        if not lines:
            return f'<div class="log-section"><div class="log-label">{label}</div><div class="log-empty">no entries</div></div>'
        ents = []
        for ln in lines:
            col = "#4ade80" if any(k in ln for k in ["ORDER SUBMITTED", "Logged", "complete"]) \
                  else "#f87171" if any(k in ln for k in ["ERROR", "FAIL", "failed"]) \
                  else "#94a3b8"
            ents.append(f'<div class="log-line" style="color:{col}">{ln}</div>')
        return f'<div class="log-section"><div class="log-label">{label}</div>{"".join(ents)}</div>'

    # Recent orders
    filled = [o for o in orders if o.get("status") == "filled"][:10]
    orders_rows = "\n".join(
        f'<tr><td><strong>{o["symbol"]}</strong></td>'
        f'<td style="color:{"#4ade80" if o["side"]=="buy" else "#f87171"};font-weight:600">{o["side"].upper()}</td>'
        f'<td style="text-align:right">${o["filled_avg_price"]:.2f}</td>'
        f'<td style="text-align:right">${o["notional"]:,.0f}</td>'
        f'<td>{o["filled_at"]}</td></tr>'
        for o in filled
    ) if filled else '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">No recent fills</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paper Trading — {TODAY}</title>
<style>
  :root{{--bg:#0f172a;--s1:#1e293b;--s2:#263248;--bd:#334155;--tx:#e2e8f0;--mu:#94a3b8;--gr:#4ade80;--rd:#f87171}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}}
  a{{color:inherit;text-decoration:none}}
  .container{{max-width:1180px;margin:0 auto;padding:24px 16px}}
  header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:24px;border-bottom:1px solid var(--bd);padding-bottom:16px}}
  header h1{{font-size:1.4rem;font-weight:700}}
  .gen{{color:var(--mu);font-size:0.78rem;text-align:right}}
  .error-banner{{background:#7f1d1d40;border:1px solid var(--rd);border-radius:8px;padding:10px 14px;margin-bottom:18px;color:var(--rd);font-size:0.85rem}}
  /* Summary bar */
  .summary-bar{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:28px}}
  .sum-card{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:14px 16px}}
  .sum-label{{color:var(--mu);font-size:0.71rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
  .sum-val{{font-size:1.3rem;font-weight:700}}
  .sum-sub{{color:var(--mu);font-size:0.76rem;margin-top:2px}}
  /* Section titles */
  .sec-title{{font-size:0.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--mu);margin:28px 0 12px;display:flex;align-items:center;gap:8px}}
  .sec-title::after{{content:"";flex:1;height:1px;background:var(--bd)}}
  .sec-header{{margin:28px 0 12px;font-size:1rem;padding-left:12px}}
  .subsec-label{{color:var(--mu);font-size:0.71rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin:14px 0 6px}}
  /* Strategy tiles */
  .tile-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-bottom:32px}}
  .tile{{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:12px}}
  .tile-header{{display:flex;justify-content:space-between;align-items:flex-start}}
  .tile-name{{font-weight:700;font-size:0.95rem}}
  .tile-type{{color:var(--mu);font-size:0.73rem;margin-top:2px}}
  .status-badge{{font-size:0.68rem;font-weight:700;padding:2px 8px;border-radius:20px;text-transform:uppercase;letter-spacing:.04em}}
  .status-badge.active{{background:#14532d40;color:#4ade80;border:1px solid #4ade8040}}
  .status-badge.stub{{background:#1e293b;color:#64748b;border:1px solid #334155}}
  /* Equity bar */
  .equity-bar{{display:flex;align-items:center;gap:10px;background:var(--s2);border-radius:8px;padding:10px 12px}}
  .eq-start,.eq-current,.eq-return{{display:flex;flex-direction:column}}
  .eq-label{{color:var(--mu);font-size:0.67rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px}}
  .eq-val{{font-size:1.0rem;font-weight:700}}
  .eq-arrow{{color:var(--mu);font-size:1.1rem;flex-shrink:0}}
  .eq-current{{flex:1}}
  /* Sharpe pair */
  .sharpe-pair{{display:flex;align-items:center;gap:8px;font-size:0.8rem}}
  .sp-label{{color:var(--mu);font-size:0.7rem;text-transform:uppercase;letter-spacing:.04em}}
  .sp-val{{font-weight:700;font-size:0.95rem}}
  .sp-divider{{color:var(--mu);font-size:0.75rem;padding:0 2px}}
  /* Meta row */
  .tile-meta{{display:flex;gap:10px}}
  .meta-item{{background:var(--s2);border:1px solid var(--bd);border-radius:6px;padding:6px 10px;flex:1}}
  .meta-label{{color:var(--mu);font-size:0.65rem;text-transform:uppercase;letter-spacing:.04em;display:block}}
  .meta-val{{font-weight:700;font-size:0.85rem;margin-top:1px;display:block}}
  .tile-positions{{font-size:0.8rem;color:var(--mu)}}
  /* Tables */
  table{{width:100%;border-collapse:collapse;background:var(--s1);border-radius:10px;overflow:hidden;border:1px solid var(--bd)}}
  th{{background:var(--s2);color:var(--mu);font-weight:600;font-size:0.71rem;text-transform:uppercase;letter-spacing:.05em;padding:8px 12px;text-align:left}}
  td{{padding:8px 12px;border-top:1px solid var(--bd);font-size:0.84rem}}
  tr:hover td{{background:var(--s2)}}
  /* Stat row */
  .stat-row{{display:flex;gap:10px;flex-wrap:wrap}}
  .stat{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:9px 14px;min-width:90px}}
  .stat-label{{color:var(--mu);font-size:0.68rem;text-transform:uppercase;letter-spacing:.04em}}
  .stat-val{{font-size:1.05rem;font-weight:700;margin-top:2px}}
  /* Logs */
  .log-section{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:12px;margin-bottom:10px}}
  .log-label{{font-size:0.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--mu);margin-bottom:6px}}
  .log-line{{font-family:"SF Mono","Fira Code",monospace;font-size:0.7rem;padding:1px 0;white-space:pre-wrap;word-break:break-all}}
  .log-empty{{color:var(--mu);font-size:0.8rem;font-style:italic}}
  /* Layout */
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
  @media(max-width:680px){{.two-col{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container" id="top">

<header>
  <div>
    <h1>Paper Trading Dashboard</h1>
    <div style="color:var(--mu);font-size:0.82rem;margin-top:2px">George · {TODAY}</div>
  </div>
  <div class="gen">Generated {NOW}</div>
</header>

{err_banner}

<!-- Account summary -->
<div class="summary-bar">
  <div class="sum-card">
    <div class="sum-label">Alpaca Paper Equity</div>
    <div class="sum-val">{eq_str}</div>
    <div class="sum-sub">Total account</div>
  </div>
  <div class="sum-card">
    <div class="sum-label">Day P&amp;L</div>
    <div class="sum-val" style="color:{dpnl_color}">{dpnl_str}</div>
    <div class="sum-sub" style="color:{dpnl_color}">{dpct_str}</div>
  </div>
  <div class="sum-card">
    <div class="sum-label">Buying Power</div>
    <div class="sum-val">{bp_str}</div>
    <div class="sum-sub">Available</div>
  </div>
  <div class="sum-card">
    <div class="sum-label">Virtual Portfolio</div>
    <div class="sum-val">{fmt_dollar(total_virtual)}</div>
    <div class="sum-sub" style="color:{pct_color(total_ret)}">{fmt_pct(total_ret)} vs ${total_start:,.0f} start</div>
  </div>
  <div class="sum-card">
    <div class="sum-label">Alpaca Positions</div>
    <div class="sum-val">{n_pos}</div>
    <div class="sum-sub">Active orders</div>
  </div>
</div>

<!-- Strategy tiles -->
<div class="sec-title">Strategies — $5,000 each</div>
<div class="tile-grid">
{tiles_html}
</div>

<!-- H174 PEAD detail -->
<div class="sec-title">H174 PEAD-NLP — Detail</div>
{pead_detail_html(watchlist)}

<!-- Recent fills -->
<div class="sec-title">Recent Filled Orders</div>
<table>
  <thead><tr><th>Symbol</th><th>Side</th><th style="text-align:right">Fill Price</th><th style="text-align:right">Notional</th><th>Filled At</th></tr></thead>
  <tbody>{orders_rows}</tbody>
</table>

<!-- Activity logs -->
<div class="sec-title">Activity Logs</div>
{log_block(overnight_log, "PEAD Overnight — 11 PM scoring")}
{log_block(open_log, "PEAD Open — 9:30 AM gap detection")}
{log_block(exits_log, "PEAD Exits — 3:45 PM MOC")}

</div>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{NOW}] Generating EOD dashboard…")
    acct      = get_alpaca_state()
    orders    = get_recent_orders(20)
    watchlist = load_json(PAPER_DIR / "pead_watchlist.json", {})

    html = build_html(acct, orders, watchlist)
    out  = REPORTS_DIR / f"eod_dashboard_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[{NOW}] Saved → {out}")
    print(f"DASHBOARD_PATH={out}")
    return str(out)


if __name__ == "__main__":
    main()
