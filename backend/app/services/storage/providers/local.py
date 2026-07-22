"""Local private-directory storage provider.

Objects live under ``ASSET_ROOT`` (outside any web root). Reads by the browser
go through the backend, which authorizes ownership and returns an
``X-Accel-Redirect`` to an internal Nginx location. Keys are relative POSIX
paths; traversal is rejected.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.services.storage.base import AccessURL, ObjectNotFoundError, StoredObject

_CHUNK = 1024 * 1024

# Nginx internal location that maps to ASSET_ROOT (see deploy/nginx/conf.d).
PROTECTED_PREFIX = "/_protected/"


def _safe_key(key: str) -> str:
    normalized = os.path.normpath(key).replace("\\", "/").lstrip("/")
    if normalized.startswith("..") or "/../" in normalized or normalized == "":
        raise ValidationError("Invalid storage key")
    return normalized


class LocalStorage:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or get_settings().asset_root)

    def _path(self, key: str) -> Path:
        return self.root / _safe_key(key)

    def put_stream(
        self, key: str, stream: BinaryIO, *, media_type: str | None = None, max_bytes: int
    ) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha256()
        total = 0
        tmp = path.with_suffix(path.suffix + ".part")
        try:
            with tmp.open("wb") as out:
                while True:
                    chunk = stream.read(_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValidationError(
                            f"Object exceeds max_bytes ({max_bytes})",
                            code="payload_too_large",
                            status=413,
                        )
                    hasher.update(chunk)
                    out.write(chunk)
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        return StoredObject(
            key=_safe_key(key), byte_size=total, sha256=hasher.hexdigest(), media_type=media_type
        )

    def open_stream(self, key: str) -> Iterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)

        def _iter() -> Iterator[bytes]:
            with path.open("rb") as f:
                while True:
                    chunk = f.read(_CHUNK)
                    if not chunk:
                        break
                    yield chunk

        return _iter()

    def copy(self, src_key: str, dst_key: str) -> StoredObject:
        src = self._path(src_key)
        if not src.is_file():
            raise ObjectNotFoundError(src_key)
        dst = self._path(dst_key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        hasher = hashlib.sha256()
        size = 0
        with dst.open("rb") as f:
            for chunk in iter(lambda: f.read(_CHUNK), b""):
                hasher.update(chunk)
                size += len(chunk)
        return StoredObject(key=_safe_key(dst_key), byte_size=size, sha256=hasher.hexdigest())

    def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def access_url(self, key: str, *, expires_in_seconds: int = 60) -> AccessURL:
        # Local objects are served via an internal redirect; the URL is the
        # protected same-origin path the backend sets as X-Accel-Redirect.
        return AccessURL(
            url=PROTECTED_PREFIX + _safe_key(key),
            expires_in_seconds=expires_in_seconds,
            same_origin=True,
        )


_default: LocalStorage | None = None


def get_storage() -> LocalStorage:
    """Return the configured storage gateway (local by default)."""
    global _default
    if _default is None:
        _default = LocalStorage()
    return _default


def reset_storage() -> None:
    global _default
    _default = None
