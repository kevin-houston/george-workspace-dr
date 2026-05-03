# The Intelligence Brief — March 27, 2026
### Daily AI Insights Podcast

---

## INTRO

**Alex:** Welcome back to The Intelligence Brief. I'm Alex, and with me as always is Jordan.

**Jordan:** Hey everyone. So Alex — yesterday we ended the episode with this idea that AI has crossed some kind of infrastructure threshold, that the rules are changing. And today I feel like the universe is just... responding.

**Alex:** Right, because today we have a story that's basically the counterargument to all of it. François Chollet dropped a new benchmark yesterday that made every major AI model look like it's failing first grade.

**Jordan:** While also, simultaneously, GPT-5.4 just crossed the human baseline on autonomous task execution. So we have AI humbled and AI triumphant on the same day.

**Alex:** And underneath both of those, we've got Atlassian announcing it's cutting ten percent of its global workforce — sixteen hundred people — explicitly to make room for AI. And legal AI startup Harvey just closed at an eleven billion dollar valuation.

**Jordan:** It's a lot. Let's go story by story because each of these deserves real attention.

---

**Alex:** ARC-AGI-3. It launched on March 25th, and I want to start with the numbers because they're genuinely shocking. Gemini 3.1 Pro — the current benchmark leader across most tests — scored 0.37%. GPT-5.4 scored 0.26%. Claude Opus 4.6 scored 0.25%. Grok-4.20 scored exactly zero.

**Jordan:** And humans — untrained humans, no special knowledge, just regular people dropped into the thing for the first time — solved one hundred percent of the tasks.

**Alex:** Every single one of the 135 environments. That's not a rounding error. That's a chasm.

**Jordan:** So let's explain what this benchmark actually tests, because it's radically different from anything before it. Previous ARC versions were grid puzzles — you'd look at some examples and infer the transformation rule. Clever, but learnable. ARC-AGI-3 drops you into an interactive video-game-like environment with zero instructions, zero stated goals, zero description of the rules. You have to explore, figure out what you're supposed to do, form a plan, and execute it.

**Alex:** And François Chollet — who created the original ARC benchmark back in 2019 — has been very clear about why this design matters. He said, and I'm quoting: "The G in AGI stands for general. True general intelligence solves new tasks independently, without special human guidance — exactly as ordinary humans do."

**Jordan:** The scoring system is also worth understanding because it's sophisticated. They use something called RHAE — Relative Human Action Efficiency. It doesn't just ask did you solve it, it asks how efficiently. And it uses a squared formula, so a model that needs ten times as many actions as a human doesn't score ten percent — it scores one percent. Brute force is explicitly punished.

**Alex:** There's one number from the paper that really stuck with me. They built a custom scaffolding harness for Claude Opus 4.6 that pushed it to 97.1% on a single familiar environment. Ninety-seven point one percent.

**Jordan:** Right, but then the same model, same scaffolding, dropped to zero percent on an unfamiliar environment. And Chollet's point is exactly that. The scaffolding is solving the task, not the model. The moment you remove the hand-holding, the capability evaporates.

**Alex:** The non-LLM approaches are what really tell the story. Simple reinforcement learning and graph search algorithms scored 12.58% — twelve times better than every frontier language model. A CNN doing structured exploration beat GPT-5.4 by over twelve percentage points.

**Jordan:** Which is the kind of result that should make the whole field stop and think. We've been scaling transformers, refining RLHF, building incredible context windows — and a graph search algorithm is twelve times better at genuine exploration and generalization.

**Alex:** Chollet's foundation is putting up two million dollars in prize money on Kaggle for anyone who can crack it. And as of right now, it's the only unsaturated general agentic intelligence benchmark in existence. Everything else — the labs have already figured out how to score well on.

**Jordan:** So what's the implication? I think it's this: the AI capabilities we've been measuring and celebrating are real, but they're a specific kind of intelligence. Pattern recognition at scale in known domains. What we haven't built is adaptive reasoning in genuinely novel contexts. And that's apparently what intelligence is.

---

