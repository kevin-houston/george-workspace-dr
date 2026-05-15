# Daily AI Insights — May 13, 2026
## Episode Title: The $950 Billion Question
**Runtime**: ~13 minutes | **Hosts**: Alex & Jordan

---

## INTRO

**Alex:** Welcome to Daily AI Insights. I'm Alex.

**Jordan:** And I'm Jordan. It is May 13th, 2026, and the AI industry did not take the week off.

**Alex:** Not even close. Today: Anthropic is in talks to raise money at a valuation that would put it above OpenAI — near a trillion dollars. And that's not a typo.

**Jordan:** We also have the latest act in an escalating AI security arms race — OpenAI just launched something called Daybreak, going head-to-head with Anthropic's Mythos model on the same turf: finding software vulnerabilities before attackers do.

**Alex:** On the hardware side, AMD posted Q1 numbers that are quietly changing the story about who wins the AI chip race.

**Jordan:** And finally: a small startup called Subquadratic may have just shipped the first commercial language model that isn't built like every other language model. We'll explain what that means and why it matters.

**Alex:** Let's get into it.

---

## SEGMENT 1: Anthropic Nears $950 Billion Valuation

**Jordan:** So, Anthropic. The New York Times broke this last night, and Bloomberg and the Financial Times have since confirmed it: Anthropic is in active talks to raise somewhere between thirty and fifty billion dollars in a new funding round that would value the company at up to nine hundred and fifty billion dollars.

**Alex:** Nine hundred and fifty billion. For context: three months ago, Anthropic was valued at three hundred and eighty billion dollars. Before that round, it was around sixty billion. This is a company that has roughly tripled in value in ninety days.

**Jordan:** And it would actually put Anthropic's valuation above OpenAI, which raised money in March at an eight hundred and fifty-two billion dollar valuation.

**Alex:** So we now have two AI companies whose valuations exceed most of the world's publicly traded corporations, competing with each other in weeks-long fundraising rounds. The broader venture context is staggering — AI companies pulled in two hundred and ninety-seven billion dollars in just the first quarter of 2026, according to data cited in the Times piece.

**Jordan:** Let's talk about what's actually driving this, because it's not just hype. Dario Amodei recently said Anthropic hit a thirty billion dollar annual revenue run rate. And then, in one of the more unusual investor signals in recent memory, said he hoped the company wouldn't actually grow eighty times this year because that would be — and I'm quoting — "crazy and too hard to handle."

**Alex:** For a company that was doing a few hundred million in revenue two years ago, that trajectory is almost incomprehensible. Claude Code — the agentic coding product — has been a major driver. Once engineers adopt it as infrastructure, it's very sticky.

**Jordan:** There's also genuine political intrigue baked into this story. Anthropic released a model called Mythos last month — powerful enough at finding software vulnerabilities that the company declined to release it publicly, giving access to only a handful of organizations. That move complicated their relationship with the Department of Defense, which called Anthropic a security risk. Anthropic then sued the government.

**Alex:** And now — because the model is apparently that powerful — there are reportedly "productive" White House conversations happening, with U.S. officials trying to mend the rift.

**Jordan:** The round hasn't closed, and the Times was careful to note talks could still fall apart. But Google has already committed up to forty billion in Anthropic, and Amazon up to twenty-five billion.

**Alex:** The real story here isn't just the number. It's that Anthropic — which was founded by people who left OpenAI over safety concerns — has become simultaneously the most safety-focused lab and arguably the most commercially aggressive one. Those two things are usually in tension. Right now they're somehow executing on both.

---

## SEGMENT 2: The AI Security Arms Race — Daybreak vs. Mythos

**Jordan:** Which leads directly into our second story, because OpenAI is not watching Mythos happen from the sidelines.

**Alex:** On May 10th, OpenAI launched Daybreak. It's a cybersecurity initiative that bundles their frontier models — GPT-5.5, and a permissive variant called GPT-5.5-Cyber — with Codex Security, their agentic coding harness, and a network of security partners.

**Jordan:** The pitch is straightforward: your development team uses Daybreak to find vulnerabilities in your own codebase before an attacker does. It can build threat models for a repository, identify and test vulnerabilities in an isolated environment, and propose patches. Multiple outlets confirmed this — The Hacker News, Forbes — and they're right to frame it as a direct counter to Anthropic's Mythos.

