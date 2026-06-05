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

import itertools

from .episode import Episode, make_manifest
from .events.schema import EventKind, JsonlEmitter
from .experiments.supplier_injection import CHANNELS, DEFENSE_ARMS, build
from .scenario import Scenario

_DEFAULT = "scenarios/s01_spoofed_supplier.json"


def _apply_supplier_experiment(scen: Scenario, *, channel: str, contain: bool) -> Scenario:
    payload = scen.bad_agent.payload.body if scen.bad_agent.payload else ""
    inj = build(channel=channel, contain=contain, payload_text=payload)
    scen.experiment = {
        "mode": "supplier_injection",
        "channel": inj.channel,
        "contain": inj.contain,
        "payload_text": inj.payload_text,
    }
    return scen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run one BreachBench episode.")
    ap.add_argument("scenario", nargs="?", default=_DEFAULT, help="path to a scenario .json")
    ap.add_argument("--out", default="runs", help="output dir (default: runs/)")
    ap.add_argument("--no-open", action="store_true", help="don't open the PNG when done")
    ap.add_argument("--no-viz", action="store_true", help="skip the graph (JSONL + summary only)")
    ap.add_argument(
        "--supplier-matrix",
        action="store_true",
        help="run attack × channel × contain cells (supplier-injection experiment)",
    )
    args = ap.parse_args(argv)

    if args.supplier_matrix:
        return _run_supplier_matrix(args)

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


def _run_supplier_matrix(args) -> int:
    """Run attack_class × channel × defense_arm for one scenario (local matrix smoke)."""
    base = Scenario.load(args.scenario)
    os.makedirs(args.out, exist_ok=True)
    for channel, contain in itertools.product(CHANNELS, DEFENSE_ARMS):
        scen = Scenario.load(args.scenario)
        scen = _apply_supplier_experiment(scen, channel=channel, contain=contain)
        arm = "defense" if contain else "attack"
        run_id = f"{scen.id}_{channel}_{arm}"
        jsonl_path = os.path.join(args.out, f"{run_id}.jsonl")
        emitter = JsonlEmitter(jsonl_path)
        emitter.manifest(make_manifest(run_id, scen, _dt.datetime.now().isoformat(timespec="seconds")))
        ep = Episode(scen, run_id=run_id, emitter=emitter)
        ep.run()
        emitter.close()
        print(f"  {run_id}: {ep.outcome()}  channel={channel} contain={contain}")
    print(f"\n  supplier matrix done → {args.out}/")
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
