"""
H195 — STORM: Dual VQ-VAE Spatio-Temporal Factor Model
=======================================================
Inspired by: arXiv:2412.09468 (WSDM '26)
"STORM: A Spatio-Temporal Factor Model Based on Dual VQ-VAE for Financial Trading"

Architecture:
  - Time-series encoder (LSTM): encodes 20-day daily return sequences per stock
  - Cross-sectional encoder (GCN): encodes factor cross-section using correlation graph
  - Dual VQ-VAE: quantizes each latent via separate codebooks (64 vectors each)
  - Commitment loss enforces orthogonality between TS and CS representations
  - Linear predictor: combined quantized latent → next-month return score

Strategy:
  - Universe: same 30 large-cap stocks as H188/H191/H192
  - Long top-6 by predicted score, equal-weight, monthly rebalance
  - IS: 2015–2021, OOS: 2022–2024
  - Baseline: H188 (Sharpe 1.07), target H195 > 1.2

Features:
  - TS branch: 20-day daily log-returns (1-dim) per stock
  - CS branch: [momentum_12m, reversal_1m, realized_vol_21d, prox_52wk]
"""

import warnings
warnings.filterwarnings("ignore")

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# PyTorch imports — fail early with helpful message if not installed
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except ImportError:
    sys.exit("PyTorch not found. Install with: pip install torch --index-url https://download.pytorch.org/whl/cpu")

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"

UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD":  "Information Technology",
    "V":    "Financials",             "MA":   "Financials",
    "BAC":  "Financials",             "WFC":  "Financials",  "JPM": "Financials",
    "UNH":  "Health Care",            "LLY":  "Health Care",
    "PFE":  "Health Care",            "JNJ":  "Health Care", "ABBV": "Health Care",
    "WMT":  "Consumer Staples",       "HD":   "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW":  "Consumer Discretionary",
    "COST": "Consumer Staples",       "CVX":  "Energy",      "XOM":  "Energy",
    "BA":   "Industrials",            "CAT":  "Industrials", "IBM":  "Information Technology",
}
UNIVERSE = list(UNIVERSE_SECTORS.keys())

DATA_START = "2013-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2015-01-01")
IS_END     = pd.Timestamp("2021-12-31")
OOS_START  = pd.Timestamp("2022-01-01")
OOS_END    = pd.Timestamp("2024-12-31")

TS_WINDOW  = 20   # trading days for LSTM lookback
N_LONG     = 6    # stocks in long portfolio
EPOCHS     = 150
LR         = 1e-3
HIDDEN_DIM = 32
LATENT_DIM = 16
N_EMBED    = 64   # codebook size per VQ-VAE
COMMIT_COST = 0.25
CORR_THRESH = 0.30  # edge threshold for correlation graph


# ─────────────────────────────────────────────────────────────────────────────
# STORM model components
# ─────────────────────────────────────────────────────────────────────────────

