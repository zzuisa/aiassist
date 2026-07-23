"""Search endpoint: grouped, highlighted, ownership-isolated results."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user
from app.db.session import get_db
from app.modules.search import service

router = APIRouter(tags=["search"])


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=200),
    types: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    type_list = [t.strip() for t in types.split(",")] if types else None
    return service.search(db, user.id, q, type_list)
