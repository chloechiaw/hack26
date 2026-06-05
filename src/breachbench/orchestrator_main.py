"""Fleet orchestrator (breachbench/orchestrator): provision DBs + spin N world pairs.

Uses docker CLI (OrbStack / Docker Desktop). Agent: runc, --network none, read-only.
Harness: DB mount + IPC unix socket in shared volume.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATE_WORLDS = ROOT / "db" / "scripts" / "generate_worlds.py"
IPC_SOCK = "/ipc/harness.sock"
DEFAULT_FLEET_PROJECT = "breachbench-fleet"


def _fleet_labels(project: str, i: int, role: str) -> list[str]:
    """OrbStack / Docker Desktop group containers by compose project label."""
    labels = {
        "com.docker.compose.project": project,
        "com.docker.compose.service": f"{role}-{i}",
        "breachbench.role": role,
        "breachbench.world_index": str(i),
    }
    out: list[str] = []
    for key, value in labels.items():
        out.extend(["--label", f"{key}={value}"])
    return out


def _host_mount_paths(
    ipc_root: Path,
) -> tuple[Path, Path]:
    """Docker bind mounts are resolved on the HOST, not inside this container.

    When the orchestrator runs in Docker, set HOST_REPO to the repo path on the host
    (e.g. -e HOST_REPO="$(pwd)" -v "$(pwd)/db/worlds:/app/db/worlds").
    """
    host_repo = os.environ.get("HOST_REPO", "").strip()
    if host_repo:
        worlds_dir = Path(host_repo) / "db" / "worlds"
        host_ipc = os.environ.get("HOST_IPC_ROOT", os.environ.get("IPC_ROOT", str(ipc_root)))
        return worlds_dir, Path(host_ipc)
    return ROOT / "db" / "worlds", ipc_root


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=check)


def provision_world_dbs() -> None:
    db = ROOT / "db" / "coffeeshop.db"
    seed = ROOT / "db" / "coffeeshop_seed.sql"
    if not db.is_file() and seed.is_file():
        conn = sqlite3.connect(db)
        try:
            conn.executescript(seed.read_text())
            conn.commit()
        finally:
            conn.close()
    if GENERATE_WORLDS.is_file():
        run([sys.executable, str(GENERATE_WORLDS)])


def spin_world(
    i: int,
    *,
    harness_image: str,
    agent_image: str,
    worlds_dir: Path,
    ipc_root: Path,
    network: str,
    project: str,
    agent_once: bool,
) -> None:
    world_id = f"world_{i}"
    ipc = ipc_root / world_id
    ipc.mkdir(parents=True, exist_ok=True)
    db_host = worlds_dir / f"{world_id}.db"
    if not db_host.is_file():
        raise FileNotFoundError(f"missing world db for bind mount: {db_host}")

    harness_name = f"bb-harness-{i}"
    agent_name = f"bb-agent-{i}"
    port = 9000 + i

    run(["docker", "rm", "-f", harness_name, agent_name], check=False)

    run([
        "docker", "run", "-d",
        "--name", harness_name,
        *_fleet_labels(project, i, "harness"),
        "--network", network,
        "-p", f"127.0.0.1:{port}:9000",
        "-v", f"{db_host.resolve()}:/data/world.db:rw",
        "-v", f"{ipc.resolve()}:/ipc:rw",
        "-e", f"WORLD_ID={world_id}",
        "-e", "IPC_DIR=/ipc",
        harness_image,
        "--world-id", world_id,
        "--ipc-dir", "/ipc",
    ])

    # Agent: hardened, no network — IPC via shared unix socket only
    agent_cmd = [
        "docker", "run", "-d",
        "--name", agent_name,
        *_fleet_labels(project, i, "agent"),
        "--network", "none",
        "--read-only",
        "--restart", "unless-stopped",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--tmpfs", "/home/agent:rw,noexec,nosuid,size=128m",
        "--cap-drop=ALL",
        "--security-opt", "no-new-privileges:true",
        "--pids-limit", "256",
        "--memory", "512m",
        "--cpus", "0.5",
        "-v", f"{ipc.resolve()}:/ipc:rw",
        "-e", f"IPC_SOCKET={IPC_SOCK}",
        "-e", "IPC_DIR=/ipc",
        agent_image,
    ]
    if agent_once:
        agent_cmd.append("--once")
    run(agent_cmd)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Spin BreachBench fleet (OrbStack/Docker)")
    ap.add_argument("-n", "--worlds", type=int, default=int(os.environ.get("N_WORLDS", "50")))
    ap.add_argument("--harness-image", default=os.environ.get("HARNESS_IMAGE", "breachbench/harness:latest"))
    ap.add_argument("--agent-image", default=os.environ.get("AGENT_IMAGE", "breachbench/agent:latest"))
    ap.add_argument("--ipc-root", type=Path, default=Path(os.environ.get("IPC_ROOT", "/tmp/breachbench")))
    ap.add_argument("--network", default=os.environ.get("FLEET_NETWORK", "breachbench-fleet"))
    ap.add_argument(
        "--project",
        default=os.environ.get("FLEET_PROJECT", DEFAULT_FLEET_PROJECT),
        help="compose project label — groups all fleet containers in OrbStack/Docker UI",
    )
    ap.add_argument("--build", action="store_true", help="build harness + agent images")
    ap.add_argument(
        "--agent-once",
        action="store_true",
        help="agent runs IPC smoke test then exits (default: stay running idle)",
    )
    ap.add_argument("--down", action="store_true", help="remove fleet containers (by project label)")
    args = ap.parse_args(argv)

    if args.down:
        listed = subprocess.run(
            [
                "docker", "ps", "-aq",
                "--filter", f"label=com.docker.compose.project={args.project}",
            ],
            capture_output=True, text=True, check=False,
        )
        ids = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
        if ids:
            run(["docker", "rm", "-f", *ids], check=False)
        else:
            run(["docker", "rm", "-f", *[f"bb-harness-{i}" for i in range(args.worlds)],
                 *[f"bb-agent-{i}" for i in range(args.worlds)]], check=False)
        print(f"fleet torn down (project={args.project})")
        return 0

    if args.build:
        run(["docker", "build", "-f", "docker/Dockerfile.harness", "-t", args.harness_image, str(ROOT)])
        run(["docker", "build", "-f", "docker/Dockerfile.agent", "-t", args.agent_image, str(ROOT)])
        run(["docker", "build", "-f", "docker/Dockerfile.orchestrator", "-t", "breachbench/orchestrator:latest", str(ROOT)])

    run(["docker", "network", "create", args.network], check=False)
    provision_world_dbs()

    worlds_dir, ipc_root = _host_mount_paths(args.ipc_root)
    worlds_dir.mkdir(parents=True, exist_ok=True)
    ipc_root.mkdir(parents=True, exist_ok=True)
    print(f"host worlds_dir={worlds_dir}")
    print(f"host ipc_root={ipc_root}")
    print(f"compose project={args.project}  (OrbStack/Docker UI group)")

    for i in range(args.worlds):
        spin_world(
            i,
            harness_image=args.harness_image,
            agent_image=args.agent_image,
            worlds_dir=worlds_dir,
            ipc_root=ipc_root,
            network=args.network,
            project=args.project,
            agent_once=args.agent_once,
        )

    up = subprocess.run(
        ["docker", "ps", "--filter", "name=bb-harness-", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=False,
    ).stdout.strip().splitlines()
    up = [n for n in up if n]
    print(f"\nFleet up: {args.worlds} worlds requested; {len(up)} harness containers running")
    print(f"  harness  http://127.0.0.1:9000/health  (+1 port per world)")
    agent_mode = "smoke then exit" if args.agent_once else "idle (long-running)"
    print(f"  agent    --network none  IPC unix {IPC_SOCK} in {ipc_root}/world_N/  mode={agent_mode}")
    if len(up) < args.worlds:
        print("  WARNING: not all harnesses are up — check: docker logs bb-harness-0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
