import unittest
import uuid
from datetime import date, datetime, timezone

from app.routers.v1 import employees


class EmployeeDrawerSummaryContractTests(unittest.TestCase):
    def test_fetch_employee_drawer_base_tolerates_missing_soft_delete_columns(self):
        employee_id = uuid.uuid4()
        captured: dict[str, object] = {}

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params):
                captured["sql"] = sql
                captured["params"] = params

            def fetchone(self):
                return {"id": str(employee_id)}

        class FakeConn:
            def cursor(self):
                return FakeCursor()

        original_exists = employees._table_column_exists
        employees._table_column_exists = lambda conn, table, column: False if (table, column) in {
            ("employees", "is_deleted"),
            ("employees", "is_active"),
            ("arls_users", "is_active"),
            ("arls_users", "is_deleted"),
        } else True
        try:
            row = employees._fetch_employee_drawer_base(
                FakeConn(),
                tenant_id="tenant-1",
                employee_id=employee_id,
            )
        finally:
            employees._table_column_exists = original_exists

        sql = str(captured["sql"])
        self.assertEqual(row["id"], str(employee_id))
        self.assertNotIn("e.is_deleted", sql)
        self.assertIn("TRUE AS is_active", sql)
        self.assertIn("WHERE TRUE", sql)

    def test_build_summary_payload_exposes_header_actions_and_previews(self):
        employee_id = uuid.uuid4()
        base_row = {
            "id": employee_id,
            "tenant_id": "tenant-1",
            "tenant_code": "SRS_KOREA",
            "tenant_name": "SRS Korea",
            "employee_code": "R692-001",
            "management_no_str": "1",
            "full_name": "서성원",
            "phone": "010-1111-2222",
            "hire_date": date(2024, 11, 1),
            "leave_date": None,
            "is_active": True,
            "company_name": "SRS Korea",
            "site_name": "Apple_가로수길",
            "site_code": "R692",
            "linked_user_id": "user-1",
            "linked_user_role": "hq_admin",
            "linked_username": "hq_admin",
            "soc_login_id": "01059387659",
            "soc_role": "HQ_Admin",
        }

        attendance_section = employees.EmployeeDrawerAttendanceOut(
            state="ok",
            empty_message=None,
            last_30d_normal_count=employees.EmployeeDrawerMetricOut(value=5, state="ok"),
            last_30d_late_count=employees.EmployeeDrawerMetricOut(value=None, state="unavailable", empty_message="지각 데이터가 연결되지 않았습니다"),
            last_30d_missing_count=employees.EmployeeDrawerMetricOut(value=1, state="ok"),
            last_30d_leave_or_excused_count=employees.EmployeeDrawerMetricOut(value=0, state="ok"),
            recent_attendance_records=[
                employees.EmployeeDrawerAttendanceRecordOut(
                    date=date(2026, 3, 10),
                    check_in=datetime(2026, 3, 10, 0, 5, tzinfo=timezone.utc),
                    check_out=datetime(2026, 3, 10, 9, 5, tzinfo=timezone.utc),
                    status_label="정상",
                )
            ],
        )
        schedule_section = employees.EmployeeDrawerScheduleOut(
            state="ok",
            empty_message=None,
            current_week_assignment_count=employees.EmployeeDrawerMetricOut(value=3, state="ok"),
            next_week_assignment_count=employees.EmployeeDrawerMetricOut(value=4, state="ok"),
            upcoming_schedule_count=employees.EmployeeDrawerMetricOut(value=5, state="ok"),
            current_leave_display_count=employees.EmployeeDrawerMetricOut(value=0, state="ok"),
            upcoming_schedules=[
                employees.EmployeeDrawerScheduleItemOut(
                    date=date(2026, 3, 14),
                    shift_kind="주간근무",
                    display_label="주간근무 08:00-18:00",
                    site_name="Apple_가로수길",
                )
            ],
        )
        leave_request_section = employees.EmployeeDrawerLeaveRequestsOut(
            state="ok",
            empty_message=None,
            leave_used_days=employees.EmployeeDrawerMetricOut(value=3.0, state="ok"),
            leave_remaining_days=employees.EmployeeDrawerMetricOut(value=None, state="unavailable", empty_message="연차 잔여일 데이터를 불러올 수 없습니다"),
            half_day_count=employees.EmployeeDrawerMetricOut(value=1, state="ok"),
            leave_pending_count=employees.EmployeeDrawerMetricOut(value=0, state="ok"),
            total_request_count_recent_window=employees.EmployeeDrawerMetricOut(value=2, state="ok"),
            pending_request_count=employees.EmployeeDrawerMetricOut(value=1, state="ok"),
            approved_request_count_recent_window=employees.EmployeeDrawerMetricOut(value=1, state="ok"),
            rejected_request_count_recent_window=employees.EmployeeDrawerMetricOut(value=0, state="ok"),
            recent_leave_entries=[],
            recent_request_entries=[
                employees.EmployeeDrawerRequestEntryOut(
                    request_type="출퇴근 수정",
                    requested_at=datetime(2026, 3, 11, 3, 0, tzinfo=timezone.utc),
                    status="pending",
                    short_summary="체크아웃 누락",
                )
            ],
        )

        original_attendance = employees._fetch_drawer_recent_attendance
        original_schedule = employees._fetch_drawer_schedule_section
        original_leave = employees._fetch_drawer_leave_request_section

        employees._fetch_drawer_recent_attendance = lambda conn, tenant_id, employee_id: (attendance_section, attendance_section.recent_attendance_records[:1], 1)
        employees._fetch_drawer_schedule_section = lambda conn, tenant_id, employee_id: (schedule_section, schedule_section.upcoming_schedules[:1], "2026-03-14 · 주간근무 08:00-18:00")
        employees._fetch_drawer_leave_request_section = lambda conn, tenant_id, employee_id: (leave_request_section, leave_request_section.recent_request_entries[:1], 1)
        try:
            payload = employees._build_employee_drawer_summary_payload(
                None,
                employee_row=base_row,
                tenant_code="SRS_KOREA",
                actor_role=employees.ROLE_BRANCH_MANAGER,
            )
        finally:
            employees._fetch_drawer_recent_attendance = original_attendance
            employees._fetch_drawer_schedule_section = original_schedule
            employees._fetch_drawer_leave_request_section = original_leave

        self.assertEqual(payload.header.employee_name, "서성원")
        self.assertEqual(payload.header.employee_number, "R692-001")
        self.assertEqual(payload.header.role_display, "HQ Admin")
        self.assertEqual(payload.header.account_link_status, "연결됨")
        self.assertTrue(payload.actions.can_edit_profile)
        self.assertTrue(payload.actions.can_manage_account_link)
        self.assertEqual(payload.overview.monthly_attendance_exception_count.value, 1)
        self.assertEqual(payload.overview.pending_request_count.value, 1)
        self.assertEqual(len(payload.overview.recent_attendance_preview), 1)
        self.assertEqual(len(payload.overview.upcoming_schedule_preview), 1)
        self.assertEqual(payload.meta.contract_version, "employee_drawer_summary.v1")

    def test_request_status_bucket_and_leave_duration_helpers(self):
        self.assertEqual(employees._drawer_request_status_bucket("requested"), "pending")
        self.assertEqual(employees._drawer_request_status_bucket("approved"), "approved")
        self.assertEqual(employees._drawer_request_status_bucket("rejected"), "rejected")
        self.assertEqual(
            employees._drawer_leave_duration_days(date(2026, 3, 1), date(2026, 3, 3), None),
            3.0,
        )
        self.assertEqual(
            employees._drawer_leave_duration_days(date(2026, 3, 1), date(2026, 3, 1), "am"),
            0.5,
        )

    def test_attendance_status_helper_distinguishes_missing_paths(self):
        self.assertEqual(employees._drawer_attendance_status_label("in", "out")[0], "정상")
        self.assertEqual(employees._drawer_attendance_status_label("in", None)[0], "퇴근 누락")
        self.assertEqual(employees._drawer_attendance_status_label(None, "out")[0], "출근 누락")


if __name__ == "__main__":
    unittest.main()
