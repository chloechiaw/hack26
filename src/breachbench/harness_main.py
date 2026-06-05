"""Per-world harness (breachbench/harness): SQLite, event_log, SimAPI, IPC server."""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import threading
from pathlib import Path

from breachbench.database.events import fetch_event_log_at_path
from breachbench.ipc.server import HarnessState, make_handler_class, serve_tcp, serve_unix
from breachbench.scenario import Scenario
from breachbench.sim.vending_sim import VendingSim

ROOT = Path(__file__).resolve().parents[2]
SEED_SQL = ROOT / "db" / "coffeeshop_seed.sql"
DEFAULT_SCENARIO = ROOT / "scenarios" / "s01_spoofed_supplier.json"
UNIX_SOCK_NAME = "harness.sock"


def ensure_world_db(db_path: Path) -> None:
    if db_path.is_file():
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    template = ROOT / "db" / "coffeeshop.db"
    if template.is_file():
        shutil.copy2(template, db_path)
        return
    if not SEED_SQL.is_file():
        raise FileNotFoundError(f"no DB at {db_path} and no seed at {SEED_SQL}")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SEED_SQL.read_text())
        conn.commit()
    finally:
        conn.close()


def load_scenario(path: Path) -> Scenario:
    return Scenario.load(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BreachBench per-world harness")
    ap.add_argument("--world-id", default=os.environ.get("WORLD_ID", "world_0"))
    ap.add_argument("--db", type=Path, default=Path(os.environ.get("WORLD_DB", "/data/world.db")))
    ap.add_argument("--ipc-dir", type=Path, default=Path(os.environ.get("IPC_DIR", "/ipc")))
    ap.add_argument("--port", type=int, default=int(os.environ.get("HARNESS_PORT", "9000")))
    ap.add_argument("--scenario", type=Path, default=Path(os.environ.get("SCENARIO", str(DEFAULT_SCENARIO))))
    args = ap.parse_args(argv)

    ensure_world_db(args.db)
    args.ipc_dir.mkdir(parents=True, exist_ok=True)
    unix_path = args.ipc_dir / UNIX_SOCK_NAME

    scen = load_scenario(args.scenario)
    sim = VendingSim(scen)
    state = HarnessState(
        world_id=args.world_id,
        db_path=args.db,
        sim=sim,
        unix_socket=unix_path,
    )
    handler = make_handler_class(state)
    n_events = len(fetch_event_log_at_path(args.db, args.world_id))

    tcp = serve_tcp(args.port, handler)
    unix = serve_unix(unix_path, handler)
    os.chmod(unix_path, 0o666)

    print(f"harness ready  world_id={args.world_id}  db={args.db}  seed_events={n_events}")
    print(f"  tcp   0.0.0.0:{args.port}  GET /health /events  POST /tool")
    print(f"  unix  {unix_path}  (agent IPC, --network none)")

    threading.Thread(target=tcp.serve_forever, daemon=True, name="harness-tcp").start()
    try:
        unix.serve_forever()
    except KeyboardInterrupt:
        print("harness stopped")
    finally:
        tcp.shutdown()
        unix.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
