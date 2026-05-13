# Daily AI Insights — May 13, 2026

**Episode Title:** Altman Takes the Stand

**Runtime:** ~13 minutes
**Hosts:** Alex (male), Jordan (female)

---

## INTRO

**Alex:** Good morning. I'm Alex.

**Jordan:** And I'm Jordan. This is Daily AI Insights.

**Alex:** A lot happening today. OpenAI's Sam Altman was on the witness stand yesterday, being cross-examined by Elon Musk's attorneys. We'll go through what he said and what it means for a company that's become the most consequential in tech.

**Jordan:** We're also looking at a GitHub repository that has done something almost no software project has ever done — overtaken React in total stars in under three months.

**Alex:** State-level AI law is landing. Not proposals. Not frameworks. Connecticut's SB5 is heading to the governor's desk and has real teeth starting this fall.

**Jordan:** And we'll close with what happened at SAP's annual conference this week, because the enterprise agentic AI story moved from pilot to product in a single keynote.

**Alex:** Let's get into it.

---

## SEGMENT 1 — Altman on the Stand

**Jordan:** So the OpenAI-versus-Musk trial has been running for three weeks now, and yesterday was the moment a lot of people had been waiting for — Sam Altman in the witness chair.

**Alex:** And the central question that Musk's legal team is pressing on is whether OpenAI's conversion from a nonprofit to a public benefit corporation is effectively stealing assets that were donated in good faith to a charity.

**Jordan:** Musk's lawyer Steven Molo went after Altman on a text message that Altman sent Musk in February 2023, where he wrote that OpenAI "would not have happened without you." Molo asked if Altman stood by that. Altman said — and this is a direct quote — "I have changed my view on Elon significantly."

**Alex:** Which is fairly remarkable to say under oath in a courtroom. What else came out?

**Jordan:** The big factual claim that emerged from earlier testimony — not Altman's, but through other witnesses — is that Musk allegedly demanded 90 percent of OpenAI at one point during the early days. Altman addressed this indirectly but didn't refute the underlying dynamic.

**Alex:** Under cross-examination, Musk's lawyer asked him directly: "Are you completely trustworthy?" Altman said yes, that he believes he is — quote — "an honest and trustworthy businessperson." The contrast with Musk's own testimony earlier in the trial is pretty stark. Multiple outlets noted that Musk was combative and raised his voice during questioning. Altman was, by most accounts, measured and careful.

**Jordan:** Closing arguments are scheduled for Thursday, and the judge could have a verdict from the advisory jury as early as next week.

**Alex:** The stakes here go beyond the two people in the room. If Musk wins — even partially — it could force OpenAI to revisit its conversion terms, potentially delay or complicate its plan to become a fully for-profit company. That has downstream consequences for how the company raises capital and competes with Google and Anthropic.

**Jordan:** And for builders specifically: OpenAI's product roadmap and pricing structure are deeply tied to its capital structure. If the corporate conversion is disrupted or delayed, expect some turbulence in how API access and enterprise agreements are structured.

**Alex:** Closing arguments Thursday. We'll have an update Friday.

---

## SEGMENT 2 — The GitHub Phenomenon: OpenClaw

**Jordan:** Okay, let's talk about a software project that has genuinely broken records. OpenClaw — github.com/openclaw/openclaw — now has over 310,000 stars on GitHub.

**Alex:** For context: React, the JavaScript framework built by Facebook and used on hundreds of millions of websites, took roughly eight years to accumulate that kind of star count. OpenClaw did it in about 60 days after going viral in January.

**Jordan:** According to multiple tracking sources, OpenClaw overtook React to become the most-starred active software project in GitHub history in under two months.

**Alex:** So what actually is it?

**Jordan:** OpenClaw is a personal AI assistant that runs entirely on your own devices — no cloud required — and acts as a local gateway connecting AI models to over 50 integrations. We're talking WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Microsoft Teams, WeChat. It speaks and listens on macOS, iOS, and Android. It renders a live canvas you can interact with.

**Alex:** So it's not another chatbot wrapper. It's an agent you own, that lives on your device, and talks to you through whatever app you already use.

**Jordan:** The project was built by Austrian developer Peter Steinberger, who published it in November 2025 under the name Clawdbot. It hit critical mass in January when it started spreading through developer communities, and NVIDIA has since put out a post on what the project means for autonomous agent deployment.

