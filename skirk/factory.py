"""Build selectable transports from CLI arguments."""

from __future__ import annotations

from argparse import Namespace

from .transports.base import BlobStore
from .transports.drive import DriveBlobStore
from .transports.gcs import GcsBlobStore
from .transports.local import LocalBlobStore
from .transports.sheets import SheetsRingStore


def build_blob_store(args: Namespace) -> BlobStore:
    transport = args.transport
    if transport == "local":
        return LocalBlobStore(args.local_root)
    if transport == "gcs":
        if not args.bucket:
            raise SystemExit("--bucket is required for --transport gcs")
        return GcsBlobStore(
            bucket=args.bucket,
            proxy=args.proxy,
            google_ip=args.google_ip,
            route_mode=args.route_mode,
        )
    if transport == "drive":
        return DriveBlobStore(
            folder_id=args.drive_folder_id,
            proxy=args.proxy,
            google_ip=args.google_ip,
            route_mode=args.route_mode,
        )
    if transport == "sheets":
        if not args.spreadsheet_id:
            raise SystemExit("--spreadsheet-id is required for --transport sheets")
        return SheetsRingStore(
            spreadsheet_id=args.spreadsheet_id,
            range_name=args.sheet_range,
            proxy=args.proxy,
            google_ip=args.google_ip,
            route_mode=args.route_mode,
        )
    raise SystemExit(f"unsupported transport: {transport}")
