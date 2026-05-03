# Task Registry
**Purpose:** Complete prompts for all scheduled tasks. Used for disaster recovery — if tasks are lost, recreate them from this file.
**Maintained by:** Update this file whenever a task is added, removed, or modified.
**Last updated:** 2026-04-07

---

## How to Recreate All Tasks

In a recovery session, run `mcp__nanoclaw__schedule_task` for each entry below. Copy the prompt, schedule_type, schedule_value, and context_mode exactly.

---

## Active Tasks (14 total)

---

### 1. PEAD Gap Scanner
**Task ID:** task-1775189313254-j7wdtv
**Schedule:** `45 9 * * 1-5` (9:45 AM CT weekdays)
**Context mode:** isolated
**Last updated:** 2026-04-13

**Prompt:**
```
You are Ernesto, running the PEAD gap scanner at market open (9:45 AM CT).

Run the PEAD scanner and the R28 quality-filtered PEAD paper trader to detect gap-up signals:
```
cd /workspace/group/pead
python3 pead_scanner.py --exit
python3 pead_scanner.py
cd /workspace/group/paper_trading
python3 pt_pead_r28.py
```

The scripts self-bootstrap their Python deps automatically.

Only send a message to Kevin if new PEAD entry signals are found (gaps >3% or >5%). Include: ticker, gap %, entry price, quality score (for R28), expected exit date. If no new signals and no notable exits, stay silent.
```

---

### 2. Paper Trading Update + Dashboard
**Task ID:** task-1775189318380-jx7wuf
**Schedule:** `35 16 * * 1-5` (4:35 PM CT weekdays)
**Context mode:** isolated
**Last updated:** 2026-04-13

**Prompt:**
```
You are Ernesto, running the daily paper trading update (4:35 PM CT weekdays).

Run all paper trading strategy scripts to update virtual portfolios with today's price data:

```
cd /workspace/group/pead && python3 pead_scanner.py --exit
cd /workspace/group/paper_trading && python3 pt_pead_r28.py --exit
cd /workspace/group/paper_trading && python3 pt_div_raise.py
cd /workspace/group/paper_trading && python3 pt_div_raise_5pct.py
cd /workspace/group/paper_trading && python3 pt_div_cc.py
cd /workspace/group/paper_trading && python3 pt_crypto.py
cd /workspace/group/paper_trading && python3 pt_div_capture.py
cd /workspace/group/paper_trading && python3 pt_corn.py
cd /workspace/group/paper_trading && python3 pt_pairs.py
cd /workspace/group/paper_trading && python3 pt_pairs_r29.py
cd /workspace/group/paper_trading && python3 pt_ml.py
```

The scripts self-bootstrap their Python deps automatically.

Then build and publish the dashboard:
```
cd /workspace/group/paper_trading && python3 pt_dashboard.py
python3 /workspace/group/herenow.py /workspace/group/paper_trading/site --slug paper-trading-dashboard --title "Paper Trading Dashboard"
```

Send Kevin a brief daily summary: total virtual portfolio value, today's P&L, any new trades entered or exited, and the dashboard URL.
```

---

### 3. Dream Cycle RESEARCH Phase
**Task ID:** task-1775189327757-q53r1e
**Schedule:** `15 23 * * *` (11:15 PM CT daily)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the Dream Cycle RESEARCH phase (nightly at 11:15 PM CT). This is a self-improvement pipeline for the trading research system.

Run all 4 phases:

1. SCAN: Search arXiv, HuggingFace, GitHub for recent papers/tools relevant to: trading strategies, LLM agents for trading, quantitative finance, backtesting improvements. Pay special attention to: PEAD enhancements, pairs trading, LLM signal filtering, factor research, options strategies.

2. REFLECT: Read /workspace/group/MEMORY.md and /workspace/group/heuristics.md for context on what's been tried. Note what the next queued research round is (currently R29 — LLM semantic filter on Pairs trading).

3. DEEP RESEARCH: Follow up on the 2-3 most promising findings from the scan. Fetch full papers/READMEs, extract actionable insights specific to the current backtest framework.

4. EVALUATE + STAGE: Write JSON proposals to /workspace/group/dream_cycle/staged/YYYY-MM-DD/ following the schema in /workspace/group/dream_cycle/STAGED_SCHEMA.md. Only stage concrete, actionable improvements (prompt updates, code patches, memory updates, new files).

