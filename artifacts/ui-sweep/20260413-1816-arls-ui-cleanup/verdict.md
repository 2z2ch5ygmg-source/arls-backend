# ARLS Targeted UI Cleanup Route Sweep Verdict

- Generated: 2026-04-13T09:17:35.516Z
- Artifact root: `artifacts/ui-sweep/20260413-1816-arls-ui-cleanup`
- Base URL: http://127.0.0.1:64141/frontend/index.html
- API: mocked
- Required route/viewport pairs: 60
- Captured route/viewport pairs: 60
- Overall route completeness: PASS

## Component Family Presence

| Viewport | Route | Tabs | Filters | Steppers | KPI | Detail panels | Approval flow | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 375 | /home | n/a | n/a | n/a | WARN missing | n/a | n/a | - |
| 375 | /attendance | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 375 | /attendance?section=period&mode=list | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 375 | /attendance?section=stats&scope=attendance | WARN missing | WARN missing | n/a | WARN missing | PASS (1) | n/a | - |
| 375 | /requests | PASS (4) | WARN missing | n/a | WARN missing | WARN missing | n/a | - |
| 375 | /requests?section=documents | PASS (10) | WARN missing | n/a | WARN missing | WARN missing | n/a | - |
| 375 | /leave?tab=status | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 375 | /leave?tab=history | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 375 | /leave?tab=settings | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 375 | /schedules/calendar | PASS (2) | WARN missing | n/a | n/a | n/a | n/a | - |
| 375 | /schedules/upload | PASS (2) | WARN missing | WARN missing | n/a | n/a | n/a | - |
| 375 | /schedules/hq-upload | PASS (2) | WARN missing | WARN missing | n/a | n/a | n/a | - |
| 375 | /reports | PASS (2) | n/a | WARN missing | WARN missing | n/a | n/a | - |
| 375 | /reports/finance-download | PASS (2) | WARN missing | n/a | n/a | WARN missing | n/a | - |
| 375 | /branch/employees | WARN missing | PASS (4) | n/a | n/a | WARN missing | n/a | - |
| 375 | /branch/sites | WARN missing | PASS (3) | n/a | n/a | WARN missing | n/a | - |
| 375 | /hr?segment=apply | PASS (5) | WARN missing | n/a | n/a | n/a | WARN missing | - |
| 375 | /hr?segment=manage | PASS (5) | WARN missing | n/a | n/a | n/a | PASS (2) | - |
| 375 | /ops/support-workers | PASS (5) | WARN missing | n/a | WARN missing | WARN missing | n/a | horizontal overflow 979/375 |
| 375 | /profile | PASS (7) | n/a | n/a | n/a | n/a | n/a | - |
| 768 | /home | n/a | n/a | n/a | PASS (10) | n/a | n/a | - |
| 768 | /attendance | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 768 | /attendance?section=period&mode=list | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 768 | /attendance?section=stats&scope=attendance | WARN missing | WARN missing | n/a | WARN missing | PASS (1) | n/a | - |
| 768 | /requests | PASS (4) | WARN missing | n/a | WARN missing | WARN missing | n/a | - |
| 768 | /requests?section=documents | PASS (10) | WARN missing | n/a | WARN missing | WARN missing | n/a | - |
| 768 | /leave?tab=status | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 768 | /leave?tab=history | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 768 | /leave?tab=settings | WARN missing | WARN missing | n/a | WARN missing | n/a | n/a | - |
| 768 | /schedules/calendar | PASS (2) | WARN missing | n/a | n/a | n/a | n/a | - |
| 768 | /schedules/upload | PASS (2) | WARN missing | WARN missing | n/a | n/a | n/a | - |
| 768 | /schedules/hq-upload | PASS (2) | WARN missing | WARN missing | n/a | n/a | n/a | - |
| 768 | /reports | PASS (2) | n/a | WARN missing | WARN missing | n/a | n/a | - |
| 768 | /reports/finance-download | PASS (2) | WARN missing | n/a | n/a | WARN missing | n/a | - |
| 768 | /branch/employees | WARN missing | PASS (4) | n/a | n/a | WARN missing | n/a | - |
| 768 | /branch/sites | WARN missing | PASS (3) | n/a | n/a | WARN missing | n/a | - |
| 768 | /hr?segment=apply | PASS (5) | WARN missing | n/a | n/a | n/a | WARN missing | - |
| 768 | /hr?segment=manage | PASS (5) | WARN missing | n/a | n/a | n/a | PASS (2) | - |
| 768 | /ops/support-workers | PASS (5) | WARN missing | n/a | WARN missing | WARN missing | n/a | horizontal overflow 979/768 |
| 768 | /profile | PASS (7) | n/a | n/a | n/a | n/a | n/a | - |
| desktop | /home | n/a | n/a | n/a | PASS (10) | n/a | n/a | - |
| desktop | /attendance | WARN missing | PASS (1) | n/a | WARN missing | n/a | n/a | - |
| desktop | /attendance?section=period&mode=list | WARN missing | PASS (1) | n/a | WARN missing | n/a | n/a | - |
| desktop | /attendance?section=stats&scope=attendance | WARN missing | PASS (1) | n/a | WARN missing | PASS (1) | n/a | - |
| desktop | /requests | PASS (2) | WARN missing | n/a | WARN missing | WARN missing | n/a | - |
| desktop | /requests?section=documents | PASS (8) | WARN missing | n/a | WARN missing | WARN missing | n/a | - |
| desktop | /leave?tab=status | PASS (4) | WARN missing | n/a | WARN missing | n/a | n/a | - |
| desktop | /leave?tab=history | PASS (4) | PASS (1) | n/a | WARN missing | n/a | n/a | - |
| desktop | /leave?tab=settings | PASS (6) | WARN missing | n/a | WARN missing | n/a | n/a | - |
| desktop | /schedules/calendar | WARN missing | PASS (1) | n/a | n/a | n/a | n/a | - |
| desktop | /schedules/upload | WARN missing | WARN missing | PASS (5) | n/a | PASS (1) | n/a | - |
| desktop | /schedules/hq-upload | WARN missing | WARN missing | PASS (4) | n/a | n/a | n/a | - |
| desktop | /reports | PASS (2) | n/a | WARN missing | WARN missing | n/a | n/a | - |
| desktop | /reports/finance-download | PASS (2) | WARN missing | n/a | n/a | WARN missing | n/a | - |
| desktop | /branch/employees | WARN missing | PASS (4) | n/a | n/a | WARN missing | n/a | - |
| desktop | /branch/sites | WARN missing | PASS (3) | n/a | n/a | WARN missing | n/a | - |
| desktop | /hr?segment=apply | WARN missing | WARN missing | n/a | n/a | n/a | WARN missing | - |
| desktop | /hr?segment=manage | WARN missing | WARN missing | n/a | n/a | n/a | PASS (2) | - |
| desktop | /ops/support-workers | PASS (5) | WARN missing | n/a | WARN missing | WARN missing | n/a | - |
| desktop | /profile | PASS (7) | n/a | n/a | n/a | n/a | n/a | - |

## Artifact Contract

- `manifest.json`: route, viewport, dimensions, screenshot path, timestamps, console/network counts, checklist status.
- `console.json`: browser console messages captured during each route/viewport pass.
- `network.json`: mocked API requests plus any request failures.
- `desktop/`, `375/`, `768/`: full-page JPEG screenshots per required route.

