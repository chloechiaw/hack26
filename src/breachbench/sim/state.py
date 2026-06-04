"""WorldState — the simulator owns all of this; the agent never touches it directly.

The agent acts only through SimAPI tools and sees only ToolResults (SPEC §2). These
dataclasses are the ground truth the hard oracle reads (SPEC §4). One WorldState ⇄ one
SQLite file per world for trivial snapshot/replay (SPEC §7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import vb_spec


@dataclass
class Product:
    name: str
    unit_cost: float          # what the operator paid wholesale
    price: float              # current sale price (set_price)


@dataclass
class InventorySlot:
    product: str
    qty: int


@dataclass
class Supplier:
    supplier_id: str
    name: str
    products: list[str]
    unit_prices: dict[str, float]
    lead_time_days: int
    payment_account: str       # legitimate destination for this supplier's invoices


@dataclass
class Order:
    order_id: str
    supplier_id: str
    items: dict[str, int]      # product -> qty
    amount: float
    placed_day: float
    arrives_day: float
    paid: bool = False
    delivered: bool = False


@dataclass
class Transaction:
    step: int
    sim_day: float
    delta: float               # +credit / -debit
    balance_after: float
    kind: str                  # sale | fee | payment | collect | refund | ...
    payee_account: str | None = None   # set for outbound payments (oracle reads this)
    memo: str = ""


@dataclass
class Email:
    sender: str
    to: str
    subject: str
    body: str
    sim_day: float
    step: int = 0              # step at which it was sent (oracle attributes leaks to this)
    from_adversary: bool = False
    spoof_note: str = ""       # e.g. "DMARC=fail", "look-alike domain"
    read: bool = False


@dataclass
class WorldState:
    """Complete, serializable state of one world."""
    world_id: str
    seed: int
    sim_day: float = 0.0
    step: int = 0
    balance: float = vb_spec.START_BALANCE
    daily_fee: float = vb_spec.DAILY_FEE

    products: dict[str, Product] = field(default_factory=dict)
    storage: list[InventorySlot] = field(default_factory=list)
    machine: list[InventorySlot] = field(default_factory=list)
    suppliers: dict[str, Supplier] = field(default_factory=dict)
    orders: list[Order] = field(default_factory=list)
    ledger: list[Transaction] = field(default_factory=list)

    inbox: list[Email] = field(default_factory=list)     # operator inbox
    outbox: list[Email] = field(default_factory=list)    # operator outbound (oracle reads this)
    machine_cash: float = 0.0

    # --- account/contact whitelists the oracle checks against (from scenario) ---
    legitimate_payees: set[str] = field(default_factory=set)
    legitimate_contacts: set[str] = field(default_factory=set)
    protected_fields: list[str] = field(default_factory=list)

    @property
    def net_worth(self) -> float:
        """Balance + machine cash + inventory at cost (VB objective)."""
        inv = sum(
            slot.qty * self.products[slot.product].unit_cost
            for slot in (self.storage + self.machine)
            if slot.product in self.products
        )
        return self.balance + self.machine_cash + inv
