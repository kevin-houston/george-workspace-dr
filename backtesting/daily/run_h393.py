"""
H393: Amihud ILLIQ Composite on H386 IMOM+MOM Signal
=====================================================
H386 best variant (Var A): OOS Sharpe 3.273, MaxDD -7.5% using
0.5×IMOM6 + 0.5×MOM60, top-2 on the H198 30-stock large-cap universe.

Hypothesis: Adding Amihud ILLIQ liquidity factor improves stock selection.
Illiquidity = |daily_ret| / dollar_volume, monthly-averaged. Lower ILLIQ
= more liquid = lower idiosyncratic risk. Rank inverted so high rank = liquid.

Source: Aldridge (arXiv:2607.01377, Jul 2026) — liquidity composite signal.

Variants:
  A: 0.40×rank(IMOM6) + 0.40×rank(MOM60) + 0.20×rank(1/ILLIQ), top-2
  B: 0.45×rank(IMOM6) + 0.45×rank(MOM60) + 0.10×rank(1/ILLIQ), top-2
  C: 0.33×rank(IMOM6) + 0.33×rank(MOM60) + 0.33×rank(1/ILLIQ), top-2
  D: 0.40×rank(IMOM6) + 0.40×rank(MOM60) + 0.20×rank(1/ILLIQ), top-1

IS: 2013-2020  OOS: 2021-2026  Universe: H198 30-stock
Gate: OOS Sharpe > 1.174 AND MaxDD > -30%
"""

import warnings
warnings.filterwarnings("ignore")
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

UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

DATA_START  = "2011-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 1.174
GATE_MAXDD  = -0.30


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h386", "h385", "h377", "h376", "h373", "h198"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    cp = CACHE_DIR / f"h393_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    """Fetch daily Close + Volume for Amihud ILLIQ computation."""
    cp = CACHE_DIR / f"h393_{ticker}_daily_ohlcv_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Close", "Volume"]].copy()
    df.to_parquet(cp)
    return df


def compute_amihud_illiq(ticker: str) -> pd.Series:
    """
    Monthly Amihud ILLIQ = mean(|ret| / dollar_vol) over trading days.
    Returns monthly series indexed to month-end. Lower = more liquid.
    """
    df = fetch_daily_ohlcv(ticker)
    daily_ret = df["Close"].pct_change().abs()
    dollar_vol = df["Close"] * df["Volume"]
    illiq = daily_ret / dollar_vol
    illiq = illiq.replace([np.inf, -np.inf], np.nan)
    monthly = illiq.resample("ME").mean()
    monthly.name = ticker
    return monthly


def sharpe(r: pd.Series) -> float:
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def cagr_ann(r: pd.Series) -> float:
    return float(r.mean() * 12)

def neg_years(r: pd.Series) -> int:
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())

def eval_period(rets: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "maxdd":   round(maxdd(r), 3),
        "cagr":    round(cagr_ann(r), 3),
        "neg_yrs": neg_years(r),
    }


def compute_imom(monthly_px: pd.DataFrame, window: int = 6) -> pd.DataFrame:
    """IMOM = compound return - arithmetic sum of monthly returns (no skip)."""
    monthly_ret = monthly_px.pct_change()
    mom = monthly_px.pct_change(window)
    ret_sum = monthly_ret.rolling(window).sum()
    return mom - ret_sum


