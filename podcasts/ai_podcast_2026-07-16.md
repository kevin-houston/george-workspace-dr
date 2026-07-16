# Daily AI Insights — Thursday, July 16, 2026

## Hosts
- **Alex** (en-US-GuyNeural)
- **Jordan** (en-US-JennyNeural)

## Sources
1. Thinking Machines Lab — Inkling announcement: https://thinkingmachines.ai/inkling/
2. xAI / SpaceXAI — grok-build GitHub repo: https://github.com/xai-org/grok-build
3. HN thread "Grok Build is open source" — 469 points, 510 comments
4. Greg Sadetsky — "LLM Networking with MikroTik": https://greg.technology/blog/llm-networking-mikrotik
5. HN thread "LLM Networking with MikroTik" — 92 points
6. IEEE Spectrum — "High Bandwidth Flash Unlocks Massive Model Storage": https://spectrum.ieee.org/high-bandwidth-flash
7. HN thread "High-Bandwidth Flash offers efficient storage for model weights" — 49 points

---

## INTRO

**Alex:** Good morning, and welcome to Daily AI Insights. I'm Alex.

**Jordan:** And I'm Jordan. It is Thursday, July 16th, and there's a lot happening. A brand new open-weights model from a lab most people hadn't heard of yesterday, a major coding agent that just dropped its source code, someone's been letting LLMs configure their home and office networks, and a new memory technology that could reshape AI inference hardware in a few years.

**Alex:** Good mix. Something new, something open-source, something scrappy, and something that matters even though it's not shipping yet. Let's get into it.

---

## SEGMENT 1: Inkling — A New Open-Weights Contender

**Alex:** Story one: a company called Thinking Machines Lab just released an open-weights model called Inkling, and it landed on Hacker News with over a thousand points and 250-plus comments. That's the kind of traction you usually see for a major GPT release.

**Jordan:** So who is Thinking Machines? They describe their mission as building AI that "extends human will and judgment." They've been quietly developing a fine-tuning platform called Tinker, and Inkling is the model that powers it — now released with full weights.

**Alex:** The specs are notable. Inkling is a Mixture-of-Experts transformer — 975 billion total parameters, 41 billion active. It was pretrained on 45 trillion tokens of text, images, audio, and video. Context window is one million tokens. And it reasons natively over text, images, and audio in one unified model — not as bolted-on modes.

**Jordan:** The 41 billion active parameter count is the number that matters for inference compute. That puts it in the range of serious production models, while the MoE architecture means there's a much larger parameter bank backing it without proportional inference cost.

**Alex:** What I find most interesting is the benchmark positioning. They're comparing Inkling against Nemotron 3 Ultra, GLM 5.2, GPT 5.6 Sol, and Claude Fable 5 — and they explicitly say: Inkling is not the strongest model today, open or closed. They're not claiming to win on any single benchmark.

**Jordan:** What are they claiming?

**Alex:** Breadth. The argument is that the best base model for customization isn't the one with the highest benchmark ceiling — it's the one that's strong across many domains, flexible enough to adapt, and actually available in a form you can fine-tune. Inkling is open-weights, immediately available for fine-tuning on Tinker, with a playground for developers to test it directly.

**Jordan:** And they showed that with a remarkable demo. Using the Tinker console, Inkling fine-tuned itself — wrote the fine-tuning job, ran it, evaluated the result. They show it running inside an OpenCode harness, which is a nice nod to the coding agent ecosystem.

**Alex:** They also ship a companion model called Inkling-Small — 12 billion active parameters, trained with the same recipe, lower cost and latency. So it's a model family, not a one-off.

**Jordan:** The strategic bet here is clear. Frontier model performance is converging. The differentiation is shifting to the customization layer. If you believe that, owning the fine-tuning platform and releasing the base model is exactly the right play.

**Alex:** Inkling is on Hugging Face now. Full weights, available to fine-tune on Tinker today.

---

## SEGMENT 2: Grok Build Goes Open Source

**Alex:** Story two: SpaceXAI just open-sourced Grok Build — their terminal-based AI coding agent. The repository hit Hacker News with 469 points and 510 comments. That comment count puts it among the most-discussed threads of the week.

