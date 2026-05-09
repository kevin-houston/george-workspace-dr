# Daily AI Insights — May 8, 2026
## When AI Finds What Humans Missed
**Runtime:** ~12-14 minutes
**Hosts:** Alex (male), Jordan (female)

---

**INTRO**

**Alex:** Good morning, and welcome to Daily AI Insights. I'm Alex, and today is Friday, May 8th, 2026. We've got a genuinely heavy news week to close out.

**Jordan:** I'm Jordan, and no kidding. We're talking about an AI model that found bugs hiding in operating systems for 27 years, a five-nation security coalition sounding the alarm on autonomous agents, Google's biggest model update of the year, and a $700 billion infrastructure bet that's bumping up against a wall made of physics.

**Alex:** All four of those stories have serious implications for developers and builders, and we're going to dig into the real numbers. Let's get into it.

---

**SEGMENT 1 — The Bug Hunter: Anthropic's Mythos and Project Glasswing**

**Alex:** So let's start with the story that triggered a genuine policy shift in Washington this week. Anthropic has a new model called Claude Mythos Preview, and it is not generally available. That is not an accident.

**Jordan:** Right — Anthropic made a deliberate choice to hold this back. The reason: Mythos Preview can find and exploit software vulnerabilities at a level that, according to Anthropic, surpasses all but the most skilled human security researchers. And they've demonstrated that. Over the past several weeks, Mythos identified thousands of zero-day vulnerabilities across every major operating system and every major web browser.

**Alex:** When you say thousands, people might tune that out as a marketing number. But the specifics here are remarkable. The model found a 27-year-old bug in OpenBSD — software that has been under continuous security review for nearly three decades. It also found a 16-year-old vulnerability in FFmpeg, which is embedded in basically everything that plays video. And it found a memory-corrupting flaw in a memory-safe virtual machine monitor, which is the kind of thing those monitors are explicitly designed to prevent.

**Jordan:** So the question is: what do you do with a model that capable? Anthropic's answer is Project Glasswing. Instead of releasing Mythos to the public, they're giving controlled access to a select group of organizations to use it defensively — finding and patching vulnerabilities before bad actors can exploit them.

**Alex:** The partner list is significant: AWS, Apple, Broadcom, Cisco, CrowdStrike, Google, JPMorgan Chase, the Linux Foundation, Microsoft, NVIDIA, and Palo Alto Networks. Anthropic is also putting $100 million in usage credits and $4 million in direct donations behind open-source security work as part of the initiative.

**Jordan:** And this model is what spooked Washington into a U-turn. Fortune reported on May 6th that the Trump administration — which spent much of 2025 rolling back Biden-era AI safety policies — is now considering an executive order that would require evaluation of advanced AI models before public release.

**Alex:** The White House's National Economic Council Director Kevin Hassett said the administration is, quote, "studying possibly an executive order" to establish those evaluation protocols. And a renamed version of the old U.S. AI Safety Institute, now called CAISI — the Center for AI Standards and Innovation — has already completed over 40 evaluations of frontier models including unreleased ones, in partnership with Google, Microsoft, and xAI.

**Jordan:** The irony is not subtle. The administration that called AI safety theater is now considering safety requirements because an AI just walked through the front door of every major operating system.

**Alex:** The Berryville Institute of Machine Learning identified 23 security risks they describe as living "inside the black box" of frontier models. Critics worry about conflicts of interest when companies self-report. But right now, the Glasswing model — where capability drives responsibility — is the only framework anyone has actually deployed.

**Jordan:** It's a complicated story: the same model that represents the risk is also the most powerful tool available to address it.

---

**SEGMENT 2 — Slow Down: Five Eyes Issues First Agentic AI Security Guidance**

**Jordan:** Speaking of AI risks, on May 1st, six intelligence and cybersecurity agencies across five countries published something they've never published before: joint security guidance specifically for agentic AI systems.

**Alex:** The agencies involved are CISA and the NSA in the U.S., the UK's National Cyber Security Centre, Canada's Centre for Cyber Security, Australia's Signals Directorate, and New Zealand's National Cyber Security Centre. The document is titled "Careful Adoption of Agentic AI Services," and the title says everything about the tone.

**Jordan:** The core concern is that AI agents — systems that can take multi-step actions autonomously, call external tools, and make decisions without human sign-off — are being deployed in critical infrastructure with what the agencies call "virtually no governance framework." They identified 23 distinct risks and laid out over 100 best practices.

