# Sentrix UI Ownership Contract

## What Sentrix visibly owns after rollback

- `지원근무자 현황` as an operational monitoring screen
- support request state views
- support ticket state views
- support worker roster/status result rendering
- support-related status and notification visibility already present in Sentrix

## What Sentrix no longer visibly owns

- workbook download
- workbook upload
- workbook inspect/review
- workbook apply/reconcile entrypoint
- HQ Excel submission workspace
- workbook context bootstrap controls

## Handoff message text

- Primary message:
  - `지원근무 엑셀 다운로드/업로드/반영은 ARLS에서 수행합니다. Sentrix에서는 지원 요청 상태와 지원근무자 현황을 확인합니다.`
- Secondary guidance:
  - `ARLS > 보고 > 지원근무자 제출(월초)에서 workbook을 처리하고, Sentrix에서는 현재 범위의 지원 요청 상태와 확정 근무자를 확인합니다.`

## Deep link / redirect behavior

- Legacy deep links such as `mode=hq-submission` must not render a dead workbook page.
- They resolve to the normal Sentrix support status screen.
- Sentrix shows a compact ownership handoff message/toast.
- Sentrix does not expose workbook controls on that landing state.

## Retained screens / components

- `지원근무자 현황`
- overall / day / night mode controls
- site filter
- support request list/calendar/detail views
- support ticket and support status rendering

## Removed or hidden screens / components

- visible `HQ 지원 제출 워크스페이스`
- workbook upload panel
- workbook download panel
- review/apply control panel
- visible workbook context bootstrap area
