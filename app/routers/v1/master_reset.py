from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from psycopg import sql

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from .master_tenants import (
    MASTER_TENANT_CODE,
    _append_integration_audit_log,
    _hard_delete_tenant_rows,
    _list_tenants_for_purge,
    _require_dev,
)

logger = logging.getLogger(__name__)

RESET_CONFIRM_PHRASE = "RESET_ALL_EXCEPT_MASTER"
RESET_MODE_HARD = "HARD"


router = APIRouter(
    prefix="/master",
    tags=["master-reset"],
    dependencies=[Depends(apply_rate_limit)],
)


class MasterResetRequest(BaseModel):
    confirm: str = Field(min_length=1)
    mode: str = Field(default=RESET_MODE_HARD, min_length=1)


def _count_rows(conn, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
            """,
            (table_name,),
        )
        exists = bool(int((cur.fetchone() or {}).get("total") or 0))
    if not exists:
        return 0

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT COUNT(*) AS total FROM {}").format(sql.Identifier(table_name))
        )
        row = cur.fetchone() or {}
        return int(row.get("total") or 0)


def _normalize_tenant_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def _is_protected_tenant(row: dict) -> bool:
    return _normalize_tenant_code(row.get("tenant_code")) == MASTER_TENANT_CODE or bool(row.get("is_master"))


def _require_master_dev(user: dict) -> str:
    actor_role = _require_dev(user)
    actor_tenant_code = _normalize_tenant_code(user.get("tenant_code"))
    if actor_tenant_code != MASTER_TENANT_CODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "MASTER 테넌트 개발자만 실행할 수 있습니다."},
        )
    return actor_role


@router.post("/reset")
def hard_reset_except_master(
    payload: MasterResetRequest,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_master_dev(user)

    confirm = str(payload.confirm or "").strip()
    if confirm != RESET_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CONFIRM_MISMATCH", "message": "확인 문구가 일치하지 않습니다."},
        )

    mode = str(payload.mode or "").strip().upper()
    if mode != RESET_MODE_HARD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_MODE", "message": "mode는 HARD만 허용됩니다."},
        )

    rows = _list_tenants_for_purge(conn)
    protected_rows = [row for row in rows if _is_protected_tenant(row)]
    target_rows = [row for row in rows if not _is_protected_tenant(row)]

    if not protected_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "MASTER_NOT_FOUND", "message": "보호 대상 MASTER 테넌트를 찾을 수 없습니다."},
        )

    for row in target_rows:
        tenant_code = _normalize_tenant_code(row.get("tenant_code"))
        if tenant_code == MASTER_TENANT_CODE or bool(row.get("is_master")):
            logger.error(
                "master protection violation detected during reset: tenant_id=%s tenant_code=%s",
                row.get("id"),
                tenant_code,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "MASTER_PROTECTED", "message": "MASTER 테넌트 삭제 시도가 감지되어 중단했습니다."},
            )

    deleted_tenants = 0
    deleted_users = 0
    deleted_sites = 0
    deleted_schedules = 0
    deleted_attendance = 0
    per_table_totals: dict[str, int] = {}

    try:
        for row in target_rows:
            tenant_id = row.get("id")
            if tenant_id is None:
                continue
            tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
            per_table = _hard_delete_tenant_rows(conn, tenant_uuid)
            deleted_tenants += 1
            for table_name, count in (per_table or {}).items():
                per_table_totals[table_name] = int(per_table_totals.get(table_name, 0)) + int(count or 0)

        deleted_users = int(per_table_totals.get("arls_users", 0))
        deleted_sites = int(per_table_totals.get("sites", 0))
        deleted_schedules = int(per_table_totals.get("monthly_schedules", 0))
        deleted_attendance = int(per_table_totals.get("attendance_records", 0))

        _append_integration_audit_log(
            conn,
            tenant_id=None,
            action_type="master_hard_reset",
            actor_user_id=user.get("id"),
            actor_role=actor_role,
            target_type="tenant",
            target_id="all_except_master",
            detail={
                "mode": "hard",
                "confirm": RESET_CONFIRM_PHRASE,
                "deleted_tenants": deleted_tenants,
                "deleted_users": deleted_users,
                "deleted_sites": deleted_sites,
                "deleted_schedules": deleted_schedules,
                "deleted_attendance": deleted_attendance,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("master hard reset failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "RESET_FAILED", "message": f"초기화 중 오류가 발생했습니다: {exc}"},
        ) from exc

    return {
        "ok": True,
        "mode": "HARD",
        "deleted_tenants": deleted_tenants,
        "deleted_users": deleted_users,
        "deleted_sites": deleted_sites,
        "deleted_schedules": deleted_schedules,
        "deleted_attendance": deleted_attendance,
    }


@router.get("/reset/status")
def get_master_reset_status(
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_master_dev(user)

    rows = _list_tenants_for_purge(conn)
    non_master = []
    master = None

    for row in rows:
        row_id = row.get("id")
        serialized_id = str(row_id) if row_id is not None else ""
        tenant_code = _normalize_tenant_code(row.get("tenant_code"))
        item = {
            "id": serialized_id,
            "tenant_code": tenant_code,
            "tenant_name": row.get("tenant_name"),
            "is_active": bool(row.get("is_active", True)),
            "is_deleted": bool(row.get("is_deleted", False)),
            "is_master": bool(row.get("is_master", False)) or tenant_code == MASTER_TENANT_CODE,
        }
        if item["is_master"]:
            master = item
        else:
            non_master.append(item)

    return {
        "ok": True,
        "tenant_count": _count_rows(conn, "tenants"),
        "user_count": _count_rows(conn, "arls_users"),
        "site_count": _count_rows(conn, "sites"),
        "schedule_count": _count_rows(conn, "monthly_schedules"),
        "attendance_count": _count_rows(conn, "attendance_records"),
        "master_tenant": master,
        "non_master_tenants": non_master,
        "non_master_count": len(non_master),
    }
