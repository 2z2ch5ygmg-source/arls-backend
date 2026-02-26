from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import requests
from fastapi import APIRouter, Body, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from psycopg import errors as pg_errors
from psycopg import sql

from ...config import settings
from ...deps import apply_rate_limit, get_db_conn, require_roles
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV
from ...utils.tenant_context import (
    build_tenant_identifier_candidates,
    normalize_tenant_identifier,
    resolve_scoped_tenant,
)

router = APIRouter(
    prefix="/admin/tenants",
    tags=["admin-tenants"],
    dependencies=[Depends(apply_rate_limit)],
)

logger = logging.getLogger(__name__)
PROTECTED_TENANT_CODES = {"master", "platform"}
RESET_CONFIRM_PHRASE = "RESET"


class TenantResetRequest(BaseModel):
    confirm: str | None = Field(default=None)


class TenantResetFullRequest(BaseModel):
    confirm: str | None = Field(default=None)
    mode: str = Field(default="HARD")
    reset_soc: bool = Field(default=True)
    reset_hr: bool = Field(default=True)
    rebuild_after: bool = Field(default=False)


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
            LIMIT 1
            """,
            (table_name,),
        )
        return bool(cur.fetchone())


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
        return bool(cur.fetchone())


def _list_tenant_scoped_tables(conn) -> dict[str, dict[str, bool]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.table_name,
                   BOOL_OR(c.column_name = 'tenant_id') AS has_tenant_id,
                   BOOL_OR(c.column_name = 'tenant_code') AS has_tenant_code
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema
             AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
              AND c.column_name IN ('tenant_id', 'tenant_code')
              AND c.table_name <> 'tenants'
            GROUP BY c.table_name
            ORDER BY c.table_name
            """
        )
        rows = cur.fetchall()

    return {
        str(row["table_name"]): {
            "has_tenant_id": bool(row.get("has_tenant_id", False)),
            "has_tenant_code": bool(row.get("has_tenant_code", False)),
        }
        for row in rows
    }


def _build_tenant_predicate(
    *,
    has_tenant_id: bool,
    has_tenant_code: bool,
    tenant_id: str,
    tenant_code_candidates: list[str],
) -> tuple[sql.SQL | None, list[Any]]:
    clauses: list[sql.SQL] = []
    params: list[Any] = []
    if has_tenant_id and tenant_id:
        clauses.append(sql.SQL("tenant_id::text = %s"))
        params.append(tenant_id)
    if has_tenant_code and tenant_code_candidates:
        clauses.append(sql.SQL("lower(trim(tenant_code::text)) = ANY(%s::text[])"))
        params.append(tenant_code_candidates)
    if not clauses:
        return None, []
    return sql.SQL(" OR ").join(clauses), params


def _count_tenant_rows(
    conn,
    table_name: str,
    *,
    has_tenant_id: bool,
    has_tenant_code: bool,
    tenant_id: str,
    tenant_code_candidates: list[str],
) -> int:
    predicate, params = _build_tenant_predicate(
        has_tenant_id=has_tenant_id,
        has_tenant_code=has_tenant_code,
        tenant_id=tenant_id,
        tenant_code_candidates=tenant_code_candidates,
    )
    if predicate is None:
        return 0
    query = sql.SQL("SELECT COUNT(*) AS total FROM {} WHERE {}").format(sql.Identifier(table_name), predicate)
    with conn.cursor() as cur:
        cur.execute(query, tuple(params))
        row = cur.fetchone() or {}
    return int(row.get("total") or 0)


def _delete_tenant_rows(
    conn,
    table_name: str,
    *,
    has_tenant_id: bool,
    has_tenant_code: bool,
    tenant_id: str,
    tenant_code_candidates: list[str],
) -> int:
    predicate, params = _build_tenant_predicate(
        has_tenant_id=has_tenant_id,
        has_tenant_code=has_tenant_code,
        tenant_id=tenant_id,
        tenant_code_candidates=tenant_code_candidates,
    )
    if predicate is None:
        return 0
    query = sql.SQL("DELETE FROM {} WHERE {}").format(sql.Identifier(table_name), predicate)
    with conn.cursor() as cur:
        cur.execute(query, tuple(params))
        return int(cur.rowcount or 0)


