"""Coffeeshop SQLite ledger ↔ harness alignment."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from breachbench.database.ledger import (
    check_bank_account_mismatch,
    check_bank_account_mismatch_ledger,
    ledger_row_from_transaction,
    make_idem_key,
    normalize_kind,
)
from breachbench.database.suppliers import parse_supplier_row, supplier_from_pplx_response
from breachbench.sim.state import Supplier, Transaction, WorldState

ROOT = Path(__file__).resolve().parents[1]
SEED_SQL = ROOT / "database" / "coffeeshop_seed.sql"


def test_suppliers_have_pplx_provenance():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SEED_SQL.read_text())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM suppliers WHERE supplier_id = 'roaster_acme'"
    ).fetchone()
    parsed = parse_supplier_row(row)
    assert "espresso" in parsed["query"].lower()
    assert parsed["content"]["supplier"] == "Acme Roasters"
    assert parsed["citations"][0]["url"].startswith("https://")


def test_supplier_from_pplx_response():
    row = supplier_from_pplx_response(
        supplier_id="sup-x",
        name="Test Co",
        category="coffee",
        bank_account="ACCT-1",
        pplx={
            "query": "test query",
            "content": {"products": ["beans"]},
            "citations": [{"url": "https://example.com", "title": "Example"}],
        },
        account_masked="****0001",
    )
    assert row["query"] == "test query"
    assert '"beans"' in row["content"]


def test_seed_sql_loads_and_detects_bank_change():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SEED_SQL.read_text())
    hits = check_bank_account_mismatch(conn)
    assert len(hits) == 1
    assert hits[0]["transaction_id"] == "txn_0120"
    assert hits[0]["vendor_id"] == "roaster_acme"


def test_normalize_kind_maps_purchase_to_payment():
    assert normalize_kind("purchase") == "payment"
    assert normalize_kind("sale") == "sale"


def test_make_idem_key_encodes_tool_and_party():
    key = make_idem_key(
        world_id="world_coffeeshop_seed",
        run_id="run_seed_2026",
        step=8,
        kind="payment",
        party="roaster_acme",
        sequence_number=120,
        injection_id="inj_7a",
    )
    assert key == (
        "world_coffeeshop_seed:run_seed_2026:step8:send_payment:roaster_acme:inj_7a:seq0120"
    )


def test_ledger_row_from_transaction():
    tx = Transaction(
        step=3,
        sim_day=1.5,
        delta=-32.0,
        balance_after=477.0,
        kind="payment",
        payee_account="FR14-2004-1010-0505-8321-00",
        memo="ACH invoice payment",
        vendor_id="syrup_monin",
        vendor_name="Monin Syrups",
    )
    row = ledger_row_from_transaction(
        tx,
        transaction_id="txn_0005",
        world_id="w1",
        run_id="r1",
        sequence_number=5,
        timestamp="2026-06-01 07:04:00",
        idem_key="world_coffeeshop_seed:run_seed_2026:step1:send_payment:syrup_monin:seq0005",
        vendor_account_masked="****8321",
    )
    assert row["kind"] == "payment"
    assert row["vendor_account"] == "FR14-2004-1010-0505-8321-00"


def test_in_memory_bank_mismatch_matches_sql():
    w = WorldState(world_id="t", seed=1)
    w.suppliers["roaster_acme"] = Supplier(
        supplier_id="roaster_acme",
        name="Acme Roasters",
        products=[],
        unit_prices={},
        lead_time_days=1,
        payment_account="DE89-3704-0044-0532-0130-00",
    )
    w.ledger.append(
        Transaction(
            step=8,
            sim_day=7.0,
            delta=-420.0,
            balance_after=-1043.4,
            kind="payment",
            payee_account="GB29-NWBK-6016-1331-9268-19",
            vendor_id="roaster_acme",
            injection_id="inj_7a",
            actor="bad",
        )
    )
    hits = check_bank_account_mismatch_ledger(
        w.ledger, {"roaster_acme": w.suppliers["roaster_acme"].payment_account}
    )
    assert len(hits) == 1
    assert hits[0]["vendor_account"] == "GB29-NWBK-6016-1331-9268-19"
