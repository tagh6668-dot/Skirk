from __future__ import annotations

from pathlib import Path

from skirk.blobq import receive_file, send_file
from skirk.transports.local import LocalBlobStore


def test_blobq_local_e2e(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    output = tmp_path / "output.bin"
    source.write_bytes((b"abcdef" * 200_000) + b"tail")
    store = LocalBlobStore(tmp_path / "store")

    sent = send_file(
        store=store,
        input_path=source,
        secret="test-secret",
        chunk_size=128 * 1024,
    )
    received = receive_file(
        store=store,
        output_path=output,
        secret="test-secret",
        session_id=sent.session_id,
    )

    assert output.read_bytes() == source.read_bytes()
    assert received.bytes_plaintext == source.stat().st_size
    assert len(sent.objects) > 1


def test_blobq_delete_after_receive(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    output = tmp_path / "output.bin"
    source.write_bytes(b"delete-after")
    store = LocalBlobStore(tmp_path / "store")

    sent = send_file(store=store, input_path=source, secret="test-secret")
    receive_file(
        store=store,
        output_path=output,
        secret="test-secret",
        session_id=sent.session_id,
        delete_after=True,
    )

    assert store.list(sent.session_id) == []
