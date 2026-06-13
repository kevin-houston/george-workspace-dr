# Daily AI Insights — June 11, 2026
## Episode Title: Microsoft Goes It Alone

**Runtime:** ~12–14 minutes
**Hosts:** Alex (male), Jordan (female)
**Date:** Thursday, June 11, 2026

---

## INTRO

**Alex:** Welcome to Daily AI Insights. I'm Alex.

**Jordan:** And I'm Jordan. It is Thursday, June 11, 2026, and this week has been genuinely consequential for the AI industry — Microsoft just cut its own model family loose from OpenAI, two competing AI labs are racing each other to Wall Street, Congress has written the first serious federal AI bill, and a Chinese lab has permanently repriced the frontier API market.

**Alex:** We'll get into all of it. Let's start with the story that has the most long-term structural significance: Microsoft just launched seven in-house AI models, and they explicitly built them without OpenAI.

**Jordan:** The era of that partnership being load-bearing infrastructure for Microsoft is over. We have the receipts.

---

## SEGMENT 1 — Microsoft Builds Its Own Stack: The MAI Family

**Alex:** So to set the scene — Microsoft Build 2026 happened last week, and Microsoft AI used it to announce what they're calling the MAI model family. Seven models, all trained in-house, all without OpenAI's involvement.

**Jordan:** And that last part matters because it wasn't always possible. Back in April, the Microsoft-OpenAI partnership restrictions were lifted, which gave Microsoft full rights to train its own models independently. This MAI launch is the first full exercise of those rights.

**Alex:** Right. The headline model is MAI-Thinking-1, the reasoning flagship. It's a 35 billion active parameter mixture-of-experts model with a 256K context window. Microsoft is claiming it reaches 97 percent on AIME 2025 and 94.5 percent on AIME 2026.

**Jordan:** For listeners who aren't deep in the benchmarks — AIME is the American Invitational Mathematics Examination, and it's become one of the harder reasoning benchmarks that frontier labs use to differentiate models. Those numbers put MAI-Thinking-1 in serious company.

**Alex:** Microsoft is also claiming it's preferred over Claude Sonnet 4.6 in blind human evaluations. The training data is fully traceable — no distillation from other labs, enterprise-grade provenance. That's actually a meaningful differentiation for corporate customers who care about supply chain.

**Jordan:** The second model that matters immediately for builders is MAI-Code-1-Flash. Five billion active parameters, live in GitHub Copilot right now, in the model picker in VS Code. Microsoft says it uses 60 percent fewer tokens than comparable coding models and outperforms Claude Haiku 4.5 on coding benchmarks at a lower price.

**Alex:** That "fewer tokens" claim is more interesting than any benchmark number. Token efficiency is where developer costs live. If your everyday autocomplete and inline help is using a model that's 60 percent cheaper to run, that compounds fast at scale.

**Jordan:** The rest of the family includes MAI-Image-2.5 for image generation — ranking above Gemini on the Arena leaderboard — MAI-Transcribe-1.5 for speech-to-text across 43 languages at five times the speed of current rivals, and MAI-Voice-2 for speech generation across 15-plus languages.

**Alex:** What I want to pull back and highlight is the strategic inflection here. Microsoft has been the largest investor and distribution partner for OpenAI. GPT-4, GPT-4o, o1 — all of that has been the engine under the hood of Copilot and Azure AI. They are now building their own engine.

**Jordan:** And not just prototypes. MAI-Code-1-Flash is shipping to GitHub Copilot users today. MAI-Thinking-1 is going to Azure AI Foundry. These are not research previews. Microsoft's blog post used the phrase "hill-climbing machine" to describe their development philosophy — fast iteration, competitive positioning, not a one-time announcement.

**Alex:** If you're a developer building on Azure or using GitHub Copilot, this week's news means your AI stack just got more diverse. You're no longer dependent on a single upstream model provider. That's a meaningful change in the risk profile of what you're building on.

---

## SEGMENT 2 — The AI IPO Race: Anthropic vs. OpenAI

**Alex:** Okay, segment two. The AI industry is about to have its IPO moment — or really, its IPO race. Anthropic filed a confidential S-1 with the SEC on June 1st. OpenAI followed with its own confidential filing on June 8th. Two of the most valuable private companies in the world, filing within a week of each other.

**Jordan:** The numbers are striking. Anthropic's filing came after a $65 billion Series H round that put its valuation at $965 billion. OpenAI is at $852 billion. So Anthropic actually edges out OpenAI on paper valuation right now — which would have seemed impossible eighteen months ago.

**Alex:** Revenue tells the same story. Anthropic is reporting a $47 billion annual run-rate, up from $10 billion last year. OpenAI disclosed $20-plus billion in 2025 annual recurring revenue. Both are growing at a pace that's genuinely hard to comprehend.

