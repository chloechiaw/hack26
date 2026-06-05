"""Harness HTTP API: health, events, SimAPI tool dispatch."""

from __future__ import annotations

import json
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

if TYPE_CHECKING:
    from ..sim.vending_sim import VendingSim


class ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """Python 3.12 has no socketserver.ThreadingUnixServer — compose it."""


def make_handler_class(state: "HarnessState") -> type[BaseHTTPRequestHandler]:
    class HarnessHandler(BaseHTTPRequestHandler):
        def address_string(self) -> str:
            if isinstance(self.client_address, tuple) and self.client_address:
                return super().address_string()
            return "unix"

        def log_message(self, fmt: str, *args) -> None:
            print(f"[harness {state.world_id}] {self.address_string()} - {fmt % args}")

        def _read_json(self) -> dict[str, Any]:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0:
                return {}
            return json.loads(self.rfile.read(n))

        def _send_json(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = unquote(self.path.split("?", 1)[0])
            if path == "/health":
                return self._send_json(200, {
                    "ok": True,
                    "world_id": state.world_id,
                    "db": str(state.db_path),
                    "ipc_socket": str(state.unix_socket) if state.unix_socket else None,
                })
            if path == "/events":
                return self._send_json(200, {
                    "world_id": state.world_id,
                    "events": state.load_events(),
                })
            self.send_error(404)

        def do_POST(self) -> None:
            path = unquote(self.path.split("?", 1)[0])
            if path != "/tool":
                return self.send_error(404)
            try:
                payload = self._read_json()
                name = payload.get("name", "")
                args = payload.get("args") or {}
                if not name:
                    return self._send_json(400, {"ok": False, "error": "missing tool name"})
                result = state.call_tool(name, args)
                return self._send_json(200, result)
            except Exception as exc:
                return self._send_json(500, {"ok": False, "error": str(exc)})

    return HarnessHandler


class HarnessState:
    def __init__(
        self,
        *,
        world_id: str,
        db_path: Path,
        sim: "VendingSim",
        unix_socket: Path | None = None,
    ) -> None:
        self.world_id = world_id
        self.db_path = db_path
        self.sim = sim
        self.unix_socket = unix_socket

    def load_events(self) -> list[dict[str, Any]]:
        from ..database.events import fetch_event_log_at_path

        return fetch_event_log_at_path(self.db_path, self.world_id)

    def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tr = self.sim.call(name, args)
        return {
            "ok": tr.ok,
            "summary": tr.summary,
            "data": tr.data,
            "ledger_delta": tr.ledger_delta,
        }


def serve_tcp(port: int, handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("0.0.0.0", port), handler)


def serve_unix(socket_path: Path, handler: type[BaseHTTPRequestHandler]) -> ThreadingUnixServer:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()
    return ThreadingUnixServer(str(socket_path), handler)
