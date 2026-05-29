# Daily AI Insights — May 28, 2026
## Episode Title: Walls, Wires, and a New Architecture

**Runtime:** ~13 minutes
**Hosts:** Alex (male), Jordan (female)

---

## INTRO

**Alex:** Good morning and welcome to Daily AI Insights. I'm Alex.

**Jordan:** And I'm Jordan. It is Wednesday, May 28th, and we have a packed show for you today.

**Alex:** We do. The theme today — if there is one — is what happens when the old rules don't fit anymore. Old infrastructure rules, old regulatory frameworks, old chip architectures. Everything is getting renegotiated.

**Jordan:** We're going to cover a five-billion-dollar bet on Google's custom silicon, a landmark deal in Brussels that quietly rewrote the EU AI Act, a genuine policy reversal in Washington over AI safety, and what might be the first serious challenger to the transformer architecture in years.

**Alex:** That's a lot of rewiring for one morning. Let's get into it.

---

## SEGMENT 1: Blackstone and Google's $5 Billion TPU Cloud Bet

**Alex:** So the big infrastructure story this week is the Blackstone-Google joint venture. Announced May 18th — Blackstone is putting in five billion dollars in equity to co-create what they're calling a new compute-as-a-service company built around Google's Tensor Processing Units.

**Jordan:** And this isn't just another data center deal. The key word is TPU-as-a-service. Right now, if you want access to Google's TPUs, you go through Google Cloud. This new company would give customers a second, separate channel to that compute.

**Alex:** Right. Google brings the hardware — the chips, the software stack, the networking — and Blackstone brings capital and its real estate development muscle. They own more than 1.3 trillion dollars in assets and have become the largest private owner of data centers globally.

**Jordan:** The company has already named a CEO: Benjamin Treynor Sloss, who spent two decades at Google, most recently as chief programs officer. So this isn't a passive financial bet. They're building an operating company.

**Alex:** The first 500 megawatts of capacity is targeted for 2027. And that number — 500 megawatts — is worth sitting with for a second.

**Jordan:** It's a city's worth of electricity.

**Alex:** Basically. For context, a large traditional data center might run 10 to 40 megawatts. The new generation of AI facilities is scaling to 100 to 500 megawatts, and the electrical grid is struggling to keep up. Industry analysts say 30 to 50 percent of planned 2026 data center capacity will slip to 2028 because grid connections take three to seven years to process and transformer equipment has multiyear lead times.

**Jordan:** So even with five billion dollars and Google's chips, you can still get stuck in the queue at the utility company.

**Alex:** Which is why the site selection and real estate expertise Blackstone brings is genuinely strategic, not just financial. They're navigating a physical world problem, not a compute problem.

**Jordan:** This also fits into a broader pattern. Google just announced its eighth-generation TPUs — the TPU 8t for training, which delivers nearly three times the compute performance of its predecessor, and the TPU 8i for inference, engineered specifically for the low-latency needs of agentic workflows. That's 384 megabytes of on-chip SRAM and doubled interconnect bandwidth.

**Alex:** And at the same time, Meta announced a deal to purchase up to 100 billion dollars worth of AMD chips over multiple years. AMD's data center revenue hit 10.3 billion last quarter on the strength of its Instinct and EPYC lines. Everyone is building their own silicon moat.

**Jordan:** The Blackstone deal is confirmed by multiple sources — CNBC, Data Center Dynamics, Blackstone's own press release. This one is solid.

---

## SEGMENT 2: The EU AI Act Just Got a Rewrite

**Alex:** Okay, moving to Europe. On May 7th — three weeks ago — the Council of the EU and the European Parliament reached a provisional agreement that effectively amends the AI Act before its most significant provisions even go into force.

**Jordan:** This is the so-called Omnibus VII deal, and it matters because the original AI Act had a hard deadline of August 2nd, 2026 for high-risk AI system obligations to kick in. That deadline is now gone.

**Alex:** Pushed to when?

**Jordan:** For use-based applications — meaning AI used in hiring, education, critical infrastructure — the deadline moves to December 2027. For product-regulated cases, like medical devices or machinery embedding AI, it moves to August 2028.

**Alex:** So companies that have been scrambling to get compliant for this summer are getting an extra 16 to 24 months depending on their category.

