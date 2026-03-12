# Sentrix Step 3B Post-Fix Test Matrix

| scenario | ticket create/update | confirmed worker persistence | final state | notification event fired | ARLS UPSERT / RETRACT outbox emitted | PASS/FAIL |
| --- | --- | --- | --- | --- | --- | --- |
| HQ exact-filled support upload | update path completed | 2 workers persisted | `approved` | yes (`new_ticket_comment`, push path invoked) | yes, approval bridge emitted (`SUPPORT_ROSTER_BRIDGE_UPSERT`) | PASS |
| HQ underfilled support upload | update path completed | 1 worker persisted | `pending` | yes (`new_ticket_comment`, push path invoked) | yes, retract emitted because prior approved reflection existed (`SUPPORT_ROSTER_BRIDGE_RETRACT`) | PASS |
| HQ overfilled support upload | update path completed | 3 workers persisted | `pending` | yes (`new_ticket_comment`, push path invoked) | no, no approved bridge remained active | PASS |
| External worker only | update path completed | 2 external workers persisted | `approved` | yes (`new_ticket_comment`, push path invoked) | no, external workers are excluded from ARLS bridge | PASS |
| Mixed external + self-staff | update path completed | 2 workers persisted | `approved` | yes (`new_ticket_comment`, push path invoked) | yes, UPSERT emitted for self-staff subset only | PASS |
| State reversal (approved -> pending) | same scope updated in place | latest snapshot kept only current worker set | `pending` | yes (`new_ticket_comment`, push path invoked) | yes, RETRACT emitted for prior approved self-staff reflection | PASS |
