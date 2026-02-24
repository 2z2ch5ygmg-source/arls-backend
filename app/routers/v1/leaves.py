from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import LeaveRequestCreate, LeaveRequestOut, LeaveRequestReview
from ...utils.permissions import (
    ROLE_BRANCH_MANAGER,
    can_request_leave,
    can_review_leave_request,
    is_super_admin,
)

router = APIRouter(prefix="/leaves", tags=["leaves"], dependencies=[Depends(apply_rate_limit)])

ALLOWED_LEAVE_STATUSES = {"pending", "approved", "rejected", "cancelled"}
SITE_SCOPED_REVIEW_ROLES = {ROLE_BRANCH_MANAGER}


def _parse_status_filter_values(raw_value: str | None, *, default: list[str] | None = None) -> list[str]:
    raw = str(raw_value or "").strip().lower()
    if not raw:
        return list(default or [])
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not values:
        return list(default or [])
    invalid = [item for item in values if item not in ALLOWED_LEAVE_STATUSES]
    if invalid:
        raise HTTPException(status_code=400, detail="invalid status")
    deduped: list[str] = []
    for item in values:
        if item in deduped:
            continue
        deduped.append(item)
    return deduped


def _lookup_emp(conn, tenant_id, employee_code):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, site_id, employee_code
            FROM employees
            WHERE tenant_id = %s AND employee_code = %s
            """,
            (tenant_id, employee_code),
        )
        return cur.fetchone()


def _resolve_target_tenant(conn, user, tenant_code: str | None):
    own_tenant_id = user["tenant_id"]
    own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
    requested_tenant_code = str(tenant_code or "").strip().upper()

    if not is_super_admin(user["role"]):
        if requested_tenant_code and requested_tenant_code != own_tenant_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant mismatch")
        return {"id": own_tenant_id, "tenant_code": own_tenant_code}

    if not requested_tenant_code:
        return {"id": own_tenant_id, "tenant_code": own_tenant_code}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code
            FROM tenants
            WHERE tenant_code = %s
              AND COALESCE(is_active, TRUE) = TRUE
            LIMIT 1
            """,
            (requested_tenant_code,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return row


def _resolve_user_scope_site_id(conn, user) -> str | None:
    if user.get("site_id"):
        return str(user["site_id"])
    if user.get("employee_id"):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT site_id
                FROM employees
                WHERE id = %s
                """,
                (user["employee_id"],),
            )
            row = cur.fetchone()
            if row and row.get("site_id"):
                return str(row["site_id"])
    return None


def _normalize_attachment_names(values) -> list[str]:
    normalized: list[str] = []
    for item in (values or []):
        text = str(item or "").strip()
        if not text:
            continue
        # Strip any path segment from browser-provided filenames.
        text = text.replace("\\", "/").split("/")[-1].strip()
        if not text:
            continue
        if len(text) > 120:
            text = text[:120]
        if text in normalized:
            continue
        normalized.append(text)
        if len(normalized) >= 3:
            break
    return normalized


def _row_to_out(row) -> LeaveRequestOut:
    return LeaveRequestOut(
        id=row["id"],
        tenant_code=row["tenant_code"],
        employee_code=row["employee_code"],
        employee_name=row.get("employee_name"),
        site_code=row.get("site_code"),
        site_name=row.get("site_name"),
        leave_type=row["leave_type"],
        half_day_slot=row.get("half_day_slot"),
        start_at=row["start_at"],
        end_at=row["end_at"],
        reason=row["reason"],
        attachment_names=_normalize_attachment_names(row.get("attachment_names")),
        status=row["status"],
        requested_at=row.get("requested_at"),
        reviewed_at=row.get("reviewed_at"),
        review_note=row.get("review_note"),
        reviewed_by_username=row.get("reviewed_by_username"),
    )


def _fetch_leave_out(conn, leave_id, tenant_id=None, for_update: bool = False):
    with conn.cursor() as cur:
        clauses = ["lr.id = %s"]
        params: list = [leave_id]
        if tenant_id is not None:
            clauses.append("lr.tenant_id = %s")
            params.append(tenant_id)

        if for_update:
            cur.execute(
                f"""
                SELECT id
                FROM leave_requests
                WHERE {" AND ".join(clauses)}
                FOR UPDATE
                """,
                tuple(params),
            )
            if not cur.fetchone():
                return None

        sql = f"""
            SELECT lr.id, t.tenant_code, e.employee_code, e.full_name AS employee_name,
                   s.site_code, s.site_name,
                   lr.leave_type, lr.half_day_slot, lr.start_at, lr.end_at, lr.reason, lr.attachment_names, lr.status,
                   lr.requested_at, lr.reviewed_at, lr.review_note,
                   reviewer.username AS reviewed_by_username, lr.tenant_id,
                   lr.employee_id, e.site_id
            FROM leave_requests lr
            JOIN tenants t ON t.id = lr.tenant_id
            JOIN employees e ON e.id = lr.employee_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN arls_users reviewer ON reviewer.id = lr.reviewed_by
            WHERE {" AND ".join(clauses)}
        """
        cur.execute(sql, tuple(params))
        return cur.fetchone()


@router.get("", response_model=list[LeaveRequestOut])
def list_leaves(
    status_filter: str | None = Query(default=None, alias="status"),
    employee_code: str | None = Query(default=None),
    tenant_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if status_filter and status_filter not in ALLOWED_LEAVE_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    clauses: list[str] = []
    params: list = []

    if not is_super_admin(user["role"]):
        clauses.append("lr.tenant_id = %s")
        params.append(user["tenant_id"])
        if tenant_code and tenant_code != user.get("tenant_code"):
            raise HTTPException(status_code=403, detail="tenant mismatch")
    elif tenant_code:
        clauses.append("t.tenant_code = %s")
        params.append(tenant_code)

    if user.get("employee_id"):
        clauses.append("lr.employee_id = %s")
        params.append(user["employee_id"])
    elif employee_code:
        clauses.append("e.employee_code = %s")
        params.append(employee_code)

    if status_filter:
        clauses.append("lr.status = %s")
        params.append(status_filter)

    params.append(limit)
    where_clause = " AND ".join(clauses) if clauses else "TRUE"

    sql = f"""
        SELECT lr.id, t.tenant_code, e.employee_code, e.full_name AS employee_name,
               s.site_code, s.site_name,
               lr.leave_type, lr.half_day_slot, lr.start_at, lr.end_at, lr.reason, lr.attachment_names, lr.status,
               lr.requested_at, lr.reviewed_at, lr.review_note,
               reviewer.username AS reviewed_by_username
        FROM leave_requests lr
        JOIN tenants t ON t.id = lr.tenant_id
        JOIN employees e ON e.id = lr.employee_id
        LEFT JOIN sites s ON s.id = e.site_id
        LEFT JOIN arls_users reviewer ON reviewer.id = lr.reviewed_by
        WHERE {where_clause}
        ORDER BY lr.requested_at DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_out(row) for row in rows]


