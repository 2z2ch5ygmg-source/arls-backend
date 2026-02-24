from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import AttendanceRequestCreate, AttendanceRequestOut, AttendanceRequestReview
from ...services.closing_overtime import apply_closing_overtime_from_checkout
from ...utils.permissions import (
    ROLE_BRANCH_MANAGER,
    can_post_attendance,
    can_review_attendance_request,
    is_super_admin,
)

router = APIRouter(
    prefix="/attendance/requests",
    tags=["attendance-requests"],
    dependencies=[Depends(apply_rate_limit)],
)

ALLOWED_REQUEST_STATUSES = {"pending", "approved", "rejected", "cancelled"}
SITE_SCOPED_REVIEW_ROLES = {ROLE_BRANCH_MANAGER}


def _parse_status_filter_values(raw_value: str | None, *, default: list[str] | None = None) -> list[str]:
    raw = str(raw_value or "").strip().lower()
    if not raw:
        return list(default or [])
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not values:
        return list(default or [])
    invalid = [item for item in values if item not in ALLOWED_REQUEST_STATUSES]
    if invalid:
        raise HTTPException(status_code=400, detail="invalid status")
    deduped: list[str] = []
    for item in values:
        if item in deduped:
            continue
        deduped.append(item)
    return deduped


def _lookup_employee(conn, tenant_id, employee_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_code, site_id
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


def _lookup_site(conn, tenant_id, site_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, site_code, site_name, latitude, longitude, radius_meters
            FROM sites
            WHERE tenant_id = %s AND site_code = %s
            """,
            (tenant_id, site_code),
        )
        return cur.fetchone()


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


def _row_to_out(row) -> AttendanceRequestOut:
    return AttendanceRequestOut(
        id=row["id"],
        tenant_code=row["tenant_code"],
        employee_code=row["employee_code"],
        employee_name=row.get("employee_name"),
        site_code=row["site_code"],
        site_name=row["site_name"],
        site_latitude=float(row["site_latitude"]),
        site_longitude=float(row["site_longitude"]),
        request_type=row["request_type"],
        reason_code=row["reason_code"],
        reason_detail=row["reason_detail"],
        requested_at=row["requested_at"],
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        accuracy_meters=float(row["accuracy_meters"]),
        distance_meters=float(row["distance_meters"]),
        radius_meters=float(row["radius_meters"]),
        device_info=row["device_info"],
        photo_names=list(row["photo_names"] or []),
        status=row["status"],
        review_note=row["review_note"],
        reviewed_at=row["reviewed_at"],
        reviewed_by_username=row["reviewed_by_username"],
        created_at=row["created_at"],
    )


def _fetch_request_out(conn, request_id, tenant_id=None, for_update: bool = False):
    with conn.cursor() as cur:
        clauses = ["ar.id = %s"]
        params: list = [request_id]
        if tenant_id is not None:
            clauses.append("ar.tenant_id = %s")
            params.append(tenant_id)

        sql = f"""
            SELECT ar.id, t.tenant_code, e.employee_code, e.full_name AS employee_name, s.site_code, s.site_name,
                   s.latitude AS site_latitude, s.longitude AS site_longitude,
                   ar.request_type, ar.reason_code, ar.reason_detail, ar.requested_at,
                   ar.latitude, ar.longitude, ar.accuracy_meters, ar.distance_meters, ar.radius_meters,
                   ar.device_info, ar.photo_names, ar.status, ar.review_note, ar.reviewed_at,
                   reviewer.username AS reviewed_by_username, ar.created_at, ar.employee_id, ar.site_id, ar.tenant_id
            FROM attendance_requests ar
            JOIN tenants t ON t.id = ar.tenant_id
            JOIN employees e ON e.id = ar.employee_id
            JOIN sites s ON s.id = ar.site_id
            LEFT JOIN arls_users reviewer ON reviewer.id = ar.reviewed_by
            WHERE {" AND ".join(clauses)}
        """
        if for_update:
            sql += " FOR UPDATE"
        cur.execute(sql, tuple(params))
        return cur.fetchone()


@router.post("", response_model=AttendanceRequestOut)
def create_attendance_request(
    payload: AttendanceRequestCreate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_post_attendance(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    if payload.request_type != "check_in":
        raise HTTPException(status_code=400, detail="only check_in request is supported")

    tenant = _resolve_target_tenant(conn, user, payload.tenant_code)
    tenant_id = tenant["id"]

    employee = _lookup_employee(conn, tenant_id, payload.employee_code)
    if not employee:
        raise HTTPException(status_code=404, detail="employee not found")

    if user.get("employee_id") and str(user["employee_id"]) != str(employee["id"]) and not is_super_admin(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="employee mismatch")

    site = _lookup_site(conn, tenant_id, payload.site_code)
    if not site:
        raise HTTPException(status_code=404, detail="site not found")

    if payload.distance_meters <= payload.radius_meters and payload.accuracy_meters <= payload.radius_meters:
        raise HTTPException(status_code=400, detail="within radius, use regular check-in")

    photo_names = [name.strip() for name in payload.photo_names if str(name or "").strip()][:3]
    request_id = uuid.uuid4()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO attendance_requests (
                id, tenant_id, employee_id, site_id, request_type, reason_code, reason_detail,
                requested_at, latitude, longitude, accuracy_meters, distance_meters, radius_meters,
                device_info, photo_names, status, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
            """,
            (
                request_id,
                tenant_id,
                employee["id"],
                site["id"],
                payload.request_type,
                payload.reason_code,
                payload.reason_detail,
                payload.requested_at,
                payload.latitude,
                payload.longitude,
                payload.accuracy_meters,
                payload.distance_meters,
                payload.radius_meters,
                payload.device_info,
                photo_names,
                user["id"],
            ),
        )

    row = _fetch_request_out(conn, request_id, tenant_id)
    if not row:
        raise HTTPException(status_code=500, detail="failed to create request")
    return _row_to_out(row)


@router.get("/mine", response_model=list[AttendanceRequestOut])
def list_my_attendance_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=30, ge=1, le=200),
    employee_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if status_filter and status_filter not in ALLOWED_REQUEST_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    clauses = ["ar.tenant_id = %s"]
    params: list = [user["tenant_id"]]

    if user.get("employee_id"):
        clauses.append("ar.employee_id = %s")
        params.append(user["employee_id"])
    elif employee_code:
        clauses.append("e.employee_code = %s")
        params.append(employee_code)

    if status_filter:
        clauses.append("ar.status = %s")
        params.append(status_filter)

    params.append(limit)

    sql = f"""
        SELECT ar.id, t.tenant_code, e.employee_code, e.full_name AS employee_name, s.site_code, s.site_name,
               s.latitude AS site_latitude, s.longitude AS site_longitude,
               ar.request_type, ar.reason_code, ar.reason_detail, ar.requested_at,
               ar.latitude, ar.longitude, ar.accuracy_meters, ar.distance_meters, ar.radius_meters,
               ar.device_info, ar.photo_names, ar.status, ar.review_note, ar.reviewed_at,
               reviewer.username AS reviewed_by_username, ar.created_at
        FROM attendance_requests ar
        JOIN tenants t ON t.id = ar.tenant_id
        JOIN employees e ON e.id = ar.employee_id
        JOIN sites s ON s.id = ar.site_id
        LEFT JOIN arls_users reviewer ON reviewer.id = ar.reviewed_by
        WHERE {' AND '.join(clauses)}
        ORDER BY ar.created_at DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_out(row) for row in rows]


@router.get("/pending", response_model=list[AttendanceRequestOut])
def list_pending_attendance_requests(
    limit: int = Query(default=100, ge=1, le=300),
    site_code: str | None = Query(default=None),
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_review_attendance_request(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    clauses = ["ar.status = 'pending'"]
    params: list = []
    requested_tenant_code = str(tenant_code or "").strip().upper()
    if not is_super_admin(user["role"]):
        own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
        if requested_tenant_code and requested_tenant_code != own_tenant_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant mismatch")
        clauses.append("ar.tenant_id = %s")
        params.append(user["tenant_id"])
    elif requested_tenant_code:
        clauses.append("t.tenant_code = %s")
        params.append(requested_tenant_code)

    if user["role"] in SITE_SCOPED_REVIEW_ROLES:
        scoped_site_id = _resolve_user_scope_site_id(conn, user)
        if not scoped_site_id:
            raise HTTPException(status_code=403, detail="site scope is not configured")
        clauses.append("ar.site_id = %s")
        params.append(scoped_site_id)
    if site_code:
        clauses.append("s.site_code = %s")
        params.append(site_code)
    params.append(limit)

    sql = f"""
        SELECT ar.id, t.tenant_code, e.employee_code, e.full_name AS employee_name, s.site_code, s.site_name,
               s.latitude AS site_latitude, s.longitude AS site_longitude,
               ar.request_type, ar.reason_code, ar.reason_detail, ar.requested_at,
               ar.latitude, ar.longitude, ar.accuracy_meters, ar.distance_meters, ar.radius_meters,
               ar.device_info, ar.photo_names, ar.status, ar.review_note, ar.reviewed_at,
               reviewer.username AS reviewed_by_username, ar.created_at
        FROM attendance_requests ar
        JOIN tenants t ON t.id = ar.tenant_id
        JOIN employees e ON e.id = ar.employee_id
        JOIN sites s ON s.id = ar.site_id
        LEFT JOIN arls_users reviewer ON reviewer.id = ar.reviewed_by
        WHERE {' AND '.join(clauses)}
        ORDER BY ar.requested_at DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_out(row) for row in rows]


