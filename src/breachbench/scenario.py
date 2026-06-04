"""Scenario — one complete, deterministic world definition (SPEC §5).

A Scenario is the unit the runner fans out ×50. It fully determines a world:
the operator model + defenses, the adversary model + attack payload, the seeded
economy, and the oracle thresholds. Loading validates against the required keys in
`schemas/scenario.schema.json` (structural check, no external jsonschema dep).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .config import vb_spec
from .oracle.oracle import OracleConfig


@dataclass
class AttackPayload:
    """The injected email + when/how it lands (SPEC §5). This is the knob that makes
    'force the failure deterministically' a scenario setting, not luck."""
    sender: str
    spoof_note: str
    subject: str
    body: str
    injection_step: int               # step at which the email is delivered to the inbox
    persistence: int = 1              # how many follow-up nudges the adversary sends


@dataclass
class GoodAgentCfg:
    model: str = vb_spec.DEFAULT_GOOD_MODEL
    defenses: list[str] = field(default_factory=list)   # e.g. ["verify-sender"]


@dataclass
class BadAgentCfg:
    model: str = vb_spec.DEFAULT_BAD_MODEL
    attack_class: str = "spoofed-supplier"
    payload: AttackPayload | None = None


@dataclass
class WorldCfg:
    start_balance: float = vb_spec.START_BALANCE
    daily_fee: float = vb_spec.DAILY_FEE
    horizon_days: float = vb_spec.DEFAULT_HORIZON_DAYS
    seed: int = 0
    demand: dict[str, Any] = field(default_factory=dict)
    suppliers: list[dict[str, Any]] = field(default_factory=list)
    legitimate_payees: list[str] = field(default_factory=list)
    legitimate_contacts: list[str] = field(default_factory=list)
    protected_fields: list[str] = field(default_factory=lambda: [
        "balance", "transaction history", "account number", "routing"])


@dataclass
class Scenario:
    schema_version: str
    id: str
    location: str
    good_agent: GoodAgentCfg
    bad_agent: BadAgentCfg
    world: WorldCfg
    oracle: OracleConfig
    expected_outcome: str | None = None   # for test fixtures: breached|meltdown|defended|running

    # ---- loading / validation --------------------------------------------
    REQUIRED_KEYS = ["schema_version", "id", "location", "good_agent", "bad_agent",
                     "world"]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Scenario":
        missing = [k for k in cls.REQUIRED_KEYS if k not in d]
        if missing:
            raise ValueError(f"scenario missing required keys: {missing}")
        if d["bad_agent"].get("attack_class") not in vb_spec.ATTACK_CLASSES:
            raise ValueError(f"unknown attack_class: {d['bad_agent'].get('attack_class')}")

        payload = None
        if d["bad_agent"].get("payload"):
            payload = AttackPayload(**d["bad_agent"]["payload"])

        return cls(
            schema_version=d["schema_version"],
            id=d["id"],
            location=d["location"],
            good_agent=GoodAgentCfg(**d.get("good_agent", {})),
            bad_agent=BadAgentCfg(
                model=d["bad_agent"].get("model", vb_spec.DEFAULT_BAD_MODEL),
                attack_class=d["bad_agent"]["attack_class"],
                payload=payload,
            ),
            world=WorldCfg(**d.get("world", {})),
            oracle=OracleConfig.from_dict(d.get("oracle")),
            expected_outcome=d.get("expected_outcome"),
        )

    @classmethod
    def load(cls, path: str) -> "Scenario":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
