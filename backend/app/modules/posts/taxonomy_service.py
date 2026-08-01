"""Taxonomy: category tree, tags, keywords, aliases and merges (spec 005, US8).

Categories form a bounded-depth tree; tags carry alias profiles; keywords track
synonyms and stop-words. Small merges run in one transaction; large merges run as
an idempotent background job writing a ``TaxonomyMerge`` audit row. Disabled items
stay resolvable for history. Implementation lands in T146–T149.
"""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationError
from app.models.blog import (
    PostCategoryProfile,
    PostKeyword,
    PostKeywordAlias,
    PostKeywordLink,
    PostTagAlias,
    PostTagProfile,
    TaxonomyMerge,
)
from app.models.foundation import ActivityLog, AsyncJob, Category, Tag
from app.models.posts import Post, PostTag

KINDS = {"category", "tag", "keyword"}
MAX_CATEGORY_DEPTH = 3
BACKGROUND_MERGE_THRESHOLD = 500


def _validate_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValidationError("invalid taxonomy kind", code="invalid_taxonomy_kind")


def _owned_parent(session: Session, user_id: uuid.UUID, parent_id: uuid.UUID) -> Category:
    parent = session.get(Category, parent_id)
    if parent is None or parent.user_id != user_id or parent.kind != "post":
        raise ValidationError("parent category not found", code="invalid_parent_category")
    return parent


def _category_depth(session: Session, user_id: uuid.UUID, category_id: uuid.UUID) -> int:
    depth, seen = 1, set()
    current: uuid.UUID | None = category_id
    while current:
        if current in seen:
            raise ValidationError("category cycle detected", code="category_cycle")
        seen.add(current)
        profile = session.get(PostCategoryProfile, current)
        if profile is None or profile.user_id != user_id:
            raise ValidationError("parent category not found", code="invalid_parent_category")
        current = profile.parent_category_id
        if current:
            depth += 1
    return depth


def _validate_parent(
    session: Session,
    user_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    *,
    item_id: uuid.UUID | None = None,
) -> None:
    if parent_id is None:
        return
    _owned_parent(session, user_id, parent_id)
    if parent_id == item_id:
        raise ValidationError("category cannot parent itself", code="category_cycle")
    current: uuid.UUID | None = parent_id
    while current:
        if current == item_id:
            raise ValidationError("category cycle detected", code="category_cycle")
        profile = session.get(PostCategoryProfile, current)
        current = profile.parent_category_id if profile else None
    if _category_depth(session, user_id, parent_id) >= MAX_CATEGORY_DEPTH:
        raise ValidationError("category depth exceeds 3", code="category_depth_exceeded")


def _check_alias_collisions(
    session: Session,
    user_id: uuid.UUID,
    kind: str,
    name: str,
    aliases: list[str],
    *,
    item_id: uuid.UUID | None = None,
) -> None:
    values = {name.casefold(), *(alias.casefold() for alias in aliases)}
    if len(values) != len(aliases) + 1:
        raise ConflictError("alias collides with canonical name", code="taxonomy_alias_collision")
    if kind == "tag":
        tags = session.scalars(select(Tag).where(Tag.user_id == user_id)).all()
        tag_aliases = session.scalars(
            select(PostTagAlias).where(PostTagAlias.user_id == user_id)
        ).all()
        collision = any(t.id != item_id and t.name.casefold() in values for t in tags) or any(
            a.tag_id != item_id and a.alias.casefold() in values for a in tag_aliases
        )
    else:
        keywords = session.scalars(select(PostKeyword).where(PostKeyword.user_id == user_id)).all()
        keyword_aliases = session.scalars(
            select(PostKeywordAlias).where(PostKeywordAlias.user_id == user_id)
        ).all()
        collision = any(
            k.id != item_id and k.canonical_text.casefold() in values for k in keywords
        ) or any(a.keyword_id != item_id and a.alias.casefold() in values for a in keyword_aliases)
    if collision:
        raise ConflictError(
            "taxonomy name or alias already exists", code="taxonomy_alias_collision"
        )


