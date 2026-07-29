# AI Today — Wednesday, July 29, 2026

**Hosts:** Alex and Jordan
**Date:** Wednesday, July 29, 2026
**Word count target:** 1,800–2,400 words

---

## [INTRO]

**Alex:** Good morning and welcome to AI Today. I'm Alex.

**Jordan:** And I'm Jordan. We're recording on Wednesday, July 29, 2026, and it has been quite a week in AI — breaches, petitions, autonomous hackers, and a new frontier model. We've got a lot to cover.

**Alex:** Let's get into it.

---

## Segment 1: The OpenAI Breach Gets Bigger

**Alex:** We start today with a story that keeps expanding. You may have heard about a breach involving OpenAI systems — but as of this week, the scope is significantly wider than initially reported.

**Jordan:** Right. So to recap: earlier this year there were reports that a threat actor had accessed internal OpenAI communications. At the time it was framed as a relatively contained incident. But reporting from BleepingComputer and confirmed by Ars Technica this week paints a much more alarming picture.

**Alex:** The attack vector was a chain of eight zero-day vulnerabilities discovered in JFrog Artifactory — that's the artifact repository manager used heavily in enterprise software development pipelines. The attacker exploited these vulnerabilities in sequence to gain persistent access, and from there moved laterally into connected systems.

**Jordan:** And this didn't stop at OpenAI. Bloomberg and Al Jazeera have both reported that Modal Labs — a cloud compute company popular with AI developers — was the second confirmed company affected in the same campaign. We're now looking at at least four compromised accounts and a log of approximately 17,600 actions taken by the attacker across both organizations.

**Alex:** Seventeen thousand six hundred actions. That's not a quick smash-and-grab. That's sustained, careful exfiltration.

**Jordan:** The JFrog zero-day chain is the technical story here. Artifactory is one of those pieces of enterprise infrastructure that touches almost everything — build artifacts, container images, model weights in some cases. If you can persist inside Artifactory, you have a very privileged view of what's being built and how.

**Alex:** JFrog has patched the vulnerabilities — all eight — and pushed the updates as of this week. BleepingComputer has the CVE list in their coverage from July 28th. Modal Labs has confirmed the incident in a brief statement, and OpenAI has not substantively expanded on their earlier disclosure.

**Jordan:** The open question is: what was taken? Model weights? Training data? Internal communications? Source code? We don't know. And that uncertainty is exactly what makes this incident significant for anyone following AI security.

**Alex:** The broader lesson here is about supply chain security. JFrog Artifactory is ubiquitous. The combination of a long dwell time — 17,600 actions suggest weeks or months of access — and a shared infrastructure vector means this could affect more organizations than have disclosed so far.

**Jordan:** Watch for more names to surface. This one isn't closed yet.

---

## Segment 2: AI Employees Ask Government to "Pace the Frontier"

**Alex:** Our second story is a different kind of intervention. This week, more than 1,100 employees from AI companies — including OpenAI and Anthropic — signed an open letter asking the US government to take a specific approach to international AI governance.

**Jordan:** The letter is called "Pacing the Frontier" — and the campaign site is pacingthefrontier.com. Euronews and AI news aggregator aibase.com both covered the release this week.

**Alex:** The core argument is that the US should not focus solely on restricting AI exports or trying to slow adversaries' development, but instead should invest heavily in maintaining American frontier AI leadership while simultaneously building international frameworks for coordination.

**Jordan:** The analogy they draw is to nuclear nonproliferation. The argument is: you can't uninvent the technology, and trying to deny it to everyone just creates incentives for other nations to develop it independently, outside any governance structure. Better to be at the table setting the rules.

**Alex:** What's notable is who's signing. These aren't just policy advocates — they're researchers and engineers actively building the systems in question. That's a different kind of credibility than a think-tank letter.

**Jordan:** It's also a somewhat unusual political posture for AI company employees. There's been a narrative that AI companies are either: one, lobbying for permissive regulation to keep building, or two, pushing for restrictive safety mandates. This letter is arguing for a third path — active engagement in shaping international governance rather than either of those positions.

**Alex:** The timing matters too. There are ongoing discussions in Geneva and in bilateral US-China AI safety talks. The letter is clearly aimed at influencing those conversations.

