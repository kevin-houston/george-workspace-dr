---
updated: 2026-06-26
---

# Prediction Market Automated Trading Pipeline

Operational guide for running a live Kalshi/Polymarket trading pipeline on George's infrastructure. Companion to the strategy playbook in [algorithmic-strategies.md](algorithmic-strategies.md) and the [nowcasting-playbook.md](nowcasting-playbook.md).

---

## Architecture overview

The standard pattern is an **event-driven cycle loop** rather than a cron-heavy approach:

```
Ingest → Score → Decide → Execute → Track → Alert
  ↑                                           |
  └───────────────── loop (60s) ──────────────┘
```

**Key reference implementations**:

| Repo | Stars | Description |
|------|-------|-------------|
| [ryanfrigo/kalshi-ai-trading-bot](https://github.com/ryanfrigo/kalshi-ai-trading-bot) | ~300 | Toolkit: RSA auth, SQLite, LLM scoring, Kelly sizing, Streamlit dashboard |
| [OctagonAI/kalshi-deep-trading-bot](https://github.com/OctagonAI/kalshi-deep-trading-bot) | ~200 | 5-gate risk engine, deep fundamental research, CLI interface |
| [0mnjb/Kalshi-AI-Trading-Bot](https://github.com/0mnjb/Kalshi-AI-Trading-Bot) | ~100 | 5-model ensemble; only trades when all models agree |

The ryanfrigo toolkit is the cleanest reference. Core modules:
- `src/clients/kalshi_client.py` — RSA-signed REST + WebSocket
- `src/jobs/ingest.py` — Events API → SQLite
- `src/jobs/track.py` — stop-loss, take-profit, time exits
- `src/clients/openrouter_client.py` — swappable LLM backend
- `beast_mode_dashboard.py` — Streamlit P&L monitor

---

## Production-safe scheduler (APScheduler)

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logging.basicConfig(level=logging.INFO)
scheduler = BlockingScheduler(timezone="America/Chicago")

# Hourly market scan
scheduler.add_job(ingest_markets, CronTrigger(minute=0),
                  id="ingest", replace_existing=True)

# Every 5 min during pre-release windows
scheduler.add_job(check_edge_and_trade, CronTrigger(minute="*/5"),
                  id="trade_scan", replace_existing=True)

# Position tracker — continuous
scheduler.add_job(track_positions, CronTrigger(minute="*/2"),
                  id="track", replace_existing=True)

# Daily tearsheet
scheduler.add_job(daily_summary, CronTrigger(hour=18, minute=0),
                  id="summary", replace_existing=True)

scheduler.start()
```

**Alternative**: Use George's existing NanoClaw `schedule_task` with a pre-task script that checks whether a trade opportunity exists before waking the agent. This is the zero-credit-waste approach:

```javascript
// pre_task_kalshi_check.mjs — outputs {wakeAgent, data}
const r = await fetch("https://trading-api.kalshi.com/trade-api/v2/markets?status=open&category=economics");
const { markets } = await r.json();
const openMarkets = markets.filter(m => m.event_ticker.includes("CPI") || m.event_ticker.includes("FED"));
console.log(JSON.stringify({ wakeAgent: openMarkets.length > 0, data: { markets: openMarkets } }));
```

---

## SQLite tracking schema

Minimal schema for a paper-trading tracker:

```sql
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,            -- 'yes' | 'no'
    entry_price REAL NOT NULL,     -- 0-1 scale
    contracts INTEGER NOT NULL,
    entry_ts TEXT NOT NULL,
    exit_price REAL,
    exit_ts TEXT,
    status TEXT DEFAULT 'open',    -- 'open' | 'closed' | 'expired'
    pnl REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS model_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    model_prob REAL NOT NULL,      -- our estimate P(YES)
    market_price REAL NOT NULL,    -- Kalshi ask / mid price
    edge REAL NOT NULL,            -- model_prob - market_price
    kelly_f REAL,
    trade_taken INTEGER DEFAULT 0, -- 1 if trade executed
    outcome REAL,                  -- 1 if YES won, 0 if NO won (null until settlement)
    brier_contrib REAL             -- (model_prob - outcome)^2
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    n_trades INTEGER DEFAULT 0,
    win_rate REAL,
    pnl REAL,
    balance REAL,
    brier_avg REAL
);
```

```python
import sqlite3
from pathlib import Path

DB_PATH = Path("/workspace/agent/backtesting/paper_trading/kalshi_paper.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def log_prediction(market_id, model_prob, market_price, kelly_f):
    edge = model_prob - market_price
    with get_db() as conn:
        conn.execute("""
            INSERT INTO model_predictions (market_id, ts, model_prob, market_price, edge, kelly_f)
            VALUES (?, datetime('now'), ?, ?, ?, ?)
        """, (market_id, model_prob, market_price, edge, kelly_f))
        conn.commit()

def close_position(position_id, exit_price, outcome):
    """Call when market settles. outcome=1 if YES won."""
    with get_db() as conn:
        conn.execute("""
            UPDATE positions SET exit_price=?, status='closed', pnl=?
            WHERE id=?
        """, (exit_price, (outcome - exit_price), position_id))
        conn.execute("""
            UPDATE model_predictions SET outcome=?, brier_contrib=?
            WHERE market_id = (SELECT market_id FROM positions WHERE id=?)
        """, (outcome, None, position_id))
        conn.commit()
```

---

## Position sizing and risk controls

Production-safe defaults from live bot experience:

```python
RISK = {
    "kelly_fraction":    0.25,   # quarter-Kelly
    "min_confidence":    0.45,   # skip trades below this LLM confidence
    "max_position_pct":  0.05,   # max 5% of balance per trade
    "max_category_pct":  0.30,   # max 30% in one event category (CPI, FOMC, ...)
    "drawdown_halt":     0.15,   # pause all trading if down 15% from peak
    "min_edge":          0.03,   # minimum model-market divergence to trade
}

def check_drawdown_halt(balance_history: list[float]) -> bool:
    """Return True if we should halt trading."""
    if len(balance_history) < 2:
        return False
    peak = max(balance_history)
    current = balance_history[-1]
    return (peak - current) / peak >= RISK["drawdown_halt"]

def size_trade(model_prob, market_price, balance, category_exposure):
    """Returns (side, contracts, spend) or None if no trade."""
    edge = model_prob - market_price
    if abs(edge) < RISK["min_edge"]:
        return None

    side = "yes" if edge > 0 else "no"
    price = market_price if side == "yes" else (1 - market_price)
    M = 1.0 / price
    kelly_f = (model_prob * M - (1 - model_prob)) / (M - 1)
    kelly_f = max(0, kelly_f) * RISK["kelly_fraction"]

    max_from_kelly = kelly_f * balance
    max_from_cap   = balance * RISK["max_position_pct"]
    max_from_cat   = balance * RISK["max_category_pct"] - category_exposure
    spend = min(max_from_kelly, max_from_cap, max(0, max_from_cat))

    contracts = max(1, int(spend / price))
    return side, contracts, spend
```

---

## Minimal live pipeline (nowcasting → Kalshi)

End-to-end pipeline for the CPI nowcasting strategy (see [algorithmic-strategies.md § 3](algorithmic-strategies.md) for model code):

```python
#!/usr/bin/env python3
"""
kalshi_live_cpi.py — minimal CPI nowcasting → Kalshi execution pipeline.
Designed for the George container. Runs at 4 AM CT on CPI release mornings.
"""
import os
import json
import datetime
from pathlib import Path

# --- Nowcast (simplified; full model in nowcasting-playbook.md) ----
from fredapi import Fred
from statsmodels.tsa.arima.model import ARIMA
from scipy.stats import norm
import numpy as np

def build_cpi_nowcast() -> tuple[float, float]:
    """Returns (mu, sigma) for YoY CPI estimate."""
    fred = Fred(api_key=os.environ["FRED_API_KEY"])
    cpi = fred.get_series("CPIAUCSL").dropna()
    yoy = cpi.pct_change(12).dropna() * 100
    model = ARIMA(yoy, order=(2, 0, 1)).fit()
    fc = model.get_forecast(steps=1)
    mu  = fc.predicted_mean.iloc[0]
    std = fc.conf_int(alpha=0.32).diff(axis=1).iloc[0, 1] / 2
    return mu, std

def prob_in_band(lo, hi, mu, sigma):
    return norm.cdf(hi, mu, sigma) - norm.cdf(lo, mu, sigma)

# --- Market lookup (Kalshi REST) ---
import httpx, base64, time, hashlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def get_active_cpi_markets(kalshi_client) -> list[dict]:
    r = httpx.get("https://trading-api.kalshi.com/trade-api/v2/markets",
                  params={"status": "open", "category": "economics", "limit": 200},
                  headers=kalshi_client._headers("GET", "/trade-api/v2/markets"))
    return [m for m in r.json().get("markets", [])
            if "CPI" in m["ticker"].upper() and m["status"] == "open"]

# --- Main loop ---
def run_once(dry_run=True):
    mu, sigma = build_cpi_nowcast()
    print(f"Nowcast: CPI={mu:.2f}% ± {sigma:.2f}%")

    from kalshi_client import KalshiClient   # from ryanfrigo/kalshi-ai-trading-bot
    client = KalshiClient(
        key_id=os.environ["KALSHI_KEY_ID"],
        private_key_pem=os.environ["KALSHI_PRIVATE_KEY"],
    )

    markets = get_active_cpi_markets(client)
    balance = client.get_balance()
    positions = client.get_positions()
    cat_exposure = sum(p["value"] for p in positions if "CPI" in p.get("ticker","").upper())

    for market in markets:
        # Parse band from ticker (e.g. "CPI-26JUN-B32" = "will CPI be ≥3.2%?")
        # Kalshi CPI contract interpretation varies; parse carefully
        yes_ask = market["yes_ask"] / 100
        band_lo, band_hi = parse_cpi_band(market["ticker"])  # your parser
        model_prob = prob_in_band(band_lo, band_hi, mu, sigma)

        sizing = size_trade(model_prob, yes_ask, balance, cat_exposure)
        if sizing is None:
            continue
        side, contracts, spend = sizing

        print(f"{market['ticker']}: model={model_prob:.3f} mkt={yes_ask:.3f} "
              f"edge={model_prob-yes_ask:+.3f} → {side} ×{contracts}")

        if not dry_run:
            order = client.place_order(market["ticker"], side,
                                       int(yes_ask * 100), contracts)
            log_prediction(market["ticker"], model_prob, yes_ask,
                           spend / balance)

if __name__ == "__main__":
    import sys
    dry_run = "--live" not in sys.argv
    run_once(dry_run=dry_run)
```

**Scheduling**: Add to George's task scheduler as a 4 AM CT job on CPI morning (first Tuesday after the 10th of each month). BLS releases at 8:30 AM ET; Kalshi closes CPI contracts ~30 min before, so 4–6 AM ET is the optimal window.

---

## Monitoring and tearsheet

```python
def daily_tearsheet():
    """Print P&L summary. Run at 6 PM CT daily."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT COUNT(*) as n, AVG(pnl) as avg_pnl, SUM(pnl) as total_pnl,
                   AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0.0 END) as win_rate,
                   AVG(brier_contrib) as brier
            FROM positions WHERE status='closed'
              AND date(exit_ts) = date('now')
        """).fetchone()

        balance = conn.execute("""
            SELECT balance FROM daily_stats ORDER BY date DESC LIMIT 1
        """).fetchone()

    print(f"=== Daily Tearsheet {datetime.date.today()} ===")
    print(f"Trades: {rows['n']}  Win%: {rows['win_rate']*100:.0f}%  "
          f"Avg P&L: ${rows['avg_pnl']:.2f}  Total: ${rows['total_pnl']:.2f}")
    print(f"Brier score (day): {rows['brier']:.4f}")
    print(f"Balance: ${balance['balance']:.2f}")
```

---

## Graduation gates (paper → live)

Mirror the equity strategy graduation criteria:

| Gate | Threshold | Notes |
|------|-----------|-------|
| Minimum trades | ≥ 50 resolved contracts | For statistical significance |
| Brier score | < 0.20 (beat market calibration) | Track per event category |
| Win rate @ >5% edge | ≥ 55% | Confirms model edge is real |
| Sharpe (quarterly) | ≥ 0.8 | After Kalshi fees |
| Drawdown | < 20% | From paper balance peak |
| Regime coverage | At least 2 FOMC cycles + 3 CPI releases | Model must work across rate regimes |

---

## Known failure modes

1. **Kalshi closes contracts early**: CPI contracts close ~30 min before release. Miss this → your order queues but doesn't fill. Always check `status == "open"` and `close_time` before placing.
2. **Model-market convergence**: Pre-release, smart money and algo traders continuously reprice. Monitor `yes_ask` over the last 2 hours — if the market is moving toward your model estimate, the edge is being arbitraged away. Respect the 3% minimum edge; check again at -2h before release.
3. **Event cancellation / postponement**: BLS occasionally delays CPI. Kalshi voids these contracts. Handle gracefully with `settlement_value` monitoring.
4. **Auth token expiry**: RSA key signing is per-request (stateless); no token management needed. But key rotation (Kalshi account settings → API keys) should be tracked.
5. **Category concentration**: Multiple CPI bands all show edge → you're correlated across all of them. Cap category exposure (30% default) and treat all open CPI contracts as one correlated position.

---

## Integration checklist (before going live)

- [ ] `KALSHI_KEY_ID` and `KALSHI_PRIVATE_KEY` added to OneCLI vault
- [ ] SQLite DB initialized at `backtesting/paper_trading/kalshi_paper.db`
- [ ] Paper trading mode tested with ≥10 resolved contracts
- [ ] Graduation gates met (see table above)
- [ ] NanoClaw schedule task created (4 AM CT CPI mornings, with pre-task checking market status)
- [ ] Daily tearsheet wired to send Kevin a message if drawdown > 10%
- [ ] `EDGAR_KEY` credential test (for FinBERT enhancement layer; optional)

---

## CloddsBot — Claude-Native Multi-Market Prediction Agent

**Repo**: [alsk1992/CloddsBot](https://github.com/alsk1992/CloddsBot) — Apache 2.0, self-hosted  
**Scope**: 1000+ markets — Polymarket, Kalshi, Binance, Hyperliquid, Solana DEXs, 5 EVM chains  
**Built on**: Claude (Anthropic) with agent commerce protocol for machine-to-machine payments  

### What it does

- **Edge scanning**: evaluates 1000+ active markets for mispricing vs model estimates
- **Instant execution**: submits orders autonomously on detected edge
- **Risk management**: position sizing and drawdown monitoring built-in
- **M2M payments**: agent commerce protocol enables cross-agent coordination (other Claude agents can subscribe to its signals)

### Integration with our H185 pipeline

Our H185 CPI nowcasting produces p(CPI > X) from Cleveland Fed. CloddsBot can:
1. Subscribe to our George agent via M2M → receive p(CPI) estimates
2. Compare vs live Kalshi prices via its scanning loop
3. Execute Kelly-sized bets autonomously when edge > threshold

This would remove the manual step in our current H185 workflow (George checks price, manually submits via Kalshi CLI).

### vs oracle3

| | oracle3 | CloddsBot |
|-|---------|----------|
| Pricing model | Wang Transform (λ̂=0.183 calibrated) | Claude LLM-based |
| Scope | Kalshi/Polymarket/Solana | 1000+ markets incl. crypto DEXs |
| Open source | Yes (Apache 2.0) | Yes (Apache 2.0) |
| Calibration | 291K resolved contracts | Not published |
| Best for | Quantitative binary markets | Broad coverage / LLM-based edge |

For quantitative H185 work: prefer oracle3's Wang Transform. For exploratory multi-market scanning: CloddsBot's broader coverage is valuable.
