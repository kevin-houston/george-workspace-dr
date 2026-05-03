# Daily AI Insights — March 28, 2026
**Episode: "The Paradox Issue"**

---

## INTRO

**Alex:** Welcome to Daily AI Insights. I'm Alex.

**Jordan:** And I'm Jordan. And today we're calling this one the Paradox Issue — because every story we're covering has a twist that contradicts the obvious headline.

**Alex:** AI is failing a benchmark at one percent. AI is driving trade growth to record highs. The federal government wants to help AI by taking power away from the states. And NVIDIA is building the infrastructure for the agent economy, with a partner list that reads like the Fortune 100.

**Jordan:** Four stories, four counterintuitive punchlines. Let's get into it.

---

## SEGMENT 1: ARC-AGI-3 — The Benchmark That Humbles Everyone

**Alex:** Let's start with a research story that dropped this week and genuinely stopped me in my tracks. The team behind the ARC-AGI benchmark — that's the test François Chollet designed specifically to measure fluid, generalizable intelligence — released ARC-AGI-3.

**Jordan:** And the headline number is brutal. Humans solve one hundred percent of the test environments. Frontier AI systems, as of right now, score below one percent.

**Alex:** One percent. Not one percent less than humans. One percent total.

**Jordan:** Right. And this is after the AI industry spent two years celebrating ARC-AGI-2 progress. There was genuine excitement when models started cracking ARC-AGI-2 above the fifty percent mark.

**Alex:** So what makes ARC-AGI-3 so much harder? The key design choice is that it's interactive. It's not about pattern matching on static grids. It's about agents navigating novel, abstract, turn-based environments — the kind of situation where you have to learn the rules of the game and adapt in real time.

**Jordan:** And it deliberately strips out language and external knowledge. You can't Google your way through it. You can't pattern-match to training data. The benchmark is specifically designed to test what researchers call fluid adaptive efficiency.

**Alex:** Which is exactly what AI has been worst at all along. We've gotten incredibly good at retrieving, remixing, and generating. But genuinely novel reasoning from first principles? That gap hasn't closed.

**Jordan:** What I find most interesting is the timing. We're in a moment where OpenAI just crossed twenty-five billion dollars in annualized revenue. GPT-5.4 is at human parity on desktop productivity tasks. And yet ARC-AGI-3 is showing that a crucial dimension of intelligence — the adaptive, exploratory kind — is essentially untouched.

**Alex:** It's a really useful corrective. The benchmark is doing what benchmarks are supposed to do: revealing where the ceiling actually is, not just confirming that the leading models are impressive.

**Jordan:** Chollet has always said AGI isn't about doing tasks you've seen before faster and better. It's about facing genuinely new problems. And this benchmark is saying — clearly — that problem remains wide open.

**Alex:** One percent is a humbling number for an industry that has been talking seriously about AGI timelines.

---

## SEGMENT 2: White House National AI Policy Framework — Federalism Meets the Future

**Alex:** Okay, policy segment. Last Thursday, March twentieth, the White House released its National Policy Framework for Artificial Intelligence — a set of legislative recommendations to Congress laying out how the federal government wants AI regulated at the national level.

**Jordan:** And the headline policy position is federal preemption. The White House wants a unified federal AI law that would override the patchwork of state AI regulations that have been building up over the last two years.

**Alex:** California's Transparency in Frontier AI Act. Texas's Responsible AI Governance Act. Both went into effect January first. New York has been drafting its own version. And the White House is basically saying: if Congress passes a federal framework, those state laws go away.

**Jordan:** The argument from the administration and from most of the tech industry is that a patchwork of fifty different state regulations creates compliance chaos, slows innovation, and hands a strategic advantage to China.

**Alex:** There's real merit to that argument. A company trying to deploy an AI product in all fifty states potentially faces fifty different compliance regimes. That's not hypothetical — that's the reality as of right now.

**Jordan:** But there's a genuine tension here. States have historically been the laboratories of democracy on consumer protection. And a lot of the state AI laws are specifically about protecting people from surveillance, algorithmic bias, and deepfakes.

**Alex:** The framework does preserve some state powers. It explicitly keeps states' traditional authority to protect children, prevent fraud, and safeguard consumers. But it would block states from regulating AI model development itself or imposing liability on AI developers for how third parties use their systems.

