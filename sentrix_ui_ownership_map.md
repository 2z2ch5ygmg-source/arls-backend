# Sentrix UI Ownership Map

## Executive Summary

- The cleanest UI surface that should remain is the support-status read-model workspace at `/ops/support-workers`.
- The repo still exposes visible workbook download/upload/review surfaces inside ARLS, even though final apply now redirects into an external Sentrix workspace.
- The older schedule-side HQ upload/final-download flow is still live on the backend and still has frontend route remnants, but it looks legacy and mis-owned for the target architecture.

## 1. Current Visible UI Surfaces

| Surface | Route / page | Backing code | Ownership assessment |
| --- | --- | --- | --- |
| Support worker status list | `/ops/support-workers` | `frontend/index.html` support-status section, `frontend/js/app.js:loadSupportStatusWorkspace`, backend `/api/v1/schedules/support-status-workspace` | Keep. This is a read-model and ops workspace, not the source-of-truth writer. |
| Support-status HQ Excel workspace tab | Same page, second tab under `/ops/support-workers` | `frontend/index.html` HQ workspace section, `frontend/js/app.js:onSupportStatusHqDownload`, `onSupportStatusHqInspect`, `onSupportStatusHqApply` | Mixed / likely wrong owner. It is still visible workbook ingress inside ARLS. |
| Schedule workspace hidden HQ upload tab | Known route `/schedules/hq-upload` | `frontend/js/app.js` route table and hidden tab markup in `frontend/index.html` | Legacy / mis-owned. |
| Schedule reports review flow | `/schedules/reports?flow=review` | `frontend/js/app.js:buildScheduleReportsFinanceRoute`, hidden tab/menu mappings | Still active for schedule/finance reporting, but not a clean Sentrix submission owner. |
| External Sentrix HQ submission workspace | `https://security-ops-center-prod-002-260227135557.azurewebsites.net/#/ops/support?mode=hq-submission...` | `frontend/js/app.js:buildSentrixHqSupportSubmissionUrl` | Correct visible submission owner for the target architecture. |

## 2. Support Worker Status UI

### Route and access
- Frontend route constant:
  - `frontend/js/app.js:355`
  - `ROUTE_SUPPORT_STATUS = '/ops/support-workers'`
- View resolution:
  - `frontend/js/app.js:18500-18517`
- Access gate:
  - `frontend/js/app.js:18572-18575`
  - Manager-shell only on the frontend

### Backend API
- `app/routers/v1/schedules.py:get_support_status_workspace`
- Route:
  - `GET /api/v1/schedules/support-status-workspace`

### What it does
- Loads a combined read-model from:
  - `sentrix_support_request_tickets`
  - `support_assignment`
- Aggregates request count, assigned count, status, source labels, and worker display values.

### Assessment
- This page is read-model / display-only.
- It should remain, but only as a consumer of support truth, not as a place that owns workbook ingress or state transitions.

## 3. Support-Status HQ Workbook Workspace

### Visible page elements
- `frontend/index.html:1635-1710`
  - download step
  - upload/inspect step
  - explicit REPLACE note

### Frontend actions
- `frontend/js/app.js:7089-7122`
  - loads `/schedules/support-roundtrip/hq-workspace`
- `frontend/js/app.js:7125-7149`
  - downloads `/schedules/support-roundtrip/hq-roster-workbook`
- `frontend/js/app.js:7151-7194`
  - uploads to `/schedules/support-roundtrip/hq-roster-upload/inspect`
- `frontend/js/app.js:7197-7244`
  - does not apply locally
  - builds external Sentrix URL and opens a new window

### Ownership reading
- Download and inspect are still visibly owned by ARLS UI.
- Final apply is already treated as external Sentrix ownership.
- For the target architecture, the visible workbook ingress should move out of this UI as well, leaving at most a launcher or read-only artifact pointer.

## 4. Old Workbook Upload / Download / Review / Apply UI

