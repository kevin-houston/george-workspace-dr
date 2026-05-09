# Daily AI Insights — May 9, 2026

**Episode Title: Benchmarks, Agents, and the Power Problem**

*Runtime: ~13 minutes | Hosts: Alex and Jordan*

---

## INTRO

**Alex:** Good morning and welcome to Daily AI Insights. I'm Alex.

**Jordan:** And I'm Jordan. It is Saturday, May 9th, and this week was a genuinely big one — we got a model shootout between OpenAI and Anthropic, a multinational government warning about AI agents, a jaw-dropping look at what it costs to build the infrastructure underneath all of this, and a research breakthrough that has mathematicians paying attention.

**Alex:** A lot to get through. Let's start with the model releases, because the last two weeks have been a reminder that the benchmark wars are very much still on.

**Jordan:** Very much so. Buckle up.

---

## SEGMENT 1: The Model Releases — GPT-5.5 Instant Meets Claude Opus 4.7

**Alex:** So Anthropic fired first. Claude Opus 4.7 went generally available on April 16th — and the headline number was SWE-bench Pro jumping from 53.4 percent to 64.3 percent. That's a ten-point gain on the hardest version of the software engineering benchmark.

**Jordan:** To put that in context for listeners who don't track benchmarks obsessively: SWE-bench Pro is the version of the coding test that strips away hints and requires the model to find the actual bug in a real-world repository. A ten-point jump is significant. Opus 4.7 also hit 87.6 percent on SWE-bench Verified, up from 80.8, and it triples image resolution compared to 4.6.

**Alex:** And pricing stayed the same — five dollars per million input tokens, twenty-five per million output. Though Anthropic noted the new tokenizer can increase token counts by up to 35 percent depending on content type, so the per-task cost may drift upward.

**Jordan:** Then OpenAI came back on May 5th with GPT-5.5 Instant as the new default ChatGPT model. The architectural claim here is genuinely interesting: natively omnimodal. Text, images, audio, video — one unified system, not separate models stitched together.

**Alex:** The API context window on GPT-5.5 Instant is 400K tokens, while the full GPT-5.5 model for developers supports up to a million. And the hallucination reduction number is striking — OpenAI says GPT-5.5 Instant produced 52.5 percent fewer hallucinated claims than its predecessor on high-stakes prompts in medicine, law, and finance.

**Jordan:** That's the number I keep coming back to. Benchmark scores matter to developers, but hallucination rates on medical and legal questions — that's what actually determines whether an enterprise legal team or a hospital system deploys this thing.

**Alex:** Right. And what's notable about the timing here is that Claude Opus 4.7 launched before GPT-5.5, and Anthropic's SWE-bench Pro lead held even after GPT-5.5 arrived. So heading into today, Anthropic holds the coding benchmark lead and OpenAI is ahead on the hallucination-reduction story.

**Jordan:** It's also worth mentioning that Anthropic has a preview model — Claude Mythos Preview — with some extraordinary numbers: 93.9 percent on SWE-bench Verified, 94.6 percent on GPQA Diamond. That's not generally available yet, but it signals where Anthropic is heading.

**Alex:** So for developers: if you're building code agents, Opus 4.7 is leading on the benchmarks that matter. If you're building anything that requires factual reliability at scale, the GPT-5.5 hallucination improvements are worth evaluating closely.

**Jordan:** And if you're neither, Gemini 3.1 Pro is currently the cheapest frontier-class model in the U.S. and holds the top spot on GPQA Diamond at 94.3 percent. The competitive landscape right now is genuinely three-way.

---

## SEGMENT 2: Five Eyes Sounds the Alarm on Agentic AI

**Alex:** Let's talk agents. On May 1st, six intelligence and cybersecurity agencies from the Five Eyes alliance — that's CISA and NSA from the U.S., Australia's ASD, Canada's CCCS, New Zealand's NCSC, and the UK's NCSC — published what they called "Careful Adoption of Agentic AI Services." It was the first coordinated multi-government statement specifically about autonomous AI agents.

**Jordan:** And the message was not subtle. The guidance warns that agentic AI systems will likely misbehave and amplify existing organizational vulnerabilities. The recommendation is to deploy slowly, start with low-risk tasks, and keep humans in the loop.

**Alex:** The core concern is privilege escalation. These agencies found that most organizations deploying agents have granted them excessive access — more permissions than any single employee would have — without commensurate governance or oversight.

**Jordan:** The document identifies five risk categories: privilege, design and configuration, behavioral, structural, and accountability. And the behavioral one is worth dwelling on — it covers cases where an agent does exactly what it was told, but what it was told turns out to be wrong in context.

