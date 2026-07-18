# AI Today — Saturday, July 18, 2026

**Hosts:** Alex and Jordan  
**Word count target:** 1,800–2,400 words

---

## INTRO

**Alex:** Good morning and welcome to AI Today. I'm Alex.

**Jordan:** And I'm Jordan. It is Saturday, July 18, 2026. We've got a varied mix today — some macro numbers on the open-source AI ecosystem, a meditation on what benchmarks are actually for, a practitioner's field report on porting LLM training to a TPU, and a language-specific TTS system that handles problems no general-purpose model even knows exist.

**Alex:** Let's get into it.

---

## SEGMENT 1: Mozilla's State of Open Source AI — The Numbers Behind the Shift

**Jordan:** We start with the biggest-picture story of the week. Mozilla published V1.0 of their State of Open Source AI report yesterday, and it has the kind of data that puts the last two years in perspective. Some of these numbers surprised even the people who compiled it.

**Alex:** Let's go through the key ones. The first is the capability gap between open-weight and closed models, measured by Chatbot Arena over the last two and a half years. In January 2024, the gap was 8.04 points — open models were meaningfully behind. By August 2024, that had collapsed to 0.5 points. In February 2025, DeepSeek-R1 briefly matched the top US model outright. Then the gap reopened to 3.3 points by March 2026 as closed reasoning models pulled ahead.

**Jordan:** So the current state is: 3.3% average gap, but that average conceals a lot. The report is specific about where the gap is and isn't. Open models are at or near parity on coding, instruction-following, and general knowledge. The gap concentrates in reasoning, long-context retrieval, and agentic tasks.

**Alex:** Which means for the majority of production workloads, the gap is negligible. The report backs that up with a statistic that jumped out at me: a majority of tokens routed through OpenRouter now come from open-weight models. That's a shift from roughly a third at the end of 2025 to majority by mid-2026. And the five highest-volume models on OpenRouter's trailing-month leaderboard are all open weights — DeepSeek V4 Flash leading at 18.4 trillion tokens routed, followed by MiMo-V2.5 from Xiaomi, Hy3 preview from Tencent, MiniMax M3, and something called Owl Alpha from an undisclosed origin.

**Jordan:** That list is dominated by Chinese labs, and the token volumes are staggering. The first closed model on the leaderboard is Anthropic's Claude Sonnet series, which comes in after that open top-five.

**Alex:** The third major finding is inference cost. GPT-4-class inference has fallen 50 times in 36 months — from $20 per million tokens in late 2022 to $0.40 today. The report cites Stanford HAI, Epoch AI, and an MIT study that each measure this differently, so the exact multiplier varies, but the directionality is consistent across all three sources.

**Jordan:** What the report uses all of this to argue is that the frontier isn't where most value gets created. Their framing: commodity inputs don't hold pricing power. Value moves up to the agentic harness — the systems built on top of models, not the models themselves. The CEO letter from Raffi Krikorian draws the comparison to Mozilla's own history: Netscape tried to own the browser, open source competed, open won, and the value migrated to what you built on top of it.

**Alex:** The report also leads with a set of vignettes that aren't statistics but are worth hearing. A Māori broadcaster training speech models for te reo on a license that keeps the data with its people. PwC fine-tuning an open model on finance language and running it for hundreds of clients on their own hardware, no per-token meter. Researchers building a medical model with the Red Cross tuned to humanitarian guidelines. Farmers in East Africa diagnosing cassava disease with a model that runs offline on a phone in fields where there's no cloud connectivity.

**Jordan:** Those aren't hypothetical use cases. Those are the report's opening paragraphs as concrete examples of what open weights actually enable that proprietary APIs can't. The full report is downloadable from stateofopensource.ai.

---

## SEGMENT 2: Kimi K3 and What the Pelican Benchmark Is Actually Good For

**Alex:** Story two. Yesterday we covered Kimi K3's announcement. Today we have Simon Willison's analysis — his post from simonwillison.net, which picked up 348 points on Hacker News. Willison is one of the most reliable practitioner voices in this space, and his angle on Kimi K3 is less about the architecture and more about what running a single informal test can actually tell you.

