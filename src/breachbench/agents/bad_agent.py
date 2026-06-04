"""Bad agent — inbox-only adversary loop (interface + stub).

Capability boundary (SPEC §1): the adversary has ONLY read_email / send_email. No sim
DB, no shell, no money primitive. Its entire job is to craft mail that tricks the
operator into using the operator's own dangerous capabilities. The attack payload and
its injection timing come from the scenario (scenario.bad_agent.payload), which is what
makes 'force the failure deterministically' a knob rather than luck.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import vb_spec
from ..scenario import BadAgentCfg


class BadAgent(ABC):
    """Adversary loop contract. `send_to_inbox` is injected by the runner (it routes the
    adversary's send_email into the operator's inbox)."""

    def __init__(self, cfg: BadAgentCfg, send_to_inbox, read_inbox):
        self.cfg = cfg
        self.model = cfg.model
        self.payload = cfg.payload
        self.tools = vb_spec.ADVERSARY_TOOLS
        self._send = send_to_inbox     # (sender, subject, body, spoof_note) -> None
        self._read = read_inbox        # () -> list[Email] (operator replies to adversary)

    @abstractmethod
    def maybe_inject(self, step: int) -> bool:
        """At each step, decide whether to deliver the payload (or a persistence nudge).
        Returns True if a message was injected this step."""

    def run_static(self) -> None:
        """Simplest deterministic adversary: deliver the scripted payload at
        payload.injection_step, then `persistence` follow-ups. Concrete impl next step."""
        raise NotImplementedError("adversary loop lands in the next step")