**Alex:** And yet — here's the tension — GPT-5.4 just crossed the human baseline on a completely different benchmark, and that result is also real and significant.

**Jordan:** OSWorld-V. Tell me about this one.

**Alex:** OSWorld-V tests something very specific: can an AI autonomously execute multi-step workflows across software environments? Think: "book me a flight, add it to my calendar, draft an email to my team, and attach the itinerary." That whole chain. GPT-5.4 scored 75% on this benchmark. The human baseline is 72.4%.

**Jordan:** So AI is now better than humans at autonomous digital task execution. That's a real milestone.

**Alex:** It is. And the context window is relevant here — GPT-5.4 ships with a one million token context window. So it can hold the entire state of a complex multi-step workflow in working memory and reason across the whole thing simultaneously.

**Jordan:** I want to push on the framing though. OSWorld-V is testing a specific, relatively well-defined domain — computer-based tasks with clear success criteria. It's not testing open-ended judgment or creativity or adaptation. It's testing "can you reliably execute a workflow."

**Alex:** That's fair. And if you put these two benchmarks side by side — ARC-AGI-3 and OSWorld-V — you get a really clear picture of where AI is and isn't. Reliable workflow execution in defined domains: yes, now at or above human level. Adaptive problem-solving in novel environments with no instructions: still basically zero.

**Jordan:** Which maps pretty neatly onto what you'd want to automate versus what you'd want to keep human judgment on. The routine, structured work — maybe AI handles that. The genuinely novel situations — you want a person.

**Alex:** Or at least you want a person supervising. The scary version is when organizations don't appreciate the difference and deploy autonomous AI in situations that look routine but actually aren't.

**Jordan:** The governance problem again.

---

**Alex:** Speaking of organizations making big bets on AI — Atlassian. The Australian enterprise software company, maker of Jira and Confluence — announced this week that it's cutting roughly ten percent of its global workforce. That's about sixteen hundred people.

**Jordan:** And the CEO, Mike Cannon-Brookes, was remarkably direct about the reason. He said AI has "fundamentally changed the mix of skills the company needs." And he's not just laying off one department — he's simultaneously replacing his single CTO with two new AI-focused CTOs.

**Alex:** Which is a structural signal, not just a headcount signal. This isn't "we need to cut costs." This is "the entire technical leadership model for this company is changing."

**Jordan:** What makes Atlassian different from some other high-profile layoffs we've seen is that they're not in financial distress. This is a deliberate transformation. They're redirecting resources toward AI development and enterprise sales.

**Alex:** And Cannon-Brookes framed it in a way that I think is worth sitting with. He didn't say "AI is replacing people." He said the mix of skills has fundamentally changed. Which is a softer framing, but the math is still sixteen hundred people out the door.

**Jordan:** I keep coming back to the ARC-AGI-3 result here, because there's a kind of irony in it. On the same week that we learn AI can't adaptively reason its way through a novel video game environment, a major company is laying off sixteen hundred humans because AI changed what skills they need.

**Alex:** Right. The capabilities that matter for enterprise software workflows — code generation, documentation, customer support automation, ticket triage — those are exactly the structured, well-defined tasks where AI is strong. Not the ARC-AGI-3 tasks. So for Atlassian's purposes, the AI is good enough.

**Jordan:** And that's the reality that a lot of companies are navigating. Not "is AI AGI" — but "is AI good enough for this specific thing we pay people to do?" And the answer is increasingly yes, for a wide swath of knowledge work.

**Alex:** Atlassian is probably not the last. There are going to be more announcements like this. And the pattern — leadership acknowledging AI changed the skill mix, restructuring toward AI-native roles — that's a template other companies are going to follow.

---

**Alex:** One more story, and it's a pure business signal. Harvey — a legal AI startup — just closed a two hundred million dollar funding round led by GIC and Sequoia. Valuation: eleven billion dollars.

**Jordan:** Eleven billion for a legal AI company. Let's put that in context. Harvey is building AI for lawyers — contract analysis, due diligence, research, drafting. The kind of work that junior associates at law firms bill out at three to four hundred dollars an hour.

