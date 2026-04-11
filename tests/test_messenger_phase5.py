from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parent.parent
RETIREMENT_MIGRATION = ROOT / "migrations" / "033_retire_messenger_meetings.sql"

class MessengerPhase5RetirementTests(unittest.TestCase):
    def test_messenger_router_and_service_modules_are_removed(self):
        self.assertFalse((ROOT / "app" / "routers" / "v1" / "messenger.py").exists())
        self.assertFalse((ROOT / "app" / "services" / "messenger.py").exists())

    def test_messenger_routes_are_not_mounted(self):
        paths = {route.path for route in app.routes}

        self.assertFalse(any(path.startswith("/api/v1/messenger") for path in paths))

    def test_messenger_endpoint_family_is_only_caught_by_generic_preflight_route(self):
        client = TestClient(app)

        response = client.get("/api/v1/messenger/conversations")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers.get("allow"), "OPTIONS")

    def test_retirement_migration_drops_messenger_tables_and_indexes(self):
        sql = RETIREMENT_MIGRATION.read_text(encoding="utf-8")

        for table_name in [
            "announcement_rooms",
            "chat_polls",
            "chat_reactions",
            "chat_reads",
            "chat_attachments",
            "chat_messages",
            "chat_members",
            "chat_conversations",
            "presence_sessions",
        ]:
            self.assertIn(f"DROP TABLE IF EXISTS {table_name};", sql)

        for index_name in [
            "idx_announcement_rooms_tenant_scope_active",
            "idx_chat_reactions_message_reaction_created",
            "idx_chat_reads_tenant_user_conversation",
            "idx_chat_conversations_tenant_type_updated",
            "idx_presence_sessions_user_last_seen",
            "idx_chat_messages_conversation_created",
            "idx_chat_members_user_conversation",
            "idx_chat_conversations_tenant_created",
        ]:
            self.assertIn(f"DROP INDEX IF EXISTS {index_name};", sql)

        self.assertIn("module_key IN ('messenger', 'meetings')", sql)

if __name__ == "__main__":
    unittest.main()
