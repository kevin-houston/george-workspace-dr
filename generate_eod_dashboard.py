#!/usr/bin/env python3
"""
generate_eod_dashboard.py — End-of-day paper trading HTML dashboard.

Strategy tiles: starting equity, current equity, P&L, days active, Sharpe.
All active paper trading strategies shown with detail sections below.
"""

import json
import os
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

TODAY    = date.today().isoformat()
TODAY_DT = date.today()
NOW      = datetime.now().strftime("%Y-%m-%d %H:%M")

# ─── Strategy registry ────────────────────────────────────────────────────────

STRATEGIES = [
    {
        "id":           "h112",
        "name":         "H112 Composite Rotation",
        "short":        "ETF Rotation — Monthly",
        "desc":         "3-signal ETF rotation (H041a intl momentum + H026 sector + H045 credit). "
                        "Monthly rebalance. Weights: H041a 22% / H026 27% / H045 21%.",
        "sharpe_oos":   4.16,
        "sharpe_label": "OOS Sharpe (2003–2025)",
        "start_date":   "2026-04-28",
        "status":       "active",
        "symbols":      None,   # populated from h112_monthly_trades.json
        "color":        "#3b82f6",
        "detail_id":    "detail-h112",
    },
    {
        "id":           "h112ibs",
        "name":         "H112 Daily IBS",
        "short":        "IBS Mean-Reversion — Daily",
        "desc":         "XLK (20%) + SMH (8%) + IGV (2%) internal bar-strength mean-reversion. "
                        "Entry: IBS < 0.20 with gap filter. Exit: IBS > 0.75 or max 6 days.",
        "sharpe_oos":   2.38,
        "sharpe_label": "OOS Sharpe (H067)",
        "start_date":   "2026-04-28",
        "status":       "active",
        "symbols":      ["XLK", "SMH", "IGV"],
        "color":        "#8b5cf6",
        "detail_id":    "detail-h112ibs",
    },
    {
        "id":           "h016",
        "name":         "H016/H020 ETF Rotation",
        "short":        "5-Asset Momentum — Monthly",
        "desc":         "Top-2 of SPY / QQQ / TLT / GLD / IEF by 12-month momentum + carry. "
                        "Monthly rebalance. OOS Sharpe 1.11 (H020). Precursor to H112.",
        "sharpe_oos":   1.11,
        "sharpe_label": "OOS Sharpe (H020)",
        "start_date":   "2026-04-26",
        "status":       "active",
        "symbols":      None,   # populated from h016_positions.json
        "color":        "#06b6d4",
        "detail_id":    "detail-h016",
    },
    {
        "id":           "h009",
        "name":         "H009 Daily IBS",
        "short":        "SPY Mean-Reversion — Daily",
        "desc":         "SPY IBS < 0.20 buy signal, IBS > 0.80 or 5-day hold exit. "
                        "Oversold daily mean-reversion. Corr to H020 = 0.21.",
        "sharpe_oos":   0.96,
        "sharpe_label": "OOS Sharpe (H009)",
        "start_date":   "2026-04-28",
        "status":       "active",
        "symbols":      ["SPY"],
        "color":        "#10b981",
        "detail_id":    "detail-h009",
    },
    {
        "id":           "h174",
        "name":         "H174 PEAD-NLP",
        "short":        "Earnings Gap — Daily",
        "desc":         "NLP-scored earnings surprise gap-up plays. Score ≥ 0.18, "
                        "surprise ≥ 2%, gap ≥ 3%. 5% equity per position, 20-day hold.",
        "sharpe_oos":   1.28,
        "sharpe_label": "IS Sharpe (2018–2021)",
        "start_date":   "2026-05-01",
        "status":       "active",
        "symbols":      None,   # populated from pead_positions.json
        "color":        "#f59e0b",
        "detail_id":    "detail-h174",
    },
    {
        "id":           "h181",
        "name":         "H181 Industry Reversal",
        "short":        "Sector-Adjusted Reversal — Monthly",
        "desc":         "Long bottom-6 stocks by industry-adjusted 1-month return. "
                        "30 large-cap S&P 500 stocks, 8 GICS sectors. Equal-weight.",
        "sharpe_oos":   1.138,
        "sharpe_label": "OOS Sharpe (2021–2026)",
        "start_date":   "2026-05-01",
        "status":       "active",
        "symbols":      None,   # no JSON tracking yet
        "color":        "#ec4899",
        "detail_id":    "detail-h181",
    },
    {
        "id":           "options",
        "name":         "Options Book",
        "short":        "Defined-Risk — Manual",
        "desc":         "Discretionary defined-risk structures. IC SPY, bull spreads "
                        "WMT/DLTR, risk reversal DLTR. Each sized to max loss < 2% equity.",
        "sharpe_oos":   None,
        "sharpe_label": "No backtest (manual)",
        "start_date":   "2026-04-26",
        "status":       "active",
        "symbols":      None,   # populated from trades.json
        "color":        "#f97316",
        "detail_id":    "detail-options",
    },
]

# ─── Data loaders ─────────────────────────────────────────────────────────────

def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default if default is not None else []


def tail_log(path: Path, n: int = 30) -> list[str]:
    if not path.exists():
        return []
    return path.read_text().splitlines()[-n:]


