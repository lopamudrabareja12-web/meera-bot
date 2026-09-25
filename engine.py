"""
Shared drafting engine used by the Telegram webhook, the web UI, and the
local polling bot: builds the prompt, calls Gemini, and (best-effort) grounds
the draft with a real, current Google News link.
"""

from __future__ import annotations

import os

import google.generativeai as genai

from news import find_candidate_articles
from voice_rubric import SYSTEM_PROMPT

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
_picker_model = genai.GenerativeModel(GEMINI_MODEL)


def _pick_relevant_article(note: str, candidates: list[dict]) -> dict | None:
    if not candidates:
        return None

    listing = "\n".join(
        f"{i}. \"{c['title']}\" ({c.get('source') or 'unknown source'})"
        for i, c in enumerate(candidates)
    )
    prompt = (
        "A writer is drafting a skincare industry post about the note below. Here is a list "
        "of recent news headlines from an automated search. Reply with ONLY the number of the "
        "single headline whose SUBJECT MATTER is closely related to the note's topic and would "
        "add credible, relevant context if cited — it does not need to match the note's exact "
        "angle or claim, just be substantively about the same ingredient/topic/regulatory area. "
        "Reject generic buying guides, 'best products' roundups, 'we tested N products' listicles, "
        "and anything only tangentially connected by a shared keyword. If nothing qualifies, "
        "reply with exactly: none\n\n"
        f"Note: {note}\n\nHeadlines:\n{listing}\n\nAnswer:"
    )

    try:
        reply = _picker_model.generate_content(prompt).text.strip().lower()
        if reply == "none" or not reply.isdigit():
            return None
        index = int(reply)
        return candidates[index] if 0 <= index < len(candidates) else None
    except Exception:
        return None


def generate_draft(channel: str, note: str) -> dict:
    candidates = find_candidate_articles(note)
    article = _pick_relevant_article(note, candidates)

    prompt = f"Channel: {channel}\n\nNotes:\n{note}"
    if article:
        prompt += (
            "\n\nA recent, related news item. A link to it will be appended to the post "
            "automatically after you write it, so do not add your own link or repeat the URL "
            "in the body — but you may reference it by name or publication in a sentence, "
            "accurately, without misrepresenting what it says:\n"
            f"\"{article['title']}\" ({article.get('source') or 'source unknown'})"
        )

    response = _model.generate_content(prompt)
    draft_text = response.text.rstrip()

    if article:
        draft_text += f"\n\nSource: {article['title']} — {article['link']}"

    return {"draft": draft_text, "related_article": article}
