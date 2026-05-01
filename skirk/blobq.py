"""Chunked encrypted object queue shared by Skirk storage-like transports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .protocol import Direction, decode_session_id, derive_key, encode_session_id, open_envelope, seal
from .transports.base import BlobStore


DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024


@dataclass(frozen=True)
class SendResult:
    session_id: str
    objects: list[str]
    bytes_plaintext: int


@dataclass(frozen=True)
class ReceiveResult:
    session_id: str
    objects: list[str]
    bytes_plaintext: int


def send_file(
    *,
    store: BlobStore,
    input_path: str | Path,
    secret: str,
    session_id: str | None = None,
    direction: Direction = Direction.UP,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    cleanup_existing: bool = False,
) -> SendResult:
    path = Path(input_path)
    sid = decode_session_id(session_id)
    key = derive_key(secret)
    prefix = f"{sid.hex()}/{direction.name.lower()}/"
    if cleanup_existing:
        for info in store.list(prefix):
            store.delete(info.name)

    objects: list[str] = []
    total = 0
    sequence = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            final = len(chunk) < chunk_size
            payload = seal(
                key=key,
                session_id=sid,
                direction=direction,
                sequence=sequence,
                plaintext=chunk,
                final=final,
            )
            object_name = f"{prefix}{sequence:016x}.skb"
            store.put(object_name, payload)
            objects.append(object_name)
            total += len(chunk)
            sequence += 1
            if final:
                break
    return SendResult(session_id=encode_session_id(sid), objects=objects, bytes_plaintext=total)


def receive_file(
    *,
    store: BlobStore,
    output_path: str | Path,
    secret: str,
    session_id: str,
    direction: Direction = Direction.UP,
    delete_after: bool = False,
) -> ReceiveResult:
    sid = decode_session_id(session_id)
    key = derive_key(secret)
    prefix = f"{sid.hex()}/{direction.name.lower()}/"
    infos = sorted(store.list(prefix), key=lambda item: item.name)
    if not infos:
        raise FileNotFoundError(f"no objects found for prefix {prefix}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    names: list[str] = []
    expected = 0
    with output.open("wb") as handle:
        for info in infos:
            envelope, plaintext = open_envelope(key=key, data=store.get(info.name))
            if envelope.session_id != sid:
                raise ValueError(f"session mismatch in {info.name}")
            if envelope.sequence != expected:
                raise ValueError(f"missing sequence {expected}; got {envelope.sequence}")
            if envelope.direction != direction:
                raise ValueError(f"direction mismatch in {info.name}")
            handle.write(plaintext)
            total += len(plaintext)
            names.append(info.name)
            expected += 1
            if envelope.flags & 1:
                break
    if delete_after:
        for name in names:
            store.delete(name)
    return ReceiveResult(session_id=encode_session_id(sid), objects=names, bytes_plaintext=total)
