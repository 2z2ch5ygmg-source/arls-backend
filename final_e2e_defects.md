# Final E2E Defects

## 1. Sentrix support-roster side effect crashes before notification and bridge enqueue
- Severity: High
- Product area: Sentrix backend Step 3B
- File:
  - `/Users/mark/Desktop/security-ops-center/app.py:11401`
  - `/Users/mark/Desktop/security-ops-center/app.py:12096`

### Symptom
- Local integrated reconciliation logs:
  - `[support-roster.consume] side-effect failed ticket_id=... error=NameError:name 'get_ticket_status_label' is not defined`

### Exact break point
- `_build_support_roster_notification_body()` calls `get_ticket_status_label(...)` at `/Users/mark/Desktop/security-ops-center/app.py:11411`
- There is no matching function definition in the file
- `_consume_support_roster_scope_snapshots()` catches the exception at `/Users/mark/Desktop/security-ops-center/app.py:12096-12108` and continues

### Impact
- Step 2B core still succeeds:
  - ticket create/update
  - snapshot persistence
  - confirmed worker storage
  - approved/pending calculation
- Step 3B does not complete:
  - support-roster notification body is not built
  - `send_apns_to_users(...)` support notification path does not run
  - `enqueue_hr_approval_outbox_event(...)` UPSERT / RETRACT path does not run
  - fresh ARLS bridge emission cannot be confirmed end-to-end

### Affected scenarios
- 2. HQ exact-filled support upload
- 3. HQ underfilled support upload
- 5. External worker only
- 6. Mixed external + self-staff
- 7. State reversal
- multi-site notification grouping check

## 2. Newly created pending scopes can skip notifications entirely
- Severity: Medium
- Product area: Sentrix backend Step 3B
- File:
  - `/Users/mark/Desktop/security-ops-center/app.py:11533-11536`

### Symptom
- Overfilled local scenario created a pending ticket with 3 confirmed workers
- Result:
  - `broadcast_events = []`
  - `push_sync_calls = 0`
  - `push_async = 0`

### Exact break point
- `meaningful_change` is currently computed as:
  - `status_changed`
  - `worker_change_messages`
  - `previous_request_count != request_count`
- On a newly created scope that is already `pending` before and after reconciliation, the current gate can stay false even though confirmed workers changed from empty to populated

### Impact
- HQ reconciliation can succeed without sending the required `[HQ] 지원근무자 업데이트 발생` notification
- This is most visible on initial `underfilled` / `overfilled` pending scopes

### Affected scenarios
- 4. HQ overfilled support upload
- likely also initial underfilled pending scopes with no status transition

## Verification limitations (not product defects)
- No browser screenshots were captured in this shell-only session
- Sentrix production `hq_admin / Admin123!` login returned `401`, so live Sentrix UI/API verification was limited
