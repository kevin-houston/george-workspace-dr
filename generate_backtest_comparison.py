#!/usr/bin/env python3
"""
Paper Trading vs Backtest Comparison Report
Usage: python3 generate_backtest_comparison.py [YYYY-MM-DD]
Output: reports/backtest_comparison_YYYY-MM-DD.html
"""

import json, re, os, glob, math, sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

WORKSPACE = Path("/workspace/agent")
REPORTS_DIR = WORKSPACE / "reports"
PT_DIR = WORKSPACE / "backtesting" / "paper_trading"

TODAY = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")

# ── Known backtest benchmarks ───────────────────────────────────────────────

BM = {
    "h026_sharpe":        1.200,   # H026 standalone OOS 2020-2026
    "h301_sharpe":        1.529,   # H026 + SPY 200MA overlay
    "production_sharpe":  4.158,   # Full production portfolio OOS 2004-2025
    "production_cagr":    0.235,
    "production_maxdd":  -0.036,
    "ibs_note": "IBS backtested per-ETF; exact Sharpe not stored; mean-reversion win rate typically >60%",
    "pead_win_rate":      0.818,   # H174 OOS (n=22)
    "pead_avg_ret":       0.0689,  # H174 OOS mean return per trade
    "pead_n_oos":         22,
}

# ── Data extraction ──────────────────────────────────────────────────────────

def equity_curve():
    """Extract daily equity from EOD dashboard HTML files."""
    records = []
    for path in sorted(glob.glob(str(REPORTS_DIR / "eod_dashboard_*.html"))):
        m = re.search(r"eod_dashboard_(\d{4}-\d{2}-\d{2})\.html", path)
        if not m:
            continue
        html = open(path).read()
        eq = re.search(r'class="sum-val">\$([0-9,]+\.[0-9]+)', html)
        if eq:
            records.append({"date": m.group(1), "equity": float(eq.group(1).replace(",", ""))})
    return records


def portfolio_stats(records):
    """Annualised Sharpe, CAGR, MaxDD from EOD equity curve."""
    if len(records) < 3:
        return {}
    eq = [r["equity"] for r in records]
    dates = [datetime.strptime(r["date"], "%Y-%m-%d") for r in records]
    rets = [(eq[i] - eq[i-1]) / eq[i-1] for i in range(1, len(eq))]
    n = len(rets)
    mu = sum(rets) / n
    var = sum((r - mu)**2 for r in rets) / max(n-1, 1)
    sd = math.sqrt(var) if var > 0 else 0
    sharpe = mu / sd * math.sqrt(252) if sd > 0 else None
    total_ret = (eq[-1] - eq[0]) / eq[0]
    elapsed = (dates[-1] - dates[0]).days
    cagr = (1 + total_ret) ** (365 / max(elapsed, 1)) - 1
    peak = eq[0]; max_dd = 0.0
    for e in eq:
        if e > peak:
            peak = e
        dd = (e - peak) / peak
        if dd < max_dd:
            max_dd = dd
    # Standard error of annualised Sharpe (Lo 2002)
    sharpe_se = math.sqrt((1 + (sharpe or 0)**2 / 2) / max(n, 1)) * math.sqrt(252)
    return {
        "n": n, "total_ret": total_ret, "cagr": cagr,
        "sharpe": sharpe, "max_dd": max_dd,
        "start": records[0]["date"], "end": records[-1]["date"],
        "start_eq": eq[0], "end_eq": eq[-1],
        "elapsed_days": elapsed, "sharpe_se": sharpe_se,
    }


def ibs_stats():
    """Closed IBS round-trips and open positions."""
    path = PT_DIR / "h112_ibs_trades.json"
    if not path.exists():
        return {"closed": [], "open_count": 0, "win_rate": None, "avg_ret": None}
    trades = json.loads(path.read_text())
    open_pos = {}
    closed = []
    for t in trades:
        s = t["symbol"]
        if t["action"] == "BUY":
            open_pos[s] = t
        elif t["action"] == "SELL" and s in open_pos:
            e = open_pos.pop(s)
            ret = (t["price"] - e["price"]) / e["price"]
            held = (datetime.strptime(t["date"], "%Y-%m-%d") -
                    datetime.strptime(e["date"], "%Y-%m-%d")).days
            closed.append({
                "symbol": s, "entry": e["date"], "exit": t["date"],
                "entry_px": e["price"], "exit_px": t["price"],
                "return": ret, "held_days": held,
            })
    win_rate = sum(1 for t in closed if t["return"] > 0) / len(closed) if closed else None
    avg_ret  = sum(t["return"] for t in closed) / len(closed) if closed else None
    return {
        "closed": closed, "open_count": len(open_pos),
        "win_rate": win_rate, "avg_ret": avg_ret,
    }


