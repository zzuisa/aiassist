"""Deterministic URL classification before any network access."""

from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlsplit


class UrlType(StrEnum):
    bilibili = "bilibili"
    webpage = "webpage"
    unsupported = "unsupported"


_BILIBILI_VIDEO_PATH = re.compile(r"^/video/BV[A-Za-z0-9]+(?:/|$)", re.IGNORECASE)


def detect_url_type(url: str) -> UrlType:
    """Classify a validated-looking HTTP URL without resolving or fetching it.

    Security-sensitive DNS/IP validation remains in the existing URL extractor;
    this function only selects the processing pipeline and deliberately matches
    exact host boundaries so lookalike domains are never treated as Bilibili.
    """
    try:
        parsed = urlsplit((url or "").strip())
    except ValueError:
        return UrlType.unsupported
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return UrlType.unsupported
    if parsed.username is not None or parsed.password is not None:
        return UrlType.unsupported

    host = parsed.hostname.lower().rstrip(".")
    if host == "b23.tv":
        return UrlType.bilibili if parsed.path not in {"", "/"} else UrlType.unsupported
    if host == "bilibili.com" or host.endswith(".bilibili.com"):
        return UrlType.bilibili if _BILIBILI_VIDEO_PATH.match(parsed.path) else UrlType.webpage
    return UrlType.webpage
