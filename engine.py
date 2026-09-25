"""
Shared drafting engine used by the Telegram webhook, the web UI, and the
local polling bot: builds the prompt, calls Gemini, and (best-effort) grounds
the draft with a real, current Google News link.
"""

from __future__ import annotations

import os

import google.generativeai as genai

from news import find_related_article
from voice_rubric import SYSTEM_PROMPT

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)


def generate_draft(channel: str, note: str) -> dict:
    article = find_related_article(note)

    prompt = f"Channel: {channel}\n\nNotes:\n{note}"
    if article:
        prompt += (
            "\n\nA recent, possibly related news item (use it only if it's genuinely "
            "relevant and you can reference it accurately — never force it in, and never "
            "misrepresent what it says):\n"
            f"\"{article['title']}\" ({article.get('source') or 'source unknown'}) — {article['link']}"
        )

    response = _model.generate_content(prompt)
    return {"draft": response.text, "related_article": article}
