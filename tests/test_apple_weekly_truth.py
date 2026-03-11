from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.services import apple_weekly_truth as truth_service
from app.services.apple_weekly_truth import (
    SERVICE_STATE_SITE_NOT_ONBOARDED,
    _merge_employee_site_payload,
    build_apple_weekly_truth_contract,
    build_attendance_sessions_from_rows,
    build_employee_identity_payload,
    build_employee_overnight_summary,
    build_late_summary,
    build_leave_summary,
    build_overtime_summary,
    build_site_identity_payload,
    build_site_overnight_summary,
    expand_leave_records_by_business_date,
    normalize_week_start,
)

KST = timezone(timedelta(hours=9))
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"


class AppleWeeklyTruthTests(unittest.TestCase):
    def test_normalize_week_start_rolls_back_to_monday(self):
        self.assertEqual(normalize_week_start(date(2026, 3, 11)), date(2026, 3, 9))

    def test_attendance_session_same_day_check_in_and_out(self):
        week_start = date(2026, 3, 9)
        sessions, warnings = build_attendance_sessions_from_rows(
            [
                {
                    "employee_id": "emp-1",
                    "site_id": "site-1",
                    "site_code": "R692",
                    "event_type": "check_in",
                    "event_at": datetime(2026, 3, 9, 8, 0, tzinfo=KST),
                },
                {
                    "employee_id": "emp-1",
                    "site_id": "site-1",
                    "site_code": "R692",
                    "event_type": "check_out",
                    "event_at": datetime(2026, 3, 9, 18, 0, tzinfo=KST),
                },
            ],
            week_start,
            week_start + timedelta(days=6),
        )
        row = sessions[("emp-1", date(2026, 3, 9))]
        self.assertEqual(row["business_date"], date(2026, 3, 9))
        self.assertEqual(row["worked_minutes"], 600)
        self.assertEqual(warnings, [])

    def test_attendance_session_overnight_checkout_keeps_checkin_business_date(self):
        week_start = date(2026, 3, 9)
        sessions, warnings = build_attendance_sessions_from_rows(
            [
                {
                    "employee_id": "emp-2",
                    "site_id": "site-1",
                    "site_code": "R692",
                    "event_type": "check_in",
                    "event_at": datetime(2026, 3, 10, 22, 30, tzinfo=KST),
                },
                {
                    "employee_id": "emp-2",
                    "site_id": "site-1",
                    "site_code": "R692",
                    "event_type": "check_out",
                    "event_at": datetime(2026, 3, 11, 7, 45, tzinfo=KST),
                },
            ],
            week_start,
            week_start + timedelta(days=6),
        )
        row = sessions[("emp-2", date(2026, 3, 10))]
        self.assertEqual(row["business_date"], date(2026, 3, 10))
        self.assertEqual(row["worked_minutes"], 555)
        self.assertEqual(warnings, [])

    def test_leave_expansion_marks_each_business_date_and_preserves_ids(self):
        week_start = date(2026, 3, 9)
        expanded = expand_leave_records_by_business_date(
            [
                {
                    "id": "leave-1",
                    "employee_id": "emp-3",
                    "leave_type": "annual",
                    "half_day_slot": None,
                    "status": "approved",
                    "reason": "vacation",
                    "start_at": date(2026, 3, 10),
                    "end_at": date(2026, 3, 12),
                }
            ],
            week_start,
            week_start + timedelta(days=6),
        )
        self.assertEqual(expanded[("emp-3", date(2026, 3, 10))][0]["leave_type"], "annual")
        self.assertEqual(expanded[("emp-3", date(2026, 3, 12))][0]["leave_request_id"], "leave-1")

    def test_leave_summary_marks_partial_leave_and_staffing_impact(self):
        summary = build_leave_summary(
            [
                {
                    "leave_request_id": "leave-2",
                    "leave_type": "annual",
                    "half_day_slot": "am",
                    "status": "approved",
                    "reason": "hospital",
                    "start_date": "2026-03-10",
                    "end_date": "2026-03-10",
                }
            ]
        )
        self.assertTrue(summary["has_leave"])
        self.assertTrue(summary["is_partial_leave"])
        self.assertEqual(summary["staffing_impact"], "partial_leave")
        self.assertEqual(summary["half_day_slot"], "am")

    def test_late_summary_preserves_exact_minutes(self):
        summary = build_late_summary({"minutes_late": 17, "note": "gate issue"})
        self.assertTrue(summary["is_late"])
        self.assertEqual(summary["minutes_late"], 17)
        self.assertTrue(summary["exact_minutes_available"])
        self.assertEqual(summary["source"], "late_shift_log")

    def test_overtime_summary_keeps_operational_truth_and_precision(self):
        summary = build_overtime_summary(
            {
                "approved_minutes": 120,
                "overtime_units": 2,
                "overtime_hours_step": 2.0,
                "source": "ATTENDANCE_CLOSE",
                "overtime_source": "ATTENDANCE_CLOSE",
            },
            {"hours": 1.0, "status": "APPROVED", "reason": "complaint", "source_event_uid": "evt-1"},
            attendance_row={"worked_minutes": 600},
            schedule_row={"shift_type": "day"},
        )
        self.assertEqual(summary["soc_approved_minutes"], 120)
        self.assertEqual(summary["attendance_extension_minutes"], 120)
        self.assertEqual(summary["attendance_extension_precision"], "approved_minutes")
        self.assertEqual(summary["sources"], ["soc_overtime_approvals", "apple_daytime_ot"])

    def test_employee_overnight_summary_uses_cross_day_attendance(self):
        summary = build_employee_overnight_summary(
            {
                "check_in_at": datetime(2026, 3, 10, 22, 30, tzinfo=KST),
                "check_out_at": datetime(2026, 3, 11, 7, 45, tzinfo=KST),
                "worked_minutes": 555,
            },
            {"headcount": 1},
        )
        self.assertTrue(summary["has_overnight"])
        self.assertTrue(summary["crosses_midnight"])
        self.assertEqual(summary["origin_business_date"], "2026-03-10")
        self.assertEqual(summary["target_calendar_date"], "2026-03-11")

    def test_site_overnight_summary_reconciles_record_and_attendance(self):
        summary = build_site_overnight_summary(
            {"headcount": 2, "time_range": "22:00-08:00", "hours": 10.0},
            business_date=date(2026, 3, 10),
            attendance_cross_day_count=1,
        )
        self.assertEqual(summary["reconciliation_status"], "mismatch")
        self.assertIn("overnight_headcount_mismatch", summary["conflict_flags"])

    def test_site_mismatch_warning_is_emitted_when_same_employee_uses_two_site_codes(self):
        warnings: list[str] = []
        base = build_site_identity_payload("APPLE", {"site_id": "site-1", "site_code": "R692", "site_name": "Apple Garosu"})
        incoming = build_site_identity_payload("APPLE", {"site_id": "site-2", "site_code": "R700", "site_name": "Apple Hongdae"})
        _merge_employee_site_payload(base, incoming, warnings, source_label="attendance")
        self.assertEqual(warnings, ["site_mismatch:attendance:R692:R700"])

    def test_employee_identity_falls_back_to_uuid_and_marks_missing_employee_code(self):
        payload, warnings = build_employee_identity_payload(
            "APPLE",
            {
                "id": "emp-4",
                "employee_uuid": "uuid-123",
                "employee_code": "",
                "full_name": "Kim Guard",
            },
        )
        self.assertEqual(payload["canonical_employee_key"], "uuid-123")
        self.assertEqual(warnings, ["employee_code_missing"])

    def test_leave_summary_defaults_to_no_leave_when_missing(self):
        summary = build_leave_summary(None)
        self.assertFalse(summary["has_leave"])
        self.assertEqual(summary["leave_types"], [])
        self.assertEqual(summary["section_state"], "supported_present")

    def test_contract_marks_overtime_without_attendance_as_hard_error(self):
        tenant_row = {"id": "tenant-1", "tenant_code": "APPLE", "tenant_name": "Apple"}
        week_start = date(2026, 3, 9)
        site = {
            "site_id": "site-1",
            "site_code": "R692",
            "site_name": "Apple Garosu",
            "company_code": "APPLE",
            "company_name": "Apple",
        }
        schedule_rows = []
        attendance_rows = []
        leave_rows = []
        late_rows = []
        soc_overtime_rows = [
            {
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "work_date": date(2026, 3, 9),
                "approved_minutes": 90,
                "overtime_units": 1,
                "overtime_hours_step": 1.5,
                "overtime_source": "ATTENDANCE_CLOSE",
                "source": "ATTENDANCE_CLOSE",
                "reason": "closing",
            }
        ]
        patches = [
            patch("app.services.apple_weekly_truth._fetch_sites", return_value=[site]),
            patch("app.services.apple_weekly_truth._fetch_schedule_rows", return_value=schedule_rows),
            patch("app.services.apple_weekly_truth._fetch_attendance_rows", return_value=attendance_rows),
            patch("app.services.apple_weekly_truth._fetch_leave_rows", return_value=leave_rows),
            patch("app.services.apple_weekly_truth._fetch_late_rows", return_value=late_rows),
            patch("app.services.apple_weekly_truth._fetch_soc_overtime_rows", return_value=soc_overtime_rows),
            patch("app.services.apple_weekly_truth._fetch_apple_daytime_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_overnight_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_support_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_event_rows", return_value=[]),
        ]
        for active_patch in patches:
            active_patch.start()
        try:
            contract = build_apple_weekly_truth_contract(object(), tenant_row=tenant_row, week_start=week_start, include_debug=False)
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()
        row = contract["employee_day_rows"][0]
        self.assertIn("attendance_missing_for_overtime", row["missing_data_flags"])
        discrepancy = next(item for item in row["discrepancies"] if item["code"] == "attendance_missing_for_overtime")
        self.assertEqual(discrepancy["severity"], "hard_error")
        self.assertEqual(row["confidence_state"], "conflict")

    def test_contract_marks_late_leave_overlap_and_duplicate_overnight(self):
        tenant_row = {"id": "tenant-1", "tenant_code": "APPLE", "tenant_name": "Apple"}
        week_start = date(2026, 3, 9)
        site = {
            "site_id": "site-1",
            "site_code": "R692",
            "site_name": "Apple Garosu",
            "company_code": "APPLE",
            "company_name": "Apple",
        }
        schedule_rows = [
            {
                "schedule_id": "sched-1",
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "schedule_date": date(2026, 3, 10),
                "shift_type": "day",
                "source": "SOC",
                "source_ticket_id": 101,
                "schedule_note": None,
                "leader_user_id": None,
            }
        ]
        leave_rows = [
            {
                "id": "leave-1",
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "leave_type": "annual",
                "half_day_slot": None,
                "start_at": date(2026, 3, 10),
                "end_at": date(2026, 3, 10),
                "reason": "vacation",
                "status": "approved",
            }
        ]
        late_rows = [
            {
                "late_log_id": "late-1",
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "work_date": date(2026, 3, 10),
                "minutes_late": 10,
                "note": "traffic",
            }
        ]
        overnight_rows = [
            {
                "overnight_record_id": "ov-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "work_date": date(2026, 3, 10),
                "headcount": 1,
                "time_range": "22:00-08:00",
                "hours": 10.0,
                "source_ticket_id": 1,
                "source_event_uid": "evt-1",
            },
            {
                "overnight_record_id": "ov-2",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "work_date": date(2026, 3, 10),
                "headcount": 2,
                "time_range": "22:00-08:00",
                "hours": 10.0,
                "source_ticket_id": 2,
                "source_event_uid": "evt-2",
            },
        ]
        patches = [
            patch("app.services.apple_weekly_truth._fetch_sites", return_value=[site]),
            patch("app.services.apple_weekly_truth._fetch_schedule_rows", return_value=schedule_rows),
            patch("app.services.apple_weekly_truth._fetch_attendance_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_leave_rows", return_value=leave_rows),
            patch("app.services.apple_weekly_truth._fetch_late_rows", return_value=late_rows),
            patch("app.services.apple_weekly_truth._fetch_soc_overtime_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_apple_daytime_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_overnight_rows", return_value=overnight_rows),
            patch("app.services.apple_weekly_truth._fetch_support_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_event_rows", return_value=[]),
        ]
        for active_patch in patches:
            active_patch.start()
        try:
            contract = build_apple_weekly_truth_contract(object(), tenant_row=tenant_row, week_start=week_start, include_debug=False)
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()
        row = next(item for item in contract["employee_day_rows"] if item["business_date"] == "2026-03-10")
        self.assertIn("late_leave_overlap", row["conflict_flags"])
        self.assertEqual(next(item for item in row["discrepancies"] if item["code"] == "late_leave_overlap")["severity"], "warning")
        site_day = next(item for item in contract["site_day_summaries"] if item["business_date"] == "2026-03-10")
        self.assertIn("duplicate_overnight_records", site_day["conflict_flags"])
        self.assertEqual(next(item for item in site_day["discrepancies"] if item["code"] == "duplicate_overnight_records")["severity"], "warning")

    def test_contract_builds_phase4_truth_for_mixed_week(self):
        tenant_row = {"id": "tenant-1", "tenant_code": "APPLE", "tenant_name": "Apple"}
        week_start = date(2026, 3, 9)
        site = {
            "site_id": "site-1",
            "site_code": "R692",
            "site_name": "Apple Garosu",
            "company_code": "APPLE",
            "company_name": "Apple",
        }
        schedule_rows = [
            {
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "schedule_date": date(2026, 3, 9),
                "shift_type": "day",
                "source": "SOC",
                "source_ticket_id": 101,
                "schedule_note": None,
                "leader_user_id": None,
            },
            {
                "employee_id": "emp-2",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-2",
                "employee_code": "E002",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim Two",
                "duty_role": "GUARD",
                "schedule_date": date(2026, 3, 10),
                "shift_type": "night",
                "source": "SOC",
                "source_ticket_id": 102,
                "schedule_note": None,
                "leader_user_id": None,
            },
            {
                "employee_id": "emp-6",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-6",
                "employee_code": "E006",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim Six",
                "duty_role": "GUARD",
                "schedule_date": date(2026, 3, 14),
                "shift_type": "day",
                "source": "SOC",
                "source_ticket_id": 103,
                "schedule_note": None,
                "leader_user_id": None,
            },
        ]
        attendance_rows = [
            {
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "event_type": "check_in",
                "event_at": datetime(2026, 3, 9, 8, 0, tzinfo=KST),
                "auto_checkout": False,
            },
            {
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "event_type": "check_out",
                "event_at": datetime(2026, 3, 9, 20, 0, tzinfo=KST),
                "auto_checkout": False,
            },
            {
                "employee_id": "emp-2",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-2",
                "employee_code": "E002",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim Two",
                "duty_role": "GUARD",
                "event_type": "check_in",
                "event_at": datetime(2026, 3, 10, 22, 30, tzinfo=KST),
                "auto_checkout": False,
            },
            {
                "employee_id": "emp-2",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-2",
                "employee_code": "E002",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim Two",
                "duty_role": "GUARD",
                "event_type": "check_out",
                "event_at": datetime(2026, 3, 11, 7, 45, tzinfo=KST),
                "auto_checkout": False,
            },
            {
                "employee_id": "emp-3",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-3",
                "employee_code": "E003",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim Three",
                "duty_role": "GUARD",
                "event_type": "check_in",
                "event_at": datetime(2026, 3, 12, 8, 0, tzinfo=KST),
                "auto_checkout": False,
            },
            {
                "employee_id": "emp-3",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-3",
                "employee_code": "E003",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim Three",
                "duty_role": "GUARD",
                "event_type": "check_out",
                "event_at": datetime(2026, 3, 12, 18, 0, tzinfo=KST),
                "auto_checkout": False,
            },
        ]
        leave_rows = [
            {
                "id": "leave-1",
                "employee_id": "emp-4",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-4",
                "employee_code": "E004",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim Four",
                "duty_role": "GUARD",
                "leave_type": "annual",
                "half_day_slot": None,
                "start_at": date(2026, 3, 11),
                "end_at": date(2026, 3, 11),
                "reason": "vacation",
                "status": "approved",
            },
            {
                "id": "leave-2",
                "employee_id": "emp-5",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-5",
                "employee_code": "E005",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim Five",
                "duty_role": "GUARD",
                "leave_type": "annual",
                "half_day_slot": "pm",
                "start_at": date(2026, 3, 13),
                "end_at": date(2026, 3, 13),
                "reason": "clinic",
                "status": "approved",
            },
        ]
        late_rows = [
            {
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "work_date": date(2026, 3, 9),
                "minutes_late": 17,
                "note": "traffic",
            }
        ]
        soc_overtime_rows = [
            {
                "employee_id": "emp-1",
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "full_name": "Kim One",
                "duty_role": "GUARD",
                "work_date": date(2026, 3, 9),
                "approved_minutes": 120,
                "overtime_units": 2,
                "overtime_hours_step": 2.0,
                "overtime_source": "ATTENDANCE_CLOSE",
                "source": "ATTENDANCE_CLOSE",
                "reason": "closing",
            }
        ]
        apple_daytime_rows = []
        overnight_rows = [
            {
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "work_date": date(2026, 3, 10),
                "headcount": 1,
                "time_range": "22:00-08:00",
                "hours": 10.0,
                "source_ticket_id": 9001,
                "source_event_uid": "overnight-evt-1",
            }
        ]
        support_rows = [
            {
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "company_code": "APPLE",
                "company_name": "Apple",
                "work_date": date(2026, 3, 9),
                "worker_type": "F",
                "employee_id": "emp-1",
                "employee_uuid": "uuid-1",
                "employee_code": "E001",
                "external_employee_key": None,
                "linked_employee_id": None,
                "employee_name": "Kim One",
                "duty_role": "GUARD",
                "name": "Kim One",
                "source": "SHEET",
            }
        ]
        event_rows = [
            {
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "work_date": date(2026, 3, 9),
                "type": "EVENT",
                "description": "Townhall",
            },
            {
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
                "work_date": date(2026, 3, 9),
                "type": "ADDITIONAL",
                "description": "Mall extended hours",
            },
        ]

        patches = [
            patch("app.services.apple_weekly_truth._fetch_sites", return_value=[site]),
            patch("app.services.apple_weekly_truth._fetch_schedule_rows", return_value=schedule_rows),
            patch("app.services.apple_weekly_truth._fetch_attendance_rows", return_value=attendance_rows),
            patch("app.services.apple_weekly_truth._fetch_leave_rows", return_value=leave_rows),
            patch("app.services.apple_weekly_truth._fetch_late_rows", return_value=late_rows),
            patch("app.services.apple_weekly_truth._fetch_soc_overtime_rows", return_value=soc_overtime_rows),
            patch("app.services.apple_weekly_truth._fetch_apple_daytime_rows", return_value=apple_daytime_rows),
            patch("app.services.apple_weekly_truth._fetch_overnight_rows", return_value=overnight_rows),
            patch("app.services.apple_weekly_truth._fetch_support_rows", return_value=support_rows),
            patch("app.services.apple_weekly_truth._fetch_event_rows", return_value=event_rows),
        ]
        for active_patch in patches:
            active_patch.start()
        try:
            contract = build_apple_weekly_truth_contract(
                object(),
                tenant_row=tenant_row,
                week_start=week_start,
                include_debug=True,
            )
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()

        self.assertEqual(contract["contract_version"], "2026-03-07.phase4")
        self.assertEqual(contract["scope"]["site_count"], 1)
        self.assertIn("overtime_summary.normal_scheduled_minutes", contract["unsupported_fields"])
        self.assertIn("contract_state", contract)
        self.assertIn("discrepancy_summary", contract)
        self.assertIn("service_state", contract)
        self.assertIn("rollout", contract)
        self.assertIn("observability", contract)
        self.assertEqual(contract["service_state"], "supported_with_warnings")
        self.assertEqual(contract["rollout"]["gate_status"], "open")

        employee_rows = {
            (row["employee"]["employee_code"], row["business_date"]): row
            for row in contract["employee_day_rows"]
        }
        self.assertEqual(employee_rows[("E001", "2026-03-09")]["late_tardy_summary"]["minutes_late"], 17)
        self.assertEqual(employee_rows[("E001", "2026-03-09")]["late_tardy_summary"]["section_state"], "supported_present")
        self.assertEqual(employee_rows[("E001", "2026-03-09")]["overtime_summary"]["attendance_extension_minutes"], 120)
        self.assertTrue(employee_rows[("E002", "2026-03-10")]["overnight_summary"]["has_overnight"])
        self.assertTrue(employee_rows[("E004", "2026-03-11")]["leave_summary"]["has_leave"])
        self.assertTrue(employee_rows[("E005", "2026-03-13")]["leave_summary"]["is_partial_leave"])
        self.assertIn("schedule_missing_for_attendance", employee_rows[("E003", "2026-03-12")]["missing_data_flags"])
        self.assertIn("attendance_missing_for_scheduled_shift", employee_rows[("E006", "2026-03-14")]["missing_data_flags"])
        self.assertTrue(employee_rows[("E001", "2026-03-09")]["support_assignment_summary"]["has_support_assignment"])
        self.assertEqual(employee_rows[("E003", "2026-03-12")]["confidence_state"], "warning")
        self.assertTrue(employee_rows[("E001", "2026-03-09")]["traceability"]["source_refs"]["overtime"])
        self.assertTrue(employee_rows[("E004", "2026-03-11")]["leave_summary"]["trace_refs"])
        self.assertIn(
            "schedule_missing_for_attendance",
            [item["code"] for item in employee_rows[("E003", "2026-03-12")]["discrepancies"]],
        )

        site_days = {row["business_date"]: row for row in contract["site_day_summaries"] if row["site"]["site_code"] == "R692"}
        self.assertEqual(site_days["2026-03-10"]["overnight_summary"]["reconciliation_status"], "matched")
        self.assertEqual(site_days["2026-03-09"]["event_additional_note_summary"]["event_count"], 1)
        self.assertEqual(site_days["2026-03-09"]["event_additional_note_summary"]["additional_count"], 1)
        self.assertEqual(site_days["2026-03-12"]["attendance_summary"]["attendance_without_schedule_count"], 1)
        self.assertEqual(site_days["2026-03-14"]["attendance_summary"]["scheduled_without_attendance_count"], 1)
        self.assertEqual(site_days["2026-03-10"]["overnight_summary"]["section_state"], "supported_present")
        self.assertEqual(site_days["2026-03-14"]["confidence_state"], "incomplete")
        self.assertIn("scheduled_without_attendance_present", site_days["2026-03-14"]["attendance_summary"]["missing_data_flags"])
        self.assertIn("hard_error", contract["discrepancy_summary"]["employee_day"])

        expected_fixture = json.loads((FIXTURE_ROOT / "apple_weekly_truth_phase4_mixed_week_expected.json").read_text(encoding="utf-8"))
        actual_fixture = {
            "contract_version": contract["contract_version"],
            "contract_state": contract["contract_state"],
            "service_state": contract["service_state"],
            "service_signals": contract["service_signals"],
            "scope": {
                "site_count": contract["scope"]["site_count"],
                "site_code": contract["scope"]["site_code"],
            },
            "rollout": {
                "mode": contract["rollout"]["mode"],
                "gate_status": contract["rollout"]["gate_status"],
                "fully_supported_site_codes": contract["rollout"]["fully_supported_site_codes"],
            },
            "observability": {
                "unsupported_fields": contract["observability"]["unsupported_fields"],
                "source_coverage": contract["observability"]["source_coverage"],
            },
            "employee_row_sample": {
                "employee_code": employee_rows[("E001", "2026-03-09")]["employee"]["employee_code"],
                "business_date": employee_rows[("E001", "2026-03-09")]["business_date"],
                "late_minutes": employee_rows[("E001", "2026-03-09")]["late_tardy_summary"]["minutes_late"],
                "attendance_extension_minutes": employee_rows[("E001", "2026-03-09")]["overtime_summary"]["attendance_extension_minutes"],
                "support_assignment": employee_rows[("E001", "2026-03-09")]["support_assignment_summary"]["has_support_assignment"],
            },
            "site_day_sample": {
                "business_date": site_days["2026-03-09"]["business_date"],
                "event_count": site_days["2026-03-09"]["event_additional_note_summary"]["event_count"],
                "additional_count": site_days["2026-03-09"]["event_additional_note_summary"]["additional_count"],
            },
        }
        self.assertEqual(actual_fixture, expected_fixture)

    def test_contract_rollout_blocks_non_onboarded_site(self):
        tenant_row = {"id": "tenant-1", "tenant_code": "APPLE", "tenant_name": "Apple"}
        site = {
            "site_id": "site-2",
            "site_code": "R738",
            "site_name": "Apple Myeongdong",
            "company_code": "APPLE",
            "company_name": "Apple",
        }
        with patch("app.services.apple_weekly_truth._fetch_sites", return_value=[site]), patch.object(
            truth_service.settings,
            "apple_weekly_truth_site_allowlist",
            ["R692"],
        ):
            contract = build_apple_weekly_truth_contract(
                object(),
                tenant_row=tenant_row,
                week_start=date(2026, 3, 9),
                site_code="R738",
                include_debug=False,
            )
        self.assertEqual(contract["service_state"], SERVICE_STATE_SITE_NOT_ONBOARDED)
        self.assertEqual(contract["rollout"]["gate_status"], "blocked")
        self.assertEqual(contract["employee_day_rows"], [])
        self.assertEqual(contract["site_day_summaries"], [])

    def test_contract_exposes_phase4_observability_fields(self):
        tenant_row = {"id": "tenant-1", "tenant_code": "APPLE", "tenant_name": "Apple"}
        site = {
            "site_id": "site-1",
            "site_code": "R692",
            "site_name": "Apple Garosu",
            "company_code": "APPLE",
            "company_name": "Apple",
        }
        patches = [
            patch("app.services.apple_weekly_truth._fetch_sites", return_value=[site]),
            patch("app.services.apple_weekly_truth._fetch_schedule_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_attendance_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_leave_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_late_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_soc_overtime_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_apple_daytime_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_overnight_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_support_rows", return_value=[]),
            patch("app.services.apple_weekly_truth._fetch_event_rows", return_value=[]),
        ]
        for active_patch in patches:
            active_patch.start()
        try:
            contract = build_apple_weekly_truth_contract(
                object(),
                tenant_row=tenant_row,
                week_start=date(2026, 3, 9),
                site_code="R692",
                include_debug=True,
            )
        finally:
            for active_patch in reversed(patches):
                active_patch.stop()
        self.assertIn("observability", contract)
        self.assertIn("rollout", contract)
        self.assertIn("domain_capabilities", contract)
        self.assertEqual(contract["rollout"]["mode"], "all_sites")
        self.assertIn("latency_ms", contract["observability"])
        self.assertIn("source_coverage", contract["observability"])
        self.assertIn("unsupported_fields", contract["observability"])


if __name__ == "__main__":
    unittest.main()
