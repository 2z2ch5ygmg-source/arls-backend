from __future__ import annotations

import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from psycopg import errors as pg_errors

from ...deps import get_db_conn, get_current_user, apply_rate_limit
from ...schemas import TenantCreate, TenantOut, TenantProfileOut, TenantProfileUpdate, TenantUpdate
from ...utils.permissions import (
    ROLE_BRANCH_MANAGER,
    ROLE_DEVELOPER,
    ROLE_DEV,
    ROLE_HQ_ADMIN,
    can_manage_tenant,
    normalize_role,
    user_role_sql_variants,
)
from ...utils.tenant_context import (
    TENANT_ID_PATTERN,
    build_tenant_identifier_candidates,
    canonical_tenant_identifier,
)

router = APIRouter(prefix="/tenants", tags=["tenants"], dependencies=[Depends(apply_rate_limit)])
logger = logging.getLogger(__name__)
_ALLOWED_SEAL_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg"}
_ALLOWED_SEAL_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_MAX_SEAL_IMAGE_BYTES = 2 * 1024 * 1024


def _normalize_tenant_code(value: str | None) -> str:
    return canonical_tenant_identifier(value)


def _slugify_tenant_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "company"


def _resolve_default_tenant_code(base_code: str) -> str:
    normalized = _normalize_tenant_code(base_code) or "company"
    if not TENANT_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_INPUT",
                "message": "입력값을 확인해주세요.",
                "fields": {"tenant_name": "invalid"},
            },
        )
    return normalized


def _release_deleted_tenant_code(conn, tenant_code: str) -> int:
    normalized_code = _normalize_tenant_code(tenant_code)
    if not normalized_code:
        return 0
    candidate_aliases = list(build_tenant_identifier_candidates(normalized_code)) or [normalized_code]
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tenants
            SET tenant_code = CONCAT(
                    COALESCE(NULLIF(trim(tenant_code), ''), 'tenant'),
                    '__deleted__',
                    substring(replace(id::text, '-', '') from 1 for 8)
                ),
                updated_at = timezone('utc', now())
            WHERE lower(trim(tenant_code)) = ANY(%s::text[])
              AND COALESCE(is_deleted, FALSE) = TRUE
            RETURNING id
            """,
            (candidate_aliases,),
        )
        rows = cur.fetchall()
    return len(rows)


def _normalize_profile_text(value: str | None, *, max_length: int = 255) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _get_tenant_or_404(conn, tenant_id: uuid.UUID):
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
    if not row or bool(row.get("is_deleted")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "회사를 찾을 수 없습니다."},
        )
    return row


def _assert_tenant_profile_access(user: dict, tenant_row: dict) -> None:
    actor_role = normalize_role(user.get("role"))
    if actor_role == ROLE_DEV:
        return
    if actor_role != ROLE_BRANCH_MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "접근 권한이 없습니다."},
        )
    if str(user.get("tenant_id") or "") != str(tenant_row.get("id") or ""):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "본인 회사 정보만 수정할 수 있습니다."},
        )


def _build_tenant_profile_out(tenant_id: uuid.UUID, row: dict | None = None) -> TenantProfileOut:
    profile_row = row or {}
    seal_attachment_id = _normalize_profile_text(str(profile_row.get("seal_attachment_id") or ""), max_length=128)
    return TenantProfileOut(
        tenant_id=tenant_id,
        ceo_name=_normalize_profile_text(profile_row.get("ceo_name"), max_length=120),
        biz_reg_no=_normalize_profile_text(profile_row.get("biz_reg_no"), max_length=64),
        address=_normalize_profile_text(profile_row.get("address"), max_length=255),
        phone=_normalize_profile_text(profile_row.get("phone"), max_length=64),
        email=_normalize_profile_text(profile_row.get("email"), max_length=120),
        seal_attachment_id=seal_attachment_id,
        updated_at=profile_row.get("updated_at"),
    )


@router.get("", response_model=list[TenantOut])
def list_tenants(
    include_inactive: bool = Query(default=False),
    include_deleted: bool = Query(default=False),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_tenant(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    where_clauses: list[str] = []
    if not include_deleted:
        where_clauses.append("COALESCE(is_deleted, FALSE) = FALSE")
    if not include_inactive:
        where_clauses.append("COALESCE(is_active, TRUE) = TRUE")
    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, tenant_code, tenant_name,
                   COALESCE(is_active, TRUE) AS is_active,
                   COALESCE(is_deleted, FALSE) AS is_deleted
            FROM tenants
            {where}
            ORDER BY tenant_name
            """
        )
        rows = [TenantOut(**r) for r in cur.fetchall()]
    return rows


