# Sentrix UI Rollback Pass 1 Notes

## Files changed

- `/Users/mark/Desktop/security-ops-center/static/index.html`
- `/Users/mark/Desktop/security-ops-center/static/app.js`
- `/Users/mark/Desktop/security-ops-center/static/styles.css`

## Routes, pages, components removed or hidden

- Removed the visible `HQ 지원 제출 워크스페이스` block from the `지원근무자 현황` screen.
- Removed the visible workbook operation surface from Sentrix UI:
  - `컨텍스트 새로고침`
  - `ARLS artifact 다운로드`
  - `검토`
  - `적용`
  - file upload input
  - month/site/revision workbook operation summary area
- Old deep links using `#/ops/support?...mode=hq-submission...` no longer try to open a workbook workflow shell.
- Instead, those links resolve to the normal `지원근무자 현황` screen and show a compact ownership handoff message.

## What remained

- `지원근무자 현황` operational screen remains intact.
- Existing support request / support ticket / support worker status views remain intact.
- Overall / day / night mode switching remains intact.
- Site filter remains intact.
- Support roster and ticket state rendering remains intact.
- Backend support submission bridge logic was intentionally left untouched in this pass.

## Ownership notice added

- Added a compact handoff card on the support status screen.
- Message:
  - `지원근무 엑셀 다운로드/업로드/반영은 ARLS에서 수행합니다. Sentrix에서는 지원 요청 상태와 지원근무자 현황을 확인합니다.`
- Added one compact navigation action:
  - `ARLS에서 제출 열기`

## Old HQ submission route behavior

- `mode=hq-submission` hash/query context is treated as a legacy handoff entry.
- The URL hash is normalized back to the safe support screen route.
- The user lands on `지원근무자 현황`, not on an empty or broken workbook shell.
- A compact info toast explains that the Excel submission flow now belongs to ARLS.

## What was intentionally not changed

- No ARLS code was changed.
- No Sentrix backend support submission endpoints were removed in this pass.
- No support request/ticket/status truth logic was removed.
- No mobile-specific UI changes were made.
- No redesign was applied outside the support status area.
