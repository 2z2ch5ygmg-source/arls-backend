from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from app.services import messenger


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
        if sql.lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT")):
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
        self.commit_count = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commit_count += 1


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
        raise RuntimeError("notification failure")


class _RaisingAuditService:
    def __init__(self, conn) -> None:
        self.conn = conn

    def write_event(self, **kwargs):
        raise RuntimeError("audit failure")


class MessengerPhase5Tests(unittest.TestCase):
    def test_phase5_migration_exists(self):
        sql = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "029_messenger_phase5_indexes.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("idx_chat_conversations_tenant_type_updated", sql)
        self.assertIn("idx_chat_reads_tenant_user_conversation", sql)
        self.assertIn("idx_chat_reactions_message_reaction_created", sql)
        self.assertIn("idx_announcement_rooms_tenant_scope_active", sql)

    def test_create_announcement_conversation_inserts_members_and_room(self):
        conn = _FakeConn()
        audit = _FakeAuditService(conn)

        with patch.object(
            messenger,
            "_fetch_user_directory_map",
            return_value={
                "user-1": {"employee_id": "emp-1"},
                "user-2": {"employee_id": "emp-2"},
            },
        ), patch.object(
            messenger,
            "get_conversation_detail",
            return_value={"id": "conversation-1", "conversation_type": "announcement"},
        ), patch.object(
            messenger,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = messenger.create_conversation(
                conn,
                tenant_id="tenant-1",
                current_user={
                    "tenant_id": "tenant-1",
                    "id": "user-1",
                    "employee_id": "emp-1",
                    "role": "hq_admin",
                },
                conversation_type="announcement",
                member_user_ids=["user-2"],
                title="운영 공지",
                announcement_room_key="ops-room",
                announcement_scope_type="tenant",
            )

        self.assertEqual(result["conversation_type"], "announcement")
        self.assertTrue(any("INSERT INTO chat_conversations" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO chat_members" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO announcement_rooms" in sql for sql, _ in conn.executed))
        self.assertEqual(audit.calls[0]["action_type"], "conversation_created")

    def test_create_message_inserts_poll_and_dispatches_notifications(self):
        conn = _FakeConn()
        dispatcher = _FakeDispatcher(conn)
        audit = _FakeAuditService(conn)

        with patch.object(
            messenger,
            "_ensure_member_access",
            return_value={"title": "운영 방"},
        ), patch.object(
            messenger,
            "_validate_attachment_objects",
            return_value=["attachment-1"],
        ), patch.object(
            messenger,
            "_list_conversation_member_user_ids",
            return_value=["user-1", "user-2", "user-3"],
        ), patch.object(
            messenger,
            "_fetch_message_detail",
            return_value={"id": "message-1", "message_type": "poll"},
        ), patch.object(
            messenger,
            "GroupwareNotificationDispatcher",
            return_value=dispatcher,
        ), patch.object(
            messenger,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = messenger.create_message(
                conn,
                tenant_id="tenant-1",
                conversation_id="conversation-1",
                current_user={
                    "tenant_id": "tenant-1",
                    "id": "user-1",
                    "employee_id": "emp-1",
                    "role": "officer",
                    "full_name": "홍길동",
                },
                body="투표 확인 부탁드립니다.",
                message_type="poll",
                mentioned_user_ids=["user-2"],
                attachment_object_ids=["attachment-1"],
                poll_question="어느 일정으로 진행할까요?",
                poll_options=["A안", "B안"],
            )

        self.assertEqual(result["message_type"], "poll")
        self.assertTrue(any("INSERT INTO chat_messages" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO chat_attachments" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO chat_polls" in sql for sql, _ in conn.executed))
        self.assertTrue(any("UPDATE chat_conversations" in sql for sql, _ in conn.executed))
        self.assertEqual(conn.commit_count, 1)
        self.assertEqual(len(dispatcher.calls), 2)
        mention_call = next(call for call in dispatcher.calls if call["user_id"] == "user-2")
        self.assertEqual(mention_call["category"], "warn")
        self.assertEqual(audit.calls[0]["action_type"], "message_created")

    def test_mark_conversation_read_upserts_chat_reads(self):
        conn = _FakeConn()

        with patch.object(messenger, "_ensure_member_access", return_value={"conversation_id": "conversation-1"}), patch.object(
            messenger,
            "_fetch_message_owner_row",
            return_value={"conversation_id": "conversation-1"},
        ):
            result = messenger.mark_conversation_read(
                conn,
                tenant_id="tenant-1",
                conversation_id="conversation-1",
                current_user={
                    "tenant_id": "tenant-1",
                    "id": "user-1",
                    "employee_id": "emp-1",
                },
                message_id="message-1",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["last_read_message_id"], "message-1")
        self.assertTrue(any("INSERT INTO chat_reads" in sql for sql, _ in conn.executed))
        self.assertTrue(any("UPDATE chat_members" in sql for sql, _ in conn.executed))

    def test_upsert_presence_session_returns_presence_payload(self):
        conn = _FakeConn()
        expected_presence = {
            "status": "online",
            "last_seen_at": "2026-03-31T00:00:00Z",
            "device_type": "web",
            "session_key": "web:user-1",
            "meta_json": {"page": "messenger"},
            "is_active": True,
        }

        with patch.object(
            messenger,
            "_fetch_presence_map",
            return_value={"user-1": expected_presence},
        ):
            result = messenger.upsert_presence_session(
                conn,
                tenant_id="tenant-1",
                current_user={"tenant_id": "tenant-1", "id": "user-1", "employee_id": "emp-1"},
                session_key="web:user-1",
                status_value="online",
                device_type="web",
                meta_json={"page": "messenger"},
            )

        self.assertEqual(result["presence"], expected_presence)
        self.assertTrue(any("INSERT INTO presence_sessions" in sql for sql, _ in conn.executed))

    def test_create_message_returns_fallback_payload_when_post_processing_fails(self):
        conn = _FakeConn()

        with patch.object(
            messenger,
            "_ensure_member_access",
            return_value={"title": "운영 방"},
        ), patch.object(
            messenger,
            "_validate_attachment_objects",
            return_value=[],
        ), patch.object(
            messenger,
            "_list_conversation_member_user_ids",
            return_value=["user-1", "user-2"],
        ), patch.object(
            messenger,
            "_fetch_message_detail",
            side_effect=RuntimeError("hydrate failure"),
        ), patch.object(
            messenger,
            "GroupwareNotificationDispatcher",
            return_value=_RaisingDispatcher(conn),
        ), patch.object(
            messenger,
            "GroupwareAuditService",
            return_value=_RaisingAuditService(conn),
        ):
            result = messenger.create_message(
                conn,
                tenant_id="tenant-1",
                conversation_id="conversation-1",
                current_user={
                    "tenant_id": "tenant-1",
                    "id": "user-1",
                    "employee_id": "emp-1",
                    "role": "officer",
                    "full_name": "홍길동",
                    "username": "hong",
                },
                body="테스트 메시지",
                message_type="text",
                mentioned_user_ids=["user-2"],
            )

        self.assertEqual(result["conversation_id"], "conversation-1")
        self.assertEqual(result["message_type"], "text")
        self.assertEqual(result["body"], "테스트 메시지")
        self.assertEqual(result["sender_name"], "홍길동")
        self.assertEqual(result["mentioned_user_ids"], ["user-2"])
        self.assertEqual(result["attachments"], [])
        self.assertTrue(result["is_mine"])
        self.assertEqual(conn.commit_count, 1)


if __name__ == "__main__":
    unittest.main()
