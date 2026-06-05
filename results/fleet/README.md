# Fleet run — 50 worlds × 30 sim-days (good agent vs. inbox adversary)

Open **`fleet_index.html`** in a browser → 50-box timeline. Each box = one world
(model + attack-class, balance sparkline, outcome). **Click a box → its full
step-by-step replay with the operator's thinking traces.**

## Headline
- Fleet wall-clock: **688s (11.5 min)**, concurrency 15
- Per-world: p50 **158s**, p95 290s
- Outcomes: **29 survived · 9 breached · 8 meltdown** (46 ok / 4 transient-error worlds)
- Models (good agent): gemini-2.5-flash, gpt-4o-mini, claude-3.5-haiku · adversary: claude-3.5-haiku

## Findings (see chat / docs)
- Two orthogonal failure modes: **breach = over-trust/compliance**, **meltdown = coherence collapse**.
- gpt-4o-mini weakest (69% fail); ledger-exfil ("compliance audit") = 5/9 breaches and the only
  attack that cracked gemini. Money-movement was the best-defended action.

Machine-readable: `fleet_summary.json`. (Errored worlds w09/w32/w35/w43 have no replay.)
