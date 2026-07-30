"""Read-side queries: listing, triage, search, timeline, word cloud (spec 005).

Owner-scoped listing with combinable filters and derived AI/source summaries;
triage projections (quick/failed/stale/draft). Search / timeline / word-cloud land
in later user stories. Implemented here: T116 (list) and T117 (triage).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.blog import PostSource
from app.models.posts import Post

# content_status values that mean "not yet an organized article" — the triage
# backlog. 'quick' captures also surface here via content_class.
_TRIAGE_STATUSES = ("pending_capture", "pending_parse", "triage", "draft")
_ACTIVE_EXCLUDED = ("archived", "discarded")

# A draft/triage item untouched for this long is considered stale.
STALE_AFTER = timedelta(days=14)


def _derived_ai_state(post: Post) -> str:
    """Compact AI state for list rows (presentation-only)."""
    if post.content_status == "ai_review":
        return "review"
    if post.content_status in ("ai_queued", "ai_processing"):
        return "processing"
    if post.latest_ai_status == "failed":
        return "failed"
    if post.ai_optimization_count and post.ai_optimization_count > 0:
        return "optimized"
    return "none"


def _source_count(session: Session, post_id: uuid.UUID) -> int:
    return session.scalar(
        select(func.count()).select_from(PostSource).where(PostSource.post_id == post_id)
    ) or 0


def list_row(session: Session, post: Post) -> dict[str, Any]:
    return {
        "id": str(post.id),
        "title": post.title,
        "content_status": post.content_status,
        "content_class": post.content_class,
        "status": post.status,
        "ai_state": _derived_ai_state(post),
        "source_count": _source_count(session, post.id),
        "updated_at": post.updated_at.isoformat(),
        "created_at": post.created_at.isoformat(),
    }


def list_posts(
    session: Session,
    user_id: uuid.UUID,
    *,
    content_status: str | None = None,
    content_class: str | None = None,
    status: str | None = None,
    ai_state: str | None = None,
    search: str | None = None,
    include_inactive: bool = False,
    sort: str = "updated_desc",
    cursor: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    """Owner-scoped, filterable listing with counts and an offset cursor.

    Returns ``{items, next_cursor, total, counts_by_status}``. ``ai_state`` is a
    derived filter applied in Python (it is presentation-only, not a column).
    """
    base = select(Post).where(Post.user_id == user_id, Post.deleted_at.is_(None))
    if not include_inactive:
        base = base.where(Post.content_status.notin_(_ACTIVE_EXCLUDED))
    if content_status:
        base = base.where(Post.content_status == content_status)
    if content_class:
        base = base.where(Post.content_class == content_class)
    if status:
        base = base.where(Post.status == status)
    if search:
        like = f"%{search.strip()}%"
        base = base.where(or_(Post.title.ilike(like), Post.markdown.ilike(like)))

    order = {
        "updated_desc": Post.updated_at.desc(),
        "updated_asc": Post.updated_at.asc(),
        "created_desc": Post.created_at.desc(),
        "created_asc": Post.created_at.asc(),
    }.get(sort, Post.updated_at.desc())

    rows = list(session.scalars(base.order_by(order)).all())
    if ai_state:
        rows = [p for p in rows if _derived_ai_state(p) == ai_state]

    total = len(rows)
    page = rows[cursor : cursor + limit]
    next_cursor = cursor + limit if cursor + limit < total else None

    # Counts across the (unpaged, pre-ai_state) filtered set, grouped by status.
    counts: dict[str, int] = {}
    for p in rows:
        counts[p.content_status] = counts.get(p.content_status, 0) + 1

    return {
        "items": [list_row(session, p) for p in page],
        "next_cursor": next_cursor,
        "total": total,
        "counts_by_status": counts,
    }


# ---------------------------------------------------------------------------
# Triage (spec 005, US6, T117)
# ---------------------------------------------------------------------------


def _triage_reason(post: Post, now: datetime) -> str:
    """Why an item is in the triage backlog (first match wins)."""
    if post.latest_ai_status == "failed" or post.content_status == "pending_parse":
        return "failed"
    if post.content_class == "quick":
        return "quick"
    if (now - post.updated_at) > STALE_AFTER:
        return "stale"
    return "draft"


def _quick_preview(markdown: str, limit: int = 140) -> str:
    text = " ".join((markdown or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def triage_items(
    session: Session,
    user_id: uuid.UUID,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    """Triage backlog with a derived reason per item and reason counts."""
    now = datetime.now(UTC)
    rows = list(
        session.scalars(
            select(Post)
            .where(
                Post.user_id == user_id,
                Post.deleted_at.is_(None),
                Post.content_status.in_(_TRIAGE_STATUSES),
            )
            .order_by(Post.updated_at.desc())
        ).all()
    )
    items = []
    counts: dict[str, int] = {"quick": 0, "failed": 0, "stale": 0, "draft": 0}
    for p in rows:
        r = _triage_reason(p, now)
        counts[r] = counts.get(r, 0) + 1
        if reason and r != reason:
            continue
        items.append(
            {
                "id": str(p.id),
                "title": p.title,
                "reason": r,
                "content_class": p.content_class,
                "content_status": p.content_status,
                "preview": _quick_preview(p.markdown),
                "source_count": _source_count(session, p.id),
                "updated_at": p.updated_at.isoformat(),
            }
        )
    return {"items": items, "counts_by_reason": counts}
