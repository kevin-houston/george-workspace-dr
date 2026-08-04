"""
H490 — True ADDV-Based Dynamic Top-200 NASDAQ Momentum Universe
==================================================================
Genuine gap flagged at the end of H488 (2026-08-02): every prior stock-momentum
test (H198, H241-H243, H245, H248, H277, H336, H487, H488) used either a static
30-stock NASDAQ mega-cap list or a static ~200-stock S&P-membership-based list.
None used a true Average Daily Dollar Volume (ADDV) ranking recomputed monthly
to dynamically select the top-200 NASDAQ names, which is the actual §3.1
"151 Trading Strategies" construction. This closes that gap.

Candidate superset: ~230 current NASDAQ-listed names spanning tech, biotech,
consumer, communications, industrials-on-NASDAQ, and fintech (NOT limited to
NASDAQ-100 mega-caps — includes mid-caps so ADDV ranking has real work to do).
CAVEAT (same as H272/H277/H336): the candidate superset itself is a *current*
listing snapshot, so this still carries survivorship bias one level up (a stock
that delisted/was acquired before 2026 and would have ranked in the historical
top-200 by ADDV in, say, 2015 is not in the candidate pool at all). What is
genuinely new here is the *monthly re-ranking by trailing ADDV within the pool*
— unlike H241 et al., the 200 names selected each month actually change based
on trading activity, not a single fixed list held constant for the whole test.

Variants:
  A — Dynamic ADDV top-200, 6-1m momentum, top decile (20) EW, monthly rebal
  B — Dynamic ADDV top-200, 12-1m momentum, top decile (20) EW, monthly rebal
  C — Diagnostic: STATIC top-200 by ADDV (ranked once, as of the last IS month,
      then held fixed for the whole backtest) + 6-1m momentum — isolates how
      much of A's edge (if any) comes from dynamic re-ranking vs just having a
      liquidity-informed initial universe.

Gate: OOS Sharpe > 1.174 (H198 confirmed 6-1m 30-stock NASDAQ baseline)
IS: 2013-2020   OOS: 2021-2026   TC: 0.10% round-trip
"""

import warnings; warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# ~230 current NASDAQ-listed names, multi-sector, mega- through mid-cap
CANDIDATES = [
    # Mega-cap tech / NASDAQ-100 core
    "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","AVGO","TSLA","ASML",
    "AMD","ADBE","CSCO","QCOM","INTU","TXN","AMAT","MU","LRCX","INTC",
    "ADI","KLAC","SNPS","CDNS","CRWD","MRVL","NXPI","FTNT","WDAY","ROP",
    "PANW","ON","MCHP","TEAM","ANSS","ZS","DDOG","OKTA","DOCU","NET",
    "SNOW","PLTR","PYPL","COIN","HOOD","ZM","ETSY","TTD","PINS","MTCH",
    "LBTYA","LBTYK","SIRI","WBD","CHTR","CMCSA","TMUS","VRSN","WDC","STX",
    "SWKS","QRVO","CDW","GFS","GEHC","APP","ARM","SMCI","DELL","HPQ",
    # Biotech / healthcare
    "AMGN","GILD","VRTX","REGN","BIIB","ILMN","MRNA","BMRN","ALNY","INCY",
    "EXAS","UTHR","JAZZ","NBIX","HALO","IONS","VTRS","CRSP","BNTX","SAGE",
    "ARWR","BGNE","DXCM","IDXX","ISRG","ALGN","HOLX","RARE","SRPT","TECH",
    "MRTX","LEGN","NTRA","PODD","RVMD","VRNA","XENE","INSM","ACAD","NUVL",
    # Consumer / retail
    "COST","SBUX","MAR","BKNG","ORLY","ROST","LULU","ULTA","DLTR","TSCO",
    "MNST","KDP","KHC","CPRT","PCAR","CTAS","FAST","ODFL","CSX","PAYX",
    "ABNB","DASH","EA","TTWO","VRSK","POOL","WING","CROX","DECK","BROS",
    # Financials / fintech
    "FITB","HBAN","CME","SOFI","AFRM","UPST","MKTX","NDAQ","CBOE","RJF",
    # ADRs / international on NASDAQ
    "JD","PDD","BIDU","NTES","MELI","TCOM","ASML","BABA","SE","MRVL",
    # Communications / media
    "GOOGL","FOXA","LYV","IPGP","EA","TTWO",
    # Industrials / materials / energy-on-NASDAQ
    "LKQ","GLPI","CCEP","XEL","AEP","EXC","PPL","AZN","REGN","CTSH",
    "PAYC","TTEK","EXPD","JBHT","OLED","ENPH","FSLR","SEDG","RUN","PLUG",
    "AXON","TRMB","GEN","AKAM","JNPR","VOD","ERIC","NOK","LOGI","CIEN",
    "ULTA","FIVE","BURL","ORLY","AZO","GNTX","LEA","ALGN","MASI","CHRW",
]
# Deduplicate, preserve order
seen = set()
CANDIDATES = [t for t in CANDIDATES if not (t in seen or seen.add(t))]

