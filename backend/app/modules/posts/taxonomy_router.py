"""Owned category, tag and keyword governance endpoints (spec 005, US8)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.db.session import get_db
from app.modules.jobs.schemas import serialize_job
from app.modules.posts import taxonomy_service
from app.modules.posts.schemas import (
    TaxonomyItemOut,
    TaxonomyMergeBody,
    TaxonomyPatch,
    TaxonomyWrite,
)

router = APIRouter(prefix="/blog/taxonomy", tags=["blog-taxonomy"])


@router.get("/{kind}")
def list_taxonomy(
    kind: str,
    enabled: bool | None = None,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TaxonomyItemOut]:
    return [
        TaxonomyItemOut(**item)
        for item in taxonomy_service.list_items(db, user.id, kind, enabled=enabled)
    ]


@router.post("/{kind}", status_code=201)
def create_taxonomy(
    kind: str,
    body: TaxonomyWrite,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaxonomyItemOut:
    item = taxonomy_service.create_item(
        db,
        user.id,
        kind,
        name=body.name,
        description=body.description,
        parent_id=body.parent_id,
        aliases=body.aliases,
        color=body.color,
        enabled=body.enabled,
        stop_word=body.stop_word,
    )
    db.commit()
    return TaxonomyItemOut(**item)


@router.patch("/{kind}/{item_id}")
def update_taxonomy(
    kind: str,
    item_id: uuid.UUID,
    body: TaxonomyPatch,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> TaxonomyItemOut:
    item = taxonomy_service.update_item(
        db, user.id, kind, item_id, **body.model_dump(exclude_unset=True)
    )
    db.commit()
    return TaxonomyItemOut(**item)


@router.post("/keyword/recompute", status_code=202)
def recompute_keywords(
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    job = taxonomy_service.request_keyword_recompute(db, user.id)
    db.commit()
    return serialize_job(job).model_dump(mode="json")  # type: ignore[arg-type]


@router.post("/{kind}/merge")
def merge_taxonomy(
    kind: str,
    body: TaxonomyMergeBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    status, result = taxonomy_service.request_merge(
        db, user.id, kind, body.source_id, body.target_id
    )
    db.commit()
    if status == "queued":
        return serialize_job(result).model_dump(mode="json")  # type: ignore[arg-type]
    return result  # type: ignore[return-value]
