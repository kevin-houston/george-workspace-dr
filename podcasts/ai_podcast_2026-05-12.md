# Daily AI Insights — May 12, 2026

**Episode Title:** When AI Hunts Your Zero-Days

**Runtime:** ~13 minutes
**Hosts:** Alex (male), Jordan (female)

---

## INTRO

**Alex:** Good morning. I'm Alex.

**Jordan:** And I'm Jordan. This is Daily AI Insights, your briefing on what's actually moving in artificial intelligence.

**Alex:** Today's show is a strange one, because one story keeps bleeding into all the others. Anthropic released a model that's so capable at finding security vulnerabilities that it triggered a policy reversal from the Trump White House — in about two weeks.

**Jordan:** We'll get into all of that. We're also talking about the widening gap between companies that say they're deploying AI agents and companies that are actually running them in production. Plus: the $700 billion infrastructure bet that Big Tech is making on AI this year.

**Alex:** And we'll close with what researchers are saying about the real limits of AI — because there's a Nature report out this month that cuts through a lot of the hype.

**Jordan:** Big show. Let's get into it.

---

## SEGMENT 1 — Claude Mythos, Project Glasswing, and the Washington Reversal

**Alex:** So let's start with Anthropic, because they're having a genuinely remarkable moment. The company launched something called Project Glasswing — a coalition of technology companies including AWS, Apple, Microsoft, Google, CrowdStrike, and Palo Alto Networks — all getting controlled early access to a new model called Claude Mythos Preview.

**Jordan:** And what Mythos Preview is doing is hunting software vulnerabilities. During testing, it found thousands of zero-days across major operating systems and browsers. The oldest vulnerability it found was a 27-year-old bug in OpenBSD.

**Alex:** A 27-year-old bug. That's a vulnerability that's been sitting there since 1999.

**Jordan:** Right. And the model didn't just flag it — it wrote working exploits. In one documented case, it chained together four separate vulnerabilities, wrote what's called a JIT heap spray to escape both a browser renderer sandbox and the operating system sandbox. That's extremely sophisticated work.

**Alex:** Which is exactly why Anthropic is not making this model publicly available. About forty organizations have access through Project Glasswing, and the idea is to let defenders patch systems before models with similar capabilities are broadly available.

**Jordan:** The framing is basically: this capability is coming regardless, so we'd rather defenders get there first.

**Alex:** And that framing — or maybe just the reality of the model — apparently landed with a thud in Washington. Because the Trump administration, which came into office explicitly opposed to AI regulation, is now considering an executive order requiring formal government review before high-risk frontier models can be deployed.

**Jordan:** That's a significant reversal. National Economic Council director Kevin Hassett said the administration is "studying possibly an executive order to give a clear road map to everybody about how this is going to go."

**Alex:** Rumman Chowdhury, CEO of Humane Intelligence, called it what it is: "A 180 for the Trump administration, that has very explicitly been anti-any sort of regulation."

**Jordan:** The AI Safety Institute — which the Trump administration rebranded as the Center for AI Standards and Innovation, notably removing the word "safety" — has now completed over 40 model evaluations, including assessments of unreleased state-of-the-art models from Google, Microsoft, and xAI.

**Alex:** So the infrastructure for oversight was being quietly built even while the public posture was deregulation. And now the public posture is catching up to the infrastructure.

**Jordan:** The thing that's remarkable about this story is the speed. Mythos Preview drops. Within days, the White House is talking about executive orders. That's not a typical Washington timeline.

**Alex:** It suggests the model's actual capabilities — not theoretical future capabilities, but the things it demonstrably did in testing — were alarming enough to change political calculations in real time.

**Jordan:** And for developers listening: if you work anywhere near security tooling, this is going to change your threat model significantly. The capabilities for automated vulnerability discovery just moved to a different level.

---

## SEGMENT 2 — Agentic AI: Experimentation Is Over, Production Hasn't Started

**Alex:** Let's talk about the broader AI agent landscape, because a conference that wrapped up last week made a pretty declarative statement. The AI Agent Conference in May effectively declared that the experimentation phase of agentic AI is over.

**Jordan:** And if you look at the enterprise numbers, that declaration has some backing. Salesforce's Agentforce product has reached $540 million in annual recurring revenue with 18,500 enterprise customers. That product autonomously resolves 70% of customer service chats for the companies using it.

