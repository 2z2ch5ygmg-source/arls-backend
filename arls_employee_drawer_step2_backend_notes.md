# ARLS Employee Drawer Step 2 Backend Notes

## Files changed
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/employees.py`
- `/Users/mark/Desktop/rg-arls-dev/app/employee_drawer_schemas.py`
- `/Users/mark/Desktop/rg-arls-dev/tests/test_employee_drawer_summary_contract.py`

## What changed
- Added a consolidated backend response for the employee detail drawer:
  - `GET /api/v1/employees/{employee_id}/drawer-summary`
- Added compact nested contract sections:
  - `header`
  - `actions`
  - `overview`
  - `attendance`
  - `schedule`
  - `leave_requests`
  - `meta`
- Kept the existing employee list/detail flows intact; this is an additive contract.

## Data sources used
- Employee identity:
  - `employees`
  - `sites`
  - `companies`
  - latest active `arls_users`
- Attendance:
  - `attendance_records`
- Schedule:
  - `monthly_schedules`
- Leave:
  - `leave_requests`
- Request history:
  - `attendance_requests`
  - `document_requests`

## Aggregation logic added
- Header identity is resolved from employee/site/company/account-link fields in one query.
- Attendance summary:
  - last 30 days grouped by local work date
  - normal vs missing derived from check-in/check-out presence
  - recent list capped to 7
- Schedule summary:
  - current week / next week / upcoming counts
  - upcoming list capped to 5
- Leave/request summary:
  - approved leave usage and half-day counts
  - pending leave count
  - attendance/document request counts for recent window
  - recent leave and request lists capped to 5

## Zero / empty / unavailable handling
- Added explicit metric state model:
  - `ok`
  - `empty`
  - `unavailable`
- Section payloads also expose `state` and `empty_message` so the frontend can compress no-data areas.
- Example strategy:
  - true zero count => `value=0, state=ok`
  - no recent records => section `state=empty`
  - no connected source => `state=unavailable`

## Compatibility strategy
- Existing employee endpoints are untouched.
- The new drawer contract is additive and can be adopted by the rebuilt frontend drawer without breaking the current UI.
- `meta.compatibility` documents how old tab concepts map into the new summary sections.

## Intentionally not changed
- No frontend drawer rendering in this pass
- No Sentrix integration changes
- No new leave-balance source creation
- No redesign of employee list or org hub routes
