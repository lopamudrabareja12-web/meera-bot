"""
Google News RSS lookup: given a search query, fetches the top result and
extracts headline, source, publish date, summary, and link. Best-effort —
any failure (network, empty feed, bad XML) returns None rather than
blocking the draft.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def fetch_top_article(query: str, timeout: int = 5) -> dict | None:
    query = (query or "").strip()
    if not query:
        return None

    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"

    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        item = root.find("./channel/item")
        if item is None:
            print(f"[news] no RSS results for query: {query!r}")
            return None

        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        date = (item.findtext("pubDate") or "").strip()
        summary = _clean_html(item.findtext("description") or "")
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else None

        if not title or not link:
            return None

        return {"title": title, "link": link, "source": source, "date": date, "summary": summary}
    except Exception as exc:
        print(f"[news] RSS lookup failed for {query!r}: {exc!r}")
        return None