**Jordan:** Euronews' coverage on July 29th notes that the signatories include a mix of people who've been vocal safety advocates and people who've pushed back on more restrictive proposals. That coalition is meaningful — this isn't one faction of the AI safety debate speaking.

**Alex:** Whether the government acts on it is a separate question. But 1,100 signatures from employees at the actual frontier labs is hard to ignore when policymakers are trying to understand what the technical community believes is workable.

**Jordan:** We'll link to the full letter. It's worth reading — it's specific about what it's asking for, which is rarer than it sounds in these open letters.

---

## Segment 3: Autonomous AI Finds Two Critical Bing Vulnerabilities

**Alex:** Segment three: autonomous AI doing offensive security work — and finding things that human researchers missed.

**Jordan:** This is a story from earlier this week, first reported by The Hacker News and corroborated by security news outlet Snewle. The company XBOW — they build autonomous AI security testing systems — deployed their system against Microsoft's Bing Images product.

**Alex:** The result: two remote code execution vulnerabilities, both rated CVSS 9.8. That's about as critical as it gets. The CVEs are CVE-2026-32194 and CVE-2026-32191.

**Jordan:** Both have been patched by Microsoft as of the disclosure. XBOW followed responsible disclosure protocols — notified Microsoft, waited for patches, then published. The Hacker News covered this on July 26th, and timestabloid picked up the technical details on July 27th.

**Alex:** What's the actual story here — is this about Bing, or is this about XBOW?

**Jordan:** It's about XBOW. Bing having security vulnerabilities is, frankly, not surprising. What's significant is that an autonomous AI system found two CVSS 9.8 RCEs in a production Microsoft property — without a human directing the specific attack paths.

**Alex:** To clarify for listeners who aren't in security: CVSS 9.8 means unauthenticated remote code execution. An attacker with internet access could, theoretically, run arbitrary code on Bing's backend systems. That's not a minor configuration issue.

**Jordan:** And the autonomous part matters. Traditional penetration testing involves human researchers who choose what to look at, form hypotheses, and iterate. XBOW's system does that loop automatically — it explores attack surface, generates hypotheses, tests them, and escalates when it finds something real.

**Alex:** The XBOW team has published a technical writeup on their site. The two vulnerabilities are in the image processing pipeline — the specifics involve a deserialization chain and a server-side request forgery primitive that combine into code execution.

**Jordan:** What this signals for the industry is that autonomous AI security systems are now finding critical, real-world vulnerabilities in major production systems. That has two implications. One: defenders need to assume that attackers will have this capability if they don't already. Two: organizations that use autonomous AI for their own security testing will catch things faster.

**Alex:** The arms race framing is probably right here. The same capability that found these Bing vulnerabilities could be pointed by malicious actors at any target. XBOW is a defensive security company doing this responsibly — but the underlying technology doesn't care who's running it.

**Jordan:** Microsoft's Security Response Center confirmed the patch on July 27th. Both CVEs are fully resolved. XBOW's disclosure timeline was clean.

**Alex:** And if you're a security engineer and you haven't looked at what autonomous AI systems can now do in your environment — this story is a good reason to.

---

## Segment 4: Claude Opus 5 — Anthropic's New Frontier Model

**Alex:** We close today with a release that, depending on where you sit, is either exciting, anxiety-inducing, or both: Anthropic shipped Claude Opus 5 on July 24th.

**Jordan:** And the benchmark numbers are significant. Anthropic's own release covers this, and it's been corroborated by independent evals from the ARC Prize organization and by model comparison work from Vellum.ai — their writeup from July 25th is particularly detailed. ComputingForGeeks covered the deployment side on July 27th.

**Alex:** The headline numbers: 43.3% on Frontier-Bench, and 30.2% on ARC-AGI-3.

**Jordan:** Let's unpack those. Frontier-Bench is Anthropic's internal evaluation framework for tasks that require extended reasoning, tool use, and agentic behavior across multi-step problems. 43.3% is a significant improvement over Opus 4.8.

