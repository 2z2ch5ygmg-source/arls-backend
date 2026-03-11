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
    if "success" in payload and "data" in payload:
        data = payload.get("data")
        if isinstance(data, dict):
            return data
    return payload


def _assert_status(response, expected_status: int):
    if response.status_code != expected_status:
        payload = _api_json(response)
        raise AssertionError(
            f"expected status={expected_status}, actual={response.status_code}, payload={payload}"
        )


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
            (
                user_id,
                tenant_id,
                username,
                hash_password(password),
                f"Pytest Dev {suffix}",
            ),
        )

    return user_id, username, password


def _create_tenant_company_site(conn, *, tenant_code: str, tenant_name: str) -> dict[str, str]:
    tenant_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    site_id = str(uuid.uuid4())

    company_code = f"CMP_{tenant_code[-4:]}"
    site_code = f"S_{tenant_code[-4:]}"

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
            (company_id, tenant_id, company_code, f"{tenant_name} Company"),
        )
        cur.execute(
            """
            INSERT INTO sites (
                id, tenant_id, company_id, site_code, site_name,
                latitude, longitude, radius_meters,
                address, is_active, created_at, updated_at, place_id, employee_sequence_seed
            )
            VALUES (
                %s, %s, %s, %s, %s,
                37.5665, 126.9780, 80,
                %s, TRUE, timezone('utc', now()), timezone('utc', now()), NULL, 0
            )
            """,
            (site_id, tenant_id, company_id, site_code, f"{tenant_name} Site", f"{tenant_name} Address"),
        )

    return {
        "tenant_id": tenant_id,
        "tenant_code": tenant_code,
        "company_code": company_code,
        "site_code": site_code,
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
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_code": tenant_code,
            "username": username,
            "password": password,
        },
    )
    return response


def _create_employee(
    client: TestClient,
    *,
    token: str,
    tenant_id: str,
    company_code: str,
    site_code: str,
    full_name: str,
    management_no: str,
    phone: str,
):
    response = client.post(
        "/api/v1/employees",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tenant_id": tenant_id,
            "company_code": company_code,
            "site_code": site_code,
            "full_name": full_name,
            "management_no_str": management_no,
            "phone": phone,
            "birth_date": "1990-01-01",
            "address": "Seoul",
            "hire_date": "2024-01-01",
            "guard_training_cert_no": "CERT-001",
            "soc_role": "Supervisor",
        },
    )
    return response


