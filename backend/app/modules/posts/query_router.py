"""Blog query + content-type endpoints (spec 005, US2 T052 / US9 later).

Content types live under ``/blog/content-types``. Later user stories add search
and word-cloud read endpoints to the same ``/blog`` router.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.posts import content_types, query_service, service
from app.modules.posts.schemas import (
    BatchBody,
    ContentTypeOut,
    ContentTypeWrite,
    MergeBody,
    content_type_out,
    post_out,
)

query_router = APIRouter(prefix="/blog", tags=["blog-query"])


# ---------------------------------------------------------------------------
# Article management: list / triage / merge / batch / export (spec 005, US6)
# ---------------------------------------------------------------------------


@query_router.get("/articles")
def list_articles(
    content_status: str | None = None,
    content_class: str | None = None,
    status: str | None = None,
    ai_state: str | None = None,
    search: str | None = None,
    include_inactive: bool = False,
    sort: str = "updated_desc",
    cursor: int = 0,
    limit: int = 30,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return query_service.list_posts(
        db, user.id,
        content_status=content_status, content_class=content_class, status=status,
        ai_state=ai_state, search=search, include_inactive=include_inactive,
        sort=sort, cursor=cursor, limit=min(limit, 100),
    )


@query_router.get("/triage")
def list_triage(
    reason: str | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return query_service.triage_items(db, user.id, reason=reason)


@query_router.post("/articles/merge")
def merge_articles(
    body: MergeBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    post = service.merge_posts(
        db, user.id, body.primary_id, body.secondary_id,
        order=body.order, title=body.title, current_version=body.primary_version,
    )
    db.commit()
    return post_out(post).model_dump(mode="json")


@query_router.post("/articles/batch")
def batch_articles(
    body: BatchBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    results = service.batch_operation(db, user.id, body.post_ids, body.op, body.params)
    db.commit()
    succeeded = sum(1 for r in results if r["ok"])
    return {"results": results, "succeeded": succeeded, "failed": len(results) - succeeded}


@query_router.get("/articles/{post_id}/export")
def export_article(
    post_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    post = service.get_post(db, user.id, post_id)
    return {
        "filename": f"{(post.slug or post.title or 'article')}.md",
        "title": post.title,
        "markdown": post.markdown,
    }


@query_router.get("/content-types")
def list_content_types(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ContentTypeOut]:
    return [content_type_out(ct) for ct in content_types.list_all_content_types(db, user.id)]


@query_router.post("/content-types", status_code=201)
def create_content_type(
    body: ContentTypeWrite,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ContentTypeOut:
    ct = content_types.create_content_type(
        db, user.id,
        content_class=body.content_class, key=body.key, name=body.name,
        field_schema=body.field_schema, description=body.description,
        sort_order=body.sort_order, enabled=body.enabled,
    )
    db.commit()
    return content_type_out(ct)


@query_router.patch("/content-types/{content_type_id}")
def update_content_type(
    content_type_id: uuid.UUID,
    body: ContentTypeWrite,
    response: Response,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> ContentTypeOut:
    ct, warnings = content_types.update_content_type(
        db, user.id, content_type_id,
        name=body.name, description=body.description, field_schema=body.field_schema,
        sort_order=body.sort_order, enabled=body.enabled,
    )
    db.commit()
    if warnings:
        response.headers["X-Blog-Warnings"] = "; ".join(warnings)
    return content_type_out(ct)