**Jordan:** That liability shield is significant. It's essentially Section 230 logic applied to AI. AI developers wouldn't be responsible for what third parties do with their models.

**Alex:** And just like Section 230, it will be fought over for years. The framework is not law yet — the White House says it wants to work with Congress to pass a bill this year, and they think there's bipartisan support. But the political path through Congress is genuinely uncertain.

**Jordan:** What I think is most notable is that this framework exists at all. A year ago, the federal posture on AI was largely hands-off. Now the White House is actively trying to shape the legislative landscape before the states shape it for them.

**Alex:** And the Business Software Alliance immediately welcomed it. They've been pushing hard for federal preemption precisely because the alternative — compliance with dozens of conflicting state regimes — is untenable at scale.

**Jordan:** There's also a wildcard in here. The framework explicitly calls for Congress to establish regulatory sandboxes for AI applications — isolated testing environments where companies can develop and test without immediately triggering full regulatory compliance.

**Alex:** That's actually a meaningful pro-innovation provision. If it makes it into law, it could dramatically speed up the deployment of AI in regulated industries like healthcare and finance.

---

## SEGMENT 3: NVIDIA's Enterprise Agent Platform — The Infrastructure Layer Arrives

**Alex:** Let's talk about GTC, because Jensen Huang had a big week. On March sixteenth, NVIDIA announced the Agent Toolkit — an open-source software stack designed specifically to help enterprises build and deploy autonomous AI agents at scale.

**Jordan:** And the partner list is not small. Twenty major software platforms committed to the toolkit at launch, including Adobe, Atlassian, SAP, Salesforce, ServiceNow, Siemens, Cisco, CrowdStrike, Palantir, and Red Hat.

**Alex:** Jensen Huang described the vision this way: "Employees will be supercharged by teams of frontier, specialized and custom-built agents they deploy and manage." He's describing a specific organizational structure — human workers managing fleets of AI agents.

**Jordan:** Let's break down what the toolkit actually is. There are four core components. Nemotron is NVIDIA's family of open-source models optimized specifically for agentic reasoning — and it's reportedly cutting costs by over fifty percent on benchmark tasks compared to using frontier models alone.

**Alex:** AI-Q is an open agent framework built on LangChain. It lets developers build agents that can perceive, reason, and act on enterprise knowledge. Think of it as the brain layer — it decides what the agent should do next based on what it knows.

**Jordan:** OpenShell is the runtime layer — it enforces security, network, and privacy guardrails. So when your autonomous agent starts making API calls and executing processes, it's doing so within boundaries your IT and legal teams have defined. That's actually the piece I find most underrated.

**Alex:** Why?

**Jordan:** Because the reason most enterprise AI pilots don't reach production isn't the model quality. It's governance. It's the security team saying no. OpenShell is directly targeting that blocker.

**Alex:** And cuOpt is a skill library for optimization tasks within agent workflows. If your agent is managing logistics or scheduling, it has dedicated optimization tools rather than trying to brute-force those problems through a language model.

**Jordan:** The Salesforce implementation is worth highlighting. They're using Slack as the primary interface — employees interact with Agentforce agents directly inside Slack, and those agents pull from both on-premises and cloud data sources. The agent infrastructure runs on NVIDIA hardware underneath.

**Alex:** The bigger picture here is that NVIDIA is building the platform layer for the agent economy. Not just the chips — the software stack that sits between the chips and the enterprise applications. That's a much larger business than just selling GPUs.

**Jordan:** And with twenty major enterprise software companies already committed, this becomes a default standard almost by accident. If your SAP implementation, your Salesforce CRM, your Cisco network all speak the same agent protocol — that protocol wins.

---

## SEGMENT 4: The AI Trade Paradox — Tariffs Rise, AI Trade Booms

**Alex:** Last story. And this one is the most counterintuitive of the four. Everyone has been predicting that Trump's tariffs — now at their highest levels since World War II — would hurt the AI industry. Disrupt chip supply chains, raise data center costs, slow the infrastructure build-out.

**Jordan:** And according to McKinsey's most recent analysis, the opposite happened.