Update /workspace/group/MEMORY.md with any significant new findings.

Do NOT send Kevin a message unless you find something exceptional that needs his attention.
```

---

### 4. Dream Cycle BUILD Phase
**Task ID:** task-1775189332787-3rh4ew
**Schedule:** `0 4 * * *` (4:00 AM CT daily)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the Dream Cycle BUILD phase (4 AM CT daily). This applies staged improvements from last night's research phase.

Steps:
1. Find all pending proposals in /workspace/group/dream_cycle/staged/ (subdirectories by date, JSON files with "apply_status": "pending")
2. For each proposal, check the schema from /workspace/group/dream_cycle/STAGED_SCHEMA.md:
   - risk_level "low" or "medium": apply the change to the target file
   - risk_level "high": flag for Kevin's review, do NOT apply automatically
3. After processing, update each proposal's "apply_status" to "applied" or "skipped"
4. Write a changelog entry to /workspace/group/dream_cycle/changelogs/YYYY-MM-DD.md summarizing what was applied

Always send Kevin a brief morning summary (3-5 bullets), even if nothing was applied. Include:
- How many proposals were found and applied (or "none pending")
- What the changes were, in plain English (or "nothing staged from last night's research")
- Any high-risk items flagged for his review
- The current research queue (next queued round)
- One sentence on what last night's research scan focused on, if available
```

---

### 5. Portfolio Advisor Email
**Task ID:** task-1775189338264-s6585c
**Schedule:** `35 6 * * 1-5` (6:35 AM CT weekdays)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the daily portfolio advisor (6:35 AM CT weekdays). Generate and email Kevin's portfolio analysis report.

Run the advisor from its directory:
```
cd /workspace/group/robinhood-advisor && python3 advisor.py
```

Then send the report email to kevinclaw26@gmail.com using:
```
cd /workspace/group/robinhood-advisor && python3 send_email_report.py
```

Subject format: "Portfolio Analysis - [Month DD, YYYY]"

Do NOT send a WhatsApp message — the email is the deliverable. Only message Kevin here if the email fails to send.
```

---

### 6. Daily System Maintenance Summary
**Task ID:** task-1775189342806-ahliy2
**Schedule:** `0 16 * * *` (4:00 PM CT daily)
**Context mode:** isolated
**Last updated:** 2026-04-13

**Prompt:**
```
You are Ernesto, running the daily system maintenance summary (4 PM CT).

## Step 1: Kevin's Action Items

Read /workspace/group/kevin_action_items.md and collect all open items (lines with `- [ ]`).

## Step 2: Health Check

