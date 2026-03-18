# ARLS Sentrix Boundary Map

## Boundary Summary

- Outbound from ARLS to Sentrix:
  - normalized support-demand/request snapshots from canonical monthly import
  - normalized HQ roster snapshots from HQ workbook apply
- Inbound from Sentrix to ARLS:
  - support-origin materialization/retract actions that ARLS consumes and writes into `monthly_schedules`
- Important caveat:
  - `app/routers/v1/integrations.py` still contains a legacy parallel Sentrix/SOC materialization path

## E. Sentrix Integration Boundary

## 1. ARLS -> Sentrix Normalized Roster Snapshot Handoff

### Common handoff builder

- `app/routers/v1/schedules.py`
  - `_build_sentrix_support_roster_handoff_payload`
  - `_post_sentrix_support_roster_handoff`

### Network/config seam

- `app/config.py`
  - `soc_support_roster_handoff_url`
  - `sentrix_support_bridge_token`

### Payload characteristics

- `snapshot_mode = "replace"`
- `replace_scope`
  - `mode = "site_month_full_snapshot"`
  - `month`
  - `site_codes`
  - `shift_kinds`
  - `date_scope.start_date`
  - `date_scope.end_date`
  - `source_upload_batch_id`
- worker rows include identity hints and workbook lineage such as:
  - `canonical_employee_id_hint`
  - `source_cell_ref`
  - self-staff flag

### Evidence

- `tests/test_schedule_support_roundtrip.py`
  - `test_build_sentrix_support_roster_handoff_payload_preserves_scope_lineage`
- `tests/test_schedule_monthly_import_canonical.py`
  - `test_sync_canonical_schedule_import_sentrix_support_requests_posts_full_replace_snapshot`
  - `test_sync_canonical_schedule_import_sentrix_support_requests_sends_empty_scope_snapshot_for_removed_day_requests`

## 2. ARLS -> Sentrix Support-Demand / Ticket-Related Payloads

### Canonical monthly import path

- Route
  - `POST /api/v1/schedules/import/{batch_id}/apply`
- Functions
  - `_build_support_request_rows_from_import_payloads`
  - `_build_canonical_schedule_import_sentrix_scope_apply_specs`
  - `_sync_canonical_schedule_import_sentrix_support_requests`
  - `_upsert_sentrix_support_request_ticket_row`
  - `_retract_sentrix_support_request_ticket_row`

### Architectural meaning

- Base workbook support-demand scopes are normalized by ARLS
- ARLS sends a replace-snapshot handoff to Sentrix
- ARLS keeps request-ticket tracking rows locally, but that is not the final ticket-state authority

## 3. HQ Roster Handoff Boundary

### Routes

- `GET /api/v1/schedules/support-roundtrip/hq-workspace`
- `GET /api/v1/schedules/support-roundtrip/hq-roster-workbook`
- `POST /api/v1/schedules/support-roundtrip/hq-roster-upload/inspect`
- `POST /api/v1/schedules/support-roundtrip/hq-roster-upload/{batch_id}/apply`

### Functions

- `_build_support_roster_hq_workspace_payload`
- `_build_support_roster_hq_download_workbook`
- `_build_support_roster_hq_upload_inspect_result`
- `_persist_sentrix_hq_roster_preview_batch`
- `_apply_sentrix_hq_roster_batch`
- `_build_sentrix_support_roster_handoff_payload`
- `_post_sentrix_support_roster_handoff`

### Storage

- `sentrix_support_hq_roster_batches`
- `sentrix_support_hq_roster_rows`
- `sentrix_support_roster_snapshots`
- `sentrix_support_roster_snapshot_entries`
- `sentrix_support_notification_audit`
- `sentrix_support_arls_bridge_actions`

## 4. Sentrix -> ARLS Support-Origin Materialization / Retract Consumption

### Processing entrypoint

- `POST /api/v1/schedules/support-roundtrip/arls-bridge/process`

### Bridge-authenticated external router

- `app/routers/v1/schedules.py`
  - `bridge_router = APIRouter(prefix="/schedules/bridge/sentrix-hq", ...)`
  - `_require_sentrix_support_bridge_token`
  - `_resolve_sentrix_bridge_tenant`
  - `_build_sentrix_bridge_actor`

### Materialization functions

- `_load_sentrix_support_materialization_row`
- `_upsert_sentrix_support_materialization_row`
- `_apply_sentrix_support_bridge_action`
- `_process_sentrix_support_arls_bridge_actions`
- `_publish_sentrix_support_schedule_realtime_event`

### Materialization behavior

- If ARLS finds an existing row with same Sentrix lineage, it updates it
- If a foreign/manual/base row already occupies the slot, ARLS links the materialization instead of overwriting
- Retract removes ARLS-owned Sentrix materialized rows or marks the materialization retracted

### Persistence

- `sentrix_support_schedule_materializations`
- `monthly_schedules` rows with `source='sentrix_support_ticket'`

### Evidence

- `tests/test_arls_support_origin_materialization.py`
  - upsert/update without duplicate
  - retract fallback behavior
  - linked-existing-row preservation
- `tests/test_sentrix_support_schedule_realtime.py`
  - realtime publish after bridge processing

## 5. Legacy Parallel Boundary Still Active

### File

- `app/routers/v1/integrations.py`

### Functions

- `_upsert_materialized_schedule_row`
- `_retract_materialized_schedule_rows_for_ticket`
- `_retract_materialized_schedule_rows_for_employees`
- `_retract_support_origin_schedule_rows`
- `_apply_internal_support_schedule_targets`
- `_retract_internal_support_schedule_targets`
- `_apply_support_assignment_for_ticket`

### Routes

- `POST /api/v1/integrations/soc/events`
- `POST /api/v1/integrations/google-sheets/support-assignments/webhook`

### Why this is a boundary risk

- It still writes `SOC` / `sentrix_support_ticket` schedule rows directly
- It still manages support assignments through legacy webhook and SOC event payloads
- It overlaps with the newer bridge/materialization path in `schedules.py`

## 6. Exact Files / Routes / Contracts

### Primary boundary files

- `app/routers/v1/schedules.py`
- `app/routers/v1/integrations.py`
- `app/config.py`
- `app/schemas.py`
- `migrations/011_schedule_import_apply_and_sentrix_tickets.sql`
- `migrations/012_sentrix_hq_roster_batches.sql`
- `migrations/013_sentrix_hq_postprocessing.sql`
- `migrations/014_arls_sentrix_support_materialization.sql`

### Relevant schema classes

- `SupportRoundtripStatusOut`
- `SupportRosterHqWorkspaceOut`
- `SupportRosterHqUploadInspectOut`
- `SupportRosterHqApplyOut`
- `ImportPreviewOut`
- `ImportApplyOut`

## Architecture Review Notes

- ARLS has a clear outbound Sentrix handoff boundary in `schedules.py`, but it is surrounded by legacy overlap.
- The cleanest architectural seam is the replace-snapshot payload builder/poster pair.
- The riskiest seam is duplicated inbound support-origin materialization across `schedules.py` and `integrations.py`.
