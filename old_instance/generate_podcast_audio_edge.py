#!/usr/bin/env python3
"""
Generate audio podcast from markdown script using Microsoft Edge TTS
Takes a Daily AI Insights markdown file and converts it to audio

Usage:
    python3 generate_podcast_audio_edge.py podcasts/ai_podcast_2026-03-10.md

Requirements:
    pip install edge-tts
    apt install ffmpeg  # for merging audio segments
"""

import asyncio
import edge_tts
import re
import sys
import os
from pathlib import Path
import subprocess

# Voice assignments for the two hosts
ALEX_VOICE = "en-US-GuyNeural"  # Male voice for Alex
JORDAN_VOICE = "en-US-JennyNeural"  # Female voice for Jordan

# Alternative voices you can try:
# "en-US-DavisNeural" - Male, warm and friendly
# "en-US-JasonNeural" - Male, professional
# "en-US-AriaNeural" - Female, conversational
# "en-US-SaraNeural" - Female, news anchor style

# Audio settings
RATE = "+0%"  # Speed adjustment (-50% to +100%)
VOLUME = "+0%"  # Volume adjustment

class PodcastGenerator:
    def __init__(self, markdown_file):
        self.markdown_file = Path(markdown_file)
        self.output_dir = self.markdown_file.parent / "audio"
        self.output_dir.mkdir(exist_ok=True)
        self.segments = []

    def parse_markdown(self):
        """Parse markdown file and extract dialogue"""
        print(f"📄 Reading {self.markdown_file}...")

        with open(self.markdown_file, 'r') as f:
            content = f.read()

        # Extract dialogue sections (everything between ## INTRO and ## SOURCES)
        dialogue_match = re.search(r'## INTRO\n\n(.*?)\n---\n\n## SOURCES', content, re.DOTALL)
        if not dialogue_match:
            print("❌ Could not find dialogue section in markdown")
            return False

        dialogue_text = dialogue_match.group(1)

        # Parse speaker lines
        lines = dialogue_text.split('\n')
        current_speaker = None

        for line in lines:
            line = line.strip()

            # Match speaker pattern: **Alex:** or **Jordan:**
            speaker_match = re.match(r'\*\*(\w+):\*\*\s*(.*)', line)
            if speaker_match:
                current_speaker = speaker_match.group(1)
                text = speaker_match.group(2).strip()

                # Skip if it's a segment header or empty
                if text and not text.startswith('[') and not line.startswith('##'):
                    self.segments.append({
                        'speaker': current_speaker,
                        'text': text
                    })

        print(f"✅ Extracted {len(self.segments)} dialogue segments")
        return len(self.segments) > 0

    def clean_text_for_tts(self, text):
        """Clean text for better TTS pronunciation"""
        # Remove markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Remove bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Remove italic
        text = re.sub(r'`([^`]+)`', r'\1', text)  # Remove code

        # Remove stage directions in brackets
        text = re.sub(r'\[laughs?\]', '', text)
        text = re.sub(r'\[.*?\]', '', text)

        # Handle acronyms for better pronunciation
        acronyms = {
            'AI': 'A I',
            'LLM': 'L L M',
            'GPU': 'G P U',
            'CPU': 'C P U',
            'API': 'A P I',
            'TTS': 'T T S',
            'CEO': 'C E O',
            'CIO': 'C I O',
            'CISO': 'C I S O',
            'DoD': 'D O D',
            'TPU': 'T P U',
            'MCP': 'M C P',
            'SLA': 'S L A',
            'VIX': 'V I X',
            'ASIC': 'A S I C',
            'SDK': 'S D K',
            'USB': 'U S B',
            'EBITDA': 'E B I T D A',
            'MIT': 'M I T',
            'RSS': 'R S S',
            'GPT': 'G P T',
        }

        for acronym, pronunciation in acronyms.items():
            text = re.sub(r'\b' + acronym + r'\b', pronunciation, text)

        # Handle percentages
        text = re.sub(r'(\d+)%', r'\1 percent', text)

        # Handle X number format (like 2.6x, 10x)
        text = re.sub(r'(\d+\.?\d*)x\b', r'\1 times', text)

        # Clean up extra whitespace
        text = ' '.join(text.split())

        return text

    async def generate_segment_audio(self, index, speaker, text):
        """Generate audio for a single segment"""
        voice = ALEX_VOICE if speaker.lower() == 'alex' else JORDAN_VOICE
        output_file = self.output_dir / f"segment_{index:04d}.mp3"

        # Clean text for TTS
        clean_text = self.clean_text_for_tts(text)

        # Generate audio
        communicate = edge_tts.Communicate(
            clean_text,
            voice,
            rate=RATE,
            volume=VOLUME
        )
        await communicate.save(str(output_file))

        return output_file

    async def generate_all_segments(self):
        """Generate audio for all segments"""
        print(f"\n🎙️  Generating audio segments...")
        print(f"  Alex voice: {ALEX_VOICE}")
        print(f"  Jordan voice: {JORDAN_VOICE}")
        print()

        audio_files = []

        for i, segment in enumerate(self.segments):
            speaker = segment['speaker']
            text = segment['text']

            print(f"[{i+1}/{len(self.segments)}] {speaker}: {text[:60]}...")

            audio_file = await self.generate_segment_audio(i, speaker, text)
            audio_files.append(audio_file)

        print(f"\n✅ Generated {len(audio_files)} audio segments")
        return audio_files

    def merge_audio_files(self, audio_files):
        """Merge audio files using ffmpeg"""
        print("\n🎵 Merging audio segments...")

        # Create concat file for ffmpeg
        concat_file = self.output_dir / "concat_list.txt"
        with open(concat_file, 'w') as f:
            for audio_file in audio_files:
                f.write(f"file '{audio_file.name}'\n")

        # Output file name based on input
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', self.markdown_file.name)
        date_str = date_match.group(1) if date_match else "unknown"
        output_file = self.output_dir.parent / f"podcast_audio_{date_str}.mp3"

        # Run ffmpeg to concatenate
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            '-y',  # Overwrite output file
            str(output_file)
        ]

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"✅ Final podcast saved to: {output_file}")

            # Get file size and duration
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"   File size: {size_mb:.2f} MB")

            # Get duration using ffprobe
            try:
                duration_cmd = [
                    'ffprobe',
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(output_file)
                ]
                duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
                if duration_result.returncode == 0:
                    duration_sec = float(duration_result.stdout.strip())
                    duration_min = duration_sec / 60
                    print(f"   Duration: {duration_min:.1f} minutes")
            except:
                pass

            return output_file
        except subprocess.CalledProcessError as e:
            print(f"❌ Error merging audio: {e}")
            print(f"   stderr: {e.stderr}")
            print(f"   You can manually merge using: {' '.join(cmd)}")
            return None
        except FileNotFoundError:
            print("❌ ffmpeg not found. Please install ffmpeg to merge audio files.")
            print(f"   Individual segments saved in: {self.output_dir}")
            return None

    async def generate(self):
        """Main generation process"""
        print("="*80)
        print("  DAILY AI INSIGHTS PODCAST AUDIO GENERATOR")
        print("  Using Microsoft Edge TTS")
        print("="*80)
        print()

        # Parse markdown
        if not self.parse_markdown():
            return False

        # Generate segments
        audio_files = await self.generate_all_segments()

        # Merge segments
        final_file = self.merge_audio_files(audio_files)

        print()
        print("="*80)
        if final_file:
            print("  ✅ Podcast generation complete!")
            print(f"  🎧 Listen: {final_file}")
            print(f"  📁 Segments: {self.output_dir}")
        else:
            print("  ⚠️  Segments generated but not merged")
            print(f"  📁 Individual files: {self.output_dir}")
        print("="*80)

        return True


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_podcast_audio_edge.py <markdown_file>")
        print("\nExample:")
        print("  python3 generate_podcast_audio_edge.py podcasts/ai_podcast_2026-03-10.md")
        print("\nRequirements:")
        print("  pip install edge-tts")
        print("  apt install ffmpeg")
        sys.exit(1)

    markdown_file = sys.argv[1]

    if not os.path.exists(markdown_file):
        print(f"❌ File not found: {markdown_file}")
        sys.exit(1)

    generator = PodcastGenerator(markdown_file)
    success = await generator.generate()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
