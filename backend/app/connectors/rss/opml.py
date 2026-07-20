"""Bounded OPML parsing for RSS subscription import."""

from __future__ import annotations

from dataclasses import dataclass

from defusedxml import ElementTree

from app.connectors.rss.errors import RSSConnectorError


@dataclass(frozen=True)
class OPMLFeed:
    name: str
    feed_url: str


def parse_opml(
    payload: bytes,
    *,
    max_bytes: int,
    max_outlines: int,
) -> list[OPMLFeed]:
    if len(payload) > max_bytes:
        raise RSSConnectorError("opml_too_large")
    try:
        root = ElementTree.fromstring(payload)
    except Exception as exc:
        raise RSSConnectorError("malformed_opml") from exc
    feeds: list[OPMLFeed] = []
    for outline in root.iter("outline"):
        url = (outline.attrib.get("xmlUrl") or outline.attrib.get("xmlurl") or "").strip()
        if not url:
            continue
        if len(feeds) >= max_outlines:
            raise RSSConnectorError("opml_outline_limit")
        label = (
            outline.attrib.get("title")
            or outline.attrib.get("text")
            or url
        )
        feeds.append(OPMLFeed(name=" ".join(label.split())[:120], feed_url=url))
    if not feeds:
        raise RSSConnectorError("opml_no_feeds")
    return feeds
