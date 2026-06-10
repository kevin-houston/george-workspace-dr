"""
H268 — LLM-Driven Factor Expression Search Loop
Inspired by Alpha-GPT (arXiv:2308.00016)

Universe:  30 large-cap S&P 500 stocks
IS:        2013-01-01 – 2020-12-31
OOS:       2021-01-01 – 2025-12-31
Portfolio: long top-6 by factor score, monthly rebalance, 10bp txn cost
Gate:      OOS Sharpe > 1.0  AND  OOS Corr vs SPY < 0.5
"""

import os, sys, json, re, traceback, warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT         = Path("/workspace/agent")
CACHE_FILE   = ROOT / "backtesting/cache/h268_price_data.parquet"
RESULTS_FILE = ROOT / "backtesting/results/h268_results.json"
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── universe & dates ───────────────────────────────────────────────────────────
UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","NVDA","AVGO","TSLA",
    "JPM","V","UNH","JNJ","XOM","WMT","HD","PG","MA","CVX",
    "ABBV","MRK","PEP","KO","BAC","LLY","TMO","COST","ACN",
    "MCD","DHR","LOW",
]
IS_START  = "2013-01-01"
IS_END    = "2020-12-31"
OOS_START = "2021-01-01"
OOS_END   = "2025-12-31"
DATA_START = "2012-01-01"   # extra year for warm-up

TOP_N     = 6              # stocks to hold
TXCOST_BP = 10             # basis points per trade (one-way)

# ── 1. DATA LOADER ─────────────────────────────────────────────────────────────

def load_data() -> dict:
    """Return dict of {field: DataFrame(dates x tickers)}.

    Cache layout uses a MultiIndex: (field, ticker).
    SPY is stored separately under field 'spy_close' with a single column 'SPY'.
    """
    if CACHE_FILE.exists():
        print(f"[data] loading cache from {CACHE_FILE}")
        raw = pd.read_parquet(CACHE_FILE)
        fields = raw.columns.get_level_values(0).unique().tolist()
        result = {}
        for f in fields:
            result[f] = raw[f].copy()
        # Validate SPY is present; if not, re-download
        if "spy_close" not in result or result["spy_close"].empty:
            print("[data] SPY missing from cache, re-downloading ...")
            CACHE_FILE.unlink()
            return load_data()
        return result

    print(f"[data] downloading {len(UNIVERSE)} universe tickers from yfinance ...")
    raw_uni = yf.download(
        UNIVERSE,
        start=DATA_START,
        end="2026-01-01",
        auto_adjust=True,
        progress=False,
    )

    data = {}
    keep_map = {"Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume"}

    if isinstance(raw_uni.columns, pd.MultiIndex):
        for yf_field, field_name in keep_map.items():
            if yf_field in raw_uni.columns.get_level_values(0):
                data[field_name] = raw_uni[yf_field].copy()
    else:
        # Single ticker fallback
        for yf_field, field_name in keep_map.items():
            if yf_field in raw_uni.columns:
                data[field_name] = raw_uni[[yf_field]]

    print("[data] downloading SPY ...")
    spy_raw = yf.download("SPY", start=DATA_START, end="2026-01-01",
                          auto_adjust=True, progress=False)
    if isinstance(spy_raw.columns, pd.MultiIndex):
        spy_close = spy_raw["Close"].copy()
        if isinstance(spy_close, pd.DataFrame):
            spy_close = spy_close.iloc[:, 0]
    else:
        spy_close = spy_raw["Close"] if "Close" in spy_raw.columns else spy_raw.iloc[:, 0]
    data["spy_close"] = spy_close.to_frame("SPY")

    # Cache: flatten to parquet with MultiIndex columns (field, ticker)
    frames = {f: df for f, df in data.items() if df is not None}
    combined = pd.concat(frames, axis=1)
    combined.to_parquet(CACHE_FILE)
    print(f"[data] cached to {CACHE_FILE}")
    return data


# ── 2. EXPRESSION PRIMITIVES ───────────────────────────────────────────────────

