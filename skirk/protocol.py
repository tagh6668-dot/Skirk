"""Encrypted chunk envelope used by Skirk mailbox-style transports."""

from __future__ import annotations

import base64
import os
import struct
from dataclasses import dataclass
from enum import IntEnum

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


MAGIC = b"SKB1"
VERSION = 1
HEADER = struct.Struct("!4sB16sBBQII")
SESSION_LEN = 16
KEY_LEN = 32
MAX_SEQ = (1 << 56) - 1


class Direction(IntEnum):
    UP = 1
    DOWN = 2


class Flags(IntEnum):
    DATA = 0
    FINAL = 1


@dataclass(frozen=True)
class Envelope:
    session_id: bytes
    direction: Direction
    sequence: int
    flags: int
    plaintext_len: int
    ciphertext: bytes

    def object_name(self) -> str:
        return f"{self.session_id.hex()}/{self.direction.name.lower()}/{self.sequence:016x}.skb"


def new_session_id() -> bytes:
    return os.urandom(SESSION_LEN)


def encode_session_id(session_id: bytes) -> str:
    if len(session_id) != SESSION_LEN:
        raise ValueError("session_id must be 16 bytes")
    return session_id.hex()


def decode_session_id(value: str | None) -> bytes:
    if not value:
        return new_session_id()
    raw = bytes.fromhex(value)
    if len(raw) != SESSION_LEN:
        raise ValueError("session id must be 16 bytes / 32 hex chars")
    return raw


def derive_key(secret: str | bytes) -> bytes:
    """Derive a 256-bit AEAD key from a user secret or raw key string."""

    if isinstance(secret, str):
        value = secret.strip()
        if value.startswith("hex:"):
            raw = bytes.fromhex(value[4:])
            if len(raw) != KEY_LEN:
                raise ValueError("hex key must be 32 bytes")
            return raw
        if value.startswith("base64:"):
            raw = base64.b64decode(value[7:])
            if len(raw) != KEY_LEN:
                raise ValueError("base64 key must be 32 bytes")
            return raw
        ikm = value.encode("utf-8")
    else:
        ikm = secret
    return HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=b"skirk-v1-static-salt",
        info=b"skirk-blobq-aead-key",
    ).derive(ikm)


def _nonce(session_id: bytes, direction: Direction, sequence: int) -> bytes:
    if len(session_id) != SESSION_LEN:
        raise ValueError("session_id must be 16 bytes")
    if not 0 <= sequence <= MAX_SEQ:
        raise ValueError("sequence out of supported nonce range")
    return session_id[:4] + bytes([int(direction)]) + sequence.to_bytes(7, "big")


def seal(
    *,
    key: bytes,
    session_id: bytes,
    direction: Direction,
    sequence: int,
    plaintext: bytes,
    final: bool = False,
) -> bytes:
    flags = int(Flags.FINAL if final else Flags.DATA)
    header = HEADER.pack(
        MAGIC,
        VERSION,
        session_id,
        int(direction),
        flags,
        sequence,
        len(plaintext),
        # AES-GCM appends a 16-byte tag to the plaintext-length ciphertext.
        len(plaintext) + 16,
    )
    ciphertext = AESGCM(key).encrypt(_nonce(session_id, direction, sequence), plaintext, header)
    return header + ciphertext


def open_envelope(*, key: bytes, data: bytes) -> tuple[Envelope, bytes]:
    if len(data) < HEADER.size:
        raise ValueError("envelope too short")
    magic, version, session_id, direction_raw, flags, sequence, plaintext_len, ciphertext_len = HEADER.unpack(
        data[: HEADER.size]
    )
    if magic != MAGIC:
        raise ValueError("bad envelope magic")
    if version != VERSION:
        raise ValueError(f"unsupported envelope version {version}")
    if ciphertext_len != len(data) - HEADER.size:
        raise ValueError("ciphertext length mismatch")
    direction = Direction(direction_raw)
    header = data[: HEADER.size]
    ciphertext = data[HEADER.size :]
    plaintext = AESGCM(key).decrypt(_nonce(session_id, direction, sequence), ciphertext, header)
    if len(plaintext) != plaintext_len:
        raise ValueError("plaintext length mismatch")
    return (
        Envelope(
            session_id=session_id,
            direction=direction,
            sequence=sequence,
            flags=flags,
            plaintext_len=plaintext_len,
            ciphertext=ciphertext,
        ),
        plaintext,
    )


def random_secret() -> str:
    return "base64:" + base64.b64encode(os.urandom(KEY_LEN)).decode("ascii")
