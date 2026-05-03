# Daily AI Podcast Generator - Setup Guide

## Overview

This system generates daily NotebookLM-style podcast scripts from X.com content about GenAI, Agentic Engineering, and related topics.

## Files Created

1. **daily_ai_podcast_generator.py** - Main script generator
2. **collect_x_content.sh** - Content collection helper
3. **podcasts/** - Output directory for generated scripts

## How It Works

### Phase 1: Content Collection (requires Claude agent)
- Monitors key X.com accounts and hashtags
- Scrapes interesting posts from the last 24 hours
- Topics: GenAI, Agentic AI, LLMs, Autonomous Agents, nanoclaw

### Phase 2: Script Generation
- Creates conversational dialogue between two hosts (Alex & Jordan)
- NotebookLM-style natural discussion format
- Summarizes and explains key developments
- Outputs markdown script file

### Phase 3: Audio Production (optional, requires TTS)
- Use ElevenLabs, OpenAI TTS, or similar
- Convert script to audio
- Distribute as podcast

## Key X.com Sources Monitored

### Companies & Organizations:
- @OpenAI
- @AnthropicAI
- @GoogleDeepMind
- @GoogleAI
- @MetaAI
- @MSFTResearch
- @GroqInc

### Thought Leaders:
- @AlliKMiller
- @RonaldvanLoon
- @andrewng
- @ylecun
- @karpathy
- @sama
- @demishassabis

### Hashtags:
- #GenAI
- #AgenticAI
- #LLM
- #AgenticEngineering
- #nanoclaw
- #AIAgents

## Running Manually

Generate today's podcast script:

```bash
cd /workspace/group
python3 daily_ai_podcast_generator.py
```

Output location: `/workspace/group/podcasts/ai_podcast_YYYY-MM-DD.md`

## Scheduling with Nanoclaw

To run automatically every day at 6 AM:

```javascript
schedule_task({
  prompt: "Generate today's AI podcast script by:\n1. Using agent-browser to search X.com for #GenAI, #AgenticAI, #LLM posts from last 24h\n2. Collect 5-10 most interesting/important posts\n3. Run /workspace/group/daily_ai_podcast_generator.py with collected content\n4. Save output to /workspace/group/podcasts/",
  schedule_type: "cron",
  schedule_value: "0 6 * * *",  // 6 AM daily
  context_mode: "group"
})
```

## Sample Output

See: `/workspace/group/podcasts/ai_podcast_2026-02-23.md`

The script includes:
- **Intro** - Welcome and date
- **Main Content** - 3-5 conversational segments discussing top AI topics
- **Outro** - Closing thoughts and call to action
- **Metadata** - Generation timestamp and sources

## Next Steps for Full Audio Production

### Option 1: ElevenLabs
```bash
# Install ElevenLabs SDK
pip install elevenlabs

# Convert script to audio
python convert_to_audio.py --script podcasts/ai_podcast_2026-02-23.md --voice1 adam --voice2 rachel
```

### Option 2: OpenAI TTS
```bash
# Use OpenAI's TTS API
curl https://api.openai.com/v1/audio/speech \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1-hd",
    "input": "...",
    "voice": "alloy"
  }'
```

### Option 3: Google Cloud TTS
```bash
# Use Google Cloud Text-to-Speech
gcloud ml speech synthesize-long-audio \
  --text-file=podcasts/ai_podcast_2026-02-23.md \
  --output=audio.mp3 \
  --voice=en-US-Neural2-J
```

## Customization

### Change Host Names
Edit `PODCAST_TEMPLATE` in `daily_ai_podcast_generator.py`:
```python
**Alex:** -> **[YourName]:**
**Jordan:** -> **[OtherName]:**
```

### Adjust Content Sources
Edit `SOURCES` dict in `daily_ai_podcast_generator.py`:
```python
SOURCES = {
    "accounts": ["@YourFavoriteAccount", ...],
    "hashtags": ["#YourHashtag", ...],
    "keywords": ["your keyword", ...]
}
```

### Change Schedule Time
Modify the cron expression:
- `"0 6 * * *"` = 6 AM daily
- `"0 18 * * *"` = 6 PM daily
- `"0 9 * * 1-5"` = 9 AM weekdays only

## Troubleshooting

### Issue: No content collected
**Solution:** Ensure agent-browser skill is available and X.com is accessible

### Issue: Script looks repetitive
**Solution:** Need more diverse content sources - expand the SOURCES dict

### Issue: Want more technical depth
**Solution:** Add more technical accounts to monitor (e.g., @karpathy, @AnthropicAI research team)

### Issue: Script too long/short
**Solution:** Adjust the number of content items passed to `generate_podcast_script()`

## Future Enhancements

- [ ] Add sentiment analysis to prioritize controversial/interesting takes
- [ ] Include code snippets when discussing technical topics
- [ ] Add "quote of the day" from prominent AI researchers
- [ ] Generate episode artwork automatically
- [ ] Create RSS feed for podcast distribution
- [ ] Add chapter markers for different topics
- [ ] Include links to source tweets in show notes

## Resources

- [NotebookLM](https://notebooklm.google/) - Inspiration for conversational style
- [ElevenLabs](https://elevenlabs.io/) - High-quality TTS
- [OpenAI TTS](https://platform.openai.com/docs/guides/text-to-speech) - Alternative TTS
- [Podcast RSS Spec](https://help.apple.com/itc/podcasts_connect/#/itcb54353390) - For distribution

---

*Created: February 23, 2026*
*Version: 1.0*
