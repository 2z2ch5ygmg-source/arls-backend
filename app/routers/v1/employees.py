from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from psycopg.errors import ForeignKeyViolation
import requests

from ...config import settings
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import EmployeeCreate, EmployeeOut, EmployeeUpdate
from ...security import hash_password
from ...services.guard_roster_docx import (
    build_employee_code_from_management_no,
    extract_primary_docx_photo,
    match_site_candidates,
    parse_guard_roster_docx,
    select_site_match_query_text,
)
from ...services.sites_match_index import list_site_match_index_rows
from ...utils.address_norm import normalize_address_text
from ...utils.credential_norm import normalize_auth_identifier
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, ROLE_EMPLOYEE, normalize_role, normalize_user_role
from ...utils.schema_introspection import table_column_exists
from ...utils.sql_debug import SQLPlaceholderMismatchError, exec_checked
from ...utils.tenant_context import canonical_tenant_identifier, enforce_staff_site_scope, resolve_scoped_tenant

router = APIRouter(prefix="/employees", tags=["employees"], dependencies=[Depends(apply_rate_limit)])
logger = logging.getLogger(__name__)

SOC_EMPLOYEE_ROLE_MAP: dict[str, str] = {
    "OFFICER": "Officer",
    "VICE_SUPERVISOR": "Vice_Supervisor",
    "SUPERVISOR": "Supervisor",
    "HQ_ADMIN": "HQ_Admin",
    "DEVELOPER": "Developer",
}
SOC_SYNC_ALLOWED_ROLES = {
    "OFFICER",
    "VICE_SUPERVISOR",
    "SUPERVISOR",
    "HQ_ADMIN",
    "DEVELOPER",
}

GUARD_ROSTER_IMPORT_MAX_FILES = 30
GUARD_ROSTER_IMPORT_SITE_MATCH_THRESHOLD = 0.60


def _table_column_exists(conn, table_name: str, column_name: str) -> bool:
    return table_column_exists(conn, table_name, column_name)


class GuardRosterCommitItem(BaseModel):
    filename: str | None = Field(default=None, max_length=255)
    management_no: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    birthdate: str | None = Field(default=None, max_length=16)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    placement_text: str | None = Field(default=None, max_length=255)
    training_cert_no: str | None = Field(default=None, max_length=120)
    hire_date: str | None = Field(default=None, max_length=16)
    leave_date: str | None = Field(default=None, max_length=16)
    site_code: str = Field(min_length=1, max_length=64)
    site_name: str | None = Field(default=None, max_length=120)
    employee_code: str | None = Field(default=None, max_length=120)
    roster_docx_id: str | None = Field(default=None, max_length=64)
    photo_id: str | None = Field(default=None, max_length=64)
    username: str | None = Field(default=None, max_length=120)
    initial_password: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=64)
    must_change_password: bool = True
    soc_role: str | None = Field(default=None, max_length=64)

    @field_validator(
        "filename",
        "management_no",
        "name",
        "birthdate",
        "phone",
        "address",
        "placement_text",
        "training_cert_no",
        "hire_date",
        "leave_date",
        "site_code",
        "site_name",
        "employee_code",
        "roster_docx_id",
        "photo_id",
        "username",
        "initial_password",
        "role",
        "soc_role",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class GuardRosterCommitRequest(BaseModel):
    upload_session_id: str = Field(min_length=1, max_length=64)
    items: list[GuardRosterCommitItem] = Field(default_factory=list)

    @field_validator("upload_session_id", mode="before")
    @classmethod
    def _trim_upload_session_id(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("upload_session_id is required")
        return normalized


class GuardRosterCancelRequest(BaseModel):
    upload_session_id: str = Field(min_length=1, max_length=64)

    @field_validator("upload_session_id", mode="before")
    @classmethod
    def _trim_upload_session_id(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("upload_session_id is required")
        return normalized


def _normalize_roster_text(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_optional_roster_text(value: str | None) -> str | None:
    normalized = _normalize_roster_text(value)
    return normalized or None


def _parse_roster_date(value: str | None) -> date | None:
    raw = _normalize_roster_text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _build_guard_roster_file_name(file_uuid: str, source_filename: str) -> str:
    ext = source_filename.rsplit(".", 1)[-1].lower() if "." in source_filename else "docx"
    safe_ext = "docx" if ext not in {"docx"} else ext
    return f"{file_uuid}.{safe_ext}"


def _fetch_tenant_sites_for_roster_match(conn, tenant_id: str) -> tuple[list[dict[str, Any]], int]:
    # 우선: 주소 매칭 인덱스 테이블 사용
    try:
        indexed_rows = list_site_match_index_rows(conn, tenant_id=tenant_id)
    except Exception:
        indexed_rows = []
    index_total_sites = len(indexed_rows)

    normalized_rows: list[dict[str, Any]] = []
    for row in indexed_rows:
        site_id = str(row.get("site_id") or "").strip()
        if not site_id:
            continue
        address_text = str(row.get("address_text") or "").strip()
        normalized_rows.append(
            {
                "site_id": site_id,
                "site_code": site_id,
                "site_name": str(row.get("site_name") or "").strip(),
                "address_text": address_text,
                "address_norm": str(row.get("address_norm") or "").strip() or normalize_address_text(address_text),
            }
        )
    return normalized_rows, index_total_sites


def _find_site_relation_by_code(conn, tenant_id: str, site_code: str) -> dict[str, Any] | None:
    normalized_code = _normalize_roster_text(site_code).upper()
    if not normalized_code:
        return None
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            SELECT s.id AS site_id, s.site_code, s.site_name, c.id AS company_id, c.company_code
            FROM sites s
            JOIN companies c ON c.id = s.company_id
            WHERE s.tenant_id = %s
              AND upper(s.site_code) = upper(%s)
            LIMIT 1
            """,
            (tenant_id, normalized_code),
            stage="guard_roster.find_site_relation",
        )
        return cur.fetchone()


def _ensure_management_no(value: str | None) -> str:
    normalized = _normalize_roster_text(value)
    if not normalized:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "management_no is required")
    return normalized


def _raise_api_error(status_code: int, code: str, message: str):
    raise HTTPException(status_code=status_code, detail={"error": code, "message": message})


def _normalize_tenant_code(value: str | None) -> str:
    return canonical_tenant_identifier(value)


def _lookup_relation_ids(conn, tenant_id, company_code, site_code):
    company_code_text = str(company_code or "").strip()
    site_code_text = str(site_code or "").strip()
    if not company_code_text:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_INPUT", "company_code is required")
    if not site_code_text:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_INPUT", "site_code is required")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id AS company_id, c.company_code
            FROM companies c
            WHERE c.tenant_id = %s
              AND upper(c.company_code) = upper(%s)
            LIMIT 1
            """,
            (tenant_id, company_code_text),
        )
        company = cur.fetchone()
        if not company:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "COMPANY_NOT_FOUND", "company not found")

        cur.execute(
            """
            SELECT s.id AS site_id, s.site_code
            FROM sites s
            WHERE s.company_id = %s
              AND upper(s.site_code) = upper(%s)
            LIMIT 1
            """,
            (company["company_id"], site_code_text),
        )
        site = cur.fetchone()
    if not site:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "SITE_NOT_FOUND", "site not found")
    return company["company_id"], site["site_id"], company["company_code"], site["site_code"]


def _lookup_relation_ids_by_site(conn, tenant_id, site_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS site_id, s.site_code, c.id AS company_id, c.company_code
            FROM sites s
            JOIN companies c ON c.id = s.company_id
            WHERE s.id = %s
              AND c.tenant_id = %s
            LIMIT 1
            """,
            (site_id, tenant_id),
        )
        row = cur.fetchone()
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "SITE_NOT_FOUND", "site not found")
    return row["company_id"], row["site_id"], row["company_code"], row["site_code"]


def _branch_manager_site_id(user: dict) -> str:
    site_id = str(user.get("site_id") or "").strip()
    if not site_id:
        _raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "SITE_SCOPE_REQUIRED",
            "branch manager site scope is required",
        )
    return site_id


def _assert_branch_manager_site_scope(user: dict, target_site_id: str | None):
    actor_role = normalize_role(user.get("role"))
    if actor_role != ROLE_BRANCH_MANAGER:
        return
    manager_site_id = _branch_manager_site_id(user)
    if str(target_site_id or "") != manager_site_id:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")


def _reserve_next_employee_sequence(conn, tenant_id, site_id) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sites
            SET employee_sequence_seed = COALESCE(employee_sequence_seed, 0) + 1
            WHERE id = %s
              AND tenant_id = %s
            RETURNING employee_sequence_seed
            """,
            (site_id, tenant_id),
        )
        row = cur.fetchone()
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "SITE_NOT_FOUND", "site not found")
    return max(1, int((row or {}).get("employee_sequence_seed") or 1))


