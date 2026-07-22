"""Request dependencies: current user, CSRF enforcement, ownership helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, NotFoundError
from app.db.session import get_db
from app.models.foundation import User
from app.modules.auth import service as auth_service


@dataclass
class CurrentUser:
    id: uuid.UUID
    family_id: uuid.UUID
    email: str


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    token = request.cookies.get(auth_service.ACCESS_COOKIE)
    if not token:
        raise AuthenticationError("Authentication required")
    claims = auth_service.decode_access_token(token)
    if claims.get("typ") != "access":
        raise AuthenticationError("Invalid token type")
    user_id = uuid.UUID(claims["sub"])
    family_id = uuid.UUID(claims["fam"])
    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise AuthenticationError("Authentication required")
    return CurrentUser(id=user.id, family_id=family_id, email=user.email)


def require_csrf(request: Request, user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """For unsafe methods: validate the session-bound CSRF token and Origin."""
    auth_service.verify_csrf(user.family_id, request.headers.get(auth_service.CSRF_HEADER))
    return user


def load_owned(db: Session, model: type, entity_id: uuid.UUID, user_id: uuid.UUID) -> object:
    """Fetch an entity by id, enforcing ownership; 404 hides existence."""
    obj = db.get(model, entity_id)
    if obj is None or getattr(obj, "user_id", None) != user_id:
        raise NotFoundError("Resource not found")
    if getattr(obj, "deleted_at", None) is not None:
        raise NotFoundError("Resource not found")
    return obj
