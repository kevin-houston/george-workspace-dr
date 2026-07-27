# AI Today — Monday, July 27, 2026

**Runtime target:** ~18 minutes
**Hosts:** Alex and Jordan

---

## INTRO

**Alex:** Good morning and welcome to AI Today. It's Monday, July 27, 2026. I'm Alex.

**Jordan:** And I'm Jordan. Monday after a busy AI week — and we've got four stories this morning that are all genuinely practitioner-relevant. Not just model-release noise. Actual things that change how you build and operate AI systems.

**Alex:** We've got the biggest open-source weight drop of the year happening literally today, physical AI landing on edge hardware from NVIDIA, the DeepSeek price war taking a surprise turn, and a red teamer who just claimed to have broken every major AI product at once.

**Jordan:** Let's get into it.

---

## SEGMENT 1: Kimi K3 Open Weights Land Today — The Frontier Goes Open-Source

**Alex:** We start with something that was scheduled for today specifically. Moonshot AI committed weeks ago to releasing the full weights for Kimi K3 by July 27th. And that's today.

**Jordan:** So let's set the context. Kimi K3 went live as an API and in the Kimi apps on July 16th. At that point, you could call it, use it, build on it — but you couldn't download and self-host the model. That changes today, when Moonshot publishes the full checkpoint.

**Alex:** And the numbers are staggering. K3 is a 2.8-trillion-parameter Mixture-of-Experts model. That's the full parameter count. In practice, because it's MoE architecture, the model activates only a portion of those experts per inference step — but 2.8 trillion is what's in the checkpoint. According to Amplifi Labs' analysis published three days ago, the weights come in at roughly 1.4 terabytes in four-bit precision.

**Jordan:** Right. This is not something you spin up on a consumer GPU. You need distributed inference infrastructure. But here's the thing: if you have that infrastructure, or you can rent it on a cloud provider — multiple of which reportedly had day-zero hosting ready — the license is what really matters for builders.

**Alex:** And the license is Modified MIT. That's a very permissive open arrangement: commercial use, fine-tuning, derivatives — all permitted. According to Amplifi Labs and the Kimi AI Rankings tracker, both confirmed this separately.

**Jordan:** The performance case is also strong. The Artificial Analysis Intelligence Index and the AI Rankings tracker both place K3 in the global top four — behind Claude Fable 5 and GPT-5.6 Sol in most composite benchmarks, but ahead of other frontier contenders. Wikipedia's Kimi article, updated three days ago, notes that on Arena.ai's front-end web development benchmark specifically, K3 ranked first — beating both Fable 5 and GPT-5.6 Sol on that task.

**Alex:** That's a meaningful benchmark to win. Front-end web development is a high-usage agentic task. Real practitioners care about that.

**Jordan:** Moonshot's own tech blog describes K3 as having "strong long-horizon coding performance" — the ability to sustain extended engineering sessions, navigate large repositories, and orchestrate terminal tools with minimal human supervision. That's a very specific description of the kind of agentic coding use case that's growing fast.

**Alex:** There's also a geopolitical dimension that a lot of observers are noting. Moonshot AI built K3 under U.S. export restrictions — they don't have access to the highest-tier Nvidia compute. According to the AI Rankings tracker, the fact that a model trained under those hardware constraints is competing at the frontier says something real about the pace of Chinese AI development.

**Jordan:** For developers making tooling decisions right now: this is the moment where "open-source frontier model" stops being a contradiction in terms. If K3's benchmark numbers hold under community scrutiny over the next couple weeks — which we'll be watching — it fundamentally changes the self-hosting calculus.

**Alex:** The checkpoint should appear on Hugging Face today. Given Moonshot delivered the K2 weights on schedule when that was a similar wait-and-see situation, most observers expect this to land on time.

---

## SEGMENT 2: NVIDIA Cosmos 3 Edge Brings Physical AI to Jetson Hardware

**Alex:** Story two takes us from language models to the physical world. NVIDIA presented 22 technical breakthroughs at SIGGRAPH 2026 last week, but the one that caught our attention for practitioners is Cosmos 3 Edge.

**Jordan:** Some background: the Cosmos family is NVIDIA's set of open world models. These are not chatbots. They're models that understand physical environments — how scenes evolve, how objects interact, what physical actions mean in three-dimensional space. They're built for embodied AI: robots, autonomous systems, simulation.

**Alex:** Cosmos 3 Edge is a 4-billion-parameter model in that family, designed to run locally on NVIDIA Jetson hardware. Jetson is NVIDIA's line of edge computing boards — the kind you'd embed in a robot, a drone, a factory quality-inspection system, or an autonomous vehicle platform. Not server-class GPUs. Actual embedded hardware.