**Alex:** Global trade actually grew faster than the world economy despite the tariffs. And AI-related shipments — chips, servers, networking gear — were the single largest growth driver, accounting for roughly one-third of all trade expansion over the past year.

**Jordan:** Semiconductors and data-center equipment now comprise over thirty-five percent of global trade. That's a staggering number. The world is trading AI infrastructure at massive scale.

**Alex:** The rerouting story is fascinating. U.S.-China trade is down about thirty percent, roughly a hundred and thirty billion dollars in Chinese exports that just evaporated. But China's overall trade surplus actually hit record highs because they pivoted to supplying components to emerging economies.

**Jordan:** Vietnam, Thailand, and Malaysia captured the consumer electronics manufacturing that fled China. India grabbed significant smartphone market share — fifteen billion dollars more in U.S. exports after the U.S. cut Chinese smartphone imports by forty percent.

**Alex:** And the U.S. trade deficit? Essentially unchanged. Nine hundred and one billion versus nine hundred and three billion the prior period. The deficit just migrated — from China to Vietnam and Taiwan.

**Jordan:** So the tariffs didn't fix the trade deficit. They reshuffled which countries the U.S. runs the deficit with.

**Alex:** McKinsey's Tiago Devesa characterized the dynamics really well. He called AI "a long-term wave" reshaping trade patterns and the tariffs "last year's disruptive splash." The wave is bigger than the splash.

**Jordan:** There's a real risk scenario underneath this though. The worry isn't that tariffs stop AI trade — the data shows they haven't. It's that by squeezing Southeast Asian and South Asian countries, we're inadvertently pushing them toward closer relationships with Beijing. If you're Vietnam navigating the U.S.-China tech rivalry, you're going to hedge.

**Alex:** And on the chip side, TSMC is still irreplaceable for leading-edge AI. Even with a fifteen percent tariff on Taiwanese goods — reduced from twenty percent after a January deal — there's no alternative. The chips keep flowing because they have to.

**Jordan:** It's a strange situation. Costs are rising. The buildout continues anyway. And the trade flows find new paths through the global system regardless of where tariffs are set.

---

## CLOSING: The Throughline

**Jordan:** So let's find the throughline. Four stories: ARC-AGI-3, the White House policy framework, NVIDIA's enterprise platform, and the tariff paradox.

**Alex:** Here's what keeps coming back to me: AI is becoming infrastructure. Not a product — infrastructure.

**Jordan:** Say more.

**Alex:** When something is infrastructure, everyone fights over who controls it. States and the federal government fight over who regulates it — that's the policy story. Countries fight over who manufactures the hardware — that's the tariffs story. Companies fight over who owns the platform layer — that's the NVIDIA story.

**Jordan:** And ARC-AGI-3?

**Alex:** That's the reminder that despite all the infrastructure-level fights, the technology itself is still far from finished. We're building the highways for a vehicle that doesn't fully work yet. The interesting question is whether that matters.

**Jordan:** History suggests it doesn't stop the building. The internet was built as infrastructure before most of what we do on it existed. The highway system was built before the suburbs it enabled were planned.

**Alex:** So maybe the fact that AI is already being fought over like infrastructure — regulated, tariffed, platform-layered — is actually a signal that the underlying capability is further along than one percent on ARC-AGI-3 suggests.

**Jordan:** Or it's a signal that we're all very optimistic about that last ninety-nine percent.

**Alex:** Either way, it's a fascinating time to be paying attention. That's it for today's Daily AI Insights. Thanks for listening.

**Jordan:** See you tomorrow.

---

## SOURCES

- ARC-AGI-3 benchmark: humans 100%, frontier AI <1% — llm-stats.com/ai-news, March 2026
- White House National Policy Framework for Artificial Intelligence — whitehouse.gov, March 20, 2026; Ropes & Gray LLP analysis; Nixon Peabody analysis
- NVIDIA Agent Toolkit GTC 2026 announcement — nvidianews.nvidia.com, March 16, 2026; VentureBeat/AI News coverage
- McKinsey Global Institute trade analysis — Euronews, March 26, 2026; Epoch AI/Stanford capex data
- OpenAI $25B / Anthropic $19B annualized revenue — Reuters via labla.org, March 2026
- GPT-5.4 OSWorld 75% benchmark — renovateqr.com AI model releases March 2026
