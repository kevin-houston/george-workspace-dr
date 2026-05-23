#!/usr/bin/env python3
"""
Robinhood + Finviz Dashboard
Fetches live positions from Robinhood, enriches with Finviz data, saves HTML report.
Credentials via env vars: ROBINHOOD_USERNAME, ROBINHOOD_PASSWORD, ROBINHOOD_MFA (optional)
"""
import os
import sys
import json
import datetime
import time
import pickle
from pathlib import Path

# ── Credentials ──────────────────────────────────────────────────────────────
USERNAME = os.environ.get("ROBINHOOD_USERNAME", "")
PASSWORD = os.environ.get("ROBINHOOD_PASSWORD", "")
MFA_CODE = os.environ.get("ROBINHOOD_MFA", "")  # only if MFA is required
PICKLE_PATH = str(Path.home() / ".robinhood_session")

# ── Login ─────────────────────────────────────────────────────────────────────
import robin_stocks.robinhood as rh

def login():
    if not USERNAME or not PASSWORD:
        print("ERROR: ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD env vars not set.")
        sys.exit(1)
    kwargs = dict(username=USERNAME, password=PASSWORD,
                  store_session=True, pickle_path=PICKLE_PATH)
    if MFA_CODE:
        kwargs["mfa_code"] = MFA_CODE
    try:
        rh.login(**kwargs)
        print("✅ Robinhood login OK")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        sys.exit(1)

def get_positions():
    """Return list of {ticker, qty, avg_cost, current_price, equity, pnl_pct}"""
    raw = rh.get_open_stock_positions()
    positions = []
    for pos in raw:
        try:
            qty = float(pos.get("quantity", 0))
            if qty < 0.001:
                continue
            avg_cost = float(pos.get("average_buy_price", 0))
            instrument_url = pos.get("instrument")
            instrument = rh.get_instrument_by_url(instrument_url)
            ticker = instrument.get("symbol", "???")
            quote = rh.get_latest_price(ticker)
            current_price = float(quote[0]) if quote else 0.0
            equity = qty * current_price
            pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost else 0.0
            positions.append({
                "ticker": ticker,
                "qty": qty,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "equity": equity,
                "pnl_pct": pnl_pct,
            })
        except Exception as e:
            print(f"  ⚠️  Skipped one position: {e}")
    positions.sort(key=lambda x: x["equity"], reverse=True)
    return positions

# ── Finviz enrichment ─────────────────────────────────────────────────────────
def get_finviz_data(ticker):
    try:
        from finvizfinance.quote import finvizfinance as fvf
        stock = fvf(ticker)
        fund = stock.ticker_fundament()
        ratings_df = stock.ticker_outer_ratings()
        news_df = stock.ticker_news()

        # Fundamentals we care about
        keys = ["Market Cap", "P/E", "Forward P/E", "EPS (ttm)", "EPS next Y",
                "Profit Margin", "Debt/Eq", "Beta", "RSI (14)", "52W High",
                "52W Low", "Avg Volume", "Sector", "Industry"]
        fundamentals = {k: fund.get(k, "—") for k in keys}

        # Latest analyst rating
        if ratings_df is not None and not ratings_df.empty:
            latest = ratings_df.sort_values("Date", ascending=False).iloc[0]
            analyst = f"{latest.get('Firm','?')} → {latest.get('Rating','?')} ({latest.get('Price Target','?')})"
        else:
            analyst = "—"

        # Top 3 news items
        news = []
        if news_df is not None and not news_df.empty:
            for _, row in news_df.head(3).iterrows():
                news.append({"title": row.get("Title",""), "link": row.get("Link",""),
                             "date": str(row.get("Date",""))})

        return {"fundamentals": fundamentals, "analyst": analyst, "news": news}
    except Exception as e:
        return {"fundamentals": {}, "analyst": "—", "news": [], "error": str(e)}

# ── HTML generation ───────────────────────────────────────────────────────────
PNL_COLOR = lambda p: "#16a34a" if p >= 0 else "#dc2626"

