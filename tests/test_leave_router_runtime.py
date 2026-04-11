from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import patch

from app.routers.v1 import leaves
from fastapi import HTTPException
from app.schemas import LeaveGrantCreate


class _FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))

    def fetchone(self):
        if self.conn.fetchone_queue:
            return self.conn.fetchone_queue.pop(0)
        return None

    def fetchall(self):
        if self.conn.fetchall_queue:
            return self.conn.fetchall_queue.pop(0)
        return []


class _FakeConn:
    def __init__(self, *, fetchone_queue=None, fetchall_queue=None) -> None:
        self.fetchone_queue = list(fetchone_queue or [])
        self.fetchall_queue = list(fetchall_queue or [])
        self.executed: list[tuple[str, object]] = []
        self.rollback_count = 0

    def cursor(self):
        return _FakeCursor(self)

    def rollback(self):
        self.rollback_count += 1


def _user(role: str = "hq_admin") -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "tenant-1",
        "tenant_code": "srs_korea",
        "tenant_name": "SRS Korea",
        "role": role,
        "employee_id": None,
        "site_id": None,
    }


def test_list_leaves_allows_case_insensitive_tenant_scope():
    conn = _FakeConn(fetchall_queue=[[]])

    result = leaves.list_leaves(
        status_filter=None,
        employee_code=None,
        tenant_code="SRS_KOREA",
        limit=20,
        conn=conn,
        user=_user(),
    )

    assert result == []
    assert any("FROM leave_requests" in sql for sql, _ in conn.executed)


def test_resolve_target_tenant_allows_super_admin_case_insensitive_lookup():
    conn = _FakeConn()
    user = _user(role="developer")
    with patch.object(
        leaves,
        "fetch_tenant_row_any",
        return_value={"id": "tenant-1", "tenant_code": "srs_korea", "is_active": True, "is_deleted": False},
    ):
        result = leaves._resolve_target_tenant(conn, user, "SRS_KOREA")

    assert result["id"] == "tenant-1"
    assert result["tenant_code"] == "SRS_KOREA"


def test_resolve_target_tenant_rejects_unknown_super_admin_tenant():
    conn = _FakeConn()
    user = _user(role="developer")
    with patch.object(leaves, "fetch_tenant_row_any", return_value=None):
        try:
            leaves._resolve_target_tenant(conn, user, "UNKNOWN")
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("expected HTTPException")


def test_list_leave_grants_returns_items():
    grant_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    conn = _FakeConn(
        fetchall_queue=[[
            {
                "id": grant_id,
                "tenant_code": "SRS_KOREA",
                "employee_code": "R692-1",
                "employee_name": "홍길동",
                "site_code": "R692",
                "site_name": "서울",
                "policy_id": policy_id,
                "policy_name": "기본 연차 정책",
                "grant_type": "annual",
                "granted_days": 15,
                "effective_from": date(2026, 1, 1),
                "effective_to": date(2026, 12, 31),
                "reference_key": "annual_default:2026",
                "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ]]
    )

    result = leaves.list_leave_grants(
        tenant_code="SRS_KOREA",
        limit=50,
        conn=conn,
        user=_user(),
    )

    assert len(result["items"]) == 1
    assert result["items"][0].employee_code == "R692-1"
    assert result["items"][0].grant_type == "annual"


def test_create_leave_grant_creates_row_and_refreshes_balance():
    grant_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    conn = _FakeConn(
        fetchone_queue=[
            {"id": policy_id, "display_name": "기본 연차 정책"},
            {"id": "emp-1", "site_id": "site-1", "employee_code": "R692-1"},
            {
                "id": grant_id,
                "tenant_code": "SRS_KOREA",
                "employee_code": "R692-1",
                "employee_name": "홍길동",
                "site_code": "R692",
                "site_name": "서울",
                "policy_id": policy_id,
                "policy_name": "기본 연차 정책",
                "grant_type": "manual",
                "granted_days": 3,
                "effective_from": date(2026, 4, 1),
                "effective_to": date(2026, 12, 31),
                "reference_key": f"manual:{grant_id}",
                "created_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            },
        ]
    )
    payload = LeaveGrantCreate(
        employee_code="R692-1",
        policy_id=policy_id,
        grant_type="manual",
        granted_days=3,
        effective_from=date(2026, 4, 1),
        effective_to=date(2026, 12, 31),
    )

    with patch.object(leaves, "compute_employee_leave_balance_summary", return_value={"remaining_days": 18.0}) as balance_mock:
        result = leaves.create_leave_grant(
            payload=payload,
            tenant_code="SRS_KOREA",
            conn=conn,
            user=_user(),
        )

    assert result.employee_code == "R692-1"
    assert result.granted_days == 3
    balance_mock.assert_called_once()


def test_get_leave_balance_falls_back_when_compute_raises():
    conn = _FakeConn()
    user = _user(role="hq_admin")
    with patch.object(
        leaves,
        "_resolve_target_tenant",
        return_value={"id": "tenant-1", "tenant_code": "SRS_KOREA"},
    ), patch.object(
        leaves,
        "_resolve_leave_balance_employee",
        return_value={"id": "emp-1", "employee_code": "R692-1"},
    ), patch.object(
        leaves,
        "compute_employee_leave_balance_summary",
        side_effect=RuntimeError("broken ledger path"),
    ), patch.object(
        leaves,
        "_compute_legacy_employee_leave_balance_summary",
        return_value={
            "tenant_id": "tenant-1",
            "employee_id": "emp-1",
            "policy_id": None,
            "policy_key": "annual_default",
            "policy_name": "기본 연차 정책",
            "year": 2026,
            "granted_days": 15.0,
            "used_days": 2.0,
            "remaining_days": 13.0,
            "restored_days": 0.0,
        },
    ) as fallback_mock:
        result = leaves.get_leave_balance(
            employee_code="R692-1",
            year=2026,
            tenant_code="SRS_KOREA",
            conn=conn,
            user=user,
        )

    assert result["employee_code"] == "R692-1"
    assert result["remaining_days"] == 13.0
    assert conn.rollback_count == 1
    fallback_mock.assert_called_once()
