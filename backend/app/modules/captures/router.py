"""Capture endpoints: list/create, detail/update/delete, asset access, convert."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, require_csrf
from app.core.errors import NotFoundError
from app.db.session import get_db
from app.models.captures import Capture, CaptureAsset
from app.modules.captures import service
from app.services.storage.providers.local import get_storage

router = APIRouter(prefix="/captures", tags=["captures"])


class CaptureCreate(BaseModel):
    model_config = {"extra": "forbid"}
    type: str = Field(
        pattern="^(item|inspiration|note|image|document|link|location|purchase|blog_material)$"
    )
    title: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=20000)
    upload_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    url: str | None = None


class CapturePatch(BaseModel):
    model_config = {"extra": "forbid"}
    version: int
    title: str | None = None
    description: str | None = None
    category_id: uuid.UUID | None = None
    brand: str | None = None
    model: str | None = None
    material: str | None = None
    color: str | None = None
    storage_location: str | None = None
    usage_status: str | None = None


class ConvertBody(BaseModel):
    model_config = {"extra": "forbid"}
    target_type: str = Field(pattern="^(task|purchase|restock_reminder|blog_material|habit)$")
    overrides: dict = Field(default_factory=dict)


def _provenance(user_val, ai_val) -> dict | None:  # type: ignore[no-untyped-def]
    if user_val is not None:
        return {"value": user_val, "source": "user"}
    if ai_val is not None:
        return {"value": ai_val, "source": "ai"}
    return None


def _capture_out(db: Session, c: Capture) -> dict:
    assets = service.list_assets(db, c.id)
    fields = {}
    for name, u, a in [
        ("title", c.title_user, c.title_ai),
        ("description", c.description_user, c.description_ai),
        ("brand", c.brand_user, c.brand_ai),
        ("model", c.model_user, c.model_ai),
        ("material", c.material_user, c.material_ai),
        ("color", c.color_user, c.color_ai),
        ("storage_location", c.storage_location_user, c.storage_location_ai),
    ]:
        prov = _provenance(u, a)
        if prov is not None:
            if u is None and a is not None:
                prov["confidence"] = float(c.ai_confidence) if c.ai_confidence else None
            fields[name] = prov
    return {
        "id": str(c.id),
        "type": c.type,
        "private": True,
        "fields": fields,
        "assets": [
            {
                "id": str(a.id),
                "role": a.role,
                "media_type": a.media_type,
                "byte_size": a.byte_size,
                "width": a.width,
                "height": a.height,
                "status": a.status,
            }
            for a in assets
        ],
        "processing_status": c.processing_status,
        "possible_duplicate_of": str(c.possible_duplicate_of) if c.possible_duplicate_of else None,
        "usage_status": c.usage_status,
        "ocr_text": c.ocr_text,
        "version": c.version,
        "created_at": c.created_at.isoformat(),
    }


@router.get("")
def list_captures(
    type: str | None = Query(default=None),
    state: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    items = service.list_captures(db, user.id, type_=type, state=state)
    return {"items": [_capture_out(db, c) for c in items], "next_cursor": None}


@router.post("", status_code=202)
def create_capture(
    body: CaptureCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    capture = service.create_capture(
        db,
        user.id,
        capture_type=body.type,
        title=body.title,
        description=body.description,
        upload_ids=body.upload_ids,
        url=body.url,
    )
    db.commit()
    return _capture_out(db, capture)


@router.get("/{capture_id}")
def get_capture(
    capture_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _capture_out(db, service.get_capture(db, user.id, capture_id))


@router.patch("/{capture_id}")
def update_capture(
    capture_id: uuid.UUID,
    body: CapturePatch,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    data = body.model_dump(exclude_unset=True, exclude={"version"})
    capture = service.update_capture(db, user.id, capture_id, body.version, data)
    db.commit()
    return _capture_out(db, capture)


@router.delete("/{capture_id}", status_code=204)
def delete_capture(
    capture_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_capture(db, user.id, capture_id)
    db.commit()
    return Response(status_code=204)


@router.get("/{capture_id}/assets/{asset_id}/access")
def asset_access(
    capture_id: uuid.UUID,
    asset_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    capture = service.get_capture(db, user.id, capture_id)
    asset = db.get(CaptureAsset, asset_id)
    if asset is None or asset.capture_id != capture.id or asset.user_id != user.id:
        raise NotFoundError("Asset not found")
    access = get_storage().access_url(asset.storage_key)
    from datetime import UTC, datetime, timedelta

    expires = datetime.now(UTC) + timedelta(seconds=access.expires_in_seconds)
    return {"url": access.url, "expires_at": expires.isoformat()}


@router.post("/{capture_id}/convert", status_code=201)
def convert(
    capture_id: uuid.UUID,
    body: ConvertBody,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    entity_type, entity_id = service.convert_capture(
        db, user.id, capture_id, body.target_type, body.overrides
    )
    db.commit()
    return {"type": entity_type, "id": str(entity_id)}