**Alex:** The specific line from the guidance that stood out to me was this: "Every individual component in an agentic AI system widens the attack surface, exposing the system to additional avenues of exploitation." That framing — attack surface growing with every tool you add to an agent — is a useful lens for developers building these systems.

**Jordan:** And this comes against a backdrop that Gartner put numbers to: 79 percent of companies have adopted AI agents in some form, but only 2 percent have fully deployed them. And Gartner projects that 40 percent of agentic AI projects are at risk of failure by 2027 due to governance gaps and unclear return on investment.

**Alex:** So you have this situation where enterprises are rushing to deploy agents, intelligence agencies are saying slow down, and the gap between "we're using agents" and "we have governance for agents" is genuinely wide.

**Jordan:** And on the developer side, that gap is an opportunity. The teams that are building the observability tooling, the audit logging, the permission scoping — they're solving a real problem right now. The Five Eyes guidance is, in a way, a product roadmap for the security tooling space.

**Alex:** That's a generous interpretation but probably accurate.

---

## SEGMENT 3: The $690 Billion Infrastructure Sprint — And Why Power Is the Constraint

**Alex:** Let's zoom out from the software layer to the infrastructure underneath it. This week, data from Q1 2026 earnings and analyst research converged on a single number: the five largest U.S. cloud and AI infrastructure companies have committed somewhere between $660 and $725 billion in capital expenditure for 2026. That's roughly double 2025 levels.

**Jordan:** To put individual pieces on it: Microsoft committed $80 billion for fiscal year 2026 alone. Alphabet is planning between $175 and $185 billion in total 2026 capex, with $70 to $74 billion going specifically to data center construction.

**Alex:** These are numbers that don't feel real until you think about what they're buying. Racks that used to draw 30 to 40 kilowatts are now designed in the hundreds of kilowatts. Some new designs are approaching the megawatt range per rack. A single large AI training facility now requires between 100 megawatts and 1,000 megawatts of dedicated power.

**Jordan:** And here is the critical shift that analysts flagged this quarter: 2026 is the year AI infrastructure moved from being capital-constrained to being energy-constrained. You can raise the money. You cannot speed up the grid.

**Alex:** The grid interconnection queue in the U.S. exceeds 2,100 gigawatts of pending projects. Transformer lead times are 18 to 24 months. Grid interconnect approvals take 18 to 36 months. Nearly 50 percent of data center projects scheduled to complete this year are facing delays directly tied to power availability.

**Jordan:** And there's a helium story in there that I found almost absurd — strikes on Qatari helium production have driven spot prices up significantly, and semiconductor fabs in Taiwan and South Korea are now rationing the helium used in chip manufacturing. It's a reminder that this infrastructure chain is global and fragile.

**Alex:** The strategic response from hyperscalers is increasingly: become your own utility. Microsoft, Google, and Amazon are all investing directly in nuclear and renewable power projects. The phrase analysts are using is "Bring Your Own Power." The grid is no longer a background assumption — it's a primary development challenge.

**Jordan:** For developers and builders, this has real implications. About 30 to 50 percent of planned 2026 capacity is expected to slip to 2028. That means inference pricing is unlikely to fall as fast as the past two years suggested it might. The compute abundance story has a power constraint in the middle of it.

**Alex:** Worth pricing into your product planning.

---

## SEGMENT 4: DeepMind's AI Co-Mathematician — and a Real Open Problem Solved

**Jordan:** And now for something a little different. Google DeepMind this week published research on what they're calling the AI Co-Mathematician — a multi-agent system built on the Gemini models, designed to collaborate with human researchers on open-ended mathematical problems.

**Alex:** The benchmark number here is striking: the system scored 48 percent on FrontierMath Tier 4. FrontierMath is the benchmark Epoch AI built specifically to challenge AI systems with problems that human experts estimated would take AI systems years or even decades to approach. Tier 4 is the hardest tier. 48 percent is a new high.

**Jordan:** But benchmarks are one thing. The real story is Marc Lackenby, a mathematician at Oxford. He used the Co-Mathematician system to work on Problem 21.10 in the Kourovka Notebook — which, for the non-group-theorists among our listeners, is a curated collection of open problems in group theory that mathematicians have been working on for decades.

**Alex:** A reviewer agent in the system spotted a flaw in the AI's first proof attempt. And Lackenby realized, when he saw the flaw flagged, that he knew how to fill the gap. That's the collaboration model working: not the AI replacing the mathematician, but the AI's self-critique surfacing something the human could then resolve.

