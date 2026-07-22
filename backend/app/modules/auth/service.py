"""Authentication service: passwords, JWT access tokens, refresh rotation, CSRF.

- Passwords use Argon2id.
- Access tokens are short-lived JWTs (HS256) delivered in an HttpOnly cookie.
- Refresh tokens are random opaque strings; only their hash is stored. Reuse of
  a rotated token revokes the whole family (reuse detection).
- A per-session CSRF token is bound to the refresh family.
- Login is throttled per (email, ip) window.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthenticationError, RateLimitedError
from app.models.foundation import RefreshSession, User

_hasher = PasswordHasher()

UNKNOWN_IP = "0.0.0.0"  # noqa: S104 - placeholder IP string, not a bind address

ACCESS_COOKIE = "__Host-aiassist_access"
REFRESH_COOKIE = "__Host-aiassist_refresh"
CSRF_HEADER = "X-CSRF-Token"
JWT_ALGORITHM = "HS256"

# In-process login attempt counter. A single-process personal deployment does
# not need a distributed limiter; Redis-backed limiting is a later hardening.
_login_attempts: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _signing_key() -> str:
    key = get_settings().resolved_jwt_signing_key
    if not key:
        raise RuntimeError("JWT signing key is not configured")
    return key


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    csrf_token: str
    family_id: uuid.UUID
    access_expires_at: datetime
    refresh_expires_at: datetime


def issue_access_token(user_id: uuid.UUID, family_id: uuid.UUID) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=settings.access_token_ttl_seconds)
    payload = {
        "sub": str(user_id),
        "fam": str(family_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, _signing_key(), algorithm=JWT_ALGORITHM), exp


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _signing_key(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token expired", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid access token") from exc


def _derive_csrf(family_id: uuid.UUID) -> str:
    return hmac.new(
        _signing_key().encode(), f"csrf:{family_id}".encode(), hashlib.sha256
    ).hexdigest()


def verify_csrf(family_id: uuid.UUID, token: str | None) -> None:
    if not token or not hmac.compare_digest(_derive_csrf(family_id), token):
        raise AuthenticationError("Invalid CSRF token", code="csrf_failed", status=403)


def _check_login_rate(email: str, ip: str) -> None:
    settings = get_settings()
    key = f"{email.lower()}|{ip}"
    now = datetime.now(UTC).timestamp()
    window = settings.login_window_seconds
    attempts = [t for t in _login_attempts.get(key, []) if now - t < window]
    if len(attempts) >= settings.login_max_attempts:
        raise RateLimitedError("Too many login attempts. Try again later.")
    attempts.append(now)
    _login_attempts[key] = attempts


def reset_login_throttle() -> None:
    _login_attempts.clear()


def _new_refresh(
    session: Session,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    ip_prefix: str | None,
    ua_hash: str | None,
) -> tuple[str, datetime]:
    settings = get_settings()
    raw = secrets.token_urlsafe(48)
    exp = datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds)
    session.add(
        RefreshSession(
            user_id=user_id,
            token_hash=_hash_token(raw),
            family_id=family_id,
            expires_at=exp,
            ip_prefix=ip_prefix,
            user_agent_hash=ua_hash,
        )
    )
    return raw, exp


def login(
    session: Session,
    email: str,
    password: str,
    *,
    ip: str = UNKNOWN_IP,
    user_agent: str | None = None,
) -> tuple[User, TokenBundle]:
    _check_login_rate(email, ip)
    user = session.scalar(select(User).where(User.email == email))
    # Constant-ish work + generic error to avoid user enumeration.
    if user is None or not verify_password(user.password_hash, password):
        raise AuthenticationError("Invalid email or password", code="invalid_credentials")
    if user.status != "active":
        raise AuthenticationError("Invalid email or password", code="invalid_credentials")

    family_id = uuid.uuid4()
    ua_hash = _hash_token(user_agent)[:64] if user_agent else None
    ip_prefix = ".".join(ip.split(".")[:2]) if "." in ip else ip[:16]
    refresh, refresh_exp = _new_refresh(session, user.id, family_id, ip_prefix, ua_hash)
    access, access_exp = issue_access_token(user.id, family_id)
    user.last_login_at = datetime.now(UTC)
    bundle = TokenBundle(
        access_token=access,
        refresh_token=refresh,
        csrf_token=_derive_csrf(family_id),
        family_id=family_id,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )
    return user, bundle


def rotate_refresh(
    session: Session,
    refresh_token: str,
    *,
    ip: str = UNKNOWN_IP,
    user_agent: str | None = None,
) -> tuple[User, TokenBundle]:
    token_hash = _hash_token(refresh_token)
    record = session.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash))
    if record is None:
        raise AuthenticationError("Invalid refresh session", code="refresh_invalid")

    now = datetime.now(UTC)
    if record.revoked_at is not None or record.rotated_at is not None:
        # Reuse of a rotated/revoked token: revoke the entire family. Commit the
        # revocation before raising so it survives the request's rollback path.
        _revoke_family(session, record.user_id, record.family_id)
        session.commit()
        raise AuthenticationError("Refresh token reuse detected", code="refresh_reused")
    if record.expires_at <= now:
        raise AuthenticationError("Refresh session expired", code="refresh_expired")

    record.rotated_at = now
    user = session.get(User, record.user_id)
    if user is None or user.status != "active":
        raise AuthenticationError("Invalid refresh session", code="refresh_invalid")

    ua_hash = _hash_token(user_agent)[:64] if user_agent else None
    ip_prefix = ".".join(ip.split(".")[:2]) if "." in ip else ip[:16]
    new_refresh, refresh_exp = _new_refresh(session, user.id, record.family_id, ip_prefix, ua_hash)
    access, access_exp = issue_access_token(user.id, record.family_id)
    bundle = TokenBundle(
        access_token=access,
        refresh_token=new_refresh,
        csrf_token=_derive_csrf(record.family_id),
        family_id=record.family_id,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )
    return user, bundle


def _revoke_family(session: Session, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    rows = session.scalars(
        select(RefreshSession).where(
            RefreshSession.user_id == user_id,
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
        )
    )
    for r in rows:
        r.revoked_at = now


def logout(session: Session, refresh_token: str | None, family_id: uuid.UUID | None) -> None:
    if refresh_token:
        record = session.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == _hash_token(refresh_token))
        )
        if record is not None:
            _revoke_family(session, record.user_id, record.family_id)
    elif family_id is not None:
        rows = session.scalars(select(RefreshSession).where(RefreshSession.family_id == family_id))
        for r in rows:
            if r.revoked_at is None:
                r.revoked_at = datetime.now(UTC)


def revoke_all_sessions(
    session: Session, user_id: uuid.UUID, *, keep_family: uuid.UUID | None = None
) -> None:
    now = datetime.now(UTC)
    rows = session.scalars(
        select(RefreshSession).where(
            RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None)
        )
    )
    for r in rows:
        if keep_family is None or r.family_id != keep_family:
            r.revoked_at = now
