# Sentrix Support Domain Map

## Executive Summary

- The strongest local support-domain logic lives in `app/routers/v1/schedules.py` and the Sentrix migrations.
- The repo still models Sentrix as ticket truth, roster truth, state engine, notification owner, and ARLS bridge emitter.
- The active runtime write path has moved outward: both canonical schedule import sync and HQ roster apply now post a replace-style handoff to an external Sentrix endpoint instead of completing the full local state engine.
- Several local “core” functions still exist but have no in-repo caller. That is important transition-state evidence, not dead certainty about production behavior outside this repo.

## 1. Ticket Truth

### Schema
- `migrations/011_schedule_import_apply_and_sentrix_tickets.sql:75-101`
  - Defines `sentrix_support_request_tickets`.
  - Unique scope is `(tenant_id, site_id, work_date, shift_kind, source_workflow)`.
  - `request_count`, `work_purpose`, `status`, `source_batch_id`, `source_revision`, and `detail_json` live here.

### Readers
- `app/routers/v1/schedules.py:_load_sentrix_support_ticket_scope_map`
  - Loads active request tickets by tenant/month/site for HQ roster inspect.
- `app/routers/v1/schedules.py:_load_support_status_workspace_rows`
  - Reads `sentrix_support_request_tickets` for the support-status UI.

### Local writers
- `app/routers/v1/schedules.py:_upsert_sentrix_support_request_ticket_row`
- `app/routers/v1/schedules.py:_retract_sentrix_support_request_ticket_row`

### Important evidence
- A repo-wide search found only the definitions of `_upsert_sentrix_support_request_ticket_row` and `_retract_sentrix_support_request_ticket_row`; no in-repo caller was found.
- The active canonical-import sync path is `app/routers/v1/schedules.py:_sync_canonical_schedule_import_sentrix_support_requests`, and it posts outward via `_post_sentrix_support_roster_handoff` instead of calling the local upsert/retract helpers.

### Current reading
- The table still represents the intended ticket truth model.
- In this repo, the direct local writer path is no longer the active write path.

## 2. Roster Truth

### Preview / inspect persistence
- `migrations/012_sentrix_hq_roster_batches.sql:1-60`
  - `sentrix_support_hq_roster_batches`
  - `sentrix_support_hq_roster_rows`
- `app/routers/v1/schedules.py:_persist_sentrix_hq_roster_preview_batch`
  - Persists HQ roster inspect results before apply.

### Intended final roster truth
- `migrations/013_sentrix_hq_postprocessing.sql:23-93`
  - `sentrix_support_roster_snapshots`
  - `sentrix_support_roster_snapshot_entries`
- `app/routers/v1/schedules.py:_persist_sentrix_hq_roster_snapshot`
  - Builds and persists current-vs-previous snapshot state per ticket.

### Important evidence
- A repo-wide search found only the definition of `_persist_sentrix_hq_roster_snapshot`; no in-repo caller was found.

### Current reading
- Preview batch tables are definitely live.
- Snapshot tables look like the intended final roster truth, but the local persistence path is currently orphaned in this repo.

## 3. Confirmed Worker Persistence

### Worker parsing and normalization
- `app/routers/v1/schedules.py:_parse_sentrix_hq_worker_cell`
  - Parses worker cells, including self-staff format validation and employee matching.
- `app/routers/v1/schedules.py:_build_sentrix_hq_snapshot_entries`
  - Normalizes confirmed worker entries into snapshot payloads.

### Persistence target
- `migrations/013_sentrix_hq_postprocessing.sql:56-93`
  - `sentrix_support_roster_snapshot_entries`
  - Stores slot index, normalized affiliation/name, display value, self-staff flag, employee linkage, worker type, validity, and payload JSON.

### Current reading
- Confirmed workers are normalized very explicitly in code.
- Local persistence is modeled, but the final snapshot writer is not wired from the active apply path in this repo.

## 4. Approved / Pending Engine

### Main calculator
- `app/routers/v1/schedules.py:_build_support_roster_hq_upload_inspect_result`

### Core rules
- `request_count = max(int((artifact_scope or {}).get("request_count") or 0), 0)`
- `valid_filled_count == request_count`
  - `target_status = auto_approved`
- `valid_filled_count < request_count`
  - `target_status = approval_pending`
  - Adds `REQUEST_COUNT_MISMATCH_UNDER`
- `valid_filled_count > request_count`
  - `target_status = approval_pending`
  - Adds `REQUEST_COUNT_MISMATCH_OVER`
  - Overflow workers are marked over-capacity

