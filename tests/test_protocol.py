from __future__ import annotations

import pytest

from skirk.protocol import Direction, derive_key, new_session_id, open_envelope, seal


def test_envelope_round_trips_and_authenticates_header() -> None:
    key = derive_key("test-secret")
    session_id = new_session_id()
    sealed = seal(
        key=key,
        session_id=session_id,
        direction=Direction.UP,
        sequence=7,
        plaintext=b"hello skirk",
        final=True,
    )

    envelope, plaintext = open_envelope(key=key, data=sealed)

    assert plaintext == b"hello skirk"
    assert envelope.session_id == session_id
    assert envelope.direction == Direction.UP
    assert envelope.sequence == 7
    assert envelope.flags == 1


def test_envelope_rejects_tampering() -> None:
    key = derive_key("test-secret")
    sealed = bytearray(
        seal(
            key=key,
            session_id=new_session_id(),
            direction=Direction.DOWN,
            sequence=1,
            plaintext=b"payload",
        )
    )
    sealed[-1] ^= 1

    with pytest.raises(Exception):
        open_envelope(key=key, data=bytes(sealed))
