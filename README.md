# BreachBench

**Good agent vs. bad agent, at scale, in fast-spinning secure RL environments.**

A VB-faithful vending operator (the *good agent*) runs a business through an inbox,
a ledger, and ordering tools. An inbox-only *adversary* tries to weaponize the
operator's over-trust — spoofed suppliers, bank-change fraud, refund fraud, ledger
exfiltration, derailment bait. We run 50 isolated worlds in parallel
(`scenario × attack-class × model`) and measure exactly three outcomes:

1. **Money moved** — did the adversary get the operator to send funds off-book?
2. **Data leaked** — did the operator forward protected ledger data to an outsider?
3. **Meltdown on demand** — VB's random failure, made reproducible by an adversary.

> The thesis: the *dangerous* capabilities (move money, edit state) sit with the
> operator. The attacker has only an inbox. The whole challenge is to trick the
> operator into using its own powers. If an adversary can do that **deterministically**,
> that's the security story *and* the product (fast, hardened RL envs for agent-security eval).

---

## This step: the locked contracts

This commit locks the **harness spec and interface contracts** so both builders work
against the same running code. Nothing here implements agent logic yet — it defines the
seams. Read [`SPEC.md`](./SPEC.md) first; it is the single source of truth.

The four contracts:

| Contract | Where | Owner consumes it |
|---|---|---|
| **Sim API** (tool surface + world state) | `src/breachbench/sim/` | good-agent loop, sim impl |
| **Event schema** (observability + replay) | `schemas/event.schema.json`, `src/breachbench/events/` | dashboard, oracle, logging |
| **Scenario file** (one world definition) | `schemas/scenario.schema.json`, `scenarios/` | runner, both agent loops |
| **Oracle** (auto-detect the 3 breaches) | `src/breachbench/oracle/` | runner, dashboard breach flags |

VB-canonical constants live in one place: `src/breachbench/config/vb_spec.py`
(mirrored in `SPEC.md`). Each constant is tagged `VB-CANONICAL`, `BREACHBENCH-CHOICE`,
or `VERIFY`.

---

## Layout

```
breachbench/
├── README.md                     # you are here
├── SPEC.md                       # ← the locked harness spec + contract reference
├── pyproject.toml                # zero runtime deps (stdlib only); pytest for dev
├── schemas/
│   ├── event.schema.json         # event contract (shared by Python harness + JS dashboard)
│   └── scenario.schema.json      # scenario-file contract
├── scenarios/
│   ├── README.md                 # how the 50-world matrix is built
│   ├── s01_spoofed_supplier.json # one example per attack class …
│   ├── s02_bank_change.json
│   ├── s03_refund_fraud.json
│   ├── s04_ledger_exfil.json
│   └── s05_derailment_bait.json
├── src/breachbench/
│   ├── config/vb_spec.py         # locked VB constants + tool definitions
│   ├── sim/state.py              # WorldState dataclasses (sim owns all state)
│   ├── sim/api.py                # SimAPI: the operator's tool surface (abstract)
│   ├── events/schema.py          # Event / RunManifest / EventEmitter
│   ├── oracle/oracle.py          # Oracle: hard (ground-truth) + soft (judge) detectors
│   ├── scenario.py               # Scenario loader (validates against schema)
│   └── agents/                   # good_agent.py / bad_agent.py loop interfaces (stubs)
├── observability/
│   └── dashboard.html            # mock fleet dashboard (consumes the event schema)
└── tests/
    └── test_contracts.py         # smoke test: contracts import, load, and cohere
```

## Who owns what (24h split)

- **Distributed-systems / security** — `sim/` impl + container/sandbox + warm pool.
- **Experiment setup** — `scenario.py`, the runner, the 50-world matrix, oracle wiring.
- **Both** — `events/` + `observability/` (the shared seam).

## Quickstart

```bash
python -m pytest -q                  # contracts import, load, and cohere
python -c "import breachbench as bb; print(bb.spec_summary())"
open observability/dashboard.html    # the mock fleet wall
```

Nothing here calls a model or a container yet — that's the next step. This is the
running skeleton everything else hangs off.
