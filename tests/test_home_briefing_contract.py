from __future__ import annotations

from datetime import date, datetime, timezone

from app.routers.v1 import home as home_router
from app.schemas import (
    HomeBriefingListRowOut,
    HomeBriefingPersonalSummaryOut,
    HomeBriefingRequestSummaryOut,
    HomeBriefingWeekSummaryOut,
)


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn
        self._one = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executions.append((" ".join(str(sql).split()), params))
        if not self.conn.fetchone_results:
            self._one = None
            return
        self._one = self.conn.fetchone_results.pop(0)

    def fetchone(self):
        return self._one

    def fetchall(self):
        if not self.conn.fetchall_results:
            return []
        return self.conn.fetchall_results.pop(0)


class _FakeConn:
    def __init__(self, fetchone_results=None, *, fetchall_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])
        self.executions: list[tuple[str, tuple | None]] = []

    def cursor(self):
        return _FakeCursor(self)


def _patch_common(monkeypatch):
    monkeypatch.setattr(home_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})
    monkeypatch.setattr(
        home_router,
        "_today_context",
        lambda: (
            datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 30, 0, 0, tzinfo=timezone.utc),
            date(2026, 3, 29),
        ),
    )
    monkeypatch.setattr(
        home_router,
        "_kst_day_bounds_for_date",
        lambda *_args, **_kwargs: (
            datetime(2026, 3, 28, 15, 0, tzinfo=timezone.utc),
            datetime(2026, 3, 29, 15, 0, tzinfo=timezone.utc),
        ),
    )
    monkeypatch.setattr(
        home_router,
        "_lookup_site_row",
        lambda *args, **kwargs: {
            "id": "site-1",
            "site_code": "R738",
            "site_name": "Apple_명동",
        },
    )
    monkeypatch.setattr(home_router, "_fetch_notice_summaries", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        home_router,
        "_build_request_summary",
        lambda *args, **kwargs: HomeBriefingRequestSummaryOut(
            total_pending_count=3,
            leave_pending_count=1,
            attendance_pending_count=2,
            correction_pending_count=0,
            unread_count=1,
        ),
    )
    monkeypatch.setattr(
        home_router,
        "_fetch_today_staff_snapshot",
        lambda *args, **kwargs: [
            {
                "employee_name": "김감독",
                "employee_code": "R738-1",
                "site_code": "R738",
                "site_name": "Apple_명동",
                "has_check_in": False,
                "approved_leave": False,
                "pending_attendance": True,
                "pending_leave": False,
                "shift_type": "day",
            }
        ],
    )
    monkeypatch.setattr(
        home_router,
        "_fetch_assignment_flags",
        lambda *args, **kwargs: {
            "site_count": 2,
            "closer_missing_count": 1,
            "leader_missing_count": 0,
        },
    )
    monkeypatch.setattr(
        home_router,
        "_build_attention_rows",
        lambda _snapshot, *, include_names: [
            HomeBriefingListRowOut(
                title="김감독" if include_names else "출근 누락",
                subtitle="Apple_명동 · 오늘 출근 기록이 없습니다." if include_names else "근무 시작 확인이 필요합니다.",
                value="R738",
                pill_label="출근 누락",
                pill_tone="error",
            )
        ],
    )
    monkeypatch.setattr(
        home_router,
        "_fetch_hq_org_issue_rows",
        lambda *args, **kwargs: [
            HomeBriefingListRowOut(
                title="미연동 직원",
                subtitle="계정 연결이 되지 않은 직원이 남아 있습니다.",
                value="1명",
                pill_label="조직 점검",
                pill_tone="warn",
            )
        ],
    )
    monkeypatch.setattr(
        home_router,
        "_build_personal_summary",
        lambda *args, **kwargs: HomeBriefingPersonalSummaryOut(
            employee_name="QA 사용자",
            site_code="R738",
            site_name="Apple_명동",
            today_status="WORKING",
            button_mode="check_out",
            next_shift_label="2026-03-30 · 주간근무",
            pending_leave_count=1,
            pending_attendance_count=2,
            unread_count=1,
        ),
    )
    monkeypatch.setattr(
        home_router,
        "_build_week_summary",
        lambda *args, **kwargs: HomeBriefingWeekSummaryOut(
            start_date="2026-03-23",
            end_date="2026-03-29",
            scheduled_days=5,
            worked_days=4,
            off_days=1,
        ),
    )


def test_home_briefing_hq_payload_is_tenant_wide(monkeypatch):
    _patch_common(monkeypatch)
    user = {
        "id": "user-hq",
        "role": "hq_admin",
        "tenant_id": "tenant-1",
        "active_tenant_id": "tenant-1",
        "site_id": "site-1",
        "site_code": "R738",
    }

    result = home_router.get_home_briefing(conn=object(), user=user)

    assert result.audience == "hq"
    assert result.scope_label == "전체 운영 범위"
    assert result.ops_summary is not None
    assert result.approval_summary is not None
    assert result.org_issue_rows[0].title == "미연동 직원"
    assert result.attendance_issue_rows[0].title == "김감독"
    assert result.site_summary is None
    assert result.site_readiness_summary is None


