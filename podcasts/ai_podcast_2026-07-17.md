# AI Today — Friday, July 17, 2026

**Hosts:** Alex and Jordan  
**Word count target:** 1,800–2,400 words

---

## INTRO

**Alex:** Good morning and welcome to AI Today. I'm Alex.

**Jordan:** And I'm Jordan. It is Friday, July 17, 2026, and we are wrapping up what has been genuinely a packed week in AI. We've got four stories today that all landed yesterday, and they hit completely different parts of the ecosystem — open weights, local tooling, agentic benchmarks, and platform consolidation.

**Alex:** Four stories from one Thursday. Let's get into it.

---

## SEGMENT 1: Kimi K3 — The World's First Open 3-Trillion-Parameter Model

**Jordan:** We start with the biggest one by points on Hacker News — 1,677 points as of this morning. Moonshot AI, the Chinese lab behind the Kimi product line, announced Kimi K3: a 2.8 trillion parameter model. They're calling it the world's first open model to reach the 3-trillion-class.

**Alex:** And to be clear, it's not live with full weights yet. The blog post says the complete weights drop July 27. But the model is already available through Kimi.com, Kimi Work, Kimi Code, and their API, running with maximum thinking effort by default.

**Jordan:** Right, so it's accessible, but the full open release — the thing that would let the open-source community run and fine-tune it — is ten days out. Which is interesting timing. The announcement comes before the weights, so they're managing the moment a bit.

**Alex:** Let's talk architecture, because this is where it gets genuinely novel. Kimi K3 isn't just a scale-up of K2. They introduced two new architectural pieces: Kimi Delta Attention, which they abbreviate KDA, and something called Attention Residuals. The idea is to improve how information flows across both sequence length — think very long contexts — and model depth, meaning across many layers.

**Jordan:** And this is a Mixture of Experts model, so not all 2.8 trillion parameters are active at once. They're running 16 experts out of 896 per forward pass. That's an extremely sparse activation — less than 2% of total parameters active on any given token. They wrap this in what they call a Stable LatentMoE framework to keep training from destabilizing at that sparsity level.

**Alex:** The headline efficiency claim is 2.5 times better scaling efficiency than Kimi K2. Which means, roughly, they're getting more capability per unit of compute than their previous architecture. That's the core claim behind why going to 2.8 trillion parameters is worth the infrastructure cost.

**Jordan:** Now, how does it actually perform? The blog is careful here. They explicitly say Kimi K3's overall performance still trails the most powerful proprietary models — they name Claude Fable 5 and GPT-5.6 Sol by name. But they say it demonstrates frontier-level performance on their evaluation suite and consistently outperforms other tested models.

**Alex:** So not the top of the leaderboard overall, but competitive in the open-weight category — and given that the open-weight category has historically been a full generation behind proprietary models, this is a meaningful compression of that gap.

**Jordan:** Context window is 1 million tokens, with native vision. They're also including a chart in the blog that shows the open frontier model size over time — and Moonshot AI has held the upper bound of open model sizes for nine of the past twelve months. That's a consistent push at the frontier from a lab that often gets less coverage in English-speaking media than DeepSeek or Qwen.

**Alex:** One practical note: at launch the model runs with max thinking effort by default, and low and high effort modes come later. So right now, if you're using the API, you're getting the full reasoning mode for every query.

**Jordan:** The July 27 weight release is the one to watch. That's when researchers can actually study the architecture, the community can build on it, and GGUF quantizations will start appearing for local runs.

**Alex:** Bottom line for segment one: Kimi K3 is a genuinely novel architecture at frontier scale, and next week the weights land. If you're tracking the open-weights frontier, this is the release of the year so far.

---

## SEGMENT 2: LM Studio Bionic — An AI Agent Built for Local and Open Models

**Alex:** Story two: LM Studio shipped Bionic yesterday, and it's a significant product expansion. LM Studio has been the go-to desktop app for running local models — you download a model, spin it up, get a local API endpoint, done. Bionic is them moving up the stack into full agentic workflows.

