"""
H022 — Tax-Efficient Variant of H020
--------------------------------------
Universe : SPY, QQQ, TLT, GLD, IEF
Signal   : top-2 by (12m momentum rank + inverse 6m vol rank), 50/50 each
Rebalance: monthly (last trading day of month)
Period   : 2008-01-01 → 2026-04-25

Minimum-hold rule (H022 modification):
  After buying a position, do NOT sell it unless:
    (a) It has been held >= 12 months (LTCG threshold), OR
    (b) Its combined score drops to LAST PLACE (rank 5) — "forced exit"
  If signal says replace a position but it hasn't hit 12m AND isn't rank 5,
  hold it anyway until one of those conditions is met.

After-tax model: identical to H020
  - STCG rate: 37%  (held < 12 months)
  - LTCG rate: 20%  (held >= 12 months)
  - Losses carry forward by type (ST / LT)
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

INITIAL_EQUITY   = 100_000.0
CACHE_DIR        = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR      = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

FULL_START       = "2007-01-01"   # need 12m warmup before 2008-01-01
ANALYSIS_START   = "2008-01-01"
ANALYSIS_END     = "2026-04-25"

STCG_RATE        = 0.37
LTCG_RATE        = 0.20

UNIVERSE         = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
TOP_N            = 2
N_ASSETS         = len(UNIVERSE)    # 5 — rank 5 = last place


# ─────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────

def _cache_path(tickers, start, end):
    import hashlib
    key = "_".join(sorted(tickers)) + f"_close_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h022_{h}.parquet"


def fetch_close(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    cp = _cache_path(tickers, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} from {start} to {end} …")
    raw    = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────
# Signal computation
# ─────────────────────────────────────────────

def compute_monthly_signals(prices: pd.DataFrame, assets: list[str]) -> list[dict]:
    """
    Returns list of dicts with keys: date, top (list of top-2 tickers),
    scores (combined rank dict), ranks (dict ticker -> rank 1..5, higher = worse).
    """
    px           = prices[assets].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1

    records = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N:
            continue
        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        # rank: 1 = worst combined score, N = best. We want descending rank for "worst".
        score_rank = combined.rank(ascending=True)  # 1=worst, 5=best
        top        = list(combined.nlargest(TOP_N).index)
        records.append({
            "date":       month_end,
            "top":        top,
            "scores":     combined.to_dict(),
            "score_rank": score_rank.to_dict(),  # lower number = worse
        })
    return records


# ─────────────────────────────────────────────
# Lot + Tax ledger
# ─────────────────────────────────────────────

@dataclass
class Lot:
    ticker:              str
    purchase_date:       pd.Timestamp
    cost_basis_per_share: float
    shares:              float


@dataclass
class TaxLedger:
    stcg_carryforward:  float = 0.0
    ltcg_carryforward:  float = 0.0
    total_stcg_gains:   float = 0.0
    total_ltcg_gains:   float = 0.0
    total_stcg_losses:  float = 0.0
    total_ltcg_losses:  float = 0.0
    total_tax_paid:     float = 0.0
    sale_events:        list  = field(default_factory=list)


def realize_lots(
    lots: list[Lot],
    price_now: float,
    sale_date: pd.Timestamp,
    ledger: TaxLedger,
    hp_by_etf: dict,
) -> float:
    """Sell all lots for a ticker at price_now; record tax; return taxes owed."""
    taxes_owed = 0.0
    for lot in lots:
        proceeds   = lot.shares * price_now
        cost       = lot.shares * lot.cost_basis_per_share
        gain       = proceeds - cost
        days_held  = (sale_date - lot.purchase_date).days
        hp_by_etf[lot.ticker].append(days_held)

        if days_held >= 365:
            if gain >= 0:
                ledger.total_ltcg_gains += gain
                if ledger.ltcg_carryforward < 0:
                    offset   = min(gain, -ledger.ltcg_carryforward)
                    taxable  = gain - offset
                    ledger.ltcg_carryforward += offset
                else:
                    taxable = gain
                tax_due     = taxable * LTCG_RATE
                taxes_owed += tax_due
            else:
                ledger.total_ltcg_losses    += abs(gain)
                ledger.ltcg_carryforward    += gain
            ledger.sale_events.append({
                "date":      str(sale_date.date()),
                "ticker":    lot.ticker,
                "days_held": days_held,
                "gain":      round(gain, 2),
                "type":      "LTCG" if gain >= 0 else "LT_LOSS",
            })
        else:
            if gain >= 0:
                ledger.total_stcg_gains += gain
                if ledger.stcg_carryforward < 0:
                    offset   = min(gain, -ledger.stcg_carryforward)
                    taxable  = gain - offset
                    ledger.stcg_carryforward += offset
                else:
                    taxable = gain
                tax_due     = taxable * STCG_RATE
                taxes_owed += tax_due
            else:
                ledger.total_stcg_losses    += abs(gain)
                ledger.stcg_carryforward    += gain
            ledger.sale_events.append({
                "date":      str(sale_date.date()),
                "ticker":    lot.ticker,
                "days_held": days_held,
                "gain":      round(gain, 2),
                "type":      "STCG" if gain >= 0 else "ST_LOSS",
            })
    return taxes_owed


# ─────────────────────────────────────────────
# H022 minimum-hold rule helper
# ─────────────────────────────────────────────

def should_sell(
    ticker: str,
    purchase_date: pd.Timestamp,
    rebalance_date: pd.Timestamp,
    score_rank: dict,   # {ticker: rank}, 1=worst, N=best
) -> bool:
    """
    Return True if the position qualifies to be sold under H022 rules:
      - held >= 365 days (LTCG threshold), OR
      - ticker's score rank == 1 (last place / rank 5 among 5 assets)
    """
    days_held = (rebalance_date - purchase_date).days
    if days_held >= 365:
        return True
    # Force exit if it's the worst-ranked asset in the universe
    rank = score_rank.get(ticker, N_ASSETS)  # default worst if missing
    if rank == 1:   # rank 1 = worst (ascending rank)
        return True
    return False


# ─────────────────────────────────────────────
# Main backtest engine
# ─────────────────────────────────────────────

def run_backtest(prices: pd.DataFrame) -> dict:
    """
    Runs H022 (pre-tax + after-tax) from ANALYSIS_START to ANALYSIS_END.
    """
    assets  = [a for a in UNIVERSE if a in prices.columns]
    signals = compute_monthly_signals(prices, assets)
    print(f"  Computed {len(signals)} monthly signal observations")

    # Filter to analysis window
    signals = [s for s in signals if str(s["date"])[:10] >= ANALYSIS_START]

    px           = prices[assets].loc[ANALYSIS_START:ANALYSIS_END].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    signal_dates = {s["date"]: s for s in signals}

    valid_months = sorted(
        d for d in signal_dates
        if d >= pd.Timestamp(ANALYSIS_START) and d <= pd.Timestamp(ANALYSIS_END)
    )
    print(f"  Analysis months: {len(valid_months)}, "
          f"{valid_months[0].date()} → {valid_months[-1].date()}")

    # ── State ──────────────────────────────────────────────────────────
    # Pre-tax
    pretax_equity = INITIAL_EQUITY
    pretax_curve  = [(pd.Timestamp(ANALYSIS_START), INITIAL_EQUITY)]
    # Track: what 2 slots currently hold and since when (for pre-tax hold rule)
    pretax_holdings: dict[str, pd.Timestamp] = {}   # ticker -> purchase_date

    # After-tax
    aftertax_equity = INITIAL_EQUITY
    aftertax_curve  = [(pd.Timestamp(ANALYSIS_START), INITIAL_EQUITY)]
    aftertax_lots:  dict[str, list[Lot]] = defaultdict(list)  # ticker -> lots
    tax_ledger      = TaxLedger()
    hp_by_etf: dict[str, list[int]] = defaultdict(list)

    # Hold-rule stats
    hold_overrides   = 0   # times a sell was deferred due to <12m + not rank-5
    forced_exits     = 0   # times rank-5 triggered early sale

    prev_month_end = None

    for idx, month_end in enumerate(valid_months):
        sig        = signal_dates[month_end]
        desired    = sig["top"]             # list of top-2
        score_rank = sig["score_rank"]      # {ticker: rank 1..5}

        if prev_month_end is None:
            # Initialise both portfolios at the first signal date
            for ticker in desired:
                if ticker in px.columns:
                    price      = float(px.loc[:month_end, ticker].iloc[-1])
                    allocation = INITIAL_EQUITY * 0.50

                    # Pre-tax
                    pretax_holdings[ticker] = month_end

                    # After-tax
                    shares = allocation / price
                    aftertax_lots[ticker].append(Lot(
                        ticker=ticker,
                        purchase_date=month_end,
                        cost_basis_per_share=price,
                        shares=shares,
                    ))
            prev_month_end = month_end
            continue

        # ── Period price slice ─────────────────────────────────────────
        period_px = px.loc[prev_month_end:month_end]
        if len(period_px) < 2:
            prev_month_end = month_end
            continue

        # ── Pre-tax: daily equity curve for this period ─────────────────
        current_tickers_pretax = list(pretax_holdings.keys())
        for day_idx in range(1, len(period_px)):
            day     = period_px.index[day_idx]
            day_ret = 0.0
            for ticker in current_tickers_pretax:
                if ticker in period_px.columns:
                    p0 = float(period_px[ticker].iloc[day_idx - 1])
                    p1 = float(period_px[ticker].iloc[day_idx])
                    if p0 > 0:
                        day_ret += (p1 / p0 - 1) / TOP_N
            pretax_curve.append((day, pretax_curve[-1][1] * (1 + day_ret)))

        pretax_equity = pretax_curve[-1][1]

        # ── After-tax: daily equity curve ──────────────────────────────
        current_tickers_at = list(aftertax_lots.keys())
        for day_idx in range(1, len(period_px)):
            day     = period_px.index[day_idx]
            day_ret = 0.0
            for ticker in current_tickers_at:
                if ticker in period_px.columns:
                    p0 = float(period_px[ticker].iloc[day_idx - 1])
                    p1 = float(period_px[ticker].iloc[day_idx])
                    if p0 > 0:
                        day_ret += (p1 / p0 - 1) / TOP_N
            aftertax_curve.append((day, aftertax_curve[-1][1] * (1 + day_ret)))

        # ── Apply H022 minimum-hold rule at month-end ───────────────────
        #
        # For each CURRENTLY held ticker:
        #   - If signal still wants it (in desired top-2): keep
        #   - If signal dropped it:
        #       check should_sell(ticker, purchase_date, month_end, score_rank)
        #       True  → sell (LTCG or forced exit)
        #       False → hold (defer, do not buy replacement this month)
        #
        # After deciding what to sell, buy replacements for freed slots.

        # --- Pre-tax decision ---
        new_pretax_holdings: dict[str, pd.Timestamp] = {}
        freed_slots_pretax = 0

        for ticker, buy_date in pretax_holdings.items():
            if ticker in desired:
                # Still desired — keep
                new_pretax_holdings[ticker] = buy_date
            else:
                # Not in desired top-2 anymore
                days_held = (month_end - buy_date).days
                rank      = score_rank.get(ticker, 1)
                if days_held >= 365:
                    # LTCG exit — sell
                    freed_slots_pretax += 1
                elif rank == 1:
                    # Forced exit (rank 5 / last place)
                    freed_slots_pretax += 1
                    forced_exits += 1
                else:
                    # Hold override — keep despite not being in desired
                    new_pretax_holdings[ticker] = buy_date
                    hold_overrides += 1

        # Buy replacements for freed slots + any desired assets not already held
        desired_not_held = [t for t in desired if t not in new_pretax_holdings]
        for i, ticker in enumerate(desired_not_held[:freed_slots_pretax]):
            new_pretax_holdings[ticker] = month_end

        pretax_holdings = new_pretax_holdings

        # --- After-tax decision (same logic, but with lot tracking) ---
        taxes_owed         = 0.0
        new_aftertax_lots: dict[str, list[Lot]] = defaultdict(list)
        freed_slots_at     = 0

        for ticker, lots in aftertax_lots.items():
            if ticker in desired:
                new_aftertax_lots[ticker] = lots
            else:
                # Earliest purchase date for this position
                earliest_buy = min(lot.purchase_date for lot in lots)
                days_held    = (month_end - earliest_buy).days
                rank         = score_rank.get(ticker, 1)
                price_now    = float(period_px[ticker].iloc[-1]) if ticker in period_px.columns else 0.0

                if days_held >= 365:
                    # LTCG exit
                    taxes_owed    += realize_lots(lots, price_now, month_end, tax_ledger, hp_by_etf)
                    freed_slots_at += 1
                elif rank == 1:
                    # Forced exit (rank 5)
                    taxes_owed    += realize_lots(lots, price_now, month_end, tax_ledger, hp_by_etf)
                    freed_slots_at += 1
                else:
                    # Hold override
                    new_aftertax_lots[ticker] = lots

        # Deduct taxes from after-tax equity
        tax_ledger.total_tax_paid += taxes_owed
        at_val = aftertax_curve[-1][1] - taxes_owed
        if at_val <= 0:
            at_val = aftertax_curve[-1][1]
        aftertax_curve[-1] = (aftertax_curve[-1][0], at_val)
        aftertax_equity    = at_val

        # Buy into freed slots
        desired_not_held_at  = [t for t in desired if t not in new_aftertax_lots]
        for ticker in desired_not_held_at[:freed_slots_at]:
            price_now = float(period_px[ticker].iloc[-1]) if ticker in period_px.columns else 0.0
            if price_now > 0:
                # Allocate 50% of current equity
                allocation = aftertax_equity * 0.50
                shares     = allocation / price_now
                new_aftertax_lots[ticker].append(Lot(
                    ticker=ticker,
                    purchase_date=month_end,
                    cost_basis_per_share=price_now,
                    shares=shares,
                ))

        # Weight rebalance for held tickers (keep 50/50 target)
        # Simple: don't rebalance held positions mid-hold (avoids extra tax events)
        aftertax_lots = new_aftertax_lots

        prev_month_end = month_end

    # ── Build Series ──────────────────────────────────────────────────
    def to_series(curve):
        idx  = pd.DatetimeIndex([d for d, _ in curve])
        vals = [v for _, v in curve]
        s    = pd.Series(vals, index=idx)
        return s[~s.index.duplicated(keep='last')]

    pretax_series  = to_series(pretax_curve)
    aftertax_series = to_series(aftertax_curve)

    return {
        "pretax_series":    pretax_series,
        "aftertax_series":  aftertax_series,
        "tax_ledger":       tax_ledger,
        "hp_by_etf":        hp_by_etf,
        "hold_overrides":   hold_overrides,
        "forced_exits":     forced_exits,
    }


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series) -> dict:
    if len(eq) < 10:
        return {"error": "insufficient data"}
    eq   = eq.dropna()
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr    = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol     = rets.std() * np.sqrt(252)
    sharpe  = cagr / vol if vol > 0 else 0
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
    print("H022 — Tax-Efficient H020 (Minimum-Hold Rule)")
    print("Universe: SPY, QQQ, TLT, GLD, IEF — top-2 monthly rotation")
    print(f"Period  : {ANALYSIS_START} → {ANALYSIS_END}")
    print(f"Tax rates: STCG={STCG_RATE:.0%}  LTCG={LTCG_RATE:.0%}")
    print("Minimum hold: sell only if held >= 12m OR score rank = 5 (last)")
    print("=" * 72)

    prices = fetch_close(UNIVERSE, FULL_START, ANALYSIS_END)
    print(f"  Fetched: {len(prices)} trading days, {list(prices.columns)}")

    print("\n  Running H022 backtest …")
    result = run_backtest(prices)

    pretax_s   = result["pretax_series"]
    aftertax_s = result["aftertax_series"]
    ledger     = result["tax_ledger"]
    hp_by_etf  = result["hp_by_etf"]
    hold_overrides = result["hold_overrides"]
    forced_exits   = result["forced_exits"]

    m_pretax   = calc_stats(pretax_s)
    m_aftertax = calc_stats(aftertax_s)

    # SPY benchmark
    spy_px = prices["SPY"].loc[ANALYSIS_START:ANALYSIS_END]
    eq_spy = INITIAL_EQUITY * (spy_px / spy_px.iloc[0])
    m_spy  = calc_stats(eq_spy)

    # ── Tax breakdown ──────────────────────────────────────────────────
    total_gains    = ledger.total_stcg_gains + ledger.total_ltcg_gains
    stcg_pct       = (ledger.total_stcg_gains / total_gains * 100) if total_gains > 0 else 0
    ltcg_pct       = (ledger.total_ltcg_gains / total_gains * 100) if total_gains > 0 else 0
    sale_events    = ledger.sale_events
    n_stcg_sales   = sum(1 for e in sale_events if e["type"] == "STCG")
    n_ltcg_sales   = sum(1 for e in sale_events if e["type"] == "LTCG")
    n_st_losses    = sum(1 for e in sale_events if e["type"] == "ST_LOSS")
    n_lt_losses    = sum(1 for e in sale_events if e["type"] == "LT_LOSS")

    # Average holding periods by ETF
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

    # ── H020 baseline (loaded from saved results) ─────────────────────
    h020_path = RESULTS_DIR / "h020_aftertax_results.json"
    h020 = {}
    if h020_path.exists():
        h020 = json.loads(h020_path.read_text())

    h020_pretax   = h020.get("pretax",   {})
    h020_aftertax = h020.get("aftertax", {})
    h020_stcg_pct = h020.get("tax_breakdown", {}).get("stcg_pct_of_gains", 89.75)

    # ── Print results ──────────────────────────────────────────────────
    print("\n" + "─" * 72)
    print("  PERFORMANCE COMPARISON")
    print("─" * 72)
    header = f"  {'Strategy':<26} {'CAGR':>7} {'Sharpe':>8} {'MaxDD':>8} {'Final $':>12}"
    print(header)
    print(f"  {'─' * 64}")

    rows = [
        ("H020 Pre-Tax",    h020_pretax),
        ("H020 After-Tax",  h020_aftertax),
        ("H022 Pre-Tax",    m_pretax),
        ("H022 After-Tax",  m_aftertax),
        ("SPY Buy&Hold",    m_spy),
    ]
    for label, m in rows:
        if "error" in m:
            print(f"  {label:<26}  ERROR")
        else:
            fv = m.get("final_value", 0)
            print(f"  {label:<26} {m['cagr']:>6.2%}  {m['sharpe']:>7.3f}  "
                  f"{m['max_drawdown']:>7.2%}  ${fv:>11,.0f}")

    print("\n" + "─" * 72)
    print("  TAX BREAKDOWN — H022")
    print("─" * 72)
    print(f"  Total gross ST gains:  ${ledger.total_stcg_gains:>12,.0f}  ({stcg_pct:.1f}% of total gains)")
    print(f"  Total gross LT gains:  ${ledger.total_ltcg_gains:>12,.0f}  ({ltcg_pct:.1f}% of total gains)")
    print(f"  Total ST losses:       ${ledger.total_stcg_losses:>12,.0f}")
    print(f"  Total LT losses:       ${ledger.total_ltcg_losses:>12,.0f}")
    print(f"  Total tax paid:        ${ledger.total_tax_paid:>12,.0f}")
    print(f"  STCG sales: {n_stcg_sales}  |  LTCG sales: {n_ltcg_sales}  |  ST losses: {n_st_losses}  |  LT losses: {n_lt_losses}")
    print(f"  H020 STCG % of gains:  {h020_stcg_pct:.1f}%")
    print(f"  H022 STCG % of gains:  {stcg_pct:.1f}%")
    print(f"  Hold overrides (deferred sales): {hold_overrides}")
    print(f"  Forced exits (rank-5):           {forced_exits}")

    print("\n" + "─" * 72)
    print("  AVERAGE HOLDING PERIODS BY ETF — H022")
    print("─" * 72)
    for ticker, hp in sorted(avg_hp.items()):
        print(f"  {ticker:<5}  avg {hp['avg_days']:>6.1f} days  "
              f"median {hp['median_days']:>6.1f}  n={hp['n_sales']:>3}  "
              f"{hp['pct_lt']:>5.1f}% held ≥12m  [{hp['min_days']}–{hp['max_days']} days]")

    if "error" not in m_pretax and "error" not in m_aftertax:
        print(f"\n  H022 CAGR drag from taxes: {m_pretax['cagr'] - m_aftertax['cagr']:.2%} per year")
        print(f"  H022 Tax efficiency:       "
              f"{m_aftertax['final_value'] / m_pretax['final_value'] * 100:.1f}% of pre-tax terminal value")

    if "error" not in m_aftertax and "error" not in h020_aftertax:
        delta_cagr = m_aftertax["cagr"] - h020_aftertax.get("cagr", 0)
        print(f"\n  After-tax improvement over H020: {delta_cagr:+.2%} CAGR")

    # ── Save ────────────────────────────────────────────────────────────
    out = {
        "strategy":   "H022 — Tax-Efficient H020 (Minimum-Hold Rule)",
        "universe":   UNIVERSE,
        "period":     f"{ANALYSIS_START} → {ANALYSIS_END}",
        "tax_rates":  {"stcg": STCG_RATE, "ltcg": LTCG_RATE},
        "pretax":     m_pretax,
        "aftertax":   m_aftertax,
        "spy_bh":     m_spy,
        "comparison_table": {
            "h020_pretax":   h020_pretax,
            "h020_aftertax": h020_aftertax,
            "h022_pretax":   m_pretax,
            "h022_aftertax": m_aftertax,
        },
        "tax_breakdown": {
            "total_stcg_gains":   round(ledger.total_stcg_gains, 2),
            "total_ltcg_gains":   round(ledger.total_ltcg_gains, 2),
            "total_stcg_losses":  round(ledger.total_stcg_losses, 2),
            "total_ltcg_losses":  round(ledger.total_ltcg_losses, 2),
            "total_tax_paid":     round(ledger.total_tax_paid, 2),
            "stcg_pct_of_gains":  round(stcg_pct, 2),
            "ltcg_pct_of_gains":  round(ltcg_pct, 2),
            "n_stcg_sales":       n_stcg_sales,
            "n_ltcg_sales":       n_ltcg_sales,
            "n_st_losses":        n_st_losses,
            "n_lt_losses":        n_lt_losses,
            "stcg_carryforward":  round(ledger.stcg_carryforward, 2),
            "ltcg_carryforward":  round(ledger.ltcg_carryforward, 2),
        },
        "hold_rule_stats": {
            "hold_overrides":  hold_overrides,
            "forced_exits":    forced_exits,
            "h020_stcg_pct":   h020_stcg_pct,
            "h022_stcg_pct":   round(stcg_pct, 2),
        },
        "avg_holding_periods": avg_hp,
        "sale_events_sample":  sale_events[:50],
        "total_sale_events":   len(sale_events),
        "cagr_drag":           round(
            m_pretax.get("cagr", 0) - m_aftertax.get("cagr", 0), 4
        ) if "error" not in m_pretax and "error" not in m_aftertax else None,
    }

    out_path = RESULTS_DIR / "h022_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return out


if __name__ == "__main__":
    main()
