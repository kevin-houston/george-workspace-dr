# Daily AI Insights — May 20, 2026
## Episode Title: "Zero-Days, TPU Clouds, and the Policy U-Turn"
**Runtime**: ~13 minutes | **Hosts**: Alex, Jordan

---

## INTRO

**Alex:** Good morning and welcome to Daily AI Insights. I'm Alex.

**Jordan:** And I'm Jordan. Today is Wednesday, May 20th, 2026, and we've got a packed show.

**Alex:** We do. We're talking about a brand-new $5 billion data center deal that landed yesterday — Google and Blackstone teaming up to build a TPU cloud. We'll dig into what that actually means for developers and enterprises.

**Jordan:** Then we're getting into one of the most genuinely unnerving AI stories of the year. Anthropic's new model, Claude Mythos, has been quietly finding thousands of zero-day vulnerabilities across every major operating system and web browser on the planet — and most of them still aren't patched.

**Alex:** That's right. And that story is directly connected to our third segment, because it may be what finally convinced the Trump administration to reverse course on AI safety oversight.

**Jordan:** And we wrap with the global regulatory picture — the EU just struck a deal to simplify its AI Act rules, and Colorado just repealed and replaced its own AI law. The regulatory ground is shifting fast.

**Alex:** Lots to cover. Let's get into it.

---

## SEGMENT 1: Blackstone + Google — The $5 Billion TPU Cloud

**Jordan:** So, yesterday — May 19th — Blackstone and Google announced a joint venture to create what they're calling a new TPU Cloud. Blackstone is putting in $5 billion in equity capital upfront, and the new company will sell access to Google's Tensor Processing Units as a compute-as-a-service offering, separate from Google Cloud itself.

**Alex:** And the goal is to bring 500 megawatts of data center capacity online by 2027. Just to put that in perspective — a single megawatt powers roughly 750 homes. We're talking about enough electricity to power a mid-sized city, dedicated to AI compute.

**Jordan:** This is the second major deal Blackstone has struck this month. Earlier in May they announced a similar venture with Anthropic. Blackstone manages over $1.3 trillion in assets, and they have clearly decided that the AI infrastructure layer is where they want to be.

**Alex:** Right, and the Google angle here is interesting because this is very explicitly about TPUs — not GPUs. Google has been investing in its own silicon for over a decade, and the new 8th-generation TPUs they announced at Google Cloud Next are extraordinary on paper.

**Jordan:** Walk us through the numbers.

**Alex:** So there are two chips in the new generation — the TPU 8t for training, and the TPU 8i for inference. The training chip packs 9,600 units into a single superpod. That delivers 121 exaflops of compute and two petabytes of shared memory. For context, that's nearly triple the performance of the previous generation.

**Jordan:** Triple. And the inference chip?

**Alex:** 80 percent better performance per dollar compared to the prior generation, with on-chip SRAM tripled to 384 megabytes. They've also introduced something called the Collectives Acceleration Engine, which cuts latency by up to 5x — that's critical for agentic workloads where you have many models talking to each other.

**Jordan:** So Google is making the case that its own silicon is genuinely competitive with NVIDIA's H100s and the new Blackwell chips. And this Blackstone deal is essentially Google saying — here's a new way to access our infrastructure, not just through GCP's standard cloud console.

**Alex:** Exactly. Enterprises can go directly to this new entity for TPU capacity. And the context here is the broader infrastructure arms race — the five largest US cloud and AI companies have committed somewhere between $660 and $700 billion in capital expenditure this year. That's nearly double 2025 levels.

**Jordan:** The numbers are almost incomprehensible. And the grid is struggling. Infrastructure analysts are projecting that 30 to 50 percent of planned 2026 data center capacity will slip to 2028 because of power availability constraints. High-bandwidth memory manufacturers — SK Hynix, Micron, Samsung — have already preallocated their entire 2026 production.

**Alex:** So we're in a world where demand for AI compute is growing faster than the physical infrastructure can be built. The Blackstone-Google deal is one piece of a much larger effort to close that gap.

---

## SEGMENT 2: Claude Mythos and Project Glasswing — AI as a Vulnerability Hunter

**Jordan:** Okay. This story is one I keep coming back to because it sits right at the intersection of capability and risk in a way that's hard to fully process.

**Alex:** Set it up for us.

**Jordan:** So Anthropic has a new frontier model called Claude Mythos — it's not publicly available. What they've done with it is run it through a controlled program called Project Glasswing, where they gave a small set of partner organizations access to use Mythos specifically for finding cybersecurity vulnerabilities in critical software.

**Alex:** And what did it find?