def get_alpaca_state() -> dict:
    result = {
        "equity": None, "last_equity": None, "day_pnl": None,
        "day_pnl_pct": None, "buying_power": None, "positions": [], "error": None,
    }
    try:
        from alpaca.trading.client import TradingClient
        api_key = os.environ.get("ALPACA_API_KEY", "")
        secret  = os.environ.get("ALPACA_SECRET", "")
        if not api_key or not secret:
            result["error"] = "ALPACA_API_KEY / ALPACA_SECRET not set"
            return result
        client = TradingClient(api_key, secret, paper=True)
        acct   = client.get_account()
        equity = float(acct.equity)
        last   = float(acct.last_equity)
        result.update({
            "equity": equity, "last_equity": last,
            "day_pnl": equity - last,
            "day_pnl_pct": (equity - last) / last * 100 if last else 0,
            "buying_power": float(acct.buying_power),
        })
        pos_map = {}
        for p in client.get_all_positions():
            pos_map[p.symbol] = {
                "symbol":          p.symbol,
                "qty":             float(p.qty),
                "avg_cost":        float(p.avg_entry_price),
                "current_price":   float(p.current_price),
                "market_value":    float(p.market_value),
                "cost_basis":      float(p.cost_basis),
                "unrealized_pl":   float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc) * 100,
                "change_today":    float(p.change_today) * 100,
            }
        result["positions"] = list(pos_map.values())
        result["position_map"] = pos_map
    except Exception as e:
        result["error"] = str(e)
        result["position_map"] = {}
    return result


def get_recent_orders(n: int = 20) -> list[dict]:
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        api_key = os.environ.get("ALPACA_API_KEY", "")
        secret  = os.environ.get("ALPACA_SECRET", "")
        client  = TradingClient(api_key, secret, paper=True)
        orders  = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.ALL, limit=n))
        return [
            {
                "symbol":            o.symbol,
                "side":              o.side.value,
                "qty":               float(o.qty or 0),
                "notional":          float(o.notional) if o.notional else float((o.qty or 0) * (o.filled_avg_price or 0)),
                "status":            o.status.value,
                "filled_at":         str(o.filled_at)[:16] if o.filled_at else "",
                "filled_avg_price":  float(o.filled_avg_price or 0),
            }
            for o in orders
        ]
    except Exception:
        return []


def strategy_pnl(strat_id: str, pos_map: dict,
                 h112: list, h016: list, pead_open: list, options: list) -> dict:
    """
    Compute starting notional, current value, P&L for each strategy
    by matching symbols from position tracking files to live Alpaca positions.
    """
    out = {"start_val": None, "curr_val": None, "pnl": None, "pnl_pct": None, "positions": []}

    if strat_id == "h112":
        if not h112:
            return out
        last = h112[-1]
        targets = last.get("target", {})
        start_val = sum(targets.values())
        curr_val  = sum(pos_map[s]["market_value"] for s in targets if s in pos_map)
        # Positions from Alpaca for H112 symbols
        out["positions"] = [pos_map[s] for s in targets if s in pos_map]
        if curr_val and start_val:
            out["start_val"] = start_val
            out["curr_val"]  = curr_val
            out["pnl"]       = curr_val - start_val
            out["pnl_pct"]   = (curr_val - start_val) / start_val * 100

    elif strat_id == "h016":
        if not h016:
            return out
        last     = h016[-1]
        holdings = last.get("holdings", [])
        entries  = last.get("entry_prices", {})
        # Approximate start value from Alpaca position cost_basis
        positions = [pos_map[s] for s in holdings if s in pos_map]
        if not positions:
            return out
        start_val = sum(p["cost_basis"] for p in positions)
        curr_val  = sum(p["market_value"] for p in positions)
        out["positions"] = positions
        out["start_val"] = start_val
        out["curr_val"]  = curr_val
        out["pnl"]       = curr_val - start_val
        out["pnl_pct"]   = (curr_val - start_val) / start_val * 100 if start_val else 0

    elif strat_id == "h112ibs":
        syms = ["XLK", "SMH", "IGV"]
        positions = [pos_map[s] for s in syms if s in pos_map]
        if not positions:
            return out
        start_val = sum(p["cost_basis"] for p in positions)
        curr_val  = sum(p["market_value"] for p in positions)
        out["positions"] = positions
        out["start_val"] = start_val
        out["curr_val"]  = curr_val
        out["pnl"]       = curr_val - start_val
        out["pnl_pct"]   = (curr_val - start_val) / start_val * 100 if start_val else 0

    elif strat_id == "h009":
        h009_pos = load_json(PAPER_DIR / "h009_position.json", {})
        if h009_pos.get("status") != "open":
            return out
        entry_price = h009_pos.get("entry_price", 0)
        qty         = h009_pos.get("qty", 0)
        notional    = h009_pos.get("notional", 0)
        spy_live    = pos_map.get("SPY", {})
        curr_price  = spy_live.get("current_price", entry_price)
        curr_val    = qty * curr_price
        pnl         = curr_val - notional
        out["start_val"]  = notional
        out["curr_val"]   = curr_val
        out["pnl"]        = pnl
        out["pnl_pct"]    = pnl / notional * 100 if notional else 0
        out["positions"]  = [{
            "symbol":          "SPY",
            "qty":             qty,
            "avg_cost":        entry_price,
            "current_price":   curr_price,
            "market_value":    curr_val,
            "unrealized_pl":   pnl,
            "unrealized_plpc": pnl / notional * 100 if notional else 0,
        }]

    elif strat_id == "h174":
        if not pead_open:
            return out
        positions = []
        total_notional = 0
        for p in pead_open:
            ticker = p.get("ticker", "")
            notional = p.get("notional", 0)
            pnl_pct_val = p.get("pnl_pct") or 0
            positions.append({
                "symbol":          ticker,
                "cost_basis":      notional,
                "market_value":    notional * (1 + pnl_pct_val / 100),
                "unrealized_plpc": pnl_pct_val,
            })
            total_notional += notional
        out["positions"]  = positions
        out["start_val"]  = total_notional
        out["curr_val"]   = total_notional  # approximate; no live price in pead_positions
        out["pnl"]        = 0
        out["pnl_pct"]    = 0

    elif strat_id == "h181":
        h181_pos = load_json(PAPER_DIR / "h181_positions.json", [])
        last = next((e for e in reversed(h181_pos) if e.get("status") == "open"), None)
        if not last:
            return out
        holdings     = last.get("holdings", [])
        entry_prices = last.get("entry_prices", {})
        target       = last.get("target", {})
        positions    = []
        start_val    = 0.0
        curr_val     = 0.0
        for sym in holdings:
            ep       = entry_prices.get(sym, 0)
            notional = target.get(sym, 0)
            live     = pos_map.get(sym, {})
            cp       = live.get("current_price", ep)
            qty      = notional / ep if ep else 0
            mv       = qty * cp
            start_val += notional
            curr_val  += mv
            positions.append({
                "symbol":          sym,
                "qty":             qty,
                "avg_cost":        ep,
                "current_price":   cp,
                "market_value":    mv,
                "unrealized_pl":   mv - notional,
                "unrealized_plpc": (mv - notional) / notional * 100 if notional else 0,
            })
        out["positions"] = positions
        out["start_val"] = start_val
        out["curr_val"]  = curr_val
        out["pnl"]       = curr_val - start_val
        out["pnl_pct"]   = (curr_val - start_val) / start_val * 100 if start_val else 0

    elif strat_id == "options":
        open_opts = [o for o in options if o.get("status") == "open"]
        # Net cost/credit of all open positions
        total_at_risk = sum(
            (o.get("net_debit", 0) or 0) * 100 * o.get("qty", 1)
            for o in open_opts
        )
        total_credit = sum(
            (o.get("net_credit", 0) or 0) * 100 * o.get("qty", 1)
            for o in open_opts
        )
        out["start_val"] = total_at_risk + total_credit
        out["curr_val"]  = out["start_val"]  # No live BSM without SPY price here
        out["pnl"]       = 0
        out["pnl_pct"]   = 0

    return out


