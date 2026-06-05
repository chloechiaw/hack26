"""Agent-side harness client — tool calls only; never exposes DB paths."""

from __future__ import annotations

import json
import os
import socket
import http.client
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, unix_path: str) -> None:
        super().__init__("localhost")
        self.unix_path = unix_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.unix_path)


def resolve_ipc_target() -> tuple[str, str | None]:
    """Return (mode, target) where mode is 'unix' or 'http'."""
    sock = os.environ.get("IPC_SOCKET", "").strip()
    if sock:
        return "unix", sock
    url = os.environ.get("HARNESS_URL", "").strip()
    if url:
        return "http", url.rstrip("/")
    return "http", "http://127.0.0.1:9000"


class HarnessClient:
    """Call harness tools; agent sees only ToolResult-shaped JSON."""

    def __init__(self, *, unix_path: str | None = None, base_url: str | None = None) -> None:
        if unix_path:
            self._mode = "unix"
            self._unix = unix_path
            self._base = ""
        elif base_url:
            self._mode = "http"
            self._unix = None
            self._base = base_url.rstrip("/")
        else:
            mode, target = resolve_ipc_target()
            self._mode = mode
            if mode == "unix":
                self._unix = target
                self._base = ""
            else:
                self._unix = None
                self._base = target or ""

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def events(self) -> dict[str, Any]:
        return self._request("GET", "/events")

    def call_tool(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"name": name, "args": args or {}}).encode()
        return self._request("POST", "/tool", body=body)

    def _request(self, method: str, path: str, body: bytes | None = None) -> dict[str, Any]:
        if self._mode == "unix":
            assert self._unix
            conn = UnixHTTPConnection(self._unix)
            try:
                conn.request(method, path, body=body, headers={"Content-Type": "application/json"} if body else {})
                resp = conn.getresponse()
                raw = resp.read()
                if resp.status >= 400:
                    raise URLError(f"harness {resp.status}: {raw.decode()[:500]}")
                return json.loads(raw.decode())
            finally:
                conn.close()
        url = f"{self._base}{path}"
        req = Request(url, data=body, method=method)
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except OSError as exc:
            raise URLError(str(exc)) from exc
