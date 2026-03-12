# ARLS Support-Origin Truth Contract

## Lineage fields
- `source = sentrix_support_ticket`
- `source_ticket_id`
- `source_ticket_uuid`
- `source_ticket_state`
- `source_action_last_seen` / `source_action`
- `source_upload_batch_id` or snapshot revision lineage
- `tenant`
- `site`
- `work_date`
- `shift_kind`
- `employee_id`
- `self_staff = true`

## UPSERT rules
- Accept only canonical Sentrix support payloads.
- Require:
  - support source
  - ticket id
  - site identity
  - date
  - shift kind
  - employee id
  - employee display name
  - `self_staff = true`
- UPSERT is valid only when ticket state is approved.
- Same ticket + same employee + same site + same date + same shift kind updates in place.

## RETRACT rules
- Locate rows by support lineage identity.
- Owned support-origin rows are removed from active truth.
- Linked base/manual rows are preserved and only the materialization record is retracted.
- Repeated RETRACT is safe.

## Same-shift dedupe rules
- Same ticket lineage => update, not duplicate.
- Existing base/manual same-shift row => keep one visible schedule row and link the materialization.
- Different Sentrix lineage already owning the same slot => block.

## Coexistence rules
- Base/manual/support-origin lineages coexist.
- Day and night remain independent.
- Support-origin writes never overwrite unrelated base/manual rows.

## Date attribution rules
- A support assignment for a given work date remains visible in that same work date context.
- Overnight/night support is not shifted to the next visible day.
