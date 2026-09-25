"""
Shared drafting engine used by the Telegram webhook, the web UI, and the
local polling bot: builds the prompt, calls Gemini, and (best-effort) grounds
the draft with a real, current Google News link — the "news angle" feature.

Flow: note -> Gemini extracts 3-5 search terms -> Google News RSS (top
result) -> that headline/source/date/summary is handed to the SAME
drafting call alongside the note, with instructions to use it only if it's
genuinely relevant. The drafting call ends its response with a
NEWS_USED: yes/no marker (stripped before sending) so we know whether to
append the source/verification line — using our own fetched link, not
whatever the model might reproduce, so it can't drift or get mangled.

Does not touch voice_rubric.py (Meera's voice system prompt) — the news
instructions live only in the per-request prompt built here.
"""

from __future__ import annotations

import os
import re

import google.generativeai as genai

from news import fetch_top_article
from voice_rubric import SYSTEM_PROMPT

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
SCORE_THRESHOLD = 6

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
_terms_model = genai.GenerativeModel(GEMINI_MODEL)
_scorer_model = genai.GenerativeModel(GEMINI_MODEL)

NEWS_USED_MARKER = "NEWS_USED:"

_SCORE_RE = re.compile(r"SCORE:\s*(\d+)", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON:\s*(.+)", re.IGNORECASE)


def score_note(note: str) -> dict:
    """Score a raw note 0-10 for whether it's worth drafting into a post.

    Deliberately strict: a task reminder, a logistics note, or an abandoned
    half-sentence should score low even though it's real text — there has to
    be an actual claim, mechanism, story, or point of view to draft from.
    """
    prompt = (
        "You triage rough notes before they're turned into LinkedIn posts or newsletters "
        "for a skincare brand founder. Score the note below from 0 to 10 for how ready it "
        "is to draft into an actual post.\n\n"
        "Score high (7-10) ONLY if the note contains a specific claim, mechanism, story, "
        "or clear point of view — something with real content to build a post around.\n"
        "Score low (0-3) if the note is a task reminder, a to-do, a logistics note "
        "(ordering supplies, scheduling, admin), a half-formed or abandoned thought, or "
        "just doesn't have enough substance to say anything to a reader.\n"
        "Score in between (4-6) if there's a kernel of a usable idea but it's vague, "
        "underdeveloped, or missing the specifics needed to actually write from.\n\n"
        "Be strict — most rough notes people jot down are NOT ready to draft. Do not be "
        "generous just because a note is on-topic for skincare.\n\n"
        "Reply on ONE line, in exactly this format, nothing else:\n"
        "SCORE: <integer 0-10> | REASON: <one short sentence>\n\n"
        f"Note: {note}"
    )

    try:
        reply = _scorer_model.generate_content(prompt).text.strip()
        score_match = _SCORE_RE.search(reply)
        reason_match = _REASON_RE.search(reply)
        score = int(score_match.group(1)) if score_match else 0
        reason = reason_match.group(1).strip() if reason_match else reply
        return {"score": max(0, min(10, score)), "reason": reason}
    except Exception as exc:
        print(f"[score] scoring failed: {exc!r}")
        return {"score": 0, "reason": "Scoring failed, so this was rejected rather than drafted blind."}


def _extract_search_terms(note: str) -> list[str]:
    prompt = (
        "Extract 3 to 5 short search terms/phrases from the note below that would find "
        "relevant, current news coverage on the same topic. Reply with ONLY the terms, "
        "comma-separated, nothing else.\n\n"
        f"Note: {note}"
    )
    try:
        reply = _terms_model.generate_content(prompt).text.strip()
        terms = [t.strip() for t in reply.split(",") if t.strip()]
        return terms or [note[:80]]
    except Exception as exc:
        print(f"[news] search-term extraction failed: {exc!r}")
        return [note[:80]]


def _find_news_angle(note: str) -> dict | None:
    # Try each extracted term on its own — combining all of them into one query
    # over-dilutes the search and reliably returns nothing. Capped at 3 attempts
    # to bound worst-case latency (each RSS call has its own timeout).
    for term in _extract_search_terms(note)[:3]:
        article = fetch_top_article(term)
        if article:
            return article
    return None


def generate_draft(channel: str, note: str) -> dict:
    article = _find_news_angle(note)

    prompt = f"Channel: {channel}\n\nNotes:\n{note}"

    if article:
        prompt += (
            "\n\nHere is a recent news item found for this topic:\n"
            f"Headline: {article['title']}\n"
            f"Source: {article.get('source') or 'unknown'}\n"
            f"Date: {article.get('date') or 'unknown'}\n"
            f"Summary: {article.get('summary') or 'n/a'}\n\n"
            "If this news item is genuinely relevant, use it to make the post timely. "
            "If it doesn't fit naturally, ignore it.\n\n"
            "After writing the post, add one final line by itself, exactly "
            f'"{NEWS_USED_MARKER} yes" if you actually referenced this news item in the '
            f'post, or exactly "{NEWS_USED_MARKER} no" if you did not use it. This marker '
            "line is removed automatically before publishing — it is not part of the post."
        )

    response = _model.generate_content(prompt)
    draft_text = response.text.rstrip()

    used_news = False
    if article:
        lines = draft_text.splitlines()
        if lines and lines[-1].strip().upper().startswith(NEWS_USED_MARKER):
            used_news = lines[-1].strip().lower().endswith("yes")
            draft_text = "\n".join(lines[:-1]).rstrip()

    if used_news:
        draft_text += f"\n\nSource: {article['title']} — {article['link']}"

    return {"draft": draft_text, "related_article": article if used_news else None}
