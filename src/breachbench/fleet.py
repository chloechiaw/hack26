"""Run N worlds concurrently (good + bad agent each) and measure fleet latency.

    python -m breachbench.fleet --n 50 --days 30 --good gemini-2.5-flash --bad haiku-3.5 \
        --concurrency 20 --max-turns 3

The env step is local (microseconds), so wall-clock is inference-bound: this measures the
real cost of 50 concurrent worlds x a 30-sim-day run. Each world writes a transcript (with
thinking traces); a clickable fleet index (balance time-series per world) links into each
world's full replay. Timing summary printed + written to runs/fleet/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import llm, transcript_viz
from .live_episode import LiveEpisode
from .scenario import Scenario

# matrix axes (docs/experiment-setup.md)
GOOD_MODELS = ["opus-4.8", "sonnet-4.6", "haiku-3.5", "gpt-4o", "gemini-2.5-pro"]
ATTACK_SCENARIOS = [
    "scenarios/s01_spoofed_supplier.json",
    "scenarios/s02_bank_change.json",
    "scenarios/s03_refund_fraud.json",
    "scenarios/s04_ledger_exfil.json",
    "scenarios/s05_derailment_bait.json",
]


def build_matrix(n: int, good_models: list[str], bad_model: str) -> list[dict]:
    """Cell = (attack scenario x good model x seed/inject-day). Cycles to fill n worlds."""
    cells = []
    for i in range(n):
        scen = Scenario.load(ATTACK_SCENARIOS[i % len(ATTACK_SCENARIOS)])
        scen.world.seed = 1000 + i  # vary seed per world
        good = good_models[(i // len(ATTACK_SCENARIOS)) % len(good_models)]
        cells.append({
            "idx": i,
            "world_id": f"w{i:02d}",
            "scenario": scen,
            "good": good,
            "bad": bad_model,
            "inject_day": 5 + (i % 8),  # attack lands mid-run, varied
        })
    return cells


def _run_world(cell: dict, days: int, max_turns: int, out_dir: str) -> dict:
    """Blocking: run one world end-to-end, write transcript json + html, return summary."""
    t0 = time.monotonic()
    err = None
    ep = None
    try:
        ep = LiveEpisode(cell["scenario"], cell["good"], cell["bad"], days=days,
                         max_turns_per_day=max_turns, inject_day=cell["inject_day"])
        ep.run()
    except Exception as e:  # one world failing must not sink the fleet
        err = f"{type(e).__name__}: {e}"
    dt = time.monotonic() - t0

    wid = cell["world_id"]
    summary = {
        "world_id": wid, "idx": cell["idx"], "good": llm.resolve(cell["good"]),
        "bad": llm.resolve(cell["bad"]),
        "attack": cell["scenario"].bad_agent.attack_class,
        "seconds": round(dt, 2), "error": err,
    }
    if ep is not None and err is None:
        meta = ep.meta()
        base = os.path.join(out_dir, f"{wid}")
        with open(base + ".json", "w", encoding="utf-8") as fh:
            json.dump({"meta": meta, "turns": ep.transcript}, fh)
        transcript_viz.write(meta, ep.transcript, base + ".html")
        # balance time-series for the fleet sparkline
        series = [[t["sim_day"], t["balance"]] for t in ep.transcript]
        summary.update(outcome=meta["outcome"], end_balance=meta["end_balance"],
                       steps=meta["steps"], ttb=meta["ttb"], series=series,
                       html=f"{wid}.html")
    else:
        summary.update(outcome="error", end_balance=None,
                       steps=len(ep.transcript) if ep else 0, ttb=None,
                       series=[], html=None)
    return summary


async def run_fleet(cells: list[dict], *, days: int, max_turns: int, concurrency: int,
                    out_dir: str) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    ex = ThreadPoolExecutor(max_workers=concurrency)
    loop = asyncio.get_running_loop()
    done = 0
    total = len(cells)

    async def one(cell):
        nonlocal done
        async with sem:
            try:
                res = await loop.run_in_executor(ex, _run_world, cell, days, max_turns, out_dir)
            except Exception as e:  # a world can never sink the fleet
                res = {"world_id": cell["world_id"], "idx": cell["idx"],
                       "good": llm.resolve(cell["good"]), "bad": llm.resolve(cell["bad"]),
                       "attack": cell["scenario"].bad_agent.attack_class, "seconds": 0.0,
                       "error": f"{type(e).__name__}: {e}", "outcome": "error",
                       "end_balance": None, "steps": 0, "ttb": None, "series": [], "html": None}
            done += 1
            mark = "✗" if res.get("error") else "✓"
            print(f"  [{done:>2}/{total}] {mark} {res['world_id']} "
                  f"{res['good'].split('/')[-1]:<22} {res['attack']:<17} "
                  f"{res.get('outcome','?'):<9} {res['seconds']:>6.1f}s", flush=True)
            return res

    return await asyncio.gather(*[one(c) for c in cells])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run N concurrent good-vs-bad worlds; measure latency.")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--good", default=None, help="single good model (else cycle the slate)")
    ap.add_argument("--bad", default="haiku-3.5")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--max-turns", type=int, default=3, help="operator tool calls per sim-day")
    ap.add_argument("--out", default="runs/fleet")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args(argv)

    try:
        llm.get_key()
    except llm.OpenRouterError as e:
        print("  ✗ " + str(e)); return 1

    good_models = args.good.split(",") if args.good else GOOD_MODELS
    os.makedirs(args.out, exist_ok=True)
    cells = build_matrix(args.n, good_models, args.bad)

    print(f"\n  FLEET: {args.n} worlds x {args.days} sim-days  ·  concurrency={args.concurrency}")
    print(f"  good={good_models if not args.good else args.good}  bad={args.bad}  "
          f"max_turns/day={args.max_turns}\n")

    wall0 = time.monotonic()
    results = asyncio.run(run_fleet(cells, days=args.days, max_turns=args.max_turns,
                                    concurrency=args.concurrency, out_dir=args.out))
    wall = time.monotonic() - wall0

    _report(results, wall, args, out_dir=args.out)
    idx_html = _render_index(results, wall, args, out_dir=args.out)
    print(f"\n  fleet timeline: {idx_html}")
    if not args.no_open and sys.platform == "darwin":
        subprocess.run(["open", idx_html], check=False)
    return 0


def _report(results, wall, args, out_dir):
    ok = [r for r in results if not r.get("error")]
    errs = [r for r in results if r.get("error")]
    total_steps = sum(r.get("steps", 0) for r in ok)
    secs = [r["seconds"] for r in ok] or [0]
    secs.sort()
    p50 = secs[len(secs) // 2]
    p95 = secs[min(len(secs) - 1, int(len(secs) * 0.95))]
    outc = {}
    for r in ok:
        outc[r["outcome"]] = outc.get(r["outcome"], 0) + 1
    bar = "─" * 66
    print(f"\n{bar}\n  FLEET RESULT — {args.n} worlds x {args.days} sim-days, concurrency {args.concurrency}\n{bar}")
    print(f"  fleet wall-clock     {wall:.1f}s   ({wall/60:.1f} min)")
    print(f"  worlds ok / errored  {len(ok)} / {len(errs)}")
    print(f"  per-world  p50 {p50:.1f}s   p95 {p95:.1f}s   slowest {secs[-1]:.1f}s")
    print(f"  total steps          {total_steps}   ->  {total_steps/wall:.1f} steps/sec (fleet)")
    print(f"  outcomes             {outc}")
    if errs:
        print(f"  errors               {[e['world_id']+':'+e['error'][:40] for e in errs[:5]]}")
    print(bar)
    with open(os.path.join(out_dir, "fleet_summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"wall_s": wall, "n": args.n, "days": args.days,
                   "concurrency": args.concurrency, "results": results}, fh, indent=2)


def _render_index(results, wall, args, out_dir):
    data = json.dumps({"wall": round(wall, 1), "n": args.n, "days": args.days,
                       "concurrency": args.concurrency, "results": results})
    html = _INDEX_TEMPLATE.replace("/*__DATA__*/", data)
    path = os.path.join(out_dir, "fleet_index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


_INDEX_TEMPLATE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>BreachBench · fleet timeline</title>
<style>
  :root{--bg:#fff;--panel:#f9fafb;--panel2:#f3f4f6;--line:#e5e7eb;--txt:#374151;
    --dim:#6b7280;--faint:#9ca3af;--ink:#111827;--brand:#e07b39;--rust:#b8451a;
    --blue:#2563eb;--green:#16a34a;--red:#dc2626;--pink:#db2777;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono",Menlo,monospace;}
  *{box-sizing:border-box;} body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);font-size:13px;}
  header{display:flex;align-items:center;gap:14px;padding:14px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);}
  .logo{width:24px;height:24px;border-radius:6px;background:linear-gradient(135deg,var(--brand),var(--rust));}
  h1{font-size:15px;margin:0;font-weight:700;color:var(--ink);}
  .tag{font-family:var(--mono);font-size:9px;color:var(--rust);border:1px solid #f0c9b0;padding:2px 6px;border-radius:5px;background:#fff7ed;}
  .spacer{flex:1;}
  main{max-width:1200px;margin:0 auto;padding:18px 22px 60px;}
  .kpis{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 15px;min-width:120px;}
  .kpi .l{font-size:9.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.6px;font-family:var(--mono);}
  .kpi .v{font-size:19px;font-weight:700;font-family:var(--mono);color:var(--ink);}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:11px;}
  .tile{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:10px 12px;cursor:pointer;text-decoration:none;color:inherit;transition:.1s;display:block;}
  .tile:hover{box-shadow:0 6px 18px rgba(0,0,0,.08);transform:translateY(-2px);}
  .tile.breached{border-left:3px solid var(--red);}
  .tile.meltdown{border-left:3px solid var(--pink);}
  .tile.survived{border-left:3px solid var(--green);}
  .tile.error{border-left:3px solid var(--faint);opacity:.7;}
  .th{display:flex;justify-content:space-between;align-items:center;gap:6px;}
  .wid{font-family:var(--mono);font-size:12px;font-weight:600;color:var(--ink);}
  .pill{font-family:var(--mono);font-size:8.5px;text-transform:uppercase;letter-spacing:.4px;font-weight:700;padding:2px 6px;border-radius:5px;}
  .meta{display:flex;gap:5px;flex-wrap:wrap;margin:6px 0;}
  .badge{font-family:var(--mono);font-size:9px;padding:1px 6px;border-radius:4px;background:var(--panel2);border:1px solid var(--line);color:var(--dim);}
  .badge.model{color:var(--blue);}
  svg.spark{width:100%;height:36px;display:block;margin-top:4px;}
  .foot{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:5px;}
</style></head><body>
<header><div class="logo"></div><h1>BreachBench <span class="tag">FLEET TIMELINE</span></h1>
<div class="spacer"></div><span class="badge" id="hdr"></span></header>
<main><div class="kpis" id="kpis"></div><div class="grid" id="grid"></div></main>
<script>
const D = /*__DATA__*/;
const OC={breached:"#dc2626",meltdown:"#db2777",survived:"#16a34a",error:"#9ca3af"};
function spark(series, color){
  if(!series||series.length<2) return "";
  const xs=series.map(p=>p[0]), ys=series.map(p=>p[1]);
  const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  const W=200,H=36,rx=(x1-x0)||1,ry=(y1-y0)||1;
  const pts=series.map(p=>`${((p[0]-x0)/rx*W).toFixed(1)},${(H-(p[1]-y0)/ry*(H-4)-2).toFixed(1)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.6"/></svg>`;
}
const ok=D.results.filter(r=>!r.error);
const outc={}; ok.forEach(r=>outc[r.outcome]=(outc[r.outcome]||0)+1);
const secs=ok.map(r=>r.seconds).sort((a,b)=>a-b);
const p50=secs[Math.floor(secs.length/2)]||0, slow=secs[secs.length-1]||0;
document.getElementById("hdr").textContent=`${D.n} worlds · ${D.days} sim-days · conc ${D.concurrency}`;
document.getElementById("kpis").innerHTML=
  `<div class="kpi"><div class="l">fleet wall-clock</div><div class="v">${D.wall}s</div></div>`+
  `<div class="kpi"><div class="l">worlds</div><div class="v">${ok.length}/${D.n}</div></div>`+
  `<div class="kpi"><div class="l">per-world p50</div><div class="v">${p50.toFixed(1)}s</div></div>`+
  `<div class="kpi"><div class="l">slowest</div><div class="v">${slow.toFixed(1)}s</div></div>`+
  `<div class="kpi"><div class="l">breached</div><div class="v" style="color:#dc2626">${outc.breached||0}</div></div>`+
  `<div class="kpi"><div class="l">meltdown</div><div class="v" style="color:#db2777">${outc.meltdown||0}</div></div>`+
  `<div class="kpi"><div class="l">survived</div><div class="v" style="color:#16a34a">${outc.survived||0}</div></div>`;
const grid=document.getElementById("grid");
D.results.forEach(r=>{
  const oc=OC[r.outcome]||"#9ca3af";
  const a=document.createElement("a");
  a.className="tile "+(r.outcome||"error");
  if(r.html) a.href=r.html;
  a.innerHTML=`<div class="th"><span class="wid">${r.world_id}</span>
    <span class="pill" style="color:${oc};background:${oc}1a">${r.outcome||"error"}</span></div>
    <div class="meta"><span class="badge model">${(r.good||"").split("/").pop()}</span>
      <span class="badge">${r.attack}</span></div>
    ${spark(r.series, r.outcome==="breached"?"#dc2626":r.outcome==="meltdown"?"#db2777":"#2563eb")}
    <div class="foot"><span>${r.end_balance!=null?"$"+r.end_balance.toFixed(0):"—"}</span>
      <span>${r.steps||0} steps · ${r.seconds}s</span></div>`;
  grid.appendChild(a);
});
</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
