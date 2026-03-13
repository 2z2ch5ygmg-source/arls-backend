# ARLS Employee Drawer Step 2 Backend Manual Checklist

## Header
- Open the employee drawer summary endpoint for an active employee.
- Confirm header contains:
  - employee name
  - employee number
  - role display
  - employment status
  - company
  - site + site code
  - hire date
  - account link status
  - phone
  - avatar initials

## Actions
- Confirm `actions` section exists.
- Confirm quick-action flags are present:
  - `can_edit_profile`
  - `can_view_schedule`
  - `can_view_attendance`
  - `can_view_requests`
  - `can_deactivate_or_archive`
  - `can_manage_account_link`

## Overview
- Confirm overview KPIs return structured metric objects.
- Confirm overview includes:
  - monthly attendance exception count
  - next schedule summary
  - annual leave remaining days
  - pending request count
- Confirm previews are short lists, not full history blobs.

## Attendance
- Confirm attendance section exposes:
  - section state
  - empty message when no records exist
  - last 30d counts
  - recent attendance records list

## Schedule
- Confirm schedule section exposes:
  - current week count
  - next week count
  - upcoming count
  - leave-display count
  - upcoming schedules list

## Leave / Requests
- Confirm leave_requests section exposes:
  - leave used days
  - leave remaining days
  - half-day count
  - leave pending count
  - recent-window request counts
  - recent leave list
  - recent request list

## State semantics
- Confirm at least one field returns `state=unavailable` when no backend source exists.
- Confirm empty sections return `state=empty` with a readable message.
- Confirm true zero values can still return `value=0`.

## Payload size
- Confirm no full attendance/request history is returned.
- Confirm recent lists are capped to short windows only.
