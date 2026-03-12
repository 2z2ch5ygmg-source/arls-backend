# ARLS Frontend Step1 UI Restore Notes

## Files changed
- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/frontend/css/styles.css`

## Old ownership problems
- Excel workflow sections were stacked in one long scrolling page.
- HQ support upload looked like a continuation of the same scroll, not a separate operator flow.
- Mapping profile ownership was technically available, but not visibly anchored as Step 1 of the Excel workflow.
- The review/apply states did not behave like wizard pages, so analysis/apply completion still felt like “same page, new content below”.

## New tab / step structure
- Primary upload owner tab:
  - `Excel로 근무표 간편 제작`
  - Steps:
    1. 매핑 프로필 사전 설정
    2. 업로드 대상 선택
    3. 양식 다운로드 + 파일 업로드
    4. 반영 검토
    5. 적용 진행 / 완료
- HQ-only secondary owner tab:
  - `지점별 스케쥴 업로드 확인`
  - Visible only to HQ / Development / Master
  - Steps:
    3. HQ 제출용 추출
    4. HQ 작성본 업로드
    5. 업로드 미리보기
    6. 업로드 진행 / 완료

## What duplicate / wrong entry points were removed or demoted
- The old long-scroll “all sections visible” composition is no longer the primary experience.
- Report-tab workbook flow remains only as shortcut/export context; the main workbook owner is now the upload workspace.
- The template-area mapping profile remains available, but its visible ownership is demoted there and promoted into Step 1.

## How mapping profile ownership was moved
- Step 1 now surfaces:
  - readiness badge
  - compact mapping summary
  - manage/edit entrypoint
- The wizard cannot move past Step 1 unless at least one mapping entry exists.

## Wizard behavior restored
- Only one step body is shown at a time.
- Top context bar now keeps:
  - tenant
  - site
  - month
  - file name
  - revision
  - current step
- Base upload analysis success moves the user directly into Step 4 review.
- Base apply moves into Step 5 apply/complete state.
- HQ inspect success moves into Step 5 preview.
- HQ apply moves into Step 6 progress/complete state.

## HQ resume handling
- HQ workflow progress is persisted locally with:
  - month
  - site
  - current step
  - artifact id
  - revision
  - file name metadata
- On re-entry, the user is asked whether to resume.
- Resume safely reapplies the saved month/site after site options finish loading.

## What was intentionally not changed
- Mobile layout was not touched.
- Base parser/apply business logic was not redesigned.
- Sentrix-side state engine logic was not moved into ARLS.
- HQ partial multi-site selection matrix/download contract was not fully rewritten in this pass; the wizard ownership and step flow were restored first.
