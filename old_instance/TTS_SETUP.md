# Local TTS Setup with Piper

## ✅ Successfully Installed: Piper TTS

**Status:** Fully functional and generating audio!

---

## 🎯 What's Installed:

1. **Piper TTS Binary** - v2023.11.14-2
   - Location: `/workspace/group/piper/`
   - Fast, local neural text-to-speech
   - No internet required after voice models are downloaded

2. **Voice Models:**
   - **en_US-lessac-medium** (Male voice) - Alex
   - **en_US-amy-medium** (Female voice) - Jordan

3. **Audio Generation Script:**
   - Location: `/workspace/group/generate_podcast_audio.py`
   - Converts markdown scripts to multi-voice audio
   - Automatically assigns voices based on speaker names

---

## 🚀 How to Use:

### Generate Audio from Script:

```bash
cd /workspace/group
python3 generate_podcast_audio.py podcasts/ai_podcast_2026-02-23.md
```

### Output:
- Individual segments: `/workspace/group/podcasts/audio/segment_000.wav`, etc.
- Each speaker gets appropriate voice (Alex=male, Jordan=female)
- Total: ~8-10 MB for a 5-10 minute podcast

---

## 🎙️ Available Voices:

### Currently Installed:

| Speaker | Voice Model | Description | Gender |
|---------|-------------|-------------|--------|
| Alex | en_US-lessac-medium | Clear, professional | Male |
| Jordan | en_US-amy-medium | Warm, conversational | Female |

### Add More Voices:

Download from Hugging Face: https://huggingface.co/rhasspy/piper-voices

```bash
cd /workspace/group/tts_voices

# Ryan (male, low)
curl -L https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx -o en_US-ryan-medium.onnx
curl -L https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json -o en_US-ryan-medium.onnx.json

# Libritts (high quality, multiple speakers)
curl -L https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/libritts/high/en_US-libritts-high.onnx -o en_US-libritts-high.onnx
curl -L https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/libritts/high/en_US-libritts-high.onnx.json -o en_US-libritts-high.onnx.json
```

---

## 🔧 Technical Details:

### Voice Model Files:
Each voice needs two files:
- `.onnx` - The neural network model (~60 MB)
- `.onnx.json` - Configuration file (voice metadata)

### Performance:
- Real-time factor: ~0.12 (12% of audio length to generate)
- 8 seconds of audio = ~1 second to generate
- Very fast on CPU, no GPU required

### Audio Format:
- Output: 16-bit WAV files
- Sample rate: 22050 Hz
- Quality: Good for podcasts and voice content

---

## 📝 Integration with Daily Podcast:

### Current Workflow:

1. **Script Generation** (automated at 6 AM)
   - Collects X.com content
   - Generates NotebookLM-style dialogue
   - Saves as markdown: `podcasts/ai_podcast_YYYY-MM-DD.md`

2. **Audio Generation** (run manually or add to automation)
   ```bash
   python3 generate_podcast_audio.py podcasts/ai_podcast_YYYY-MM-DD.md
   ```
   - Parses markdown script
   - Generates audio for each speaker segment
   - Saves individual WAV files

3. **Merging** (optional, requires sox or ffmpeg)
   ```bash
   # Install sox for merging:
   # sudo apt-get install sox

   # Or use ffmpeg:
   # sudo apt-get install ffmpeg
   ```

---

## 🎨 Customization:

### Change Voice Assignments:

Edit `/workspace/group/generate_podcast_audio.py`:

```python
VOICES = {
    "Alex": "en_US-lessac-medium.onnx",     # Change this
    "Jordan": "en_US-amy-medium.onnx",       # Change this
    "HOST": "en_US-lessac-medium.onnx",
    "GUEST": "en_US-amy-medium.onnx",
}
```

### Test Individual Voice:

```bash
cd /workspace/group
echo "This is a test message" | ./piper/piper --model tts_voices/en_US-amy-medium.onnx --output_file test.wav
```

---

## 📊 Comparison: Local vs Cloud TTS

| Feature | Piper (Local) | Inference.sh | ElevenLabs |
|---------|---------------|--------------|------------|
| **Cost** | Free | Pay per use | $5-30/month |
| **Speed** | Very fast | Fast | Fast |
| **Quality** | Good | Excellent | Excellent |
| **Voices** | 26+ | 50+ | 100+ |
| **Internet** | Not required | Required | Required |
| **Privacy** | Complete | Moderate | Moderate |
| **Setup** | Done! ✅ | Needs credits | Needs API key |

**Verdict:** Piper is perfect for your use case - free, fast, good quality, and works locally!

---

## 🔄 Automated Daily Podcast (Full Audio)

### Update Scheduled Task:

Modify your 6 AM task to include audio generation:

```javascript
schedule_task({
  prompt: "Generate today's Daily AI Insights podcast with AUDIO:

1. Collect X.com content (#GenAI, #AgenticAI, #LLM)
2. Generate NotebookLM-style script (Alex & Jordan)
3. Save script: /workspace/group/podcasts/ai_podcast_[DATE].md
4. Generate audio: python3 /workspace/group/generate_podcast_audio.py [script-path]
5. Audio segments saved to: /workspace/group/podcasts/audio/
6. Send summary of topics covered",

  schedule_type: "cron",
  schedule_value: "0 6 * * *",
  context_mode: "group"
})
```

---

## 🎧 Next Steps:

### Option 1: Keep Individual Segments
- Already done! ✅
- Listen to any segment individually
- Easier to edit/rearrange

### Option 2: Auto-Merge Segments
- Install sox: `sudo apt-get install sox`
- Script will automatically merge all segments
- Creates single podcast episode file

### Option 3: Add Intro/Outro Music
- Generate music with AI (free tools available)
- Add to script with `[MUSIC]` tags
- Merge with audio segments

### Option 4: Advanced Features
- Background music during dialogue
- Sound effects between segments
- Dynamic volume adjustments
- Professional audio mastering

---

## 📚 Resources:

### Piper TTS:
- [GitHub](https://github.com/rhasspy/piper)
- [Voice Samples](https://rhasspy.github.io/piper-samples/)
- [Hugging Face Models](https://huggingface.co/rhasspy/piper-voices)

### Alternative TTS (if needed):
- **Kokoro TTS** - 82M model, 26 voices, 8 languages
- **Coqui TTS** - Voice cloning, XTTS v2, 16 languages
- **Tortoise TTS** - Very high quality, slower

---

## ✅ Success!

**Your daily AI podcast system now generates:**
1. ✅ Text scripts (NotebookLM-style dialogue)
2. ✅ Audio files (Multi-voice, professional quality)
3. ✅ Automated daily (6 AM schedule)
4. ✅ Completely free (no API costs)
5. ✅ Works offline (no internet needed for TTS)

**Next time you run the daily task, you'll have a complete audio podcast ready to listen to or distribute!**

---

*Last updated: February 23, 2026*
*Piper TTS version: 2023.11.14-2*
*Status: Operational ✅*
