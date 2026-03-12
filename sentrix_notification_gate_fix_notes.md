# Sentrix Support-Roster Notification Gate Fix - Pass 2

## Files Changed
- `/Users/mark/Desktop/security-ops-center/app.py`
- `/Users/mark/Desktop/security-ops-center/test_sentrix_support_roster_side_effects.py`

## Problem
- Step 3B notification gate relied too narrowly on:
  - `status_changed`
  - `worker_change_messages`
  - `previous_request_count != request_count`
- This missed first-time pending scopes and pending-to-pending replace uploads where confirmed worker roster changed materially but status/request count did not.

## What Changed
- Added a stable worker-roster signature serializer for support-roster side effects.
- Expanded `meaningful_change` to fire when any of these are true:
  - status changed
  - request_count changed
  - worker change messages exist
  - confirmed worker roster signature changed
  - worker count changed
  - self-staff bridge candidate set changed
  - scope was newly created
- Added `scope_created` metadata from the roster consumer into the Step 3B side-effect band.

## Dedupe Behavior
- Identical repeated pending uploads no longer notify.
- A new snapshot UUID alone does not force notification.
- Notification only fires when business-meaningful roster content changes.

## Regression Coverage Added
- newly created pending scope with filled workers -> notification fires
- existing pending scope with roster change -> notification fires
- identical pending re-upload -> suppressed
- approved path still not broken
- approved -> pending still not broken
- notification-body failure isolation still preserved

## Validation
- `python3 -m py_compile /Users/mark/Desktop/security-ops-center/app.py /Users/mark/Desktop/security-ops-center/test_sentrix_support_roster_side_effects.py`
- `python3 -m unittest -q /Users/mark/Desktop/security-ops-center/test_sentrix_support_roster_side_effects.py`

## Intentionally Not Changed
- notification audience/message rules
- Step 2B ticket/roster truth semantics
- ARLS code
- frontend/UI
