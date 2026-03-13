# ARLS HQ Tab Backend Contract Notes

## Files Changed
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py`
- `/Users/mark/Desktop/rg-arls-dev/app/schemas.py`
- `/Users/mark/Desktop/rg-arls-dev/tests/test_schedule_support_roundtrip.py`

## Old State-Coupling Problem
- HQ workspace payload was minimal and mostly revision/source oriented.
- Tab B did not expose its own selected-site set, resume state, or step context.
- Upload inspect used metadata/sheet mismatches as loose warnings and could silently exclude sheets.
- Preview rows still exposed count-summary text as the main `reason` field for day scopes.
- Overfilled scopes were treated as blocking instead of reviewable `승인대기`.

## New Independent HQ Tab State Model
- `hq-workspace` now returns a dedicated Tab B contract with:
  - tenant context
  - actor role
  - current step
  - available site codes
  - selected site codes
  - selection capability flags
  - resume state
  - success-banner summary
  - user-facing `ui_summary`
  - separable `technical_details`
- Workspace site rows now include:
  - upload state
  - selectable/selected flags
  - last uploaded timestamp
  - stale state and stale reason
  - blocked reason
- Tab B selected sites can be passed independently and no longer depend on Tab A state.

## Mismatch Validation Behavior
- Step 4 inspect now returns structured in-place mismatch data:
  - `missing_selected_sites`
  - `extra_unselected_sites`
  - `unresolved_sheets`
  - `stale_sites`
  - `blocking_errors`
- Missing selected site sheets are blocking.
- Extra unselected site sheets are blocking.
- BC34 fallback remains supported for damaged sheet names.
- Sites outside the selected set are not silently ignored anymore.

## Preview Aggregation Behavior
- Step 5 preview remains aggregated one row per scope:
  - site
  - date
  - shift kind
- Aggregated rows now include:
  - `ticket_status`
  - `ticket_status_label`
  - `review_level`
  - `blocking_errors`
- Day scope `reason` now comes from canonical artifact-side day reason text.
- Missing day reason now produces `DAY_SCOPE_REASON_MISSING` blocking review state.
- Night scope `reason` continues to use workbook/artefact purpose text.
- Overfilled scopes now stay reviewable with `approval_pending` instead of being blocked.

## Technical Metadata Separation
- Normal UI-facing fields now sit in:
  - workspace `ui_summary`
  - inspect `ui_summary`
  - upload meta `ui_summary`
  - apply `completion_summary`
- Low-level metadata is still available in:
  - workspace `technical_details`
  - inspect `technical_details`
  - upload meta `technical_details`
  - apply `technical_details`

## What Was Intentionally Not Changed
- Base monthly upload parser/apply flow was not redesigned.
- Sentrix ticket/state ownership was not moved.
- Final ARLS support-origin materialization was not added here.
- Mobile/frontend rendering behavior was not changed in this step.