**Jordan:** Right. And the stated reason is simplification — the EU has been trying to reduce compliance burden on smaller businesses. But critics will note that this is also the third time major AI Act deadlines have shifted since the regulation was adopted in 2024.

**Alex:** Is this a capitulation to industry pressure, or is it genuine acknowledgment that the rules needed refinement?

**Jordan:** Probably some of both. The agreement does include some genuinely new restrictions — not just delays. Specifically, the co-legislators added a prohibition on AI-generated non-consensual intimate images and CSAM. That's tightening, not loosening.

**Alex:** And the deal clarifies something that's been murky: the competence split between the EU AI Office and national regulators for general-purpose AI models. If the same company both builds the model and deploys it in a system, the AI Office has jurisdiction. If it's a third-party deployment, national authorities stay in charge.

**Jordan:** Which is a significant governance question as you have more and more companies building their own models and also shipping applications on top of them.

**Alex:** The formal adoption is still expected before August 2nd, which is the current trigger date. So the legal machinery is moving fast for EU standards.

**Jordan:** And this confirms something we've been watching: the EU is recalibrating from enforcement-first to a more phased, iterative approach. Whether that's wisdom or backsliding depends on who you ask.

---

## SEGMENT 3: Washington's AI Safety Reversal

**Alex:** From Brussels to Washington. This one has a bit of a "things they said they'd never do" quality to it.

**Jordan:** The short version: the Trump administration, which came into office explicitly criticizing Biden's AI safety executive order as overreach, is now quietly implementing policies that look a lot like that order.

**Alex:** The specific trigger, according to Fortune's reporting from May 6th, was Anthropic's Mythos model. Mythos apparently demonstrated the ability to autonomously identify and exploit cybersecurity vulnerabilities — that set off alarm bells in national security circles.

**Jordan:** And the response was to dust off something called CAISI — the Center for AI Standards and Innovation. That's the Trump administration's rebrand of Biden's US AI Safety Institute, which the new administration had initially sidelined.

**Alex:** But now CAISI is operational, and it has formal partnerships with Google, Microsoft, and Elon Musk's xAI to evaluate AI models before public release and conduct post-deployment assessments.

**Jordan:** The parallel to drug approval processes is explicit. Officials are reportedly studying an executive order that would require safety evaluations for frontier AI models before they can go public — analogous to how the FDA clears pharmaceuticals.

**Alex:** That would be a significant shift. The US has been the most permissive major AI jurisdiction by design. An evaluation requirement would align Washington closer to what the EU and UK have been building.

**Jordan:** And notably, the Defense Production Act invocation — which Biden used to require large model developers to share safety testing results with the government — is apparently remaining in place rather than being rescinded.

**Alex:** I want to flag the sourcing here. The Fortune piece is the primary source on the Mythos specifics and the executive order study. The broader CAISI reactivation and DPA invocation are corroborated by policy publications. But the executive order hasn't been signed — that part is still "under study."

**Jordan:** Accurate. So the policy reversal on CAISI and government model evaluation partnerships is confirmed. The drug-approval-style mandate is a policy proposal, not a done deal.

**Alex:** The broader point stands: national security concerns are doing what safety advocacy could not — moving the most pro-industry administration in recent memory toward AI oversight.

**Jordan:** Whether that oversight ends up being rigorous or cosmetic is the next question.

---

## SEGMENT 4: The Post-Transformer Moment?

**Alex:** Okay, last story — and this is the one that might age the best or worst depending on how the next 18 months play out. A company called Subquadratic launched something called SubQ 1M-Preview on May 5th, and it's being called the first commercial large language model built on a fully subquadratic sparse attention architecture.

**Jordan:** Translation: it doesn't use a transformer.

**Alex:** Doesn't use a standard transformer. Instead of the quadratic scaling that transformers have — where compute costs grow with the square of context length — SubQ claims to scale linearly. They're reporting up to 52 times faster attention at long contexts and a native context window of 12 million tokens.

**Jordan:** For comparison, Gemini 3.1 Ultra has a 2 million token context window, which was already considered enormous. 12 million is a different category.

