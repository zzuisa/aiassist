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
from app.modules.posts import content_types
from app.modules.posts.schemas import (
    ContentTypeOut,
    ContentTypeWrite,
    content_type_out,
)

query_router = APIRouter(prefix="/blog", tags=["blog-query"])


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