def _ordered_tenant_purge_tables(scoped_tables: dict[str, dict[str, bool]]) -> list[str]:
    priority_tables = [
        # 1) 업로드/임시 데이터
        "guard_roster_import_files",
        "guard_roster_import_sessions",
        # 2) 첨부/파일
        "employee_attachments",
        "attachments",
        "file_metadata",
        # 3) 근태/요청/휴가
        "attendance_records",
        "attendance_requests",
        "leave_requests",
        "leaves",
        # 4) 스케줄/템플릿
        "schedule_import_rows",
        "schedule_import_batches",
        "monthly_schedules",
        "schedules_monthly_rows",
        "schedules_monthly",
        "schedule_templates",
        # 5) 직원/계정
        "employees",
        "arls_users",
        # 6) 지점/회사 관련
        "sites_match_index",
        "sites",
        "companies",
        # 7) 테넌트 연동/설정
        "google_sheet_profiles",
        "sheets_sync_log",
        "sheets_sync_retry_queue",
        "integration_event_log",
        "integration_feature_flags",
        "integration_audit_logs",
        "soc_event_ingests",
        "api_idempotency_keys",
    ]
    ordered: list[str] = []
    for table_name in priority_tables:
        if table_name in scoped_tables and table_name not in ordered:
            ordered.append(table_name)
    for table_name in sorted(scoped_tables.keys()):
        if table_name not in ordered:
            ordered.append(table_name)
    return ordered


