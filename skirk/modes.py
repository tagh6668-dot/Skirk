"""Mode registry for Skirk's selectable transports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeInfo:
    name: str
    status: str
    throughput: str
    latency: str
    notes: str


MODES = [
    ModeInfo(
        "gcs-blobq",
        "implemented",
        "highest confirmed bulk candidate",
        "seconds",
        "Encrypted chunk objects in Cloud Storage. Best for bulk transfer when writes work through the SOCKS path.",
    ),
    ModeInfo(
        "drive-blobq",
        "implemented",
        "medium",
        "seconds",
        "Encrypted chunk files in Drive. More overhead than Cloud Storage, but the API route worked.",
    ),
    ModeInfo(
        "sheets-ring",
        "implemented",
        "low",
        "seconds+",
        "Append-only encrypted rows. Use as control channel or tiny mailbox, not data plane.",
    ),
    ModeInfo(
        "apps-script-goose2",
        "template",
        "best remaining interactive candidate",
        "subsecond to seconds",
        "Needs deployed Apps Script + exit. This repo includes the core protocol and placeholder template path.",
    ),
    ModeInfo(
        "app-engine-stream",
        "template",
        "potentially highest if real appspot SNI works",
        "low/medium",
        "Not created yet because App Engine region creation is project-level. Public appspot real-SNI probe worked.",
    ),
    ModeInfo(
        "cloudrun-stream",
        "probe-only failed",
        "would be high",
        "low",
        "Implemented probe showed run.app is not reachable in this network.",
    ),
    ModeInfo(
        "local",
        "implemented",
        "filesystem speed",
        "local",
        "Deterministic E2E simulator for the shared encrypted BlobQ protocol.",
    ),
]
