"""Stable body + typed field diffing for post revisions (spec 005, US4, T086).

Two independent concerns:

* ``body_diff`` — a deterministic, line-oriented diff of two Markdown bodies,
  returned both as a unified-diff string and as structured hunks so the frontend
  can render an inline or side-by-side view without re-diffing.
* ``field_diff`` — a typed, three-way comparison of the *base* (what the AI
  branched from), the *current* article (which the user may have edited since)
  and the *candidate* (the AI proposal), one entry per field. This is what the
  review UI reasons about: whether a field is unchanged, changed only by the
  user, changed only by the AI, or in conflict (changed by both to different
  values).

Both functions are pure — no ORM, no session — so they are trivially testable
and reusable for any revision pair.
"""

from __future__ import annotations

import difflib
from typing import Any

# Fields compared three-way. Mirrors service._APPLYABLE_TOP_FIELDS plus the
# expandable ``structured_data`` map handled specially below.
COMPARED_FIELDS = (
    "title",
    "subtitle",
    "summary",
    "markdown",
    "content_class",
    "content_type_id",
    "language",
)

# Per-field three-way status.
UNCHANGED = "unchanged"  # base == current == candidate (nothing to do)
USER_ONLY = "user_only"  # user edited; AI kept base value
AI_ONLY = "ai_only"  # AI changed; user kept base value
AGREED = "agreed"  # user and AI independently reached the same new value
CONFLICT = "conflict"  # user and AI diverged to different values


def _line_hunks(a: str, b: str) -> list[dict[str, Any]]:
    """Structured opcode hunks between two texts (line granularity)."""
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    sm = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)
    hunks: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        hunks.append(
            {
                "op": tag,  # 'replace' | 'delete' | 'insert'
                "old_start": i1,
                "old_lines": a_lines[i1:i2],
                "new_start": j1,
                "new_lines": b_lines[j1:j2],
            }
        )
    return hunks


def body_diff(old_markdown: str, new_markdown: str, *, from_label: str = "current",
              to_label: str = "candidate") -> dict[str, Any]:
    """Deterministic body diff as a unified string plus structured hunks."""
    old = (old_markdown or "").splitlines(keepends=True)
    new = (new_markdown or "").splitlines(keepends=True)
    unified = "".join(
        difflib.unified_diff(old, new, fromfile=from_label, tofile=to_label)
    )
    hunks = _line_hunks(old_markdown or "", new_markdown or "")
    return {
        "from_label": from_label,
        "to_label": to_label,
        "unified_diff": unified,
        "hunks": hunks,
        "changed": bool(hunks),
    }


def _classify(base: Any, current: Any, candidate: Any) -> str:
    user_changed = current != base
    ai_changed = candidate != base
    if not ai_changed and not user_changed:
        return UNCHANGED
    if ai_changed and not user_changed:
        return AI_ONLY
    if user_changed and not ai_changed:
        return USER_ONLY
    # Both changed relative to base.
    return AGREED if current == candidate else CONFLICT


def _structured_keys(*snapshots: dict[str, Any]) -> list[str]:
    keys: set[str] = set()
    for snap in snapshots:
        sd = snap.get("structured_data") or {}
        if isinstance(sd, dict):
            keys.update(sd.keys())
    return sorted(keys)


def field_diff(
    base: dict[str, Any],
    current: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Typed three-way field diff keyed by field path.

    Each entry: ``{base, current, candidate, status}``. ``structured_data`` is
    expanded to ``structured_data.<key>`` entries so a single key can be applied
    without touching the rest of the map. Only fields that differ somewhere are
    returned; a field equal across all three snapshots is omitted.
    """
    out: dict[str, dict[str, Any]] = {}
    for field in COMPARED_FIELDS:
        b, c, d = base.get(field), current.get(field), candidate.get(field)
        status = _classify(b, c, d)
        if status == UNCHANGED:
            continue
        out[field] = {"base": b, "current": c, "candidate": d, "status": status}

    b_sd = base.get("structured_data") or {}
    c_sd = current.get("structured_data") or {}
    d_sd = candidate.get("structured_data") or {}
    for key in _structured_keys(base, current, candidate):
        b, c, d = b_sd.get(key), c_sd.get(key), d_sd.get(key)
        status = _classify(b, c, d)
        if status == UNCHANGED:
            continue
        out[f"structured_data.{key}"] = {
            "base": b,
            "current": c,
            "candidate": d,
            "status": status,
        }
    return out