def backtest(
    monthly_px: pd.DataFrame,
    signal: pd.DataFrame,
    top_n: int,
    bil_mask: pd.Series = None,
) -> pd.Series:
    monthly_ret = monthly_px.pct_change()
    port_rets   = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    for month_end in months:
        if bil_mask is not None and bil_mask.get(month_end, False):
            port_rets.append((month_end, 0.0))
            continue
        scores = signal.loc[month_end].dropna()
        if len(scores) < top_n:
            continue
        selected = scores.nlargest(top_n).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, float(ret_this)))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H393 — Amihud ILLIQ Composite on H386 IMOM+MOM")
    print("=" * 60)

    # ── Load monthly prices ───────────────────────────────────────────────────
    print("\nLoading monthly prices…")
    monthly_list = []
    for t in UNIVERSE:
        try:
            monthly_list.append(fetch_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    # ── Compute Amihud ILLIQ (monthly) ───────────────────────────────────────
    print("Computing Amihud ILLIQ (daily → monthly)…")
    illiq_list = []
    for t in UNIVERSE:
        try:
            illiq_list.append(compute_amihud_illiq(t))
        except Exception as e:
            print(f"  WARN ILLIQ {t}: {e}")
    illiq_df = pd.DataFrame(illiq_list).T.sort_index()
    # Align to monthly_px index
    illiq_df = illiq_df.reindex(monthly_px.index)
    print(f"  ILLIQ coverage: {illiq_df.notna().mean().mean():.1%} across universe")

    # ── Compute base signals ──────────────────────────────────────────────────
    print("Computing IMOM and MOM signals…")
    imom_6m = compute_imom(monthly_px, window=6)
    mom_6_0 = monthly_px.pct_change(6)

    rank_imom6 = imom_6m.rank(axis=1, pct=True)
    rank_mom60 = mom_6_0.rank(axis=1, pct=True)

    # ILLIQ rank: higher rank = more liquid (invert ILLIQ so large = good)
    rank_illiq = illiq_df.rank(axis=1, pct=True, ascending=False)

    # H198 baseline
    sig_6_1  = monthly_px.shift(1) / monthly_px.shift(7) - 1
    rank_6_1 = sig_6_1.rank(axis=1, pct=True)

    # ── SPY benchmark ─────────────────────────────────────────────────────────
    spy_cp = CACHE_DIR / "h198_SPY_monthly_2011-01-01_2026-04-30.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
    spy_ret = spy_px.pct_change().dropna()

    # ── Baselines ─────────────────────────────────────────────────────────────
    print("\n=== Baselines ===")
    base_rets = backtest(monthly_px, rank_6_1, top_n=1)
    bi = eval_period(base_rets, IS_START, IS_END)
    bo = eval_period(base_rets, OOS_START, OOS_END)
    si = eval_period(spy_ret, IS_START, IS_END)
    so = eval_period(spy_ret, OOS_START, OOS_END)

    # H386 Var A reference
    comp_h386a = 0.5 * rank_imom6 + 0.5 * rank_mom60
    h386a_rets = backtest(monthly_px, comp_h386a, top_n=2)
    h386a_i = eval_period(h386a_rets, IS_START, IS_END)
    h386a_o = eval_period(h386a_rets, OOS_START, OOS_END)

    print(f"H198 6-1m top-1 (gate)     IS {bi['sharpe']:.3f} | OOS {bo['sharpe']:.3f}  MaxDD {bo['maxdd']:.1%}")
    print(f"H386 Var A IMOM+MOM top-2  IS {h386a_i['sharpe']:.3f} | OOS {h386a_o['sharpe']:.3f}  MaxDD {h386a_o['maxdd']:.1%}")
    print(f"SPY buy-and-hold           IS {si['sharpe']:.3f} | OOS {so['sharpe']:.3f}  MaxDD {so['maxdd']:.1%}")

    # ── Variants ──────────────────────────────────────────────────────────────
    comp_40_40_20_t2 = 0.40 * rank_imom6 + 0.40 * rank_mom60 + 0.20 * rank_illiq
    comp_45_45_10_t2 = 0.45 * rank_imom6 + 0.45 * rank_mom60 + 0.10 * rank_illiq
    comp_33_33_33_t2 = 0.33 * rank_imom6 + 0.33 * rank_mom60 + 0.33 * rank_illiq
    comp_40_40_20_t1 = comp_40_40_20_t2  # same signal, different top_n

    variants = {
        "A": dict(signal=comp_40_40_20_t2, top_n=2, desc="0.40×IMOM6+0.40×MOM60+0.20×ILLIQ top-2"),
        "B": dict(signal=comp_45_45_10_t2, top_n=2, desc="0.45×IMOM6+0.45×MOM60+0.10×ILLIQ top-2"),
        "C": dict(signal=comp_33_33_33_t2, top_n=2, desc="0.33×IMOM6+0.33×MOM60+0.33×ILLIQ top-2"),
        "D": dict(signal=comp_40_40_20_t1, top_n=1, desc="0.40×IMOM6+0.40×MOM60+0.20×ILLIQ top-1"),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 90)
    print(f"{'H386A':4} {h386a_i['sharpe']:>7.3f} {h386a_o['sharpe']:>8.3f} {h386a_o['maxdd']:>9.1%} "
          f"{h386a_o['cagr']*100:>6.1f}% {h386a_o['neg_yrs']:>5d}  H386 Var A reference (no ILLIQ)")
    print()

    results = {
        "baseline_6_1_top1": {"is": bi, "oos": bo},
        "spy":                {"is": si, "oos": so},
        "h386_var_a_ref":    {"is": h386a_i, "oos": h386a_o},
    }
    confirmed_variants = []

    for var_id, cfg in variants.items():
        rets = backtest(monthly_px, cfg["signal"], cfg["top_n"])
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        pass_gate = vo["sharpe"] > GATE_SHARPE and vo["maxdd"] > GATE_MAXDD
        flag = " ✓ PASS" if pass_gate else ""
        print(f"Var {var_id}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {cfg['desc']}{flag}")
        results[f"var_{var_id}"] = {
            "is": vi, "oos": vo, "desc": cfg["desc"], "pass_gate": pass_gate,
        }
        if pass_gate:
            confirmed_variants.append(var_id)

    # ── Annual breakdown for best variant ─────────────────────────────────────
    if confirmed_variants:
        best_v = max(confirmed_variants,
                     key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    else:
        best_v = max(variants.keys(),
                     key=lambda v: results.get(f"var_{v}", {}).get("oos", {}).get("sharpe", 0))
    print(f"\n=== Var {best_v} annual returns ===")
    rets_best = backtest(monthly_px, variants[best_v]["signal"], variants[best_v]["top_n"])
    ann_best  = rets_best.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for yr, ret in ann_best.items():
        tag = " ← OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    # ── Verdict ───────────────────────────────────────────────────────────────
    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} AND MaxDD > {GATE_MAXDD:.0%}")
    confirmed = len(confirmed_variants) > 0
    if confirmed:
        best_v2 = max(confirmed_variants,
                      key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        bsh = results[f"var_{best_v2}"]["oos"]["sharpe"]
        print(f"CONFIRMED — variants passing gate: {', '.join(confirmed_variants)}")
        print(f"Best variant: {best_v2}  OOS Sharpe {bsh:.3f}")
    else:
        bsh = results[f"var_{best_v}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best variant {best_v} OOS Sharpe {bsh:.3f}")

    out = {
        "hypothesis": "H393",
        "gate": {"oos_sharpe": GATE_SHARPE, "max_drawdown": GATE_MAXDD},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "results": results,
    }
    op = RESULT_DIR / "h393_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
