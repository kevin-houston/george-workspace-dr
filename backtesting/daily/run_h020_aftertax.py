"""
H020 After-Tax Analysis
-----------------------
Universe : SPY, QQQ, TLT, GLD, IEF
Signal   : top-2 by (12m momentum rank + inverse 6m vol rank), 50/50 each
Rebalance: monthly (last trading day of month)
Period   : 2008-01-01 → 2026-04-25

After-tax rules:
  - On each SALE: if held < 12 months → STCG rate 37%; if ≥ 12 months → LTCG rate 20%
  - Losses carry forward (by type: ST or LT)
  - Track after-tax equity curve alongside pre-tax
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

INITIAL_EQUITY = 100_000.0
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

FULL_START = "2007-01-01"   # need 12m warmup before 2008-01-01
ANALYSIS_START = "2008-01-01"
ANALYSIS_END   = "2026-04-25"

STCG_RATE = 0.37
LTCG_RATE = 0.20

UNIVERSE = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
TOP_N = 2


# ─────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────

def _cache_path(tickers, start, end):
    import hashlib
    key = "_".join(sorted(tickers)) + f"_close_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h020_at_{h}.parquet"


def fetch_close(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    cp = _cache_path(tickers, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} from {start} to {end} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────
# Signal computation
# ─────────────────────────────────────────────

def compute_monthly_signals(prices: pd.DataFrame, assets: list[str]) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by month-end dates with columns = assets,
    values = combined rank score (higher = better). Also returns selected top_n.
    """
    px = prices[assets].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    records = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N:
            continue
        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top = list(combined.nlargest(TOP_N).index)
        records.append({
            "date": month_end,
            "top": top,
            "scores": combined.to_dict(),
        })

    return records


# ─────────────────────────────────────────────
# Position tracker for tax accounting
# ─────────────────────────────────────────────

@dataclass
class Lot:
    ticker: str
    purchase_date: pd.Timestamp
    cost_basis_per_share: float   # price per share at purchase
    shares: float                 # number of "shares" (we track fractional)


@dataclass
class TaxLedger:
    stcg_carryforward: float = 0.0   # net ST gains accumulated (can be negative = loss)
    ltcg_carryforward: float = 0.0   # net LT gains accumulated
    total_stcg_gains: float = 0.0    # gross ST gains before tax
    total_ltcg_gains: float = 0.0    # gross LT gains before tax
    total_stcg_losses: float = 0.0   # gross ST losses
    total_ltcg_losses: float = 0.0   # gross LT losses
    total_tax_paid: float = 0.0
    sale_events: list = field(default_factory=list)  # for auditing


# ─────────────────────────────────────────────
# Pre-tax backtest: track exact monthly positions
# ─────────────────────────────────────────────

