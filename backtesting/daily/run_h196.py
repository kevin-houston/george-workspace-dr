"""
H196 — STORM Scale Test: 100-Stock S&P 500 Universe
=====================================================
H195 confirmed STORM (dual VQ-VAE spatio-temporal) on 30-stock universe,
OOS Sharpe=0.963 — below H191-C (1.110) and H192-D (1.367).

KEY HYPOTHESIS from H195: "STORM's advantage may require larger, more heterogeneous
universes (500+ stocks) where the graph connectivity and codebook diversity add
meaningful orthogonality. On 30 highly correlated large-caps, the GCN stage adds
limited new information."

H196 tests this by expanding to 100 S&P 500 stocks across all 11 GICS sectors
(~9 per sector), providing a much more heterogeneous correlation graph. If the
dual VQ-VAE orthogonality advantage is scale-dependent, we expect:
  - Better IS/OOS degradation ratio (30-stock: 41% Sharpe decay)
  - OOS Sharpe > 1.0 (beating the 30-stock H195 result)
  - Better portfolio diversity (codebook usage spread across 64 vectors more evenly)

Architecture: identical to H195.
Universe: 100 S&P 500 stocks, all 11 GICS sectors, ~9/sector
Strategy: long top-10 (10% of universe, same quintile proportion as H195's 6/30=20%),
  equal-weight, monthly rebalance.
IS: 2015–2021, OOS: 2022–2024.

Confirm: OOS Sharpe > 0.963 (beats 30-stock H195) AND IS/OOS degradation < 30%.
"""

import warnings
warnings.filterwarnings("ignore")

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except ImportError:
    sys.exit("PyTorch not found. Install: pip install torch --index-url https://download.pytorch.org/whl/cpu")

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# ── 100-stock S&P 500 universe — 11 GICS sectors (approx 9 each) ─────────────
UNIVERSE_SECTORS = {
    # Information Technology (11)
    "AAPL": "IT",  "MSFT": "IT",  "NVDA": "IT",  "AVGO": "IT",  "QCOM": "IT",
    "AMD":  "IT",  "ORCL": "IT",  "CRM":  "IT",  "IBM":  "IT",  "INTC": "IT",  "TXN": "IT",
    # Communication Services (8)
    "GOOGL":"Comm", "META": "Comm", "NFLX": "Comm", "DIS":  "Comm",
    "CMCSA":"Comm", "T":    "Comm", "VZ":   "Comm", "ATVI": "Comm",
    # Consumer Discretionary (9)
    "AMZN": "CD",  "TSLA": "CD",  "HD":   "CD",  "LOW":  "CD",  "NKE": "CD",
    "SBUX": "CD",  "MCD":  "CD",  "TGT":  "CD",  "BKNG": "CD",
    # Consumer Staples (8)
    "WMT":  "CS",  "COST": "CS",  "PG":   "CS",  "KO":   "CS",
    "PEP":  "CS",  "MDLZ": "CS",  "CL":   "CS",  "GIS":  "CS",
    # Financials (9)
    "JPM":  "Fin", "BAC":  "Fin", "WFC":  "Fin", "GS":   "Fin",  "MS":  "Fin",
    "V":    "Fin", "MA":   "Fin", "AXP":  "Fin", "BLK":  "Fin",
    # Health Care (10)
    "UNH":  "HC",  "LLY":  "HC",  "JNJ":  "HC",  "ABBV": "HC",  "PFE":  "HC",
    "MRK":  "HC",  "TMO":  "HC",  "ABT":  "HC",  "BMY":  "HC",  "AMGN": "HC",
    # Industrials (9)
    "BA":   "Ind", "CAT":  "Ind", "HON":  "Ind", "RTX":  "Ind", "LMT":  "Ind",
    "UPS":  "Ind", "DE":   "Ind", "GE":   "Ind", "MMM":  "Ind",
    # Energy (7)
    "XOM":  "En",  "CVX":  "En",  "COP":  "En",  "SLB":  "En",
    "PXD":  "En",  "EOG":  "En",  "PSX":  "En",
    # Materials (7)
    "LIN":  "Mat", "APD":  "Mat", "ECL":  "Mat", "NEM":  "Mat",
    "FCX":  "Mat", "NUE":  "Mat", "DOW":  "Mat",
    # Real Estate (7)
    "PLD":  "RE",  "AMT":  "RE",  "CCI":  "RE",  "EQIX": "RE",
    "PSA":  "RE",  "WY":   "RE",  "SPG":  "RE",
    # Utilities (7)
    "NEE":  "Util","DUK":  "Util","SO":   "Util","D":    "Util",
    "AEP":  "Util","EXC":  "Util","XEL":  "Util",
}
UNIVERSE = list(UNIVERSE_SECTORS.keys())
SPY = "SPY"
print(f"Universe: {len(UNIVERSE)} stocks, 11 GICS sectors")