**Jordan:** The key announcement here, confirmed by the NVIDIA engineer who posted the Hugging Face release, is what this single model does in one package. To quote that post: it connects "scene understanding, future prediction, simulation, and robot action generation in one compact model." Previously you'd typically need separate systems for each of those tasks — or you'd need to punt the inference to a cloud data center.

**Alex:** And that cloud dependency is the thing that kills real-time physical applications. If a robot has to ping a remote server to decide how to navigate around a moving obstacle, you've introduced latency that makes operation impractical in dynamic environments. Running the model locally changes that. This is what "edge AI" has been promising for years — and Cosmos 3 Edge is a concrete delivery of it.

**Jordan:** Humanoid robotics technology coverage cited Japan's industrial robotics community specifically building on this model, noting that "physical AI is bringing intelligence into machines" — their quote. When Japan's robotics industry is explicitly naming your model as the infrastructure layer, that's a signal about real-world adoption direction.

**Alex:** The model is open — available on Hugging Face as of the SIGGRAPH announcement. According to NVIDIA's developer forum recap for the conference, the Cosmos 3 Edge release was one of the headline items, alongside a new Agent Toolkit for Omniverse that adds AI agent capabilities to simulation environment building.

**Jordan:** SIGGRAPH is historically a graphics and interactive techniques conference, but in 2026 it has become a venue where physical AI and rendering pipelines converge. The idea that you simulate an environment, train an agent in that simulation, and then deploy the agent on edge hardware using a world model for real-time reasoning — that whole stack is starting to close up into something you can actually ship.

**Alex:** Wccftech confirmed 22 total research breakthroughs from NVIDIA at the conference. The synthetic video detection tool for newsrooms was also notable from a media integrity standpoint — but Cosmos 3 Edge is the one with the clearest path to developer adoption.

**Jordan:** Four-billion parameters is small enough to run locally on capable edge devices. The open weights mean you can fine-tune for specific robotic tasks. And the scope — one model for scene understanding, prediction, simulation, and action generation — is what makes it architecturally interesting, not just the size.

---

## SEGMENT 3: DeepSeek V4 Goes Stable and Reverses the Price War

**Alex:** Story three is about money, strategy, and a pricing move that caught a lot of developers off guard.

**Jordan:** So the short version: DeepSeek was the company that fired the opening shot in the AI API price war. Cheap models, low inference costs, competitive performance — it forced other providers to cut prices and justify their pricing tiers. DeepSeek was the aggressor.

**Alex:** Past tense, as of July 24th.

**Jordan:** On July 24th, DeepSeek moved V4 from preview to general availability. And when the model went stable, two things happened simultaneously: they retired the legacy API aliases developers had been using, and they posted new pricing that includes peak-hour surcharges.

**Alex:** According to AITrendyReview's analysis, V4-Pro is now priced at $0.435 per million input tokens and $0.87 per million output tokens — plus time-of-day variation at peak demand. Spoon AI's July 24th coverage cited the South China Morning Post saying explicitly: "After triggering a price war, DeepSeek reverses course with surcharge on peak-hour API use."

**Jordan:** It's still dramatically cheaper than the closed-source alternatives. Something like 34 times cheaper than GPT-5.6 by some comparisons. But the direction of the move is what matters. And in the API business, direction matters a lot — because it tells you where the floor is.

**Alex:** This is a pattern with some cloud services. Low prices to drive adoption and create switching costs — integrations, tooling, workflows built around your endpoint format — and then price rationalization once you have the user base.

**Jordan:** For developers who are running DeepSeek integrations in production, there are two concrete action items. First: the legacy endpoint names — things like deepseek-v3 — are gone. You need to update to the canonical deepseek-v4-pro or deepseek-v4-flash endpoint names. According to DeepSeek's official API changelog, both models support both OpenAI ChatCompletions format and the Anthropic-compatible interface, which is useful if you're building multi-provider systems.

**Alex:** Second: you now have time-of-day pricing to factor into your cost models for high-volume production workloads. That's a new operational consideration that didn't exist a week ago. If your traffic is bursty and coincides with peak hours, your costs look different than they did.

**Jordan:** On the self-hosting side: V4-Pro and V4-Flash both have weights on Hugging Face under MIT license. The technical report is in the V4-Pro repo. If peak-hour pricing is a concern, self-hosting remains an option for teams with the infrastructure — though at the model's scale, that's not trivial.

**Alex:** The macro takeaway here might be that "race to zero" was always going to hit a wall. Inference at scale has real costs. DeepSeek ran the experiment, built the user base, and is now moving toward a more sustainable cost structure. Whether other providers read this as permission to stop cutting, or whether someone else undercuts to take market share — that's the dynamic worth watching.

