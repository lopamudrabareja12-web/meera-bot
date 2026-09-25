"""
Shared drafting engine used by the Telegram webhook, the web UI, and the
local polling bot: builds the prompt, calls Gemini, and (best-effort) grounds
the draft with a real, current Google News link.

The draft and the news lookup run in parallel (not one after another) —
sequential took ~20s in practice (RSS fetch + a Gemini "picker" call + the
main Gemini call), which risks exceeding the serverless function timeout on
Vercel before a response is ever sent back.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import google.generativeai as genai

from news import find_candidate_articles
from voice_rubric import SYSTEM_PROMPT

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
_picker_model = genai.GenerativeModel(GEMINI_MODEL)


def _pick_relevant_article(note: str) -> dict | None:
    candidates = find_candidate_articles(note)
    if not candidates:
        print(f"[news] no RSS candidates for note: {note[:80]!r}")
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
            print(f"[news] picker rejected all {len(candidates)} candidates for: {note[:80]!r}")
            return None
        index = int(reply)
        if 0 <= index < len(candidates):
            return candidates[index]
        print(f"[news] picker returned out-of-range index {index!r}")
        return None
    except Exception as exc:
        print(f"[news] picker failed: {exc!r}")
        return None


def _write_draft(channel: str, note: str) -> str:
    prompt = f"Channel: {channel}\n\nNotes:\n{note}"
    return _model.generate_content(prompt).text.rstrip()


def generate_draft(channel: str, note: str) -> dict:
    with ThreadPoolExecutor(max_workers=2) as pool:
        draft_future = pool.submit(_write_draft, channel, note)
        article_future = pool.submit(_pick_relevant_article, note)
        draft_text = draft_future.result()
        article = article_future.result()

    if article:
        draft_text += f"\n\nSource: {article['title']} — {article['link']}"

    return {"draft": draft_text, "related_article": article}
