# ARLS Phase 2 Patch Manual Test Checklist

## Setup
- Open `ARLS > 스케쥴 > 근무일정 > Excel로 근무표 간편 제작`
- Use the real production-like workbook that previously took 2-3 minutes
- Select the real target site and target month used in the failed test

## Analysis-state lock checks
- Start analysis and confirm the following controls become non-editable while analysis is running:
  - upload file
  - target site
  - target month
  - mapping/template profile selector if exposed
- Confirm loading/progress UI is visible while waiting.
- Confirm the UI keeps the analyzed context bound to one deterministic analysis result.

## Placeholder employee row checks
- Use a workbook containing base-schedule rows where employee name cell is `0` or `"0"`.
- Run analysis.
- Confirm those rows do not produce `직원 매칭 실패`.
- Confirm those placeholder rows do not appear as actionable employee rows in preview.

## Label normalization checks
- Verify real labels with newline/spacing variants are recognized:
  - `주간\n추가 근무자`
  - `야간\n추가 근무자`
  - `외부인원 \n투입 수`
  - `작업 목적`
  - `작업 내용`
- Confirm day/night support blocks are detected consistently.
- Confirm purpose field is interpreted consistently even when the workbook uses `작업 내용`.

## Required-count parsing checks
- Verify strings like `섭외 1인 요청`, `섭외 2인 요청`, `섭외 3인 요청` parse to `1`, `2`, `3`.
- Verify a blank required-count with an otherwise empty support block is not blocking.
- Verify a blank required-count with worker/vendor/purpose payload becomes a structured blocking issue.

## Mapping checks
- Verify tenant mapping profile is loaded once and applied consistently.
- If profile is missing entirely:
  - confirm one strong workspace-level blocking issue appears
  - confirm row results are blocked without guessed template fallback
- If a specific key is missing:
  - confirm only affected rows fail with structured mapping errors

## Preview trustworthiness checks
- Confirm preview rows show:
  - source row number
  - date
  - section/block
  - row type
  - employee/value
  - current ARLS value
  - upload result
  - reason
- Confirm protected support fields are labeled as ignored/protected, not generic parser failures.
- Confirm false employee and false template failures are materially reduced compared with the previous run.

## Stale-result checks
- Complete one analysis run.
- Change file, site, or month.
- Confirm the old analysis result is treated as stale and a new analysis is required before apply.

## Timing checks
- After analysis completes, inspect preview metadata/logs for:
  - `workbook_load`
  - `section_parse`
  - `employee_match_preload`
  - `template_mapping_preload`
  - `row_normalization_pass`
  - `issue_grouping`
  - `preview_build`
  - `preview_persist`
  - `request_total`
- Confirm runtime no longer feels like the previous 2-3 minute stall.