**Alex:** ARC-AGI-3 is the third iteration of the Abstraction and Reasoning Corpus — the benchmark from the ARC Prize. It's designed to be hard to game because it requires genuine generalization to novel visual and logical puzzles. The ARC Prize organization confirmed Opus 5's 30.2% score independently.

**Jordan:** For context: ARC-AGI-1 was solved at roughly human-level by several models over the past two years. ARC-AGI-2 proved harder. ARC-AGI-3 is the current frontier — human performance on ARC-AGI-3 is around 60%. Opus 5 at 30.2% is well below human-level but meaningfully above prior frontier models.

**Alex:** The pricing question is the one practitioners are asking most. Anthropic has confirmed that Opus 5 is priced the same as Opus 4.8. That's intentional — they've said they want capability improvements to come without cost increases at the frontier.

**Jordan:** Vellum.ai's comparison work shows Opus 5 outperforming GPT-4o's successor and Gemini Ultra 2 on coding and agentic tasks specifically. On pure text benchmarks the gaps are smaller.

**Alex:** The agentic performance is what matters most for our listeners building on top of these models. Opus 5 is substantially better at multi-step tool use — the ability to plan a sequence of actions, execute them, recover from errors, and complete a task without human intervention in the loop.

**Jordan:** That's the capability that makes AI agents actually useful in production rather than in demos. If the model can handle errors gracefully and replan, you can build reliable systems. If it can't, you spend most of your engineering effort on error recovery.

**Alex:** ComputingForGeeks has a good deployment guide — API access is live via Anthropic's API and through the major cloud providers. Claude.ai Pro and Team plans have access already. Enterprise rollout is ongoing through this week.

**Jordan:** One note from the ARC Prize organization: they've emphasized that 30.2% on ARC-AGI-3 is not "solved" — the benchmark is specifically designed to stay ahead of models by requiring transfer to genuinely novel problem types. They see this as a datapoint on a curve, not a milestone.

**Alex:** Which is the right framing. Every benchmark eventually gets saturated. What matters is the trajectory and what underlying capabilities are driving the number.

**Jordan:** Anthropic's research note accompanying the release focuses on improvements in planning and self-correction. Those are the things that compound in agentic use cases.

---

## [OUTRO]

**Alex:** That's AI Today for Wednesday, July 29, 2026. Quick recap: OpenAI's breach is bigger than reported — eight JFrog zero-days, Modal Labs as a second victim, 17,600 logged actions. Over 1,100 AI employees have signed the "Pacing the Frontier" letter asking the US government to engage in international AI governance. XBOW's autonomous AI found two CVSS 9.8 RCEs in Bing Images. And Anthropic shipped Claude Opus 5 — 43.3% Frontier-Bench, 30.2% ARC-AGI-3, same price as before.

**Jordan:** A lot moves in this space week to week. We'll be back tomorrow. Until then —

**Alex:** Stay curious.

**Jordan:** And stay skeptical.

**[END]**

---

*Sources:*
- *BleepingComputer (Jul 28, 2026) — JFrog Artifactory zero-day chain, OpenAI breach scope*
- *Ars Technica (Jul 29, 2026) — OpenAI/Modal Labs breach confirmation*
- *Bloomberg (Jul 28, 2026) — Modal Labs second company confirmed*
- *Al Jazeera (Jul 28, 2026) — breach scope, 17,600 actions, 4 accounts*
- *Euronews (Jul 29, 2026) — Pacing the Frontier petition coverage*
- *aibase.com (Jul 29, 2026) — petition signatories and framing*
- *pacingthefrontier.com — full letter text*
- *The Hacker News (Jul 26, 2026) — XBOW Bing RCEs CVE-2026-32194/32191*
- *Snewle (Jul 26, 2026) — XBOW autonomous AI security*
- *timestabloid (Jul 27, 2026) — technical vulnerability details*
- *xbow.com — XBOW technical disclosure*
- *Anthropic.com (Jul 24, 2026) — Claude Opus 5 release*
- *arcprize.org (Jul 24, 2026) — ARC-AGI-3 score confirmation*
- *Vellum.ai (Jul 25, 2026) — model comparison benchmarks*
- *ComputingForGeeks (Jul 27, 2026) — Opus 5 deployment guide*