def cs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank, 0-1 normalised."""
    return df.rank(axis=1, pct=True)

def rolling_mean(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.rolling(n, min_periods=max(1, n // 2)).mean()

def rolling_std(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.rolling(n, min_periods=max(1, n // 2)).std()

def rolling_max(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.rolling(n, min_periods=max(1, n // 2)).max()

def delta(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df - df.shift(n)

def zscore(df: pd.DataFrame, n: int) -> pd.DataFrame:
    mu  = rolling_mean(df, n)
    sig = rolling_std(df, n)
    return (df - mu) / (sig + 1e-9)


def make_env(data: dict) -> dict:
    """Build the evaluation namespace."""
    close  = data["close"]
    open_  = data["open"]
    high   = data["high"]
    low    = data["low"]
    volume = data["volume"]

    r1d  = close.pct_change(1)
    r5d  = close.pct_change(5)
    r21d = close.pct_change(21)

    env = {
        # raw series
        "close":   close,
        "open":    open_,
        "high":    high,
        "low":     low,
        "volume":  volume,
        # derived returns
        "returns_1d":  r1d,
        "returns_5d":  r5d,
        "returns_21d": r21d,
        # functions
        "cs_rank":      cs_rank,
        "rolling_mean": rolling_mean,
        "rolling_std":  rolling_std,
        "rolling_max":  rolling_max,
        "delta":        delta,
        "zscore":       zscore,
        # safe numeric builtins
        "abs": abs,
        "np":  np,
    }
    return env


# ── 3. EXPRESSION EVALUATOR ────────────────────────────────────────────────────

ALLOWED_NAMES = {
    "close","open","high","low","volume",
    "returns_1d","returns_5d","returns_21d",
    "cs_rank","rolling_mean","rolling_std","rolling_max",
    "delta","zscore",
    "abs","np",
}

_IDENT_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _safe_check(expr: str) -> None:
    """Raise ValueError if expr references any name not in ALLOWED_NAMES."""
    names = set(_IDENT_RE.findall(expr))
    bad = names - ALLOWED_NAMES
    if bad:
        raise ValueError(f"Disallowed names in expression: {bad}")


def eval_factor(expr_str: str, env: dict) -> pd.DataFrame:
    """
    Safely evaluate expr_str in the primitive namespace.
    Returns a DataFrame (dates x tickers) of factor scores.
    """
    _safe_check(expr_str)
    result = eval(expr_str, {"__builtins__": {}}, env)  # noqa: S307
    if not isinstance(result, pd.DataFrame):
        raise TypeError(f"Expression must return a DataFrame, got {type(result)}")
    return result


# ── 4. BACKTEST ENGINE ─────────────────────────────────────────────────────────

def run_backtest(factor_df: pd.DataFrame, data: dict) -> dict:
    """
    Monthly rebalance: go long top-N stocks by factor score.
    Deduct 10bp per position changed.
    """
    close = data["close"]
    spy_df = data.get("spy_close")

    # Resample factor to month-end
    factor_m = factor_df.resample("ME").last()
    close_m  = close.resample("ME").last()

    # Monthly returns
    ret_m = close_m.pct_change()

    # Align indices
    common_idx = factor_m.index.intersection(ret_m.index)
    factor_m = factor_m.reindex(common_idx)
    ret_m    = ret_m.reindex(common_idx)

    port_dates   = []
    port_returns = []
    prev_positions = set()

    for i in range(1, len(common_idx)):
        date   = common_idx[i]
        prev_d = common_idx[i - 1]

        scores = factor_m.loc[prev_d].dropna()
        if len(scores) < TOP_N:
            continue

        top_stocks = set(scores.nlargest(TOP_N).index)
        avail = [t for t in top_stocks if t in ret_m.columns and not np.isnan(ret_m.loc[date, t])]
        if not avail:
            continue

        gross = ret_m.loc[date, avail].mean()

        # turnover: fraction of portfolio that changed
        turnover = len(top_stocks.symmetric_difference(prev_positions)) / TOP_N
        txcost   = turnover * (TXCOST_BP / 10_000)

        port_dates.append(date)
        port_returns.append(gross - txcost)
        prev_positions = top_stocks

    port = pd.Series(port_returns, index=port_dates, name="port").dropna()

    def sharpe(s: pd.Series) -> float:
        if len(s) < 6 or s.std() == 0:
            return np.nan
        return float((s.mean() / s.std()) * np.sqrt(12))

    def max_dd(s: pd.Series) -> float:
        if len(s) == 0:
            return np.nan
        cum = (1 + s).cumprod()
        roll_max = cum.cummax()
        dd = (cum - roll_max) / roll_max
        return float(dd.min())

    is_mask  = (port.index >= IS_START)  & (port.index <= IS_END)
    oos_mask = (port.index >= OOS_START) & (port.index <= OOS_END)

    is_ret  = port[is_mask]
    oos_ret = port[oos_mask]

    # SPY OOS correlation
    corr_spy = np.nan
    if spy_df is not None and not spy_df.empty:
        spy_col = spy_df.iloc[:, 0]  # take first column regardless of name
        spy_m = spy_col.resample("ME").last().pct_change()
        common_oos = oos_ret.index.intersection(spy_m.index)
        if len(common_oos) > 12:
            corr_spy = float(oos_ret.reindex(common_oos).corr(spy_m.reindex(common_oos)))

    return {
        "is_sharpe":    sharpe(is_ret),
        "oos_sharpe":   sharpe(oos_ret),
        "corr_spy":     corr_spy,
        "oos_maxdd":    max_dd(oos_ret),
        "oos_n_months": int(oos_mask.sum()),
    }


# ── 5. LLM EXPRESSION GENERATOR ───────────────────────────────────────────────

PRIMITIVES_DOC = """
Available primitives (all operate on DataFrames indexed by date, columns = tickers):

  close, open, high, low, volume          -- raw OHLCV DataFrames
  returns_1d, returns_5d, returns_21d     -- close.pct_change(1/5/21)

  cs_rank(df)                             -- cross-sectional percentile rank [0,1]
  rolling_mean(df, n)                     -- rolling n-period mean
  rolling_std(df, n)                      -- rolling n-period std
  rolling_max(df, n)                      -- rolling n-period max
  delta(df, n)                            -- df - df.shift(n)
  zscore(df, n)                           -- (df - rolling_mean) / rolling_std over n periods