**Jordan:** Thousands of high-severity zero-day vulnerabilities. Across every major operating system, every major web browser. Some of the bugs it found are old — really old. The oldest confirmed so far is a 27-year-old flaw in OpenBSD, which is an operating system specifically known for its security focus. There was also a 16-year-old bug in FFmpeg — a library used by virtually every piece of video software on the planet — that had already been hit by automated testing tools five million times without being caught.

**Alex:** The FFmpeg one is striking because it shows the qualitative difference here. Automated fuzzing tools ran over that bug five million times and missed it. Mythos found it. That's not incremental improvement — that's a different category of capability.

**Jordan:** And Anthropic was transparent about what Mythos can do on the offensive side too. On the CyberGym benchmark — which tests a model's ability to reproduce known vulnerabilities — Mythos scored 83.1 percent accuracy. Claude Opus 4.6, the current production model, scores 66.6 percent. That gap matters.

**Alex:** So the approach they've taken is: we have this capability, it's too dangerous to release openly — over 99 percent of the vulnerabilities found are still unpatched — but we can use it defensively with a controlled set of partners.

**Jordan:** Right. The partner list is significant: Amazon Web Services, Apple, Broadcom, Cisco, CrowdStrike, Google, JPMorganChase, the Linux Foundation, Microsoft, NVIDIA, Palo Alto Networks — plus over 40 additional organizations building critical software infrastructure. Anthropic also put $100 million in model usage credits into the program, plus $4 million in direct donations to open-source security organizations including OpenSSF and the Apache Software Foundation.

**Alex:** The pricing for when Mythos eventually enters broader availability — $25 per million input tokens, $125 per million output tokens. That's expensive by current standards, which probably reflects both the capability level and the risk-based access controls they're building around it.

**Jordan:** Here's the thing that I keep sitting with: Anthropic is essentially saying this model can break into almost anything. They're choosing to use that power to patch software. But the model exists. That capability exists. And that reality is driving the conversation we're about to have in the next segment.

---

## SEGMENT 3: The Trump Administration's AI Oversight U-Turn

**Alex:** So the Fortune headline from May 6th was pretty stark: "Trump administration suddenly embraces AI oversight ideas it once rejected." And the story connects almost directly to what we just described.

**Jordan:** The administration that came in explicitly rolling back Biden-era AI safety regulations is now, reportedly, seriously considering an executive order that would create a government-industry working group to evaluate frontier AI systems before public release. Kevin Hassett, the White House National Economic Council Director, was quoted comparing the concept to the FDA drug approval process — "released to the wild after they've been proven safe."

**Alex:** And the framing around Mythos's cybersecurity capabilities is cited as a major driver. When an AI model can chain together four browser vulnerabilities into a working exploit — in Mythos's case, writing what's described as a complex JIT heap spray that escaped both the renderer and OS sandboxes — that's a national security issue, not just a consumer protection issue.

**Jordan:** Rumman Chowdhury, the CEO of Humane Intelligence, was pretty blunt about the reversal: "This is a 180 for the Trump administration, that has very explicitly been anti-any sort of regulation."

**Alex:** The substance of what's being considered: over 40 AI model evaluations have already been completed, including some unreleased systems. Pre-deployment evaluation agreements with Google, Microsoft, and xAI are reportedly in the works.

**Jordan:** There are real challenges here though. The funding for government-side evaluation capability is reportedly insufficient compared to international peer institutions. And there's a fundamental tension: the evaluations depend on cooperation from the very companies building the models.

**Alex:** Which is the core problem in any self-regulatory or quasi-regulatory framework — you need independent capacity to evaluate what you're overseeing.

**Jordan:** Right. The FDA comparison Hassett made is interesting precisely because the FDA took decades to build the institutional capacity to actually evaluate drugs. AI is moving at a pace where you can't wait decades.

**Alex:** And yet something is clearly better than nothing. The administration was in a position where a competitor could theoretically use a model like Mythos for offensive purposes, and there was no government apparatus to even understand what that meant.

---

## SEGMENT 4: The Global Regulatory Shuffle — EU Simplifies, Colorado Reverses

**Jordan:** Zooming out, the regulatory picture globally this week shows two different trends happening simultaneously.

**Alex:** Walk us through the EU piece first.

**Jordan:** On May 7th, the European Parliament and the Council of the EU reached a provisional agreement to streamline certain rules within the AI Act. This is notable because the high-risk AI provisions of the original AI Act are due to enter into force on August 2nd — literally less than three months from now. Legislators treated this with urgency precisely because that deadline is imminent.

