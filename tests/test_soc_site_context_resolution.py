from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.routers.v1 import integrations


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))

    def fetchall(self):
        return list(self.conn.rows)


class _FakeConn:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.executed: list[tuple[str, tuple | None]] = []

    def cursor(self):
        return _FakeCursor(self)


class SocSiteContextResolutionTests(unittest.TestCase):
    def test_resolve_soc_site_context_accepts_site_name_hint(self):
        conn = _FakeConn(
            [
                {
                    "id": "site-1",
                    "site_code": "R692",
                    "site_name": "본사",
                    "address": "",
                    "company_id": "company-1",
                    "company_code": "SRS",
                    "_match_rank": 3,
                }
            ]
        )

        result = integrations._resolve_soc_site_context_by_hint(
            conn,
            tenant_id="tenant-1",
            site_hint=" 본사 ",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "site-1")
        self.assertEqual(result["site_code"], "R692")
        self.assertNotIn("_match_rank", result)
        self.assertEqual(
            conn.executed[0][1],
            ("본사", "본사", "본사", "tenant-1", "본사", "본사", "본사", "본사"),
        )

    def test_resolve_soc_site_context_prefers_site_code_over_name_match(self):
        conn = _FakeConn(
            [
                {
                    "id": "site-code",
                    "site_code": "본사",
                    "site_name": "코드 매칭",
                    "address": "",
                    "company_id": "company-1",
                    "company_code": "SRS",
                    "_match_rank": 0,
                },
                {
                    "id": "site-name",
                    "site_code": "R692",
                    "site_name": "본사",
                    "address": "",
                    "company_id": "company-1",
                    "company_code": "SRS",
                    "_match_rank": 3,
                },
            ]
        )

        result = integrations._resolve_soc_site_context_by_hint(
            conn,
            tenant_id="tenant-1",
            site_hint="본사",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "site-code")

    def test_resolve_soc_site_context_rejects_ambiguous_site_name_hint(self):
        conn = _FakeConn(
            [
                {
                    "id": "site-a",
                    "site_code": "R692",
                    "site_name": "본사",
                    "address": "",
                    "company_id": "company-1",
                    "company_code": "SRS",
                    "_match_rank": 3,
                },
                {
                    "id": "site-b",
                    "site_code": "R738",
                    "site_name": "본사",
                    "address": "",
                    "company_id": "company-1",
                    "company_code": "SRS",
                    "_match_rank": 3,
                },
            ]
        )

        with self.assertRaises(HTTPException) as raised:
            integrations._resolve_soc_site_context_by_hint(
                conn,
                tenant_id="tenant-1",
                site_hint="본사",
            )

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