# ─── HTML helpers ─────────────────────────────────────────────────────────────

def pct_color(v: float) -> str:
    if v > 0:   return "#4ade80"
    if v < 0:   return "#f87171"
    return "#94a3b8"


def fmt_pct(v: float, sign: bool = True) -> str:
    s = "+" if (sign and v > 0) else ""
    return f"{s}{v:.2f}%"


def fmt_dollar(v: float, sign: bool = False) -> str:
    s = "+" if (sign and v > 0) else ""
    return f"{s}${v:,.2f}"


def days_active(start_date_str: str) -> int:
    try:
        return (TODAY_DT - date.fromisoformat(start_date_str)).days
    except Exception:
        return 0


# ─── Strategy tile HTML ───────────────────────────────────────────────────────

def build_strategy_tile(strat: dict, pnl_data: dict) -> str:
    color     = strat["color"]
    name      = strat["name"]
    short     = strat["short"]
    desc      = strat["desc"]
    sharpe    = strat["sharpe_oos"]
    sharpe_lbl = strat["sharpe_label"]
    start     = strat["start_date"]
    d_active  = days_active(start)
    detail    = strat["detail_id"]

    # Sharpe badge
    sharpe_html = (
        f'<div class="sharpe-badge" style="background:{color}20;color:{color}">'
        f'Sharpe {sharpe:.2f}</div>'
        if sharpe else
        '<div class="sharpe-badge" style="background:#1e293b;color:#64748b">No backtest</div>'
    )

    # P&L stats
    start_val = pnl_data.get("start_val")
    curr_val  = pnl_data.get("curr_val")
    pnl       = pnl_data.get("pnl")
    pnl_pct   = pnl_data.get("pnl_pct")
    n_pos     = len(pnl_data.get("positions", []))

    if start_val is not None and curr_val is not None:
        sv_str   = fmt_dollar(start_val)
        cv_str   = fmt_dollar(curr_val)
        pnl_str  = f'<span style="color:{pct_color(pnl)};font-weight:700">{fmt_dollar(pnl, sign=True)}</span>'
        pct_str  = f'<span style="color:{pct_color(pnl_pct)};font-weight:700">{fmt_pct(pnl_pct)}</span>'
        pnl_bg   = "#15803d20" if pnl >= 0 else "#7f1d1d20"
        border_c = "#4ade8040" if pnl >= 0 else "#f8717140"
    elif n_pos == 0:
        sv_str = cv_str = "—"
        pnl_str = '<span style="color:#64748b">No trades yet</span>'
        pct_str = '<span style="color:#64748b">—</span>'
        pnl_bg  = "#1e293b"
        border_c = "#334155"
    else:
        sv_str = cv_str = "—"
        pnl_str = '<span style="color:#64748b">Live tracking pending</span>'
        pct_str = '<span style="color:#64748b">—</span>'
        pnl_bg  = "#1e293b"
        border_c = "#334155"

    positions_note = f"{n_pos} open position{'s' if n_pos != 1 else ''}" if n_pos > 0 else "no open positions"

    return f"""
<div class="tile" style="border-left:3px solid {color}">
  <div class="tile-header">
    <div>
      <div class="tile-name" style="color:{color}">{name}</div>
      <div class="tile-short">{short}</div>
    </div>
    {sharpe_html}
  </div>
  <div class="tile-desc">{desc}</div>
  <div class="tile-stats">
    <div class="tile-stat">
      <div class="ts-label">Starting Notional</div>
      <div class="ts-val">{sv_str}</div>
    </div>
    <div class="tile-stat">
      <div class="ts-label">Current Value</div>
      <div class="ts-val">{cv_str}</div>
    </div>
    <div class="tile-stat" style="background:{pnl_bg};border-color:{border_c}">
      <div class="ts-label">P&amp;L ($)</div>
      <div class="ts-val">{pnl_str}</div>
    </div>
    <div class="tile-stat" style="background:{pnl_bg};border-color:{border_c}">
      <div class="ts-label">P&amp;L (%)</div>
      <div class="ts-val">{pct_str}</div>
    </div>
    <div class="tile-stat">
      <div class="ts-label">Days Active</div>
      <div class="ts-val">{d_active}</div>
    </div>
    <div class="tile-stat">
      <div class="ts-label">Backtest Sharpe</div>
      <div class="ts-val" style="color:{color}">{f'{sharpe:.2f}' if sharpe else '—'}</div>
    </div>
  </div>
  <div class="tile-footer">
    <span style="color:#64748b;font-size:0.75rem">{positions_note} · since {start}</span>
    <a href="#{detail}" class="tile-link" style="color:{color}">Details ↓</a>
  </div>
</div>"""