**Alex:** The timing is interesting, because OpenClaw went viral right around when concerns about AI data privacy were peaking. There's a version of this story where the appetite for a local, self-hosted AI agent is partly a reaction to the centralized model of OpenAI and Anthropic.

**Jordan:** It's MIT-licensed. Anyone can fork it, build on top of it, deploy it internally. And 58,000 forks suggests that's exactly what people are doing.

**Alex:** For developers: this project is worth understanding structurally. The architecture of a local AI gateway with deep integration into messaging platforms is going to show up in a lot of enterprise deployments where data can't leave the building. If you're building AI tooling and your customers have sovereignty requirements, the OpenClaw pattern is worth studying.

**Jordan:** Three hundred and ten thousand stars is also, candidly, a community signal. When that many developers are paying attention to something, the ecosystem around it grows fast. Plugins, adapters, integrations — the infrastructure for building on top of OpenClaw is being laid right now.

**Alex:** And it's free.

---

## SEGMENT 3 — State AI Law Gets Real: Connecticut SB5

**Alex:** Let's talk about regulation, because something changed this week that isn't getting enough attention.

**Jordan:** Connecticut's SB5 passed the state legislature on May 1st, and Governor Lamont has confirmed he plans to sign it. This is not a proposal. It is not a framework. It is not a set of principles. It is law, with compliance dates beginning October 1st of this year.

**Alex:** That is five months away.

**Jordan:** Five months. And the provisions are substantive. On employment: companies that use automated tools in hiring, promotion, or personnel decisions have to disclose that they're using AI, employees get the right to know, and — this is the important part — using an AI tool is explicitly not a legal defense if that tool discriminates.

**Alex:** So "the algorithm did it" is not an argument you can make in a Connecticut court.

**Jordan:** Not anymore. There are also whistleblower-style protections for people inside AI companies who report safety concerns. And the chatbot provisions are notable: starting January 2027, any AI companion — defined broadly as any model that communicates in natural language and simulates human conversation — has to disclose that it's not human.

**Alex:** The contrast with Colorado is instructive. Colorado passed an AI bill a year ago that was fairly prescriptive — required detailed risk management programs, impact assessments, proactive anti-discrimination auditing. And now Colorado is in the process of rolling much of that back, with SB26-189, which replaces the requirements-heavy approach with a leaner documentation-and-notice framework.

**Jordan:** So you have two adjacent states doing opposite things. Connecticut is adding substantive requirements. Colorado is peeling them back.

**Alex:** Which tells you there is no consensus at the state level on what AI compliance actually looks like. But here's the thing: if you operate in Connecticut — or if your company's employment decisions affect Connecticut residents — the law applies to you regardless of where you're headquartered.

**Jordan:** The federal picture remains murky. The White House is still working on what an executive order on high-risk AI would look like, but it hasn't landed. Meanwhile, Connecticut, Texas, and several other states are moving forward with binding requirements.

**Alex:** The practical implication for any company deploying AI in HR workflows: you need a Connecticut compliance audit on your roadmap for Q3.

**Jordan:** SB5 is also the first comprehensive state law to address AI companions directly — which is relevant for any company building conversational AI. The disclosure requirements are broad. If your product communicates in natural language and could be perceived as human, Connecticut wants a label on it.

---

## SEGMENT 4 — Enterprise Agentic AI: SAP Sapphire

**Alex:** The last segment is about what happened at SAP's annual Sapphire conference this week, because the enterprise AI deployment story crossed a threshold.

**Jordan:** SAP unveiled what they're calling the Autonomous Enterprise at Sapphire 2026. The centerpiece is a unified Business AI Platform — merging three previously separate SAP AI products into one environment where companies can build, deploy, and govern agents.

**Alex:** And the headline number is 50-plus domain-specific AI agents — called Joule Assistants — deployed across finance, supply chain, procurement, HR, and customer experience. These are not demos. These are production agents running in SAP's installed base.

**Jordan:** For context: SAP's ERP software runs the back-office operations of roughly 77 percent of the world's transaction revenue. When SAP deploys 50 AI agents into those workflows, it's not a pilot with a handful of customers. It's a product that could touch billions of dollars in operational decisions almost immediately.