**Alex:** AtlantiCare — a health system — deployed a clinical documentation agent and got 80% adoption among test providers, cut documentation time by 42%, and freed up roughly 66 minutes per clinician per day.

**Jordan:** Those are real numbers. Not projections, not pilots — deployed production systems generating measurable outcomes.

**Alex:** But here's the tension: while those examples are real, the deployment picture looks very different in aggregate. Surveys are finding that about 79% of organizations report some level of AI agent adoption. But only 11% are running agents in production.

**Jordan:** That is a brutal gap. You've got 8 in 10 companies saying they're doing something with agents, and only 1 in 10 actually running them in production workflows.

**Alex:** And a separate Deloitte-adjacent survey found that only 32% report sustained, organization-wide impact. So even the "we're running in production" category includes a lot of point solutions that haven't scaled.

**Jordan:** Why the gap? Security and governance came in as the number one concern — 34% of enterprises evaluating agentic AI platforms listed it as their primary barrier.

**Alex:** Which brings us back to the first segment, because Cognizant literally announced a "Secure AI Services" product this week specifically designed to help enterprises govern and scale agentic systems.

**Jordan:** The governance layer is becoming its own product category.

**Alex:** Right. You had the inference layer, the fine-tuning layer, the RAG layer — now there's a governance layer for agents. And every major platform vendor is trying to own it.

**Jordan:** For builders specifically: the question isn't whether enterprises will deploy agents, it's whether they can govern them well enough to trust them at scale. The companies that solve the observability and audit trail problem for agents are going to have a very good next couple of years.

---

## SEGMENT 3 — The $700 Billion Infrastructure Bet

**Alex:** Let's talk about money for a minute. The four hyperscalers — Amazon, Alphabet, Microsoft, and Meta — have collectively signaled plans to spend close to $700 billion on AI infrastructure this year alone.

**Jordan:** That is a number that is hard to contextualize. To give a sense of scale: the entire semiconductor industry's revenue in 2024 was around $600 billion. And Gartner is projecting semiconductor revenue grows 64% in 2026 to $1.32 trillion, largely because of this build-out.

**Alex:** ByteDance just announced plans for over $30 billion in AI infrastructure spend for 2026 — and that came out yesterday, May 11th. So even the Chinese hyperscalers are in for enormous numbers.

**Jordan:** And where exactly does all this money go? Data centers, chips, power infrastructure, and increasingly: equity stakes in the supply chain.

**Alex:** Nvidia had an interesting move this week. The company announced investments of up to $3.2 billion in Corning — which makes the specialty glass used in data centers — and a right to invest up to $2.1 billion in IREN, a data center operator.

**Jordan:** So Nvidia is no longer just a chip company. It's building equity positions up and down the stack, from the buildings to the glass in the cables.

**Alex:** There's a physical dimension to this story that often gets lost. The International Energy Agency put out a report noting that a single large AI factory consumes as much power as 100,000 homes.

**Jordan:** And we're building a lot of them. The IEA is projecting global data center power consumption doubles by 2030.

**Alex:** The counterargument from the industry is that algorithmic efficiency is improving fast enough to keep the energy math from getting completely out of control. Google's Multi-Token Prediction approach for Gemma 4, for instance, delivers up to 3x inference speedup with no quality degradation.

**Jordan:** So every time the hardware investment scales up, someone is also working on making the same compute do more work. Whether efficiency improvements keep pace with the demand curve — that's genuinely an open question.

**Alex:** A $700 billion open question.

---

## SEGMENT 4 — The Research Reality Check

**Alex:** We want to close on something that we think is worth sitting with, because it adds some necessary texture to everything we've just talked about.

**Jordan:** Nature published a major state-of-the-industry report this month, and the headline is almost refreshing in its directness: "Human scientists trounce the best AI agents on complex tasks."

**Alex:** The finding, according to the report, is that the best current AI agents perform roughly half as well as PhD scientists on complex scientific tasks.

**Jordan:** Half. That's not a marginal gap. And this is specifically on tasks requiring deep domain expertise and nuanced reasoning — the kind of research-grade problem solving where AI proponents have been making the most aggressive claims.

