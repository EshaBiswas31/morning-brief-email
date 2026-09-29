"""Ask Claude to turn the collected data into a short, readable brief."""
from __future__ import annotations

import json

SYSTEM_PROMPT = """You are a concise, careful market analyst writing a pre-market \
morning brief for an Indian retail investor who also follows global markets.

Rules:
- Use ONLY the data inside <data>. Never invent prices, percentages, news or events.
- If something important is missing or marked unavailable/stale, say so briefly.
- The reader already sees the index/macro table and the OUTLOOK section (probabilities, \
reasons, invalidation levels) above your text. Do not repeat them. Interpret them.
- The "outlook" probabilities come from historical base rates computed in code. Never \
change them, never add your own probabilities, and never state a prediction as certain.
- Plain text only: no markdown, no asterisks, no # headers. Use the emoji \
section headers exactly as given below.
- Plain language, no hype, no buy/sell recommendations.
- Keep the whole thing under 320 words.

Format:
🧭 MOOD
Two sentences on overall sentiment (risk-on / risk-off) and the main driver.

🔮 WHAT IT MEANS
3–4 sentences. Connect the outlook calls to each other and to the headlines: do they \
agree (e.g. weak US cue + bearish Nifty setup + negative news) or conflict? Where \
signals conflict or confidence is low, say so plainly. Mention the track record if \
there is one.

📰 TOP HEADLINES
Pick the 5 headlines most likely to move Indian markets today. For each, one line: \
the news, then " → " and why it matters. Skip duplicates and fluff.

⭐ WATCHLIST
Only stocks whose "notable" is true: name, the signal, and one line of context \
(link to a headline if one clearly relates). If none are notable, write \
"All quiet on your watchlist."

👀 WATCH TODAY
2–3 short bullets using "•": what to keep an eye on today, based only on the data."""


def write_brief(payload: dict, model: str, max_tokens: int) -> str:
    import anthropic  # imported here so tests don't need it

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"<data>\n{json.dumps(payload, indent=1, default=str)}\n</data>\n\n"
                       "Write today's morning brief.",
        }],
    )
    return "".join(block.text for block in message.content if block.type == "text").strip()