def create_item(
    session: Session,
    user_id: uuid.UUID,
    kind: str,
    *,
    name: str,
    description: str | None = None,
    parent_id: uuid.UUID | None = None,
    aliases: list[str] | None = None,
    color: str | None = None,
    enabled: bool = True,
    stop_word: bool = False,
) -> dict:
    _validate_kind(kind)
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValidationError("taxonomy name is required", code="invalid_taxonomy_name")
    aliases = list(dict.fromkeys(a.strip() for a in aliases or [] if a.strip()))

    if kind == "category":
        category_existing = session.scalar(
            select(Category).where(
                Category.user_id == user_id,
                Category.kind == "post",
                func.lower(Category.name) == cleaned_name.lower(),
            )
        )
        if category_existing is not None:
            raise ConflictError("category already exists", code="taxonomy_exists")
        _validate_parent(session, user_id, parent_id)
        category_item = Category(id=uuid.uuid4(), user_id=user_id, name=cleaned_name, kind="post")
        session.add(category_item)
        session.flush()
        session.add(
            PostCategoryProfile(
                category_id=category_item.id,
                user_id=user_id,
                parent_category_id=parent_id,
                description=description,
                enabled=enabled,
            )
        )
        result_id = category_item.id
    elif kind == "tag":
        _check_alias_collisions(session, user_id, kind, cleaned_name, aliases)
        tag_existing = session.scalar(
            select(Tag).where(Tag.user_id == user_id, func.lower(Tag.name) == cleaned_name.lower())
        )
        if tag_existing is not None:
            raise ConflictError("tag already exists", code="taxonomy_exists")
        if any(len(alias) > 64 for alias in aliases):
            raise ValidationError("tag alias is too long", code="invalid_taxonomy_alias")
        tag_item = Tag(id=uuid.uuid4(), user_id=user_id, name=cleaned_name)
        session.add(tag_item)
        session.flush()
        session.add(
            PostTagProfile(
                tag_id=tag_item.id,
                user_id=user_id,
                color=color,
                description=description,
                enabled=enabled,
            )
        )
        session.add_all(
            PostTagAlias(id=uuid.uuid4(), user_id=user_id, tag_id=tag_item.id, alias=alias)
            for alias in aliases
        )
        result_id = tag_item.id
    else:
        _check_alias_collisions(session, user_id, kind, cleaned_name, aliases)
        keyword_existing = session.scalar(
            select(PostKeyword).where(
                PostKeyword.user_id == user_id,
                func.lower(PostKeyword.canonical_text) == cleaned_name.lower(),
            )
        )
        if keyword_existing is not None:
            raise ConflictError("keyword already exists", code="taxonomy_exists")
        keyword_item = PostKeyword(
            id=uuid.uuid4(),
            user_id=user_id,
            canonical_text=cleaned_name,
            description=description,
            enabled=enabled,
            is_stop_word=stop_word,
        )
        session.add(keyword_item)
        session.flush()
        session.add_all(
            PostKeywordAlias(
                id=uuid.uuid4(), user_id=user_id, keyword_id=keyword_item.id, alias=alias
            )
            for alias in aliases
        )
        result_id = keyword_item.id
    session.flush()
    return get_item(session, user_id, kind, result_id)


def update_item(
    session: Session,
    user_id: uuid.UUID,
    kind: str,
    item_id: uuid.UUID,
    **changes: object,
) -> dict:
    current = get_item(session, user_id, kind, item_id)
    raw_name = changes.get("name")
    name = str(current["name"] if raw_name is None else raw_name).strip()
    if not name:
        raise ValidationError("taxonomy name is required", code="invalid_taxonomy_name")
    raw_aliases = changes.get("aliases", current["aliases"])
    if raw_aliases is not None and not isinstance(raw_aliases, list):
        raise ValidationError("aliases must be a list", code="invalid_taxonomy_alias")
    aliases = list(
        dict.fromkeys(str(alias).strip() for alias in (raw_aliases or []) if str(alias).strip())
    )
    if kind == "category":
        category = session.get(Category, item_id)
        category_profile = session.get(PostCategoryProfile, item_id)
        if category is None or category_profile is None:
            raise ValidationError("taxonomy item not found", code="taxonomy_not_found")
        parent_id = cast(
            uuid.UUID | None,
            changes.get("parent_id", category_profile.parent_category_id),
        )
        _validate_parent(session, user_id, parent_id, item_id=item_id)
        category.name = name
        category_profile.parent_category_id = parent_id
        category_profile.description = cast(
            str | None, changes.get("description", category_profile.description)
        )
        category_profile.enabled = bool(changes.get("enabled", category_profile.enabled))
    elif kind == "tag":
        _check_alias_collisions(session, user_id, kind, name, aliases, item_id=item_id)
        tag = session.get(Tag, item_id)
        tag_profile = session.get(PostTagProfile, item_id)
        if tag is None or tag_profile is None:
            raise ValidationError("taxonomy item not found", code="taxonomy_not_found")
        tag.name = name
        tag_profile.description = cast(
            str | None, changes.get("description", tag_profile.description)
        )
        tag_profile.color = cast(str | None, changes.get("color", tag_profile.color))
        tag_profile.enabled = bool(changes.get("enabled", tag_profile.enabled))
        session.execute(delete(PostTagAlias).where(PostTagAlias.tag_id == item_id))
        session.add_all(
            PostTagAlias(id=uuid.uuid4(), user_id=user_id, tag_id=item_id, alias=a) for a in aliases
        )
    else:
        _check_alias_collisions(session, user_id, kind, name, aliases, item_id=item_id)
        keyword = session.get(PostKeyword, item_id)
        if keyword is None:
            raise ValidationError("taxonomy item not found", code="taxonomy_not_found")
        keyword.canonical_text = name
        keyword.description = cast(str | None, changes.get("description", keyword.description))
        keyword.enabled = bool(changes.get("enabled", keyword.enabled))
        keyword.is_stop_word = bool(changes.get("stop_word", keyword.is_stop_word))
        session.execute(delete(PostKeywordAlias).where(PostKeywordAlias.keyword_id == item_id))
        session.add_all(
            PostKeywordAlias(id=uuid.uuid4(), user_id=user_id, keyword_id=item_id, alias=a)
            for a in aliases
        )
    session.flush()
    return get_item(session, user_id, kind, item_id)


