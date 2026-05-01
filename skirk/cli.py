"""Command line interface for Skirk transport prototypes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .blobq import receive_file, send_file
from .factory import build_blob_store
from .hybrid import hybrid_receive_file, hybrid_send_file
from .modes import MODES
from .protocol import Direction, random_secret
from .transports.drive import DriveBlobStore
from .transports.sheets import SheetsRingStore


def add_transport_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--transport", choices=["local", "gcs", "drive", "sheets"], default="local")
    parser.add_argument("--local-root", default=".skirk-local-store")
    parser.add_argument("--bucket", help="Cloud Storage bucket for --transport gcs")
    parser.add_argument("--drive-folder-id", help="Optional Drive folder id for --transport drive")
    parser.add_argument("--spreadsheet-id", help="Spreadsheet id for --transport sheets")
    parser.add_argument("--sheet-range", default="skirk!A:D")
    parser.add_argument("--proxy", default=os.environ.get("SKIRK_SOCKS", "socks5h://127.0.0.1:1080"))
    parser.add_argument("--google-ip", default=os.environ.get("SKIRK_GOOGLE_IP", "216.239.38.120"))
    parser.add_argument(
        "--route-mode",
        choices=["real-pinned", "google-front-pinned"],
        default=os.environ.get("SKIRK_ROUTE_MODE", "real-pinned"),
        help="real-pinned uses the service hostname as SNI; google-front-pinned uses www.google.com SNI plus Host header.",
    )


def add_google_route_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--proxy", default=os.environ.get("SKIRK_SOCKS", "socks5h://127.0.0.1:1080"))
    parser.add_argument("--google-ip", default=os.environ.get("SKIRK_GOOGLE_IP", "216.239.38.120"))
    parser.add_argument(
        "--route-mode",
        choices=["real-pinned", "google-front-pinned"],
        default=os.environ.get("SKIRK_ROUTE_MODE", "real-pinned"),
    )


def build_hybrid_stores(args: argparse.Namespace) -> tuple[DriveBlobStore, SheetsRingStore]:
    if not args.spreadsheet_id:
        raise SystemExit("--spreadsheet-id is required")
    return (
        DriveBlobStore(
            folder_id=args.drive_folder_id,
            proxy=args.proxy,
            google_ip=args.google_ip,
            route_mode=args.route_mode,
        ),
        SheetsRingStore(
            spreadsheet_id=args.spreadsheet_id,
            range_name=args.sheet_range,
            proxy=args.proxy,
            google_ip=args.google_ip,
            route_mode=args.route_mode,
        ),
    )


def cmd_modes(_: argparse.Namespace) -> int:
    rows = [
        {
            "name": mode.name,
            "status": mode.status,
            "throughput": mode.throughput,
            "latency": mode.latency,
            "notes": mode.notes,
        }
        for mode in MODES
    ]
    print(json.dumps(rows, indent=2))
    return 0


def cmd_keygen(_: argparse.Namespace) -> int:
    print(random_secret())
    return 0


def cmd_blobq_send(args: argparse.Namespace) -> int:
    store = build_blob_store(args)
    result = send_file(
        store=store,
        input_path=args.input,
        secret=args.secret,
        session_id=args.session,
        direction=Direction[args.direction],
        chunk_size=args.chunk_size,
        cleanup_existing=args.cleanup_existing,
    )
    print(json.dumps(result.__dict__, indent=2))
    return 0


def cmd_blobq_recv(args: argparse.Namespace) -> int:
    store = build_blob_store(args)
    result = receive_file(
        store=store,
        output_path=args.output,
        secret=args.secret,
        session_id=args.session,
        direction=Direction[args.direction],
        delete_after=args.delete_after,
    )
    print(json.dumps(result.__dict__, indent=2))
    return 0


def cmd_hybrid_send(args: argparse.Namespace) -> int:
    data_store, control_store = build_hybrid_stores(args)
    result = hybrid_send_file(
        data_store=data_store,
        control_store=control_store,
        input_path=args.input,
        secret=args.secret,
        session_id=args.session,
        direction=Direction[args.direction],
        chunk_size=args.chunk_size,
        cleanup_existing=args.cleanup_existing,
    )
    print(json.dumps(result.__dict__, indent=2))
    return 0


def cmd_hybrid_recv(args: argparse.Namespace) -> int:
    data_store, control_store = build_hybrid_stores(args)
    result = hybrid_receive_file(
        data_store=data_store,
        control_store=control_store,
        output_path=args.output,
        secret=args.secret,
        session_id=args.session,
        direction=Direction[args.direction],
        delete_after=args.delete_after,
    )
    print(json.dumps(result.__dict__, indent=2))
    return 0


def cmd_e2e_local(args: argparse.Namespace) -> int:
    from tempfile import TemporaryDirectory

    secret = args.secret or random_secret()
    payload = (b"skirk-e2e\n" + os.urandom(1024 * 1024 + 333))
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "store"
        src = Path(tmp) / "input.bin"
        dst = Path(tmp) / "output.bin"
        src.write_bytes(payload)
        args.transport = "local"
        args.local_root = str(root)
        store = build_blob_store(args)
        sent = send_file(store=store, input_path=src, secret=secret, chunk_size=128 * 1024)
        received = receive_file(store=store, output_path=dst, secret=secret, session_id=sent.session_id)
        if dst.read_bytes() != payload:
            raise SystemExit("E2E payload mismatch")
    print(
        json.dumps(
            {
                "ok": True,
                "session_id": sent.session_id,
                "objects": len(sent.objects),
                "bytes": received.bytes_plaintext,
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skirk")
    sub = parser.add_subparsers(dest="command", required=True)

    modes = sub.add_parser("modes", help="List selectable Skirk modes")
    modes.set_defaults(func=cmd_modes)

    keygen = sub.add_parser("keygen", help="Generate a 256-bit shared secret")
    keygen.set_defaults(func=cmd_keygen)

    send = sub.add_parser("blobq-send", help="Send a file through a BlobQ transport")
    add_transport_args(send)
    send.add_argument("--secret", required=True)
    send.add_argument("--session")
    send.add_argument("--direction", choices=["UP", "DOWN"], default="UP")
    send.add_argument("--chunk-size", type=int, default=4 * 1024 * 1024)
    send.add_argument("--cleanup-existing", action="store_true")
    send.add_argument("input")
    send.set_defaults(func=cmd_blobq_send)

    recv = sub.add_parser("blobq-recv", help="Receive a file through a BlobQ transport")
    add_transport_args(recv)
    recv.add_argument("--secret", required=True)
    recv.add_argument("--session", required=True)
    recv.add_argument("--direction", choices=["UP", "DOWN"], default="UP")
    recv.add_argument("--delete-after", action="store_true")
    recv.add_argument("output")
    recv.set_defaults(func=cmd_blobq_recv)

    hybrid_send = sub.add_parser("hybrid-send", help="Send using Drive data lane and Sheets control lane")
    add_google_route_args(hybrid_send)
    hybrid_send.add_argument("--drive-folder-id")
    hybrid_send.add_argument("--spreadsheet-id", required=True)
    hybrid_send.add_argument("--sheet-range", default="skirk!A:D")
    hybrid_send.add_argument("--secret", required=True)
    hybrid_send.add_argument("--session")
    hybrid_send.add_argument("--direction", choices=["UP", "DOWN"], default="UP")
    hybrid_send.add_argument("--chunk-size", type=int, default=4096)
    hybrid_send.add_argument("--cleanup-existing", action="store_true")
    hybrid_send.add_argument("input")
    hybrid_send.set_defaults(func=cmd_hybrid_send)

    hybrid_recv = sub.add_parser("hybrid-recv", help="Receive using Drive data lane and Sheets control lane")
    add_google_route_args(hybrid_recv)
    hybrid_recv.add_argument("--drive-folder-id")
    hybrid_recv.add_argument("--spreadsheet-id", required=True)
    hybrid_recv.add_argument("--sheet-range", default="skirk!A:D")
    hybrid_recv.add_argument("--secret", required=True)
    hybrid_recv.add_argument("--session", required=True)
    hybrid_recv.add_argument("--direction", choices=["UP", "DOWN"], default="UP")
    hybrid_recv.add_argument("--delete-after", action="store_true")
    hybrid_recv.add_argument("output")
    hybrid_recv.set_defaults(func=cmd_hybrid_recv)

    e2e = sub.add_parser("e2e-local", help="Run deterministic local encrypted BlobQ E2E test")
    add_transport_args(e2e)
    e2e.add_argument("--secret")
    e2e.set_defaults(func=cmd_e2e_local)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
