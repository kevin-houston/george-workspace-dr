"""
H204 — Deep Reinforcement Learning Portfolio vs Momentum Baseline
=================================================================
Source: FinRL (AI4Finance-Foundation); arXiv:2511.12120 (PPO+A2C+DDPG ensemble);
        arXiv:2508.20103 (DDPG-TiDE, Sharpe 1.13)

Hypothesis: A PPO agent trained on our 30-stock IS (2013–2020) achieves
OOS Sharpe > 0.8 on 2021–2026. Secondary: Corr(H204, H198) < 0.6 for
blending value regardless of absolute Sharpe.

Algorithm: PPO (stable-baselines3)
  - 3-seed ensemble, average daily weights across seeds
  - State: 60-day rolling return matrix (60 × 30) + current portfolio weights (30)
  - Action: 30-dim continuous → softmax → long-only portfolio weights
  - Reward: daily portfolio return − 10bps × sum(|Δweights|)
  - IS: 2013–2020  OOS: 2021–2026

CRITICAL: strict temporal cutoff — observation at step t uses only t−60..t−1.
Train ONLY on IS data. OOS evaluation is pure holdout, no retraining.
"""

import warnings
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from typing import Optional

import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE_SECTORS = {
    "AAPL": "IT",  "MSFT": "IT",   "AMZN": "CD",  "GOOGL": "CS",
    "META": "CS",  "TSLA": "CD",   "NVDA": "IT",  "AVGO": "IT",
    "QCOM": "IT",  "AMD":  "IT",   "V":    "FIN", "MA":   "FIN",
    "BAC":  "FIN", "WFC":  "FIN",  "JPM":  "FIN", "UNH":  "HC",
    "LLY":  "HC",  "PFE":  "HC",   "JNJ":  "HC",  "ABBV": "HC",
    "WMT":  "CS2", "HD":   "CD",   "SBUX": "CD",  "LOW":  "CD",
    "COST": "CS2", "CVX":  "ENE",  "XOM":  "ENE", "BA":   "IND",
    "CAT":  "IND", "IBM":  "IT",
}
UNIVERSE = list(UNIVERSE_SECTORS.keys())
N_STOCKS = len(UNIVERSE)

DATA_START = "2012-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

LOOKBACK   = 60    # days of return history in observation
COST_BPS   = 10    # one-way turnover cost
N_SEEDS    = 3
TIMESTEPS  = 300_000
POLICY_KWARGS = dict(net_arch=[128, 64])


# ── Data loading ───────────────────────────────────────────────────────────────

def fetch_prices() -> pd.DataFrame:
    frames = {}
    for ticker in UNIVERSE:
        cp = CACHE_DIR / f"h204_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
        # Try reuse from h202 cache
        cp2 = CACHE_DIR / f"h202_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            s = pd.read_parquet(cp).squeeze()
        elif cp2.exists():
            s = pd.read_parquet(cp2).squeeze()
        else:
            print(f"  Downloading {ticker}…")
            raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw = raw.xs(ticker, axis=1, level=1)
            s = raw["Close"]
            pd.DataFrame(s).to_parquet(cp)
        frames[ticker] = s
    prices = pd.DataFrame(frames).dropna(how="all")
    prices = prices.fillna(method="ffill").dropna()
    return prices


# ── Custom Gymnasium Environment ───────────────────────────────────────────────