**Jordan:** This is significant timing. Claude Code, OpenCode, and others are all competing in the coding agent category. Dropping Grok Build's source into the mix changes the conversation.

**Alex:** Let me describe what Grok Build actually is. It's a full-screen TUI — terminal user interface — written in Rust. It runs as a coding agent: understands your codebase, edits files, executes shell commands, searches the web, manages long-running tasks. You can run it interactively, headlessly for scripting or CI, or embedded in editors via something called the Agent Client Protocol.

**Jordan:** The Rust implementation is significant. Most coding agent harnesses are Python or TypeScript. Rust gives you the performance characteristics that matter for a responsive TUI — you're not fighting async Python overhead when you're streaming LLM output into a terminal the user is watching.

**Alex:** The repo went from zero to 8,800 stars and 1,400 forks in the hours after launch. That's a productive open-source debut.

**Jordan:** What's in the codebase?

**Alex:** The core is the xai-grok-pager binary — TUI and agent runtime. Supports macOS, Linux, and Windows. The notable thing architecturally is the Agent Client Protocol, or ACP. It's a standardized protocol so editors can communicate with the agent harness — their version of LSP for AI agents.

**Jordan:** That's the detail I'd watch closely. LSP — the Language Server Protocol — became critical infrastructure. It's why VS Code and Neovim can share the same language server. If ACP gains similar traction, it means coding agents stop being tightly coupled to one product.

**Alex:** Which is clearly in SpaceXAI's interest. They want Grok accessible in any editor, so they're motivated to push for an open protocol. Whether the community adopts it depends on whether Claude Code and others build against it too.

**Jordan:** The release structure is worth noting. This is a clean open-source dump from their internal monorepo — a single commit, "Publish harness and TUI open-source." They'll sync periodically. It's the same model Meta uses for Llama weights: you get the artifact, not the development history.

**Alex:** For practitioners: the harness of a production AI coding agent is now readable. How they handle tool dispatch, session management, long-running task coordination — it's all there. Instructive whether you're building your own tooling or just trying to understand how these systems work.

---

## SEGMENT 3: Vibe Networking — LLMs Meet MikroTik

**Jordan:** Story three is the most fun one today. A developer named Greg Sadetsky published a blog post called "LLM Networking with MikroTik" — 92 Hacker News points, and a comment section full of people who've done similar things and wanted to share notes.

**Alex:** Greg has been using Claude Code to set up small networks using MikroTik hardware. For those outside networking circles: MikroTik makes inexpensive, reliable, feature-rich routers and switches. The running joke is that you can do almost anything with a MikroTik, as long as you're willing to absorb the documentation for a hundred hours first.

**Jordan:** And the LLM apparently already absorbed it.

**Alex:** That's exactly the framing. Greg calls LLMs "chaotic force multipliers" for niche technical work. They know MikroTik. They know networking concepts. They let a half-experienced practitioner — his self-description — accomplish things he couldn't reach alone.

**Jordan:** He gives eleven practical tips. What are the most useful?

**Alex:** The biggest one: don't use SSH for LLM-driven MikroTik configuration. He describes a "death by a thousand cuts" problem when you're piping text through SSH — the agent loses context, commands get garbled, output parsing breaks down. The much better approach is MikroTik's REST/JSON API, which gives the LLM a clean structured interface.

**Jordan:** That principle generalizes. Whenever you're giving an LLM access to a system, prefer machine-readable structured interfaces over text-stream protocols. SSH was designed for humans reading terminal output. LLMs work better with JSON.

**Alex:** He also recommends dumping the entire config before and after any change — version-control those snapshots — and going step by step rather than asking the LLM to "set up my network" all at once.

**Jordan:** The same lesson everyone learns about LLM-driven tasks. Decompose aggressively. Test after each step. LLMs hallucinate.

**Alex:** There's a clever tip for handling IP address conflicts during network migrations. The solution is MAC-Telnet — a telnet client that operates at Layer 2, the MAC address layer. Even when the IP addresses are a mess and you can't reach the router at its normal address, you can reach it via its hardware address. He and Claude built a small CLI wrapper to make it more LLM-accessible.

