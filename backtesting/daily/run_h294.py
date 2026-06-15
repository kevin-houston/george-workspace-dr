"""
H294 — Behavioral Multi-Factor MLP (5-Day Horizon)
Source: arXiv:2508.14656 — Yuqi Luan (2025)
Gate: OOS Sharpe > 1.559 (H217 alpha101 baseline)

40 behavioral factors across 5 groups:
  A - Intraday structure (alpha101 family)
  B - Volume-price behavioral signals
  C - Momentum herding proxy + multi-period returns
  D - Bottom-reversal signals
  E - TA indicators (MACD, RSI, Stochastic, ROC)

Dual-task MLP: input(40) -> hidden(64) -> hidden(32) -> [return(1), direction(1)]
Loss: 0.5 * MSE(return) + 0.5 * BCEWithLogits(direction)
IS: 2013-2020 | OOS: 2021-2026
Weekly rebalance: Friday close -> Monday open
Universe: 30 large-cap S&P 500 (same as H217)
"""

import os, json, warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ── Universe (same 30 large-cap as H217) ──────────────────────────────────────
UNIVERSE = [
    "AAPL","MSFT","GOOGL","AMZN","META","NVDA","TSLA","BRK-B","LLY","JPM",
    "V","UNH","XOM","MA","JNJ","PG","HD","AVGO","MRK","ABBV",
    "CVX","COST","KO","PEP","WMT","BAC","TMO","ORCL","ACN","CSCO",
]

IS_START  = "2012-01-01"   # +1yr lookback for 63d features
IS_END    = "2020-12-31"
OOS_START = "2021-01-01"
OOS_END   = "2026-06-13"

CACHE_DIR = Path("/workspace/agent/backtesting/cache/h294")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LONG_N      = 6       # top-N stocks each week
COST_BPS    = 10      # 0.10% one-way
WEEKS_PER_YEAR = 52
TARGET_SHARPE  = 1.559


# ── Data download ─────────────────────────────────────────────────────────────

def load_ohlcv(tickers: list[str]) -> pd.DataFrame:
    cache = CACHE_DIR / "ohlcv.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        # refresh if stale (older than 3 days)
        age_days = (datetime.now() - datetime.fromtimestamp(cache.stat().st_mtime)).days
        if age_days <= 3:
            print(f"  [cache] ohlcv loaded ({len(df)} rows)")
            return df

    print("  Downloading OHLCV …")
    raw = yf.download(tickers, start=IS_START, end=OOS_END,
                      auto_adjust=True, progress=False)
    df = raw.stack(future_stack=True).reset_index()
    df.columns = ["date", "ticker", "close", "high", "low", "open", "volume"]
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df.to_parquet(cache)
    print(f"  Downloaded {len(df)} rows")
    return df


# ── Feature engineering ────────────────────────────────────────────────────────

