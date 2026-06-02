"""
H242 — Sector-Neutral 200-Stock Momentum (H241-SN)
===================================================
H241's Variant A showed OOS Sharpe=1.222 with Corr(SPY)=-0.276 and 0 negative years.
Root cause question: Is the negative SPY correlation due to:
  (a) Sector concentration — momentum loaded into Energy 2022 (up +~65%) while tech crashed
  (b) Genuine stock-selection alpha that persists across sectors

H242 test: sector-neutral variant of H241-A
  - Rank stocks WITHIN each GICS sector by 6-1m momentum
  - Select top-2 from each of 11 sectors → 22-stock portfolio (near equal sector exposure)
  - Compare OOS Sharpe, MaxDD, SPY correlation, 2022 return

If Corr(H242, SPY) remains negative and Sharpe improves: genuine stock selection.
If Corr(H242, SPY) turns positive and 2022 return collapses: sector concentration was the driver.

Also tests: Vol-scaled weights (inverse-vol, normalized) vs equal-weight.

IS: 2013–2020   OOS: 2021–2026
Confirm: OOS Sharpe > H241-A baseline (1.222)
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

IS_START  = pd.Timestamp("2013-01-01")
IS_END    = pd.Timestamp("2020-12-31")
OOS_START = pd.Timestamp("2021-01-01")
OOS_END   = pd.Timestamp("2026-05-31")
TC        = 0.001

# GICS sector assignments for H241 universe (11 sectors)
SECTOR_MAP = {
    # Info Tech
    "AAPL":"IT","MSFT":"IT","NVDA":"IT","AVGO":"IT","AMD":"IT","QCOM":"IT","ORCL":"IT",
    "CRM":"IT","ADBE":"IT","INTC":"IT","TXN":"IT","ACN":"IT","IBM":"IT","AMAT":"IT",
    "LRCX":"IT","MU":"IT","NOW":"IT","INTU":"IT","ADI":"IT","NXPI":"IT","MCHP":"IT",
    "KLAC":"IT","CDNS":"IT","SNPS":"IT","FTNT":"IT","GLW":"IT","HPE":"IT","KEYS":"IT",
    "ZBRA":"IT","JNPR":"IT",
    # Consumer Disc
    "AMZN":"CD","TSLA":"CD","HD":"CD","MCD":"CD","NKE":"CD","SBUX":"CD","LOW":"CD",
    "TJX":"CD","F":"CD","GM":"CD","CMG":"CD","BKNG":"CD","ROST":"CD","DRI":"CD",
    "DHI":"CD","LEN":"CD","PHM":"CD","NVR":"CD","TOL":"CD","EXPE":"CD",
    # Financials
    "JPM":"FIN","BAC":"FIN","WFC":"FIN","GS":"FIN","MS":"FIN","C":"FIN","BLK":"FIN",
    "AXP":"FIN","CB":"FIN","PGR":"FIN","MET":"FIN","PRU":"FIN","TRV":"FIN","ICE":"FIN",
    "CME":"FIN","SCHW":"FIN","USB":"FIN","PNC":"FIN","TFC":"FIN","SPGI":"FIN",
    "MCO":"FIN","COF":"FIN","DFS":"FIN","AIG":"FIN","MMC":"FIN",
    # Healthcare
    "UNH":"HC","LLY":"HC","JNJ":"HC","ABBV":"HC","MRK":"HC","PFE":"HC","TMO":"HC",
    "ABT":"HC","AMGN":"HC","GILD":"HC","MDT":"HC","BMY":"HC","ISRG":"HC","CVS":"HC",
    "CI":"HC","HUM":"HC","ELV":"HC","REGN":"HC","VRTX":"HC","ZBH":"HC","BDX":"HC",
    "BSX":"HC","EW":"HC","DXCM":"HC","HOLX":"HC",
    # Staples
    "WMT":"CS","COST":"CS","PG":"CS","KO":"CS","PEP":"CS","PM":"CS","MO":"CS",
    "MDLZ":"CS","CL":"CS","GIS":"CS","K":"CS","CPB":"CS","HRL":"CS","SJM":"CS","CAG":"CS",
    # Energy
    "XOM":"EN","CVX":"EN","COP":"EN","EOG":"EN","PSX":"EN","VLO":"EN","MPC":"EN",
    "SLB":"EN","HAL":"EN","OXY":"EN","HES":"EN","APA":"EN","DVN":"EN","FANG":"EN","KMI":"EN",
    # Industrials
    "HON":"IND","UPS":"IND","RTX":"IND","LMT":"IND","CAT":"IND","GE":"IND","NOC":"IND",
    "BA":"IND","DE":"IND","EMR":"IND","ETN":"IND","ITW":"IND","CTAS":"IND","WM":"IND",
    "RSG":"IND","CSX":"IND","NSC":"IND","UNP":"IND","FDX":"IND","MMM":"IND",
    # Materials
    "LIN":"MAT","APD":"MAT","SHW":"MAT","ECL":"MAT","NEM":"MAT","FCX":"MAT",
    "NUE":"MAT","ALB":"MAT","CF":"MAT","MOS":"MAT",
    # Real Estate
    "PLD":"RE","AMT":"RE","EQIX":"RE","CCI":"RE","SPG":"RE","O":"RE",
    "DLR":"RE","EXR":"RE","AVB":"RE","EQR":"RE",
    # Utilities
    "NEE":"UT","DUK":"UT","SO":"UT","D":"UT","AEP":"UT","EXC":"UT",
    "PCG":"UT","SRE":"UT","XEL":"UT","PPL":"UT",
    # Comm Services
    "GOOGL":"CS2","META":"CS2","NFLX":"CS2","DIS":"CS2","CMCSA":"CS2","VZ":"CS2",
    "T":"CS2","TMUS":"CS2","CHTR":"CS2","FOXA":"CS2","EA":"CS2","TTWO":"CS2",
    "OMC":"CS2","IPG":"CS2","LDOS":"CS2",
}

TOPS_PER_SECTOR = 2  # top-2 per sector → up to 22 stocks

def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r): return float((1 + r).prod())
def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())
def neg_yrs(r):
    return int((r.groupby(r.index.year).apply(lambda x: (1+x).prod()-1) < 0).sum())

def load_panel() -> pd.DataFrame:
    """Load pre-built panel from H241 run (reuse exact same data)."""
    # Reload prices from cache
    cache = CACHE_DIR / "h241_monthly_prices.parquet"
    prices = pd.read_parquet(cache)
    ret = prices.pct_change()
    rows = []
    dates = prices.index
    for i in range(13, len(dates) - 1):
        date = dates[i]
        r1m = ret.iloc[i - 1]
        mom_6_1  = prices.iloc[i-1] / prices.iloc[i-7]  - 1
        mom_12_1 = prices.iloc[i-1] / prices.iloc[i-13] - 1
        vol_12m  = ret.iloc[i-12:i].std() * np.sqrt(12)
        fwd_ret  = ret.iloc[i + 1]
        tickers = prices.columns[prices.iloc[i-1].notna() & prices.iloc[i+1].notna()]
        for t in tickers:
            rows.append({
                'date': date,
                'ticker': t,
                'sector': SECTOR_MAP.get(t, 'OTHER'),
                'fwd_ret': fwd_ret[t],
                'mom_6_1': mom_6_1[t],
                'mom_12_1': mom_12_1[t],
                'rev_1m': r1m[t],
                'vol_12m': vol_12m[t],
            })
    df = pd.DataFrame(rows).dropna(subset=['mom_6_1','fwd_ret'])
    return df.set_index(['date','ticker'])


def run_sector_neutral(panel: pd.DataFrame,
                       vol_scaled: bool = False,
                       tops: int = TOPS_PER_SECTOR) -> pd.Series:
    """Select top-N per sector by 6-1m momentum. Vol-scale weights optionally."""
    dates = panel.index.get_level_values('date').unique().sort_values()
    port_rets = []
    prev_set: set = set()

    for date in dates:
        df_t = panel.loc[date].copy()

        selected = []
        for sector, grp in df_t.groupby('sector'):
            if len(grp) < tops:
                selected.extend(grp.nlargest(len(grp), 'mom_6_1').index.tolist())
            else:
                selected.extend(grp.nlargest(tops, 'mom_6_1').index.tolist())

        if not selected:
            port_rets.append(0.0)
            prev_set = set()
            continue

        df_sel = df_t.loc[selected]

        turnover = len(set(selected).symmetric_difference(prev_set)) / max(1, 2*len(selected))
        tc_drag = turnover * TC
        prev_set = set(selected)

        if vol_scaled:
            w = 1.0 / (df_sel['vol_12m'].replace(0, np.nan).fillna(df_sel['vol_12m'].mean()) + 1e-8)
            w = w / w.sum()
            ret_monthly = (df_sel['fwd_ret'] * w).sum() - tc_drag
        else:
            ret_monthly = df_sel['fwd_ret'].mean() - tc_drag

        port_rets.append(ret_monthly)

    s = pd.Series(port_rets, index=dates)
    s.index = pd.to_datetime(s.index)
    return s


def main():
    print("=" * 65)
    print("H242 — Sector-Neutral 200-Stock Momentum")
    print("H241-A baseline: OOS Sharpe=1.222, Corr(SPY)=-0.276, 0 neg yrs")
    print("=" * 65)

    print("\nLoading panel from H241 cache…")
    panel = load_panel()
    print(f"  Panel: {len(panel):,} stock-months")

    spy_raw = yf.download("SPY", start="2010-01-01", end="2026-05-31",
                          auto_adjust=True, progress=False)['Close']
    if isinstance(spy_raw, pd.DataFrame):
        spy_raw = spy_raw.squeeze()
    spy_ret = spy_raw.resample("ME").last().pct_change().squeeze()
    spy_oos = spy_ret.loc[OOS_START:OOS_END].dropna()

    variants = {
        'SN-EW':  (False, TOPS_PER_SECTOR),    # sector-neutral, equal weight
        'SN-VS':  (True,  TOPS_PER_SECTOR),    # sector-neutral, vol-scaled
        'SN-1':   (False, 1),                  # sector-neutral, top-1 per sector
        'SN-3':   (False, 3),                  # sector-neutral, top-3 per sector
    }

    results = {}
    print()
    for name, (vs, tops) in variants.items():
        label = f"top-{tops} per sector {'vol-scaled' if vs else 'equal-weight'}"
        all_ret = run_sector_neutral(panel, vol_scaled=vs, tops=tops)
        is_ret  = all_ret.loc[IS_START:IS_END]
        oos_ret = all_ret.loc[OOS_START:OOS_END]

        aligned_spy = spy_oos.reindex(oos_ret.index).squeeze()
        corr_spy = float(oos_ret.corr(aligned_spy))

        ann_oos = oos_ret.groupby(oos_ret.index.year).apply(lambda x: (1+x).prod()-1)
        ann_str = " | ".join(f"{y}:{v*100:+.1f}%" for y, v in ann_oos.items())

        print(f"--- Variant {name}: {label} ---")
        print(f"  IS  Sharpe={sharpe(is_ret):.3f}  Cumul={cumul(is_ret):.3f}×  MaxDD={maxdd(is_ret)*100:.1f}%  NegYrs={neg_yrs(is_ret)}")
        print(f"  OOS Sharpe={sharpe(oos_ret):.3f}  Cumul={cumul(oos_ret):.3f}×  MaxDD={maxdd(oos_ret)*100:.1f}%  NegYrs={neg_yrs(oos_ret)}")
        print(f"  Corr(OOS,SPY)={corr_spy:.3f}")
        print(f"  Annual OOS: {ann_str}")
        print()

        results[name] = {
            'is_sharpe': round(sharpe(is_ret),3),
            'oos_sharpe': round(sharpe(oos_ret),3),
            'oos_cumul': round(cumul(oos_ret),3),
            'oos_maxdd': round(maxdd(oos_ret)*100,1),
            'oos_neg_yrs': neg_yrs(oos_ret),
            'corr_spy_oos': round(corr_spy,3),
            'oos_2022': round(float(ann_oos.get(2022, np.nan))*100,1),
        }

    print(f"--- SPY Benchmark ---")
    print(f"  OOS Sharpe={sharpe(spy_oos):.3f}  Cumul={cumul(spy_oos):.3f}×  MaxDD={maxdd(spy_oos)*100:.1f}%")

    best_sn_sharpe = max(v['oos_sharpe'] for v in results.values())
    h241_baseline = 1.222
    confirmed = best_sn_sharpe > h241_baseline
    best_name = max(results, key=lambda k: results[k]['oos_sharpe'])
    best_corr = results[best_name]['corr_spy_oos']
    best_2022 = results[best_name]['oos_2022']

    print(f"\nCONFIRM CHECK: Best SN OOS Sharpe {best_sn_sharpe:.3f} > H241-A 1.222 → {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"SECTOR CONCENTRATION DIAGNOSIS:")
    print(f"  Best variant: {best_name}, Corr(SPY)={best_corr:.3f}, 2022 ret={best_2022:+.1f}%")
    print(f"  H241-A: Corr(SPY)=-0.276, 2022 ret=+11.7%")
    if abs(best_corr) < 0.10 and best_2022 < 5.0:
        print(f"  → DIAGNOSIS: Negative correlation in H241-A was SECTOR CONCENTRATION (energy tilt 2022)")
    elif best_corr < -0.15:
        print(f"  → DIAGNOSIS: Negative correlation persists → genuine STOCK SELECTION alpha")
    else:
        print(f"  → DIAGNOSIS: Mixed — partial sector effect, partial stock selection")

    out = RESULT_DIR / 'h242_results.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