**Alex:** The document gives two specific scenarios that illustrate the problem. In the first, an AI agent with broad write permissions to install software patches inadvertently executes actions beyond its assigned task. In the second — and this one is more chilling — an organization deploys a procurement agent with access to financial systems, email, and contracts. A compromised tool integrates into that workflow, and attackers inherit the agent's excessive privileges. They modify contracts, approve unauthorized payments, forge audit logs. The agent did exactly what it was told; it just got told the wrong thing.

**Jordan:** The recommendations are grounded in existing security frameworks rather than calling for new regulation. Zero trust, defense-in-depth, least-privilege access. Each agent should carry a cryptographically secured identity, use short-lived credentials, encrypt communications with other agents. And for high-impact actions, a human has to sign off.

**Alex:** The central message is "resilience, reversibility, and risk containment over efficiency gains." Which is going to be a tension point, because efficiency is exactly why enterprises are deploying these systems.

**Jordan:** Gartner projects that 40% of enterprise applications will include embedded, task-specific AI agents by end of 2026. But they also warn that 40% of those projects are at risk of failure by 2027 due to governance gaps and unclear ROI. The Five Eyes document and those Gartner numbers are telling the same story from different angles.

**Alex:** The Register described the guidance as the security community saying: agents will misbehave, and you should plan for that, not around it.

**Jordan:** If you're building anything with autonomous agents right now, this document is a weekend read. The full guidance is public from CISA.

---

**SEGMENT 3 — Google's Biggest Model Drop of the Year: Gemini 3.1 Ultra**

**Alex:** Let's talk about the most significant new model available to developers right now. Google released Gemini 3.1 Ultra this week — and the headline number is a 2-million token context window.

**Jordan:** To put that in human terms: 2 million tokens is roughly 1,500 pages of dense text. Or several full-length novels. Or hours of video — processed in a single prompt, without chunking.

**Alex:** And this is native multimodal, not stitched together. Text, images, audio, and video are all processed through the same architecture. Google's claim is that the model can reason across modalities simultaneously rather than transcribing or converting between them first.

**Jordan:** The benchmark improvements are meaningful. According to the release materials, Gemini 3.1 Ultra scores 28% higher than its predecessor on ARC-AGI-3, which tests reasoning on novel problems. It also shows gains on GPQA Diamond and SWE-Bench Pro. For coding agents specifically, according to the LLM leaderboard at llm-stats.com, Gemini 3.1 Pro is currently the strongest model in head-to-head coding arena comparisons.

**Alex:** One capability worth flagging for developers: the model can execute Python in a native sandboxed environment. It writes code, runs it, observes the output, and revises — all within the model itself, without an external tool call.

**Jordan:** That is significant for agentic use cases. The context window alone enables a workflow where you hand Gemini an entire codebase and ask it to find issues, rather than chunking files and losing cross-file context.

**Alex:** On pricing, Gemini 3.1 Ultra runs at $12 per million input tokens and $36 per million output tokens. That's premium tier — more expensive than the Pro variant at $2 and $12. But for long-context applications where you previously needed to stitch together multiple calls, the economics might actually be better on a per-task basis.

**Jordan:** The model is rolling out on gemini.google.com on the Advanced plan, through Google AI Studio, and on the Gemini API. Google's also baking tighter integration with Search and AI Overviews, which gives the model access to real-time freshness signals.

**Alex:** The context window war has been heating up all year, and Gemini 3.1 Ultra is the current record holder. Claude Opus 4.6's context is smaller; GPT-5.5 is also behind. This is Google's clearest statement yet that they see long-context, multi-document reasoning as their competitive edge.

---

**SEGMENT 4 — $700 Billion and a Power Problem**

**Jordan:** Now let's zoom out from individual models to the infrastructure that makes all of this possible — and the constraints that are starting to bite.

**Alex:** Fortune reported on April 30th that the big four hyperscalers — Alphabet, Amazon, Meta, and Microsoft — spent over $130 billion on AI infrastructure in Q1 alone. The full-year 2026 projection is approximately $700 billion. For reference, that's up from about $410 billion in 2025. McKinsey projects total AI capex will need to reach $6.7 trillion globally by 2030 to meet compute demand.

**Jordan:** Google announced at its Next '26 conference this week that its new TPU 8t chip can connect 134,000 TPUs within a single data center and over one million across multiple sites in a single training cluster. The performance claim is nearly 3x higher compute than the previous generation, with 121 exaflops of capacity in one superpod and 2 petabytes of shared memory.

