from __future__ import annotations

import unittest
from unittest.mock import patch

from app.routers.v1 import schedules


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.query = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = tuple(params)

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows):
        self.cursor_instance = _FakeCursor(rows)

    def cursor(self):
        return self.cursor_instance


class SentrixHqEmployeeTruthBridgeTests(unittest.TestCase):
    def test_bridge_query_falls_back_when_canonical_employee_id_column_is_missing(self):
        conn = _FakeConn(
            [
                {
                    "employee_id": "emp-1",
                    "canonical_employee_id": "uuid-r738-2",
                    "employee_uuid": "uuid-r738-2",
                    "employee_code": "R738-2",
                    "full_name": "서경원",
                    "phone": "01011111111",
                    "site_id": "site-r738",
                    "site_code": "R738",
                    "site_name": "Apple_명동",
                    "company_code": "SRS_KOREA",
                    "user_id": "user-1",
                    "username": "01011111111",
                    "user_role": "vice_supervisor",
                    "soc_role": "Vice Supervisor",
                }
            ]
        )

        def has_column(_conn, table_name, column_name):
            return {
                ("employees", "is_active"): True,
                ("employees", "is_deleted"): True,
                ("employees", "canonical_employee_id"): False,
                ("employees", "employee_uuid"): True,
                ("employees", "employee_code"): True,
                ("employees", "soc_role"): True,
                ("sites", "is_active"): True,
                ("sites", "is_deleted"): True,
                ("arls_users", "is_deleted"): True,
            }.get((table_name, column_name), True)

        with patch("app.routers.v1.schedules._require_sentrix_support_bridge_token"), patch(
            "app.routers.v1.schedules._resolve_sentrix_bridge_tenant",
            return_value={"id": "tenant-1", "tenant_code": "SRS_KOREA"},
        ), patch(
            "app.routers.v1.schedules.table_column_exists",
            side_effect=has_column,
        ):
            result = schedules.get_sentrix_hq_employee_truth_bridge(
                tenant_code="srs_korea",
                authorization="Bearer test-token",
                conn=conn,
            )

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["employees"][0]["canonical_employee_id"], "uuid-r738-2")
        self.assertIn("COALESCE(e.employee_uuid::text, '') AS employee_uuid", conn.cursor_instance.query)
        self.assertNotIn("COALESCE(e.canonical_employee_id, '') AS canonical_employee_id", conn.cursor_instance.query)
        self.assertIn("NULLIF(TRIM(COALESCE(e.employee_uuid::text, '')), '')", conn.cursor_instance.query)


if __name__ == "__main__":
    unittest.main()
