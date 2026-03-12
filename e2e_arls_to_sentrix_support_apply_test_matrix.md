# E2E Test Matrix: ARLS HQ Support Apply -> Sentrix Ticket/Status Update

## Test Context

- Site: `R692`
- Month: `2026-03`
- ARLS HQ roster batch: `5dae8cfb-3079-447b-b871-a339a576798f`
- Artifact: `sentrix-hq:SRS_KOREA:2026-03:R692:26a61b383dd4b21b`

| ID | Check | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| A | Run ARLS HQ support roster apply | ARLS apply executes for known site/month batch | Apply audit exists and result persisted for batch `5dae8cfb-3079-447b-b871-a339a576798f` | PASS |
| B | ARLS should not report false success | Full success only if Sentrix handoff succeeds | Batch stored `handoff_status=partial`, `status=failed`, `handoff_failed_count=33` | PASS |
| C | Sentrix ticket rows created/upserted for all required scopes | All required day/night scopes exist or update in Sentrix | Only `1` scope updated, `33` failed with `Sentrix support ticket scope를 찾지 못했습니다.` | FAIL |
| D | Support worker status screen updated | Sentrix support worker status should reflect all affected scopes | Sentrix actual support ticket truth contains only `1` `R692/2026-03` support ticket, so full screen update cannot happen | FAIL |
| E | Approved vs pending split correct | Exact-filled => 승인, mismatch => 승인대기 | ARLS calculated `auto_approved=5`, `approval_pending=29`, but Sentrix reflected only `1` pending scope | FAIL |
| F | Confirmed workers contain affiliation + name | Entered workers should appear in Sentrix confirmed workers | ARLS normalized rows contain values like `BK 홍길동`, `BK 몬치치`, but Sentrix successful scope had `confirmed_workers=[]`; auto-approved scopes did not update Sentrix | FAIL |
| G | Replace upload updates same ticket, not duplicate | Same scope should update existing ticket in place | Transport matched existing Sentrix ticket `id=12` and did not create a duplicate, but the visible ticket state is contaminated by prior/manual data so this is only transport-level evidence | PARTIAL PASS |

## Supporting Evidence

### ARLS batch result summary

- `affected_scope_count = 34`
- `handoff_success_count = 1`
- `handoff_failed_count = 33`
- `updated_scope_count = 1`
- `created_scope_count = 0`
- `auto_approved = 5`
- `approval_pending = 29`

### ARLS normalized worker evidence

For scope `R692:2026-03-01:day`:

- requested_count: `2`
- valid_filled_count: `2`
- worker 1: `bk 홍길동` -> `BK 홍길동`
- worker 2: `bk 몬치치` -> `BK 몬치치`
- target_status: `auto_approved`

### Sentrix actual ticket evidence

Only one actual `R692 / 2026-03` support ticket was present:

- ticket id: `12`
- type: `야간 지원 요청`
- work date: `2026-03-15`
- current status: `approved`
- current requested_count: `1`
- current confirmed_workers: `[{ affiliation: "bk", worker_name: "강민경" }]`

But the same ticket's `arls_hq_roster_handoff` metadata for current batch `7752d88f-ca35-4759-aefc-e8d0a2becc66` contains:

- `worker_entries = []`

So the current visible ticket state is not reliable evidence that the current workbook reflection succeeded.

## Overall Verdict

- Transport/handoff verification: `PASS`
- Full business reconciliation verification: `FAIL`
- Root reasons:
  - Sentrix actual ticket scope inventory is missing `33` scopes required by the uploaded workbook flow
  - the single matched scope is not clean evidence because its current visible state does not match the current handoff payload