### State normalization helpers
- `app/routers/v1/schedules.py:_normalize_sentrix_hq_roster_final_state`
- `app/routers/v1/schedules.py:_extract_sentrix_ticket_hq_roster_status`
- `app/routers/v1/schedules.py:_get_support_roster_hq_ticket_status_label`

### Current reading
- The approved/pending calculation is one of the clearest pieces of real support-domain logic in the repo.
- It is driven by artifact/ticket scope, not by arbitrary workbook values.

## 5. `request_count` Ownership

### True source
- `app/routers/v1/schedules.py:_build_support_roster_hq_artifact_scope_map`
  - Reads support request scope from exported monthly support request rows.
- `app/routers/v1/schedules.py:_build_support_roster_hq_upload_inspect_result`
  - Uses `artifact_scope.request_count` as the comparison baseline.

### Workbook values are only reference data
- `workbook_required_count`
- `workbook_required_raw`

### Canonical import upstream source
- `app/routers/v1/schedules.py:_build_canonical_schedule_import_sentrix_scope_apply_specs`
  - Creates request scopes from parsed workbook `support_blocks`.
  - Uses `required_count_numeric` as the support request count.

### Current reading
- `request_count` belongs to the upstream support-request artifact, not to the HQ workbook UI.

## 6. Replace Semantics

### Backend handoff payload
- `app/routers/v1/schedules.py:_build_sentrix_support_roster_handoff_payload`
  - Builds:
    - `snapshot_mode: "replace"`
    - `replace_scope.mode: "site_month_full_snapshot"`
    - `replace_scope.snapshot_mode: "replace"`
    - selected site/month/date scope

### Frontend UX
- `frontend/index.html:1697-1700`
  - Explicit REPLACE note says re-upload replaces existing support roster and does not merge.

### Canonical import tests
- `tests/test_schedule_monthly_import_canonical.py:1879-2047`
  - Confirms the sync path posts a full replace snapshot and can send an empty-scope snapshot for removed requests.

### Current reading
- Replace semantics are explicit and central.
- They are not inferred behavior; they are encoded in payload shape and user-facing copy.

## 7. Active Upstream Write Paths

### Canonical schedule import
- `app/routers/v1/schedules.py:_sync_canonical_schedule_import_sentrix_support_requests`
  - Builds support scopes from canonical import output.
  - Posts a replace-style roster snapshot outward.

### HQ roster apply
- `app/routers/v1/schedules.py:_apply_sentrix_hq_roster_batch`
  - Validates preview batch.
  - Builds replace-style handoff payload.
  - Calls `_post_sentrix_support_roster_handoff`.

### External endpoint config
- `app/config.py:94-109`
  - `SOC_SUPPORT_ROSTER_HANDOFF_URL`
  - `SENTRIX_SUPPORT_BRIDGE_TOKEN`
  - `SUPPORT_ROSTER_HANDOFF_TIMEOUT_SECONDS`

## 8. Functions That Look Core But Are Currently Orphaned

No in-repo caller was found for:

- `app/routers/v1/schedules.py:_upsert_sentrix_support_request_ticket_row`
- `app/routers/v1/schedules.py:_retract_sentrix_support_request_ticket_row`
- `app/routers/v1/schedules.py:_persist_sentrix_hq_roster_snapshot`
- `app/routers/v1/schedules.py:_queue_sentrix_hq_arls_bridge_actions`
- `app/routers/v1/schedules.py:_resolve_sentrix_hq_notification_user_ids`
- `app/routers/v1/schedules.py:_insert_sentrix_hq_notification_audit`
- `app/routers/v1/schedules.py:_update_sentrix_hq_notification_audit_after_push`

That does not mean the design is unimportant. It means the active runtime ownership has shifted away from this repo, while the local domain model still describes the intended Sentrix state engine.

## 9. What Is Truly Core Support-Domain Logic Here

Most clearly core:

- Support request scope extraction from canonical imports
- HQ roster inspect and validation rules
- Approved vs pending state calculation
- Replace-snapshot payload building
- Self-staff filtering and ARLS bridge materialization rules
- Support status read-model assembly across ticket plus assignment state

Mixed or transitional:

- Local ticket upsert/retract helpers
- Local snapshot persistence
- Local notification audit
- Local bridge outbox creation

Legacy / wrong-owner domain still live:

- `support_assignment` CRUD and materialization
- old support-roundtrip HQ upload/apply/final-download flow
- SOC support-assignment event ingestion
