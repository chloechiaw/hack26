"""Agent sandbox (breachbench/agent): model loop stub; tools via harness IPC only."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from breachbench.ipc.client import HarnessClient, resolve_ipc_target


def wait_for_harness(client: HarnessClient, *, attempts: int = 30) -> None:
    for i in range(attempts):
        try:
            h = client.health()
            if h.get("ok"):
                print(f"harness ok: {json.dumps(h)}")
                return
        except Exception as exc:
            print(f"waiting for harness ({i + 1}/{attempts}): {exc}")
        time.sleep(2)
    raise RuntimeError("harness not reachable over IPC")


def smoke_tools(client: HarnessClient) -> None:
    """Prove agent sees only ToolResult JSON, not DB."""
    for name, args in (
        ("get_balance_and_transactions", {}),
        ("search_for_suppliers", {"query": "coffee"}),
        ("read_email", {}),
    ):
        out = client.call_tool(name, args)
        print(f"tool {name} -> ok={out.get('ok')} summary={out.get('summary', '')[:120]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BreachBench agent (sandboxed)")
    ap.add_argument("--ipc-dir", type=Path, default=Path(os.environ.get("IPC_DIR", "/ipc")))
    ap.add_argument("--ipc-socket", default=os.environ.get("IPC_SOCKET", ""))
    ap.add_argument("--harness-url", default=os.environ.get("HARNESS_URL", ""))
    ap.add_argument("--once", action="store_true", help="run smoke tools and exit")
    args = ap.parse_args(argv)

    ipc_sock = args.ipc_socket or str(args.ipc_dir / "harness.sock")
    mode, _ = resolve_ipc_target()
    if args.ipc_socket or (mode == "unix" and not args.harness_url):
        client = HarnessClient(unix_path=ipc_sock)
        print(f"agent IPC unix://{ipc_sock}  uid={os.getuid()}  (no DB, no API keys)")
    else:
        client = HarnessClient(base_url=args.harness_url)
        print(f"agent IPC http://{args.harness_url}  uid={os.getuid()}")

    wait_for_harness(client)
    smoke_tools(client)

    if args.once:
        print("agent smoke done")
        return 0

    print("agent idle (replace with LLMOperator + HarnessClient.call_tool)")
    while True:
        time.sleep(300)


if __name__ == "__main__":
    sys.exit(main())