def render_html(positions, finviz_data):
    ts = datetime.datetime.now().strftime("%B %d, %Y %I:%M %p CT")
    total_equity = sum(p["equity"] for p in positions)

    cards = ""
    for pos in positions:
        t = pos["ticker"]
        fv = finviz_data.get(t, {})
        fund = fv.get("fundamentals", {})
        pnl_color = PNL_COLOR(pos["pnl_pct"])
        pnl_sign = "+" if pos["pnl_pct"] >= 0 else ""

        fund_rows = ""
        for k, v in fund.items():
            fund_rows += f"<tr><td>{k}</td><td><b>{v}</b></td></tr>"

        news_html = ""
        for n in fv.get("news", []):
            news_html += f'<li><a href="{n["link"]}" target="_blank">{n["title"]}</a> <span class="date">{n["date"][:10]}</span></li>'

        analyst = fv.get("analyst", "—")
        err = fv.get("error", "")
        err_html = f'<p class="err">⚠️ Finviz: {err}</p>' if err else ""

        weight = (pos["equity"] / total_equity * 100) if total_equity else 0

        cards += f"""
        <div class="card">
          <div class="card-header">
            <div class="ticker">{t}</div>
            <div class="price">${pos['current_price']:.2f}
              <span class="pnl" style="color:{pnl_color}">{pnl_sign}{pos['pnl_pct']:.1f}%</span>
            </div>
          </div>
          <div class="meta">
            {pos['qty']:.4f} shares · avg cost ${pos['avg_cost']:.2f} · equity ${pos['equity']:,.0f} · weight {weight:.1f}%
          </div>
          {err_html}
          <div class="two-col">
            <div>
              <h4>Fundamentals</h4>
              <table class="fund-table">{fund_rows}</table>
            </div>
            <div>
              <h4>Latest Analyst Rating</h4>
              <p class="analyst">{analyst}</p>
              <h4>Recent News</h4>
              <ul class="news">{news_html}</ul>
            </div>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Robinhood Portfolio Dashboard</title>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0 }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
           background:#0f172a; color:#e2e8f0; padding:24px }}
    h1 {{ font-size:1.6rem; margin-bottom:4px; color:#f8fafc }}
    .subtitle {{ color:#94a3b8; font-size:.85rem; margin-bottom:24px }}
    .summary {{ background:#1e293b; border-radius:10px; padding:16px 20px;
                display:flex; gap:32px; margin-bottom:24px; flex-wrap:wrap }}
    .summary-item {{ display:flex; flex-direction:column }}
    .summary-item .label {{ font-size:.72rem; text-transform:uppercase;
                             letter-spacing:.05em; color:#64748b }}
    .summary-item .value {{ font-size:1.25rem; font-weight:600; color:#f8fafc }}
    .card {{ background:#1e293b; border-radius:12px; padding:20px;
             margin-bottom:16px; border:1px solid #334155 }}
    .card-header {{ display:flex; justify-content:space-between; align-items:center;
                    margin-bottom:6px }}
    .ticker {{ font-size:1.4rem; font-weight:700; color:#38bdf8 }}
    .price {{ font-size:1.2rem; font-weight:600 }}
    .pnl {{ font-size:.95rem; margin-left:8px; font-weight:700 }}
    .meta {{ font-size:.8rem; color:#94a3b8; margin-bottom:12px }}
    .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:16px;
                margin-top:12px }}
    h4 {{ font-size:.78rem; text-transform:uppercase; letter-spacing:.05em;
          color:#64748b; margin-bottom:6px }}
    .fund-table {{ width:100%; border-collapse:collapse; font-size:.82rem }}
    .fund-table td {{ padding:3px 6px; border-bottom:1px solid #334155 }}
    .fund-table tr:last-child td {{ border-bottom:none }}
    .fund-table td:first-child {{ color:#94a3b8; width:55% }}
    .analyst {{ font-size:.85rem; background:#0f172a; border-radius:6px;
                padding:8px 10px; margin-bottom:10px }}
    .news {{ font-size:.8rem; list-style:none; padding:0 }}
    .news li {{ margin-bottom:6px; line-height:1.35 }}
    .news a {{ color:#7dd3fc; text-decoration:none }}
    .news a:hover {{ text-decoration:underline }}
    .date {{ color:#64748b; font-size:.72rem; margin-left:4px }}
    .err {{ color:#f87171; font-size:.78rem; margin-bottom:8px }}
    @media (max-width:600px) {{ .two-col {{ grid-template-columns:1fr }} }}
  </style>
</head>
<body>
  <h1>Robinhood Portfolio Dashboard</h1>
  <p class="subtitle">Generated {ts} · {len(positions)} positions</p>
  <div class="summary">
    <div class="summary-item"><span class="label">Total Equity</span>
      <span class="value">${total_equity:,.0f}</span></div>
    <div class="summary-item"><span class="label">Positions</span>
      <span class="value">{len(positions)}</span></div>
  </div>
  {cards}
</body>
</html>"""

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🔐 Logging in to Robinhood...")
    login()

    print("📊 Fetching positions...")
    positions = get_positions()
    print(f"   Found {len(positions)} positions")

    print("🔍 Enriching with Finviz data...")
    finviz_data = {}
    for i, pos in enumerate(positions):
        t = pos["ticker"]
        print(f"   [{i+1}/{len(positions)}] {t}...")
        finviz_data[t] = get_finviz_data(t)
        time.sleep(0.5)  # be polite to Finviz

    print("🖥️  Rendering dashboard...")
    html = render_html(positions, finviz_data)
    out_path = f"/workspace/agent/reports/robinhood_dashboard_{datetime.date.today()}.html"
    os.makedirs("/workspace/agent/reports", exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    print(f"✅ Dashboard saved: {out_path}")

    # Also save latest as a fixed filename for easy access
    latest_path = "/workspace/agent/reports/robinhood_dashboard_latest.html"
    with open(latest_path, "w") as f:
        f.write(html)
    print(f"✅ Latest copy: {latest_path}")
