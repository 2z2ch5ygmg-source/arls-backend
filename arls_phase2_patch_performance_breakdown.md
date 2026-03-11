# ARLS Phase 2 Patch Performance Breakdown

## Before
- Observed in production-like testing: monthly upload analysis took roughly 2-3 minutes.
- The real workbook also produced large amounts of false error noise, which increased row normalization and persistence volume.

## Main bottlenecks identified
- Every parsed body/support cell was being normalized and persisted, including large volumes of blank unchanged rows.
- Employee matching still ran for rows that were blank/no-op.
- Template resolution used repeated per-row scans over the template list.
- Missing mapping profiles could still fall through to guessed-template logic, causing extra work and misleading results.

## Optimization strategy used
- Parse the uploaded workbook once and keep section results in memory.
- Keep employee master and mapping profile/template data preloaded once per preview.
- Pre-index templates by `template_id` for O(1) mapping resolution.
- Skip resolution/persistence for blank unchanged rows.
- Skip employee matching for no-op blank body rows.
- Keep issue grouping as a grouped post-step instead of repeated duplicate issue payload construction for profile-level failures.
- Return and log analysis timing metadata for every major phase.

## Analysis timing instrumentation now emitted
- `workbook_load`
- `section_parse`
- `current_export_context`
- `current_value_index_build`
- `template_mapping_preload`
- `employee_match_preload`
- `existing_state_preload`
- `row_normalization_pass`
- `issue_grouping`
- `preview_build`
- `preview_persist`
- `request_total`

## Expected runtime effect
- The largest reduction should come from not persisting large volumes of blank unchanged cells into `schedule_import_rows`.
- Secondary gains come from skipping unnecessary employee-match work and avoiding repeated linear template lookups.
- The parser should also stop spending time on false blocking caused by placeholder/label/count misclassification.

## Before/after numbers
- Before: user-reported 2-3 minutes on the real workbook.
- After: exact real-workbook rerun numbers were not available in this workspace during the patch.
- Verification path added:
  - preview metadata timing fields
  - server log timing line from `/schedules/import/preview`

## Follow-up measurement instruction
- Re-run the original real workbook on the patched build.
- Capture `analysis_timings_ms` from the preview response.
- Compare `request_total` and `preview_persist` directly against the prior observed 2-3 minute behavior.
