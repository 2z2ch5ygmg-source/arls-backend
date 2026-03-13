## Files changed

- `/Users/mark/Desktop/rg-arls-dev/frontend/index.html`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/frontend/css/styles.css`

## Old UI problems

- Base upload and HQ workflow were presented as a long-scroll mixed workspace.
- HQ workflow reused parts of Tab A state, especially site/month context.
- Reports/support wording implied mixed ownership and exposed internal workflow language.
- HQ upload/review/apply surfaces showed technical metadata too early.
- Multi-site HQ selection was not explicit enough for one-workbook / many-sheet behavior.

## New wizard structure

### Tab A: `Excel로 근무표 간편 제작`

Step flow:
1. 매핑 프로필 선택
2. 업로드 컨텍스트 선택
3. 양식 다운로드 + 파일 업로드
4. 반영 검토
5. 적용 진행 / 완료

- One step body is shown at a time.
- Wizard navigation uses explicit 이전 / 다음 buttons.
- The top summary bar stays visible with tenant / site / month / file / revision / current step.

### Tab B: `지점별 스케쥴 업로드 확인`

Step flow:
3. HQ 제출용 추출
4. HQ 작성본 업로드
5. 업로드 미리보기
6. 업로드 진행 / 완료

- The HQ tab is visually emphasized for HQ users.
- Completion returns to the Step 3 summary state and shows a dismissible success banner.

## Independent Tab B context model

- Tab B now keeps its own tenant / month / selected-site state.
- Tab B no longer inherits the base upload selected site, month, or file.
- Dev/Master can choose tenant in both workflows.
- HQ and lower roles stay fixed to their own tenant.
- Supervisor / Vice Supervisor do not see the HQ tab.

## Site selection table behavior

- Step 3 shows site rows with:
  - 선택
  - 지점명
  - 상태
  - 최근 업로드 시각
  - 메모
- `완료 지점 전체 선택` and `선택 해제` actions are supported.
- File-missing rows remain non-selectable.
- Selection summary explicitly explains one workbook / many sheets and excluded stale/missing counts.

## Preview table behavior

- Step 5 renders one aggregated row per support scope.
- Default mode is 오류/검토 중심 보기 and users can switch to 전체 보기.
- Main columns are user-facing:
  - 시트명
  - 지점
  - 날짜
  - 구분
  - 요청인원수
  - 입력인원수
  - 근무자명
  - Ticket상태
  - 사유
- Worker names are joined in source order instead of split into separate rows.

## What technical info was hidden

- Normal operator-facing areas no longer foreground:
  - artifact_id
  - raw revision
  - source batch id
  - bridge/internal ownership text
- Development / Master can still inspect technical metadata in a collapsed 상세 정보 section.

## What was intentionally not changed

- Backend parser / inspect / apply contracts were not changed in this pass.
- Sentrix integration behavior was not changed.
- Mobile layout was not redesigned.
- Base upload parser/apply core logic was not rewritten.
- Finance submission flow remains separate and was only cleaned up where support-report confusion leaked into it.
