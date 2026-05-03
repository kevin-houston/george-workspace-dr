# Microsoft Edge TTS Setup Guide

Using Microsoft Edge's free text-to-speech API to generate podcast audio from markdown scripts.

## Installation (Run on Host Machine)

```bash
# Install edge-tts Python package
pip install edge-tts

# Make sure ffmpeg is installed (for merging audio)
sudo apt install ffmpeg  # Ubuntu/Debian
# or
brew install ffmpeg  # macOS
```

## Testing Edge TTS

Run the test script to verify installation:

```bash
cd /home/kevin/nc/nanoclaw/groups/main
python3 test_edge_tts.py
```

This will:
1. Generate a test audio file (`test_output.mp3`)
2. List available English (US) voices
3. Create a sample 4-line conversation

Play the test output:
```bash
ffplay test_output.mp3
# or
mpv test_output.mp3
# or open in any audio player
```

## Generating Podcast Audio

Convert any Daily AI Insights podcast script to audio:

```bash
cd /home/kevin/nc/nanoclaw/groups/main
python3 generate_podcast_audio_edge.py podcasts/ai_podcast_2026-03-10.md
```

Output will be saved to:
- `podcasts/podcast_audio_2026-03-10.mp3` - Final merged podcast
- `podcasts/audio/segment_*.mp3` - Individual dialogue segments

## Voice Configuration

The script uses these voices by default:
- **Alex** (male host): `en-US-GuyNeural`
- **Jordan** (female host): `en-US-JennyNeural`

To change voices, edit `generate_podcast_audio_edge.py`:

```python
# Line 23-24
ALEX_VOICE = "en-US-DavisNeural"  # Warm, friendly male
JORDAN_VOICE = "en-US-AriaNeural"  # Conversational female
```

### Available Voices

Run this to list all voices:
```bash
edge-tts --list-voices | grep en-US
```

**Popular English US voices:**
- `en-US-GuyNeural` - Male, professional
- `en-US-DavisNeural` - Male, warm
- `en-US-JasonNeural` - Male, news anchor
- `en-US-JennyNeural` - Female, friendly
- `en-US-AriaNeural` - Female, conversational
- `en-US-SaraNeural` - Female, professional

## Audio Settings

You can adjust speed and volume in `generate_podcast_audio_edge.py`:

```python
# Line 29-30
RATE = "+10%"  # Speed: -50% to +100% (0% = normal)
VOLUME = "+5%"  # Volume: -50% to +50% (0% = normal)
```

## Command Line TTS (Quick Testing)

Generate audio from command line:

```bash
# Basic usage
edge-tts --text "Hello world" --write-media hello.mp3

# Specific voice
edge-tts --text "Testing voice" --voice "en-US-GuyNeural" --write-media test.mp3

# With speed adjustment
edge-tts --text "Faster speech" --rate="+20%" --write-media fast.mp3

# From file
edge-tts --file script.txt --voice "en-US-JennyNeural" --write-media output.mp3

# With subtitles
edge-tts --text "Hello" --write-media audio.mp3 --write-subtitles subs.srt
```

## Features

✅ **Free** - No API key or payment required
✅ **High Quality** - Neural voices sound natural
✅ **Fast** - Generates audio quickly
✅ **No Limits** - Unlimited usage
✅ **Multiple Formats** - MP3, WAV, OGG
✅ **100+ Languages** - Not just English
✅ **Subtitles** - Can generate SRT/VTT files
✅ **SSML Support** - Advanced voice control

## Automation

You could automate podcast audio generation by adding to the scheduled task:

```python
# After generating the markdown podcast script:
import subprocess
subprocess.run([
    'python3',
    '/home/kevin/nc/nanoclaw/groups/main/generate_podcast_audio_edge.py',
    '/home/kevin/nc/nanoclaw/groups/main/podcasts/ai_podcast_2026-03-10.md'
])
```

Or schedule separately to run after the text podcast is generated.

## Comparison with Other TTS

| Feature | Edge TTS | Piper TTS | OpenAI TTS | ElevenLabs |
|---------|----------|-----------|------------|------------|
| Cost | Free | Free | $0.015/1K chars | $5-330/mo |
| Quality | Excellent | Good | Excellent | Best |
| Voices | 400+ | 50+ | 6 | 1000+ |
| Speed | Fast | Very Fast | Fast | Fast |
| API Key | No | No | Yes | Yes |
| Offline | No | Yes | No | No |

**Edge TTS is perfect for:**
- Automated podcast generation
- Free, high-quality audio
- Quick iteration and testing
- Multi-voice conversations

## Troubleshooting

**"edge-tts command not found"**
- Make sure you installed with `pip install edge-tts`
- Try `python3 -m edge_tts` instead

**"ffmpeg not found"**
- Install ffmpeg: `sudo apt install ffmpeg`
- Individual segments still saved in `podcasts/audio/`

**Audio sounds robotic**
- Make sure you're using Neural voices (ending in "Neural")
- Try different voices - some are more natural than others
- Adjust RATE to slow down slightly (`RATE = "-10%"`)

**Acronyms sound weird**
- The script automatically handles common acronyms (AI, LLM, GPU, etc.)
- Add more to the `acronyms` dict in `clean_text_for_tts()` function

## Next Steps

1. Test installation: `python3 test_edge_tts.py`
2. Generate audio for today's podcast: `python3 generate_podcast_audio_edge.py podcasts/ai_podcast_2026-03-10.md`
3. Listen and adjust voice/speed settings as needed
4. Optionally integrate into daily podcast generation workflow
