"""event_log reads from per-world SQLite files."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from breachbench.database.events import (
    fetch_event_log,
    fetch_event_log_any_world,
    list_world_ids,
    world_db_path,
)

ROOT = Path(__file__).resolve().parents[1]
WORLDS = ROOT / "db" / "worlds"


@pytest.mark.skipif(not (WORLDS / "world_0.db").is_file(), reason="run generate_worlds.py first")
def test_list_world_ids_includes_world_0():
    ids = list_world_ids(worlds_dir=WORLDS)
    assert "world_0" in ids


@pytest.mark.skipif(not (WORLDS / "world_0.db").is_file(), reason="run generate_worlds.py first")
def test_fetch_event_log_any_world_returns_seed_rows():
    events = fetch_event_log_any_world("world_0", worlds_dir=WORLDS)
    assert len(events) >= 8
    assert events[0]["kind"] in {"tool", "email_in", "ledger", "attack", "probe", "breach"}
    breach = [e for e in events if e["kind"] == "breach"]
    assert breach and breach[0]["breach_money_moved"]


def test_fetch_event_log_empty_when_no_matching_world_id(tmp_path: Path):
    db = tmp_path / "world_99.db"
    seed = ROOT / "db" / "coffeeshop.db"
    if not seed.is_file():
        pytest.skip("coffeeshop.db missing")
    conn = sqlite3.connect(db)
    src = sqlite3.connect(seed)
    src.backup(conn)
    src.close()
    conn.close()
    assert fetch_event_log("world_99", worlds_dir=tmp_path) == []
    any_rows = fetch_event_log_any_world("world_99", worlds_dir=tmp_path)
    assert len(any_rows) >= 8


def test_world_db_path_rejects_traversal():
    with pytest.raises(ValueError):
        world_db_path("../etc/passwd")
