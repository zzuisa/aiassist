"""Upload endpoints: create session, stream content, complete."""

from __future__ import annotations

import uuid

from app.api.dependencies import CurrentUser, require_csrf
from app.db.session import get_db
from app.modules.uploads import service
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/uploads", tags=["uploads"])


class UploadCreate(BaseModel):
    model_config = {"extra": "forbid"}
    purpose: str = Field(pattern="^(capture|voice|post_cover|attachment)$")
    filename: str = Field(max_length=255)
    media_type: str = Field(max_length=120)
    byte_size: int = Field(ge=1)
    sha256: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")


def _out(upload) -> dict:  # type: ignore[no-untyped-def]
    return {
        "id": str(upload.id),
        "status": upload.status,
        "upload_url": f"/api/v1/uploads/{upload.id}/content",
        "expires_at": upload.expires_at.isoformat(),
    }


@router.post("", status_code=201)
def create_upload(
    body: UploadCreate,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    upload = service.create_session(
        db,
        user.id,
        purpose=body.purpose,
        filename=body.filename,
        media_type=body.media_type,
        byte_size=body.byte_size,
        sha256=body.sha256,
    )
    db.commit()
    return _out(upload)


class _StreamReader:
    """Adapts a Starlette request stream to a synchronous read() interface used
    by the storage gateway. Reads the whole body then serves it chunk-wise."""

    def __init__(self, data: bytes) -> None:
        self._buf = memoryview(data)
        self._pos = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._buf[self._pos :]
            self._pos = len(self._buf)
            return bytes(chunk)
        chunk = self._buf[self._pos : self._pos + size]
        self._pos += len(chunk)
        return bytes(chunk)


@router.put("/{upload_id}/content", status_code=204)
async def put_content(
    upload_id: uuid.UUID,
    request: Request,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    upload = service.get_owned(db, user.id, upload_id)
    body = await request.body()
    service.store_bytes(db, upload, _StreamReader(body))
    db.commit()
    return Response(status_code=204)


@router.post("/{upload_id}/complete")
def complete_upload(
    upload_id: uuid.UUID,
    user: CurrentUser = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> dict:
    upload = service.complete(db, user.id, upload_id)
    db.commit()
    return _out(upload)
