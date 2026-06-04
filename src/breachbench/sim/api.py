"""SimAPI — the operator's tool surface (abstract contract).

The simulator owns all world state (state.py). Every tool is conceptually
`(world_state, args) -> (new_world_state, ToolResult)`; the agent receives only the
ToolResult. Tools never raise to the agent — failures come back as `ok=False`.

This module defines the *contract*. The concrete simulator (the distributed-systems
owner) subclasses `SimAPI` and implements each method against a real WorldState +
SQLite snapshot. The good-agent loop depends only on this abstract surface and on
`vb_spec.OPERATOR_TOOLS` for the model-facing tool JSON.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..events.schema import Event


@dataclass
class ToolResult:
    """What the agent sees after any tool call (SPEC §2.4)."""
    ok: bool
    summary: str                       # the natural-language result shown to the agent
    data: dict[str, Any] = field(default_factory=dict)
    ledger_delta: float = 0.0
    emits: list["Event"] = field(default_factory=list)  # events the runner forwards


class SimAPI(ABC):
    """Abstract operator tool surface. One instance == one world.

    Method names and signatures are the locked contract. Tool JSON given to the model
    lives in `vb_spec.OPERATOR_TOOLS` and MUST stay in sync with these methods.
    """

    # --- inbox / mail ------------------------------------------------------
    @abstractmethod
    def read_email(self) -> ToolResult:
        """Return unread inbox (includes adversary mail)."""

    @abstractmethod
    def send_email(self, to: str, subject: str, body: str) -> ToolResult:
        """Send outbound mail. Recorded in the outbox the leak-oracle reads."""

    # --- ledger / money ----------------------------------------------------
    @abstractmethod
    def get_balance_and_transactions(self) -> ToolResult:
        """Return current balance + ledger."""

    @abstractmethod
    def send_payment(self, payee_account: str, amount: float, reference: str) -> ToolResult:
        """Money-movement primitive. The money-oracle watches the destination account."""

    @abstractmethod
    def collect_cash(self) -> ToolResult:
        """Sweep machine cash into the balance."""

    # --- supply / inventory ------------------------------------------------
    @abstractmethod
    def search_for_suppliers(self, query: str) -> ToolResult:
        """Return suppliers with products, prices, lead times, and payment accounts."""

    @abstractmethod
    def research_products(self, query: str) -> ToolResult:
        """Web-search engine (Perplexity) to research popular products & typical prices."""

    @abstractmethod
    def set_price(self, product: str, price: float) -> ToolResult:
        """Set unit sale price for a product."""

    @abstractmethod
    def move_items_from_storage_to_machine(self, items: list[dict]) -> ToolResult:
        """Restock machine slots from storage. items: [{product, qty}, ...]."""

    @abstractmethod
    def check_inventory(self) -> ToolResult:
        """Return storage + machine-slot inventory."""

    # --- time --------------------------------------------------------------
    @abstractmethod
    def advance_day(self) -> ToolResult:
        """Advance one sim-day: apply fee, land deliveries, sell to demand."""

    # --- reserved, out-of-scope v1 (SPEC §2.3) -----------------------------
    def run_bash(self, command: str) -> ToolResult:  # pragma: no cover - reserved
        raise NotImplementedError("operator shell is reserved, out-of-scope v1")

    # --- dispatch helper ---------------------------------------------------
    def call(self, tool: str, args: dict[str, Any]) -> ToolResult:
        """Dispatch a model-emitted tool call by name. Unknown tool -> ok=False."""
        from ..config import vb_spec
        if tool not in vb_spec.OPERATOR_TOOL_NAMES:
            return ToolResult(ok=False, summary=f"unknown tool: {tool}")
        return getattr(self, tool)(**args)
