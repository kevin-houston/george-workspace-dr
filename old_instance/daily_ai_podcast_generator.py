#!/usr/bin/env python3
"""
Daily AI Podcast Script Generator
Generates NotebookLM-style podcast scripts from X.com content about GenAI, Agentic Engineering, etc.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# Key X.com accounts and hashtags to monitor
SOURCES = {
    "accounts": [
        "@OpenAI",
        "@AnthropicAI",
        "@GoogleDeepMind",
        "@GoogleAI",
        "@MetaAI",
        "@MSFTResearch",
        "@GroqInc",
        "@AlliKMiller",
        "@RonaldvanLoon",
        "@andrewng",
        "@ylecun",
        "@karpathy",
        "@sama",
        "@demishassabis",
    ],
    "hashtags": [
        "#GenAI",
        "#AgenticAI",
        "#LLM",
        "#AI",
        "#MachineLearning",
        "#AgenticEngineering",
        "#nanoclaw",
        "#AIAgents",
        "#AutonomousAI",
    ],
    "keywords": [
        "agentic",
        "agent",
        "LLM",
        "generative AI",
        "Claude",
        "GPT",
        "autonomous",
        "nanoclaw",
        "AI engineering",
    ]
}

PODCAST_TEMPLATE = """# Daily AI Insights Podcast
## {date}

---

**[INTRO MUSIC FADES]**

**Alex:** Hey everyone, welcome back to Daily AI Insights! I'm Alex.

**Jordan:** And I'm Jordan. It's {day_of_week}, {formatted_date}, and wow, the AI world has been buzzing today!

**Alex:** Absolutely! We've been combing through X—formerly Twitter—looking at what the leading voices in GenAI and agentic engineering are talking about, and there's some fascinating stuff to unpack.

**Jordan:** Before we dive in, just a quick reminder: we pull insights from top AI researchers, companies like OpenAI, Anthropic, Google DeepMind, and independent developers building the future of autonomous AI agents.

**Alex:** Right. So let's get into it. What caught your eye first today?

---

{main_content}

---

**Alex:** {closing_thought}

**Jordan:** {jordan_closing}

**Alex:** That's all for today's Daily AI Insights. If you're building with AI agents or exploring agentic engineering, we'd love to hear from you.

**Jordan:** Yeah, drop us your thoughts. And we'll be back tomorrow with more from the cutting edge of AI.

**Alex:** Until then, keep building!

**[OUTRO MUSIC]**

---

*Generated on {timestamp}*
*Sources: X.com posts from the last 24 hours*
*Topics: Generative AI, Agentic Engineering, LLMs, Autonomous Agents*
"""

def generate_conversational_segment(topic, posts_summary, insight):
    """Generate a conversational segment between Alex and Jordan"""

    segment = f"""
**Jordan:** So, {topic}—this is getting a lot of attention today.

**Alex:** Right! {posts_summary}

**Jordan:** That's interesting. {insight}

**Alex:** Exactly. And I think what's fascinating here is how quickly this is evolving. Just last month we wouldn't have been talking about this at this scale.

**Jordan:** True. The pace is incredible.
"""
    return segment

def generate_podcast_script(content_items, date=None):
    """Generate a full podcast script from collected content"""

    if date is None:
        date = datetime.now()

    # Format dates
    day_of_week = date.strftime("%A")
    formatted_date = date.strftime("%B %d, %Y")
    timestamp = date.isoformat()

    # Generate main content sections
    main_segments = []

    for item in content_items:
        segment = generate_conversational_segment(
            topic=item.get("topic", "AI developments"),
            posts_summary=item.get("summary", "We're seeing interesting developments"),
            insight=item.get("insight", "This could have significant implications")
        )
        main_segments.append(segment)

    main_content = "\n".join(main_segments)

    # Generate closing thoughts
    closing_thought = "Well, that's the landscape as of today. Lots of innovation happening."
    jordan_closing = "Absolutely. It's an exciting time to be following this space."

    # Fill in the template
    script = PODCAST_TEMPLATE.format(
        date=formatted_date,
        day_of_week=day_of_week,
        formatted_date=formatted_date,
        main_content=main_content,
        closing_thought=closing_thought,
        jordan_closing=jordan_closing,
        timestamp=timestamp
    )

    return script

def save_script(script, output_dir="/workspace/group/podcasts"):
    """Save the generated script to a file"""

    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Generate filename with date
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"ai_podcast_{date_str}.md"
    filepath = os.path.join(output_dir, filename)

    # Write the script
    with open(filepath, 'w') as f:
        f.write(script)

    print(f"✅ Podcast script saved to: {filepath}")
    return filepath

def create_sample_content():
    """Create sample content for testing (will be replaced by real scraping)"""

    return [
        {
            "topic": "agentic AI systems are becoming more autonomous",
            "summary": "We're seeing posts from multiple researchers talking about how LLMs are no longer just chatbots—they're actually running workflows, making decisions, and executing tasks with minimal human intervention",
            "insight": "What's really striking is how this mirrors what we talked about last week with tool use. These agents aren't just calling APIs anymore; they're reasoning about when and how to use them"
        },
        {
            "topic": "the shift from prompt engineering to agentic engineering",
            "summary": "Several folks at OpenAI and Anthropic have been discussing this transition. It's not about crafting the perfect prompt anymore—it's about designing systems where agents can iterate, learn from failures, and improve their own prompts",
            "insight": "This is a fundamental shift in how we think about building with AI. We're moving from single-shot interactions to systems that can run autonomously for extended periods"
        },
        {
            "topic": "new developments in context window expansion",
            "summary": "There's been chatter about models with 1 million+ token context windows becoming more practical for production use. Google's been particularly active in this space",
            "insight": "The implications are huge. When your AI can hold an entire codebase in context, or process weeks of conversation history, the kinds of tasks it can handle fundamentally change"
        }
    ]

if __name__ == "__main__":
    print("🎙️  Daily AI Podcast Script Generator")
    print("=" * 60)

    # For now, use sample content
    # TODO: Replace with actual X.com scraping
    print("📝 Generating content from sample data...")
    print("    (Will be replaced with live X.com scraping)")

    content = create_sample_content()

    print(f"📊 Found {len(content)} topics to discuss")

    # Generate the script
    print("✍️  Generating podcast script...")
    script = generate_podcast_script(content)

    # Save to file
    filepath = save_script(script)

    print("\n✨ Done! Your podcast script is ready.")
    print(f"📁 Location: {filepath}")
    print("\n💡 Next steps:")
    print("   1. Review the script")
    print("   2. Use a TTS service to convert to audio (ElevenLabs, OpenAI TTS, etc.)")
    print("   3. Schedule this script to run daily with nanoclaw")