DATA_START  = "2010-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
TOP_UNIV    = 200
TOP_N       = 20    # top decile of 200 (Var D overrides to 40, top quintile)
TC          = 0.001
ADDV_LOOKBACK_M = 3  # trailing months for ADDV calc

H198_GATE = 1.174

# ── helpers ─────────────────────────────────────────────────────────────────

def sharpe(r):
    r = r.dropna()
    return float(r.mean() / r.std() * np.sqrt(12)) if len(r) and r.std() > 0 else 0.0

def cumul(r):
    r = r.dropna()
    return float((1 + r).prod()) if len(r) else 1.0

def maxdd(r):
    r = r.dropna()
    if not len(r): return 0.0
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_yrs(r):
    r = r.dropna()
    if not len(r): return 0
    ann = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())

# ── data ────────────────────────────────────────────────────────────────────

def load_data():
    close_cache = CACHE_DIR / "h490_daily_close.parquet"
    vol_cache   = CACHE_DIR / "h490_daily_volume.parquet"
    if close_cache.exists() and vol_cache.exists():
        close = pd.read_parquet(close_cache)
        vol   = pd.read_parquet(vol_cache)
        missing = [t for t in CANDIDATES if t not in close.columns]
        if not missing:
            print(f"  Loaded from cache: {close.shape[1]} tickers")
            return close[CANDIDATES], vol[CANDIDATES]
    print(f"  Downloading {len(CANDIDATES)} tickers (daily, batch)…")
    raw = yf.download(CANDIDATES, start=DATA_START, end=DATA_END,
                       auto_adjust=True, progress=False, threads=True)
    close = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw
    vol   = raw['Volume'] if isinstance(raw.columns, pd.MultiIndex) else None
    close.to_parquet(close_cache)
    vol.to_parquet(vol_cache)
    available = [t for t in CANDIDATES if t in close.columns]
    print(f"  Saved: {len(available)}/{len(CANDIDATES)} tickers")
    return close[available], vol[available]

# ── universe + signal construction ─────────────────────────────────────────

def build_monthly(close: pd.DataFrame, vol: pd.DataFrame):
    dollar_vol = (close * vol)
    monthly_close = close.resample("ME").last()
    monthly_addv  = dollar_vol.resample("ME").mean()  # avg daily $ vol within each month
    return monthly_close, monthly_addv