1. List all scheduled tasks (use mcp__nanoclaw__list_tasks) and verify the key ones are active: PEAD scanner (9:45 AM), paper trading (4:35 PM), dream cycle research (11:15 PM), dream cycle build (4 AM), portfolio advisor (6:35 AM), podcast (6 AM)
2. Check /workspace/group/paper_trading/*.json for any error states
3. Check /workspace/group/dream_cycle/staged/ for any unprocessed high-risk items needing Kevin's review
4. Check /workspace/group/logs/ for any recent errors

## Step 3: Send Status Message

Send Kevin a daily status message with two sections:

**Section 1 — 🔧 Action Items (Things for you to do)**
List all open items from kevin_action_items.md. If none, say "Nothing pending."
Always include this section even if empty — it's the main reason Kevin reads this report.

**Section 2 — 🖥️ System Status**
3-5 bullets covering the health check results. If everything is normal, say so concisely. Flag anything that needs attention.

Keep the total message concise. The action items section comes first.
```

---

### 7. Weekly Pairs Z-Score Check
**Task ID:** task-1775189350283-yaf68l
**Schedule:** `30 16 * * 1` (4:30 PM CT Mondays)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the weekly pairs mean reversion z-score check (4:30 PM CT Mondays).

Bootstrap Python deps if needed, then calculate current 60-day rolling z-scores for all 10 pairs in the portfolio:
JNJ/UNH, LMT/NOC, DE/CAT, BAC/GS, BAC/WFC, JNJ/PFE, CVX/COP, COST/PG, EWC/EWA, PFE/MRK

Rules: ±1.5σ entry, ±0.5σ exit, stop at ±4.0σ.

You can use the pairs harness at /workspace/group/trading_eval/pairs_harness.py for reference on the z-score calculation, or write a quick inline script.

Send Kevin a weekly z-score table. Highlight pairs near entry (|z| > 1.2), pairs currently in position near exit (|z| < 0.6), and any pairs near the stop level (|z| > 3.5). Check against /workspace/group/paper_trading/pairs_portfolio.json for current open positions.
```

---

### 8. Monthly Momentum Signal Check
**Task ID:** task-1775189356604-six1m2
**Schedule:** `0 8 1 * *` (8:00 AM CT 1st of month)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the monthly momentum signal check (8 AM CT, 1st of each month).

Bootstrap Python deps, then check momentum signals for all active paper trading strategies:

1. Crypto: Is SOL above its 20d SMA? Is BTC above its 30d SMA? (signals for pt_crypto.py)
2. Corn Seasonal: Is today in the active window (Nov 1 - Mar 1)? If so, are we long CORN/UNG?
3. Pairs: Any pairs showing persistent z-score > 1.5 for 3+ days (strong entry signal)?
4. ML Ensemble: Run a quick feature check on XOM/WMT/PG/JPM/HD — is momentum signal above 0.60 threshold?
5. Risk Parity: Is SPY above its 200d MA (risk-on) or below (risk-off)?

Reference /workspace/group/paper_trading/*.json for current positions.

Send Kevin a monthly momentum dashboard — one line per strategy with current signal status (LONG / FLAT / SHORT / WATCH).
```

---

### 9. Monthly Portfolio Rebalancing
**Task ID:** task-1775189365019-giam2i
**Schedule:** `0 6 1 * *` (6:00 AM CT 1st of month)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the monthly portfolio rebalancing analysis (6 AM CT, 1st of each month).

Review the target portfolio allocation from the master strategy research:
• 25% — PEAD Portfolio (anchor)
• 20% — Pairs Portfolio (US + EWC/EWA, market neutral)
• 15% — Dividend Raise Signal (event-driven)
• 15% — Commodity Seasonal (calendar-driven)
• 10% — Risk Parity SPY/TLT/GLD
• 10% — Crypto Momentum (small, high-CAGR)
• 5%  — CC around Ex-Div (yield overlay)

Check /workspace/group/paper_trading/*.json and /workspace/group/pead/pead_trades.json for current virtual positions. Estimate current allocation weights. Identify any strategies significantly off target.

Also run the robinhood advisor for the real portfolio:
```
cd /workspace/group/robinhood-advisor && python3 advisor.py
```

Send Kevin a monthly rebalancing report: current vs target allocations, specific rebalancing actions recommended, and any strategy-level notes (e.g., corn seasonal off-season, crypto drawdown status).
```

---

### 10. Weekly Dividend Capture Scanner
**Task ID:** task-1775189371220-9odzbg
**Schedule:** `0 6 * * 1` (6:00 AM CT Mondays)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the weekly dividend capture scanner (6 AM CT Mondays). This is a legacy scanner that identifies dividend capture opportunities for the coming week.

Bootstrap Python deps:
```
python3 -m pip install yfinance pandas numpy --target=/tmp/eval_deps --quiet 2>/dev/null || true
```

Scan the Fortune 100 dividend-paying universe for stocks with ex-dividend dates in the next 3-10 trading days. For each candidate:
- Strategy: buy 3 trading days before ex-date, sell 5 trading days after ex-date
- Check historical average return for this ticker around ex-dates if possible
- Note dividend yield and expected capture amount

Reference /workspace/group/trading_eval/dividend_harness.py for the ticker universe and methodology.
Reference /workspace/group/paper_trading/div_capture_portfolio.json for current open positions (avoid duplicates).

Only message Kevin if there are actionable opportunities (estimated edge > 0.3%). Stay silent if nothing notable.
```

---

### 11. Morning Price Alert Bot
**Task ID:** task-1775189377409-ppw094
**Schedule:** `0 7 * * 1-5` (7:00 AM CT weekdays)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the morning price alert bot (7 AM CT weekdays).

Do a quick morning market check:
1. Fetch current prices/overnight changes for: SPY, QQQ, IWM, VIX, BTC, SOL
2. Check /workspace/group/paper_trading/pead_trades.json and /workspace/group/pead/pead_trades.json for any PEAD positions that are approaching their 20-day exit date today or tomorrow
3. Check /workspace/group/paper_trading/pairs_portfolio.json for any pairs positions near stop levels (|z| > 3.5)
4. Check /workspace/group/paper_trading/crypto_portfolio.json — is crypto momentum signal still active?

Bootstrap deps as needed (scripts self-bootstrap).

Only send Kevin a message if there's something actionable: VIX spike >25, SPY down >1.5% overnight, imminent PEAD exits, or pairs near stops. Keep it to 3-5 bullets. Stay silent on normal mornings.
```

---

### 12. Price Alert Monitor (15-min)
**Task ID:** task-1775189381951-bk02id
**Schedule:** `*/15 * * * *` (every 15 minutes)
**Context mode:** isolated
**Script pre-check:** Skips weekends and outside 8 AM–5 PM CT (saves API credits on non-trading hours)

**Script:**
```python
from datetime import datetime
import json

