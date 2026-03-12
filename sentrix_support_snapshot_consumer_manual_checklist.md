# Sentrix Support Snapshot Consumer Manual Checklist

## Precheck
- Verify Sentrix health endpoint returns `200`.
- Verify the target tenant is `SRS_Korea`.
- Verify the target support request ticket already exists for each `site/date/shift` scope.

## Exact-Filled Case
- Apply an ARLS normalized snapshot where `valid_filled_count == ticket.request_count`.
- Confirm Sentrix ticket status becomes `approved`.
- Confirm support worker status view shows the filled workers.
- Confirm `confirmed_workers` contains affiliation + name rows.

## Underfilled Case
- Apply a later replace snapshot with fewer valid workers than `ticket.request_count`.
- Confirm the same ticket scope remains and is updated in place.
- Confirm Sentrix ticket status reverts to `pending`.
- Confirm only the latest confirmed workers remain on the ticket.

## Overfilled Case
- Apply a later replace snapshot with more valid workers than `ticket.request_count`.
- Confirm Sentrix ticket status stays `pending`.
- Confirm all current filled workers are still written to `confirmed_workers`.

## Replace Semantics
- Apply snapshot A for one scope.
- Apply snapshot B for the same `site/date/shift`.
- Confirm snapshot B replaces snapshot A instead of merging old workers forward.
- Confirm `support_roster_snapshots.is_current = 1` only for the latest snapshot.

## Duplicate Slot Case
- Apply a snapshot where the same worker appears twice in two separate slots.
- Confirm both slots are preserved in Sentrix for ARLS snapshot consumption.
- Confirm `valid_filled_count` reflects both slots.

## Missing Ticket Scope Case
- Apply a snapshot for a scope that has no Sentrix support ticket.
- Confirm Sentrix returns structured mismatch data.
- Confirm the response is JSON and does not report success for that scope.

## Audit / Lineage
- Inspect `support_roster_snapshots` for:
  - `artifact_id`
  - `revision`
  - `source_upload_batch_id`
  - `month_key`
  - `site_code`
  - `work_date`
  - `shift_kind`
- Inspect `support_roster_snapshot_entries` for the current snapshot rows.

## Notifications / Bridge
- Confirm approved scopes still emit the usual downstream side effects.
- Confirm reverted pending scopes still update ticket truth and broadcast status changes.
- Confirm no duplicate logical tickets are created for the same scope.