def resolve_name(session: Session, user_id: uuid.UUID, kind: str, value: str) -> dict | None:
    needle = value.strip().casefold()
    for item in list_items(session, user_id, kind, enabled=True):
        if item["name"].casefold() == needle or any(
            a.casefold() == needle for a in item["aliases"]
        ):
            return item
    return None


def normalize_recommendations(
    session: Session, user_id: uuid.UUID, kind: str, values: list[str]
) -> list[dict]:
    resolved, seen = [], set()
    for value in values:
        item = resolve_name(session, user_id, kind, value)
        if item and not item["stop_word"] and item["id"] not in seen:
            resolved.append(item)
            seen.add(item["id"])
    return resolved


def get_item(session: Session, user_id: uuid.UUID, kind: str, item_id: uuid.UUID) -> dict:
    items = list_items(session, user_id, kind, item_id=item_id)
    if not items:
        raise ValidationError("taxonomy item not found", code="taxonomy_not_found")
    return items[0]


def list_items(
    session: Session,
    user_id: uuid.UUID,
    kind: str,
    *,
    enabled: bool | None = None,
    item_id: uuid.UUID | None = None,
) -> list[dict]:
    _validate_kind(kind)
    if kind == "category":
        category_stmt = (
            select(Category, PostCategoryProfile, func.count(Post.id))
            .join(PostCategoryProfile, PostCategoryProfile.category_id == Category.id)
            .outerjoin(Post, Post.category_id == Category.id)
            .where(Category.user_id == user_id, Category.kind == "post")
            .group_by(Category.id, PostCategoryProfile.category_id)
            .order_by(func.lower(Category.name))
        )
        if enabled is not None:
            category_stmt = category_stmt.where(PostCategoryProfile.enabled == enabled)
        if item_id is not None:
            category_stmt = category_stmt.where(Category.id == item_id)
        return [
            {
                "id": str(item.id),
                "kind": kind,
                "name": item.name,
                "description": profile.description,
                "parent_id": str(profile.parent_category_id)
                if profile.parent_category_id
                else None,
                "aliases": [],
                "color": None,
                "enabled": profile.enabled,
                "stop_word": False,
                "usage_count": count,
            }
            for item, profile, count in session.execute(category_stmt)
        ]
    if kind == "tag":
        tag_stmt = (
            select(Tag, PostTagProfile, func.count(PostTag.post_id))
            .join(PostTagProfile, PostTagProfile.tag_id == Tag.id)
            .outerjoin(PostTag, PostTag.tag_id == Tag.id)
            .where(Tag.user_id == user_id)
            .group_by(Tag.id, PostTagProfile.tag_id)
            .order_by(func.lower(Tag.name))
        )
        if enabled is not None:
            tag_stmt = tag_stmt.where(PostTagProfile.enabled == enabled)
        if item_id is not None:
            tag_stmt = tag_stmt.where(Tag.id == item_id)
        tag_rows = session.execute(tag_stmt).all()
        return [
            {
                "id": str(item.id),
                "kind": kind,
                "name": item.name,
                "description": profile.description,
                "parent_id": None,
                "aliases": list(
                    session.scalars(
                        select(PostTagAlias.alias).where(PostTagAlias.tag_id == item.id)
                    )
                ),
                "color": profile.color,
                "enabled": profile.enabled,
                "stop_word": False,
                "usage_count": count,
            }
            for item, profile, count in tag_rows
        ]
    keyword_stmt = (
        select(PostKeyword, func.count(PostKeywordLink.post_id))
        .outerjoin(PostKeywordLink, PostKeywordLink.keyword_id == PostKeyword.id)
        .where(PostKeyword.user_id == user_id)
        .group_by(PostKeyword.id)
        .order_by(func.lower(PostKeyword.canonical_text))
    )
    if enabled is not None:
        keyword_stmt = keyword_stmt.where(PostKeyword.enabled == enabled)
    if item_id is not None:
        keyword_stmt = keyword_stmt.where(PostKeyword.id == item_id)
    keyword_rows = session.execute(keyword_stmt).all()
    return [
        {
            "id": str(item.id),
            "kind": kind,
            "name": item.canonical_text,
            "description": item.description,
            "parent_id": None,
            "aliases": list(
                session.scalars(
                    select(PostKeywordAlias.alias).where(PostKeywordAlias.keyword_id == item.id)
                )
            ),
            "color": None,
            "enabled": item.enabled,
            "stop_word": item.is_stop_word,
            "usage_count": count,
        }
        for item, count in keyword_rows
    ]