def test_home_briefing_supervisor_sees_named_team_attention(monkeypatch):
    _patch_common(monkeypatch)
    user = {
        "id": "user-sv",
        "role": "supervisor",
        "tenant_id": "tenant-1",
        "active_tenant_id": "tenant-1",
        "employee_id": "employee-1",
        "site_id": "site-1",
        "site_code": "R738",
    }

    result = home_router.get_home_briefing(conn=object(), user=user)

    assert result.audience == "supervisor"
    assert result.site_summary is not None
    assert result.team_attention_rows[0].title == "김감독"
    assert "지점 운영 범위" in result.scope_label
    assert result.approval_summary is None
    assert result.org_issue_rows == []
    assert result.personal_summary is not None


def test_home_briefing_vice_is_count_only(monkeypatch):
    _patch_common(monkeypatch)
    user = {
        "id": "user-vice",
        "role": "vice_supervisor",
        "tenant_id": "tenant-1",
        "active_tenant_id": "tenant-1",
        "employee_id": "employee-2",
        "site_id": "site-1",
        "site_code": "R738",
    }

    result = home_router.get_home_briefing(conn=object(), user=user)

    assert result.audience == "vice"
    assert result.site_readiness_summary is not None
    assert result.team_attention_rows == []
    assert result.approval_summary is None
    assert result.org_issue_rows == []
    assert "현장 준비도" in result.scope_label
    assert result.personal_summary is not None


def test_home_briefing_officer_is_self_only(monkeypatch):
    _patch_common(monkeypatch)
    user = {
        "id": "user-officer",
        "role": "officer",
        "tenant_id": "tenant-1",
        "active_tenant_id": "tenant-1",
        "employee_id": "employee-3",
        "site_id": "site-1",
        "site_code": "R738",
    }

    result = home_router.get_home_briefing(conn=object(), user=user)

    assert result.audience == "officer"
    assert result.scope_label == "본인 근무 기준"
    assert result.personal_summary is not None
    assert result.week_summary is not None
    assert result.site_summary is None
    assert result.site_readiness_summary is None
    assert result.team_attention_rows == []
    assert result.org_issue_rows == []
    assert result.approval_summary is None


def test_fetch_hq_org_issue_rows_skips_employee_deleted_clause_when_column_missing(monkeypatch):
    conn = _FakeConn(
        [
            {"employee_total": 4, "unassigned_employee_count": 1, "unlinked_count": 2},
            {"inactive_site_count": 1},
        ]
    )
    monkeypatch.setattr(home_router, "_table_exists", lambda _conn, table_name: table_name in {"employees", "sites"})
    monkeypatch.setattr(
        home_router,
        "_table_column_exists",
        lambda _conn, table_name, column_name: not (table_name == "employees" and column_name == "is_deleted"),
    )

    rows = home_router._fetch_hq_org_issue_rows(conn, tenant_id="tenant-1")

    employee_sql, employee_params = conn.executions[0]
    assert "COALESCE(e.is_deleted, FALSE) = FALSE" not in employee_sql
    assert employee_params == ("tenant-1",)
    assert rows[0].title == "미연동 직원"


def test_fetch_today_staff_snapshot_uses_set_joins_and_utc_request_bounds(monkeypatch):
    conn = _FakeConn(
        fetchall_results=[
            [
                {
                    "employee_id": "employee-1",
                    "employee_code": "R738-1",
                    "employee_name": "김감독",
                    "site_code": "R738",
                    "site_name": "Apple_명동",
                    "shift_type": "day",
                    "has_check_in": True,
                    "approved_leave": False,
                    "pending_leave": False,
                    "pending_attendance": True,
                }
            ]
        ]
    )
    day_start = datetime(2026, 3, 28, 15, 0, tzinfo=timezone.utc)
    day_end = datetime(2026, 3, 29, 15, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(home_router, "_table_exists", lambda *_args, **_kwargs: True)

    rows = home_router._fetch_today_staff_snapshot(
        conn,
        tenant_id="tenant-1",
        target_date=date(2026, 3, 29),
        day_start_utc=day_start,
        day_end_utc=day_end,
    )

    snapshot_sql, params = conn.executions[0]
    assert rows[0]["employee_id"] == "employee-1"
    assert "LEFT JOIN checkins" in snapshot_sql
    assert "LEFT JOIN pending_attendance" in snapshot_sql
    assert "JOIN scheduled ON scheduled.employee_id = ar.employee_id" in snapshot_sql
    assert "JOIN scheduled ON scheduled.employee_id = arq.employee_id" in snapshot_sql
    assert "arq.requested_at >=" in snapshot_sql
    assert "AT TIME ZONE" not in snapshot_sql
    assert day_start in params
    assert day_end in params


def test_fetch_hq_org_issue_rows_skips_site_status_columns_when_missing(monkeypatch):
    conn = _FakeConn(
        [
            {"employee_total": 4, "unassigned_employee_count": 1, "unlinked_count": 2},
            {"inactive_site_count": 0},
        ]
    )
    monkeypatch.setattr(home_router, "_table_exists", lambda _conn, table_name: table_name in {"employees", "sites"})
    monkeypatch.setattr(
        home_router,
        "_table_column_exists",
        lambda _conn, table_name, column_name: not (
            table_name == "sites" and column_name in {"is_active", "is_deleted"}
        ),
    )

    rows = home_router._fetch_hq_org_issue_rows(conn, tenant_id="tenant-1")

    site_sql, site_params = conn.executions[1]
    assert "COALESCE(is_active, TRUE)" not in site_sql
    assert "COALESCE(is_deleted, FALSE)" not in site_sql
    assert "TRUE = FALSE" in site_sql
    assert "FALSE = TRUE" in site_sql
    assert site_params == ("tenant-1",)
    assert rows[2].title == "비활성 지점"