def _delete_employee(client: TestClient, *, token: str, employee_id: str, tenant_code: str):
    return client.delete(
        f"/api/v1/employees/{employee_id}",
        params={"tenant_code": tenant_code},
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture(autouse=True)
def _disable_soc_sync():
    prev_enabled = bool(settings.soc_integration_enabled)
    settings.soc_integration_enabled = False
    try:
        yield
    finally:
        settings.soc_integration_enabled = prev_enabled


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_tc1_multi_tenant_same_phone_login(client: TestClient):
    suffix = _suffix()
    tenant_ids: list[str] = []
    actor_user_ids: list[str] = []

    conn = _db_conn()
    try:
        actor_user_id, actor_username, actor_password = _create_dev_actor(conn, suffix=suffix)
        actor_user_ids.append(actor_user_id)

        tenant_a = _create_tenant_company_site(
            conn,
            tenant_code=f"JIP_{suffix}",
            tenant_name=f"Jip {suffix}",
        )
        tenant_b = _create_tenant_company_site(
            conn,
            tenant_code=f"APPLE_{suffix}",
            tenant_name=f"Apple {suffix}",
        )
        tenant_ids.extend([tenant_a["tenant_id"], tenant_b["tenant_id"]])
        conn.commit()

        actor_login = _login(
            client,
            tenant_code="MASTER",
            username=actor_username,
            password=actor_password,
        )
        _assert_status(actor_login, 200)
        actor_token = _api_data(actor_login)["access_token"]

        create_a = _create_employee(
            client,
            token=actor_token,
            tenant_id=tenant_a["tenant_id"],
            company_code=tenant_a["company_code"],
            site_code=tenant_a["site_code"],
            full_name="Jip Worker",
            management_no="1001",
            phone="010 5938 7659",
        )
        _assert_status(create_a, 200)

        create_b = _create_employee(
            client,
            token=actor_token,
            tenant_id=tenant_b["tenant_id"],
            company_code=tenant_b["company_code"],
            site_code=tenant_b["site_code"],
            full_name="Apple Worker",
            management_no="2001",
            phone="010 5938 7659",
        )
        _assert_status(create_b, 200)

        login_a = _login(
            client,
            tenant_code=tenant_a["tenant_code"],
            username="01059387659",
            password="01059387659",
        )
        _assert_status(login_a, 200)
        assert str(_api_data(login_a)["user"]["tenant_id"]) == tenant_a["tenant_id"]

        login_b = _login(
            client,
            tenant_code=tenant_b["tenant_code"],
            username="010 5938 7659",
            password="01059387659",
        )
        _assert_status(login_b, 200)
        assert str(_api_data(login_b)["user"]["tenant_id"]) == tenant_b["tenant_id"]

        wrong_tenant = _login(
            client,
            tenant_code=f"NOPE_{suffix}",
            username="01059387659",
            password="01059387659",
        )
        _assert_status(wrong_tenant, 401)
    finally:
        _cleanup(conn, tenant_ids=tenant_ids, user_ids=actor_user_ids)
        conn.commit()
        conn.close()


def test_tc2_register_delete_reregister_same_tenant_login(client: TestClient):
    suffix = _suffix()
    tenant_ids: list[str] = []
    actor_user_ids: list[str] = []

    conn = _db_conn()
    try:
        actor_user_id, actor_username, actor_password = _create_dev_actor(conn, suffix=suffix)
        actor_user_ids.append(actor_user_id)

        tenant = _create_tenant_company_site(
            conn,
            tenant_code=f"JIP_{suffix}",
            tenant_name=f"Jip {suffix}",
        )
        tenant_ids.append(tenant["tenant_id"])
        conn.commit()

        actor_login = _login(
            client,
            tenant_code="MASTER",
            username=actor_username,
            password=actor_password,
        )
        _assert_status(actor_login, 200)
        actor_token = _api_data(actor_login)["access_token"]

        create_1 = _create_employee(
            client,
            token=actor_token,
            tenant_id=tenant["tenant_id"],
            company_code=tenant["company_code"],
            site_code=tenant["site_code"],
            full_name="Jip Rehire",
            management_no="3001",
            phone="010 5938 7659",
        )
        _assert_status(create_1, 200)
        employee_id_1 = str(_api_data(create_1)["id"])

        login_before_delete = _login(
            client,
            tenant_code=tenant["tenant_code"],
            username="01059387659",
            password="01059387659",
        )
        _assert_status(login_before_delete, 200)

        delete_resp = _delete_employee(
            client,
            token=actor_token,
            employee_id=employee_id_1,
            tenant_code=tenant["tenant_code"],
        )
        _assert_status(delete_resp, 200)

        login_after_delete = _login(
            client,
            tenant_code=tenant["tenant_code"],
            username="01059387659",
            password="01059387659",
        )
        _assert_status(login_after_delete, 401)

        create_2 = _create_employee(
            client,
            token=actor_token,
            tenant_id=tenant["tenant_id"],
            company_code=tenant["company_code"],
            site_code=tenant["site_code"],
            full_name="Jip Rehire Again",
            management_no="3002",
            phone="010 5938 7659",
        )
        _assert_status(create_2, 200)

        login_after_reregister = _login(
            client,
            tenant_code=tenant["tenant_code"],
            username="01059387659",
            password="01059387659",
        )
        _assert_status(login_after_reregister, 200)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM arls_users
                WHERE tenant_id = %s
                  AND username = %s
                  AND COALESCE(is_deleted, FALSE) = FALSE
                  AND is_active = TRUE
                """,
                (tenant["tenant_id"], "01059387659"),
            )
            row = cur.fetchone()
            assert int(row["cnt"]) == 1
    finally:
        _cleanup(conn, tenant_ids=tenant_ids, user_ids=actor_user_ids)
        conn.commit()
        conn.close()


def test_tc3_password_change_then_login_with_new_password(client: TestClient):
    suffix = _suffix()
    tenant_ids: list[str] = []
    actor_user_ids: list[str] = []

    conn = _db_conn()
    try:
        actor_user_id, actor_username, actor_password = _create_dev_actor(conn, suffix=suffix)
        actor_user_ids.append(actor_user_id)

        tenant = _create_tenant_company_site(
            conn,
            tenant_code=f"JIP_{suffix}",
            tenant_name=f"Jip {suffix}",
        )
        tenant_ids.append(tenant["tenant_id"])
        conn.commit()

        actor_login = _login(
            client,
            tenant_code="MASTER",
            username=actor_username,
            password=actor_password,
        )
        _assert_status(actor_login, 200)
        actor_token = _api_data(actor_login)["access_token"]

        create_emp = _create_employee(
            client,
            token=actor_token,
            tenant_id=tenant["tenant_id"],
            company_code=tenant["company_code"],
            site_code=tenant["site_code"],
            full_name="Jip Password",
            management_no="4001",
            phone="010 5938 7659",
        )
        _assert_status(create_emp, 200)

        login_initial = _login(
            client,
            tenant_code=tenant["tenant_code"],
            username="01059387659",
            password="01059387659",
        )
        _assert_status(login_initial, 200)
        employee_token = _api_data(login_initial)["access_token"]

        change_password = client.patch(
            "/api/v1/users/me/password",
            headers={"Authorization": f"Bearer {employee_token}"},
            json={
                "current_password": "01059387659",
                "new_password": "NewPass!7659",
            },
        )
        _assert_status(change_password, 200)

        login_old_password = _login(
            client,
            tenant_code=tenant["tenant_code"],
            username="01059387659",
            password="01059387659",
        )
        _assert_status(login_old_password, 401)

        login_new_password = _login(
            client,
            tenant_code=tenant["tenant_code"],
            username="01059387659",
            password="NewPass!7659",
        )
        _assert_status(login_new_password, 200)
    finally:
        _cleanup(conn, tenant_ids=tenant_ids, user_ids=actor_user_ids)
        conn.commit()
        conn.close()
