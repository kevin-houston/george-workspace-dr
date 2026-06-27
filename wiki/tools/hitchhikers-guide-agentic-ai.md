---
title: "The Hitchhiker's Guide to Agentic AI: From Foundations to Systems"
url: https://arxiv.org/abs/2606.24937
added: 2026-06-26
category: tools/reference
type: survey/practitioner-guide
author: Haggai Roitman (IBM Research)
submitted: 2026-06-22
arxiv: "2606.24937"
---

# The Hitchhiker's Guide to Agentic AI

Comprehensive practitioner's reference covering the full agentic AI stack — from LLM internals to production multi-agent systems. Pairs theoretical foundations with implementation guidance and code examples.

## Structure (5 layers)

1. **LLM Foundations** — Transformer architecture, GPU systems, training (SFT, LoRA, MoE), model compression, inference optimization

2. **Alignment & Reasoning** — RLHF, PPO, DPO variants, GRPO, reward modeling, chain-of-thought, test-time scaling

3. **Agentic Systems** — Trajectory-based RL, RAG implementations, memory architectures, agent design patterns, context management

4. **Multi-Agent Coordination** — Model Context Protocol (MCP), tool integration, A2A communication, network topologies

5. **Production Deployment** — Development frameworks, UI design, evaluation methodologies, deployment strategies

## Relevance to George's workflow

- **MCP architecture**: Layer 4 covers MCP + A2A — directly relevant to George's tool stack and NanoClaw wiring
- **Multi-agent patterns**: Layer 4 topology guidance applies to H274 (PEAD 3-agent debate design) and CBS evaluation
- **RAG implementations**: Layer 3 applies to H319 (LLM semantic network, 10-K embeddings)
- **Evaluation methodologies**: Layer 5 is a reference for agent eval frameworks beyond backtesting
- **Memory architectures**: Layer 3 memory patterns relevant to George's wiki + CLAUDE.local.md design

## Status

Reference only. No code/dataset released (guide paper). Use as lookup when designing multi-agent or RAG components.