**Alex:** The simplification is focused on the high-risk category — basically making compliance pathways clearer for companies actually trying to comply. The AI Act is a sprawling regulation, and there's been a consistent concern from European businesses that the compliance burden is so complex it advantages large companies that can absorb the legal overhead.

**Jordan:** Meanwhile, on May 14th, Colorado Governor signed Senate Bill 189, which effectively repealed and replaced Colorado's own AI Act — a law that had been considered one of the more aggressive state-level AI regulations in the US. The new version is significantly softer, moving from a prescriptive risk-based framework to a more limited disclosure-focused model.

**Alex:** Colorado's original law was being closely watched as a potential template for other states. Its replacement represents something of a retreat from the earlier position, though supporters of the new law argue that more targeted disclosure requirements are actually more enforceable.

**Jordan:** And sitting over all of this is the White House framework from March — a four-page blueprint pushing for a unified federal approach to AI governance, which would preempt state-level regulation if enacted by Congress. The White House wants six objectives: protecting children, safeguarding against AI harms, respecting IP, preventing censorship, promoting innovation, and building an AI-ready workforce.

**Alex:** So the picture globally is: the EU is trying to make its complex rules simpler and more workable ahead of enforcement. States are moving in multiple directions. The federal government is shifting from anti-regulation to pro-safety-evaluation. And the actual capability of the models is outpacing all of it.

**Jordan:** Which is honestly the story of this entire year. The capabilities are real, the deployments are accelerating, and the governance frameworks are catching up as fast as democratic institutions can move — which is not fast.

---

## OUTRO

**Alex:** Alright, let's land this. Big day in AI news. The Blackstone-Google $5 billion TPU cloud deal is the infrastructure story — a new pathway to specialized compute that puts Google's silicon more directly in competition with NVIDIA at the data center level.

**Jordan:** Claude Mythos finding thousands of unpatched zero-days across critical software is the capability story — and a reminder that the dual-use problem in AI is no longer theoretical.

**Alex:** The Trump administration's move toward pre-deployment evaluation is the governance story — a significant reversal, still early, but the direction of travel has changed.

**Jordan:** And the global regulatory picture is in flux — simplification in Europe, retreat in Colorado, federal preemption push in Washington. Builders and deployers are navigating a patchwork that may or may not consolidate in the next 12 months.

**Alex:** That's Daily AI Insights for Wednesday, May 20th. Thanks for listening. We'll be back tomorrow morning.

**Jordan:** Stay curious.

---

## SOURCES

- [Blackstone Announces Joint Venture with Google to Create New TPU Cloud — Blackstone Press Release](https://www.blackstone.com/news/press/blackstone-announces-joint-venture-with-google-to-create-new-tpu-cloud/)
- [Blackstone to invest $5 billion in AI infrastructure venture with Google, powered by TPU chips — CNBC](https://www.cnbc.com/2026/05/19/blackstone-google-ai-data-center-joint-venture-tpu.html)
- [AI Infrastructure at Google Cloud Next '26 — Google Cloud Blog](https://cloud.google.com/blog/products/compute/ai-infrastructure-at-next26)
- [Project Glasswing: Securing critical software for the AI era — Anthropic](https://www.anthropic.com/glasswing)
- [Anthropic's Claude Mythos Finds Thousands of Zero-Day Flaws Across Major Systems — The Hacker News](https://thehackernews.com/2026/04/anthropics-claude-mythos-finds.html)
- [Could Claude Mythos Actually Destroy the Internet? — The Ringer](https://www.theringer.com/2026/05/06/tech/claude-mythos-anthropic-project-glasswing-cybersecurity-threat-ai)
- [Trump administration suddenly embraces AI oversight ideas it once rejected — Fortune](https://fortune.com/2026/05/06/trump-administration-embraces-ai-oversight-policies-it-once-rejected-anthropic-mythos-caisi/)
- [EU Council and Parliament agree to simplify and streamline AI rules — EU Council](https://www.consilium.europa.eu/en/press/press-releases/2026/05/07/artificial-intelligence-council-and-parliament-agree-to-simplify-and-streamline-rules/)
- [Colorado Legislature Doubles Back on Risk-Based AI Act — National Law Review](https://natlawreview.com/article/colorado-legislature-doubles-back-risk-based-ai-act)
- [White House Releases a National Policy Framework for Artificial Intelligence — Holland & Knight](https://www.hklaw.com/en/insights/publications/2026/03/white-house-releases-a-national-policy-framework-for-artificial)
- [Big Tech is about to spend $700 billion on AI this year — Fortune](https://fortune.com/2026/04/30/big-tech-hyperscalers-will-spend-700-billion-on-ai-infrastructure-this-year-with-no-clear-end-in-sight-eye-on-ai/)
