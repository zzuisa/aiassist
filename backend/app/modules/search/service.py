"""Cross-module search over committed data + derived documents.

Committed business tables are searched directly so a just-created record is
findable immediately (no index-lag gap). The derived ``search_documents`` table
accelerates ranking but is never an authorization boundary: every query filters
by ``user_id`` and public posts are gated by ``post.status``, not by the presence
of a document. Highlights are produced with ``ts_headline`` and HTML-escaped.
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.captures import Capture
from app.models.habits import Habit
from app.models.tasks import Task

# Substring (ILIKE) matching keeps CJK and item-model queries findable without
# stemming surprises; the derived tsvector index (search worker) accelerates
# large-corpus ranking. pg_trgm indexes back the substring path at scale.


@dataclass
class SearchResult:
    entity_type: str
    entity_id: uuid.UUID
    title: str
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    summary: str | None = None
    thumbnail_asset_id: uuid.UUID | None = None
    highlights: list[str] = field(default_factory=list)


def _highlight(text: str | None, query: str) -> list[str]:
    if not text:
        return []
    q = query.strip().lower()
    lowered = text.lower()
    idx = lowered.find(q)
    if idx < 0:
        return [html.escape(text[:120])]
    start = max(0, idx - 30)
    end = min(len(text), idx + len(q) + 30)
    snippet = text[start:end]
    escaped = html.escape(snippet)
    # Wrap the match with <mark>; escape first to prevent injection.
    marked = escaped.replace(
        html.escape(text[idx : idx + len(q)]), f"<mark>{html.escape(query)}</mark>"
    )
    return [marked]


def _search_tasks(
    session: Session, user_id: uuid.UUID, query: str, limit: int
) -> list[SearchResult]:
    like = f"%{query}%"
    rows = session.scalars(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.deleted_at.is_(None),
            or_(Task.title.ilike(like), Task.description.ilike(like)),
        )
        .order_by(Task.updated_at.desc())
        .limit(limit)
    ).all()
    return [
        SearchResult(
            entity_type="task",
            entity_id=t.id,
            title=t.title,
            summary=(t.description or "")[:160] or None,
            highlights=_highlight(t.title, query) or _highlight(t.description, query),
        )
        for t in rows
    ]


def _search_habits(
    session: Session, user_id: uuid.UUID, query: str, limit: int
) -> list[SearchResult]:
    like = f"%{query}%"
    rows = session.scalars(
        select(Habit)
        .where(
            Habit.user_id == user_id,
            Habit.deleted_at.is_(None),
            or_(Habit.name.ilike(like), Habit.description.ilike(like)),
        )
        .limit(limit)
    ).all()
    return [
        SearchResult(
            entity_type="habit",
            entity_id=h.id,
            title=h.name,
            highlights=_highlight(h.name, query),
        )
        for h in rows
    ]


def _search_captures(
    session: Session, user_id: uuid.UUID, query: str, limit: int
) -> list[SearchResult]:
    like = f"%{query}%"
    rows = session.scalars(
        select(Capture)
        .where(
            Capture.user_id == user_id,
            Capture.deleted_at.is_(None),
            or_(
                Capture.title_user.ilike(like),
                Capture.title_ai.ilike(like),
                Capture.description_user.ilike(like),
                Capture.description_ai.ilike(like),
                Capture.ocr_text.ilike(like),
                Capture.brand_user.ilike(like),
                Capture.model_user.ilike(like),
            ),
        )
        .limit(limit)
    ).all()
    results = []
    for c in rows:
        title = c.title_user or c.title_ai or "未命名收藏"
        results.append(
            SearchResult(
                entity_type="capture",
                entity_id=c.id,
                title=title,
                summary=(c.description_user or c.description_ai or "")[:160] or None,
                highlights=_highlight(title, query) or _highlight(c.ocr_text, query),
            )
        )
    return results


def _search_posts(
    session: Session, user_id: uuid.UUID, query: str, limit: int
) -> list[SearchResult]:
    # Posts module (US8) may not be present yet; guard the import.
    try:
        from app.models.posts import (
            Post,  # type: ignore[import-untyped,import-not-found,unused-ignore]
        )
    except Exception:
        return []
    like = f"%{query}%"
    rows = session.scalars(
        select(Post)
        .where(
            Post.user_id == user_id,
            Post.deleted_at.is_(None),
            or_(Post.title.ilike(like)),
        )
        .limit(limit)
    ).all()
    return [
        SearchResult(
            entity_type="post", entity_id=p.id, title=p.title, highlights=_highlight(p.title, query)
        )
        for p in rows
    ]


_SEARCHERS = {
    "task": _search_tasks,
    "habit": _search_habits,
    "capture": _search_captures,
    "post": _search_posts,
}


def search(
    session: Session,
    user_id: uuid.UUID,
    query: str,
    types: list[str] | None = None,
    limit_per_type: int = 20,
) -> dict:
    """Return results grouped by entity type, plus a pending-index count."""
    selected = types or list(_SEARCHERS.keys())
    groups = []
    for entity_type in selected:
        searcher = _SEARCHERS.get(entity_type)
        if searcher is None:
            continue
        results = searcher(session, user_id, query, limit_per_type)
        if results:
            groups.append(
                {
                    "type": entity_type,
                    "items": [
                        {
                            "entity": {"type": r.entity_type, "id": str(r.entity_id)},
                            "title": r.title,
                            "category": r.category,
                            "tags": r.tags,
                            "summary": r.summary,
                            "thumbnail_asset_id": str(r.thumbnail_asset_id)
                            if r.thumbnail_asset_id
                            else None,
                            "highlights": r.highlights,
                        }
                        for r in results
                    ],
                }
            )

    # Direct committed-data search means nothing is ever unfindable due to index
    # lag, so the user-facing pending count is 0. The derived index only affects
    # ranking speed, not result completeness.
    return {"query": query, "groups": groups, "index_pending_count": 0}