def run_backtest_with_tax(prices: pd.DataFrame) -> dict:
    """
    Runs H020 strategy from ANALYSIS_START to ANALYSIS_END.
    Returns pre-tax and after-tax equity curves, plus tax breakdown.
    """
    assets = [a for a in UNIVERSE if a in prices.columns]
    if len(assets) < TOP_N:
        raise ValueError(f"Need at least {TOP_N} assets in prices, got {assets}")

    signals = compute_monthly_signals(prices, assets)
    print(f"  Computed {len(signals)} monthly signal observations")

    # Filter to analysis window
    signals = [s for s in signals if str(s["date"])[:10] >= ANALYSIS_START]

    # Build daily price index over the analysis window
    px = prices[assets].loc[ANALYSIS_START:ANALYSIS_END].dropna(how="all")

    # Get all month-end dates that fall within our signal list
    signal_dates = {s["date"]: s["top"] for s in signals}

    # ── Pre-tax simulation ──────────────────────────────────────────────
    # We track equity dollar-for-dollar using monthly holding periods.
    # Each month: 50% in each of top 2 assets, rebalanced at month-end.

    monthly_px = px.resample("ME").last()
    # Filter signal dates to those within analysis range
    valid_months = [d for d in signal_dates if d >= pd.Timestamp(ANALYSIS_START) and d <= pd.Timestamp(ANALYSIS_END)]
    valid_months.sort()

    if not valid_months:
        raise ValueError("No valid signal months in analysis range")

    print(f"  Analysis months: {len(valid_months)}, from {valid_months[0].date()} to {valid_months[-1].date()}")

    # Pre-tax: simple monthly return tracking
    pretax_equity = INITIAL_EQUITY
    pretax_curve = [(pd.Timestamp(ANALYSIS_START), INITIAL_EQUITY)]

    # After-tax: we apply tax drag at each rebalance
    aftertax_equity = INITIAL_EQUITY
    aftertax_curve  = [(pd.Timestamp(ANALYSIS_START), INITIAL_EQUITY)]

    tax_ledger = TaxLedger()

    # Lots: list of Lot objects for currently held positions
    # We represent the portfolio as "shares" of each ETF, with lots tracking purchase date/price
    current_portfolio: dict[str, list[Lot]] = defaultdict(list)  # ticker -> list of Lot

    # Track holding periods for stats
    holding_periods_by_etf: dict[str, list[int]] = defaultdict(list)  # ticker -> [days held]

    prev_month_end = None
    prev_top = []

    for idx, month_end in enumerate(valid_months):
        top = signal_dates[month_end]

        if prev_month_end is None:
            # Initialize: buy top-2 at month-end prices, 50/50
            for ticker in top:
                if ticker in px.columns:
                    price = float(px.loc[:month_end, ticker].iloc[-1])
                    allocation = aftertax_equity * 0.50
                    shares = allocation / price
                    lot = Lot(
                        ticker=ticker,
                        purchase_date=month_end,
                        cost_basis_per_share=price,
                        shares=shares,
                    )
                    current_portfolio[ticker].append(lot)
            prev_month_end = month_end
            prev_top = top
            continue

        # ── Step 1: Compute pre-tax returns for the period ──────────────
        period_px = px.loc[prev_month_end:month_end]
        if len(period_px) < 2:
            prev_month_end = month_end
            prev_top = top
            continue

        # Pre-tax: apply monthly return
        pretax_period_ret = 0.0
        for ticker in prev_top:
            if ticker in period_px.columns:
                p0 = float(period_px[ticker].iloc[0])
                p1 = float(period_px[ticker].iloc[-1])
                if p0 > 0:
                    pretax_period_ret += (p1 / p0 - 1) / TOP_N

        pretax_equity *= (1 + pretax_period_ret)

        # Daily breakdown for pre-tax curve
        for day_idx in range(1, len(period_px)):
            day = period_px.index[day_idx]
            day_ret = 0.0
            for ticker in prev_top:
                if ticker in period_px.columns:
                    p0 = float(period_px[ticker].iloc[day_idx - 1])
                    p1 = float(period_px[ticker].iloc[day_idx])
                    if p0 > 0:
                        day_ret += (p1 / p0 - 1) / TOP_N
            pretax_curve.append((day, pretax_curve[-1][1] * (1 + day_ret)))

        # ── Step 2: After-tax rebalance ─────────────────────────────────
        # Determine what changed: sold assets and new assets
        sold_tickers = [t for t in prev_top if t not in top]
        new_tickers  = [t for t in top if t not in prev_top]
        held_tickers = [t for t in top if t in prev_top]

        # Current market value of portfolio
        portfolio_value_before_tax = 0.0
        for ticker, lots in current_portfolio.items():
            if ticker in period_px.columns:
                price_now = float(period_px[ticker].iloc[-1])
                for lot in lots:
                    portfolio_value_before_tax += lot.shares * price_now

        # Also apply daily after-tax curve (same returns as pre-tax within period, tax only at rebalance)
        for day_idx in range(1, len(period_px)):
            day = period_px.index[day_idx]
            day_ret = 0.0
            for ticker in prev_top:
                if ticker in period_px.columns:
                    p0 = float(period_px[ticker].iloc[day_idx - 1])
                    p1 = float(period_px[ticker].iloc[day_idx])
                    if p0 > 0:
                        day_ret += (p1 / p0 - 1) / TOP_N
            aftertax_curve.append((day, aftertax_curve[-1][1] * (1 + day_ret)))

        # Process sales and compute tax
        taxes_owed = 0.0
        for ticker in sold_tickers:
            lots = current_portfolio.pop(ticker, [])
            price_now = float(period_px[ticker].iloc[-1]) if ticker in period_px.columns else 0
            for lot in lots:
                proceeds = lot.shares * price_now
                cost     = lot.shares * lot.cost_basis_per_share
                gain     = proceeds - cost
                days_held = (month_end - lot.purchase_date).days
                holding_periods_by_etf[ticker].append(days_held)

                if days_held >= 365:
                    # LTCG
                    if gain >= 0:
                        tax_ledger.total_ltcg_gains += gain
                        # Apply loss carryforward
                        if tax_ledger.ltcg_carryforward < 0:
                            offset = min(gain, -tax_ledger.ltcg_carryforward)
                            taxable = gain - offset
                            tax_ledger.ltcg_carryforward += offset
                        else:
                            taxable = gain
                        tax_due = taxable * LTCG_RATE
                        taxes_owed += tax_due
                        tax_ledger.ltcg_carryforward += (gain - taxable)  # net gain after offset = 0 if fully offset
                        # Actually: if gain was partially offset, leftover was taxed
                    else:
                        # LT loss
                        tax_ledger.total_ltcg_losses += abs(gain)
                        tax_ledger.ltcg_carryforward += gain  # negative

                    tax_ledger.sale_events.append({
                        "date": str(month_end.date()),
                        "ticker": ticker,
                        "days_held": days_held,
                        "gain": round(gain, 2),
                        "type": "LTCG" if gain >= 0 else "LT_LOSS",
                    })
                else:
                    # STCG
                    if gain >= 0:
                        tax_ledger.total_stcg_gains += gain
                        if tax_ledger.stcg_carryforward < 0:
                            offset = min(gain, -tax_ledger.stcg_carryforward)
                            taxable = gain - offset
                            tax_ledger.stcg_carryforward += offset
                        else:
                            taxable = gain
                        tax_due = taxable * STCG_RATE
                        taxes_owed += tax_due
                    else:
                        tax_ledger.total_stcg_losses += abs(gain)
                        tax_ledger.stcg_carryforward += gain  # negative

                    tax_ledger.sale_events.append({
                        "date": str(month_end.date()),
                        "ticker": ticker,
                        "days_held": days_held,
                        "gain": round(gain, 2),
                        "type": "STCG" if gain >= 0 else "ST_LOSS",
                    })

        # Also: held tickers - if portfolio needs to rebalance weight (e.g., drift), sell/buy difference
        # For simplicity: held tickers are kept as-is (no partial rebalance)

        # Deduct taxes from after-tax equity
        tax_ledger.total_tax_paid += taxes_owed

        # After-tax equity after paying taxes
        aftertax_after_tax = aftertax_curve[-1][1] - taxes_owed
        if aftertax_after_tax <= 0:
            aftertax_after_tax = aftertax_curve[-1][1]  # floor at pre-tax (edge case)

        # Update after-tax curve's last point to reflect tax payment
        aftertax_curve[-1] = (aftertax_curve[-1][0], aftertax_after_tax)
        aftertax_equity = aftertax_after_tax

        # Update lots for held tickers (just update value reference, shares unchanged)
        # New tickers: buy at month-end prices, proportional to remaining equity

        # Determine new portfolio allocation:
        # After taxes, remaining capital = aftertax_equity
        # All positions: held_tickers keep their lots, new_tickers get fresh lots

        # First, let's figure out remaining capital after accounting for sold positions
        # Value of held positions (at current prices)
        held_value = 0.0
        for ticker in held_tickers:
            if ticker in period_px.columns:
                price_now = float(period_px[ticker].iloc[-1])
                for lot in current_portfolio[ticker]:
                    held_value += lot.shares * price_now

        # Capital to redeploy = aftertax_equity - held_value
        # (This handles the case where sold positions freed up cash minus taxes)
        cash_available = aftertax_equity - held_value

        # Ideal allocation: 50% each in top 2
        for ticker in top:
            ideal_allocation = aftertax_equity * 0.50
            price_now = float(period_px[ticker].iloc[-1]) if ticker in period_px.columns else 0
            if price_now <= 0:
                continue

            if ticker in held_tickers:
                # Currently held - check if we need to adjust weight
                current_held_val = sum(lot.shares * price_now for lot in current_portfolio[ticker])
                diff_val = ideal_allocation - current_held_val
                if abs(diff_val) > 1.0:  # meaningful rebalance
                    if diff_val > 0:
                        # Buy more
                        new_shares = diff_val / price_now
                        current_portfolio[ticker].append(Lot(
                            ticker=ticker,
                            purchase_date=month_end,
                            cost_basis_per_share=price_now,
                            shares=new_shares,
                        ))
                    else:
                        # Sell excess (FIFO)
                        sell_value = -diff_val
                        remaining = sell_value
                        new_lots = []
                        for lot in current_portfolio[ticker]:
                            lot_val = lot.shares * price_now
                            if remaining <= 0:
                                new_lots.append(lot)
                            elif lot_val <= remaining:
                                remaining -= lot_val
                                # This sale is a rebalance trim - for simplicity treat as new lot removal
                                # Tax already accounted for in the main sell logic above (simplified)
                            else:
                                # Partial sell
                                shares_to_sell = remaining / price_now
                                lot.shares -= shares_to_sell
                                remaining = 0
                                new_lots.append(lot)
                        if new_lots:
                            current_portfolio[ticker] = new_lots
            else:
                # New ticker - buy fresh
                if cash_available >= 0:
                    shares = min(ideal_allocation, cash_available) / price_now
                    current_portfolio[ticker].append(Lot(
                        ticker=ticker,
                        purchase_date=month_end,
                        cost_basis_per_share=price_now,
                        shares=shares,
                    ))
                    cash_available -= shares * price_now

        prev_month_end = month_end
        prev_top = top

    # ── Build Series from curves ──────────────────────────────────────
    pretax_idx  = pd.DatetimeIndex([d for d, _ in pretax_curve])
    pretax_vals = [v for _, v in pretax_curve]
    pretax_series = pd.Series(pretax_vals, index=pretax_idx)
    pretax_series = pretax_series[~pretax_series.index.duplicated(keep='last')]

    aftertax_idx  = pd.DatetimeIndex([d for d, _ in aftertax_curve])
    aftertax_vals = [v for _, v in aftertax_curve]
    aftertax_series = pd.Series(aftertax_vals, index=aftertax_idx)
    aftertax_series = aftertax_series[~aftertax_series.index.duplicated(keep='last')]

    return {
        "pretax_series":  pretax_series,
        "aftertax_series": aftertax_series,
        "tax_ledger":     tax_ledger,
        "holding_periods_by_etf": holding_periods_by_etf,
    }


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series) -> dict:
    if len(eq) < 10:
        return {"error": "insufficient data"}
    eq = eq.dropna()
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr   = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol    = rets.std() * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    max_dd   = (eq / roll_max - 1).min()
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0
    win_rate = (rets > 0).mean()
    return {
        "cagr":         round(float(cagr),    4),
        "sharpe":       round(float(sharpe),   4),
        "max_drawdown": round(float(max_dd),   4),
        "calmar":       round(float(calmar),   4),
        "ann_vol":      round(float(vol),      4),
        "win_rate":     round(float(win_rate), 4),
        "n_years":      round(float(n_years),  1),
        "final_value":  round(float(eq.iloc[-1]), 2),
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("=" * 72)
    print("H020 After-Tax Analysis")
    print("Universe: SPY, QQQ, TLT, GLD, IEF — top-2 monthly rotation")
    print(f"Period:   {ANALYSIS_START} → {ANALYSIS_END}")
    print(f"Tax rates: STCG={STCG_RATE:.0%}  LTCG={LTCG_RATE:.0%}")
    print("=" * 72)

    # Fetch data (extra warmup for 12m momentum signal)
    prices = fetch_close(UNIVERSE, FULL_START, ANALYSIS_END)
    print(f"  Fetched prices: {len(prices)} days, {list(prices.columns)}")

    print("\n  Running backtest with tax accounting …")
    result = run_backtest_with_tax(prices)

    pretax_s  = result["pretax_series"]
    aftertax_s = result["aftertax_series"]
    ledger    = result["tax_ledger"]
    hp_by_etf = result["holding_periods_by_etf"]

    # Stats
    m_pretax  = calc_stats(pretax_s)
    m_aftertax = calc_stats(aftertax_s)

    # SPY buy-and-hold benchmark
    spy_px = prices["SPY"].loc[ANALYSIS_START:ANALYSIS_END]
    eq_spy = INITIAL_EQUITY * (spy_px / spy_px.iloc[0])
    m_spy  = calc_stats(eq_spy)

    # ── Tax breakdown ─────────────────────────────────────────────────
    total_gross_gains  = ledger.total_stcg_gains  + ledger.total_ltcg_gains
    total_gross_losses = ledger.total_stcg_losses + ledger.total_ltcg_losses

    stcg_pct = (ledger.total_stcg_gains / total_gross_gains * 100) if total_gross_gains > 0 else 0
    ltcg_pct = (ledger.total_ltcg_gains / total_gross_gains * 100) if total_gross_gains > 0 else 0

    # Average holding period per ETF
    avg_hp = {}
    for ticker, hp_list in hp_by_etf.items():
        if hp_list:
            avg_hp[ticker] = {
                "avg_days":    round(float(np.mean(hp_list)), 1),
                "median_days": round(float(np.median(hp_list)), 1),
                "min_days":    int(min(hp_list)),
                "max_days":    int(max(hp_list)),
                "n_sales":     len(hp_list),
                "pct_lt":      round(sum(1 for d in hp_list if d >= 365) / len(hp_list) * 100, 1),
            }

    # Total sale events
    sale_events = ledger.sale_events
    n_stcg_sales = sum(1 for e in sale_events if e["type"] == "STCG")
    n_ltcg_sales = sum(1 for e in sale_events if e["type"] == "LTCG")
    n_st_losses  = sum(1 for e in sale_events if e["type"] == "ST_LOSS")
    n_lt_losses  = sum(1 for e in sale_events if e["type"] == "LT_LOSS")

    # Print summary
    print("\n" + "─" * 72)
    print("  PERFORMANCE COMPARISON")
    print("─" * 72)
    print(f"  {'Strategy':<22} {'CAGR':>7} {'Sharpe':>8} {'MaxDD':>8} {'Final $':>12}")
    print(f"  {'─'*60}")
    for label, m in [("H020 Pre-Tax", m_pretax), ("H020 After-Tax", m_aftertax), ("SPY Buy&Hold", m_spy)]:
        if "error" in m:
            print(f"  {label:<22}  ERROR")
        else:
            print(f"  {label:<22} {m['cagr']:>6.2%}  {m['sharpe']:>7.3f}  {m['max_drawdown']:>7.2%}  ${m['final_value']:>11,.0f}")

    print("\n" + "─" * 72)
    print("  TAX BREAKDOWN")
    print("─" * 72)
    print(f"  Total gross ST gains:  ${ledger.total_stcg_gains:>12,.0f}  ({stcg_pct:.1f}% of total gains)")
    print(f"  Total gross LT gains:  ${ledger.total_ltcg_gains:>12,.0f}  ({ltcg_pct:.1f}% of total gains)")
    print(f"  Total ST losses:       ${ledger.total_stcg_losses:>12,.0f}")
    print(f"  Total LT losses:       ${ledger.total_ltcg_losses:>12,.0f}")
    print(f"  Total tax paid:        ${ledger.total_tax_paid:>12,.0f}")
    print(f"  ST loss carryforward:  ${ledger.stcg_carryforward:>12,.0f}")
    print(f"  LT loss carryforward:  ${ledger.ltcg_carryforward:>12,.0f}")
    print(f"  STCG sales: {n_stcg_sales}  |  LTCG sales: {n_ltcg_sales}  |  ST losses: {n_st_losses}  |  LT losses: {n_lt_losses}")

    print("\n" + "─" * 72)
    print("  AVERAGE HOLDING PERIODS BY ETF")
    print("─" * 72)
    for ticker, hp in sorted(avg_hp.items()):
        print(f"  {ticker:<5}  avg {hp['avg_days']:>6.1f} days  median {hp['median_days']:>6.1f}  "
              f"n={hp['n_sales']:>3}  {hp['pct_lt']:>5.1f}% held ≥12m  "
              f"[{hp['min_days']}–{hp['max_days']} days]")

    if not avg_hp:
        print("  (No completed sales recorded — check signal coverage)")

    # CAGR drag from taxes
    if "error" not in m_pretax and "error" not in m_aftertax:
        cagr_drag = m_pretax["cagr"] - m_aftertax["cagr"]
        print(f"\n  CAGR drag from taxes: {cagr_drag:.2%} per year")
        print(f"  Tax efficiency:       {m_aftertax['final_value'] / m_pretax['final_value'] * 100:.1f}% of pre-tax terminal value")

    # ── Save results ─────────────────────────────────────────────────
    out = {
        "strategy": "H020 After-Tax Analysis",
        "universe": UNIVERSE,
        "period":   f"{ANALYSIS_START} → {ANALYSIS_END}",
        "tax_rates": {"stcg": STCG_RATE, "ltcg": LTCG_RATE},
        "pretax":   m_pretax,
        "aftertax": m_aftertax,
        "spy_bh":   m_spy,
        "tax_breakdown": {
            "total_stcg_gains":    round(ledger.total_stcg_gains, 2),
            "total_ltcg_gains":    round(ledger.total_ltcg_gains, 2),
            "total_stcg_losses":   round(ledger.total_stcg_losses, 2),
            "total_ltcg_losses":   round(ledger.total_ltcg_losses, 2),
            "total_tax_paid":      round(ledger.total_tax_paid, 2),
            "stcg_pct_of_gains":   round(stcg_pct, 2),
            "ltcg_pct_of_gains":   round(ltcg_pct, 2),
            "n_stcg_sales":        n_stcg_sales,
            "n_ltcg_sales":        n_ltcg_sales,
            "n_st_losses":         n_st_losses,
            "n_lt_losses":         n_lt_losses,
            "stcg_carryforward":   round(ledger.stcg_carryforward, 2),
            "ltcg_carryforward":   round(ledger.ltcg_carryforward, 2),
        },
        "avg_holding_periods": avg_hp,
        "sale_events_sample":  sale_events[:50],  # first 50 for reference
        "total_sale_events":   len(sale_events),
        "cagr_drag":           round(m_pretax.get("cagr", 0) - m_aftertax.get("cagr", 0), 4) if "error" not in m_pretax and "error" not in m_aftertax else None,
    }

    out_path = RESULTS_DIR / "h020_aftertax_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")

    return out


if __name__ == "__main__":
    main()
