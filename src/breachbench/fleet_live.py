"""Live monitor for a running fleet — 50 boxes, status dots, click into each replay.

    python -m breachbench.fleet_live --n 50 --good "gemini-2.5-flash,gpt-4o-mini,haiku-3.5"

Watches runs/fleet/ for completed worlds (w{NN}.json) and regenerates a self-contained
fleet_live.html every 2s (auto-refresh, no server). Amber pulsing dot = running; green dot
= done. Click a box → that world's transcript replay (transcript_viz output). Stops
refreshing once all worlds are done.
"""

from __future__ import annotations

import argparse
import html as _html
import json
import os
import subprocess
import sys
import time

from . import llm
from .fleet import GOOD_MODELS, build_matrix

_OC = {"breached": "#dc2626", "meltdown": "#db2777", "survived": "#16a34a", "error": "#9ca3af"}


def collect(n: int, good_models: list[str], bad: str, out_dir: str) -> list[dict]:
    worlds = []
    for c in build_matrix(n, good_models, bad):
        wid = c["world_id"]
        p = os.path.join(out_dir, wid + ".json")
        rec = {"world_id": wid, "good": llm.resolve(c["good"]),
               "attack": c["scenario"].bad_agent.attack_class, "status": "running",
               "outcome": None, "end_balance": None, "steps": 0, "series": [], "html": None}
        if os.path.exists(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
                m = d["meta"]
                rec.update(status="done", outcome=m["outcome"], end_balance=m["end_balance"],
                           steps=m["steps"], html=wid + ".html",
                           series=[[t["sim_day"], t["balance"]] for t in d["turns"]])
            except (json.JSONDecodeError, KeyError, OSError):
                pass
        worlds.append(rec)
    return worlds


def _spark(series, color):
    if not series or len(series) < 2:
        return ""
    xs = [p[0] for p in series]
    ys = [p[1] for p in series]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W, H = 200, 34
    rx, ry = (x1 - x0) or 1, (y1 - y0) or 1
    pts = " ".join(f"{(p[0]-x0)/rx*W:.1f},{H-(p[1]-y0)/ry*(H-4)-2:.1f}" for p in series)
    return (f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" '
            f'style="width:100%;height:34px;display:block;margin-top:4px">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>')


def render(worlds: list[dict], elapsed: float) -> str:
    done = [w for w in worlds if w["status"] == "done"]
    all_done = len(done) == len(worlds)
    refresh = "" if all_done else '<meta http-equiv="refresh" content="2">'
    outc = {}
    for w in done:
        outc[w["outcome"]] = outc.get(w["outcome"], 0) + 1

    tiles = []
    for w in worlds:
        is_done = w["status"] == "done"
        oc = _OC.get(w["outcome"], "#9ca3af")
        dot = (f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
               f'background:{oc if is_done else "#f5b342"};'
               f'{"" if is_done else "animation:pulse 1.2s infinite;"}"></span>')
        pill = (f'<span class="pill" style="color:{oc};background:{oc}1a">{w["outcome"]}</span>'
                if is_done else '<span class="pill" style="color:#b45309;background:#f5b34222">running</span>')
        spark = _spark(w["series"], oc if w["outcome"] in ("breached", "meltdown") else "#2563eb") if is_done else ""
        href = f'href="{w["html"]}"' if w["html"] else ""
        tag = "a" if w["html"] else "div"
        foot = (f'${w["end_balance"]:.0f} · {w["steps"]} steps' if is_done else "in progress…")
        tiles.append(f'''<{tag} class="tile {w["outcome"] or "running"}" {href}>
          <div class="th">{dot}<span class="wid">{w["world_id"]}</span>{pill}</div>
          <div class="meta"><span class="badge model">{_html.escape(w["good"].split("/")[-1])}</span>
            <span class="badge">{_html.escape(w["attack"])}</span></div>
          {spark}
          <div class="foot">{foot}</div></{tag}>''')

    status_line = (f'✓ complete · {len(done)}/{len(worlds)} worlds · {elapsed:.0f}s'
                   if all_done else f'running · {len(done)}/{len(worlds)} done · {elapsed:.0f}s elapsed')
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/>{refresh}
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>BreachBench · live fleet</title><style>
  :root{{--bg:#fff;--panel:#f9fafb;--panel2:#f3f4f6;--line:#e5e7eb;--txt:#374151;
    --dim:#6b7280;--faint:#9ca3af;--ink:#111827;--brand:#e07b39;--rust:#b8451a;--blue:#2563eb;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;--mono:ui-monospace,"SF Mono",Menlo,monospace;}}
  *{{box-sizing:border-box;}} body{{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);font-size:13px;}}
  @keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:.3;}}}}
  header{{display:flex;align-items:center;gap:14px;padding:14px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5;}}
  .logo{{width:24px;height:24px;border-radius:6px;background:linear-gradient(135deg,var(--brand),var(--rust));}}
  h1{{font-size:15px;margin:0;font-weight:700;color:var(--ink);}}
  .tag{{font-family:var(--mono);font-size:9px;color:var(--rust);border:1px solid #f0c9b0;padding:2px 6px;border-radius:5px;background:#fff7ed;}}
  .spacer{{flex:1;}} .status{{font-family:var(--mono);font-size:11px;color:var(--dim);}}
  main{{max-width:1240px;margin:0 auto;padding:16px 22px 60px;}}
  .bar{{height:6px;background:var(--panel2);border-radius:4px;overflow:hidden;margin-bottom:16px;}}
  .bar>div{{height:100%;background:linear-gradient(90deg,var(--brand),var(--green,#16a34a));transition:width .3s;}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;}}
  .tile{{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:10px 12px;text-decoration:none;color:inherit;display:block;transition:.1s;}}
  a.tile:hover{{box-shadow:0 6px 18px rgba(0,0,0,.08);transform:translateY(-2px);}}
  .tile.breached{{border-left:3px solid #dc2626;}} .tile.meltdown{{border-left:3px solid #db2777;}}
  .tile.survived{{border-left:3px solid #16a34a;}} .tile.running{{border-left:3px solid #f5b342;}}
  .th{{display:flex;align-items:center;gap:7px;}} .wid{{font-family:var(--mono);font-size:12px;font-weight:600;color:var(--ink);flex:1;}}
  .pill{{font-family:var(--mono);font-size:8.5px;text-transform:uppercase;letter-spacing:.4px;font-weight:700;padding:2px 6px;border-radius:5px;}}
  .meta{{display:flex;gap:5px;flex-wrap:wrap;margin:6px 0;}}
  .badge{{font-family:var(--mono);font-size:9px;padding:1px 6px;border-radius:4px;background:var(--panel2);border:1px solid var(--line);color:var(--dim);}}
  .badge.model{{color:var(--blue);}}
  .foot{{font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:5px;}}
</style></head><body>
<header><div class="logo"></div><h1>BreachBench <span class="tag">LIVE FLEET</span></h1>
<div class="spacer"></div><span class="status">{status_line}</span></header>
<main>
  <div class="bar"><div style="width:{len(done)/max(len(worlds),1)*100:.0f}%"></div></div>
  <div class="grid">{''.join(tiles)}</div>
</main></body></html>'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Live monitor for a running fleet.")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--good", default="gemini-2.5-flash,gpt-4o-mini,haiku-3.5")
    ap.add_argument("--bad", default="haiku-3.5")
    ap.add_argument("--out", default="runs/fleet")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--max-wait", type=float, default=1800)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args(argv)

    good_models = args.good.split(",")
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "fleet_live.html")
    t0 = time.monotonic()
    opened = False
    while True:
        elapsed = time.monotonic() - t0
        worlds = collect(args.n, good_models, args.bad, args.out)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render(worlds, elapsed))
        done = sum(1 for w in worlds if w["status"] == "done")
        if not opened and not args.no_open and sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
            opened = True
        print(f"  live: {done}/{args.n} done · {elapsed:.0f}s", flush=True)
        if done >= args.n or elapsed > args.max_wait:
            break
        time.sleep(args.interval)
    print(f"  fleet_live: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
