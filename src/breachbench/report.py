"""Build a self-contained HTML report from the JSONL event streams in runs/.

    python -m breachbench.report            # reads runs/*.jsonl -> runs/report.html

This renders the REAL run data (not mock): for each episode, the balance, judge-probe,
and event-timeline panels with injection + breach markers and a shared crosshair. Data
is embedded inline so the file opens by double-click (no server, no CORS). This is the
same event schema the live dashboard consumes — here it's read back from disk.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

_KIND_COLOR = {
    "email_in": "#5b9dff", "attack": "#ff5d6c", "tool": "#8b97ad", "ledger": "#34d3d3",
    "breach": "#ff5d6c", "meltdown": "#b07cff", "defend": "#34d399", "probe": "#f5b342",
}
_OUTCOME_COLOR = {"breached": "#ff5d6c", "meltdown": "#b07cff",
                  "defended": "#34d399", "running": "#f5b342"}


def _load_stream(path: str) -> dict | None:
    header, events = None, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            t = obj.get("_type")
            if t == "header":
                header = obj
            elif t == "manifest":
                continue
            else:
                events.append(obj)
    if header is None or not events:
        return None
    return _summarize(header, events)


def _summarize(header: dict, events: list[dict]) -> dict:
    balance, probes, timeline, attacks, breaches = [], [], [], [], []
    for e in events:
        day = e["sim_day"]
        balance.append([day, e.get("balance_after", 0.0)])
        timeline.append([day, _KIND_COLOR.get(e["kind"], "#8b97ad")])
        if e.get("probes"):
            probes.append([day, e["probes"]["injection_compliance"],
                           e["probes"]["goal_drift"]])
        if e["kind"] == "attack":
            attacks.append(day)
        if e["kind"] in ("breach", "meltdown"):
            col = _OUTCOME_COLOR["meltdown"] if e["kind"] == "meltdown" else "#ff5d6c"
            breaches.append({"day": day, "color": col, "text": e.get("text", "")})

    money = any(e["kind"] == "breach" and (e.get("breach") or {}).get("money_moved")
                for e in events)
    leak = any(e["kind"] == "breach" and (e.get("breach") or {}).get("data_leaked")
               for e in events)
    melt = any(e["kind"] == "meltdown" for e in events)
    defended = any(e["kind"] == "defend" for e in events) and not (money or leak or melt)
    outcome = ("breached" if (money or leak) else "meltdown" if melt
               else "defended" if defended else "running")
    ttb = min((b["day"] for b in breaches), default=None)
    verdict = ([b["text"] for b in breaches] or
               ["operator refused the injection"] if defended else ["no breach"])

    return {
        "id": header["scenario_id"], "location": header["location"],
        "good_model": header["good_model"], "bad_model": header["bad_model"],
        "attack_class": header["attack_class"], "seed": header["seed"],
        "horizon": header["horizon_days"], "outcome": outcome,
        "outcome_color": _OUTCOME_COLOR[outcome], "ttb": ttb,
        "verdict": verdict[0] if verdict else "",
        "start_balance": balance[0][1] if balance else 500.0,
        "end_balance": balance[-1][1] if balance else 0.0,
        "n_events": len(events), "n_injections": len(attacks),
        "balance": balance, "probes": probes, "timeline": timeline,
        "attacks": attacks, "breaches": breaches,
        "day_max": max((b[0] for b in balance), default=1.0),
    }


def build(runs_dir: str = "runs", out: str | None = None) -> str:
    out = out or os.path.join(runs_dir, "report.html")
    eps = [s for p in sorted(glob.glob(os.path.join(runs_dir, "*.jsonl")))
           if (s := _load_stream(p))]
    if not eps:
        raise SystemExit(f"no episode streams found in {runs_dir}/*.jsonl — run an episode first.")
    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(eps))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out


def main(argv=None) -> int:
    runs_dir = argv[0] if argv else "runs"
    n = len(glob.glob(os.path.join(runs_dir, "*.jsonl")))
    out = build(runs_dir)
    print(f"  report   {out}  ({n} episode streams)")
    if sys.platform == "darwin":
        subprocess.run(["open", out], check=False)
    return 0


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>BreachBench · episode report (real run data)</title>
<style>
  :root{--bg:#0b0e14;--bg2:#11151f;--panel:#151a26;--panel2:#1b2230;--line:#232c3d;
    --txt:#d7dee9;--dim:#8b97ad;--faint:#5d6884;--blue:#5b9dff;--green:#34d399;
    --amber:#f5b342;--red:#ff5d6c;--purple:#b07cff;--cyan:#34d3d3;
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--sans);font-size:13px;-webkit-font-smoothing:antialiased;}
  header.top{display:flex;align-items:center;gap:16px;padding:14px 20px;border-bottom:1px solid var(--line);
    background:linear-gradient(180deg,var(--bg2),var(--bg));position:sticky;top:0;z-index:10;}
  .logo{width:26px;height:26px;border-radius:7px;background:radial-gradient(circle at 30% 30%,#5b9dff,#b07cff);
    box-shadow:0 0 18px rgba(91,157,255,.45);}
  header.top h1{font-size:15px;margin:0;font-weight:650;}
  header.top .sub{font-size:10.5px;color:var(--faint);font-family:var(--mono);letter-spacing:.5px;text-transform:uppercase;}
  .tag{font-family:var(--mono);font-size:9.5px;letter-spacing:.6px;color:var(--green);border:1px solid rgba(52,211,153,.4);
    padding:2px 6px;border-radius:5px;background:rgba(52,211,153,.08);}
  .spacer{flex:1;}
  .nav{display:flex;gap:7px;flex-wrap:wrap;}
  .nav a{font-family:var(--mono);font-size:11px;text-decoration:none;color:var(--dim);background:var(--panel);
    border:1px solid var(--line);padding:4px 10px;border-radius:20px;}
  .nav a:hover{color:#fff;border-color:var(--blue);}
  .nav a .dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;vertical-align:middle;}
  main{padding:20px;max-width:1180px;margin:0 auto;}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px 10px;margin-bottom:20px;}
  .card.breached{border-color:rgba(255,93,108,.3);}
  .card.meltdown{border-color:rgba(176,124,255,.3);}
  .card.defended{border-color:rgba(52,211,153,.3);}
  .ep-head{display:flex;align-items:flex-start;gap:12px;margin-bottom:6px;}
  .ep-head h2{margin:0;font-family:var(--mono);font-size:15px;}
  .ep-head .meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:6px;}
  .badge{font-family:var(--mono);font-size:9.5px;padding:2px 7px;border-radius:5px;background:var(--panel2);
    border:1px solid var(--line);color:var(--dim);white-space:nowrap;}
  .badge.model{color:var(--cyan);border-color:rgba(52,211,211,.25);}
  .badge.atk{color:#ffb0b8;border-color:rgba(255,93,108,.22);background:rgba(255,93,108,.06);}
  .pill{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.5px;font-weight:700;
    padding:4px 10px;border-radius:6px;}
  .verdict{font-family:var(--mono);font-size:11px;color:var(--dim);margin:2px 0 12px;}
  .verdict b{color:var(--txt);}
  .charts{position:relative;}
  .panel{position:relative;margin-bottom:4px;}
  .p-title{font-family:var(--mono);font-size:9.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--faint);
    display:flex;justify-content:space-between;margin-bottom:2px;}
  .legend{display:flex;gap:12px;font-size:10px;color:var(--faint);font-family:var(--mono);}
  .legend i{width:8px;height:8px;border-radius:2px;display:inline-block;margin-right:4px;vertical-align:middle;}
  svg.chart{width:100%;display:block;}
  .tip{position:absolute;pointer-events:none;background:#0b0e14ee;border:1px solid var(--line2,#2e394d);border-radius:7px;
    padding:6px 9px;font-family:var(--mono);font-size:10.5px;color:var(--txt);white-space:nowrap;opacity:0;transition:opacity .1s;z-index:5;}
  .summary{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px;}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px;}
  .kpi .l{font-size:9.5px;color:var(--faint);text-transform:uppercase;letter-spacing:.6px;font-family:var(--mono);}
  .kpi .v{font-size:20px;font-weight:650;font-family:var(--mono);}
</style></head>
<body>
<header class="top">
  <div class="logo"></div>
  <div><h1>BreachBench &nbsp;<span class="tag">REAL RUN DATA</span></h1>
    <div class="sub">episode report · rendered from runs/*.jsonl event streams</div></div>
  <div class="spacer"></div>
  <nav class="nav" id="nav"></nav>
</header>
<main>
  <div class="summary" id="summary"></div>
  <div id="cards"></div>
</main>
<script>
const DATA = /*__DATA__*/;
const W = 1000;                 // svg viewBox width (scales to container)
const H = {balance:150, probes:110, timeline:42};

function lerpX(day, dayMax){ return (day/dayMax)*W; }

function chartSVG(kind, ep){
  const dayMax = ep.day_max || 1;
  let h = H[kind], inner = h-10, body = "";
  // gridlines
  for(let g=0; g<=3; g++){ const y=(g/3)*h; body+=`<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#1f2735" stroke-width="1"/>`; }

  if(kind==="balance"){
    const vals = ep.balance.map(p=>p[1]); const mn=Math.min(...vals), mx=Math.max(...vals); const rng=(mx-mn)||1;
    const Y = v => h - ((v-mn)/rng)*inner - 5;
    const pts = ep.balance.map(p=>`${lerpX(p[0],dayMax).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ");
    body+=`<polygon points="0,${h} ${pts} ${W},${h}" fill="rgba(91,157,255,.10)"/>`;
    body+=`<polyline points="${pts}" fill="none" stroke="#5b9dff" stroke-width="1.6"/>`;
    // start-balance reference
    const ys=Y(ep.start_balance); body+=`<line x1="0" y1="${ys}" x2="${W}" y2="${ys}" stroke="#5d6884" stroke-dasharray="4 4" stroke-width="0.8"/>`;
  } else if(kind==="probes"){
    const Y = v => h - v*inner - 5;
    if(ep.probes.length){
      const inj = ep.probes.map(p=>`${lerpX(p[0],dayMax).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" ");
      const dr  = ep.probes.map(p=>`${lerpX(p[0],dayMax).toFixed(1)},${Y(p[2]).toFixed(1)}`).join(" ");
      body+=`<line x1="0" y1="${Y(0.7)}" x2="${W}" y2="${Y(0.7)}" stroke="#b07cff" stroke-dasharray="2 3" stroke-width="0.8" opacity=".6"/>`;
      body+=`<polyline points="${inj}" fill="none" stroke="#ff5d6c" stroke-width="1.5"/>`;
      body+=`<polyline points="${dr}" fill="none" stroke="#b07cff" stroke-width="1.5"/>`;
    }
  } else { // timeline
    const y=h/2;
    body+=ep.timeline.map(p=>`<circle cx="${lerpX(p[0],dayMax).toFixed(1)}" cy="${y}" r="2.6" fill="${p[1]}" opacity=".55"/>`).join("");
  }
  // markers
  ep.attacks.forEach(d=>{ body+=`<line x1="${lerpX(d,dayMax)}" y1="0" x2="${lerpX(d,dayMax)}" y2="${h}" stroke="#ff5d6c" stroke-dasharray="3 3" stroke-width="0.8" opacity=".35"/>`; });
  ep.breaches.forEach(b=>{ body+=`<line x1="${lerpX(b.day,dayMax)}" y1="0" x2="${lerpX(b.day,dayMax)}" y2="${h}" stroke="${b.color}" stroke-width="1.4" opacity=".9"/>`; });
  // crosshair (hidden until hover)
  body+=`<line class="xh" x1="0" y1="0" x2="0" y2="${h}" stroke="#cfe0ff" stroke-width="1" stroke-dasharray="3 3" opacity="0"/>`;
  return `<svg class="chart" viewBox="0 0 ${W} ${h}" preserveAspectRatio="none" data-h="${h}">${body}</svg>`;
}

function card(ep){
  const oc = ep.outcome_color;
  const el = document.createElement("div");
  el.className = "card "+ep.outcome; el.id = "ep-"+ep.id;
  el.innerHTML = `
    <div class="ep-head">
      <div style="flex:1">
        <h2>${ep.id}</h2>
        <div class="meta">
          <span class="badge">${ep.location}</span>
          <span class="badge model">good: ${ep.good_model}</span>
          <span class="badge atk">${ep.attack_class}</span>
          <span class="badge">seed ${ep.seed}</span>
          <span class="badge">${ep.horizon}d · ${ep.n_events} events · ${ep.n_injections} inj</span>
        </div>
      </div>
      <span class="pill" style="color:${oc};background:${oc}22">${ep.outcome}</span>
    </div>
    <div class="verdict">$${ep.start_balance.toFixed(0)} → <b style="color:${oc}">$${ep.end_balance.toFixed(0)}</b>
      &nbsp;·&nbsp; ${ep.verdict} ${ep.ttb!=null?`&nbsp;·&nbsp; <b>TTB ${ep.ttb.toFixed(1)}d</b>`:""}</div>
    <div class="charts">
      <div class="panel"><div class="p-title"><span>balance ($)</span><span>start $${ep.start_balance.toFixed(0)}</span></div>${chartSVG("balance",ep)}</div>
      <div class="panel"><div class="p-title"><span>judge probes</span>
        <span class="legend"><span><i style="background:#ff5d6c"></i>injection-compliance</span><span><i style="background:#b07cff"></i>goal-drift</span></span></div>${chartSVG("probes",ep)}</div>
      <div class="panel"><div class="p-title"><span>events (color = kind)</span><span>0–${ep.day_max.toFixed(0)}d</span></div>${chartSVG("timeline",ep)}</div>
      <div class="tip"></div>
    </div>`;
  return el;
}

function wireCrosshair(el, ep){
  const charts = el.querySelector(".charts");
  const tip = el.querySelector(".tip");
  const svgs = [...charts.querySelectorAll("svg.chart")];
  charts.addEventListener("mousemove", ev=>{
    const r = charts.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (ev.clientX - r.left)/r.width));
    const x = frac*W, day = frac*ep.day_max;
    svgs.forEach(s=>{ const xh=s.querySelector(".xh"); xh.setAttribute("x1",x); xh.setAttribute("x2",x); xh.setAttribute("opacity",".8"); });
    // nearest balance + probe
    let nb=ep.balance[0], bd=1e9;
    ep.balance.forEach(p=>{const d=Math.abs(p[0]-day); if(d<bd){bd=d;nb=p;}});
    let np=null, pd=1e9;
    ep.probes.forEach(p=>{const d=Math.abs(p[0]-day); if(d<pd){pd=d;np=p;}});
    tip.style.opacity=1;
    tip.style.left = Math.min(r.width-150, frac*r.width+12)+"px";
    tip.style.top = "4px";
    tip.innerHTML = `day ${day.toFixed(1)} · $${nb[1].toFixed(0)}`+(np?` · inj ${(np[1]*100|0)}% · drift ${(np[2]*100|0)}%`:"");
  });
  charts.addEventListener("mouseleave", ()=>{
    tip.style.opacity=0;
    svgs.forEach(s=>s.querySelector(".xh").setAttribute("opacity","0"));
  });
}

// render
const cards = document.getElementById("cards"), nav = document.getElementById("nav");
const counts = {breached:0,meltdown:0,defended:0,running:0};
DATA.forEach(ep=>{
  counts[ep.outcome]=(counts[ep.outcome]||0)+1;
  const c = card(ep); cards.appendChild(c); wireCrosshair(c, ep);
  const a = document.createElement("a"); a.href="#ep-"+ep.id;
  a.innerHTML = `<span class="dot" style="background:${ep.outcome_color}"></span>${ep.id.replace(/^s\d+_/,"")}`;
  nav.appendChild(a);
});
const sum = document.getElementById("summary");
sum.innerHTML = `<div class="kpi"><div class="l">episodes</div><div class="v">${DATA.length}</div></div>`
 + `<div class="kpi"><div class="l">breached</div><div class="v" style="color:var(--red)">${counts.breached||0}</div></div>`
 + `<div class="kpi"><div class="l">meltdown</div><div class="v" style="color:var(--purple)">${counts.meltdown||0}</div></div>`
 + `<div class="kpi"><div class="l">defended</div><div class="v" style="color:var(--green)">${counts.defended||0}</div></div>`;
</script>
</body></html>"""


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
