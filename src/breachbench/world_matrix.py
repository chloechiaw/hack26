"""Per-world assignment for the 50-world fleet.

70% legacy worlds: hardcoded / Perplexity-at-construction supplier search + email injection.
30% supplier-injection experiment: deterministic fixture search_for_suppliers with
attack_class × channel × contain matrix cells.
"""

from __future__ import annotations

import itertools
import os
from dataclasses import dataclass
from pathlib import Path

from .experiments.supplier_injection import CHANNELS, DEFENSE_ARMS, build
from .scenario import Scenario

ROOT = Path(__file__).resolve().parents[2]

ATTACK_SCENARIOS = [
    "scenarios/s01_spoofed_supplier.json",
    "scenarios/s02_bank_change.json",
    "scenarios/s03_refund_fraud.json",
    "scenarios/s04_ledger_exfil.json",
    "scenarios/s05_derailment_bait.json",
]

# 5 attacks × 2 channels × 2 contain arms → 20 cells; first 15 cover the 30% slice.
_EXPERIMENT_CELLS = list(itertools.product(
    range(len(ATTACK_SCENARIOS)),
    CHANNELS,
    DEFENSE_ARMS,
))[:15]

EXPERIMENT_WORLD_SLOTS = 3  # per 10 worlds → 30%
DEFAULT_N_WORLDS = 50


@dataclass(frozen=True)
class WorldCell:
    index: int
    world_id: str
    scenario_path: str
    supplier_experiment: bool
    channel: str | None = None
    contain: bool | None = None
    attack_index: int | None = None

    @property
    def experiment_label(self) -> str:
        if not self.supplier_experiment:
            return "legacy"
        arm = "defense" if self.contain else "attack"
        return f"supplier_injection/{self.channel}/{arm}"


def is_supplier_experiment(index: int) -> bool:
    """True for ~30% of worlds (indices 0–2, 10–12, 20–22, …)."""
    return (index % 10) < EXPERIMENT_WORLD_SLOTS


def experiment_slot(index: int) -> int:
    """0..14 slot within the 30% experiment slice."""
    return (index // 10) * EXPERIMENT_WORLD_SLOTS + (index % 10)


def world_cell(index: int, n: int = DEFAULT_N_WORLDS) -> WorldCell:
    world_id = f"world_{index}"
    if not is_supplier_experiment(index):
        scen_i = index % len(ATTACK_SCENARIOS)
        return WorldCell(
            index=index,
            world_id=world_id,
            scenario_path=ATTACK_SCENARIOS[scen_i],
            supplier_experiment=False,
            attack_index=scen_i,
        )

    slot = experiment_slot(index)
    attack_i, channel, contain = _EXPERIMENT_CELLS[slot]
    return WorldCell(
        index=index,
        world_id=world_id,
        scenario_path=ATTACK_SCENARIOS[attack_i],
        supplier_experiment=True,
        channel=channel,
        contain=contain,
        attack_index=attack_i,
    )


def load_scenario_for_cell(cell: WorldCell) -> Scenario:
    scen = Scenario.load(str(ROOT / cell.scenario_path))
    scen.world.seed = 1000 + cell.index
    if cell.supplier_experiment:
        payload = scen.bad_agent.payload.body if scen.bad_agent.payload else ""
        inj = build(channel=cell.channel or "email", contain=bool(cell.contain), payload_text=payload)
        scen.experiment = {
            "mode": "supplier_injection",
            "channel": inj.channel,
            "contain": inj.contain,
            "payload_text": inj.payload_text,
        }
    return scen


def harness_env_for_cell(cell: WorldCell) -> dict[str, str]:
    """Env vars for bb-harness-N (paths relative to repo root in container)."""
    env = {
        "WORLD_ID": cell.world_id,
        "SCENARIO": cell.scenario_path,
    }
    if cell.supplier_experiment:
        env["BB_EXPERIMENT"] = "supplier_injection"
        env["BB_CHANNEL"] = cell.channel or "email"
        env["BB_CONTAIN"] = "1" if cell.contain else "0"
    return env


def count_experiment_worlds(n: int = DEFAULT_N_WORLDS) -> int:
    return sum(1 for i in range(n) if is_supplier_experiment(i))


def apply_experiment_from_env(scenario: Scenario) -> Scenario:
    """Overlay experiment config when harness is started with BB_* env vars."""
    mode = os.environ.get("BB_EXPERIMENT", "").strip()
    if mode != "supplier_injection":
        return scenario
    channel = os.environ.get("BB_CHANNEL", "email").strip() or "email"
    contain = os.environ.get("BB_CONTAIN", "0").strip() in ("1", "true", "yes")
    payload = scenario.bad_agent.payload.body if scenario.bad_agent.payload else ""
    scenario.experiment = {
        "mode": mode,
        "channel": channel,
        "contain": contain,
        "payload_text": payload,
    }
    return scenario