**Jordan:** There's a catch with OpenAI's picture, though. Their internal projections show $14 billion in losses for 2026. That's the reality of running frontier compute infrastructure at this scale. Anthropic, by contrast, says it's approaching its first profitable quarter, which is a very different investor story.

**Alex:** Both filings are confidential, which is standard — it lets them go back and forth with the SEC before the S-1 goes public. Reports point to Anthropic targeting a listing as soon as October, with OpenAI likely to follow.

**Jordan:** What's interesting about this race is what it reveals about positioning. Anthropic going first signals confidence that its story — safety-focused, enterprise-grade, profitable trajectory — is the right narrative for public markets right now.

**Alex:** OpenAI's story is more complicated. High valuation, large losses, a Microsoft relationship that just became more competitive given the MAI announcement we just covered. But OpenAI still has the consumer brand recognition that Anthropic doesn't.

**Jordan:** For developers and builders: this is the moment where the AI infrastructure layer becomes publicly traded and legible to the broader market. The API pricing wars, the benchmark competition, the enterprise deals — all of it is about to start showing up in quarterly earnings calls. Which could either drive more transparency, or drive more benchmark-gaming.

**Alex:** Both, probably.

---

## SEGMENT 3 — Congress Writes a Federal AI Bill

**Jordan:** Segment three, let's talk regulation. On June 4th — one week ago — Representatives Jay Obernolte, a Republican from California, and Lori Trahan, a Democrat from Massachusetts, released a discussion draft of the Great American Artificial Intelligence Act.

**Alex:** Which is quite a name.

**Jordan:** It is. But the substance is real. This is the first bipartisan draft of comprehensive federal AI legislation in the US. It has four titles: frontier AI governance, workforce, cybersecurity, and research and international cooperation.

**Alex:** Walk me through the governance piece, because that's where the teeth are.

**Jordan:** On the frontier side, the bill would require large model developers to disclose information about their models, submit to third-party audits through what they're calling Independent Verification Organizations, and protect whistleblowers who report safety violations. That's a meaningful accountability structure that doesn't currently exist at the federal level.

**Alex:** The state preemption clause is where it gets controversial. The bill would preempt state laws that specifically regulate the development of AI models, with a three-year sunset. So states couldn't pile on with their own conflicting development rules while the federal framework gets established.

**Jordan:** This is a direct response to the patchwork situation that's been building. Colorado's comprehensive AI law takes effect June 30th — nineteen days from now. California has the AI Transparency Act. Texas has the Responsible AI Governance Act. You have thirty-plus states doing their own thing, and companies are struggling to build products that comply with all of them simultaneously.

**Alex:** The key nuance the bill draws is between development and deployment. State laws around how AI is used — employment discrimination, housing, healthcare — those are explicitly not preempted. The three-year freeze is specifically on rules about building the models themselves.

**Jordan:** Which is a reasonable line to draw, but it will absolutely be fought over. The AI industry has been pushing hard for federal preemption. Civil liberties groups and state attorneys general have been pushing back equally hard.

**Alex:** The IVO structure — Independent Verification Organizations for third-party audits — is interesting as a governance model. It's similar to how financial auditors work. Not government inspectors reviewing every model; accredited third parties that certify compliance. That's a workable framework if the standards are set correctly.

**Jordan:** Big if. But the bipartisan authorship matters here. You don't usually see a tech-district Republican and a Massachusetts Democrat releasing joint AI legislation unless there's real political will behind it.

**Alex:** The White House released a four-page blueprint in March directing Congress to do exactly this kind of unified federal framework. So the executive branch, at least, is aligned with where this draft is headed. If you're building AI products that will ship in the US in 2027, this draft is worth reading — the audit requirement alone has real engineering and compliance implications.

---

## SEGMENT 4 — DeepSeek's Permanent Price War and the Huawei Hardware Story

**Alex:** Final segment, and this one is really about the economics of AI inference — specifically what happens when a well-funded Chinese lab decides to make a price cut permanent and signals it can sustain it because of domestic chip supply.

**Jordan:** DeepSeek made its 75 percent price cut on V4 Pro permanent on May 23rd. The new pricing is $0.0035 per million input tokens and $0.83 per million output tokens. The previous pricing was roughly $0.0145 input and $3.48 output.

**Alex:** For context: that $0.83 output token price puts DeepSeek V4 Pro below every major competitor. GPT-4-class output tokens at comparable quality are running multiple dollars per million. And DeepSeek V4 Pro is not a small model — it runs a one million token context window.

**Jordan:** The hardware story behind this is what makes it significant beyond just another price cut. When V4 launched, DeepSeek said the Pro version cost significantly more to run because of constraints in high-end compute. They were waiting on Huawei's Ascend 950 supernodes to ship at scale.

