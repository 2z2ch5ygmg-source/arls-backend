# ARLS Employee Drawer Summary Contract

## Endpoint
- `GET /api/v1/employees/{employee_id}/drawer-summary`

## Top-level response shape
- `header`
- `actions`
- `overview`
- `attendance`
- `schedule`
- `leave_requests`
- `meta`

## Header fields
- `employee_id`
- `employee_name`
- `employee_number`
- `manager_or_admin_number`
- `role_display`
- `employment_status`
- `company_name`
- `site_name`
- `site_code`
- `hire_date`
- `leave_date`
- `account_link_status`
- `phone`
- `avatar_initials`
- `subtitle`

## Actions section
- `can_edit_profile`
- `can_view_schedule`
- `can_view_attendance`
- `can_view_requests`
- `can_deactivate_or_archive`
- `can_manage_account_link`
- `disabled_reasons`
- `route_targets`

## Overview KPI fields
- `monthly_attendance_exception_count`
- `next_schedule_summary`
- `annual_leave_remaining_days`
- `pending_request_count`
- `workforce_info`
- `recent_attendance_preview`
- `recent_request_preview`
- `upcoming_schedule_preview`

## Attendance section
- `state`
- `empty_message`
- `last_30d_normal_count`
- `last_30d_late_count`
- `last_30d_missing_count`
- `last_30d_leave_or_excused_count`
- `recent_attendance_records`

### Attendance record fields
- `date`
- `scheduled_start`
- `scheduled_end`
- `check_in`
- `check_out`
- `status_label`
- `notes`

## Schedule section
- `state`
- `empty_message`
- `current_week_assignment_count`
- `next_week_assignment_count`
- `upcoming_schedule_count`
- `current_leave_display_count`
- `upcoming_schedules`

### Schedule item fields
- `date`
- `shift_kind`
- `start_time`
- `end_time`
- `site_name`
- `source_lineage`
- `display_label`

## Leave / request section
- `state`
- `empty_message`
- `leave_used_days`
- `leave_remaining_days`
- `half_day_count`
- `leave_pending_count`
- `total_request_count_recent_window`
- `pending_request_count`
- `approved_request_count_recent_window`
- `rejected_request_count_recent_window`
- `recent_leave_entries`
- `recent_request_entries`

### Leave entry fields
- `leave_type`
- `start_date`
- `end_date`
- `duration`
- `status`
- `requested_at`

### Request entry fields
- `request_type`
- `requested_at`
- `status`
- `short_summary`

## Zero / empty / unavailable state rules
- Metrics use:
  - `value`
  - `state`
  - `empty_message`
- Allowed metric states:
  - `ok`
  - `empty`
  - `unavailable`
- Sections such as `attendance`, `schedule`, `leave_requests` also expose:
  - `state`
  - `empty_message`

### Interpretation
- Actual zero:
  - `value = 0`
  - `state = "ok"`
- No recent data:
  - section `state = "empty"`
  - `empty_message` present
- Source unavailable:
  - metric or section `state = "unavailable"`
  - `empty_message` explains the gap

## Payload size constraints
- No full history tables
- Recent attendance list capped to 7
- Upcoming schedule list capped to 5
- Recent leave list capped to 5
- Recent request list capped to 5
- Overview previews are short subsets only

## Old-to-new compatibility notes
- Old `기본정보` concept maps to:
  - `header`
  - `overview.workforce_info`
- Old `출퇴근 요약` maps to:
  - `attendance`
- Old `스케줄 요약` maps to:
  - `schedule`
- Old `휴가 요약` + `요청 이력` maps to:
  - `leave_requests`

## Intentionally excluded in this phase
- Full history pagination
- New leave-balance source creation
- Sentrix data
- Mobile-specific variants
