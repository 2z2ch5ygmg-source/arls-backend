# Final Ownership Validation Summary

## ARLS visible ownership confirmed?
Yes.

Evidence:
- live ARLS HQ workspace endpoint responds for `SRS_Korea / 2026-03`
- live HQ workbook download works from ARLS
- live final Excel download works from ARLS
- ARLS frontend source still drives:
  - `/schedules/support-roundtrip/hq-workspace`
  - `/schedules/support-roundtrip/hq-roster-workbook`
  - `/schedules/support-roundtrip/hq-roster-upload/inspect`
  - `/schedules/support-roundtrip/hq-roster-upload/{batch_id}/apply`

## Sentrix visible ownership removed?
Yes.

Evidence:
- live Sentrix root HTML does not contain:
  - `opsSupportSubmissionWorkspace`
  - `HQ 지원 제출 워크스페이스`
  - `ARLS artifact 다운로드`
  - `컨텍스트 새로고침`
- Sentrix frontend still redirects legacy `mode=hq-submission` to ARLS
- Sentrix support roster page removes any legacy submission root before rendering

## Base schedule truth in ARLS confirmed?
Yes, with one limitation.

Confirmed:
- ARLS source status exists for `R692 / 2026-03`
- artifact metadata and final workbook are present
- final workbook downloads successfully

Limitation:
- this verification did not query ARLS production DB rows directly

## Support ticket truth in Sentrix confirmed?
Yes, at backend core level.

Confirmed locally with current code:
- tickets are created when scope is missing
- same logical scope updates the same ticket in place
- request count comes from the normalized ARLS snapshot
- latest roster snapshot replaces the old one
- `exact-filled => approved`
- `underfilled / overfilled => pending`
- confirmed workers remain stored even when state is `pending`

## Self-staff bridge behavior confirmed?
Not end-to-end.

Confirmed in isolation:
- ARLS bridge/materialization unit tests pass

Not confirmed end-to-end:
- current Sentrix Step 3B crashes before UPSERT / RETRACT outbox enqueue

## External worker exclusion confirmed?
Partially.

Confirmed locally:
- external workers count toward Sentrix fulfillment
- external-only exact fill can become `approved`
- confirmed workers keep the external rows
- no self-staff bridge targets were produced in the external-only scenario

Not fully confirmed end-to-end:
- because the Step 3B crash prevented fresh outbox emission, a live ARLS no-op bridge path was not observed

## Final unresolved issues if any
Yes.

1. Sentrix Step 3B side-effect band references undefined `get_ticket_status_label`, aborting support-roster notification and ARLS bridge enqueue.
2. Newly created pending scopes can skip notifications because the `meaningful_change` gate is too narrow.

## Final verdict
- ARLS is the only visible Excel ingress owner: confirmed
- Sentrix is the support state engine: confirmed at core backend level
- Full final integrated workflow acceptance: **not yet**

Blocking reason:
- Step 3B automation defects prevent final notification + ARLS UPSERT / RETRACT confirmation in a fresh end-to-end run