def monthly_signals():
    """H026 signal history from monthly trade log."""
    path = PT_DIR / "h112_monthly_trades.json"
    if not path.exists():
        return []
    return [
        {
            "date": t["date"],
            "h026": (t.get("signals", {}).get("h026", {}).get("top_n") or ["?"])[0],
            "equity": t["equity"],
        }
        for t in json.loads(path.read_text())
    ]


def spy_return(start_date: str, end_date: str):
    """SPY total return over the period, for context."""
    if not HAS_YF:
        return None
    try:
        spy = yf.download("SPY", start=start_date,
                          end=(datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"),
                          progress=False, auto_adjust=True)
        if spy.empty or len(spy) < 2:
            return None
        closes = spy["Close"].values.flatten()
        return float(closes[-1] / closes[0] - 1)
    except Exception:
        return None


# ── HTML generation ──────────────────────────────────────────────────────────

CSS = """
:root{--bg:#0f172a;--s1:#1e293b;--s2:#263248;--bd:#334155;--tx:#e2e8f0;--mu:#94a3b8;--gr:#4ade80;--rd:#f87171;--bl:#60a5fa;--yl:#fbbf24}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;line-height:1.5}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:1.3rem;font-weight:700}
.gen{color:var(--mu);font-size:0.78rem}
header{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:1px solid var(--bd);padding-bottom:14px;margin-bottom:20px}
.bar{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:28px}
.card{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:14px 16px}
.clabel{color:var(--mu);font-size:0.7rem;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}
.cval{font-size:1.25rem;font-weight:700}
.csub{color:var(--mu);font-size:0.76rem;margin-top:3px}
.sec{font-size:0.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--mu);margin:24px 0 10px;display:flex;align-items:center;gap:8px}
.sec::after{content:"";flex:1;height:1px;background:var(--bd)}
table{width:100%;border-collapse:collapse;background:var(--s1);border-radius:10px;overflow:hidden;border:1px solid var(--bd);margin-bottom:20px}
th{background:var(--s2);color:var(--mu);font-size:0.7rem;text-transform:uppercase;letter-spacing:.05em;padding:9px 12px;text-align:left}
td{padding:9px 12px;border-top:1px solid var(--bd);font-size:0.84rem}
tr:hover td{background:var(--s2)}
.gr{color:var(--gr);font-weight:600}
.rd{color:var(--rd);font-weight:600}
.yl{color:var(--yl);font-weight:600}
.mu{color:var(--mu)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
.scard{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:16px}
.scard h3{font-size:0.9rem;font-weight:700;margin-bottom:4px}
.scard .sdesc{color:var(--mu);font-size:0.76rem;margin-bottom:10px}
.row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--bd);font-size:0.83rem}
.row:last-child{border-bottom:none}
.flag{background:#7f1d1d40;border:1px solid var(--rd);border-radius:8px;padding:10px 14px;margin-bottom:14px;color:var(--rd);font-size:0.83rem}
.info{background:#1e3a5f40;border:1px solid var(--bl);border-radius:8px;padding:10px 14px;margin-bottom:14px;color:var(--bl);font-size:0.83rem}
.spark{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:16px;margin-bottom:20px}
"""

def pct(v, digits=1):
    if v is None: return "—"
    s = f"{v*100:+.{digits}f}%"
    return s

def fmt(v, digits=2):
    if v is None: return "—"
    return f"{v:.{digits}f}"

def color_class(v, good_positive=True):
    if v is None: return "mu"
    if good_positive:
        return "gr" if v > 0 else ("rd" if v < 0 else "mu")
    else:
        return "rd" if v > 0 else ("gr" if v < 0 else "mu")

def sparkline_svg(records, width=900, height=80):
    """Inline SVG equity sparkline."""
    vals = [r["equity"] for r in records]
    dates = [r["date"] for r in records]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = hi - lo or 1
    pad = 4
    def px(i): return pad + i * (width - 2*pad) / max(len(vals)-1, 1)
    def py(v): return height - pad - (v - lo) / rng * (height - 2*pad)
    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals))
    start_color = "#4ade80" if vals[-1] >= vals[0] else "#f87171"
    label_first = f"${vals[0]/1000:.1f}k  {dates[0]}"
    label_last  = f"{dates[-1]}  ${vals[-1]/1000:.1f}k"
    return f"""<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:{height}px">
  <polyline points="{pts}" fill="none" stroke="{start_color}" stroke-width="2"/>
  <text x="{pad}" y="{height-1}" font-size="10" fill="#94a3b8">{label_first}</text>
  <text x="{width-pad}" y="{height-1}" font-size="10" fill="#94a3b8" text-anchor="end">{label_last}</text>
</svg>"""


