from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import (
    NoticeCreateIn,
    NoticeDeleteOut,
    NoticeDetailOut,
    NoticeListOut,
    NoticeSummaryOut,
    NoticeUpdateIn,
)
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, normalize_role
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/notices", tags=["notices"], dependencies=[Depends(apply_rate_limit)])

NOTICE_CATEGORY_VALUES = {"ops", "attendance", "schedule", "hr", "system", "event"}
NOTICE_BODY_BLOCK_KIND_VALUES = {"paragraph", "table"}
PINNED_LIMIT = 3


def _normalize_notice_category(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in NOTICE_CATEGORY_VALUES else "all"


def _ensure_notice_manage_permission(user: dict[str, Any]) -> None:
    if normalize_role(user.get("role")) not in {ROLE_DEV, ROLE_BRANCH_MANAGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "공지 작성 권한이 없습니다."},
        )


def _extract_notice_preview(body_text: str | None) -> str | None:
    raw = " ".join(str(body_text or "").strip().split())
    if not raw:
        return None
    if len(raw) <= 120:
        return raw
    return f"{raw[:117].rstrip()}..."


def _normalize_notice_body_blocks(
    raw_blocks: Any,
    *,
    fallback_body_text: str | None = None,
) -> list[dict[str, Any]]:
    blocks_source: list[Any] = []
    if isinstance(raw_blocks, str):
        try:
            parsed = json.loads(raw_blocks)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            blocks_source = parsed
    elif isinstance(raw_blocks, list):
        blocks_source = raw_blocks

    normalized_blocks: list[dict[str, Any]] = []
    for block in blocks_source:
        if hasattr(block, "model_dump"):
            block = block.model_dump()
        if not isinstance(block, dict):
            continue
        kind = str(block.get("kind") or "").strip().lower()
        if kind not in NOTICE_BODY_BLOCK_KIND_VALUES:
            continue
        if kind == "paragraph":
            text = str(block.get("text") or "").strip()
            if not text:
                continue
            variant = str(block.get("variant") or "").strip().lower()
            normalized: dict[str, Any] = {
                "kind": "paragraph",
                "variant": "lead" if variant == "lead" else "body",
                "text": text[:4000],
            }
            title = str(block.get("title") or "").strip()
            if title:
                normalized["title"] = title[:120]
            normalized_blocks.append(normalized)
            continue

        title = str(block.get("title") or "").strip()[:120]
        raw_columns = block.get("columns")
        raw_rows = block.get("rows")
        columns = []
        if isinstance(raw_columns, list):
            columns = [str(item or "").strip()[:80] for item in raw_columns[:6]]
        rows_source = raw_rows if isinstance(raw_rows, list) else []
        width = min(
            max(
                len(columns),
                max((len(row) for row in rows_source if isinstance(row, list)), default=0),
            ),
            6,
        )
        if width <= 0:
            continue
        if not columns:
            columns = [f"항목 {index + 1}" for index in range(width)]
        elif len(columns) < width:
            columns = columns + [f"항목 {index + 1}" for index in range(len(columns), width)]
        else:
            columns = columns[:width]

        rows: list[list[str]] = []
        for row in rows_source[:20]:
            if not isinstance(row, list):
                continue
            normalized_row = [str(row[index] or "").strip()[:400] if index < len(row) else "" for index in range(width)]
            if any(normalized_row):
                rows.append(normalized_row)

        if not rows and not any(columns) and not title:
            continue
        normalized = {
            "kind": "table",
            "columns": columns,
            "rows": rows,
        }
        if title:
            normalized["title"] = title
        normalized_blocks.append(normalized)

    fallback = str(fallback_body_text or "").strip()
    if normalized_blocks:
        return normalized_blocks
    if fallback:
        return [{"kind": "paragraph", "variant": "body", "text": fallback[:4000]}]
    return []