**Jordan:** His test is the "pelican benchmark." For the last 21 months, whenever a new model drops, Willison runs the same prompt: Generate an SVG of a pelican riding a bicycle. It sounds absurd and it started as a joke — his point was how hard it is to compare models. But for the first year or so, it turned out to have a surprising correlation to actual model quality. Better models made better pelicans.

**Alex:** That correlation has weakened significantly. Willison notes that GPT-5.6 Sol and Claude Fable 5 produce pelicans that are outclassed by GLM-5.2 — and he's clear that GLM-5.2 is not a Fable-class model. The pelican has become somewhat detached from overall capability.

**Jordan:** So what's it still good for? Willison makes three points. First: it's a forcing function for actually running the model. If he shows you a pelican, that means he got through the API or ran the weights. Second: even a single prompt can reveal interesting model characteristics. His Kimi K3 pelican, for example, cost 25 cents — 95 input tokens but 16,658 output tokens, of which 13,241 were reasoning tokens. That's an enormous amount of internal deliberation for drawing a bird.

**Alex:** That ratio tells you something real about how the model allocates compute. It's spending about 80% of its output budget on reasoning before it says anything. Whether that's well-calibrated for a simple visual task is a legitimate question.

**Jordan:** Third — and this is the critical point Willison makes — the pelican doesn't test the thing that matters most right now: agentic tool calling and reliable operation as conversations grow long. If you want to understand what a model is capable of in 2026, you need to test it on multi-step tasks with tools, not SVG generation.

**Alex:** He also notes that Kimi K3 has taken the top spot on Arena.ai's Frontend Code arena, surpassing Claude Fable 5. That's a specific capability leaderboard worth watching. On coding tasks, Kimi K3 is currently the strongest available model.

**Jordan:** The pricing is also notable. Kimi K3 comes in at $3 per million input tokens and $15 per million output tokens — same as Anthropic's Claude Sonnet tier, and the most expensive model ever released by a Chinese AI lab. Their earlier model, Kimi K2.6, was $0.95 input and $4 output. The 2.8 trillion parameter scale is also more than twice K2's size.

**Alex:** Full weights still releasing July 27. That's the date to watch if you want to run it or fine-tune it.

---

## SEGMENT 3: Porting Nanochat to a TPU — A Full Report on What Carries and What Breaks

**Jordan:** Story three is a detailed field report that got much less traffic than it deserves — 37 points on Hacker News, but it's dense with practical information for anyone doing ML training at the infrastructure layer.

**Alex:** The project is nanochat-jax. Karpathy's nanochat is a full-stack LLM training repository — tokenizer training, pretraining, supervised fine-tuning, and reinforcement learning in a single codebase. The reason people know it is the "$100 speedrun" benchmark: four hours on an 8×H100 node, about $100 in compute, and you have a working chatbot. The base model stop is cheaper — two hours and $48.

**Jordan:** The author ported this to JAX and ran it on a Google TPU v6e-8 slice — that's eight chips on a single host. The v6e is notable because its matrix unit grew from 128×128 to 256×256 compared to prior TPU generations, doubling compute, while HBM dropped from 95GB per chip on v5p to 32GB. So it's a compute-heavy, memory-lean tradeoff.

**Alex:** The headline result is mixed in an instructive way. Model quality reproduced: the CORE score — which averages accuracy across 22 evaluation tasks, rescaled so random guessing is zero — came out at 0.2695, which lands just above Karpathy's reference band of 0.2512 to 0.2677. So the recipe transfers faithfully. But compute efficiency didn't follow: MFU landed at 24%, compared to 47-48% on H100s.

**Jordan:** That gap is where the technical lessons live. The 256×256 MXU means any tensor dimension that isn't a multiple of 256 gets padded with zeros — wasted flops. The v6e's memory constraint means you're trading off batch size more aggressively than on H100. XLA's compilation model is different enough from PyTorch's JIT that some patterns that "just work" in eager mode need explicit restructuring.

**Alex:** The total cost on spot pricing was $60.80 over 12.19 hours — versus the H100 reference run at around $48 for a shorter time. One preemption happened and was recovered. The on-demand cost would have been roughly $263.

