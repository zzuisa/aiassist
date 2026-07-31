"""Shared bounded HTTP timeout for external LLM providers."""

from __future__ import annotations

import httpx

from app.core.config import get_settings


def llm_http_timeout() -> httpx.Timeout:
    """Return separate connect/read limits suitable for long async generation.

    The 300-second default applies to waiting for model output. Connect and pool
    acquisition remain short so DNS, routing, or capacity faults fail quickly.
    """
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.llm_connect_timeout_seconds,
        read=settings.llm_read_timeout_seconds,
        write=60.0,
        pool=settings.llm_connect_timeout_seconds,
    )
