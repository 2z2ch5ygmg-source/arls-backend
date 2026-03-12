# ARLS Step 2 Preview Visibility Rules

## Default preview mode
- Default mode: `기본 보기`
- Optional secondary mode: `전체 보기`

## Actionable row definition
A row is actionable only when it requires a human decision in Step 2.

Included by default:
- blocking/error rows
- true review rows on real base schedule body cells

Examples:
- template mapping missing on a base schedule row
- employee match failure
- ambiguous employee match
- stale template family/revision blocker
- real overwrite conflict
- lineage conflict

## Protected support row exclusion rules
Rows are hidden from the main preview table when they are support/protected informational rows only.

Excluded by default:
- `day_support*`
- `night_support*`
- `sentrix_support_ticket`
- rows with `parsed_semantic_type` like `protected_*`
- rows classified as `protected_info_only`

## Kept vs hidden examples

Kept in `기본 보기`:
- `주간근무` body row with template mapping failure
- `야간근무` body row with employee match failure
- base schedule row with real blocking conflict

Hidden in `기본 보기`:
- `주간 지원 근무자`
- `야간 지원 근무자`
- `주간 추가 근무자 수`
- `야간 근무자 총 수`
- `작업 목적`
- `외부인원 투입 수`
- support-demand summary rows
- protected/ignored support info rows

## Optional 전체 보기
- `전체 보기` exists.
- `전체 보기` exposes the broader preview dataset, including protected/support informational rows.
- `기본 보기` remains the default for normal operator review.