@router.post("", response_model=TenantOut)
def create_tenant(payload: TenantCreate, conn=Depends(get_db_conn), user=Depends(get_current_user)):
    if not can_manage_tenant(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    tenant_name = str(payload.tenant_name or "").strip()
    if not tenant_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_INPUT",
                "message": "입력값을 확인해주세요.",
                "fields": {"tenant_name": "required"},
                "detail": "tenant_name is required",
            },
        )

    tenant_code_input_raw = str(payload.tenant_code or "").strip().lower()
    tenant_code_auto = _resolve_default_tenant_code(_slugify_tenant_name(tenant_name))
    released_count = 0
    if tenant_code_input_raw:
        if not TENANT_ID_PATTERN.fullmatch(tenant_code_input_raw):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_INPUT",
                    "message": "입력값을 확인해주세요.",
                    "fields": {"tenant_code": "invalid"},
                },
            )
        tenant_code_normalized = tenant_code_input_raw
        released_count = _release_deleted_tenant_code(conn, tenant_code_normalized)
    else:
        released_count = _release_deleted_tenant_code(conn, tenant_code_auto)
        tenant_code_normalized = tenant_code_auto

    if released_count > 0:
        logger.info(
            "create_tenant released deleted tenant_code aliases: candidate=%s released=%s",
            tenant_code_normalized,
            released_count,
        )

    tenant_id = uuid.uuid4()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tenant_code,
                       COALESCE(is_active, TRUE) AS is_active,
                       COALESCE(is_deleted, FALSE) AS is_deleted
                FROM tenants
                WHERE lower(trim(tenant_name)) = lower(trim(%s))
                  AND COALESCE(is_deleted, FALSE) = FALSE
                LIMIT 1
                """,
                (tenant_name,),
            )
            existing_by_name = cur.fetchone()
            if existing_by_name:
                logger.warning(
                    "create_tenant name conflict: tenant_name=%s existing_id=%s existing_code=%s existing_active=%s existing_deleted=%s",
                    tenant_name,
                    existing_by_name.get("id"),
                    existing_by_name.get("tenant_code"),
                    existing_by_name.get("is_active"),
                    existing_by_name.get("is_deleted"),
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "TENANT_NAME_EXISTS",
                        "message": "이미 존재하는 테넌트명입니다.",
                        "detail": {
                            "tenant_id": str(existing_by_name.get("id") or ""),
                            "tenant_code": str(existing_by_name.get("tenant_code") or ""),
                            "is_active": bool(existing_by_name.get("is_active", True)),
                            "is_deleted": bool(existing_by_name.get("is_deleted", False)),
                        },
                    },
                )

            candidate_aliases = list(build_tenant_identifier_candidates(tenant_code_normalized)) or [tenant_code_normalized]
            cur.execute(
                """
                SELECT id,
                       tenant_code,
                       COALESCE(is_active, TRUE) AS is_active,
                       COALESCE(is_deleted, FALSE) AS is_deleted
                FROM tenants
                WHERE lower(trim(tenant_code)) = ANY(%s::text[])
                  AND COALESCE(is_deleted, FALSE) = FALSE
                LIMIT 1
                """,
                (candidate_aliases,),
            )
            existing = cur.fetchone()
            if existing:
                logger.warning(
                    "create_tenant conflict: requested=%s normalized=%s existing_id=%s existing_code=%s existing_active=%s existing_deleted=%s",
                    payload.tenant_code,
                    tenant_code_normalized,
                    existing.get("id"),
                    existing.get("tenant_code"),
                    existing.get("is_active"),
                    existing.get("is_deleted"),
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "TENANT_EXISTS",
                        "message": "이미 존재하는 회사명입니다.",
                        "detail": {
                            "tenant_id": str(existing.get("id") or ""),
                            "tenant_code": str(existing.get("tenant_code") or ""),
                            "is_active": bool(existing.get("is_active", True)),
                            "is_deleted": bool(existing.get("is_deleted", False)),
                        },
                    },
                )

            cur.execute(
                """
                INSERT INTO tenants (id, tenant_code, tenant_name, is_active, updated_at)
                VALUES (%s, %s, %s, %s, timezone('utc', now()))
                RETURNING id, tenant_code, tenant_name, COALESCE(is_active, TRUE) AS is_active
                """,
                (tenant_id, tenant_code_normalized, tenant_name, payload.is_active),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("failed to create tenant")
    except HTTPException:
        raise
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "TENANT_EXISTS", "message": "이미 존재하는 테넌트 정보입니다."},
        ) from exc
    except Exception as exc:
        logger.exception("create_tenant failed: tenant_code=%s", tenant_code_normalized, exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL", "message": "서버 오류입니다. 잠시 후 다시 시도해주세요."},
        ) from exc
    return TenantOut(**row)


@router.put("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_tenant(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if str(user.get("tenant_id")) == str(tenant_id) and not payload.is_active:
        raise HTTPException(status_code=400, detail="cannot deactivate current tenant")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tenants
            SET tenant_name = %s,
                is_active = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            RETURNING id, tenant_code, tenant_name, COALESCE(is_active, TRUE) AS is_active
            """,
            (payload.tenant_name, payload.is_active, tenant_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="tenant not found")
    return TenantOut(**row)


