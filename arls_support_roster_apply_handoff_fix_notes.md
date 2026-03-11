# ARLS HQ Support Roster Apply -> Sentrix Handoff Repair - Pass 1

## Files changed
- `/Users/mark/Desktop/rg-arls-dev/app/config.py`
- `/Users/mark/Desktop/rg-arls-dev/app/schemas.py`
- `/Users/mark/Desktop/rg-arls-dev/app/routers/v1/schedules.py`
- `/Users/mark/Desktop/rg-arls-dev/frontend/js/app.js`
- `/Users/mark/Desktop/rg-arls-dev/tests/test_schedule_support_roundtrip.py`
- `/Users/mark/Desktop/rg-arls-dev/arls_support_roster_apply_handoff_fix_notes.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_support_roster_apply_handoff_manual_checklist.md`
- `/Users/mark/Desktop/rg-arls-dev/arls_to_sentrix_roster_snapshot_contract.md`

## What was broken
- ARLS HQ roster apply could finish local batch processing without proving that Sentrix had actually updated.
- The apply result shape was too weak for real downstream troubleshooting.
- Frontend messaging treated apply as broadly successful unless it was hard-blocked.
- Handoff payload lineage and worker provenance were not exposed as a formal contract.

## What was restored
- ARLS HQ roster apply now builds a canonical normalized support roster snapshot per site/date/shift scope.
- ARLS now posts that snapshot to a dedicated Sentrix internal handoff endpoint instead of stopping at local preview/apply semantics.
- ARLS full success now requires both:
  - ARLS local apply preconditions passed
  - Sentrix handoff succeeded
- ARLS partial/failure results are preserved with:
  - `artifact_id`
  - `source_upload_batch_id`
  - `retry_token`
  - handoff success/failure counts
  - affected sites/dates/scope counts
  - per-scope handoff results

## Handoff model
- Source batch remains the retry anchor.
- ARLS sends normalized worker rows so Sentrix does not have to re-parse raw Excel.
- Sentrix receives:
  - workbook lineage
  - scope granularity
  - normalized worker entries
  - provenance per worker cell
- Sentrix remains the owner of:
  - request-count truth
  - approved/pending calculation
  - confirmed worker persistence
  - notifications
  - ARLS bridge follow-up

## Frontend behavior corrected
- HQ roster apply result now distinguishes:
  - full success
  - partial success
  - blocked
  - handoff failure
- Scope result rows now display Sentrix handoff status and ticket id instead of showing a misleading generic apply state.
- Toasts no longer imply success when handoff only partially succeeded or failed.

## Functional notes
- Retry does not require re-upload. The same batch can be applied again when the prior result was failed/partial.
- Blocked results still preserve preview and do not emit Sentrix handoff.
- This pass does not move Sentrix state logic into ARLS.

## Intentionally not changed
- No broad ARLS schedule UI redesign
- No Sentrix ticket-generation logic migration into ARLS
- No change to base monthly upload ownership
- No duplication of Sentrix exact-filled / pending state engine inside ARLS
