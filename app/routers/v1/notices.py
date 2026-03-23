from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import NoticeCreateIn, NoticeDetailOut, NoticeListOut, NoticeSummaryOut
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, normalize_role
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/notices", tags=["notices"], dependencies=[Depends(apply_rate_limit)])

NOTICE_CATEGORY_VALUES = {"ops", "attendance", "schedule", "hr", "system", "event"}
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
    return NoticeDetailOut(
        id=row["id"],
        category=str(row.get("category") or "ops").strip() or "ops",
        title=str(row.get("title") or "").strip() or "-",
        body_text=str(row.get("body_text") or "").strip(),
        body_preview=_extract_notice_preview(row.get("body_text")),
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
    normalized_category = _normalize_notice_category(category)

    with conn.cursor() as cur:
        if normalized_category == "all":
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
        else:
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
                  AND n.category = %s
                ORDER BY n.is_pinned DESC, n.published_at DESC, n.created_at DESC, n.id DESC
                LIMIT %s
                """,
                (tenant_id, normalized_category, int(limit)),
            )
        rows = [dict(row) for row in (cur.fetchall() or [])]

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

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notices (
                tenant_id,
                category,
                title,
                body_text,
                is_pinned,
                created_by,
                updated_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id,
                payload.category,
                payload.title,
                payload.body_text,
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
