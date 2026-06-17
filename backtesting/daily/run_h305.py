"""
H305 — Multi-Modal Earnings Direction Classifier
=================================================

Hypothesis:
  Upgrade H174 (FinBERT 8-K score + EPS surprise → PEAD) by adding 15
  fundamental features and 3 technical indicators, then training a binary
  Transformer classifier on the combined feature vector.

  Source: arXiv:2605.25894 — "Predicting Stock Price Direction on Earnings
  Announcement Days using Multi-modal Deep Learning" (Noseda, Soldati, Paina,
  May 2026). Design extension — paper uses press releases; H305 uses EDGAR
  8-K full-document FinBERT scores from H174 pipeline.

  Feature vector (20 dims):
    - finbert_score (from H174 EDGAR pipeline)
    - eps_surprise (actual - consensus, normalized)
    - 15 fundamentals via FMP: gross_margin, revenue_yoy, eps_yoy, pe_ratio,
      ps_ratio, fcf_yield, debt_equity, current_ratio, asset_growth,
      net_income_growth, operating_margin, rd_pct_revenue, buyback_yield,
      revenue_surprise, return_on_equity
    - 3 technicals: RSI_14, ATR_20_pct, ret_20d (pre-announcement)

  Binary label: 1 if 20-day forward return > +3%, else 0.
  Classifier: LSTM and Transformer (compare both).

  MASK-FIRST (arXiv:2507.07107):
    Fit MinMaxScaler on IS feature matrix ONLY.
    Apply to OOS using IS-fitted scaler.
    Never fit_transform on full sample.

  IS:  2015-01-01 to 2021-12-31
  OOS: 2022-01-01 to 2026-06-15
  Gate: OOS WR > 84% OR MeanRet > 8.5% (vs H174 baseline WR=81.8%, MeanRet=6.89%)
  Cost: ~$0 incremental (FMP quota, no new LLM calls)

Implementation TODO:
  1. Load H174 event database (EDGAR 8-K scored events with finbert_score + eps_surprise)
     → /workspace/agent/backtesting/paper_trading/pead_watchlist.json or rebuild from
       /workspace/agent/backtesting/daily/run_h174.py output
  2. For each event (ticker, date), pull 15 fundamentals from FMP API (quarterly TTM)
     → GET https://financialmodelingprep.com/api/v3/key-metrics/{ticker}?period=quarter
     → GET https://financialmodelingprep.com/api/v3/income-statement/{ticker}?period=quarter
  3. Pull 3 technicals from yfinance (14d RSI, 20d ATR as pct of price, 20d pre-event return)
  4. Build IS and OOS feature matrices
  5. Fit MinMaxScaler on IS ONLY → transform OOS with IS scaler
  6. Train LSTM (hidden=64, 2 layers, dropout=0.2) on IS with TimeSeriesSplit CV
  7. Train Transformer (d_model=32, nhead=4, nlayers=2) on IS
  8. Evaluate OOS: WR, MeanRet vs H174 gate
  9. Ensemble: if both models agree (score > 0.6), flag as HIGH CONFIDENCE entry
"""

raise NotImplementedError(
    "H305 is a stub — implementation required. "
    "See docstring above for full step-by-step design."
)