---

## SEGMENT 4: Red Teamer Claims Universal Jailbreak Across Every Major AI Model

**Jordan:** Story four is a security story, and we want to be careful about what's claimed versus what's independently verified — because those are not the same thing here.

**Alex:** On July 25th — two days ago — a well-known AI red teamer called Pliny the Liberator publicly claimed to have developed a universal jailbreak that works against the leading large language models. Specifically: GPT-5.6 Sol, Claude Opus 5, and Fable.

**Jordan:** That's a striking claim, and "universal" is doing a lot of work in that sentence. The usual challenge with jailbreaks is that they're model-specific — what bypasses one model's safety training typically fails on another, because the training processes are different. A jailbreak that allegedly spans multiple frontier models from multiple organizations with different safety approaches is, if true, significant.

**Alex:** The claim was covered by Overcentral and InfoSec Bulletin on July 25th, and Cybersecurity News the same day. All three confirmed the broad claim. The specific method has not been publicly disclosed — Pliny has a pattern of partial disclosure, but it's not a formal CVE-style process.

**Jordan:** Xenospectrum did a verification analysis and found that the reproduction conditions needed to prove universality — their words — "remain unclear." They're tracking it as a credible claim that hasn't been independently reproduced at the level of rigor the "universal" framing would require.

**Alex:** There's also useful context from OpenAI's side. According to Remio AI's coverage, OpenAI used an automated red-teaming system called GPT-Red to harden GPT-5.6 — it attacked and broke essentially every internal model before 5.6, and the results of those attacks were incorporated into 5.6's training. So the claim that a single technique now bypasses that specifically hardened model, plus Anthropic's and Fable's separate stacks, is either a genuine systematic weakness or it requires careful interpretation of what "works" and "universal" mean in practice.

**Jordan:** All three companies presumably received some form of private notice before the public claim went out. Whether they've validated it internally, whether they're rolling out mitigations, whether they push back on the framing — we don't know yet.

**Alex:** For practitioners, the most durable takeaway from this kind of story — regardless of how this specific claim resolves — is that safety guardrails should not be your only line of defense for sensitive applications. Input filtering, output monitoring, sandboxed execution environments, rate limiting on unusual usage patterns: these matter independently of what the base model refuses by default.

**Jordan:** Jailbreaks exist. Better jailbreaks emerge. The defense architecture needs to assume that and build accordingly — not assume the model is the complete safety layer.

**Alex:** We'll follow this as the companies respond and as independent researchers attempt reproduction. If this firms up into a confirmed finding, the implications for enterprise AI product security are significant and we'll cover it in depth.

---

## OUTRO

**Alex:** That's our Monday. Four stories: Kimi K3's 2.8-trillion-parameter open weights landing today under a permissive MIT license, NVIDIA Cosmos 3 Edge bringing physical AI reasoning to Jetson edge hardware, DeepSeek V4 going stable with peak-hour surge pricing after triggering the industry price war, and Pliny the Liberator's universal jailbreak claim against GPT-5.6, Claude Opus 5, and Fable.

**Jordan:** The thread I keep seeing across these: the frontier is getting more distributed — open weights competing with closed models, edge inference replacing cloud dependencies, pricing pressures reshaping who can afford to build what. And the security surface is expanding as fast as the capability.

**Alex:** More capability, more complexity, more attack surface. That's where we are.

**Jordan:** Thanks for listening to AI Today. Back tomorrow with more.

**Alex:** Have a great Monday.

---

*Approximate word count: ~2,050 words*

**Sources:**
- **Kimi K3 weights**: kimi.com/blog/kimi-k3; amplifilabs.com/post/kimi-k3-the-complete-guide (3 days ago); en.wikipedia.org/wiki/Kimi_(chatbot) (updated 3 days ago); theairankings.com/moonshot (1 week ago)
- **NVIDIA Cosmos 3 Edge / SIGGRAPH 2026**: linkedin.com NVIDIA team post; humanoidroboticstechnology.com; forums.developer.nvidia.com/t/icym-nvidia-announcements-at-siggraph-2026; wccftech.com/nvidia-graphics-research-siggraph (6 days ago)
- **DeepSeek V4 stable / surge pricing**: aitrendyreview.com/deepseek-v4-vs-gpt-5-6-pricing-worth-it; spoonai.me/posts/2026-07-24-deepseek-v4-stable-release (both July 24)
- **Jailbreak claim**: overcentral.com/en/pliny-liberator-universal-jailbreak; infosecbulletin.com; cybersecuritynews.com/jailbreak-on-top-ai-models; xenospectrum.com/en/universal-jailbreak-claim-verification (all July 25, 2026)
