# E2E Verification Notes: ARLS HQ Support Apply -> Sentrix Ticket/Status Update

## Scope

- Verification only
- Target flow: ARLS HQ support roster apply -> Sentrix ticket/status update
- Target site/month: `R692` / `2026-03`
- Target ARLS HQ roster batch: `5dae8cfb-3079-447b-b871-a339a576798f`
- Target artifact: `sentrix-hq:SRS_KOREA:2026-03:R692:26a61b383dd4b21b`

## Verification Method

1. Checked ARLS batch audit/result persisted in production PostgreSQL.
2. Queried ARLS shadow support scope tables for the same site/month.
3. Queried Sentrix production SQLite data through App Service SCM command API.
4. Compared:
   - ARLS batch preview/apply result
   - ARLS shadow support scope inventory
   - Sentrix actual ticket/payload state

## Verified Facts

### 1. ARLS HQ roster apply did execute

- ARLS batch `5dae8cfb-3079-447b-b871-a339a576798f` has apply audit written.
- Persisted ARLS result:
  - `status = failed`
  - `blocking_issue_count = 0`
  - `valid_scope_count = 34`
  - `apply_result.handoff_status = partial`
  - `apply_result.handoff_message = 일부 scope만 Sentrix에 반영되었습니다.`

This confirms ARLS no longer reports a false full success for this batch.

### 2. ARLS built a real normalized roster snapshot

ARLS batch data contains normalized worker rows and scope summaries. Example for `R692:2026-03-01:day`:

- `target_status = auto_approved`
- `request_count = 2`
- `valid_filled_count = 2`
- worker rows preserved:
  - `bk 홍길동` -> normalized as `BK 홍길동`
  - `bk 몬치치` -> normalized as `BK 몬치치`

This confirms ARLS normalized roster data exists before handoff.

### 3. ARLS handoff result was partial, not successful

Persisted apply result for the target batch:

- `affected_scope_count = 34`
- `handoff_success_count = 1`
- `handoff_failed_count = 33`
- `updated_scope_count = 1`
- `created_scope_count = 0`
- `applied_scope_count = 1`
- `failed_scope_count = 33`
- repeated failure message:
  - `Sentrix support ticket scope를 찾지 못했습니다.`

This means the transport/handoff path ran, but downstream Sentrix scope resolution failed for most scopes.

### 4. ARLS shadow scope inventory exists for all required scopes

In ARLS table `sentrix_support_request_tickets`, production data for `R692 / 2026-03` contains `34` support request scopes.

This matches the ARLS HQ roster batch scope count.

### 5. Sentrix actual support ticket inventory does not match ARLS shadow scope inventory

In Sentrix production `tickets` + `tickets_template_fields`, support request rows for `R692 / 2026-03` resolve to only `1` real support ticket:

- Sentrix ticket id: `12`
- type: `야간 지원 요청`
- site: `R692`
- date: `2026-03-15`
- status: `pending`
- requested_count: `1`
- confirmed_workers: `[]`

No other `R692 / 2026-03` day/night support tickets were present in Sentrix actual ticket truth at verification time.

### 6. One scope was transport-matched, but it is not reliable proof of workbook reflection

The single transport-success scope was:

- `R692:2026-03-15:night`
- `sentrix_ticket_id = 12`
- `handoff_status = success`
- `handoff_message = Sentrix ticket updated`

However, this scope is not trustworthy as proof that the current HQ workbook was reflected end-to-end.

Current Sentrix ticket `12` now shows:

- `status = approved`
- `confirmed_workers = [{ affiliation: "bk", worker_name: "강민경" }]`
- `requested_count = 1`

But the same ticket payload also contains current ARLS handoff metadata:

- `source_upload_batch_id = 7752d88f-ca35-4759-aefc-e8d0a2becc66`
- `scope_key = R692:2026-03-15:night`
- `worker_entries = []`

That means the current visible ticket state does not align with the current ARLS batch payload for that scope.

The most likely interpretation is:

- the handoff matched one existing Sentrix scope,
- but the currently visible approved/confirmed-worker state was produced by prior or manual Sentrix-side edits,
- not by the current ARLS workbook handoff result itself.

## End-to-End Outcome

### Confirmed working

- ARLS HQ roster apply executes.
- ARLS builds normalized snapshot data.
- ARLS no longer claims full success when Sentrix handoff is incomplete.
- ARLS persists retryable, structured apply result state.
- For one matched Sentrix scope, ARLS was able to reach an existing Sentrix ticket without creating a duplicate.

### Not working end-to-end

- Sentrix does not have actual ticket scopes for `33/34` required scopes.
- Therefore Sentrix support worker status cannot reflect the full uploaded workbook.
- Approved vs pending split is not reflected in Sentrix for most scopes.
- The single transport-success scope is contaminated by existing/manual Sentrix state, so it is not valid proof of workbook reflection either.

## Primary Interpretation

The repaired ARLS apply/handoff path is functioning as a real handoff path.

The remaining end-to-end break is not “ARLS said success but did nothing” anymore.

The current blocking mismatch is:

- ARLS shadow support scope inventory: `34`
- Sentrix actual support ticket inventory for same site/month: `1`

That upstream inventory mismatch prevents full reconciliation in Sentrix.