@router.get("/{tenant_id}/profile", response_model=TenantProfileOut)
def get_tenant_profile(
    tenant_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_row = _get_tenant_or_404(conn, tenant_id)
    _assert_tenant_profile_access(user, tenant_row)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tenant_id, ceo_name, biz_reg_no, address, phone, email, seal_attachment_id, updated_at
            FROM tenant_profiles
            WHERE tenant_id = %s
            LIMIT 1
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
    return _build_tenant_profile_out(tenant_id, row)


@router.put("/{tenant_id}/profile", response_model=TenantProfileOut)
def upsert_tenant_profile(
    tenant_id: uuid.UUID,
    payload: TenantProfileUpdate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_row = _get_tenant_or_404(conn, tenant_id)
    _assert_tenant_profile_access(user, tenant_row)

    resolved_ceo_name = _normalize_profile_text(payload.ceo_name, max_length=120)
    resolved_biz_reg_no = _normalize_profile_text(payload.biz_reg_no, max_length=64)
    resolved_address = _normalize_profile_text(payload.address, max_length=255)
    resolved_phone = _normalize_profile_text(payload.phone, max_length=64)
    resolved_email = _normalize_profile_text(payload.email, max_length=120)
    resolved_seal_attachment_id = _normalize_profile_text(payload.seal_attachment_id, max_length=128)

    with conn.cursor() as cur:
        if resolved_seal_attachment_id:
            cur.execute(
                """
                SELECT id
                FROM tenant_profile_attachments
                WHERE tenant_id = %s
                  AND id::text = %s
                LIMIT 1
                """,
                (tenant_id, resolved_seal_attachment_id),
            )
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "VALIDATION_ERROR",
                        "message": "입력값을 확인해주세요.",
                        "fields": {"seal_attachment_id": "not_found"},
                    },
                )

        cur.execute(
            """
            INSERT INTO tenant_profiles (
                tenant_id, ceo_name, biz_reg_no, address, phone, email, seal_attachment_id, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (tenant_id)
            DO UPDATE SET
                ceo_name = EXCLUDED.ceo_name,
                biz_reg_no = EXCLUDED.biz_reg_no,
                address = EXCLUDED.address,
                phone = EXCLUDED.phone,
                email = EXCLUDED.email,
                seal_attachment_id = EXCLUDED.seal_attachment_id,
                updated_at = timezone('utc', now())
            RETURNING tenant_id, ceo_name, biz_reg_no, address, phone, email, seal_attachment_id, updated_at
            """,
            (
                tenant_id,
                resolved_ceo_name,
                resolved_biz_reg_no,
                resolved_address,
                resolved_phone,
                resolved_email,
                resolved_seal_attachment_id,
            ),
        )
        row = cur.fetchone()
    return _build_tenant_profile_out(tenant_id, row)


