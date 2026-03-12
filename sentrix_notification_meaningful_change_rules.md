# Sentrix Notification Meaningful-Change Rules

## Old Gate Logic
- notify if:
  - `status_changed`
  - OR `worker_change_messages` exists
  - OR `previous_request_count != request_count`

## Why It Was Too Narrow
- `worker_change_messages` returned empty when previous roster was empty and current roster became populated.
- A new pending scope could therefore skip notification if:
  - status stayed `pending`
  - request_count stayed the same
  - worker roster changed from empty -> populated

## New Gate Logic
- notify if any of the following is true:
  - status changed
  - request_count changed
  - worker change messages exist
  - confirmed worker roster signature changed
  - worker count changed
  - self-staff bridge candidate set changed
  - scope was newly created

## Roster Change Conditions Counted As Meaningful
- empty -> populated confirmed roster
- populated -> empty confirmed roster
- changed worker list
- changed worker order / slot placement
- changed affiliation / raw display / employee resolution
- changed self-staff vs external mix
- changed approved self-staff bridge candidate set

## Dedupe / Suppression Rules
- identical repeated upload stays suppressed if:
  - status unchanged
  - request_count unchanged
  - confirmed worker roster signature unchanged
  - bridge candidate set unchanged
  - scope is not newly created
- snapshot UID change alone does not trigger notification
