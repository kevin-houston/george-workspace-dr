# Kevin's Action Items

Items here are surfaced in the **4 PM daily status report**. Add new items from any task or session.
Mark done by changing `[ ]` → `[x]` (or I'll mark them when confirmed complete).

Format: `- [ ] YYYY-MM-DD — Category — Description`

---

## Open

- [ ] 2026-04-13 — Robinhood — Run one-time login to cache session token (fixes portfolio advisor using stale March 8 holdings). Command: `groups/telegram_main/robinhood-advisor/venv/bin/python groups/telegram_main/robinhood-advisor/login_once.py`

---
### 📡 Data Sources to Set Up

- [x] 2026-04-13 — Data: OpenAI API key — ✅ Done 2026-04-21. Key set in `/workspace/group/.env`. 122 models confirmed available. Unlocks R28 Phase 2 real EarningsQualityAgent, R33 QuantaAlpha, R29 LLM filter.

- [x] 2026-04-13 — Data: Financial Modeling Prep (FMP) API key — ✅ Done 2026-04-21. Key set in `/workspace/group/.env`. AAPL earnings surprises confirmed working. Enables real EPS surprise data for PEAD strategies.

- [x] 2026-04-13 — Data: Polygon.io API key — ✅ Done 2026-04-21. Key set in `/workspace/group/.env`. Status OK, OHLCV bars confirmed. Enables options data for Bull Put Spread paper trading.

- [x] 2026-04-13 — Data: NewsAPI.org key — ✅ Done 2026-04-21. Key set in `/workspace/group/.env` as `NEWSAPI_KEY`. 39 articles confirmed. Enables news sentiment for portfolio advisor and R28 NewsAgent.

- [x] 2026-04-13 — Data: ChartLibrary API key (free sandbox) — ✅ Done 2026-04-21. Key set in `/workspace/group/.env`. Working at `https://chartlibrary.io/api/v1/` with `Authorization: Bearer` header. AAPL pattern matches confirmed. 200 calls/day sandbox tier.

- [ ] 2026-04-13 — Data: HistoricalOptionData.com free data — Fill out the form at historicaloptiondata.com/free-data/ to get an FTP download link for free EOD options data (bid/ask, all strikes/expirations, back to 2003, one free symbol per month). Enables running the R28 bull put spread backtest (Sharpe 2.58/2.47 on XOM/CVX) through Optopsy (`pip install optopsy`) and building a proper `pt_bull_put_spread.py` paper trader. No cost, just a name/email form.

- [x] 2026-04-13 — Data: FRED API key (free) — ✅ Done 2026-04-21. Key set in `/workspace/group/.env`. 10Y-2Y yield spread confirmed working. Already in use by macro_harness.py for regime classification.

## Done

<!-- Move completed items here with [x] and a done date -->
