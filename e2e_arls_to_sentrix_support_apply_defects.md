# E2E Defects: ARLS HQ Support Apply -> Sentrix Ticket/Status Update

## DEF-01: Sentrix actual support ticket scopes are missing for most ARLS-required scopes

- Severity: High
- Area: ARLS -> Sentrix handoff / Sentrix ticket inventory

### Symptom

ARLS HQ roster apply for batch `5dae8cfb-3079-447b-b871-a339a576798f` processed `34` scopes, but Sentrix updated only `1` scope and failed `33` with:

- `Sentrix support ticket scope를 찾지 못했습니다.`

### Evidence

- ARLS shadow scope table `sentrix_support_request_tickets` contains `34` `R692 / 2026-03` scopes.
- Sentrix actual `tickets` truth contains only `1` `R692 / 2026-03` support request ticket.

### Impact

- Sentrix support worker status screen cannot reflect the uploaded workbook fully.
- Approved/pending transitions cannot be applied for most scopes.
- Confirmed worker values cannot be populated for the failed scopes.

### Likely Root Cause

The upstream base schedule -> Sentrix support ticket emission path did not create or sync actual Sentrix ticket scopes to match ARLS shadow support demand scopes.

## DEF-02: ARLS preview scope matching is based on ARLS-local shadow scope inventory, not Sentrix actual ticket truth

- Severity: High
- Area: ARLS HQ roster review/apply consistency

### Symptom

ARLS review rows and scope summaries show matched ticket context for many scopes, including:

- `matched_ticket = true`
- `current_status = approved/pending`

But at apply time, Sentrix handoff fails for those same scopes because Sentrix cannot find the ticket scope.

### Evidence

Example scope:

- `R692:2026-03-01:day`
- ARLS scope summary shows:
  - `matched_ticket = true`
  - `ticket_id = 8d002006-0701-4025-aba8-89ca9e1c4a05`
  - `target_status = auto_approved`
- Apply result for same scope:
  - `handoff_status = failed`
  - `handoff_message = Sentrix support ticket scope를 찾지 못했습니다.`

### Impact

- Operator review is misleading.
- The user can believe Sentrix already has corresponding scopes when it does not.
- Apply failure appears as a downstream surprise instead of a pre-apply inventory blocker.

### Recommended Fix Direction

Either:

1. Make ARLS preview explicitly distinguish `ARLS shadow scope matched` vs `Sentrix actual ticket scope matched`, or
2. Validate Sentrix actual scope existence before allowing HQ roster apply to proceed as a normal apply path.

## DEF-03: Approved vs pending split cannot be verified end-to-end because auto-approved scopes never reached Sentrix

- Severity: High
- Area: Business outcome verification

### Symptom

ARLS computed:

- `auto_approved = 5`
- `approval_pending = 29`

But Sentrix reflected only one scope, and that one scope remained pending.

### Evidence

ARLS normalized auto-approved scope example:

- `R692:2026-03-01:day`
- `request_count = 2`
- `valid_filled_count = 2`
- entered workers:
  - `BK 홍길동`
  - `BK 몬치치`

Sentrix did not contain the corresponding ticket scope, so no approved state or confirmed workers were updated for that scope.

### Impact

- The core business promise of HQ roster apply is not achieved.
- Exact-filled scopes do not become visible `승인` rows in Sentrix.

## DEF-04: Single transport-success scope is contaminated by existing/manual Sentrix state

- Severity: High
- Area: Verification integrity / replace semantics

### Symptom

ARLS reports one successful scope handoff for `R692:2026-03-15:night`, but the currently visible Sentrix ticket state for that scope does not match the current handoff payload.

### Evidence

Current Sentrix ticket `12` shows:

- `status = approved`
- `requested_count = 1`
- `confirmed_workers = [{ affiliation: "bk", worker_name: "강민경" }]`

But the same ticket's current ARLS handoff metadata shows:

- `source_upload_batch_id = 7752d88f-ca35-4759-aefc-e8d0a2becc66`
- `scope_key = R692:2026-03-15:night`
- `worker_entries = []`

So the current visible approved/confirmed state cannot have been produced by this current handoff payload alone.

### Impact

- The single “success 1건” result is misleading as a business success signal.
- Transport success and business reflection success are being conflated.
- End-to-end verification cannot treat this one scope as a clean pass.

### Likely Root Cause

One of these is happening:

1. manual Sentrix edits after ARLS handoff preserved/overwrote the visible scope state, or
2. Sentrix consumer replace semantics did not fully overwrite prior confirmed/status state for a matched scope.

### Recommended Fix Direction

- Separate transport success from effective state change in ARLS apply result messaging.
- Verify Sentrix consumer replace behavior for matched scopes with empty worker payloads.

## DEF-05: Confirmed worker population is blocked by missing scope inventory, not by roster normalization

- Severity: Medium
- Area: Worker payload propagation

### Symptom

ARLS normalized worker entries correctly, but Sentrix confirmed worker fields are not populated for the scopes that failed ticket lookup.

### Evidence

ARLS row normalization preserved affiliation + name fields:

- `bk 홍길동` -> `BK 홍길동`
- `bk 몬치치` -> `BK 몬치치`

Sentrix only updated one scope:

- ticket id `12`
- `confirmed_workers = []`

That successful scope had zero filled workers, so it does not prove worker propagation for filled scopes.

### Impact

- Verification item `confirmed workers fields contain affiliation + name` is not satisfied end-to-end.

### Recommended Fix Direction

Fix ticket scope inventory first, then re-run the same workbook on a scope with entered workers and verify `confirmed_workers` payload propagation.
