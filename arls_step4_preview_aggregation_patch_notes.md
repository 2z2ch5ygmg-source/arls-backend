# ARLS Step 4 Preview Aggregation Patch Notes

## Files changed
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/arls_step4_preview_aggregation_patch_notes.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_step4_preview_aggregation_manual_checklist.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_step4_preview_column_contract.md`

## Old fragmented row problem
- Step 4 preview table rendered `scope_summary` rows and `worker` rows together.
- One support scope could appear as multiple rows:
  - scope row
  - worker 1 row
  - worker 2 row
- This made the operator read one 날짜/주야 scope in a fragmented way.

## New aggregated row logic
- The Step 4 table now aggregates preview display rows by:
  - sheet
  - site
  - date
  - shift kind
- Only one preview row is rendered for each support scope.
- Worker slot rows are no longer rendered separately in the ARLS Step 4 preview table.

## How worker rows are collapsed into one scope row
- The frontend now groups raw `review_rows` by scope key.
- `scope_summary` rows provide:
  - canonical request count
  - entered count
  - target ticket status
  - day-side review reason
- `worker` rows contribute only ordered valid worker names.
- Invalid worker rows are excluded from the `근무자명` join result and remain represented through grouped issues.

## How Ticket상태 is derived
- The new `Ticket상태` column uses the existing scope target status.
- No parallel `target 상태` column is kept in the preview table.
- The column reflects the same reconciliation output already produced by the current workflow:
  - 승인
  - 승인대기

## How 사유 is chosen
- 주간:
  - uses the existing scope-level day-side review reason
- 야간:
  - uses workbook `작업목적`
  - if `작업목적` is empty, the column stays empty/compact instead of reusing worker-slot text

## What was intentionally not changed
- No Step 4 parser rewrite
- No Sentrix state logic rewrite
- No ARLS apply/handoff logic change
- No workspace-wide UI redesign beyond the preview table contract
