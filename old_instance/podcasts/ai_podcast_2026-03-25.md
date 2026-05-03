# AI Insights — March 25, 2026
## Episode Title: "Shock, Shock!"

## INTRO

**Alex:** Welcome to AI Insights. I'm Alex.

**Jordan:** And I'm Jordan. March 25th, 2026. And I want to start with two words that perfectly capture the mood of this week in AI: "Shock. Shock."

**Alex:** That's an actual quote from Donald Knuth's latest paper. The 87-year-old father of computer science, author of The Art of Computer Programming, one of the most rigorous mathematical minds alive — opened his most recent academic paper with those two words. Because Claude solved a problem he'd been stuck on for weeks.

**Jordan:** And that story, as remarkable as it is, isn't even the most dramatic thing that happened in the last 24 hours. A federal judge looked at the Pentagon's actions against Anthropic yesterday and said — quote — "It looks like an attempt to cripple Anthropic."

**Alex:** We've also got Oracle potentially cutting up to 30,000 employees to fund a 156 billion dollar AI infrastructure deal. And Jensen Huang is telling the world that in ten years, every person at work will have 100 AI agents working alongside them.

**Jordan:** Every story today has that same quality as Knuth's paper. Shock. Something just crossed a threshold nobody was quite ready for.

**Alex:** Let's start with the judge.

---

**Alex:** Yesterday, in San Francisco federal court, U.S. District Judge Rita Lin held the preliminary injunction hearing in the Anthropic versus Pentagon case. And she did not hide her reaction.

**Jordan:** The judge said the government's actions were "troubling" from the start. Then she said — directly — "It looks like an attempt to cripple Anthropic." Her concern was that the designation appeared designed to punish Anthropic for speaking out, not to address any legitimate national security risk.

**Alex:** She asked a pointed question about the scope. If the actual security concern is about how Claude might be used in a weapons system — why ban every federal agency and every contractor doing business with the Pentagon from using Anthropic at all? Why not just stop using Claude yourself?

**Jordan:** Which is the logical question. If you're worried about a vendor's product in a specific context, you stop using it in that context. You don't try to cut off their entire business.

**Alex:** The government's lawyer pushed back. They argued the actions weren't retaliatory — they were based on Anthropic's substantive disagreement over how Claude could be used, not the company's public statements criticizing the contract terms. And they made a somewhat remarkable argument: that Anthropic is a risk because, in the future, the company could theoretically update Claude in a way that endangers national security.

**Jordan:** So the argument is: we're designating them a supply chain risk not for something they've done, but for something they might theoretically do in the future.

**Alex:** Which the judge appeared to find unpersuasive. She's expected to issue a ruling by March 26th — possibly as soon as tomorrow. If she grants the preliminary injunction, the designation gets paused and Anthropic can operate normally while the full case moves through the courts.

**Jordan:** And the stakes are enormous even beyond Anthropic. Defense contractors including Amazon, Microsoft, and Palantir — if the designation stands — have to certify they don't use Claude in any work for the military. That's not just Anthropic's business. That's the whole AI ecosystem's relationship to government contracts.

**Alex:** The judge called the designation "the first time a U.S. company has been publicly named a supply chain risk under a statute designed to protect military systems from foreign sabotage."

**Jordan:** That phrase. "Foreign sabotage." Being applied to an American company that refused two specific contract clauses. The judge noticed.

---

**Alex:** Story two. And this one is going to be one of those moments people look back on. Donald Knuth published a paper this month. He is 87 years old. He wrote the foundational textbooks of computer science. He invented TeX, the typesetting system most scientific papers are written in. He's basically the patron saint of rigorous, careful, human mathematical reasoning.

**Jordan:** And he opened his paper with "Shock! Shock!" Because Anthropic's Claude Opus 4.6 solved a graph theory problem he had been working on for weeks.

**Alex:** What was the problem?

**Jordan:** It comes from a new volume of The Art of Computer Programming. The question involved decomposing the arcs of a directed graph into three Hamiltonian cycles. These are mathematical structures that visit every point in a graph exactly once. Knuth had solved the special case for small values of the parameter, but couldn't find a general construction that worked for all odd numbers.

