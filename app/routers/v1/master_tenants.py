from __future__ import annotations

import json
import logging
import os
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from psycopg import errors as pg_errors
from psycopg import sql

from ...config import settings
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...utils.permissions import can_manage_tenant, normalize_role

MASTER_TENANT_CODE = "MASTER"
PURGE_CONFIRM_PHRASE = "DELETE ALL TENANTS EXCEPT MASTER"
PURGE_MODE_SOFT = "SOFT"
PURGE_MODE_HARD = "HARD"

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/master/tenants",
    tags=["master-tenants"],
    dependencies=[Depends(apply_rate_limit)],
)


class TenantPurgeRequest(BaseModel):
    mode: str = Field(default=PURGE_MODE_SOFT)
    confirm: str = Field(min_length=1)


def _require_dev(user: dict) -> str:
    actor_role = normalize_role(user.get("role"))
    if not can_manage_tenant(actor_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "개발자 권한이 필요합니다."},
        )
    return actor_role


def _fetch_tenant(conn, tenant_id: uuid.UUID):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code, tenant_name,
                   COALESCE(is_active, TRUE) AS is_active,
                   COALESCE(is_deleted, FALSE) AS is_deleted
            FROM tenants
            WHERE id = %s
            LIMIT 1
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
    return row


def _normalize_tenant_code(value: str | None) -> str:
    return str(value or "").strip().lower()


def _has_column(conn, table_name: str, column_name: str) -> bool:
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


def _has_table(conn, table_name: str) -> bool:
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


def _resolve_tenant_by_ref(conn, tenant_ref: str):
    ref = str(tenant_ref or "").strip()
    if not ref:
        return None

    has_is_master = _has_column(conn, "tenants", "is_master")
    is_uuid = False
    tenant_uuid = None
    try:
        tenant_uuid = uuid.UUID(ref)
        is_uuid = True
    except ValueError:
        tenant_uuid = None

    with conn.cursor() as cur:
        if has_is_master:
            base_sql = """
                SELECT id, tenant_code, tenant_name,
                       COALESCE(is_active, TRUE) AS is_active,
                       COALESCE(is_deleted, FALSE) AS is_deleted,
                       COALESCE(is_master, FALSE) AS is_master
                FROM tenants
            """
        else:
            base_sql = """
                SELECT id, tenant_code, tenant_name,
                       COALESCE(is_active, TRUE) AS is_active,
                       COALESCE(is_deleted, FALSE) AS is_deleted,
                       FALSE AS is_master
                FROM tenants
            """

        if is_uuid and tenant_uuid is not None:
            cur.execute(f"{base_sql} WHERE id = %s LIMIT 1", (tenant_uuid,))
            row = cur.fetchone()
            if row:
                return row

        normalized_code = _normalize_tenant_code(ref)
        cur.execute(
            f"{base_sql} WHERE lower(trim(tenant_code)) = %s LIMIT 1",
            (normalized_code,),
        )
        row = cur.fetchone()
    return row


def _build_db_debug_info() -> dict:
    raw_url = str(settings.database_url or "").strip()
    if not raw_url:
        return {
            "engine": "unknown",
            "db_path_or_conn": "DATABASE_URL is empty",
            "container_id": str(os.getenv("HOSTNAME") or "").strip() or None,
            "build_version": str(os.getenv("APP_BUILD_VERSION") or os.getenv("APP_VERSION") or settings.environment or "unknown").strip(),
        }

    parsed = urlparse(raw_url)
    scheme = str(parsed.scheme or "").split("+")[0].strip().lower()
    if scheme in {"postgres", "postgresql"}:
        host = str(parsed.hostname or "").strip() or "-"
        port = f":{parsed.port}" if parsed.port else ""
        db_name = str(parsed.path or "").strip().lstrip("/") or "-"
        conn_hint = f"{host}{port}/{db_name}"
    elif scheme.startswith("sqlite"):
        sqlite_path = str(parsed.path or "").strip()
        conn_hint = sqlite_path or (raw_url if raw_url.startswith("sqlite:") else "sqlite://<unknown>")
    else:
        host = str(parsed.hostname or "").strip() or "-"
        db_name = str(parsed.path or "").strip().lstrip("/") or "-"
        conn_hint = f"{host}/{db_name}"

    return {
        "engine": scheme or "unknown",
        "db_path_or_conn": conn_hint,
        "container_id": str(os.getenv("HOSTNAME") or "").strip() or None,
        "build_version": str(os.getenv("APP_BUILD_VERSION") or os.getenv("APP_VERSION") or settings.environment or "unknown").strip(),
    }