# ─── Detail section builders ──────────────────────────────────────────────────

def pos_table_rows(positions: list) -> str:
    if not positions:
        return '<tr><td colspan="6" style="text-align:center;color:#64748b;padding:14px">No open positions</td></tr>'
    rows = []
    for p in sorted(positions, key=lambda x: -abs(x.get("market_value", 0))):
        pl  = p.get("unrealized_pl", p.get("pnl", 0)) or 0
        plp = p.get("unrealized_plpc", 0) or 0
        rows.append(f"""
        <tr>
          <td><strong>{p.get('symbol','?')}</strong></td>
          <td style="text-align:right">{p.get('qty', '—')}</td>
          <td style="text-align:right">${p.get('avg_cost', p.get('cost_basis', 0)):.2f}</td>
          <td style="text-align:right">${p.get('current_price', 0):.2f}</td>
          <td style="text-align:right">${p.get('market_value', 0):,.0f}</td>
          <td style="text-align:right;color:{pct_color(pl)};font-weight:600">{fmt_dollar(pl, sign=True)} / {fmt_pct(plp)}</td>
        </tr>""")
    return "\n".join(rows)


def log_block(lines: list[str], label: str) -> str:
    if not lines:
        return f'<div class="log-section"><div class="log-label">{label}</div><div class="log-empty">no entries</div></div>'
    entries = []
    for ln in lines:
        col = "#4ade80" if any(k in ln for k in ["filled", "EXIT", "ORDER SUBMITTED", "CONFIRMED"]) \
              else "#f87171" if any(k in ln for k in ["ERROR", "FAIL", "failed"]) \
              else "#94a3b8"
        entries.append(f'<div class="log-line" style="color:{col}">{ln}</div>')
    return f'<div class="log-section"><div class="log-label">{label}</div>{"".join(entries)}</div>'


def section_header(strat: dict) -> str:
    color = strat["color"]
    return f"""
<div class="sec-header" id="{strat['detail_id']}" style="border-left:3px solid {color};padding-left:12px">
  <span style="color:{color};font-weight:700">{strat['name']}</span>
  <span style="color:#64748b;font-size:0.8rem;margin-left:8px">{strat['short']}</span>
  <a href="#top" style="float:right;color:#475569;font-size:0.75rem;text-decoration:none">↑ top</a>
</div>"""


# ─── Options detail ───────────────────────────────────────────────────────────

