"""Protected-token extraction and comparison (spec 005, US3, T069).

Some spans of a post must not be silently rewritten by AI: fenced/inline code,
shell commands, URLs, bare numbers, dates and block quotations. We extract these
tokens from the base text and from an AI candidate, then compare: a protected
token that disappears or changes is reported.

Severity:
* ``blocking``  — code, commands or quotations changed (semantic-risk edits);
* ``warning``   — URLs, numbers or dates changed (often legitimate, but flagged).

Everything here is pure and deterministic so it is cheap to unit-test and safe to
run in the worker without side effects.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

# Token categories and their extraction patterns (applied to raw Markdown).
_FENCE_RE = re.compile(r"```.*?\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_COMMAND_RE = re.compile(r"^\s*[$#]\s+(.+)$", re.MULTILINE)
_URL_RE = re.compile(r"https?://[^\s)\]}>\"']+")
_NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w.])")
_DATE_RE = re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b")
_QUOTE_RE = re.compile(r"^\s*(?:>|&gt;)\s?(.*)$", re.MULTILINE)

_BLOCKING = frozenset({"code", "command", "quote"})

CATEGORY_ORDER = ("code", "command", "url", "number", "date", "quote")


def extract_tokens(markdown: str) -> dict[str, list[str]]:
    """Extract protected tokens by category from *markdown*.

    Code spans are extracted first and removed before scanning for URLs, numbers
    and dates, so a value living inside code is only ever counted as ``code``
    (never double-counted). Within each category the exact multiset (with counts)
    matters, so duplicates are preserved; callers compare multisets.
    """
    fenced = _FENCE_RE.findall(markdown)
    code = [c.strip() for c in fenced]
    code += [c.strip() for c in _INLINE_CODE_RE.findall(markdown)]
    # Commands are shell-prompt lines found inside fenced code.
    commands = [c.strip() for cblock in fenced for c in _COMMAND_RE.findall(cblock)]

    # Remove code spans before scanning prose-level tokens.
    prose = _FENCE_RE.sub(" ", markdown)
    prose = _INLINE_CODE_RE.sub(" ", prose)

    urls = _URL_RE.findall(prose)
    dates = _DATE_RE.findall(prose)
    # Dates contain digits; strip them before number extraction to avoid overlap.
    prose_no_dates = _DATE_RE.sub(" ", prose)
    numbers = _NUMBER_RE.findall(prose_no_dates)
    quotes = [q.strip() for q in _QUOTE_RE.findall(prose) if q.strip()]
    return {
        "code": [c for c in code if c],
        "command": commands,
        "url": urls,
        "number": numbers,
        "date": dates,
        "quote": quotes,
    }


def token_hash(markdown: str) -> str:
    """A stable hash of the protected-token multiset (order-independent)."""
    tokens = extract_tokens(markdown)
    payload = "|".join(f"{cat}:" + ",".join(sorted(tokens[cat])) for cat in CATEGORY_ORDER)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProtectedChange:
    __slots__ = ("added", "category", "removed", "severity")

    def __init__(self, category: str, removed: list[str], added: list[str]) -> None:
        self.category = category
        self.removed = removed
        self.added = added
        self.severity = "blocking" if category in _BLOCKING else "warning"

    def as_warning(self) -> dict:
        return {
            "code": "protected_token_changed",
            "field": self.category,
            "message": (
                f"{self.category} tokens changed: "
                f"{len(self.removed)} removed, {len(self.added)} added"
            ),
            "severity": self.severity,
        }


def compare(base_markdown: str, candidate_markdown: str) -> list[ProtectedChange]:
    """Return the protected-token changes from *base* to *candidate*.

    A category with an identical multiset yields no change. Otherwise the removed
    and added tokens are reported so the reviewer can see exactly what moved.
    """
    base = extract_tokens(base_markdown)
    cand = extract_tokens(candidate_markdown)
    changes: list[ProtectedChange] = []
    for cat in CATEGORY_ORDER:
        b = Counter(base[cat])
        c = Counter(cand[cat])
        if b == c:
            continue
        removed = list((b - c).elements())
        added = list((c - b).elements())
        if removed or added:
            changes.append(ProtectedChange(cat, removed, added))
    return changes


def has_blocking_change(changes: list[ProtectedChange]) -> bool:
    return any(ch.severity == "blocking" for ch in changes)
