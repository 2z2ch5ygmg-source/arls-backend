from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import connect
from psycopg.rows import dict_row

from app.config import settings
from app.main import app
from app.security import hash_password


def _db_conn():
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for integration tests")
    return connect(settings.database_url, row_factory=dict_row)


def _api_json(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {"raw": response.text}
    if isinstance(payload, dict):
        return payload
    return {"raw": payload}


def _api_data(response) -> dict[str, Any]:
    payload = _api_json(response)
    if "success" in payload and "data" in payload and isinstance(payload["data"], dict):
        return payload["data"]
    return payload


def _assert_status(response, expected_status: int):
    if response.status_code != expected_status:
        raise AssertionError(f"expected={expected_status} actual={response.status_code} payload={_api_json(response)}")


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


def _ensure_master_tenant(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM tenants
            WHERE lower(tenant_code) = 'master'
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE tenants
                SET is_active = TRUE,
                    is_deleted = FALSE,
                    deleted_at = NULL,
                    deleted_by = NULL,
                    updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (row["id"],),
            )
            return str(row["id"])

        tenant_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO tenants (id, tenant_code, tenant_name, is_active, is_deleted, created_at, updated_at)
            VALUES (%s, 'MASTER', 'Master Tenant', TRUE, FALSE, timezone('utc', now()), timezone('utc', now()))
            """,
            (tenant_id,),
        )
        return tenant_id


def _create_dev_actor(conn, *, suffix: str) -> tuple[str, str, str]:
    tenant_id = _ensure_master_tenant(conn)
    user_id = str(uuid.uuid4())
    username = f"pytest_dev_{suffix.lower()}"
    password = f"Dev!{suffix}123"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO arls_users (
                id, tenant_id, username, password_hash, full_name, role,
                is_active, is_deleted, must_change_password, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, 'developer',
                TRUE, FALSE, FALSE, timezone('utc', now()), timezone('utc', now())
            )
            """,
            (user_id, tenant_id, username, hash_password(password), f"Pytest Dev {suffix}"),
        )
    return user_id, username, password


def _create_tenant_scope(conn, *, tenant_code: str, tenant_name: str, site_code: str, site_name: str) -> dict[str, str]:
    tenant_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    site_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tenants (id, tenant_code, tenant_name, is_active, is_deleted, created_at, updated_at)
            VALUES (%s, %s, %s, TRUE, FALSE, timezone('utc', now()), timezone('utc', now()))
            """,
            (tenant_id, tenant_code, tenant_name),
        )
        cur.execute(
            """
            INSERT INTO companies (id, tenant_id, company_code, company_name, created_at)
            VALUES (%s, %s, %s, %s, timezone('utc', now()))
            """,
            (company_id, tenant_id, f"CMP_{site_code}", f"{tenant_name} Company"),
        )
        cur.execute(
            """
            INSERT INTO sites (
                id, tenant_id, company_id, site_code, site_name, latitude, longitude, radius_meters,
                address, is_active, is_deleted, created_at, updated_at, employee_sequence_seed
            )
            VALUES (
                %s, %s, %s, %s, %s, 37.5665, 126.9780, 80,
                %s, TRUE, FALSE, timezone('utc', now()), timezone('utc', now()), 0
            )
            """,
            (site_id, tenant_id, company_id, site_code, site_name, f"{site_name} Address"),
        )
    return {
        "tenant_id": tenant_id,
        "tenant_code": tenant_code,
        "site_id": site_id,
        "site_code": site_code,
        "site_name": site_name,
    }


def _cleanup(conn, *, tenant_ids: list[str], user_ids: list[str]):
    with conn.cursor() as cur:
        if user_ids:
            cur.execute("DELETE FROM arls_users WHERE id = ANY(%s::uuid[])", (user_ids,))
        if tenant_ids:
            cur.execute("DELETE FROM arls_users WHERE tenant_id = ANY(%s::uuid[])", (tenant_ids,))
            cur.execute("DELETE FROM employees WHERE tenant_id = ANY(%s::uuid[])", (tenant_ids,))
            cur.execute("DELETE FROM sites WHERE tenant_id = ANY(%s::uuid[])", (tenant_ids,))
            cur.execute("DELETE FROM companies WHERE tenant_id = ANY(%s::uuid[])", (tenant_ids,))
            cur.execute("DELETE FROM tenants WHERE id = ANY(%s::uuid[])", (tenant_ids,))


def _login(client: TestClient, *, tenant_code: str, username: str, password: str):
    return client.post(
        "/api/v1/auth/login",
        json={"tenant_code": tenant_code, "username": username, "password": password},
    )


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_employee_list_repairs_missing_row_from_active_arls_user(client: TestClient):
    suffix = _suffix()
    tenant_ids: list[str] = []
    user_ids: list[str] = []

    conn = _db_conn()
    try:
        dev_user_id, dev_username, dev_password = _create_dev_actor(conn, suffix=suffix)
        user_ids.append(dev_user_id)

        tenant_scope = _create_tenant_scope(
            conn,
            tenant_code=f"SRSFIX_{suffix}",
            tenant_name=f"SRS Fix {suffix}",
            site_code="R738",
            site_name="Apple_명동",
        )
        tenant_ids.append(tenant_scope["tenant_id"])

        target_user_id = str(uuid.uuid4())
        user_ids.append(target_user_id)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO arls_users (
                    id, tenant_id, username, password_hash, full_name, role,
                    is_active, is_deleted, must_change_password, phone,
                    employee_id, site_id, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, 'officer',
                    TRUE, FALSE, FALSE, %s,
                    NULL, %s, timezone('utc', now()), timezone('utc', now())
                )
                """,
                (
                    target_user_id,
                    tenant_scope["tenant_id"],
                    f"r738_{suffix.lower()}",
                    hash_password("Temp!123456"),
                    "김민규",
                    "01022222222",
                    tenant_scope["site_id"],
                ),
            )
        conn.commit()

        actor_login = _login(client, tenant_code="MASTER", username=dev_username, password=dev_password)
        _assert_status(actor_login, 200)
        actor_token = _api_data(actor_login)["access_token"]

        dev_list = client.get(
            f"/api/v1/dev/employees?tenant_code={tenant_scope['tenant_code']}&site_code={tenant_scope['site_code']}&include_account=1",
            headers={"Authorization": f"Bearer {actor_token}"},
        )
        _assert_status(dev_list, 200)
        dev_payload = dev_list.json()
        dev_names = [str(item.get("full_name") or "") for item in dev_payload]
        assert "김민규" in dev_names

        employee_list = client.get(
            f"/api/v1/employees?tenant_code={tenant_scope['tenant_code']}&site_code={tenant_scope['site_code']}&include_account=1",
            headers={"Authorization": f"Bearer {actor_token}"},
        )
        _assert_status(employee_list, 200)
        employee_payload = employee_list.json()
        employee_names = [str(item.get("full_name") or "") for item in employee_payload]
        assert "김민규" in employee_names

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.full_name, e.employee_code, au.employee_id
                FROM arls_users au
                LEFT JOIN employees e ON e.id = au.employee_id
                WHERE au.id = %s
                """,
                (target_user_id,),
            )
            repaired_row = cur.fetchone()
        assert repaired_row is not None
        assert str(repaired_row["full_name"] or "").strip() == "김민규"
        assert str(repaired_row["employee_code"] or "").startswith("R738-")
        assert repaired_row["employee_id"] is not None
    finally:
        _cleanup(conn, tenant_ids=tenant_ids, user_ids=user_ids)
        conn.commit()
        conn.close()
