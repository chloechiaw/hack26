"""BreachBench — good agent vs. bad agent, at scale, in secure RL environments.

This package is the LOCKED interface layer (SPEC.md). It imports with zero deps and
defines the four contracts: sim API, event schema, scenario file, oracle.
"""

from __future__ import annotations

from .config import vb_spec
from .config.vb_spec import (
    ADVERSARY_TOOLS,
    ATTACK_CLASSES,
    OPERATOR_TOOLS,
    SPEC_VERSION,
    spec_summary,
)
from .events.schema import (
    Actor,
    BreachFlags,
    Event,
    EventEmitter,
    EventKind,
    JsonlEmitter,
    Probes,
    RunManifest,
    WorldHeader,
)
from .oracle.oracle import Oracle, OracleConfig, OracleVerdict
from .scenario import Scenario
from .sim.api import SimAPI, ToolResult
from .sim.state import WorldState

__all__ = [
    "vb_spec", "SPEC_VERSION", "spec_summary",
    "OPERATOR_TOOLS", "ADVERSARY_TOOLS", "ATTACK_CLASSES",
    "Event", "EventKind", "Actor", "Probes", "BreachFlags",
    "RunManifest", "WorldHeader", "EventEmitter", "JsonlEmitter",
    "Oracle", "OracleConfig", "OracleVerdict",
    "Scenario", "SimAPI", "ToolResult", "WorldState",
]