**Alex:** The NVIDIA integration is notable. SAP and NVIDIA announced something called NemoClaw — a reference blueprint for developing and deploying autonomous agents inside Joule Studio, SAP's agent development environment. The idea is to give enterprise developers a structured path from prototype to trusted production agent, with NVIDIA's inference infrastructure underneath.

**Jordan:** SAP also announced a 100 million dollar AI fund for startups building on top of their platform. Which is a common move — tie the ecosystem to your infrastructure — but signals that they expect significant third-party agent development on their stack.

**Alex:** SAP isn't alone this week. Salesforce's Agentforce opened so agents can execute workflows directly. Cloudflare let agents deploy applications autonomously. Microsoft activated agentic infrastructure capabilities. All in the same week.

**Jordan:** This is the enterprise agentic moment that has been building for 18 months. The question in 2024 was "will enterprises actually deploy AI agents?" The question in 2025 was "how do you govern them?" The question in 2026, apparently, is "which agent platform do you want to be locked into?"

**Alex:** For builders: the vendor lock-in risk in agentic AI platforms is real and getting more real. SAP's agents live in SAP's platform. Salesforce's agents live in Salesforce. The companies that build portable, platform-agnostic agent infrastructure — things like OpenClaw, which we covered in the last segment — may have an advantage as enterprises figure out their agent strategy.

**Jordan:** The governance layer is still the open problem. SAP has a deployment framework but monitoring, auditing, and explaining what agents actually did remains unsolved at scale.

---

## OUTRO

**Jordan:** That's Daily AI Insights for May 13, 2026. Quick recap: Sam Altman testified in the OpenAI-versus-Musk trial — closing arguments Thursday, verdict possible next week. OpenClaw has surpassed 310,000 GitHub stars, overtaking React to become the most-starred active project in GitHub history. Connecticut's SB5 is heading to the governor's desk and brings real AI compliance requirements starting October 1st. And SAP launched 50-plus enterprise AI agents at Sapphire, with NVIDIA's NemoClaw blueprint underneath.

**Alex:** Four stories that, between them, cover law, code, courtrooms, and corporate software. A full map of where AI is landing.

**Jordan:** Thanks for listening. We'll be back tomorrow.

**Alex:** Stay curious.

---

## SOURCES

1. **OpenAI / Altman testimony** — CNBC (May 12, 2026): https://www.cnbc.com/2026/05/12/openai-trial-updates-sam-altman-set-to-testify-in-musk-suit.html | NPR: https://www.npr.org/2026/05/12/nx-s1-5811730/openai-sam-altman-testimony-elon-musk-trial | Fortune: https://fortune.com/2026/05/12/sam-altman-testimony-open-ai-elon-musk-trial/ | Al Jazeera (90% claim): https://www.aljazeera.com/news/2026/5/12/sam-altman-says-elon-musk-wanted-90-percent-of-openai-in-high-stakes-trial | CNN: https://www.cnn.com/2026/05/12/tech/sam-altman-openai-vs-elon-musk-testimony

2. **OpenClaw GitHub** — GitHub: https://github.com/openclaw/openclaw | DigitalOcean overview: https://www.digitalocean.com/resources/articles/what-is-openclaw | NVIDIA Blog: https://blogs.nvidia.com/blog/what-openclaw-agents-mean-for-every-organization/ | Star count tracking: https://www.askglitch.com/blog/top-5-trending-ai-github-repos-may-2026

3. **Connecticut SB5** — CT Mirror (passage): https://ctmirror.org/2026/05/01/artificial-intelligence-house-regulation-passage-ct/ | DLA Piper (full analysis): https://www.dlapiper.com/en-us/insights/publications/2026/05/unpacking-connecticuts-new-ai-law | Kelley Drye (CO comparison): https://www.kelleydrye.com/viewpoints/blogs/ad-law-access/ai-regulatory-roundup-recent-developments-in-colorado-connecticut-and-california

4. **SAP Sapphire + NVIDIA NemoClaw** — Reworked.co (SAP Autonomous Enterprise): https://www.reworked.co/digital-workplace/sap-unveils-autonomous-enterprise-100m-ai-fund/ | HPCwire (NVIDIA SAP): https://www.hpcwire.com/aiwire/2026/05/12/nvidia-and-sap-bring-trust-to-specialized-agents/
