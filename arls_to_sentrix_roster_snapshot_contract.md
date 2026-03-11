# ARLS -> Sentrix Support Roster Snapshot Contract

## Ownership
- ARLS owns:
  - workbook ingress
  - workbook parsing
  - normalized roster snapshot generation
  - review/apply entrypoint
- Sentrix owns:
  - support ticket truth
  - support roster truth
  - exact-filled / pending calculation
  - confirmed worker persistence
  - notifications
  - ARLS bridge follow-up

## Payload schema

Top-level fields:
- `tenant_code`
- `tenant_id`
- `artifact_id`
- `source_upload_batch_id`
- `month`
- `download_scope`
- `selected_site_code`
- `workbook_family`
- `template_version`
- `revision`
- `affected_site_codes`
- `affected_dates`
- `affected_scope_count`
- `scopes`

Per-scope fields:
- `scope_key`
- `sheet_name`
- `site_id`
- `site_code`
- `site_name`
- `month`
- `work_date`
- `shift_kind`
- `request_count`
- `valid_filled_count`
- `invalid_filled_count`
- `target_status`
- `current_status`
- `current_ticket_hint`
- `workbook_required_count`
- `workbook_required_raw`
- `external_count_raw`
- `purpose_text`
- `matched_ticket`
- `worker_entries`

Per-worker normalized fields:
- `slot_index`
- `raw_cell_text`
- `parsed_display_value`
- `normalized_affiliation`
- `normalized_name`
- `worker_type`
- `self_staff`
- `countable`
- `parse_valid`
- `issue_code`
- `issue_message`
- `canonical_employee_hint.employee_id`
- `canonical_employee_hint.employee_code`
- `canonical_employee_hint.employee_name`
- `row_provenance.sheet_name`
- `row_provenance.source_row`
- `row_provenance.source_col`
- `row_provenance.source_cell_ref`

## Granularity
- Handoff scope is independent per:
  - site
  - date
  - shift kind
- Sentrix can process each scope independently and return mixed results in one batch.

## Success semantics
- Full success:
  - ARLS apply preconditions passed
  - Sentrix handoff succeeded for all scopes
- Partial success:
  - ARLS built the snapshot
  - at least one scope succeeded
  - at least one scope failed
  - or ARLS local apply completed but downstream handoff failed in a retryable way
- Failure:
  - Sentrix handoff failed for the whole apply result
  - ARLS must not present this as complete success
- Blocked:
  - review/apply preconditions failed before handoff

## Retry behavior
- Retry basis is `source_upload_batch_id`
- ARLS stores apply result/audit in the batch summary
- Retry must not require re-upload of the workbook
- Failed or partial handoff results must remain understandable and retryable

## Lineage fields
- `artifact_id`
- `source_upload_batch_id`
- `month`
- `revision`
- `workbook_family`
- `template_version`
- `sheet_name`
- worker row provenance

## What ARLS does NOT decide
- ARLS does not finalize approved vs pending policy beyond preview hints
- ARLS does not own support ticket truth
- ARLS does not send notifications
- ARLS does not own support roster truth after handoff