def _insert_reset_audit_log(
    conn,
    *,
    tenant_id: str,
    tenant_code: str,
    user: dict,
    deleted: dict[str, int],
    before_counts: dict[str, int],
) -> None:
    if not _table_exists(conn, "integration_audit_logs"):
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO integration_audit_logs (
                id, tenant_id, action_type, source, actor_user_id, actor_role,
                target_type, target_id, detail, created_at
            )
            VALUES (
                %s, %s, %s, 'hr', %s, %s,
                'tenant', %s, %s::jsonb, timezone('utc', now())
            )
            """,
            (
                uuid.uuid4(),
                tenant_id,
                "tenant_hr_hard_reset",
                user.get("id"),
                user.get("role"),
                tenant_code,
                json.dumps(
                    {
                        "mode": "hard_delete",
                        "deleted": deleted,
                        "before_counts": before_counts,
                    },
                    ensure_ascii=False,
                ),
            ),
        )


def _resolve_reset_target(conn, user: dict, tenant_header: str) -> tuple[str, str]:
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=tenant_header,
        require_dev_context=True,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    tenant_code = normalize_tenant_identifier(scoped_tenant.get("tenant_code")) or tenant_header
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
        )
    if tenant_code in PROTECTED_TENANT_CODES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "TENANT_RESET_FORBIDDEN", "message": "보호 테넌트는 초기화할 수 없습니다."},
        )
    return tenant_id, tenant_code


def _validate_reset_confirm(confirm_value: str | None, *, required: bool) -> None:
    normalized = str(confirm_value or "").strip().upper()
    if required and normalized != RESET_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CONFIRM_MISMATCH", "message": "확인 문구가 일치하지 않습니다."},
        )
    if not required and normalized and normalized != RESET_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CONFIRM_MISMATCH", "message": "확인 문구가 일치하지 않습니다."},
        )


def _run_hr_tenant_hard_reset(
    conn,
    user: dict,
    *,
    tenant_header: str,
    confirm_value: str | None = None,
    require_confirm: bool = False,
) -> dict[str, Any]:
    _validate_reset_confirm(confirm_value, required=require_confirm)

    stage = "resolve_tenant_scope"
    tenant_id = ""
    tenant_code = tenant_header
    try:
        stage = "resolve_target"
        tenant_id, tenant_code = _resolve_reset_target(conn, user, tenant_header)

        stage = "collect_tenant_tables"
        scoped_tables = _list_tenant_scoped_tables(conn)
        ordered_tables = _ordered_tenant_purge_tables(scoped_tables)
        tenant_code_candidates = list(build_tenant_identifier_candidates(tenant_code))
        if tenant_code and tenant_code not in tenant_code_candidates:
            tenant_code_candidates.append(tenant_code)

        before_counts: dict[str, int] = {}
        for table_name in ordered_tables:
            table_scope = scoped_tables.get(table_name) or {}
            has_tenant_id = bool(table_scope.get("has_tenant_id"))
            has_tenant_code = bool(table_scope.get("has_tenant_code"))
            stage = f"count:{table_name}"
            before_counts[table_name] = _count_tenant_rows(
                conn,
                table_name,
                has_tenant_id=has_tenant_id,
                has_tenant_code=has_tenant_code,
                tenant_id=tenant_id,
                tenant_code_candidates=tenant_code_candidates,
            )

        deleted: dict[str, int] = {}
        pending_tables = ordered_tables[:]
        while pending_tables:
            unresolved_tables: list[str] = []
            progressed = False
            for table_name in pending_tables:
                table_scope = scoped_tables.get(table_name) or {}
                has_tenant_id = bool(table_scope.get("has_tenant_id"))
                has_tenant_code = bool(table_scope.get("has_tenant_code"))
                stage = f"delete:{table_name}"
                with conn.cursor() as cur:
                    cur.execute("SAVEPOINT tenant_reset_table_sp")
                try:
                    deleted[table_name] = _delete_tenant_rows(
                        conn,
                        table_name,
                        has_tenant_id=has_tenant_id,
                        has_tenant_code=has_tenant_code,
                        tenant_id=tenant_id,
                        tenant_code_candidates=tenant_code_candidates,
                    )
                    with conn.cursor() as cur:
                        cur.execute("RELEASE SAVEPOINT tenant_reset_table_sp")
                    progressed = True
                except pg_errors.ForeignKeyViolation:
                    with conn.cursor() as cur:
                        cur.execute("ROLLBACK TO SAVEPOINT tenant_reset_table_sp")
                        cur.execute("RELEASE SAVEPOINT tenant_reset_table_sp")
                    unresolved_tables.append(table_name)
                except Exception:
                    with conn.cursor() as cur:
                        cur.execute("ROLLBACK TO SAVEPOINT tenant_reset_table_sp")
                        cur.execute("RELEASE SAVEPOINT tenant_reset_table_sp")
                    raise

            if unresolved_tables and not progressed:
                raise RuntimeError("fk_constraint_blocked: " + ", ".join(unresolved_tables[:8]))
            pending_tables = unresolved_tables

        stage = "write_audit_log"
        _insert_reset_audit_log(
            conn,
            tenant_id=tenant_id,
            tenant_code=tenant_code,
            user=user,
            deleted=deleted,
            before_counts=before_counts,
        )

        print(
            "[HR RESET] tenant hard reset "
            f"tenant={tenant_code} users={deleted.get('arls_users', 0)} "
            f"employees={deleted.get('employees', 0)} sites={deleted.get('sites', 0)}"
        )

        return {
            "success": True,
            "tenant_id": tenant_id,
            "tenant_code": tenant_code,
            "mode": "HARD",
            "deleted": deleted,
            "summary": {
                "users": int(deleted.get("arls_users", 0)),
                "employees": int(deleted.get("employees", 0)),
                "sites": int(deleted.get("sites", 0)),
            },
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception(
            "tenant reset failed tenant_code=%s tenant_id=%s stage=%s",
            tenant_code,
            tenant_id,
            stage,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "TENANT_RESET_FAILED",
                "stage": stage,
                "message": "테넌트 데이터 초기화 중 오류가 발생했습니다.",
                "detail": str(exc),
            },
        )


def _call_soc_tenant_full_reset(tenant_code: str) -> dict[str, Any]:
    soc_base_url = str(getattr(settings, "soc_base_url", "") or "").strip().rstrip("/")
    if not soc_base_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "SOC_BASE_URL_MISSING", "message": "SOC_BASE_URL 설정이 필요합니다."},
        )

    hr_reset_token = str(getattr(settings, "hr_reset_token", "") or "").strip()
    if not hr_reset_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "HR_RESET_TOKEN_MISSING", "message": "HR_RESET_TOKEN 미설정"},
        )

    reset_url = str(getattr(settings, "soc_reset_url", "") or "").strip()
    if not reset_url:
        reset_url = f"{soc_base_url}/api/admin/hr/reset-tenant"
    if reset_url.startswith("/"):
        reset_url = f"{soc_base_url}{reset_url}"
    reset_url = reset_url.rstrip("/")

    print(
        f"[HR->SOC] reset-full call url={reset_url} tenant={tenant_code} token_len={len(hr_reset_token)}"
    )
    try:
        response = requests.post(
            reset_url,
            headers={
                "X-HR-RESET-TOKEN": hr_reset_token,
                "X-Tenant-Id": tenant_code,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
    except Exception as exc:
        print(f"[HR->SOC] reset-full failed tenant={tenant_code} error={repr(exc)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "SOC_RESET_FAILED",
                "message": "SOC reset failed",
                "soc_status": None,
                "soc_body": str(exc),
            },
        ) from exc

    body_text = (response.text or "").strip()
    print(f"[HR->SOC] reset-full status={response.status_code} tenant={tenant_code} body={body_text[:300]}")
    if int(response.status_code) != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "SOC_RESET_FAILED",
                "message": "SOC reset failed",
                "soc_status": int(response.status_code),
                "soc_body": body_text[:300],
            },
        )

    try:
        payload = response.json()
    except Exception:
        payload = {"raw": body_text[:300]}
    return {
        "ok": True,
        "status_code": int(response.status_code),
        "payload": payload,
    }


@router.post("/reset")
def reset_tenant_hr_data(
    payload: TenantResetRequest | None = Body(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(ROLE_DEV, ROLE_BRANCH_MANAGER)),
):
    tenant_header = normalize_tenant_identifier(x_tenant_id)
    if not tenant_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "TENANT_CONTEXT_REQUIRED", "message": "작업회사 선택이 필요합니다."},
        )
    confirm_value = str((payload.confirm if payload else "") or "").strip()
    return _run_hr_tenant_hard_reset(
        conn,
        user,
        tenant_header=tenant_header,
        confirm_value=confirm_value,
        require_confirm=False,
    )


@router.post("/reset-full")
def reset_tenant_full(
    payload: TenantResetFullRequest | None = Body(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(ROLE_DEV, ROLE_BRANCH_MANAGER)),
):
    request_payload = payload or TenantResetFullRequest()
    tenant_header = normalize_tenant_identifier(x_tenant_id)
    if not tenant_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "TENANT_CONTEXT_REQUIRED", "message": "작업회사 선택이 필요합니다."},
        )

    mode = str(request_payload.mode or "HARD").strip().upper()
    if mode != "HARD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_MODE", "message": "mode는 HARD만 허용됩니다."},
        )

    _validate_reset_confirm(request_payload.confirm, required=True)

    _, tenant_code = _resolve_reset_target(conn, user, tenant_header)

    soc_reset_result: dict[str, Any] = {"skipped": True}
    if bool(request_payload.reset_soc):
        soc_reset_result = _call_soc_tenant_full_reset(tenant_code)

    hr_deleted_result: dict[str, Any] = {"skipped": True}
    if bool(request_payload.reset_hr):
        hr_deleted_result = _run_hr_tenant_hard_reset(
            conn,
            user,
            tenant_header=tenant_header,
            confirm_value=RESET_CONFIRM_PHRASE,
            require_confirm=True,
        )

    backfill_result: dict[str, Any] = {"skipped": True}
    if bool(request_payload.rebuild_after):
        if bool(request_payload.reset_hr):
            backfill_result = {
                "skipped": True,
                "reason": "HR_HARD_DELETE_EXECUTED",
                "message": "HR 데이터가 삭제되어 backfill을 실행하지 않았습니다.",
            }
        else:
            # Optional flow: keep disabled by default; can be enabled by setting rebuild_after=true with reset_hr=false.
            backfill_result = {
                "skipped": True,
                "reason": "NOT_IMPLEMENTED",
                "message": "rebuild_after는 현재 별도 backfill 버튼으로 실행하세요.",
            }

    return {
        "success": True,
        "tenant_code": tenant_code,
        "mode": mode,
        "soc_reset": soc_reset_result,
        "hr_deleted": hr_deleted_result,
        "backfill": backfill_result,
    }
