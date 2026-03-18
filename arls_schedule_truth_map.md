# ARLS Schedule Truth Map

## Ownership Summary

- ARLS is the base schedule truth owner.
- ARLS is the support-origin materialization owner.
- ARLS is not the final support ticket/state truth owner.
- The practical truth tables are `monthly_schedules` and `site_daytime_need_counts`, with lineage and bridge support tables layered around them.

## Truth Tables And Source Markers

| Table / marker | Meaning | Evidence |
| --- | --- | --- |
| `monthly_schedules` | Main persisted schedule truth | `migrations/001_init.sql` plus later `ALTER TABLE` migrations |
| `site_daytime_need_counts` | Base daytime support-demand truth per site/date | `migrations/005_schedule_import_roundtrip_hardening.sql`, lineage columns in `migrations/011_schedule_import_apply_and_sentrix_tickets.sql` |
| `ARLS_MONTHLY_BASE_UPLOAD_SOURCE = "arls_monthly_base_upload"` | Base monthly workbook rows owned by canonical upload | `app/routers/v1/schedules.py` |
| `ARLS_SUPPORT_UPLOAD_INTERNAL_SOURCE = "support_upload_internal"` | Self-staff support rows materialized from base workbook support section | `app/routers/v1/schedules.py` |
| `SENTRIX_ARLS_BRIDGE_SOURCE = "sentrix_support_ticket"` | Sentrix-origin materialized rows | `app/routers/v1/schedules.py` |
| `SENTRIX_HQ_ROSTER_ASSIGNMENT_SOURCE = "HQ_ROUNDTRIP"` | Legacy HQ roundtrip overlay rows | `app/routers/v1/schedules.py` |

## A. Base Schedule Domain

### Base monthly upload parser

- Download entrypoints
  - `GET /api/v1/schedules/import/template`
  - `GET /api/v1/schedules/import/latest-base`
- Parser/export functions
  - `_detect_arls_import_workbook_context`
  - `_parse_arls_canonical_import_sheet`
  - `_collect_monthly_export_context`
  - `_build_monthly_export_workbook_from_contexts`
- Frontend entrypoints
  - `onScheduleTemplateDownload`
  - `onScheduleLatestBaseDownload`
  - `onSchedulePreview`
  - `onScheduleApply`

### Mapping profile usage during base upload

- Validation and lookup
  - `_fetch_active_schedule_import_mapping_profile`
  - `_build_schedule_import_mapping_summary`
  - `_build_schedule_import_mapping_lookup`
  - `_resolve_schedule_import_mapping_templates`
  - `_validate_mapping_profile_requirements`
  - `_resolve_import_body_value`
- Preview/apply routes
  - `POST /api/v1/schedules/import/preview`
  - `POST /api/v1/schedules/import/{batch_id}/apply`

### Base schedule apply

- Preview/build
  - `_build_schedule_import_preview_result`
  - `_persist_schedule_import_preview_batch`
- Re-load + apply
  - `_load_canonical_schedule_import_apply_context`
  - `_apply_canonical_schedule_import_batch`
- Low-level mutators
  - `_insert_monthly_schedule_row`
  - `_update_monthly_schedule_row`
  - `_delete_monthly_schedule_row`
  - `_upsert_daytime_need_count_row`
  - `_delete_daytime_need_count_row`

### Employee/site/template matching

- Site resolution
  - `_resolve_site_context_by_code`
  - `_resolve_site_context_by_id`
- Employee resolution
  - `_resolve_employee_by_code`
  - `_resolve_employee_by_id`
  - `_employee_is_active_for_schedule_date`
  - `_resolve_import_employee_match`
- Validation
  - `_validate_regular_shift_worker`
  - `_validate_support_shift_worker`

### Lineage handling

- Source ownership helpers
  - `_is_monthly_base_schedule_source`
  - `_is_support_upload_internal_source`
  - `_is_daytime_need_base_source`
- Schema lineage columns
  - `monthly_schedules.source`, `source_ticket_id`, `source_batch_id`, `source_revision`, `source_ticket_uuid`, `source_ticket_state`, `source_action`, `source_self_staff`
  - `site_daytime_need_counts.source_batch_id`, `source_revision`
- Canonical apply semantics
  - Base upload replaces only rows owned by `arls_monthly_base_upload`
  - Self-staff support overlay replaces only rows owned by `support_upload_internal`
  - Daytime need rows replace only base-owned entries
  - Foreign lineage rows are preserved or surfaced as conflicts instead of being silently overwritten

