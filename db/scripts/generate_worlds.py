"""Provision per-world SQLite files from the coffeeshop template."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_WORLDS_NUM = 50

_DB_DIR = Path(__file__).resolve().parents[1]
_TEMPLATE_DB = _DB_DIR / "coffeeshop.db"
_WORLDS_DIR = _DB_DIR / "worlds"


def sync_world_from_template(template: Path, dest: Path) -> str:
    """Create or refresh dest from template. Returns 'created' or 'updated'."""
    if not template.is_file():
        raise FileNotFoundError(f"Template DB not found: {template}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    existed = dest.exists()
    src = sqlite3.connect(f"file:{template}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return "updated" if existed else "created"


def main() -> None:
    created = updated = 0
    for i in range(_WORLDS_NUM):
        world_id = f"world_{i}"
        dest = _WORLDS_DIR / f"{world_id}.db"
        action = sync_world_from_template(_TEMPLATE_DB, dest)
        if action == "created":
            created += 1
        else:
            updated += 1
        print(f"{action}: {dest.relative_to(_DB_DIR.parent)}")

    print(f"Done — {created} created, {updated} updated ({_WORLDS_NUM} worlds)")


if __name__ == "__main__":
    main()
