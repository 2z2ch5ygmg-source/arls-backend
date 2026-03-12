# ARLS Monthly Upload and HQ Excel Workflow Inventory

Inspection date: 2026-03-11  
Codebase inspected: `/Users/mark/Desktop/rg-arls-dev`

## 1. Current ARLS files and components

### Base monthly schedule upload workspace

Current route and view:
- Route constant: `/schedule/upload`
- Main HTML panel: `/Users/mark/Desktop/rg-arls-dev/frontend/index.html` `#scheduleUploadPanel`
- Route constants in `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`:
  - `ROUTE_SCHEDULE_UPLOAD`
  - `ROUTE_SCHEDULE_REPORTS`
  - `ROUTE_SUPPORT_STATUS`

Current upload workspace buttons:
- `schedule-download-blank-template`
- `schedule-download-latest-base`
- `preview-schedule`
- `apply-schedule`
- `schedule-reset-upload`

Current frontend implementation:
- `renderScheduleUploadWorkspace`
- `onSchedulePreview`
- `onScheduleApply`
- `onScheduleTemplateDownload`
- `onScheduleLatestBaseDownload`

Current backend implementation in `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py`:
- `GET /import/template`
- `GET /import/latest-base`
- `POST /import/preview`
- `POST /import/{batch_id}/apply`
- `_apply_canonical_schedule_import_batch`

### Upload analysis / preview / apply

Current ownership:
- ARLS already correctly owns supervisor base monthly schedule upload.

Current behavior of apply:
- writes canonical monthly schedule truth into `monthly_schedules`
- writes daytime support need rows
- creates/updates/retracts local ARLS table `sentrix_support_request_tickets`
- registers `schedule_support_roundtrip_sources` for site/month source lineage

Important finding:
- I did not find a direct ARLS runtime API call that creates live support tickets in Sentrix during schedule import apply.
- ARLS currently writes a local table named `sentrix_support_request_tickets` and logs integration events, which is a source-of-truth warning.

### Monthly export

Current backend paths:
- `GET /export/monthly-excel`
- `GET /export`
- `_collect_monthly_export_context`
- `_build_schedule_export_revision`

Current purpose:
- rebuild or export the current ARLS canonical workbook
- serve as the basis for support-demand workbook generation

### HQ 제출용 추출 in report tab

Current UI:
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html` `#scheduleSupportRoundtripPanel`
- Route: `/schedule/reports`

Visible buttons:
- `schedule-support-hq-download`
- `schedule-support-open-sentrix`
- `schedule-support-copy-artifact`

Current text on screen:
- ARLS is framed as export-only
- Sentrix is framed as submit/apply owner

Current frontend functions:
- `renderScheduleSupportRoundtripStatus`
- `loadScheduleSupportRoundtripStatus`
- `onScheduleSupportHqDownload`
- `onScheduleSupportOpenSentrix`

Current backend status/data paths:
- `GET /support-roundtrip/status`
- `GET /support-roundtrip/hq-workspace`
- `GET /support-roundtrip/hq-roster-workbook`

### ARLS support-status HQ Excel workspace

Current route and page:
- Route constant: `/ops/support-workers`
- HTML panel: `/Users/mark/Desktop/rg-arls-dev/frontend/index.html` `#supportStatusHqPanel`

Visible controls:
- `support-status-hq-refresh`
- `support-status-hq-set-scope`
- `support-status-hq-download`
- `support-status-hq-inspect`
- `support-status-hq-apply`

Current frontend functions:
- `renderSupportStatusHqWorkspace`
- `loadSupportStatusHqWorkspaceContract`
- `onSupportStatusHqDownload`
- `onSupportStatusHqInspect`
- `onSupportStatusHqApply`

Current behavior:
- download and inspect are still real ARLS actions
- apply no longer completes locally from this UI
- apply redirects into Sentrix HQ submission workspace

This is a duplicated ownership surface.

## 2. Current backend support-roundtrip and HQ roster paths

### Current ARLS-native HQ workbook endpoints

Still present and functional:
- `GET /support-roundtrip/hq-workspace`
- `GET /support-roundtrip/hq-roster-workbook`
- `POST /support-roundtrip/hq-roster-upload/inspect`
- `POST /support-roundtrip/hq-roster-upload/{batch_id}/apply`

Supporting functions:
- `_build_support_roster_hq_workspace_payload`
- `_build_support_roster_hq_download_workbook`
- `_build_support_roster_hq_upload_inspect_result`
- `_persist_sentrix_hq_roster_preview_batch`
- `_apply_sentrix_hq_roster_batch`

What these already do:
- resolve site/month workspace context
- generate the support-demand workbook
- validate metadata and sheet scope
- inspect HQ-filled workbook
- persist preview batches and review rows
- apply roster results
- queue ARLS materialization bridge actions
- generate notifications/audit records

### Legacy ARLS-native HQ upload flow

Still present:
- `GET /support-roundtrip/hq-workbook`
- `POST /support-roundtrip/hq-upload/preview`
- `POST /support-roundtrip/hq-upload/{batch_id}/apply`
- `GET /support-roundtrip/final-excel`

