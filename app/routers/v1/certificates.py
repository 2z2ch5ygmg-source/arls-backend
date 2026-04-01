from __future__ import annotations

from io import BytesIO
from pathlib import Path
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from ...db import get_connection
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services import certificates_mail as certificates_mail_service
from ...services.approval_engine import create_certificate_request_approval_adapter, record_approval_action
from ...services.certificates_mail import (
    CERTIFICATE_DAILY_LIMIT,
    EMPLOYMENT_CERTIFICATE_TYPE_KEY,
    backfill_legacy_employment_certificate_requests,
    list_admin_certificate_requests,
    list_certificate_issue_jobs,
    list_certificate_requests,
    list_certificate_types,
    retry_certificate_issue_job,
)
from ...services.employment_certificate import (
    build_issue_number,
    build_purpose_label,
    generate_employment_certificate_pdf,
    issue_employment_certificate_pdf_from_docx,
    send_certificate_mail,
)
from ...utils.permissions import ROLE_DEVELOPER, ROLE_HQ_ADMIN, normalize_user_role
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/certificates", tags=["certificates"], dependencies=[Depends(apply_rate_limit)])
TZ_KST = timezone(timedelta(hours=9))


class CertificateRequestCreate(BaseModel):
    type_key: str = Field(min_length=1, max_length=64)
    purpose_code: str = Field(min_length=1, max_length=32)
    purpose_text: str | None = Field(default=None, max_length=120)
    submit_to: str = Field(min_length=1, max_length=120)
    copy_count: int = Field(default=1, ge=1, le=20)
    include_address: bool = False
    include_phone: bool = False

    @field_validator("type_key", mode="before")
    @classmethod
    def _normalize_type_key(cls, value: str | None) -> str:
        return str(value or "").strip().lower()

    @field_validator("purpose_code", mode="before")
    @classmethod
    def _normalize_purpose_code(cls, value: str | None) -> str:
        normalized = str(value or "").strip().upper()
        if normalized not in {"BANK", "GOV", "CARD", "OTHER"}:
            raise ValueError("purpose_code is invalid")
        return normalized

    @field_validator("purpose_text", "submit_to", mode="before")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class CertificateRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=2, max_length=400)

    @field_validator("rejection_reason", mode="before")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("rejection_reason is required")
        return normalized


def _raise_api_error(status_code: int, code: str, message: str, *, fields: dict[str, str] | None = None) -> None:
    detail: dict[str, Any] = {"error": code, "message": message}
    if fields:
        detail["fields"] = fields
    raise HTTPException(status_code=status_code, detail=detail)


def _ensure_admin(user: dict) -> None:
    if normalize_user_role(user.get("role")) not in {ROLE_DEVELOPER, ROLE_HQ_ADMIN}:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "증명서 관리 화면은 관리자만 조회할 수 있습니다.")


def _ensure_employee_context(user: dict) -> str:
    employee_id = str(user.get("employee_id") or "").strip()
    if not employee_id:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "EMPLOYEE_CONTEXT_REQUIRED", "직원 계정 연결이 필요합니다.")
    return employee_id


def _today_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(TZ_KST)


def _template_key_for_recipient(recipient_role: str) -> str:
    normalized = str(recipient_role or "").strip().lower()
    return "certificate_issued_company" if normalized == "company" else "certificate_issued_employee"


def _normalize_bytes(value: Any) -> bytes:
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, bytes):
        return value
    return bytes(value or b"")