**Jordan:** What's architecturally interesting about the system is how it handles uncertainty. It's not just a single model answering a question — it's a hierarchy of agents running parallel research workstreams, tracking failed hypotheses, and producing LaTeX write-ups with margin annotations and provenance notes. Failed approaches are preserved as first-class outputs.

**Alex:** That last point matters more than it might seem. In scientific research, knowing what doesn't work is genuinely valuable. Most AI systems discard failed reasoning. This one logs it.

**Jordan:** And the real-world implication for researchers — not just mathematicians — is that we're entering a period where "AI co-author" is less metaphor and more accurate description. The question is less "can AI do research" and more "what does the collaboration interface look like."

**Alex:** And whether the mathematician's name goes first on the paper.

**Jordan:** That question is absolutely going to a committee somewhere.

---

## OUTRO

**Alex:** Quick recap. OpenAI's GPT-5.5 Instant is the new ChatGPT default, cutting hallucinations by 52 percent and bringing a 400K context window. Anthropic's Opus 4.7 holds the SWE-bench Pro lead at 64.3 percent. Both are worth re-evaluating if you haven't recently.

**Jordan:** Five Eyes agencies are warning that rapid agentic deployments are outpacing governance — the attack surface grows with every tool you add. Enterprises and developers should read the May 1st guidance; it's specific and actionable.

**Alex:** The AI infrastructure buildout is hitting a power wall. $690 billion in committed capex for 2026, but grid constraints mean nearly half of planned capacity may slip to 2028. Inference pricing won't fall as fast as compute spending suggests.

**Jordan:** And Google DeepMind's AI Co-Mathematician scored 48 percent on FrontierMath Tier 4 and helped resolve a real open problem in group theory. The era of AI-assisted mathematical research is not coming — it's here.

**Alex:** That's Daily AI Insights for May 9th. We'll be back on Monday. If you found this useful, share it with someone building in the space. I'm Alex.

**Jordan:** And I'm Jordan. Have a good weekend.

---

## SOURCES

1. [OpenAI releases GPT-5.5 Instant, a new default model for ChatGPT — TechCrunch](https://techcrunch.com/2026/05/05/openai-releases-gpt-5-5-instant-a-new-default-model-for-chatgpt/)
2. [GPT-5.5 Instant: smarter, clearer, and more personalized — OpenAI](https://openai.com/index/gpt-5-5-instant/)
3. [OpenAI updates ChatGPT Instant with GPT 5.5 — Axios](https://www.axios.com/2026/05/05/openai-chatgpt-update-default-model)
4. [Introducing Claude Opus 4.7 — Anthropic](https://www.anthropic.com/news/claude-opus-4-7)
5. [Claude Opus 4.7 leads on SWE-bench and agentic reasoning — The Next Web](https://thenextweb.com/news/anthropic-claude-opus-4-7-coding-agentic-benchmarks-release)
6. [Claude Opus 4.7 Benchmarks Explained — Vellum](https://www.vellum.ai/blog/claude-opus-4-7-benchmarks-explained)
7. [Five Eyes warn agentic AI is too dangerous for rapid rollout — The Register](https://www.theregister.com/2026/05/04/five_eyes_agentic_ai_recommendations/)
8. [US government, allies publish guidance on how to safely deploy AI agents — CyberScoop](https://cyberscoop.com/cisa-nsa-five-eyes-guidance-secure-deployment-ai-agents/)
9. [Five Eyes Sound Alarm on Autonomous AI Security Risks — BankInfoSecurity](https://www.bankinfosecurity.com/five-eyes-sound-alarm-on-autonomous-ai-security-risks-a-31590)
10. [Hyperscaler CapEx Hits $690B in 2026 — Introl Blog](https://introl.com/blog/hyperscaler-capex-690-billion-microsoft-azure-power-bottleneck-2026)
11. [AI-First Hyperscalers: 2026's Sprint Meets the Power Bottleneck — Data Center Knowledge](https://www.datacenterknowledge.com/hyperscalers/hyperscalers-in-2026-what-s-next-for-the-world-s-largest-data-center-operators-)
12. [The great data center delay: Why your AI chips are stuck in 2026 — Manufacturing Dive](https://www.manufacturingdive.com/news/opinion-omdia-ai-semiconductor-chip-scarcity/817172/)
13. [Google DeepMind Releases AI Co-Mathematician — OfficeChai](https://officechai.com/ai/google-deepmind-releases-ai-co-mathematician-that-creates-new-high-score-on-frontiermath-benchmark/)
14. [Best AI Models: April + May 2026 Leaderboard — Build Fast With AI](https://www.buildfastwithai.com/blogs/best-ai-models-may-2026-leaderboard)
