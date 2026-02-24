from __future__ import annotations

import uuid

from .config import settings
from .db import get_connection
from .security import hash_password
from .utils.permissions import ROLE_DEV


def ensure_seed_admin() -> None:
    if not (settings.init_admin_password and settings.init_admin_username):
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenants (id, tenant_code, tenant_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (tenant_code)
                DO NOTHING
                """,
                (uuid.uuid4(), settings.init_admin_tenant_code, "Master Tenant"),
            )
            cur.execute(
                "SELECT id FROM tenants WHERE tenant_code = %s",
                (settings.init_admin_tenant_code,),
            )
            tenant = cur.fetchone()
            if not tenant:
                return

            cur.execute(
                """
                SELECT id FROM arls_users
                WHERE tenant_id = %s AND username = %s
                """,
                (tenant["id"], settings.init_admin_username),
            )
            existing = cur.fetchone()
            if existing:
                return

            cur.execute(
                """
                INSERT INTO arls_users (id, tenant_id, username, password_hash, full_name, role, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, true)
                """,
                (
                    uuid.uuid4(),
                    tenant["id"],
                    settings.init_admin_username,
                    hash_password(settings.init_admin_password),
                    "Master DEV",
                    ROLE_DEV,
                ),
            )