class PortfolioEnv(gym.Env):
    """
    Long-only daily portfolio rebalancing environment.
    Observation: (LOOKBACK, N_STOCKS) flattened returns + current weights
    Action: N_STOCKS continuous values → softmax → portfolio weights
    """

    def __init__(self, returns: pd.DataFrame, start_idx: int = 0,
                 end_idx: Optional[int] = None):
        super().__init__()
        self.returns = returns.values.astype(np.float32)
        self.dates   = returns.index
        self.start   = max(start_idx, LOOKBACK)
        self.end     = end_idx if end_idx is not None else len(self.returns) - 1
        self.n       = N_STOCKS

        obs_dim = LOOKBACK * self.n + self.n
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(self.n,), dtype=np.float32
        )
        self.reset()

    def _get_obs(self):
        hist = self.returns[self.t - LOOKBACK: self.t].flatten()
        # Clip to [-1, 1] range for stability
        hist = np.clip(hist, -0.30, 0.30)
        return np.concatenate([hist, self.weights]).astype(np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.t = self.start
        self.weights = np.ones(self.n, dtype=np.float32) / self.n
        self.portfolio_value = 1.0
        return self._get_obs(), {}

    def step(self, action):
        # Softmax to get valid long-only weights
        a = np.exp(action - action.max())
        new_weights = a / a.sum()

        turnover = np.abs(new_weights - self.weights).sum()
        cost = turnover * COST_BPS / 10000

        day_ret = self.returns[self.t]
        port_ret = float(np.dot(new_weights, day_ret)) - cost

        self.weights = new_weights
        self.portfolio_value *= (1 + port_ret)
        self.t += 1

        done = self.t >= self.end
        obs = self._get_obs() if not done else self._get_obs()
        return obs, port_ret, done, False, {"portfolio_value": self.portfolio_value}


# ── Metrics ────────────────────────────────────────────────────────────────────

def sharpe(r: pd.Series) -> float:
    r = r.squeeze()
    std = float(r.std())
    if len(r) < 20 or std == 0:
        return 0.0
    return float(r.mean() / std * np.sqrt(252))


def max_dd(r: pd.Series) -> float:
    cumulative = (1 + r).cumprod()
    peak = cumulative.cummax()
    dd = (cumulative - peak) / peak
    return float(dd.min())


def neg_years(r: pd.Series) -> int:
    annual = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    return int((annual < 0).sum())


# ── Rollout: collect daily returns from a trained model ───────────────────────

def rollout(model: PPO, returns: pd.DataFrame,
            start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> pd.Series:
    idx = returns.index
    start_i = max(idx.searchsorted(start_dt), LOOKBACK)
    end_i   = idx.searchsorted(end_dt, side="right")

    env = PortfolioEnv(returns, start_idx=start_i, end_idx=end_i)
    obs, _ = env.reset()

    daily_rets = []
    dates_out  = []
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = env.step(action)
        daily_rets.append(reward)
        dates_out.append(returns.index[env.t - 1])

    return pd.Series(daily_rets, index=dates_out, name="RL")


# ── H198 baseline (6-1m cross-sectional momentum, monthly rebalance) ──────────

def compute_h198_returns(prices: pd.DataFrame) -> pd.Series:
    """Simple 6-1m rank signal, monthly rebalance, long top-6."""
    rets = prices.pct_change()
    monthly_dates = prices.resample("ME").last().index

    port_rets = []
    port_dates_all = []

    for i in range(1, len(monthly_dates)):
        signal_date = monthly_dates[i - 1]
        hold_start  = monthly_dates[i - 1]
        hold_end    = monthly_dates[i]

        # 6-1m momentum signal
        try:
            p_now = prices.loc[signal_date]
            p_6m  = prices.asof(signal_date - pd.DateOffset(months=6))
            p_1m  = prices.asof(signal_date - pd.DateOffset(months=1))
            if p_now.isna().any() or p_6m.isna().any():
                continue
            mom = (p_1m / p_6m) - 1
            if mom.isna().all():
                continue
            top6 = mom.nlargest(6).index.tolist()
        except Exception:
            continue

        # Daily returns in holding period
        mask = (rets.index > hold_start) & (rets.index <= hold_end)
        period_rets = rets.loc[mask, top6].mean(axis=1)
        port_rets.extend(period_rets.tolist())
        port_dates_all.extend(period_rets.index.tolist())

    return pd.Series(port_rets, index=port_dates_all, name="H198")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("H204 — Deep RL Portfolio (PPO) vs H198 Momentum Baseline")
    print("=" * 60)

    print("\nLoading price data…")
    prices = fetch_prices()
    returns = prices.pct_change().fillna(0)
    print(f"  Universe: {len(prices.columns)} stocks | {prices.index[0].date()} – {prices.index[-1].date()}")

    # IS / OOS index positions
    is_mask  = (returns.index >= IS_START)  & (returns.index <= IS_END)
    oos_mask = (returns.index >= OOS_START) & (returns.index <= OOS_END)
    is_idx_start  = is_mask.argmax()
    is_idx_end    = len(returns) - is_mask[::-1].argmax() - 1
    oos_idx_start = oos_mask.argmax()
    oos_idx_end   = len(returns) - oos_mask[::-1].argmax() - 1

    print(f"  IS:  {IS_START.date()} to {IS_END.date()} ({is_mask.sum()} days)")
    print(f"  OOS: {OOS_START.date()} to {OOS_END.date()} ({oos_mask.sum()} days)")

    # ── Train PPO agents (multi-seed) ─────────────────────────────────────────
    print(f"\nTraining PPO ({N_SEEDS} seeds × {TIMESTEPS:,} steps)…")
    models = []
    for seed in range(N_SEEDS):
        print(f"  Seed {seed+1}/{N_SEEDS}…")
        env_fn = lambda: PortfolioEnv(returns, start_idx=is_idx_start + LOOKBACK,
                                      end_idx=is_idx_end)
        vec_env = DummyVecEnv([env_fn])
        model = PPO(
            "MlpPolicy", vec_env,
            learning_rate=3e-4,
            n_steps=512,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            policy_kwargs=POLICY_KWARGS,
            verbose=0,
            seed=seed,
        )
        model.learn(total_timesteps=TIMESTEPS)
        models.append(model)
        print(f"    Seed {seed+1} training complete.")

    # ── IS evaluation ─────────────────────────────────────────────────────────
    print("\nEvaluating IS performance…")
    is_returns_all = []
    for seed, model in enumerate(models):
        r = rollout(model, returns, IS_START, IS_END)
        is_returns_all.append(r)
        print(f"  Seed {seed+1} IS Sharpe: {sharpe(r):.3f}")

    # Ensemble: average daily returns across seeds (aligns by date)
    is_ensemble = pd.concat(is_returns_all, axis=1).mean(axis=1)
    is_ensemble.index = pd.to_datetime(is_ensemble.index)
    is_r = is_ensemble[IS_START:IS_END]
    print(f"  Ensemble IS: Sharpe={sharpe(is_r):.3f}  MaxDD={max_dd(is_r):.1%}"
          f"  Cumul={(1+is_r).prod():.2f}×")

    # ── OOS evaluation ────────────────────────────────────────────────────────
    print("\nEvaluating OOS performance…")
    oos_returns_all = []
    for seed, model in enumerate(models):
        r = rollout(model, returns, OOS_START, OOS_END)
        oos_returns_all.append(r)
        print(f"  Seed {seed+1} OOS Sharpe: {sharpe(r):.3f}")

    oos_ensemble = pd.concat(oos_returns_all, axis=1).mean(axis=1)
    oos_ensemble.index = pd.to_datetime(oos_ensemble.index)
    oos_r = oos_ensemble[OOS_START:OOS_END]
    print(f"  Ensemble OOS: Sharpe={sharpe(oos_r):.3f}  MaxDD={max_dd(oos_r):.1%}"
          f"  NegYrs={neg_years(oos_r)}")

    # ── H198 baseline ─────────────────────────────────────────────────────────
    print("\nComputing H198 baseline (6-1m momentum, long top-6)…")
    h198_rets = compute_h198_returns(prices)
    h198_oos = h198_rets[OOS_START:OOS_END]
    print(f"  H198 OOS: Sharpe={sharpe(h198_oos):.3f}  MaxDD={max_dd(h198_oos):.1%}"
          f"  Cumul={(1+h198_oos).prod():.2f}×")

    # ── SPY benchmark ─────────────────────────────────────────────────────────
    spy_cp = CACHE_DIR / f"h204_SPY_close_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy = pd.read_parquet(spy_cp).squeeze()
    else:
        spy = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)["Close"]
        pd.DataFrame(spy).to_parquet(spy_cp)
    spy_rets = spy.pct_change().fillna(0)
    spy_oos = spy_rets[OOS_START:OOS_END]
    print(f"  SPY OOS: Sharpe={sharpe(spy_oos):.3f}  MaxDD={max_dd(spy_oos):.1%}")

    # ── Correlation diagnostic ────────────────────────────────────────────────
    common = oos_r.index.intersection(h198_oos.index)
    if len(common) > 50:
        corr_rl_h198 = oos_r.loc[common].corr(h198_oos.loc[common])
        corr_rl_spy  = oos_r.loc[common].corr(spy_oos.loc[common])
    else:
        corr_rl_h198 = corr_rl_spy = np.nan
    print(f"\nCorr(H204 RL, H198 momentum) OOS: {corr_rl_h198:.3f}")
    print(f"Corr(H204 RL, SPY) OOS:            {corr_rl_spy:.3f}")

    # ── Year-by-year OOS ──────────────────────────────────────────────────────
    print("\n── OOS Year-by-Year ──────────────────────────────────────────")
    print(f"{'Year':<6} {'SPY':>7} {'H198':>8} {'H204-RL':>9}")
    for yr in sorted(spy_oos.index.year.unique()):
        def yr_ret(s):
            sub = s[s.index.year == yr]
            return (1 + sub).prod() - 1 if len(sub) > 0 else np.nan
        print(f"{yr:<6} {yr_ret(spy_oos):>+7.1%} {yr_ret(h198_oos):>+8.1%}"
              f" {yr_ret(oos_r):>+9.1%}")

    # ── Confirm gate ──────────────────────────────────────────────────────────
    oos_sharpe = sharpe(oos_r)
    confirmed  = oos_sharpe > 0.8
    corr_ok    = abs(corr_rl_h198) < 0.6 if not np.isnan(corr_rl_h198) else False
    print(f"\n══ SUMMARY ══════════════════════════════════════════════════")
    print(f"H204 RL ensemble OOS Sharpe:  {oos_sharpe:.3f}  Gate=0.8  "
          f"{'✓ CONFIRMED' if confirmed else '✗ NOT CONFIRMED'}")
    print(f"H198 baseline OOS Sharpe:     {sharpe(h198_oos):.3f}")
    print(f"Corr(H204, H198) OOS:         {corr_rl_h198:.3f}  "
          f"{'✓ <0.6' if corr_ok else '✗ ≥0.6'}")
    print(f"OOS MaxDD: {max_dd(oos_r):.1%}  NegYrs: {neg_years(oos_r)}")

    # ── Save results ──────────────────────────────────────────────────────────
    results = {
        "hypothesis": "H204",
        "description": "PPO Deep RL Portfolio (3-seed ensemble) vs H198 Momentum",
        "is_period":  f"{IS_START.date()} – {IS_END.date()}",
        "oos_period": f"{OOS_START.date()} – {OOS_END.date()}",
        "n_seeds": N_SEEDS, "timesteps_per_seed": TIMESTEPS,
        "is_sharpe":   float(sharpe(is_r)),
        "is_maxdd":    float(max_dd(is_r)),
        "oos_sharpe":  float(oos_sharpe),
        "oos_maxdd":   float(max_dd(oos_r)),
        "oos_cagr":    float(oos_r.mean() * 252 * 100),
        "oos_neg_yrs": int(neg_years(oos_r)),
        "oos_cumul":   float((1 + oos_r).prod()),
        "h198_oos_sharpe": float(sharpe(h198_oos)),
        "spy_oos_sharpe":  float(sharpe(spy_oos)),
        "corr_rl_h198":    float(corr_rl_h198) if not np.isnan(corr_rl_h198) else None,
        "corr_rl_spy":     float(corr_rl_spy)  if not np.isnan(corr_rl_spy)  else None,
        "confirmed":  bool(confirmed),
        "confirm_gate": "OOS Sharpe > 0.8",
        "secondary_corr_gate": "Corr(H204, H198) < 0.6",
        "secondary_corr_ok": bool(corr_ok),
    }
    out_path = RESULT_DIR / "h204_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