**Alex:** The partner list is significant. Akamai, Cisco, Cloudflare, CrowdStrike, Fortinet, Oracle, Palo Alto Networks, Zscaler. These aren't pilot customers. These are the companies that run the internet's defensive infrastructure.

**Jordan:** Access isn't fully public yet — organizations have to request a scan or contact OpenAI's sales team. Same controlled rollout as Mythos. Which tells you something about how seriously both companies view the dual-use risk here.

**Alex:** OpenAI is handling that by tiering access: there's a standard version with normal safeguards, a Trusted Access for Cyber version for verified defensive work, and GPT-5.5-Cyber, the permissive model for red teaming and pen testing in controlled environments.

**Jordan:** And here's a consequence worth sitting with: these tools are simultaneously making the security problem worse in the short term. HackerOne — the major bug bounty platform — paused its internet bug bounty program in March. The reason: AI-assisted research has accelerated vulnerability discovery so fast that open-source maintainers can't keep up with the flood of incoming reports.

**Alex:** Some of those reports are hallucinated too. AI-generated vulnerabilities that sound completely plausible but don't actually exist. It's called triage fatigue, and it's a real operational problem right now.

**Jordan:** So the picture is: AI both amplifies the threat and is being proposed as the solution. And the two most capable AI labs in the world are now in a direct race to be the dominant defensive layer. For anyone building security tooling — or trying to secure your own infrastructure — both Daybreak and Mythos are worth tracking closely.

---

## SEGMENT 3: AMD's Breakout Quarter — Data Center Up 57%

**Alex:** Let's talk chips. AMD posted Q1 2026 earnings about a week ago, and these numbers deserve more attention than they've gotten.

**Jordan:** Total revenue: ten point three billion dollars, up thirty-eight percent year-over-year. Beat analyst estimates by four percent. But the number to focus on is the data center segment: five point eight billion dollars, up fifty-seven percent.

**Alex:** That is not a rounding error. Fifty-seven percent growth. And it beat Wall Street expectations — analysts had projected five point six billion. AMD also raised its Q2 guidance to eleven point two billion dollars. Shares jumped sixteen percent after the report.

**Jordan:** Lisa Su has been executing a long-term chip strategy here. The Instinct GPU line for AI training and inference has gone from largely an afterthought to a genuine alternative to Nvidia's H-series. The EPYC CPU line has taken meaningful data center market share from Intel.

**Alex:** For context on why this matters: the narrative around AI infrastructure has basically been "Nvidia or nothing" for the past two years. AMD demonstrating it can actually ship at scale and win significant data center contracts changes that narrative for the entire industry.

**Jordan:** There's a complementary data point here. A company called Zyphra released an open-weight model last week — ZAYA1-8B — trained end-to-end on AMD Instinct hardware. Not ported from a Nvidia-trained checkpoint. Trained from scratch on AMD.

**Alex:** That's a proof of concept that matters. If competitive open-weight models can be built without a Nvidia dependency, AI infrastructure gets a lot less concentrated at the supply chain level.

**Jordan:** The semiconductor industry is on track to cross one trillion dollars in annual revenue this year for the first time, according to IDC. AI infrastructure is essentially the entire growth driver. AMD's quarter is one piece of evidence that the hardware race is becoming genuinely competitive.

**Alex:** And competition at the infrastructure layer has downstream benefits for everyone building on top of it — more supply, better pricing, more options.

---

## SEGMENT 4: The Architecture Frontier — A Non-Transformer LLM Ships

**Jordan:** Our final story is the most technical, but if you build with these models professionally it's probably the one with the most interesting long-term implications.

**Alex:** So throughout May, the very top of AI model leaderboards has been quiet. GPT-5.5 broke sixty on Artificial Analysis's Intelligence Index in late April — that's the highest score the index has seen. Claude Opus 4.7 landed just before that. After a chaotic April where five different labs put models above 50 in a single month, May has been a breather at the frontier.

**Jordan:** What showed up instead was a company called Subquadratic — and a model called SubQ — which launched May 5th with twenty-nine million dollars in seed funding and one very specific claim: their model is not a transformer.

