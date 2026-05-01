"""Sheets-backed low-rate BlobStore.

This treats a spreadsheet range as an append-only log. Deletes are tombstones,
not physical row removal, because the simple Values API is much safer than
structural sheet mutation for this prototype.
"""

from __future__ import annotations

import base64
import json
import time
from urllib.parse import quote, urlencode

from skirk.curl import CurlHttpClient, GoogleRoute, gcloud_access_token

from .base import ObjectInfo, TransportError


class SheetsRingStore:
    host = "sheets.googleapis.com"

    def __init__(
        self,
        *,
        spreadsheet_id: str,
        range_name: str = "skirk!A:D",
        proxy: str = "socks5h://127.0.0.1:1080",
        google_ip: str = "216.239.38.120",
        route_mode: str = "real-pinned",
        token: str | None = None,
    ):
        self.spreadsheet_id = spreadsheet_id
        self.range_name = range_name
        self.token = token or gcloud_access_token()
        self.client = CurlHttpClient(GoogleRoute(proxy=proxy, google_ip=google_ip, mode=route_mode))

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _append_row(self, row: list[str]) -> None:
        encoded_range = quote(self.range_name, safe="")
        params = urlencode({"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"})
        body = json.dumps({"majorDimension": "ROWS", "values": [row]}).encode("utf-8")
        result = self.client.request(
            method="POST",
            host=self.host,
            path=f"/v4/spreadsheets/{self.spreadsheet_id}/values/{encoded_range}:append?{params}",
            headers=self._auth() | {"Content-Type": "application/json"},
            body=body,
        )
        if not result.ok:
            raise TransportError(f"Sheets append failed status={result.status}: {result.body[:500]!r}")

    def _rows(self) -> list[list[str]]:
        encoded_range = quote(self.range_name, safe="")
        result = self.client.request(
            method="GET",
            host=self.host,
            path=f"/v4/spreadsheets/{self.spreadsheet_id}/values/{encoded_range}",
            headers=self._auth(),
        )
        if not result.ok:
            raise TransportError(f"Sheets read failed status={result.status}: {result.body[:500]!r}")
        payload = json.loads(result.body.decode("utf-8"))
        return payload.get("values", [])

    def put(self, name: str, data: bytes) -> None:
        encoded = base64.urlsafe_b64encode(data).decode("ascii")
        self._append_row([name, encoded, str(time.time_ns()), "put"])

    def get(self, name: str) -> bytes:
        latest: list[str] | None = None
        for row in self._rows():
            if len(row) >= 4 and row[0] == name:
                latest = row
        if not latest or latest[3] == "delete":
            raise FileNotFoundError(name)
        return base64.urlsafe_b64decode(latest[1].encode("ascii"))

    def list(self, prefix: str) -> list[ObjectInfo]:
        latest: dict[str, list[str]] = {}
        for row in self._rows():
            if len(row) >= 4 and row[0].startswith(prefix):
                latest[row[0]] = row
        return [
            ObjectInfo(name=name, size=len(row[1]), updated=row[2])
            for name, row in sorted(latest.items())
            if row[3] != "delete"
        ]

    def delete(self, name: str) -> None:
        self._append_row([name, "", str(time.time_ns()), "delete"])