**Jordan:** The meta-point is the one worth sitting with. Most LLM use-case discussions focus on coding, writing, reasoning. But they work equally well — maybe better, in some ways — in technical domains with well-documented APIs and structured CLIs. Networking, database administration, infrastructure configuration. The knowledge exists in training data. The interface is structured. The LLM just needs a human in the loop to verify.

**Alex:** He also mentions multi-LLM consensus for high-stakes config. He'll ask several models to independently review a network configuration and flag discrepancies before applying it. That's a practical technique for anything where mistakes are painful to reverse.

---

## SEGMENT 4: High-Bandwidth Flash — AI's Next Memory Tier

**Alex:** Final story, infrastructure hardware. IEEE Spectrum published a piece this week on High-Bandwidth Flash — HBF — as a potential new memory tier for AI inference workloads. It landed on Hacker News with around 50 points.

**Jordan:** Why is memory such a constraint for AI?

**Alex:** Large models require enormous memory to serve. The current gold standard is HBM — High Bandwidth Memory — which stacks DRAM chips vertically using advanced packaging. HBM4E can deliver up to 3.6 terabytes per second of bandwidth per stack. That's extremely fast, but also expensive per gigabyte, and capacity-limited.

**Jordan:** And HBF is applying the same stacking idea to NAND flash — the memory in SD cards and thumb drives.

**Alex:** Right. Standard NAND flash delivers about 4.8 gigabytes per second of read bandwidth. HBM4E is roughly 750 times faster. So flash sounds useless for this. But there's an insight that changes the calculus.

**Jordan:** Writing to flash is slow. Reading from flash can be made fast.

**Alex:** And for AI inference, you only ever read the model weights. During training, you're reading and writing billions of parameters on every backward pass — flash fails there. But during inference, the model weights are frozen. They're read-only. You load them once and reference them repeatedly. Flash's write penalty vanishes.

**Jordan:** So the architecture becomes: HBM stays as the high-speed scratchpad — it handles the KV cache, the active attention computation. HBF sits underneath storing the static model weights, which you stream into HBM as needed.

**Alex:** SanDisk has published fact sheets for a first-generation HBF product: up to 16 stacked NAND dies, 512 gigabytes of capacity per stack, 1.6 terabytes per second of read bandwidth. The roadmap shows Gen 2 at 2 terabytes per second and Gen 3 at 3.2 terabytes per second.

**Jordan:** That Gen 3 number starts to become genuinely interesting relative to what it costs. You'd be getting HBM-adjacent bandwidth at flash's cost and capacity density.

**Alex:** The timeline caveat is real — first production isn't expected until at least late 2027, broad deployment is a 2029 or 2030 story. But the architectural reason it matters is worth understanding now. Today, serving a very large model means keeping all the weights in expensive HBM or in slower DRAM. HBF creates a viable third tier: high-capacity, read-optimized, cheaper than HBM, sitting between DRAM and HBM in the hierarchy.

**Jordan:** It's the tiered memory architecture CPUs have used for decades — L1, L2, L3, then main memory — applied to AI accelerators. The reason it hasn't happened for AI is that flash was too slow to be useful in this role. HBF is trying to change that.

**Alex:** If it works, it unlocks serving much larger models without proportionally more HBM budget. That's currently the binding constraint on inference cost. Worth tracking.

---

## OUTRO

**Jordan:** Pulling it together. Four stories today, and they paint a pretty coherent picture of where things are moving.

**Alex:** At the model layer, a new entrant released an open-weights multimodal model specifically designed for customization — not the strongest, but the most forkable. And they made the case that "most forkable" is the right bet.

**Jordan:** At the tooling layer, the production source code for a major coding agent is now public. The TUI harness, the tool loop, the agent protocol for editor embedding. Read it if you want to understand how these systems actually work.

**Alex:** At the practitioner layer, LLMs are proving useful for technical domains well beyond coding — network administration, infrastructure configuration, anything with structured interfaces and documented APIs.

**Jordan:** And at the hardware layer, a new memory architecture is coming that could split the AI inference stack into a compute scratchpad and a static weight store — potentially unlocking much larger models at meaningfully lower cost.

**Alex:** That's our show for Thursday, July 16th. Thanks for listening to Daily AI Insights.

**Jordan:** See you tomorrow.
