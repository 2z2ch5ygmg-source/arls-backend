from __future__ import annotations

from uuid import uuid4

from app.routers.v1 import calendar as calendar_router
from app.schemas import CalendarContainerOut, CalendarSyncConnectionOut, CalendarSyncConnectionUpsertIn


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
        self.commit_calls = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commit_calls += 1


def _sample_container() -> CalendarContainerOut:
    return CalendarContainerOut(
        id=uuid4(),
        scope_type="shared",
        name="공유 캘린더",
        color="#ff7a1a",
        provider="arls",
        permission="owner",
        is_default=True,
        badge_label="공유",
        owner_label="HQ",
    )


def _sample_sync(container_id) -> CalendarSyncConnectionOut:
    return CalendarSyncConnectionOut(
        id=uuid4(),
        provider="google",
        account_email="hq@example.com",
        account_label="HQ Google",
        access_scope="read_write",
        sync_state="connected",
        last_synced_at="2026-03-31T09:00:00+09:00",
        default_container_id=container_id,
        default_container_label="공유 캘린더",
        selected_external_calendars=["primary", "team"],
        last_sync_error=None,
    )


def _patch_scope(monkeypatch):
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})


def test_create_sync_connection_returns_saved_row(monkeypatch):
    _patch_scope(monkeypatch)
    container = _sample_container()
    expected = _sample_sync(container.id)
    conn = _FakeConn(fetchone_queue=[{"id": str(expected.id)}])
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_fetch_sync_connection_for_manager", lambda *args, **kwargs: expected)
    payload = CalendarSyncConnectionUpsertIn(
        provider="google",
        access_scope="read_write",
        account_email="hq@example.com",
        account_label="HQ Google",
        default_container_id=container.id,
        selected_external_calendars=["primary", "team"],
    )

    result = calendar_router.create_calendar_sync_connection(
        payload=payload,
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin"},
    )

    assert str(result.id) == str(expected.id)
    assert result.default_container_id == container.id
    assert conn.commit_calls == 1
    insert_sql = next(sql for sql, _ in conn.executed if "INSERT INTO calendar_sync_connections" in sql)
    assert "selected_external_calendars_json" in insert_sql


def test_update_sync_connection_returns_saved_row(monkeypatch):
    _patch_scope(monkeypatch)
    container = _sample_container()
    expected = _sample_sync(container.id)
    conn = _FakeConn()
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    monkeypatch.setattr(
        calendar_router,
        "_fetch_sync_connection_for_manager",
        lambda *args, **kwargs: expected,
    )
    payload = CalendarSyncConnectionUpsertIn(
        provider="outlook",
        access_scope="read",
        account_email="ops@example.com",
        account_label="Ops Outlook",
        default_container_id=container.id,
        selected_external_calendars=["primary"],
    )

    result = calendar_router.update_calendar_sync_connection(
        sync_connection_id=str(expected.id),
        payload=payload,
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin"},
    )

    assert str(result.id) == str(expected.id)
    assert conn.commit_calls == 1
    update_sql = next(sql for sql, _ in conn.executed if "UPDATE calendar_sync_connections" in sql)
    assert "default_container_id" in update_sql


def test_run_sync_connection_updates_sync_timestamp(monkeypatch):
    _patch_scope(monkeypatch)
    expected = _sample_sync(uuid4())
    conn = _FakeConn()
    monkeypatch.setattr(calendar_router, "_fetch_sync_connection_for_manager", lambda *args, **kwargs: expected)

    result = calendar_router.run_calendar_sync_connection(
        sync_connection_id=str(expected.id),
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin"},
    )

    assert str(result.id) == str(expected.id)
    assert conn.commit_calls == 1
    update_sql = next(sql for sql, _ in conn.executed if "UPDATE calendar_sync_connections" in sql)
    assert "last_synced_at" in update_sql


def test_delete_sync_connection_returns_deleted(monkeypatch):
    _patch_scope(monkeypatch)
    expected = _sample_sync(uuid4())
    conn = _FakeConn()
    monkeypatch.setattr(calendar_router, "_fetch_sync_connection_for_manager", lambda *args, **kwargs: expected)

    result = calendar_router.delete_calendar_sync_connection(
        sync_connection_id=str(expected.id),
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin"},
    )

    assert result["deleted"] is True
    assert result["id"] == str(expected.id)
    assert conn.commit_calls == 1
