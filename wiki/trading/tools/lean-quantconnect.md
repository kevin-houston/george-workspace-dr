---
updated: 2026-04-26
status: evaluated — Docker pending approval
---

# LEAN / QuantConnect

**LEAN** is QuantConnect's open-source algorithmic trading engine — the same engine that powers their cloud platform, available for self-hosted use.

- **Repo**: github.com/QuantConnect/Lean
- **CLI**: `pip install lean` (installed at `/home/node/.local/bin/lean`, v1.0.225)
- **License**: Apache 2.0
- **Languages**: Python and C# both first-class

---

## Why It Matters for Our Setup

| Feature | Our Current Setup | LEAN |
|---------|-------------------|------|
| Options backtesting | Not possible | ✅ Full support |
| Greeks / IV | Not available | ✅ Daily pre-calc + real-time |
| Multi-leg orders | Not implemented | ✅ Combo orders |
| Early assignment | Not modeled | ✅ Automatic heuristic |
| Futures / FX | Not available | ✅ Full support |
| Live trading bridge | Not available | ✅ Broker connectors |
| Data management | yfinance/Alpaca manual | ✅ Managed with ApiDataProvider |

Our homegrown `backtesting/daily/` is faster for rapid hypothesis testing on daily EOD equity strategies. LEAN is the right tool for **options strategies and eventual live trading**.

---

## Installation Status

| Component | Status |
|-----------|--------|
| `lean` CLI | ✅ Installed (v1.0.225) |
| Docker | ⏳ Admin approval pending |
| .NET SDK 8.0 | ⏳ Admin approval pending |
| QuantConnect account | ❓ Not confirmed — ask Kevin |

---

## Two Paths to Run LEAN

### Path A: Cloud Backtesting (No Docker needed)
1. Create free account at quantconnect.com
2. `lean login` — enter User ID + API token from QC account settings
3. `lean cloud push` — upload algorithm
4. `lean cloud backtest` — run on QuantConnect servers
5. Results pulled back locally

**Free tier**: 10 backtests/day, up to 10 years minute-resolution data, full options data included.

### Path B: Local (Requires Docker)
1. `lean init` — scaffold config and data directory
2. `lean project-create --language python "MyStrategy"` — create project
3. Write algorithm in `MyStrategy/main.py`
4. `lean backtest "MyStrategy"` — runs in Docker container
5. Results in `MyStrategy/backtests/<timestamp>/`

Data auto-downloaded on first run via `ApiDataProvider` (requires QC account for auth, but free).

---

## Options Capabilities

| Feature | Support |
|---------|---------|
| Greeks (Δ, Γ, θ, ν) | ✅ Daily pre-calc; real-time in algo |
| Implied Volatility | ✅ Per-contract Black-Scholes |
| Option chain filtering | ✅ By delta, DTE, IV, OI |
| Early assignment (American) | ✅ Auto: >5% ITM near expiry |
| European-style (SPX) | ✅ |
| Multi-leg combo orders | ✅ |
| IV surface / skew | ⚠️ Not natively; custom indicator needed |
| Pin risk | ❌ Not modeled |
| Intraday Greeks | ⚠️ Daily only in historical backtests |

---

## Python Algorithm Structure (LEAN)

```python
class IronCondorAlgorithm(QCAlgorithm):
    
    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100_000)
        
        self.spy = self.add_equity("SPY", Resolution.MINUTE).symbol
        option = self.add_option("SPY", Resolution.MINUTE)
        option.set_filter(lambda u: u.include_weeklys()
                                     .expiration(30, 60)
                                     .delta(0.10, 0.30))
        
    def on_data(self, data):
        chain = data.option_chains.get(self.spy)
        if not chain:
            return
        
        # Filter: 45-DTE contracts
        expiry = min(c.expiry for c in chain)
        calls = [c for c in chain if c.right == OptionRight.CALL 
                 and c.expiry == expiry]
        puts  = [c for c in chain if c.right == OptionRight.PUT 
                 and c.expiry == expiry]
        
        # Select 16-delta strikes
        short_call = min(calls, key=lambda c: abs(c.greeks.delta - (-0.16)))
        short_put  = min(puts,  key=lambda c: abs(c.greeks.delta - 0.16))
        # ... build condor, submit combo order
```

---

## LEAN vs. Our Daily Engine

| Use case | Use |
|----------|-----|
| Daily EOD momentum/rotation strategies | Our `backtesting/daily/` (faster, simpler) |
| Options strategies (iron condor, CSP, CC) | LEAN |
| Intraday ORB strategies | Our `backtesting/orb/` |
| Live trading automation | LEAN (when ready) |
| Options strategy → live Alpaca | LEAN (Alpaca broker integration exists) |

---

## Running LEAN without the CLI (Docker-in-Docker workaround)

The LEAN CLI has a Docker-in-Docker path issue when running in a container: it creates temp files in `/tmp` of the container but the Docker daemon (on the host) can't find those paths.

**Workaround**: run LEAN's Docker image directly using host filesystem paths.

Host path mapping: container `/workspace/agent/` = host `/home/kevin/nc/nanoclaw-v2/groups/dm-with-kevin/`

```bash
HOST=/home/kevin/nc/nanoclaw-v2/groups/dm-with-kevin/backtesting/lean
docker run --name lean_run \
  -v "$HOST/lean-docker-config.json:/Lean/Launcher/bin/Debug/config.json:ro" \
  -v "$HOST/BuyHold:/Lean/Launcher/bin/Debug/Algorithm.Python/BuyHold:ro" \
  quantconnect/lean:latest
docker cp lean_run:/Lean/Launcher/bin/Debug/BuyHoldSPY.json ./results/
docker rm lean_run
```

Helper script: `backtesting/lean/run_lean.sh <AlgorithmName> [config_file]`

**Validated**: SPY buy-and-hold 2019–2021 gave 24.8% CAGR, 33.5% max DD — matches reality.

## Algorithm Status

| Algorithm | File | Status |
|-----------|------|--------|
| Iron Condor (H007) | `backtesting/lean/IronCondor/main.py` | ✅ Written — needs options data |
| Buy-and-Hold test | `backtesting/lean/BuyHold/main.py` | ✅ Validated |

Iron condor implements: monthly entry, 45-DTE, 16-delta shorts, 5-pt wings, tastytrade exit rules (50% profit / 2× loss / 21 DTE).

**Options data gap**: LEAN image has only 1 day of SPY options data (2023-08-03). Full backtest requires QC account (org tier, paid) or ThetaData subscription ($35/month).

See [Options Income Strategies](../algorithms/options-income-strategies.md) for strategy background and [Hypothesis Log](../backtesting/hypothesis-log.md) for H007 card.

---

## Next Steps

1. Get Kevin's answer on QuantConnect account (for cloud path — no Docker needed)
2. Admin approve Docker (for local path)
3. Run `lean backtest "IronCondor"` — algorithm ready
4. Compare LEAN results to manual calculations to validate engine accuracy