def _list_tenants_for_debug(conn) -> list[dict]:
    has_is_master = _has_column(conn, "tenants", "is_master")
    has_status = _has_column(conn, "tenants", "status")
    has_created_at = _has_column(conn, "tenants", "created_at")

    status_expr = "COALESCE(status, '') AS status" if has_status else "''::text AS status"
    created_expr = "created_at" if has_created_at else "NULL::timestamptz AS created_at"
    is_master_expr = "COALESCE(is_master, FALSE) AS is_master" if has_is_master else "FALSE AS is_master"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, tenant_code, tenant_name,
                   COALESCE(is_active, TRUE) AS is_active,
                   COALESCE(is_deleted, FALSE) AS is_deleted,
                   {status_expr},
                   {created_expr},
                   {is_master_expr}
            FROM tenants
            ORDER BY lower(trim(tenant_code)), created_at NULLS FIRST
            """
        )
        rows = cur.fetchall()

    items: list[dict] = []
    for row in rows:
        code_raw = str(row.get("tenant_code") or "").strip()
        code_normalized = _normalize_tenant_code(code_raw)
        items.append(
            {
                "tenant_id": str(row.get("id") or ""),
                "tenant_code": code_normalized,
                "tenant_code_raw": code_raw,
                "tenant_name": row.get("tenant_name"),
                "is_active": bool(row.get("is_active", True)),
                "is_deleted": bool(row.get("is_deleted", False)),
                "status": str(row.get("status") or "").strip(),
                "is_master": bool(row.get("is_master", False)) or code_normalized == MASTER_TENANT_CODE.lower(),
                "created_at": row.get("created_at"),
            }
        )
    return items


def _list_tenants_for_purge(conn) -> list[dict]:
    has_is_master = _has_column(conn, "tenants", "is_master")
    with conn.cursor() as cur:
        if has_is_master:
            cur.execute(
                """
                SELECT id, tenant_code, tenant_name,
                       COALESCE(is_active, TRUE) AS is_active,
                       COALESCE(is_deleted, FALSE) AS is_deleted,
                       COALESCE(is_master, FALSE) AS is_master
                FROM tenants
                ORDER BY tenant_code
                """
            )
        else:
            cur.execute(
                """
                SELECT id, tenant_code, tenant_name,
                       COALESCE(is_active, TRUE) AS is_active,
                       COALESCE(is_deleted, FALSE) AS is_deleted,
                       FALSE AS is_master
                FROM tenants
                ORDER BY tenant_code
                """
            )
        return [dict(row) for row in cur.fetchall()]


def _soft_delete_tenant_rows(conn, tenant_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> int:
    has_status = _has_column(conn, "tenants", "status")
    with conn.cursor() as cur:
        if has_status:
            cur.execute(
                """
                UPDATE tenants
                SET status = 'disabled',
                    is_deleted = TRUE,
                    deleted_at = timezone('utc', now()),
                    deleted_by = %s,
                    is_active = FALSE,
                    updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (actor_user_id, tenant_id),
            )
        else:
            cur.execute(
                """
                UPDATE tenants
                SET is_deleted = TRUE,
                    deleted_at = timezone('utc', now()),
                    deleted_by = %s,
                    is_active = FALSE,
                    updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (actor_user_id, tenant_id),
            )
        cur.execute(
            """
            UPDATE arls_users
            SET is_deleted = TRUE,
                deleted_at = timezone('utc', now()),
                deleted_by = %s,
                is_active = FALSE,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            """,
            (actor_user_id, tenant_id),
        )
        disabled_users = int(cur.rowcount or 0)
    return disabled_users


def _tenant_column_type_map(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.table_name, c.data_type
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema
             AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND c.column_name = 'tenant_id'
              AND c.table_name <> 'tenants'
              AND t.table_type = 'BASE TABLE'
            ORDER BY c.table_name
            """
        )
        rows = cur.fetchall()
    return {
        str(row["table_name"]): str(row.get("data_type") or "").strip().lower()
        for row in rows
    }


