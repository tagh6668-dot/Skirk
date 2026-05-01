"""Small curl wrapper for Google-fronted REST probes and transports."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .transports.base import TransportError


@dataclass(frozen=True)
class CurlResult:
    status: int
    body: bytes
    metrics: dict
    stderr: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass(frozen=True)
class GoogleRoute:
    """Route an HTTPS request through the known Google-reachable edge."""

    proxy: str = "socks5h://127.0.0.1:1080"
    google_ip: str = "216.239.38.120"
    mode: str = "real-pinned"

    def request_host(self, host: str) -> str:
        if self.mode == "google-front-pinned":
            return "www.google.com"
        return host

    def connect_host(self, host: str) -> str:
        return self.request_host(host)

    def headers(self, host: str) -> list[str]:
        if self.mode == "google-front-pinned":
            return ["-H", f"Host: {host}"]
        return []


class CurlHttpClient:
    def __init__(self, route: GoogleRoute, timeout_seconds: int = 240):
        self.route = route
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        *,
        method: str,
        host: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        output_binary: bool = True,
    ) -> CurlResult:
        request_host = self.route.request_host(host)
        url = f"https://{request_host}{path}"
        with tempfile.NamedTemporaryFile(delete=False) as body_file:
            body_path = Path(body_file.name)
        args = [
            "/usr/bin/curl",
            "-sS",
            "--proxy",
            self.route.proxy,
            "--connect-timeout",
            "20",
            "--max-time",
            str(self.timeout_seconds),
            "--http1.1",
            "--connect-to",
            f"{self.route.connect_host(host)}:443:{self.route.google_ip}:443",
            "-X",
            method,
            "-o",
            str(body_path),
            "-w",
            "%{json}",
        ]
        args += self.route.headers(host)
        for key, value in (headers or {}).items():
            args += ["-H", f"{key}: {value}"]
        if body is not None:
            args += ["--data-binary", "@-"]
        args.append(url)
        proc = subprocess.run(
            args,
            input=body,
            capture_output=True,
            timeout=self.timeout_seconds + 10,
        )
        try:
            metrics = json.loads(proc.stdout.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            metrics = {"raw": proc.stdout.decode("utf-8", errors="replace")}
        response_body = body_path.read_bytes() if body_path.exists() else b""
        body_path.unlink(missing_ok=True)
        status = int(metrics.get("http_code") or 0)
        if proc.returncode != 0:
            raise TransportError(
                f"curl failed exit={proc.returncode} status={status}: {proc.stderr.decode('utf-8', errors='replace').strip()}"
            )
        if not output_binary:
            response_body.decode("utf-8")
        return CurlResult(
            status=status,
            body=response_body,
            metrics=metrics,
            stderr=proc.stderr.decode("utf-8", errors="replace").strip(),
        )


def gcloud_access_token() -> str:
    if token := os.environ.get("SKIRK_ACCESS_TOKEN"):
        return token
    env = os.environ.copy()
    env["PATH"] = f"{Path.home() / 'google-cloud-sdk/bin'}:{env.get('PATH', '')}"
    proc = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
        env=env,
    )
    return proc.stdout.strip()