def _reset_site_sequence_if_empty(conn, tenant_id, site_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM employees
            WHERE tenant_id = %s
              AND site_id = %s
            """,
            (tenant_id, site_id),
        )
        row = cur.fetchone()
        remaining = int((row or {}).get("cnt") or 0)
        if remaining == 0:
            cur.execute(
                """
                UPDATE sites
                SET employee_sequence_seed = 0
                WHERE id = %s
                  AND tenant_id = %s
                """,
                (site_id, tenant_id),
            )


def _format_employee_code(site_code: str, sequence_no: int) -> str:
    return f"{str(site_code or '').strip().upper()}-{int(sequence_no):03d}"


def _to_soc_sync_role(user_role: str | None, soc_role: str | None = None) -> str:
    candidates: list[str] = []
    if soc_role:
        candidates.append(str(soc_role))
    if user_role:
        candidates.append(str(user_role))

    for candidate in candidates:
        normalized = candidate.strip().replace("-", "_").replace(" ", "_").upper()
        if normalized in SOC_SYNC_ALLOWED_ROLES:
            return normalized

    normalized_user_role = normalize_user_role(user_role)
    if normalized_user_role in SOC_SYNC_ALLOWED_ROLES:
        return normalized_user_role.upper()
    return "OFFICER"


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_soc_role(value: str | None, *, required: bool) -> str | None:
    normalized = _normalize_optional_text(value)
    if not normalized:
        if required:
            _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "soc_role is required")
        return None

    key = normalized.replace("-", "_").replace(" ", "_").upper()
    mapped = SOC_EMPLOYEE_ROLE_MAP.get(key)
    if not mapped:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "soc_role must be one of: Officer, Vice_Supervisor, Supervisor, HQ_Admin, Developer",
        )
    return mapped


def _resolve_import_account_role(
    *,
    role_value: str | None = None,
    soc_role_value: str | None = None,
) -> tuple[str, str]:
    normalized_user_role = normalize_user_role(role_value or soc_role_value or "Officer")
    user_role_key = str(normalized_user_role or "").strip().replace("-", "_").replace(" ", "_").upper()
    soc_role = SOC_EMPLOYEE_ROLE_MAP.get(user_role_key, "Officer")
    return normalized_user_role, soc_role


def _to_iso_date(value) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    text = str(value).strip()
    return text or None


def _post_employee_sync_to_soc(
    *,
    tenant_code: str,
    site_code: str,
    employee_uuid: str,
    employee_code: str,
    full_name: str,
    phone: str | None,
    username: str | None = None,
    user_role: str | None,
    birth_date=None,
    leave_date=None,
    hire_date=None,
    address: str | None = None,
    guard_training_cert_no: str | None = None,
    management_no_str: str | None = None,
    note: str | None = None,
    roster_docx_attachment_id: str | None = None,
    photo_attachment_id: str | None = None,
    soc_login_id: str | None = None,
    soc_temp_password: str | None = None,
    soc_role: str | None = None,
):
    if not bool(settings.soc_integration_enabled):
        print("[HR->SOC] employee-sync SKIP: soc_integration_enabled=false")
        logger.info("employees.soc_sync skipped: soc_integration_enabled=false")
        return

    url = str(settings.soc_employee_sync_url or "").strip()
    if not url:
        print("[HR->SOC] employee-sync SKIP: empty url")
        logger.info("employees.soc_sync skipped: SOC_EMPLOYEE_SYNC_URL is empty")
        return

    tenant_id_norm = str(tenant_code or "").strip().lower()
    site_code_norm = str(site_code or "").strip()
    employee_uuid_norm = str(employee_uuid or "").strip() or str(uuid.uuid4())
    employee_code_norm = str(employee_code or "").strip()
    role_norm = _to_soc_sync_role(user_role, soc_role)

    payload = {
        "event_type": "EMPLOYEE_CREATED",
        "tenant_id": tenant_id_norm,
        "site_code": site_code_norm,
        "employee": {
            "employee_uuid": employee_uuid_norm,
            "employee_code": employee_code_norm,
            "name": str(full_name or "").strip(),
            "phone": phone,
            "username": _normalize_optional_text(username),
            "role": role_norm,
            "birthdate": _to_iso_date(birth_date),
            "address": _normalize_optional_text(address),
            "training_cert_no": _normalize_optional_text(guard_training_cert_no),
            "hire_date": _to_iso_date(hire_date),
            "leave_date": _to_iso_date(leave_date),
            "management_no_str": _normalize_optional_text(management_no_str),
            "roster_docx_attachment_id": _normalize_optional_text(roster_docx_attachment_id),
            "photo_attachment_id": _normalize_optional_text(photo_attachment_id),
            "note": _normalize_optional_text(note),
        },
    }
    print(
        f"[HR->SOC] POST {url} "
        f"event_type={payload['event_type']} "
        f"tenant={tenant_id_norm} site={site_code_norm} "
        f"uuid={employee_uuid_norm} role={role_norm}"
    )
    try:
        response = requests.post(url, json=payload, timeout=5)
        print(f"[HR->SOC] status={response.status_code} body={(response.text or '')[:200]}")
        if response.status_code >= 400:
            print(
                "[HR->SOC] payload="
                + str(
                    {
                        "event_type": payload["event_type"],
                        "tenant_id": tenant_id_norm,
                        "site_code": site_code_norm,
                        "employee": {
                            "employee_uuid": employee_uuid_norm,
                            "employee_code": employee_code_norm,
                            "role": role_norm,
                        },
                    }
                )
            )
        logger.info(
            "[HR->SOC] employee-sync status=%s body=%s url=%s employee_uuid=%s employee_code=%s",
            response.status_code,
            (response.text or "")[:200],
            url,
            payload["employee"]["employee_uuid"],
            payload["employee"]["employee_code"],
        )
    except Exception as exc:
        print(f"[HR->SOC] failed: {repr(exc)} url={url} uuid={employee_uuid_norm}")
        logger.warning(
            "[HR->SOC] employee-sync failed: %s url=%s employee_uuid=%s employee_code=%s",
            str(exc),
            url,
            payload["employee"]["employee_uuid"],
            payload["employee"]["employee_code"],
        )


def _resolve_target_tenant(conn, user, tenant_code: str | None, tenant_id: str | None = None):
    row = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        body_tenant_id=tenant_id,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    logger.info(
        "employees.resolve_tenant resolved role=%s tenant_id=%s tenant_code=%s",
        normalize_role(user["role"]),
        row.get("id"),
        row.get("tenant_code"),
    )
    return row


def _create_guard_roster_upload_session(
    conn,
    *,
    tenant_id: str,
    uploaded_by: str,
) -> str:
    session_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO guard_roster_import_sessions (
                id, tenant_id, uploaded_by, status
            )
            VALUES (%s, %s, %s, 'OPEN')
            """,
            (session_id, tenant_id, uploaded_by),
        )
    return session_id


def _fetch_guard_roster_upload_session(
    conn,
    *,
    tenant_id: str,
    session_id: str,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            SELECT id, tenant_id, uploaded_by, status
            FROM guard_roster_import_sessions
            WHERE id = %s
              AND tenant_id = %s
            LIMIT 1
            """,
            (session_id, tenant_id),
            stage="guard_roster.fetch_session",
        )
        return cur.fetchone()


def _require_guard_roster_open_session(
    conn,
    *,
    tenant_id: str,
    session_id: str,
    actor_id: str,
    actor_role: str,
) -> dict[str, Any]:
    row = _fetch_guard_roster_upload_session(conn, tenant_id=tenant_id, session_id=session_id)
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "UPLOAD_SESSION_NOT_FOUND", "upload session not found")

    if actor_role != ROLE_DEV and str(row.get("uploaded_by") or "") != actor_id:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    current_status = str(row.get("status") or "").strip().upper()
    if current_status != "OPEN":
        _raise_api_error(status.HTTP_409_CONFLICT, "UPLOAD_SESSION_CLOSED", "upload session is not open")
    return row


def _close_guard_roster_upload_session(
    conn,
    *,
    tenant_id: str,
    session_id: str,
    status_value: str,
) -> None:
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            UPDATE guard_roster_import_sessions
            SET status = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND tenant_id = %s
            """,
            (str(status_value or "OPEN").upper(), session_id, tenant_id),
            stage="guard_roster.close_session",
        )


def _delete_guard_roster_upload_session(
    conn,
    *,
    tenant_id: str,
    session_id: str,
) -> tuple[int, int]:
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            DELETE FROM guard_roster_import_files
            WHERE tenant_id = %s
              AND upload_session_id = %s
              AND upper(import_status) = 'STAGED'
            """,
            (tenant_id, session_id),
            stage="guard_roster.delete_session_files",
        )
        deleted_files = int(cur.rowcount or 0)
        exec_checked(
            cur,
            """
            DELETE FROM guard_roster_import_sessions
            WHERE id = %s
              AND tenant_id = %s
            """,
            (session_id, tenant_id),
            stage="guard_roster.delete_session",
        )
        deleted_sessions = int(cur.rowcount or 0)
    return deleted_files, deleted_sessions


def _mark_guard_roster_files_committed(
    conn,
    *,
    tenant_id: str,
    session_id: str,
) -> None:
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            UPDATE guard_roster_import_files
            SET import_status = 'COMMITTED',
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND upload_session_id = %s
            """,
            (tenant_id, session_id),
            stage="guard_roster.mark_files_committed",
        )