def options_detail_rows(options: list) -> str:
    open_opts = [o for o in options if o.get("status") == "open"]
    if not open_opts:
        return '<tr><td colspan="7" style="text-align:center;color:#64748b;padding:14px">No open positions</td></tr>'
    rows = []
    for o in open_opts:
        strategy   = o.get("strategy", "?").replace("_", " ").title()
        underlying = o.get("underlying", "?")
        expiry     = o.get("expiry", "?")
        try:
            dte = (date.fromisoformat(expiry) - TODAY_DT).days
        except Exception:
            dte = "?"
        net_credit = o.get("net_credit")
        net_debit  = o.get("net_debit")
        net_str    = f"+${net_credit:.2f} cr" if net_credit else (f"-${net_debit:.2f} db" if net_debit else "—")
        max_profit = o.get("max_profit", 0)
        pnl_val    = o.get("pnl")
        pnl_str    = f'<span style="color:{pct_color(pnl_val)};font-weight:600">{fmt_dollar(pnl_val, sign=True)}</span>' if pnl_val is not None else "—"
        rows.append(f"""
        <tr>
          <td><strong>{underlying}</strong></td>
          <td>{strategy}</td>
          <td>{o.get('entered','?')}</td>
          <td>{expiry} <span style="color:#64748b">({dte}d)</span></td>
          <td style="text-align:right">{net_str}</td>
          <td style="text-align:right">${max_profit:.0f}</td>
          <td style="text-align:right">{pnl_str}</td>
        </tr>""")
    return "\n".join(rows)


# ─── PEAD detail ──────────────────────────────────────────────────────────────

def pead_detail(pead_open: list, pead_closed: list, watchlist: dict) -> str:
    # Stats
    closed_pnls = [t.get("pnl_pct", 0) for t in pead_closed if t.get("pnl_pct") is not None]
    wins   = [p for p in closed_pnls if p > 0]
    losses = [p for p in closed_pnls if p <= 0]
    wr     = len(wins) / len(closed_pnls) * 100 if closed_pnls else 0
    aw     = sum(wins)   / len(wins)   if wins   else 0
    al     = sum(losses) / len(losses) if losses else 0
    exp    = (wr / 100 * aw) + ((1 - wr / 100) * al)

    # Open positions table
    if not pead_open:
        open_rows = '<tr><td colspan="7" style="text-align:center;color:#64748b;padding:14px">No open positions</td></tr>'
    else:
        rows = []
        for p in pead_open:
            try:
                hold = (TODAY_DT - date.fromisoformat(p.get("entry_date",""))).days
            except Exception:
                hold = "?"
            pnl_pct = p.get("pnl_pct")
            pnl_str = f'<span style="color:{pct_color(pnl_pct)};font-weight:600">{fmt_pct(pnl_pct)}</span>' if pnl_pct is not None else "—"
            rows.append(f"""
            <tr>
              <td><strong>{p.get('ticker','?')}</strong></td>
              <td>{p.get('entry_date','?')}</td>
              <td style="text-align:right">{hold}d</td>
              <td>{p.get('exit_date','?')}</td>
              <td style="text-align:right">${p.get('notional',0):,.0f}</td>
              <td style="text-align:right">{p.get('gap_pct',0):.1f}%</td>
              <td style="text-align:right">{pnl_str}</td>
            </tr>""")
        open_rows = "\n".join(rows)

    # Closed trades
    if not pead_closed:
        closed_rows = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">No closed trades yet</td></tr>'
    else:
        rows = []
        for t in reversed(pead_closed[-10:]):
            pnl_pct = t.get("pnl_pct")
            pnl_str = f'<span style="color:{pct_color(pnl_pct)};font-weight:600">{fmt_pct(pnl_pct)}</span>' if pnl_pct is not None else "—"
            rows.append(f"""
            <tr>
              <td><strong>{t.get('ticker','?')}</strong></td>
              <td>{t.get('entry_date','?')}</td>
              <td>{t.get('exit_date','?')}</td>
              <td style="text-align:right">${t.get('entry_price',0):.2f} → ${t.get('exit_price',0):.2f}</td>
              <td style="text-align:right">{pnl_str}</td>
            </tr>""")
        closed_rows = "\n".join(rows)

    # Watchlist
    wl_cands = watchlist.get("candidates", [])
    wl_scores = watchlist.get("scores", {})
    wl_date = watchlist.get("date", "—")
    wl_reason = watchlist.get("reason", "")
    if not wl_cands:
        wl_html = f'<p style="color:#64748b;font-size:0.85rem;padding:12px">No candidates tonight ({wl_reason or "none"})</p>'
    else:
        wl_rows = "".join(
            f'<tr><td><strong>{t}</strong></td><td style="text-align:right">{wl_scores.get(t, {}).get("nlp_score", wl_scores.get(t, "?")):.3f}</td></tr>'
            for t in wl_cands
        )
        wl_html = f'<table><thead><tr><th>Ticker</th><th style="text-align:right">NLP Score</th></tr></thead><tbody>{wl_rows}</tbody></table>'

    col = "#f59e0b"
    return f"""
<div class="stat-row" style="margin-bottom:14px">
  <div class="stat"><div class="stat-label">Trades</div><div class="stat-val">{len(pead_closed)}</div></div>
  <div class="stat"><div class="stat-label">Win Rate</div><div class="stat-val" style="color:{pct_color(wr-50)}">{wr:.0f}%</div></div>
  <div class="stat"><div class="stat-label">Avg Win</div><div class="stat-val" style="color:#4ade80">{aw:+.1f}%</div></div>
  <div class="stat"><div class="stat-label">Avg Loss</div><div class="stat-val" style="color:#f87171">{al:.1f}%</div></div>
  <div class="stat"><div class="stat-label">Expectancy</div><div class="stat-val" style="color:{pct_color(exp)}">{exp:+.2f}%</div></div>
</div>
<div class="two-col">
  <div>
    <div class="subsec-label">Open Positions</div>
    <table>
      <thead><tr><th>Ticker</th><th>Entry</th><th>Hold</th><th>Exit Date</th><th style="text-align:right">Notional</th><th style="text-align:right">Gap</th><th style="text-align:right">P&amp;L</th></tr></thead>
      <tbody>{open_rows}</tbody>
    </table>
  </div>
  <div>
    <div class="subsec-label">Tonight's Watchlist ({wl_date})</div>
    {wl_html}
    <div class="subsec-label" style="margin-top:14px">Recent Closed</div>
    <table>
      <thead><tr><th>Ticker</th><th>Entry</th><th>Exit</th><th style="text-align:right">Prices</th><th style="text-align:right">P&amp;L</th></tr></thead>
      <tbody>{closed_rows}</tbody>
    </table>
  </div>
</div>"""