@router.post("", response_model=LeaveRequestOut)
def create_leave(payload: LeaveRequestCreate, conn=Depends(get_db_conn), user=Depends(get_current_user)):
    if not can_request_leave(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    tenant = _resolve_target_tenant(conn, user, payload.tenant_code)
    tenant_id = tenant["id"]

    emp = _lookup_emp(conn, tenant_id, payload.employee_code)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee not found")

    if user.get("employee_id") and str(user["employee_id"]) != str(emp["id"]) and not is_super_admin(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="employee mismatch")

    attachment_names = _normalize_attachment_names(payload.attachment_names)
    request_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO leave_requests (
                id, tenant_id, employee_id, leave_type, half_day_slot, start_at, end_at, reason, attachment_names, status, requested_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', timezone('utc', now()))
            """,
            (
                request_id,
                tenant_id,
                emp["id"],
                payload.leave_type,
                payload.half_day_slot,
                payload.start_at,
                payload.end_at,
                payload.reason,
                attachment_names,
            ),
        )

    row = _fetch_leave_out(conn, request_id, tenant_id)
    if not row:
        raise HTTPException(status_code=500, detail="failed to create leave")
    return _row_to_out(row)


@router.get("/pending", response_model=list[LeaveRequestOut])
def list_pending_leaves(
    limit: int = Query(default=100, ge=1, le=300),
    site_code: str | None = Query(default=None),
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_review_leave_request(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    clauses = ["lr.status = 'pending'"]
    params: list = []

    if not is_super_admin(user["role"]):
        clauses.append("lr.tenant_id = %s")
        params.append(user["tenant_id"])
        if tenant_code and tenant_code != user.get("tenant_code"):
            raise HTTPException(status_code=403, detail="tenant mismatch")
    elif tenant_code:
        clauses.append("t.tenant_code = %s")
        params.append(tenant_code)

    if user["role"] in SITE_SCOPED_REVIEW_ROLES:
        scoped_site_id = _resolve_user_scope_site_id(conn, user)
        if not scoped_site_id:
            raise HTTPException(status_code=403, detail="site scope is not configured")
        clauses.append("e.site_id = %s")
        params.append(scoped_site_id)

    if site_code:
        clauses.append("s.site_code = %s")
        params.append(site_code)

    params.append(limit)

    sql = f"""
        SELECT lr.id, t.tenant_code, e.employee_code, e.full_name AS employee_name,
               s.site_code, s.site_name,
               lr.leave_type, lr.half_day_slot, lr.start_at, lr.end_at, lr.reason, lr.attachment_names, lr.status,
               lr.requested_at, lr.reviewed_at, lr.review_note,
               reviewer.username AS reviewed_by_username
        FROM leave_requests lr
        JOIN tenants t ON t.id = lr.tenant_id
        JOIN employees e ON e.id = lr.employee_id
        LEFT JOIN sites s ON s.id = e.site_id
        LEFT JOIN arls_users reviewer ON reviewer.id = lr.reviewed_by
        WHERE {' AND '.join(clauses)}
        ORDER BY lr.requested_at DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_out(row) for row in rows]


@router.get("/review-queue", response_model=list[LeaveRequestOut])
def list_review_queue_leaves(
    status_filter: str | None = Query(default="pending", alias="status"),
    limit: int = Query(default=150, ge=1, le=400),
    site_code: str | None = Query(default=None),
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_review_leave_request(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    statuses = _parse_status_filter_values(status_filter, default=["pending"])
    clauses = ["lr.status = ANY(%s)"]
    params: list = [statuses]

    if not is_super_admin(user["role"]):
        clauses.append("lr.tenant_id = %s")
        params.append(user["tenant_id"])
        if tenant_code and tenant_code != user.get("tenant_code"):
            raise HTTPException(status_code=403, detail="tenant mismatch")
    elif tenant_code:
        clauses.append("t.tenant_code = %s")
        params.append(tenant_code)

    if user["role"] in SITE_SCOPED_REVIEW_ROLES:
        scoped_site_id = _resolve_user_scope_site_id(conn, user)
        if not scoped_site_id:
            raise HTTPException(status_code=403, detail="site scope is not configured")
        clauses.append("e.site_id = %s")
        params.append(scoped_site_id)

    if site_code:
        clauses.append("s.site_code = %s")
        params.append(site_code)

    params.append(limit)

    sql = f"""
        SELECT lr.id, t.tenant_code, e.employee_code, e.full_name AS employee_name,
               s.site_code, s.site_name,
               lr.leave_type, lr.half_day_slot, lr.start_at, lr.end_at, lr.reason, lr.attachment_names, lr.status,
               lr.requested_at, lr.reviewed_at, lr.review_note,
               reviewer.username AS reviewed_by_username
        FROM leave_requests lr
        JOIN tenants t ON t.id = lr.tenant_id
        JOIN employees e ON e.id = lr.employee_id
        LEFT JOIN sites s ON s.id = e.site_id
        LEFT JOIN arls_users reviewer ON reviewer.id = lr.reviewed_by
        WHERE {' AND '.join(clauses)}
        ORDER BY
          CASE
            WHEN lr.status = 'pending' THEN 0
            WHEN lr.status = 'approved' THEN 1
            WHEN lr.status = 'rejected' THEN 2
            ELSE 3
          END,
          COALESCE(lr.reviewed_at, lr.requested_at) DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_out(row) for row in rows]


@router.post("/{leave_id}/cancel", response_model=LeaveRequestOut)
def cancel_leave(
    leave_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_scope = None if is_super_admin(user["role"]) else user["tenant_id"]
    row = _fetch_leave_out(conn, leave_id, tenant_scope, for_update=True)
    if not row:
        raise HTTPException(status_code=404, detail="leave request not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="leave request is not pending")

    is_owner = bool(user.get("employee_id")) and str(user["employee_id"]) == str(row["employee_id"])
    can_admin_cancel = can_review_leave_request(user["role"]) or is_super_admin(user["role"])
    if can_admin_cancel and user["role"] in SITE_SCOPED_REVIEW_ROLES:
        scoped_site_id = _resolve_user_scope_site_id(conn, user)
        if not scoped_site_id or str(row["site_id"]) != str(scoped_site_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if not is_owner and not can_admin_cancel:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE leave_requests
            SET status = 'cancelled',
                cancelled_at = timezone('utc', now())
            WHERE id = %s
            """,
            (leave_id,),
        )

    updated = _fetch_leave_out(conn, leave_id, tenant_scope)
    if not updated:
        raise HTTPException(status_code=500, detail="leave request update failed")
    return _row_to_out(updated)


@router.post("/{leave_id}/review", response_model=LeaveRequestOut)
def review_leave(
    leave_id: uuid.UUID,
    payload: LeaveRequestReview,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_review_leave_request(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    tenant_scope = None if is_super_admin(user["role"]) else user["tenant_id"]
    row = _fetch_leave_out(conn, leave_id, tenant_scope, for_update=True)
    if not row:
        raise HTTPException(status_code=404, detail="leave request not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="leave request is not pending")

    if user["role"] in SITE_SCOPED_REVIEW_ROLES:
        scoped_site_id = _resolve_user_scope_site_id(conn, user)
        if not scoped_site_id or str(row["site_id"]) != str(scoped_site_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE leave_requests
            SET status = %s,
                review_note = %s,
                reviewed_by = %s,
                reviewed_at = timezone('utc', now())
            WHERE id = %s
            """,
            (
                payload.status,
                payload.review_note,
                user["id"],
                leave_id,
            ),
        )

    updated = _fetch_leave_out(conn, leave_id, tenant_scope)
    if not updated:
        raise HTTPException(status_code=500, detail="leave request update failed")
    return _row_to_out(updated)