**Alex:** Standard transformer attention — the architecture running GPT, Claude, Gemini, and essentially every major LLM — is computationally O-N-squared in context length. Double the context window, quadruple the compute cost. That's why long-context models are expensive, and why most "million-token context" claims come with quiet asterisks about quality degrading at scale.

**Jordan:** SubQ uses sparse, subquadratic attention end-to-end. The first release ships with a native twelve million token context window and claims roughly one-fifth the cost of frontier models on long-context tasks, and up to fifty-two times faster attention at scale.

**Alex:** To be fully transparent: those are vendor numbers. No independent third-party benchmark has verified the 52x claim yet. And subquadratic attention as a research area isn't new — Mamba, RWKV, Hyena, BASED have all shown promise and then plateaued against frontier transformers on standard tasks.

**Jordan:** So the honest question is whether SubQ is the one that doesn't plateau. What's genuinely new here is the packaging: it's the first time someone has put subquadratic attention behind a commercial API and built a real product on top. SubQ Code is a repo-wide coding agent designed to use the full context window.

**Alex:** And that's the actual use case. If you want to load an entire large codebase into context, analyze hundreds of documents simultaneously, or run multi-document research at scale — transformer inference costs become a real constraint. If SubQ's cost numbers hold in practice, the economics change.

**Jordan:** Separately, OpenAI on May 5th made GPT-5.5 Instant the new default for ChatGPT — not the frontier GPT-5.5, but the lighter, faster sibling. The framing they chose is worth noting: fewer hallucinations in regulated domains like law, medicine, and finance. Not "smarter."

**Alex:** That's a tell about where the competition is actually heading. Not higher benchmark scores — reliable behavior in professional, high-stakes settings. When the ChatGPT default changes, the median experience for hundreds of millions of users changes overnight.

**Jordan:** So: no new frontier model in the first half of May. But a potential architectural disruption, a default model swap affecting hundreds of millions of people, and the first proof that competitive models can train on non-Nvidia hardware. Not bad for a quiet month.

---

## OUTRO

**Alex:** That's Daily AI Insights for May 13th, 2026. Four stories: Anthropic approaching a trillion-dollar valuation, OpenAI and Anthropic racing to own the AI security layer, AMD proving the chip race has a second competitor, and a non-transformer LLM shipping commercially for the first time.

**Jordan:** The security story and the architecture story are both early-stage and moving fast. If either is directly relevant to what you're building, they're worth watching more than a typical week's news cycle.

**Alex:** We'll be back tomorrow. Thanks for listening.

**Jordan:** See you then.

---

## SOURCES

1. **Anthropic $950B valuation talks** — *New York Times*, May 12, 2026: https://www.nytimes.com/2026/05/12/technology/anthropic-funding-950-billion-valuation.html (corroborated by Bloomberg and Financial Times)

2. **OpenAI Daybreak cybersecurity initiative** — *The Hacker News*, May 12, 2026: https://thehackernews.com/2026/05/openai-launches-daybreak-for-ai-powered.html (corroborated by Forbes: https://www.forbes.com/sites/timkeary/2026/05/12/openai-daybreak-goes-head-to-head-with-anthropic-to-redefine-security/ and MarkTechPost)

3. **AMD Q1 2026 data center +57%** — *TheStreet*, May 10, 2026: https://www.thestreet.com/investing/stocks/amd-and-intel-lead-2026-gains-as-ai-guard-changes (corroborated by Intellectia.ai, Investing.com, TradingKey)

4. **SubQ non-transformer LLM + GPT-5.5 Instant default** — *WhatLLM.org*, May 13, 2026: https://whatllm.org/blog/new-ai-models-may-2026 (corroborated by llm-stats.com)

5. **Claude Opus 4.7 launch** — *Anthropic*, April 2026: https://www.anthropic.com/news/claude-opus-4-7

6. **HackerOne bug bounty pause** — cited in The Hacker News Daybreak article (source 2)

7. **IDC semiconductor forecast** — *IDC*: https://www.idc.com/resource-center/blog/semiconductor-market-to-surge-past-the-trillion-dollar-threshold-ai-infrastructure-drives-market-growth/
