# Automated Podcast Audio Generation & Email

Set up daily podcast audio generation with automatic email delivery.

## Prerequisites

1. **Shared venv set up** (run `./setup_shared_venv.sh` first)
2. **ffmpeg installed** (`sudo apt install ffmpeg`)
3. **Gmail App Password** in `.env` file

## Setup Gmail App Password

Create a `.env` file in `/home/kevin/nc/nanoclaw/groups/main/`:

```bash
cd /home/kevin/nc/nanoclaw/groups/main
nano .env
```

Add this line (replace with your actual app password):
```
GMAIL_APP_PASSWORD=your_16_character_app_password
```

**How to get a Gmail App Password:**
1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" and "Other (Custom name)"
3. Name it "Nanoclaw Podcast"
4. Copy the 16-character password
5. Paste it in the .env file

## Test Manually First

```bash
cd /home/kevin/nc/nanoclaw/groups/main
source venv/bin/activate
python3 generate_and_email_podcast.py
```

This will:
1. Find today's podcast markdown file
2. Generate audio using Edge TTS
3. Merge segments into final MP3
4. Email the MP3 to kevinclaw26@gmail.com

## Automated Daily Schedule

Add to your crontab to run automatically:

```bash
crontab -e
```

Add this line (runs at 6:15 AM daily, 15 minutes after text podcast generation):

```cron
15 6 * * * cd /home/kevin/nc/nanoclaw/groups/main && /home/kevin/nc/nanoclaw/groups/main/venv/bin/python generate_and_email_podcast.py >> podcast_audio.log 2>&1
```

**Why 6:15 AM?**
- Text podcast generates at 6:00 AM (in container)
- Audio generation runs at 6:15 AM (on host, 15 min later)
- Gives the text podcast time to finish first

## What You'll Receive

Every morning you'll get an email:
- **Subject:** "Daily AI Insights Podcast - 2026-03-10"
- **Attachment:** MP3 file (~15 minutes, 10-15 MB)
- **Format:** High-quality neural TTS voices
- **Playable:** On phone, computer, car, anywhere

## Monitoring

Check the log file to see if it's working:

```bash
tail -f /home/kevin/nc/nanoclaw/groups/main/podcast_audio.log
```

## Troubleshooting

**Email not sending:**
- Check `.env` file has correct GMAIL_APP_PASSWORD
- Verify Gmail App Password is still active
- Check log file for error messages

**Audio not generating:**
- Make sure edge-tts is installed: `source venv/bin/activate && pip list | grep edge-tts`
- Check ffmpeg is installed: `which ffmpeg`
- Look for errors in podcast_audio.log

**No email received:**
- Check spam folder
- Verify recipient email in script (default: kevinclaw26@gmail.com)
- Check Gmail "Sent" folder to see if it sent

## Voice Customization

To change voices, edit `generate_and_email_podcast.py`:

```python
# Line 21-22
ALEX_VOICE = "en-US-DavisNeural"    # Change male voice
JORDAN_VOICE = "en-US-AriaNeural"   # Change female voice
```

Available voices:
- `en-US-GuyNeural` - Professional male (default for Alex)
- `en-US-DavisNeural` - Warm, friendly male
- `en-US-JasonNeural` - News anchor male
- `en-US-JennyNeural` - Friendly female (default for Jordan)
- `en-US-AriaNeural` - Conversational female
- `en-US-SaraNeural` - Professional female

## Complete Daily Automation Schedule

With this setup, your daily automation will be:

**6:00 AM** - Text podcast generated (container)
**6:15 AM** - Audio generated & emailed (host)
**6:30 AM** - Portfolio advisor email (container)
**6:35 AM** - Portfolio report email (container)
**4:00 PM** - System maintenance summary (container)
**4:30 PM** - Stock prices updated (host)

## Files Generated

- `/home/kevin/nc/nanoclaw/groups/main/podcasts/ai_podcast_YYYY-MM-DD.md` - Text script
- `/home/kevin/nc/nanoclaw/groups/main/podcasts/podcast_audio_YYYY-MM-DD.mp3` - Audio file
- `/home/kevin/nc/nanoclaw/groups/main/podcasts/audio/segment_*.mp3` - Individual segments
- `/home/kevin/nc/nanoclaw/groups/main/podcast_audio.log` - Generation log

## Disk Space Management

Audio files are ~10-15 MB each. To clean up old files:

```bash
# Delete audio files older than 30 days
find /home/kevin/nc/nanoclaw/groups/main/podcasts -name "podcast_audio_*.mp3" -mtime +30 -delete

# Delete segment folders older than 7 days
find /home/kevin/nc/nanoclaw/groups/main/podcasts/audio -name "segment_*.mp3" -mtime +7 -delete
```

Or add to crontab to run weekly:

```cron
0 2 * * 0 find /home/kevin/nc/nanoclaw/groups/main/podcasts -name "podcast_audio_*.mp3" -mtime +30 -delete
```

## Manual Generation

If you miss a day or want to regenerate:

```bash
cd /home/kevin/nc/nanoclaw/groups/main
source venv/bin/activate

# Generate audio for today
python3 generate_and_email_podcast.py

# Generate for specific date
python3 generate_podcast_audio_edge.py podcasts/ai_podcast_2026-03-09.md
# Then email manually or run generate_and_email_podcast.py
```