**Alex:** His colleague Filip Stappers had found solutions experimentally for specific cases from 4 to 16 — but no one could identify the underlying pattern.

**Jordan:** Stappers fed the problem to Claude Opus 4.6. In roughly one hour, over 31 systematic explorations, Claude tried brute-force searches, invented what it called "serpentine patterns," hit dead ends, changed strategy, and eventually found a general construction that works for all odd cases.

**Alex:** The key breakthrough — and this is the remarkable part — Claude independently recognized that the problem had the structure of a Cayley digraph from group theory. That reformulation is what unlocked the general solution. It wasn't just a search, it was a conceptual reframing.

**Jordan:** Knuth wrote the rigorous proof himself. Claude found the construction. Those are different contributions — but finding a pattern that generalizes across infinite cases is genuinely non-trivial.

**Alex:** And Knuth's reaction?

**Jordan:** He ended the paper by writing: "It seems I'll have to revise my opinions about generative AI one of these days." Knuth had historically been skeptical of LLMs — he found them impressive for text but doubted they could do the kind of rigorous mathematical reasoning his work demands. This was a public updating of that position.

**Alex:** The paper has gotten 635,000 views. It's being called one of the most discussed AI-mathematics events in a decade.

**Jordan:** What strikes me is the collaboration model. Knuth posed the problem. Claude explored the structure. Knuth wrote the proof. That's a new kind of human-AI partnership in mathematics — not replacement, not just assistance, but a genuinely novel division of cognitive labor.

**Alex:** And the problem for even values of m? Still open. Claude found one edge of the answer, and there's more to do.

---

**Alex:** Story three. Oracle. And this story is about what happens when the AI buildout outpaces the economics.

**Jordan:** Oracle is reportedly planning to cut between 20,000 and 30,000 employees. That would be one of the largest workforce reductions in the company's history — out of approximately 162,000 people. The goal is to generate 8 to 10 billion dollars in cash flow.

**Alex:** Why do they need the cash?

**Jordan:** Because Oracle is contractually committed to a 156 billion dollar deal with OpenAI requiring 3 million GPUs over five years. The infrastructure to support that is enormously expensive. And here's the part that should make people pay attention: several U.S. banks have scaled back financing for Oracle's AI data center expansion.

**Alex:** The banks got cold feet.

**Jordan:** The banks got cold feet. Lenders have roughly doubled the interest rate premiums they charge Oracle for data center project financing since September 2025. Borrowing costs are now at levels typically reserved for non-investment grade companies. Oracle's stock has fallen 54% from its September high.

**Alex:** Fifty-four percent. And yet Oracle's cloud infrastructure revenue grew 66% year over year. GPU-related infrastructure was up 177%. The underlying business is strong.

**Jordan:** Which tells you something important about the math of this moment. You can have extraordinary revenue growth and still be in a financial crisis if the capital expenditure required to generate that growth outpaces your ability to fund it. Oracle is essentially building a city to rent apartments — the demand is real, but the construction costs are breaking them before the rent checks clear.

**Alex:** And they're getting creative. They're now requiring 40% upfront deposits from new customers — asking clients to help fund the infrastructure before it exists. They're exploring arrangements where customers bring their own chips.

**Jordan:** TD Cowen analysts project the investments could result in negative cash flow for several years, with returns not expected until approximately 2030.

**Alex:** Four years of negative cash flow, betting that the AI buildout continues at this pace and that the returns materialize.

**Jordan:** That's the bet every major cloud provider is making. Microsoft, Google, Amazon, Oracle — they're all spending at scales that assume the demand will be there to justify it. Oracle is just the first one where the financing is visibly straining.

**Alex:** And the 20 to 30 thousand people losing their jobs are funding that bet.

---

**Alex:** Last story. Jensen Huang has a vision for 2036. And it is not subtle.

**Jordan:** At a recent event, Nvidia's CEO projected that by 2036, every person in a knowledge-work environment will have 100 AI agents working alongside them. At Nvidia specifically, that means their current 75,000 human employees working alongside millions of agents.

**Alex:** McKinsey is already at that ratio — 25,000 AI agents working with 40,000 human employees. That's more than half an agent per person today.

