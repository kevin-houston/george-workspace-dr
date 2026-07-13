# AI Today — Monday, July 13, 2026

*Hosts: Alex and Jordan | Runtime: ~20 minutes*

---

## Segment 1: The Token Overhead Hiding Inside Your Coding Agent

**Alex:** Good morning, and welcome to AI Today. I'm Alex.

**Jordan:** And I'm Jordan. It's Monday, we've got a technically dense show today, and I want to warn listeners up front: there's a theme running through basically everything. You cannot trust surface-level numbers when it comes to AI tooling costs. You have to measure at the boundary.

**Alex:** Perfect setup for our first story. Systima AI — a firm focused on agentic AI for regulated industries — published a twenty-minute deep read on Saturday called "Claude Code Is Way More Token-Hungry Than OpenCode. We Measured Exactly How Much." It went to the top of Hacker News with 604 points and 327 comments, and it deserves that attention.

**Jordan:** The method is the right one. They spliced a logging proxy between each coding harness and the model endpoint, capturing the exact JSON payload the harness sent and the exact usage block the API returned. Ground truth on both sides.

**Alex:** And the headline number is stark. When you ask Claude Code and OpenCode to do the exact same one-line task — "Reply with exactly: OK" — Claude Code sends roughly 33,000 tokens before the prompt arrives. OpenCode sends about 7,000. That's a 4.7x gap, and it's almost entirely tool schemas.

**Jordan:** Claude Code ships 27 tools, totaling 99,778 characters of schema. OpenCode ships 10, totaling 20,856. The extra tools are real: Claude Code's catalog includes background-agent orchestration, worktree management, push notifications, a scheduler — the full platform stack. OpenCode's is a stripped-down coding core. Claude Code also injects three system-reminder blocks into its first message: a catalog of agent types, a catalog of available skills, and user context. All of that costs tokens on every request.

**Alex:** Now here's the finding that I think has the most operational consequence: cache instability. Prompt caching is supposed to defray those costs — you write the prefix once and read it back cheaply. But it only works if the prefix stays stable. On the same file-summarization task, Claude Code wrote 53,839 cache tokens across five requests, including one complete mid-task rewrite of its full 43,000-token prefix. OpenCode wrote 1,003 cache tokens. Same task — 54 times more cache writes from Claude Code.

**Jordan:** The multipliers stack quickly in production. A 72KB instruction file — a real CLAUDE.md from a production repo — adds over 20,000 tokens to every single request. Five modest MCP servers add another 5,000 to 7,000. By the time a typical production setup sends its first request, it's 75,000 to 85,000 tokens in before the user has typed a word.

**Alex:** Subagents are the steepest cliff. A task that took 121,000 tokens when done directly cost 513,000 tokens when fanned out to two subagents — a 4.2x multiplier — because every subagent pays its own bootstrap and its full transcript flows back to the parent.

**Jordan:** One result did favor Claude Code: on a multi-step write-run-test-fix task, Claude Code batched the entire job into three model requests by parallelizing tool calls. OpenCode made nine sequential requests, re-paying its baseline nine times. Totals converged. The metric is whole-task input, not per-request baseline.

**Alex:** One nuance worth flagging: on Claude Fable 5, the gap narrowed from 4.7x to 3.3x. Claude Code sends substantially less system prompt doctrine to newer models — 27,787 characters to Sonnet but only 10,526 to Fable. OpenCode's payload was byte-identical across both models. The ratio is model-dependent, not a constant.

**Jordan:** The practical takeaway: if you're making tooling or model decisions based on the pricing page, you're measuring the wrong thing. Instrument at the API boundary, as Systima did. The full post is at systima.ai/blog/claude-code-vs-opencode-token-overhead — twenty minutes well spent if you run agents in production.

---

## Segment 2: What GPT-5.6 Actually Costs in Production

**Alex:** Story two is a production migration report, and it validates the theme from segment one in a different way. Ploy — a startup that builds and optimizes marketing websites using an AI agent — published a detailed account of migrating from Claude Opus 4.8 to GPT-5.6 Sol. It surfaced on Hacker News today with 213 points and 91 comments.

**Jordan:** The headline numbers are good: 2.2 times faster to a finished page — wall-clock time dropped from eight minutes to three minutes and forty-two seconds. Twenty-seven percent cheaper per completed build, from $3.06 down to $2.22. Visual quality score actually went up, from 0.936 to 0.970. On output tokens, GPT-5.6 wrote 17,000 versus Opus's 33,000 — leaner code, fewer unused CSS variables, same rendered result.