def _persist_guard_roster_source_file(
    conn,
    *,
    tenant_id: str,
    upload_session_id: str,
    uploaded_by: str,
    filename: str,
    docx_bytes: bytes,
    photo_bytes: bytes | None,
    photo_mime_type: str | None,
    photo_filename: str | None,
) -> str:
    import_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            INSERT INTO guard_roster_import_files (
                id, tenant_id, upload_session_id, uploaded_by, filename, mime_type, file_bytes,
                photo_bytes, photo_mime_type, photo_filename, import_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'STAGED')
            """,
            (
                import_id,
                tenant_id,
                upload_session_id,
                uploaded_by,
                filename,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                docx_bytes,
                photo_bytes,
                photo_mime_type,
                photo_filename,
            ),
            stage="guard_roster.persist_source_file",
        )
    return import_id


def _fetch_guard_roster_file(conn, *, file_id: str, tenant_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            SELECT id, tenant_id, filename, mime_type, file_bytes,
                   photo_bytes, photo_mime_type, photo_filename,
                   upload_session_id, import_status
            FROM guard_roster_import_files
            WHERE id = %s
              AND tenant_id = %s
            LIMIT 1
            """,
            (file_id, tenant_id),
            stage="guard_roster.fetch_file",
        )
        return cur.fetchone()


