# Sentrix Support-Roster Side-Effect Band Fix - Pass 1

## Files Changed
- `/Users/mark/Desktop/security-ops-center/app.py`
- `/Users/mark/Desktop/security-ops-center/test_sentrix_support_roster_side_effects.py`

## What Was Fixed
- Restored missing `get_ticket_status_label()` in Sentrix backend by reusing the existing support-request status normalization/label rules and extending them for `needs_info`, `done`, and `deleted`.
- Reconnected `_build_support_roster_notification_body()` so Step 3B notification body generation no longer crashes with `NameError`.
- Added stage-specific notification failure isolation so a notification-body or notification-dispatch failure is logged with exact stage/context and does not block ARLS outbox enqueue.

## Side-Effect Band Behavior
- `_emit_support_roster_update_side_effects()` now:
  - builds support-roster notification body without missing helper failure
  - logs `SUPPORT_ROSTER_SIDE_EFFECT_FAILED` with stage/context on notification-stage failure
  - continues to ARLS bridge enqueue logic after notification failure isolation
- Step 2B core semantics were intentionally left unchanged:
  - ticket create/update
  - request_count source
  - roster replace semantics
  - approved/pending calculation
  - confirmed worker persistence

## Regression Coverage Added
- approved side-effect path: notification + UPSERT enqueue
- pending side-effect path: notification + RETRACT enqueue
- notification body label generation
- notification-body failure isolation still allowing outbox enqueue

## Validation Run
- `python3 -m py_compile /Users/mark/Desktop/security-ops-center/app.py /Users/mark/Desktop/security-ops-center/test_sentrix_support_roster_side_effects.py`
- `python3 -m unittest -q /Users/mark/Desktop/security-ops-center/test_sentrix_support_roster_side_effects.py`

## Intentionally Not Changed
- Sentrix frontend
- ARLS code
- raw workbook parsing
- Step 2B ticket/roster truth rules
- notification audience/message business rules
