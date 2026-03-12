# Sentrix Support Snapshot Consumer Fix Notes

## Files Changed
- `/Users/mark/Desktop/security-ops-center/app.py`

## What Was Fixed
- Added a real normalized support roster snapshot consumer for Sentrix support ticket reconciliation.
- Stopped the internal Sentrix apply path from bouncing the request back to ARLS.
- Added snapshot audit storage for replace-based roster updates.
- Moved manual confirmed-worker save onto the same reconciliation path so manual and ARLS-driven updates use the same state rules.

## Reconciliation Repairs
- Canonical required count now comes from the existing Sentrix ticket payload.
- Approval rule is now exact match only:
  - `valid_filled_count == request_count` => `approved`
  - `valid_filled_count < request_count` => `pending`
  - `valid_filled_count > request_count` => `pending`
- Replace semantics now overwrite the current roster snapshot per `site/date/shift` logical scope instead of merging stale workers forward.
- Confirmed workers are written even when the ticket remains pending.

## Consumer Input
- The consumer now accepts normalized scope snapshots built from ARLS handoff payloads.
- Supported shapes:
  - `scope_snapshots`
  - `scopeSnapshots`
  - `scopes`
  - `review_rows` / `reviewRows`
- Direct ARLS handoff `worker_entries` are now consumed correctly.

## Ticket Lookup / Upsert Rules
- Sentrix matches the logical ticket scope by:
  - `site_code`
  - `work_date`
  - `shift_kind`
- If one matching ticket exists, it is updated in place.
- If no matching ticket exists, the scope is returned as a structured mismatch.
- If multiple matching tickets exist, the scope is returned as a duplicate-scope mismatch.
- The engine does not create duplicate ticket scopes.

## Snapshot Audit Storage
- Added `support_roster_snapshots`
- Added `support_roster_snapshot_entries`
- Stored audit fields include:
  - old status
  - new status
  - request count
  - valid filled count
  - invalid filled count
  - artifact id
  - revision
  - source upload batch id
  - month
  - site/date/shift scope
  - previous workers
  - next workers

## Confirmed Workers Repair
- Confirmed worker rows now preserve:
  - `affiliation`
  - `worker_name`
  - `raw_display`
  - `self_staff`
  - `employee_id`
  - `employee_code`
  - `employee_name`
  - `slot_index`
  - `source_site_code`
  - `source_date`
  - `source_shift_kind`
- Duplicate workers in separate slots are preserved and count separately for ARLS snapshot consumption.

## Manual Save Path
- `PATCH /api/ops/support-requests/{id}/confirmed-workers` now uses the shared reconciliation helper.
- Manual save still dedupes repeated `affiliation + worker_name` pairs.
- Legacy tickets without an explicit request count still fall back to the current confirmed count baseline for manual saves only.

## Internal Apply Path
- `POST /api/ops/support-submissions/{batch_id}/apply`
  - operator path: remains non-owner / blocked
  - internal bridge path: now consumes normalized snapshots directly
- If the internal payload is missing normalized snapshots, Sentrix now returns structured JSON error instead of pretending the apply succeeded.

## What Was Intentionally Not Changed
- No Sentrix UI redesign in this pass.
- No ARLS UI changes in this pass.
- No removal of ticket truth, reconciliation engine, notifications, or ARLS bridge side effects.
- No raw workbook parsing was reintroduced in Sentrix.
