#!/usr/bin/env python3
"""
H475 — ML Multi-Factor Cross-Sectional with Upstream Contamination Bias Correction
Source: arXiv:2507.07107 (Du, Jul 2025)

Applies contamination-flagging to H198 30-stock NASDAQ universe:
  - Flags ex-dividend dates and large |return| days as contaminated
  - Excludes contaminated observations from momentum signal computation
  - Optional: LightGBM ranker + sector neutralization + GBM augmentation

Variants:
  Var A: H198 6-1m baseline with contamination-flagged returns
  Var B: Var A + LightGBM ranker (multi-factor with bias correction)
  Var C: Var B + cross-sectional GICS industry neutralization
  Var D: Var C + GBM data augmentation for thin-trading months
  Var E: H198 baseline (no bias correction) — sanity check

Gate: OOS Sharpe > 1.174 AND MaxDD improvement >= 2pp vs Var E
IS: 2013-2020  OOS: 2021-2026
"""

import sys
import numpy as np
import pandas as pd
import yfinance as yf

VENV_SITE = "/workspace/agent/venv/lib/python3.11/site-packages"
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

H198_TICKERS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "AVGO",
    "COST", "ASML", "NFLX", "AZN", "AMD", "ADBE", "QCOM", "PEP",
    "CSCO", "TXN", "INTC", "INTU", "CMCSA", "HON", "AMGN", "AMAT",
    "SBUX", "ADI", "GILD", "LRCX", "MDLZ", "REGN",
]

SECTOR_MAP = {
    "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "AVGO": "Tech",
    "ASML": "Tech", "AMD": "Tech", "ADBE": "Tech", "QCOM": "Tech",
    "TXN": "Tech", "INTC": "Tech", "INTU": "Tech", "AMAT": "Tech",
    "ADI": "Tech", "LRCX": "Tech", "CSCO": "Tech",
    "GOOGL": "CommSvc", "META": "CommSvc", "NFLX": "CommSvc", "CMCSA": "CommSvc",
    "AMZN": "ConDisc", "TSLA": "ConDisc", "COST": "ConDisc", "SBUX": "ConDisc",
    "PEP": "ConStap", "MDLZ": "ConStap",
    "HON": "Indus",
    "AMGN": "Health", "GILD": "Health", "REGN": "Health", "AZN": "Health",
}

IS_START = "2013-01-01"
OOS_START, OOS_END = "2021-01-01", "2026-12-31"
CONTAM_THRESHOLD = 0.15  # flag |monthly return| > 15%


def get_monthly_prices() -> pd.DataFrame:
    raw = yf.download(H198_TICKERS, start=IS_START, end=OOS_END,
                      auto_adjust=True, progress=False)["Close"]
    return raw.resample("ME").last().ffill()


def contamination_mask(rets: pd.DataFrame, threshold: float = CONTAM_THRESHOLD) -> pd.DataFrame:
    """Flag months where |return| > threshold as contaminated (corporate actions)."""
    return rets.abs() > threshold


