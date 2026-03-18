# ARLS Excel Workflow Map

## Workflow Summary

ARLS currently exposes three distinct Excel-oriented workflow families:

1. Canonical base monthly workbook ingress
2. New HQ roster workbook inspect/apply flow that hands normalized snapshots to Sentrix
3. Legacy support-roundtrip HQ workbook flow that still writes local roundtrip tables and overlays

## B. Excel Workflows

## 1. Base Upload Flow

### User-facing workflow

- UI shell
  - `frontend/index.html`
    - `#scheduleImportSite`
    - `#scheduleImportMonth`
    - `#scheduleImportFile`
    - `#scheduleImportMappingProfileSelect`
- Frontend controller
  - `frontend/js/app.js`
    - `onScheduleTemplateDownload`
    - `onScheduleLatestBaseDownload`
    - `onSchedulePreview`
    - `onScheduleApply`

### Backend routes

- `GET /api/v1/schedules/import/template`
- `GET /api/v1/schedules/import/latest-base`
- `POST /api/v1/schedules/import/preview`
- `POST /api/v1/schedules/import/{batch_id}/apply`

### Backend functions

- Workbook detection / parse
  - `_detect_arls_import_workbook_context`
  - `_parse_arls_canonical_import_sheet`
- Current-state export used for template/latest-base and preview comparison
  - `_collect_monthly_export_context`
  - `_build_monthly_export_workbook_from_contexts`
- Preview persistence / rebuild
  - `_build_schedule_import_preview_result`
  - `_persist_schedule_import_preview_batch`
  - `_load_canonical_schedule_import_apply_context`
- Final apply
  - `_apply_canonical_schedule_import_batch`

### What the base workbook carries

- Main body schedule cells
- Daytime need counts
- Day/night support-demand blocks
- Support worker rows for self-staff internal support
- Hidden metadata used to validate template version, support form version, month/site/export revision

## 2. Preview / Inspect / Apply Behavior

### Base upload preview

- `onSchedulePreview` posts workbook + site + month to `/api/v1/schedules/import/preview`
- `_build_schedule_import_preview_result` compares uploaded workbook to current export context
- Preview batches are stored in `schedule_import_batches`
- Raw workbook is persisted and re-read at apply time, so apply does not trust stale preview JSON alone

### Base upload apply

- `onScheduleApply` calls `/api/v1/schedules/import/{batch_id}/apply`
- `_load_canonical_schedule_import_apply_context` rebuilds parse state from persisted raw workbook
- `_apply_canonical_schedule_import_batch` applies only source-owned rows and preserves foreign lineage rows

## 3. Day/Night Support Parsing Inside Base Workbook

### Parsing and normalization

- `_parse_arls_canonical_import_sheet`
- `_build_support_request_rows_from_import_payloads`
- `_validate_support_shift_worker`
- `_resolve_import_employee_match`

### Important behaviors

- Day and night support scopes are parsed separately
- Internal self-staff support rows can materialize `support_upload_internal` schedule rows
- External or unresolved support workers stay in request/inspection semantics instead of becoming local owned schedule truth
- Existing protected or foreign lineage rows are surfaced in preview rather than blindly replaced

### Evidence from tests

- `tests/test_schedule_monthly_import_canonical.py`
  - `test_parse_canonical_sheet_reads_body_need_and_protected_sections`
  - `test_build_support_request_rows_from_import_payloads_keeps_meaningful_day_and_night_scopes`
  - `test_validate_support_shift_worker_applies_same_store_internal_candidate`
  - `test_validate_support_shift_worker_marks_other_site_candidate_for_review`
  - `test_apply_canonical_schedule_import_batch_materializes_internal_support_shift_without_overwriting_day_shift`

## 4. Support-Demand Artifact Generation

### Artifact/source registration after base upload

- `_register_support_roundtrip_source_after_import`
- `_build_support_roundtrip_status_payload`

### Storage

- `schedule_support_roundtrip_sources`
- `schedule_support_roundtrip_batches`
- `schedule_support_roundtrip_rows`
- `schedule_support_roundtrip_assignments`

### Artifact semantics

- Source artifact key is shaped as `sentrix-hq:{TENANT}:{YYYY-MM}:{SITE}:{REV}`
- Source-change detection compares raw workbook SHA, semantic signature, and source revision
- If source changed after an HQ-authored result exists, ARLS marks the roundtrip state stale (`hq_merge_stale`) and blocks downstream “final” download until re-handoff

