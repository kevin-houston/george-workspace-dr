# H324 — Speaker-Weighted FinBERT PEAD
# Source: arXiv:2604.13260 (Liu et al. 2026)
# Hypothesis: Weighting FinBERT sentiment by speaker role (Analyst 49%,
# CFO 30%, Exec 16%, Other 5%) improves H174 signal quality without
# reducing sample size, since no additional filter gates are applied.
#
# Key difference from H174:
#   H174: single FinBERT score over full 8-K text, threshold >= 0.18
#   H324: parse transcript into speaker sections, FinBERT per section,
#         compute weighted_score = 0.49*analyst + 0.30*cfo + 0.16*exec + 0.05*other
#         entry threshold: weighted_score >= 0.18 (same as H174)
#
# Design:
# - Universe: same 30-stock H163/H174 universe
# - Source: EDGAR 8-K text already cached at backtesting/cache/h163_finbert_scores.parquet
# - Speaker parsing: regex on common patterns:
#     'OPERATOR:', 'ANALYST:', 'Q:', 'Question:' -> analyst
#     'CFO:', 'CHIEF FINANCIAL OFFICER:', 'Chief Financial Officer' -> cfo
#     'CEO:', 'CHIEF EXECUTIVE OFFICER:' -> exec
# - FinBERT: ProsusAI/finbert, batch mode per section
# - IS: 2021-2023 | OOS: 2024-2026 (same as H317)
# - Gate: WR > 70% AND n >= 20 AND mean_ret > 4%
# - Also check: is OOS WR higher than H174 baseline 81.8% (with same or more n)?
#
# Note: if EDGAR 8-K text doesn't have speaker-segmented format (some are
# plain text, some are structured), fall back to H174 uniform scoring.
# Hypothesis is CONFIRMED only if speaker-weighting outperforms uniform weighting
# on matched OOS events.
#
# Cache: h163_finbert_scores.parquet has full 8-K text. Speaker parsing is
# a post-processing step applied to the same cached text.
#
# Cross-reference: wiki/trading/algorithms/event-driven.md (H174 design)
pass
