# ARLS Finance Workflow Phase 1 Manual Checklist

## Flow A: Finance용 스케쥴 제출
- [ ] Supervisor account can open `Finance용 스케쥴 제출`
- [ ] Vice Supervisor account cannot see the Finance reports workspace
- [ ] HQ account can open Flow A and select any site in own tenant
- [ ] Development/Master account can switch tenant in Flow A
- [ ] Context cards update after changing tenant/site/month
- [ ] `1차 스케쥴 다운로드` downloads a workbook for the selected site + month
- [ ] Upload file summary shows file name, site, and month before preview
- [ ] `업로드 미리보기` fills the preview table and summary text
- [ ] `게시` is disabled before a valid preview exists
- [ ] Successful publish shows `게시 완료` banner with compact summary
- [ ] Recent publish history shows at most 3 rows
- [ ] Publish history marks the current/latest row clearly

## Flow B: 지점별 스케쥴 업로드 확인
- [ ] Flow B tab is hidden from Supervisor
- [ ] Flow B tab is visible for HQ
- [ ] Flow B tab is visible for Development/Master
- [ ] Month/tenant context loads the per-site publish table
- [ ] Table columns are `선택 / 지점명 / 상태 / 최근 게시 시각 / 메모`
- [ ] `파일 없음` rows are not selectable
- [ ] `게시 완료` rows are selectable
- [ ] `업데이트 필요` rows are selectable and visually distinct from `파일 없음`
- [ ] `완료 지점 전체 선택` selects all selectable rows
- [ ] `선택 해제` clears all selected rows
- [ ] `2차 스케쥴 다운로드` is disabled when nothing is selected
- [ ] Multiple selected sites download as one workbook
- [ ] Download success banner appears after 2차 download

## Update Needed UX
- [ ] Download a site once in Flow B
- [ ] Publish a newer workbook for the same site + month in Flow A
- [ ] Return to Flow B and verify the site shows `업데이트 필요`
- [ ] Re-download that site in Flow B and verify the state returns to `게시 완료`

## Non-Goals Regression Check
- [ ] Existing support roundtrip HQ upload wizard still opens and works from the upload workspace
- [ ] Existing monthly upload/import workflow still loads
- [ ] No Sentrix page or route was changed as part of this phase
