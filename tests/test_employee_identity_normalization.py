from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from app.routers.v1 import dev_scope, employees, integrations
from app.services.guard_roster_docx import build_employee_code_from_management_no
from app.utils.employee_identity import normalize_employee_code, normalize_management_no


class _RowsCursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql, _params=None):
        return None

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return None


class _RowsConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _RowsCursor(self._rows)


class EmployeeIdentityNormalizationTests(unittest.TestCase):
    def test_numeric_management_numbers_collapse_leading_zeroes(self):
        self.assertEqual(normalize_management_no("020"), "20")
        self.assertEqual(normalize_employee_code("R738-020"), "R738-20")
        self.assertEqual(build_employee_code_from_management_no("R738", "020"), "R738-20")

    def test_lookup_by_management_identity_matches_legacy_padded_row(self):
        rows = [
            {
                "id": "emp-legacy",
                "tenant_id": "tenant-1",
                "site_id": "site-r738",
                "employee_code": "R738-020",
                "management_no_str": "020",
                "full_name": "서경원",
                "phone": "01011111111",
            }
        ]
        with patch("app.routers.v1.employees._table_column_exists", return_value=True):
            row = employees._lookup_employee_by_management_identity(
                _RowsConn(rows),
                tenant_id="tenant-1",
                site_id="site-r738",
                site_code="R738",
                management_no="20",
            )

        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "emp-legacy")

    def test_list_employees_collapses_padded_and_unpadded_duplicate_rows(self):
        canonical_row = {
            "id": uuid.uuid4(),
            "tenant_id": uuid.uuid4(),
            "employee_code": "R738-20",
            "sequence_no": 20,
            "full_name": "서경원",
            "phone": "01011111111",
            "site_code": "R738",
            "site_name": "Apple_명동",
            "company_code": "CMP_R738",
            "is_active": True,
            "is_deleted": False,
            "management_no_str": "20",
            "gender": None,
            "resident_no": None,
            "birth_date": None,
            "address": "서울",
            "hire_date": None,
            "leave_date": None,
            "guard_training_cert_no": None,
            "note": None,
            "roster_docx_attachment_id": None,
            "photo_attachment_id": None,
            "soc_login_id": "01011111111",
            "soc_role": "Vice Supervisor",
            "user_id": uuid.uuid4(),
            "username": "01011111111",
            "user_role": "vice_supervisor",
        }
        legacy_row = {
            **canonical_row,
            "id": uuid.uuid4(),
            "employee_code": "R738-020",
            "management_no_str": "020",
            "user_id": None,
            "username": None,
            "user_role": None,
        }

        original_resolve_tenant = employees._resolve_target_tenant
        original_table_column_exists = employees._table_column_exists
        employees._resolve_target_tenant = lambda conn, user, tenant_code, tenant_id=None: {
            "id": "tenant-1",
            "tenant_code": "SRS_KOREA",
            "tenant_name": "SRS Korea",
        }
        employees._table_column_exists = lambda conn, table, column: True
        try:
            payload = employees.list_employees(
                site_id=None,
                site_code=None,
                q=None,
                limit=50,
                offset=0,
                include_inactive=False,
                include_deleted=False,
                detail=False,
                include_account=True,
                tenant_code=None,
                conn=_RowsConn([legacy_row, canonical_row]),
                user={"role": employees.ROLE_DEV},
            )
        finally:
            employees._resolve_target_tenant = original_resolve_tenant
            employees._table_column_exists = original_table_column_exists

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0].full_name, "서경원")
        self.assertEqual(payload[0].username, "01011111111")

    def test_dev_scope_dedupes_same_identity_rows(self):
        rows = [
            {
                "id": "emp-legacy",
                "tenant_id": "tenant-1",
                "tenant_code": "SRS_KOREA",
                "tenant_name": "SRS Korea",
                "employee_code": "R738-020",
                "management_no_str": "020",
                "sequence_no": 20,
                "full_name": "서경원",
                "phone": "01011111111",
                "site_code": "R738",
                "site_name": "Apple_명동",
                "company_code": "CMP_R738",
                "is_active": True,
                "is_deleted": False,
                "birth_date": None,
                "address": None,
                "hire_date": None,
                "leave_date": None,
                "guard_training_cert_no": None,
                "note": None,
                "roster_docx_attachment_id": None,
                "photo_attachment_id": None,
                "soc_login_id": None,
                "soc_role": "Vice Supervisor",
                "user_id": None,
                "username": None,
                "user_role": None,
            },
            {
                "id": "emp-canonical",
                "tenant_id": "tenant-1",
                "tenant_code": "SRS_KOREA",
                "tenant_name": "SRS Korea",
                "employee_code": "R738-20",
                "management_no_str": "20",
                "sequence_no": 20,
                "full_name": "서경원",
                "phone": "01011111111",
                "site_code": "R738",
                "site_name": "Apple_명동",
                "company_code": "CMP_R738",
                "is_active": True,
                "is_deleted": False,
                "birth_date": None,
                "address": "서울",
                "hire_date": None,
                "leave_date": None,
                "guard_training_cert_no": None,
                "note": None,
                "roster_docx_attachment_id": None,
                "photo_attachment_id": None,
                "soc_login_id": "01011111111",
                "soc_role": "Vice Supervisor",
                "user_id": "user-1",
                "username": "01011111111",
                "user_role": "vice_supervisor",
            },
        ]

        with patch("app.routers.v1.dev_scope._table_column_exists", return_value=True):
            payload = dev_scope._collapse_employee_directory_rows(rows)

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], "emp-canonical")

    def test_soc_sync_resolves_legacy_padded_employee_code_to_existing_row(self):
        rows = [
            {
                "id": "emp-legacy",
                "tenant_id": "tenant-1",
                "company_id": "company-1",
                "site_id": "site-r738",
                "employee_code": "R738-020",
                "management_no_str": "020",
                "full_name": "서경원",
                "external_employee_key": "",
                "linked_employee_id": "",
            }
        ]

        with patch("app.routers.v1.integrations.table_column_exists", return_value=True):
            row = integrations._resolve_employee(
                _RowsConn(rows),
                "tenant-1",
                "R738-20",
                site_id="site-r738",
            )

        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "emp-legacy")


if __name__ == "__main__":
    unittest.main()
