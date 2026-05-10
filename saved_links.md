# Saved Links

Kevin's saved articles, posts, and links for later reference.

---

## 2026-05-09

### OpenHuman — Open-source agentic desktop assistant (Kevin calls it "open brain")
- **Repo:** https://github.com/tinyhumansai/openhuman
- **Site:** https://tinyhumans.ai/openhuman
- **Install:** `curl -fsSL https://raw.githubusercontent.com/tinyhumansai/openhuman/main/scripts/install.sh | bash`
- **Stack:** Rust (69%) + TypeScript (27%), GPL-3.0, early beta — 549 stars, 44 tags, 1,636 commits
- **Key features:** Memory Tree (≤3k-token Markdown chunks, scored + hierarchical, SQLite-backed, Obsidian vault mirror), 20-min auto-fetch loop (Gmail/Calendar/GitHub/Slack/Notion/118+ OAuth), TokenJuice (80% token compression), model routing (reasoning/fast/vision), native voice (ElevenLabs TTS, STT, Google Meet integration), desktop mascot
- **Architecture of note:** Karpathy-style Obsidian wiki auto-built from connected services. Every ingested item → canonicalized chunk → scored → folded into hierarchical summary trees → SQLite + .md files
- **Intent:** Kevin plans to set this up in the near future as a more sophisticated memory/ingestion layer
- **Saved by Kevin:** 2026-05-09

---

### EvoScientist — Self-evolving AI scientist framework
- **Repo:** https://github.com/EvoScientist/EvoScientist
- **Stars:** 2.8k stars, 181 forks, Apache 2.0, Python
- **Tagline:** "Harness Vibe Research with Self-evolving AI Scientists"
- **What it is:** Autonomous research agent system with 6 coordinated sub-agents (plan, research, code, debug, analyze, write). "Human-on-the-loop" paradigm — AI acts as a research buddy that co-evolves with the researcher. Persistent memory across sessions. Full lifecycle: intake → plan → execute → evaluate → write → verify.
- **Key features:** Multi-model (Anthropic/OpenAI/Google/MiniMax/NVIDIA), multi-channel (CLI + Telegram/Slack/WeChat), dynamic system prompt rewriting, MCP server support, installable GitHub skills, per-turn tool selection
- **Benchmarks:** #1 on DeepResearch Bench I & II, #1 on AstaBench Code & Execution and Data Analysis, ICAIS 2025 Best Paper — legitimate signals, not just hype
- **Relevance:** Most directly relevant to the nightly hypothesis research loop — could automate parts of the plan/research/code/analyze pipeline. The Telegram integration mirrors how Kevin and I work. Memory + self-evolution connects to the OpenHuman direction.
- **Saved by Kevin:** 2026-05-09

---

### AI Obsidian Plugins — Curated GitHub repo (danielrosehill)
- **Tweet:** https://x.com/aiedge_/status/2053233603937714474 (via @aiedge_, 2026-05-09)
- **Repo:** https://github.com/danielrosehill/Obisidian-For-LLM-Obsessed
- **Summary:** Curated collection of the best Obsidian plugins that use AI — for building an AI second brain / memory layer in Obsidian
- **Context:** Relevant to OpenHuman ("open brain") setup — OpenHuman mirrors memory into an Obsidian vault; these plugins extend that vault with AI capabilities
- **Saved by Kevin:** 2026-05-09

---

### @RoundtableSpace tweet — Modular Claude Code AI dev team structure
- **Tweet:** https://x.com/roundtablespace/status/2052935335156342958
- **Author:** 0xMarioNawfal (@RoundtableSpace) — 59.8K views, 81 likes, 84 bookmarks
- **Content:** "DEVELOPERS ARE STRUCTURING CLAUDE CODE LIKE A FULL AI DEV TEAM USING MODULAR AGENT SYSTEMS. The setup separates memory, workflows, guardrails, delegated agents, and plugins into organized layers that automate complex software tasks."
- **Quoting:** @dr_cintas (Alvaro Cintas, May 7): "How to set up Claude Code so it runs like a full dev team: 5 folders. 1. CLAUDE.md → Memory (repo constitution, naming rules, global + local). 2. skills/ → Knowledge."
- **Relevance:** Directly describes what George is — a modular Claude Code agent with CLAUDE.md, `.local-fragments/`, wiki, and skill layers. The Perplexity gotchas flywheel work today is an extension of this exact pattern.
- **Saved by Kevin:** 2026-05-09