@router.post("/{tenant_id}/profile/seal")
async def upload_tenant_profile_seal(
    tenant_id: uuid.UUID,
    file: UploadFile = File(...),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_row = _get_tenant_or_404(conn, tenant_id)
    _assert_tenant_profile_access(user, tenant_row)

    file_name = _normalize_profile_text(file.filename or "tenant-seal.png", max_length=255) or "tenant-seal.png"
    lower_name = file_name.lower()
    ext = ""
    if "." in lower_name:
        ext = f".{lower_name.rsplit('.', 1)[-1]}"
    mime_type = _normalize_profile_text(file.content_type or "", max_length=64) or "application/octet-stream"

    if ext not in _ALLOWED_SEAL_IMAGE_EXTENSIONS and mime_type not in _ALLOWED_SEAL_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": "입력값을 확인해주세요.",
                "fields": {"seal_image": "invalid_format"},
            },
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": "입력값을 확인해주세요.",
                "fields": {"seal_image": "empty"},
            },
        )
    if len(raw_bytes) > _MAX_SEAL_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VALIDATION_ERROR",
                "message": "입력값을 확인해주세요.",
                "fields": {"seal_image": "max_2mb"},
            },
        )

    normalized_mime = mime_type.lower()
    if normalized_mime == "image/jpg":
        normalized_mime = "image/jpeg"
    if normalized_mime not in {"image/png", "image/jpeg"}:
        normalized_mime = "image/png" if ext == ".png" else "image/jpeg"

    attachment_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tenant_profile_attachments (
                id, tenant_id, file_name, mime_type, file_bytes, created_at
            )
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            """,
            (attachment_id, tenant_id, file_name, normalized_mime, raw_bytes),
        )
        cur.execute(
            """
            INSERT INTO tenant_profiles (tenant_id, seal_attachment_id, updated_at)
            VALUES (%s, %s, timezone('utc', now()))
            ON CONFLICT (tenant_id)
            DO UPDATE SET
                seal_attachment_id = EXCLUDED.seal_attachment_id,
                updated_at = timezone('utc', now())
            """,
            (tenant_id, str(attachment_id)),
        )

    return {
        "success": True,
        "tenant_id": str(tenant_id),
        "seal_attachment_id": str(attachment_id),
        "file_name": file_name,
        "mime_type": normalized_mime,
    }


@router.get("/{tenant_id}/profile/seal/{attachment_id}")
def download_tenant_profile_seal(
    tenant_id: uuid.UUID,
    attachment_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_row = _get_tenant_or_404(conn, tenant_id)
    _assert_tenant_profile_access(user, tenant_row)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, file_name, mime_type, file_bytes
            FROM tenant_profile_attachments
            WHERE tenant_id = %s
              AND id = %s
            LIMIT 1
            """,
            (tenant_id, attachment_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "도장 이미지를 찾을 수 없습니다."},
        )

    file_name = _normalize_profile_text(row.get("file_name"), max_length=255) or "tenant-seal.png"
    mime_type = _normalize_profile_text(row.get("mime_type"), max_length=64) or "application/octet-stream"
    file_bytes = row.get("file_bytes")
    if isinstance(file_bytes, memoryview):
        payload = file_bytes.tobytes()
    elif isinstance(file_bytes, bytes):
        payload = file_bytes
    else:
        payload = bytes(file_bytes or b"")

    return Response(
        content=payload,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{file_name}"'},
    )


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


