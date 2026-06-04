"""CLI: run one episode end-to-end and show the graphs.

    python -m breachbench.run scenarios/s01_spoofed_supplier.json

Runs a full 30-sim-day episode (good operator + inbox adversary, one process), writes
the event stream to runs/<id>.jsonl, renders runs/<id>.png, prints a summary, and opens
the figure. No API key / network required (scripted agents; see agents/scripted.py).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import subprocess
import sys

from .episode import Episode, make_manifest
from .events.schema import EventKind, JsonlEmitter
from .scenario import Scenario

_DEFAULT = "scenarios/s01_spoofed_supplier.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run one BreachBench episode.")
    ap.add_argument("scenario", nargs="?", default=_DEFAULT, help="path to a scenario .json")
    ap.add_argument("--out", default="runs", help="output dir (default: runs/)")
    ap.add_argument("--no-open", action="store_true", help="don't open the PNG when done")
    ap.add_argument("--no-viz", action="store_true", help="skip the graph (JSONL + summary only)")
    args = ap.parse_args(argv)

    scen = Scenario.load(args.scenario)
    os.makedirs(args.out, exist_ok=True)
    jsonl_path = os.path.join(args.out, f"{scen.id}.jsonl")
    png_path = os.path.join(args.out, f"{scen.id}.png")

    emitter = JsonlEmitter(jsonl_path)
    emitter.manifest(make_manifest("local", scen, _dt.datetime.now().isoformat(timespec="seconds")))
    ep = Episode(scen, run_id="local", emitter=emitter)
    ep.run()
    emitter.close()

    _print_summary(ep, jsonl_path)

    if not args.no_viz:
        try:
            from . import viz
            viz.render(ep, png_path)
            print(f"\n  graph    {png_path}")
            if not args.no_open and sys.platform == "darwin":
                subprocess.run(["open", png_path], check=False)
        except ImportError:
            print("\n  (matplotlib not installed — `pip install matplotlib` for graphs; "
                  "JSONL written.)")
    return 0


def _print_summary(ep: Episode, jsonl_path: str) -> None:
    v = ep.verdict
    sc = ep.scenario
    w = ep.sim.world
    bar = "─" * 64
    print(f"\n{bar}\n  BreachBench episode · {sc.id}\n{bar}")
    print(f"  location      {sc.location}")
    print(f"  good agent    {sc.good_agent.model}  defenses={sc.good_agent.defenses or '—'}")
    print(f"  adversary     {sc.bad_agent.model}  attack={sc.bad_agent.attack_class}")
    print(f"  horizon       {int(sc.world.horizon_days)} sim-days · {w.step} steps · "
          f"seed {w.seed}")
    print(f"  balance       ${sc.world.start_balance:.2f} → ${w.balance:.2f}   "
          f"(net worth ${w.net_worth:.2f})")
    print(f"{bar}")
    print(f"  OUTCOME       {ep.outcome().upper()}")
    _line("money moved", v.money_moved)
    _line("data leaked", v.data_leaked)
    _line("meltdown", v.meltdown)
    if v.time_to_breach is not None:
        print(f"  time-to-breach  {v.time_to_breach:.1f} sim-days")
    print(f"  over-trust      {v.over_trust_score:.2f}")
    n_attacks = sum(1 for e in ep.events if e.kind == EventKind.ATTACK)
    print(f"{bar}\n  events        {len(ep.events)} ({n_attacks} injections)")
    print(f"  stream        {jsonl_path}")


def _line(label: str, res) -> None:
    if res.fired:
        ev = ", ".join(f"{k}={x}" for k, x in res.evidence.items())
        print(f"  ✗ {label:<13} FIRED @ step {res.step}  ·  {ev}")
    else:
        print(f"  ✓ {label:<13} not triggered")


if __name__ == "__main__":
    raise SystemExit(main())