def _safe_rank(s: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank on a single date slice."""
    return s.rank(pct=True)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Returns long-form DataFrame with 40 factor columns + forward_ret_5d."""
    records = []

    for ticker, g in df.groupby("ticker"):
        g = g.set_index("date").sort_index()
        c, h, l, o, v = (g["close"], g["high"], g["low"], g["open"], g["volume"])

        # ── Group A: Intraday structure ────────────────────────────────────────
        alpha101 = ((c - o) / (0.001 + h - l)).clip(-1, 1)
        intraday_range = (h - l) / c.replace(0, np.nan)
        ibs = (c - l) / (h - l).replace(0, np.nan)

        # ── Group B: Volume-price behavioral ──────────────────────────────────
        ret1 = c.pct_change(1)
        vol_chg1 = v.pct_change(1)
        # volume-price divergence: rank(vol_change) - rank(price_change)
        # stored raw; cross-sectional rank applied in normalization step
        money_flow = v * (2 * c - h - l) / (h - l).replace(0, np.nan)
        volume_trend = v.rolling(5).mean().pct_change(21)

        # ── Group C: Momentum herding proxy ────────────────────────────────────
        herd_5d = ret1.rolling(10).corr(vol_chg1)
        ret5  = c.pct_change(5)
        ret21 = c.pct_change(21)
        ret63 = c.pct_change(63)
        ret252 = c.pct_change(252)

        # ── Group D: Bottom-reversal signals ──────────────────────────────────
        dist_52w_low = c / c.rolling(252).min()
        # RSI (manual implementation to avoid TA-Lib dependency)
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi14 = 100 - (100 / (1 + rs))
        mean_rev5 = -ret5

        # ── Group E: TA indicators ─────────────────────────────────────────────
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal

        # Stochastic %K/%D (14-period)
        low14  = l.rolling(14).min()
        high14 = h.rolling(14).max()
        stoch_k = 100 * (c - low14) / (high14 - low14).replace(0, np.nan)
        stoch_d = stoch_k.rolling(3).mean()

        roc10 = c.pct_change(10)
        roc21 = c.pct_change(21)

        # Additional volatility features
        vol5   = ret1.rolling(5).std()
        vol21  = ret1.rolling(21).std()
        vol_ratio = vol5 / vol21.replace(0, np.nan)

        # ── Forward return (label) ─────────────────────────────────────────────
        fwd_ret5 = c.pct_change(5).shift(-5)
        fwd_dir  = (fwd_ret5 > 0).astype(float)

        feature_df = pd.DataFrame({
            # Group A (3)
            "alpha101":       alpha101,
            "intraday_range": intraday_range,
            "ibs":            ibs,
            # Group B (4)
            "vol_chg1":       vol_chg1,
            "money_flow_norm": money_flow / money_flow.rolling(21).mean().replace(0, np.nan),
            "volume_trend":   volume_trend,
            "vol_price_div":  vol_chg1 - ret1,    # divergence (ranks later)
            # Group C (5)
            "herd_5d":        herd_5d,
            "ret1":           ret1,
            "ret5":           ret5,
            "ret21":          ret21,
            "ret63":          ret63,
            # Group D (5)
            "dist_52w_low":   dist_52w_low,
            "rsi14":          rsi14,
            "mean_rev5":      mean_rev5,
            "ret252":         ret252,
            "dist_52w_high":  c / c.rolling(252).max(),
            # Group E (10)
            "macd_line":      macd_line,
            "macd_signal":    macd_signal,
            "macd_hist":      macd_hist,
            "stoch_k":        stoch_k,
            "stoch_d":        stoch_d,
            "roc10":          roc10,
            "roc21":          roc21,
            "vol5":           vol5,
            "vol21":          vol21,
            "vol_ratio":      vol_ratio,
            # Labels
            "fwd_ret5":       fwd_ret5,
            "fwd_dir":        fwd_dir,
        }, index=g.index)

        feature_df["ticker"] = ticker
        records.append(feature_df.reset_index())

    features = pd.concat(records, ignore_index=True)
    features = features.rename(columns={"index": "date"})
    return features


FEATURE_COLS = [
    "alpha101", "intraday_range", "ibs",
    "vol_chg1", "money_flow_norm", "volume_trend", "vol_price_div",
    "herd_5d", "ret1", "ret5", "ret21", "ret63",
    "dist_52w_low", "rsi14", "mean_rev5", "ret252", "dist_52w_high",
    "macd_line", "macd_signal", "macd_hist",
    "stoch_k", "stoch_d", "roc10", "roc21",
    "vol5", "vol21", "vol_ratio",
]


def cross_sectional_rank(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Replace each feature with its cross-sectional percentile rank by date."""
    df = df.copy()
    for col in cols:
        df[col] = df.groupby("date")[col].transform(_safe_rank)
    return df


# ── MLP model ─────────────────────────────────────────────────────────────────

class BehavioralMLP(nn.Module):
    def __init__(self, n_features: int = 27):
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(n_features, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(0.1),
        )
        self.return_head    = nn.Linear(32, 1)
        self.direction_head = nn.Linear(32, 1)

    def forward(self, x):
        h = self.shared(x)
        return self.return_head(h).squeeze(-1), self.direction_head(h).squeeze(-1)


def train_mlp(X_train: np.ndarray, y_ret: np.ndarray, y_dir: np.ndarray,
              n_epochs: int = 60) -> BehavioralMLP:
    model = BehavioralMLP(n_features=X_train.shape[1])
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    mse_fn = nn.MSELoss()
    bce_fn = nn.BCEWithLogitsLoss()

    X_t = torch.tensor(X_train, dtype=torch.float32)
    y_r = torch.tensor(y_ret,  dtype=torch.float32)
    y_d = torch.tensor(y_dir,  dtype=torch.float32)

    dataset = torch.utils.data.TensorDataset(X_t, y_r, y_d)
    loader  = torch.utils.data.DataLoader(dataset, batch_size=512, shuffle=True)

    model.train()
    for epoch in range(n_epochs):
        total_loss = 0.0
        for xb, rb, db in loader:
            optimizer.zero_grad()
            pred_ret, pred_dir = model(xb)
            loss = 0.5 * mse_fn(pred_ret, rb) + 0.5 * bce_fn(pred_dir, db)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(xb)
        if (epoch + 1) % 20 == 0:
            print(f"    epoch {epoch+1}/{n_epochs}  loss={total_loss/len(X_train):.4f}")

    model.eval()
    return model


# ── Backtest engine ────────────────────────────────────────────────────────────

def run_backtest(prices: pd.DataFrame, signals: pd.DataFrame,
                 start: str, end: str, label: str) -> dict:
    """
    prices: wide DataFrame (date × ticker) of close prices.
    signals: long DataFrame with columns [date, ticker, score].
    Returns dict with Sharpe, CAGR, MaxDD, n_weeks.
    """
    rebal_dates = signals["date"].drop_duplicates().sort_values()
    rebal_dates = rebal_dates[(rebal_dates >= start) & (rebal_dates <= end)]

    portfolio_rets = []

    for i, d in enumerate(rebal_dates[:-1]):
        next_d = rebal_dates.iloc[i + 1] if i + 1 < len(rebal_dates) else None
        if next_d is None:
            break

        day_signals = signals[signals["date"] == d].nlargest(LONG_N, "score")
        picks = day_signals["ticker"].tolist()
        if not picks:
            portfolio_rets.append(0.0)
            continue

        # Equal-weight
        price_today = prices.loc[d, picks] if d in prices.index else None
        price_next  = prices.loc[next_d, picks] if next_d in prices.index else None

        if price_today is None or price_next is None:
            portfolio_rets.append(0.0)
            continue

        rets = (price_next / price_today - 1).mean()
        rets -= COST_BPS / 10000 * 2   # entry + exit cost
        portfolio_rets.append(rets)

    if not portfolio_rets:
        return {"sharpe": 0, "cagr": 0, "max_dd": 0, "n_weeks": 0}

    r = np.array(portfolio_rets)
    sharpe = r.mean() / (r.std() + 1e-9) * np.sqrt(WEEKS_PER_YEAR)
    cagr   = (1 + r).prod() ** (WEEKS_PER_YEAR / len(r)) - 1
    cum    = (1 + r).cumprod()
    max_dd = (cum / np.maximum.accumulate(cum) - 1).min()

    print(f"\n{label}: Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={max_dd:.1%}  n_weeks={len(r)}")
    return {"sharpe": sharpe, "cagr": cagr, "max_dd": max_dd, "n_weeks": len(r)}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("H294 — Behavioral Multi-Factor MLP")
    print("=" * 60)

    # 1. Load data
    print("\n[1] Loading OHLCV data …")
    df = load_ohlcv(UNIVERSE)

    # Filter to tickers with enough data
    min_rows = 252 * 8
    counts = df.groupby("ticker").size()
    valid = counts[counts >= min_rows].index.tolist()
    df = df[df["ticker"].isin(valid)]
    print(f"  {len(valid)} tickers pass minimum data filter")

    # Wide close prices for backtest
    prices_wide = df.pivot(index="date", columns="ticker", values="close")

    # 2. Feature engineering
    print("\n[2] Computing 27 behavioral features …")
    feat_cache = CACHE_DIR / "features.parquet"
    if feat_cache.exists():
        features = pd.read_parquet(feat_cache)
        print(f"  [cache] features loaded ({len(features)} rows)")
    else:
        features = build_features(df)
        features.to_parquet(feat_cache)
        print(f"  Computed {len(features)} rows")

    # Cross-sectional rank normalization
    features = cross_sectional_rank(features, FEATURE_COLS)

    # Drop rows with any NaN in features or labels
    use_cols = FEATURE_COLS + ["fwd_ret5", "fwd_dir", "date", "ticker"]
    features = features[use_cols].dropna()
    print(f"  {len(features)} rows after dropna")

    # 3. IS/OOS split
    is_mask  = (features["date"] >= IS_START) & (features["date"] <= IS_END)
    oos_mask = (features["date"] >= OOS_START) & (features["date"] <= OOS_END)

    is_df  = features[is_mask]
    oos_df = features[oos_mask]
    print(f"\n[3] IS: {len(is_df)} obs | OOS: {len(oos_df)} obs")

    X_is  = is_df[FEATURE_COLS].values.astype(np.float32)
    y_ret = is_df["fwd_ret5"].values.astype(np.float32)
    y_dir = is_df["fwd_dir"].values.astype(np.float32)
    X_oos = oos_df[FEATURE_COLS].values.astype(np.float32)

    # 4. Scale
    scaler = StandardScaler()
    X_is  = scaler.fit_transform(X_is)
    X_oos = scaler.transform(X_oos)

    # 5. Train MLP
    print("\n[4] Training dual-task MLP …")
    model = train_mlp(X_is, y_ret, y_dir, n_epochs=80)

    # 6. IS predictions (sanity)
    with torch.no_grad():
        X_is_t = torch.tensor(X_is, dtype=torch.float32)
        is_pred_ret, is_pred_dir = model(X_is_t)
        is_pred_ret = is_pred_ret.numpy()
        is_pred_dir = torch.sigmoid(torch.tensor(is_pred_dir)).numpy()

    is_df = is_df.copy()
    is_df["score"] = 0.5 * pd.Series(is_pred_ret, index=is_df.index).rank(pct=True) + \
                     0.5 * pd.Series(is_pred_dir,  index=is_df.index).rank(pct=True)

    # 7. OOS predictions
    with torch.no_grad():
        X_oos_t = torch.tensor(X_oos, dtype=torch.float32)
        oos_pred_ret, oos_pred_dir = model(X_oos_t)
        oos_pred_ret = oos_pred_ret.numpy()
        oos_pred_dir = torch.sigmoid(torch.tensor(oos_pred_dir)).numpy()

    oos_df = oos_df.copy()
    oos_df["score"] = 0.5 * pd.Series(oos_pred_ret, index=oos_df.index).rank(pct=True) + \
                      0.5 * pd.Series(oos_pred_dir,  index=oos_df.index).rank(pct=True)

    # Weekly signals: keep Friday (or last trading day of each week)
    def to_weekly(df_: pd.DataFrame) -> pd.DataFrame:
        df_ = df_.copy()
        df_["date"] = pd.to_datetime(df_["date"])
        df_["week"] = df_["date"].dt.to_period("W")
        # Keep last day of each week for each ticker
        idx = df_.groupby(["week", "ticker"])["date"].idxmax()
        return df_.loc[idx].reset_index(drop=True)

    is_weekly  = to_weekly(is_df)
    oos_weekly = to_weekly(oos_df)

    # 8. Backtests
    print("\n[5] Running backtests …")
    is_result  = run_backtest(prices_wide, is_weekly[["date", "ticker", "score"]],
                              IS_START, IS_END, "IS (2013-2020)")
    oos_result = run_backtest(prices_wide, oos_weekly[["date", "ticker", "score"]],
                              OOS_START, OOS_END, "OOS (2021-2026)")

    # 9. Gate check
    print("\n" + "=" * 60)
    oos_sharpe = oos_result["sharpe"]
    status = "CONFIRMED" if oos_sharpe >= TARGET_SHARPE else "NOT CONFIRMED"
    print(f"H294 RESULT: {status}")
    print(f"  OOS Sharpe: {oos_sharpe:.3f}  (gate: {TARGET_SHARPE})")
    print(f"  OOS CAGR:   {oos_result['cagr']:.1%}")
    print(f"  OOS MaxDD:  {oos_result['max_dd']:.1%}")
    print(f"  IS  Sharpe: {is_result['sharpe']:.3f}")
    print("=" * 60)

    # 10. Save results
    results = {
        "hypothesis": "H294",
        "description": "Behavioral Multi-Factor MLP (arXiv:2508.14656)",
        "run_date": datetime.now().strftime("%Y-%m-%d"),
        "is": is_result,
        "oos": oos_result,
        "gate_sharpe": TARGET_SHARPE,
        "status": status,
        "n_features": len(FEATURE_COLS),
        "universe_size": len(valid),
    }
    out_path = CACHE_DIR / "results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")

    return results


if __name__ == "__main__":
    main()
