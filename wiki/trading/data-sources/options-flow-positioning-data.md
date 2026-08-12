---
added: 2026-08-12
updated: 2026-08-12
category: data-source
relevance: options-income-strategies.md (0DTE iron condor GEX gate), smart-money-concepts-ict.md, spx-dispersion-variance.md, value-factors.md (congressional overlap with alternative-data.md)
---

# Options Flow, Dealer Positioning & Dark Pool Data

Distinct from raw options *chain* data (see [Options Data Sources](options-data.md) — ThetaData/ORATS/Polygon for historical Greeks/IV) and from general [alternative data](alternative-data.md) (Quiver's congressional/social feeds). This page covers products that compute or aggregate **derived positioning signals**: unusual options flow/"whale" alerts, dealer gamma exposure (GEX/DEX/VEX), dark pool prints, and the vendors that package them.

The category splits into three distinct product types, useful for choosing a stack:

| Category | What it gives you | Vendors |
|----------|-------------------|---------|
| **Raw data infrastructure** | Tick-level trades/quotes you compute signals from yourself | Polygon/Massive, Tradier, ThetaData |
| **Pre-computed exposure analytics** | Per-strike dealer gamma/delta/vanna, gamma flip, call/put walls, already computed | FlashAlpha, ORATS, SpotGamma |
| **Flow & sentiment products** | Human-readable "unusual activity" alerts, dark pool prints, congressional/insider overlays | Unusual Whales, Quiver Quantitative |

No free tier exists for real-time flow or positioning data at production quality — this is a paid-only category. FlashAlpha is the only vendor here offering a genuinely free (if limited) tier.

---

## Unusual Whales — flow, dark pool, congress/insiders

**URL**: https://unusualwhales.com  
**API docs**: https://api.unusualwhales.com/docs  
**Public API overview**: https://unusualwhales.com/public-api

The broadest single API in this category: 200+ REST endpoints plus 15 WebSocket channels plus a hosted MCP server, spanning options flow/whale alerts, dark pool prints and levels, Market Tide (net premium, put/call ratio sentiment), GEX/Greeks (11 endpoints), congressional trades (4 endpoints), insider Form 4 filings (4 endpoints), earnings, and standard price/stock data (37 endpoints).

### Auth & access

```python
import requests

UW_KEY = "YOUR_UW_API_KEY"

def uw_get(path: str, **params) -> dict:
    r = requests.get(
        f"https://api.unusualwhales.com/api/{path}",
        headers={"Authorization": f"Bearer {UW_KEY}"},
        params=params, timeout=15,
    )
    r.raise_for_status()
    return r.json()

# Example: net GEX for a ticker
gex = uw_get("stock/SPY/greek-exposure")

# Example: dark pool prints for a ticker
prints = uw_get("darkpool/SPY")
```

### MCP server (direct Claude/agent integration)

```json
{
  "mcpServers": {
    "unusual-whales": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://api.unusualwhales.com/api/mcp",
                "--header", "Authorization: Bearer YOUR_API_KEY"]
    }
  }
}
```

Can be wired via this project's `add_mcp_server` tool once a key is provisioned through OneCLI.

### Pricing (as of 2026-08)

| Tier | Price | Notes |
|------|-------|-------|
| API Trial (Basic) | Free for 1 week, billed weekly | 30,000 req/day, 90-day historical lookback |
| API Basic | $150/mo ($125/mo annual) | 40,000 req/day, 2-year historical lookback |
| Historical option trades (full market) | $250/mo | Separate add-on; 10% discount on annual |
| Retail subscription (dashboard, not API) | $48/mo | UI only, not API access |

**No permanent free tier for the API** — only a 1-week trial. Historical option-trade replay is priced separately from the live-flow API.

### Verdict for this project

Best fit as a **discretionary confirmation layer** for the existing 0DTE iron condor and PEAD-GAP strategies — e.g., cross-check a PEAD-GAP entry against dark-pool prints or unusual call/put flow before committing capital — rather than a backtestable systematic signal, since the paid historical tier ($250/mo full-market) is expensive relative to project scale and there's no evidence yet that flow/dark-pool signals have been isolated with an IS/OOS Sharpe edge (unlike, e.g., H163/H174 FinBERT PEAD). Treat as a research/monitoring tool, not (yet) a hypothesis input.

---

## FlashAlpha — pre-computed dealer positioning (GEX/DEX/VEX/CHEX)

**URL**: https://flashalpha.com  
**Already referenced** in [options-income-strategies.md](../algorithms/options-income-strategies.md) (0DTE iron condor GEX gate) and [options-data.md](options-data.md) source comparison table.

FlashAlpha is the quant-first alternative to Unusual Whales' flow-alert focus: one API call returns per-strike dollar gamma, net GEX, gamma flip level, call wall, put wall, and a regime classification (positive/negative gamma). The Alpha (top) plan adds raw SVI vol-surface parameters per expiry, total variance surface grids, butterfly/calendar arbitrage detection, variance swap fair values, and vanna/charm/volga/speed surfaces.

### Pricing (2026, corrected from the 2026-05-01 options-data.md figures)

| Tier | Price/mo |
|------|----------|
| Free | $0 — 5 req/day, no credit card required |
| Starter | $63 |
| Pro | $239 |
| Alpha | $1,199 |
| Commercial | From $2,500/mo |

**Note**: `options-data.md` currently lists FlashAlpha as "Free / $79 / $299" (as of 2026-05-01) — pricing has since restructured to $0 / $63 / $239 / $1,199. Worth reconciling that table on a future pass.

### Free tier viability

5 requests/day is enough to spot-check the GEX regime classification (positive vs. negative gamma) for SPY once daily before the 0DTE entry window (2:00–2:44pm ET per the existing playbook) — but not enough for systematic backtesting or multi-ticker scanning. The existing options-income-strategies.md playbook already references "FlashAlpha or equivalent" for the dealer GEX risk score gate; this confirms the free tier is usable for that single-ticker, once-daily checklist item without a paid plan.

### Verdict

Already the recommended vendor in this wiki's 0DTE playbook — this page just consolidates *why* (public documented REST API + free tier, vs. Unusual Whales' no-free-tier flow product and SpotGamma's dashboard-only, no-public-API positioning).

---

## SpotGamma — dashboard, no public API

**URL**: https://spotgamma.com

Strongest discretionary-trader brand for gamma exposure ("HIRO" real-time flow indicator, gamma levels dashboard). No public, documented REST API as of this research — positioning data is consumed through the dashboard or a TradingView integration, not programmatically. **Not usable for automated/backtested strategies in this project's pipeline** — logged for reference only, since it recurs in every options-analytics comparison alongside FlashAlpha and Unusual Whales.

---

## Quiver Quantitative — dark pool short-volume angle

Already covered in depth in [Alternative Data Sources](alternative-data.md) (congressional trades, WSB mentions, Wikipedia views, government contracts). Cross-referencing here for completeness: Quiver's `offexchange()` endpoint tracks off-exchange/dark-pool short volume as % of total volume per ticker — a cheaper ($30/mo, bundled with the rest of the Quiver API) but coarser (ticker-daily, not per-print) alternative to Unusual Whales' `darkpool` endpoints (3 endpoints, print + level granularity). Use Quiver if dark-pool *volume percentage* is enough signal; use Unusual Whales if individual dark-pool *prints* (size, price, time) are needed.

---

## Comparison summary

| Provider | Best for | Free tier | Paid entry | Public API | Backtestable history |
|----------|----------|-----------|-----------|-----------|----------------------|
| Unusual Whales | Flow alerts, dark pool prints, congress/insiders in one API | 1-week trial only | $150/mo (40k req/day) | Yes, REST+WS+MCP | 2yr @ $150/mo, full history priced separately ($250/mo) |
| FlashAlpha | Pre-computed GEX/DEX/VEX, vol surfaces | Yes — 5 req/day | $63/mo | Yes, REST, documented | Since Jan 2017 (minute-level) |
| SpotGamma | Discretionary gamma dashboard | Dashboard trial only | Subscription (dashboard) | **No public API** | N/A |
| Quiver Quantitative | Dark-pool % + congress/insider/social bundle | No | $30/mo | Yes, REST + `pip install quiverquant` | Nightly since ~2018 |

**Recommended stack for this project**: FlashAlpha free tier (5 req/day covers the existing single-ticker daily 0DTE GEX check) + Unusual Whales as a manual/discretionary confirmation layer if Kevin wants deeper flow visibility, upgrading to the $150/mo Unusual Whales API tier only if a systematic backtest first demonstrates the flow signal has edge beyond what GEX regime classification already provides.

---

## Cross-References

- [Options Data Sources](options-data.md) — historical chains, IV, Greeks (raw data, not positioning)
- [Alternative Data Sources](alternative-data.md) — Quiver congressional/social/short-volume detail
- [0DTE Iron Condor / Options Income Strategies](../algorithms/options-income-strategies.md) — existing production use of FlashAlpha GEX gate
- [SPX Dispersion Trading & Variance Risk Premium](../algorithms/spx-dispersion-variance.md) — potential consumer of dealer positioning data for entry timing
- [Smart Money Concepts (ICT)](../algorithms/smart-money-concepts-ict.md) — order block / liquidity concepts that dark pool print data could validate empirically