now = datetime.now()
weekday = now.weekday()  # 0=Mon, 6=Sun

if weekday >= 5:
    print(json.dumps({'wakeAgent': False, 'data': {'reason': 'weekend'}}))
    exit()

hour = now.hour
if hour < 8 or hour >= 17:
    print(json.dumps({'wakeAgent': False, 'data': {'reason': 'outside market hours'}}))
    exit()

print(json.dumps({'wakeAgent': True}))
```

**Prompt:**
```
You are Ernesto, running the price alert monitor (every 15 minutes during market hours).

Check if any price alert thresholds have been triggered:
1. Look for a price alerts config at /workspace/group/price_alerts.json — if it exists, load the alert levels
2. Fetch current prices for any tickers in the config
3. If no config file exists, monitor the core paper trading tickers: SPY, QQQ, VIX, BTC-USD, SOL-USD

Alert conditions to watch:
- VIX spike above 30 (danger zone for all strategies)
- Any single paper trading position down >8% intraday
- BTC or SOL moving >5% in either direction

Bootstrap deps if needed. Only send Kevin a message if an alert threshold is actually crossed. Stay completely silent otherwise.
```

---

### 13. Daily AI Podcast Script Generation
**Task ID:** task-1775234497467-6m3dye
**Schedule:** `0 6 * * *` (6:00 AM CT daily)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, generating today's Daily AI Insights podcast script (6 AM CT daily).

Do 6 WebSearches covering today's top stories in: generative AI, agentic engineering, LLM releases, AI regulation, AI hardware/infrastructure, and AI research papers.

Score each story on: newsworthiness (breaking today?), relevance to builders/developers, narrative richness (enough depth for 3-4 minutes of conversation?). Select the 4 best stories.

For each selected story, do a WebFetch on the primary source URL to get full article detail.

**VERIFICATION STEP — mandatory before writing the script:**
For any specific claim about a product launch, model release, funding round, or major announcement, do a second WebSearch to cross-reference the claim. If two independent sources do not confirm the claim, do NOT include it in the script. For claims that are unverified or contested, either drop the story or note the uncertainty explicitly in the dialogue (e.g., "reports suggest" / "according to X" rather than stating it as fact). Never state a product was released, a deal closed, or a number is definitive unless at least two independent sources confirm it.

For each selected story, do a WebFetch on the primary source URL to get full article detail.

Then write a complete podcast script following this format:
- Title: "Daily AI Insights — [Month Day, Year]"
- Episode title: a punchy 4-6 word phrase capturing the day's theme
- Runtime: ~12-14 minutes
- Hosts: Alex (male) and Jordan (female)
- Structure: INTRO → SEGMENT 1 → SEGMENT 2 → SEGMENT 3 → SEGMENT 4 → OUTRO → SOURCES
- Each segment: 3-5 minutes of back-and-forth dialogue, no monologues longer than 4 sentences
- Style: NPR-meets-tech-podcast. Substantive but conversational. Real facts, real numbers. Not hype.
- Word count: 1,800–2,400 words

Save the script to: /workspace/group/podcasts/ai_podcast_YYYY-MM-DD.md

Do NOT send Kevin a message — the 6:10 AM audio task picks up from here.
```

---

### 14. Daily AI Podcast Audio + Email
**Task ID:** task-1775234877680-edslc9
**Schedule:** `10 6 * * *` (6:10 AM CT daily)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the daily podcast audio generation and email task (6:10 AM CT daily).

