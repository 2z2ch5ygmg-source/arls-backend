from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..utils.address_norm import normalize_address_text


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_site_match_index_entry(
    conn,
    *,
    tenant_id: str,
    site_id: str,
    site_name: str,
    address_text: str | None,
) -> None:
    site_key = str(site_id or "").strip()
    if not site_key:
        return
    normalized_address_text = str(address_text or "").strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sites_match_index (
                id, tenant_id, site_id, site_name, address_text, address_norm, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, site_id)
            DO UPDATE SET
                site_name = EXCLUDED.site_name,
                address_text = EXCLUDED.address_text,
                address_norm = EXCLUDED.address_norm,
                updated_at = EXCLUDED.updated_at
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                site_key,
                str(site_name or "").strip(),
                normalized_address_text,
                normalize_address_text(normalized_address_text),
                _utc_iso_now(),
            ),
        )


def delete_site_match_index_entry(conn, *, tenant_id: str, site_id: str) -> None:
    site_key = str(site_id or "").strip()
    if not site_key:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM sites_match_index
            WHERE tenant_id = %s
              AND site_id = %s
            """,
            (tenant_id, site_key),
        )


def list_site_match_index_rows(conn, *, tenant_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT site_id, site_name, address_text, address_norm, updated_at
            FROM sites_match_index
            WHERE tenant_id = %s
            ORDER BY site_name, site_id
            """,
            (tenant_id,),
        )
        rows = cur.fetchall() or []
    return list(rows)


def rebuild_site_match_index_for_tenant(conn, *, tenant_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT site_code, site_name, COALESCE(address, '') AS address_text
            FROM sites
            WHERE tenant_id = %s
            ORDER BY site_code
            """,
            (tenant_id,),
        )
        site_rows = cur.fetchall() or []

    with conn.cursor() as cur:
        cur.execute("DELETE FROM sites_match_index WHERE tenant_id = %s", (tenant_id,))

    rebuilt = 0
    for row in site_rows:
        site_id = str(row.get("site_code") or "").strip()
        if not site_id:
            continue
        upsert_site_match_index_entry(
            conn,
            tenant_id=tenant_id,
            site_id=site_id,
            site_name=str(row.get("site_name") or "").strip(),
            address_text=str(row.get("address_text") or "").strip(),
        )
        rebuilt += 1
    return rebuilt