def _tenant_non_base_objects(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.table_name,
                   COALESCE(t.table_type, 'UNKNOWN') AS object_type
            FROM information_schema.columns c
            LEFT JOIN information_schema.tables t
              ON t.table_schema = c.table_schema
             AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND c.column_name = 'tenant_id'
              AND c.table_name <> 'tenants'
              AND COALESCE(t.table_type, '') <> 'BASE TABLE'
            ORDER BY c.table_name
            """
        )
        rows = cur.fetchall()
    return [
        {
            "name": str(row.get("table_name") or "").strip(),
            "object_type": str(row.get("object_type") or "UNKNOWN").strip(),
        }
        for row in rows
    ]


def _delete_table_rows_by_tenant(conn, table_name: str, tenant_data_type: str, tenant_id: uuid.UUID) -> int:
    if tenant_data_type == "uuid":
        query = sql.SQL("DELETE FROM {} WHERE tenant_id = %s").format(sql.Identifier(table_name))
        params = (tenant_id,)
    else:
        query = sql.SQL("DELETE FROM {} WHERE tenant_id::text = %s").format(sql.Identifier(table_name))
        params = (str(tenant_id),)
    with conn.cursor() as cur:
        cur.execute(query, params)
        return int(cur.rowcount or 0)


def _hard_delete_tenant_rows(conn, tenant_id: uuid.UUID) -> dict[str, int]:
    table_types = _tenant_column_type_map(conn)
    if not table_types:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
            if int(cur.rowcount or 0) == 0:
                raise RuntimeError("tenant_not_found")
        return {}

    # Priority order for common dependent tables; unknown tables are appended alphabetically.
    priority_tables = [
        "sheets_sync_retry_queue",
        "sheets_sync_log",
        "integration_event_log",
        "integration_audit_logs",
        "soc_event_ingests",
        "api_idempotency_keys",
        "schedule_import_rows",
        "schedule_import_batches",
        "google_sheet_profiles",
        "integration_feature_flags",
        "attendance_requests",
        "leave_requests",
        "support_assignment",
        "daily_event_log",
        "late_shift_log",
        "apple_late_shift",
        "apple_daytime_ot",
        "apple_overtime_log",
        "apple_report_overnight_records",
        "apple_overnight_reports",
        "soc_overtime_approvals",
        "site_daily_closing_ot",
        "overnight_assignments",
        "monthly_schedules",
        "attendance_records",
        "employees",
        "sites",
        "companies",
        "arls_users",
    ]
    ordered_tables: list[str] = []
    for table in priority_tables:
        if table in table_types and table not in ordered_tables:
            ordered_tables.append(table)
    for table in sorted(table_types.keys()):
        if table not in ordered_tables:
            ordered_tables.append(table)

    pending = ordered_tables[:]
    deleted_counts: dict[str, int] = {}

    while pending:
        unresolved: list[str] = []
        progressed = False
        for table_name in pending:
            with conn.cursor() as cur:
                cur.execute("SAVEPOINT purge_table_sp")
            try:
                deleted_counts[table_name] = _delete_table_rows_by_tenant(
                    conn,
                    table_name,
                    table_types.get(table_name, "uuid"),
                    tenant_id,
                )
                with conn.cursor() as cur:
                    cur.execute("RELEASE SAVEPOINT purge_table_sp")
                progressed = True
            except pg_errors.ForeignKeyViolation:
                with conn.cursor() as cur:
                    cur.execute("ROLLBACK TO SAVEPOINT purge_table_sp")
                    cur.execute("RELEASE SAVEPOINT purge_table_sp")
                unresolved.append(table_name)
            except Exception as exc:
                with conn.cursor() as cur:
                    cur.execute("ROLLBACK TO SAVEPOINT purge_table_sp")
                    cur.execute("RELEASE SAVEPOINT purge_table_sp")
                reason = str(exc).strip().replace("\n", " ")
                if len(reason) > 300:
                    reason = f"{reason[:297]}..."
                raise RuntimeError(
                    f"delete_failed:{table_name}:{reason}"
                ) from exc

        if unresolved and not progressed:
            raise RuntimeError(
                f"fk_constraint_blocked: {', '.join(unresolved[:8])}"
            )
        pending = unresolved

    with conn.cursor() as cur:
        cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
        if int(cur.rowcount or 0) == 0:
            raise RuntimeError("tenant_not_found")
    return deleted_counts


def _append_integration_audit_log(
    conn,
    *,
    tenant_id: uuid.UUID | None,
    action_type: str,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    target_type: str,
    target_id: str,
    detail: dict,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO integration_audit_logs (
                id, tenant_id, action_type, source, actor_user_id, actor_role,
                target_type, target_id, detail, created_at
            )
            VALUES (
                %s, %s, %s, 'hr', %s, %s,
                %s, %s, %s::jsonb, timezone('utc', now())
            )
            """,
            (
                uuid.uuid4(),
                tenant_id,
                action_type,
                actor_user_id,
                actor_role,
                target_type,
                target_id,
                json.dumps(detail, ensure_ascii=False),
            ),
        )


