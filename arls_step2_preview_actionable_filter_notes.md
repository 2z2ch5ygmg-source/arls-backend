# ARLS Step 2 Preview Actionable Filter Notes

## Files changed
- `/Users/mark/Desktop/rg-arls-dev/app/schemas.py`
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py`
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/tests/test_schedule_monthly_import_canonical.py`
- `/Users/mark/Desktop/rg-arls-dev/arls_step2_preview_actionable_filter_notes.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_step2_preview_actionable_filter_manual_checklist.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_step2_preview_visibility_rules.md`

## Old noisy preview behavior
- Step 2 row preview rendered nearly every non-unchanged row by default.
- This included:
  - `반영 예정` rows
  - protected support metadata rows
  - support-demand/support-roster informational rows
  - support summary count rows
- The result was a large yellow/red table even when most rows were not operator actions.

## New filter logic
- Backend now classifies each preview row with:
  - `preview_visibility_class`
  - `actionable`
  - `protected_info_only`
- Frontend default mode is now `기본 보기`.
- `기본 보기` shows only:
  - actionable review rows
  - blocking/error rows
- `전체 보기` remains available as an optional secondary mode.

## Which support rows are hidden from main preview
- support-demand/support-roster informational rows
- protected support metadata rows
- support summary/count rows
- rows classified as `protected_info_only`

Examples hidden by default:
- `주간 지원 근무자`
- `야간 지원 근무자`
- `주간 추가 근무자 수`
- `야간 근무자 총 수`
- `작업 목적`
- `외부인원 투입 수`
- `Sentrix 지원 요청` summary rows

## Which base rows are still shown
- real base schedule body rows with actionable review status
- real base schedule body rows with blocking errors

Examples kept:
- template mapping missing on body rows
- employee match failure
- employee ambiguous match
- stale/wrong template family issues
- lineage conflicts
- real overwrite conflicts on base schedule cells

## What remains in issue summary only
- protected support metadata awareness
- support-demand informational rows
- ignored protected values that are not operator decisions in Step 2
- support summary counts that do not require a direct row action
