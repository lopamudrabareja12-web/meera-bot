"""
Pulls one relevant, recent article from Google News RSS for the topic in a
note. Best-effort: any failure (network, empty feed, bad XML) returns None
rather than blocking the draft.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are",
    "was", "were", "with", "this", "that", "it", "its", "how", "why", "what",
    "most", "some", "not", "does", "do", "did", "so",
}


def _extract_query(note: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", note) if w.lower() not in _STOPWORDS]
    return " ".join(words[:6]) or note[:60]


def find_related_article(note: str, timeout: int = 5) -> dict | None:
    query = _extract_query(note)
    if not query:
        return None

    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"

    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        item = root.find("./channel/item")
        if item is None:
            return None

        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else None

        if not title or not link:
            return None

        return {"title": title, "link": link, "source": source}
    except Exception:
        return None
