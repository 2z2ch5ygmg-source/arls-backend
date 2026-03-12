# ARLS Frontend Step1 UI Restore Manual Checklist

## Base wizard
- Open `스케쥴 > 근무일정 > Excel로 근무표 간편 제작`.
- Confirm only Step 1 body is visible first.
- Confirm top context bar shows tenant / site / month / file / revision / current step.
- Confirm Step 1 next button is disabled when mapping profile is empty.
- Confirm Step 1 next button becomes enabled after mapping profile exists.
- Confirm Step 2 next button stays disabled until site + month are selected.
- Confirm Step 3 shows:
  - 빈 양식 다운로드
  - 최신 기준본 다운로드
  - 파일 업로드
  - 분석 시작
- Confirm analysis success moves directly to Step 4.
- Confirm apply click moves directly to Step 5 and does not leave the user in long-scroll mode.

## HQ wizard
- Log in as HQ / Development / Master.
- Confirm second tab `지점별 스케쥴 업로드 확인` is visible.
- Log in as normal Supervisor / Vice Supervisor.
- Confirm the second tab is hidden.
- In HQ tab, confirm export -> upload -> preview -> complete progression works as separate wizard pages.
- Confirm HQ inspect success moves to preview automatically.
- Confirm HQ apply moves to completion/progress automatically.

## Resume
- In HQ tab, advance to upload or preview state.
- Leave the page and come back.
- Confirm the resume prompt appears.
- Confirm accepting resume restores month/site/step.

## Cleanup / ownership
- Confirm the upload workspace is now the obvious owner of the Excel workflow.
- Confirm 보고 tab no longer looks like the main workbook processing owner.
- Confirm the templates area no longer visually competes as the main mapping-profile owner.
