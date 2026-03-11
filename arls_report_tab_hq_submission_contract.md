# ARLS Report Tab HQ Submission Contract

## Ownership Split
- ARLS owns:
  - base schedule upload/export
  - support-demand extraction
  - support-demand workbook artifact generation
- Sentrix owns:
  - HQ support roster submission/upload
  - roster preview/reconciliation
  - ticket state updates
  - HQ support roster apply workflow

## ARLS Role In The Report Tab
- ARLS remains the source/export side for HQ support submission.
- ARLS does **not** own `HQ 지원근무 병합 후 반영` after this correction.
- The support report tab should guide the user to export or hand off the artifact to Sentrix.

## Visible Actions
- `지원근무자용 시트 다운로드`
  - downloads the ARLS-generated support-demand workbook for the selected `site/month`
- `Sentrix에서 지원근무자 제출 열기`
  - opens the Sentrix HQ submission workspace using the current artifact context
- `artifact_id 복사`
  - copies the current source artifact identifier for audit/handoff use

## Handoff Fields
- `artifact_id`
- `site`
- `month`
- `revision`
- `generated_at`

These fields represent the latest ARLS-generated support-demand workbook artifact that Sentrix can consume.

## Status Semantics
- `원본 리비전`
  - latest ARLS source revision for the selected `site/month`
- `Sentrix handoff`
  - whether Sentrix has a recent submission based on the current source revision
- `artifact`
  - whether the current ARLS source artifact is available for handoff
- `작업 위치`
  - always communicates that HQ roster submission/apply belongs to Sentrix

## Stale Behavior
- If Sentrix submission is older than the latest ARLS source revision:
  - show `재전달 필요`
  - instruct the operator to open Sentrix again with the latest artifact

## Explicit Non-Ownership
- ARLS no longer presents HQ roster merge/apply as an in-ARLS workflow in this tab.
- The report tab remains available and useful, but only as:
  - export workspace
  - artifact handoff workspace
  - status visibility workspace
