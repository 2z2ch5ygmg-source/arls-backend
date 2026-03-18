# Sentrix Notifications Map

## Executive Summary

- Notification infrastructure exists locally, but the active Sentrix apply path mostly reports notification counts coming back from an external handoff response.
- The repo contains Sentrix-specific recipient resolution, audit persistence, and push update helpers.
- No in-repo caller was found for those Sentrix-specific write helpers.
- There is no literal `meaningful_change` flag in the repo; the local design uses snapshot-signature change detection instead.

## 1. Notification Entry Points

### In-app notification read APIs
- `app/routers/v1/notifications.py`

Routes:
- `GET /api/v1/notifications/in-app`
- `POST /api/v1/notifications/in-app/{notification_id}/read`
- `POST /api/v1/notifications/in-app/read-all`

What they do:
- read from `in_app_notifications`
- mark notifications read
- expose unread counts

These are read-model APIs, not Sentrix-specific notification writers.

### Generic push transport
- `app/services/push_notifications.py:318-363`
  - `send_push_notification_to_users`

What it does:
- resolves push devices for a user ID set
- sends FCM messages
- returns target/sent/failed counts

## 2. Sentrix-Specific Helper Functions

### Status label mapping
- `app/routers/v1/schedules.py:_normalize_sentrix_hq_roster_final_state`
- `app/routers/v1/schedules.py:_extract_sentrix_ticket_hq_roster_status`
- `app/routers/v1/schedules.py:_get_support_roster_hq_ticket_status_label`

These helpers map:
- `auto_approved` to approved
- `approval_pending` to approval pending
- cancelled/rejected/deleted/unavailable/retracted labels
- `upload_blocked` to a blocked label in UI review rows

### Recipient resolution
- `app/routers/v1/schedules.py:_resolve_sentrix_hq_notification_user_ids`

Recipients:
- always includes `hq_admin` and `developer`
- includes `supervisor` and `vice_supervisor` only when site-scoped to the same site

### Notification audit persistence
- `app/routers/v1/schedules.py:_insert_sentrix_hq_notification_audit`
- `app/routers/v1/schedules.py:_update_sentrix_hq_notification_audit_after_push`

Audit table:
- `migrations/013_sentrix_hq_postprocessing.sql:95-121`
  - `sentrix_support_notification_audit`

## 3. Notification Body Generation

### What exists
- Generic push sender accepts `title`, `body`, and `data`.
- Notification audit stores a `message` column and `payload_json`.

### What was not found
- No dedicated Sentrix-specific notification body builder function.
- No in-repo caller building and inserting Sentrix notification messages for the new HQ roster flow.

### Practical reading
- The repo models where notification messages would be stored and pushed.
- The active message generation likely moved to the external Sentrix handoff owner.

## 4. `meaningful_change` Gate Logic

### What was searched
- No `meaningful_change` symbol exists in the repo.

### Actual local change gate
- `app/routers/v1/schedules.py:_build_sentrix_hq_snapshot_signature`
- `app/routers/v1/schedules.py:_persist_sentrix_hq_roster_snapshot`

Rule:
- `changed = previous_signature != current_signature`

Signature inputs:
- request count
- valid/invalid filled counts
- normalized ticket state
- normalized confirmed worker entries

### Important caveat
- No in-repo caller was found for `_persist_sentrix_hq_roster_snapshot`.
- The local change gate is designed and implemented, but not wired from the current active apply path in this repo.

## 5. Active Apply-Path Notification Signals

### Current result mapper
- `app/routers/v1/schedules.py:_build_sentrix_support_roster_apply_result_from_handoff`

What it consumes from external handoff response:
- `notifications_created`
- `notification_sites`
- `push_sent`
- `push_failed`

### Practical reading
- The active runtime path trusts external Sentrix response counters rather than performing the notification writes locally.

## 6. In-App Notification Storage

### Schema
- `migrations/013_sentrix_hq_postprocessing.sql:1-21`
  - `in_app_notifications`
  - includes `category`, `message`, `dedupe_key`, `payload_json`, `read_at`

### Reader
- `app/routers/v1/notifications.py`

### Ownership reading
- This repo still owns the notification inbox table and read API.
- It does not obviously own the active Sentrix-specific write path for the new roster flow anymore.

## 7. What Is Live vs Transitional

### Live
- `in_app_notifications` inbox APIs
- generic FCM push transport
- external handoff response counters being surfaced in apply results

### Transitional / orphaned
- `_resolve_sentrix_hq_notification_user_ids`
- `_insert_sentrix_hq_notification_audit`
- `_update_sentrix_hq_notification_audit_after_push`
- snapshot-signature change detection as a would-be meaningful-change gate

## 8. Bottom Line

- Notification infra is present locally.
- Sentrix-specific notification ownership is described locally but not clearly executed locally anymore.
- For second-stage review, the important boundary question is whether notification creation should stay external to this repo or be re-wired back into the local snapshot/audit/push pipeline.
