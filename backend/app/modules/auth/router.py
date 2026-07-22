"""Auth routes: login, refresh, logout, me. Same-origin HttpOnly cookies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user
from app.core.config import AppEnv, get_settings
from app.core.errors import AuthenticationError
from app.db.session import get_db
from app.models.foundation import User
from app.modules.auth import service as auth_service
from app.modules.auth.schemas import LoginRequest, LoginResponse, UserOut
from app.modules.auth.service import TokenBundle

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else auth_service.UNKNOWN_IP


def _set_auth_cookies(response: Response, bundle: TokenBundle) -> None:
    settings = get_settings()
    secure = settings.app_env == AppEnv.production
    response.set_cookie(
        auth_service.ACCESS_COOKIE,
        bundle.access_token,
        max_age=settings.access_token_ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        auth_service.REFRESH_COOKIE,
        bundle.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(auth_service.ACCESS_COOKIE, path="/")
    response.delete_cookie(auth_service.REFRESH_COOKIE, path="/")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    user, bundle = auth_service.login(
        db,
        payload.email,
        payload.password,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    _set_auth_cookies(response, bundle)
    return LoginResponse(
        user=UserOut.model_validate(user, from_attributes=True),
        csrf_token=bundle.csrf_token,
    )


@router.post("/refresh", status_code=204)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(auth_service.REFRESH_COOKIE)
    if not token:
        raise AuthenticationError("Missing refresh token", code="refresh_invalid")
    _, bundle = auth_service.rotate_refresh(
        db,
        token,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    _set_auth_cookies(response, bundle)
    response.headers["X-CSRF-Token"] = bundle.csrf_token
    response.status_code = 204
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(auth_service.REFRESH_COOKIE)
    auth_service.logout(db, token, None)
    db.commit()
    _clear_auth_cookies(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    db_user = db.get(User, user.id)
    return UserOut.model_validate(db_user, from_attributes=True)