**Jordan:** And the number Jensen's projecting — 100 per person — is not a vague aspiration. It's based on the trajectory of how enterprises are deploying agents right now. The cost of running an agent is falling. The capability is rising. And the tasks that agents can reliably handle are expanding every quarter.

**Alex:** What does 100 agents per person actually mean in practice?

**Jordan:** It means different agents for different tasks — some running continuously in the background, some invoked on demand. An agent monitoring your email for action items. An agent pulling competitive intelligence. An agent tracking your code repository for regressions. An agent updating your CRM after every call.

**Alex:** None of which requires general intelligence. All of which is currently done by humans.

**Jordan:** And that's the honest version of Jensen's number. It's not 100 general-purpose AI employees. It's 100 specialized task-automation loops that together do things that used to require people.

**Alex:** The question I keep coming back to is: if a company runs 100 agents per employee — which McKinsey is already approaching — does it eventually need fewer employees?

**Jordan:** Oracle is answering that question right now.

**Alex:** Yeah.

---

**Alex:** Throughline. All four stories. What's the thread?

**Jordan:** I keep coming back to the word "threshold." Every story this week is about something crossing a line that people thought was still in the future.

**Alex:** The legal threshold: the Pentagon designated an American company a supply chain risk using a statute meant for foreign adversaries. A federal judge said it openly looked like punishment. That's a line that nobody expected to cross.

**Jordan:** The intellectual threshold: Claude solved an open problem in mathematics from one of the world's most rigorous thinkers. In an hour. Knuth literally wrote "Shock. Shock." That's a line he thought wouldn't be crossed for years, if ever.

**Alex:** The financial threshold: Oracle is cutting 30,000 people and banks are doubling interest rates, and the reason is that the AI infrastructure buildout has gotten so expensive that standard corporate financing can't keep up. The economics crossed into unsustainable territory.

**Jordan:** And Jensen's vision is saying: the ratio of AI to humans in knowledge work is going to cross 100 to 1. Which, if true, is a demographic threshold for employment.

**Alex:** Knuth started his paper with "Shock. Shock." I think that's the only honest reaction to a week like this one.

**Jordan:** The pace isn't slowing down. The surprises keep coming. The most useful skill right now might just be the willingness to update your priors when the evidence says you were wrong.

**Alex:** Like a 87-year-old who rewrote his opinion about AI at the end of a paper.

**Jordan:** Exactly like that.

**Alex:** Thanks for listening to AI Insights. We'll be back tomorrow.

**Jordan:** Stay curious.

---

## SOURCES

- Anthropic vs. Pentagon hearing — NPR, March 24, 2026; CNBC, March 24, 2026; Axios, March 24, 2026; Fortune, March 24, 2026; Al Jazeera, March 24, 2026
- Judge Rita Lin quotes — NPR, March 24, 2026; CNBC, March 24, 2026
- "First U.S. company designated supply chain risk" framing — AndroidHeadlines; Federal News Network
- Microsoft/Palantir/Amazon contractor impact — CNBC; Federal News Network
- Donald Knuth "Claude's Cycles" paper — Stanford CS faculty page; BoingBoing, March 3, 2026; AI Automation Global; Awesome Agents; Medium/@sarraghribi.eng
- "Shock! Shock!" quote / "revise my opinions" quote — Knuth paper; multiple sources
- 31 explorations, 1 hour, Cayley digraph breakthrough — zenvanriel.com; awesomeagents.ai
- 635,000 views statistic — multiple sources
- Oracle 20,000-30,000 layoffs / $156B OpenAI deal / banks doubling rates — Bloomberg, March 5, 2026; TD Cowen report; CIO Magazine; TechRepublic; Yahoo Finance
- Oracle stock -54%, cloud revenue +66%, GPU infra +177% — Yahoo Finance; CIO
- Oracle negative cash flow until 2030 — TD Cowen analyst estimates
- Jensen Huang 100 agents per person by 2036 — TechStartups, March 24, 2026; Crescendo.ai
- McKinsey 25,000 agents / 40,000 employees — McKinsey internal data; AI Agent Store
