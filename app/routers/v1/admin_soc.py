from __future__ import annotations

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from ...config import settings
from ...deps import apply_rate_limit, get_db_conn, require_roles
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV
from ...utils.tenant_context import normalize_tenant_identifier, resolve_scoped_tenant
from .sites import _post_site_sync_to_soc

router = APIRouter(
    prefix="/admin/soc",
    tags=["admin-soc"],
    dependencies=[Depends(apply_rate_limit)],
)


def _run_backfill_sites_to_soc(
    *,
    tenant_code: str | None = None,
    conn,
    user,
):
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = scoped_tenant.get("id")
    tenant_code_value = str(scoped_tenant.get("tenant_code") or "").strip()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT site_code, site_name
            FROM sites
            WHERE tenant_id = %s
            ORDER BY site_code
            """,
            (tenant_id,),
        )
        rows = cur.fetchall()

    sent = 0
    failed: list[dict] = []
    for row in rows:
        site_code_value = str(row.get("site_code") or "").strip()
        print(
            f"[HR->SOC] site-sync POST url={settings.soc_site_sync_url} "
            f"tenant={tenant_code_value} site={site_code_value}"
        )
        ok, status_code, reason = _post_site_sync_to_soc(
            tenant_code=tenant_code_value,
            site_code=site_code_value,
            site_name=row.get("site_name"),
            event_type="SITE_UPDATED",
        )
        print(f"[HR->SOC] site-sync status={status_code} body={(reason or '')[:120]}")
        if ok:
            sent += 1
            continue

        fail_reason = str(reason or "").strip()
        if not fail_reason:
            if status_code is None:
                fail_reason = "sync failed"
            else:
                fail_reason = f"http_{status_code}"
        failed.append({"site_code": site_code_value, "reason": fail_reason})

    return {
        "tenant_id": str(tenant_id),
        "tenant_code": tenant_code_value,
        "sent": sent,
        "failed": failed,
    }


@router.post("/backfill-sites")
def backfill_sites_to_soc(
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(ROLE_DEV, ROLE_BRANCH_MANAGER)),
):
    result = _run_backfill_sites_to_soc(
        tenant_code=tenant_code,
        conn=conn,
        user=user,
    )
    return {"sent": result["sent"], "failed": result["failed"]}


@router.post("/reset-master-data")
def reset_soc_master_data(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(ROLE_DEV, ROLE_BRANCH_MANAGER)),
):
    tenant = normalize_tenant_identifier(x_tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TENANT_CONTEXT_REQUIRED", "message": "작업회사 선택이 필요합니다."},
        )

    soc_base_url = str(getattr(settings, "soc_base_url", "") or "").strip().rstrip("/")
    if not soc_base_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "SOC_BASE_URL_MISSING", "message": "SOC_BASE_URL 설정이 필요합니다."},
        )

    hr_reset_token = str(getattr(settings, "hr_reset_token", "") or "").strip()
    if not hr_reset_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "HR_RESET_TOKEN_MISSING", "message": "HR_RESET_TOKEN 미설정"},
        )

    reset_url = str(getattr(settings, "soc_reset_url", "") or "").strip()
    if not reset_url:
        reset_url = f"{soc_base_url}/api/admin/hr/reset-tenant"
    if reset_url.startswith("/"):
        reset_url = f"{soc_base_url}{reset_url}"
    reset_url = reset_url.rstrip("/")
    print(
        f"[HR->SOC] reset call url={reset_url} tenant={tenant} token_len={len(hr_reset_token)}"
    )
    try:
        reset_response = requests.post(
            reset_url,
            headers={
                "X-HR-RESET-TOKEN": hr_reset_token,
                "X-Tenant-Id": tenant,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
    except Exception as exc:
        print(f"[HR->SOC] reset failed: {repr(exc)} url={reset_url} tenant={tenant}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "SOC_RESET_FAILED",
                "message": "SOC reset failed",
                "soc_status": None,
                "soc_body": str(exc),
            },
        ) from exc

    reset_body = (reset_response.text or "").strip()
    print(
        f"[HR->SOC] reset resp status={reset_response.status_code} body={reset_body[:300]}"
    )
    if int(reset_response.status_code) != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "SOC_RESET_FAILED",
                "message": "SOC reset failed",
                "soc_status": int(reset_response.status_code),
                "soc_body": reset_body[:300],
            },
        )

    reset_payload = None
    try:
        reset_payload = reset_response.json()
    except Exception:
        reset_payload = {"raw": reset_body[:300]}

    backfill_result = _run_backfill_sites_to_soc(
        tenant_code=tenant,
        conn=conn,
        user=user,
    )
    return {
        "success": True,
        "tenant_id": tenant,
        "reset": {
            "ok": True,
            "status_code": int(reset_response.status_code),
            "body": reset_body[:300],
            "payload": reset_payload,
        },
        "backfill": {
            "sent": backfill_result["sent"],
            "failed": backfill_result["failed"],
        },
        "sent": backfill_result["sent"],
        "failed": backfill_result["failed"],
    }
