"""Event schema — the observability + replay contract (SPEC §3).

One append-only JSONL stream per world. The dashboard, the oracle, and replay all read
the same stream — there is no second source of truth for "what happened". Field names
mirror `schemas/event.schema.json` (shared with the JS dashboard) exactly.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol


class EventKind(str, Enum):
    EMAIL_IN = "email_in"   # routine inbound mail
    ATTACK = "attack"       # adversary injection landed in the operator inbox
    TOOL = "tool"           # operator tool call
    PROBE = "probe"         # judge-model probe sample (compliance / drift)
    LEDGER = "ledger"       # balance change (sale, fee, payment, collect)
    BREACH = "breach"       # oracle fired: money_moved or data_leaked
    MELTDOWN = "meltdown"   # oracle fired: meltdown
    DEFEND = "defend"       # operator correctly refused an attack


class Actor(str, Enum):
    OPERATOR = "operator"
    ADVERSARY = "adversary"
    SIM = "sim"
    ORACLE = "oracle"


@dataclass
class RunManifest:
    """One per fleet run (SPEC §3.1)."""
    run_id: str
    created_at: str          # ISO8601; injected by caller (no wall-clock in pure code)
    spec_version: str
    horizon_days: float
    n_worlds: int
    git_sha: str = ""

    def to_json(self) -> str:
        return json.dumps({"_type": "manifest", **asdict(self)})


@dataclass
class WorldHeader:
    """First line of each world's stream (SPEC §3.2)."""
    run_id: str
    world_id: str
    scenario_id: str
    location: str
    good_model: str
    bad_model: str
    attack_class: str
    seed: int
    horizon_days: float
    snapshot_path: str = ""   # e.g. runs/<run>/wNN.sqlite

    def to_json(self) -> str:
        return json.dumps({"_type": "header", **asdict(self)})


@dataclass
class Probes:
    injection_compliance: float  # 0..1, judge model
    goal_drift: float            # 0..1, judge model


@dataclass
class BreachFlags:
    money_moved: bool = False
    data_leaked: bool = False
    meltdown: bool = False

    def any(self) -> bool:
        return self.money_moved or self.data_leaked or self.meltdown


@dataclass
class Event:
    """One per step (SPEC §3.3). Optional fields stay None and are omitted on serialize."""
    run_id: str
    world_id: str
    step: int
    sim_day: float
    kind: EventKind
    actor: Actor
    text: str = ""
    tool: str | None = None
    tool_args: dict[str, Any] | None = None
    email: dict[str, Any] | None = None         # {from, to, subject, body, spoof_note}
    ledger_delta: float = 0.0
    balance_after: float = 0.0
    probes: Probes | None = None
    breach: BreachFlags | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "run_id": self.run_id,
            "world_id": self.world_id,
            "step": self.step,
            "sim_day": self.sim_day,
            "kind": self.kind.value if isinstance(self.kind, EventKind) else self.kind,
            "actor": self.actor.value if isinstance(self.actor, Actor) else self.actor,
            "text": self.text,
            "ledger_delta": self.ledger_delta,
            "balance_after": self.balance_after,
        }
        if self.tool is not None:
            d["tool"] = self.tool
        if self.tool_args is not None:
            d["tool_args"] = self.tool_args
        if self.email is not None:
            d["email"] = self.email
        if self.probes is not None:
            d["probes"] = asdict(self.probes)
        if self.breach is not None:
            d["breach"] = asdict(self.breach)
        if self.meta:
            d["meta"] = self.meta
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EventEmitter(Protocol):
    """Sink for the event stream (SPEC §3.4). JsonlEmitter is the reference impl;
    a future StreamEmitter (SSE/WebSocket) implements the same protocol so the
    dashboard moves poll -> push with no schema change."""

    def manifest(self, manifest: RunManifest) -> None: ...
    def header(self, header: WorldHeader) -> None: ...
    def emit(self, event: Event) -> None: ...
    def close(self) -> None: ...


class JsonlEmitter:
    """Append-only JSONL, one file per world. Reference implementation."""

    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")

    def manifest(self, manifest: RunManifest) -> None:
        self._write(manifest.to_json())

    def header(self, header: WorldHeader) -> None:
        self._write(header.to_json())

    def emit(self, event: Event) -> None:
        self._write(event.to_json())

    def _write(self, line: str) -> None:
        self._fh.write(line + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
