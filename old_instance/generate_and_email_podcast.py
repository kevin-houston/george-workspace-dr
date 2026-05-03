#!/usr/bin/env python3
"""
Generate podcast audio and email it
Runs on host machine after the text podcast is generated

Requirements:
    - edge-tts (auto-installed if missing)
    - ffmpeg optional (falls back to Python MP3 concat)
    - Gmail credentials in .env file
"""

import asyncio
import subprocess, sys

# Auto-install edge-tts to a known local directory that is always on sys.path
_DEPS_DIR = "/tmp/podcast_deps"
if _DEPS_DIR not in sys.path:
    sys.path.insert(0, _DEPS_DIR)

try:
    import edge_tts
except ImportError:
    import subprocess as _sp, urllib.request as _req, tempfile as _tmp, os as _os
    print("⚙️  edge-tts not found, installing to /tmp/podcast_deps...")
    _os.makedirs(_DEPS_DIR, exist_ok=True)
    # Bootstrap pip if needed, then install edge-tts to known target dir
    try:
        _sp.run([sys.executable, "-m", "pip", "--version"], check=True, capture_output=True)
    except Exception:
        _gp = _tmp.mktemp(suffix=".py")
        _req.urlretrieve("https://bootstrap.pypa.io/get-pip.py", _gp)
        _sp.run([sys.executable, _gp, "--user", "--break-system-packages", "-q"], check=True)
        _os.unlink(_gp)
    _sp.run([sys.executable, "-m", "pip", "install", "edge-tts", f"--target={_DEPS_DIR}", "-q"])  # no check=True — warnings cause non-zero exit
    if _DEPS_DIR not in sys.path:
        sys.path.insert(0, _DEPS_DIR)
    import edge_tts
import re
import os
import sys
from pathlib import Path
import subprocess
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.audio import MIMEAudio

# Voice assignments
ALEX_VOICE = "en-US-GuyNeural"
JORDAN_VOICE = "en-US-JennyNeural"

# Email settings
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "kevinclaw26@gmail.com"
RECIPIENT_EMAIL = "kevinclaw26@gmail.com"

class PodcastAudioGenerator:
    def __init__(self, markdown_file):
        self.markdown_file = Path(markdown_file)
        self.output_dir = self.markdown_file.parent / "audio"
        self.output_dir.mkdir(exist_ok=True)
        self.segments = []

    def parse_markdown(self):
        """Parse markdown file and extract dialogue"""
        print(f"📄 Reading {self.markdown_file.name}...")

        with open(self.markdown_file, 'r') as f:
            content = f.read()

        # Strategy 1: Try structured ## INTRO ... ## SOURCES format
        dialogue_match = re.search(r'## INTRO\n\n(.*?)\n---\n\n## SOURCES', content, re.DOTALL)
        if dialogue_match:
            dialogue_text = dialogue_match.group(1)
            print("📋 Using structured INTRO/SOURCES format")
        else:
            # Strategy 2: Fall back to extracting all speaker lines from the full document
            # This handles the **[INTRO]** / **[SEGMENT N]** style format
            print("📋 Using full-document speaker extraction (flexible format)")
            dialogue_text = content

        # Parse speaker lines
        for line in dialogue_text.split('\n'):
            line = line.strip()
            speaker_match = re.match(r'\*\*(\w+):\*\*\s*(.*)', line)
            if speaker_match:
                speaker = speaker_match.group(1)
                text = speaker_match.group(2).strip()

                # Skip stage directions and section headers
                if text and not text.startswith('[') and speaker.lower() in ('alex', 'jordan'):
                    self.segments.append({'speaker': speaker, 'text': text})

        print(f"✅ Extracted {len(self.segments)} dialogue segments")
        return len(self.segments) > 0

    def clean_text_for_tts(self, text):
        """Clean text for better TTS pronunciation"""
        # Remove markdown
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'\[laughs?\]', '', text)
        text = re.sub(r'\[.*?\]', '', text)

        # Handle acronyms
        acronyms = {
            'AI': 'A I', 'LLM': 'L L M', 'GPU': 'G P U', 'CPU': 'C P U',
            'API': 'A P I', 'TTS': 'T T S', 'CEO': 'C E O', 'CIO': 'C I O',
            'CISO': 'C I S O', 'DoD': 'D O D', 'TPU': 'T P U', 'MCP': 'M C P',
            'SLA': 'S L A', 'VIX': 'V I X', 'ASIC': 'A S I C', 'SDK': 'S D K',
            'USB': 'U S B', 'EBITDA': 'E B I T D A', 'MIT': 'M I T',
            'RSS': 'R S S', 'GPT': 'G P T', 'NVDA': 'N V D A',
        }

        for acronym, pronunciation in acronyms.items():
            text = re.sub(r'\b' + acronym + r'\b', pronunciation, text)

        text = re.sub(r'(\d+)%', r'\1 percent', text)
        text = re.sub(r'(\d+\.?\d*)x\b', r'\1 times', text)
        text = ' '.join(text.split())

        return text

    async def generate_segment_audio(self, index, speaker, text):
        """Generate audio for a single segment"""
        voice = ALEX_VOICE if speaker.lower() == 'alex' else JORDAN_VOICE
        output_file = self.output_dir / f"segment_{index:04d}.mp3"

        clean_text = self.clean_text_for_tts(text)

        communicate = edge_tts.Communicate(clean_text, voice, rate="+0%", volume="+0%")
        await communicate.save(str(output_file))

        return output_file

    async def generate_all_segments(self):
        """Generate audio for all segments"""
        print(f"\n🎙️  Generating audio segments...")
        print(f"  Alex: {ALEX_VOICE}")
        print(f"  Jordan: {JORDAN_VOICE}\n")

        audio_files = []

        for i, segment in enumerate(self.segments):
            speaker = segment['speaker']
            text = segment['text']
            print(f"[{i+1}/{len(self.segments)}] {speaker}: {text[:50]}...")

            audio_file = await self.generate_segment_audio(i, speaker, text)
            audio_files.append(audio_file)

        print(f"\n✅ Generated {len(audio_files)} segments")
        return audio_files

    def merge_audio_files(self, audio_files):
        """Merge audio files using ffmpeg"""
        print("\n🎵 Merging audio segments...")

        concat_file = self.output_dir / "concat_list.txt"
        with open(concat_file, 'w') as f:
            for audio_file in audio_files:
                f.write(f"file '{audio_file.name}'\n")

        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', self.markdown_file.name)
        date_str = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
        output_file = self.output_dir.parent / f"podcast_audio_{date_str}.mp3"

        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0',
            '-i', str(concat_file), '-c', 'copy', '-y', str(output_file)
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"✅ Podcast saved: {output_file.name} ({size_mb:.2f} MB)")
            return output_file
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("⚠️  ffmpeg not available, using Python MP3 concat fallback...")
            return self._merge_python_fallback(audio_files, output_file)

    def _merge_python_fallback(self, audio_files, output_file):
        """Merge MP3 segments by concatenating bytes (works for CBR MP3s from edge-tts)"""
        try:
            with open(output_file, 'wb') as out:
                for f in audio_files:
                    out.write(f.read_bytes())
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"✅ Podcast saved (Python merge): {output_file.name} ({size_mb:.2f} MB)")
            return output_file
        except Exception as e:
            print(f"❌ Python merge failed: {e}")
            return None

    async def generate(self):
        """Main generation process"""
        if not self.parse_markdown():
            return None

        audio_files = await self.generate_all_segments()
        final_file = self.merge_audio_files(audio_files)

        return final_file