class TimeSeriesEncoder(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, latent_dim: int):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.proj = nn.Linear(hidden_dim, latent_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [N, T, input_dim]
        _, (h, _) = self.lstm(x)
        return self.proj(h[-1])  # [N, latent_dim]


class GraphEncoder(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, latent_dim: int):
        super().__init__()
        self.linear = nn.Linear(input_dim, hidden_dim)
        self.proj   = nn.Linear(hidden_dim, latent_dim)

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        # x: [N, input_dim], adj: [N, N] row-normalized
        h   = torch.relu(self.linear(x))
        deg = adj.sum(1, keepdim=True).clamp(min=1.0)
        agg = torch.matmul(adj, h) / deg
        return self.proj(agg)  # [N, latent_dim]


class VectorQuantizer(nn.Module):
    def __init__(self, num_embeddings: int, embedding_dim: int, commitment_cost: float):
        super().__init__()
        self.embeddings    = nn.Embedding(num_embeddings, embedding_dim)
        self.commit_cost   = commitment_cost
        nn.init.uniform_(self.embeddings.weight, -1 / num_embeddings, 1 / num_embeddings)

    def forward(self, z: torch.Tensor):
        # z: [N, D]
        dist = (
            z.unsqueeze(1) - self.embeddings.weight.unsqueeze(0)
        ).pow(2).sum(-1)                      # [N, num_embeddings]
        idx  = dist.argmin(1)                 # [N]
        z_q  = self.embeddings(idx)           # [N, D]
        # Straight-through estimator
        z_st = z + (z_q - z).detach()
        vq_loss = (
            (z_q.detach() - z).pow(2).mean() * self.commit_cost
            + (z_q - z.detach()).pow(2).mean()
        )
        return z_st, vq_loss


class STORM(nn.Module):
    def __init__(self, ts_input_dim: int, cs_input_dim: int):
        super().__init__()
        self.ts_enc  = TimeSeriesEncoder(ts_input_dim, HIDDEN_DIM, LATENT_DIM)
        self.cs_enc  = GraphEncoder(cs_input_dim, HIDDEN_DIM, LATENT_DIM)
        self.ts_vq   = VectorQuantizer(N_EMBED, LATENT_DIM, COMMIT_COST)
        self.cs_vq   = VectorQuantizer(N_EMBED, LATENT_DIM, COMMIT_COST)
        self.pred    = nn.Linear(LATENT_DIM * 2, 1)

    def forward(self, ts_x: torch.Tensor, cs_x: torch.Tensor, adj: torch.Tensor):
        ts_z            = self.ts_enc(ts_x)        # [N, LATENT_DIM]
        ts_zq, ts_loss  = self.ts_vq(ts_z)

        cs_z            = self.cs_enc(cs_x, adj)   # [N, LATENT_DIM]
        cs_zq, cs_loss  = self.cs_vq(cs_z)

        combined = torch.cat([ts_zq, cs_zq], dim=-1)  # [N, 2*LATENT_DIM]
        score    = self.pred(combined).squeeze(-1)     # [N]
        vq_loss  = ts_loss + cs_loss
        return score, vq_loss


# ─────────────────────────────────────────────────────────────────────────────
# Data loading and feature engineering
# ─────────────────────────────────────────────────────────────────────────────

def load_daily_prices() -> pd.DataFrame:
    cache = CACHE_DIR / f"h195_daily_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        print("  Loading from cache…")
        return pd.read_parquet(cache)

    # Reuse H188 cache if it covers same range
    h188_cache = CACHE_DIR / f"h188_daily_{DATA_START}_{DATA_END}.parquet"
    if h188_cache.exists():
        print("  Reusing H188 daily cache…")
        df = pd.read_parquet(h188_cache)
        df.to_parquet(cache)
        return df

    print(f"  Downloading {len(UNIVERSE)} tickers from yfinance…")
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    prices = prices.dropna(how="all", axis=0)
    prices.to_parquet(cache)
    return prices


def compute_cs_features(prices: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """
    Cross-sectional factor values for all stocks as of rebal date.
    Returns DataFrame [N_stocks × 4]: momentum_12m, reversal_1m, vol_21d, prox_52wk
    """
    hist = prices[prices.index <= as_of]
    if len(hist) < 253:
        return pd.DataFrame()

    last   = hist.iloc[-1]
    one_m  = hist.tail(22).iloc[0]  # ~21 trading days ago
    twelve = hist.tail(252).iloc[0]

    mom_12m   = (last / twelve - 1).replace([np.inf, -np.inf], np.nan)
    rev_1m    = (last / one_m  - 1).replace([np.inf, -np.inf], np.nan)
    vol_21d   = np.log(hist.tail(22) / hist.tail(22).shift(1)).std() * np.sqrt(252)
    prox_52wk = (last / hist.tail(252).max()).replace([np.inf, -np.inf], np.nan)

    feat = pd.DataFrame({
        "mom_12m":   mom_12m,
        "rev_1m":    rev_1m,
        "vol_21d":   vol_21d,
        "prox_52wk": prox_52wk,
    }).dropna()
    return feat


def compute_ts_sequences(daily_returns: pd.DataFrame, as_of: pd.Timestamp,
                         tickers: list) -> np.ndarray:
    """
    For each stock, return the last TS_WINDOW log-returns ending at as_of.
    Returns array [N_stocks, TS_WINDOW, 1].
    """
    hist = daily_returns[daily_returns.index <= as_of][tickers].tail(TS_WINDOW + 1)
    if len(hist) < TS_WINDOW:
        return np.zeros((len(tickers), TS_WINDOW, 1))

    seqs = hist.values[-TS_WINDOW:]         # [TS_WINDOW, N]
    seqs = seqs.T[:, :, np.newaxis]        # [N, TS_WINDOW, 1]
    seqs = np.nan_to_num(seqs, nan=0.0)
    # Standardize each sequence independently
    std = seqs.std(axis=1, keepdims=True) + 1e-8
    seqs = seqs / std
    return seqs.astype(np.float32)


def build_adj_matrix(prices: pd.DataFrame, as_of: pd.Timestamp,
                     tickers: list) -> np.ndarray:
    """
    Build thresholded correlation adjacency matrix (symmetric, no self-loops).
    """
    hist = prices[prices.index <= as_of][tickers].tail(252)
    rets = np.log(hist / hist.shift(1)).dropna()
    corr = rets.corr().fillna(0).values
    # Threshold and remove self-loops
    adj  = (corr >= CORR_THRESH).astype(float)
    np.fill_diagonal(adj, 0.0)
    return adj.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Training and inference
# ─────────────────────────────────────────────────────────────────────────────

def build_monthly_dataset(prices: pd.DataFrame, daily_returns: pd.DataFrame,
                          start: pd.Timestamp, end: pd.Timestamp) -> list:
    """
    Build list of (ts_x, cs_x, adj, labels, tickers) for each rebalance month
    in [start, end].  label = next-month return.
    """
    monthly_px = prices.resample("ME").last()
    months = monthly_px.loc[start:end].index
    dataset = []

    for i in range(1, len(months) - 1):
        rebal = months[i]
        hold  = months[i + 1]

        cs = compute_cs_features(prices, rebal)
        if len(cs) < N_LONG * 2:
            continue

        tickers = cs.index.tolist()
        cs_arr  = cs.values.astype(np.float32)

        # Cross-sectional rank-normalize each feature
        cs_ranked = (pd.DataFrame(cs_arr).rank(pct=True) - 0.5).values.astype(np.float32)

        ts_arr = compute_ts_sequences(daily_returns, rebal, tickers)
        adj    = build_adj_matrix(prices, rebal, tickers)

        # Labels: next-month returns
        labels = np.full(len(tickers), np.nan)
        for j, t in enumerate(tickers):
            if t in monthly_px.columns:
                p1 = monthly_px.at[rebal, t] if rebal in monthly_px.index else np.nan
                p2 = monthly_px.at[hold,  t] if hold  in monthly_px.index else np.nan
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    labels[j] = (p2 - p1) / p1

        valid = np.isfinite(labels)
        if valid.sum() < N_LONG * 2:
            continue

        dataset.append({
            "rebal":    rebal,
            "hold":     hold,
            "ts_x":     ts_arr,
            "cs_x":     cs_ranked,
            "adj":      adj,
            "labels":   labels,
            "tickers":  tickers,
            "valid":    valid,
        })

    return dataset


def train_storm(model: STORM, dataset: list) -> None:
    optimizer = optim.Adam(model.parameters(), lr=LR, weight_decay=1e-4)
    model.train()

    for epoch in range(EPOCHS):
        total_loss = 0.0
        for sample in dataset:
            ts_x   = torch.tensor(sample["ts_x"])
            cs_x   = torch.tensor(sample["cs_x"])
            adj    = torch.tensor(sample["adj"])
            labels = torch.tensor(sample["labels"].astype(np.float32))
            valid  = torch.tensor(sample["valid"])

            optimizer.zero_grad()
            scores, vq_loss = model(ts_x, cs_x, adj)

            pred_loss = ((scores[valid] - labels[valid]) ** 2).mean()
            loss = pred_loss + vq_loss
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        if (epoch + 1) % 30 == 0:
            print(f"    Epoch {epoch+1:3d}/{EPOCHS}  loss={total_loss/len(dataset):.5f}")


def score_month(model: STORM, sample: dict) -> pd.Series:
    model.eval()
    with torch.no_grad():
        ts_x = torch.tensor(sample["ts_x"])
        cs_x = torch.tensor(sample["cs_x"])
        adj  = torch.tensor(sample["adj"])
        scores, _ = model(ts_x, cs_x, adj)
    return pd.Series(scores.numpy(), index=sample["tickers"])


# ─────────────────────────────────────────────────────────────────────────────
# Backtest loop
# ─────────────────────────────────────────────────────────────────────────────

def run_oos_backtest(model: STORM, oos_dataset: list) -> pd.DataFrame:
    records = []
    for sample in oos_dataset:
        scores = score_month(model, sample)
        valid_tickers = [t for t, v in zip(sample["tickers"], sample["valid"]) if v]
        scores = scores[valid_tickers]

        if len(scores) < N_LONG:
            continue

        long_tickers = scores.nlargest(N_LONG).index.tolist()
        valid_labels = {t: lbl for t, lbl, v in zip(sample["tickers"], sample["labels"], sample["valid"]) if v}
        rets = [valid_labels[t] for t in long_tickers if t in valid_labels]

        if not rets:
            continue

        records.append({
            "date":         sample["hold"],
            "port_ret":     float(np.mean(rets)),
            "n_held":       len(rets),
            "long_tickers": ",".join(long_tickers),
        })

    return pd.DataFrame(records).set_index("date")


def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    if len(returns) == 0:
        return {"label": label}
    cum   = (1 + returns).cumprod()
    n_yrs = len(returns) / 12.0
    cagr  = cum.iloc[-1] ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = (returns.mean() / returns.std() * np.sqrt(12)) if returns.std() > 0 else 0.0
    dd    = (cum / cum.cummax()) - 1
    return {
        "label":        label,
        "n_months":     len(returns),
        "cumul":        round(float(cum.iloc[-1]), 4),
        "cagr_pct":     round(cagr * 100, 2),
        "sharpe":       round(sharpe, 3),
        "max_dd_pct":   round(float(dd.min()) * 100, 2),
        "mean_monthly": round(float(returns.mean()) * 100, 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("  H195 — STORM Dual VQ-VAE Spatio-Temporal Factor Model")
    print("  arXiv:2412.09468 (WSDM '26)")
    print("=" * 64)

    torch.manual_seed(42)
    np.random.seed(42)

    print(f"\n[1/6] Loading daily prices…")
    prices = load_daily_prices()
    available = [t for t in UNIVERSE if t in prices.columns and prices[t].notna().sum() > 300]
    prices = prices[available]
    print(f"  {len(available)}/{len(UNIVERSE)} tickers, {prices.index[0].date()} → {prices.index[-1].date()}")

    print("\n[2/6] Computing daily log-returns…")
    daily_rets = np.log(prices / prices.shift(1)).dropna()

    print(f"\n[3/6] Building IS dataset ({IS_START.date()} → {IS_END.date()})…")
    is_data = build_monthly_dataset(prices, daily_rets, IS_START, IS_END)
    print(f"  {len(is_data)} training months")

    print(f"\n[4/6] Building OOS dataset ({OOS_START.date()} → {OOS_END.date()})…")
    oos_data = build_monthly_dataset(prices, daily_rets, OOS_START, OOS_END)
    print(f"  {len(oos_data)} test months")

    if not is_data:
        print("ERROR: no IS data — check data range")
        return

    # Infer dims from first sample
    ts_dim = is_data[0]["ts_x"].shape[-1]    # = 1 (log-returns)
    cs_dim = is_data[0]["cs_x"].shape[-1]    # = 4 (factors)

    print(f"\n[5/6] Training STORM (epochs={EPOCHS}, hidden={HIDDEN_DIM}, latent={LATENT_DIM})…")
    print(f"  TS input dim: {ts_dim}, CS input dim: {cs_dim}, codebook: {N_EMBED}")
    model = STORM(ts_dim, cs_dim)
    train_storm(model, is_data)

    print("\n[6/6] OOS backtest…")
    oos_results = run_oos_backtest(model, oos_data)

    # SPY benchmark for OOS
    spy_cache = CACHE_DIR / "spy_monthly.parquet"
    if spy_cache.exists():
        spy_close = pd.read_parquet(spy_cache)["close"]
    else:
        spy_raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
        spy_close = spy_raw["Close"].resample("ME").last()
        spy_close.name = "close"
        pd.DataFrame({"close": spy_close}).to_parquet(spy_cache)

    spy_oos_rets = spy_close.pct_change().dropna()
    spy_oos      = spy_oos_rets[(spy_oos_rets.index >= OOS_START) &
                                (spy_oos_rets.index <= OOS_END)]

    h195_is  = calc_metrics(run_oos_backtest(model, is_data)["port_ret"], "H195-IS")
    h195_oos = calc_metrics(oos_results["port_ret"], "H195-OOS")
    spy_m    = calc_metrics(spy_oos, "SPY-OOS")

    print("\n── Results ─────────────────────────────────────────────────────")
    for m in [h195_is, h195_oos, spy_m]:
        print(f"  {m.get('label',''):<12}  Sharpe={m.get('sharpe','N/A'):>6}  "
              f"CAGR={m.get('cagr_pct','N/A'):>6}%  "
              f"MaxDD={m.get('max_dd_pct','N/A'):>7}%  "
              f"Cumul={m.get('cumul','N/A'):>6}x")

    # Save results
    out = RESULT_DIR / "h195_storm_results.json"
    import json
    result = {
        "hypothesis":  "H195",
        "model":       "STORM dual VQ-VAE",
        "run_date":    datetime.now().isoformat(),
        "is_period":   f"{IS_START.date()} → {IS_END.date()}",
        "oos_period":  f"{OOS_START.date()} → {OOS_END.date()}",
        "architecture": {
            "ts_window":   TS_WINDOW,
            "hidden_dim":  HIDDEN_DIM,
            "latent_dim":  LATENT_DIM,
            "n_embed":     N_EMBED,
            "epochs":      EPOCHS,
            "corr_thresh": CORR_THRESH,
        },
        "is_metrics":  h195_is,
        "oos_metrics": h195_oos,
        "spy_metrics": spy_m,
        "confirmed":   h195_oos.get("sharpe", 0) > 0.8,
    }
    out.write_text(json.dumps(result, indent=2))
    print(f"\n  Results saved → {out}")

    sharpe_oos = h195_oos.get("sharpe", 0)
    if sharpe_oos > 0.8:
        print(f"\n  ✓ H195 CONFIRMED — OOS Sharpe {sharpe_oos:.3f} > 0.8 threshold")
    else:
        print(f"\n  ✗ H195 NOT CONFIRMED — OOS Sharpe {sharpe_oos:.3f} below 0.8")


if __name__ == "__main__":
    main()
