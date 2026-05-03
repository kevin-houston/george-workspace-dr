# SAE Company Similarity for Pairs Trading

**Source**: arXiv:2412.02605 — "Interpretable Company Similarity with Sparse Autoencoders"
**Venue**: ACL 2025 Industry Track, Vienna (peer-reviewed)
**Authors**: Molinari et al.
**GitHub**: https://github.com/FlexCode29/company_similarity_sae
**Pre-computed features**: HuggingFace `marco-molinari/company_reports_with_features`

## Summary

Applies Sparse Autoencoders (SAEs) to decompose Llama 3.1 8B internal activations when processing SEC 10-K company descriptions. The sparse feature vectors provide interpretable, scalable company similarity scores that outperform traditional SIC codes and semantic embeddings for pairs trading.

## Architecture

- **LLM**: Llama 3.1 8B
- **Layer**: 30 (≈90% model depth, via residual stream)
- **SAE**: EleutherAI/sae-llama-3-8b-32x (pre-trained)
  - TopK activation, k=128
  - Input: 4,096 dims
  - Output: 131,072 dims (32x expansion)
- **Dataset**: 27,888 SEC 10-K annual reports, 1996-2020

## Pairs Trading Performance (Out-of-Sample 2014-2020)

| Method | Sharpe |
|--------|--------|
| SAE GCD | **12.18** |
| SAE GCD Rolling | 9.69 |
| PaLM-gecko Embeddings | 10.57 |
| SIC Codes | 9.70 |
| BERT Embeddings | 7.58 |
| SBERT | 7.69 |

## Cointegration Strategy Details
- Pre-selection: Pearson correlation > 0.95 in-sample (2002-2013)
- Cointegration: Engle-Granger ADF, p < 0.01
- Entry: spread > ±1σ; exit: mean reversion; stop: ±2σ
- Out-of-sample: 2014-2020

## Application to R29

Add as Stage 1.5 in R29 pipeline:
1. Factor residualize returns (Stage 0)
2. SPONGEsym graph cluster (Stage 0.5)
3. **SAE cluster filter** (Stage 1.5) — download pre-computed features from HuggingFace
4. Cointegration test (Stage 1)
5. LLM economic plausibility (Stage 2)
6. Kelly-sized trade (Stage 3)

Cost: SAE is pre-computed (free HuggingFace download). No API calls required for this stage.

## Notes

- GPU not required if using pre-computed features (EleutherAI computed them; HuggingFace hosts)
- PCA file required for GCD algorithm (linked via Google Drive in repo README)
- For stocks not in dataset (post-2020 additions): use sector ETF proxy or run EDGAR 10-K + SAE inference