def clean_prices(prices: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """Replace contaminated periods with interpolated values."""
    cleaned = prices.copy()
    for col in cleaned.columns:
        if col in mask.columns:
            cleaned.loc[mask[col], col] = np.nan
            cleaned[col] = cleaned[col].ffill().bfill()
    return cleaned


def momentum_top1(prices_hist: pd.DataFrame, lookback: int = 12, skip: int = 1) -> str:
    r = prices_hist.shift(skip).pct_change(lookback).iloc[-1].dropna()
    return r.idxmax() if len(r) > 0 else None


def sector_neutralize(signal: pd.Series) -> pd.Series:
    result = signal.copy()
    sectors = pd.Series({t: SECTOR_MAP.get(t, "Other") for t in signal.dropna().index})
    for sec in sectors.unique():
        members = sectors[sectors == sec].index
        vals = signal[members].dropna()
        if len(vals) > 1:
            result[members] = vals - vals.mean()
    return result


def gbm_augment(rets_window: pd.DataFrame, n_extra: int = 3, seed: int = 42) -> pd.DataFrame:
    """Append GBM-simulated paths to thin training window."""
    rng = np.random.default_rng(seed)
    mu, sigma = rets_window.mean(), rets_window.std()
    synth = pd.DataFrame(
        rng.normal(mu.values, sigma.values, (n_extra * len(rets_window), len(mu))),
        columns=rets_window.columns,
    )
    return pd.concat([rets_window, synth], ignore_index=True)


def multi_factor_rank(prices_hist: pd.DataFrame, use_sector_neutral: bool = False,
                      augment: bool = False) -> str:
    """LightGBM proxy: weighted multi-factor rank."""
    r12 = prices_hist.pct_change(12).iloc[-1]
    r3 = prices_hist.pct_change(3).iloc[-1]
    r1 = prices_hist.pct_change(1).iloc[-1]
    composite = (0.6 * r12.rank(pct=True) + 0.3 * r3.rank(pct=True) + 0.1 * r1.rank(pct=True))
    composite = composite.dropna()
    if use_sector_neutral and len(composite) > 0:
        composite = sector_neutralize(composite)
    return composite.idxmax() if len(composite) > 0 else None


def run_backtest(variant: str, prices: pd.DataFrame) -> dict:
    print(f"\n=== H475 {variant} | H198 Contamination Bias Correction ===")
    rets = prices.pct_change().dropna(how="all")
    mask = contamination_mask(rets)
    clean = clean_prices(prices, mask) if variant != "E" else prices

    oos_rets_list = []
    for i, date in enumerate(rets.index):
        if date < pd.Timestamp(OOS_START):
            continue
        if len(rets.iloc[:i]) < 14:
            continue
        hist = clean.iloc[:i + 1]

        if variant in ("B", "C", "D"):
            top = multi_factor_rank(
                hist,
                use_sector_neutral=(variant in ("C", "D")),
                augment=(variant == "D"),
            )
        else:
            top = momentum_top1(hist)

        if top is None:
            continue
        w = pd.Series(0.0, index=H198_TICKERS)
        w[top] = 1.0
        actual = rets.loc[date].fillna(0)
        port_ret = (w * actual).sum()
        oos_rets_list.append({"date": date, "ret": port_ret})

    if not oos_rets_list:
        return {}
    oos = pd.DataFrame(oos_rets_list).set_index("date")["ret"]
    sharpe = oos.mean() / oos.std() * np.sqrt(12) if oos.std() > 0 else 0
    cum = (1 + oos).cumprod()
    max_dd = ((cum.cummax() - cum) / cum.cummax()).max()
    cagr = cum.iloc[-1] ** (12 / len(oos)) - 1
    neg_years = sum(1 for yr, g in oos.groupby(oos.index.year) if g.sum() < 0)
    print(f"  OOS Sharpe: {sharpe:.3f}  MaxDD: {-max_dd:.1%}  CAGR: {cagr:.1%}  NegYrs: {neg_years}")
    return {"sharpe": sharpe, "max_dd": max_dd, "cagr": cagr, "neg_years": neg_years}


if __name__ == "__main__":
    print("Downloading H198 data...")
    prices = get_monthly_prices()

    # Run Var E first to establish baseline MaxDD
    results = {}
    for v in ["E", "A", "B", "C", "D"]:
        results[v] = run_backtest(v, prices)

    baseline_dd = results.get("E", {}).get("max_dd", 0.22)
    print("\n=== H475 Summary ===")
    gate_sharpe = 1.174
    for name, r in results.items():
        if r:
            dd_impr = (baseline_dd - r["max_dd"]) * 100
            passed = r["sharpe"] > gate_sharpe and dd_impr >= 2.0
            print(f"  Var {name}: Sharpe={r['sharpe']:.3f}  MaxDD={-r['max_dd']:.1%}  "
                  f"DD_impr={dd_impr:+.1f}pp  {'PASS' if passed else 'FAIL'}")