DATA_START   = "2013-01-01"
DATA_END     = "2025-04-30"
IS_START     = pd.Timestamp("2015-01-01")
IS_END       = pd.Timestamp("2021-12-31")
OOS_START    = pd.Timestamp("2022-01-01")
OOS_END      = pd.Timestamp("2024-12-31")

TS_WINDOW    = 20
N_LONG       = 10    # top-10% (10/100 = 10%... actually ~same quintile as H195's 6/30=20%)
              # use 20 for 20th percentile to match H195 methodology exactly
EPOCHS       = 60    # reduced from H195's 150 for speed; sufficient for convergence test
LR           = 1e-3
HIDDEN_DIM   = 32
LATENT_DIM   = 16
N_EMBED      = 64
COMMIT_COST  = 0.25
CORR_THRESH  = 0.30

# Use 20% of universe like H195 (6/30 = 20%)
N_LONG = max(10, len(UNIVERSE) // 5)  # 20th percentile = top-20 of 100


# ── STORM model (identical to H195) ──────────────────────────────────────────

class TimeSeriesEncoder(nn.Module):
    def __init__(self, input_dim, hidden_dim, latent_dim):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.proj = nn.Linear(hidden_dim, latent_dim)

    def forward(self, x):
        _, (h, _) = self.lstm(x)
        return self.proj(h[-1])


class GraphEncoder(nn.Module):
    def __init__(self, input_dim, hidden_dim, latent_dim):
        super().__init__()
        self.linear = nn.Linear(input_dim, hidden_dim)
        self.proj   = nn.Linear(hidden_dim, latent_dim)

    def forward(self, x, adj):
        h   = torch.relu(self.linear(x))
        deg = adj.sum(1, keepdim=True).clamp(min=1.0)
        agg = torch.matmul(adj, h) / deg
        return self.proj(agg)


class VectorQuantizer(nn.Module):
    def __init__(self, num_embeddings, embedding_dim, commitment_cost):
        super().__init__()
        self.embeddings  = nn.Embedding(num_embeddings, embedding_dim)
        self.commit_cost = commitment_cost
        nn.init.uniform_(self.embeddings.weight, -1 / num_embeddings, 1 / num_embeddings)

    def forward(self, z):
        dist = (z.unsqueeze(1) - self.embeddings.weight.unsqueeze(0)).pow(2).sum(-1)
        idx  = dist.argmin(1)
        z_q  = self.embeddings(idx)
        z_st = z + (z_q - z).detach()
        vq_loss = (
            (z_q.detach() - z).pow(2).mean() * self.commit_cost
            + (z_q - z.detach()).pow(2).mean()
        )
        return z_st, vq_loss


class STORM(nn.Module):
    def __init__(self, ts_input_dim, cs_input_dim):
        super().__init__()
        self.ts_enc = TimeSeriesEncoder(ts_input_dim, HIDDEN_DIM, LATENT_DIM)
        self.cs_enc = GraphEncoder(cs_input_dim, HIDDEN_DIM, LATENT_DIM)
        self.ts_vq  = VectorQuantizer(N_EMBED, LATENT_DIM, COMMIT_COST)
        self.cs_vq  = VectorQuantizer(N_EMBED, LATENT_DIM, COMMIT_COST)
        self.pred   = nn.Linear(LATENT_DIM * 2, 1)

    def forward(self, ts_x, cs_x, adj):
        ts_z, ts_loss = self.ts_vq(self.ts_enc(ts_x))
        cs_z, cs_loss = self.cs_vq(self.cs_enc(cs_x, adj))
        score = self.pred(torch.cat([ts_z, cs_z], dim=-1)).squeeze(-1)
        return score, ts_loss + cs_loss


# ── Data loading ─────────────────────────────────────────────────────────────

def load_prices() -> tuple[pd.DataFrame, pd.Series]:
    cache = CACHE_DIR / f"h196_100stock_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        print("  Loading from H196 cache…")
        df = pd.read_parquet(cache)
    else:
        print(f"  Downloading {len(UNIVERSE)+1} tickers (this may take a few minutes)…")
        raw = yf.download(UNIVERSE + [SPY], start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=True)
        df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        df = df.dropna(how="all", axis=0)
        df.to_parquet(cache)
        print(f"  Cached {len(df)} rows.")

    if SPY not in df.columns:
        spy_raw = yf.download(SPY, start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
        df[SPY] = spy_raw["Close"].squeeze().reindex(df.index, method="ffill")

    # Keep only tickers with sufficient history
    available = [t for t in UNIVERSE if t in df.columns and df[t].notna().sum() > 500]
    print(f"  Available after coverage filter: {len(available)} stocks")
    return df[available].copy(), df[SPY].copy()


# ── Feature engineering ───────────────────────────────────────────────────────

def build_monthly_samples(
    daily_prices: pd.DataFrame, spy_prices: pd.Series
) -> list[dict]:
    """
    For each monthly rebalance: build (ts_feats, cs_feats, adj, next_month_ret).
    Returns list of sample dicts with keys: date, tickers, ts, cs, adj, ret.
    """
    tickers    = list(daily_prices.columns)
    N          = len(tickers)
    monthly_px = daily_prices.resample("ME").last()
    month_ends = monthly_px.index

    daily_rets = daily_prices.pct_change()
    log_rets   = np.log1p(daily_rets.fillna(0))

    samples = []
    for i in range(1, len(month_ends) - 1):
        rebal_date  = month_ends[i]
        future_date = month_ends[i + 1]

        # Need at least TS_WINDOW + 252 days of history
        hist = daily_rets[daily_rets.index <= rebal_date]
        if len(hist) < TS_WINDOW + 252:
            continue

        # ── Time-series features: last TS_WINDOW daily log-returns per stock ──
        ts_window = log_rets[log_rets.index <= rebal_date].tail(TS_WINDOW)
        ts_arr = ts_window.reindex(columns=tickers).fillna(0).values.T  # [N, T]

        # ── Cross-sectional features: momentum, reversal, vol, 52wk ─────────
        prices_hist = daily_prices[daily_prices.index <= rebal_date]
        p_last = monthly_px.iloc[i]
        p_1m   = monthly_px.iloc[i - 1] if i >= 1 else p_last
        p_12m  = monthly_px.iloc[i - 13] if i >= 13 else None

        cs_feats = {}
        for t in tickers:
            if t not in prices_hist.columns:
                continue
            ph = prices_hist[t].dropna()
            if len(ph) < 253:
                continue
            last_px = ph.iloc[-1]
            high52  = ph.tail(252).max()
            p1m_val = p_1m.get(t, np.nan)
            rev_1m  = (last_px / p1m_val - 1) if p1m_val and p1m_val > 0 else np.nan
            mom_12m = (last_px / p_12m.get(t, np.nan) - 1) if p_12m is not None and p_12m.get(t, np.nan) > 0 else np.nan
            vol_21d = daily_rets[t].dropna().tail(21).std() * np.sqrt(252) if t in daily_rets else np.nan
            prox    = last_px / high52 if high52 > 0 else np.nan
            cs_feats[t] = [mom_12m, rev_1m, vol_21d, prox]

        avail = [t for t in tickers if t in cs_feats and all(pd.notna(v) for v in cs_feats[t])]
        if len(avail) < N_LONG * 2:
            continue

        avail_idx = {t: tickers.index(t) for t in avail if t in tickers}

        # Rank-normalize CS features cross-sectionally
        cs_mat = np.array([cs_feats[t] for t in avail], dtype=np.float32)
        for j in range(cs_mat.shape[1]):
            col = cs_mat[:, j]
            ranks = pd.Series(col).rank().values
            cs_mat[:, j] = (ranks - ranks.mean()) / (ranks.std() + 1e-8)

        # Correlation graph over rolling 63d returns (quarterly)
        corr_rets = daily_rets[avail].tail(63).fillna(0)
        corr_mat  = corr_rets.corr().values
        corr_mat  = np.nan_to_num(corr_mat, nan=0.0)
        adj = (np.abs(corr_mat) > CORR_THRESH).astype(np.float32)
        np.fill_diagonal(adj, 1.0)

        # Next-month returns for labels
        future_rets = {}
        for t in avail:
            p_cur  = p_last.get(t, np.nan)
            p_fut  = monthly_px.iloc[i + 1].get(t, np.nan)
            if pd.notna(p_cur) and pd.notna(p_fut) and p_cur > 0:
                future_rets[t] = (p_fut - p_cur) / p_cur

        avail_with_ret = [t for t in avail if t in future_rets]
        if len(avail_with_ret) < N_LONG * 2:
            continue

        avail_idx_final = [avail.index(t) for t in avail_with_ret]
        ts_sub  = ts_arr[[tickers.index(t) for t in avail_with_ret]]
        cs_sub  = cs_mat[[avail.index(t) for t in avail_with_ret]]
        adj_sub = adj[np.ix_(avail_idx_final, avail_idx_final)]
        ret_arr = np.array([future_rets[t] for t in avail_with_ret], dtype=np.float32)

        samples.append({
            "date":    rebal_date,
            "tickers": avail_with_ret,
            "ts":      ts_sub.astype(np.float32),
            "cs":      cs_sub,
            "adj":     adj_sub,
            "ret":     ret_arr,
        })

    return samples


# ── Training and backtesting ──────────────────────────────────────────────────

def train_model(is_samples: list[dict]) -> STORM:
    if not is_samples:
        raise ValueError("No IS samples available")

    cs_dim = is_samples[0]["cs"].shape[1]
    model  = STORM(ts_input_dim=1, cs_input_dim=cs_dim)
    opt    = optim.Adam(model.parameters(), lr=LR)

    for epoch in range(EPOCHS):
        total_loss = 0.0
        for s in is_samples:
            ts  = torch.from_numpy(s["ts"]).unsqueeze(-1)  # [N, T, 1]
            cs  = torch.from_numpy(s["cs"])
            adj = torch.from_numpy(s["adj"])
            y   = torch.from_numpy(s["ret"])

            score, vq_loss = model(ts, cs, adj)
            # Ranking loss: MSE on rank-normalized labels
            rank_y = torch.from_numpy(
                pd.Series(s["ret"]).rank().values.astype(np.float32)
            )
            rank_y = (rank_y - rank_y.mean()) / (rank_y.std() + 1e-8)
            loss   = ((score - rank_y) ** 2).mean() + vq_loss
            opt.zero_grad()
            loss.backward()
            opt.step()
            total_loss += loss.item()

        if (epoch + 1) % 20 == 0:
            print(f"    Epoch {epoch+1:3d}/{EPOCHS}  avg_loss={total_loss/len(is_samples):.4f}")

    return model


def run_oos_backtest(model: STORM, oos_samples: list[dict]) -> pd.Series:
    model.eval()
    rets, dates = [], []
    with torch.no_grad():
        for s in oos_samples:
            ts    = torch.from_numpy(s["ts"]).unsqueeze(-1)
            cs    = torch.from_numpy(s["cs"])
            adj   = torch.from_numpy(s["adj"])
            score, _ = model(ts, cs, adj)
            scores_np = score.numpy()
            top_idx   = np.argsort(-scores_np)[:N_LONG]
            month_rets = s["ret"][top_idx]
            rets.append(float(np.mean(month_rets)))
            dates.append(s["date"])
    return pd.Series(rets, index=pd.DatetimeIndex(dates), name="H196")


def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    if len(returns) == 0:
        return {"label": label, "sharpe": 0, "cumul": 0, "cagr_pct": 0,
                "max_dd_pct": 0, "neg_years": 0}
    cum   = (1 + returns).cumprod()
    n_yrs = len(returns) / 12.0
    cagr  = cum.iloc[-1] ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = returns.mean() / returns.std() * np.sqrt(12) if returns.std() > 0 else 0.0
    dd     = (cum / cum.cummax()) - 1
    annual = returns.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {
        "label":      label,
        "n_months":   len(returns),
        "cumul":      round(float(cum.iloc[-1]), 4),
        "cagr_pct":   round(cagr * 100, 2),
        "sharpe":     round(sharpe, 3),
        "max_dd_pct": round(float(dd.min()) * 100, 2),
        "neg_years":  int(annual.lt(0).sum()),
    }


def main():
    print("=" * 72)
    print("  H196 — STORM Scale Test: 100-Stock S&P 500 Universe")
    print("  Testing whether larger universe unlocks dual VQ-VAE advantage")
    print("=" * 72)
    print(f"  N_LONG={N_LONG} (top {N_LONG/len(UNIVERSE)*100:.0f}% = same 20th-pct as H195)")
    print(f"  EPOCHS={EPOCHS}, HIDDEN={HIDDEN_DIM}, LATENT={LATENT_DIM}, N_EMBED={N_EMBED}")

    print("\n[1] Loading prices…")
    prices, spy_px = load_prices()
    active_n = len(prices.columns)
    print(f"    {active_n} tickers × {len(prices)} trading days")

    print("\n[2] Building monthly samples…")
    all_samples = build_monthly_samples(prices, spy_px)
    print(f"    {len(all_samples)} monthly samples total")

    is_samples  = [s for s in all_samples if IS_START  <= s["date"] <= IS_END]
    oos_samples = [s for s in all_samples if OOS_START <= s["date"] <= OOS_END]
    print(f"    IS: {len(is_samples)} months  |  OOS: {len(oos_samples)} months")

    if len(is_samples) < 12 or len(oos_samples) < 6:
        print("ERROR: Insufficient data for training/testing.")
        return

    print(f"\n[3] Training STORM on IS data ({len(is_samples)} months)…")
    model = train_model(is_samples)

    print("\n[4] IS backtest…")
    is_rets = run_oos_backtest(model, is_samples)  # re-uses model
    m_is = calc_metrics(is_rets, "H196 IS 2015–2021")
    print(f"    IS: Sharpe={m_is['sharpe']:.3f}  Cumul={m_is['cumul']:.3f}×  "
          f"CAGR={m_is['cagr_pct']:.1f}%  MaxDD={m_is['max_dd_pct']:.1f}%")

    print("\n[5] OOS backtest…")
    oos_rets = run_oos_backtest(model, oos_samples)
    m_oos = calc_metrics(oos_rets, "H196 OOS 2022–2024")
    print(f"    OOS: Sharpe={m_oos['sharpe']:.3f}  Cumul={m_oos['cumul']:.3f}×  "
          f"CAGR={m_oos['cagr_pct']:.1f}%  MaxDD={m_oos['max_dd_pct']:.1f}%")

    # SPY benchmark
    spy_monthly = spy_px.resample("ME").last().pct_change().dropna()
    spy_oos = spy_monthly[(spy_monthly.index >= OOS_START) & (spy_monthly.index <= OOS_END)]
    m_spy   = calc_metrics(spy_oos, "SPY OOS 2022–2024")
    print(f"    SPY: Sharpe={m_spy['sharpe']:.3f}  Cumul={m_spy['cumul']:.3f}×")

    # IS/OOS degradation
    if m_is["sharpe"] > 0:
        degradation = (m_is["sharpe"] - m_oos["sharpe"]) / m_is["sharpe"] * 100
    else:
        degradation = float("nan")
    print(f"\n    IS/OOS Sharpe degradation: {degradation:.1f}%  "
          f"(H195 30-stock: 41%)")

    # Confirm
    print("\n[6] Verdict:")
    beats_h195 = m_oos["sharpe"] > 0.963
    low_decay  = degradation < 30 if not np.isnan(degradation) else False
    beats_spy  = m_oos["sharpe"] > m_spy["sharpe"]
    print(f"    OOS Sharpe > 0.963 (H195): {'✓' if beats_h195 else '✗'}  ({m_oos['sharpe']:.3f})")
    print(f"    IS/OOS decay < 30%:        {'✓' if low_decay  else '✗'}  ({degradation:.1f}%)")
    print(f"    OOS beats SPY:             {'✓' if beats_spy  else '✗'}")

    if beats_h195 and low_decay:
        verdict = "CONFIRMED — scale unlocks STORM advantage"
    elif beats_spy:
        verdict = "PARTIAL — beats SPY but not a strong scale improvement"
    else:
        verdict = "NOT CONFIRMED — scale does not unlock STORM advantage"
    print(f"\n    VERDICT: {verdict}")

    # Save
    out = RESULT_DIR / "h196_storm_100stock.txt"
    out.write_text(
        f"H196 — STORM 100-stock S&P 500 Scale Test\n"
        f"N={active_n} stocks, N_LONG={N_LONG}, EPOCHS={EPOCHS}\n"
        f"IS 2015-2021:  Sharpe={m_is['sharpe']:.3f} Cumul={m_is['cumul']:.3f}x "
        f"CAGR={m_is['cagr_pct']:.1f}% MaxDD={m_is['max_dd_pct']:.1f}%\n"
        f"OOS 2022-2024: Sharpe={m_oos['sharpe']:.3f} Cumul={m_oos['cumul']:.3f}x "
        f"CAGR={m_oos['cagr_pct']:.1f}% MaxDD={m_oos['max_dd_pct']:.1f}%\n"
        f"SPY OOS:       Sharpe={m_spy['sharpe']:.3f} Cumul={m_spy['cumul']:.3f}x\n"
        f"IS/OOS Sharpe degradation: {degradation:.1f}%\n"
        f"VERDICT: {verdict}\n"
    )
    print(f"\n✓ Results saved to {out}")


if __name__ == "__main__":
    main()
