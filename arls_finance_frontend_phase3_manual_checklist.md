# ARLS Finance Frontend Phase 3 Manual Checklist

## 1. Flow A Context and 1차 Download
- Open the Finance reports workspace as a Finance-allowed user.
- Select tenant/site/month for Flow A.
- Confirm status cards and helper text refresh for the selected context.
- Click `1차 스케쥴 다운로드`.
- Confirm workbook download succeeds.
- Confirm compact success feedback appears.

## 2. Flow A Upload Preview
- Select an edited Finance workbook.
- Confirm file/site/month summary updates immediately.
- Click `업로드 미리보기`.
- Confirm preview table, blocked reasons, and preview summary render without page reload.
- Confirm `게시` only becomes enabled when backend preview returns `can_apply=true`.

## 3. Flow A Publish
- With a valid preview ready, click `게시`.
- Confirm `게시 완료` banner appears.
- Confirm current status cards refresh.
- Confirm uploaded file input resets so the previous file name no longer remains selected.
- Confirm latest 3 publish history rows refresh immediately.

## 4. Flow A Empty / Error States
- Open Flow A with no site selected and confirm compact guidance is shown.
- Attempt preview without selecting a file and confirm inline guidance appears.
- Trigger a preview validation failure and confirm blocked reasons/errors are visible without breaking the page.

## 5. Flow B Status Board
- Open `지점별 스케쥴 업로드 확인` as an HQ review role.
- Change the target month and confirm the site table refetches.
- Confirm top summary cards show counts for:
  - 게시 완료 수
  - 파일 없음 수
  - 업데이트 필요 수
  - 현재 선택 수
- Confirm `파일 없음` rows are not selectable.
- Confirm `게시 완료` and `업데이트 필요` rows are selectable.

## 6. Flow B Multi-Site 2차 Download
- Select multiple valid rows.
- Confirm selected count updates live.
- Click `2차 스케쥴 다운로드`.
- Confirm one workbook downloads.
- Confirm success banner appears after download.
- Confirm HQ workspace refetches automatically after the download.

## 7. Update-Needed Behavior
- Download 2차 for a site as HQ/Development.
- Publish a newer Finance file for the same site+month from Flow A or another allowed account.
- Return to Flow B and refresh/reopen the month.
- Confirm the row shows `업데이트 필요` in orange.
- Download 2차 again.
- Confirm the row returns to `게시 완료` after the refetch completes.

## 8. Role Visibility
- Supervisor: Flow A visible, Flow B tab hidden.
- HQ/Development backend-allowed review roles: Flow A and Flow B both visible.
- Users outside Finance workflow scope: Finance workspace hidden.

## 9. Technical Metadata Hiding
- Confirm the main Flow B table does not expose artifact ids, raw revisions, or source batch ids.
- Confirm `상세 정보` remains collapsed and only appears for development-capable users.