**Alex:** And Sequoia and GIC are not known for backing moonshots. These are investors who want to see clear revenue traction and a defensible market. So what does this tell us?

**Jordan:** It tells us that professional services — law, accounting, consulting — is seen as the next major vertical for AI. Healthcare AI has already attracted enormous capital. Legal is the next domain with massive inefficiency, clear ROI on automation, and strong willingness to pay from enterprise clients.

**Alex:** The math is compelling. Legal services globally is a trillion-dollar market. Law firms are under constant pressure from clients to reduce billing hours. AI that can do in two minutes what took an associate three hours — that sells itself.

**Jordan:** And the barriers to entry are high enough that Harvey has a real moat. Legal AI needs to be deeply trained on legal documents, case law, regulatory filings. It needs to understand jurisdiction-specific rules. It can't hallucinate citations — the consequences are too real.

**Alex:** That last point is significant. Harvey is competing in a domain where being wrong is expensive. Not expensive the way a bad marketing email is expensive. Expensive the way malpractice is expensive.

**Jordan:** So the technical bar is genuinely high, and if you clear it — and Sequoia thinks Harvey has cleared it — you've got an extraordinary business. Eleven billion dollars says the investors think this is real.

**Alex:** It's also part of a broader story about AI moving from horizontal tools — the ChatGPTs and Claudes of the world, useful for everything, specialized for nothing — to vertical applications with deep domain expertise. Harvey in law. Abridge in medical notes. Runway in video. The vertical plays are where the serious money is going now.

---

**Alex:** Throughline time. What ties ARC-AGI-3, GPT-5.4 on OSWorld-V, Atlassian's layoffs, and Harvey's funding round into a single idea?

**Jordan:** I've been thinking about this. And I think it's the word "sufficient." Not "superintelligent," not "AGI," not even "better than humans" across the board. Just: sufficient.

**Alex:** Say more.

**Jordan:** ARC-AGI-3 proves that frontier AI is not sufficient for genuine novel generalization. Zero point three seven percent. But OSWorld-V proves it is sufficient for autonomous execution of structured workflows. Atlassian decided AI is sufficient to replace a specific set of technical roles. Harvey's investors decided the model is sufficient for legal work with real consequences.

**Alex:** The word "sufficient" shifts everything. Because it's not a binary — AI is or isn't intelligent. It's a question asked domain by domain, task by task. Is this AI sufficient for this job? And the answer is spreading through the economy in real time.

**Jordan:** And Chollet's work is important precisely because it draws a clear line around where sufficient ends. Novel environments. Adaptive reasoning. Situations with no instructions and no examples. That's still entirely human territory.

**Alex:** For now.

**Jordan:** For now. Which is why the two million dollar prize exists.

**Alex:** The question every organization should be asking right now is: which of our tasks are OSWorld-V tasks, and which are ARC-AGI-3 tasks? Because the answer tells you exactly where to invest in AI and where to invest in people.

**Jordan:** And the companies that get that mapping right are going to have an enormous advantage over the ones that either over-automate or under-automate.

**Alex:** That's The Intelligence Brief for March 27th, 2026. Thanks for listening.

**Jordan:** Stay curious.

---

## SOURCES

- ARC-AGI-3 launch announcement — arcprize.org/arc-agi/3
- The Decoder: "ARC-AGI-3 offers $2M to any AI that matches untrained humans, yet every frontier model scores below 1%" — the-decoder.com
- Rundown AI: "ARC-AGI-3 resets the frontier AI scoreboard" — therundown.ai
- Dev.to: "GPT-5, Claude, Gemini All Score Below 1% — ARC AGI 3 Just Broke Every Frontier Model"
- LLM Stats: AI Updates March 2026 — llm-stats.com
- Crescendo AI: Latest AI news and breakthroughs 2026 — crescendo.ai
- FutureTech AI Marketing: March 27, 2026 AI News Roundup — blog.tahababa.com
- White House National Policy Framework for Artificial Intelligence (March 20, 2026) — whitehouse.gov
- Cooley Law: White House AI Regulatory Blueprint analysis — cooley.com
