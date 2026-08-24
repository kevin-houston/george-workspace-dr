---
created: 2026-08-24
updated: 2026-08-24
category: paper-trading
tags: [corporate-actions, dividends, splits, alpaca, reconciliation, ops]
---

# Corporate Actions Handling — Dividends, Splits & Symbol Changes in Automated Paper Trading

Every monthly-rebalanced sleeve in the production portfolio (H149/H026 ETF rotation,
H181 stock reversal) and the daily IBS sleeve holds positions in dividend-paying
ETFs/stocks across a full Alpaca paper cycle. None of the paper-trading scripts
(`h112_monthly.py`, `h181_monthly.py`, `pead_*` family) currently reconcile cash
dividends, splits, or symbol changes against `strategy_accounts.json` — a real gap,
since a silent split or an unrecorded dividend credit will desync a strategy's tracked
equity from what Alpaca's account actually holds, corrupting the OOS-vs-live comparison
the Live Graduation Criteria gate depends on.

**Related pages**: [Live Graduation Criteria](live-graduation-criteria.md) | [Risk Controls & Live Trading Monitoring](risk-controls-and-monitoring.md) | [Idempotency & Concurrency Control](idempotency-concurrency-control.md)

---

## Why this matters here specifically

- Sector ETFs (XLK/XLE/XLF/etc.) and low-vol ETFs (USMV/SPLV/etc.) used across
  H026/H041a/H045/H354 all pay quarterly cash dividends — ignored dividends understate
  a sleeve's true total return relative to its backtested benchmark, which is built on
  `yfinance`/adjusted-close data that already bakes dividends into the price series.
  A paper account tracking raw price return will structurally under-report vs. the
  backtest it's meant to validate.
- Forward/reverse stock splits change share count and price simultaneously; if a
  script computes position size from a stale `shares_held` value across a split
  boundary, the next rebalance's sell/buy delta will be wrong by the split ratio.
  Individual stocks in H181's 30-stock universe are more split-prone than the ETF
  sleeves.
- Symbol changes / ticker migrations (not covered by Alpaca's Corporate Actions API —
  see below) can silently break scripts that key `strategy_accounts.json` positions by
  ticker string.

None of this has caused a live incident yet (per `.local-fragments/task-registry.md`),
but it's an unaddressed gap flagged now rather than discovered mid-drawdown.

---

## Alpaca's Corporate Actions API