def _flatten_notice_body_text(
    body_blocks: list[dict[str, Any]] | None,
    *,
    fallback_body_text: str | None = None,
) -> str:
    blocks = body_blocks or []
    if not blocks:
        return str(fallback_body_text or "").strip()

    chunks: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("kind") or "").strip().lower()
        if kind == "paragraph":
            text = str(block.get("text") or "").strip()
            if text:
                chunks.append(text)
            continue
        if kind == "table":
            title = str(block.get("title") or "").strip()
            columns = [str(item or "").strip() for item in (block.get("columns") or []) if str(item or "").strip()]
            rows = block.get("rows") if isinstance(block.get("rows"), list) else []
            if title:
                chunks.append(title)
            if columns:
                chunks.append(" | ".join(columns))
            for row in rows:
                if isinstance(row, list):
                    line = " | ".join(str(cell or "").strip() for cell in row if str(cell or "").strip())
                    if line:
                        chunks.append(line)
    flattened = "\n\n".join(chunk for chunk in chunks if chunk)
    if flattened:
        return flattened[:20000]
    return str(fallback_body_text or "").strip()[:20000]


def _map_notice_summary(row: dict[str, Any]) -> NoticeSummaryOut:
    return NoticeSummaryOut(
        id=row["id"],
        category=str(row.get("category") or "ops").strip() or "ops",
        title=str(row.get("title") or "").strip() or "-",
        body_preview=_extract_notice_preview(row.get("body_text")),
        is_pinned=bool(row.get("is_pinned")),
        published_at=row["published_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_name=str(row.get("created_by_name") or "").strip() or None,
    )


def _map_notice_detail(row: dict[str, Any]) -> NoticeDetailOut:
    body_blocks = _normalize_notice_body_blocks(row.get("body_blocks"), fallback_body_text=row.get("body_text"))
    body_text = _flatten_notice_body_text(body_blocks, fallback_body_text=row.get("body_text"))
    return NoticeDetailOut(
        id=row["id"],
        category=str(row.get("category") or "ops").strip() or "ops",
        title=str(row.get("title") or "").strip() or "-",
        body_text=body_text,
        body_blocks=body_blocks,
        body_preview=_extract_notice_preview(body_text),
        is_pinned=bool(row.get("is_pinned")),
        published_at=row["published_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_name=str(row.get("created_by_name") or "").strip() or None,
    )


def _fetch_notice_row(conn, *, tenant_id: str, notice_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.id,
                   n.category,
                   n.title,
                   n.body_text,
                   n.body_blocks,
                   n.is_pinned,
                   n.published_at,
                   n.created_at,
                   n.updated_at,
                   COALESCE(u.full_name, u.username, '-') AS created_by_name
            FROM notices n
            LEFT JOIN arls_users u
              ON u.id = n.created_by
            WHERE n.tenant_id = %s
              AND n.id = %s
            LIMIT 1
            """,
            (tenant_id, notice_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _fetch_notice_rows(
    conn,
    *,
    tenant_id: str,
    category: str = "all",
    query: str = "",
    limit: int = 80,
) -> list[dict[str, Any]]:
    normalized_category = _normalize_notice_category(category)
    normalized_query = str(query or "").strip()
    search_like = f"%{normalized_query}%"
    sql = """
        SELECT n.id,
               n.category,
               n.title,
               n.body_text,
               n.is_pinned,
               n.published_at,
               n.created_at,
               n.updated_at,
               COALESCE(u.full_name, u.username, '-') AS created_by_name
        FROM notices n
        LEFT JOIN arls_users u
          ON u.id = n.created_by
        WHERE n.tenant_id = %s
    """
    params: list[Any] = [tenant_id]
    if normalized_category != "all":
        sql += " AND n.category = %s"
        params.append(normalized_category)
    if normalized_query:
        sql += """
            AND (
              n.title ILIKE %s
              OR n.body_text ILIKE %s
            )
        """
        params.extend([search_like, search_like])
    sql += """
        ORDER BY n.is_pinned DESC, n.published_at DESC, n.created_at DESC, n.id DESC
        LIMIT %s
    """
    params.append(int(limit))

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return [dict(row) for row in (cur.fetchall() or [])]


def _enforce_pinned_limit(conn, *, tenant_id: str, actor_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
              SELECT id,
                     ROW_NUMBER() OVER (
                       ORDER BY published_at DESC, created_at DESC, id DESC
                     ) AS row_rank
              FROM notices
              WHERE tenant_id = %s
                AND is_pinned = TRUE
            )
            UPDATE notices AS n
            SET is_pinned = FALSE,
                updated_at = timezone('utc', now()),
                updated_by = %s
            FROM ranked
            WHERE n.id = ranked.id
              AND ranked.row_rank > %s
              AND n.is_pinned = TRUE
            """,
            (tenant_id, actor_id, PINNED_LIMIT),
        )


@router.get("/home-teaser", response_model=NoticeListOut)
def list_notice_home_teaser(
    limit: int = Query(default=3, ge=1, le=5),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT n.id,
                   n.category,
                   n.title,
                   n.body_text,
                   n.is_pinned,
                   n.published_at,
                   n.created_at,
                   n.updated_at,
                   COALESCE(u.full_name, u.username, '-') AS created_by_name
            FROM notices n
            LEFT JOIN arls_users u
              ON u.id = n.created_by
            WHERE n.tenant_id = %s
            ORDER BY n.is_pinned DESC, n.published_at DESC, n.created_at DESC, n.id DESC
            LIMIT %s
            """,
            (tenant_id, int(limit)),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]

    return NoticeListOut(items=[_map_notice_summary(row) for row in rows])


@router.get("", response_model=NoticeListOut)
def list_notices(
    category: str = Query(default="all"),
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=80, ge=1, le=200),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    rows = _fetch_notice_rows(
        conn,
        tenant_id=tenant_id,
        category=category,
        query=q,
        limit=limit,
    )

    return NoticeListOut(items=[_map_notice_summary(row) for row in rows])


@router.get("/{notice_id}", response_model=NoticeDetailOut)
def get_notice_detail(
    notice_id: str,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    row = _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "공지사항을 찾을 수 없습니다."},
        )
    return _map_notice_detail(row)


@router.post("", response_model=NoticeDetailOut, status_code=status.HTTP_201_CREATED)
def create_notice(
    payload: NoticeCreateIn,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_notice_manage_permission(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    actor_id = str(user.get("id") or "").strip()
    body_blocks = _normalize_notice_body_blocks(payload.body_blocks, fallback_body_text=payload.body_text)
    body_text = _flatten_notice_body_text(body_blocks, fallback_body_text=payload.body_text)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notices (
                tenant_id,
                category,
                title,
                body_text,
                body_blocks,
                is_pinned,
                created_by,
                updated_by
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id,
                payload.category,
                payload.title,
                body_text,
                json.dumps(body_blocks, ensure_ascii=False),
                bool(payload.is_pinned),
                actor_id,
                actor_id,
            ),
        )
        created_row = cur.fetchone() or {}
        created_id = str(created_row.get("id") or "").strip()

    if payload.is_pinned:
        _enforce_pinned_limit(conn, tenant_id=tenant_id, actor_id=actor_id)

    row = _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=created_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "NOTICE_CREATE_FAILED", "message": "공지 저장에 실패했습니다."},
        )
    return _map_notice_detail(row)


@router.patch("/{notice_id}", response_model=NoticeDetailOut)
def update_notice(
    notice_id: str,
    payload: NoticeUpdateIn,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_notice_manage_permission(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    actor_id = str(user.get("id") or "").strip()
    body_blocks = _normalize_notice_body_blocks(payload.body_blocks, fallback_body_text=payload.body_text)
    body_text = _flatten_notice_body_text(body_blocks, fallback_body_text=payload.body_text)
    if not _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "공지사항을 찾을 수 없습니다."},
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE notices
            SET category = %s,
                title = %s,
                body_text = %s,
                body_blocks = %s::jsonb,
                is_pinned = %s,
                updated_at = timezone('utc', now()),
                updated_by = %s
            WHERE tenant_id = %s
              AND id = %s
            """,
            (
                payload.category,
                payload.title,
                body_text,
                json.dumps(body_blocks, ensure_ascii=False),
                bool(payload.is_pinned),
                actor_id,
                tenant_id,
                notice_id,
            ),
        )

    if payload.is_pinned:
        _enforce_pinned_limit(conn, tenant_id=tenant_id, actor_id=actor_id)

    row = _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "NOTICE_UPDATE_FAILED", "message": "공지 수정에 실패했습니다."},
        )
    return _map_notice_detail(row)


@router.delete("/{notice_id}", response_model=NoticeDeleteOut)
def delete_notice(
    notice_id: str,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_notice_manage_permission(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    if not _fetch_notice_row(conn, tenant_id=tenant_id, notice_id=notice_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "공지사항을 찾을 수 없습니다."},
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM notices
            WHERE tenant_id = %s
              AND id = %s
            """,
            (tenant_id, notice_id),
        )

    return NoticeDeleteOut(deleted=True, id=notice_id)