def build_html(eq_records, stats, ibs, monthly, spy_ret):
    now = datetime.now().strftime("%Y-%m-%d %H:%M CT")
    sharpe_live = stats.get("sharpe")
    sharpe_bm   = BM["h026_sharpe"]
    sharpe_se   = stats.get("sharpe_se", 0)

    # Divergence flags
    flags = []
    if sharpe_live is not None and sharpe_se > 0:
        z = (sharpe_live - sharpe_bm) / sharpe_se
        if z < -2:
            flags.append(f"⚠ Live Sharpe ({fmt(sharpe_live)}) is more than 2σ below H026 benchmark ({sharpe_bm}). "
                         f"z = {z:.1f}. Investigate whether the signal or execution has degraded.")
        elif z > 2:
            flags.append(f"✓ Live Sharpe ({fmt(sharpe_live)}) is more than 2σ above H026 benchmark — outperforming.")

    n_days = stats.get("n", 0)
    infos = []
    if n_days < 40:
        infos.append(f"Statistical note: {n_days} trading-day samples. Sharpe SE ≈ {fmt(sharpe_se)}. "
                     f"Need ≥60 samples for reliable estimates — treat current figures as directional only.")
    if ibs["win_rate"] is None:
        infos.append("IBS: no closed round-trips yet. Win rate comparison pending.")

    # IBS trades table rows
    ibs_rows = ""
    for t in ibs["closed"]:
        c = color_class(t["return"])
        ibs_rows += f"""<tr>
          <td>{t['symbol']}</td><td>{t['entry']}</td><td>{t['exit']}</td>
          <td>${t['entry_px']:.2f}</td><td>${t['exit_px']:.2f}</td>
          <td class="{c}">{pct(t['return'])}</td><td>{t['held_days']}d</td></tr>"""
    if not ibs_rows:
        ibs_rows = "<tr><td colspan='7' class='mu' style='text-align:center'>No closed trades yet</td></tr>"

    # Monthly signal history rows
    sig_rows = ""
    prev_h026 = None
    for s in monthly:
        changed = s["h026"] != prev_h026 and prev_h026 is not None
        badge = " <span style='color:var(--yl);font-size:0.72rem'>← rotated</span>" if changed else ""
        sig_rows += f"<tr><td>{s['date']}</td><td><strong>{s['h026']}</strong>{badge}</td><td>${s['equity']:,.0f}</td></tr>"
        prev_h026 = s["h026"]

    # Comparison table
    def bm_row(metric, live_val, bm_val, fmt_fn=pct, good_positive=True, note=""):
        if live_val is None:
            live_str = "<span class='mu'>—</span>"
            status = "<span class='mu'>insufficient data</span>"
        else:
            c = color_class(live_val, good_positive)
            live_str = f"<span class='{c}'>{fmt_fn(live_val)}</span>"
            if bm_val is not None:
                delta = live_val - bm_val
                dc = color_class(delta, good_positive)
                delta_str = ("+" if delta >= 0 else "") + fmt_fn(delta)
                status = f"<span class='{dc}'>{delta_str}</span> vs benchmark"
            else:
                status = "<span class='mu'>—</span>"
        bm_str = fmt_fn(bm_val) if bm_val is not None else "—"
        return f"<tr><td>{metric}</td><td>{live_str}</td><td>{bm_str}</td><td>{status}</td><td class='mu' style='font-size:0.78rem'>{note}</td></tr>"

    flag_html = "".join(f"<div class='flag'>{f}</div>" for f in flags)
    info_html = "".join(f"<div class='info'>{i}</div>" for i in infos)

    spy_str = pct(spy_ret) if spy_ret is not None else "—"
    total_ret_str = pct(stats.get("total_ret"))
    total_ret_class = color_class(stats.get("total_ret"))

    sharpe_str = fmt(sharpe_live) if sharpe_live is not None else "—"
    sharpe_class = color_class(sharpe_live)
    se_str = f"±{fmt(sharpe_se)}" if sharpe_se else ""

    maxdd_str = pct(stats.get("max_dd"))
    cagr_str = pct(stats.get("cagr"))

    elapsed = stats.get("elapsed_days", 0)
    n_samples = stats.get("n", 0)

    # IBS comparison
    ibs_wr_str = pct(ibs["win_rate"]) if ibs["win_rate"] is not None else "—"
    ibs_wr_class = color_class(ibs["win_rate"])
    ibs_avg_str = pct(ibs["avg_ret"]) if ibs["avg_ret"] is not None else "—"
    n_closed = len(ibs["closed"])
    n_open = ibs["open_count"]

    spark = sparkline_svg(eq_records)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paper vs Backtest — {TODAY}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <div>
    <h1>Paper Trading vs Backtest</h1>
    <div style="color:var(--mu);font-size:0.78rem">{stats.get('start','?')} → {stats.get('end','?')} &nbsp;|&nbsp; {elapsed} calendar days &nbsp;|&nbsp; {n_samples} EOD samples</div>
  </div>
  <div class="gen">Generated {now}</div>
