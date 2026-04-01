from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from app.services import meetings


class _FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            self.rowcount = 1
        else:
            self.rowcount = 0

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

    def cursor(self):
        return _FakeCursor(self)


class _FakeDispatcher:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.calls: list[dict[str, object]] = []

    def dispatch_in_app(self, **kwargs):
        self.calls.append(kwargs)
        return "notification-id"


class _FakeAuditService:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.calls: list[dict[str, object]] = []

    def write_event(self, **kwargs):
        self.calls.append(kwargs)


class _RaisingDispatcher:
    def __init__(self, conn) -> None:
        self.conn = conn

    def dispatch_in_app(self, **kwargs):
        raise RuntimeError("notification write failed")


class _RaisingAuditService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def write_event(self, **kwargs):
        raise RuntimeError("audit write failed")


class MeetingsPhase6Tests(unittest.TestCase):
    def test_phase6_migration_exists(self):
        sql = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "030_meetings_rollout_phase6.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("idx_meeting_sessions_room_state_started", sql)
        self.assertIn("idx_meeting_participants_room_user", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS groupware_rollout_checks", sql)
        self.assertIn("chk_groupware_rollout_checks_status", sql)

    def test_create_meeting_room_inserts_room_participants_and_chat_link(self):
        conn = _FakeConn()
        dispatcher = _FakeDispatcher(conn)
        audit = _FakeAuditService(conn)

        with patch.object(
            meetings,
            "_fetch_user_directory_map",
            return_value={
                "user-1": {"employee_id": "emp-1"},
                "user-2": {"employee_id": "emp-2"},
            },
        ), patch.object(
            meetings,
            "_validate_linked_conversation",
            return_value="conversation-1",
        ), patch.object(
            meetings,
            "get_meeting_room_detail",
            return_value={"id": "room-1", "state": "scheduled"},
        ), patch.object(
            meetings,
            "GroupwareNotificationDispatcher",
            return_value=dispatcher,
        ), patch.object(
            meetings,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = meetings.create_meeting_room(
                conn,
                tenant_id="tenant-1",
                current_user={"tenant_id": "tenant-1", "id": "user-1", "employee_id": "emp-1", "role": "hq_admin"},
                title="주간 운영 회의",
                participant_user_ids=["user-2"],
                linked_conversation_id="conversation-1",
                start_now=False,
            )

        self.assertEqual(result["state"], "scheduled")
        self.assertTrue(any("INSERT INTO meeting_rooms" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO meeting_participants" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO meeting_chat_links" in sql for sql, _ in conn.executed))
        self.assertEqual(dispatcher.calls[0]["user_id"], "user-2")
        self.assertEqual(audit.calls[0]["action_type"], "room_created")

    def test_create_meeting_room_tolerates_notification_failures(self):
        conn = _FakeConn()
        audit = _FakeAuditService(conn)

        with patch.object(
            meetings,
            "_fetch_user_directory_map",
            return_value={
                "user-1": {"employee_id": "emp-1"},
                "user-2": {"employee_id": "emp-2"},
            },
        ), patch.object(
            meetings,
            "_validate_linked_conversation",
            return_value=None,
        ), patch.object(
            meetings,
            "get_meeting_room_detail",
            return_value={"id": "room-1", "state": "live", "participant_count": 2},
        ), patch.object(
            meetings,
            "GroupwareNotificationDispatcher",
            return_value=_RaisingDispatcher(conn),
        ), patch.object(
            meetings,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = meetings.create_meeting_room(
                conn,
                tenant_id="tenant-1",
                current_user={"tenant_id": "tenant-1", "id": "user-1", "employee_id": "emp-1", "role": "hq_admin"},
                title="즉시 운영 회의",
                participant_user_ids=["user-2"],
                linked_conversation_id=None,
                start_now=False,
            )

        self.assertEqual(result["state"], "live")
        self.assertEqual(result["participant_count"], 2)
        self.assertTrue(any("INSERT INTO meeting_participants" in sql for sql, _ in conn.executed))

    def test_start_meeting_session_sets_room_live_and_inserts_event(self):
        conn = _FakeConn()
        audit = _FakeAuditService(conn)

        with patch.object(
            meetings,
            "_ensure_host_access",
            return_value=(
                {"id": "room-1", "host_user_id": "user-1", "title": "주간 운영 회의"},
                {"participant_role": "host"},
            ),
        ), patch.object(
            meetings,
            "get_meeting_room_detail",
            return_value={"id": "room-1", "state": "live"},
        ), patch.object(
            meetings,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = meetings.start_meeting_session(
                conn,
                tenant_id="tenant-1",
                room_id="room-1",
                current_user={"tenant_id": "tenant-1", "id": "user-1", "employee_id": "emp-1", "role": "hq_admin"},
                media_backend="pion",
                meta_json={"origin": "manual"},
            )

        self.assertEqual(result["state"], "live")
        self.assertTrue(any("UPDATE meeting_rooms" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO meeting_sessions" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO meeting_events" in sql for sql, _ in conn.executed))
        self.assertEqual(audit.calls[0]["action_type"], "session_started")

    def test_add_meeting_participants_tolerates_notification_and_audit_failures(self):
        conn = _FakeConn()

        with patch.object(
            meetings,
            "_ensure_host_access",
            return_value=(
                {"id": "room-1", "room_key": "mtg-room-1", "title": "주간 운영 회의"},
                {"participant_role": "host"},
            ),
        ), patch.object(
            meetings,
            "_fetch_user_directory_map",
            return_value={"user-2": {"employee_id": "emp-2"}},
        ), patch.object(
            meetings,
            "get_meeting_room_detail",
            return_value={"id": "room-1", "participant_count": 2},
        ), patch.object(
            meetings,
            "GroupwareNotificationDispatcher",
            return_value=_RaisingDispatcher(conn),
        ), patch.object(
            meetings,
            "GroupwareAuditService",
            return_value=_RaisingAuditService(conn),
        ):
            result = meetings.add_meeting_participants(
                conn,
                tenant_id="tenant-1",
                room_id="room-1",
                current_user={"tenant_id": "tenant-1", "id": "user-1", "role": "hq_admin"},
                participant_user_ids=["user-2"],
            )

        self.assertEqual(result["participant_count"], 2)
        self.assertTrue(any("INSERT INTO meeting_participants" in sql for sql, _ in conn.executed))

    def test_record_rollout_check_inserts_check(self):
        conn = _FakeConn(fetchone_queue=[{"id": "check-1", "checked_at": "2026-03-31T00:00:00Z", "created_at": "2026-03-31T00:00:00Z"}])
        audit = _FakeAuditService(conn)

        with patch.object(meetings, "GroupwareAuditService", return_value=audit):
            result = meetings.record_rollout_check(
                conn,
                tenant_id="tenant-1",
                current_user={"tenant_id": "tenant-1", "id": "user-1", "role": "hq_admin"},
                environment_key="prod",
                check_type="load_test",
                status_value="passed",
                summary="10인 회의 부하테스트 통과",
                detail_json={"target_participants": 12},
            )

        self.assertEqual(result["status"], "passed")
        self.assertTrue(any("INSERT INTO groupware_rollout_checks" in sql for sql, _ in conn.executed))
        self.assertEqual(audit.calls[0]["action_type"], "rollout_check_recorded")

    def test_get_meeting_rollout_status_summarizes_runtime_and_checks(self):
        conn = _FakeConn(fetchone_queue=[{"cnt": 4}, {"cnt": 1}, {"cnt": 1}])

        with patch.object(
            meetings,
            "_fetch_rollout_checks",
            return_value=[
                {"check_type": "load_test", "status": "passed"},
                {"check_type": "tenant_isolation", "status": "ready"},
            ],
        ):
            result = meetings.get_meeting_rollout_status(
                conn,
                tenant_id="tenant-1",
                current_user={"tenant_id": "tenant-1", "id": "user-1"},
            )

        self.assertEqual(result["runtime"]["room_count"], 4)
        self.assertEqual(result["runtime"]["live_room_count"], 1)
        self.assertEqual(result["readiness"]["status"], "ready")
        self.assertTrue(result["readiness"]["load_test_recorded"])
        self.assertTrue(result["readiness"]["tenant_isolation_recorded"])

    def test_list_meeting_rooms_uses_exists_scope_without_distinct(self):
        conn = _FakeConn(fetchall_queue=[[]])

        result = meetings.list_meeting_rooms(
            conn,
            tenant_id="tenant-1",
            current_user={"tenant_id": "tenant-1", "id": "user-1"},
        )

        self.assertEqual(result, [])
        first_sql = conn.executed[0][0]
        self.assertIn("EXISTS", first_sql)
        self.assertNotIn("SELECT DISTINCT", first_sql.upper())


if __name__ == "__main__":
    unittest.main()
