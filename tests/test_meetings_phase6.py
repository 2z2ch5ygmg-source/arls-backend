from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parent.parent
RETIREMENT_MIGRATION = ROOT / "migrations" / "033_retire_messenger_meetings.sql"

class MeetingsPhase6RetirementTests(unittest.TestCase):
    def test_meetings_router_and_service_modules_are_removed(self):
        self.assertFalse((ROOT / "app" / "routers" / "v1" / "meetings.py").exists())
        self.assertFalse((ROOT / "app" / "services" / "meetings.py").exists())

    def test_meetings_routes_are_not_mounted(self):
        paths = {route.path for route in app.routes}

        self.assertFalse(any(path.startswith("/api/v1/meetings") for path in paths))

    def test_meetings_endpoint_family_is_only_caught_by_generic_preflight_route(self):
        client = TestClient(app)

        response = client.get("/api/v1/meetings/rooms")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers.get("allow"), "OPTIONS")

    def test_retirement_migration_drops_meetings_tables_and_indexes(self):
        sql = RETIREMENT_MIGRATION.read_text(encoding="utf-8")

        for table_name in [
            "meeting_chat_links",
            "meeting_events",
            "meeting_sessions",
            "meeting_participants",
            "meeting_rooms",
        ]:
            self.assertIn(f"DROP TABLE IF EXISTS {table_name};", sql)

        for index_name in [
            "idx_meeting_chat_links_room_created",
            "idx_meeting_sessions_room_state_started",
            "idx_meeting_participants_room_user",
            "idx_meeting_events_room_created",
            "idx_meeting_participants_room_joined",
            "idx_meeting_rooms_tenant_state_scheduled",
        ]:
            self.assertIn(f"DROP INDEX IF EXISTS {index_name};", sql)

        self.assertIn("DELETE FROM groupware_rollout_checks", sql)
        self.assertNotIn("CASCADE", sql.upper())

if __name__ == "__main__":
    unittest.main()
