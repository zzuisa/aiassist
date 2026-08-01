"""Read-side queries: listing, triage, search, timeline, word cloud (spec 005).

Owner-scoped listing with combinable filters and derived AI/source summaries;
triage projections (quick/failed/stale/draft). Search / timeline / word-cloud land
in later user stories. Implemented here: T116 (list) and T117 (triage).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import cast, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select
from sqlalchemy.sql.sqltypes import Text

from app.core.errors import ValidationError
from app.models.blog import PostKeyword, PostKeywordLink, PostSource, PostWordCloudSnapshot
from app.models.foundation import AsyncJob, Category, Tag
from app.models.posts import Post, PostTag

# content_status values that mean "not yet an organized article" — the triage
# backlog. 'quick' captures also surface here via content_class.
_TRIAGE_STATUSES = ("pending_capture", "pending_parse", "triage", "draft")
_ACTIVE_EXCLUDED = ("archived", "discarded")

# A draft/triage item untouched for this long is considered stale.
STALE_AFTER = timedelta(days=14)
WORD_CLOUD_FILTER_KEYS = ("year", "month", "from", "to", "content_class", "category_id")


def normalize_word_cloud_filter(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return a stable, bounded filter representation used for hashing and jobs."""
    normalized: dict[str, Any] = {}
    for key in WORD_CLOUD_FILTER_KEYS:
        value = (raw or {}).get(key)
        if value is None or value == "":
            continue
        try:
            if key in {"year", "month"}:
                numeric_value = int(value)
                if key == "year" and not 1970 <= numeric_value <= 2200:
                    raise ValidationError(
                        "invalid word-cloud year", code="invalid_word_cloud_filter"
                    )
                if key == "month" and not 1 <= numeric_value <= 12:
                    raise ValidationError(
                        "invalid word-cloud month", code="invalid_word_cloud_filter"
                    )
                value = numeric_value
            elif key == "category_id":
                value = str(uuid.UUID(str(value)))
            elif key in {"from", "to"}:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                value = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
        except ValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"invalid word-cloud filter field: {key}", code="invalid_word_cloud_filter"
            ) from exc
        if key not in {"year", "month", "category_id"}:
            value = str(value).strip()
        normalized[key] = value
    return normalized


def word_cloud_filter_hash(filters: dict[str, Any]) -> str:
    payload = json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def serialize_word_cloud(snapshot: PostWordCloudSnapshot) -> dict[str, Any]:
    return {
        "id": str(snapshot.id),
        "source_kind": snapshot.source_kind,
        "filter": snapshot.filter_json,
        "terms": snapshot.terms_json,
        "article_count": snapshot.article_count,
        "status": snapshot.status,
        "generated_at": snapshot.generated_at.isoformat() if snapshot.generated_at else None,
        "error_code": snapshot.error_code,
    }


def get_word_cloud_snapshot(
    session: Session, user_id: uuid.UUID, source_kind: str, filters: dict[str, Any] | None
) -> PostWordCloudSnapshot | None:
    normalized = normalize_word_cloud_filter(filters)
    return session.scalar(
        select(PostWordCloudSnapshot).where(
            PostWordCloudSnapshot.user_id == user_id,
            PostWordCloudSnapshot.source_kind == source_kind,
            PostWordCloudSnapshot.filter_hash == word_cloud_filter_hash(normalized),
        )
    )


def request_word_cloud_rebuild(
    session: Session,
    user_id: uuid.UUID,
    source_kind: str,
    filters: dict[str, Any] | None,
    *,
    min_frequency: int | None = None,
    max_terms: int | None = None,
) -> tuple[AsyncJob, PostWordCloudSnapshot | None]:
    if source_kind not in {"tag", "keyword"}:
        raise ValidationError("unsupported word-cloud source", code="invalid_word_cloud_source")
    from app.modules.jobs import service as jobs_service
    from app.modules.posts import settings_service
    from app.services.outbox.publisher import append_event

    normalized = normalize_word_cloud_filter(filters)
    snapshot = get_word_cloud_snapshot(session, user_id, source_kind, normalized)
    previous = snapshot if snapshot and snapshot.generated_at else None
    if snapshot and snapshot.async_job_id:
        active = session.get(AsyncJob, snapshot.async_job_id)
        if active and active.status in {"pending", "queued", "processing"}:
            return active, previous
    if snapshot is None:
        snapshot = PostWordCloudSnapshot(
            id=uuid.uuid4(),
            user_id=user_id,
            source_kind=source_kind,
            filter_json=normalized,
            filter_hash=word_cloud_filter_hash(normalized),
            terms_json=[],
            status="stale",
        )
        session.add(snapshot)
        session.flush()
    settings = settings_service.settings_to_dict(settings_service.get_settings(session, user_id))[
        "word_cloud"
    ]
    minimum = min_frequency or int(settings["min_term_count"])
    maximum = max_terms or int(settings["max_terms"])
    minimum = min(max(minimum, 1), 100_000)
    maximum = min(max(maximum, 1), 500)
    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="blog.wordcloud",
        entity_type="word_cloud_snapshot",
        entity_id=snapshot.id,
        idempotency_key=f"wordcloud:{snapshot.id}:{uuid.uuid4()}",
    )
    snapshot.async_job_id = job.id
    snapshot.status = "stale"
    snapshot.error_code = None
    append_event(
        session,
        event_type="blog.wordcloud",
        aggregate_type="word_cloud_snapshot",
        aggregate_id=snapshot.id,
        routing_key="blog.wordcloud.rebuild",
        payload={
            "snapshot_id": str(snapshot.id),
            "min_frequency": minimum,
            "max_terms": maximum,
        },
        user_id=user_id,
    )
    return job, previous


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
    return (
        session.scalar(
            select(func.count()).select_from(PostSource).where(PostSource.post_id == post_id)
        )
        or 0
    )


