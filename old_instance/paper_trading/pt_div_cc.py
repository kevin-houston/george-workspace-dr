#!/usr/bin/env python3
"""
Dividend Strategy #2: Covered Calls Around Ex-Div Paper Trader
Signal: sell a 2% OTM covered call 10 trading days before each ex-dividend date.
Close at ex-date: collect premium if stock < strike, capped return if called away.
Universe: Dividend Aristocrats + Fortune 100 payers (~50 stocks)
Run daily at 4:35 PM CT after market close.
"""

import sys, json, math
from datetime import date, timedelta
from pathlib import Path

try:
    import yfinance as yf
    import numpy as np
    from scipy.stats import norm
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    'yfinance', 'pandas', 'numpy', 'scipy', '--break-system-packages', '-q'],
                   capture_output=True)
    import yfinance as yf
    import numpy as np
    from scipy.stats import norm

PORTFOLIO_FILE  = Path(__file__).parent / 'div_cc_portfolio.json'
VIRTUAL_CAPITAL = 5000.0
POSITION_SIZE   = 500.0    # per covered call position
MAX_POSITIONS   = 10
DAYS_BEFORE_EX  = 10       # sell call this many trading days before ex-date
OTM_PCT         = 0.02     # 2% OTM strike
RF              = 0.045    # risk-free rate

UNIVERSE = [
    'ABT','ADP','AFL','APD','AXP','BA','CAT','CL','CMCSA','COST',
    'CVX','DE','DIS','GD','GE','GS','HD','HON','IBM','ITW',
    'JNJ','JPM','KMB','KO','LIN','LMT','LOW','MCD','MDT','MMM',
    'MRK','MSFT','NKE','NOC','PEP','PG','RTX','SYY','T','TGT',
    'TROW','UNH','UNP','UPS','V','VZ','WMT','XOM','PFE','C',
]

def load() -> dict:
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {
        'strategy': 'Covered Calls around Ex-Div (10d before, 2% OTM)',
        'backtest_sharpe': 2.643,
        'virtual_capital': VIRTUAL_CAPITAL,
        'open_positions': {},  # key=ticker_exdate → position details
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None
    }

def save(data: dict):
    with open(PORTFOLIO_FILE, 'w') as f: json.dump(data, f, indent=2, default=str)

def bs_call(S, K, T, sigma, r=RF):
    if T <= 0 or sigma <= 0: return max(S - K, 0)
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return float(S * norm.cdf(d1) - K * np.exp(-r*T) * norm.cdf(d2))

def get_vol(ticker: str, window: int = 20) -> float:
    """Compute 20-day realized vol."""
    try:
        hist = yf.download(ticker, period='60d', auto_adjust=True, progress=False)
        if len(hist) < window + 2: return 0.20
        col = 'Close' if 'Close' in hist.columns else hist.columns[0]
        rets = hist[col].squeeze().pct_change().dropna()
        return float(rets.tail(window).std() * np.sqrt(252))
    except:
        return 0.20

def trading_days_until(target: date, from_date: date = None) -> int:
    """Count trading days from from_date to target."""
    d = from_date or date.today()
    count = 0
    while d < target:
        d += timedelta(days=1)
        if d.weekday() < 5: count += 1
    return count

def find_upcoming_ex_dates(ticker: str, lookahead_days: int = 15) -> list:
    """Find ex-dividend dates coming up within the next lookahead_days calendar days."""
    try:
        t = yf.Ticker(ticker)
        divs = t.dividends
        if divs is None or len(divs) == 0: return []
        divs.index = divs.index.tz_localize(None) if divs.index.tz else divs.index
        today = date.today()
        future = today + timedelta(days=lookahead_days)
        upcoming = []
        for dt, amt in divs.items():
            d = dt.date() if hasattr(dt, 'date') else dt
            if today <= d <= future:
                upcoming.append({'ex_date': d, 'amount': float(amt)})
        return upcoming
    except:
        return []

