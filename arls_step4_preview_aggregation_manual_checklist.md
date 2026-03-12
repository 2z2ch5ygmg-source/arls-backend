# ARLS Step 4 Preview Aggregation Manual Checklist

## Scope aggregation
- Upload an HQ support roster workbook with at least one scope containing 2 worker cells.
- Verify the Step 4 preview renders exactly one row for that 날짜/주야 scope.
- Verify separate worker slot rows are not shown.

## Column contract
- Verify the preview columns are exactly:
  - 시트명
  - 지점
  - 날짜
  - 구분
  - 요청인원수
  - 입력인원수
  - 근무자명
  - Ticket상태
  - 사유

## Count rules
- Verify `요청인원수` matches existing Sentrix ticket request count.
- Verify `입력인원수` counts only valid entered workers.
- Verify blank cells do not count.
- Verify invalid cells do not count.

## Worker name aggregation
- Verify valid worker names are joined in workbook slot order.
- Verify the separator is `, `.
- Verify duplicate names in separate valid slots remain duplicated in the joined string.

## Day/night reason rules
- For a 주간 scope, verify `사유` uses the scope-level day-side review reason.
- For a 야간 scope with `작업목적`, verify `사유` shows that value.
- For a 야간 scope without `작업목적`, verify `사유` is empty or a compact empty marker.

## Ticket status binding
- Verify `입력인원수 == 요청인원수` shows `승인`.
- Verify `입력인원수 != 요청인원수` shows `승인대기`.

## Issue handling
- Verify grouped issue cards still show blocking/warning issues for invalid input scopes.
- Verify the table does not expand back into worker-slot rows just to expose issue details.
