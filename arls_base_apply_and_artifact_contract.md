## ARLS Base Apply And Artifact Contract

### Base apply scope
- Scope is exactly one:
  - tenant
  - site
  - month
- Base apply writes only ARLS base-upload lineage rows for that site+month.
- Base apply may also update ARLS-owned daytime need-count rows for that same site+month.
- Base apply does not create or update Sentrix tickets in Step 2A.

### Lineage rules
- Base schedule rows:
  - `source = arls_monthly_base_upload`
  - `source_batch_id = upload batch id`
  - `source_revision = workbook/source revision`
- Support-demand artifact lineage:
  - `schedule_support_roundtrip_sources.source_batch_id`
  - `schedule_support_roundtrip_sources.source_revision`
  - persisted analyzed `schedule_import_rows.payload_json`

### Support-demand artifact schema
- Artifact root:
  - `artifact_id`
  - `source_upload_batch_id`
  - `tenant`
  - `site`
  - `month`
  - `workbook_family`
  - `workbook_revision`
  - `generated_at`
  - `support_scope_count`
- Each support scope:
  - `site`
  - `date`
  - `shift_kind`
  - `requested_count`
  - `raw_requested_count`
  - `purpose_text` for night if present
  - `required_row_no`
  - `source_sheet`
  - revision linkage through source batch/source revision

### Artifact revision rules
- Revision must change when:
  - base schedule truth changes
  - daytime need rows change
  - extracted support-demand scope payload changes
- Revision is computed from ARLS-owned data and the active/imported source batch.
- HQ export should use the active ARLS source batch as the primary support-demand source.

### Apply result schema
- `base_schedule_created`
- `base_schedule_updated`
- `base_schedule_removed`
- `artifact_generated`
- `artifact_id`
- `artifact_revision`
- `artifact_generated_at`
- `support_scope_count`
- `warnings/failures` via:
  - `blocking_failures`
  - `partial_failures`
  - `failed_items`
- `source_upload_batch_id` via `upload_batch_id`

### Failure semantics
- Blocked:
  - workbook invalid
  - stale revision
  - unresolved mapping/profile mismatch
  - unresolved blocking parser issues
- Partial failure:
  - base schedule apply succeeded
  - artifact/source registration failed
- Full success:
  - base schedule apply succeeded
  - artifact/source registration succeeded

### Explicit non-goals for Step 2A
- No Sentrix ticket creation
- No HQ support roster reconciliation
- No Sentrix status calculation
- No support roster bridge execution