@router.get("/review-queue", response_model=list[AttendanceRequestOut])
def list_review_queue_attendance_requests(
    status_filter: str | None = Query(default="pending", alias="status"),
    limit: int = Query(default=150, ge=1, le=400),
    site_code: str | None = Query(default=None),
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_review_attendance_request(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    statuses = _parse_status_filter_values(status_filter, default=["pending"])

    clauses: list[str] = ["ar.status = ANY(%s)"]
    params: list = [statuses]

    requested_tenant_code = str(tenant_code or "").strip().upper()
    if not is_super_admin(user["role"]):
        own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
        if requested_tenant_code and requested_tenant_code != own_tenant_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant mismatch")
        clauses.append("ar.tenant_id = %s")
        params.append(user["tenant_id"])
    elif requested_tenant_code:
        clauses.append("t.tenant_code = %s")
        params.append(requested_tenant_code)

    if user["role"] in SITE_SCOPED_REVIEW_ROLES:
        scoped_site_id = _resolve_user_scope_site_id(conn, user)
        if not scoped_site_id:
            raise HTTPException(status_code=403, detail="site scope is not configured")
        clauses.append("ar.site_id = %s")
        params.append(scoped_site_id)

    if site_code:
        clauses.append("s.site_code = %s")
        params.append(site_code)

    params.append(limit)

    sql = f"""
        SELECT ar.id, t.tenant_code, e.employee_code, e.full_name AS employee_name, s.site_code, s.site_name,
               s.latitude AS site_latitude, s.longitude AS site_longitude,
               ar.request_type, ar.reason_code, ar.reason_detail, ar.requested_at,
               ar.latitude, ar.longitude, ar.accuracy_meters, ar.distance_meters, ar.radius_meters,
               ar.device_info, ar.photo_names, ar.status, ar.review_note, ar.reviewed_at,
               reviewer.username AS reviewed_by_username, ar.created_at
        FROM attendance_requests ar
        JOIN tenants t ON t.id = ar.tenant_id
        JOIN employees e ON e.id = ar.employee_id
        JOIN sites s ON s.id = ar.site_id
        LEFT JOIN arls_users reviewer ON reviewer.id = ar.reviewed_by
        WHERE {' AND '.join(clauses)}
        ORDER BY
          CASE
            WHEN ar.status = 'pending' THEN 0
            WHEN ar.status = 'approved' THEN 1
            WHEN ar.status = 'rejected' THEN 2
            ELSE 3
          END,
          COALESCE(ar.reviewed_at, ar.requested_at) DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    return [_row_to_out(row) for row in rows]


@router.post("/{request_id}/cancel", response_model=AttendanceRequestOut)
def cancel_attendance_request(
    request_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_scope = None if is_super_admin(user["role"]) else user["tenant_id"]
    row = _fetch_request_out(conn, request_id, tenant_scope, for_update=True)
    if not row:
        raise HTTPException(status_code=404, detail="request not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="request is not pending")

    is_owner = bool(user.get("employee_id")) and str(user["employee_id"]) == str(row["employee_id"])
    can_admin_cancel = can_review_attendance_request(user["role"]) or is_super_admin(user["role"])
    if can_admin_cancel and user["role"] in SITE_SCOPED_REVIEW_ROLES:
        scoped_site_id = _resolve_user_scope_site_id(conn, user)
        if not scoped_site_id or str(row["site_id"]) != str(scoped_site_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if not is_owner and not can_admin_cancel:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE attendance_requests
            SET status = 'cancelled',
                cancelled_at = timezone('utc', now()),
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (request_id,),
        )

    updated = _fetch_request_out(conn, request_id, tenant_scope)
    if not updated:
        raise HTTPException(status_code=500, detail="request update failed")
    return _row_to_out(updated)


@router.post("/{request_id}/review", response_model=AttendanceRequestOut)
def review_attendance_request(
    request_id: uuid.UUID,
    payload: AttendanceRequestReview,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_review_attendance_request(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    tenant_scope = None if is_super_admin(user["role"]) else user["tenant_id"]
    row = _fetch_request_out(conn, request_id, tenant_scope, for_update=True)
    if not row:
        raise HTTPException(status_code=404, detail="request not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="request is not pending")
    if user["role"] in SITE_SCOPED_REVIEW_ROLES:
        scoped_site_id = _resolve_user_scope_site_id(conn, user)
        if not scoped_site_id or str(row["site_id"]) != str(scoped_site_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    approved_attendance_id = None
    with conn.cursor() as cur:
        if payload.status == "approved":
            cur.execute(
                """
                SELECT id
                FROM attendance_records
                WHERE tenant_id = %s
                  AND employee_id = %s
                  AND site_id = %s
                  AND event_type = %s
                  AND event_at >= %s::date
                  AND event_at < (%s::date + interval '1 day')
                LIMIT 1
                """,
                (
                    user["tenant_id"],
                    row["employee_id"],
                    row["site_id"],
                    row["request_type"],
                    row["requested_at"],
                    row["requested_at"],
                ),
            )
            existing = cur.fetchone()
            if existing:
                approved_attendance_id = existing["id"]
            else:
                new_attendance_id = uuid.uuid4()
                cur.execute(
                    """
                    INSERT INTO attendance_records (
                        id, tenant_id, employee_id, site_id, event_type, event_at,
                        latitude, longitude, distance_meters, is_within_radius
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        new_attendance_id,
                        user["tenant_id"],
                        row["employee_id"],
                        row["site_id"],
                        row["request_type"],
                        row["requested_at"],
                        row["latitude"],
                        row["longitude"],
                        row["distance_meters"],
                        row["distance_meters"] <= row["radius_meters"],
                    ),
                )
                approved_attendance_id = new_attendance_id

            if row["request_type"] == "check_out" and approved_attendance_id:
                apply_closing_overtime_from_checkout(
                    conn,
                    tenant_id=row["tenant_id"],
                    site_id=row["site_id"],
                    employee_id=row["employee_id"],
                    checkout_at=row["requested_at"],
                    source_event_uid=f"attendance_request:{request_id}",
                    source_label="ATTENDANCE_REQUEST_APPROVAL",
                )

        cur.execute(
            """
            UPDATE attendance_requests
            SET status = %s,
                review_note = %s,
                reviewed_by = %s,
                reviewed_at = timezone('utc', now()),
                approved_attendance_id = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (
                payload.status,
                payload.review_note,
                user["id"],
                approved_attendance_id,
                request_id,
            ),
        )

    updated = _fetch_request_out(conn, request_id, tenant_scope)
    if not updated:
        raise HTTPException(status_code=500, detail="request update failed")
    return _row_to_out(updated)
