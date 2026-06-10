# H269 — LLM High-Volume Ideation Sprint
# Source: arXiv:2409.04109 (Si et al. 2024) + Kevin direction 2026-06-09
#
# Idea: dedicated high-throughput ideation session — 15-20 raw factor/strategy ideas
# generated with no feasibility filter. Kevin picks 2-3 to develop further.
# LLM ideas rated MORE NOVEL than PhD students (Si et al.) — novelty is the goal,
# human feasibility filtering happens after.
#
# Sprint format:
#   1. George runs structured Claude API ideation prompt with novelty constraints
#   2. Output: 15-20 ideas organized by (signal type, data source, universe, mechanism)
#   3. Saved to dream_cycle/ideation/YYYY-MM-DD_sprint.md
#   4. Kevin flags 2-3 → become QUEUED hypotheses via normal pipeline
#
# Novelty constraints:
#   - Must be backtestable (concrete signal, not vague)
#   - Must name an accessible data source (EDGAR, yfinance, Alpaca, FRED, Polygon)
#   - Must not overlap with H159-H269 (checked against hypothesis log)
#
# Run on demand (Kevin request) or quarterly as research refresh
# Scaffold only — full implementation pending
