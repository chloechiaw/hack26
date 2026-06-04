"""Good agent — VB-faithful operator loop (interface + stub).

Depends only on the SimAPI contract (sim/api.py) and the operator tool JSON
(vb_spec.OPERATOR_TOOLS). The concrete loop (next step) drives a model: read tool
results -> decide -> call SimAPI.call(tool, args) -> repeat until horizon. Context is
trimmed to the recent-token budget (vb_spec.VB_CONTEXT_TRIM_TOKENS, VERIFY) plus an
agent-side memory store (NOT part of the sim contract — see SPEC §6).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import vb_spec
from ..sim.api import SimAPI


class GoodAgent(ABC):
    """Operator loop contract."""

    def __init__(self, sim: SimAPI, model: str = vb_spec.DEFAULT_GOOD_MODEL,
                 defenses: list[str] | None = None):
        self.sim = sim
        self.model = model
        self.defenses = defenses or []
        self.tools = vb_spec.OPERATOR_TOOLS

    @abstractmethod
    def step(self) -> None:
        """Advance one operator turn: query model, dispatch one tool via self.sim.call."""

    def run(self, max_steps: int) -> None:
        """Drive the loop to the horizon (or until the runner halts it on a breach)."""
        raise NotImplementedError("operator loop lands in the next step")