def usage_count(session: Session, user_id: uuid.UUID, kind: str, item_id: uuid.UUID) -> int:
    item = get_item(session, user_id, kind, item_id)
    return int(item["usage_count"])


def _disable_item(session: Session, kind: str, item_id: uuid.UUID) -> None:
    if kind == "category":
        category_profile = session.get(PostCategoryProfile, item_id)
        if category_profile is None:
            raise ValidationError("taxonomy item not found", code="taxonomy_not_found")
        category_profile.enabled = False
    elif kind == "tag":
        tag_profile = session.get(PostTagProfile, item_id)
        if tag_profile is None:
            raise ValidationError("taxonomy item not found", code="taxonomy_not_found")
        tag_profile.enabled = False
    else:
        item = session.get(PostKeyword, item_id)
        if item is None:
            raise ValidationError("taxonomy item not found", code="taxonomy_not_found")
        item.enabled = False


def merge_items(
    session: Session,
    user_id: uuid.UUID,
    kind: str,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    *,
    merge_id: uuid.UUID | None = None,
) -> dict:
    _validate_kind(kind)
    if source_id == target_id:
        raise ConflictError("source and target must differ", code="taxonomy_merge_self")
    get_item(session, user_id, kind, source_id)
    get_item(session, user_id, kind, target_id)
    existing = session.scalar(
        select(TaxonomyMerge).where(
            TaxonomyMerge.user_id == user_id,
            TaxonomyMerge.kind == kind,
            TaxonomyMerge.source_id == source_id,
            TaxonomyMerge.target_id == target_id,
            TaxonomyMerge.status == "completed",
        )
    )
    if existing:
        return get_item(session, user_id, kind, target_id)
    audit = session.get(TaxonomyMerge, merge_id) if merge_id else None
    if audit is None:
        audit = TaxonomyMerge(
            id=merge_id or uuid.uuid4(),
            user_id=user_id,
            kind=kind,
            source_id=source_id,
            target_id=target_id,
            status="processing",
        )
        session.add(audit)
    affected = usage_count(session, user_id, kind, source_id)
    if kind == "category":
        # Redirecting a category into one of its descendants would turn the
        # target into its own parent when source children are reassigned.
        current: uuid.UUID | None = target_id
        while current:
            if current == source_id:
                raise ConflictError(
                    "category cannot merge into its descendant",
                    code="category_merge_cycle",
                )
            profile = session.get(PostCategoryProfile, current)
            current = profile.parent_category_id if profile else None
        session.execute(
            update(Post)
            .where(Post.user_id == user_id, Post.category_id == source_id)
            .values(category_id=target_id)
        )
        session.execute(
            update(PostCategoryProfile)
            .where(
                PostCategoryProfile.user_id == user_id,
                PostCategoryProfile.parent_category_id == source_id,
            )
            .values(parent_category_id=target_id)
        )
    elif kind == "tag":
        post_ids = session.scalars(
            select(PostTag.post_id).where(PostTag.user_id == user_id, PostTag.tag_id == source_id)
        ).all()
        target_posts = set(
            session.scalars(
                select(PostTag.post_id).where(
                    PostTag.user_id == user_id, PostTag.tag_id == target_id
                )
            ).all()
        )
        session.add_all(
            PostTag(post_id=post_id, tag_id=target_id, user_id=user_id)
            for post_id in post_ids
            if post_id not in target_posts
        )
        session.execute(
            delete(PostTag).where(PostTag.user_id == user_id, PostTag.tag_id == source_id)
        )
    else:
        links = session.scalars(
            select(PostKeywordLink).where(
                PostKeywordLink.user_id == user_id,
                PostKeywordLink.keyword_id == source_id,
            )
        ).all()
        target_posts = set(
            session.scalars(
                select(PostKeywordLink.post_id).where(
                    PostKeywordLink.user_id == user_id,
                    PostKeywordLink.keyword_id == target_id,
                )
            ).all()
        )
        session.add_all(
            PostKeywordLink(
                post_id=link.post_id,
                keyword_id=target_id,
                user_id=user_id,
                source=link.source,
                weight=link.weight,
            )
            for link in links
            if link.post_id not in target_posts
        )
        session.execute(
            delete(PostKeywordLink).where(
                PostKeywordLink.user_id == user_id,
                PostKeywordLink.keyword_id == source_id,
            )
        )
    _disable_item(session, kind, source_id)
    audit.affected_count = affected
    audit.status = "completed"
    session.add(
        ActivityLog(
            user_id=user_id,
            actor_type="user",
            action="blog.taxonomy_merged",
            entity_type=f"taxonomy_{kind}",
            entity_id=target_id,
            after_summary_json={"source_id": str(source_id), "affected_count": affected},
        )
    )
    session.flush()
    return get_item(session, user_id, kind, target_id)


