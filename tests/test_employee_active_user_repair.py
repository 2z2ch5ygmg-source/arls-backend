from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import connect
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from app.config import settings
from app import db as app_db
from app.main import app
from app.security import hash_password

DB_CONNECT_TIMEOUT_SECONDS = 5
DB_STATEMENT_TIMEOUT_MS = 5000
DB_LOCK_TIMEOUT_MS = 2000


def _build_test_database_url(raw_value: str | None = None) -> str:
    raw = str(raw_value if raw_value is not None else settings.database_url or "").strip()
    if not raw:
        return ""
    if "connect_timeout=" in raw and "statement_timeout=" in raw:
        return raw
    return make_conninfo(
        raw,
        connect_timeout=DB_CONNECT_TIMEOUT_SECONDS,
        options=(
            f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS} "
            f"-c lock_timeout={DB_LOCK_TIMEOUT_MS}"
        ),
    )


def _db_conn(conninfo: str | None = None):
    resolved_conninfo = str(conninfo or _build_test_database_url()).strip()
    if not resolved_conninfo:
        pytest.skip("DATABASE_URL is required for integration tests")
    try:
        return connect(resolved_conninfo, row_factory=dict_row)
    except Exception as exc:
        pytest.skip(f"database unavailable for integration test: {exc}")


def _table_column_exists(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
        return cur.fetchone() is not None


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


def _api_rows(response) -> list[dict[str, Any]]:
    payload = _api_json(response)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return payload["data"]
        if isinstance(payload.get("items"), list):
            return payload["items"]
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data["items"]
    return []


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
    has_site_deleted = _table_column_exists(conn, "sites", "is_deleted")
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
        if has_site_deleted:
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
        else:
            cur.execute(
                """
                INSERT INTO sites (
                    id, tenant_id, company_id, site_code, site_name, latitude, longitude, radius_meters,
                    address, is_active, created_at, updated_at, employee_sequence_seed
                )
                VALUES (
                    %s, %s, %s, %s, %s, 37.5665, 126.9780, 80,
                    %s, TRUE, timezone('utc', now()), timezone('utc', now()), 0
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
    original_database_url = settings.database_url
    test_database_url = _build_test_database_url(original_database_url)
    settings.database_url = test_database_url
    if app_db._pool is not None:
        app_db._pool.close()
        app_db._pool = None
    try:
        with _db_conn(test_database_url) as probe_conn:
            with probe_conn.cursor() as cur:
                cur.execute("SELECT 1")
        with TestClient(app) as test_client:
            yield test_client
    except Exception as exc:
        pytest.skip(f"database unavailable for integration test: {exc}")
    finally:
        if app_db._pool is not None:
            app_db._pool.close()
            app_db._pool = None
        settings.database_url = original_database_url


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
        dev_payload = _api_rows(dev_list)
        dev_names = [str(item.get("full_name") or "") for item in dev_payload]
        assert "김민규" in dev_names

        employee_list = client.get(
            f"/api/v1/employees?tenant_code={tenant_scope['tenant_code']}&site_code={tenant_scope['site_code']}&include_account=1",
            headers={"Authorization": f"Bearer {actor_token}"},
        )
        _assert_status(employee_list, 200)
        employee_payload = _api_rows(employee_list)
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
