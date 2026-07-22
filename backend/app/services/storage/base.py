"""Provider-neutral storage gateway protocol.

Business modules depend only on this protocol. The default provider stores
objects in a private local directory; an S3-compatible adapter is optional. Keys
are internal and never returned to clients directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO, Protocol, runtime_checkable


class StorageError(Exception):
    """Stable storage failure category."""


class ObjectNotFoundError(StorageError):
    pass


@dataclass
class StoredObject:
    key: str
    byte_size: int
    sha256: str
    media_type: str | None = None


@dataclass
class AccessURL:
    url: str
    expires_in_seconds: int
    # When True the URL is a same-origin protected path served via X-Accel;
    # when False it is a signed absolute URL (S3).
    same_origin: bool


@runtime_checkable
class StorageGateway(Protocol):
    def put_stream(
        self, key: str, stream: BinaryIO, *, media_type: str | None = None, max_bytes: int
    ) -> StoredObject:
        """Stream bytes to storage, enforcing max_bytes, returning size+hash."""
        ...

    def open_stream(self, key: str) -> Iterator[bytes]:
        """Yield object bytes; raises ObjectNotFoundError if missing."""
        ...

    def copy(self, src_key: str, dst_key: str) -> StoredObject: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def access_url(self, key: str, *, expires_in_seconds: int = 60) -> AccessURL:
        """Return an authorized access reference for an already-owned object."""
        ...