Legacy tables behind it:
- `schedule_support_roundtrip_sources`
- `schedule_support_roundtrip_batches`
- `schedule_support_roundtrip_rows`
- `schedule_support_roundtrip_assignments`

What legacy apply still does:
- writes support assignments directly in ARLS
- updates `schedule_support_roundtrip_sources`
- updates final-download availability flags
- merges roster outcome into ARLS-owned support roundtrip records

This proves ARLS still contains a real HQ Excel apply engine.

### ARLS bridge endpoints created for Sentrix-owned UI

Current bridge paths:
- `GET /schedules/bridge/sentrix-hq/workspace`
- `GET /schedules/bridge/sentrix-hq/artifact/download`
- `POST /schedules/bridge/sentrix-hq/upload/inspect`
- `POST /schedules/bridge/sentrix-hq/upload/{batch_id}/apply`

Current purpose:
- allow Sentrix to act as the visible owner while ARLS does the real work

This is the main ownership inversion now in production.

## 3. Whether ARLS currently has or could support a second upload mode

Answer:
- Yes, ARLS already has the backend needed for a second upload mode for HQ support-roster submission.

Evidence:
- ARLS already generates the canonical HQ workbook
- ARLS already validates the returned workbook
- ARLS already persists preview batches
- ARLS already has apply logic for roster results
- ARLS already carries artifact metadata and revision metadata in hidden workbook sheets
- ARLS already has UI shells in `지원근무자 현황 > HQ 엑셀 워크스페이스`

Practical implication:
- Restoring HQ workbook upload ownership to ARLS does not require inventing a new parser.
- It is primarily a UI ownership and routing cleanup, not a parser-from-scratch effort.

## 4. Where current ARLS ownership is wrong or duplicated

### Wrong/duplicated ownership today

There are three concurrent models in the current code:

1. Base schedule upload in ARLS
- correct owner

2. Report tab says ARLS is export-only and Sentrix owns submit/apply
- visible owner: Sentrix

3. ARLS support-status HQ panel and legacy backend still expose real HQ workbook download/upload/inspect/apply behavior
- real engine still in ARLS

This creates duplicated ownership across:
- report tab
- support-status HQ panel
- Sentrix embedded HQ workspace
- ARLS bridge endpoints
- legacy ARLS HQ upload/apply endpoints

### Most important ownership confusion

The report tab currently says:
- ARLS only exports
- Sentrix owns HQ apply

But the code still contains:
- ARLS-native workbook generation
- ARLS-native workbook inspection
- ARLS-native batch persistence
- ARLS-native apply paths

So the product messaging and technical implementation are currently inconsistent.

## 5. Which current ARLS screens and buttons should remain

### Remain safely

Keep in ARLS:
- `/schedule/upload`
  - blank template download
  - latest base download
  - preview
  - apply
- monthly export endpoints
- support-demand artifact generation
- source revision tracking
- schedule truth ownership
- final ARLS materialization of valid Sentrix-approved self-staff assignments

### Also remain as ARLS-owned HQ Excel entry

One ARLS HQ Excel surface should remain:
- either `/schedule/reports` support submission area
- or `/ops/support-workers` HQ Excel workspace

But only one should be the visible owner.

## 6. Which current ARLS screens and buttons should be restored or added

### Restore/add in ARLS

ARLS needs a single clearly-owned HQ support-roster flow that includes:
- workbook download
- filled workbook upload
- inspect/review
- apply trigger
- artifact context display
- stale/source-revision warnings

Existing parts that can be reused:
- download: `support-status-hq-download` or `schedule-support-hq-download`
- inspect: `support-status-hq-inspect`
- apply: backend already exists

What should change later:
- ARLS should stop redirecting apply to Sentrix from `support-status-hq-apply`
- ARLS should no longer tell the operator that submit/apply belongs to Sentrix

## 7. Existing artifact and revision generation paths

### Source artifact lineage

Base upload apply registers source lineage in:
- `schedule_support_roundtrip_sources`

Registration function:
- `_register_support_roundtrip_source_after_import`

Source fields tracked:
- `source_batch_id`
- `source_revision`
- `source_filename`
- `state`
- `latest_hq_batch_id`
- `latest_hq_revision`
- `latest_merged_revision`

### Workbook generation

Current workbook builders:
- `_build_support_roster_hq_download_workbook`
- `_build_support_only_workbook`

Current hidden workbook metadata:
- `tenant_code`
- `month`
- `download_scope`
- `workbook_family`
- `template_version`
- `bundle_revision`
- `site_codes_json`
- `site_revision_map_json`
- `selected_site_code`
- `selected_site_name`

These are already strong enough for ARLS-owned download/upload continuity.

## 8. Safe rollback conclusion for ARLS

ARLS already contains almost all of the pieces needed for the corrected workflow:
- supervisor base monthly ingress
- canonical workbook generation
- HQ workbook download
- HQ workbook upload inspect/apply engine
- source revision and artifact lineage
- final schedule materialization hooks

What is wrong today is not missing backend capability.
What is wrong is visible workflow ownership and duplicated UI surfaces.
