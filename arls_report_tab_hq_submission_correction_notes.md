# ARLS Report Tab HQ Submission Correction Notes

## Files Changed
- `app/routers/v1/schedules.py`
- `app/schemas.py`
- `frontend/index.html`
- `frontend/js/app.js`
- `frontend/css/styles.css`
- `arls_report_tab_hq_submission_contract.md`

## What Was Wrong
- The ARLS `보고` tab still presented `HQ 지원근무 병합 후 반영` as if ARLS owned the HQ roster merge/apply workflow.
- That conflicted with the agreed system design where:
  - ARLS owns support-demand extraction and workbook artifact generation.
  - Sentrix owns HQ support roster submission, reconciliation, approval/state changes, and apply.
- The old ARLS-side preview/apply framing made the workflow look like an in-ARLS ownership path instead of an export/handoff path.

## Correction Applied
- ARLS support report workflow is now framed as `export + handoff` only.
- The in-ARLS HQ merge/apply ownership was removed from the visible workflow.
- The report tab keeps:
  - support-demand workbook export
  - latest source revision visibility
  - current Sentrix handoff status
  - artifact metadata panel
- The report tab now opens Sentrix for HQ submission work instead of attempting roster merge/apply inside ARLS.

## Sentrix Handoff Path
- Added a dedicated `Sentrix에서 지원근무자 제출 열기` action.
- Added artifact handoff metadata display:
  - `artifact_id`
  - `site`
  - `month`
  - `revision`
  - `generated_at`
- Added `artifact_id 복사` action for manual handoff/troubleshooting.

## Backend Contract Changes
- `support-roundtrip/status` now exposes explicit artifact metadata:
  - `artifact_id`
  - `artifact_revision`
  - `artifact_generated_at`
- Stale messaging was updated to describe `Sentrix 재전달 필요` instead of ARLS final-download ownership.
- Absence of a Sentrix submission is no longer treated as an ARLS-side merge/apply blocker by default.

## UI Ownership After Patch
- ARLS:
  - source workbook export
  - source revision/artifact visibility
  - Sentrix handoff entry point
- Sentrix:
  - HQ roster submission
  - preview/reconciliation
  - apply/state changes

## Intentionally Not Changed
- Existing backend HQ upload preview/apply endpoints were not removed in this pass.
- The report tab contract changed so those legacy ARLS-side endpoints are no longer the primary UI path.
- Finance submission workflow under the same `보고` tab was not changed.
