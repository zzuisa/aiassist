"""Effective field-policy calculation and path validation (spec 005, US3, T070).

A Skill version declares per-field policies (blog-skill-config.v1.field_policies).
When an AI candidate is produced, each proposed field is classified against the
*effective* policy — the Skill policy clamped by a hard safety ceiling — into:

* ``full``      — may be applied automatically (subject to user confirmation UI);
* ``partial``   — may be suggested but requires explicit confirmation;
* ``rejected``  — must never be written from AI output.

The ceiling exists so a mis-configured Skill can never escalate a field beyond
what is safe (e.g. no field is ever silently ``auto_fill`` for protected content,
and unknown/unlisted fields default to ``suggest_only``).
"""

from __future__ import annotations

# Policies a Skill may declare (mirrors the contract enum).
POLICIES = (
    "forbid",
    "suggest_only",
    "require_confirmation",
    "fill_if_empty",
    "auto_fill",
    "allow_overwrite",
    "keep_both_on_conflict",
)

# Top-level fields an AI candidate may ever touch (aligns with service allow-list).
APPLYABLE_TOP_FIELDS = frozenset(
    {"title", "subtitle", "summary", "markdown", "content_class", "language", "structured_data"}
)

# Hard ceiling per field: a Skill policy is never allowed to exceed this.
# ``markdown`` (the body) can never be auto-applied — it always needs review.
_CEILING = {
    "markdown": "require_confirmation",
    "title": "allow_overwrite",
    "subtitle": "allow_overwrite",
    "summary": "allow_overwrite",
    "content_class": "require_confirmation",
    "language": "require_confirmation",
    "structured_data": "require_confirmation",
}

# Ordering of increasing "write power"; used to clamp a policy to the ceiling.
_RANK = {
    "forbid": 0,
    "suggest_only": 1,
    "require_confirmation": 2,
    "keep_both_on_conflict": 2,
    "fill_if_empty": 3,
    "allow_overwrite": 4,
    "auto_fill": 5,
}

_DEFAULT_POLICY = "suggest_only"


def _top(path: str) -> str:
    return path.split(".", 1)[0]


def validate_path(path: str) -> None:
    """Raise ValueError if *path* is not an applyable top-level or structured subkey."""
    top = _top(path)
    if top not in APPLYABLE_TOP_FIELDS:
        raise ValueError(f"field '{path}' is not applyable by AI")


def effective_policy(field_policies: dict[str, str], path: str) -> str:
    """Compute the effective policy for *path*, clamped by the safety ceiling."""
    top = _top(path)
    declared = field_policies.get(path) or field_policies.get(top) or _DEFAULT_POLICY
    if declared not in _RANK:
        declared = _DEFAULT_POLICY
    ceiling = _CEILING.get(top, "require_confirmation")
    # Clamp the declared policy down to the ceiling's rank.
    if _RANK[declared] > _RANK[ceiling]:
        return ceiling
    return declared


def classify_field(
    field_policies: dict[str, str],
    path: str,
    *,
    has_blocking_protected_change: bool = False,
) -> str:
    """Classify one proposed field into full / partial / rejected.

    A blocking protected-token change forces ``rejected`` regardless of policy.
    """
    try:
        validate_path(path)
    except ValueError:
        return "rejected"
    policy = effective_policy(field_policies, path)
    if policy == "forbid":
        return "rejected"
    if has_blocking_protected_change and _top(path) == "markdown":
        return "rejected"
    if policy in ("auto_fill", "allow_overwrite", "fill_if_empty"):
        return "full"
    # suggest_only / require_confirmation / keep_both_on_conflict
    return "partial"


def classify_candidate(
    field_policies: dict[str, str],
    proposed_fields: list[str],
    *,
    blocking_markdown_change: bool = False,
) -> dict[str, str]:
    """Classify every proposed field; returns ``{path: full|partial|rejected}``."""
    result: dict[str, str] = {}
    for path in proposed_fields:
        result[path] = classify_field(
            field_policies,
            path,
            has_blocking_protected_change=blocking_markdown_change,
        )
    return result