def _count_tenant_reference_rows(conn, tenant_id: uuid.UUID) -> list[dict]:
    references: list[dict] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_name = 'tenant_id'
              AND table_name <> 'tenants'
            ORDER BY table_name
            """
        )
        tables = [
            {
                "table_name": str(row["table_name"]),
                "data_type": str(row["data_type"] or "").strip().lower(),
            }
            for row in cur.fetchall()
        ]

    with conn.cursor() as cur:
        for item in tables:
            table_name = item["table_name"]
            data_type = item["data_type"]
            if data_type == "uuid":
                query = sql.SQL("SELECT COUNT(*) AS total FROM {} WHERE tenant_id = %s").format(
                    sql.Identifier(table_name)
                )
                params = (tenant_id,)
            else:
                query = sql.SQL("SELECT COUNT(*) AS total FROM {} WHERE tenant_id::text = %s").format(
                    sql.Identifier(table_name)
                )
                params = (str(tenant_id),)
            cur.execute(query, params)
            row = cur.fetchone() or {}
            total = int(row.get("total") or 0)
            if total > 0:
                references.append({"table": table_name, "count": total})
    return references


@router.post("/purge")
def purge_tenants(
    payload: TenantPurgeRequest,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_dev(user)
    actor_tenant_code = str(user.get("tenant_code") or "").strip().upper()
    if actor_tenant_code != MASTER_TENANT_CODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "MASTER 테넌트 개발자만 실행할 수 있습니다."},
        )

    mode = str(payload.mode or PURGE_MODE_SOFT).strip().upper()
    if mode not in {PURGE_MODE_SOFT, PURGE_MODE_HARD}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_MODE", "message": "mode는 SOFT 또는 HARD만 허용됩니다."},
        )
    if str(payload.confirm or "").strip() != PURGE_CONFIRM_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CONFIRM_MISMATCH", "message": "확인 문구가 일치하지 않습니다."},
        )

    rows = _list_tenants_for_purge(conn)
    protected: list[str] = []
    targets: list[dict] = []
    for row in rows:
        tenant_code = str(row.get("tenant_code") or "").strip().upper()
        is_master = bool(row.get("is_master"))
        if tenant_code == MASTER_TENANT_CODE or is_master:
            if tenant_code:
                protected.append(tenant_code)
            continue
        targets.append(row)

    deleted: list[str] = []
    failed: list[dict] = []
    actor_user_id = user.get("id")

    if mode == PURGE_MODE_SOFT:
        for row in targets:
            tenant_id = row.get("id")
            tenant_code = str(row.get("tenant_code") or "").strip().upper() or str(tenant_id)
            try:
                _soft_delete_tenant_rows(conn, tenant_id, actor_user_id)
                deleted.append(tenant_code)
            except Exception as exc:
                logger.exception("tenant soft purge failed: tenant=%s", tenant_code, exc_info=exc)
                failed.append({"tenant": tenant_code, "reason": str(exc)})
    else:
        for row in targets:
            tenant_id = row.get("id")
            tenant_code = str(row.get("tenant_code") or "").strip().upper() or str(tenant_id)
            with conn.cursor() as cur:
                cur.execute("SAVEPOINT purge_tenant_sp")
            try:
                _hard_delete_tenant_rows(conn, tenant_id)
                with conn.cursor() as cur:
                    cur.execute("RELEASE SAVEPOINT purge_tenant_sp")
                deleted.append(tenant_code)
            except Exception as exc:
                with conn.cursor() as cur:
                    cur.execute("ROLLBACK TO SAVEPOINT purge_tenant_sp")
                    cur.execute("RELEASE SAVEPOINT purge_tenant_sp")
                logger.exception("tenant hard purge failed: tenant=%s", tenant_code, exc_info=exc)
                failed.append({"tenant": tenant_code, "reason": str(exc)})
                break

    _append_integration_audit_log(
        conn,
        tenant_id=None,
        action_type="tenant_purge_soft" if mode == PURGE_MODE_SOFT else "tenant_purge_hard",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        target_type="tenant",
        target_id="all_except_master",
        detail={
            "mode": mode.lower(),
            "confirm": PURGE_CONFIRM_PHRASE,
            "protected_count": len(protected),
            "deleted_count": len(deleted),
            "failed_count": len(failed),
            "deleted": deleted[:200],
            "failed": failed[:50],
        },
    )

    return {
        "ok": len(failed) == 0,
        "mode": mode,
        "protected": sorted(set(protected)),
        "deleted": deleted,
        "failed": failed,
        "target_count": len(targets),
    }


@router.get("/debug")
def debug_tenants(
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_dev(user)
    db_info = _build_db_debug_info()
    tenants = _list_tenants_for_debug(conn)
    logger.info(
        "master_tenants.debug actor=%s role=%s db_engine=%s db_conn=%s container=%s tenants=%s",
        user.get("username"),
        actor_role,
        db_info.get("engine"),
        db_info.get("db_path_or_conn"),
        db_info.get("container_id"),
        len(tenants),
    )
    return {
        "db_info": db_info,
        "tenant_exists_check_source": {
            "table": "tenants",
            "predicate": "lower(trim(tenant_code))",
            "cache": "none",
        },
        "tenant_id_non_base_objects": _tenant_non_base_objects(conn),
        "tenants": tenants,
    }


@router.post("/{tenant_id}/disable")
def disable_tenant(
    tenant_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_dev(user)
    tenant = _fetch_tenant(conn, tenant_id)
    if not tenant or tenant.get("is_deleted"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "테넌트를 찾을 수 없습니다."},
        )
    tenant_code = str(tenant.get("tenant_code") or "").strip().upper()
    if tenant_code == MASTER_TENANT_CODE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "MASTER_TENANT_PROTECTED", "message": "MASTER 테넌트는 비활성화할 수 없습니다."},
        )
    if str(user.get("tenant_id")) == str(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "CURRENT_TENANT_PROTECTED", "message": "현재 로그인한 테넌트는 비활성화할 수 없습니다."},
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tenants
            SET is_active = FALSE,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (tenant_id,),
        )
        cur.execute(
            """
            UPDATE arls_users
            SET is_active = FALSE,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            """,
            (tenant_id,),
        )
        disabled_users = int(cur.rowcount or 0)

    _append_integration_audit_log(
        conn,
        tenant_id=tenant_id,
        action_type="tenant_disable",
        actor_user_id=user.get("id"),
        actor_role=actor_role,
        target_type="tenant",
        target_id=str(tenant_id),
        detail={
            "tenant_code": tenant_code,
            "tenant_name": tenant.get("tenant_name"),
            "disabled_users": disabled_users,
            "mode": "disable",
        },
    )

    return {
        "ok": True,
        "tenant_id": str(tenant_id),
        "tenant_code": tenant_code,
        "status": "disabled",
        "disabled_users": disabled_users,
    }


@router.delete("/{tenant_ref}")
def delete_tenant(
    tenant_ref: str,
    hard_delete: bool = Query(default=False),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_dev(user)
    tenant = _resolve_tenant_by_ref(conn, tenant_ref)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "테넌트를 찾을 수 없습니다."},
        )
    tenant_id = tenant.get("id")
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "테넌트를 찾을 수 없습니다."},
        )
    tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
    tenant_code_raw = str(tenant.get("tenant_code") or "").strip()
    tenant_code_normalized = _normalize_tenant_code(tenant_code_raw)
    if tenant_code_normalized == MASTER_TENANT_CODE.lower() or bool(tenant.get("is_master")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "MASTER_TENANT_PROTECTED", "message": "MASTER 테넌트는 삭제할 수 없습니다."},
        )
    if str(user.get("tenant_id")) == str(tenant_uuid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "CURRENT_TENANT_PROTECTED", "message": "현재 로그인한 테넌트는 삭제할 수 없습니다."},
        )

    ref_is_uuid = False
    try:
        uuid.UUID(str(tenant_ref).strip())
        ref_is_uuid = True
    except ValueError:
        ref_is_uuid = False

    effective_hard_delete = bool(hard_delete) or (not ref_is_uuid)

    if effective_hard_delete:
        try:
            per_table_counts = _hard_delete_tenant_rows(conn, tenant_uuid)
        except Exception as exc:
            logger.exception(
                "master_tenants.force_hard_delete.failed actor=%s tenant_ref=%s tenant_id=%s tenant_code=%s",
                user.get("username"),
                tenant_ref,
                tenant_id,
                tenant_code_raw,
                exc_info=exc,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "HARD_DELETE_FAILED",
                    "message": "테넌트 강제 삭제 중 오류가 발생했습니다.",
                    "detail": str(exc),
                },
            ) from exc
        logger.info(
            "master_tenants.force_hard_delete actor=%s tenant_ref=%s tenant_id=%s tenant_code=%s deleted_tables=%s",
            user.get("username"),
            tenant_ref,
            tenant_id,
            tenant_code_raw,
            sorted((per_table_counts or {}).keys()),
        )

        _append_integration_audit_log(
            conn,
            tenant_id=tenant_uuid,
            action_type="tenant_hard_delete",
            actor_user_id=user.get("id"),
            actor_role=actor_role,
            target_type="tenant",
            target_id=str(tenant_uuid),
            detail={
                "tenant_code": tenant_code_raw,
                "tenant_name": tenant.get("tenant_name"),
                "mode": "hard_delete",
                "deleted_table_counts": per_table_counts,
            },
        )
        return {
            "deleted": True,
            "mode": "HARD",
            "tenant_id": str(tenant_uuid),
            "tenant_code": tenant_code_normalized,
            "tenant_code_raw": tenant_code_raw,
            "deleted_table_counts": per_table_counts,
        }

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tenants
            SET is_deleted = TRUE,
                deleted_at = timezone('utc', now()),
                deleted_by = %s,
                is_active = FALSE,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (user.get("id"), tenant_uuid),
        )
        cur.execute(
            """
            UPDATE arls_users
            SET is_deleted = TRUE,
                deleted_at = timezone('utc', now()),
                deleted_by = %s,
                is_active = FALSE,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            """,
            (user.get("id"), tenant_uuid),
        )
        deleted_users = int(cur.rowcount or 0)

    _append_integration_audit_log(
        conn,
        tenant_id=tenant_uuid,
        action_type="tenant_soft_delete",
        actor_user_id=user.get("id"),
        actor_role=actor_role,
        target_type="tenant",
        target_id=str(tenant_uuid),
        detail={
            "tenant_code": tenant_code_raw,
            "tenant_name": tenant.get("tenant_name"),
            "deleted_users": deleted_users,
            "mode": "soft_delete",
        },
    )
    return {
        "deleted": True,
        "mode": "SOFT",
        "tenant_id": str(tenant_uuid),
        "tenant_code": tenant_code_normalized,
        "tenant_code_raw": tenant_code_raw,
        "disabled_users": deleted_users,
    }