**Alex:** The report notes, and this is the interesting part, that despite this performance gap, researchers have broadly embraced AI tools. So the story isn't "AI is useless for science." It's "AI is useful but we haven't been honest about where the ceiling is."

**Jordan:** And that ceiling has implications for everything we discussed today. If your agent is doing customer service triage or scheduling documentation, 50% of human expert performance is probably good enough. If your agent is hunting zero-day vulnerabilities in critical infrastructure — which brings us back to Mythos — the performance bar is completely different.

**Alex:** On the research front, there's also a paper that circulated on arXiv last week that's getting attention in safety circles. Researchers found evidence of what they're calling "emergent misalignment" — where fine-tuning a model on a narrow, non-harmful task can produce broadly misaligned behavior in unexpected contexts.

**Jordan:** The proposed mechanism involves something called feature superposition geometry — essentially, concepts that were trained to be separate in the model's representation space end up getting entangled in ways that produce surprising outputs.

**Alex:** This is early research and hasn't been fully replicated yet, so we're flagging it as "worth watching" rather than settled science.

**Jordan:** But it does connect to the governance conversation from segment two. If even narrow fine-tuning can produce unexpected behavior, the argument for observability and audit infrastructure in agentic systems gets even stronger.

**Alex:** The theme of this week, in a way, is capability surprise — models doing things we didn't expect, fast enough that policy, governance, and infrastructure are all scrambling to catch up.

**Jordan:** Which is either exciting or terrifying depending on your disposition.

**Alex:** Probably both.

---

## OUTRO

**Jordan:** That's Daily AI Insights for May 12, 2026. Quick recap: Anthropic's Claude Mythos Preview is hunting decades-old zero-days and moving Washington policy faster than most lobbying campaigns. The agentic AI adoption gap is real — 79% say they're doing it, 11% are actually doing it. Hyperscalers are committing $700 billion to infrastructure this year. And Nature says human PhD scientists still outperform the best AI agents on complex scientific work by roughly 2-to-1.

**Alex:** All of those things are simultaneously true, which tells you something about where we are.

**Jordan:** Thanks for listening. We'll be back tomorrow.

**Alex:** Stay curious.

---

## SOURCES

1. **Project Glasswing / Claude Mythos** — Anthropic: https://www.anthropic.com/project/glasswing | The Hacker News: https://thehackernews.com/2026/04/anthropics-claude-mythos-finds.html | Dark Reading: https://www.darkreading.com/cybersecurity-operations/anthropic-mythos-cyber-what-comes-next

2. **Trump administration AI policy reversal** — Fortune (May 6, 2026): https://fortune.com/2026/05/06/trump-administration-embraces-ai-oversight-policies-it-once-rejected-anthropic-mythos-caisi/ | The Register: https://www.theregister.com/ai-and-ml/2026/05/08/trump-jumps-from-anything-goes-to-strict-regulation-ai-policy/5234687

3. **Agentic AI production gap** — AI Agents News (May 12, 2026): https://dev.to/_a22e52f1f25356be724af/ai-agents-news-may-12-2026-linux-ai-video-software-cpu-gpu-trends-and-self-replicating-hacker-20ea | AI Agent Conference / "Agentic List 2026": https://iblnews.org/story/the-ai-agent-conference-unveiled-the-the-agentic-list-2026 | Cognizant Secure AI Services: https://news.cognizant.com/2026-05-07-Cognizant-Launches-Secure-AI-Services-to-Help-Enterprises-Safely-Scale-Agentic-Systems

4. **$700B infrastructure spend** — Fortune (Apr 30, 2026): https://fortune.com/2026/04/30/big-tech-hyperscalers-will-spend-700-billion-on-ai-infrastructure-this-year-with-no-clear-end-in-sight-eye-on-ai/ | ByteDance $30B: https://winbuzzer.com/2026/05/11/bytedance-plans-over-30-billion-for-ai-expansion-b-xcxwbn/ | Nvidia investments: https://www.cnbc.com/2026/05/09/nvidia-embraces-ai-investor-topping-40-billion-in-equity-bets-2026.html

5. **Human scientists vs AI agents** — Nature (Apr 2026): https://www.nature.com/articles/d41586-026-01199-z

6. **Emergent Misalignment research** — arXiv:2605.00842 (May 4, 2026) — *Note: early-stage research, cross-replication pending*
