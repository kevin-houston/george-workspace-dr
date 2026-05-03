#!/usr/local/bin/python3.13
"""
VoxCPM Podcast Generator — resumable, chunk-by-chunk
Run: PYTHONPATH=/workspace/group/.venv/lib/python3.13/site-packages /usr/local/bin/python3.13 /workspace/group/podcasts/generate_voxcpm_podcast.py

Reads ai_podcast_2026-04-10.md, generates each dialogue line as an individual
WAV segment (skipping any already done), then combines and emails the MP3.
Survives container restarts — re-run to resume.
"""

import os
import re
import subprocess
import smtplib
import numpy as np
import soundfile as sf
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ── Paths ─────────────────────────────────────────────────────────────────────
THIS_DIR    = Path(__file__).parent.resolve()
GROUP_DIR   = THIS_DIR.parent
SCRIPT_FILE = THIS_DIR / "ai_podcast_2026-04-10.md"
SEGMENTS_DIR = THIS_DIR / "voxcpm_segments"   # Per-line WAV files (persistent)
OUTPUT_WAV  = THIS_DIR / "ai_podcast_2026-04-10_voxcpm.wav"
OUTPUT_MP3  = THIS_DIR / "ai_podcast_2026-04-10_voxcpm.mp3"
ENV_FILE    = GROUP_DIR / ".env"
HF_CACHE    = GROUP_DIR / ".hf_cache"

# ── Voice control strings ─────────────────────────────────────────────────────
ALEX_VOICE   = "A confident, clear male podcast host voice with warm authoritative tone. American English."
JORDAN_VOICE = "A sharp, analytical female podcast host voice, articulate and engaging. American English."

SILENCE_MS      = 400
SAMPLE_RATE     = 24000
SILENCE_SAMPLES = int(SAMPLE_RATE * SILENCE_MS / 1000)
INFERENCE_STEPS = 2   # Fast CPU mode — lower quality but ~5x faster than default


def load_env(env_file: Path) -> dict:
    env = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return env


def parse_script(md_file: Path) -> list[tuple[str, str]]:
    lines = []
    pattern = re.compile(r"^\*\*(ALEX|JORDAN):\*\*\s*(.+)$")
    for line in md_file.read_text().splitlines():
        m = pattern.match(line.strip())
        if m:
            text = m.group(2).strip()
            if text:
                lines.append((m.group(1), text))
    return lines


def generate_segments(dialogue: list[tuple[str, str]]) -> bool:
    """Generate one WAV per dialogue line, skipping already-done ones.
    Returns True if all segments are complete."""
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # Find which segments still need generating
    pending = []
    for i, (speaker, text) in enumerate(dialogue):
        seg_path = SEGMENTS_DIR / f"seg_{i:03d}_{speaker}.wav"
        if not seg_path.exists():
            pending.append((i, speaker, text, seg_path))

    if not pending:
        print("✅ All segments already generated.")
        return True

    total = len(dialogue)
    done = total - len(pending)
    print(f"📊 Progress: {done}/{total} segments done, {len(pending)} remaining.")
    print(f"⏳ Loading VoxCPM2 model...")

    from voxcpm import VoxCPM
    HF_CACHE.mkdir(parents=True, exist_ok=True)
    tts = VoxCPM.from_pretrained(
        hf_model_id="openbmb/VoxCPM2",
        cache_dir=str(HF_CACHE),
        load_denoiser=False,  # Skip ModelScope denoiser download — runs faster
        optimize=False,
    )
    print("✅ Model loaded. Generating segments...")

    for i, speaker, text, seg_path in pending:
        control = ALEX_VOICE if speaker == "ALEX" else JORDAN_VOICE
        # VoxCPM voice control: prepend (description) to the text
        styled_text = f"({control}){text}"
        print(f"  [{i+1}/{total}] {speaker}: {text[:70]}{'...' if len(text) > 70 else ''}")
        wav = tts.generate(
            text=styled_text,
            cfg_value=2.0,
            inference_timesteps=INFERENCE_STEPS,
        )
        wav = np.array(wav, dtype=np.float32).flatten()
        sf.write(str(seg_path), wav, SAMPLE_RATE)

    # Check if all done now
    remaining = sum(
        1 for i, (spk, _) in enumerate(dialogue)
        if not (SEGMENTS_DIR / f"seg_{i:03d}_{spk}.wav").exists()
    )
    return remaining == 0