**Alex:** Nvidia's next architecture — Vera Rubin, the successor to Blackwell — is still expected in late 2026. Individual H100 GPUs are running up to $40,000 each, and an eight-GPU server costs hundreds of thousands of dollars.

**Jordan:** But the story that keeps emerging from industry observers is not who's building the most — it's who can actually get power. A Manufacturing Dive piece this week described power scarcity as having shifted from a temporary bottleneck to the primary constraint limiting AI and hyperscale growth.

**Alex:** And there are compounding supply chain problems. Strikes on Qatari helium production — helium accounts for roughly a third of global supply and is critical for chip fabrication — have doubled spot prices. Fabs in Taiwan and South Korea are now rationing. Copper, essential for data center wiring, hit $6 per pound in January and is currently around $5.61.

**Jordan:** There's also an interesting infrastructure shift happening. 2026 is being described by industry analysts as the year the industry pivots from training clusters to inference infrastructure. The question is no longer who can build the biggest campus — it's who can deploy reliable, power-efficient inference capacity at scale.

**Alex:** And that brings in a divergence among the hyperscalers. Meta's Hyperion project in Louisiana is a $27 billion build with, according to reports, millions of GPUs. That kind of investment makes sense if you believe inference demand will scale proportionally with capability. Wall Street is less certain — Meta and Microsoft shares fell after Q1 earnings on spending concerns, while Alphabet and Amazon rose on strong cloud revenue.

**Jordan:** The bull case is that $700 billion is a down payment on infrastructure that will be generating returns for decades. The bear case is that AI hardware depreciates fast, and nobody knows exactly where the demand ceiling is.

**Alex:** What seems undeniable is that power is now a geopolitical and industrial policy issue as much as a tech issue. Where you can get reliable, cheap electricity increasingly determines where AI gets built.

---

**OUTRO**

**Jordan:** Alright — four stories today that connect in ways that might not be obvious at first. An AI system powerful enough to threaten global software security is what finally pushed a reluctant administration toward oversight. Five of the world's most trusted security agencies are telling builders to slow down on autonomous agents. Google is competing on context and native multimodality. And the entire industry is bumping against physics — specifically, where to get enough power.

**Alex:** If you're a developer, the Five Eyes guidance and the Glasswing precedent are the most actionable. The guidance is free and public from CISA. The Glasswing story is a preview of how the industry will handle dual-use capabilities going forward.

**Jordan:** Next week we'll be watching for any executive order movement out of the White House, and for whether Grok 5 or GPT-5.5 Instant's full rollout changes the benchmark picture.

**Alex:** Thanks for listening to Daily AI Insights. We're back Monday. Have a good weekend.

**Jordan:** Take care.

---

**SOURCES**
1. Anthropic's Claude Mythos Finds Thousands of Zero-Day Flaws Across Major Systems — https://thehackernews.com/2026/04/anthropics-claude-mythos-finds.html
2. Project Glasswing: Securing critical software for the AI era — https://www.anthropic.com/glasswing
3. Trump administration suddenly embraces AI oversight ideas it once rejected — https://fortune.com/2026/05/06/trump-administration-embraces-ai-oversight-policies-it-once-rejected-anthropic-mythos-caisi/
4. Five Eyes warn agentic AI is too dangerous for rapid rollout — https://www.theregister.com/2026/05/04/five_eyes_agentic_ai_recommendations/
5. US government, allies publish guidance on how to safely deploy AI agents — https://cyberscoop.com/cisa-nsa-five-eyes-guidance-secure-deployment-ai-agents/
6. Gemini 3.1 Ultra Released: 2M Token Context + Native Multimodal Mastery — https://seohq.github.io/gemini-3-1-ultra-release-2026
7. AI infrastructure at Next '26 — https://cloud.google.com/blog/products/compute/ai-infrastructure-at-next26
8. Big Tech is about to spend $700 billion on AI this year — https://fortune.com/2026/04/30/big-tech-hyperscalers-will-spend-700-billion-on-ai-infrastructure-this-year-with-no-clear-end-in-sight-eye-on-ai/
9. The great data center delay: Why your AI chips are stuck in 2026 — https://www.manufacturingdive.com/news/opinion-omdia-ai-semiconductor-chip-scarcity/817172/
10. LLM Leaderboard 2026: Compare 300+ Top AI Models — https://llm-stats.com/
