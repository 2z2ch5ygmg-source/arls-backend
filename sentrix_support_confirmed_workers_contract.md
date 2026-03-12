# Sentrix Support Confirmed Workers Contract

## Confirmed Worker Schema
Each confirmed worker row written by the Sentrix reconciliation engine contains:

```json
{
  "affiliation": "string",
  "worker_name": "string",
  "raw_display": "string|null",
  "self_staff": true,
  "employee_id": "string|null",
  "employee_code": "string|null",
  "employee_name": "string|null",
  "slot_index": 1,
  "source_site_code": "string|null",
  "source_date": "YYYY-MM-DD|null",
  "source_shift_kind": "day|night"
}
```

## When Confirmed Workers Are Written
- Confirmed workers are written whenever Sentrix consumes a normalized support roster snapshot for a valid ticket scope.
- They are written even if the final ticket state is `pending`.
- They are also written for manual HQ confirmed-worker saves.

## Approved / Pending Rules
- Canonical `required_count` is the existing Sentrix ticket `request_count`.
- `valid_filled_count == request_count` => `approved`
- `valid_filled_count < request_count` => `pending`
- `valid_filled_count > request_count` => `pending`

## Replace Behavior
- HQ upload is replace, not merge.
- For one logical scope (`site/date/shift`), the latest roster snapshot replaces the previous current roster.
- Old workers are not merged forward.
- The latest snapshot is marked current in `support_roster_snapshots`.

## Ticket Lookup / Upsert Rules
- Lookup key:
  - `site_code`
  - `work_date`
  - `shift_kind`
- If exactly one Sentrix support ticket exists for the logical scope, Sentrix updates that ticket in place.
- If no ticket exists, Sentrix returns a structured mismatch.
- If multiple tickets exist for the same logical scope, Sentrix returns a duplicate-scope mismatch.
- Sentrix does not create a second logical ticket for the same scope in this consumer path.

## Missing Scope Mismatch Handling
- Missing or ambiguous ticket scopes are returned in structured JSON mismatch entries.
- The consumer response includes:
  - `scope_key`
  - `site_code`
  - `work_date`
  - `shift_kind`
  - `code`
  - `reason`
  - `upstream_ticket_scope_id` when available

## Counting Rules
- Each valid worker entry counts as `1`.
- Duplicate workers in separate slots count separately.
- Blank rows do not count.
- Invalid parsed rows do not count.
- Both self-staff and external workers count toward Sentrix fulfillment.

## Lineage / Audit Fields
- `artifact_id`
- `revision`
- `source_upload_batch_id`
- `month_key`
- `upstream_ticket_scope_id`
- `site_code`
- `work_date`
- `shift_kind`

## Output Guarantees
- Confirmed workers remain populated on the ticket payload after apply.
- Support worker status screens can render:
  - current status
  - confirmed workers
  - site/date/shift linkage
- Repeated uploads are deterministic under replace semantics.
