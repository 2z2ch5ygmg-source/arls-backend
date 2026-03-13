# ARLS HQ Preview And Handoff Contract

## Sheet / Site Validation Rules
- Primary site identifier: sheet name.
- Fallback identifier: merged-cell `BC34`.
- If neither resolves:
  - blocking error
  - sheet added to `unresolved_sheets`.
- If a selected site is missing from workbook:
  - blocking error
  - added to `missing_selected_sites`.
- If workbook contains extra unselected site sheet:
  - blocking error
  - added to `extra_unselected_sites`.
- If resolved site falls outside selected site set:
  - blocking error.
- If workbook month differs from selected month:
  - blocking error.

## BC34 Fallback Rule
- `BC34` is only used when sheet name cannot directly resolve to a tenant-scoped workspace site.
- If fallback produces a single tenant-scoped match, resolution method is `bc34`.
- If fallback is empty or ambiguous, sheet is unresolved.

## Preview Row Aggregation Schema
One preview row per `(site_code, work_date, shift_kind)`:
- `sheet_name`
- `site_code`
- `site_name`
- `date`
- `shift_kind`
- `requested_count`
- `entered_count`
- `worker_names`
- `ticket_status`
- `ticket_status_label`
- `reason`
- `review_level`
- `blocking_errors[]`

## `requested_count` Source Rule
- `requested_count` comes from the ARLS support-demand artifact scope for the exact site/date/shift.
- It is not inferred from workbook free text inside HQ upload.

## Day Reason Binding Rule
- Day scope `reason` comes from canonical artifact-side day support reason text.
- If day reason is unavailable:
  - `DAY_SCOPE_REASON_MISSING`
  - blocking review state
  - no fake reason synthesis.

## Night Purpose Rule
- Night scope `reason` uses workbook `작업목적`, with artifact purpose retained as fallback/reference.

## Handoff Payload Fields
Per-scope handoff to Sentrix includes:
- `tenant`
- `month`
- `site_code`
- `site_name`
- `work_date`
- `shift_kind`
- `requested_count`
- `valid_filled_count`
- `invalid_filled_count`
- `target_status`
- `day_reason`
- `night_purpose`
- `scope_reason`
- `worker_entries[]`
- `workbook_lineage{}`
- `artifact_lineage{}`
- `artifact_source_batch_id`
- `artifact_source_revision`

## Apply Result Semantics
- `success`
  - all valid scopes handed off
- `partial_success`
  - some scopes handed off, some excluded/failed
- `failure`
  - no meaningful handoff completed

Returned apply payload includes:
- `completion_summary{}`
- `technical_details{}`
- `scope_results[]`
- real `handoff_status`
- real `handoff_message`
