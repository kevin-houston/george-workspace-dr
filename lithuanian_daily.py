#!/usr/bin/env python3
"""
Daily Lithuanian phrase generator.
Picks the next phrase from the list (by day index), generates TTS audio,
and prints a JSON payload for the scheduled task to send.
"""

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

import edge_tts

VOICE = "lt-LT-OnaNeural"
OUTPUT = Path("/workspace/agent/lithuanian_phrase.mp3")

# Ordered phrase list — one per day, cycling after the end
PHRASES = [
    {
        "lt": "Labas rytas",
        "phonetic": "LAH-bahs REE-tahs",
        "en": "Good morning",
        "note": 'Used until about noon. "Rytas" means morning.',
    },
    {
        "lt": "Labas vakaras",
        "phonetic": "LAH-bahs VAH-kah-rahs",
        "en": "Good evening",
        "note": '"Vakaras" means evening. Switch to this after sunset.',
    },
    {
        "lt": "Kaip sekasi?",
        "phonetic": "KYPE SEH-kah-see",
        "en": "How are you?",
        "note": 'Casual form. Literally "How is it going for you?"',
    },
    {
        "lt": "Ačiū",
        "phonetic": "AH-choo",
        "en": "Thank you",
        "note": "One of the most useful words. The č is like 'ch' in 'church'.",
    },
    {
        "lt": "Prašom",
        "phonetic": "PRAH-shohm",
        "en": "Please / You're welcome",
        "note": "Works both ways — as 'please' when asking and 'you're welcome' in reply to ačiū.",
    },
    {
        "lt": "Atsiprašau",
        "phonetic": "aht-see-prah-SHOW",
        "en": "Excuse me / I'm sorry",
        "note": "Use it to get attention or to apologise. Stress falls on the last syllable.",
    },
    {
        "lt": "Taip",
        "phonetic": "TIPE",
        "en": "Yes",
        "note": 'Rhymes with the English word "type".',
    },
    {
        "lt": "Ne",
        "phonetic": "NEH",
        "en": "No",
        "note": 'Short and crisp — just one syllable. Also means "not".',
    },
    {
        "lt": "Kiek tai kainuoja?",
        "phonetic": "KYEHK TIE kye-NOO-oh-yah",
        "en": "How much does this cost?",
        "note": "Essential for shopping. 'Kiek' = how much, 'kainuoja' = costs.",
    },
    {
        "lt": "Aš nesuprantu",
        "phonetic": "ahsh neh-soo-PRAHN-too",
        "en": "I don't understand",
        "note": '"Aš" = I, "nesuprantu" = don\'t understand. Very useful as a beginner!',
    },
    {
        "lt": "Kur yra tualetas?",
        "phonetic": "KOOR EE-rah too-ah-LEH-tahs",
        "en": "Where is the bathroom?",
        "note": '"Kur" = where, "yra" = is, "tualetas" = toilet/bathroom.',
    },
    {
        "lt": "Vienas, du, trys",
        "phonetic": "VYEH-nahs, DOO, TREES",
        "en": "One, two, three",
        "note": "The first three numbers. 'Trys' sounds like 'trees' with a rolled r.",
    },
    {
        "lt": "Labas naktis",
        "phonetic": "LAH-bahs NAHK-tees",
        "en": "Good night",
        "note": '"Naktis" means night. Said when parting for the evening.',
    },
    {
        "lt": "Mano vardas yra...",
        "phonetic": "MAH-noh VAHR-dahs EE-rah",
        "en": "My name is...",
        "note": '"Mano" = my, "vardas" = name, "yra" = is. Follow with your name.',
    },
    {
        "lt": "Ar kalbate angliškai?",
        "phonetic": "ahr KAHL-bah-teh ahng-LEESH-kye",
        "en": "Do you speak English?",
        "note": '"Angliškai" means "in English". A lifesaver when you get stuck.',
    },
    {
        "lt": "Vanduo, prašom",
        "phonetic": "VAHN-doo-oh, PRAH-shohm",
        "en": "Water, please",
        "note": '"Vanduo" = water. Essential at any restaurant.',
    },
    {
        "lt": "Sveikas / Sveika",
        "phonetic": "SVAY-kahs / SVAY-kah",
        "en": "Hi (informal greeting)",
        "note": '"Sveikas" to a male, "Sveika" to a female. Also means "healthy".',
    },
    {
        "lt": "Iki pasimatymo",
        "phonetic": "EE-kee pah-see-mah-TEE-moh",
        "en": "Goodbye (until we meet again)",
        "note": "The formal farewell. The short version is just 'Iki!'",
    },
    {
        "lt": "Lietuva",
        "phonetic": "lyeh-too-VAH",
        "en": "Lithuania",
        "note": "The country itself! Stress on the last syllable, as with most Lithuanian words ending in -a.",
    },
    {
        "lt": "Aš myliu tave",
        "phonetic": "ahsh MEE-lyoo TAH-veh",
        "en": "I love you",
        "note": '"Aš" = I, "myliu" = love, "tave" = you. The \'y\' in myliu is a long vowel — like "ee".',
    },
]


def get_todays_phrase() -> dict:
    # Cycle through the list using the day-of-year so it advances daily
    day_index = date.today().timetuple().tm_yday - 1  # 0-based
    return PHRASES[day_index % len(PHRASES)]


async def generate_audio(text: str):
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(str(OUTPUT))


def format_message(phrase: dict, day_num: int) -> str:
    return (
        f"🇱🇹 **Lithuanian Phrase #{day_num}**\n\n"
        f"**{phrase['lt']}**\n"
        f"📖 *{phrase['en']}*\n"
        f"🔤 Phonetic: **{phrase['phonetic']}**\n\n"
        f"💡 {phrase['note']}"
    )


def main():
    phrase = get_todays_phrase()
    day_num = (date.today().timetuple().tm_yday % len(PHRASES)) or len(PHRASES)

    asyncio.run(generate_audio(phrase["lt"]))

    msg = format_message(phrase, day_num)
    # Print JSON for the scheduled task to consume
    print(json.dumps({"message": msg, "audio_path": str(OUTPUT), "phrase": phrase}))


if __name__ == "__main__":
    main()