**Alex:** The company raised a 29-million-dollar seed round, which is small by frontier AI standards but real money for an architecture-level bet. And their claim of roughly one-fifth the cost of frontier models on long-context tasks — if that holds up — would be genuinely disruptive.

**Jordan:** There's always a "but" at this point.

**Alex:** There is. We have the company's own benchmarks. We don't yet have independent third-party replication on full model quality. The architecture has been explored in research form — state space models, linear attention variants — and none have displaced transformers at scale yet.

**Jordan:** This also isn't the first time a non-transformer approach has launched with strong claims. Mamba, RWKV, and RetNet all got significant attention in 2024 and 2025 without dethroning the standard architecture.

**Alex:** Right. What's different here is it's a commercial product launch with a seed round, not just a research paper. That changes the dynamic slightly — there are investors who've evaluated the claims.

**Jordan:** And there's a separate academic signal worth noting. Researchers at Penn published a paper on a hybrid light-matter particle system that could dramatically reduce energy use for AI compute — by up to 100 times by one metric. That's basic research, years from production, but it speaks to how much engineering pressure there is right now on the energy and cost side of inference.

**Alex:** The benchmark race at the frontier has also hit something of a plateau this month. GPT-5.5 crossed 60 on the Intelligence Index — Claude Opus 4.7 helped set the table by breaking 57 in April — but we're in a relative lull before what most analysts expect will be a significant release in late May or June.

**Jordan:** So the headline models are incremental right now, and the interesting architecture bets are running underneath.

**Alex:** Which is exactly when the alternative approaches get their hearing.

**Jordan:** We'll watch SubQ carefully. If independent evaluations hold up, this is a big deal. If they don't, it joins a long list of transformer challengers.

---

## OUTRO

**Alex:** That's our show for today. Let's do a quick recap. Blackstone and Google are building a five-billion-dollar TPU cloud company, targeting 500 megawatts of compute capacity by 2027.

**Jordan:** The EU AI Act got an Omnibus amendment — high-risk deadlines pushed 16 to 24 months, new prohibitions on synthetic CSAM, and clearer jurisdiction rules for general-purpose AI.

**Alex:** The Trump administration reversed course on AI safety policy, reactivating the renamed AI Safety Institute and partnering with labs on pre-deployment evaluations — driven, reportedly, by national security concerns about frontier model capabilities.

**Jordan:** And a startup called Subquadratic launched what may be the first commercial post-transformer LLM. Early claims are remarkable. Independent verification is the next step.

**Alex:** Big week for a field that supposedly takes breaks in late May.

**Jordan:** Apparently not. Thanks for listening to Daily AI Insights. See you tomorrow.

---

## SOURCES

1. Blackstone press release — Blackstone-Google TPU Joint Venture: https://www.blackstone.com/news/press/blackstone-announces-joint-venture-with-google-to-create-new-tpu-cloud/
2. CNBC — Blackstone $5B Google JV: https://www.cnbc.com/2026/05/19/blackstone-google-ai-data-center-joint-venture-tpu.html
3. Data Center Dynamics — Blackstone-Google TPU cloud platform: https://www.datacenterdynamics.com/en/news/blackstone-and-google-team-up-for-new-tpu-based-cloud-platform/
4. EU Council — AI Act Omnibus Agreement, May 7: https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/
5. VerifyWise — EU AI Act Omnibus analysis: https://verifywise.ai/blog/eu-ai-act-omnibus-what-changed
6. Lewis Silkin — EU AI Act slim-down summary: https://www.lewissilkin.com/insights/2026/05/07/the-council-and-parliament-agree-to-slim-down-and-delay-parts-of-the-eu-ai-act-102ms0v
7. Fortune — Trump administration AI oversight reversal: https://fortune.com/2026/05/06/trump-administration-embraces-ai-oversight-policies-it-once-rejected-anthropic-mythos-caisi/
8. WhatLLM — New AI models May 2026, SubQ and benchmarks: https://whatllm.org/blog/new-ai-models-may-2026
9. Google Cloud Blog — AI infrastructure, TPU 8th gen, Next '26: https://cloud.google.com/blog/products/compute/ai-infrastructure-at-next26
10. Manufacturing Dive — Data center capacity delays 2026: https://www.manufacturingdive.com/news/opinion-omdia-ai-semiconductor-chip-scarcity/817172/