**Alex:** That's the headline. Here's the migration report underneath it. Three things went wrong before they got there.

**Jordan:** The first was tool call behavior. Ploy's agent has a code tool with 25 top-level parameters, one required and 24 optional. Claude sends only the ones it's using. GPT-5.6 sends all 25, every time — inventing plausible values for the ones it doesn't need: offset zero, timeout 120,000, siteId with a zeroed UUID. They logged 6,635 GPT-5.6 tool calls and found all 25 parameters present in every single one of them. Claude sent the full set in 0.1% of calls.

**Alex:** The problem is that an invented value is indistinguishable from an intended one. Offset zero was being passed to their file-read implementation as a real argument, and 52 to 64 percent of GPT-5.6's file reads were coming back empty as a result. The model didn't know — it just did the work worse. Prompting didn't fix it; OpenAI's strict mode didn't fix it. The fix that worked was a schema transform at the provider boundary: rewrite every optional parameter to anyOf T or null, giving the model an explicit way to signal "not using this," then strip the nulls before the tool sees them. After that change, empty file reads went from 52 percent to zero, and the agent needed about 30 percent fewer tool calls for the same work.

**Jordan:** The second problem was prompt caching. Before they fixed it, GPT-5.6 looked about 50 percent more expensive than Opus. Every dollar of that gap was cache misconfiguration, not model pricing.

**Alex:** GPT-5.6 changed OpenAI's caching model. Earlier GPT models cached on partial prefix matches implicitly. GPT-5.6 dropped that; it now requires explicit cache breakpoints with a prompt_cache_key, and the key is part of cache identity. A new conversation sharing the same 29,000-token static prefix cached zero percent of it until they added the key. Scoping the key per-conversation also fails: no session ever hits the shared prefix. The correct scope is per-workspace, so all conversations in a customer workspace share the cache entry while per-key traffic stays within OpenAI's roughly 15-requests-per-minute limit per node. After switching to workspace-scoped keys, first-call cache hit rate went from zero to 83.7 percent, uncached input tokens dropped 28 percent, and GPT-5.6's per-suite cost landed below Opus's.

**Jordan:** The third fix was short but it broke real conversations: GPT-5.6's Responses API replays prior-turn reasoning as server-side item references by default. Conversations were failing mid-session with "Item not found" errors. Setting store false makes the SDK request encrypted reasoning blobs and replay them self-contained, without server state references.

**Alex:** The post is a useful migration guide, and it reinforces something we covered last week: every provider has its own caching semantics, and cold-cache cost comparisons between models are measuring your configuration, not the model. Full post at ploy.ai/blog/migrating-a-production-ai-agent-to-gpt-5-6.

---

## Segment 3: What xAI's Grok CLI Is Sending Over the Wire

**Alex:** Story three is the one that's going to get forwarded to security teams today. A researcher using the handle cereblab published a wire-level teardown of xAI's Grok Build coding CLI — version 0.2.93 — on GitHub Gist. It reached 478 points and 173 comments on Hacker News, and it's independently confirmed by at least two other researchers.

**Jordan:** The method is reproducible: the researcher routed all Grok traffic through mitmproxy, capturing the exact payloads. The findings are specific and backed by SHA-256-verified artifacts.

**Alex:** Three things worth knowing. First: when Grok reads a file — including a .env secrets file — it transmits the contents verbatim and unredacted to xAI's /v1/responses endpoint, and the same content is packaged into a session archive uploaded to persistent storage. The researcher used canary values — fake secrets with unique markers — and could grep them back out of the captured request bodies. A dot-env file is treated like any other file.

**Jordan:** Second, and this is the more surprising finding: Grok uploads the entire repository as a git bundle, independent of what the agent reads. On a 12-gigabyte repository where the prompt was "reply OK, do not read any files," the /v1/responses channel moved 192 kilobytes — model turns only. The /v1/storage channel moved 5.1 gigabytes, all HTTP 200, zero failures before the capture was truncated. That's a 27,800-to-one ratio. The researcher then git-cloned a wire-captured bundle from a separate run and recovered a file the agent was explicitly told not to open, with its unique canary marker intact and the full git history present.

**Alex:** The destination is a Google Cloud Storage bucket called grok-code-session-traces, named verbatim in the binary's own source paths. The binary ships a first-party Rust crate called xai-data-collector.

**Jordan:** Third: the "Improve the model" opt-out makes no difference. After turning it off, the researcher re-ran on the same repository. The /v1/settings response from the server still returned trace_upload_enabled: true, upload_enabled: true, session_registry_enabled: true. The git bundle still uploaded. The toggle governs whether xAI trains on the data, which is a policy question. The upload happens either way.