def _is_guard_roster_file_in_session(
    conn,
    *,
    tenant_id: str,
    upload_session_id: str,
    file_id: str,
) -> bool:
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            SELECT 1
            FROM guard_roster_import_files
            WHERE id = %s
              AND tenant_id = %s
              AND upload_session_id = %s
              AND upper(import_status) = 'STAGED'
            LIMIT 1
            """,
            (file_id, tenant_id, upload_session_id),
            stage="guard_roster.file_in_session",
        )
        return cur.fetchone() is not None


def _upsert_guard_roster_employee(
    conn,
    *,
    tenant_id: str,
    tenant_code: str,
    site_relation: dict[str, Any],
    item: GuardRosterCommitItem,
) -> tuple[str, dict[str, Any]]:
    management_no = _ensure_management_no(item.management_no)
    full_name = _normalize_roster_text(item.name)
    if not full_name:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "name is required")

    site_code = str(site_relation.get("site_code") or "").strip().upper()
    company_code = str(site_relation.get("company_code") or "").strip().upper()
    employee_code = _normalize_roster_text(item.employee_code) or build_employee_code_from_management_no(site_code, management_no)
    if not employee_code:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "employee_code generation failed")

    phone = _normalize_optional_roster_text(item.phone)
    address = _normalize_optional_roster_text(item.address)
    note = _normalize_optional_text(address)
    roster_docx_attachment_id = _normalize_optional_roster_text(item.roster_docx_id)
    photo_attachment_id = _normalize_optional_roster_text(item.photo_id)
    account_user_role, account_soc_role = _resolve_import_account_role(
        role_value=item.role,
        soc_role_value=item.soc_role,
    )
    normalized_soc_role = _normalize_soc_role(item.soc_role or item.role, required=False) or account_soc_role

    normalized_phone_credential = normalize_auth_identifier(phone)
    if not normalized_phone_credential:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "phone is required")

    # AUTH HOTFIX: account credentials are always normalized from phone.
    account_username = normalized_phone_credential
    account_initial_password = normalized_phone_credential
    account_password_hash = hash_password(account_initial_password)
    account_must_change_password = True

    user_has_must_change_password = _table_column_exists(conn, "arls_users", "must_change_password")

    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            SELECT id, employee_uuid, employee_code, full_name, phone, birth_date, hire_date,
                   leave_date, address, management_no_str, roster_docx_attachment_id, photo_attachment_id,
                   guard_training_cert_no, note, soc_login_id, soc_role,
                   username, password_hash, must_change_password, role
            FROM employees
            WHERE tenant_id = %s
              AND upper(employee_code) = upper(%s)
            LIMIT 1
            """,
            (tenant_id, employee_code),
            stage="guard_roster.employees_lookup",
        )
        existing = cur.fetchone()

        birth_date = _parse_roster_date(item.birthdate)
        hire_date = _parse_roster_date(item.hire_date)
        leave_date = _parse_roster_date(item.leave_date)
        training_cert_no = _normalize_optional_roster_text(item.training_cert_no)

        if existing:
            update_fields = {
                "company_id": site_relation["company_id"],
                "site_id": site_relation["site_id"],
                "employee_code": employee_code,
                "full_name": full_name,
                "phone": phone,
                "birth_date": birth_date,
                "hire_date": hire_date,
                "leave_date": leave_date,
                "address": address,
                "management_no_str": management_no,
                "roster_docx_attachment_id": roster_docx_attachment_id or existing.get("roster_docx_attachment_id"),
                "photo_attachment_id": photo_attachment_id or existing.get("photo_attachment_id"),
                "guard_training_cert_no": training_cert_no,
                "note": note,
                "username": account_username,
                "password_hash": account_password_hash,
                "must_change_password": account_must_change_password,
                "role": account_user_role,
                "soc_role": normalized_soc_role or existing.get("soc_role"),
            }
            update_set_clause = ",\n                    ".join(f"{column} = %s" for column in update_fields)
            update_values = list(update_fields.values())
            update_values.append(existing["id"])
            exec_checked(
                cur,
                f"""
                UPDATE employees
                SET {update_set_clause},
                    updated_at = timezone('utc', now())
                WHERE id = %s
                RETURNING id, employee_uuid, employee_code, full_name, phone,
                          birth_date, hire_date, leave_date, address, management_no_str,
                          roster_docx_attachment_id, photo_attachment_id,
                          guard_training_cert_no, note, soc_login_id, soc_role,
                          username, password_hash, must_change_password, role
                """,
                tuple(update_values),
                stage="guard_roster.employees_update",
            )
            row = cur.fetchone()
            action = "UPDATED"
        else:
            employee_id = str(uuid.uuid4())
            employee_uuid = str(uuid.uuid4())
            insert_fields = {
                "id": employee_id,
                "employee_uuid": employee_uuid,
                "tenant_id": tenant_id,
                "company_id": site_relation["company_id"],
                "site_id": site_relation["site_id"],
                "sequence_no": None,
                "employee_code": employee_code,
                "full_name": full_name,
                "phone": phone,
                "duty_role": "GUARD",
                "birth_date": birth_date,
                "hire_date": hire_date,
                "guard_training_cert_no": training_cert_no,
                "leave_date": leave_date,
                "address": address,
                "management_no_str": management_no,
                "roster_docx_attachment_id": roster_docx_attachment_id,
                "photo_attachment_id": photo_attachment_id,
                "note": note,
                "soc_login_id": None,
                "soc_role": normalized_soc_role or "Officer",
                "username": account_username,
                "password_hash": account_password_hash,
                "must_change_password": account_must_change_password,
                "role": account_user_role,
            }
            insert_columns = ", ".join(insert_fields.keys())
            insert_placeholders = ", ".join(["%s"] * len(insert_fields))
            exec_checked(
                cur,
                f"""
                INSERT INTO employees ({insert_columns})
                VALUES ({insert_placeholders})
                RETURNING id, employee_uuid, employee_code, full_name, phone,
                          birth_date, hire_date, leave_date, address, management_no_str,
                          roster_docx_attachment_id, photo_attachment_id,
                          guard_training_cert_no, note, soc_login_id, soc_role,
                          username, password_hash, must_change_password, role
                """,
                tuple(insert_fields.values()),
                stage="guard_roster.employees_insert",
            )
            row = cur.fetchone()
            action = "CREATED"

    employee_id_value = str(row.get("id") or "")
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            SELECT id, employee_id
            FROM arls_users
            WHERE tenant_id = %s
              AND lower(username) = lower(%s)
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (tenant_id, account_username),
            stage="guard_roster.users_lookup_by_username",
        )
        username_owner = cur.fetchone()
        if username_owner and str(username_owner.get("employee_id") or "") not in {"", employee_id_value}:
            _raise_api_error(status.HTTP_409_CONFLICT, "USERNAME_EXISTS", "username already exists in tenant")

        exec_checked(
            cur,
            """
            SELECT id
            FROM arls_users
            WHERE tenant_id = %s
              AND employee_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (tenant_id, employee_id_value),
            stage="guard_roster.users_lookup_by_employee",
        )
        existing_user = cur.fetchone()
        target_user_id = str(existing_user.get("id") or "") if existing_user else ""
        if not target_user_id and username_owner and str(username_owner.get("employee_id") or "") == employee_id_value:
            target_user_id = str(username_owner.get("id") or "")

        if target_user_id:
            if user_has_must_change_password:
                exec_checked(
                    cur,
                    """
                    UPDATE arls_users
                    SET username = %s,
                        password_hash = %s,
                        full_name = %s,
                        role = %s,
                        employee_id = %s,
                        site_id = %s,
                        is_active = TRUE,
                        must_change_password = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (
                        account_username,
                        account_password_hash,
                        full_name,
                        account_user_role,
                        employee_id_value,
                        site_relation["site_id"],
                        account_must_change_password,
                        target_user_id,
                    ),
                    stage="guard_roster.users_update_with_must_change",
                )
            else:
                exec_checked(
                    cur,
                    """
                    UPDATE arls_users
                    SET username = %s,
                        password_hash = %s,
                        full_name = %s,
                        role = %s,
                        employee_id = %s,
                        site_id = %s,
                        is_active = TRUE,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (
                        account_username,
                        account_password_hash,
                        full_name,
                        account_user_role,
                        employee_id_value,
                        site_relation["site_id"],
                        target_user_id,
                    ),
                    stage="guard_roster.users_update_without_must_change",
                )
        else:
            new_user_id = str(uuid.uuid4())
            if user_has_must_change_password:
                exec_checked(
                    cur,
                    """
                    INSERT INTO arls_users (
                        id, tenant_id, username, password_hash, full_name, role, is_active,
                        employee_id, site_id, must_change_password, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, timezone('utc', now()), timezone('utc', now()))
                    """,
                    (
                        new_user_id,
                        tenant_id,
                        account_username,
                        account_password_hash,
                        full_name,
                        account_user_role,
                        employee_id_value,
                        site_relation["site_id"],
                        account_must_change_password,
                    ),
                    stage="guard_roster.users_insert_with_must_change",
                )
            else:
                exec_checked(
                    cur,
                    """
                    INSERT INTO arls_users (
                        id, tenant_id, username, password_hash, full_name, role, is_active,
                        employee_id, site_id, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, timezone('utc', now()), timezone('utc', now()))
                    """,
                    (
                        new_user_id,
                        tenant_id,
                        account_username,
                        account_password_hash,
                        full_name,
                        account_user_role,
                        employee_id_value,
                        site_relation["site_id"],
                    ),
                    stage="guard_roster.users_insert_without_must_change",
                )

    _post_employee_sync_to_soc(
        tenant_code=tenant_code,
        site_code=site_code,
        employee_uuid=str(row.get("employee_uuid") or ""),
        employee_code=str(row.get("employee_code") or employee_code),
        full_name=str(row.get("full_name") or full_name),
        phone=row.get("phone"),
        username=account_username,
        user_role=row.get("soc_role"),
        birth_date=row.get("birth_date"),
        leave_date=row.get("leave_date"),
        hire_date=row.get("hire_date"),
        address=row.get("address"),
        guard_training_cert_no=row.get("guard_training_cert_no"),
        management_no_str=row.get("management_no_str"),
        note=row.get("note"),
        roster_docx_attachment_id=row.get("roster_docx_attachment_id"),
        photo_attachment_id=row.get("photo_attachment_id"),
        soc_login_id=row.get("soc_login_id"),
        soc_role=row.get("soc_role"),
    )
    row_payload = {
        "employee_id": str(row.get("id") or ""),
        "employee_uuid": str(row.get("employee_uuid") or ""),
        "employee_code": str(row.get("employee_code") or employee_code),
        "full_name": str(row.get("full_name") or full_name),
        "phone": str(row.get("phone") or ""),
        "username": account_username,
        "role": account_user_role,
        "company_code": company_code,
        "site_code": site_code,
    }
    return action, row_payload


@router.post("/import/guard-roster-docx")
async def import_guard_roster_docx(
    files: list[UploadFile] = File(...),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = str(tenant.get("id") or "")
    tenant_code_norm = str(tenant.get("tenant_code") or "").strip().lower()
    uploaded_by = str(user.get("id") or "")
    if not files:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "docx files are required")
    if len(files) > GUARD_ROSTER_IMPORT_MAX_FILES:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            f"최대 {GUARD_ROSTER_IMPORT_MAX_FILES}개의 파일만 업로드할 수 있습니다.",
        )

    upload_session_id = _create_guard_roster_upload_session(
        conn,
        tenant_id=tenant_id,
        uploaded_by=uploaded_by,
    )
    tenant_sites, index_total_sites = _fetch_tenant_sites_for_roster_match(conn, tenant_id)
    response_items: list[dict[str, Any]] = []

    for upload in files:
        filename = str(upload.filename or "guard-roster.docx").strip() or "guard-roster.docx"
        if not filename.lower().endswith(".docx"):
            response_items.append(
                {
                    "filename": filename,
                    "parsed": {},
                    "match": {"site_code": "", "site_name": "", "confidence": 0, "candidates": [], "status": "INVALID_FILE"},
                    "generated": {"employee_code": ""},
                    "attachments": {"roster_docx_id": "", "photo_id": ""},
                    "status": "INVALID_FILE",
                    "message": "docx 파일만 업로드할 수 있습니다.",
                    "debug": {
                        "query_text_raw": "",
                        "query_norm": "",
                        "index_total_sites": index_total_sites,
                        "match_reason": "INVALID_FILE",
                    },
                }
            )
            continue

        file_bytes = await upload.read()
        if not file_bytes:
            response_items.append(
                {
                    "filename": filename,
                    "parsed": {},
                    "match": {"site_code": "", "site_name": "", "confidence": 0, "candidates": [], "status": "INVALID_FILE"},
                    "generated": {"employee_code": ""},
                    "attachments": {"roster_docx_id": "", "photo_id": ""},
                    "status": "INVALID_FILE",
                    "message": "빈 파일입니다.",
                    "debug": {
                        "query_text_raw": "",
                        "query_norm": "",
                        "index_total_sites": index_total_sites,
                        "match_reason": "INVALID_FILE",
                    },
                }
            )
            continue

        try:
            parsed = parse_guard_roster_docx(file_bytes)
        except Exception as exc:
            response_items.append(
                {
                    "filename": filename,
                    "parsed": {},
                    "match": {"site_code": "", "site_name": "", "confidence": 0, "candidates": [], "status": "PARSE_FAILED"},
                    "generated": {"employee_code": ""},
                    "attachments": {"roster_docx_id": "", "photo_id": ""},
                    "status": "PARSE_FAILED",
                    "message": f"문서 파싱 실패: {str(exc)}",
                    "debug": {
                        "query_text_raw": "",
                        "query_norm": "",
                        "index_total_sites": index_total_sites,
                        "match_reason": "PARSER_EXCEPTION",
                    },
                }
            )
            continue

        parsed_address_raw = str(parsed.get("address") or "").strip()
        parsed_placement_raw = str(parsed.get("placement_text") or "").strip()
        query_text_raw = select_site_match_query_text(
            placement_text=parsed_placement_raw,
            address_text=parsed_address_raw,
        )
        query_norm = normalize_address_text(query_text_raw)
        parse_failed = not parsed_address_raw and not parsed_placement_raw
        if parse_failed:
            match_result = {
                "site_code": "",
                "site_name": "",
                "confidence": 0.0,
                "candidates": [],
                "status": "PARSE_FAILED",
                "query_norm": "",
                "match_reason": "PARSE_FAILED",
            }
        elif index_total_sites <= 0:
            match_result = {
                "site_code": "",
                "site_name": "",
                "confidence": 0.0,
                "candidates": [],
                "status": "INDEX_EMPTY",
                "query_norm": query_norm,
                "match_reason": "INDEX_EMPTY",
            }
        else:
            match_result = match_site_candidates(
                placement_text=parsed_placement_raw,
                address_text=parsed_address_raw,
                sites=tenant_sites,
                threshold=GUARD_ROSTER_IMPORT_SITE_MATCH_THRESHOLD,
                top_n=3,
            )
        match_reason = str(match_result.get("match_reason") or "").strip().upper()
        match_status = str(match_result.get("status") or "").strip().upper()
        if parse_failed:
            item_status = "PARSE_FAILED"
            item_message = "DOCX에서 주소/배치지 추출 실패"
        elif match_reason == "INDEX_EMPTY" or match_status == "INDEX_EMPTY":
            item_status = "INDEX_EMPTY"
            item_message = "지점 인덱스가 비어있음(지점 등록/인덱스 재생성 필요)"
        elif match_status == "AUTO_CONFIRMED":
            item_status = "AUTO_CONFIRMED"
            item_message = "자동 확정"
        elif match_status == "AUTO_SELECTED":
            item_status = "AUTO_SELECTED"
            item_message = "자동선택(검토필요)"
        else:
            item_status = "NEEDS_SITE_PICK"
            item_message = "자동매칭 점수 부족(수동 선택 필요)"

        management_no_str = str(parsed.get("management_no_str") or parsed.get("management_no") or "")
        candidate_items = []
        for candidate in list(match_result.get("candidates") or []):
            candidate_site_code = str(candidate.get("site_code") or candidate.get("site_id") or "").strip()
            candidate_site_name = str(candidate.get("site_name") or candidate_site_code).strip()
            candidate_score = float(candidate.get("score") or 0)
            candidate_items.append(
                {
                    "site_id": candidate_site_code,
                    "site_code": candidate_site_code,
                    "site_name": candidate_site_name,
                    "score": round(candidate_score, 3),
                    "employee_code_preview": (
                        build_employee_code_from_management_no(candidate_site_code, management_no_str)
                        if candidate_site_code and management_no_str
                        else ""
                    ),
                }
            )

        generated_code = build_employee_code_from_management_no(
            str(match_result.get("site_code") or ""),
            management_no_str,
        )

        photo_bytes, photo_mime, photo_filename = extract_primary_docx_photo(file_bytes)
        attachment_id = _persist_guard_roster_source_file(
            conn,
            tenant_id=tenant_id,
            upload_session_id=upload_session_id,
            uploaded_by=uploaded_by,
            filename=filename,
            docx_bytes=file_bytes,
            photo_bytes=photo_bytes,
            photo_mime_type=photo_mime,
            photo_filename=photo_filename,
        )
        response_items.append(
            {
                "filename": filename,
                "parsed": {
                    "management_no": management_no_str,
                    "management_no_str": management_no_str,
                    "name": str(parsed.get("name") or ""),
                    "birthdate": str(parsed.get("birthdate") or ""),
                    "phone": str(parsed.get("phone") or ""),
                    "address": parsed_address_raw,
                    "address_raw": parsed_address_raw,
                    "placement_text": parsed_placement_raw,
                    "placement_text_raw": parsed_placement_raw,
                    "training_cert_no": str(parsed.get("training_cert_no") or ""),
                    "hire_date": str(parsed.get("hire_date") or ""),
                    "leave_date": str(parsed.get("leave_date") or ""),
                },
                "match": {
                    "site_code": str(match_result.get("site_code") or ""),
                    "site_name": str(match_result.get("site_name") or ""),
                    "status": item_status,
                    "reason": match_reason or ("PARSE_FAILED" if parse_failed else "UNKNOWN"),
                    "confidence": float(match_result.get("confidence") or 0),
                    "candidates": candidate_items,
                },
                "generated": {"employee_code": generated_code},
                "attachments": {
                    "roster_docx_id": attachment_id,
                    "photo_id": attachment_id if photo_bytes else "",
                },
                "status": item_status,
                "debug": {
                    "query_text_raw": query_text_raw,
                    "query_norm": str(match_result.get("query_norm") or query_norm or ""),
                    "index_total_sites": index_total_sites,
                    "match_reason": match_reason or ("PARSE_FAILED" if parse_failed else "UNKNOWN"),
                    "message": item_message,
                    "address_raw": parsed_address_raw,
                },
                "tenant_id": tenant_code_norm,
            }
        )

    return {"success": True, "upload_session_id": upload_session_id, "items": response_items}


@router.get("/import/guard-roster-docx/files/{file_id}")
def download_guard_roster_source_file(
    file_id: str,
    kind: str = Query(default="docx", max_length=16),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    row = _fetch_guard_roster_file(conn, file_id=file_id, tenant_id=str(tenant.get("id") or ""))
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "file not found")

    normalized_kind = str(kind or "docx").strip().lower()
    if normalized_kind == "photo":
        photo_bytes = row.get("photo_bytes")
        if not photo_bytes:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "photo not found")
        filename = str(row.get("photo_filename") or f"{file_id}.jpg")
        media_type = str(row.get("photo_mime_type") or "image/jpeg")
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=bytes(photo_bytes), media_type=media_type, headers=headers)

    docx_bytes = row.get("file_bytes")
    filename = str(row.get("filename") or f"{file_id}.docx")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=bytes(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@router.post("/import/guard-roster-docx/commit")
def commit_guard_roster_docx_import(
    payload: GuardRosterCommitRequest,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    upload_session_id = _normalize_roster_text(payload.upload_session_id)
    if not upload_session_id:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "upload_session_id is required")
    if not payload.items:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "items is required")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = str(tenant.get("id") or "")
    tenant_code_value = str(tenant.get("tenant_code") or "").strip()
    actor_id = str(user.get("id") or "")
    _require_guard_roster_open_session(
        conn,
        tenant_id=tenant_id,
        session_id=upload_session_id,
        actor_id=actor_id,
        actor_role=actor_role,
    )

    created = 0
    updated = 0
    failed: list[dict[str, str]] = []
    committed_items: list[dict[str, Any]] = []

    for index, item in enumerate(payload.items):
        savepoint = f"guard_roster_import_{index}"
        with conn.cursor() as cur:
            exec_checked(cur, f"SAVEPOINT {savepoint}", stage="guard_roster.commit.savepoint")
        try:
            roster_docx_id = _normalize_roster_text(item.roster_docx_id)
            if roster_docx_id and not _is_guard_roster_file_in_session(
                conn,
                tenant_id=tenant_id,
                upload_session_id=upload_session_id,
                file_id=roster_docx_id,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "INVALID_UPLOAD_SESSION_ITEM", "message": "upload session item mismatch"},
                )

            site_relation = _find_site_relation_by_code(conn, tenant_id, item.site_code)
            if not site_relation:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": "SITE_NOT_FOUND", "message": "site not found"},
                )

            action, row_payload = _upsert_guard_roster_employee(
                conn,
                tenant_id=tenant_id,
                tenant_code=tenant_code_value,
                site_relation=site_relation,
                item=item,
            )
            committed_items.append(
                {
                    "filename": _normalize_roster_text(item.filename),
                    "employee_code": row_payload.get("employee_code"),
                    "site_code": row_payload.get("site_code"),
                    "status": action,
                }
            )
            if action == "CREATED":
                created += 1
            else:
                updated += 1
            with conn.cursor() as cur:
                exec_checked(cur, f"RELEASE SAVEPOINT {savepoint}", stage="guard_roster.commit.release_savepoint")
        except SQLPlaceholderMismatchError as exc:
            with conn.cursor() as cur:
                exec_checked(cur, f"ROLLBACK TO SAVEPOINT {savepoint}", stage="guard_roster.commit.rollback_savepoint")
                exec_checked(cur, f"RELEASE SAVEPOINT {savepoint}", stage="guard_roster.commit.release_after_rollback")
            failed.append(
                {
                    "filename": _normalize_roster_text(item.filename) or "-",
                    "management_no": _normalize_roster_text(item.management_no),
                    "code": "SQL_MISMATCH",
                    "stage": exc.stage,
                    "reason": str(exc),
                }
            )
        except Exception as exc:
            with conn.cursor() as cur:
                exec_checked(cur, f"ROLLBACK TO SAVEPOINT {savepoint}", stage="guard_roster.commit.rollback_savepoint")
                exec_checked(cur, f"RELEASE SAVEPOINT {savepoint}", stage="guard_roster.commit.release_after_rollback")
            failed.append(
                {
                    "filename": _normalize_roster_text(item.filename) or "-",
                    "management_no": _normalize_roster_text(item.management_no),
                    "stage": "guard_roster.commit.item",
                    "reason": str(getattr(exc, "detail", exc)),
                }
            )

    _mark_guard_roster_files_committed(
        conn,
        tenant_id=tenant_id,
        session_id=upload_session_id,
    )
    _close_guard_roster_upload_session(
        conn,
        tenant_id=tenant_id,
        session_id=upload_session_id,
        status_value="COMMITTED",
    )

    return {
        "success": True,
        "upload_session_id": upload_session_id,
        "created": created,
        "updated": updated,
        "failed": failed,
        "items": committed_items,
    }


@router.post("/import/guard-roster-docx/cancel")
def cancel_guard_roster_docx_import(
    payload: GuardRosterCancelRequest,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = str(tenant.get("id") or "")
    actor_id = str(user.get("id") or "")
    upload_session_id = _normalize_roster_text(payload.upload_session_id)
    _require_guard_roster_open_session(
        conn,
        tenant_id=tenant_id,
        session_id=upload_session_id,
        actor_id=actor_id,
        actor_role=actor_role,
    )
    deleted_files, deleted_sessions = _delete_guard_roster_upload_session(
        conn,
        tenant_id=tenant_id,
        session_id=upload_session_id,
    )
    return {
        "success": True,
        "upload_session_id": upload_session_id,
        "deleted_files": deleted_files,
        "deleted_sessions": deleted_sessions,
    }


@router.post("/attachments")
async def upload_employee_attachments(
    roster_docx: UploadFile | None = File(default=None),
    photo: UploadFile | None = File(default=None),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = str(tenant.get("id") or "")
    uploaded_by = str(user.get("id") or "")

    if roster_docx is None and photo is None:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "at least one file is required")

    roster_bytes: bytes | None = None
    roster_filename = ""
    roster_mime = ""
    if roster_docx is not None:
        roster_filename = str(roster_docx.filename or "employee-roster.docx").strip() or "employee-roster.docx"
        if not roster_filename.lower().endswith(".docx"):
            _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "roster_docx must be .docx")
        roster_bytes = await roster_docx.read()
        if not roster_bytes:
            _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "roster_docx is empty")
        roster_mime = str(roster_docx.content_type or "").strip() or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    photo_bytes: bytes | None = None
    photo_filename = ""
    photo_mime = ""
    if photo is not None:
        photo_filename = str(photo.filename or "employee-photo.jpg").strip() or "employee-photo.jpg"
        photo_bytes = await photo.read()
        if not photo_bytes:
            _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "photo is empty")
        guessed_photo_mime, _ = mimetypes.guess_type(photo_filename)
        photo_mime = str(photo.content_type or guessed_photo_mime or "image/jpeg").strip() or "image/jpeg"

    file_id = str(uuid.uuid4())
    file_bytes = roster_bytes or photo_bytes or b""
    file_name = roster_filename or photo_filename or f"employee-attachment-{file_id}"
    file_mime = roster_mime or photo_mime or "application/octet-stream"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO guard_roster_import_files (
                id, tenant_id, upload_session_id, uploaded_by, filename, mime_type, file_bytes,
                photo_bytes, photo_mime_type, photo_filename, import_status
            )
            VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, 'COMMITTED')
            """,
            (
                file_id,
                tenant_id,
                uploaded_by,
                file_name,
                file_mime,
                file_bytes,
                photo_bytes,
                photo_mime or None,
                photo_filename or None,
            ),
        )

    return {
        "success": True,
        "roster_docx_attachment_id": file_id if roster_bytes else "",
        "photo_attachment_id": file_id if photo_bytes else "",
    }