### Evidence from tests

- `tests/test_schedule_support_roundtrip.py`
  - `test_support_roundtrip_source_changed_prefers_raw_workbook_sha`
  - `test_support_roundtrip_source_signature_treats_raw_support_demand_as_canonical`
  - `test_restore_hq_merge_state_when_same_source_reuploaded`
- `tests/test_schedule_support_roundtrip_status.py`
  - `test_status_payload_exposes_sentrix_artifact_metadata`

## 5. HQ Roster Upload / Inspect / Apply Flow

## New Sentrix-facing HQ roster flow

### Backend routes

- `GET /api/v1/schedules/support-roundtrip/status`
- `GET /api/v1/schedules/support-roundtrip/hq-workspace`
- `GET /api/v1/schedules/support-roundtrip/hq-roster-workbook`
- `POST /api/v1/schedules/support-roundtrip/hq-roster-upload/inspect`
- `POST /api/v1/schedules/support-roundtrip/hq-roster-upload/{batch_id}/apply`
- `POST /api/v1/schedules/support-roundtrip/arls-bridge/process`

### Bridge routes for Sentrix/HQ external caller

- `GET /api/v1/schedules/bridge/sentrix-hq/workspace`
- `GET /api/v1/schedules/bridge/sentrix-hq/artifact/download`
- `POST /api/v1/schedules/bridge/sentrix-hq/upload/inspect`
- `POST /api/v1/schedules/bridge/sentrix-hq/upload/{batch_id}/apply`

### Backend functions

- Workspace/download
  - `_build_support_roster_hq_workspace_payload`
  - `_build_support_roster_hq_download_workbook`
- Inspect/apply
  - `_build_support_roster_hq_upload_inspect_result`
  - `_persist_sentrix_hq_roster_preview_batch`
  - `_apply_sentrix_hq_roster_batch`
- Sentrix handoff
  - `_build_sentrix_support_roster_handoff_payload`
  - `_post_sentrix_support_roster_handoff`

### Frontend functions

- `loadScheduleSupportHqWorkspaceContract`
- `onScheduleSupportHqInspect`
- `onScheduleSupportHqApply`

### Actual ownership

- ARLS validates workbook structure, parses worker cells, computes scope review results, and sends a normalized roster snapshot to Sentrix
- ARLS does not become the final support ticket/state owner here

## Legacy HQ roundtrip flow still present

### Backend routes

- `GET /api/v1/schedules/support-roundtrip/hq-workbook`
- `POST /api/v1/schedules/support-roundtrip/hq-upload/preview`
- `POST /api/v1/schedules/support-roundtrip/hq-upload/{batch_id}/apply`
- `GET /api/v1/schedules/support-roundtrip/final-excel`

### Backend functions

- `_materialize_support_roundtrip_internal_schedule_row`

### Why it matters

- This path still writes local roundtrip tables and `HQ_ROUNDTRIP` schedule rows
- It overlaps conceptually with the newer Sentrix-facing HQ roster flow
- It is a prime duplicate-surface risk for architecture review

## 6. Workbook Assets And Packaging

### Static workbook assets

- `app/templates/monthly_schedule_template.xlsx`
- `app/templates/월간 근무표 템플릿 예시.xlsx`

### Workbook-generation helper script

- `scripts/prepare_monthly_schedule_template.py`
  - Rebuilds blank canonical template from sample workbook
  - Important regression point for Excel layout/version drift

## Exact Files / Routes / Functions To Carry Forward

- `app/routers/v1/schedules.py`
- `frontend/js/app.js`
- `frontend/index.html`
- `app/templates/monthly_schedule_template.xlsx`
- `scripts/prepare_monthly_schedule_template.py`
- `tests/test_schedule_monthly_import_canonical.py`
- `tests/test_schedule_support_roundtrip.py`
- `tests/test_schedule_support_roundtrip_status.py`

## Architecture Review Notes

- The canonical base upload flow is the visible Excel ingress owner for monthly schedules.
- The HQ roster flow exists in both a new Sentrix-boundary form and a legacy local roundtrip form.
- Support-demand artifact generation is tightly coupled to workbook semantics and is not cleanly isolated from the schedule router monolith.
