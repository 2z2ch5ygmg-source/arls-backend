from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...deps import apply_rate_limit, get_db_conn, require_roles
from ...services.sites_match_index import rebuild_site_match_index_for_tenant
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(
    prefix="/admin/sites",
    tags=["admin-sites"],
    dependencies=[Depends(apply_rate_limit)],
)


@router.post("/rebuild-match-index")
def rebuild_sites_match_index(
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(ROLE_DEV, ROLE_BRANCH_MANAGER)),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "")
    rebuilt = rebuild_site_match_index_for_tenant(conn, tenant_id=tenant_id)
    return {
        "success": True,
        "tenant_id": tenant_id,
        "tenant_code": str(tenant.get("tenant_code") or "").strip(),
        "rebuilt": rebuilt,
    }