def send_email(audio_file, date_str):
    """Send podcast audio via email"""
    print(f"\n📧 Sending email...")

    # Load Gmail credentials from .env
    env_file = Path(__file__).parent / '.env'
    gmail_password = None

    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith('GMAIL_APP_PASSWORD='):
                    gmail_password = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break

    if not gmail_password:
        print("❌ GMAIL_APP_PASSWORD not found in .env file")
        return False

    # Create email
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = f"Daily AI Insights Podcast - {date_str}"

    # Email body
    body = f"""Daily AI Insights Podcast Audio

Date: {date_str}

Your daily podcast has been generated and is attached as an MP3 file.

Duration: ~15 minutes
Format: MP3
Quality: High (Microsoft Edge Neural TTS)

🎧 Listen on any device!

---
Generated automatically by nanoclaw
"""

    msg.attach(MIMEText(body, 'plain'))

    # Attach audio file
    try:
        with open(audio_file, 'rb') as f:
            audio_data = f.read()
            audio_attachment = MIMEAudio(audio_data, 'mpeg')
            audio_attachment.add_header('Content-Disposition', 'attachment', filename=audio_file.name)
            msg.attach(audio_attachment)
    except Exception as e:
        print(f"❌ Error attaching audio: {e}")
        return False

    # Send email
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, gmail_password)
        server.send_message(msg)
        server.quit()
        print(f"✅ Email sent to {RECIPIENT_EMAIL}")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False


async def main():
    print("="*80)
    print("  DAILY AI INSIGHTS PODCAST AUDIO GENERATOR")
    print("="*80)
    print()

    # Find today's podcast
    podcasts_dir = Path(__file__).parent / "podcasts"
    today = datetime.now().strftime('%Y-%m-%d')
    podcast_file = podcasts_dir / f"ai_podcast_{today}.md"

    if not podcast_file.exists():
        print(f"❌ Podcast not found: {podcast_file}")
        print("\nSearching for most recent podcast...")

        # Find most recent podcast
        podcast_files = sorted(podcasts_dir.glob("ai_podcast_*.md"), reverse=True)
        if podcast_files:
            podcast_file = podcast_files[0]
            print(f"📄 Using: {podcast_file.name}")
        else:
            print("❌ No podcast files found")
            sys.exit(1)

    # Generate audio
    generator = PodcastAudioGenerator(podcast_file)
    audio_file = await generator.generate()

    if not audio_file:
        print("\n❌ Failed to generate audio")
        sys.exit(1)

    # Extract date from filename
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', str(audio_file))
    date_str = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')

    # Send email
    email_sent = send_email(audio_file, date_str)

    print()
    print("="*80)
    if email_sent:
        print("  ✅ COMPLETE!")
        print(f"  📧 Podcast emailed to {RECIPIENT_EMAIL}")
    else:
        print("  ⚠️  Audio generated but email failed")
        print(f"  📁 File: {audio_file}")
    print("="*80)

    sys.exit(0 if email_sent else 1)


if __name__ == "__main__":
    asyncio.run(main())
