"""Drive data lane + Sheets control lane transport."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .protocol import Direction, decode_session_id, derive_key, encode_session_id, open_envelope, seal
from .transports.base import BlobStore


CONTROL_PREFIX = "control"


@dataclass(frozen=True)
class HybridSendResult:
    session_id: str
    chunks: int
    bytes_plaintext: int
    drive_objects: list[str]
    control_rows: list[str]


@dataclass(frozen=True)
class HybridReceiveResult:
    session_id: str
    chunks: int
    bytes_plaintext: int
    drive_objects: list[str]
    control_rows: list[str]


def _control_name(session_id: bytes, direction: Direction, sequence: int) -> str:
    return f"{CONTROL_PREFIX}/{session_id.hex()}/{direction.name.lower()}/{sequence:016x}"


def _data_name(session_id: bytes, direction: Direction, sequence: int) -> str:
    return f"data/{session_id.hex()}/{direction.name.lower()}/{sequence:016x}.skb"


def _control_prefix(session_id: bytes, direction: Direction) -> str:
    return f"{CONTROL_PREFIX}/{session_id.hex()}/{direction.name.lower()}/"


def hybrid_send_file(
    *,
    data_store: BlobStore,
    control_store: BlobStore,
    input_path: str | Path,
    secret: str,
    session_id: str | None = None,
    direction: Direction = Direction.UP,
    chunk_size: int = 4096,
    cleanup_existing: bool = False,
) -> HybridSendResult:
    sid = decode_session_id(session_id)
    key = derive_key(secret)
    path = Path(input_path)
    control_prefix = _control_prefix(sid, direction)

    if cleanup_existing:
        for info in control_store.list(control_prefix):
            control_store.delete(info.name)

    drive_objects: list[str] = []
    control_rows: list[str] = []
    total = 0
    sequence = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            final = len(chunk) < chunk_size
            data_name = _data_name(sid, direction, sequence)
            envelope = seal(
                key=key,
                session_id=sid,
                direction=direction,
                sequence=sequence,
                plaintext=chunk,
                final=final,
            )
            data_store.put(data_name, envelope)
            control_name = _control_name(sid, direction, sequence)
            control_payload = {
                "event": "CHUNK_READY",
                "session_id": sid.hex(),
                "direction": direction.name,
                "sequence": sequence,
                "drive_object": data_name,
                "bytes": len(chunk),
                "final": final,
            }
            control_store.put(control_name, json.dumps(control_payload, separators=(",", ":")).encode("utf-8"))
            drive_objects.append(data_name)
            control_rows.append(control_name)
            total += len(chunk)
            sequence += 1
            if final:
                break

    return HybridSendResult(
        session_id=encode_session_id(sid),
        chunks=sequence,
        bytes_plaintext=total,
        drive_objects=drive_objects,
        control_rows=control_rows,
    )


def hybrid_receive_file(
    *,
    data_store: BlobStore,
    control_store: BlobStore,
    output_path: str | Path,
    secret: str,
    session_id: str,
    direction: Direction = Direction.UP,
    delete_after: bool = False,
) -> HybridReceiveResult:
    sid = decode_session_id(session_id)
    key = derive_key(secret)
    controls = sorted(control_store.list(_control_prefix(sid, direction)), key=lambda item: item.name)
    if not controls:
        raise FileNotFoundError(f"no control rows for session {sid.hex()}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    drive_objects: list[str] = []
    control_rows: list[str] = []
    total = 0
    expected = 0

    with output.open("wb") as handle:
        for control in controls:
            payload = json.loads(control_store.get(control.name).decode("utf-8"))
            sequence = int(payload["sequence"])
            if sequence != expected:
                raise ValueError(f"missing sequence {expected}; got {sequence}")
            data_name = str(payload["drive_object"])
            envelope, plaintext = open_envelope(key=key, data=data_store.get(data_name))
            if envelope.session_id != sid:
                raise ValueError(f"session mismatch in {data_name}")
            if envelope.sequence != sequence:
                raise ValueError(f"sequence mismatch in {data_name}")
            if envelope.direction != direction:
                raise ValueError(f"direction mismatch in {data_name}")
            handle.write(plaintext)
            total += len(plaintext)
            drive_objects.append(data_name)
            control_rows.append(control.name)
            expected += 1
            if bool(payload.get("final")):
                break

    if delete_after:
        for name in drive_objects:
            data_store.delete(name)
        for name in control_rows:
            control_store.delete(name)

    return HybridReceiveResult(
        session_id=encode_session_id(sid),
        chunks=len(control_rows),
        bytes_plaintext=total,
        drive_objects=drive_objects,
        control_rows=control_rows,
    )
