# Sentrix HQ Support Submission Inventory

Inspection date: 2026-03-11  
Codebase inspected: `/Users/mark/Desktop/security-ops-center`

## 1. Current Sentrix routes, pages, and components

### HQ support submission workspace

Current UI owner:
- Route: `#/ops/support`
- Deeplink mode: `#/ops/support?mode=hq-submission&month=...&site=...&artifact_id=...&revision=...&source_upload_batch_id=...&tenant_code=...`
- Main page container: `/Users/mark/Desktop/security-ops-center/static/index.html`
- Embedded workspace section: `#opsSupportSubmissionWorkspace` in `/Users/mark/Desktop/security-ops-center/static/index.html`
- Frontend state/rendering: `/Users/mark/Desktop/security-ops-center/static/app.js`

Current frontend functions:
- `syncOpsSupportSubmissionContextFromHash`
- `buildOpsSupportSubmissionQuery`
- `getOpsSupportSubmissionStateModel`
- `renderOpsSupportSubmissionWorkspace`
- `loadOpsSupportSubmissionWorkspace`
- `onOpsSupportSubmissionDownload`
- `onOpsSupportSubmissionInspect`
- `onOpsSupportSubmissionApply`
- `openOpsSupportRosterPage`

Current behavior:
- The HQ submission workspace is not a standalone screen.
- It is embedded inside the Sentrix `지원근무자 현황` screen.
- Sentrix presents itself as the Excel workflow owner for download, upload, inspect, and apply.
- The actual parsing and apply work is not implemented in Sentrix itself. Sentrix proxies those actions to ARLS.

### Support roster / support worker status screen

Current UI:
- Route: `#/ops/support`
- Page purpose: monthly support request and confirmed-worker operations
- File: `/Users/mark/Desktop/security-ops-center/static/index.html`

Main controls on the page:
- Month navigator
- View switch: calendar / list
- Filters:
  - `#opsSupportTypeFilter`
  - `#opsSupportSiteFilter`
  - `#opsSupportStatusFilter`
- Page actions:
  - save current roster
  - export drawer
  - today
  - refresh

This page is the correct Sentrix domain area for:
- support request review
- confirmed worker editing
- ticket state reconciliation
- support worker operational follow-up

It is not the correct owner for raw Excel download/upload workflow under the corrected business rule.

## 2. Current buttons, actions, and menus related to workbook flow

### HQ submission workspace buttons

Visible buttons in `/Users/mark/Desktop/security-ops-center/static/index.html`:
- `data-action="ops-support-submission-refresh"`: `컨텍스트 새로고침`
- `data-action="ops-support-submission-download"`: `ARLS artifact 다운로드`
- file input `#opsSupportSubmissionFileInput`: HQ 작성 완료 workbook upload
- `data-action="ops-support-submission-inspect"`: `검토`
- `data-action="ops-support-submission-apply"`: `적용`

What each does today:
- `refresh`
  - reloads workspace context from `/api/ops/support-submissions/workspace`
- `download`
  - downloads workbook through Sentrix endpoint `/api/ops/support-submissions/download`
  - that endpoint forwards to ARLS bridge
- `inspect`
  - uploads base64 workbook to Sentrix endpoint `/api/ops/support-submissions/inspect`
  - Sentrix forwards to ARLS bridge
- `apply`
  - calls Sentrix endpoint `/api/ops/support-submissions/{batch_id}/apply`
  - Sentrix forwards to ARLS bridge

### Menus and entry points

Current menu dependency:
- The workspace is not on a separate menu item.
- It appears inside the `지원근무자 현황` page.
- ARLS report-tab handoff currently opens this Sentrix page directly.

### Review/apply ownership status

Current visible ownership:
- Sentrix appears to own review/apply from the operator's point of view.

Current technical ownership:
- ARLS owns workbook inspection, batch creation, and apply execution.

This is the primary ownership mistake.

## 3. Current backend and service paths in Sentrix

### Workspace bootstrap and proxy endpoints

Defined in `/Users/mark/Desktop/security-ops-center/app.py`:
- `GET /api/ops/support-submissions/workspace`
  - handler: `handle_get_ops_support_submission_workspace`
- `GET /api/ops/support-submissions/download`
  - handler: `handle_download_ops_support_submission_artifact`
- `PATCH /api/ops/support-submissions/inspect`
  - handler: `handle_post_ops_support_submission_inspect`
- `PATCH /api/ops/support-submissions/{batch_id}/apply`
  - handler: `handle_post_ops_support_submission_apply`

Important note:
- The handlers are wired under `do_PATCH` in the HTTP server, while the frontend code currently issues `POST` for inspect/apply in `/Users/mark/Desktop/security-ops-center/static/app.js`.
- That method wiring should be treated as a fragility point when removing or relocating this flow.

### ARLS bridge client code inside Sentrix

