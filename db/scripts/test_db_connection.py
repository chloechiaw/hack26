"""Smoke test: open a world DB and read one menu_items row."""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "db" / "worlds" / "world_0.db"


def main() -> None:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"World DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT item_id, name, price, category, source FROM menu_items LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise RuntimeError("menu_items is empty")

    print("OK — fetched one row from menu_items:")
    print(dict(row))


if __name__ == "__main__":
    main()
