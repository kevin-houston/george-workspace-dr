---
title: awesome-codex-subagents
created: 2026-06-22
updated: 2026-06-22
category: tools
source: https://x.com/tom_doerr/status/2069056644793688477
github: https://github.com/VoltAgent/awesome-codex-subagents
stars: 5271
author: VoltAgent
license: MIT
status: active
---

# awesome-codex-subagents

Curated collection of 166+ specialized Codex subagents across 13 development categories. By VoltAgent (same org as the [voltagent](https://github.com/VoltAgent/voltagent) TypeScript agent framework). MIT, 5.2k stars.

## What It Is

Codex subagents are named `.toml` files that define a specialized AI assistant role, installed into `~/.codex/agents/` (global) or `.codex/agents/` (project-level). The pattern is analogous to Claude Code skills/slash commands — specialized instructions that a parent agent can delegate to.

## Installation

```bash
# Global (all projects)
mkdir -p ~/.codex/agents
cp categories/07-specialized-domains/quant-analyst.toml ~/.codex/agents/

# Project-specific (overrides global on name collision)
mkdir -p .codex/agents
cp categories/04-quality-security/code-reviewer.toml .codex/agents/
```

## Subagent Structure

```toml
name = "quant-analyst"
description = "Use when a task needs quantitative analysis of models, strategies..."
model = "gpt-5.4"
model_reasoning_effort = "high"
sandbox_mode = "read-only"

[instructions]
text = """..."""
```

**Smart model routing:** `gpt-5.4` for deep reasoning (architecture reviews, security audits, financial logic); `gpt-5.3-codex-spark` for fast scanning and lighter tasks.

**Sandbox modes:** `read-only` (reviewers, auditors) or `workspace-write` (developers, engineers).

## 13 Categories

| # | Category | Count | Notable Agents |
|---|----------|-------|---------------|
| 01 | Core Development | 12 | api-designer, backend-developer, ui-fixer |
| 02 | Language Specialists | 30 | python-pro, typescript-pro, rust-engineer |
| 03 | Infrastructure | 16 | cloud-architect, kubernetes-specialist, terraform-engineer |
| 04 | Quality & Security | 19 | code-reviewer, security-auditor, penetration-tester |
| 05 | Data & AI | 13 | llm-architect, ml-engineer, reinforcement-learning-engineer |
| 06 | Developer Experience | 14 | mcp-developer, refactoring-specialist, readme-generator |
| 07 | Specialized Domains | 13 | **quant-analyst**, **fintech-engineer**, blockchain-developer |
| 08 | Business & Product | 16 | assumption-mapping, backlog-grooming |
| 09–13 | (docs, AI agents, research, ops, etc.) | ~49 | — |

## Most Relevant: quant-analyst

Uses `gpt-5.4` + `model_reasoning_effort = "high"` + `sandbox_mode = "read-only"`. Its checklist is worth reading as a template for what a rigorous quant review agent should validate:

**Focus areas:**
- Model/strategy assumption clarity and domain validity conditions
- Backtest/simulation design quality and **data-leakage prevention**
- Risk-adjusted performance interpretation (beyond raw returns)
- Sensitivity analysis across regime changes and parameter shifts
- Execution assumptions (slippage, latency, liquidity, transaction costs)
- Statistical confidence and overfitting risk controls

**Quality checks:**
- Metrics and conclusions align with realistic execution assumptions
- Out-of-sample robustness considered before recommending
- **Lookahead bias / leakage checked in inputs and methodology**
- Caveats and uncertainty explicit in proposed decisions
- Additional experiments needed to validate robustness called out

> "Do not present simulated performance as real-world guarantee unless explicitly requested by the parent agent."

This checklist is essentially a formalized version of our own `shared-eval-checklist.md` and the H174/H320 evaluation gates, but written as an agent persona.

## Most Relevant: fintech-engineer

`gpt-5.4`, `workspace-write`. Focuses on ledger integrity, idempotent transactions, reconciliation, audit trails. Relevant for paper→live trading infrastructure and Alpaca order management safety.

## Relevance to George / Kevin's Stack

- **Codex, not Claude Code:** These `.toml` files are for OpenAI Codex specifically. Not directly importable into Claude Code.
- **Pattern value:** The `quant-analyst` persona is a useful template for what a hypothesis review agent should check — directly applicable to dream cycle build-phase reviews or H323 implementation validation.
- **`mcp-developer` subagent (cat. 06):** Could be useful reference for building Codex ↔ MCP integrations (similar to hermes-gpt pattern).
- If Kevin uses Codex alongside George, these drop directly into `~/.codex/agents/` and are immediately usable.

## Cross-References

- [hermes-gpt](../tools/hermes-gpt.md) — same organizational pattern (subagent roles) for ChatGPT via Hermes Agent
- [Multi-Agent LLM Trading](../trading/algorithms/multi-agent-llm-trading.md) — agent role decomposition patterns
- [Shared Strategy Evaluation Checklist](../trading/shared-eval-checklist.md) — quant-analyst checklist is a close analog