---

### zero-native — Zig framework for native desktop/mobile apps with web UI
- **Tweet:** https://x.com/ctatedev/status/2052907884728467699
- **Repo:** https://github.com/vercel-labs/zero-native
- **Author:** Chris Tate (@ctatedev) — Developer at Vercel
- **What it does:** Desktop/mobile app shell that wraps a web frontend (Next.js, React, Svelte, Vue) in a native binary. Built in Zig — tiny binaries, fast startup. Choose between system WebView (tiny) or bundled Chromium/CEF (consistent rendering). JS bridge via `window.zero.invoke()`. Security-by-default: native commands require explicit opt-in permissions. Targets macOS, Linux, Windows, iOS, Android.
- **Relevance:** Potential path to packaging the trading dashboard as a native desktop app without Electron bloat.
- **Saved by Kevin:** 2026-05-09

---

### agent-browser — Vercel Labs browser automation CLI for AI agents
- **Tweet:** https://x.com/ctatedev/status/2052907884728467699
- **Repo:** https://github.com/vercel-labs/agent-browser
- **Author:** Chris Tate (@ctatedev) — Developer at Vercel
- **What it does:** Rust CLI for browser automation designed specifically for AI agents. Headed or headless. Zero config. Claims 93% less context than Playwright MCP. Works with Claude Code, Codex, Gemini, Cursor, Copilot, any Bash-capable agent.
- **Status:** Already installed as a skill (`~/.claude/skills/agent-browser`). I can use it now for web browsing, form-filling, screenshots, page testing.
- **Saved by Kevin:** 2026-05-09

---

## 2026-05-07

### QuantEcon — "Quantitative Economics with Python" (Sargent & Stachurski)
- **URL:** https://quantecon.org/py/index.html
- **Authors:** Thomas J. Sargent (Nobel 2011), John Stachurski
- **Type:** Open textbook — free online + PDF
- **Covers:** Dynamic programming, Markov chains, asset pricing, linear algebra, time series, econometrics, optimal stopping, calibration — all in Python (NumPy/SciPy/Matplotlib/JAX)
- **Relevance:** Reference for quantitative methods underlying the trading pipeline — particularly DP/optimal stopping (options), Markov chain modeling (regime switching), and econometric calibration
- **Saved by Kevin:** 2026-05-07

---

### SSRN 6630998 — "Short-Term Reversal Persists Globally—If Properly Measured"
- **URL:** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6630998
- **Authors:** Jan Stosik, Adam Zaremba
- **Date:** April 22, 2026
- **Core finding:** Standard reversal = 0.05%/month globally (insignificant). Industry-adjusted reversal (`REV^IN = R_i − R̄_industry`) = 0.53%/month, Sharpe 0.74, six-factor alpha 0.60% (t=4.14). Significant in 22/64 countries. Regret signal (0.40%/month) subsumed by industry-adjusted.
- **Data:** 64 countries, Jan 1990–Dec 2023, 5.79M monthly observations
- **Wiki:** [algorithms/short-term-reversal.md](wiki/trading/algorithms/short-term-reversal.md)
- **Hypothesis:** H181 (queued — industry-adjusted reversal, US stocks)
- **Saved by Kevin:** 2026-05-07

---

## 2026-05-06

### Anatoli Kopadze — X Article (paywalled)
- **Tweet:** https://x.com/anatolikopadze/status/2050225292585607440
- **Links to:** https://x.com/i/article/2050193934458978304 (X native article)
- **Author:** Anatoli Kopadze (@AnatoliKopadze) — tech/AI commentator, 31k+ posts
- **Note:** X native article, requires X subscription to read. Content unavailable. Kopadze has been posting about Claude coding demos and AI productivity around this period.
- **Saved by Kevin:** 2026-05-06
