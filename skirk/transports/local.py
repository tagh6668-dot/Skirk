"""Local filesystem BlobStore used for deterministic E2E tests."""

from __future__ import annotations

from pathlib import Path

from .base import ObjectInfo


class LocalBlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        clean = name.strip("/")
        if ".." in Path(clean).parts:
            raise ValueError("object name must not escape store root")
        return self.root / clean

    def put(self, name: str, data: bytes) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def get(self, name: str) -> bytes:
        return self._path(name).read_bytes()

    def list(self, prefix: str) -> list[ObjectInfo]:
        base = self._path(prefix)
        if base.is_file():
            files = [base]
        elif base.exists():
            files = [p for p in base.rglob("*") if p.is_file() and not p.name.endswith(".tmp")]
        else:
            files = []
        infos: list[ObjectInfo] = []
        for path in sorted(files):
            rel = path.relative_to(self.root).as_posix()
            stat = path.stat()
            infos.append(ObjectInfo(name=rel, size=stat.st_size, updated=str(stat.st_mtime)))
        return infos

    def delete(self, name: str) -> None:
        path = self._path(name)
        if path.exists():
            path.unlink()