def combine_segments(dialogue: list[tuple[str, str]]) -> np.ndarray:
    silence = np.zeros(SILENCE_SAMPLES, dtype=np.float32)
    parts = []
    for i, (speaker, _) in enumerate(dialogue):
        seg_path = SEGMENTS_DIR / f"seg_{i:03d}_{speaker}.wav"
        wav, _ = sf.read(str(seg_path), dtype="float32")
        parts.append(wav.flatten())
        parts.append(silence.copy())
    return np.concatenate(parts)


def wav_to_mp3(wav_path: Path, mp3_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-qscale:a", "2", str(mp3_path)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✅ Converted to MP3: {mp3_path.name}")
            return True
        print(f"⚠️  ffmpeg failed: {result.stderr[-200:]}")
        return False
    except FileNotFoundError:
        print("⚠️  ffmpeg not found — will email WAV")
        return False


def send_email(audio_path: Path, gmail_password: str) -> bool:
    recipient = "kevinclaw26@gmail.com"
    subtype   = "mpeg" if audio_path.suffix == ".mp3" else "wav"
    subject   = "Daily AI Insights Podcast — 2026-04-10 (VoxCPM Test)"

    msg = MIMEMultipart()
    msg["From"]    = "kevinclaw26@gmail.com"
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(
        "Daily AI Insights — Episode: Meta Swings Big, Washington Draws Lines\n"
        "Date: 2026-04-10\n\nGenerated with VoxCPM2 neural TTS.\n", "plain"
    ))

    with open(audio_path, "rb") as f:
        part = MIMEBase("audio", subtype)
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=audio_path.name)
    msg.attach(part)

    try:
        print(f"📧 Sending {audio_path.name} ({audio_path.stat().st_size/1024/1024:.1f} MB) to {recipient}...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login("kevinclaw26@gmail.com", gmail_password)
            server.sendmail("kevinclaw26@gmail.com", recipient, msg.as_string())
        print("✅ Email sent!")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False


def main():
    print("🎙️  VoxCPM Podcast Generator (resumable)")
    print(f"   Script  : {SCRIPT_FILE}")
    print(f"   Segments: {SEGMENTS_DIR}")
    print(f"   Output  : {OUTPUT_MP3}")
    print()

    dialogue = parse_script(SCRIPT_FILE)
    print(f"📄 Parsed {len(dialogue)} dialogue lines.\n")

    all_done = generate_segments(dialogue)

    if not all_done:
        print("\n⏸️  Not all segments complete — re-run to continue from here.")
        return

    print("\n🔗 Combining segments...")
    audio = combine_segments(dialogue)
    sf.write(str(OUTPUT_WAV), audio, SAMPLE_RATE)
    duration_min = len(audio) / SAMPLE_RATE / 60
    print(f"✅ WAV saved ({duration_min:.1f} min)")

    mp3_ok = wav_to_mp3(OUTPUT_WAV, OUTPUT_MP3)
    output_file = OUTPUT_MP3 if mp3_ok else OUTPUT_WAV
    if mp3_ok:
        OUTPUT_WAV.unlink()

    env = load_env(ENV_FILE)
    gmail_password = env.get("GMAIL_APP_PASSWORD")
    if not gmail_password:
        print(f"⚠️  GMAIL_APP_PASSWORD not in .env — audio saved to: {output_file}")
        return

    send_email(output_file, gmail_password)


if __name__ == "__main__":
    main()