def request_merge(
    session: Session,
    user_id: uuid.UUID,
    kind: str,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> tuple[str, dict | object]:
    existing = session.scalar(
        select(TaxonomyMerge)
        .where(
            TaxonomyMerge.user_id == user_id,
            TaxonomyMerge.kind == kind,
            TaxonomyMerge.source_id == source_id,
            TaxonomyMerge.target_id == target_id,
            TaxonomyMerge.status.in_(("pending", "processing")),
        )
        .order_by(TaxonomyMerge.created_at.desc())
    )
    if existing and existing.async_job_id:
        job = session.get(AsyncJob, existing.async_job_id)
        if job is not None:
            return "queued", job
    affected = usage_count(session, user_id, kind, source_id)
    get_item(session, user_id, kind, target_id)
    if affected < BACKGROUND_MERGE_THRESHOLD:
        return "completed", merge_items(session, user_id, kind, source_id, target_id)
    from app.modules.jobs import service as jobs_service
    from app.services.outbox.publisher import append_event

    audit = TaxonomyMerge(
        id=uuid.uuid4(),
        user_id=user_id,
        kind=kind,
        source_id=source_id,
        target_id=target_id,
        affected_count=affected,
        status="pending",
    )
    session.add(audit)
    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="blog.taxonomy_merge",
        entity_type="taxonomy_merge",
        entity_id=audit.id,
        idempotency_key=f"taxonomy:{kind}:{source_id}:{target_id}",
    )
    audit.async_job_id = job.id
    append_event(
        session,
        event_type="blog.taxonomy_merge",
        aggregate_type="taxonomy_merge",
        aggregate_id=audit.id,
        routing_key="blog.taxonomy.merge",
        payload={"merge_id": str(audit.id)},
        user_id=user_id,
    )
    return "queued", job


def request_keyword_recompute(session: Session, user_id: uuid.UUID) -> object:
    from app.modules.jobs import service as jobs_service
    from app.services.outbox.publisher import append_event

    active = session.scalar(
        select(AsyncJob)
        .where(
            AsyncJob.user_id == user_id,
            AsyncJob.job_type == "blog.keyword_recompute",
            AsyncJob.status.in_(("pending", "queued", "processing")),
        )
        .order_by(AsyncJob.created_at.desc())
    )
    if active is not None:
        return active
    invocation_id = uuid.uuid4()
    job = jobs_service.create_job(
        session,
        user_id=user_id,
        job_type="blog.keyword_recompute",
        entity_type="user",
        entity_id=user_id,
        idempotency_key=f"keyword-recompute:{user_id}:{invocation_id}",
    )
    append_event(
        session,
        event_type="blog.keyword_recompute",
        aggregate_type="user",
        aggregate_id=user_id,
        routing_key="blog.keyword.recompute",
        payload={"job_id": str(job.id), "user_id": str(user_id)},
        user_id=user_id,
    )
    return job
