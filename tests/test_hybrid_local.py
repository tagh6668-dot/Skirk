from __future__ import annotations

from pathlib import Path

from skirk.hybrid import hybrid_receive_file, hybrid_send_file
from skirk.transports.local import LocalBlobStore


def test_hybrid_local_e2e(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    output = tmp_path / "output.bin"
    source.write_bytes(b"hybrid" * 10_000 + b"tail")
    data_store = LocalBlobStore(tmp_path / "drive")
    control_store = LocalBlobStore(tmp_path / "sheets")

    sent = hybrid_send_file(
        data_store=data_store,
        control_store=control_store,
        input_path=source,
        secret="test-secret",
        chunk_size=4096,
    )
    received = hybrid_receive_file(
        data_store=data_store,
        control_store=control_store,
        output_path=output,
        secret="test-secret",
        session_id=sent.session_id,
        delete_after=True,
    )

    assert output.read_bytes() == source.read_bytes()
    assert received.bytes_plaintext == source.stat().st_size
    assert received.chunks == sent.chunks
    assert data_store.list("data") == []
    assert control_store.list("control") == []