def _ensure_can_delete_account(actor: dict) -> str:
    actor_role = normalize_role(actor.get("role"))
    if actor_role not in {ROLE_DEV, ROLE_BRANCH_MANAGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "계정 삭제 권한이 없습니다."},
        )
    return actor_role


def _count_remaining_same_role_users(conn, *, tenant_id: uuid.UUID | None, role: str, exclude_user_id: uuid.UUID) -> int:
    variants = list(user_role_sql_variants(role))
    with conn.cursor() as cur:
        if tenant_id is None:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM arls_users
                WHERE lower(trim(role)) = ANY(%s)
                  AND id <> %s
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """,
                (variants, exclude_user_id),
            )
        else:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM arls_users
                WHERE tenant_id = %s
                  AND lower(trim(role)) = ANY(%s)
                  AND id <> %s
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """,
                (tenant_id, variants, exclude_user_id),
            )
        row = cur.fetchone() or {}
    return int(row.get("total") or 0)


@router.delete("/{tenant_id}/users/{user_id}")
def delete_tenant_user(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _ensure_can_delete_account(user)

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
        tenant_row = cur.fetchone()
    if not tenant_row or tenant_row.get("is_deleted"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "테넌트를 찾을 수 없습니다."},
        )

    if actor_role == ROLE_BRANCH_MANAGER and str(user.get("tenant_id")) != str(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "다른 테넌트 계정은 삭제할 수 없습니다."},
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT au.id, au.tenant_id, au.username, au.role, au.is_active,
                   COALESCE(au.is_deleted, FALSE) AS is_deleted
            FROM arls_users au
            WHERE au.id = %s
              AND au.tenant_id = %s
            LIMIT 1
            """,
            (user_id, tenant_id),
        )
        target_user = cur.fetchone()

    if not target_user or target_user.get("is_deleted"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "USER_NOT_FOUND", "message": "계정을 찾을 수 없습니다."},
        )

    if str(target_user.get("id")) == str(user.get("id")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "SELF_DELETE_FORBIDDEN", "message": "현재 로그인 계정은 삭제할 수 없습니다."},
        )

    target_role = normalize_role(target_user.get("role"))
    if actor_role == ROLE_BRANCH_MANAGER and target_role == ROLE_DEV:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "개발자 계정은 삭제할 수 없습니다."},
        )

    if target_role == ROLE_BRANCH_MANAGER:
        remain = _count_remaining_same_role_users(
            conn,
            tenant_id=tenant_id,
            role=ROLE_HQ_ADMIN,
            exclude_user_id=user_id,
        )
        if remain <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "LAST_MANAGER_DELETE_FORBIDDEN", "message": "마지막 지점관리자 계정은 삭제할 수 없습니다."},
            )

    if target_role == ROLE_DEV:
        remain = _count_remaining_same_role_users(
            conn,
            tenant_id=None,
            role=ROLE_DEVELOPER,
            exclude_user_id=user_id,
        )
        if remain <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "LAST_DEV_DELETE_FORBIDDEN", "message": "마지막 개발자 계정은 삭제할 수 없습니다."},
            )

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET is_deleted = TRUE,
                deleted_at = timezone('utc', now()),
                deleted_by = %s,
                is_active = FALSE,
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND tenant_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            RETURNING id, username
            """,
            (user.get("id"), user_id, tenant_id),
        )
        deleted_row = cur.fetchone()

    if not deleted_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "USER_NOT_FOUND", "message": "계정을 찾을 수 없습니다."},
        )

    _append_integration_audit_log(
        conn,
        tenant_id=tenant_id,
        action_type="user_soft_delete",
        actor_user_id=user.get("id"),
        actor_role=actor_role,
        target_type="user",
        target_id=str(user_id),
        detail={
            "tenant_code": tenant_row.get("tenant_code"),
            "username": deleted_row.get("username"),
            "target_role": target_role,
            "mode": "soft_delete",
        },
    )

    return {
        "ok": True,
        "tenant_id": str(tenant_id),
        "deleted_user_id": str(user_id),
        "username": deleted_row.get("username"),
        "mode": "soft_delete",
    }
