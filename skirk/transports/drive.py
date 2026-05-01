"""Drive-backed BlobStore using Drive API v3 REST endpoints."""

from __future__ import annotations

import json
import time
from urllib.parse import quote, urlencode

from skirk.curl import CurlHttpClient, GoogleRoute, gcloud_access_token

from .base import ObjectInfo, TransportError


class DriveBlobStore:
    host = "www.googleapis.com"

    def __init__(
        self,
        *,
        folder_id: str | None = None,
        proxy: str = "socks5h://127.0.0.1:1080",
        google_ip: str = "216.239.38.120",
        route_mode: str = "real-pinned",
        token: str | None = None,
    ):
        self.folder_id = folder_id
        self.token = token or gcloud_access_token()
        self.client = CurlHttpClient(GoogleRoute(proxy=proxy, google_ip=google_ip, mode=route_mode))

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def _q(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def put(self, name: str, data: bytes) -> None:
        boundary = f"skirk-{int(time.time() * 1000)}"
        metadata: dict[str, object] = {
            "name": name,
            "mimeType": "application/octet-stream",
            "appProperties": {"skirkName": name},
        }
        if self.folder_id:
            metadata["parents"] = [self.folder_id]
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata, separators=(',', ':'))}\r\n"
            f"--{boundary}\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        result = self.client.request(
            method="POST",
            host=self.host,
            path="/upload/drive/v3/files?uploadType=multipart&fields=id,name,size",
            headers=self._auth() | {"Content-Type": f"multipart/related; boundary={boundary}", "Expect": ""},
            body=body,
        )
        if not result.ok:
            raise TransportError(f"Drive upload failed status={result.status}: {result.body[:500]!r}")

    def _query_for_name(self, name: str | None = None, prefix: str | None = None) -> str:
        clauses = ["trashed = false"]
        if self.folder_id:
            clauses.append(f"'{self.folder_id}' in parents")
        if name is not None:
            clauses.append(f"name = '{self._q(name)}'")
        if prefix is not None:
            clauses.append(f"name contains '{self._q(prefix)}'")
        return " and ".join(clauses)

    def list(self, prefix: str) -> list[ObjectInfo]:
        params = {
            "q": self._query_for_name(prefix=prefix),
            "fields": "files(id,name,size,modifiedTime)",
            "pageSize": "1000",
        }
        result = self.client.request(
            method="GET",
            host=self.host,
            path=f"/drive/v3/files?{urlencode(params)}",
            headers=self._auth(),
        )
        if not result.ok:
            raise TransportError(f"Drive list failed status={result.status}: {result.body[:500]!r}")
        payload = json.loads(result.body.decode("utf-8"))
        return [
            ObjectInfo(
                name=item["name"],
                size=int(item.get("size", 0)) if "size" in item else None,
                updated=item.get("modifiedTime"),
                token=item["id"],
            )
            for item in payload.get("files", [])
            if item.get("name", "").startswith(prefix)
        ]

    def _latest(self, name: str) -> ObjectInfo:
        params = {
            "q": self._query_for_name(name=name),
            "fields": "files(id,name,size,modifiedTime)",
            "orderBy": "modifiedTime desc",
            "pageSize": "1",
        }
        result = self.client.request(
            method="GET",
            host=self.host,
            path=f"/drive/v3/files?{urlencode(params)}",
            headers=self._auth(),
        )
        if not result.ok:
            raise TransportError(f"Drive lookup failed status={result.status}: {result.body[:500]!r}")
        files = json.loads(result.body.decode("utf-8")).get("files", [])
        if not files:
            raise FileNotFoundError(name)
        item = files[0]
        return ObjectInfo(name=item["name"], size=int(item.get("size", 0)), updated=item.get("modifiedTime"), token=item["id"])

    def get(self, name: str) -> bytes:
        info = self._latest(name)
        result = self.client.request(
            method="GET",
            host=self.host,
            path=f"/drive/v3/files/{quote(info.token or '', safe='')}?alt=media",
            headers=self._auth(),
        )
        if not result.ok:
            raise TransportError(f"Drive download failed status={result.status}: {result.body[:500]!r}")
        return result.body

    def delete(self, name: str) -> None:
        for info in self.list(name):
            if info.name != name or not info.token:
                continue
            result = self.client.request(
                method="DELETE",
                host=self.host,
                path=f"/drive/v3/files/{quote(info.token, safe='')}",
                headers=self._auth(),
            )
            if result.status not in (200, 204, 404):
                raise TransportError(f"Drive delete failed status={result.status}: {result.body[:500]!r}")
