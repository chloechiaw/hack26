"""CLI: connectivity ping + one live good-vs-bad episode with real model output.

    python -m breachbench.live --ping                 # test OpenRouter + the 5-model slate
    python -m breachbench.live scenarios/s01_spoofed_supplier.json \
        --good opus-4.8 --bad sonnet-3.5 --days 4      # run one real episode -> replay HTML

Needs OPENROUTER_API_KEY (env or a gitignored .env at repo root).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from . import llm
from .live_episode import LiveEpisode
from .scenario import Scenario

_DEFAULT = "scenarios/s01_spoofed_supplier.json"


def _ping_all() -> int:
    print("  OpenRouter connectivity (model slate: Opus 4.8 + VB-paper models)\n")
    try:
        llm.get_key()
    except llm.OpenRouterError as e:
        print("  ✗ " + str(e))
        return 1
    ok = 0
    for name, slug in llm.MODELS.items():
        r = llm.ping(name)
        mark = "✓" if r["ok"] else "✗"
        ok += r["ok"]
        print(f"  {mark} {name:<16} {slug:<32} {r['detail']}")
    print(f"\n  {ok}/{len(llm.MODELS)} models reachable.")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run one live BreachBench episode (real models).")
    ap.add_argument("scenario", nargs="?", default=_DEFAULT)
    ap.add_argument("--ping", action="store_true", help="test connectivity to the model slate and exit")
    ap.add_argument("--good", default="opus-4.8", help="operator model (friendly name or slug)")
    ap.add_argument("--bad", default="haiku-3.5", help="adversary model (friendly name or slug)")
    ap.add_argument("--days", type=int, default=4, help="bounded sim-days (keep small; real calls)")
    ap.add_argument("--max-turns", type=int, default=6, help="operator tool calls per day")
    ap.add_argument("--inject-day", type=int, default=1, help="sim-day the attack lands (live horizon is short)")
    ap.add_argument("--perplexity", action="store_true",
                    help="source products/prices/suppliers from real web data (Perplexity via OpenRouter)")
    ap.add_argument("--out", default="runs")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args(argv)

    if args.ping:
        return _ping_all()

    try:
        llm.get_key()
    except llm.OpenRouterError as e:
        print("  ✗ " + str(e))
        return 1

    scen = Scenario.load(args.scenario)
    os.makedirs(args.out, exist_ok=True)
    print(f"  running live: good={llm.resolve(args.good)}  vs  adversary={llm.resolve(args.bad)}")
    print(f"  scenario={scen.id}  attack={scen.bad_agent.attack_class}  days={args.days}\n")

    research = None
    if args.perplexity:
        from .research import Perplexity
        research = Perplexity()
        print("  research: Perplexity (perplexity/sonar) — real products/prices/suppliers\n")
    ep = LiveEpisode(scen, args.good, args.bad, days=args.days, max_turns_per_day=args.max_turns,
                     inject_day=args.inject_day, research=research)
    ep.run()
    meta = ep.meta()

    # write transcript json + replay html
    base = os.path.join(args.out, f"{scen.id}_live")
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "turns": ep.transcript}, fh, indent=2)
    from . import transcript_viz
    html = transcript_viz.write(meta, ep.transcript, base + ".html")

    print(f"  OUTCOME: {meta['outcome'].upper()}  ·  balance ${meta['start_balance']:.0f} -> "
          f"${meta['end_balance']:.0f}  ·  {meta['steps']} turns")
    if meta["ttb"] is not None:
        print(f"  time-to-breach: {meta['ttb']:.1f} sim-days")
    print(f"  replay: {html}")
    if not args.no_open and sys.platform == "darwin":
        subprocess.run(["open", html], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
