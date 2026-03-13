## Role visibility

- Verify HQ sees both `Excel로 근무표 간편 제작` and `지점별 스케쥴 업로드 확인`.
- Verify Development and Master see both tabs and can change tenant.
- Verify Supervisor / Vice Supervisor see only `Excel로 근무표 간편 제작`.

## Tab A wizard

- Step 1 blocks 다음 until a valid mapping profile is selected.
- Step 2 applies role-based tenant/site/month controls correctly.
- Step 3 shows 빈 양식 다운로드 / 최신 기준본 다운로드 / file picker / 분석 시작 only.
- Step 4 starts in 오류/검토 중심 보기 and supports 전체 보기.
- Step 5 shows 적용중 / 적용 완료 state on a dedicated completion page.

## Tab B independent context

- Change Tab A site/month and confirm Tab B month/site selection does not change.
- Change Tab B tenant/month/site and confirm Tab A context does not change.
- Re-enter Tab B and verify resume prompt restores last HQ workflow state when available.

## Tab B Step 3

- Confirm all sites for the selected tenant are listed.
- Confirm file-missing rows cannot be selected.
- Confirm `완료 지점 전체 선택` selects only download-ready rows.
- Confirm `선택 해제` clears the selection.
- Confirm selection summary explains one workbook / many sheets.

## Tab B Step 4

- Upload a valid workbook and confirm the flow stays inside Step 4 until preview is requested.
- Upload a mismatched workbook and confirm:
  - error stays in Step 4
  - mismatch reason is explicit
  - file can be replaced without leaving the step

## Tab B Step 5

- Confirm preview rows are aggregated by site/date/shift scope.
- Confirm default filter is 오류/검토 중심.
- Confirm `전체 보기` reveals all rows.
- Confirm 근무자명 is joined in source order.

## Tab B Step 6

- Confirm apply shows centered progress/completion messaging.
- Confirm completion returns to Step 3 summary state by default.
- Confirm dismissible success banner shows processed sites / approved / pending counts.

## Metadata visibility

- As HQ user, confirm artifact_id / raw revision / source batch are not shown in primary UI.
- As Dev/Master, confirm those details are available only in collapsed 상세 정보.

## Partial stale handling

- Select a mix of ready and stale sites.
- Confirm valid sites can continue while excluded stale sites remain explicit.

## Finance regression

- Open Finance reports area and confirm support-HQ workflow state is not leaking into Finance status or filters.
