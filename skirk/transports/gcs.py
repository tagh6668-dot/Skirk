"""Cloud Storage BlobStore using curl and Google-fronted routing."""

from __future__ import annotations

import json
from urllib.parse import quote, urlencode

from skirk.curl import CurlHttpClient, GoogleRoute, gcloud_access_token

from .base import ObjectInfo, TransportError


class GcsBlobStore:
    host = "storage.googleapis.com"

    def __init__(
        self,
        *,
        bucket: str,
        proxy: str = "socks5h://127.0.0.1:1080",
        google_ip: str = "216.239.38.120",
        route_mode: str = "real-pinned",
        token: str | None = None,
    ):
        self.bucket = bucket
        self.token = token or gcloud_access_token()
        self.client = CurlHttpClient(GoogleRoute(proxy=proxy, google_ip=google_ip, mode=route_mode))

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def put(self, name: str, data: bytes) -> None:
        path = f"/upload/storage/v1/b/{self.bucket}/o?{urlencode({'uploadType': 'media', 'name': name})}"
        result = self.client.request(
            method="POST",
            host=self.host,
            path=path,
            headers=self._auth() | {"Content-Type": "application/octet-stream", "Expect": ""},
            body=data,
        )
        if not result.ok:
            raise TransportError(f"Cloud Storage upload failed status={result.status}: {result.body[:500]!r}")

    def get(self, name: str) -> bytes:
        encoded = quote(name, safe="")
        path = f"/storage/v1/b/{self.bucket}/o/{encoded}?alt=media"
        result = self.client.request(method="GET", host=self.host, path=path, headers=self._auth())
        if not result.ok:
            raise TransportError(f"Cloud Storage download failed status={result.status}: {result.body[:500]!r}")
        return result.body

    def list(self, prefix: str) -> list[ObjectInfo]:
        path = f"/storage/v1/b/{self.bucket}/o?{urlencode({'prefix': prefix})}"
        result = self.client.request(method="GET", host=self.host, path=path, headers=self._auth())
        if not result.ok:
            raise TransportError(f"Cloud Storage list failed status={result.status}: {result.body[:500]!r}")
        payload = json.loads(result.body.decode("utf-8"))
        return [
            ObjectInfo(name=item["name"], size=int(item.get("size", 0)), updated=item.get("updated"))
            for item in payload.get("items", [])
        ]

    def delete(self, name: str) -> None:
        encoded = quote(name, safe="")
        path = f"/storage/v1/b/{self.bucket}/o/{encoded}"
        result = self.client.request(method="DELETE", host=self.host, path=path, headers=self._auth())
        if result.status not in (200, 204, 404):
            raise TransportError(f"Cloud Storage delete failed status={result.status}: {result.body[:500]!r}")
