from __future__ import annotations

import uuid

from app.routers.v1 import employees as employees_router


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn
        self._one = None
        self._all = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        sql = " ".join(str(query).split())
        self.conn.executions.append((sql, params))
        self._one = None
        self._all = []
        self.rowcount = 0

        if "FROM sites" in sql and "upper(site_code)" in sql:
            self._one = {"id": "site-1", "site_code": "R738", "site_name": "Apple_명동"}
            return
        if "FROM employees e" in sql and "LEFT JOIN sites s ON s.id = e.site_id" in sql:
            self._one = {
                "id": "employee-1",
                "employee_uuid": str(uuid.uuid4()),
                "employee_code": "R738-90329",
                "full_name": "QA 전파 현장 0329",
                "site_id": "site-1",
                "site_code": "R738",
            }
            return
        if "FROM employees" in sql and "site_id = %s" in sql and "ORDER BY created_at" in sql:
            self._all = [
                {
                    "id": "employee-1",
                    "employee_uuid": str(uuid.uuid4()),
                    "employee_code": "R738-90329",
                    "full_name": "QA 전파 현장 0329",
                },
                {
                    "id": "employee-2",
                    "employee_uuid": str(uuid.uuid4()),
                    "employee_code": "R738-90330",
                    "full_name": "QA 전파 현장 0330",
                },
            ]
            return
        if "FROM arls_users" in sql and "employee_id = %s" in sql:
            employee_id = str((params or ["", ""])[1])
            if employee_id in {"employee-1", "63ce2760-39bc-48d1-8f91-9ab6ba1e5143"}:
                self._all = [
                    {
                        "id": "user-1",
                        "username": "qa_prop_field_0329",
                        "role": "officer",
                        "is_active": True,
                        "is_deleted": False,
                    }
                ]
            else:
                self._all = []
            return
        if "DELETE FROM employees" in sql:
            self.rowcount = 1
            return

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._all)


class _FakeConn:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple | None]] = []

    def cursor(self):
        return _FakeCursor(self)


def test_delete_employee_purges_related_rows_before_delete(monkeypatch):
    conn = _FakeConn()
    purge_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        employees_router,
        "_purge_employee_related_rows",
        lambda *args, **kwargs: purge_calls.append(kwargs) or {},
    )
    monkeypatch.setattr(
        employees_router,
        "_resolve_target_tenant",
        lambda conn, user, tenant_code, tenant_id=None: {
            "id": "tenant-1",
            "tenant_code": "SRS_KOREA",
            "tenant_name": "SRS Korea",
        },
    )
    monkeypatch.setattr(employees_router, "_post_employee_sync_to_soc", lambda **kwargs: (True, 200, None))
    monkeypatch.setattr(employees_router, "_reset_site_sequence_if_empty", lambda *args, **kwargs: None)

    user = {
        "id": "actor-1",
        "role": "developer",
        "tenant_id": "tenant-1",
        "tenant_code": "master",
        "active_tenant_id": "srs_korea",
    }

    result = employees_router.delete_employee(
        uuid.UUID("63ce2760-39bc-48d1-8f91-9ab6ba1e5143"),
        tenant_code="srs_korea",
        conn=conn,
        user=user,
    )

    assert result["success"] is True
    assert purge_calls == [
        {
            "tenant_id": "tenant-1",
            "employee_id": "63ce2760-39bc-48d1-8f91-9ab6ba1e5143",
            "linked_user_ids": ["user-1"],
        }
    ]
    employee_lookup_queries = [sql for sql, _params in conn.executions if "FROM employees e" in sql]
    assert employee_lookup_queries
    assert "WHERE e.id = %s" in employee_lookup_queries[0]


def test_bulk_delete_employees_by_site_purges_each_employee_before_delete(monkeypatch):
    conn = _FakeConn()
    purge_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        employees_router,
        "_purge_employee_related_rows",
        lambda *args, **kwargs: purge_calls.append(kwargs) or {},
    )
    monkeypatch.setattr(
        employees_router,
        "_resolve_target_tenant",
        lambda conn, user, tenant_code, tenant_id=None: {
            "id": "tenant-1",
            "tenant_code": "SRS_KOREA",
            "tenant_name": "SRS Korea",
        },
    )
    monkeypatch.setattr(employees_router, "_post_employee_sync_to_soc", lambda **kwargs: (True, 200, None))
    monkeypatch.setattr(employees_router, "_reset_site_sequence_if_empty", lambda *args, **kwargs: None)

    user = {
        "id": "actor-1",
        "role": "developer",
        "tenant_id": "tenant-1",
        "tenant_code": "master",
        "active_tenant_id": "srs_korea",
    }

    result = employees_router.bulk_delete_employees_by_site(
        site_code="R738",
        tenant_code="srs_korea",
        conn=conn,
        user=user,
    )

    assert result["success"] is True
    assert [call["employee_id"] for call in purge_calls] == ["employee-1", "employee-2"]
    assert purge_calls[0]["linked_user_ids"] == ["user-1"]
    assert purge_calls[1]["linked_user_ids"] == []
