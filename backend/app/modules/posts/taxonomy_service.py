"""Taxonomy: category tree, tags, keywords, aliases and merges (spec 005, US8).

Categories form a bounded-depth tree; tags carry alias profiles; keywords track
synonyms and stop-words. Small merges run in one transaction; large merges run as
an idempotent background job writing a ``TaxonomyMerge`` audit row. Disabled items
stay resolvable for history. Implementation lands in T146–T149.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationError
from app.models.blog import (
    PostCategoryProfile,
    PostKeyword,
    PostKeywordAlias,
    PostKeywordLink,
    PostTagAlias,
    PostTagProfile,
)
from app.models.foundation import Category, Tag
from app.models.posts import Post, PostTag

KINDS = {"category", "tag", "keyword"}


def _validate_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ValidationError("invalid taxonomy kind", code="invalid_taxonomy_kind")


def _owned_parent(session: Session, user_id: uuid.UUID, parent_id: uuid.UUID) -> Category:
    parent = session.get(Category, parent_id)
    if parent is None or parent.user_id != user_id or parent.kind != "post":
        raise ValidationError("parent category not found", code="invalid_parent_category")
    return parent


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
        if parent_id is not None:
            _owned_parent(session, user_id, parent_id)
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