**Alex:** Those are coming. Huawei planned to ship around 750,000 units of the Ascend 950PR this year, with full-scale production in the second half of 2026. DeepSeek made the price cut permanent ahead of that timeline, signaling confidence that their compute costs are going to fall further as Huawei's domestic chip production scales.

**Jordan:** This is the Nvidia dependency reduction story playing out in real time. DeepSeek running at scale on Huawei Ascend chips rather than H100s is both a geopolitical story and an infrastructure story. It demonstrates that the export control regime meant to slow Chinese AI development has, at minimum, accelerated domestic Chinese semiconductor production.

**Alex:** The builder-level implication is direct: if you're running workloads where cost is the primary constraint — high-volume document processing, classification, retrieval-augmented generation — DeepSeek V4 Pro at these prices is worth evaluating seriously. The quality metrics are competitive with frontier models.

**Jordan:** The trust question is real for enterprise customers. Data residency, supply chain provenance, regulatory exposure — those concerns are legitimate. But the weights are open. You can pull DeepSeek V4 Pro and run it yourself, in your own infrastructure. At that point you're not touching their API at all.

**Alex:** And that's the broader point. The open-weights availability means the pricing pressure is structural, not tactical. Every other provider has to respond to a world where a capable frontier model is available to self-host for free and to run via API at commodity prices.

**Jordan:** We're heading toward a world where inference cost for most applications drops to near zero. The question stops being "can I afford to run this model" and becomes "which model do I trust, which fits my latency requirements, and which can I actually audit."

**Alex:** That's a better set of questions than the ones developers were asking two years ago.

---

## OUTRO

**Alex:** That's our show for Thursday, June 11, 2026. Four stories: Microsoft launching its own model family at Build, Anthropic and OpenAI racing each other to the public markets, Congress writing the first serious federal AI bill, and DeepSeek permanently lowering the floor on frontier API pricing.

**Jordan:** The through-line across all four: the AI infrastructure layer is becoming legible. It's going public, getting regulated, getting competed over by multiple national players. That's a materially different landscape than 2024, when a handful of labs controlled everything.

**Alex:** More players, more complexity, more opportunity — and more to track. We'll be back tomorrow.

**Jordan:** Thanks for listening to Daily AI Insights. I'm Jordan.

**Alex:** And I'm Alex. See you next time.

---

## SOURCES

1. Microsoft AI — Building a hill-climbing machine: Launching seven new MAI models: https://microsoft.ai/news/building-a-hillclimbing-machine-launching-seven-new-mai-models/
2. Microsoft AI — Introducing MAI-Thinking-1: https://microsoft.ai/news/introducing-mai-thinking-1/
3. Microsoft AI — Introducing MAI-Code-1-Flash: https://microsoft.ai/news/introducingmai-code-1-flash/
4. Neowin — Microsoft unveils MAI-Thinking-1 reasoning and MAI-Code-1 coding models: https://www.neowin.net/news/microsoft-unveils-mai-thinking-1-reasoning-and-mai-code-1-coding-models/
5. BuildFastWithAI — AI News June 11, 2026: 12 Biggest Stories Today: https://www.buildfastwithai.com/blogs/ai-news-today-june-11-2026
6. Fortune — Anthropic confidentially files for IPO after raising $65 billion at a $965 billion valuation: https://fortune.com/2026/06/01/anthropic-confidentially-files-ipo-965-billion-valuation/
7. CNBC — Anthropic confidentially files IPO prospectus with SEC: https://www.cnbc.com/2026/06/01/anthropic-ipo-s1-prospectus.html
8. Obernolte House — Great American AI Act discussion draft: https://obernolte.house.gov/media/press-releases/obernolte-trahan-release-discussion-draft-great-american-ai-act
9. Roll Call — Bipartisan AI draft proposes three-year preemption of state laws: https://rollcall.com/2026/06/04/bipartisan-ai-draft-proposes-three-year-preemption-of-state-laws/
10. DLA Piper — Unpacking the Great American AI Act: https://www.dlapiper.com/en-us/insights/publications/2026/06/unpacking-the-great-american-ai-act
11. Relveh — DeepSeek Makes 75% V4-Pro Price Cut Permanent as Huawei Chip Demand Surges: https://relvehq.com/blog/noise/deepseek-v4-pro-permanent-price-cut-huawei-ascend-950
12. Technology.org — DeepSeek Cuts V4-Pro AI Price 75% Permanently: https://www.technology.org/2026/05/25/deepseek-v4-pro-permanent-75-percent-price-cut/
13. FedScoop — Bipartisan Great American AI Act draft: https://fedscoop.com/bipartisan-great-american-ai-act-draft-proposes-new-federal-ai-governance-framework/