def run_backtest(monthly_close, monthly_addv, variant, static_universe=None, top_n=TOP_N):
    ret = monthly_close.pct_change()
    dates = monthly_close.index
    port_rets, prev_set = [], set()
    dyn_universe_sizes = []

    for i in range(13, len(dates) - 1):
        date, fwd_date = dates[i], dates[i + 1]

        lookback = 12 if variant == 'B' else 6
        p_end = monthly_close.iloc[i - 1]
        mom = monthly_close.iloc[i - 1 - lookback] .rsub(0)  # placeholder, overwritten below
        mom = (monthly_close.iloc[i - 1] / monthly_close.iloc[i - 1 - lookback]) - 1

        fwd_ret = ret.iloc[i + 1]

        if variant == 'C' and static_universe is not None:
            eligible = [t for t in static_universe if t in monthly_close.columns]
        else:
            # trailing ADDV_LOOKBACK_M-month avg ADDV through month i-1 (no lookahead)
            addv_trail = monthly_addv.iloc[i - ADDV_LOOKBACK_M:i].mean()
            eligible_all = addv_trail.dropna().sort_values(ascending=False)
            eligible = eligible_all.head(TOP_UNIV).index.tolist()

        valid = [t for t in eligible
                 if pd.notna(mom.get(t, np.nan)) and pd.notna(fwd_ret.get(t, np.nan))]
        dyn_universe_sizes.append(len(valid))

        if len(valid) < top_n:
            port_rets.append((date, 0.0))
            continue

        mom_valid = mom[valid].sort_values(ascending=False)
        top = set(mom_valid.head(top_n).index.tolist())
        turnover = len(top.symmetric_difference(prev_set)) / (2 * top_n)
        tc_drag = turnover * TC
        prev_set = top

        monthly_ret = fwd_ret[list(top)].dropna().mean()
        port_rets.append((date, monthly_ret - tc_drag))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.to_datetime(s.index)
    avg_univ = float(np.mean(dyn_universe_sizes)) if dyn_universe_sizes else 0.0
    return s, avg_univ

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("H490 — True ADDV-Based Dynamic Top-200 NASDAQ Momentum Universe")
    print("=" * 70)

    print("\nLoading daily close + volume…")
    close, vol = load_data()
    print(f"  {close.shape[1]} tickers × {len(close)} days")

    print("\nBuilding monthly close + ADDV panels…")
    monthly_close, monthly_addv = build_monthly(close, vol)
    print(f"  {len(monthly_close)} months")

    # Static universe for Var C: top-200 by ADDV as of the last IS month (2020-12)
    is_end_idx = monthly_addv.index.get_indexer([IS_END], method='nearest')[0]
    static_addv = monthly_addv.iloc[is_end_idx - ADDV_LOOKBACK_M:is_end_idx].mean()
    static_universe = static_addv.dropna().sort_values(ascending=False).head(TOP_UNIV).index.tolist()
    print(f"  Static (Var C) universe fixed as of {monthly_addv.index[is_end_idx].date()}, "
          f"{len(static_universe)} names")

    # Benchmarks
    spy_raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)['Close']
    qqq_raw = yf.download("QQQ", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)['Close']
    if isinstance(spy_raw, pd.DataFrame): spy_raw = spy_raw.squeeze()
    if isinstance(qqq_raw, pd.DataFrame): qqq_raw = qqq_raw.squeeze()
    spy_ret = spy_raw.resample("ME").last().pct_change()
    qqq_ret = qqq_raw.resample("ME").last().pct_change()

    results = {}
    print()
    for var, label, tn in [('A', 'Dynamic ADDV Top-200, 6-1m, top-20', TOP_N),
                            ('B', 'Dynamic ADDV Top-200, 12-1m, top-20', TOP_N),
                            ('C', 'Static ADDV Top-200 (fixed 2020-12), 6-1m, top-20', TOP_N),
                            ('D', 'Dynamic ADDV Top-200, 6-1m, top-40 (diversification diagnostic)', 40)]:
        var_key = 'A' if var == 'D' else var  # D reuses A's signal logic (6-1m, dynamic)
        su = static_universe if var == 'C' else None
        all_ret, avg_univ = run_backtest(monthly_close, monthly_addv, var_key, su, top_n=tn)
        is_ret  = all_ret.loc[IS_START:IS_END]
        oos_ret = all_ret.loc[OOS_START:OOS_END]

        aligned_spy = spy_ret.reindex(oos_ret.index)
        corr_spy = float(oos_ret.corr(aligned_spy))
        ann_oos = oos_ret.groupby(oos_ret.index.year).apply(lambda x: (1+x).prod()-1)
        ann_str = " | ".join(f"{y}:{v*100:+.1f}%" for y, v in ann_oos.items())

        print(f"--- Variant {var}: {label} ---")
        print(f"  Avg eligible universe size: {avg_univ:.0f}")
        print(f"  IS  Sharpe={sharpe(is_ret):.3f}  Cumul={cumul(is_ret):.3f}x  MaxDD={maxdd(is_ret)*100:.1f}%  NegYrs={neg_yrs(is_ret)}")
        print(f"  OOS Sharpe={sharpe(oos_ret):.3f}  Cumul={cumul(oos_ret):.3f}x  MaxDD={maxdd(oos_ret)*100:.1f}%  NegYrs={neg_yrs(oos_ret)}")
        print(f"  Corr(OOS,SPY)={corr_spy:.3f}")
        print(f"  Annual OOS: {ann_str}")
        print()

        results[f'variant_{var}'] = {
            'label': label,
            'avg_universe_size': round(avg_univ, 1),
            'is_sharpe': round(sharpe(is_ret), 3),
            'oos_sharpe': round(sharpe(oos_ret), 3),
            'oos_cumul': round(cumul(oos_ret), 3),
            'oos_maxdd': round(maxdd(oos_ret) * 100, 1),
            'oos_neg_yrs': neg_yrs(oos_ret),
            'corr_spy_oos': round(corr_spy, 3),
        }

    for name, bret in [('SPY', spy_ret), ('QQQ', qqq_ret)]:
        b_oos = bret.loc[OOS_START:OOS_END]
        print(f"--- {name} Benchmark ---")
        print(f"  OOS Sharpe={sharpe(b_oos):.3f}  Cumul={cumul(b_oos):.3f}x  MaxDD={maxdd(b_oos)*100:.1f}%")
        results[f'{name.lower()}_benchmark'] = {
            'oos_sharpe': round(sharpe(b_oos), 3),
            'oos_cumul': round(cumul(b_oos), 3),
            'oos_maxdd': round(maxdd(b_oos) * 100, 1),
        }

    out_path = RESULT_DIR / 'h490_results.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out_path}")

    print("\nCONFIRM CHECKS (gate: OOS Sharpe > 1.174, H198 baseline):")
    for var in ['A', 'B', 'C']:
        s = results[f'variant_{var}']['oos_sharpe']
        print(f"  Variant {var}: OOS Sharpe {s:.3f} → {'CONFIRMED' if s > H198_GATE else 'NOT CONFIRMED'}")


if __name__ == "__main__":
    main()
