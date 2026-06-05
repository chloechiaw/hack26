#!/usr/bin/env python3
"""Serve the fleet dashboard and read event_log from per-world SQLite files.

Usage (from repo root):

    python observability/serve_dashboard.py
    python observability/serve_dashboard.py --port 8766   # if 8765 is taken
    # open http://127.0.0.1:8765/

API:
    GET /api/worlds
    GET /api/worlds/<world_id>/events
"""

from __future__ import annotations

import argparse
import errno
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "observability"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from breachbench.database.events import (  # noqa: E402
    fetch_event_log_any_world,
    list_world_ids,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class DashboardHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[dashboard] {self.address_string()} - {fmt % args}")

    def _set_cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404, "Not found")
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._set_cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_GET(self) -> None:
        raw = unquote(self.path.split("?", 1)[0])
        if raw in ("/", "/dashboard.html"):
            return self._send_file(OBS / "dashboard.html")
        if raw == "/api/worlds":
            return self._send_json(200, {"worlds": list_world_ids()})
        if raw.startswith("/api/worlds/") and raw.endswith("/events"):
            world_id = raw.removeprefix("/api/worlds/").removesuffix("/events").strip("/")
            if not world_id or "/" in world_id:
                return self._send_json(400, {"error": "invalid world_id"})
            try:
                events = fetch_event_log_any_world(world_id)
            except FileNotFoundError:
                return self._send_json(404, {"error": f"world db not found: {world_id}"})
            except Exception as exc:
                return self._send_json(500, {"error": str(exc)})
            return self._send_json(200, {"world_id": world_id, "events": events})
        if raw.startswith("/"):
            candidate = OBS / raw.lstrip("/")
            if candidate.is_file() and candidate.resolve().is_relative_to(OBS.resolve()):
                return self._send_file(candidate)
        self.send_error(404, "Not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="BreachBench fleet dashboard + event_log API")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"bind address (default {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    args = parser.parse_args()

    try:
        server = DashboardHTTPServer((args.host, args.port), DashboardHandler)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(f"Port {args.port} is already in use.", file=sys.stderr)
            print("  Another dashboard server may still be running.", file=sys.stderr)
            print(f"  Stop it:  lsof -ti :{args.port} | xargs kill", file=sys.stderr)
            print(
                f"  Or use another port:  python observability/serve_dashboard.py --port {args.port + 1}",
                file=sys.stderr,
            )
            sys.exit(1)
        raise

    url = f"http://{args.host}:{args.port}/"
    print(f"BreachBench dashboard → {url}")
    print(f"Events API          → http://{args.host}:{args.port}/api/worlds/world_0/events")
    print("Open that URL in the browser (not file://) so /api/... is same-origin.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