## What Is Core Schedule Truth Logic

### Core truth path

- `app/routers/v1/schedules.py`
  - `_build_schedule_import_preview_result`
  - `_load_canonical_schedule_import_apply_context`
  - `_apply_canonical_schedule_import_batch`
  - `_insert_monthly_schedule_row`
  - `_update_monthly_schedule_row`
  - `_delete_monthly_schedule_row`
  - `_upsert_daytime_need_count_row`
- `migrations/001_init.sql`
  - bootstraps `monthly_schedules`
- `migrations/004_schedule_templates_and_monthly_meta.sql`
  - template/time metadata for schedule rows
- `migrations/011_schedule_import_apply_and_sentrix_tickets.sql`
  - import apply lineage columns on schedule/daytime need tables

### Evidence from tests

- `tests/test_schedule_monthly_import_canonical.py`
  - `test_apply_canonical_schedule_import_batch_reupload_replaces_only_target_scope`
  - `test_apply_canonical_schedule_import_batch_keeps_existing_rows_when_validation_blocks`
  - `test_apply_canonical_schedule_import_batch_deletes_stale_internal_support_rows`
  - `test_sync_canonical_schedule_import_sentrix_support_requests_posts_full_replace_snapshot`
  - `test_sync_canonical_schedule_import_sentrix_support_requests_sends_empty_scope_snapshot_for_removed_day_requests`

## Support-Origin Truth vs Final Support Truth

### ARLS-owned support-origin materialization

- Queue/process path
  - `POST /api/v1/schedules/support-roundtrip/arls-bridge/process`
  - `_process_sentrix_support_arls_bridge_actions`
  - `_apply_sentrix_support_bridge_action`
  - `_upsert_sentrix_support_materialization_row`
  - `_load_sentrix_support_materialization_row`
- Storage
  - `sentrix_support_arls_bridge_actions`
  - `sentrix_support_schedule_materializations`
  - materialized `monthly_schedules` rows with `source='sentrix_support_ticket'`

### ARLS is not final ticket/state truth owner

- Canonical import only sends support-demand/request snapshots outward:
  - `_build_support_request_rows_from_import_payloads`
  - `_sync_canonical_schedule_import_sentrix_support_requests`
  - `_upsert_sentrix_support_request_ticket_row`
  - `_retract_sentrix_support_request_ticket_row`
- HQ roster apply also hands a normalized snapshot to Sentrix rather than owning the final support-state machine:
  - `_apply_sentrix_hq_roster_batch`
  - `_build_sentrix_support_roster_handoff_payload`
  - `_post_sentrix_support_roster_handoff`

## Manual / Base / Sentrix Lineage Map

| Row type in `monthly_schedules` | Owner | Source value | Overwrite rule |
| --- | --- | --- | --- |
| Base monthly schedule row | ARLS canonical monthly import | `arls_monthly_base_upload` | Replaceable by later canonical base import for same scope |
| Internal self-staff support row from base workbook | ARLS canonical import | `support_upload_internal` | Replaceable only by same workflow/source |
| Sentrix materialized support-origin row | ARLS bridge consumer, Sentrix-origin lineage | `sentrix_support_ticket` | Updated/retracted by bridge action processing, not by base upload |
| Legacy HQ roundtrip internal overlay | Legacy HQ roundtrip path | `HQ_ROUNDTRIP` | Managed by legacy support-roundtrip apply path |
| Manual/non-base/non-Sentrix row | User/manual/other workflow | varies | Protected from canonical base overwrite; causes review/block semantics |

## Exact Files To Inspect For Schedule Truth

- `app/routers/v1/schedules.py`
- `app/routers/v1/integrations.py`
- `app/db.py`
- `migrations/001_init.sql`
- `migrations/004_schedule_templates_and_monthly_meta.sql`
- `migrations/005_schedule_import_roundtrip_hardening.sql`
- `migrations/011_schedule_import_apply_and_sentrix_tickets.sql`
- `migrations/014_arls_sentrix_support_materialization.sql`
- `tests/test_schedule_monthly_import_canonical.py`
- `tests/test_arls_support_origin_materialization.py`

## Architecture Review Notes

- The canonical base import path is the authoritative monthly schedule truth owner.
- Sentrix-origin schedule rows are materialized into the same `monthly_schedules` table but remain downstream truth reflections, not ticket-state authority.
- `app/routers/v1/integrations.py` is a major ownership hazard because it still contains another live support-origin write path into the same tables.