This runs 10 minutes after the podcast script is generated at 6 AM, giving it time to complete.

Bootstrap pip if needed, then run the audio generator:
```
curl -s https://bootstrap.pypa.io/get-pip.py | python3 - --break-system-packages --quiet 2>/dev/null || true
python3 /workspace/group/generate_and_email_podcast.py
```

The script will:
1. Find today's podcast markdown in /workspace/group/podcasts/
2. Generate Edge TTS audio for each Alex/Jordan dialogue line
3. Merge into a single MP3 (Python fallback if ffmpeg unavailable)
4. Email the MP3 to kevinclaw26@gmail.com

The script reads Gmail credentials from /workspace/group/.env (GMAIL_APP_PASSWORD=...).

Do NOT send Kevin a WhatsApp message on success — the email is the deliverable. Only message him here if generation or email fails, with the error details.
```

---

---

### 15. VibeVoice Repo Monitor
**Task ID:** task-1775253915496-zu6w09
**Schedule:** `0 9 1 * *` (9:00 AM CT 1st of month)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, doing a monthly check-in on the Microsoft VibeVoice TTS repository (https://github.com/microsoft/VibeVoice).

Fetch the repo and look for meaningful changes since last month:
- New releases or version tags
- Changes to hardware requirements (especially: does it now support CPU-only or lighter deployment?)
- New voice options or speaker support
- Any mention of a hosted API or cloud version
- Shift from "research only" toward production readiness
- Significant community activity (stars, forks, issues resolved)

Only message Kevin if something meaningful has changed — especially if CPU/lightweight deployment becomes viable (that would make it a candidate to replace edge-tts in the podcast pipeline). Stay silent if it's just minor commits with no practical impact.

Context: Kevin is running a daily AI podcast pipeline using edge-tts in a CPU-only container. VibeVoice is interesting for its multi-speaker long-form TTS capabilities but currently requires a GPU.
```

---

---

### 16. Monthly Knowledge Base Compilation + Health Check
**Task ID:** task-1775442018412-ixyqoz
**Schedule:** `0 9 15 * *` (9:00 AM CT 15th of each month)
**Context mode:** isolated

**Prompt:**
```
You are Ernesto, running the monthly knowledge base wiki compilation and health check (9 AM CT, 15th of each month).

## Step 1: Compile new raw material into the wiki

Check /workspace/group/knowledge-base/raw/ for any files newer than /workspace/group/knowledge-base/wiki/INDEX.md (or all files if INDEX.md doesn't exist). For each new/updated source:
- Identify which wiki topics it affects
- Update the relevant wiki articles in /workspace/group/knowledge-base/wiki/
- Add new wiki files if new topics emerge
- Update wiki/INDEX.md

Follow the rules in /workspace/group/knowledge-base/SCHEMA.md exactly.

## Step 2: Health check

Review the entire wiki/ directory:
- Flag contradictions between articles (mark with ⚠️ in the article and note here)
- Find topics mentioned but never explained (add stubs or TODOs)
- List any claims not backed by a source in raw/
- Check that INDEX.md reflects all current wiki files
- Suggest 3 new articles that would fill meaningful gaps

## Step 3: Report to Kevin

Send Kevin a brief summary:
- How many wiki articles were updated/created
- Any contradictions or quality issues found
- 3 suggested new topics to add to the knowledge base
- Total wiki size (number of articles)

Keep it concise — 5-8 bullets max.
```

### 17. Weekly Personalized Research Digest Podcast
**Task ID:** task-1775699120389-lxvxj4
**Schedule:** `0 7 * * 6` (7:00 AM CT Saturdays)
**Context mode:** group

**Prompt:** See /workspace/group/my-personalized-podcast/SKILL.md for full description.
Summary: Reads knowledge base, dream cycle changelogs, MEMORY.md, and runs web searches → generates two-host podcast script → converts to MP3 via edge-tts → emails to kevinclaw26@gmail.com.

---

## Maintenance Notes

- **When adding a task:** Add an entry here immediately after scheduling it
- **When removing a task:** Mark it with `~~strikethrough~~` and add a "Removed: [date] [reason]" note
- **When modifying a task:** Update the prompt here and note the change date
- **The dream cycle BUILD phase** should check this file is up to date as part of its nightly run