# ─── Main builder ─────────────────────────────────────────────────────────────

def build_html(acct: dict, h112: list, h016: list, pead_open: list, pead_closed: list,
               watchlist: dict, options: list, orders: list) -> str:

    pos_map = acct.get("position_map", {})
    equity  = acct.get("equity")
    day_pnl = acct.get("day_pnl")
    day_pct = acct.get("day_pnl_pct", 0)
    bp      = acct.get("buying_power")
    err     = acct.get("error")

    # Account-level portfolio start: earliest tracking data
    acct_start_date = "2026-04-26"
    acct_start_equity = 100_000.0  # approximate initial paper account value
    acct_days = days_active(acct_start_date)

    # P&L data per strategy
    pnl_data = {
        s["id"]: strategy_pnl(s["id"], pos_map, h112, h016, pead_open, options)
        for s in STRATEGIES
    }

    # Account summary cards
    equity_str  = fmt_dollar(equity)     if equity   is not None else "—"
    bp_str      = fmt_dollar(bp)         if bp       is not None else "—"
    day_pnl_col = pct_color(day_pnl)     if day_pnl  is not None else "#94a3b8"
    day_pnl_str = fmt_dollar(day_pnl, sign=True) if day_pnl is not None else "—"
    day_pct_str = fmt_pct(day_pct)       if day_pnl  is not None else "—"

    tot_pnl     = sum(d.get("pnl") or 0 for d in pnl_data.values())
    err_banner  = f'<div class="error-banner">⚠ Alpaca error: {err}</div>' if err else ""

    # Tiles
    tiles_html = "\n".join(build_strategy_tile(s, pnl_data[s["id"]]) for s in STRATEGIES)

    # Log tails
    open_log      = tail_log(PAPER_DIR / "pead_open.log")
    exits_log     = tail_log(PAPER_DIR / "pead_exits.log")
    overnight_log = tail_log(PAPER_DIR / "pead_overnight.log")

    # H112 holdings
    h112_last   = h112[-1] if h112 else {}
    h112_date   = h112_last.get("date", "—")
    h112_target = h112_last.get("target", {})
    h112_equity = h112_last.get("equity", 0)
    h112_total  = sum(h112_target.values())
    h112_rows   = "\n".join(
        f'<tr><td><strong>{s}</strong></td>'
        f'<td style="text-align:right">${v:,.0f}</td>'
        f'<td style="text-align:right">{v/h112_total*100:.1f}%</td>'
        f'<td style="text-align:right;color:{pct_color(pos_map.get(s,{}).get("unrealized_plpc",0))};font-weight:600">'
        f'{fmt_pct(pos_map.get(s,{}).get("unrealized_plpc",0))}</td></tr>'
        for s, v in sorted(h112_target.items(), key=lambda x: -x[1])
    ) if h112_target else '<tr><td colspan="4" style="text-align:center;color:#64748b;padding:14px">No data</td></tr>'

    # H016 holdings
    h016_last     = h016[-1] if h016 else {}
    h016_holdings = h016_last.get("holdings", [])
    h016_entries  = h016_last.get("entry_prices", {})
    h016_rows     = "\n".join(
        f'<tr><td><strong>{s}</strong></td>'
        f'<td style="text-align:right">${h016_entries.get(s,0):.2f}</td>'
        f'<td style="text-align:right">${pos_map.get(s,{}).get("current_price",0):.2f}</td>'
        f'<td style="text-align:right;color:{pct_color(pos_map.get(s,{}).get("unrealized_plpc",0))};font-weight:600">'
        f'{fmt_pct(pos_map.get(s,{}).get("unrealized_plpc",0))}</td></tr>'
        for s in h016_holdings
    ) if h016_holdings else '<tr><td colspan="4" style="text-align:center;color:#64748b;padding:14px">No data</td></tr>'

    # Recent orders table
    filled = [o for o in orders if o.get("status") == "filled"][:12]
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
<title>Paper Trading EOD — {TODAY}</title>
<style>
  :root{{--bg:#0f172a;--s1:#1e293b;--s2:#263248;--bd:#334155;--tx:#e2e8f0;--mu:#94a3b8;--gr:#4ade80;--rd:#f87171;--bl:#60a5fa}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}}
  a{{color:inherit;text-decoration:none}}
  .container{{max-width:1200px;margin:0 auto;padding:24px 16px}}
  header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:24px;border-bottom:1px solid var(--bd);padding-bottom:16px}}
  header h1{{font-size:1.4rem;font-weight:700}}
  .gen{{color:var(--mu);font-size:0.78rem;text-align:right}}
  .error-banner{{background:#7f1d1d40;border:1px solid var(--rd);border-radius:8px;padding:10px 14px;margin-bottom:18px;color:var(--rd);font-size:0.85rem}}
  /* Summary bar */
  .summary-bar{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-bottom:28px}}
  .sum-card{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:14px 16px}}
  .sum-label{{color:var(--mu);font-size:0.72rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
  .sum-val{{font-size:1.35rem;font-weight:700}}
  .sum-sub{{color:var(--mu);font-size:0.78rem;margin-top:2px}}
  /* Section */
  .sec-title{{font-size:0.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--mu);margin:28px 0 12px;display:flex;align-items:center;gap:8px}}
  .sec-title::after{{content:"";flex:1;height:1px;background:var(--bd)}}
  .sec-header{{margin:28px 0 12px;font-size:1rem}}
  .subsec-label{{color:var(--mu);font-size:0.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin:14px 0 6px}}
  /* Strategy tiles */
  .tile-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;margin-bottom:32px}}
  .tile{{background:var(--s1);border:1px solid var(--bd);border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:10px}}
  .tile-header{{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}}
  .tile-name{{font-weight:700;font-size:0.95rem}}
  .tile-short{{color:var(--mu);font-size:0.75rem;margin-top:2px}}
  .sharpe-badge{{font-size:0.72rem;font-weight:700;padding:3px 9px;border-radius:20px;white-space:nowrap}}
  .tile-desc{{color:var(--mu);font-size:0.8rem;line-height:1.5}}
  .tile-stats{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}}
  .tile-stat{{background:var(--s2);border:1px solid var(--bd);border-radius:8px;padding:8px 10px}}
  .ts-label{{color:var(--mu);font-size:0.67rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px}}
  .ts-val{{font-size:0.9rem;font-weight:700}}
  .tile-footer{{display:flex;justify-content:space-between;align-items:center;margin-top:2px}}
  .tile-link{{font-size:0.75rem;font-weight:600;opacity:.8}}
  .tile-link:hover{{opacity:1}}
  /* Tables */
  table{{width:100%;border-collapse:collapse;background:var(--s1);border-radius:10px;overflow:hidden;border:1px solid var(--bd)}}
  th{{background:var(--s2);color:var(--mu);font-weight:600;font-size:0.72rem;text-transform:uppercase;letter-spacing:.05em;padding:9px 12px;text-align:left}}
  td{{padding:9px 12px;border-top:1px solid var(--bd);font-size:0.85rem}}
  tr:hover td{{background:var(--s2)}}
  /* Stats row */
  .stat-row{{display:flex;gap:10px;flex-wrap:wrap}}
  .stat{{background:var(--s1);border:1px solid var(--bd);border-radius:8px;padding:9px 14px;min-width:100px}}
  .stat-label{{color:var(--mu);font-size:0.69rem;text-transform:uppercase;letter-spacing:.04em}}
  .stat-val{{font-size:1.05rem;font-weight:700;margin-top:2px}}
  /* Log */
  .log-section{{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:14px;margin-bottom:10px}}
  .log-label{{font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--mu);margin-bottom:6px}}
  .log-line{{font-family:"SF Mono","Fira Code",monospace;font-size:0.72rem;padding:1px 0;white-space:pre-wrap;word-break:break-all}}
  .log-empty{{color:var(--mu);font-size:0.8rem;font-style:italic}}
  /* Layout */
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
  @media(max-width:680px){{.two-col{{grid-template-columns:1fr}}.tile-stats{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body>
<div class="container" id="top">

<header>
  <div>
    <h1>📊 Paper Trading — End of Day</h1>
    <div style="color:var(--mu);font-size:0.82rem;margin-top:2px">George · {TODAY}</div>
  </div>
  <div class="gen">Generated {NOW} CT</div>
</header>

{err_banner}

<!-- Account Summary -->
<div class="summary-bar">
  <div class="sum-card">
    <div class="sum-label">Portfolio Equity</div>
    <div class="sum-val">{equity_str}</div>
    <div class="sum-sub">Alpaca paper account</div>
  </div>
  <div class="sum-card">
    <div class="sum-label">Day P&amp;L</div>
    <div class="sum-val" style="color:{day_pnl_col}">{day_pnl_str}</div>
    <div class="sum-sub" style="color:{day_pnl_col}">{day_pct_str}</div>
  </div>
  <div class="sum-card">
    <div class="sum-label">Buying Power</div>
    <div class="sum-val">{bp_str}</div>
    <div class="sum-sub">Available</div>
  </div>
  <div class="sum-card">
    <div class="sum-label">Account Age</div>
    <div class="sum-val">{acct_days}d</div>
    <div class="sum-sub">Since {acct_start_date}</div>
  </div>
  <div class="sum-card">
    <div class="sum-label">Live Positions</div>
    <div class="sum-val">{len(acct.get("positions",[]))}</div>
    <div class="sum-sub">{len([o for o in options if o.get("status")=="open"])} options · {len(pead_open)} PEAD</div>
  </div>
</div>

<!-- Strategy Tiles -->
<div class="sec-title">Active Strategies ({len(STRATEGIES)})</div>
<div class="tile-grid">
{tiles_html}
</div>

<!-- ──────────────────────────── DETAIL SECTIONS ──────────────────────────── -->

<!-- H112 Composite -->
{section_header(next(s for s in STRATEGIES if s["id"]=="h112"))}
<div style="color:var(--mu);font-size:0.8rem;margin-bottom:10px">Last rebalance <strong style="color:var(--tx)">{h112_date}</strong> · Equity at rebalance <strong style="color:var(--tx)">${h112_equity:,.0f}</strong></div>
<table>
  <thead><tr><th>Symbol</th><th style="text-align:right">Target Value</th><th style="text-align:right">Weight</th><th style="text-align:right">Live P&amp;L %</th></tr></thead>
  <tbody>{h112_rows}</tbody>
</table>

<!-- H016 -->
{section_header(next(s for s in STRATEGIES if s["id"]=="h016"))}
<div style="color:var(--mu);font-size:0.8rem;margin-bottom:10px">Holdings since <strong style="color:var(--tx)">{h016_last.get("date","—")}</strong></div>
<table>
  <thead><tr><th>Symbol</th><th style="text-align:right">Entry Price</th><th style="text-align:right">Current</th><th style="text-align:right">P&amp;L %</th></tr></thead>
  <tbody>{h016_rows}</tbody>
</table>

<!-- H112 Daily IBS -->
{section_header(next(s for s in STRATEGIES if s["id"]=="h112ibs"))}
<table>
  <thead><tr><th>Symbol</th><th>Target Alloc</th><th style="text-align:right">Avg Cost</th><th style="text-align:right">Current</th><th style="text-align:right">Mkt Value</th><th style="text-align:right">P&amp;L</th></tr></thead>
  <tbody>{pos_table_rows(pnl_data["h112ibs"].get("positions", []))}</tbody>
</table>

<!-- H009 -->
{section_header(next(s for s in STRATEGIES if s["id"]=="h009"))}
<div style="color:var(--mu);font-size:0.82rem;margin-bottom:10px">Daily SPY IBS mean-reversion. Signals infrequent (IBS &lt; 0.20 required). Uses 50% of account equity when in position.</div>
<table>
  <thead><tr><th>Symbol</th><th>Qty</th><th style="text-align:right">Entry Price</th><th style="text-align:right">Current</th><th style="text-align:right">Mkt Value</th><th style="text-align:right">P&amp;L</th></tr></thead>
  <tbody>{pos_table_rows(pnl_data["h009"].get("positions", []))}</tbody>
</table>

<!-- H174 PEAD -->
{section_header(next(s for s in STRATEGIES if s["id"]=="h174"))}
{pead_detail(pead_open, pead_closed, watchlist)}

<!-- H181 -->
{section_header(next(s for s in STRATEGIES if s["id"]=="h181"))}
<table>
  <thead><tr><th>Symbol</th><th>Qty</th><th style="text-align:right">Entry Price</th><th style="text-align:right">Current</th><th style="text-align:right">Mkt Value</th><th style="text-align:right">P&amp;L</th></tr></thead>
  <tbody>{pos_table_rows(pnl_data["h181"].get("positions", []))}</tbody>
</table>

<!-- Options -->
{section_header(next(s for s in STRATEGIES if s["id"]=="options"))}
<table>
  <thead><tr><th>Underlying</th><th>Strategy</th><th>Entered</th><th>Expiry</th><th style="text-align:right">Net</th><th style="text-align:right">Max Profit</th><th style="text-align:right">P&amp;L</th></tr></thead>
  <tbody>{options_detail_rows(options)}</tbody>
</table>

<!-- Recent Orders -->
<div class="sec-title">Recent Filled Orders</div>
<table>
  <thead><tr><th>Symbol</th><th>Side</th><th style="text-align:right">Fill Price</th><th style="text-align:right">Notional</th><th>Filled At</th></tr></thead>
  <tbody>{orders_rows}</tbody>
</table>

<!-- Activity Logs -->
<div class="sec-title">Activity Logs</div>
{log_block(overnight_log, "PEAD Overnight — 11 PM scoring")}
{log_block(open_log, "PEAD Open — 9:30 AM gap detection")}
{log_block(exits_log, "PEAD Exits — 3:45 PM MOC")}

</div>
</body>
</html>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"[{NOW}] Generating EOD dashboard…")
    acct        = get_alpaca_state()
    orders      = get_recent_orders(30)
    h112        = load_json(PAPER_DIR / "h112_monthly_trades.json", [])
    h016        = load_json(PAPER_DIR / "h016_positions.json", [])
    pead_open   = load_json(PAPER_DIR / "pead_positions.json", [])
    pead_closed = load_json(PAPER_DIR / "pead_closed.json", [])
    watchlist   = load_json(PAPER_DIR / "pead_watchlist.json", {})
    options     = load_json(PAPER_DIR / "trades.json", [])

    html = build_html(acct, h112, h016, pead_open, pead_closed, watchlist, options, orders)
    out  = REPORTS_DIR / f"eod_dashboard_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"[{NOW}] Saved → {out}")
    print(f"DASHBOARD_PATH={out}")
    return str(out)


if __name__ == "__main__":
    main()
