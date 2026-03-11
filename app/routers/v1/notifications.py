from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import InAppNotificationListOut, InAppNotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(apply_rate_limit)])


@router.get("/in-app", response_model=InAppNotificationListOut)
def list_in_app_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_id = str(user.get("tenant_id") or "").strip()
    user_id = str(user.get("id") or "").strip()
    if not tenant_id or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   message,
                   category,
                   dedupe_key,
                   payload_json,
                   created_at,
                   read_at
            FROM in_app_notifications
            WHERE tenant_id = %s
              AND user_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (tenant_id, user_id, int(limit)),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM in_app_notifications
            WHERE tenant_id = %s
              AND user_id = %s
              AND read_at IS NULL
            """,
            (tenant_id, user_id),
        )
        unread_row = cur.fetchone() or {}

    return InAppNotificationListOut(
        items=[
            InAppNotificationOut(
                id=row["id"],
                message=str(row.get("message") or "").strip() or "-",
                type=str(row.get("category") or "info").strip() or "info",
                read=row.get("read_at") is not None,
                created_at=row["created_at"],
                read_at=row.get("read_at"),
                payload=dict(row.get("payload_json") or {}),
                dedupe_key=str(row.get("dedupe_key") or "").strip() or None,
            )
            for row in rows
        ],
        unread_count=max(int(unread_row.get("cnt") or 0), 0),
    )


@router.post("/in-app/{notification_id}/read")
def mark_in_app_notification_read(
    notification_id: str,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_id = str(user.get("tenant_id") or "").strip()
    user_id = str(user.get("id") or "").strip()
    if not tenant_id or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE in_app_notifications
            SET read_at = COALESCE(read_at, timezone('utc', now()))
            WHERE id = %s
              AND tenant_id = %s
              AND user_id = %s
            """,
            (notification_id, tenant_id, user_id),
        )
        updated = int(cur.rowcount or 0)
    return {"ok": updated == 1}


@router.post("/in-app/read-all")
def mark_all_in_app_notifications_read(
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_id = str(user.get("tenant_id") or "").strip()
    user_id = str(user.get("id") or "").strip()
    if not tenant_id or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE in_app_notifications
            SET read_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND user_id = %s
              AND read_at IS NULL
            """,
            (tenant_id, user_id),
        )
        updated = max(int(cur.rowcount or 0), 0)
    return {"ok": True, "updated": updated}
