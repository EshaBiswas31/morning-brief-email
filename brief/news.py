"""Fetch and clean news headlines from RSS feeds."""
from __future__ import annotations

import calendar
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

import requests

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (morning-brief; +https://github.com)"}


def _normalize(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def dedupe(items: list[dict], threshold: float = 0.85) -> list[dict]:
    """Drop headlines that are the same story worded almost identically."""
    kept: list[dict] = []
    seen: list[str] = []
    for item in items:
        norm = _normalize(item["title"])
        if not norm:
            continue
        if any(SequenceMatcher(None, norm, s).ratio() >= threshold for s in seen):
            continue
        seen.append(norm)
        kept.append(item)
    return kept


def fetch_headlines(feeds: list[str], max_age_hours: int, limit: int) -> tuple[list[dict], list[str]]:
    """Return (headlines newest-first, list of feeds that failed)."""
    import feedparser  # imported here so tests don't need it

    now = datetime.now(timezone.utc)
    items: list[dict] = []
    failed: list[str] = []

    for url in feeds:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            if not parsed.entries:
                raise ValueError("feed returned no entries")
            source = parsed.feed.get("title", url)
            for entry in parsed.entries:
                title = (entry.get("title") or "").strip()
                if not title:
                    continue
                stamp = entry.get("published_parsed") or entry.get("updated_parsed")
                published = (
                    datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) if stamp else None
                )
                if published and (now - published).total_seconds() > max_age_hours * 3600:
                    continue
                items.append({
                    "title": title,
                    "source": source,
                    "published": published.isoformat() if published else None,
                })
        except Exception as exc:
            log.warning("Feed failed %s: %s", url, exc)
            failed.append(url)

    items.sort(key=lambda i: i["published"] or "", reverse=True)
    return dedupe(items)[:limit], failed
