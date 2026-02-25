from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...deps import apply_rate_limit, get_db_conn, require_roles
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV
from ...utils.tenant_context import resolve_scoped_tenant
from .sites import _post_site_sync_to_soc

router = APIRouter(
    prefix="/admin/soc",
    tags=["admin-soc"],
    dependencies=[Depends(apply_rate_limit)],
)


@router.post("/backfill-sites")
def backfill_sites_to_soc(
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(ROLE_DEV, ROLE_BRANCH_MANAGER)),
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
        ok, status_code, reason = _post_site_sync_to_soc(
            tenant_code=tenant_code_value,
            site_code=site_code_value,
            site_name=row.get("site_name"),
            event_type="SITE_UPDATED",
        )
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

    return {"sent": sent, "failed": failed}