A factor expression must return a DataFrame; higher score = more bullish.
Example valid expressions:
  cs_rank(-returns_21d)
  cs_rank(returns_21d / (rolling_std(returns_1d, 21) + 0.001))
  cs_rank(volume / rolling_mean(volume, 21))
""".strip()

SYSTEM_PROMPT = f"""You are an expert quantitative researcher designing equity trading signals.
Your goal is to write Python expressions for cross-sectional stock factors.
Each expression must:
  1. Use ONLY the primitives listed below (no imports, no external data, no lambda, no if/else).
  2. Return a DataFrame (dates x tickers) where higher = more bullish.
  3. Be a single Python expression (no assignments, no def, no multi-line).
  4. Be novel -- avoid exact duplicates of expressions already tried.
  5. Use only these exact function names: cs_rank, rolling_mean, rolling_std, rolling_max, delta, zscore, abs, np.

{PRIMITIVES_DOC}

When asked, respond with ONLY a JSON array of exactly 5 strings -- no prose, no markdown code fences:
["expression1", "expression2", "expression3", "expression4", "expression5"]
"""


def llm_generate_expressions(prior_results: list, domain_hint: str, client) -> list:
    """Call GPT-4o-mini, return up to 5 new factor expression strings."""

    valid = [r for r in prior_results if not np.isnan(r.get("oos_sharpe", np.nan))]
    valid.sort(key=lambda x: x["oos_sharpe"], reverse=True)
    top_3    = valid[:3]
    bottom_3 = valid[-3:] if len(valid) >= 6 else []

    prior_text = ""
    if top_3:
        prior_text += "\nTop-performing so far (try to build on or contrast these):\n"
        for r in top_3:
            prior_text += f"  OOS={r['oos_sharpe']:.3f}, IS={r['is_sharpe']:.3f}  -> {r['expr']}\n"
    if bottom_3:
        prior_text += "\nWorst-performing (avoid similar logic):\n"
        for r in bottom_3:
            prior_text += f"  OOS={r['oos_sharpe']:.3f}  -> {r['expr']}\n"
    if not prior_text:
        prior_text = "\n(No prior results yet -- explore freely.)\n"

    user_prompt = (
        f"Domain focus: {domain_hint}\n"
        f"{prior_text}\n"
        "Generate 5 new, diverse factor expressions. "
        "Return ONLY a JSON array of 5 strings, no code fences, no explanation."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.9,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content.strip()
        # strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
        raw = raw.strip()
        exprs = json.loads(raw)
        if isinstance(exprs, list):
            return [str(e).strip() for e in exprs[:5]]
    except Exception as exc:
        print(f"  [llm] generation error: {exc}")
        # Try to extract JSON array from anywhere in the response
        try:
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if match:
                exprs = json.loads(match.group())
                if isinstance(exprs, list):
                    return [str(e).strip() for e in exprs[:5]]
        except Exception:
            pass
    return []


# ── 6. MAIN LOOP ───────────────────────────────────────────────────────────────

SEED_EXPRESSIONS = [
    "cs_rank(-returns_21d)",
    "cs_rank(returns_21d / (rolling_std(returns_1d, 21) + 0.001))",
    "cs_rank(volume / rolling_mean(volume, 21))",
]

DOMAIN_HINTS = [
    "contrarian/reversal signals and short-term mean reversion",
    "volume-price divergence, liquidity surges, and turnover anomalies",
    "risk-adjusted momentum, volatility normalisation, and Sharpe-like factors",
]

LLM_ITERATIONS = 3
EXPRS_PER_ITER  = 5


def main():
    print("=" * 72)
    print("H268 -- LLM Factor Expression Search Loop (Alpha-GPT inspired)")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    # ── load data ──────────────────────────────────────────────────────────────
    data = load_data()
    env  = make_env(data)
    print(f"[data] fields: {[k for k in data if data[k] is not None]}")
    print(f"[data] dates : {data['close'].index[0].date()} -> {data['close'].index[-1].date()}")
    print(f"[data] tickers: {list(data['close'].columns[:5])} ... ({data['close'].shape[1]} total)")

    # ── init OpenAI client ─────────────────────────────────────────────────────
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[llm] WARNING: OPENAI_API_KEY not set -- LLM iterations will be skipped")
        client = None
    else:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        print("[llm] OpenAI client ready (model: gpt-4o-mini)")

    # ── evaluate expressions ───────────────────────────────────────────────────
    all_results = []
    tested_exprs = set()

    def evaluate_expr(expr: str, label: str = "") -> dict:
        if expr in tested_exprs:
            print(f"  [skip] duplicate: {expr[:70]}")
            return None
        tested_exprs.add(expr)
        tag = label or f"expr_{len(all_results)+1}"
        try:
            factor_df = eval_factor(expr, env)
            # sanity: must have enough non-NaN values
            valid_frac = factor_df.notna().mean().mean()
            if valid_frac < 0.3:
                raise ValueError(f"Too many NaNs: {valid_frac:.1%}")
            metrics = run_backtest(factor_df, data)
            result = {"expr": expr, "label": tag, **metrics}

            is_s  = metrics.get("is_sharpe",  np.nan)
            oos_s = metrics.get("oos_sharpe", np.nan)
            corr  = metrics.get("corr_spy",   np.nan)
            mdd   = metrics.get("oos_maxdd",  np.nan)

            gate = (
                not np.isnan(oos_s) and oos_s > 1.0 and
                not np.isnan(corr)  and corr  < 0.5
            )
            gate_str = "  *** PASS ***" if gate else ""
            print(
                f"  [{tag:15s}] IS={is_s:+.3f}  OOS={oos_s:+.3f}  "
                f"Corr={corr:+.3f}  MDD={mdd:.1%}{gate_str}"
            )
            print(f"             expr: {expr[:80]}")
            return result

        except Exception as exc:
            print(f"  [FAIL] {expr[:70]!r}")
            print(f"         reason: {exc}")
            return {
                "expr": expr, "label": tag, "error": str(exc),
                "is_sharpe": np.nan, "oos_sharpe": np.nan,
                "corr_spy": np.nan, "oos_maxdd": np.nan,
            }

    # ── seed round ─────────────────────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print(f"[round 0] Evaluating {len(SEED_EXPRESSIONS)} seed expressions ...")
    for i, expr in enumerate(SEED_EXPRESSIONS):
        r = evaluate_expr(expr, f"seed_{i+1}")
        if r:
            all_results.append(r)

    # ── LLM rounds ─────────────────────────────────────────────────────────────
    for iteration in range(1, LLM_ITERATIONS + 1):
        hint = DOMAIN_HINTS[(iteration - 1) % len(DOMAIN_HINTS)]
        print(f"\n{'─'*72}")
        print(f"[round {iteration}] LLM iteration -- domain: '{hint}'")

        if client is None:
            print("  [skip] no OpenAI client")
            continue

        new_exprs = llm_generate_expressions(all_results, hint, client)
        print(f"  [llm] generated {len(new_exprs)} expressions:")
        for e in new_exprs:
            print(f"    . {e[:80]}")

        if not new_exprs:
            print("  [llm] nothing generated, skipping")
            continue

        for j, expr in enumerate(new_exprs):
            r = evaluate_expr(expr, f"llm{iteration}_{j+1}")
            if r:
                all_results.append(r)

    # ── rank & filter ──────────────────────────────────────────────────────────
    valid_results = [
        r for r in all_results
        if "error" not in r and not np.isnan(r.get("oos_sharpe", np.nan))
    ]
    valid_results.sort(key=lambda x: x["oos_sharpe"], reverse=True)

    passing = [
        r for r in valid_results
        if r["oos_sharpe"] > 1.0 and r.get("corr_spy", 1.0) < 0.5
    ]

    # ── results table ──────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print("ALL TESTED EXPRESSIONS -- sorted by OOS Sharpe")
    print(f"{'='*72}")
    print(f"{'#':>3}  {'IS':>6}  {'OOS':>6}  {'Corr':>6}  {'MDD':>7}  Expression")
    print("─" * 72)
    for i, r in enumerate(valid_results, 1):
        gate_flag = " *" if (r["oos_sharpe"] > 1.0 and r.get("corr_spy", 1.0) < 0.5) else ""
        print(
            f"{i:>3}  {r['is_sharpe']:>+6.3f}  {r['oos_sharpe']:>+6.3f}  "
            f"{r.get('corr_spy', np.nan):>+6.3f}  {r.get('oos_maxdd', np.nan):>7.1%}"
            f"  {r['expr'][:52]}{gate_flag}"
        )

    failed = [r for r in all_results if "error" in r]
    if failed:
        print(f"\n[failed expressions: {len(failed)}]")
        for r in failed:
            print(f"  . {r['expr'][:60]} -- {r['error'][:60]}")

    # ── summary ────────────────────────────────────────────────────────────────
    n_tested = len(valid_results)
    n_failed = len(failed)
    n_pass   = len(passing)

    print(f"\n{'='*72}")
    print("SUMMARY")
    print(f"{'='*72}")
    print(f"  Total expressions evaluated      : {n_tested}")
    print(f"  Failed (eval errors)             : {n_failed}")
    print(f"  Passing gate (OOS>1.0, Corr<0.5): {n_pass}")
    print()

    if passing:
        print("TOP-3 PASSING EXPRESSIONS:")
        for i, r in enumerate(passing[:3], 1):
            print(f"  {i}. IS={r['is_sharpe']:+.3f}  OOS={r['oos_sharpe']:+.3f}  "
                  f"Corr={r['corr_spy']:+.3f}  MDD={r['oos_maxdd']:.1%}")
            print(f"     {r['expr']}")
    else:
        print("No expressions passed the gate (OOS Sharpe > 1.0, Corr < 0.5).")
        print("Top-3 by OOS Sharpe (best available):")
        for i, r in enumerate(valid_results[:3], 1):
            print(f"  {i}. IS={r['is_sharpe']:+.3f}  OOS={r['oos_sharpe']:+.3f}  "
                  f"Corr={r.get('corr_spy', np.nan):+.3f}  MDD={r.get('oos_maxdd', np.nan):.1%}")
            print(f"     {r['expr']}")

    # ── save results ───────────────────────────────────────────────────────────
    def safe_float(x):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return None
        return round(float(x), 6)

    output = {
        "hypothesis": "H268",
        "description": "LLM-driven factor expression search loop (Alpha-GPT inspired)",
        "run_date": datetime.now().isoformat(),
        "universe": UNIVERSE,
        "is_period": [IS_START, IS_END],
        "oos_period": [OOS_START, OOS_END],
        "top_n": TOP_N,
        "txcost_bp": TXCOST_BP,
        "gate": {"oos_sharpe_min": 1.0, "corr_spy_max": 0.5},
        "n_tested": n_tested,
        "n_failed": n_failed,
        "n_passing": n_pass,
        "all_results": [
            {
                "rank": i + 1,
                "expr": r["expr"],
                "label": r.get("label", ""),
                "is_sharpe":   safe_float(r.get("is_sharpe")),
                "oos_sharpe":  safe_float(r.get("oos_sharpe")),
                "corr_spy":    safe_float(r.get("corr_spy")),
                "oos_maxdd":   safe_float(r.get("oos_maxdd")),
                "passes_gate": bool(
                    r.get("oos_sharpe", 0) > 1.0 and
                    r.get("corr_spy",   1.0) < 0.5
                ),
            }
            for i, r in enumerate(valid_results)
        ],
        "passing_expressions": [
            {
                "rank": i + 1,
                "expr":       r["expr"],
                "is_sharpe":  safe_float(r.get("is_sharpe")),
                "oos_sharpe": safe_float(r.get("oos_sharpe")),
                "corr_spy":   safe_float(r.get("corr_spy")),
                "oos_maxdd":  safe_float(r.get("oos_maxdd")),
            }
            for i, r in enumerate(passing)
        ],
        "verdict": "CONFIRMED" if n_pass > 0 else "NOT CONFIRMED",
    }

    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n[saved] {RESULTS_FILE}")
    print(f"[verdict] H268 {output['verdict']}")

    return output


if __name__ == "__main__":
    main()