</header>

{flag_html}{info_html}

<div class="bar">
  <div class="card"><div class="clabel">Portfolio Equity</div>
    <div class="cval">${stats.get('end_eq',0):,.0f}</div>
    <div class="csub">Alpaca paper account</div></div>
  <div class="card"><div class="clabel">Total Return</div>
    <div class="cval {total_ret_class}">{total_ret_str}</div>
    <div class="csub">Since {stats.get('start','?')}</div></div>
  <div class="card"><div class="clabel">Live Sharpe (ann.)</div>
    <div class="cval {sharpe_class}">{sharpe_str}</div>
    <div class="csub">SE {se_str} &nbsp;|&nbsp; H026 bm: {sharpe_bm}</div></div>
  <div class="card"><div class="clabel">Max Drawdown</div>
    <div class="cval">{maxdd_str}</div>
    <div class="csub">EOD-to-EOD peak-to-trough</div></div>
  <div class="card"><div class="clabel">Ann. CAGR</div>
    <div class="cval">{cagr_str}</div>
    <div class="csub">Extrapolated from {n_samples}d</div></div>
  <div class="card"><div class="clabel">SPY Same Period</div>
    <div class="cval">{spy_str}</div>
    <div class="csub">Total return benchmark</div></div>
</div>

<div class="sec">Portfolio-Level Comparison</div>
<table>
  <thead><tr><th>Metric</th><th>Live (paper)</th><th>Benchmark</th><th>vs BM</th><th>Notes</th></tr></thead>
  <tbody>
    {bm_row("Sharpe (ann.)", sharpe_live, BM["h026_sharpe"],
             fmt_fn=fmt, note="H026 OOS 2020–2026. SE large with n<60.")}
    {bm_row("H301 overlay gate", sharpe_live, BM["h301_sharpe"],
             fmt_fn=fmt, note="H026+SPY 200MA overlay. Applies if SPY>200MA at month-end.")}
    {bm_row("Ann. CAGR", stats.get("cagr"), BM["production_cagr"],
             note="vs full production portfolio target (H041a+H026+H045+IBS).")}
    {bm_row("Max Drawdown", stats.get("max_dd"), BM["production_maxdd"],
             good_positive=False, note="vs production portfolio OOS -3.60% MaxDD.")}
    {bm_row("Total Return", stats.get("total_ret"), spy_ret,
             note=f"vs SPY {spy_str} same window.")}
  </tbody>
</table>

<div class="sec">H026 Monthly Rotation — Signal History</div>
<div class="info" style="margin-bottom:10px">Paper account has been in H026 signal since 2026-04-28. Signal: top-1 momentum
 from 25-asset universe. Benchmark: OOS Sharpe 1.200 (2020–2026).</div>
<table>
  <thead><tr><th>Rebalance Date</th><th>H026 Top Pick</th><th>Equity at Rebalance</th></tr></thead>
  <tbody>{sig_rows}</tbody>
</table>

