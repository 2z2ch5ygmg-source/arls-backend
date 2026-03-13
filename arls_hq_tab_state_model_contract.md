# ARLS HQ Tab State Model Contract

## Independent Tab B Context Model
- Endpoint: `GET /schedules/support-roundtrip/hq-workspace`
- Input:
  - `month`
  - optional `tenant_code` for Development/Master
  - optional `selected_site_codes[]`
- Output:
  - `tenant_code`
  - `tenant_name`
  - `actor_role`
  - `month`
  - `current_step`
  - `available_site_codes[]`
  - `selected_site_codes[]`
  - `can_select_tenant`
  - `can_select_site_set`
  - `selection_capabilities{}`
  - `tenant_context{}`
  - `ui_summary{}`
  - `technical_details{}`
  - `resume_state{}`
  - `success_banner_summary{}`
  - `sites[]`

## Role-Based Tenant Rules
- `hq_admin`: tenant fixed to own tenant.
- `developer` or `super_admin`: tenant selectable.
- `supervisor` / `vice_supervisor`: not allowed into HQ workflow.

## Site Status Table Schema
Each `sites[]` row exposes:
- `site_code`
- `site_name`
- `sheet_name`
- `sheet_name_valid`
- `download_ready`
- `source_state`
- `upload_state`
- `selectable`
- `selected`
- `last_uploaded_at`
- `note`
- `stale`
- `stale_reason`
- `blocked_reason`
- `source_revision`
- `latest_hq_revision`
- `latest_status`
- `hq_merge_stale`

## Stale / Selectable Rules
- `파일 없음`: not selectable.
- `업로드 완료`: selectable.
- `재업로드 필요 / stale`: not selectable for fresh extract, but may appear later as stale exclusion in inspect/apply.

## Resume-State Fields
- `available`
- `batch_id`
- `month`
- `status`
- `current_step`
- `selected_site_codes[]`
- `selected_site_code`
- `last_downloaded_revision`
- `uploaded_file_name`
- `latest_status`
- `last_batch_created_at`
- `last_batch_completed_at`
- `summary_json`
- `last_apply_result`

## Success-Banner Summary Fields
- `processed_site_count`
- `approved_count`
- `pending_count`
- `excluded_stale_site_count`
- optional `handoff_status`
- optional `handoff_message`

## `ui_summary` vs `technical_details`
- `ui_summary`
  - operator-facing counts and readiness
  - selected/ready/file-missing/stale counts
- `technical_details`
  - artifact id
  - revision
  - raw site revision map
  - generated timestamp
  - other lineage internals for Dev/Master-only drill-in
