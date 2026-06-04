"""Supplier rows with Perplexity provenance (query / content / citations)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def normalize_citations(raw: list[Any] | None) -> list[dict[str, str]]:
    """Normalize Perplexity/OpenRouter citation payloads to {url, title}."""
    out: list[dict[str, str]] = []
    for item in raw or []:
        if isinstance(item, dict):
            url = item.get("url") or item.get("link") or ""
            title = item.get("title") or item.get("name") or url
            if url:
                out.append({"url": str(url), "title": str(title)})
        elif isinstance(item, str) and item.startswith("http"):
            out.append({"url": item, "title": item})
    return out


def serialize_content(content: str | dict[str, Any]) -> str:
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    return content


def supplier_from_pplx_response(
    *,
    supplier_id: str,
    name: str,
    category: str,
    bank_account: str,
    pplx: dict[str, Any],
    account_masked: str | None = None,
    content: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a suppliers INSERT row from research.Perplexity.ask() output."""
    body = content if content is not None else pplx.get("content", "")
    return {
        "supplier_id": supplier_id,
        "name": name,
        "category": category,
        "bank_account": bank_account,
        "account_masked": account_masked,
        "query": pplx["query"],
        "content": serialize_content(body),
        "citations": json.dumps(normalize_citations(pplx.get("citations")), ensure_ascii=False),
    }


def parse_supplier_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """Parse DB row: decode content/citations JSON when possible."""
    get = (lambda k: row[k]) if not isinstance(row, dict) else row.get
    out = dict(row) if isinstance(row, dict) else {k: row[k] for k in row.keys()}
    for field in ("content", "citations"):
        raw = get(field)
        if raw is None:
            continue
        try:
            out[field] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            out[field] = raw
    return out


UPSERT_SUPPLIER_SQL = """
INSERT INTO suppliers (
  supplier_id, name, category, bank_account, account_masked, query, content, citations
) VALUES (
  :supplier_id, :name, :category, :bank_account, :account_masked, :query, :content, :citations
)
ON CONFLICT(supplier_id) DO UPDATE SET
  name = excluded.name,
  category = excluded.category,
  bank_account = excluded.bank_account,
  account_masked = excluded.account_masked,
  query = excluded.query,
  content = excluded.content,
  citations = excluded.citations
"""


def upsert_supplier(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(UPSERT_SUPPLIER_SQL, row)
