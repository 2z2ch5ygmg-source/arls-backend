# ARLS Instant Tab Latency Verification Notes

Tracked probe: `qa/arls-instant-tab-latency-probe.mjs`

## Probe usage

```bash
ARLS_PROBE_BASE_URL="https://<frontend-host>/index.html" \
  node qa/arls-instant-tab-latency-probe.mjs \
  --storage-state output/auth-state.json \
  --output output/arls-instant-tab-latency/probe.json
```

The probe records first-visible shell/cache/skeleton timing separately from API-settled timing and writes both JSON and Markdown reports. Use `--dry-run` to print the route/action matrix without opening Chromium.

## Priority route set

`#/home`, `#/attendance`, `#/requests`, `#/feature/notices`, `#/schedules/calendar`, `#/schedules/list`, `#/schedules/upload`, `#/schedules/hq-upload`, `#/reports?tab=finance`, `#/reports/finance-download`, `#/branch/employees`, `#/branch/sites`, `#/leave`, `#/profile`, `#/ops`, `#/ops/support-workers`, `#/calendar/month`, `#/hr`.

## Pre-action shell checks

Finance download workspace entry, schedule upload workspace entry, support-worker upload workspace entry, employee import route, calendar week/day switches, and profile logs segment.

## Stale-task race check

The probe rapidly moves `#/requests` -> `#/profile` and asserts that the first route cannot leave the app on the wrong hash, reveal the stale panel, leave stale active perf state, or emit a route-entry error after the second route is active.

## Targeted pytest command

```bash
python -m pytest \
  tests/test_schedule_finance_download_workspace.py \
  tests/test_schedule_finance_submission.py \
  tests/test_schedule_import_raw_workbook_runtime.py \
  tests/test_schedule_support_roundtrip.py \
  tests/test_leave_router_runtime.py \
  tests/test_leave_request_review_runtime.py \
  tests/test_notice_permissions.py
```

## Mutation/job smoke checks

- Finance final upload/download: progress/loading remains visible until the backend response completes; no success toast before completion.
- Schedule base upload: inspect/apply buttons stay busy through API completion and review state refreshes after completion.
- Support-worker HQ upload/download/apply: file/progress state stays honest while roundtrip APIs run and refreshed results match the backend response.
- Leave/request submit/apply/delete/final actions: destructive or state-changing success is only shown after the awaited API resolves.
