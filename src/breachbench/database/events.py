"""Read harness events from per-world coffeeshop SQLite (`event_log`)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORLDS_DIR = _REPO_ROOT / "db" / "worlds"

DEFAULT_EVENT_LOG_LIMIT = 100

_EVENT_LOG_COLUMNS = """
  event_id, world_id, run_id, sequence_number, step, sim_day, timestamp,
  kind, actor, text, tool, tool_args,
  email_from, email_to, email_subject, email_body, email_spoof_note,
  ledger_delta, balance_after, injection_compliance, goal_drift,
  breach_money_moved, breach_data_leaked, breach_meltdown,
  transaction_id, injection_id, idem_key, meta
"""


def _event_log_sql(*, world_filter: bool, limit: int) -> str:
    """Most recent `limit` rows by sequence_number, returned oldest-first."""
    where = "WHERE world_id = ?" if world_filter else ""
    return f"""
SELECT {_EVENT_LOG_COLUMNS}
FROM (
  SELECT {_EVENT_LOG_COLUMNS}
  FROM event_log
  {where}
  ORDER BY sequence_number DESC
  LIMIT ?
)
ORDER BY sequence_number ASC
"""


def world_db_path(world_id: str, *, worlds_dir: Path | None = None) -> Path:
    """Path to `db/worlds/{world_id}.db` (e.g. world_0)."""
    if not world_id or "/" in world_id or ".." in world_id:
        raise ValueError(f"invalid world_id: {world_id!r}")
    base = worlds_dir or _WORLDS_DIR
    return base / f"{world_id}.db"


def list_world_ids(*, worlds_dir: Path | None = None) -> list[str]:
    """Return sorted world ids that have a `.db` file under `db/worlds/`."""
    base = worlds_dir or _WORLDS_DIR
    if not base.is_dir():
        return []
    ids = [p.stem for p in base.glob("world_*.db")]
    return sorted(ids, key=lambda w: int(w.split("_", 1)[1]) if w.split("_", 1)[-1].isdigit() else w)


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("sim_day", "ledger_delta", "balance_after", "injection_compliance", "goal_drift"):
        if d.get(key) is not None:
            d[key] = float(d[key])
    for key in ("breach_money_moved", "breach_data_leaked", "breach_meltdown"):
        d[key] = bool(d[key])
    if d.get("tool_args"):
        try:
            d["tool_args"] = json.loads(d["tool_args"])
        except json.JSONDecodeError:
            pass
    if d.get("meta"):
        try:
            d["meta"] = json.loads(d["meta"])
        except json.JSONDecodeError:
            pass
    return d


def fetch_event_log(
    world_id: str,
    *,
    worlds_dir: Path | None = None,
    conn: sqlite3.Connection | None = None,
    limit: int = DEFAULT_EVENT_LOG_LIMIT,
) -> list[dict[str, Any]]:
    """Return up to `limit` most recent `event_log` rows for a world (chronological)."""
    sql = _event_log_sql(world_filter=True, limit=limit)
    params: tuple[Any, ...] = (world_id, limit)

    if conn is not None:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_event(r) for r in rows]

    path = world_db_path(world_id, worlds_dir=worlds_dir)
    if not path.is_file():
        raise FileNotFoundError(str(path))

    db = sqlite3.connect(path)
    try:
        db.row_factory = sqlite3.Row
        try:
            rows = db.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise
        return [_row_to_event(r) for r in rows]
    finally:
        db.close()


def fetch_event_log_at_path(
    db_path: Path,
    world_id: str,
    *,
    limit: int = DEFAULT_EVENT_LOG_LIMIT,
) -> list[dict[str, Any]]:
    """Read events from an explicit SQLite file (e.g. harness mount `/data/world.db`)."""
    db = sqlite3.connect(db_path)
    try:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            _event_log_sql(world_filter=True, limit=limit),
            (world_id, limit),
        ).fetchall()
        if rows:
            return [_row_to_event(r) for r in rows]
        rows = db.execute(
            _event_log_sql(world_filter=False, limit=limit),
            (limit,),
        ).fetchall()
        return [_row_to_event(r) for r in rows]
    finally:
        db.close()


def fetch_event_log_any_world(
    world_id: str,
    *,
    worlds_dir: Path | None = None,
    limit: int = DEFAULT_EVENT_LOG_LIMIT,
) -> list[dict[str, Any]]:
    """Like `fetch_event_log`, but if `world_id` has no rows, use the whole file."""
    path = world_db_path(world_id, worlds_dir=worlds_dir)
    if not path.is_file():
        raise FileNotFoundError(str(path))

    db = sqlite3.connect(path)
    try:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            _event_log_sql(world_filter=True, limit=limit),
            (world_id, limit),
        ).fetchall()
        if rows:
            return [_row_to_event(r) for r in rows]
        rows = db.execute(
            _event_log_sql(world_filter=False, limit=limit),
            (limit,),
        ).fetchall()
        return [_row_to_event(r) for r in rows]
    finally:
        db.close()
