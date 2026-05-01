"""Transport interfaces for Skirk mailbox/object modes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ObjectInfo:
    name: str
    size: int | None = None
    updated: str | None = None
    token: str | None = None


class BlobStore(Protocol):
    """Minimal object-store API used by BlobQ."""

    def put(self, name: str, data: bytes) -> None:
        ...

    def get(self, name: str) -> bytes:
        ...

    def list(self, prefix: str) -> list[ObjectInfo]:
        ...

    def delete(self, name: str) -> None:
        ...


class TransportError(RuntimeError):
    pass