def _fetch_certificate_request_row(conn, *, tenant_id: str, request_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT cr.id,
                   cr.tenant_id,
                   cr.company_id,
                   cr.employee_id,
                   cr.requester_user_id,
                   cr.approval_document_id,
                   cr.certificate_type_id,
                   cr.status,
                   cr.purpose_code,
                   cr.purpose_text,
                   cr.submit_to,
                   cr.copy_count,
                   cr.include_address,
                   cr.include_phone,
                   cr.rejection_reason,
                   cr.generation_error,
                   cr.mail_error,
                   cr.mail_company_sent_at,
                   cr.mail_employee_sent_at,
                   cr.requested_at,
                   cr.issued_at,
                   cr.issue_number,
                   cr.legacy_source_type,
                   cr.legacy_source_id,
                   cr.template_id,
                   cr.template_version,
                   cr.template_file_path,
                   cr.file_name,
                   cr.file_mime_type,
                   cr.file_bytes,
                   ct.type_key,
                   ct.display_name AS certificate_type_name,
                   ct.requires_approval,
                   ct.auto_mail_enabled,
                   ct.meta_json,
                   e.full_name AS employee_name,
                   e.hire_date,
                   e.leave_date,
                   COALESCE(e.employment_status, 'active') AS employment_status,
                   e.loa_start_date,
                   e.loa_end_date,
                   COALESCE(e.address, '') AS employee_address,
                   COALESCE(e.phone, '') AS employee_phone,
                   COALESCE(e.soc_role, '') AS employee_role,
                   e.birth_date,
                   COALESCE(s.site_name, '본사') AS org_name,
                   COALESCE(s.id::text, '') AS resolved_site_id,
                   COALESCE(s.site_code, '') AS site_code,
                   t.tenant_code,
                   t.tenant_name,
                   COALESCE(c.company_name, t.tenant_name) AS company_name,
                   COALESCE(c.company_code, '') AS company_code,
                   COALESCE(tp.ceo_name, '') AS ceo_name,
                   COALESCE(tp.biz_reg_no, '') AS biz_reg_no,
                   COALESCE(tp.address, '') AS company_address,
                   COALESCE(tp.phone, '') AS company_phone,
                   COALESCE(tp.email, '') AS company_email,
                   COALESCE(tp.seal_attachment_id, '') AS seal_attachment_id,
                   COALESCE(ad.status, '') AS approval_status,
                   COALESCE(job.id::text, '') AS issue_job_id,
                   COALESCE(job.job_state, '') AS issue_job_state,
                   COALESCE(job.last_error, '') AS issue_job_error
            FROM certificate_requests cr
            JOIN certificate_types ct ON ct.id = cr.certificate_type_id
            JOIN employees e ON e.id = cr.employee_id
            JOIN tenants t ON t.id = cr.tenant_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = COALESCE(cr.company_id, e.company_id, s.company_id)
            LEFT JOIN tenant_profiles tp ON tp.tenant_id = cr.tenant_id
            LEFT JOIN approval_documents ad ON ad.id = cr.approval_document_id
            LEFT JOIN LATERAL (
                SELECT id, job_state, last_error
                FROM certificate_issue_jobs
                WHERE certificate_request_id = cr.id
                ORDER BY created_at DESC
                LIMIT 1
            ) job ON TRUE
            WHERE cr.tenant_id = %s
              AND cr.id = %s
            LIMIT 1
            """,
            (tenant_id, request_id),
        )
        return cur.fetchone()


def _public_certificate_request_item(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row.get("id") or ""),
        "tenant_id": str(row.get("tenant_id") or ""),
        "company_id": str(row.get("company_id") or ""),
        "employee_id": str(row.get("employee_id") or ""),
        "requester_user_id": str(row.get("requester_user_id") or ""),
        "approval_document_id": str(row.get("approval_document_id") or ""),
        "certificate_type_id": str(row.get("certificate_type_id") or ""),
        "status": row.get("status"),
        "purpose_code": row.get("purpose_code"),
        "purpose_text": row.get("purpose_text"),
        "submit_to": row.get("submit_to"),
        "copy_count": int(row.get("copy_count") or 1),
        "include_address": bool(row.get("include_address")),
        "include_phone": bool(row.get("include_phone")),
        "rejection_reason": row.get("rejection_reason"),
        "generation_error": row.get("generation_error"),
        "mail_error": row.get("mail_error"),
        "mail_company_sent_at": row.get("mail_company_sent_at"),
        "mail_employee_sent_at": row.get("mail_employee_sent_at"),
        "requested_at": row.get("requested_at"),
        "issued_at": row.get("issued_at"),
        "issue_number": row.get("issue_number"),
        "file_ready": bool(row.get("file_bytes")),
        "legacy_source_type": row.get("legacy_source_type"),
        "legacy_source_id": row.get("legacy_source_id"),
        "template_id": str(row.get("template_id") or ""),
        "template_version": row.get("template_version"),
        "template_file_path": row.get("template_file_path"),
        "file_name": row.get("file_name"),
        "file_mime_type": row.get("file_mime_type"),
        "certificate_type_key": row.get("type_key"),
        "certificate_type_name": row.get("certificate_type_name"),
        "requires_approval": bool(row.get("requires_approval")),
        "auto_mail_enabled": bool(row.get("auto_mail_enabled")),
        "approval_status": row.get("approval_status") or None,
        "issue_job_id": row.get("issue_job_id") or None,
        "issue_job_state": row.get("issue_job_state") or None,
        "issue_job_error": row.get("issue_job_error") or None,
        "employee_name": row.get("employee_name"),
    }


def _build_certificate_context(conn, *, request_row: dict[str, Any], issue_number: str, issued_at: datetime) -> dict[str, Any]:
    from . import hr_documents

    hire_date = hr_documents._format_date(request_row.get("hire_date"))
    leave_date = hr_documents._resolve_termination_date(
        conn,
        tenant_id=str(request_row.get("tenant_id") or "").strip(),
        employee_id=str(request_row.get("employee_id") or "").strip(),
        fallback_value=request_row.get("leave_date"),
    )
    loa_start_date = hr_documents._format_date(request_row.get("loa_start_date"))
    loa_end_date = hr_documents._format_date(request_row.get("loa_end_date"))

    if hire_date and leave_date:
        employment_period = f"{hire_date} ~ {leave_date}"
    elif hire_date and loa_end_date:
        employment_period = f"{hire_date} ~ {loa_end_date}"
    elif hire_date:
        employment_period = f"{hire_date} ~"
    else:
        employment_period = ""

    issue_date_local = issued_at.astimezone(TZ_KST)
    purpose_label = build_purpose_label(str(request_row.get("purpose_code") or ""), request_row.get("purpose_text"))
    certificate_type_name = str(request_row.get("certificate_type_name") or "증명서").strip() or "증명서"

    return {
        "certificate_type_name": certificate_type_name,
        "company_name": str(request_row.get("company_name") or request_row.get("tenant_name") or "").strip(),
        "biz_reg_no": str(request_row.get("biz_reg_no") or "").strip(),
        "ceo_name": str(request_row.get("ceo_name") or "").strip(),
        "company_phone": str(request_row.get("company_phone") or "").strip(),
        "company_email": str(request_row.get("company_email") or "").strip(),
        "company_address": str(request_row.get("company_address") or "").strip(),
        "employee_name": str(request_row.get("employee_name") or "").strip(),
        "birth_date": hr_documents._format_date(request_row.get("birth_date")),
        "resident_no_masked": hr_documents._resolve_masked_resident_no(
            conn,
            tenant_id=str(request_row.get("tenant_id") or "").strip(),
            employee_id=str(request_row.get("employee_id") or "").strip(),
        ),
        "employee_address": str(request_row.get("employee_address") or "").strip() if bool(request_row.get("include_address")) else "",
        "employee_phone": str(request_row.get("employee_phone") or "").strip() if bool(request_row.get("include_phone")) else "",
        "org_name": str(request_row.get("org_name") or "본사").strip(),
        "position_name": str(request_row.get("employee_role") or "").strip(),
        "hire_date": hire_date,
        "leave_date": leave_date,
        "termination_date": leave_date,
        "loa_start_date": loa_start_date,
        "loa_end_date": loa_end_date,
        "return_due_date": loa_end_date,
        "employment_period": employment_period,
        "issue_number": issue_number,
        "issue_date": issue_date_local.strftime("%Y-%m-%d"),
        "issue_date_long": issue_date_local.strftime("%Y년 %m월 %d일"),
        "purpose_label": purpose_label,
        "submit_to": str(request_row.get("submit_to") or "").strip(),
        "copy_count": int(request_row.get("copy_count") or 1),
    }


def _process_certificate_issue_job(certificate_request_id: str) -> None:
    from . import hr_documents

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tenant_id
                    FROM certificate_requests
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (certificate_request_id,),
                )
                tenant_row = cur.fetchone() or {}
            tenant_id = str(tenant_row.get("tenant_id") or "").strip()
            if not tenant_id:
                return
            request_row = _fetch_certificate_request_row(conn, tenant_id=tenant_id, request_id=certificate_request_id)
            if not request_row:
                return
            if str(request_row.get("status") or "").strip().lower() != "generating":
                return

            certificates_mail_service.upsert_certificate_issue_job(
                conn,
                tenant_id=tenant_id,
                certificate_request_id=certificate_request_id,
                job_state="processing",
                increment_attempts=True,
                payload_extra={
                    "stage": "pdf_generation",
                    "type_key": request_row.get("type_key"),
                },
            )

            issued_at = datetime.now(timezone.utc)
            issue_number = build_issue_number(certificate_request_id, issued_at=issued_at)
            context = _build_certificate_context(conn, request_row=request_row, issue_number=issue_number, issued_at=issued_at)

            active_template, template_source = hr_documents._fetch_document_template_for_issue(
                conn,
                tenant_id=tenant_id,
                company_id=str(request_row.get("company_id") or "").strip() or None,
                document_type=str(request_row.get("type_key") or "").strip(),
            )
            template_docx_bytes = b""
            use_html_fallback = False
            fallback_html = ""
            if active_template:
                template_docx_bytes = _normalize_bytes((active_template or {}).get("file_bytes"))
                template_ext = str((active_template or {}).get("file_ext") or "").strip().lower()
                if template_ext != ".docx" or not template_docx_bytes:
                    active_template = None
                    template_source = "not_found"

            if not active_template:
                legacy_template, legacy_source = hr_documents._fetch_legacy_html_template_for_issue(
                    conn,
                    tenant_id=tenant_id,
                    company_id=str(request_row.get("company_id") or "").strip() or None,
                    document_type=str(request_row.get("type_key") or "").strip(),
                )
                fallback_html = str((legacy_template or {}).get("template_html") or "").strip()
                if legacy_template and fallback_html:
                    active_template = legacy_template
                    template_source = legacy_source
                    use_html_fallback = True
                else:
                    raise RuntimeError("ACTIVE_DOCX_TEMPLATE_NOT_FOUND")

            seal_image_bytes = hr_documents._load_seal_image_bytes(
                conn,
                tenant_id=tenant_id,
                seal_attachment_id=str(request_row.get("seal_attachment_id") or "").strip() or None,
            )
            if use_html_fallback:
                pdf_bytes = generate_employment_certificate_pdf(context, template_html=fallback_html)
            else:
                pdf_bytes = issue_employment_certificate_pdf_from_docx(
                    template_docx_bytes,
                    context,
                    seal_image_bytes=seal_image_bytes,
                )

            file_name = f"{str(request_row.get('type_key') or 'certificate').strip()}_{issue_number}.pdf"
            file_path = f"documents/certificates/{str(request_row.get('tenant_code') or 'tenant').strip().lower()}/{certificate_request_id}.pdf"
            final_status = "issued"

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE certificate_requests
                    SET status = %s,
                        issue_number = %s,
                        issued_at = CASE WHEN %s = 'issued' THEN timezone('utc', now()) ELSE issued_at END,
                        generation_error = NULL,
                        mail_error = %s,
                        mail_company_sent_at = %s,
                        mail_employee_sent_at = %s,
                        template_id = %s,
                        template_version = %s,
                        template_file_path = %s,
                        file_name = %s,
                        file_mime_type = 'application/pdf',
                        file_bytes = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (
                        final_status,
                        issue_number,
                        final_status,
                        None,
                        None,
                        None,
                        (active_template or {}).get("id"),
                        (active_template or {}).get("version"),
                        (active_template or {}).get("file_path"),
                        file_name,
                        pdf_bytes,
                        certificate_request_id,
                    ),
                )

            certificates_mail_service.upsert_certificate_issue_job(
                conn,
                tenant_id=tenant_id,
                certificate_request_id=certificate_request_id,
                job_state="completed",
                last_error=None,
                payload_extra={
                    "stage": final_status,
                    "issue_number": issue_number,
                    "template_source": template_source,
                    "template_mode": "html_fallback" if use_html_fallback else "docx",
                    "seal_attached": bool(seal_image_bytes),
                    "download_ready": True,
                    "autofill_field_count": sum(1 for value in context.values() if str(value or "").strip()),
                },
            )
    except Exception as exc:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT tenant_id
                        FROM certificate_requests
                        WHERE id = %s
                        LIMIT 1
                        """,
                        (certificate_request_id,),
                    )
                    row = cur.fetchone() or {}
                tenant_id = str(row.get("tenant_id") or "").strip()
                if tenant_id:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE certificate_requests
                            SET status = 'failed',
                                generation_error = %s,
                                updated_at = timezone('utc', now())
                            WHERE id = %s
                            """,
                            (str(exc)[:2000], certificate_request_id),
                        )
                    certificates_mail_service.upsert_certificate_issue_job(
                        conn,
                        tenant_id=tenant_id,
                        certificate_request_id=certificate_request_id,
                        job_state="failed",
                        last_error=str(exc),
                        payload_extra={"stage": "failed"},
                    )
        except Exception:
            pass


@router.get("/types")
def get_certificate_types(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    employee_id = str(user.get("employee_id") or "").strip() or None
    return {
        "items": list_certificate_types(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            employee_id=employee_id,
        )
    }


@router.post("/requests")
def post_certificate_request(
    payload: CertificateRequestCreate,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    employee_id = _ensure_employee_context(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()
    certificates_mail_service.ensure_certificate_mail_foundation(conn, tenant_id=tenant_id, actor_user_id=str(user.get("id") or "").strip() or None)

    type_row = certificates_mail_service._resolve_certificate_type_row(conn, tenant_id=tenant_id, type_key=payload.type_key)
    if not type_row or not certificates_mail_service._type_is_live(type_row):
        _raise_api_error(status.HTTP_404_NOT_FOUND, "CERTIFICATE_TYPE_NOT_FOUND", "증명서 종류를 찾을 수 없습니다.")
    employee_row = certificates_mail_service._fetch_certificate_employee_row(conn, tenant_id=tenant_id, employee_id=employee_id)
    available, reason = certificates_mail_service._certificate_type_eligibility(
        type_key=payload.type_key,
        employee_row=employee_row,
        employee_email=None,
        company_archive_email=None,
    )
    if not available:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "CERTIFICATE_REQUEST_UNAVAILABLE", reason or "증명서를 신청할 수 없습니다.")

    from . import hr_documents

    active_template, _ = hr_documents._fetch_document_template_for_issue(
        conn,
        tenant_id=tenant_id,
        company_id=str((employee_row or {}).get("company_id") or "").strip() or None,
        document_type=payload.type_key,
    )
    if not active_template:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "ACTIVE_TEMPLATE_REQUIRED", "활성 템플릿이 필요합니다.")

    today = _today_kst().date()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM certificate_requests
            WHERE tenant_id = %s
              AND employee_id = %s
              AND (requested_at AT TIME ZONE 'Asia/Seoul')::date = %s
            """,
            (tenant_id, employee_id, today),
        )
        today_count = int((cur.fetchone() or {}).get("cnt") or 0)
    if today_count >= CERTIFICATE_DAILY_LIMIT:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "DAILY_LIMIT_REACHED", "일일 발급 요청 한도를 초과했습니다.")

    request_id = str(uuid.uuid4())
    approval_required = bool(type_row.get("requires_approval"))
    initial_status = "requested" if approval_required else "generating"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO certificate_requests (
                id,
                tenant_id,
                company_id,
                certificate_type_id,
                employee_id,
                requester_user_id,
                purpose_code,
                purpose_text,
                submit_to,
                copy_count,
                include_address,
                include_phone,
                status,
                requested_at,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                timezone('utc', now()), timezone('utc', now()), timezone('utc', now())
            )
            """,
            (
                request_id,
                tenant_id,
                (employee_row or {}).get("company_id"),
                type_row.get("id"),
                employee_id,
                str(user.get("id") or "").strip() or None,
                payload.purpose_code,
                payload.purpose_text,
                payload.submit_to,
                payload.copy_count,
                payload.include_address,
                payload.include_phone,
                initial_status,
            ),
        )

    if approval_required:
        approval_detail = create_certificate_request_approval_adapter(
            conn,
            tenant_id=tenant_id,
            document_request_id=request_id,
            employee_id=employee_id,
            company_id=str((employee_row or {}).get("company_id") or "").strip() or None,
            actor_user=user,
            certificate_type_key=payload.type_key,
            certificate_type_name=str(type_row.get("display_name") or "").strip() or None,
            purpose_code=payload.purpose_code,
            purpose_text=payload.purpose_text,
            submit_to=payload.submit_to,
            copy_count=payload.copy_count,
            include_address=payload.include_address,
            include_phone=payload.include_phone,
            site_id=str((employee_row or {}).get("site_id") or "").strip() or None,
            legacy_source_type="certificate_request",
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE certificate_requests
                SET approval_document_id = %s,
                    updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (str((approval_detail or {}).get("id") or "").strip() or None, request_id),
            )
    else:
        certificates_mail_service.upsert_certificate_issue_job(
            conn,
            tenant_id=tenant_id,
            certificate_request_id=request_id,
            job_state="queued",
            payload_extra={"stage": "queued", "type_key": payload.type_key},
        )
        background_tasks.add_task(_process_certificate_issue_job, request_id)

    row = _fetch_certificate_request_row(conn, tenant_id=tenant_id, request_id=request_id)
    return {"item": _public_certificate_request_item(row)}


@router.get("/requests")
def get_my_certificate_requests(
    limit: int = Query(default=100, ge=1, le=300),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    employee_id = _ensure_employee_context(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()
    return {
        "items": list_certificate_requests(
            conn,
            tenant_id=tenant_id,
            employee_id=employee_id,
            requester_user_id=str(user.get("id") or "").strip() or None,
            limit=limit,
        )
    }


@router.get("/requests/{request_id}/download")
def get_certificate_request_download(
    request_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()
    row = _fetch_certificate_request_row(conn, tenant_id=tenant_id, request_id=request_id)
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "CERTIFICATE_REQUEST_NOT_FOUND", "증명서 요청을 찾을 수 없습니다.")

    actor_role = normalize_user_role(user.get("role"))
    if actor_role not in {ROLE_DEVELOPER, ROLE_HQ_ADMIN} and str(row.get("employee_id") or "").strip() != str(user.get("employee_id") or "").strip():
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "다운로드 권한이 없습니다.")

    file_bytes = _normalize_bytes(row.get("file_bytes"))
    if not file_bytes:
        _raise_api_error(status.HTTP_409_CONFLICT, "CERTIFICATE_NOT_READY", "아직 발급 파일이 준비되지 않았습니다.")
    file_name = str(row.get("file_name") or f"{row.get('type_key') or 'certificate'}.pdf").strip()
    return Response(
        content=file_bytes,
        media_type=str(row.get("file_mime_type") or "application/pdf"),
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/admin/requests")
def get_admin_certificate_requests(
    limit: int = Query(default=100, ge=1, le=300),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=120),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {
        "items": list_admin_certificate_requests(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            limit=limit,
            status_filter=status_filter,
            query=q,
        )
    }


@router.post("/admin/requests/{request_id}/approve")
def post_approve_certificate_request(
    request_id: str,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()
    row = _fetch_certificate_request_row(conn, tenant_id=tenant_id, request_id=request_id)
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "CERTIFICATE_REQUEST_NOT_FOUND", "증명서 요청을 찾을 수 없습니다.")
    if not str(row.get("approval_document_id") or "").strip():
        _raise_api_error(status.HTTP_409_CONFLICT, "APPROVAL_NOT_REQUIRED", "승인이 필요하지 않은 요청입니다.")

    approval_detail = record_approval_action(
        conn,
        tenant_id=tenant_id,
        document_id=str(row.get("approval_document_id") or "").strip(),
        actor_user_id=str(user.get("id") or "").strip(),
        actor_role=str(user.get("role") or "").strip() or None,
        action_type="approve",
    )
    approval_status = str((approval_detail or {}).get("status") or "").strip().lower()
    if approval_status == "approved":
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE certificate_requests
                SET status = 'generating',
                    rejection_reason = NULL,
                    updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (request_id,),
            )
        certificates_mail_service.upsert_certificate_issue_job(
            conn,
            tenant_id=tenant_id,
            certificate_request_id=request_id,
            job_state="queued",
            payload_extra={"stage": "queued_after_approval", "approval_document_id": row.get("approval_document_id")},
        )
        background_tasks.add_task(_process_certificate_issue_job, request_id)
    return {"item": _public_certificate_request_item(_fetch_certificate_request_row(conn, tenant_id=tenant_id, request_id=request_id))}


@router.post("/admin/requests/{request_id}/reject")
def post_reject_certificate_request(
    request_id: str,
    payload: CertificateRejectRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()
    row = _fetch_certificate_request_row(conn, tenant_id=tenant_id, request_id=request_id)
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "CERTIFICATE_REQUEST_NOT_FOUND", "증명서 요청을 찾을 수 없습니다.")
    if not str(row.get("approval_document_id") or "").strip():
        _raise_api_error(status.HTTP_409_CONFLICT, "APPROVAL_NOT_REQUIRED", "승인이 필요하지 않은 요청입니다.")

    record_approval_action(
        conn,
        tenant_id=tenant_id,
        document_id=str(row.get("approval_document_id") or "").strip(),
        actor_user_id=str(user.get("id") or "").strip(),
        actor_role=str(user.get("role") or "").strip() or None,
        action_type="reject",
        comment_text=payload.rejection_reason,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE certificate_requests
            SET status = 'rejected',
                rejection_reason = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (payload.rejection_reason, request_id),
        )
    certificates_mail_service.upsert_certificate_issue_job(
        conn,
        tenant_id=tenant_id,
        certificate_request_id=request_id,
        job_state="cancelled",
        last_error=payload.rejection_reason,
        payload_extra={"stage": "rejected"},
    )
    return {"item": _public_certificate_request_item(_fetch_certificate_request_row(conn, tenant_id=tenant_id, request_id=request_id))}


@router.get("/admin/issue-jobs")
def get_certificate_issue_jobs(
    limit: int = Query(default=100, ge=1, le=300),
    state_filter: str | None = Query(default=None, alias="state"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {
        "items": list_certificate_issue_jobs(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            limit=limit,
            state_filter=state_filter,
        )
    }


@router.post("/admin/backfill-legacy")
def post_certificate_backfill_legacy(
    limit: int = Query(default=200, ge=1, le=1000),
    status_filter: str | None = Query(default=None, alias="status"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return backfill_legacy_employment_certificate_requests(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        actor_user_id=str(user.get("id") or "").strip() or None,
        actor_role=str(user.get("role") or "").strip() or None,
        limit=limit,
        status_filter=status_filter,
    )


@router.post("/admin/issue-jobs/{issue_job_id}/retry")
def post_retry_certificate_issue_job(
    issue_job_id: str,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()
    result = retry_certificate_issue_job(
        conn,
        tenant_id=tenant_id,
        issue_job_id=issue_job_id,
        actor_user_id=str(user.get("id") or "").strip() or None,
        actor_role=str(user.get("role") or "").strip() or None,
    )
    if str(result.get("legacy_source_type") or "").strip() == "employment_certificate_request" and str(result.get("legacy_source_id") or "").strip():
        from .hr_documents import _process_employment_certificate_issue_job

        background_tasks.add_task(_process_employment_certificate_issue_job, str(result["legacy_source_id"]))
    elif str(result.get("certificate_request_id") or "").strip():
        background_tasks.add_task(_process_certificate_issue_job, str(result["certificate_request_id"]))
    return result


@router.get("/admin/templates")
def get_certificate_templates(
    type_key: str = Query(default=EMPLOYMENT_CERTIFICATE_TYPE_KEY, alias="type_key"),
    company_id: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()
    with conn.cursor() as cur:
        if company_id:
            cur.execute(
                """
                SELECT id, company_id, document_type, version, file_path, file_ext, is_active, created_by, created_at
                FROM document_templates
                WHERE tenant_id = %s
                  AND document_type = %s
                  AND company_id = %s::uuid
                ORDER BY version DESC
                """,
                (tenant_id, str(type_key or "").strip().lower(), company_id),
            )
        else:
            cur.execute(
                """
                SELECT id, company_id, document_type, version, file_path, file_ext, is_active, created_by, created_at
                FROM document_templates
                WHERE tenant_id = %s
                  AND document_type = %s
                ORDER BY version DESC
                """,
                (tenant_id, str(type_key or "").strip().lower()),
            )
        rows = cur.fetchall() or []
    return {
        "items": [
            {
                "id": str(row.get("id") or ""),
                "company_id": str(row.get("company_id") or ""),
                "document_type": row.get("document_type"),
                "version": int(row.get("version") or 0),
                "file_path": row.get("file_path"),
                "file_ext": row.get("file_ext"),
                "is_active": bool(row.get("is_active")),
                "created_by": str(row.get("created_by") or ""),
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]
    }


@router.post("/admin/templates/upload")
async def post_certificate_template_upload(
    type_key: str = Form(default=EMPLOYMENT_CERTIFICATE_TYPE_KEY),
    company_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()

    from . import hr_documents
    normalized_document_type = hr_documents._normalize_document_type(type_key)
    scoped_company_id = hr_documents._validate_company_scope(conn, tenant_id=tenant_id, company_id=company_id)

    original_name = str(file.filename or "").strip() or "template.docx"
    extension = Path(original_name).suffix.lower()
    if extension not in hr_documents.ALLOWED_TEMPLATE_EXTENSIONS:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "입력값을 확인해주세요.", fields={"file": "docx_only"})

    raw_bytes = await file.read()
    if not raw_bytes:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "입력값을 확인해주세요.", fields={"file": "empty"})
    if len(raw_bytes) > hr_documents.MAX_TEMPLATE_UPLOAD_BYTES:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "입력값을 확인해주세요.", fields={"file": "max_2mb"})
    try:
        from docx import Document as _DocxDocument

        _DocxDocument(BytesIO(raw_bytes))
    except Exception:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "입력값을 확인해주세요.", fields={"file": "docx_parse_failed"})

    template_id = uuid.uuid4()
    actor_id = user.get("id")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(MAX(version), 0) + 1 AS next_version
            FROM document_templates
            WHERE tenant_id = %s
              AND document_type = %s
              AND (
                    (%s::uuid IS NULL AND company_id IS NULL)
                 OR (company_id = %s::uuid)
              )
            """,
            (tenant_id, normalized_document_type, scoped_company_id, scoped_company_id),
        )
        row = cur.fetchone() or {}
        next_version = int(row.get("next_version") or 1)
        next_file_path = f"templates/{normalized_document_type}/v{next_version}{extension}"

        cur.execute(
            """
            UPDATE document_templates
            SET is_active = FALSE
            WHERE tenant_id = %s
              AND document_type = %s
              AND (
                    (%s::uuid IS NULL AND company_id IS NULL)
                 OR (company_id = %s::uuid)
              )
              AND is_active = TRUE
            """,
            (tenant_id, normalized_document_type, scoped_company_id, scoped_company_id),
        )
        cur.execute(
            """
            INSERT INTO document_templates (
                id,
                tenant_id,
                company_id,
                document_type,
                version,
                file_path,
                template_html,
                file_bytes,
                file_mime_type,
                file_ext,
                is_active,
                created_by,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, timezone('utc', now()))
            RETURNING id, company_id, document_type, version, file_path, file_ext, is_active, created_by, created_at
            """,
            (
                template_id,
                tenant_id,
                scoped_company_id,
                normalized_document_type,
                next_version,
                next_file_path,
                "",
                raw_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                extension,
                actor_id,
            ),
        )
        inserted = cur.fetchone() or {}

    return {
        "item": {
            "id": str(inserted.get("id") or template_id),
            "company_id": str(inserted.get("company_id") or scoped_company_id or ""),
            "document_type": inserted.get("document_type") or normalized_document_type,
            "version": int(inserted.get("version") or next_version),
            "file_path": inserted.get("file_path") or next_file_path,
            "file_ext": inserted.get("file_ext") or extension,
            "is_active": bool(inserted.get("is_active", True)),
            "created_by": str(inserted.get("created_by") or actor_id or ""),
            "created_at": inserted.get("created_at"),
        }
    }
