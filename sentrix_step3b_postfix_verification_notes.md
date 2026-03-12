# Sentrix Step 3B Post-Fix Verification Notes

## Verification Scope
- Sentrix backend only
- Post-fix targeted verification for Step 3B side effects after:
  - status-label helper restore
  - notification meaningful-change gate expansion

## Verification Method
- Ran a local temp-DB harness against `/Users/mark/Desktop/security-ops-center/app.py`
- Used the real Step 2B + Step 3B path:
  - `_consume_support_roster_scope_snapshots()`
  - ticket create/update
  - confirmed worker persistence
  - final state calculation
  - notification side-effect band
  - integration_outbox enqueue
- Replaced push/broker delivery with in-memory spies only to observe notification events without external side effects.

## Summary
- All 6 required scenarios passed.
- Previously failing pending scenarios now fire notifications correctly.
- Exact-filled / pending transition behavior remained correct.
- Confirmed workers remained persisted for pending states.
- ARLS outbox behavior matched expectations:
  - approved self-staff scopes -> UPSERT
  - pending scopes without prior approved bridge -> no outbox row
  - approved -> pending reversal -> RETRACT
  - external-only scopes -> no outbox row
  - mixed scopes -> self-staff subset only

## Important Observations
- New pending scopes now notify even when `status_changed = false`.
- Overfilled pending scopes also notify correctly.
- Identical repeated pending upload suppression was covered separately in the local regression test file and remained intact.
- Mixed external/self-staff approved scope emitted only the self-staff target into outbox payload.

## Verification Limits
- This pass was backend-targeted and local-harness based.
- It did not re-run full live ARLS UI wizard clicks or browser screenshots.
- Notification delivery was verified as broker/push invocation, not by checking real device receipt.