**Jordan:** And the framing is specific: this is an AI agent for getting real work done with open models. The emphasis on open models is doing some work here. The pitch isn't "use GPT-4o through us" — it's "use Llama, use Qwen, use Kimi K3 when the weights drop, and keep control of your data and your spend."

**Alex:** The three main work modes they're launching with are coding, research and documents, and voice. Let me take those in turn. For coding, Bionic can work directly in Git codebases — it has access to the file system, understands project structure, and can run commands. Standard agentic coding loop.

**Jordan:** For documents, they're targeting knowledge workers who live in slides and spreadsheets. The demo in the blog shows Bionic generating a presentation from scratch, working with existing docs, and pulling context from multiple files. Think Claude for Documents or Microsoft Copilot in Office, but running on a local or open model.

**Alex:** Voice is the one I didn't expect. They built in offline voice transcription — so you can speak into your computer and have it converted to text without any audio leaving your machine. They're positioning this as a system-wide keyboard shortcut, so you can dictate into any app, not just LM Studio itself.

**Jordan:** And then on the model execution side, you've got three options. Local — fully on your hardware, nothing leaves the machine. LM Link — which connects to another machine on your network running LM Studio. Or LM Studio Secure Cloud — for the largest open-source models that won't run locally, with what they call zero data retention by default.

**Alex:** That zero data retention claim is going to do a lot of work for enterprise users and anyone in regulated industries. The argument is: you can get frontier-level open model performance in the cloud, but none of your prompts or outputs are stored.

**Jordan:** The 264 points and 91 comments on HN suggest practitioners find this genuinely useful rather than just another local AI wrapper. The main discussion thread is full of people asking about specific model compatibility and whether they can point it at their own LLM API endpoint — which tells you the use cases are real.

**Alex:** LM Studio Bionic is available now as a download. If you've been using LM Studio as a local model host and have been managing your own agentic workflows on top of it, this is the native offering that's been missing.

---

## SEGMENT 3: The $100 Music Video Arena — What Agentic Benchmarks Actually Look Like

**Jordan:** Story three is a practitioner experiment that tells you more about the current state of AI agents than most benchmarks do. The team at TryAI built what they're calling a Music Video Arena. The setup: give Claude Fable 5 and GPT-5.6 Sol the same song — Bruno Mars and Mark Ronson's "Uptown Funk" — a hard dollar budget for generation, and six tools, then let each model run autonomously until it produces a complete music video.

**Alex:** The six tools are: a plan tool for reasoning at no cost, web search to research video generation models, a get-budget tool to check remaining spend, generate-image and generate-video which are the only paid tools, and a local shell with ffmpeg and ffprobe available for editing. The model can pick any model on FAL or Replicate and pass its own parameters.

**Jordan:** Four runs total: each model at $25 and $100. And all four finished. All four produced a valid, full-length video with the original audio muxed in. That's actually the first notable result — none of the runs crashed, got stuck, or failed to output a final product. Long-horizon agentic tasks hitting that bar reliably is newer than it sounds.

**Alex:** The differences show up in how the models worked. Both Claude Fable 5 and GPT-5.6 Sol went primarily text-to-video — feed the prompt, get a clip. But only GPT-5.6 Sol at the $25 budget used an image-to-video pipeline, generating stills first and then animating them. And at $100, Sol mixed three different video generation models in a single run. Claude stuck with a more consistent tool strategy across both budget levels.

**Jordan:** The number that most surprised me is the token cost differential. The TryAI team tracked generation spend separately from model inference cost. For the $100 budget runs, Claude Fable 5 spent $48.60 on generation. Sol spent $36.57. So Claude generated more footage. But then Claude's token cost for the run itself — the inference to run the agent — was $17 to $25 extra, which is 30 to 40 percent of the total budget. Sol's inference cost at similar token volumes was three to four dollars.

