"""
H007: Iron Condor on SPY — Black-Scholes simulation
- Entry: first trading day of each month, 45-DTE, 16-delta shorts, $5 wings
- Exit:  50% profit | "200% loss" (close debit = 2x credit) | 21 DTE
- Pricing: BSM with VIX as IV (flat term structure)
- Slippage: 2% of BSM mid per leg at entry and exit (4 legs each)
  SPY 45-DTE options are very liquid; $0.03-$0.10 spread on $1-3 options ≈ 2-3%
- Sizing: 5% max risk per condor (wing width - initial net credit)

tastytrade "200% loss" rule:
  Open credit: $1.00 net received
  Close when debit-to-close ≥ $2.00  →  net P&L = -$1.00 = -100% of credit
  Code: cost_to_close >= 2.0 * entry_credit
        i.e. pnl_mark <= -1.0 * entry_credit (NOT -2.0)
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")


# ── Black-Scholes ────────────────────────────────────────────────────────────

def bsm(S, K, T, r, sigma, right):
    if T <= 1e-6 or sigma <= 1e-6:
        return max(S - K, 0) if right == 'call' else max(K - S, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if right == 'call':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def strike_for_delta(S, T, r, sigma, target_delta, right):
    if right == 'call':
        d1 = norm.ppf(target_delta)
    else:
        d1 = norm.ppf(1.0 - target_delta)
    lnSK = d1 * sigma * np.sqrt(T) - (r + 0.5 * sigma**2) * T
    return S * np.exp(-lnSK)


def round5(K):
    return round(K / 5.0) * 5.0


# Slippage: 2% per leg (floor $0.01); SPY options at 45-DTE are very liquid
def slip(price):
    return max(0.01, price * 0.02)


# ── Strategy simulation ───────────────────────────────────────────────────────

def simulate_iron_condor(prices, vix, rfr, target_delta=0.16, wing=5.0,
                          max_risk_pct=0.05, verbose=False):
    results = []
    portfolio = 100_000.0
    active = None
    last_entry_month = -1

    for i in range(len(prices)):
        date = prices.index[i]
        S    = float(prices.iloc[i])
        iv   = float(vix.iloc[i]) / 100.0
        r    = float(rfr.iloc[i])

        # ── Exit check ─────────────────────────────────────────────────────
        if active is not None:
            exp = active['expiry']
            d   = date.date() if hasattr(date, 'date') else date
            dte = (exp - d).days

            if dte <= 0:
                p  = (-max(S - active['sc_k'], 0)
                      + max(S - active['lc_k'], 0)
                      - max(active['sp_k'] - S, 0)
                      + max(active['lp_k'] - S, 0)) * 100 * active['qty']
                pnl = active['entry_credit'] + p
                portfolio += pnl
                results.append(dict(date=date, reason='expired', pnl=pnl,
                                    entry_credit=active['entry_credit'], portfolio=portfolio))
                if verbose:
                    print(f"  EXIT expired          pnl={pnl:+7.0f}  port={portfolio:,.0f}")
                active = None
                continue

            T = dte / 365.0
            sc = bsm(S, active['sc_k'], T, r, iv, 'call')
            lc = bsm(S, active['lc_k'], T, r, iv, 'call')
            sp = bsm(S, active['sp_k'], T, r, iv, 'put')
            lp = bsm(S, active['lp_k'], T, r, iv, 'put')

            cost_to_close = (sc - lc + sp - lp) * 100 * active['qty']
            pnl_mark = active['entry_credit'] - cost_to_close

            reason = None
            if active['entry_credit'] > 0:
                if pnl_mark >= 0.50 * active['entry_credit']:
                    reason = '50pct_profit'
                elif cost_to_close >= 2.0 * active['entry_credit']:
                    # "200% loss": closing debit = 2x opening credit
                    reason = '2x_loss'
            if dte <= 21 and reason is None:
                reason = '21dte'

            if reason:
                exit_slip = (slip(sc) + slip(lc) + slip(sp) + slip(lp)) * 100 * active['qty']
                pnl = pnl_mark - exit_slip
                portfolio += pnl
                results.append(dict(date=date, reason=reason, pnl=pnl,
                                    entry_credit=active['entry_credit'], portfolio=portfolio))
                if verbose:
                    print(f"  EXIT {reason:15s} pnl={pnl:+7.0f}  port={portfolio:,.0f}")
                active = None

        # ── Entry check ────────────────────────────────────────────────────
        if active is None:
            month = date.month
            if month == last_entry_month:
                continue

            T45 = 45 / 365.0

            sc_k_f = strike_for_delta(S, T45, r, iv, target_delta, 'call')
            sp_k_f = strike_for_delta(S, T45, r, iv, target_delta, 'put')
            sc_k = round5(sc_k_f)
            sp_k = round5(sp_k_f)
            lc_k = sc_k + wing
            lp_k = sp_k - wing

            if sc_k <= S or sp_k >= S:
                continue

            sc_p = bsm(S, sc_k, T45, r, iv, 'call')
            lc_p = bsm(S, lc_k, T45, r, iv, 'call')
            sp_p = bsm(S, sp_k, T45, r, iv, 'put')
            lp_p = bsm(S, lp_k, T45, r, iv, 'put')

            gross_credit  = sc_p - lc_p + sp_p - lp_p
            entry_slip    = slip(sc_p) + slip(lc_p) + slip(sp_p) + slip(lp_p)
            net_credit    = gross_credit - entry_slip

            if net_credit <= 0.02:
                continue

            max_risk = (wing - net_credit) * 100
            if max_risk <= 0:
                continue

            qty = max(1, int(portfolio * max_risk_pct / max_risk))

            expiry = date.date() + pd.Timedelta(days=45)
            while expiry.weekday() != 4:
                expiry += pd.Timedelta(days=1)

            entry_credit = net_credit * 100 * qty
            active = dict(
                sc_k=sc_k, lc_k=lc_k, sp_k=sp_k, lp_k=lp_k,
                qty=qty, entry_credit=entry_credit, expiry=expiry,
            )
            last_entry_month = month

            if verbose:
                print(f"  ENTER {date.date()} S={S:.1f} iv={iv:.3f} "
                      f"SC={sc_k} LC={lc_k} SP={sp_k} LP={lp_k} "
                      f"qty={qty} credit=${entry_credit:.0f}")

    if active:
        residual = active['entry_credit'] * 0.5
        portfolio += residual
        results.append(dict(date=prices.index[-1], reason='end_of_data',
                             pnl=residual, entry_credit=active['entry_credit'],
                             portfolio=portfolio))

    return pd.DataFrame(results), portfolio


# ── Performance metrics ────────────────────────────────────────────────────────

def stats(trades, portfolio_final, start, end, initial=100_000.0):
    if trades.empty:
        return {}
    n_years = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    total_ret = (portfolio_final - initial) / initial
    cagr = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else np.nan

    port_vals = trades['portfolio'].values
    running_max = np.maximum.accumulate(np.maximum(port_vals, initial))
    dd = (port_vals - running_max) / running_max
    max_dd = dd.min()

    calmar = cagr / abs(max_dd) if max_dd != 0 else np.nan
    won = (trades['pnl'] > 0).sum()
    win_rate = won / len(trades)
    avg_win  = trades.loc[trades['pnl'] > 0, 'pnl'].mean() if won > 0 else 0
    avg_loss = trades.loc[trades['pnl'] <= 0, 'pnl'].mean() if (trades['pnl'] <= 0).sum() > 0 else 0

    monthly = trades.set_index('date')['pnl'].resample('ME').sum()
    monthly_ret = monthly / initial
    sharpe = monthly_ret.mean() / monthly_ret.std() * np.sqrt(12) if monthly_ret.std() > 0 else np.nan

    return dict(cagr=cagr, total_ret=total_ret, max_dd=max_dd, calmar=calmar,
                sharpe=sharpe, win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
                n_trades=len(trades), final=portfolio_final)


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    START = '2007-01-01'
    END   = '2026-04-01'

    print("Downloading SPY + VIX + ^IRX...")
    spy = yf.download("SPY",  start=START, end=END, auto_adjust=True, progress=False)['Close'].squeeze()
    vix = yf.download("^VIX", start=START, end=END, auto_adjust=True, progress=False)['Close'].squeeze()
    irx = yf.download("^IRX", start=START, end=END, auto_adjust=True, progress=False)['Close'].squeeze() / 100.0

    idx = spy.index.intersection(vix.index)
    spy = spy.reindex(idx).ffill()
    vix = vix.reindex(idx).ffill().fillna(20)
    irx = irx.reindex(idx).ffill().fillna(0.02)

    print(f"Data: {idx[0].date()} → {idx[-1].date()}  ({len(idx)} trading days)")
    print()

    print("=" * 66)
    print("H007: Iron Condor — SPY  (2007-01-01 → 2026-04-01)")
    print("  Entry: monthly, 45-DTE, 16-delta shorts, $5 wings")
    print("  Exit:  50% profit | 200% loss (close debit = 2x credit) | 21 DTE")
    print("  Sizing: 5% max risk/condor | Slip: 2% per leg")
    print("=" * 66)

    trades, final = simulate_iron_condor(spy, vix, irx, verbose=True)
    s = stats(trades, final, START, END)

    print()
    print(f"  Trades:          {s['n_trades']}")
    print(f"  Win rate:        {s['win_rate']:.1%}")
    print(f"  Avg win:         ${s['avg_win']:,.0f}")
    print(f"  Avg loss:        ${s['avg_loss']:,.0f}")
    print(f"  Final portfolio: ${s['final']:,.0f}")
    print(f"  Total return:    {s['total_ret']:.1%}")
    print(f"  CAGR:            {s['cagr']:.1%}")
    print(f"  Max drawdown:    {s['max_dd']:.1%}")
    print(f"  Calmar:          {s['calmar']:.3f}")
    print(f"  Sharpe:          {s['sharpe']:.3f}")
    print()

    spy_ret  = spy.iloc[-1] / spy.iloc[0] - 1
    spy_yrs  = (idx[-1] - idx[0]).days / 365.25
    spy_cagr = (1 + spy_ret) ** (1 / spy_yrs) - 1
    spy_dd   = (spy / spy.cummax() - 1).min()
    print(f"  SPY B&H:  CAGR {spy_cagr:.1%}  MaxDD {spy_dd:.1%}  Calmar {spy_cagr/abs(spy_dd):.3f}")
    print()

    print("-" * 66)
    print("OOS: 2020-01-01 → 2026-04-01")
    mask = spy.index >= '2020-01-01'
    t2, f2 = simulate_iron_condor(spy[mask], vix[mask], irx[mask])
    s2 = stats(t2, f2, '2020-01-01', '2026-04-01')
    if s2:
        print(f"  Trades {s2['n_trades']}  Win {s2['win_rate']:.0%}  "
              f"CAGR {s2['cagr']:.1%}  MaxDD {s2['max_dd']:.1%}  "
              f"Calmar {s2['calmar']:.3f}  Sharpe {s2['sharpe']:.3f}")
    print()

    print("-" * 66)
    print("Crisis periods:")
    for label, s_date, e_date in [
        ("2008-2009 GFC",  '2008-01-01', '2009-12-31'),
        ("2020 COVID",     '2020-01-01', '2020-12-31'),
        ("2022 Rates",     '2022-01-01', '2022-12-31'),
    ]:
        mask = (spy.index >= s_date) & (spy.index <= e_date)
        tc, fc = simulate_iron_condor(spy[mask], vix[mask], irx[mask])
        if not tc.empty:
            cr  = (fc - 100_000) / 100_000
            wr  = (tc['pnl'] > 0).mean()
            print(f"  {label:18s}  Return {cr:+.1%}  Win {wr:.0%}  Trades {len(tc)}")
        else:
            print(f"  {label:18s}  No trades")
    print()

    print("-" * 66)
    print(f"  {'Year':4}  {'Return':>8}  {'Win':>5}  {'Trades':>6}")
    for year in range(2007, 2027):
        s_y = f'{year}-01-01'
        e_y = f'{year+1}-01-01' if year < 2026 else '2026-04-01'
        mask = (spy.index >= s_y) & (spy.index < e_y)
        if mask.sum() < 10:
            continue
        ty, fy = simulate_iron_condor(spy[mask], vix[mask], irx[mask])
        if not ty.empty:
            ry = (fy - 100_000) / 100_000
            wy = (ty['pnl'] > 0).mean()
            print(f"  {year}  {ry:+8.1%}  {wy:5.0%}  {len(ty):6d}")
        else:
            print(f"  {year}  {'no trades':>8}")