**Alex:** As of this morning, a commenter notes that the server is presently returning trace_upload_enabled: false — uploads may be paused remotely — but the client capability remains in place. The mitigation that was confirmed to work: setting disable_codebase_upload to true under the harness section in ~/.grok/config.toml. There's a hardening repo at github.com/wetlink/grok-build-privacy-hardening with a canary verification script.

**Jordan:** The researcher is careful about scope: this doesn't prove xAI trains on the data, the captures are version-specific to 0.2.93, and xAI may change behavior. The defensible statement is that transmission, acceptance, and storage are proven for this version. If you're running Grok on a codebase with real secrets or proprietary source, now is the time to check. The full analysis is at the gist linked in the Hacker News thread.

---

## Segment 4: A Rust Hook That Blocks Dangerous Agent Commands

**Jordan:** Final story, and it follows naturally from what we've been discussing: an open-source tool designed to protect you from what your coding agent might do next. Destructive Command Guard — dcg — is currently the number-two trending Rust repository on GitHub today, picking up 444 stars in the past 24 hours on a total of 3,574.

**Alex:** The premise is simple. AI coding agents occasionally run commands that destroy work: git reset --hard, rm -rf on a source directory, DROP TABLE in a migration. dcg is a hook that intercepts those commands before they execute, across every major coding agent.

**Jordan:** The supported list is longer than you might expect: Claude Code, Codex CLI, Gemini CLI, GitHub Copilot CLI, VS Code Copilot Chat, Cursor, Hermes Agent, and Grok — with native hook integration for each, not workarounds. Install is one line: curl the install script from GitHub, which detects your platform and configures the appropriate hooks automatically. Works on Linux, macOS, and Windows via WSL.

**Alex:** The engineering emphasis is on latency. The hook runs for every single tool call, so it has to be invisible. The implementation is written in Rust with SIMD-accelerated pattern matching, and the benchmark numbers claim sub-millisecond filtering. There's also context-aware parsing: dcg won't block the string "rm -rf" inside a grep pattern or a code comment, but it will block it as an actual execution context. That distinction matters — naive string matching would generate constant false positives.

**Jordan:** Coverage goes well beyond basic filesystem and git commands. There are over 50 security packs for specific domains: database commands across PostgreSQL, MySQL, and MongoDB; Kubernetes operations; Docker; AWS, GCP, and Azure CLI commands; Terraform destructive operations; and more. You can install only the packs you need.

**Alex:** One detail worth highlighting: dcg also scans heredocs and inline scripts. An agent that can't run rm -rf directly might construct python -c "import os; os.remove(...)" or a bash heredoc to accomplish the same thing. The tool uses AST-level parsing via ast-grep to catch those patterns, not just surface string matching.

**Jordan:** The design philosophy is fail-open: if dcg itself encounters a timeout or parse error, it allows the command through rather than blocking your workflow. When it does block, the output is structured differently on stdout versus stderr — machine-readable denial on stdout for the harness to parse, human-readable panel with the rule context and safer alternatives on stderr for you to read.

**Alex:** If you've been running coding agents in bypassPermissions mode or with broad shell access and haven't thought about a safety layer, dcg is probably the easiest entry point. It's MIT licensed, the one-liner installer takes under a minute, and the packs can be scoped to exactly the domains you care about. github.com/Dicklesworthstone/destructive_command_guard.

---

## Closing

**Jordan:** That's four for Monday. The thread connecting everything: measure at the boundary. Whether that's token overhead at the API level, provider caching semantics during a model migration, what your coding CLI actually puts on the wire, or what commands your agent is about to execute — surface-level assumptions are costing people real money and real security exposure right now. All four of today's stories are engineers who went to the actual evidence.

**Alex:** Sources in the show notes. Back tomorrow.

**Jordan:** Have a good Monday.

---

*Sources:*
- *Systima AI (July 12, 2026): systima.ai/blog/claude-code-vs-opencode-token-overhead — verified via Hacker News (604 points, 327 comments)*
- *Ploy (July 8, 2026): ploy.ai/blog/migrating-a-production-ai-agent-to-gpt-5-6 — verified via Hacker News (213 points, 91 comments)*
- *cereblab gist (July 11–13, 2026): gist.github.com/cereblab/dc9a40bc26120f4540e4e09b75ffb547 — verified via Hacker News (478 points, 173 comments) and independent confirmation by @wetlink*
- *dcg (github.com/Dicklesworthstone/destructive_command_guard) — verified via GitHub Trending Rust #2 today (444 stars today, 3,574 total)*