<div class="sec">IBS Mean-Reversion — Round Trips</div>
<div class="grid2">
  <div class="scard">
    <h3>Live results</h3>
    <div class="sdesc">XLK (20%) + SMH (8%) + IGV (2%) | Entry IBS &lt; threshold, Exit IBS &gt; threshold or max hold</div>
    <div class="row"><span>Closed trades</span><span><strong>{n_closed}</strong></span></div>
    <div class="row"><span>Open trades</span><span><strong>{n_open}</strong></span></div>
    <div class="row"><span>Win rate</span><span class="{ibs_wr_class}"><strong>{ibs_wr_str}</strong></span></div>
    <div class="row"><span>Avg return/trade</span><span><strong>{ibs_avg_str}</strong></span></div>
  </div>
  <div class="scard">
    <h3>Backtest reference</h3>
    <div class="sdesc">IBS mean-reversion backtested per-ETF. Exact Sharpe not stored in hypothesis log; parameters confirmed OOS.</div>
    <div class="row"><span>Win rate (expected)</span><span class="mu">&gt;60% typical mean-reversion</span></div>
    <div class="row"><span>Avg hold</span><span class="mu">3–6 trading days</span></div>
    <div class="row"><span>Signal frequency</span><span class="mu">~1–3 trades/month/ETF</span></div>
    <div class="row"><span>Statistical power</span><span class="yl">Low — need ≥20 closed trades</span></div>
  </div>
</div>
<table>
  <thead><tr><th>Symbol</th><th>Entry</th><th>Exit</th><th>Entry Px</th><th>Exit Px</th><th>Return</th><th>Held</th></tr></thead>
  <tbody>{ibs_rows}</tbody>
</table>

<div class="sec">PEAD (H174) — Waiting for First Trade</div>
<div class="scard" style="margin-bottom:20px">
  <h3>H174 FinBERT dual-filter PEAD</h3>
  <div class="sdesc">Score ≥ 0.18 + EPS surprise ≥ 2% + gap-up ≥ 3%. 5% equity per position, 20-day hold.</div>
  <div class="row"><span>Live trades (paper)</span><span class="mu"><strong>0</strong> — no qualifying events yet</span></div>
  <div class="row"><span>Backtest OOS win rate</span><span class="gr"><strong>{pct(BM['pead_win_rate'])}</strong> (n={BM['pead_n_oos']})</span></div>
  <div class="row"><span>Backtest OOS avg return</span><span class="gr"><strong>{pct(BM['pead_avg_ret'])}</strong> per trade</span></div>
  <div class="row"><span>Status</span><span class="yl">Watchlist empty on recent nights — low earnings volume or no qualifying 8-Ks</span></div>
</div>

<div class="sec">Equity Curve</div>
<div class="spark">{spark}</div>

<div style="color:var(--mu);font-size:0.76rem;margin-top:20px;border-top:1px solid var(--bd);padding-top:12px">
  <strong>Caveats:</strong> {n_samples} EOD samples ({elapsed} calendar days). Sharpe SE ≈ {fmt(sharpe_se)} —
  reliable comparison requires ≥60 samples. IBS: {n_closed} closed trades — need ≥20 for win rate confidence.
  PEAD: n=0. Production portfolio full blend (H041a+H026+H045+IBS) not yet live; paper account runs H026+IBS only.
  Paper fills ≠ live fills; slippage and PDT rules not applied.
</div>
</div>
</body>
</html>"""
    return html


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"[{TODAY}] Generating backtest comparison report…")

    eq = equity_curve()
    print(f"  Equity samples: {len(eq)}")

    stats = portfolio_stats(eq)
    ibs   = ibs_stats()
    monthly = monthly_signals()

    start = stats.get("start")
    end   = stats.get("end")
    spy = spy_return(start, end) if start and end else None
    if spy is not None:
        print(f"  SPY return {start}→{end}: {spy*100:+.2f}%")

    out_path = REPORTS_DIR / f"backtest_comparison_{TODAY}.html"
    out_path.write_text(build_html(eq, stats, ibs, monthly, spy))
    print(f"  Saved → {out_path}")
    print(f"COMPARISON_PATH={out_path}")

    # Print quick summary to stdout
    s = stats.get("sharpe")
    print(f"\n  Live Sharpe: {fmt(s) if s else '—'}  (H026 bm: {BM['h026_sharpe']})")
    print(f"  Total return: {pct(stats.get('total_ret'))}")
    print(f"  Max drawdown: {pct(stats.get('max_dd'))}")
    print(f"  IBS closed trades: {len(ibs['closed'])} | win rate: {pct(ibs['win_rate'])}")
    print(f"  PEAD trades: 0")

if __name__ == "__main__":
    main()