Alpaca launched a dedicated Corporate Actions API (announced on the Alpaca blog,
[Introducing Corporate Actions API: Announcements](https://alpaca.markets/blog/introducing-corporate-actions-api-announcements/)).
It replaces the older, now-deprecated `TradingClient.get_corporate_announcements()` /
`get_corporate_announcement_by_id()` methods — new code should use
`alpaca.data.historical.corporate_actions.CorporateActionsClient.get_corporate_actions()`
from `alpaca-py`.

**Endpoint**: `GET https://data.alpaca.markets/v1/corporate-actions`
(sandbox: `https://data.sandbox.alpaca.markets/v1/corporate-actions`)

**Coverage**: `reverse_split`, `forward_split`, `unit_split`, `cash_dividend`,
`stock_dividend`, `spin_off`, `cash_merger`, `stock_merger`, `stock_and_cash_merger`,
`redemption`, `name_change`, `worthless_removal`, `rights_distribution`,
`partial_call`, `reorganization`. Full reference:
[docs.alpaca.markets/reference/corporateactions-1](https://docs.alpaca.markets/reference/corporateactions-1).

**Notable gap**: per Alpaca's own announcement post, "bespoke reorganization
announcements, such as symbol changes, redemptions, liquidations, delistings, and
tender offers['s exact timing/mechanics] are not [fully] available" through this feed
with the same reliability as scheduled dividends/splits — worth a defensive check
(ticker-not-found handling) in any script that keys off symbol strings long-term.

**Historical depth**: data available back to April 2020. New data lands "typically
before market open on the trading day following the declaration date," per Alpaca.

**Query parameters**: `symbols`, `cusips`, `types`, `region` (`us`/`non_us`/`all`,
default `us`), `start`/`end` (YYYY-MM-DD), `ids`, `limit` (1–1000, default 100),
`data_quality` (`complete`/`all`), `page_token`, `sort`. Auth via standard
`APCA-API-KEY-ID`/`APCA-API-SECRET-KEY` headers — same credentials as the trading API,
works against the paper account.

### Example: fetch upcoming dividends for the H026 universe

```python
from alpaca.data.historical.corporate_actions import CorporateActionsClient
from alpaca.data.requests import CorporateActionsRequest
from datetime import date, timedelta

client = CorporateActionsClient(api_key=API_KEY, secret_key=API_SECRET)

req = CorporateActionsRequest(
    symbol_or_symbols=["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLY", "XLP", "XLC", "XLRE"],
    types=["cash_dividend", "forward_split", "reverse_split"],
    start=date.today() - timedelta(days=7),
    end=date.today() + timedelta(days=30),
)
actions = client.get_corporate_actions(req)

for cd in actions.get("cash_dividends", []):
    print(f"{cd['symbol']}: ${cd['rate']} ex {cd['ex_date']} payable {cd['payable_date']}")
```

Raw REST equivalent (useful if the SDK method signature drifts — Alpaca's docs note
the corporate-actions surface changed materially in 2026, e.g. the June 2026
`cas_region` parameter addition):

```bash
curl -s "https://data.alpaca.markets/v1/corporate-actions?symbols=XLK,XLE,XLF&types=cash_dividend&start=2026-08-01&end=2026-09-30" \
  -H "APCA-API-KEY-ID: $ALPACA_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_SECRET"
```

### Pricing / plan requirement

Not explicitly documented on a single page — Alpaca's plan comparison pages don't call
out corporate-actions access as a separate line item, and the Basic (free) market-data
plan's own docs page doesn't mention corporate actions at all. Trading API access
(order execution, account/positions) is free-tier on a paper account regardless;
market-data endpoints beyond IEX/15-min-delayed generally require **Algo Trader Plus
($99/mo — full SIP real-time + OPRA options + up to 10k req/min)**. Given the
Corporate Actions endpoint lives under `data.alpaca.markets` alongside the paid
market-data surface, budget for the possibility it's gated the same way — verify
empirically against the paper account before relying on it (a quick unauthenticated
test call is cheap; do not assume free-tier access without checking the actual
response code).

---

## Practical reconciliation pattern for this project

This project doesn't need general-purpose adjusted-price handling (the backtests
already consume `yfinance` adjusted-close data, which bakes in dividends/splits
correctly for signal generation) — the gap is specifically **live paper-account
bookkeeping**, i.e. keeping `strategy_accounts.json` sleeve equity in sync with what
Alpaca's account actually reflects after a corporate action fires.

1. **Dividends**: Alpaca credits cash dividends directly to account cash balance on
   payable date — no position adjustment needed, but `strategy_accounts.json`'s
   per-sleeve cash tracking (if it tracks cash separately from Alpaca's pooled
   account cash) needs a matching credit, or sleeve NAV will drift low relative to the
   true Alpaca-reflected value. Simplest fix: query
   `get_corporate_actions(types=["cash_dividend"])` for held tickers each morning
   before market open, and credit `rate × shares_held_at_record_date` to the owning
   sleeve.
2. **Splits**: Alpaca auto-adjusts `qty` and average cost basis on the ex-date — no
   manual position-quantity math needed. The risk is purely in any script that caches
   `shares_held` from a prior day rather than re-querying Alpaca's live position qty
   at rebalance time. Audit `h112_monthly.py`/`h181_monthly.py` for this pattern
   before assuming they're split-safe.
3. **Symbol/ticker changes**: since Alpaca's own coverage here is incomplete, the
   cheapest mitigation is a scheduled daily check (fits the existing PEAD-style
   pre-task gate pattern) — `get_corporate_actions(types=["name_change"])` filtered to
   the current universe list, with an alert (not silent skip) if a held ticker
   appears, since this needs human/agent judgment on how to remap the position.

None of this is implemented yet. Given the low likelihood of a corporate action
hitting mid-cycle vs. the cost of building it now, this is logged here as a concrete,
scoped follow-up rather than built during this off-hours session — flagged as a staged
dream-cycle proposal (see today's scan).

---

## Sources

- [Introducing Corporate Actions API: Announcements — Alpaca blog](https://alpaca.markets/blog/introducing-corporate-actions-api-announcements/)
- [Corporate Actions — Alpaca-py SDK reference](https://alpaca.markets/sdks/python/api_reference/trading/corporate-actions.html)
- [Corporate actions — Alpaca API docs reference](https://docs.alpaca.markets/reference/corporateactions-1)
- [Mandatory Corporate Actions — Alpaca docs](https://docs.alpaca.markets/docs/mandatory-corporate-actions)
- [About Market Data API — Alpaca docs (Basic vs paid tier limits)](https://docs.alpaca.markets/docs/about-market-data-api)
- [alpaca-docs GitHub: corporate-actions/announcements.md](https://github.com/alpacahq/alpaca-docs/blob/master/content/api-references/broker-api/corporate-actions/announcements.md)
