"""
H296 — VIX Term Structure as Equity Timing Signal
===================================================
Signal: When VIX spot < VIX3M (contango / normal term structure), hold SPY.
        When VIX spot > VIX3M (backwardation / stress), hold BIL.
        Variant B: use the ratio VIX/VIX3M as a continuous signal with threshold.
        Variant C: combine VIX term structure with SPY 200-MA filter.

Rationale:
  - VIX term structure slope reflects near-term vs medium-term fear.
  - In normal markets, VIX < VIX3M (investors pay for longer-dated protection).
  - In stress, VIX spikes sharply while VIX3M lags → VIX > VIX3M (backwardation).
  - Backwardation predicts elevated volatility and negative equity returns in the
    near term. Academic support: Duarte & Jones (2007), Simon & Campasano (2014),
    Fernandez-Perez et al. (2020).

Tickers:
  ^VIX   — CBOE Volatility Index (30-day implied vol)
  ^VIX3M — CBOE 3-Month Volatility Index (93-day implied vol); yfinance ticker

IS:  2013-01-01 to 2019-12-31  (^VIX3M reliable from ~2008 but shorter cleaner)
OOS: 2020-01-01 to 2026-05-31

Gate: OOS Sharpe > 1.0 (conservative — this is a timing tool, not an alpha generator)
      AND Sharpe vs SPY buy-and-hold in OOS period

Variants:
  A) VIX < VIX3M → SPY, else BIL  (pure binary)
  B) VIX/VIX3M ratio < 0.95 → SPY, else BIL  (tighter — avoid borderline contango)
  C) VIX < VIX3M AND SPY > 200MA → SPY, else BIL  (double filter)
  D) Continuous: scale SPY weight by (1 - ratio) clipped [0,1], rebalance daily
  E) SPY buy-and-hold  (benchmark)
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2010-01-01"
FULL_END   = "2026-05-31"
IS_START   = "2013-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"

OOS_SHARPE_GATE = 1.0


def calc_stats(eq: pd.Series, label: str = "") -> dict:
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
    dd     = (eq / eq.expanding().max() - 1).min()
    neg_yrs = sum(
        1 for yr, grp in rets.groupby(rets.index.year)
        if (1 + grp).prod() - 1 < 0
    )
    return {
        "cagr":    round(float(cagr),   4),
        "sharpe":  round(float(sharpe),  4),
        "max_dd":  round(float(dd),      4),
        "ann_vol": round(float(vol),     4),
        "n_years": round(float(n_years), 1),
        "neg_yrs": neg_yrs,
    }


def build_equity(daily_signals: pd.Series, spy: pd.Series, bil: pd.Series,
                 start: str, end: str) -> pd.Series:
    """
    daily_signals: 1 = hold SPY, 0 = hold BIL (prev-day signal, forward applied)
    Returns daily equity curve.
    """
    sig  = daily_signals.shift(1).loc[start:end]   # lag 1 day to avoid look-ahead
    sp   = spy.loc[start:end]
    bl   = bil.loc[start:end]

    idx  = sig.index.intersection(sp.index).intersection(bl.index)
    sig  = sig.loc[idx]
    sp   = sp.loc[idx]
    bl   = bl.loc[idx]

    sp_ret  = sp.pct_change().fillna(0)
    bl_ret  = bl.pct_change().fillna(0)

    port_ret = sig * sp_ret + (1 - sig) * bl_ret
    equity   = INITIAL_EQUITY * (1 + port_ret).cumprod()
    return equity


def main():
    print("\n══ H296 — VIX Term Structure Equity Timing ══")
    print(f"IS: {IS_START} → {IS_END}  |  OOS: {OOS_START} → {FULL_END}\n")

    # Download
    print("  Downloading SPY, BIL, ^VIX, ^VIX3M …")
    spy_raw  = yf.download("SPY",   start=FULL_START, end=FULL_END, auto_adjust=True, progress=False)
    bil_raw  = yf.download("BIL",   start=FULL_START, end=FULL_END, auto_adjust=True, progress=False)
    vix_raw  = yf.download("^VIX",  start=FULL_START, end=FULL_END, auto_adjust=True, progress=False)
    vix3_raw = yf.download("^VIX3M",start=FULL_START, end=FULL_END, auto_adjust=True, progress=False)

    def squeeze_close(df):
        c = df["Close"] if "Close" in df.columns else df.iloc[:, 0]
        return c.squeeze()

    spy   = squeeze_close(spy_raw)
    bil   = squeeze_close(bil_raw)
    vix   = squeeze_close(vix_raw)
    vix3m = squeeze_close(vix3_raw)

    # Align on common dates
    df = pd.DataFrame({"spy": spy, "bil": bil, "vix": vix, "vix3m": vix3m}).dropna()
    print(f"  Aligned data: {len(df)} trading days, {df.index[0].date()} → {df.index[-1].date()}")
    print(f"  VIX range: {df['vix'].min():.1f} – {df['vix'].max():.1f}")
    print(f"  VIX/VIX3M backwardation fraction: {(df['vix'] > df['vix3m']).mean():.1%}\n")

    # Build signals
    ratio = df["vix"] / df["vix3m"]

    # A: binary contango/backwardation
    sig_a = (df["vix"] < df["vix3m"]).astype(float)

    # B: tighter threshold — only invest when VIX < 95% of VIX3M
    sig_b = (ratio < 0.95).astype(float)

    # C: double filter — contango AND SPY > 200MA
    ma200 = df["spy"].rolling(200).mean()
    sig_c = ((df["vix"] < df["vix3m"]) & (df["spy"] > ma200)).astype(float)

    # D: continuous — weight = clip(1 - ratio, 0, 1)  (0 when ratio≥1, 1 when ratio≤0)
    sig_d = (1 - ratio).clip(0, 1)

    # E: SPY buy-and-hold (weight=1 always)
    sig_e = pd.Series(1.0, index=df.index)

    variants = {
        "A: VIX<VIX3M binary":          sig_a,
        "B: ratio<0.95 (tighter)":      sig_b,
        "C: VIX<VIX3M + SPY>200MA":    sig_c,
        "D: continuous weight (1-ratio)": sig_d,
        "E: SPY buy-and-hold":          sig_e,
    }

    results = {}
    print("── Results ──────────────────────────────────────────────────────────\n")

    for label, sig in variants.items():
        eq_is  = build_equity(sig, df["spy"], df["bil"], IS_START,  IS_END)
        eq_oos = build_equity(sig, df["spy"], df["bil"], OOS_START, FULL_END)

        is_r  = calc_stats(eq_is,  label + " IS")
        oos_r = calc_stats(eq_oos, label + " OOS")
        results[label] = {"is": is_r, "oos": oos_r}

        print(f"  {label}")
        print(f"    IS  Sharpe={is_r.get('sharpe',0):.3f}  CAGR={is_r.get('cagr',0):.1%}  MaxDD={is_r.get('max_dd',0):.1%}  NegYrs={is_r.get('neg_yrs','?')}")
        print(f"    OOS Sharpe={oos_r.get('sharpe',0):.3f}  CAGR={oos_r.get('cagr',0):.1%}  MaxDD={oos_r.get('max_dd',0):.1%}  NegYrs={oos_r.get('neg_yrs','?')}")
        print()

    # Gate
    spy_oos = results["E: SPY buy-and-hold"]["oos"]
    print(f"\n── Gate Evaluation ──────────────────────────────────────────────────")
    print(f"  Gate: OOS Sharpe > {OOS_SHARPE_GATE}  AND  OOS Sharpe > SPY ({spy_oos.get('sharpe',0):.3f})\n")
    for label, data in results.items():
        if "buy-and-hold" in label:
            continue
        oos_s = data["oos"].get("sharpe", 0)
        passed = (oos_s > OOS_SHARPE_GATE) and (oos_s > spy_oos.get("sharpe", 0))
        status = "PASS ✓" if passed else "FAIL ✗"
        print(f"  {label}: OOS Sharpe {oos_s:.3f} → {status}")

    # Exposure stats
    print("\n── Exposure Statistics (OOS) ────────────────────────────────────────")
    for label, sig in variants.items():
        if "buy-and-hold" in label:
            continue
        sig_oos = sig.shift(1).loc[OOS_START:FULL_END]
        sig_oos = sig_oos.loc[sig_oos.index.intersection(df.index)]
        pct_invested = sig_oos.mean()
        print(f"  {label[:35]:35s}: {pct_invested:.1%} time in SPY")

    # Save
    output = {
        "hypothesis": "H296",
        "title": "VIX Term Structure Equity Timing",
        "is_period":  f"{IS_START} – {IS_END}",
        "oos_period": f"{OOS_START} – {FULL_END}",
        "gate": f"OOS Sharpe > {OOS_SHARPE_GATE} AND > SPY",
        "variants": results,
    }
    out_path = RESULT_DIR / "h296_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
