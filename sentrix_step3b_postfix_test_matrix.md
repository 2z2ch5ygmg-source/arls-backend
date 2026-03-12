# Sentrix Step 3B Post-Fix Test Matrix

| scenario | ticket create/update | confirmed worker persistence | final state | notification event | ARLS outbox | PASS/FAIL |
| --- | --- | --- | --- | --- | --- | --- |
| HQ exact-filled support upload | created ticket `#1` | `자체 홍길동`, `자체 김영희` persisted | `approved` | fired (`ticket_status_updated`, `new_ticket_comment`, sync push 1) | `SUPPORT_ASSIGNMENT_APPROVED` -> targets `uuid-1`, `uuid-2` | PASS |
| HQ underfilled support upload | created ticket `#1` | `자체 홍길동` persisted | `pending` | fired (`new_ticket_comment`, sync push 1) | none | PASS |
| HQ overfilled support upload | created ticket `#1` | `자체 홍길동`, `자체 김영희`, `자체 박철수` persisted | `pending` | fired (`new_ticket_comment`, sync push 1) | none | PASS |
| External worker only | created ticket `#1` | `협력 외부A`, `협력 외부B` persisted | `approved` | fired (`ticket_status_updated`, `new_ticket_comment`, sync push 1) | none | PASS |
| Mixed external + self-staff | created ticket `#1` | `자체 홍길동`, `협력 외부A` persisted | `approved` | fired (`ticket_status_updated`, `new_ticket_comment`, sync push 1) | `SUPPORT_ASSIGNMENT_APPROVED` -> target `uuid-1` only | PASS |
| State reversal (approved -> pending) | same ticket updated in place (`ticket_id=1`) | latest snapshot kept only `자체 홍길동` | `pending` | fired (`ticket_status_updated`, `new_ticket_comment`, sync push 1) | prior `SUPPORT_ASSIGNMENT_APPROVED` + new `SUPPORT_ASSIGNMENT_RETRACTED` | PASS |
