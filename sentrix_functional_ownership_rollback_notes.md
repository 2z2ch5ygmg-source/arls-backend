# Sentrix Functional Ownership Rollback Notes

## Files changed

- `/Users/mark/Desktop/security-ops-center/app.py`
- `/Users/mark/Desktop/security-ops-center/static/app.js`
- `/Users/mark/Desktop/security-ops-center/static/index.html`

## Routes, pages, components deprecated or hidden

- The visible HQ workbook workflow was already removed from `지원근무자 현황` in Pass 1.
- Legacy `mode=hq-submission` support links still land on the Sentrix support status screen, but now only as an ownership handoff.
- Operator-facing workbook routes are no longer the functional owner surface in Sentrix:
  - `GET /api/ops/support-submissions/workspace`
  - `GET /api/ops/support-submissions/download`
  - `PATCH /api/ops/support-submissions/inspect`
  - `PATCH /api/ops/support-submissions/{batch_id}/apply`

## Endpoints internalized or redirected

- `GET /api/ops/support-submissions/workspace`
  - operator-facing behavior: returns a structured handoff/status payload with `operator_surface=false`
  - internal behavior: legacy bridge bootstrap remains temporarily available only when `X-Sentrix-Bridge-Token` matches the configured bridge token
- `GET /api/ops/support-submissions/download`
  - operator-facing behavior: returns `410` handoff JSON
  - internal behavior: temporary bridge proxy remains available only with the internal bridge token
- `PATCH /api/ops/support-submissions/inspect`
  - operator-facing behavior: returns `410` handoff JSON
  - internal behavior: temporary bridge proxy remains available only with the internal bridge token
- `PATCH /api/ops/support-submissions/{batch_id}/apply`
  - operator-facing behavior: returns `410` handoff JSON
  - internal behavior: temporary bridge proxy remains available only with the internal bridge token

## What support engine logic was preserved

- `PATCH /api/ops/support-requests/{id}/confirmed-workers` remains intact
- support ticket truth remains intact
- support roster truth remains intact
- exact-filled / pending reconciliation semantics remain intact
- ticket status transition updates remain intact
- notification fanout remains intact
- ARLS bridge outbox enqueue / resend / retract behavior remains intact
- audit logging remains intact

## What workbook ownership was removed

- Sentrix is no longer the operator-facing owner of:
  - workbook download
  - workbook upload
  - workbook inspect/review
  - workbook apply
- Sentrix now responds with explicit handoff metadata that points the operator back to ARLS

## Migration / cleanup required

- No database migration was needed.
- No roster/ticket/audit history was removed.
- Browser-only support submission transient state is now reset when:
  - opening the support status page
  - changing month
  - changing site/status/type filters
  - jumping back to today
- The ARLS handoff button now carries current month/site context in the handoff URL hash.

## What was intentionally not changed

- The support roster reconciliation engine was not removed.
- The support ticket state engine was not removed.
- Notifications were not removed.
- ARLS bridge / outbox logic was not removed.
- ARLS code was not changed in this pass.
- Support worker status operations UI was not redesigned in this pass.