**Alex:** That's a real tradeoff. Claude Fable 5 is using significantly more tokens per step — likely due to longer thinking, more detailed plans, more careful review of its own footage — but it's generating richer output at the cost of a much higher inference bill.

**Jordan:** They counted distinct clips generated per run across all four: between 46 and 80 clips. Which means every run is making dozens of creative decisions, paying for clips, watching them, and iterating. This is genuinely autonomous multi-step work, not a single API call.

**Alex:** The whole harness is open source at github.com/hershalb/music-video-arena. They give you full run transcripts — every plan, tool call, and command for all four runs. If you want to understand how frontier models actually behave on long-horizon tasks, this is better source material than any academic benchmark.

**Jordan:** The meta-point here is that this style of measurement — a real task, a real budget, logged tool calls, auditable output — is how agentic capability actually gets understood in practice. It's messy and specific, but it's more honest than eval suites built from fixed problems.

---

## SEGMENT 4: NotebookLM Becomes Gemini Notebook — Platform Consolidation at Google Scale

**Alex:** Fourth story, and it's the platform play of the week. Google announced yesterday that NotebookLM is being renamed to Gemini Notebook. Same product. Same core research-assistant use case. New name, and now formally part of the broader Gemini ecosystem.

**Jordan:** NotebookLM launched at Google I/O 2023 as a research tool with a deceptively simple pitch: bring your sources, ask questions, get answers grounded specifically in those sources rather than the model's training data. Three years in, Google says it has 30 million users and over 600,000 organizations using it.

**Alex:** The rename isn't just cosmetic. The product now syncs with the Gemini app and is getting integrated into AI Mode in Google Search — not yet, but "soon" per the blog. So if you're searching and you want to pull something into a notebook for deeper research, that path is coming.

**Jordan:** The feature addition that matters more than the name is the secure cloud computer. Every notebook is getting a cloud compute environment that can write and execute code natively. This is the data analysis unlock — instead of describing what you want to know about a dataset you've uploaded, Gemini Notebook can actually run code against it and show you results grounded in your sources.

**Alex:** Today this is available for Google AI Ultra users and enterprise Workspace customers with expanded access. It rolls out to Pro users on the web over coming weeks.

**Jordan:** The positioning is interesting because it puts Gemini Notebook directly in competition with document-grounded coding environments. If you think about the use case — you have a folder of research papers, financial reports, or internal documents, and you want to run analysis on the data inside them — that's exactly what a lot of people are using Claude Projects and custom GPTs for. Google is now competing with that directly with a product that has 30 million people already using it.

**Alex:** The 314 points on HN with 160 comments is mostly nostalgia for the NotebookLM brand mixed with debate about what the rename signals for Google's product consolidation strategy. But the code execution addition is real and meaningful for power users.

**Jordan:** For researchers, analysts, and anyone doing document-heavy work: if you've been sleeping on NotebookLM because it felt like a novelty, the Gemini Notebook version with code execution is worth another look.

---

## OUTRO

**Alex:** That's the show for Friday. Four stories, all from yesterday: Kimi K3 and the open-weight frontier, LM Studio Bionic and local agentic tooling, the music video arena showing what real agentic benchmarks look like, and Google consolidating its research product under the Gemini umbrella with new code execution capabilities.

**Jordan:** Big week. Weights for Kimi K3 land July 27 — mark your calendar if that matters to your workflow.

**Alex:** Have a great weekend. We'll be back Monday.

**Jordan:** Take care, everyone.

---

*Script generated: Friday, July 17, 2026*  
*Sources: kimi.com/blog/kimi-k3, lmstudio.ai/blog/introducing-lm-studio-bionic, tryai.dev/blog/ai-music-video-arena-claude-vs-gpt-5.6, blog.google (NotebookLM/Gemini Notebook announcement) — all published July 16, 2026. Points from Hacker News front page, July 17, 2026 morning.*
