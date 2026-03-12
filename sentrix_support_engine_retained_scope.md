# Sentrix Support Engine Retained Scope

## What Sentrix still owns functionally

- support request ticket truth
- support roster truth
- exact-filled / underfilled / overfilled reconciliation
- ticket state transitions
- support worker status screen and support operations UI
- notification fanout
- ARLS bridge emissions for valid approved self-staff
- ARLS retract emissions when support state becomes invalid
- lineage and audit preservation around support roster changes

## What Sentrix no longer owns

- workbook download initiation for HQ support submission
- workbook upload ingress for HQ support submission
- workbook inspect/review as an operator-facing workflow
- workbook apply as an operator-facing workflow
- Sentrix-visible HQ Excel processing workspace ownership

## Operator-facing vs internal-only after rollback

- Operator-facing:
  - `#/ops/support`
  - `GET /api/ops/support-requests`
  - `PATCH /api/ops/support-requests/{id}/confirmed-workers`
  - `GET /api/tickets`
  - `GET /api/ops/support-submissions/workspace`
    - now handoff/status only

- Internal-only or deprecated operator surface:
  - `GET /api/ops/support-submissions/download`
  - `PATCH /api/ops/support-submissions/inspect`
  - `PATCH /api/ops/support-submissions/{batch_id}/apply`
  - these no longer belong to the operator-facing Sentrix workflow
  - temporary internal access is limited to requests carrying `X-Sentrix-Bridge-Token`

## What ARLS is expected to call or provide after rollback

- ARLS should remain the Excel ingress and workbook processing owner.
- ARLS should provide artifact context and normalized support roster input, not hand workbook ownership to Sentrix UI.
- Expected upstream context includes:
  - `artifact_id`
  - `month`
  - `site`
  - `date`
  - `shift kind`
  - `ticket linkage / request count context`
  - normalized worker roster rows
  - `source_upload_batch_id`

## What reconciliation / notification / bridge logic remains in Sentrix

- confirmed worker normalization
- same-ticket update-in-place semantics
- replace semantics for confirmed worker rows
- request-count comparison against confirmed worker count
- approved vs pending recalculation
- audit log write
- ticket comment write on approval transitions
- realtime broker broadcast
- APNS push notifications
- ARLS support schedule bridge UPSERT / RETRACT outbox behavior