Defined in `/Users/mark/Desktop/security-ops-center/app.py`:
- `build_arls_support_bridge_url`
- `_build_arls_support_bridge_headers`
- `_request_arls_support_bridge_json`
- `_request_arls_support_bridge_binary`
- `_build_support_submission_workspace_payload`
- `_unwrap_arls_bridge_payload`
- `_load_support_submission_site_context`

Bridge purpose:
- Sentrix does not build the workbook.
- Sentrix does not parse the workbook locally.
- Sentrix does not apply the workbook locally.
- Sentrix calls ARLS bridge endpoints and repackages the result.

### Ticket state reconciliation and support worker operations

Correct Sentrix-owned support engine paths:
- `GET /api/ops/support-requests`
  - handler: `handle_get_ops_support_requests`
- `PATCH /api/ops/support-requests/{support_request_id}/confirmed-workers`
  - handler: `handle_patch_ops_support_confirmed_workers`

Key helper functions in `/Users/mark/Desktop/security-ops-center/app.py`:
- `normalize_support_confirmed_workers`
- `normalize_support_confirmed_workers_from_payload`
- `build_support_confirmed_workers_legacy_fields`
- `normalize_support_request_status_key`
- `get_support_request_status_label`
- `enqueue_hr_approval_outbox_event`
- `send_apns_to_users_async`

These are the actual Sentrix state engine pieces to keep.

### Notifications

Current notification paths in Sentrix:
- APNS push via `send_apns_to_users_async`
- broker fanout via `BROKER.broadcast(...)`
- ARLS-facing webhook/outbox via `enqueue_hr_approval_outbox_event` and `_send_hr_webhook`

ARLS webhook target derived by Sentrix:
- `/api/v1/integrations/soc/events`

This is a legitimate Sentrix-owned outbound integration and should stay.

## 4. Keep / remove / move / UI-hide decision inventory

### Keep in Sentrix

Keep:
- `#/ops/support` support worker status page
- support request list/calendar operations
- confirmed worker save/edit flow
- ticket state reconciliation
- support request status transitions
- APNS / broker / outbox notification flow
- Sentrix truth around support request ticket state and support worker operations

Reason:
- These match the intended role of Sentrix as support-worker state engine, roster truth, and ticket truth.

### Remove from Sentrix as workflow owner

Remove or move out:
- embedded HQ Excel workspace `#opsSupportSubmissionWorkspace`
- Sentrix-owned workbook download action
- Sentrix-owned workbook upload action
- Sentrix-owned inspect action
- Sentrix-owned apply action
- `/api/ops/support-submissions/*` proxy layer as user-facing Excel workflow surface

Reason:
- Under the corrected business rule, HQ downloads and uploads Excel through ARLS, not Sentrix.
- Sentrix should consume structured results, not own the workbook UI.

### UI-hide only candidates during transition

Hide first if a two-step rollback is needed:
- `#opsSupportSubmissionWorkspace`
- deeplink mode `mode=hq-submission`
- ARLS-origin handoff links into Sentrix HQ submission mode

Reason:
- This avoids breaking the rest of `/ops/support` while ownership is transferred back to ARLS.

## 5. Data migration risk if Sentrix upload/download UI is removed

### Low-risk areas

Low or no migration need:
- Sentrix frontend workspace state is transient browser state only.
- No dedicated Sentrix database tables were found for HQ workbook batches, rows, or workbook artifacts.
- The Sentrix support submission endpoints are bridge/proxy endpoints, not independent storage owners.

### Real persistence that must remain untouched

Do not disturb:
- Sentrix `tickets` / `tickets_template_fields` support request truth
- confirmed worker fields and support request statuses
- notification/outbox records tied to support operations

### What is not stored in Sentrix

Not stored in Sentrix:
- canonical HQ workbook preview batches
- parsed workbook review rows
- ARLS artifact metadata as durable submission records

Those are currently stored and managed in ARLS.

## 6. Route, deeplink, and menu dependencies that would break

If Sentrix HQ submission UI is removed without ARLS replacement, these will break:
- ARLS report-tab button `Sentrix에서 지원근무자 제출 열기`
- ARLS support-status apply redirection into Sentrix
- existing operator bookmarks to `#/ops/support?mode=hq-submission...`
- any runbooks/documentation telling HQ to do Excel submission in Sentrix

What should not break if the removal is done correctly:
- the main Sentrix `지원근무자 현황` screen
- support request filters/month navigation
- support worker confirmed-worker save flow
- notifications and ticket reconciliation

## 7. Safe rollback conclusion for Sentrix

Correct rollback target:
- Sentrix keeps support request operations and support worker state ownership.
- Sentrix should stop owning raw workbook download/upload/review/apply UI.
- Sentrix should no longer be the operator-facing Excel ingress screen.

Recommended classification summary:
- Keep: support status engine and ticket truth
- Remove/move out: HQ workbook workspace and bridge-facing operator controls
- UI-hide during transition: HQ submission section and hash-mode deeplink
- No major Sentrix-side data migration required for the workspace removal itself
