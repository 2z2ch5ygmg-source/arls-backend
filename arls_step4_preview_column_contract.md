# ARLS Step 4 Preview Column Contract

## Final columns
1. 시트명
2. 지점
3. 날짜
4. 구분
5. 요청인원수
6. 입력인원수
7. 근무자명
8. Ticket상태
9. 사유

## Aggregation key
- `sheet_name`
- `site_code` or `site_name`
- `work_date`
- `shift_kind`

Recommended internal key:
- `(sheet_name, site_code_or_name, work_date, shift_kind)`

## 요청인원수 source
- existing canonical Sentrix ticket `request_count`
- not derived from entered worker count
- not replaced by workbook `필요인원 수`

## 입력인원수 source
- number of valid entered workers in the aggregated scope
- blank cells do not count
- invalid cells do not count
- valid duplicates in separate slots still count

## 근무자명 join rule
- use only valid parsed worker entries
- preserve workbook slot order
- join with `, `
- blank result stays empty/compact when there are zero valid workers

## Ticket상태 mapping
- use the current scope target status result
- expected values include:
  - 승인
  - 승인대기
- do not keep separate legacy `target 상태` and `검토상태` columns in the final Step 4 preview table

## 사유 rule
- 주간:
  - use the current scope-level day-side reason
- 야간:
  - use workbook `작업목적`
  - if missing, keep the field empty/compact

## Intentionally unchanged
- underlying ticket reconciliation logic
- issue grouping panel
- ARLS apply/handoff semantics
