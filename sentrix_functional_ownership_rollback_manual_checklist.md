# Sentrix Functional Ownership Rollback Manual Checklist

## Operator flow

- Open Sentrix desktop `지원근무자 현황`.
- Confirm workbook upload/download/review/apply controls are not visible.
- Confirm the compact ARLS ownership handoff card is visible.
- Click `ARLS에서 제출 열기`.
- Confirm ARLS opens instead of any Sentrix workbook action starting.

## Legacy deep link

- Open a legacy route such as:
  - `#/ops/support?mode=hq-submission&month=2026-03&site=R692`
- Confirm Sentrix opens the normal support status screen.
- Confirm a compact info toast explains that workbook processing lives in ARLS.
- Confirm there is no workbook shell in Sentrix.

## API ownership

- Call `GET /api/ops/support-submissions/workspace?month=2026-03` as an authenticated HQ user.
- Confirm the response is `200` JSON.
- Confirm it returns handoff/status metadata, not workbook ownership state.
- Confirm `operator_surface=false`.

- Call `GET /api/ops/support-submissions/download?month=2026-03` as an authenticated HQ user.
- Confirm the response is `410` JSON.
- Confirm the payload says workbook download is handled in ARLS.

- Call `PATCH /api/ops/support-submissions/inspect` as an authenticated HQ user.
- Confirm the response is `410` JSON.

- Call `PATCH /api/ops/support-submissions/{batch_id}/apply` as an authenticated HQ user.
- Confirm the response is `410` JSON.

## Support engine retained

- Open a support request detail in Sentrix.
- Update confirmed workers through the retained support operations flow.
- Confirm ticket status still recalculates.
- Confirm exact-filled / pending logic still behaves normally.
- Confirm notifications still fire where expected.
- Confirm ARLS bridge/outbox behavior still logs for approved or invalidated support assignments.