**Jordan:** The practical takeaway here is that JAX's logic layer maps cleanly from PyTorch. The stack — XLA → JAX → Flax — handles the computational primitives fine. What breaks is the implicit assumptions about memory layout, tile sizes, and how compilation overhead lands. If you're considering a TPU migration, this post documents exactly where those friction points are, with measured numbers.

**Alex:** The project is at github.com/tucan9389/nanochat-jax, and the technical writeup is in the repo's discussions tab. It's one of those posts that the ML infrastructure community will keep pointing to as TPU usage grows.

---

## SEGMENT 4: Vāgdhenu — The Sanskrit TTS That Solves Problems General Models Ignore

**Jordan:** Last segment, and it's one of my favorites this week. A researcher at the Indian Institute of Science published Vāgdhenu — that's spelled V-A-G-D-H-E-N-U, with diacritics — a text-to-speech system specifically designed for Sanskrit chanting.

**Alex:** And I want to be clear about what makes this technically interesting, because it's easy to describe it as a novelty when it's actually an example of a real engineering problem that general-purpose TTS systems haven't touched.

**Jordan:** Sanskrit has a set of phonological requirements that standard TTS pipelines break on. The biggest is script handling. If you type Sanskrit in Devanagari — the standard Hindi script — a naive TTS system applies Hindi's schwa-deletion rule, which causes the wrong vowels to be dropped in the wrong places. Sanskrit phonology doesn't follow Hindi schwa-deletion. Vāgdhenu routes Sanskrit input through Kannada orthography internally to avoid triggering the Hindi rule.

**Alex:** Then there are the phones. Sanskrit has three distinct sibilants, a full retroflex consonant series, visarga sandhi with allophonic variants called jihvāmūlīya and upadhmānīya, homorganic anusvāra, and the vocalic ṝ. These are not sounds that appear in English or Hindi TTS training data. The system handles all of them.

**Jordan:** And on top of the phonology, Sanskrit scripture is traditionally chanted, not spoken. The meter matters. A verse in vasantatilakā meter has a specific rhythmic pattern that a verse in anuṣṭubh meter doesn't. Vāgdhenu detects the meter — called vṛtta — automatically from the input text, and selects a matched reference to guide the prosody of the synthesis.

**Alex:** The training data was modest: around five hours of chant recordings, with additional voice-steering fine-tuning. The neural vocoder was further fine-tuned specifically for the chant register, which has different spectral characteristics from ordinary speech.

**Jordan:** The project is fully open: the paper is available as a PDF, code, weights, and dataset are all public. There's a live demo at prathosh.in/vagdhenu where you can paste any Sanskrit verse in any Indian script and get back a chant. The system is also deployed in a production app — Bhāgavata-VāNi — available on iOS, Android, and as a web app.

**Alex:** This is the kind of thing that makes the "AI doesn't serve everyone" criticism concrete and also shows what a path forward looks like. The general-purpose multilingual TTS systems have almost no coverage of Sanskrit chant specifically, because there's no market signal that registers. A researcher who cares about the problem, with access to open tools and a few hours of data, can build something that actually works. Paper, code, weights, dataset — all public.

**Jordan:** And the HN discussion hit 180 points with comments from Sanskrit scholars, computational linguists, and musicians who recognized the specific phonological choices as correct. That's a good sign when domain experts are in the comments saying "this actually handles the hard parts."

---

## OUTRO

**Alex:** That's the show for Saturday, July 18. Mozilla's open-source AI report with the 50x inference cost drop and open weights taking the majority of OpenRouter tokens; Simon Willison on what the pelican benchmark is and isn't good for; a full technical report on porting nanochat to a TPU v6e; and Vāgdhenu, the Sanskrit chanting TTS that handles the phonology general models ignore.

**Jordan:** Links and sources in the show notes. Enjoy the weekend — we'll be back Monday.

**Alex:** Take care.

---

*Script generated: Saturday, July 18, 2026*  
*Sources: stateofopensource.ai (Mozilla, July 2026); simonwillison.net/2026/Jul/16/kimi-k3/; github.com/tucan9389/nanochat-jax/discussions/1 (posted July 15, 2026); prathosh.in/vagdhenu/. HN points verified July 18, 2026 morning: 452, 348, 37, 180.*