### Backend routes still alive
- `GET /api/v1/schedules/support-roundtrip/hq-workbook`
- `POST /api/v1/schedules/support-roundtrip/hq-upload/preview`
- `POST /api/v1/schedules/support-roundtrip/hq-upload/{batch_id}/apply`
- `GET /api/v1/schedules/support-roundtrip/final-excel`

### Evidence
- `app/routers/v1/schedules.py:14775-15247`

### Why this looks legacy or mis-owned
- The flow still:
  - downloads a single-site workbook
  - previews local HQ upload rows
  - writes `support_assignment`
  - materializes internal schedules
  - generates a final merged Excel
- That is workbook/UI ownership inside ARLS, not the target Sentrix ownership model.

## 5. Support Submission / HQ Submission / `mode=hq-submission`

### External handoff builder
- `frontend/js/app.js:38-55`
  - `buildSentrixHqSupportSubmissionUrl`
  - Builds `#/ops/support?mode=hq-submission&month=...&site=...&artifact_id=...&revision=...&source_upload_batch_id=...&tenant_code=...`

### Call sites
- `frontend/js/app.js:onSupportStatusHqApply`
- `frontend/js/app.js:onScheduleSupportOpenSentrix`

### Ownership reading
- This is the strongest evidence that the intended visible submission owner is the external Sentrix app, not the ARLS SPA in this repo.

## 6. Redirect and Route Behavior

### Route normalization and known-route handling
- `frontend/js/app.js:18280-18307`
  - `normalizeRoutePath`
- `frontend/js/app.js:18519-18563`
  - `isKnownRoute`
- `frontend/js/app.js:18565-18604`
  - `isRouteAllowed`

### Default redirect behavior
- `frontend/js/app.js:18621-18625`
  - Dev users default to `/master/tenants`
  - Everyone else defaults to `/home`

### Hash routing
- `frontend/js/app.js:54576-54593`
  - `hashchange` handler restores/navigates the normalized route

### Important practical effect
- Legacy route aliases still normalize into current paths.
- Hidden routes are still known routes.
- That means legacy screens can remain reachable even when no longer shown in the primary UI.

## 7. Hidden or Mixed-Ownership Schedule Surfaces

### Hidden tabs
- `frontend/index.html:2037-2042`
  - `data-tab="hq-upload"` hidden
  - `data-tab="reports"` hidden

### Active route table still knows them
- `frontend/js/app.js:359-365`
  - route constants include `/schedules/hq-upload` and `/schedules/reports`
- `frontend/js/app.js:18340-18349`
  - schedule route list still treats them as real routes

### Menu remap evidence
- `frontend/js/app.js:8422`
- `frontend/js/app.js:8468`
- `frontend/js/app.js:8526`
  - menu item `schedule-hq-upload` points to `${ROUTE_SCHEDULE_REPORTS}?flow=review`

### Ownership reading
- This is a mixed-ownership transition zone.
- The route exists, the tab exists, but navigation increasingly pushes users into a report/review surface instead of a dedicated HQ-upload owner.

## 8. What Should Stay vs What Looks Legacy

### Should stay
- `/ops/support-workers`
  - Support roster status read-model
- External Sentrix handoff/open actions
  - As launchers only, if launchers are still needed

### Should be treated as legacy or mis-owned
- Visible HQ workbook download/upload/inspect UI inside ARLS
- `/schedules/hq-upload`
- old `/support-roundtrip/hq-workbook`
- old `/support-roundtrip/hq-upload/preview`
- old `/support-roundtrip/hq-upload/{batch_id}/apply`
- old `/support-roundtrip/final-excel`

## 9. Bottom Line

- Correct owner for visible submission: external Sentrix workspace.
- Correct owner for local ARLS UI: read-models, status, artifact visibility, and perhaps a thin launcher.
- Wrong-owner residue still present: workbook ingress and workbook-driven merge/apply flows inside ARLS.