@router.get("", response_model=list[EmployeeOut])
def list_employees(
    site_id: str | None = Query(default=None, max_length=64),
    site_code: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=500, ge=1, le=5000),
    include_inactive: bool = Query(default=False),
    include_deleted: bool = Query(default=False),
    detail: bool = Query(default=False),
    include_account: bool = Query(default=False),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    tenant = _resolve_target_tenant(conn, user, tenant_code)

    normalized_site_id = str(site_id or "").strip()
    if normalized_site_id.lower() == "all":
        normalized_site_id = ""
    normalized_site_code = str(site_code or "").strip()
    if normalized_site_code.lower() == "all":
        normalized_site_code = ""

    scoped_site_id = None
    scoped_site_code = None
    if actor_role == ROLE_BRANCH_MANAGER:
        scoped_site_id = _branch_manager_site_id(user)
        scoped_site_code = str(user.get("site_code") or "").strip()
        if normalized_site_id and normalized_site_id != scoped_site_id:
            _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")
        if (
            normalized_site_code
            and scoped_site_code
            and normalized_site_code.upper() != scoped_site_code.upper()
        ):
            _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")
    elif actor_role == ROLE_EMPLOYEE:
        staff_scope = enforce_staff_site_scope(user, request_site_id=normalized_site_id, request_site_code=normalized_site_code)
        scoped_site_id = str((staff_scope or {}).get("site_id") or "").strip() or None
        scoped_site_code = str((staff_scope or {}).get("site_code") or "").strip() or None
    effective_site_id = normalized_site_id or scoped_site_id
    effective_site_code = ""
    if not effective_site_id:
        effective_site_code = (normalized_site_code or scoped_site_code or "").strip()
        if effective_site_code:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT s.id
                    FROM sites s
                    WHERE s.tenant_id = %s
                      AND upper(s.site_code) = upper(%s)
                    LIMIT 1
                    """,
                    (tenant["id"], effective_site_code),
                )
                site_row = cur.fetchone()
            if site_row:
                effective_site_id = str(site_row.get("id") or "").strip()
                effective_site_code = ""

    clauses: list[str] = ["e.tenant_id = %s"]
    params = [tenant["id"]]
    if effective_site_id:
        clauses.append("s.id = %s")
        params.append(effective_site_id)
    elif effective_site_code:
        clauses.append("upper(s.site_code) = upper(%s)")
        params.append(effective_site_code)

    has_employee_active = _table_column_exists(conn, "employees", "is_active")
    has_employee_deleted = _table_column_exists(conn, "employees", "is_deleted")
    has_site_active = _table_column_exists(conn, "sites", "is_active")
    has_site_deleted = _table_column_exists(conn, "sites", "is_deleted")

    if has_employee_deleted and not include_deleted:
        clauses.append("COALESCE(e.is_deleted, FALSE) = FALSE")
    if has_site_deleted and not include_deleted:
        clauses.append("COALESCE(s.is_deleted, FALSE) = FALSE")
    if has_employee_active and not include_inactive:
        clauses.append("COALESCE(e.is_active, TRUE) = TRUE")
    if has_site_active and not include_inactive:
        clauses.append("COALESCE(s.is_active, TRUE) = TRUE")

    keyword = str(q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        clauses.append(
            """
            (
                e.employee_code ILIKE %s
                OR COALESCE(e.full_name, '') ILIKE %s
                OR COALESCE(e.phone, '') ILIKE %s
                OR COALESCE(s.site_code, '') ILIKE %s
                OR COALESCE(s.site_name, '') ILIKE %s
            )
            """
        )
        params.extend([like, like, like, like, like])

    where_sql = f"WHERE {' AND '.join(clauses)}"
    order_sql = "ORDER BY e.employee_code"
    limit_sql = "LIMIT %s"
    params.append(int(limit))

    account_join_sql = ""
    account_select_sql = "NULL::uuid AS user_id, NULL::text AS user_role"
    if include_account:
        account_select_sql = "u.id AS user_id, u.role AS user_role"
        account_join_sql = """
            LEFT JOIN (
                SELECT DISTINCT ON (au.tenant_id, au.employee_id)
                       au.tenant_id, au.employee_id, au.id, au.role
                FROM arls_users au
                WHERE COALESCE(au.is_active, TRUE) = TRUE
                  AND COALESCE(au.is_deleted, FALSE) = FALSE
                ORDER BY au.tenant_id, au.employee_id, au.updated_at DESC NULLS LAST, au.created_at DESC NULLS LAST
            ) u
              ON u.tenant_id = e.tenant_id
             AND u.employee_id = e.id
        """

    if detail:
        select_sql = """
            SELECT e.id, e.tenant_id,
                   e.employee_code, e.sequence_no, e.full_name, e.phone,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   e.management_no_str, e.birth_date, e.address, e.hire_date, e.leave_date,
                   e.guard_training_cert_no, e.note, e.roster_docx_attachment_id, e.photo_attachment_id,
                   e.soc_login_id, e.soc_role,
                   {account_select_sql}
            FROM employees e
            JOIN sites s ON s.id = e.site_id
            JOIN companies c ON c.id = s.company_id
            {account_join_sql}
            {where_sql}
            {order_sql}
            {limit_sql}
        """
    else:
        select_sql = """
            SELECT e.id, e.tenant_id,
                   e.employee_code, e.sequence_no, e.full_name, e.phone,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   e.management_no_str,
                   NULL::date AS birth_date,
                   NULL::text AS address,
                   NULL::date AS hire_date,
                   NULL::date AS leave_date,
                   NULL::text AS guard_training_cert_no,
                   NULL::text AS note,
                   NULL::text AS roster_docx_attachment_id,
                   NULL::text AS photo_attachment_id,
                   NULL::text AS soc_login_id,
                   e.soc_role,
                   {account_select_sql}
            FROM employees e
            JOIN sites s ON s.id = e.site_id
            JOIN companies c ON c.id = s.company_id
            {account_join_sql}
            {where_sql}
            {order_sql}
            {limit_sql}
        """

    with conn.cursor() as cur:
        cur.execute(
            select_sql.format(
                account_select_sql=account_select_sql,
                account_join_sql=account_join_sql,
                where_sql=where_sql,
                order_sql=order_sql,
                limit_sql=limit_sql,
            ),
            tuple(params),
        )
        rows = cur.fetchall()
    tenant_code_value = str(tenant.get("tenant_code") or "").strip().upper() or None
    tenant_name_value = str(tenant.get("tenant_name") or "").strip() or None
    result: list[EmployeeOut] = []
    for row in rows:
        resolved_user_role = row.get("user_role") or row.get("soc_role")
        payload = {
            **row,
            "tenant_code": tenant_code_value,
            "tenant_name": tenant_name_value,
            "user_role": normalize_user_role(resolved_user_role) if resolved_user_role else None,
        }
        result.append(EmployeeOut(**payload))
    return result


@router.post("", response_model=EmployeeOut)
def create_employee(
    payload: EmployeeCreate,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    requested_tenant_id = "" if actor_role == ROLE_BRANCH_MANAGER else str(payload.tenant_id or "")
    tenant = _resolve_target_tenant(conn, user, tenant_code, requested_tenant_id)
    tenant_id = tenant["id"]

    if actor_role == ROLE_BRANCH_MANAGER:
        scoped_site_id = _branch_manager_site_id(user)
        # 지점관리자는 tenant/site 스코프를 세션에서 강제 적용한다.
        # 요청 본문의 tenant/site/company 값은 신뢰하지 않는다.
        company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids_by_site(
            conn,
            tenant_id,
            scoped_site_id,
        )
    else:
        if payload.site_id:
            company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids_by_site(
                conn, tenant_id, payload.site_id
            )
        else:
            company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids(
                conn, tenant_id, payload.company_code, payload.site_code
            )

    full_name_text = str(payload.full_name or "").strip()
    normalized_soc_role = _normalize_soc_role(payload.soc_role, required=True)
    management_no_str = _normalize_optional_text(payload.management_no_str)
    address_text = _normalize_optional_text(payload.address)
    training_cert_no = _normalize_optional_text(payload.guard_training_cert_no)
    note_text = _normalize_optional_text(payload.note)
    roster_docx_attachment_id = _normalize_optional_text(payload.roster_docx_attachment_id)
    photo_attachment_id = _normalize_optional_text(payload.photo_attachment_id)
    normalized_phone_credential = normalize_auth_identifier(payload.phone)

    validation_fields: dict[str, str] = {}
    if not full_name_text:
        validation_fields["full_name"] = "required"
    if not management_no_str:
        validation_fields["management_no_str"] = "required"
    if not payload.phone or not normalized_phone_credential:
        validation_fields["phone"] = "required"
    if payload.birth_date is None:
        validation_fields["birth_date"] = "required"
    if payload.hire_date is None:
        validation_fields["hire_date"] = "required"
    if not address_text:
        validation_fields["address"] = "required"
    if not training_cert_no:
        validation_fields["guard_training_cert_no"] = "required"
    if not normalized_soc_role:
        validation_fields["soc_role"] = "required"
    if validation_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "VALIDATION_ERROR",
                "message": "입력값을 확인해주세요.",
                "fields": validation_fields,
            },
        )

    account_username = normalized_phone_credential
    account_initial_password = normalized_phone_credential
    account_password_hash = hash_password(account_initial_password)
    account_user_role = normalize_user_role(normalized_soc_role)
    account_must_change_password = True
    resolved_soc_login_id = account_username

    employee_id = uuid.uuid4()
    employee_uuid = str(uuid.uuid4())
    duty_role_value = "GUARD"
    created = None
    if management_no_str:
        generated_employee_code = build_employee_code_from_management_no(resolved_site_code, management_no_str)
        if not generated_employee_code:
            _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "management_no_str is invalid")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM employees
                WHERE tenant_id = %s
                  AND upper(employee_code) = upper(%s)
                LIMIT 1
                """,
                (tenant_id, generated_employee_code),
            )
            if cur.fetchone():
                _raise_api_error(status.HTTP_409_CONFLICT, "EMPLOYEE_CODE_CONFLICT", "employee_code already exists")

            cur.execute(
                """
                INSERT INTO employees
                    (
                      id, employee_uuid, tenant_id, company_id, site_id, sequence_no, employee_code, management_no_str,
                      full_name, phone, duty_role, birth_date, address, hire_date, leave_date,
                      guard_training_cert_no, note, roster_docx_attachment_id, photo_attachment_id,
                      soc_login_id, soc_role
                    )
                VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id, employee_code, sequence_no, full_name, phone, %s AS site_code, %s AS company_code,
                          NULL::uuid AS user_id, NULL::text AS user_role,
                          management_no_str, birth_date, address, hire_date, leave_date,
                          guard_training_cert_no, note, roster_docx_attachment_id, photo_attachment_id,
                          soc_login_id, soc_role
                """,
                (
                    employee_id,
                    employee_uuid,
                    tenant_id,
                    company_id,
                    site_id,
                    generated_employee_code,
                    management_no_str,
                    full_name_text,
                    payload.phone,
                    duty_role_value,
                    payload.birth_date,
                    address_text,
                    payload.hire_date,
                    payload.leave_date,
                    training_cert_no,
                    note_text,
                    roster_docx_attachment_id,
                    photo_attachment_id,
                    resolved_soc_login_id,
                    normalized_soc_role,
                    resolved_site_code,
                    resolved_company_code,
                ),
            )
            created = cur.fetchone()
    else:
        for _ in range(8):
            next_seq = _reserve_next_employee_sequence(conn, tenant_id, site_id)
            generated_employee_code = _format_employee_code(resolved_site_code, next_seq)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO employees
                        (
                          id, employee_uuid, tenant_id, company_id, site_id, sequence_no, employee_code, management_no_str,
                          full_name, phone, duty_role, birth_date, address, hire_date, leave_date,
                          guard_training_cert_no, note, roster_docx_attachment_id, photo_attachment_id,
                          soc_login_id, soc_role
                        )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING id, employee_code, sequence_no, full_name, phone, %s AS site_code, %s AS company_code,
                              NULL::uuid AS user_id, NULL::text AS user_role,
                              management_no_str, birth_date, address, hire_date, leave_date,
                              guard_training_cert_no, note, roster_docx_attachment_id, photo_attachment_id,
                              soc_login_id, soc_role
                    """,
                    (
                        employee_id,
                        employee_uuid,
                        tenant_id,
                        company_id,
                        site_id,
                        next_seq,
                        generated_employee_code,
                        management_no_str,
                        full_name_text,
                        payload.phone,
                        duty_role_value,
                        payload.birth_date,
                        address_text,
                        payload.hire_date,
                        payload.leave_date,
                        training_cert_no,
                        note_text,
                        roster_docx_attachment_id,
                        photo_attachment_id,
                        resolved_soc_login_id,
                        normalized_soc_role,
                        resolved_site_code,
                        resolved_company_code,
                    ),
                )
                created = cur.fetchone()
            if created:
                break
            employee_id = uuid.uuid4()

    if not created:
        _raise_api_error(
            status.HTTP_409_CONFLICT,
            "EMPLOYEE_CODE_CONFLICT",
            "failed to allocate employee_code",
        )

    user_has_must_change_password = _table_column_exists(conn, "arls_users", "must_change_password")
    created_employee_id = str(created.get("id") or "")
    target_user_id = ""
    with conn.cursor() as cur:
        exec_checked(
            cur,
            """
            SELECT id, employee_id
            FROM arls_users
            WHERE tenant_id = %s
              AND lower(username) = lower(%s)
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (tenant_id, account_username),
            stage="employees.create.users_lookup_by_username",
        )
        username_owner = cur.fetchone()
        if username_owner and str(username_owner.get("employee_id") or "") not in {"", created_employee_id}:
            _raise_api_error(status.HTTP_409_CONFLICT, "USERNAME_EXISTS", "username already exists in tenant")

        exec_checked(
            cur,
            """
            SELECT id
            FROM arls_users
            WHERE tenant_id = %s
              AND employee_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (tenant_id, created_employee_id),
            stage="employees.create.users_lookup_by_employee",
        )
        existing_user = cur.fetchone()
        if existing_user:
            target_user_id = str(existing_user.get("id") or "")
        elif username_owner and str(username_owner.get("employee_id") or "") == created_employee_id:
            target_user_id = str(username_owner.get("id") or "")

        if target_user_id:
            if user_has_must_change_password:
                exec_checked(
                    cur,
                    """
                    UPDATE arls_users
                    SET username = %s,
                        password_hash = %s,
                        full_name = %s,
                        role = %s,
                        employee_id = %s,
                        site_id = %s,
                        is_active = TRUE,
                        must_change_password = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (
                        account_username,
                        account_password_hash,
                        full_name_text,
                        account_user_role,
                        created_employee_id,
                        site_id,
                        account_must_change_password,
                        target_user_id,
                    ),
                    stage="employees.create.users_update_with_must_change",
                )
            else:
                exec_checked(
                    cur,
                    """
                    UPDATE arls_users
                    SET username = %s,
                        password_hash = %s,
                        full_name = %s,
                        role = %s,
                        employee_id = %s,
                        site_id = %s,
                        is_active = TRUE,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (
                        account_username,
                        account_password_hash,
                        full_name_text,
                        account_user_role,
                        created_employee_id,
                        site_id,
                        target_user_id,
                    ),
                    stage="employees.create.users_update_without_must_change",
                )
        else:
            new_user_id = str(uuid.uuid4())
            if user_has_must_change_password:
                exec_checked(
                    cur,
                    """
                    INSERT INTO arls_users (
                        id, tenant_id, username, password_hash, full_name, role, is_active,
                        employee_id, site_id, must_change_password, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, timezone('utc', now()), timezone('utc', now()))
                    """,
                    (
                        new_user_id,
                        tenant_id,
                        account_username,
                        account_password_hash,
                        full_name_text,
                        account_user_role,
                        created_employee_id,
                        site_id,
                        account_must_change_password,
                    ),
                    stage="employees.create.users_insert_with_must_change",
                )
            else:
                exec_checked(
                    cur,
                    """
                    INSERT INTO arls_users (
                        id, tenant_id, username, password_hash, full_name, role, is_active,
                        employee_id, site_id, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, timezone('utc', now()), timezone('utc', now()))
                    """,
                    (
                        new_user_id,
                        tenant_id,
                        account_username,
                        account_password_hash,
                        full_name_text,
                        account_user_role,
                        created_employee_id,
                        site_id,
                    ),
                    stage="employees.create.users_insert_without_must_change",
                )

    created_payload = {
        **created,
        "user_role": account_user_role,
        "soc_login_id": resolved_soc_login_id,
    }
    _post_employee_sync_to_soc(
        tenant_code=str(tenant.get("tenant_code") or ""),
        site_code=resolved_site_code,
        employee_uuid=employee_uuid,
        employee_code=str(created_payload.get("employee_code") or ""),
        full_name=str(created_payload.get("full_name") or full_name_text or ""),
        phone=created_payload.get("phone"),
        username=account_username,
        user_role=created_payload.get("user_role"),
        birth_date=created_payload.get("birth_date"),
        leave_date=created_payload.get("leave_date"),
        hire_date=created_payload.get("hire_date"),
        address=created_payload.get("address"),
        guard_training_cert_no=created_payload.get("guard_training_cert_no"),
        management_no_str=created_payload.get("management_no_str"),
        note=created_payload.get("note"),
        roster_docx_attachment_id=created_payload.get("roster_docx_attachment_id"),
        photo_attachment_id=created_payload.get("photo_attachment_id"),
        soc_login_id=resolved_soc_login_id,
        soc_temp_password=account_initial_password,
        soc_role=normalized_soc_role,
    )
    return EmployeeOut(
        **{
            **created_payload,
            "tenant_id": tenant.get("id"),
            "tenant_code": str(tenant.get("tenant_code") or ""),
            "tenant_name": str(tenant.get("tenant_name") or ""),
        }
    )


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if normalize_role(user["role"]) not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = tenant["id"]

    normalized_soc_role = _normalize_soc_role(payload.soc_role, required=False)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_code, sequence_no, full_name, phone, site_id,
                   management_no_str, birth_date, address, hire_date, leave_date,
                   guard_training_cert_no, note, roster_docx_attachment_id, photo_attachment_id,
                   soc_login_id, soc_role
            FROM employees
            WHERE id = %s
              AND tenant_id = %s
            LIMIT 1
            """,
            (str(employee_id), tenant_id),
        )
        current = cur.fetchone()
        if not current:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "EMPLOYEE_NOT_FOUND", "employee not found")

        _assert_branch_manager_site_scope(user, current["site_id"])

        cur.execute(
            """
            SELECT s.site_code, c.company_code
            FROM sites s
            JOIN companies c ON c.id = s.company_id
            WHERE s.id = %s
            LIMIT 1
            """,
            (current["site_id"],),
        )
        site_company = cur.fetchone()
        if not site_company:
            _raise_api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL", "site/company not found")

        management_no_value = _normalize_optional_text(payload.management_no_str)
        resolved_management_no = management_no_value or _normalize_optional_text(current.get("management_no_str"))
        next_employee_code = str(current.get("employee_code") or "").strip()
        if management_no_value:
            next_employee_code = build_employee_code_from_management_no(site_company["site_code"], management_no_value)
            if not next_employee_code:
                _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "management_no_str is invalid")
            cur.execute(
                """
                SELECT 1
                FROM employees
                WHERE tenant_id = %s
                  AND id <> %s
                  AND upper(employee_code) = upper(%s)
                LIMIT 1
                """,
                (tenant_id, str(employee_id), next_employee_code),
            )
            if cur.fetchone():
                _raise_api_error(status.HTTP_409_CONFLICT, "EMPLOYEE_CODE_CONFLICT", "employee_code already exists")

        resolved_address = (
            _normalize_optional_text(payload.address)
            if payload.address is not None
            else _normalize_optional_text(current.get("address"))
        )
        resolved_leave_date = payload.leave_date if payload.leave_date is not None else current.get("leave_date")
        resolved_training_cert_no = (
            _normalize_optional_text(payload.guard_training_cert_no)
            if payload.guard_training_cert_no is not None
            else _normalize_optional_text(current.get("guard_training_cert_no"))
        )
        resolved_note = _normalize_optional_text(payload.note) if payload.note is not None else _normalize_optional_text(current.get("note"))
        resolved_soc_login_id = (
            _normalize_optional_text(payload.soc_login_id)
            if payload.soc_login_id is not None
            else _normalize_optional_text(current.get("soc_login_id"))
        )
        resolved_roster_docx_attachment_id = (
            _normalize_optional_text(payload.roster_docx_attachment_id)
            if payload.roster_docx_attachment_id is not None
            else _normalize_optional_text(current.get("roster_docx_attachment_id"))
        )
        resolved_photo_attachment_id = (
            _normalize_optional_text(payload.photo_attachment_id)
            if payload.photo_attachment_id is not None
            else _normalize_optional_text(current.get("photo_attachment_id"))
        )

        cur.execute(
            """
            UPDATE employees
            SET employee_code = %s,
                management_no_str = %s,
                full_name = %s,
                phone = %s,
                birth_date = %s,
                address = %s,
                hire_date = %s,
                leave_date = %s,
                guard_training_cert_no = %s,
                note = %s,
                roster_docx_attachment_id = %s,
                photo_attachment_id = %s,
                soc_login_id = %s,
                soc_role = %s
            WHERE id = %s
              AND tenant_id = %s
            RETURNING id, employee_code, sequence_no, full_name, phone, site_id, management_no_str,
                      birth_date, address, hire_date, leave_date, guard_training_cert_no, note,
                      roster_docx_attachment_id, photo_attachment_id, soc_login_id, soc_role
            """,
            (
                next_employee_code,
                resolved_management_no,
                payload.full_name,
                payload.phone,
                payload.birth_date,
                resolved_address,
                payload.hire_date,
                resolved_leave_date,
                resolved_training_cert_no,
                resolved_note,
                resolved_roster_docx_attachment_id,
                resolved_photo_attachment_id,
                resolved_soc_login_id,
                normalized_soc_role,
                str(employee_id),
                tenant_id,
            ),
        )
        updated = cur.fetchone()

        cur.execute(
            """
            SELECT id, role
            FROM arls_users
            WHERE tenant_id = %s
              AND employee_id = %s
              AND is_active = TRUE
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
            """,
            (tenant_id, employee_id),
        )
        user_row = cur.fetchone()

    return EmployeeOut(
        id=updated["id"],
        tenant_id=tenant.get("id"),
        tenant_code=str(tenant.get("tenant_code") or ""),
        tenant_name=str(tenant.get("tenant_name") or ""),
        employee_code=updated["employee_code"],
        sequence_no=updated.get("sequence_no"),
        full_name=updated["full_name"],
        phone=updated["phone"],
        site_code=site_company["site_code"],
        company_code=site_company["company_code"],
        user_id=user_row["id"] if user_row else None,
        user_role=normalize_user_role(user_row["role"]) if user_row and user_row.get("role") else None,
        management_no_str=updated.get("management_no_str"),
        birth_date=updated.get("birth_date"),
        address=updated.get("address"),
        hire_date=updated.get("hire_date"),
        leave_date=updated.get("leave_date"),
        guard_training_cert_no=updated.get("guard_training_cert_no"),
        note=updated.get("note"),
        roster_docx_attachment_id=updated.get("roster_docx_attachment_id"),
        photo_attachment_id=updated.get("photo_attachment_id"),
        soc_login_id=updated.get("soc_login_id"),
        soc_role=updated.get("soc_role"),
    )