def list_row(session: Session, post: Post) -> dict[str, Any]:
    return {
        "id": str(post.id),
        "title": post.title,
        "content_status": post.content_status,
        "content_class": post.content_class,
        "category_id": str(post.category_id) if post.category_id else None,
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
    category_id: uuid.UUID | None = None,
    tag_id: uuid.UUID | None = None,
    keyword_id: uuid.UUID | None = None,
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
    if category_id:
        base = base.where(Post.category_id == category_id)
    if tag_id:
        base = base.where(
            exists(
                select(1).where(
                    PostTag.post_id == Post.id,
                    PostTag.user_id == user_id,
                    PostTag.tag_id == tag_id,
                )
            )
        )
    if keyword_id:
        base = base.where(
            exists(
                select(1).where(
                    PostKeywordLink.post_id == Post.id,
                    PostKeywordLink.user_id == user_id,
                    PostKeywordLink.keyword_id == keyword_id,
                )
            )
        )
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


# ---------------------------------------------------------------------------
# US7 search and timeline (T127/T132/T135)
# ---------------------------------------------------------------------------


def _contains(value: object, query: str) -> bool:
    return query.casefold() in str(value or "").casefold()


def _search_snippet(value: object, query: str, limit: int = 180) -> str | None:
    text = str(value or "")
    if not text:
        return None
    lowered = text.casefold()
    index = lowered.find(query.casefold())
    if index < 0:
        return text[:limit]
    start = max(0, index - 60)
    end = min(len(text), index + len(query) + 100)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _post_search_base(
    user_id: uuid.UUID,
    query: str,
    *,
    content_class: str | None = None,
    category_id: uuid.UUID | None = None,
) -> Select:
    like = f"%{query.strip()}%"
    source_match = exists(
        select(1)
        .select_from(PostSource)
        .where(
            PostSource.post_id == Post.id,
            PostSource.user_id == user_id,
            or_(
                PostSource.original_url.ilike(like),
                PostSource.original_title.ilike(like),
                PostSource.original_text.ilike(like),
                PostSource.user_note.ilike(like),
            ),
        )
    )
    tag_match = exists(
        select(1)
        .select_from(PostTag)
        .join(Tag, Tag.id == PostTag.tag_id)
        .where(
            PostTag.post_id == Post.id,
            PostTag.user_id == user_id,
            Tag.user_id == user_id,
            Tag.name.ilike(like),
        )
    )
    category_match = exists(
        select(1)
        .select_from(Category)
        .where(
            Category.id == Post.category_id,
            Category.user_id == user_id,
            Category.name.ilike(like),
        )
    )
    keyword_match = exists(
        select(1)
        .select_from(PostKeywordLink)
        .join(PostKeyword, PostKeyword.id == PostKeywordLink.keyword_id)
        .where(
            PostKeywordLink.post_id == Post.id,
            PostKeywordLink.user_id == user_id,
            PostKeyword.user_id == user_id,
            PostKeyword.canonical_text.ilike(like),
        )
    )
    base = select(Post).where(
        Post.user_id == user_id,
        Post.deleted_at.is_(None),
        or_(
            Post.title.ilike(like),
            Post.subtitle.ilike(like),
            Post.summary.ilike(like),
            Post.markdown.ilike(like),
            Post.location_text.ilike(like),
            Post.project_text.ilike(like),
            cast(Post.structured_data_json, Text).ilike(like),
            source_match,
            tag_match,
            category_match,
            keyword_match,
        ),
    )
    if content_class:
        base = base.where(Post.content_class == content_class)
    if category_id:
        base = base.where(Post.category_id == category_id)
    return base


def _post_search_row(session: Session, post: Post, query: str) -> dict[str, Any]:
    category = None
    if post.category_id:
        category = session.scalar(
            select(Category.name).where(
                Category.id == post.category_id,
                Category.user_id == post.user_id,
            )
        )
    tags = list(
        session.scalars(
            select(Tag.name)
            .join(PostTag, PostTag.tag_id == Tag.id)
            .where(PostTag.post_id == post.id, PostTag.user_id == post.user_id)
            .order_by(Tag.name)
        ).all()
    )
    sources = list(
        session.scalars(
            select(PostSource).where(
                PostSource.post_id == post.id,
                PostSource.user_id == post.user_id,
            )
        ).all()
    )
    keywords = list(
        session.scalars(
            select(PostKeyword.canonical_text)
            .join(PostKeywordLink, PostKeywordLink.keyword_id == PostKeyword.id)
            .where(
                PostKeywordLink.post_id == post.id,
                PostKeywordLink.user_id == post.user_id,
                PostKeyword.user_id == post.user_id,
            )
            .order_by(PostKeyword.canonical_text)
        ).all()
    )
    fields: dict[str, object] = {
        "title": post.title,
        "subtitle": post.subtitle,
        "summary": post.summary,
        "markdown": post.markdown,
        "location": post.location_text,
        "project": post.project_text,
        "structured_data": post.structured_data_json,
        "category": category,
        "tags": " ".join(tags),
        "keywords": " ".join(keywords),
        "source": " ".join(
            str(value or "")
            for source in sources
            for value in (
                source.original_url,
                source.original_title,
                source.original_text,
                source.user_note,
            )
        ),
    }
    matched_fields = [name for name, value in fields.items() if _contains(value, query)]
    snippet = next(
        (_search_snippet(value, query) for value in fields.values() if _contains(value, query)),
        None,
    )
    return {
        "id": str(post.id),
        "title": post.title,
        "summary": post.summary,
        "content_class": post.content_class,
        "category_id": str(post.category_id) if post.category_id else None,
        "category": category,
        "tags": tags,
        "content_status": post.content_status,
        "status": post.status,
        "matched_fields": matched_fields,
        "highlight": snippet,
        "occurred_at": post.occurred_at.isoformat() if post.occurred_at else None,
        "updated_at": post.updated_at.isoformat(),
    }


def search_posts(
    session: Session,
    user_id: uuid.UUID,
    query: str,
    *,
    content_class: str | None = None,
    category_id: uuid.UUID | None = None,
    ai_state: str | None = None,
    cursor: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    """Search committed Post fields directly, independent of index refresh."""
    normalized = query.strip()
    if not normalized:
        return {"query": "", "items": [], "next_cursor": None, "total": 0}
    base = _post_search_base(
        user_id, normalized, content_class=content_class, category_id=category_id
    )
    rows = list(session.scalars(base.order_by(Post.updated_at.desc(), Post.id.desc())).all())
    if ai_state:
        rows = [post for post in rows if _derived_ai_state(post) == ai_state]
    page = rows[cursor : cursor + limit]
    return {
        "query": normalized,
        "items": [_post_search_row(session, post, normalized) for post in page],
        "next_cursor": cursor + limit if cursor + limit < len(rows) else None,
        "total": len(rows),
    }


def timeline_posts(
    session: Session,
    user_id: uuid.UUID,
    *,
    year: int | None = None,
    month: int | None = None,
    content_class: str | None = None,
    category_id: uuid.UUID | None = None,
    cursor: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    """Return owner-scoped posts ordered by occurred_at with creation fallback."""
    time_value = func.coalesce(Post.occurred_at, Post.created_at)
    base = select(Post).where(Post.user_id == user_id, Post.deleted_at.is_(None))
    if content_class:
        base = base.where(Post.content_class == content_class)
    if category_id:
        base = base.where(Post.category_id == category_id)
    if year:
        start = datetime(year, month or 1, 1, tzinfo=UTC)
        if month:
            end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=UTC)
        else:
            end = datetime(year + 1, 1, 1, tzinfo=UTC)
        base = base.where(time_value >= start, time_value < end)
    rows = list(session.scalars(base.order_by(time_value.desc(), Post.id.desc())).all())
    page = rows[cursor : cursor + limit]
    items = [
        {
            "id": str(post.id),
            "title": post.title,
            "summary": post.summary,
            "content_class": post.content_class,
            "category_id": str(post.category_id) if post.category_id else None,
            "status": post.status,
            "content_status": post.content_status,
            "time": (post.occurred_at or post.created_at).isoformat(),
            "time_basis": "occurred_at" if post.occurred_at else "created_at",
        }
        for post in page
    ]
    return {
        "items": items,
        "next_cursor": cursor + limit if cursor + limit < len(rows) else None,
        "total": len(rows),
        "time_basis": "occurred_at_or_created_at",
    }
