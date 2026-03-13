from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EmployeeDrawerMetricOut(BaseModel):
    value: Any | None = None
    state: Literal["ok", "empty", "unavailable"] = "ok"
    empty_message: Optional[str] = None


class EmployeeDrawerHeaderOut(BaseModel):
    employee_id: UUID
    employee_name: str
    employee_number: str
    manager_or_admin_number: Optional[str] = None
    role_display: Optional[str] = None
    employment_status: str
    company_name: Optional[str] = None
    site_name: Optional[str] = None
    site_code: Optional[str] = None
    hire_date: Optional[date] = None
    leave_date: Optional[date] = None
    account_link_status: Optional[str] = None
    phone: Optional[str] = None
    avatar_initials: Optional[str] = None
    subtitle: Optional[str] = None


class EmployeeDrawerActionsOut(BaseModel):
    can_edit_profile: bool = False
    can_view_schedule: bool = True
    can_view_attendance: bool = True
    can_view_requests: bool = True
    can_deactivate_or_archive: bool = False
    can_manage_account_link: bool = False
    disabled_reasons: dict[str, str] = Field(default_factory=dict)
    route_targets: dict[str, str] = Field(default_factory=dict)


class EmployeeDrawerWorkforceInfoOut(BaseModel):
    company_name: Optional[str] = None
    site_name: Optional[str] = None
    site_code: Optional[str] = None
    employee_number: Optional[str] = None
    manager_or_admin_number: Optional[str] = None
    role_display: Optional[str] = None
    employment_status: Optional[str] = None
    account_link_status: Optional[str] = None
    hire_date: Optional[date] = None
    leave_date: Optional[date] = None
    phone: Optional[str] = None


class EmployeeDrawerAttendanceRecordOut(BaseModel):
    date: date
    scheduled_start: Optional[time] = None
    scheduled_end: Optional[time] = None
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    status_label: str
    notes: Optional[str] = None


class EmployeeDrawerScheduleItemOut(BaseModel):
    date: date
    shift_kind: str
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    site_name: Optional[str] = None
    source_lineage: Optional[str] = None
    display_label: str


class EmployeeDrawerLeaveEntryOut(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    duration: float
    status: Optional[str] = None
    requested_at: Optional[datetime] = None


class EmployeeDrawerRequestEntryOut(BaseModel):
    request_type: str
    requested_at: datetime
    status: str
    short_summary: Optional[str] = None


class EmployeeDrawerOverviewOut(BaseModel):
    monthly_attendance_exception_count: EmployeeDrawerMetricOut
    next_schedule_summary: EmployeeDrawerMetricOut
    annual_leave_remaining_days: EmployeeDrawerMetricOut
    pending_request_count: EmployeeDrawerMetricOut
    workforce_info: EmployeeDrawerWorkforceInfoOut
    recent_attendance_preview: list[EmployeeDrawerAttendanceRecordOut] = Field(default_factory=list)
    recent_request_preview: list[EmployeeDrawerRequestEntryOut] = Field(default_factory=list)
    upcoming_schedule_preview: list[EmployeeDrawerScheduleItemOut] = Field(default_factory=list)


class EmployeeDrawerAttendanceOut(BaseModel):
    state: Literal["ok", "empty", "unavailable"] = "ok"
    empty_message: Optional[str] = None
    last_30d_normal_count: EmployeeDrawerMetricOut
    last_30d_late_count: EmployeeDrawerMetricOut
    last_30d_missing_count: EmployeeDrawerMetricOut
    last_30d_leave_or_excused_count: EmployeeDrawerMetricOut
    recent_attendance_records: list[EmployeeDrawerAttendanceRecordOut] = Field(default_factory=list)


class EmployeeDrawerScheduleOut(BaseModel):
    state: Literal["ok", "empty", "unavailable"] = "ok"
    empty_message: Optional[str] = None
    current_week_assignment_count: EmployeeDrawerMetricOut
    next_week_assignment_count: EmployeeDrawerMetricOut
    upcoming_schedule_count: EmployeeDrawerMetricOut
    current_leave_display_count: EmployeeDrawerMetricOut
    upcoming_schedules: list[EmployeeDrawerScheduleItemOut] = Field(default_factory=list)


class EmployeeDrawerLeaveRequestsOut(BaseModel):
    state: Literal["ok", "empty", "unavailable"] = "ok"
    empty_message: Optional[str] = None
    leave_used_days: EmployeeDrawerMetricOut
    leave_remaining_days: EmployeeDrawerMetricOut
    half_day_count: EmployeeDrawerMetricOut
    leave_pending_count: EmployeeDrawerMetricOut
    total_request_count_recent_window: EmployeeDrawerMetricOut
    pending_request_count: EmployeeDrawerMetricOut
    approved_request_count_recent_window: EmployeeDrawerMetricOut
    rejected_request_count_recent_window: EmployeeDrawerMetricOut
    recent_leave_entries: list[EmployeeDrawerLeaveEntryOut] = Field(default_factory=list)
    recent_request_entries: list[EmployeeDrawerRequestEntryOut] = Field(default_factory=list)


class EmployeeDrawerMetaOut(BaseModel):
    contract_version: str = "employee_drawer_summary.v1"
    loaded_at: datetime
    tenant_code: Optional[str] = None
    sources: dict[str, str] = Field(default_factory=dict)
    compatibility: dict[str, str] = Field(default_factory=dict)


class EmployeeDrawerSummaryOut(BaseModel):
    header: EmployeeDrawerHeaderOut
    actions: EmployeeDrawerActionsOut
    overview: EmployeeDrawerOverviewOut
    attendance: EmployeeDrawerAttendanceOut
    schedule: EmployeeDrawerScheduleOut
    leave_requests: EmployeeDrawerLeaveRequestsOut
    meta: EmployeeDrawerMetaOut