@router.delete("/bulk-delete")
def bulk_delete_employees_by_site(
    site_code: str = Query(..., min_length=1, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    normalized_site_code = str(site_code or "").strip()
    if not normalized_site_code or normalized_site_code.lower() == "all":
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "site_code is required")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = tenant["id"]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, site_code
            FROM sites
            WHERE tenant_id = %s
              AND upper(site_code) = upper(%s)
            LIMIT 1
            """,
            (tenant_id, normalized_site_code),
        )
        site_row = cur.fetchone()
        if not site_row:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "SITE_NOT_FOUND", "site not found")
        _assert_branch_manager_site_scope(user, site_row["id"])

        cur.execute(
            """
            UPDATE arls_users
            SET employee_id = NULL,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND employee_id IN (
                  SELECT id
                  FROM employees
                  WHERE tenant_id = %s
                    AND site_id = %s
              )
            """,
            (tenant_id, tenant_id, site_row["id"]),
        )
        try:
            cur.execute(
                """
                DELETE FROM employees
                WHERE tenant_id = %s
                  AND site_id = %s
                """,
                (tenant_id, site_row["id"]),
            )
            deleted_count = int(cur.rowcount or 0)
        except ForeignKeyViolation:
            _raise_api_error(
                status.HTTP_409_CONFLICT,
                "EMPLOYEE_HAS_REFERENCES",
                "employee has references",
            )
        _reset_site_sequence_if_empty(conn, tenant_id, site_row["id"])

    return {
        "success": True,
        "site_code": str(site_row.get("site_code") or "").strip(),
        "deleted": deleted_count,
    }


@router.delete("/{employee_id}")
def delete_employee(
    employee_id: uuid.UUID,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if normalize_role(user["role"]) not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = tenant["id"]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_code, site_id
            FROM employees
            WHERE id = %s
              AND tenant_id = %s
            LIMIT 1
            """,
            (str(employee_id), tenant_id),
        )
        target = cur.fetchone()
        if not target:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "EMPLOYEE_NOT_FOUND", "employee not found")
        _assert_branch_manager_site_scope(user, target["site_id"])

        cur.execute(
            """
            UPDATE arls_users
            SET employee_id = NULL,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND employee_id = %s
            """,
            (tenant_id, str(employee_id)),
        )
        try:
            cur.execute(
                """
                DELETE FROM employees
                WHERE id = %s
                  AND tenant_id = %s
                """,
                (str(employee_id), tenant_id),
            )
        except ForeignKeyViolation:
            _raise_api_error(
                status.HTTP_409_CONFLICT,
                "EMPLOYEE_HAS_REFERENCES",
                "employee has references",
            )
        _reset_site_sequence_if_empty(conn, tenant_id, target["site_id"])

    return {"success": True, "employee_code": target["employee_code"]}