def run():
    data = load()
    today = date.today()
    if today.weekday() >= 5:
        print(f"Weekend, skipping ({today})")
        return

    print(f"\n=== Covered Calls around Ex-Div Paper Trader — {today} ===")

    # ── 1. Check exits: close positions where ex_date has arrived ──
    to_exit = [k for k, pos in data['open_positions'].items()
               if str(today) >= pos.get('ex_date', '9999-99-99')]
    for key in to_exit:
        pos = data['open_positions'].pop(key)
        ticker = pos['ticker']
        try:
            hist = yf.download(ticker, period='2d', auto_adjust=True, progress=False)
            if len(hist) == 0: raise ValueError
            col = 'Close' if 'Close' in hist.columns else hist.columns[0]
            exit_price = float(hist[col].iloc[-1].squeeze())
        except:
            exit_price = pos['entry_price']

        S0     = pos['entry_price']
        K      = pos['strike']
        prem   = pos['premium']
        shares = pos['shares']

        # Covered call: stock return capped at strike if called away
        if exit_price >= K:
            effective_exit = K
            called_away = True
        else:
            effective_exit = exit_price
            called_away = False

        stock_ret = (effective_exit - S0) / S0
        prem_ret  = prem / S0
        total_ret = stock_ret + prem_ret

        pnl = total_ret * shares * S0
        win = pnl > 0
        trade = {
            'ticker': ticker,
            'entry_date': pos['entry_date'],
            'exit_date': str(today),
            'ex_date': pos['ex_date'],
            'entry_price': S0,
            'exit_price': exit_price,
            'strike': K,
            'premium': prem,
            'shares': shares,
            'called_away': called_away,
            'return_pct': round(total_ret, 4),
            'pnl_usd': round(pnl, 2),
            'win': win
        }
        data['trades'].append(trade)
        data['stats']['n_trades'] += 1
        data['stats']['wins'] += int(win)
        data['stats']['total_pnl'] += pnl
        status = "CALLED" if called_away else "EXPIRED"
        print(f"  EXIT {ticker} [{status}]: ret={total_ret:+.1%} pnl=${pnl:+.2f}")

    # ── 2. Scan for new entry points: ex-dates in DAYS_BEFORE_EX trading days ──
    n_open = len(data['open_positions'])
    already_active = {pos['ticker'] + '_' + pos['ex_date']
                      for pos in data['open_positions'].values()}

    if n_open < MAX_POSITIONS:
        print(f"  Scanning for upcoming ex-dates (open={n_open}/{MAX_POSITIONS})...")
        # Lookahead window: calendar days covering DAYS_BEFORE_EX+5 trading days
        lookahead_calendar = DAYS_BEFORE_EX * 2  # generous calendar buffer

        for ticker in UNIVERSE:
            if n_open >= MAX_POSITIONS: break
            upcoming = find_upcoming_ex_dates(ticker, lookahead_days=lookahead_calendar)
            for event in upcoming:
                if n_open >= MAX_POSITIONS: break
                ex_date = event['ex_date']
                key = f"{ticker}_{ex_date}"
                if key in already_active: continue

                td_until = trading_days_until(ex_date, today)
                # Enter when exactly DAYS_BEFORE_EX trading days away
                if td_until != DAYS_BEFORE_EX: continue

                # Fetch current price and vol
                try:
                    hist = yf.download(ticker, period='2d', auto_adjust=True, progress=False)
                    if len(hist) == 0: continue
                    col = 'Close' if 'Close' in hist.columns else hist.columns[0]
                    S = float(hist[col].iloc[-1].squeeze())
                except:
                    continue

                sigma = get_vol(ticker)
                K = S * (1 + OTM_PCT)
                T = DAYS_BEFORE_EX / 252
                premium = bs_call(S, K, T, sigma)
                shares = POSITION_SIZE / S

                data['open_positions'][key] = {
                    'ticker': ticker,
                    'entry_price': S,
                    'strike': K,
                    'premium': premium,
                    'shares': shares,
                    'sigma': sigma,
                    'entry_date': str(today),
                    'ex_date': str(ex_date),
                    'div_amount': event['amount'],
                }
                n_open += 1
                already_active.add(key)
                print(f"  ENTER CC {ticker}: S=${S:.2f} K=${K:.2f} "
                      f"prem=${premium:.3f} ({premium/S:.2%}) ex={ex_date}")
    else:
        print(f"  Portfolio full ({n_open}/{MAX_POSITIONS}), no new entries")

    data['last_update'] = str(today)
    save(data)

    # ── 3. Summary ──
    stats = data['stats']
    wr = stats['wins'] / stats['n_trades'] * 100 if stats['n_trades'] > 0 else 0
    open_pnl = sum(
        pos['premium'] * pos['shares']  # unrealized = premium collected so far
        for pos in data['open_positions'].values()
    )
    total_pnl = stats['total_pnl'] + open_pnl
    print(f"\n  Open positions: {len(data['open_positions'])}")
    for key, pos in data['open_positions'].items():
        td = trading_days_until(date.fromisoformat(pos['ex_date']), today)
        print(f"    {pos['ticker']}: strike=${pos['strike']:.2f} "
              f"prem={pos['premium']/pos['entry_price']:.2%} ex={pos['ex_date']} "
              f"({td}d left)")
    print(f"\n  Realized P&L: ${stats['total_pnl']:+.2f}")
    print(f"  Open premium: ${open_pnl:+.2f}")
    print(f"  Total P&L:    ${total_pnl:+.2f}")
    print(f"  Win rate: {wr:.0f}% ({stats['wins']}/{stats['n_trades']} trades)")
    print(f"  Portfolio value: ${VIRTUAL_CAPITAL + total_pnl:,.2f}")

if __name__ == '__main__':
    run()
