# Sentrix UI Rollback Pass 1 Manual Checklist

## Support screen

- Open Sentrix desktop and go to `지원근무자 현황`.
- Confirm overall / 주간 / 야간 controls still work.
- Confirm the site filter still renders and changes support status scope.
- Confirm the monthly support summary strip still renders.

## Workbook ownership removal

- Confirm there is no visible `HQ 지원 제출 워크스페이스` card.
- Confirm there is no visible workbook file input.
- Confirm there are no visible buttons for:
  - `컨텍스트 새로고침`
  - `ARLS artifact 다운로드`
  - `검토`
  - `적용`
- Confirm there are no empty gaps or dead placeholder containers where the workbook UI used to be.

## Ownership handoff

- Confirm a compact notice is visible explaining that Excel download/upload/apply is handled in ARLS.
- Confirm the notice does not look like a broken warning block.
- Click `ARLS에서 제출 열기`.
- Confirm it opens the ARLS handoff path instead of triggering any Sentrix workbook action.

## Legacy route behavior

- Open an old deep link such as:
  - `#/ops/support?mode=hq-submission&month=2026-03&site=R692`
- Confirm the user is taken to the normal support status screen.
- Confirm the old workflow shell does not appear.
- Confirm a compact info message/toast explains that workbook submission now lives in ARLS.

## Operational integrity

- Open a support request detail row.
- Confirm support status/detail/ticket behavior still works.
- Confirm support worker status views and existing operational actions still render.
- Confirm no disabled workbook buttons remain anywhere in the visible support screen.
